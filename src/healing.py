"""
Claude-powered AI healing agent + rule-based fallback.

HealingAgent: uses Claude Sonnet with 5 investigation tools to assess and heal
a batch of raw weather readings from IMD stations across Kerala and Tamil Nadu.
Cross-validates against Tomorrow.io / NASA POWER reference data.

RuleBasedFallback: deterministic anomaly detection, NULL-fill, and cross-validation.
Used when the Anthropic API is unavailable.
"""

from __future__ import annotations
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Seasonal context for Kerala and Tamil Nadu (used by get_seasonal_context tool)
# ---------------------------------------------------------------------------

SEASONAL_CONTEXT: Dict[tuple, Dict[str, str]] = {
    # Kerala
    ("Kerala", 1): {
        "season": "Winter / Dry (Makaram)",
        "weather": "Cool nights 18-22°C, daytime 28-33°C, dry with occasional light showers, humidity 60-75%",
        "agriculture": "Rabi crop harvest, coconut picking, spice drying, land preparation for summer crops",
    },
    ("Kerala", 2): {
        "season": "Winter / Dry (Kumbham)",
        "weather": "Warming trend 20-34°C, dry, pre-monsoon thunderstorms possible late month, humidity rising",
        "agriculture": "Summer crop sowing (vegetables, pulses), rubber tapping active, fish harvesting in paddy fields",
    },
    ("Kerala", 3): {
        "season": "Pre-monsoon / Summer (Meenam)",
        "weather": "Hot 25-36°C, pre-monsoon showers and thunderstorms, humidity 65-80%, isolated heavy rain possible",
        "agriculture": "Summer rice (Puncha) harvest, land preparation for Virippu season, mango flowering",
    },
    ("Kerala", 4): {
        "season": "Pre-monsoon / Summer (Medam)",
        "weather": "Hottest month 27-37°C, frequent thunderstorms, gusty winds, humidity 70-85%",
        "agriculture": "Virippu nursery preparation, coconut harvest, cashew processing, irrigation critical",
    },
    ("Kerala", 5): {
        "season": "Pre-monsoon / Summer (Edavam)",
        "weather": "Hot and humid 26-35°C, heavy pre-monsoon showers, SW monsoon onset possible late May",
        "agriculture": "Virippu rice sowing begins with early rains, rubber tapping, pepper harvest winding down",
    },
    ("Kerala", 6): {
        "season": "Southwest Monsoon onset (Edavappathi)",
        "weather": "Heavy rainfall 200-600mm, persistent rain, temps 24-32°C, humidity 85-95%, gusty winds",
        "agriculture": "Main Virippu rice sowing, rubber tapping paused in heavy rain, cardamom flowering",
    },
    ("Kerala", 7): {
        "season": "Southwest Monsoon peak (Karkidakam)",
        "weather": "Heaviest rainfall 300-700mm, continuous rain, temps 23-30°C, very high humidity, flooding risk",
        "agriculture": "Virippu transplanting, fish breeding season, minimal field operations during heavy rain",
    },
    ("Kerala", 8): {
        "season": "Southwest Monsoon (Chingam)",
        "weather": "Heavy rain 200-500mm, temps 24-31°C, humidity 80-90%, brief dry spells possible",
        "agriculture": "Virippu rice growing, Onam festival, banana harvest, spice garden maintenance",
    },
    ("Kerala", 9): {
        "season": "Southwest Monsoon retreating (Kanni)",
        "weather": "Rain easing 150-350mm, temps 24-32°C, humidity 75-85%, NE monsoon transition",
        "agriculture": "Virippu harvest begins, Mundakan nursery preparation, coconut harvest",
    },
    ("Kerala", 10): {
        "season": "Northeast Monsoon (Thulam)",
        "weather": "Second rainfall peak 150-400mm, temps 24-32°C, cyclone risk on east coast affecting Kerala",
        "agriculture": "Mundakan rice sowing, pepper harvest begins, tapioca planting",
    },
    ("Kerala", 11): {
        "season": "Northeast Monsoon (Vrischikam)",
        "weather": "Moderate rain 100-250mm, temps 23-32°C, humidity 70-80%, gradually drying",
        "agriculture": "Mundakan rice growing, pepper and cardamom harvest peak, rubber tapping resumes",
    },
    ("Kerala", 12): {
        "season": "Post-monsoon / Dry (Dhanu)",
        "weather": "Dry spell begins, temps 22-32°C, cool nights, humidity 60-70%, clear skies",
        "agriculture": "Mundakan harvest, coconut harvest, spice drying, land preparation for rabi crops",
    },
    # Tamil Nadu
    ("Tamil Nadu", 1): {
        "season": "Winter (Thai Pongal)",
        "weather": "Cool 20-28°C, NE monsoon tail-end showers possible, humidity 65-75%, pleasant",
        "agriculture": "Samba rice harvest, Pongal festival, sugarcane harvest, rabi crops growing",
    },
    ("Tamil Nadu", 2): {
        "season": "Late Winter (Maasi)",
        "weather": "Warming 22-32°C, dry, occasional light showers in southern districts, humidity dropping",
        "agriculture": "Rabi harvest, land preparation for summer crops, groundnut sowing in dry areas",
    },
    ("Tamil Nadu", 3): {
        "season": "Summer onset (Panguni)",
        "weather": "Hot 28-38°C, dry inland, occasional thunderstorms, humidity 50-65%",
        "agriculture": "Summer ploughing, irrigation-dependent crops, mango flowering, banana harvest",
    },
    ("Tamil Nadu", 4): {
        "season": "Peak Summer (Chithirai)",
        "weather": "Very hot 32-42°C, severe heat stress inland (Salem, Madurai), isolated thunderstorms, low humidity",
        "agriculture": "Irrigation critical, groundwater depletion, summer vegetables, millets sowing where irrigated",
    },
    ("Tamil Nadu", 5): {
        "season": "Peak Summer (Vaikasi)",
        "weather": "Hottest month 35-45°C in interior districts, heat waves common, pre-monsoon thunderstorms",
        "agriculture": "Kuruvai nursery preparation with available water, mango harvest, heat stress on livestock",
    },
    ("Tamil Nadu", 6): {
        "season": "Southwest Monsoon (Aani)",
        "weather": "SW monsoon brings moderate rain 50-200mm to western ghats districts, 30-38°C, rain shadow in east",
        "agriculture": "Kuruvai rice sowing in Cauvery delta, cotton sowing, rain-fed crops in western districts",
    },
    ("Tamil Nadu", 7): {
        "season": "Southwest Monsoon (Aadi)",
        "weather": "Moderate rain 50-150mm in west, dry in east, temps 28-36°C, Aadi Perukku floods in rivers",
        "agriculture": "Kuruvai transplanting, Samba nursery prep, cotton growing, sugarcane planting",
    },
    ("Tamil Nadu", 8): {
        "season": "Late SW Monsoon (Aavani)",
        "weather": "Rain easing 50-100mm, temps 28-36°C, humidity 60-75%, dry spells in Cauvery delta",
        "agriculture": "Samba rice transplanting (main season), Kuruvai harvest begins in early-sown areas",
    },
    ("Tamil Nadu", 9): {
        "season": "Monsoon transition (Purattasi)",
        "weather": "Variable 50-150mm, temps 28-34°C, cyclone season beginning, humidity rising",
        "agriculture": "Samba rice growing, Kuruvai harvest, groundnut harvest, Navaratri festival season",
    },
    ("Tamil Nadu", 10): {
        "season": "Northeast Monsoon onset (Aipasi)",
        "weather": "NE monsoon brings heavy rain 150-400mm, temps 26-32°C, cyclone risk highest, flooding in coastal areas",
        "agriculture": "Thaladi rice sowing, Samba growing, cotton harvest, cyclone damage risk to standing crops",
    },
    ("Tamil Nadu", 11): {
        "season": "Northeast Monsoon peak (Karthigai)",
        "weather": "Heaviest rains 200-500mm, Nagappattinam/Thanjavur/Chennai most affected, flooding risk, temps 24-30°C",
        "agriculture": "Minimal field operations during heavy rain, Samba rice at critical growth stage, drainage essential",
    },
    ("Tamil Nadu", 12): {
        "season": "Post-NE Monsoon (Margazhi)",
        "weather": "Rain tapering 50-150mm, temps 22-30°C, cool mornings, humidity 70-80%",
        "agriculture": "Samba harvest approaching, Thaladi rice growing, sugarcane harvest, Margazhi season",
    },
}


