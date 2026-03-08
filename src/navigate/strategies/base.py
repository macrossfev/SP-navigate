"""Base strategy class for route planning algorithms."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from navigate.core.models import Point, PlanResult, DistanceMatrix
    from navigate.core.config import NavigateConfig


class BaseStrategy(ABC):
    """Abstract base class for route planning strategies."""

    name: str = "base"

    def __init__(self, config: "NavigateConfig"):
        self.config = config

    @abstractmethod
    def plan(self, points: List["Point"],
             dist_matrix: "DistanceMatrix") -> "PlanResult":
        """Execute route planning and return results."""
        ...

    def _estimate_drive_time_s(self, dist_km: float) -> float:
        """Estimate driving time in seconds based on average speed."""
        speed = self.config.distance.avg_speed_kmh
        return dist_km / speed * 3600 if speed > 0 else 0
