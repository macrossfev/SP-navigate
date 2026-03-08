"""
Generic data models for route planning.
Business-agnostic: domain-specific fields go into Point.metadata.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Point:
    """A geographic point to visit."""
    id: str
    name: str
    lng: float
    lat: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def coord(self) -> Tuple[float, float]:
        """Return (lat, lng) tuple for map display."""
        return (self.lat, self.lng)


@dataclass
class DayPlan:
    """A single day's visiting plan."""
    day: int
    points: List[Point]
    drive_distance_km: float = 0.0
    drive_time_min: float = 0.0
    stop_time_min: float = 0.0
    total_time_hours: float = 0.0
    route_polyline: List[Tuple[float, float]] = field(default_factory=list)

    @property
    def point_count(self) -> int:
        return len(self.points)


@dataclass
class PlanResult:
    """Complete planning result."""
    strategy_name: str
    days: List[DayPlan]
    all_points: List[Point]
    unassigned: List[Tuple[Point, float]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_days(self) -> int:
        return len(self.days)

    @property
    def total_points(self) -> int:
        return sum(d.point_count for d in self.days)

    @property
    def total_distance_km(self) -> float:
        return sum(d.drive_distance_km for d in self.days)

    @property
    def total_hours(self) -> float:
        return sum(d.total_time_hours for d in self.days)

    @property
    def max_day_points(self) -> int:
        return max((d.point_count for d in self.days), default=0)

    @property
    def avg_day_distance(self) -> float:
        return self.total_distance_km / self.total_days if self.total_days else 0.0

    def summary(self) -> str:
        lines = [
            f"\n{'=' * 55}",
            f" Result - Strategy: {self.strategy_name}",
            f"{'=' * 55}",
            f" Total points: {self.total_points}",
            f" Total days:   {self.total_days}",
            f" Total dist:   {self.total_distance_km:.1f} km",
            f" Total time:   {self.total_hours:.1f} hours",
            f" Avg daily:    {self.avg_day_distance:.1f} km",
            f"{'=' * 55}",
        ]
        for d in self.days:
            lines.append(
                f" Day {d.day:>2d}: {d.point_count} pts | "
                f"{d.drive_distance_km:>6.1f}km | "
                f"drive {d.drive_time_min:>5.0f}min | "
                f"total {d.total_time_hours:.1f}h"
            )
        if self.unassigned:
            lines.append(f" Unassigned: {len(self.unassigned)} points")
        lines.append(f"{'=' * 55}")
        return "\n".join(lines)


class DistanceMatrix:
    """Symmetric distance matrix for N points."""

    def __init__(self, size: int):
        self._size = size
        self._data: List[List[float]] = [[0.0] * size for _ in range(size)]

    @property
    def size(self) -> int:
        return self._size

    def get(self, i: int, j: int) -> float:
        return self._data[i][j]

    def set(self, i: int, j: int, value: float):
        self._data[i][j] = value
        self._data[j][i] = value

    def row(self, i: int) -> List[float]:
        return self._data[i]

    def to_list(self) -> List[List[float]]:
        return self._data

    @classmethod
    def from_points(cls, points: List[Point], dist_func) -> "DistanceMatrix":
        """Build matrix using a distance function: dist_func(p1, p2) -> float."""
        n = len(points)
        matrix = cls(n)
        for i in range(n):
            for j in range(i + 1, n):
                d = dist_func(points[i], points[j])
                matrix.set(i, j, d)
        return matrix
