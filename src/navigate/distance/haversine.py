"""Offline haversine (great-circle) distance calculation."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .base import DistanceProvider, DistanceResult

if TYPE_CHECKING:
    from navigate.core.models import Point


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance in km between two points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


class HaversineProvider(DistanceProvider):
    """Offline distance calculation using haversine formula.

    Duration is estimated from distance using avg_speed_kmh.
    No network calls required.
    """

    def __init__(self, avg_speed_kmh: float = 35.0):
        self._speed = avg_speed_kmh

    @property
    def name(self) -> str:
        return "haversine"

    def get_distance(self, origin: "Point", destination: "Point") -> DistanceResult:
        dist_km = haversine(origin.lat, origin.lng, destination.lat, destination.lng)
        duration_min = (dist_km / self._speed) * 60 if self._speed > 0 else 0
        return DistanceResult(distance_km=dist_km, duration_min=duration_min)
