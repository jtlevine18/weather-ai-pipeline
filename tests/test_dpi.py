"""Tests for the DPI integration layer."""

import asyncio
import pytest


def test_simulator_generates_farmers():
    from src.dpi.simulator import SimulatedDPIRegistry
    registry = SimulatedDPIRegistry()
    assert registry.farmer_count >= 30, f"Expected 30+ farmers, got {registry.farmer_count}"
    farmers = registry.list_farmers()
    assert len(farmers) >= 30

    for f in farmers[:3]:
        assert f["phone"].startswith("+91")
        assert f["name"]
        assert f["district"]
        assert f["crops"]


def test_simulator_deterministic():
    from src.dpi.simulator import SimulatedDPIRegistry
    r1 = SimulatedDPIRegistry()
    r2 = SimulatedDPIRegistry()
    f1 = r1.list_farmers()
    f2 = r2.list_farmers()
    assert len(f1) == len(f2)
    for a, b in zip(f1, f2):
        assert a["phone"] == b["phone"], "Phone numbers should be deterministic"
        assert a["name"] == b["name"]


def test_phone_lookup():
    from src.dpi.simulator import SimulatedDPIRegistry
    registry = SimulatedDPIRegistry()
    farmers = registry.list_farmers()
    phone = farmers[0]["phone"]
    profile = registry.lookup_by_phone(phone)
    assert profile is not None
    assert profile.aadhaar.phone == phone
    assert profile.total_area > 0
    assert profile.primary_crops


def test_aadhaar_lookup():
    from src.dpi.simulator import SimulatedDPIRegistry
    registry = SimulatedDPIRegistry()
    farmers = registry.list_farmers()
    phone = farmers[0]["phone"]
    profile = registry.lookup_by_phone(phone)
    aadhaar_id = profile.aadhaar.aadhaar_id
    profile2 = registry.lookup_by_aadhaar(aadhaar_id)
    assert profile2 is not None
    assert profile2.aadhaar.name == profile.aadhaar.name


def test_soil_health():
    from src.dpi.simulator import SimulatedDPIRegistry
    registry = SimulatedDPIRegistry()
    farmers = registry.list_farmers()
    phone = farmers[0]["phone"]
    profile = registry.lookup_by_phone(phone)
    sh = profile.soil_health
    assert sh is not None
    assert 3.0 <= sh.pH <= 10.0
    assert sh.nitrogen_kg_ha > 0
    assert sh.recommendations


def test_financial_records():
    from src.dpi.simulator import SimulatedDPIRegistry
    registry = SimulatedDPIRegistry()
    farmers = registry.list_farmers()
    phone = farmers[0]["phone"]
    profile = registry.lookup_by_phone(phone)
    assert profile.pmkisan is not None
    assert profile.pmkisan.installments_received > 0
    assert profile.pmfby is not None
    assert profile.kcc is not None
    assert profile.kcc.credit_limit > 0


def test_services_async():
    from src.dpi.services import get_service

    async def run():
        svc = get_service("aadhaar", simulation=True)
        from src.dpi.simulator import get_registry
        reg = get_registry()
        phone = reg.list_farmers()[0]["phone"]
        result = await svc.lookup(phone)
        assert result is not None
        assert result["phone"] == phone
        return result

    asyncio.run(run())


def test_dpi_agent():
    from src.dpi import DPIAgent
    from src.dpi.simulator import get_registry

    async def run():
        agent = DPIAgent()
        reg = get_registry()
        phone = reg.list_farmers()[0]["phone"]
        profile = await agent.get_or_create_profile(phone)
        assert profile is not None
        ctx = agent.profile_to_context(profile)
        assert "FARMER PROFILE" in ctx
        assert "LAND HOLDINGS" in ctx

    asyncio.run(run())


def test_station_coverage():
    from src.dpi.simulator import SimulatedDPIRegistry
    registry = SimulatedDPIRegistry()
    farmers = registry.list_farmers()
    stations = {f["station"] for f in farmers}
    from config import STATIONS
    all_stations = {s.station_id for s in STATIONS}
    missing = all_stations - stations
    assert not missing, f"Stations without farmers: {missing}"
