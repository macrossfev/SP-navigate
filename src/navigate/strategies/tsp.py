"""TSP (Traveling Salesman Problem) strategy.
Uses nearest-neighbor heuristic + 2-opt local optimization,
then splits the global route into days based on constraints.
"""
from __future__ import annotations

from typing import List, TYPE_CHECKING

from .base import BaseStrategy
from .registry import register
from ..core.models import DayPlan, PlanResult

if TYPE_CHECKING:
    from ..core.models import Point, DistanceMatrix
    from ..core.config import NavigateConfig


@register("tsp")
class TspStrategy(BaseStrategy):
    name = "tsp"

    def plan(self, points: List["Point"],
             dist_matrix: "DistanceMatrix") -> PlanResult:
        n = len(points)
        mat = dist_matrix.to_list()
        print(f"\n[TSP] {n} points")

        # 1) Nearest-neighbor heuristic
        route = self._nearest_neighbor(mat, start=0)
        init_dist = sum(mat[route[i]][route[i + 1]] for i in range(len(route) - 1))
        print(f"  NN initial distance: {init_dist:.1f} km")

        # 2) 2-opt local optimization
        max_iter = self.config.strategy.options.get("tsp_2opt_iterations", 1000)
        route = self._two_opt(route, mat, max_iter)
        opt_dist = sum(mat[route[i]][route[i + 1]] for i in range(len(route) - 1))
        print(f"  2-opt optimized:     {opt_dist:.1f} km")

        # 3) Split into days
        day_groups = self._split_into_days(route, points, mat)
        print(f"  Split into {len(day_groups)} days")

        # 4) Build result
        days = []
        for day_idx, indices in enumerate(day_groups):
            day_points = [points[i] for i in indices]
            drive_dist = sum(mat[indices[i]][indices[i + 1]]
                             for i in range(len(indices) - 1))
            drive_time_s = self._estimate_drive_time_s(drive_dist)
            stop_min = len(indices) * self.config.constraints.stop_time_per_point_min
            total_s = (drive_time_s + stop_min * 60
                       + self.config.constraints.roundtrip_overhead_seconds)

            days.append(DayPlan(
                day=day_idx + 1,
                points=day_points,
                drive_distance_km=round(drive_dist, 1),
                drive_time_min=round(drive_time_s / 60, 1),
                stop_time_min=stop_min,
                total_time_hours=round(total_s / 3600, 1),
            ))

        return PlanResult(
            strategy_name="TSP",
            days=days,
            all_points=points,
        )

    def _nearest_neighbor(self, dist_matrix: list, start: int = 0) -> List[int]:
        n = len(dist_matrix)
        visited = [False] * n
        route = [start]
        visited[start] = True
        for _ in range(n - 1):
            cur = route[-1]
            best, best_d = -1, float("inf")
            for j in range(n):
                if not visited[j] and dist_matrix[cur][j] < best_d:
                    best_d = dist_matrix[cur][j]
                    best = j
            route.append(best)
            visited[best] = True
        return route

    def _two_opt(self, route: List[int], dist_matrix: list,
                 max_iter: int = 1000) -> List[int]:
        n = len(route)
        improved = True
        iteration = 0
        while improved and iteration < max_iter:
            improved = False
            iteration += 1
            for i in range(1, n - 1):
                for j in range(i + 1, n):
                    d_before = (dist_matrix[route[i - 1]][route[i]]
                                + dist_matrix[route[j]][route[(j + 1) % n]])
                    d_after = (dist_matrix[route[i - 1]][route[j]]
                               + dist_matrix[route[i]][route[(j + 1) % n]])
                    if d_after < d_before:
                        route[i:j + 1] = reversed(route[i:j + 1])
                        improved = True
        return route

    def _split_into_days(self, route: list, points: list,
                         dist_matrix: list) -> List[List[int]]:
        available = self.config.constraints.available_field_seconds
        max_pts = self.config.constraints.max_daily_points
        max_dist = self.config.constraints.max_daily_distance_km
        stop_s = self.config.constraints.stop_time_seconds

        days = []
        current_day = []
        current_time = 0.0
        current_dist = 0.0

        for pt_idx in route:
            if not current_day:
                current_day.append(pt_idx)
                current_time = stop_s
                current_dist = 0.0
            else:
                if len(current_day) >= max_pts:
                    days.append(current_day)
                    current_day = [pt_idx]
                    current_time = stop_s
                    current_dist = 0.0
                    continue

                prev_idx = current_day[-1]
                seg_dist = dist_matrix[prev_idx][pt_idx]
                seg_time = self._estimate_drive_time_s(seg_dist)
                new_time = current_time + seg_time + stop_s
                new_dist = current_dist + seg_dist

                if max_dist > 0 and new_dist > max_dist:
                    days.append(current_day)
                    current_day = [pt_idx]
                    current_time = stop_s
                    current_dist = 0.0
                elif new_time <= available:
                    current_day.append(pt_idx)
                    current_time = new_time
                    current_dist = new_dist
                else:
                    days.append(current_day)
                    current_day = [pt_idx]
                    current_time = stop_s
                    current_dist = 0.0

        if current_day:
            days.append(current_day)
        return days