# ---------------------------------------------------------------------------
# Healing tool definitions (JSON Schema format for Claude tool-use API)
# ---------------------------------------------------------------------------

HEALING_TOOLS = [
    {
        "name": "get_station_metadata",
        "description": (
            "Get metadata for an IMD weather station: name, coordinates (lat/lon), "
            "altitude, state (Kerala or Tamil Nadu), crop context, language, and WMO SYNOP ID. "
            "Use this to understand a station's geography and agricultural context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "station_id": {
                    "type": "string",
                    "description": "Station ID, e.g. 'KL_TVM' for Thiruvananthapuram or 'TN_TNJ' for Thanjavur",
                },
            },
            "required": ["station_id"],
        },
    },
    {
        "name": "get_historical_normals",
        "description": (
            "Get historical min/mean/max values for a station in a specific calendar month, "
            "computed from past clean_telemetry readings. Returns ranges for temperature, "
            "humidity, wind_speed, pressure, and rainfall. Use this to check whether a "
            "reading falls within normal historical ranges for that station and time of year."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "station_id": {"type": "string", "description": "Station ID"},
                "month": {"type": "integer", "description": "Calendar month (1-12)"},
            },
            "required": ["station_id", "month"],
        },
    },
    {
        "name": "get_reference_comparison",
        "description": (
            "Get the Tomorrow.io (or NASA POWER fallback) cross-validation reference "
            "for a station. This is an independent weather observation fetched for the "
            "same station coordinates. Compare IMD readings against this to assess quality. "
            "Returns: source label, temperature, humidity, wind_speed, pressure, rainfall."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "station_id": {"type": "string", "description": "Station ID"},
            },
            "required": ["station_id"],
        },
    },
    {
        "name": "check_neighboring_stations",
        "description": (
            "Get current readings from neighboring IMD stations within a given radius. "
            "Use this to detect spatial inconsistencies — if one station's reading "
            "diverges wildly from all its neighbors, it's likely a sensor error. "
            "Returns station name, distance in km, and weather values for each neighbor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "station_id": {"type": "string", "description": "Station ID to find neighbors for"},
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in km (default 150)",
                    "default": 150,
                },
            },
            "required": ["station_id"],
        },
    },
    {
        "name": "get_seasonal_context",
        "description": (
            "Get the current agricultural season, typical weather patterns, and farming "
            "context for a station's region and time of year. Kerala and Tamil Nadu have "
            "distinct monsoon patterns and crop calendars. Use this to judge whether "
            "extreme-looking values are actually normal for the season."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "station_id": {"type": "string", "description": "Station ID"},
                "month": {"type": "integer", "description": "Calendar month (1-12)"},
            },
            "required": ["station_id", "month"],
        },
    },
]


