"""
6 new tool definitions + executors for the conversational agent.
These complement the existing 5 NLAgent tools.
"""

from __future__ import annotations
import asyncio
import json
from dataclasses import asdict
from typing import Any, Dict

CONVERSATION_TOOLS = [
    {
        "name": "lookup_farmer_profile",
        "description": "Look up a farmer's full DPI profile by phone number or Aadhaar ID. Returns identity, land records, crops, soil health, subsidies, insurance, and credit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Phone number (e.g. +919876543210)"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "get_soil_health",
        "description": "Get detailed Soil Health Card for a farmer: pH, N/P/K, micronutrients, recommendations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aadhaar_id": {"type": "string", "description": "Farmer's Aadhaar ID (masked format)"},
            },
            "required": ["aadhaar_id"],
        },
    },
    {
        "name": "get_insurance_status",
        "description": "Get PMFBY crop insurance status, insured crops, claims history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aadhaar_id": {"type": "string", "description": "Farmer's Aadhaar ID"},
            },
            "required": ["aadhaar_id"],
        },
    },
    {
        "name": "get_subsidy_history",
        "description": "Get PM-KISAN payment history and KCC credit card status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aadhaar_id": {"type": "string", "description": "Farmer's Aadhaar ID"},
            },
            "required": ["aadhaar_id"],
        },
    },
    {
        "name": "get_personalized_advisory",
        "description": "Generate a weather advisory personalized to the farmer's actual crops, soil, plot, and financial situation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Farmer's phone number"},
                "station_id": {"type": "string", "description": "Weather station ID (e.g. KL_TVM). If omitted, uses farmer's nearest station."},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "schedule_followup",
        "description": "Schedule a proactive follow-up message for the farmer (e.g., check back after heavy rain, remind about insurance deadline).",
        "input_schema": {
            "type": "object",
            "properties": {
                "aadhaar_id": {"type": "string", "description": "Farmer's Aadhaar ID"},
                "trigger_type": {"type": "string", "enum": ["time", "weather_event", "pipeline_run"],
                                 "description": "When to trigger the follow-up"},
                "trigger_value": {"type": "string",
                                  "description": "ISO datetime for 'time', event name for 'weather_event', or 'next' for 'pipeline_run'"},
                "message": {"type": "string", "description": "The follow-up message to send"},
            },
            "required": ["aadhaar_id", "trigger_type", "trigger_value", "message"],
        },
    },
]


def execute_conversation_tool(tool_name: str, tool_input: Dict[str, Any],
                               session_id: str = "") -> str:
    """Execute one of the 6 conversation tools. Returns JSON string."""

    if tool_name == "lookup_farmer_profile":
        return asyncio.run(_lookup_profile(tool_input))

    if tool_name == "get_soil_health":
        return _get_soil(tool_input)

    if tool_name == "get_insurance_status":
        return _get_insurance(tool_input)

    if tool_name == "get_subsidy_history":
        return _get_subsidy(tool_input)

    if tool_name == "get_personalized_advisory":
        return asyncio.run(_personalized_advisory(tool_input))

    if tool_name == "schedule_followup":
        return _schedule(tool_input, session_id)

    return json.dumps({"error": f"Unknown conversation tool: {tool_name}"})


async def _lookup_profile(tool_input: Dict) -> str:
    from src.dpi import DPIAgent
    agent = DPIAgent()
    phone = tool_input["phone"]
    profile = await agent.get_or_create_profile(phone)
    if profile is None:
        return json.dumps({"error": f"No farmer found for phone {phone}"})
    return json.dumps({
        "name": profile.aadhaar.name,
        "name_local": profile.aadhaar.name_local,
        "district": profile.aadhaar.district,
        "state": profile.aadhaar.state,
        "language": profile.aadhaar.language,
        "aadhaar_id": profile.aadhaar.aadhaar_id,
        "total_area_ha": profile.total_area,
        "primary_crops": profile.primary_crops,
        "nearest_stations": profile.nearest_stations,
        "soil_summary": profile.soil_summary,
        "financial_capacity": profile.financial_capacity,
        "land_records": [asdict(lr) for lr in profile.land_records],
    }, default=str, indent=2)


