"""Point count constraint."""
from __future__ import annotations

from typing import TYPE_CHECKING
from .base import Constraint

if TYPE_CHECKING:
    from navigate.core.models import Point


class CountConstraint(Constraint):
    """Limits number of points per day."""

    def __init__(self, max_points: int):
        self._max = max_points

    @property
    def name(self) -> str:
        return "count"

    def can_add(self, current_points: list, candidate: "Point",
                segment_distance_km: float, segment_time_min: float,
                total_distance_km: float, total_time_min: float) -> bool:
        return (len(current_points) + 1) <= self._max
