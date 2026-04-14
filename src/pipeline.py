"""
Main pipeline orchestrator — runs all 6 steps linearly.
Each step can fail independently without killing the pipeline.
"""

from __future__ import annotations
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from rich.console import Console

from config import PipelineConfig, STATIONS, STATION_MAP, FEATURED_FARMER_IDS, tz_offset_hours
from src.database import (init_db, insert_clean_telemetry, insert_forecast,
                            insert_alert, insert_delivery_log,
                            insert_delivery_metrics,
                            insert_personalized_advisory,
                            start_pipeline_run, finish_pipeline_run,
                            get_latest_clean_for_station,
                            get_clean_history_for_station)
from src.ingestion       import ingest_all_stations
from src.weather_clients import TomorrowIOClient, OpenMeteoClient, NASAPowerClient
from src.healing         import RuleBasedFallback, HealingAgent
from src.database        import insert_healing_log
from src.forecasting     import create_forecast_model, PersistenceModel, run_forecast_step, classify_condition
from src.downscaling     import IDWDownscaler
from src.translation     import get_provider, generate_advisory
from src.delivery        import MultiChannelDelivery, DEFAULT_RECIPIENTS, DeliveryChannel, Recipient
from src.models          import RawReading, CleanReading, Forecast
from src.neuralgcm_client import NeuralGCMClient, is_neuralgcm_available

log = logging.getLogger(__name__)
console = Console()