def _get_soil(tool_input: Dict) -> str:
    from src.dpi.simulator import get_registry
    registry = get_registry()
    card = registry.get_soil_health(tool_input["aadhaar_id"])
    if card is None:
        return json.dumps({"error": "No soil health card found"})
    return json.dumps(asdict(card), default=str, indent=2)


def _get_insurance(tool_input: Dict) -> str:
    from src.dpi.simulator import get_registry
    registry = get_registry()
    record = registry.get_pmfby(tool_input["aadhaar_id"])
    if record is None:
        return json.dumps({"error": "No insurance record found"})
    return json.dumps(asdict(record), default=str, indent=2)


def _get_subsidy(tool_input: Dict) -> str:
    from src.dpi.simulator import get_registry
    registry = get_registry()
    pmk = registry.get_pmkisan(tool_input["aadhaar_id"])
    kcc = registry.get_kcc(tool_input["aadhaar_id"])
    result = {}
    if pmk:
        result["pmkisan"] = asdict(pmk)
    if kcc:
        result["kcc"] = asdict(kcc)
    if not result:
        return json.dumps({"error": "No subsidy/credit records found"})
    return json.dumps(result, default=str, indent=2)


async def _personalized_advisory(tool_input: Dict) -> str:
    from src.dpi import DPIAgent
    from src.database import init_db, get_recent_forecasts
    from config import STATION_MAP

    agent = DPIAgent()
    profile = await agent.get_or_create_profile(tool_input["phone"])
    if profile is None:
        return json.dumps({"error": "Farmer not found"})

    station_id = tool_input.get("station_id") or (
        profile.nearest_stations[0] if profile.nearest_stations else None
    )
    if not station_id:
        return json.dumps({"error": "No station associated with farmer"})

    station = STATION_MAP.get(station_id)
    if not station:
        return json.dumps({"error": f"Unknown station: {station_id}"})

    # Get latest forecast for station
    conn = init_db()
    try:
        forecasts = get_recent_forecasts(conn, limit=50)
        station_fc = [f for f in forecasts if f.get("station_id") == station_id]
    finally:
        conn.close()
    if not station_fc:
        return json.dumps({"advisory": "No recent forecast available for your station. Please run the pipeline first."})

    fc = station_fc[0]

    # Build personalized context
    context = agent.profile_to_context(profile)
    condition = fc.get("condition", "clear")
    temp = fc.get("temperature", 25.0)
    rain = fc.get("rainfall", 0.0)

    return json.dumps({
        "station": station_id,
        "condition": condition,
        "temperature": temp,
        "rainfall": rain,
        "farmer_name": profile.aadhaar.name,
        "crops": profile.primary_crops,
        "soil_ph": profile.soil_health.pH if profile.soil_health else None,
        "area_ha": profile.total_area,
        "insurance_status": profile.pmfby.status if profile.pmfby else "none",
        "farmer_context": context,
        "personalized_note": (
            f"Advisory for {profile.aadhaar.name}'s {profile.total_area:.1f}ha of "
            f"{', '.join(profile.primary_crops)} in {profile.aadhaar.district}. "
            f"Forecast: {condition}, {temp:.1f}C, {rain:.1f}mm rain. "
            f"Soil pH: {profile.soil_health.pH if profile.soil_health else 'unknown'}."
        ),
    }, default=str, indent=2)


def _schedule(tool_input: Dict, session_id: str) -> str:
    from src.database import init_db
    from src.conversation.followup import schedule_followup
    conn = init_db()
    try:
        fid = schedule_followup(
            conn, tool_input["aadhaar_id"],
            tool_input["trigger_type"], tool_input["trigger_value"],
            tool_input["message"], session_id,
        )
        return json.dumps({"status": "scheduled", "followup_id": fid})
    finally:
        conn.close()
