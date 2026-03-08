"""Road network clustering strategy using Amap API for real driving distances.
Provides most accurate clustering based on actual road network.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple, TYPE_CHECKING

from .base import BaseStrategy
from .registry import register
from ..core.models import DayPlan, PlanResult

if TYPE_CHECKING:
    from ..core.models import Point, DistanceMatrix
    from ..core.config import NavigateConfig


@register("road_network")
class RoadNetworkStrategy(BaseStrategy):
    """Road network clustering strategy using Amap API."""
    
    name = "road_network"
    
    def __init__(self, config: "NavigateConfig"):
        super().__init__(config)
    
    def plan(self, points: List["Point"],
             dist_matrix: "DistanceMatrix") -> PlanResult:
        try:
            from sklearn.cluster import DBSCAN
            import numpy as np
        except ImportError:
            raise ImportError("Road network strategy requires scikit-learn")
        
        n = len(points)
        print(f"\n[Road Network] {n} points")
        
        # Get parameters
        eps_km = self.config.strategy.options.get("road_network_eps_km", 5.0)
        min_samples = self.config.strategy.options.get("road_network_min_samples", 3)
        use_amap = self.config.distance.options.get("use_amap_route", True)
        
        print(f"  eps: {eps_km} km")
        print(f"  min_samples: {min_samples}")
        print(f"  Using Amap API: {use_amap}")
        
        # Build driving distance matrix using Amap API
        if use_amap:
            print(f"\n[API] Building {n}x{n} driving distance matrix...")
            print(f"  Estimated API calls: {n * n}")
            print(f"  Estimated time: {n * n * 0.5 / 60:.1f} minutes")
            
            dist_matrix_data = self._build_amap_distance_matrix(points)
            
            # Convert to radians for DBSCAN
            # DBSCAN with precomputed distances uses the distance values directly
            dist_array = np.array(dist_matrix_data)
        else:
            # Fallback to haversine
            print("  Using haversine distance (fallback)")
            coords = np.array([[p.lat, p.lng] for p in points])
            coords_rad = np.radians(coords)
            
            # Calculate haversine distance matrix
            dist_array = np.zeros((n, n))
            for i in range(n):
                for j in range(i + 1, n):
                    d = self._haversine_rad(coords_rad[i], coords_rad[j])
                    dist_array[i, j] = d
                    dist_array[j, i] = d
        
        # Run DBSCAN with precomputed distance matrix
        # Convert eps from km to the same unit as distance matrix
        if use_amap:
            eps_value = eps_km  # Already in km
        else:
            eps_value = eps_km / 6371.0  # Convert to radians
        
        print(f"\n[DBSCAN] Running with eps={eps_value:.4f}")
        
        db = DBSCAN(eps=eps_value, min_samples=min_samples, metric='precomputed', n_jobs=-1)
        labels = db.fit_predict(dist_array)
        
        # Count clusters and outliers
        unique_labels = set(labels)
        n_clusters = len([l for l in unique_labels if l != -1])
        n_outliers = sum(1 for l in labels if l == -1)
        
        print(f"  Found {n_clusters} clusters, {n_outliers} outliers")
        
        # Group points by cluster label
        clusters = {}
        outliers = []
        
        for i, label in enumerate(labels):
            if label == -1:
                outliers.append(i)
            else:
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(i)
        
        # Build result
        days = []
        mat = dist_array if use_amap else dist_matrix.to_list()
        
        for cluster_idx, (label, point_indices) in enumerate(clusters.items()):
            cluster_points = [points[i] for i in point_indices]
            
            # Optimize order within cluster
            optimized_indices = self._optimize_order(point_indices, mat)
            optimized_points = [points[i] for i in optimized_indices]
            
            # Calculate distance
            drive_dist = sum(mat[optimized_indices[i]][optimized_indices[i + 1]]
                           for i in range(len(optimized_indices) - 1))
            drive_time_s = self._estimate_drive_time_s(drive_dist)
            stop_min = len(optimized_points) * self.config.constraints.stop_time_per_point_min
            total_s = drive_time_s + stop_min * 60 + self.config.constraints.roundtrip_overhead_seconds
            
            days.append(DayPlan(
                day=cluster_idx + 1,
                points=optimized_points,
                drive_distance_km=round(drive_dist, 1),
                drive_time_min=round(drive_time_s / 60, 1),
                stop_time_min=stop_min,
                total_time_hours=round(total_s / 3600, 1),
            ))
        
        # Handle outliers
        unassigned = [(points[i], min(mat[i][j] for j in range(n) if j != i))
                     for i in outliers]
        
        if outliers:
            print(f"\n  Outliers: {len(outliers)}")
            for idx in outliers:
                nn_dist = min(mat[idx][j] for j in range(n) if j != idx)
                print(f"    - {points[idx].name} (nearest: {nn_dist:.1f}km)")
        
        return PlanResult(
            strategy_name=f"RoadNetwork(eps={eps_km}km, min={min_samples})",
            days=days,
            all_points=points,
            unassigned=unassigned,
        )
    
    def _build_amap_distance_matrix(self, points: List["Point"]) -> List[List[float]]:
        """Build driving distance matrix using Amap API."""
        from navigate.distance.amap import AmapProvider
        
        n = len(points)
        amap_key = self.config.distance.options.get("amap_key", "de9b271958d5cf291a018d5e95f7e53d")
        avg_speed = self.config.distance.avg_speed_kmh
        
        amap = AmapProvider(api_key=amap_key, request_delay=0.5)
        
        # Initialize distance matrix
        dist_matrix = [[0.0] * n for _ in range(n)]
        
        # Calculate distances
        api_calls = 0
        for i in range(n):
            print(f"  Processing point {i+1}/{n}...")
            for j in range(i + 1, n):
                try:
                    result = amap.get_distance(points[i], points[j])
                    dist = result.distance_km
                    dist_matrix[i][j] = dist
                    dist_matrix[j][i] = dist
                    api_calls += 1
                except Exception as e:
                    # Fallback to haversine
                    d = self._haversine_km(points[i], points[j])
                    dist_matrix[i][j] = d
                    dist_matrix[j][i] = d
                
                # Progress indicator
                if api_calls % 10 == 0:
                    print(f"    API calls: {api_calls}, Progress: {100*(i*n - i*(i+1)//2 + j)/(n*(n-1)/2):.1f}%")
        
        print(f"  Total API calls: {api_calls}")
        return dist_matrix
    
    def _haversine_km(self, a: "Point", b: "Point") -> float:
        """Calculate haversine distance in km."""
        from navigate.distance.haversine import haversine
        return haversine(a.lat, a.lng, b.lat, b.lng)
    
    def _haversine_rad(self, coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """Calculate haversine distance in radians."""
        from navigate.distance.haversine import haversine
        lat1, lng1 = coord1
        lat2, lng2 = coord2
        return haversine(lat1, lng1, lat2, lng2)
    
    def _optimize_order(self, indices: List[int], dist_matrix: List[List[float]]) -> List[int]:
        """Optimize visit order within a cluster using nearest neighbor heuristic."""
        if len(indices) <= 2:
            return indices
        
        # Simple nearest neighbor
        remaining = set(indices)
        order = [indices[0]]
        remaining.remove(indices[0])
        
        while remaining:
            current = order[-1]
            nearest = min(remaining, key=lambda j: dist_matrix[current][j])
            order.append(nearest)
            remaining.remove(nearest)
        
        return order
