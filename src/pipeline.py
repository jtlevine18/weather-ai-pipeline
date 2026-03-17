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
                            start_pipeline_run, finish_pipeline_run,
                            get_latest_clean_for_station)
from src.ingestion       import ingest_all_stations
from src.weather_clients import TomorrowIOClient, OpenMeteoClient, NASAPowerClient
from src.agents          import RuleBasedFallback, ObservabilityAgent, SelfHealingAgent
from src.forecasting     import create_forecast_model, PersistenceModel, run_forecast_step
from src.downscaling     import IDWDownscaler
from src.translation     import get_provider, generate_advisory
from src.delivery        import MultiChannelDelivery, DEFAULT_RECIPIENTS, DeliveryChannel

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
        self.obs_agent     = ObservabilityAgent(config.anthropic_key)
        self.heal_agent    = SelfHealingAgent(config.anthropic_key)
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
        console.print("[bold blue]Step 1:[/bold blue] Ingesting synthetic telemetry...")
        readings = await ingest_all_stations(self.config, self.conn)
        faults   = sum(1 for r in readings if r.get("fault_type"))
        console.print(f"  [green]✓[/green] {len(readings)} readings | {faults} faults injected")
        return readings

    # ------------------------------------------------------------------
    # Step 2: Heal
    # ------------------------------------------------------------------
    async def step_heal(self, raw_readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        console.print("[bold blue]Step 2:[/bold blue] Healing anomalies via Tomorrow.io...")
        clean = []
        healed_count = 0
        skipped = 0

        # Fetch Tomorrow.io references in batches of 3 (API limit: 3 req/sec)
        station_ids = [r["station_id"] for r in raw_readings if r["station_id"] in STATION_MAP]
        references: Dict[str, Any] = {}
        batch_size = 3
        for i in range(0, len(station_ids), batch_size):
            batch = station_ids[i:i + batch_size]
            results = await asyncio.gather(*[
                self.tomorrow_io.get_current(STATION_MAP[sid].lat, STATION_MAP[sid].lon)
                for sid in batch
            ], return_exceptions=True)
            for sid, res in zip(batch, results):
                references[sid] = res if isinstance(res, dict) else None
            if i + batch_size < len(station_ids):
                await asyncio.sleep(1.0)

        for reading in raw_readings:
            ref = references.get(reading["station_id"])
            fault = reading.get("fault_type")

            if fault is None:
                # No fault — pass through with heal_action=none
                healed = dict(reading)
                healed["heal_action"] = "none"
                healed["heal_source"] = "original"
                healed["quality_score"] = 1.0
            else:
                # Try rule-based first
                healed = self.rule_healer.heal(reading, ref)
                if healed is None:
                    # Offline with no reference — try NASA POWER
                    station = STATION_MAP.get(reading["station_id"])
                    if station:
                        nasa_ref = await self.nasa_power.get_current(station.lat, station.lon)
                        if nasa_ref:
                            healed = self.rule_healer.heal(reading, nasa_ref)
                    if healed is None:
                        skipped += 1
                        continue  # Skip — never fabricate
                healed_count += 1
                healed["quality_score"] = 0.8 if healed.get("heal_action") != "none" else 1.0

            # Ensure ID exists
            if "id" not in healed:
                healed["id"] = reading.get("id", str(uuid.uuid4()))
            clean.append(healed)

        insert_clean_telemetry(self.conn, clean)
        console.print(f"  [green]✓[/green] {len(clean)} clean records | {healed_count} healed | {skipped} skipped")
        return clean

    # ------------------------------------------------------------------
    # Step 3: Forecast
    # ------------------------------------------------------------------
    async def step_forecast(self) -> List[Dict[str, Any]]:
        console.print("[bold blue]Step 3:[/bold blue] Running MOS forecasts via Open-Meteo...")
        forecasts = []
        tasks = []
        for station in STATIONS:
            obs = get_latest_clean_for_station(self.conn, station.station_id)
            tasks.append(run_forecast_step(
                station, obs, self.open_meteo,
                self.forecast_model, self.persistence,
                nasa_client=self.nasa_power,
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        mos_count = 0
        for station, result in zip(STATIONS, results):
            if isinstance(result, Exception) or result is None:
                log.warning("Forecast failed for %s: %s", station.station_id, result)
                continue
            from src.database import insert_forecast as _if
            _if(self.conn, result)
            forecasts.append(result)
            if result.get("model_used") == "hybrid_mos":
                mos_count += 1

        console.print(f"  [green]✓[/green] {len(forecasts)} forecasts | {mos_count} MOS | {len(forecasts)-mos_count} fallback")
        return forecasts

    # ------------------------------------------------------------------
    # Step 4: Downscale
    # ------------------------------------------------------------------
    async def step_downscale(self, forecasts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        console.print("[bold blue]Step 4:[/bold blue] Downscaling to farmer GPS...")
        downscaled = []

        recipient_map = {r.station_id: r for r in DEFAULT_RECIPIENTS}

        for forecast in forecasts:
            sid     = forecast["station_id"]
            station = STATION_MAP.get(sid)
            if station is None:
                downscaled.append(forecast)
                continue

            recipient = recipient_map.get(sid)
            farmer_lat = recipient.lat if hasattr(recipient, "lat") else station.lat + 0.05
            farmer_lon = recipient.lon if hasattr(recipient, "lon") else station.lon + 0.05
            farmer_alt = recipient.alt_m if recipient else None

            ds = await self.downscaler.downscale(
                forecast, station, farmer_lat, farmer_lon, farmer_alt
            )
            downscaled.append(ds)

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

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        status  = "ok" if steps_fail == 0 else "partial"
        summary = (f"{steps_ok}/6 steps ok | {len(alerts)} alerts | "
                   f"{deliveries} deliveries | {elapsed:.1f}s")

        finish_pipeline_run(self.conn, self.run_id, status, steps_ok, steps_fail, summary)
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
