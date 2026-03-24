"""
Main pipeline orchestrator — runs all 6 steps linearly.
Each step can fail independently without killing the pipeline.
"""

from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table   import Table

from config import PipelineConfig, STATIONS, STATION_MAP, StationConfig
from src.database import (init_db, insert_clean_telemetry, insert_forecast,
                            insert_alert, insert_delivery_log,
                            insert_delivery_metrics,
                            start_pipeline_run, finish_pipeline_run,
                            get_latest_clean_for_station,
                            get_clean_history_for_station)
from src.ingestion       import ingest_all_stations
from src.weather_clients import TomorrowIOClient, OpenMeteoClient, NASAPowerClient
from src.healing         import RuleBasedFallback, HealingAgent
from src.database        import insert_healing_log
from src.forecasting     import create_forecast_model, PersistenceModel, run_forecast_step
from src.downscaling     import IDWDownscaler
from src.translation     import get_provider, generate_advisory
from src.delivery        import MultiChannelDelivery, DEFAULT_RECIPIENTS, DeliveryChannel
from src.models          import RawReading, CleanReading, Forecast, Advisory, DeliveryLog

log = logging.getLogger(__name__)
console = Console()


class WeatherPipeline:
    def __init__(self, config: PipelineConfig, live_delivery: bool = False):
        self.config        = config
        self.live_delivery = live_delivery
        self.conn          = init_db(config.db_path)
        self.run_id        = str(uuid.uuid4())

        # Clients
        self.tomorrow_io   = TomorrowIOClient(config.tomorrow_io_key)
        self.open_meteo    = OpenMeteoClient()
        self.nasa_power    = NASAPowerClient()

        # Processing components
        self.rule_healer   = RuleBasedFallback()
        self.forecast_model = create_forecast_model(config.models_dir)
        self.persistence   = PersistenceModel()
        self.downscaler    = IDWDownscaler(self.nasa_power)
        self.advisory_prov = get_provider(config.anthropic_key, config.translation)

        config.delivery.live_delivery = live_delivery
        channels = [DeliveryChannel.CONSOLE]
        if live_delivery:
            channels.extend([DeliveryChannel.SMS])
        self.delivery = MultiChannelDelivery(config.delivery, channels)

    # ------------------------------------------------------------------
    # Step 1: Ingest
    # ------------------------------------------------------------------
    async def step_ingest(self) -> List[Dict[str, Any]]:
        mode = self.config.weather.ingestion_source
        label = "real (IMD)" if mode == "real" else "synthetic"
        console.print(f"[bold blue]Step 1:[/bold blue] Ingesting {label} telemetry...")
        readings = await ingest_all_stations(self.config, self.conn)

        # Source breakdown
        sources: Dict[str, int] = {}
        for r in readings:
            s = r.get("source", "unknown")
            sources[s] = sources.get(s, 0) + 1
        source_str = " | ".join(f"{k}:{v}" for k, v in sorted(sources.items()))

        faults = sum(1 for r in readings if r.get("fault_type"))
        console.print(f"  [green]✓[/green] {len(readings)} readings | {source_str} | {faults} faults")
        # Validate stage output
        readings = [RawReading(**r).model_dump() for r in readings]
        return readings

    # ------------------------------------------------------------------
    # Step 2: Heal
    # ------------------------------------------------------------------
    async def _fetch_references(self, raw_readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fetch Tomorrow.io references in batches of 10, NASA POWER fallback."""
        station_ids = [r["station_id"] for r in raw_readings if r["station_id"] in STATION_MAP]
        references: Dict[str, Any] = {}
        batch_size = 10
        for i in range(0, len(station_ids), batch_size):
            batch = station_ids[i:i + batch_size]
            results = await asyncio.gather(*[
                self.tomorrow_io.get_current(STATION_MAP[sid].lat, STATION_MAP[sid].lon)
                for sid in batch
            ], return_exceptions=True)
            for sid, res in zip(batch, results):
                references[sid] = res if isinstance(res, dict) else None
            if i + batch_size < len(station_ids):
                await asyncio.sleep(0.2)
        return references

    async def _rule_based_heal(self, raw_readings: List[Dict[str, Any]],
                                references: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Original three-phase healing: fault-based → NULL-fill → cross-validate."""
        clean = []
        skipped = 0

        for reading in raw_readings:
            ref = references.get(reading["station_id"])
            fault = reading.get("fault_type")

            # Phase 1: Fault-based healing (synthetic faults only)
            if fault is not None:
                healed = self.rule_healer.heal(reading, ref)
                if healed is None:
                    station = STATION_MAP.get(reading["station_id"])
                    if station:
                        nasa_ref = await self.nasa_power.get_current(station.lat, station.lon)
                        if nasa_ref:
                            healed = self.rule_healer.heal(reading, nasa_ref)
                            ref = ref or nasa_ref
                    if healed is None:
                        skipped += 1
                        continue
            else:
                healed = dict(reading)

            # Phase 2+3: Cross-validate against reference (all readings)
            if ref is not None:
                healed = self.rule_healer.cross_validate(healed, ref)
            else:
                station = STATION_MAP.get(reading["station_id"])
                if station and fault is None:
                    nasa_ref = await self.nasa_power.get_current(station.lat, station.lon)
                    if nasa_ref:
                        healed = self.rule_healer.cross_validate(healed, nasa_ref)
                if "quality_score" not in healed:
                    healed["heal_action"] = healed.get("heal_action", "none")
                    healed["heal_source"] = healed.get("heal_source", "original")
                    null_count = sum(1 for f in ["temperature", "humidity", "wind_speed", "pressure", "rainfall"]
                                     if healed.get(f) is None)
                    healed["quality_score"] = max(0.5, 1.0 - null_count * 0.1)

            if "id" not in healed:
                healed["id"] = reading.get("id", str(uuid.uuid4()))
            clean.append(healed)

        if skipped:
            console.print(f"  [dim]{skipped} readings skipped (unfixable)[/dim]")
        return clean

    def _store_healing_log(self, result) -> None:
        """Persist AI healing assessments to healing_log table."""
        import json as _json
        records = []
        for a in result.assessments:
            records.append({
                "id": str(uuid.uuid4()),
                "pipeline_run_id": self.run_id,
                "reading_id": a.reading_id,
                "station_id": a.station_id,
                "assessment": a.assessment,
                "reasoning": a.reasoning,
                "corrections": _json.dumps(a.corrections, default=str),
                "quality_score": a.quality_score,
                "tools_used": ",".join(a.tools_used),
                "original_values": _json.dumps(a.original_values, default=str),
                "model": result.model,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "latency_s": result.latency_s,
                "fallback_used": result.fallback_used,
            })
        if records:
            insert_healing_log(self.conn, records)

    async def step_heal(self, raw_readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        console.print("[bold blue]Step 2:[/bold blue] Healing + cross-validating via Tomorrow.io...")

        references = await self._fetch_references(raw_readings)

        # Try AI healing first (if API key available)
        if self.config.anthropic_key:
            try:
                agent = HealingAgent(self.config.anthropic_key)
                result = agent.heal_batch(raw_readings, references, self.conn)
                if not result.fallback_used:
                    self._store_healing_log(result)
                    clean = result.readings

                    # Validate stage output
                    clean = [CleanReading(**r).model_dump() for r in clean]
                    insert_clean_telemetry(self.conn, clean)

                    # Summary
                    n_good = sum(1 for a in result.assessments if a.assessment == "good")
                    n_corrected = sum(1 for a in result.assessments if a.assessment == "corrected")
                    n_filled = sum(1 for a in result.assessments if a.assessment == "filled")
                    n_flagged = sum(1 for a in result.assessments if a.assessment == "flagged")
                    n_dropped = sum(1 for a in result.assessments if a.assessment == "dropped")
                    avg_q = sum(r.get("quality_score", 1.0) for r in clean) / max(len(clean), 1)
                    console.print(
                        f"  [green]✓[/green] AI healer ({result.model}): "
                        f"{len(clean)} clean | {n_good} good | {n_corrected} corrected | "
                        f"{n_filled} filled | {n_flagged} flagged | {n_dropped} dropped | "
                        f"avg quality {avg_q:.2f} | "
                        f"{result.tokens_in}+{result.tokens_out} tokens | "
                        f"{result.latency_s:.1f}s"
                    )
                    return clean
                else:
                    log.warning("AI healing returned fallback_used=True, using rule-based")
            except Exception as e:
                log.warning("AI healing failed, falling back to rule-based: %s", e)

        # Fallback to rule-based
        console.print("  [dim]Using rule-based fallback[/dim]")
        clean = await self._rule_based_heal(raw_readings, references)

        # Validate stage output
        clean = [CleanReading(**r).model_dump() for r in clean]
        insert_clean_telemetry(self.conn, clean)

        # Summary stats
        n_xval = sum(1 for r in clean if "cross_validated" in (r.get("heal_action") or ""))
        n_filled = sum(1 for r in clean if "null_filled" in (r.get("heal_action") or ""))
        n_flagged = sum(1 for r in clean if "anomaly_flagged" in (r.get("heal_action") or ""))
        avg_q = sum(r.get("quality_score", 1.0) for r in clean) / max(len(clean), 1)
        console.print(
            f"  [green]✓[/green] {len(clean)} clean (rule-based) | "
            f"{n_xval} validated | {n_filled} null-filled | {n_flagged} flagged | "
            f"avg quality {avg_q:.2f}"
        )
        return clean

    # ------------------------------------------------------------------
    # Step 3: Forecast
    # ------------------------------------------------------------------
    async def step_forecast(self) -> List[Dict[str, Any]]:
        console.print("[bold blue]Step 3:[/bold blue] Running MOS forecasts via Open-Meteo...")
        forecasts = []

        # Batch Open-Meteo requests (20 at a time, no rate limit)
        all_tasks = []
        for station in STATIONS:
            obs = get_latest_clean_for_station(self.conn, station.station_id)
            history = get_clean_history_for_station(self.conn, station.station_id)
            all_tasks.append((station, run_forecast_step(
                station, obs, self.open_meteo,
                self.forecast_model, self.persistence,
                nasa_client=self.nasa_power,
                station_history=history,
            )))

        all_results = []
        om_batch_size = 20
        for i in range(0, len(all_tasks), om_batch_size):
            batch = all_tasks[i:i + om_batch_size]
            batch_results = await asyncio.gather(
                *[task for _, task in batch], return_exceptions=True
            )
            all_results.extend(zip([s for s, _ in batch], batch_results))
            if i + om_batch_size < len(all_tasks):
                await asyncio.sleep(0.1)

        mos_count = 0
        for station, result in all_results:
            if isinstance(result, Exception) or result is None:
                log.warning("Forecast failed for %s: %s", station.station_id, result)
                continue
            from src.database import insert_forecast as _if
            _if(self.conn, result)
            forecasts.append(result)
            if result.get("model_used") == "hybrid_mos":
                mos_count += 1

        console.print(f"  [green]✓[/green] {len(forecasts)} forecasts | {mos_count} MOS | {len(forecasts)-mos_count} fallback")
        # Validate stage output
        forecasts = [Forecast(**f).model_dump() for f in forecasts]
        return forecasts

    # ------------------------------------------------------------------
    # Step 4: Downscale
    # ------------------------------------------------------------------
    async def step_downscale(self, forecasts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        console.print("[bold blue]Step 4:[/bold blue] Downscaling to farmer GPS...")
        downscaled = []

        recipient_map = {r.station_id: r for r in DEFAULT_RECIPIENTS}

        # Build parallel downscale tasks
        passthrough = []
        ds_tasks = []
        ds_indices = []
        for idx, forecast in enumerate(forecasts):
            sid     = forecast["station_id"]
            station = STATION_MAP.get(sid)
            if station is None:
                passthrough.append((idx, forecast))
                continue

            recipient = recipient_map.get(sid)
            farmer_lat = recipient.lat if hasattr(recipient, "lat") else station.lat + 0.05
            farmer_lon = recipient.lon if hasattr(recipient, "lon") else station.lon + 0.05
            farmer_alt = recipient.alt_m if recipient else None

            ds_tasks.append(self.downscaler.downscale(
                forecast, station, farmer_lat, farmer_lon, farmer_alt
            ))
            ds_indices.append(idx)

        # Run all downscale calls in parallel
        ds_results = await asyncio.gather(*ds_tasks, return_exceptions=True)

        # Reassemble in original order
        result_map: Dict[int, Dict[str, Any]] = {}
        for idx, forecast in passthrough:
            result_map[idx] = forecast
        for idx, res in zip(ds_indices, ds_results):
            if isinstance(res, Exception):
                log.warning("Downscale failed for forecast %d: %s", idx, res)
                result_map[idx] = forecasts[idx]
            else:
                result_map[idx] = res
        downscaled = [result_map[i] for i in range(len(forecasts))]

        n_ds = sum(1 for f in downscaled if f.get("downscaled"))
        console.print(f"  [green]✓[/green] {len(downscaled)} forecasts | {n_ds} downscaled")
        return downscaled

    # ------------------------------------------------------------------
    # Step 5: Translate / advisory
    # ------------------------------------------------------------------
    async def step_translate(self, downscaled: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        console.print("[bold blue]Step 5:[/bold blue] Generating advisories + translating...")
        alerts = []

        tasks = []
        stations_list = []
        for forecast in downscaled:
            station = STATION_MAP.get(forecast["station_id"])
            if station is None:
                continue
            tasks.append(generate_advisory(self.advisory_prov, forecast, station))
            stations_list.append((forecast, station))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (forecast, station), result in zip(stations_list, results):
            if isinstance(result, Exception):
                log.warning("Advisory failed for %s: %s", station.station_id, result)
                from src.translation.local_provider import LocalProvider
                result = LocalProvider().generate_advisory(forecast, station)

            alert = {
                "id":          str(uuid.uuid4()),
                "station_id":  station.station_id,
                "farmer_lat":  forecast.get("farmer_lat", station.lat),
                "farmer_lon":  forecast.get("farmer_lon", station.lon),
                "issued_at":   datetime.utcnow().isoformat(),
                "condition":   forecast.get("condition"),
                "temperature": forecast.get("temperature"),
                "rainfall":    forecast.get("rainfall"),
                **result,
            }
            insert_alert(self.conn, alert)
            alerts.append(alert)

        rag_count = sum(1 for a in alerts if a.get("provider") == "rag_claude")
        console.print(f"  [green]✓[/green] {len(alerts)} advisories | {rag_count} RAG | {len(alerts)-rag_count} rule-based")
        return alerts

    # ------------------------------------------------------------------
    # Step 6: Deliver
    # ------------------------------------------------------------------
    async def step_deliver(self, alerts: List[Dict[str, Any]]) -> int:
        console.print("[bold blue]Step 6:[/bold blue] Delivering advisories...")
        alert_map = {a["station_id"]: a for a in alerts}
        total = 0

        for recipient in DEFAULT_RECIPIENTS:
            alert = alert_map.get(recipient.station_id)
            if alert is None:
                continue
            logs = await self.delivery.deliver(alert, recipient)
            for entry in logs:
                insert_delivery_log(self.conn, entry)
            total += len(logs)

        console.print(f"  [green]✓[/green] {total} delivery attempts")
        return total

    # ------------------------------------------------------------------
    # Full pipeline run
    # ------------------------------------------------------------------
    async def run(self) -> Dict[str, Any]:
        start_pipeline_run(self.conn, self.run_id)
        start_time = datetime.utcnow()
        steps_ok = steps_fail = 0

        console.rule(f"[bold cyan]Weather Pipeline Run {self.run_id[:8]}[/bold cyan]")

        try:
            raw       = await self.step_ingest();    steps_ok += 1
        except Exception as e:
            log.error("Step 1 failed: %s", e); steps_fail += 1; raw = []

        try:
            clean     = await self.step_heal(raw);   steps_ok += 1
        except Exception as e:
            log.error("Step 2 failed: %s", e); steps_fail += 1; clean = raw

        try:
            forecasts = await self.step_forecast();  steps_ok += 1
        except Exception as e:
            log.error("Step 3 failed: %s", e); steps_fail += 1; forecasts = []

        try:
            downscaled = await self.step_downscale(forecasts); steps_ok += 1
        except Exception as e:
            log.error("Step 4 failed: %s", e); steps_fail += 1; downscaled = forecasts

        try:
            alerts    = await self.step_translate(downscaled); steps_ok += 1
        except Exception as e:
            log.error("Step 5 failed: %s", e); steps_fail += 1; alerts = []

        try:
            deliveries = await self.step_deliver(alerts); steps_ok += 1
        except Exception as e:
            log.error("Step 6 failed: %s", e); steps_fail += 1; deliveries = 0

        # Aggregate delivery metrics per station
        forecast_sids = {f["station_id"] for f in forecasts}
        alert_sids = {a["station_id"] for a in alerts}
        try:
            dl_rows = self.conn.execute(
                "SELECT station_id, channel, status FROM delivery_log WHERE id LIKE ?",
                [f"%{self.run_id[:8]}%"],
            ).fetchall()
        except Exception:
            dl_rows = []
        delivery_by_station: Dict[str, Dict[str, Any]] = {}
        for row in dl_rows:
            sid = row[0]
            if sid not in delivery_by_station:
                delivery_by_station[sid] = {"attempted": 0, "succeeded": 0, "channels": set()}
            delivery_by_station[sid]["attempted"] += 1
            if row[2] in ("sent", "dry_run"):
                delivery_by_station[sid]["succeeded"] += 1
            delivery_by_station[sid]["channels"].add(row[1])

        all_sids = forecast_sids | alert_sids | set(delivery_by_station.keys())
        for sid in all_sids:
            dl_info = delivery_by_station.get(sid, {})
            insert_delivery_metrics(self.conn, {
                "id": f"dm_{self.run_id[:8]}_{sid}",
                "pipeline_run_id": self.run_id,
                "station_id": sid,
                "forecasts_generated": 1 if sid in forecast_sids else 0,
                "advisories_generated": 1 if sid in alert_sids else 0,
                "deliveries_attempted": dl_info.get("attempted", 0),
                "deliveries_succeeded": dl_info.get("succeeded", 0),
                "channels_used": ",".join(sorted(dl_info.get("channels", set()))) or None,
            })

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        status  = "ok" if steps_fail == 0 else "partial"
        summary = (f"{steps_ok}/6 steps ok | {len(alerts)} alerts | "
                   f"{deliveries} deliveries | {elapsed:.1f}s")

        finish_pipeline_run(self.conn, self.run_id, status, steps_ok, steps_fail, summary)

        # Run quality checks
        try:
            from src.quality_checks import run_all_checks
            run_all_checks(self.conn)
        except Exception as e:
            log.warning("Quality checks failed: %s", e)

        console.rule(f"[bold green]Run complete: {summary}[/bold green]")

        return {
            "run_id":     self.run_id,
            "status":     status,
            "steps_ok":   steps_ok,
            "steps_fail": steps_fail,
            "alerts":     len(alerts),
            "deliveries": deliveries,
            "elapsed_s":  elapsed,
        }
