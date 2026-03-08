"""Clustering strategy for route planning.
Supports centroid-based and chain-based clustering modes.
"""
from __future__ import annotations

from itertools import permutations
from typing import List, Optional, Tuple, TYPE_CHECKING

from .base import BaseStrategy
from .registry import register
from ..core.models import DayPlan, PlanResult
from ..distance.haversine import haversine

if TYPE_CHECKING:
    from ..core.models import Point, DistanceMatrix
    from ..core.config import NavigateConfig


@register("cluster")
class ClusterStrategy(BaseStrategy):
    name = "cluster"

    def __init__(self, config: "NavigateConfig",
                 base_coord: Optional[Tuple[float, float]] = None):
        super().__init__(config)
        self.base_coord = base_coord  # (lng, lat)

    def plan(self, points: List["Point"],
             dist_matrix: "DistanceMatrix") -> PlanResult:
        n = len(points)
        mat = dist_matrix.to_list()
        max_pts = self.config.constraints.max_daily_points
        method = self.config.strategy.options.get("cluster_method", "centroid")
        print(f"\n[Cluster] {n} points, max {max_pts}/day, method={method}")

        # Outlier detection
        outliers = []
        active_indices = list(range(n))
        threshold = self.config.strategy.options.get("outlier_threshold_km", 5.0)
        if threshold > 0:
            outliers, active_indices = self._detect_outliers(mat, n, threshold)
            if outliers:
                print(f"  Outliers ({threshold}km threshold): {len(outliers)}")
                for idx in outliers:
                    nn_dist = min(mat[idx][j] for j in range(n) if j != idx)
                    print(f"    - {points[idx].name} (nearest: {nn_dist:.1f}km)")

        # Build sub-matrix for active points
        active_points = [points[i] for i in active_indices]
        sub_n = len(active_points)
        sub_dist = [[0.0] * sub_n for _ in range(sub_n)]
        for i in range(sub_n):
            for j in range(i + 1, sub_n):
                d = mat[active_indices[i]][active_indices[j]]
                sub_dist[i][j] = d
                sub_dist[j][i] = d

        if method == "centroid":
            sub_clusters = self._cluster_centroid(active_points, sub_dist, max_pts)
        else:
            sub_clusters = self._cluster_chain(active_points, sub_dist, max_pts)

        # Map back to original indices
        clusters = [[active_indices[i] for i in grp] for grp in sub_clusters]
        print(f"  {len(clusters)} groups (excluding {len(outliers)} outliers)")

        # Optimize visit order within each group
        for idx, grp in enumerate(clusters):
            clusters[idx] = self._optimize_group_order(grp, mat)

        # Build result
        days = []
        for day_idx, grp in enumerate(clusters):
            day_points = [points[i] for i in grp]
            drive_dist = sum(mat[grp[i]][grp[i + 1]]
                             for i in range(len(grp) - 1))
            drive_time_s = self._estimate_drive_time_s(drive_dist)
            stop_min = len(grp) * self.config.constraints.stop_time_per_point_min
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

        unassigned = [(points[i], min(mat[i][j] for j in range(n) if j != i))
                      for i in outliers]

        return PlanResult(
            strategy_name=f"Cluster({method})",
            days=days,
            all_points=points,
            unassigned=unassigned,
        )

    def _detect_outliers(self, dist_matrix: list, n: int,
                         threshold_km: float) -> Tuple[list, list]:
        outliers, active = [], []
        for i in range(n):
            nn_dist = min(dist_matrix[i][j] for j in range(n) if j != i)
            if nn_dist > threshold_km:
                outliers.append(i)
            else:
                active.append(i)
        return outliers, active

    def _cluster_centroid(self, points: list, dist_matrix: list,
                          max_pts: int) -> List[List[int]]:
        """Furthest-point-first seed + centroid attraction."""
        n = len(points)
        unassigned = set(range(n))
        clusters = []

        while unassigned:
            remaining = list(unassigned)
            cx = sum(points[i].lng for i in remaining) / len(remaining)
            cy = sum(points[i].lat for i in remaining) / len(remaining)
            seed = max(remaining,
                       key=lambda i: haversine(points[i].lat, points[i].lng, cy, cx))

            group = [seed]
            unassigned.remove(seed)

            while len(group) < max_pts and unassigned:
                g_lng = sum(points[i].lng for i in group) / len(group)
                g_lat = sum(points[i].lat for i in group) / len(group)
                nearest = min(unassigned,
                              key=lambda j: haversine(points[j].lat, points[j].lng,
                                                      g_lat, g_lng))
                group.append(nearest)
                unassigned.remove(nearest)

            clusters.append(group)
        return clusters

    def _cluster_chain(self, points: list, dist_matrix: list,
                       max_pts: int) -> List[List[int]]:
        """Chain-based greedy clustering from base point."""
        n = len(points)
        unassigned = set(range(n))
        clusters = []

        base_distances = []
        if self.base_coord:
            b_lng, b_lat = self.base_coord
            for p in points:
                base_distances.append(haversine(p.lat, p.lng, b_lat, b_lng))
        else:
            base_distances = [0] * n

        while unassigned:
            seed = min(unassigned, key=lambda i: base_distances[i])
            group = [seed]
            unassigned.remove(seed)

            while len(group) < max_pts and unassigned:
                last = group[-1]
                nearest = min(unassigned, key=lambda j: dist_matrix[last][j])
                group.append(nearest)
                unassigned.remove(nearest)

            clusters.append(group)
        return clusters

    def _optimize_group_order(self, group: List[int],
                              dist_matrix: list) -> List[int]:
        """Optimize visit order: exhaustive for <=5 points, multi-start NN otherwise."""
        if len(group) <= 2:
            return group

        if len(group) <= 5:
            best_order, best_dist = None, float("inf")
            for perm in permutations(group):
                d = sum(dist_matrix[perm[i]][perm[i + 1]]
                        for i in range(len(perm) - 1))
                if d < best_dist:
                    best_dist = d
                    best_order = list(perm)
            return best_order

        best_order, best_dist = None, float("inf")
        for start_idx in range(len(group)):
            remaining = set(group)
            order = [group[start_idx]]
            remaining.remove(group[start_idx])
            while remaining:
                cur = order[-1]
                nxt = min(remaining, key=lambda j: dist_matrix[cur][j])
                order.append(nxt)
                remaining.remove(nxt)
            total = sum(dist_matrix[order[i]][order[i + 1]]
                        for i in range(len(order) - 1))
            if total < best_dist:
                best_dist = total
                best_order = order
        return best_order
