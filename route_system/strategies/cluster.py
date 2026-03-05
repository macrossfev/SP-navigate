"""
策略B: 聚类分组
支持两种模式:
  - "chain" (旧): 链式贪心，每次找最后一个点的最近邻
  - "centroid" (新): 最远点优先做种子 + 质心聚拢
"""
from typing import List, Optional, Tuple
from .base import BaseStrategy, DayPlan, PlanResult
from ..config import RouteConfig
from ..data_loader import SamplingPoint, haversine


class ClusterStrategy(BaseStrategy):
    name = "cluster"

    def __init__(self, config: RouteConfig,
                 base_coord: Optional[Tuple[float, float]] = None):
        super().__init__(config)
        self.base_coord = base_coord

    def plan(self, points: List[SamplingPoint],
             dist_matrix: List[List[float]]) -> PlanResult:
        n = len(points)
        max_pts = self.config.max_daily_points
        method = self.config.cluster_seed_method
        print(f"\n[策略B: 聚类] {n} 个点位, 每天≤{max_pts}个, 模式={method}")

        # 离群点检测
        outliers = []
        active_indices = list(range(n))
        threshold = self.config.outlier_threshold_km
        if threshold > 0:
            outliers, active_indices = self._detect_outliers(
                points, dist_matrix, threshold)
            if outliers:
                print(f"  离群点({threshold}km阈值): {len(outliers)} 个")
                for idx in outliers:
                    nn_dist = min(dist_matrix[idx][j] for j in range(n) if j != idx)
                    print(f"    - {points[idx].short_name} (最近邻距离 {nn_dist:.1f}km)")

        # 构建活跃点的子距离矩阵和映射
        active_points = [points[i] for i in active_indices]
        sub_n = len(active_points)
        sub_dist = [[0.0]*sub_n for _ in range(sub_n)]
        for i in range(sub_n):
            for j in range(i+1, sub_n):
                d = dist_matrix[active_indices[i]][active_indices[j]]
                sub_dist[i][j] = d
                sub_dist[j][i] = d

        if method == "centroid":
            sub_clusters = self._cluster_centroid(active_points, sub_dist, max_pts)
        else:
            sub_clusters = self._cluster_chain(active_points, sub_dist, max_pts)

        # 映射回原始索引
        clusters = [[active_indices[i] for i in grp] for grp in sub_clusters]

        print(f"  分为 {len(clusters)} 组 (排除{len(outliers)}个离群点)")

        # 组内优化访问顺序
        for idx, grp in enumerate(clusters):
            clusters[idx] = self._optimize_group_order(grp, dist_matrix)

        # 构建结果
        result = PlanResult(
            strategy_name=f"聚类分组({method})",
            config=self.config, days=[], points=points,
        )
        total_intra = 0
        for day_idx, grp in enumerate(clusters):
            dp = DayPlan(day=day_idx + 1, point_indices=grp)
            dp.points = [points[i] for i in grp]

            drive_dist = sum(dist_matrix[grp[i]][grp[i + 1]]
                             for i in range(len(grp) - 1))
            dp.drive_distance_km = round(drive_dist, 1)
            dp.drive_time_min = round(self._estimate_drive_time_s(drive_dist) / 60, 1)
            dp.stop_time_min = len(grp) * self.config.stop_time_per_point_min
            total_s = (self._estimate_drive_time_s(drive_dist)
                       + dp.stop_time_min * 60
                       + self.config.roundtrip_overhead_seconds)
            dp.total_time_hours = round(total_s / 3600, 1)
            result.days.append(dp)
            total_intra += drive_dist

            names = [points[i].short_name for i in grp]
            print(f"  第{day_idx+1}天 ({len(grp)}点, {drive_dist:.1f}km): "
                  f"{', '.join(names[:3])}{'...' if len(names) > 3 else ''}")

        # 记录离群点信息
        result.outliers = [(points[i], min(dist_matrix[i][j] for j in range(len(points)) if j != i))
                           for i in outliers]

        # 计算紧凑度指标: 每组最大点间距
        max_spreads = []
        for grp in clusters:
            if len(grp) < 2:
                max_spreads.append(0)
                continue
            spread = max(dist_matrix[grp[i]][grp[j]]
                         for i in range(len(grp)) for j in range(i+1, len(grp)))
            max_spreads.append(spread)
        avg_spread = sum(max_spreads) / len(max_spreads)
        print(f"\n  组内点间总距离: {total_intra:.1f} km")
        print(f"  平均组最大跨度: {avg_spread:.2f} km")

        return result

    def _detect_outliers(self, points, dist_matrix, threshold_km):
        """检测离群点: 最近邻距离超过阈值的点"""
        n = len(points)
        outliers = []
        active = []
        for i in range(n):
            nn_dist = min(dist_matrix[i][j] for j in range(n) if j != i)
            if nn_dist > threshold_km:
                outliers.append(i)
            else:
                active.append(i)
        return outliers, active

    def _cluster_centroid(self, points, dist_matrix, max_pts):
        """最远点优先做种子 + 质心聚拢"""
        n = len(points)
        unassigned = set(range(n))
        clusters = []

        while unassigned:
            # 种子: 离剩余点质心最远的点（最孤立的点优先）
            remaining = list(unassigned)
            cx = sum(points[i].lng for i in remaining) / len(remaining)
            cy = sum(points[i].lat for i in remaining) / len(remaining)
            seed = max(remaining,
                       key=lambda i: haversine(points[i].lat, points[i].lng, cy, cx))

            group = [seed]
            unassigned.remove(seed)

            while len(group) < max_pts and unassigned:
                # 计算当前组的质心
                g_lng = sum(points[i].lng for i in group) / len(group)
                g_lat = sum(points[i].lat for i in group) / len(group)

                # 找离质心最近的未分配点
                nearest = min(unassigned,
                              key=lambda j: haversine(points[j].lat, points[j].lng,
                                                      g_lat, g_lng))
                group.append(nearest)
                unassigned.remove(nearest)

            clusters.append(group)

        return clusters

    def _cluster_chain(self, points, dist_matrix, max_pts):
        """旧方案: 链式贪心"""
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
                              dist_matrix: List[List[float]]) -> List[int]:
        """组内全排列(≤5个点) 或 多起点最近邻"""
        if len(group) <= 2:
            return group

        # 5个点以内用全排列找最优
        if len(group) <= 5:
            from itertools import permutations
            best_order = None
            best_dist = float("inf")
            for perm in permutations(group):
                d = sum(dist_matrix[perm[i]][perm[i+1]]
                        for i in range(len(perm)-1))
                if d < best_dist:
                    best_dist = d
                    best_order = list(perm)
            return best_order

        # 大组用多起点最近邻
        best_order = None
        best_dist = float("inf")
        for start_idx in range(len(group)):
            remaining = set(group)
            order = [group[start_idx]]
            remaining.remove(group[start_idx])
            while remaining:
                cur = order[-1]
                nxt = min(remaining, key=lambda j: dist_matrix[cur][j])
                order.append(nxt)
                remaining.remove(nxt)
            total = sum(dist_matrix[order[i]][order[i+1]]
                        for i in range(len(order)-1))
            if total < best_dist:
                best_dist = total
                best_order = order
        return best_order
