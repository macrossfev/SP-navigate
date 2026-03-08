"""Distance constraint."""
from __future__ import annotations

from typing import TYPE_CHECKING
from .base import Constraint

if TYPE_CHECKING:
    from navigate.core.models import Point


class DistanceConstraint(Constraint):
    """Limits total driving distance per day."""

    def __init__(self, max_km: float):
        self._max_km = max_km

    @property
    def name(self) -> str:
        return "distance"

    def can_add(self, current_points: list, candidate: "Point",
                segment_distance_km: float, segment_time_min: float,
                total_distance_km: float, total_time_min: float) -> bool:
        if self._max_km <= 0:
            return True  # unlimited
        return total_distance_km <= self._max_km
