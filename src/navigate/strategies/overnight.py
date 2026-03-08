"""
Overnight strategy for multi-day trips with hotel stays.

This strategy handles two trip types:
1. Single-day trips: Company -> Points -> Company (same day return)
2. Overnight trips: 
   - Day 1: Company -> Points -> Hotel
   - Day 2: Hotel -> Points -> Company

Points are classified based on distance from company:
- Points within threshold: single-day trips
- Points beyond threshold: overnight trips (clustered with hotel selection)
"""
from __future__ import annotations

from typing import List, Optional, Tuple, Dict, TYPE_CHECKING

from .base import BaseStrategy
from .registry import register
from ..core.models import (
    DayPlan, PlanResult, Point, HotelInfo, TripType, DistanceMatrix
)
from ..distance.haversine import haversine

if TYPE_CHECKING:
    from ..core.config import NavigateConfig


@register("overnight")
class OvernightStrategy(BaseStrategy):
    """Overnight trip strategy with hotel stay optimization."""
    
    name = "overnight"
    
    def __init__(self, config: "NavigateConfig",
                 base_coord: Optional[Tuple[float, float]] = None,
                 base_name: str = "公司"):
        super().__init__(config)
        self.base_coord = base_coord  # (lng, lat)
        self.base_name = base_name
        
    def plan(self, points: List[Point],
             dist_matrix: DistanceMatrix) -> PlanResult:
        n = len(points)
        mat = dist_matrix.to_list()
        
        # Get configuration
        threshold = self.config.constraints.overnight_threshold_km
        hotel_radius = self.config.constraints.overnight_hotel_radius_km
        max_pts = self.config.constraints.max_daily_points
        max_hours = self.config.constraints.max_daily_hours
        single_day_max_hours = (
            self.config.constraints.single_day_max_hours 
            or max_hours
        )
        
        print(f"\n[Overnight] {n} points")
        print(f"  Threshold: {threshold} km")
        print(f"  Max pts/day: {max_pts}")
        print(f"  Max hours (single): {single_day_max_hours}h")
        print(f"  Max hours (overnight): {max_hours}h")
        
        # Classify points: single-day vs overnight
        single_day_indices, overnight_indices = self._classify_points(
            points, n, mat, threshold
        )
        
        print(f"  Single-day points: {len(single_day_indices)}")
        print(f"  Overnight points: {len(overnight_indices)}")
        
        days = []
        day_counter = 1
        
        # Plan single-day trips
        if single_day_indices:
            single_days = self._plan_single_days(
                single_day_indices, points, mat, 
                max_pts, single_day_max_hours
            )
            for sd in single_days:
                sd.day = day_counter
                day_counter += 1
                sd.start_point_name = self.base_name
                sd.end_point_name = self.base_name
            days.extend(single_days)
        
        # Plan overnight trips
        if overnight_indices:
            overnight_days = self._plan_overnight_trips(
                overnight_indices, points, mat,
                max_pts, max_hours, hotel_radius
            )
            for od in overnight_days:
                od.day = day_counter
                day_counter += 1
            days.extend(overnight_days)
        
        # Sort days by day number
        days.sort(key=lambda d: d.day)
        
        return PlanResult(
            strategy_name="Overnight",
            days=days,
            all_points=points,
            metrics={
                "single_day_points": len(single_day_indices),
                "overnight_points": len(overnight_indices),
                "overnight_trip_days": sum(
                    1 for d in days if d.is_overnight
                ),
            }
        )
    
    def _classify_points(
        self, points: List[Point], n: int, mat: List[List[float]],
        threshold: float
    ) -> Tuple[List[int], List[int]]:
        """Classify points into single-day and overnight groups."""
        if not self.base_coord:
            # No base coordinate, all points are single-day
            return list(range(n)), []
        
        base_lng, base_lat = self.base_coord
        single_day, overnight = [], []
        
        for i, p in enumerate(points):
            dist = haversine(p.lat, p.lng, base_lat, base_lng)
            if threshold > 0 and dist > threshold:
                overnight.append(i)
            else:
                single_day.append(i)
        
        return single_day, overnight
    
    def _plan_single_days(
        self, indices: List[int], points: List[Point],
        mat: List[List[float]], max_pts: int, max_hours: float
    ) -> List[DayPlan]:
        """Plan single-day round trips."""
        # Use TSP strategy for single-day points
        from .tsp import TspStrategy
        
        # Create sub-problem
        sub_points = [points[i] for i in indices]
        sub_n = len(sub_points)
        sub_mat = [[0.0] * sub_n for _ in range(sub_n)]
        for i in range(sub_n):
            for j in range(i + 1, sub_n):
                d = mat[indices[i]][indices[j]]
                sub_mat[i][j] = d
                sub_mat[j][i] = d
        
        # Create a minimal config for TSP
        from ..core.config import NavigateConfig, ConstraintsConfig
        tsp_config = NavigateConfig()
        tsp_config.constraints = ConstraintsConfig(
            max_daily_hours=max_hours,
            max_daily_points=max_pts,
            stop_time_per_point_min=self.config.constraints.stop_time_per_point_min,
            roundtrip_overhead_min=self.config.constraints.roundtrip_overhead_min,
        )
        tsp_config.distance = self.config.distance
        
        tsp = TspStrategy(tsp_config)
        sub_matrix = DistanceMatrix(sub_n)
        for i in range(sub_n):
            for j in range(sub_n):
                sub_matrix.set(i, j, sub_mat[i][j])
        
        result = tsp.plan(sub_points, sub_matrix)
        
        # Mark all as single-day trips
        for day in result.days:
            day.trip_type = TripType.SINGLE_DAY
        
        return result.days
    
    def _plan_overnight_trips(
        self, indices: List[int], points: List[Point],
        mat: List[List[float]], max_pts: int, max_hours: float,
        hotel_radius: float
    ) -> List[DayPlan]:
        """Plan overnight trips with hotel stays."""
        sub_points = [points[i] for i in indices]
        sub_n = len(sub_points)
        
        # Cluster overnight points
        clusters = self._cluster_overnight_points(
            sub_points, mat, max_pts, hotel_radius
        )
        
        print(f"  Overnight clusters: {len(clusters)}")
        
        days = []
        for cluster_idx, cluster in enumerate(clusters):
            cluster_points = [sub_points[i] for i in cluster]
            
            # Select hotel location (centroid of cluster)
            hotel = self._select_hotel_location(
                cluster_points, sub_points, mat, hotel_radius
            )
            
            # Split into Day 1 and Day 2
            day1_points, day2_points = self._split_overnight_cluster(
                cluster_points, hotel, mat
            )
            
            # Create Day 1: Company -> Points -> Hotel
            if day1_points:
                day1 = self._create_day_plan(
                    day1_points, mat, cluster_idx * 2 + 1,
                    TripType.OVERNIGHT, hotel,
                    is_day1=True
                )
                days.append(day1)
            
            # Create Day 2: Hotel -> Points -> Company
            if day2_points:
                day2 = self._create_day_plan(
                    day2_points, mat, cluster_idx * 2 + 2,
                    TripType.OVERNIGHT, hotel,
                    is_day1=False
                )
                days.append(day2)
        
        return days
    
    def _cluster_overnight_points(
        self, points: List[Point], mat: List[List[float]],
        max_pts: int, hotel_radius: float
    ) -> List[List[int]]:
        """Cluster overnight points using centroid-based method."""
        n = len(points)
        unassigned = set(range(n))
        clusters = []
        
        while unassigned:
            # Find seed point (furthest from base)
            remaining = list(unassigned)
            if self.base_coord:
                base_lng, base_lat = self.base_coord
                seed = max(
                    remaining,
                    key=lambda i: haversine(
                        points[i].lat, points[i].lng, base_lat, base_lng
                    )
                )
            else:
                seed = remaining[0]
            
            # Grow cluster
            group = [seed]
            unassigned.remove(seed)
            
            while len(group) < max_pts and unassigned:
                # Add nearest neighbor
                last = group[-1]
                nearest = min(
                    unassigned,
                    key=lambda j: mat[points.index(points[last])][points.index(points[j])]
                )
                # Use sub-matrix indices
                nearest = min(unassigned, key=lambda j: mat[last][j])
                group.append(nearest)
                unassigned.remove(nearest)
            
            clusters.append(group)
        
        return clusters
    
    def _select_hotel_location(
        self, cluster_points: List[Point], all_points: List[Point],
        mat: List[List[float]], hotel_radius: float
    ) -> HotelInfo:
        """Select hotel location near cluster centroid."""
        # Calculate centroid
        avg_lng = sum(p.lng for p in cluster_points) / len(cluster_points)
        avg_lat = sum(p.lat for p in cluster_points) / len(cluster_points)
        
        # Find nearest point to centroid as hotel reference
        nearest_point = min(
            cluster_points,
            key=lambda p: haversine(p.lat, p.lng, avg_lat, avg_lng)
        )
        
        return HotelInfo(
            name=f"住宿点 (近 {nearest_point.name})",
            lng=avg_lng,
            lat=avg_lat,
            near_point_id=nearest_point.id,
        )
    
    def _split_overnight_cluster(
        self, cluster_points: List[Point], hotel: HotelInfo,
        mat: List[List[float]]
    ) -> Tuple[List[Point], List[Point]]:
        """Split cluster into Day 1 and Day 2 points."""
        if len(cluster_points) <= 1:
            return cluster_points, []
        
        # Use TSP to find optimal order
        from .tsp import TspStrategy
        from ..core.config import NavigateConfig, ConstraintsConfig
        
        n = len(cluster_points)
        sub_mat = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                sub_mat[i][j] = mat[i][j]
                sub_mat[j][i] = sub_mat[i][j]
        
        tsp_config = NavigateConfig()
        tsp_config.constraints = ConstraintsConfig()
        tsp_config.distance = self.config.distance
        
        tsp = TspStrategy(tsp_config)
        route = tsp._nearest_neighbor(sub_mat, start=0)
        route = tsp._two_opt(route, sub_mat, 100)
        
        # Split route in half
        mid = len(route) // 2
        day1_indices = route[:mid]
        day2_indices = route[mid:]
        
        day1_points = [cluster_points[i] for i in day1_indices]
        day2_points = [cluster_points[i] for i in day2_indices]
        
        return day1_points, day2_points
    
    def _create_day_plan(
        self, points: List[Point], mat: List[List[float]],
        day_num: int, trip_type: TripType, hotel: HotelInfo,
        is_day1: bool
    ) -> DayPlan:
        """Create a DayPlan for overnight trip."""
        n = len(points)
        
        # Calculate route distance
        drive_dist = 0.0
        
        # Add base to first point
        if self.base_coord and is_day1:
            base_lng, base_lat = self.base_coord
            drive_dist += haversine(points[0].lat, points[0].lng, base_lat, base_lng)
        elif hotel:
            drive_dist += haversine(
                points[0].lat, points[0].lng, hotel.lat, hotel.lng
            )
        
        # Add inter-point distances
        for i in range(len(points) - 1):
            drive_dist += mat[i][i + 1] if i < n and i + 1 < n else 0
        
        # Add last point to destination
        if points:
            last_point = points[-1]
            if is_day1 and hotel:
                drive_dist += haversine(
                    hotel.lat, hotel.lng, last_point.lat, last_point.lng
                )
            elif self.base_coord:
                base_lng, base_lat = self.base_coord
                drive_dist += haversine(
                    last_point.lat, last_point.lng, base_lat, base_lng
                )
        
        drive_time_s = self._estimate_drive_time_s(drive_dist)
        stop_min = len(points) * self.config.constraints.stop_time_per_point_min
        total_s = drive_time_s + stop_min * 60
        
        return DayPlan(
            day=day_num,
            points=points,
            drive_distance_km=round(drive_dist, 1),
            drive_time_min=round(drive_time_s / 60, 1),
            stop_time_min=stop_min,
            total_time_hours=round(total_s / 3600, 1),
            trip_type=trip_type,
            hotel=hotel if trip_type == TripType.OVERNIGHT else None,
            start_point_name=self.base_name if is_day1 else (hotel.name if hotel else ""),
            end_point_name=(hotel.name if hotel else "") if is_day1 else self.base_name,
        )
