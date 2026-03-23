"""DPI service protocol, generic implementation, and factory."""

from __future__ import annotations
from dataclasses import asdict
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from src.dpi.simulator import get_registry


@runtime_checkable
class DPIService(Protocol):
    service_name: str
    async def lookup(self, identifier: str, **kwargs) -> Optional[Dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Simulated services — single generic class covers all 6 DPI endpoints
# ---------------------------------------------------------------------------

class SimulatedDPIService:

    _REGISTRY_METHODS = {
        "aadhaar":      "get_aadhaar",
        "land_records": "get_land_records",
        "soil_health":  "get_soil_health",
        "pmkisan":      "get_pmkisan",
        "pmfby":        "get_pmfby",
        "kcc":          "get_kcc",
    }

    def __init__(self, service_name: str):
        if service_name not in self._REGISTRY_METHODS:
            raise ValueError(f"Unknown DPI service: {service_name}")
        self.service_name = service_name

    async def lookup(self, identifier: str, **kwargs) -> Optional[Dict[str, Any]]:
        registry = get_registry()
        method = getattr(registry, self._REGISTRY_METHODS[self.service_name])
        result = method(identifier)
        if result is None:
            return None
        if isinstance(result, list):
            return {"records": [asdict(r) for r in result]}
        return asdict(result)


# ---------------------------------------------------------------------------
# Real services — placeholder for future integration
# ---------------------------------------------------------------------------

class RealDPIService:
    """Placeholder for real DPI service integration."""

    def __init__(self, service_name: str):
        self.service_name = service_name

    async def lookup(self, identifier: str, **kwargs) -> Optional[Dict[str, Any]]:
        raise NotImplementedError(f"Real {self.service_name} integration pending")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_service(name: str, simulation: bool = True) -> DPIService:
    """Return simulated or real service by name."""
    if simulation:
        return SimulatedDPIService(name)
    return RealDPIService(name)