class WeatherPipeline:
    def __init__(self, config: PipelineConfig, live_delivery: bool = False):
        self.config        = config
        self.live_delivery = live_delivery
        self.conn          = init_db(config.database_url)
        self.run_id        = str(uuid.uuid4())

        # Clients
        self.tomorrow_io   = TomorrowIOClient(config.tomorrow_io_key)
        self.open_meteo    = OpenMeteoClient(timezone=config.timezone)
        self.nasa_power    = NASAPowerClient()
        self.neuralgcm     = None
        if not config.neuralgcm.enabled:
            log.info("NeuralGCM disabled by config (use default or remove --no-neuralgcm)")
        elif not is_neuralgcm_available():
            log.warning("NeuralGCM enabled but packages missing — falling back to Open-Meteo")
        else:
            self.neuralgcm = NeuralGCMClient(
                model_name=config.neuralgcm.model_name,
                forecast_hours=config.neuralgcm.forecast_hours,
            )
            log.info("NeuralGCM ready: %s", config.neuralgcm.model_name)

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

    def _refresh_conn(self) -> None:
        """Reconnect if the DB connection was dropped (Neon 5-min idle timeout)."""
        try:
            self.conn.execute("SELECT 1")
        except Exception:
            log.info("DB connection stale — reconnecting")
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = init_db(self.config.database_url)

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
        """Fetch Tomorrow.io references in batches of 10, NASA POWER fallback.
        Skips remaining batches if first batch all fails (rate-limited)."""
        station_ids = list(dict.fromkeys(
            r["station_id"] for r in raw_readings if r["station_id"] in STATION_MAP
        ))
        references: Dict[str, Any] = {}
        batch_size = 10
        for i in range(0, len(station_ids), batch_size):
            batch = station_ids[i:i + batch_size]
            results = await asyncio.gather(*[
                self.tomorrow_io.get_current(STATION_MAP[sid].lat, STATION_MAP[sid].lon)
                for sid in batch
            ], return_exceptions=True)
            all_failed = True
            for sid, res in zip(batch, results):
                if isinstance(res, dict):
                    references[sid] = res
                    all_failed = False
                else:
                    references[sid] = None
            # If entire first batch failed (e.g. 429), skip remaining
            if i == 0 and all_failed:
                log.warning("Tomorrow.io: first batch all failed — skipping remaining stations")
                for sid in station_ids[len(batch):]:
                    references[sid] = None
                break
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
        records = []
        for a in result.assessments:
            records.append({
                "id": str(uuid.uuid4()),
                "pipeline_run_id": self.run_id,
                "reading_id": a.reading_id,
                "station_id": a.station_id,
                "assessment": a.assessment,
                "reasoning": a.reasoning,
                "corrections": json.dumps(a.corrections, default=str),
                "quality_score": a.quality_score,
                "tools_used": ",".join(a.tools_used),
                "original_values": json.dumps(a.original_values, default=str),
                "model": result.model,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "latency_s": result.latency_s,
                "fallback_used": result.fallback_used,
            })
        if records:
            insert_healing_log(self.conn, records)

    def _store_rule_based_log(self, clean_readings: List[Dict[str, Any]]) -> None:
        """Persist rule-based healing results to healing_log so dashboard shows them."""
        records = []
        for r in clean_readings:
            action = r.get("heal_action", "none")
            # Map heal_action to assessment category
            if "anomaly_flagged" in action:
                assessment = "flagged"
            elif "null_filled" in action:
                assessment = "filled"
            elif "cross_validated" in action:
                assessment = "good"
            elif "typo_corrected" in action or "ai_corrected" in action:
                assessment = "corrected"
            else:
                assessment = "good"

            records.append({
                "id": str(uuid.uuid4()),
                "pipeline_run_id": self.run_id,
                "reading_id": r.get("id", str(uuid.uuid4())),
                "station_id": r.get("station_id", ""),
                "assessment": assessment,
                "reasoning": f"Rule-based: {action}",
                "corrections": "{}",
                "quality_score": r.get("quality_score", 1.0),
                "tools_used": "",
                "original_values": "{}",
                "model": "rule-based",
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_s": 0.0,
                "fallback_used": True,
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
                    console.print(
                        f"  [yellow]⚠[/yellow] AI healing fell back to rule-based "
                        f"(used {result.tokens_in}+{result.tokens_out} tokens, "
                        f"{result.latency_s:.1f}s, {len(result.tool_calls)} tool calls)"
                    )
            except Exception as e:
                console.print(f"  [red]✗[/red] AI healing failed: {e}")
                log.warning("AI healing failed, falling back to rule-based: %s", e)

        # Fallback to rule-based
        console.print("  [dim]Using rule-based fallback[/dim]")
        clean = await self._rule_based_heal(raw_readings, references)

        # Validate stage output
        clean = [CleanReading(**r).model_dump() for r in clean]
        insert_clean_telemetry(self.conn, clean)

        # Log rule-based assessments to healing_log so dashboard shows them
        self._store_rule_based_log(clean)

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
        self._refresh_conn()
        nwp_label = "NeuralGCM + Open-Meteo fallback" if self.neuralgcm else "Open-Meteo"
        console.print(f"[bold blue]Step 3:[/bold blue] Running MOS forecasts via {nwp_label}...")

        # --- Try NeuralGCM batch (one inference → all 20 stations) ---
        neuralgcm_nwp: Dict[str, List[Dict[str, Any]]] = {}
        neuralgcm_meta = None
        if self.neuralgcm:
            try:
                from src.neuralgcm_client import get_neuralgcm_device
                device = get_neuralgcm_device()
                console.print(f"  [dim]NeuralGCM: {self.neuralgcm.model_name} on {device}[/dim]")

                neuralgcm_nwp, neuralgcm_meta = await self.neuralgcm.get_forecasts_batch(STATIONS)
                console.print(
                    f"  [green]✓[/green] NeuralGCM: {neuralgcm_meta.stations_extracted} stations | "
                    f"init={neuralgcm_meta.init_time[:19]} | "
                    f"inference={neuralgcm_meta.inference_time_s}s | "
                    f"data fetch={neuralgcm_meta.data_fetch_time_s}s"
                )
            except Exception as e:
                log.warning("NeuralGCM failed, falling back to Open-Meteo: %s", e)
                console.print(f"  [yellow]⚠[/yellow] NeuralGCM failed: {e}")
                console.print("  [dim]Falling back to Open-Meteo for all stations[/dim]")
                neuralgcm_nwp = {}

        # --- Build per-station forecast tasks ---
        forecasts = []
        all_tasks = []
        for station in STATIONS:
            obs = get_latest_clean_for_station(self.conn, station.station_id)
            history = get_clean_history_for_station(self.conn, station.station_id)
            # Use NeuralGCM NWP if available for this station, else Open-Meteo
            precomputed = neuralgcm_nwp.get(station.station_id)
            all_tasks.append((station, run_forecast_step(
                station, obs, self.open_meteo,
                self.forecast_model, self.persistence,
                nasa_client=self.nasa_power,
                station_history=history,
                precomputed_nwp=precomputed,
                tz_offset_h=tz_offset_hours(self.config.timezone),
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
        ngcm_count = 0
        for station, result in all_results:
            if isinstance(result, Exception):
                log.warning("Forecast failed for %s: %s", station.station_id, result)
                continue
            # run_forecast_step now returns List[Dict] (7 daily forecasts)
            if not result:
                continue
            fc_list = result if isinstance(result, list) else [result]
            for fc in fc_list:
                insert_forecast(self.conn, fc)
                forecasts.append(fc)
                mu = fc.get("model_used", "")
                if "mos" in mu:
                    mos_count += 1
                if fc.get("nwp_source") == "neuralgcm":
                    ngcm_count += 1

        n_stations = len(set(f["station_id"] for f in forecasts))
        n_days = max((f.get("forecast_day", 0) for f in forecasts), default=0) + 1 if forecasts else 0
        nwp_summary = f"{ngcm_count} NeuralGCM + {len(forecasts)-ngcm_count} Open-Meteo" if ngcm_count else f"{len(forecasts)} Open-Meteo"
        console.print(
            f"  [green]✓[/green] {len(forecasts)} daily forecasts ({n_stations} stations × {n_days} days) | {mos_count} MOS | NWP: {nwp_summary}"
        )
        # Validate stage output
        forecasts = [Forecast(**f).model_dump() for f in forecasts]
        return forecasts

    # ------------------------------------------------------------------
    # Step 4: Downscale
    # ------------------------------------------------------------------
    async def step_downscale(self, forecasts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._refresh_conn()
        console.print("[bold blue]Step 4:[/bold blue] Downscaling to farmer GPS...")

        recipient_map = {r.station_id: r for r in DEFAULT_RECIPIENTS}

        # Group forecasts by station — fetch NASA grid once per station,
        # then apply the same adjustment to all 7 daily forecasts.
        from collections import defaultdict
        station_groups: Dict[str, List[int]] = defaultdict(list)
        for idx, fc in enumerate(forecasts):
            station_groups[fc["station_id"]].append(idx)

        # Downscale one representative forecast per station (day 0)
        ds_tasks = []
        ds_station_ids = []
        for sid, indices in station_groups.items():
            station = STATION_MAP.get(sid)
            if station is None:
                continue
            recipient = recipient_map.get(sid)
            farmer_lat = recipient.lat if hasattr(recipient, "lat") else station.lat + 0.05
            farmer_lon = recipient.lon if hasattr(recipient, "lon") else station.lon + 0.05
            farmer_alt = recipient.alt_m if recipient else None
            # Use first forecast as representative (grid fetch is location-based, not time-based)
            ds_tasks.append(self.downscaler.downscale(
                forecasts[indices[0]], station, farmer_lat, farmer_lon, farmer_alt
            ))
            ds_station_ids.append(sid)

        # Run one downscale per station in parallel (20 calls, not 140)
        ds_results = await asyncio.gather(*ds_tasks, return_exceptions=True)

        # Build adjustment map: station_id → downscaling deltas
        adjustments: Dict[str, Dict[str, Any]] = {}
        for sid, res in zip(ds_station_ids, ds_results):
            if isinstance(res, Exception):
                log.warning("Downscale failed for %s: %s", sid, res)
                continue
            if res.get("downscaled"):
                adjustments[sid] = {
                    "idw_temp": res.get("idw_temp"),
                    "lapse_delta": res.get("lapse_delta", 0),
                    "alt_delta_m": res.get("alt_delta_m", 0),
                    "farmer_lat": res.get("farmer_lat"),
                    "farmer_lon": res.get("farmer_lon"),
                }

        # Apply adjustments to all forecasts for each station
        downscaled = []
        for fc in forecasts:
            sid = fc["station_id"]
            adj = adjustments.get(sid)
            if adj is None:
                downscaled.append(fc)
                continue
            result = dict(fc)
            result["farmer_lat"] = adj["farmer_lat"]
            result["farmer_lon"] = adj["farmer_lon"]
            result["downscaled"] = True
            result["idw_temp"] = adj["idw_temp"]
            result["lapse_delta"] = adj["lapse_delta"]
            result["alt_delta_m"] = adj["alt_delta_m"]
            # Apply lapse-rate correction to this day's forecast temperature
            if adj["idw_temp"] is not None and adj["lapse_delta"] is not None:
                result["temperature"] = round(adj["idw_temp"] + adj["lapse_delta"], 2)
                result["condition"] = classify_condition(result)
            downscaled.append(result)

        n_ds = sum(1 for f in downscaled if f.get("downscaled"))
        console.print(f"  [green]✓[/green] {len(downscaled)} forecasts | {n_ds} downscaled")
        return downscaled

    # ------------------------------------------------------------------
    # Step 5: Translate / advisory
    # ------------------------------------------------------------------
    async def step_translate(self, downscaled: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._refresh_conn()
        console.print("[bold blue]Step 5:[/bold blue] Generating weekly advisories + translating...")
        alerts = []

        # Group forecasts by station (7 daily forecasts → 1 weekly advisory)
        from collections import defaultdict
        station_forecasts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for forecast in downscaled:
            station_forecasts[forecast["station_id"]].append(forecast)

        tasks = []
        stations_list = []
        for sid, fc_list in station_forecasts.items():
            station = STATION_MAP.get(sid)
            if station is None:
                continue
            fc_list.sort(key=lambda f: f.get("forecast_day", 0))
            tasks.append(generate_advisory(self.advisory_prov, fc_list, station))
            stations_list.append((fc_list, station))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Reconnect — Claude API calls above may have taken >5min (Neon idle timeout)
        self._refresh_conn()

        for (fc_list, station), result in zip(stations_list, results):
            if isinstance(result, Exception):
                log.warning("Advisory failed for %s: %s", station.station_id, result)
                from src.translation.local_provider import LocalProvider
                result = LocalProvider().generate_advisory(fc_list, station)

            # Use day-0 forecast for alert metadata
            day0 = fc_list[0] if fc_list else {}
            alert = {
                "id":            str(uuid.uuid4()),
                "station_id":    station.station_id,
                "farmer_lat":    day0.get("farmer_lat", station.lat),
                "farmer_lon":    day0.get("farmer_lon", station.lon),
                "issued_at":     datetime.now(timezone.utc).isoformat(),
                "condition":     day0.get("condition"),
                "temperature":   day0.get("temperature"),
                "rainfall":      day0.get("rainfall"),
                "forecast_days": len(fc_list),
                **result,
            }
            insert_alert(self.conn, alert)
            alerts.append(alert)

        # Personalize for featured farmers only (demo surface). The rest of the
        # 2,000-farmer registry reuses the station-level advisory; the UI
        # surfaces the projected cost to personalize the full population.
        if self.config.anthropic_key and FEATURED_FARMER_IDS:
            try:
                await self._personalize_for_featured_farmers(alerts)
            except Exception as exc:
                log.warning("Personalized advisory pass failed: %s", exc)

        rag_count = sum(1 for a in alerts if a.get("provider") == "rag_claude")
        console.print(f"  [green]✓[/green] {len(alerts)} weekly advisories | {rag_count} RAG | {len(alerts)-rag_count} rule-based")
        return alerts

    async def _personalize_for_featured_farmers(self, alerts: List[Dict[str, Any]]) -> None:
        """Generate per-farmer Haiku-personalized advisories for FEATURED_FARMER_IDS.

        Looks up each featured farmer in the DPI registry, pulls the relevant
        station's English advisory, and produces a tailored version that gets
        stored in the personalized_advisories table. Failures are logged and
        skipped — this is a demo enhancement, never a blocker for the core
        pipeline.
        """
        from src.translation.personalized_provider import PersonalizedAdvisoryProvider
        from src.dpi.simulator import get_registry, _seed_rng, _make_phone

        provider = PersonalizedAdvisoryProvider(api_key=self.config.anthropic_key)
        registry = get_registry()
        alert_by_station: Dict[str, Dict[str, Any]] = {a["station_id"]: a for a in alerts}

        total_in = 0
        total_out = 0
        successes = 0

        for station_id, farmer_idx in FEATURED_FARMER_IDS:
            alert = alert_by_station.get(station_id)
            station = STATION_MAP.get(station_id)
            if not alert or not station:
                continue

            phone = _make_phone(station_id, farmer_idx)
            profile = registry.lookup_by_phone(phone)
            if profile is None:
                log.info("Featured farmer %s:%d not in registry — skipping", station_id, farmer_idx)
                continue

            try:
                result = await provider.personalize(
                    station_advisory_en=alert.get("advisory_en") or "",
                    station=station,
                    farmer_profile=profile,
                    language=station.language,
                )
            except Exception as exc:
                log.warning("Personalize failed for %s:%d (%s): %s",
                             station_id, farmer_idx, phone, exc)
                continue

            land = profile.land_records[0] if profile.land_records else None
            record = {
                "id":              str(uuid.uuid4()),
                "alert_id":        alert["id"],
                "station_id":      station_id,
                "farmer_phone":    phone,
                "farmer_name":     profile.aadhaar.name,
                "crops":           ", ".join(land.crops_registered) if land else "",
                "soil_type":       land.soil_type if land else "",
                "irrigation_type": land.irrigation_type if land else "",
                "area_hectares":   land.area_hectares if land else 0.0,
                "advisory_en":     result.advisory_en,
                "advisory_local":  result.advisory_local,
                "language":        station.language,
                "model":           result.model,
                "tokens_in":       result.tokens_in,
                "tokens_out":      result.tokens_out,
                "cache_read":      result.cache_read_tokens,
            }
            try:
                insert_personalized_advisory(self.conn, record)
                successes += 1
                total_in += result.tokens_in
                total_out += result.tokens_out
            except Exception as exc:
                log.warning("Insert personalized advisory failed for %s: %s", phone, exc)

        if successes:
            console.print(
                f"  [cyan]→[/cyan] {successes} featured farmers personalized "
                f"(Haiku, {total_in + total_out} tokens)"
            )

    # ------------------------------------------------------------------
    # Step 6: Deliver
    # ------------------------------------------------------------------
    async def step_deliver(self, alerts: List[Dict[str, Any]]) -> int:
        self._refresh_conn()
        console.print("[bold blue]Step 6:[/bold blue] Delivering advisories...")
        alert_map = {a["station_id"]: a for a in alerts}
        total = 0

        # Build recipients from farmer registry (covers all 20 stations)
        recipients = self._build_recipients()

        for recipient in recipients:
            alert = alert_map.get(recipient.station_id)
            if alert is None:
                continue
            logs = await self.delivery.deliver(alert, recipient)
            for entry in logs:
                insert_delivery_log(self.conn, entry)
            total += len(logs)

        console.print(f"  [green]✓[/green] {total} delivery attempts")
        return total

    def _build_recipients(self) -> List[Recipient]:
        """Pull one recipient per station from the farmer registry."""
        try:
            from src.dpi.simulator import get_registry
            registry = get_registry()
            farmers = registry.list_farmers()
            # Pick one farmer per station
            seen_stations: set = set()
            recipients = []
            for f in farmers:
                sid = f.get("station", "")
                if sid and sid not in seen_stations:
                    seen_stations.add(sid)
                    profile = registry.lookup_by_phone(f["phone"])
                    lang = profile.aadhaar.language if profile else "en"
                    recipients.append(Recipient(
                        name=f["name"],
                        phone=f["phone"],
                        station_id=sid,
                        language=lang,
                    ))
            if recipients:
                return recipients
        except Exception as e:
            log.warning("Could not load farmer registry for delivery: %s", e)
        # Fallback to hardcoded demo recipients
        return DEFAULT_RECIPIENTS

    # ------------------------------------------------------------------
    # Full pipeline run
    # ------------------------------------------------------------------
    async def run(self) -> Dict[str, Any]:
        start_pipeline_run(self.conn, self.run_id)
        start_time = datetime.now(timezone.utc)
        steps_ok = steps_fail = 0

        console.rule(f"[bold cyan]Weather Pipeline Run {self.run_id[:8]}[/bold cyan]")

        try:
            raw       = await self.step_ingest();    steps_ok += 1
        except Exception:
            log.exception("Step 1 failed"); steps_fail += 1; raw = []

        try:
            clean     = await self.step_heal(raw);   steps_ok += 1
        except Exception:
            log.exception("Step 2 failed"); steps_fail += 1; clean = raw

        try:
            forecasts = await self.step_forecast();  steps_ok += 1
        except Exception:
            log.exception("Step 3 failed"); steps_fail += 1; forecasts = []

        try:
            downscaled = await self.step_downscale(forecasts); steps_ok += 1
        except Exception:
            log.exception("Step 4 failed"); steps_fail += 1; downscaled = forecasts

        try:
            alerts    = await self.step_translate(downscaled); steps_ok += 1
        except Exception:
            log.exception("Step 5 failed"); steps_fail += 1; alerts = []

        try:
            deliveries = await self.step_deliver(alerts); steps_ok += 1
        except Exception:
            log.exception("Step 6 failed"); steps_fail += 1; deliveries = 0

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

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
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