# ---------------------------------------------------------------------------
# System prompt for the healing agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """You are a weather data quality agent for a network of 20 India Meteorological Department (IMD) stations across Kerala and Tamil Nadu.

## Data Sources You're Working With

The readings you receive are scraped from real IMD stations — each station has a WMO SYNOP ID (e.g., Thiruvananthapuram=43371, Chennai=43279, Thanjavur=43330). The data pipeline:
1. IMD city weather API provides current station observations (temperature, humidity, wind speed, wind direction, pressure, rainfall)
2. When the IMD API is unavailable, imdlib gridded data (0.25° resolution, T-1 day lag) serves as backup
3. As a last resort, synthetic readings with injected faults (typo, offline, drift, missing) are generated for testing

Your job is Step 2 of a 6-step agricultural weather pipeline: heal and quality-score these raw readings BEFORE they feed into MOS forecasting (Step 3), which ultimately generates crop advisories for smallholder farmers.

## Cross-Validation Reference

Each reading can be cross-validated against Tomorrow.io current conditions fetched for the same station coordinates. When Tomorrow.io is unavailable, NASA POWER reanalysis data (0.5° grid, 2-3 day lag) serves as fallback. Use the `get_reference_comparison` tool to access these.

Key cross-validation insight: Tomorrow.io and NASA POWER are independent data sources. When an IMD reading agrees with Tomorrow.io within thresholds (temperature ±8°C, humidity ±25%, wind ±15 km/h, pressure ±15 hPa, rainfall ±20mm), that's strong evidence the reading is good. When they diverge significantly, investigate further — the IMD reading might be wrong, OR the reference might be unreliable for that location.

