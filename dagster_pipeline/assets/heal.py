"""Step 2: Heal anomalies — AI agent primary, rule-based fallback."""

import asyncio
import json
import logging
import os
import uuid
from dagster import asset, AssetExecutionContext, AssetIn
from typing import Any, Dict, List

from config import STATION_MAP
from src.healing import HealingAgent, RuleBasedFallback
from src.models import CleanReading
from src.database import insert_healing_log
from dagster_pipeline.resources import TomorrowIOResource, NASAPowerResource, PostgresResource

log = logging.getLogger(__name__)


async def _fetch_references(
    station_ids: List[str],
    tomorrow_io_client,
) -> Dict[str, Any]:
    """Fetch Tomorrow.io references in batches."""
    references: Dict[str, Any] = {}
    batch_size = 10
    for i in range(0, len(station_ids), batch_size):
        batch = station_ids[i:i + batch_size]
        results = await asyncio.gather(*[
            tomorrow_io_client.get_current(STATION_MAP[sid].lat, STATION_MAP[sid].lon)
            for sid in batch
        ], return_exceptions=True)
        for sid, res in zip(batch, results):
            references[sid] = res if isinstance(res, dict) else None
        if i + batch_size < len(station_ids):
            await asyncio.sleep(0.2)
    return references


def _rule_based_heal(
    raw_readings: List[Dict[str, Any]],
    references: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Deterministic three-phase healing (fault → NULL-fill → cross-validate)."""
    rule_healer = RuleBasedFallback()
    clean = []
    for reading in raw_readings:
        ref = references.get(reading["station_id"])
        fault = reading.get("fault_type")

        if fault is not None:
            healed = rule_healer.heal(reading, ref)
            if healed is None:
                continue
        else:
            healed = dict(reading)

        if ref is not None:
            healed = rule_healer.cross_validate(healed, ref)
        else:
            if "quality_score" not in healed:
                healed["heal_action"] = healed.get("heal_action", "none")
                healed["heal_source"] = healed.get("heal_source", "original")
                null_count = sum(1 for f in ["temperature", "humidity", "wind_speed", "pressure", "rainfall"]
                                 if healed.get(f) is None)
                healed["quality_score"] = max(0.5, 1.0 - null_count * 0.1)

        if "id" not in healed:
            healed["id"] = reading.get("id", "unknown")
        clean.append(healed)
    return clean


@asset(
    ins={"raw_telemetry": AssetIn()},
    description="Healed telemetry — Claude AI agent (5 tools) with rule-based fallback.",
    group_name="pipeline",
)
def clean_telemetry(
    context: AssetExecutionContext,
    raw_telemetry: List[Dict[str, Any]],
    tomorrow_io: TomorrowIOResource,
    nasa_power: NASAPowerResource,
    postgres: PostgresResource,
) -> List[Dict[str, Any]]:
    station_ids = list(dict.fromkeys(
        r["station_id"] for r in raw_telemetry if r["station_id"] in STATION_MAP
    ))
    references = asyncio.run(_fetch_references(
        station_ids, tomorrow_io.get_client(),
    ))

    # Try AI healing first
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            conn = postgres.get_connection()
            try:
                agent = HealingAgent(api_key)
                result = agent.heal_batch(raw_telemetry, references, conn)
                if not result.fallback_used:
                    records = []
                    for a in result.assessments:
                        records.append({
                            "id": str(uuid.uuid4()),
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
                            "fallback_used": False,
                        })
                    insert_healing_log(conn, records)
                    clean = result.readings
                    clean = [CleanReading(**r).model_dump() for r in clean]
                    context.log.info(
                        f"AI healed {len(clean)} records | model={result.model} | "
                        f"tokens={result.tokens_in + result.tokens_out} | latency={result.latency_s:.1f}s"
                    )
                    return clean
            finally:
                conn.close()
        except Exception as e:
            context.log.warning(f"AI healing failed, falling back to rule-based: {e}")

    # Fallback to rule-based
    clean = _rule_based_heal(raw_telemetry, references)
    clean = [CleanReading(**r).model_dump() for r in clean]
    healed = sum(1 for r in clean if r.get("heal_action") != "none")
    context.log.info(f"Rule-based healed {len(clean)} records | {healed} corrected")
    return clean
