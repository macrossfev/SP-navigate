"""
策略A: 全局TSP优化 + 按时间约束分天
先用最近邻+2-opt求解全局最优访问顺序，再按每天可用时间拆分
"""
from typing import List
from .base import BaseStrategy, DayPlan, PlanResult
from ..config import RouteConfig
from ..data_loader import SamplingPoint


class TspStrategy(BaseStrategy):
    name = "tsp"

    def plan(self, points: List[SamplingPoint],
             dist_matrix: List[List[float]]) -> PlanResult:
        n = len(points)
        print(f"\n[策略A: TSP] {n} 个点位")

        # 1) 最近邻启发式
        route = self._nearest_neighbor(dist_matrix, start=0)
        init_dist = sum(dist_matrix[route[i]][route[i + 1]]
                        for i in range(len(route) - 1))
        print(f"  最近邻初始总距离: {init_dist:.1f} km")

        # 2) 2-opt 局部优化
        route = self._two_opt(route, dist_matrix)
        opt_dist = sum(dist_matrix[route[i]][route[i + 1]]
                       for i in range(len(route) - 1))
        print(f"  2-opt优化后总距离: {opt_dist:.1f} km")

        # 3) 按时间约束拆分为多天
        days = self._split_into_days(route, points, dist_matrix)
        print(f"  拆分为 {len(days)} 天")

        # 4) 构建结果
        result = PlanResult(
            strategy_name="TSP全局优化",
            config=self.config,
            days=[],
            points=points,
        )
        for day_idx, day_indices in enumerate(days):
            dp = DayPlan(day=day_idx + 1, point_indices=day_indices)
            dp.points = [points[i] for i in day_indices]

            # 估算距离和时间
            drive_dist = 0
            for i in range(len(day_indices) - 1):
                drive_dist += dist_matrix[day_indices[i]][day_indices[i + 1]]
            dp.drive_distance_km = round(drive_dist, 1)
            dp.drive_time_min = round(self._estimate_drive_time_s(drive_dist) / 60, 1)
            dp.stop_time_min = len(day_indices) * self.config.stop_time_per_point_min
            total_s = (self._estimate_drive_time_s(drive_dist)
                       + dp.stop_time_min * 60
                       + self.config.roundtrip_overhead_seconds)
            dp.total_time_hours = round(total_s / 3600, 1)
            result.days.append(dp)

        return result

    def _nearest_neighbor(self, dist_matrix, start=0) -> List[int]:
        n = len(dist_matrix)
        visited = [False] * n
        route = [start]
        visited[start] = True
        for _ in range(n - 1):
            cur = route[-1]
            best = -1
            best_d = float("inf")
            for j in range(n):
                if not visited[j] and dist_matrix[cur][j] < best_d:
                    best_d = dist_matrix[cur][j]
                    best = j
            route.append(best)
            visited[best] = True
        return route

    def _two_opt(self, route: List[int], dist_matrix) -> List[int]:
        n = len(route)
        improved = True
        iteration = 0
        max_iter = self.config.tsp_2opt_iterations
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

    def _split_into_days(self, route, points, dist_matrix) -> List[List[int]]:
        available = self.config.available_field_seconds
        max_pts = self.config.max_daily_points
        max_dist = self.config.max_daily_distance_km
        stop_s = self.config.stop_time_seconds

        days = []
        current_day = []
        current_time = 0
        current_dist = 0

        for pt_idx in route:
            if not current_day:
                current_day.append(pt_idx)
                current_time = stop_s
                current_dist = 0
            else:
                if len(current_day) >= max_pts:
                    days.append(current_day)
                    current_day = [pt_idx]
                    current_time = stop_s
                    current_dist = 0
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
                    current_dist = 0
                elif new_time <= available:
                    current_day.append(pt_idx)
                    current_time = new_time
                    current_dist = new_dist
                else:
                    days.append(current_day)
                    current_day = [pt_idx]
                    current_time = stop_s
                    current_dist = 0

        if current_day:
            days.append(current_day)
        return days