## Your Task

You receive a batch of {n_readings} raw weather readings from {n_readings} IMD stations. For each reading:
1. Assess data quality — look for typos, sensor drift, missing data, out-of-range values, spatial inconsistency with neighboring IMD stations
2. Use your tools to investigate suspicious readings — check historical normals, compare with neighbors, examine Tomorrow.io/NASA POWER reference sources, consider seasonal context
3. Produce a structured assessment for EVERY reading:
   - assessment: "good" | "corrected" | "filled" | "flagged" | "dropped"
   - reasoning: 1-2 sentences explaining your judgment (this is shown to farmers and operators on the dashboard)
   - corrections: any field corrections as {{field: new_value}} — empty dict if no corrections
   - quality_score: 0.0-1.0 confidence in the final values
   - tools_used: which tools you called while investigating this reading

## Indian Weather Context

These are tropical/subtropical stations. Normal ranges differ dramatically from temperate zones:
- Summer (Mar-May) temperatures in Tamil Nadu regularly hit 40-45°C — this is NOT anomalous
- Southwest monsoon (Jun-Sep) brings 200-600mm monthly rainfall to Kerala — extreme by global standards, normal here
- Northeast monsoon (Oct-Dec) is when Tamil Nadu gets its heaviest rain — 200-500mm in Nagappattinam/Thanjavur is expected
- Coastal stations (Kochi, Chennai, Alappuzha) have narrower temperature ranges than inland stations (Salem, Madurai, Palakkad)
- Altitude matters: Nilambur (~25m) and Palakkad (gap in Western Ghats, ~85m) have very different microclimates despite proximity

## Key Rules
- NEVER fabricate data. If you can't confidently correct a value, flag it or drop it.
- A reading with all NULLs and no reference data should be dropped.
- Temperature > 100°C is almost certainly a decimal-place typo (divide by 10): 325 → 32.5°C
- When IMD and Tomorrow.io agree closely, assign high quality (0.9+). When they diverge, investigate before deciding which to trust.
- Cross-check against neighboring IMD stations — if Thanjavur reads 15°C and Tiruchirappalli (50 km away) reads 32°C, something is wrong with the Thanjavur sensor.
- NULL fields (wind_speed, pressure especially — IMD often omits these) can be filled from Tomorrow.io reference — this is legitimate, not fabrication, because it's a real measurement from an independent source.
- Quality score should reflect your confidence: 0.95+ for clean IMD data confirmed by Tomorrow.io, 0.7-0.9 for corrected data, 0.5-0.7 for filled/estimated data, <0.5 for flagged.

## Output Format

