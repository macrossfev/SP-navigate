"""Abstract base class for constraints."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from navigate.core.models import DayPlan, Point


class Constraint(ABC):
    """A constraint that determines whether a point can be added to a day plan."""

    @abstractmethod
    def can_add(self, current_points: list, candidate: "Point",
                segment_distance_km: float, segment_time_min: float,
                total_distance_km: float, total_time_min: float) -> bool:
        """Check if adding candidate to current day is feasible.

        Args:
            current_points: Points already assigned to this day.
            candidate: The point being considered.
            segment_distance_km: Distance from last point to candidate.
            segment_time_min: Drive time from last point to candidate.
            total_distance_km: Accumulated distance for this day (including segment).
            total_time_min: Accumulated time for this day (including segment + stop).
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
