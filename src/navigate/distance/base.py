"""Abstract distance provider."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from navigate.core.models import DistanceMatrix, Point


@dataclass
class DistanceResult:
    """Result of a distance calculation between two points."""
    distance_km: float
    duration_min: float
    polyline: list = None  # Optional route polyline [(lat, lng), ...]

    def __post_init__(self):
        if self.polyline is None:
            self.polyline = []


class DistanceProvider(ABC):
    """Abstract interface for distance/route calculation."""

    @abstractmethod
    def get_distance(self, origin: "Point", destination: "Point") -> DistanceResult:
        """Calculate distance and time between two points."""
        ...

    def get_polyline(self, origin: "Point", destination: "Point") -> list:
        """Get route polyline between two points. Default uses get_distance."""
        result = self.get_distance(origin, destination)
        return result.polyline

    @property
    @abstractmethod
    def name(self) -> str:
        ...