After investigating, return your final assessment as a JSON array (one object per reading) wrapped in ```json fences. Each object must have these fields:
- reading_id (string): the id from the input reading
- station_id (string): the station_id from the input reading
- assessment (string): "good" | "corrected" | "filled" | "flagged" | "dropped"
- reasoning (string): 1-2 sentences
- corrections (object): {{field: new_value}} or empty object
- quality_score (number): 0.0-1.0
- tools_used (array of strings): tool names you called for this reading"""


# ---------------------------------------------------------------------------
# Dataclasses for agent output
# ---------------------------------------------------------------------------

@dataclass
class ReadingAssessment:
    reading_id: str
    station_id: str
    assessment: str         # good / corrected / filled / flagged / dropped
    reasoning: str
    corrections: Dict[str, Any]
    quality_score: float
    tools_used: List[str]
    original_values: Dict[str, Any]


@dataclass
class HealingResult:
    readings: List[Dict[str, Any]]
    assessments: List[ReadingAssessment]
    tool_calls: List[Dict[str, Any]]
    model: str
    tokens_in: int
    tokens_out: int
    latency_s: float
    fallback_used: bool


# ---------------------------------------------------------------------------
# Tool implementations (all local, no API calls)
# ---------------------------------------------------------------------------

WEATHER_FIELDS = ["temperature", "humidity", "wind_speed", "wind_dir", "pressure", "rainfall"]


def _tool_station_metadata(station_id: str) -> Dict[str, Any]:
    from config import STATION_MAP
    station = STATION_MAP.get(station_id)
    if station is None:
        return {"error": f"Unknown station_id: {station_id}"}
    return {
        "station_id": station.station_id,
        "name": station.name,
        "lat": station.lat,
        "lon": station.lon,
        "altitude_m": station.altitude_m,
        "state": station.state,
        "crop_context": station.crop_context,
        "language": station.language,
        "imd_id": station.imd_id,
    }


def _tool_historical_normals(station_id: str, month: int, conn) -> Dict[str, Any]:
    from src.database.telemetry import get_clean_history_for_station
    history = get_clean_history_for_station(conn, station_id, limit=500)
    if not history:
        return {"error": f"No historical data for station {station_id}"}

    # Filter to matching month
    monthly = []
    for r in history:
        ts = r.get("ts")
        if ts is None:
            continue
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                continue
        if hasattr(ts, "month") and ts.month == month:
            monthly.append(r)

    if not monthly:
        return {"info": f"No historical data for station {station_id} in month {month}",
                "total_records": len(history)}

    result: Dict[str, Any] = {"station_id": station_id, "month": month, "sample_size": len(monthly)}
    for fld in ["temperature", "humidity", "wind_speed", "pressure", "rainfall"]:
        vals = [r[fld] for r in monthly if r.get(fld) is not None]
        if vals:
            result[fld] = {
                "min": round(min(vals), 1),
                "mean": round(sum(vals) / len(vals), 1),
                "max": round(max(vals), 1),
            }
    return result


def _tool_reference_comparison(station_id: str, references: Dict[str, Any]) -> Dict[str, Any]:
    ref = references.get(station_id)
    if ref is None:
        return {"error": f"No reference data available for station {station_id} "
                "(Tomorrow.io and NASA POWER both unavailable)"}
    return {
        "station_id": station_id,
        "source": ref.get("source", "tomorrow_io"),
        "temperature": ref.get("temperature"),
        "humidity": ref.get("humidity"),
        "wind_speed": ref.get("wind_speed"),
        "pressure": ref.get("pressure"),
        "rainfall": ref.get("rainfall"),
    }


def _tool_neighboring_stations(station_id: str, radius_km: float,
                                batch_readings: List[Dict[str, Any]]) -> Dict[str, Any]:
    from config import STATION_MAP, STATIONS
    from src.downscaling.interpolation import haversine_km

    target = STATION_MAP.get(station_id)
    if target is None:
        return {"error": f"Unknown station_id: {station_id}"}

    # Build lookup from current batch
    batch_by_sid = {r["station_id"]: r for r in batch_readings}

    neighbors = []
    for station in STATIONS:
        if station.station_id == station_id:
            continue
        dist = haversine_km(target.lat, target.lon, station.lat, station.lon)
        if dist <= radius_km:
            reading = batch_by_sid.get(station.station_id, {})
            neighbors.append({
                "station_id": station.station_id,
                "name": station.name,
                "distance_km": round(dist, 1),
                "temperature": reading.get("temperature"),
                "humidity": reading.get("humidity"),
                "wind_speed": reading.get("wind_speed"),
                "pressure": reading.get("pressure"),
                "rainfall": reading.get("rainfall"),
            })

    neighbors.sort(key=lambda x: x["distance_km"])
    return {
        "station_id": station_id,
        "radius_km": radius_km,
        "neighbors_found": len(neighbors),
        "neighbors": neighbors,
    }


def _tool_seasonal_context(station_id: str, month: int) -> Dict[str, Any]:
    from config import STATION_MAP
    station = STATION_MAP.get(station_id)
    if station is None:
        return {"error": f"Unknown station_id: {station_id}"}

    key = (station.state, month)
    ctx = SEASONAL_CONTEXT.get(key)
    if ctx is None:
        return {"error": f"No seasonal context for state={station.state}, month={month}"}

    return {
        "station_id": station_id,
        "station_name": station.name,
        "state": station.state,
        "month": month,
        **ctx,
    }


# ---------------------------------------------------------------------------
# HealingAgent — Claude-powered agentic healer
# ---------------------------------------------------------------------------

class HealingAgent:
    """Uses Claude Sonnet with 5 investigation tools to assess and heal
    a batch of raw IMD weather readings."""

    MAX_TOOL_ROUNDS = 10

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _execute_tool(self, name: str, tool_input: Dict[str, Any],
                       context: Dict[str, Any]) -> str:
        """Dispatch a tool call. Returns JSON string."""
        try:
            if name == "get_station_metadata":
                result = _tool_station_metadata(tool_input["station_id"])
            elif name == "get_historical_normals":
                result = _tool_historical_normals(
                    tool_input["station_id"], tool_input["month"], context["conn"])
            elif name == "get_reference_comparison":
                result = _tool_reference_comparison(
                    tool_input["station_id"], context["references"])
            elif name == "check_neighboring_stations":
                result = _tool_neighboring_stations(
                    tool_input["station_id"],
                    tool_input.get("radius_km", 150),
                    context["batch_readings"])
            elif name == "get_seasonal_context":
                result = _tool_seasonal_context(
                    tool_input["station_id"], tool_input["month"])
            else:
                result = {"error": f"Unknown tool: {name}"}
        except Exception as exc:
            result = {"error": f"Tool execution failed: {exc}"}

        return json.dumps(result, default=str)

    def _build_system_prompt(self, n_readings: int) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(n_readings=n_readings)

    def _parse_assessments(self, text: str) -> List[Dict[str, Any]]:
        """Extract JSON assessment array from Claude's response."""
        # Try to find ```json ... ``` block
        match = re.search(r'```json\s*([\s\S]*?)```', text)
        if match:
            return json.loads(match.group(1))

        # Try bare JSON array
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            return json.loads(match.group(0))

        raise ValueError("Could not find JSON assessment array in response")

    def heal_batch(self, readings: List[Dict[str, Any]],
                    references: Dict[str, Any],
                    conn) -> HealingResult:
        """Main entry point: assess and heal a batch of raw readings.

        Args:
            readings: Raw readings from Step 1 (Ingest)
            references: Dict mapping station_id -> Tomorrow.io/NASA POWER reference
            conn: DuckDB connection for historical queries

        Returns:
            HealingResult with healed readings, assessments, and trace
        """
        t0 = time.time()
        total_tokens_in = 0
        total_tokens_out = 0
        all_tool_calls: List[Dict[str, Any]] = []

        client = self._get_client()
        context = {
            "references": references,
            "batch_readings": readings,
            "conn": conn,
        }

        # Build user message with all readings
        readings_payload = []
        for r in readings:
            readings_payload.append({
                "id": r.get("id", ""),
                "station_id": r["station_id"],
                "ts": str(r.get("ts", "")),
                "temperature": r.get("temperature"),
                "humidity": r.get("humidity"),
                "wind_speed": r.get("wind_speed"),
                "wind_dir": r.get("wind_dir"),
                "pressure": r.get("pressure"),
                "rainfall": r.get("rainfall"),
                "fault_type": r.get("fault_type"),
                "source": r.get("source", "unknown"),
            })

        now = datetime.utcnow()
        user_msg = (
            f"Current date/time: {now.isoformat()} UTC (month={now.month})\n\n"
            f"Here are {len(readings)} raw IMD station readings to assess and heal:\n\n"
            f"```json\n{json.dumps(readings_payload, indent=2, default=str)}\n```\n\n"
            "Investigate any suspicious readings using your tools, then return "
            "your assessment for ALL readings."
        )

        messages = [{"role": "user", "content": user_msg}]
        system_prompt = self._build_system_prompt(len(readings))

        # Agentic tool-use loop
        for round_num in range(self.MAX_TOOL_ROUNDS):
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                tools=HEALING_TOOLS,
                messages=messages,
            )

            total_tokens_in += getattr(response.usage, "input_tokens", 0)
            total_tokens_out += getattr(response.usage, "output_tokens", 0)

            if response.stop_reason == "end_turn":
                # Extract final assessment
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                full_text = "\n".join(text_blocks)

                try:
                    raw_assessments = self._parse_assessments(full_text)
                except (ValueError, json.JSONDecodeError) as e:
                    log.warning("Failed to parse AI healing response: %s", e)
                    return HealingResult(
                        readings=[], assessments=[], tool_calls=all_tool_calls,
                        model=self.model, tokens_in=total_tokens_in,
                        tokens_out=total_tokens_out,
                        latency_s=time.time() - t0, fallback_used=True,
                    )

                # Build ReadingAssessment objects and apply corrections
                assessments = []
                healed_readings = []
                readings_by_id = {r.get("id", ""): r for r in readings}

                for a in raw_assessments:
                    rid = a.get("reading_id", "")
                    original = readings_by_id.get(rid)
                    if original is None:
                        continue

                    # Snapshot original weather values
                    original_values = {f: original.get(f) for f in WEATHER_FIELDS}

                    assessment = ReadingAssessment(
                        reading_id=rid,
                        station_id=a.get("station_id", original["station_id"]),
                        assessment=a.get("assessment", "flagged"),
                        reasoning=a.get("reasoning", ""),
                        corrections=a.get("corrections", {}),
                        quality_score=float(a.get("quality_score", 0.5)),
                        tools_used=a.get("tools_used", []),
                        original_values=original_values,
                    )
                    assessments.append(assessment)

                    if assessment.assessment == "dropped":
                        continue

                    # Apply corrections to a copy of the reading
                    healed = dict(original)
                    for field_name, new_val in assessment.corrections.items():
                        if field_name in WEATHER_FIELDS:
                            healed[field_name] = new_val

                    # Set heal metadata
                    if assessment.corrections:
                        healed["heal_action"] = f"ai_{assessment.assessment}"
                    elif assessment.assessment == "filled":
                        healed["heal_action"] = "ai_filled"
                    elif assessment.assessment == "good":
                        healed["heal_action"] = "ai_validated"
                    else:
                        healed["heal_action"] = f"ai_{assessment.assessment}"

                    healed["heal_source"] = f"claude_{self.model}"
                    healed["quality_score"] = assessment.quality_score

                    if "id" not in healed:
                        healed["id"] = str(uuid.uuid4())

                    healed_readings.append(healed)

                return HealingResult(
                    readings=healed_readings,
                    assessments=assessments,
                    tool_calls=all_tool_calls,
                    model=self.model,
                    tokens_in=total_tokens_in,
                    tokens_out=total_tokens_out,
                    latency_s=time.time() - t0,
                    fallback_used=False,
                )

            elif response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result_str = self._execute_tool(block.name, block.input, context)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str,
                        })
                        all_tool_calls.append({
                            "tool": block.name,
                            "input": block.input,
                            "output": result_str[:500],
                            "round": round_num,
                        })
                messages.append({"role": "user", "content": tool_results})
            else:
                log.warning("Unexpected stop_reason: %s", response.stop_reason)
                break

        # Exhausted rounds without end_turn
        log.warning("AI healing exhausted %d tool rounds without completing", self.MAX_TOOL_ROUNDS)
        return HealingResult(
            readings=[], assessments=[], tool_calls=all_tool_calls,
            model=self.model, tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            latency_s=time.time() - t0, fallback_used=True,
        )


# ---------------------------------------------------------------------------
# Rule-based fallback (no API needed)
# ---------------------------------------------------------------------------

class RuleBasedFallback:
    """Deterministic anomaly detection, correction, and cross-validation."""

    TEMP_MIN, TEMP_MAX     = -5.0, 55.0
    TEMP_VALID_MIN = 0.0
    TEMP_VALID_MAX = 50.0
    RH_MIN, RH_MAX         = 0.0, 100.0
    WIND_MAX               = 150.0
    PRESSURE_MIN           = 850.0
    PRESSURE_MAX           = 1100.0

    # Thresholds for cross-validation against Tomorrow.io / NASA POWER
    CROSS_VAL_THRESHOLDS = {
        "temperature": 8.0,   # °C
        "humidity":    25.0,  # %
        "wind_speed":  15.0,  # km/h
        "pressure":    15.0,  # hPa
        "rainfall":    20.0,  # mm
    }

    WEATHER_FIELDS = ["temperature", "humidity", "wind_speed", "wind_dir", "pressure", "rainfall"]

    def detect_anomalies(self, readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        anomalies = []
        for r in readings:
            issues = []
            temp = r.get("temperature")
            if temp is not None:
                if temp > 100:
                    issues.append({"field": "temperature", "type": "typo",
                                   "value": temp, "correction": temp / 10.0})
                elif not (self.TEMP_MIN <= temp <= self.TEMP_MAX):
                    issues.append({"field": "temperature", "type": "out_of_range",
                                   "value": temp, "correction": None})
            rh = r.get("humidity")
            if rh is not None and not (self.RH_MIN <= rh <= self.RH_MAX):
                issues.append({"field": "humidity", "type": "out_of_range",
                               "value": rh, "correction": max(0, min(100, rh))})
            ws = r.get("wind_speed")
            if ws is not None and ws > self.WIND_MAX:
                issues.append({"field": "wind_speed", "type": "out_of_range",
                               "value": ws, "correction": None})
            if issues:
                anomalies.append({"station_id": r["station_id"],
                                   "reading_id": r.get("id"),
                                   "issues": issues})
        return anomalies

    def heal(self, reading: Dict[str, Any],
              reference: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Apply rule-based corrections for synthetic fault types. Returns healed copy."""
        healed = dict(reading)
        healed["heal_action"] = "none"
        healed["heal_source"] = "original"

        temp = healed.get("temperature")

        # Typo: temperature 10× too high
        if temp is not None and temp > 100:
            healed["temperature"] = temp / 10.0
            healed["heal_action"] = "typo_corrected"
            healed["heal_source"] = "rule"
            return healed

        # All None → impute from reference if available
        if temp is None and reference and reference.get("temperature") is not None:
            healed["temperature"] = reference["temperature"]
            healed["humidity"]    = reference.get("humidity", healed.get("humidity"))
            healed["wind_speed"]  = reference.get("wind_speed", healed.get("wind_speed"))
            healed["pressure"]    = reference.get("pressure", healed.get("pressure"))
            healed["rainfall"]    = reference.get("rainfall", healed.get("rainfall", 0.0))
            healed["heal_action"] = "imputed_from_reference"
            healed["heal_source"] = reference.get("source", "reference")
            return healed

        if temp is None:
            return None  # type: ignore

        return healed

    # ------------------------------------------------------------------
    # Cross-validation against reference source (Tomorrow.io / NASA POWER)
    # ------------------------------------------------------------------

    def fill_nulls(self, reading: Dict[str, Any],
                   reference: Dict[str, Any]) -> tuple:
        """Fill NULL weather fields from reference. Returns (reading, filled_fields)."""
        filled = []
        for fld in self.WEATHER_FIELDS:
            if reading.get(fld) is None and reference.get(fld) is not None:
                reading[fld] = reference[fld]
                filled.append(fld)
        return reading, filled

    def cross_validate(self, reading: Dict[str, Any],
                       reference: Dict[str, Any]) -> Dict[str, Any]:
        """Cross-validate a reading against a reference, fill NULLs, compute quality."""
        healed = dict(reading)
        ref_source = reference.get("source", "tomorrow_io")

        prior_action = healed.get("heal_action", "none")

        # Phase 2: Fill NULL fields
        healed, filled_fields = self.fill_nulls(healed, reference)

        # Phase 3: Compare non-NULL fields against reference
        anomaly_fields = []
        agreements = []
        for fld, threshold in self.CROSS_VAL_THRESHOLDS.items():
            reading_val = reading.get(fld)
            ref_val = reference.get(fld)
            if reading_val is not None and ref_val is not None:
                diff = abs(reading_val - ref_val)
                agreement = max(0.0, 1.0 - diff / threshold)
                agreements.append((fld, agreement))
                if diff > threshold:
                    anomaly_fields.append(fld)

        actions = []
        if prior_action not in ("none", "original"):
            actions.append(prior_action)
        if agreements and not anomaly_fields:
            actions.append("cross_validated")
        if filled_fields:
            actions.append("null_filled")
        if anomaly_fields:
            actions.append("anomaly_flagged")

        if actions:
            healed["heal_action"] = "+".join(actions)
            healed["heal_source"] = f"original+{ref_source}"
        elif prior_action in ("none", "original"):
            healed["heal_action"] = "cross_validated"
            healed["heal_source"] = f"original+{ref_source}"

        # Compute quality_score
        if agreements:
            total_w = 0.0
            weighted_sum = 0.0
            for fld, score in agreements:
                w = 2.0 if fld == "temperature" else 1.0
                weighted_sum += w * score
                total_w += w
            base_score = weighted_sum / total_w
        else:
            base_score = 1.0

        null_count = sum(1 for f in ["temperature", "humidity", "wind_speed", "pressure", "rainfall"]
                         if healed.get(f) is None)
        penalty = null_count * 0.05

        healed["quality_score"] = round(max(0.3, min(1.0, base_score - penalty)), 3)
        healed["fields_filled"] = len(filled_fields)

        return healed
