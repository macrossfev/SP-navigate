"""Time-based constraint."""
from __future__ import annotations

from typing import TYPE_CHECKING
from .base import Constraint

if TYPE_CHECKING:
    from navigate.core.models import Point


class TimeConstraint(Constraint):
    """Limits total time per day (drive + stop + overhead)."""

    def __init__(self, available_field_seconds: float, stop_time_seconds: float):
        self._available = available_field_seconds
        self._stop_s = stop_time_seconds

    @property
    def name(self) -> str:
        return "time"

    def can_add(self, current_points: list, candidate: "Point",
                segment_distance_km: float, segment_time_min: float,
                total_distance_km: float, total_time_min: float) -> bool:
        # total_time_min already includes this segment's drive + stop
        return (total_time_min * 60) <= self._available
