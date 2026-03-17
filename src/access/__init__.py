"""Simple role-based access control for pipeline operations."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Role(str, Enum):
    ADMIN     = "admin"
    ANALYST   = "analyst"
    FARMER    = "farmer"
    VIEWER    = "viewer"


PERMISSIONS = {
    Role.ADMIN:    ["run_pipeline", "view_data", "manage_stations", "view_logs"],
    Role.ANALYST:  ["view_data", "view_logs", "query_nl"],
    Role.FARMER:   ["view_advisories", "query_nl"],
    Role.VIEWER:   ["view_advisories"],
}


@dataclass
class User:
    username: str
    role:     Role
    stations: List[str] = field(default_factory=list)  # empty = all stations


def can(user: User, action: str) -> bool:
    return action in PERMISSIONS.get(user.role, [])


def filter_stations(user: User, station_ids: List[str]) -> List[str]:
    if not user.stations:
        return station_ids
    return [s for s in station_ids if s in user.stations]


# Demo users
DEMO_USERS = {
    "admin":   User("admin",   Role.ADMIN),
    "analyst": User("analyst", Role.ANALYST),
    "farmer1": User("farmer1", Role.FARMER,  ["KL_TVM", "KL_COK"]),
    "viewer":  User("viewer",  Role.VIEWER),
}
