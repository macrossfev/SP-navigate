"""Adaptive Area Expansion Clustering Strategy.
Clusters points by expanding area incrementally.
When adding a point requires area expansion > threshold, stop expanding.
"""
from __future__ import annotations

from typing import List, Optional, Tuple, TYPE_CHECKING

from .base import BaseStrategy
from .registry import register
from ..core.models import DayPlan, PlanResult

if TYPE_CHECKING:
    from ..core.models import Point, DistanceMatrix
    from ..core.config import NavigateConfig


@register("area_expansion")
class AreaExpansionStrategy(BaseStrategy):
    """Adaptive area expansion clustering strategy."""
    
    name = "area_expansion"
    
    def __init__(self, config: "NavigateConfig"):
        super().__init__(config)
    
    def plan(self, points: List["Point"],
             dist_matrix: "DistanceMatrix") -> PlanResult:
        try:
            from scipy.spatial import ConvexHull
            import numpy as np
        except ImportError:
            raise ImportError("Area expansion strategy requires scipy")
        
        n = len(points)
        print(f"\n[Area Expansion] {n} points")
        
        # Get parameters
        area_threshold = self.config.strategy.options.get("area_expansion_threshold_km2", 50.0)
        min_points_per_cluster = self.config.strategy.options.get("min_points_per_cluster", 3)
        max_points_per_cluster = self.config.strategy.options.get("max_points_per_cluster", 50)
        
        print(f"  Area threshold: {area_threshold} km²")
        print(f"  Min points per cluster: {min_points_per_cluster}")
        print(f"  Max points per cluster: {max_points_per_cluster}")
        
        # Convert points to numpy array (lat, lng)
        coords = np.array([[p.lat, p.lng] for p in points])
        
        # Initialize clusters
        unassigned = set(range(n))
        clusters = []
        
        # Sort points by x-coordinate (lng) to start from west to east
        sorted_indices = sorted(range(n), key=lambda i: coords[i][1])
        
        print(f"\n[Clustering] Starting...")
        
        while len(unassigned) >= min_points_per_cluster:
            # Start new cluster with the first unassigned point
            seed_idx = sorted_indices[0] if sorted_indices[0] in unassigned else next(iter(unassigned))
            current_cluster = [seed_idx]
            unassigned.remove(seed_idx)
            if seed_idx in sorted_indices:
                sorted_indices.remove(seed_idx)
            
            # Expand cluster
            expanded = True
            while expanded and len(current_cluster) < max_points_per_cluster:
                expanded = False
                
                # Find nearest unassigned point
                if not unassigned:
                    break
                
                current_coords = coords[current_cluster]
                current_hull = ConvexHull(current_coords)
                current_area = current_hull.volume  # In 2D, this is area
                
                # Try to add nearest point
                best_candidate = None
                best_increment = float('inf')
                
                for candidate_idx in unassigned:
                    # Calculate area increment
                    test_cluster = current_cluster + [candidate_idx]
                    test_coords = coords[test_cluster]
                    
                    try:
                        test_hull = ConvexHull(test_coords)
                        test_area = test_hull.volume
                        increment = test_area - current_area
                        
                        if increment < best_increment:
                            best_increment = increment
                            best_candidate = candidate_idx
                    except:
                        # ConvexHull failed (e.g., collinear points)
                        continue
                
                # Check if we can add this point
                if best_candidate is not None:
                    if best_increment <= area_threshold:
                        current_cluster.append(best_candidate)
                        unassigned.remove(best_candidate)
                        expanded = True
                        print(f"  Added point, area increment: {best_increment:.2f} km²")
                    else:
                        print(f"  Area increment {best_increment:.2f} km² > threshold {area_threshold} km², stopping expansion")
                        break
            
            if len(current_cluster) >= min_points_per_cluster:
                clusters.append(current_cluster)
                print(f"Cluster {len(clusters)}: {len(current_cluster)} points")
            else:
                # Too small, add to outliers
                for idx in current_cluster:
                    unassigned.add(idx)
        
        # Build result
        days = []
        mat = dist_matrix.to_list()
        
        for cluster_idx, cluster_indices in enumerate(clusters):
            cluster_points = [points[i] for i in cluster_indices]
            
            # Optimize order within cluster
            optimized_indices = self._optimize_order(cluster_indices, mat)
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
        
        # Handle remaining points (outliers)
        unassigned_list = list(unassigned)
        unassigned_points = [(points[i], min(mat[i][j] for j in range(n) if j != i))
                            for i in unassigned_list]
        
        if unassigned_list:
            print(f"\nUnassigned points: {len(unassigned_list)}")
            for idx in unassigned_list:
                nn_dist = min(mat[idx][j] for j in range(n) if j != idx)
                print(f"  - {points[idx].name} (nearest: {nn_dist:.1f}km)")
        
        return PlanResult(
            strategy_name=f"AreaExpansion(threshold={area_threshold}km²)",
            days=days,
            all_points=points,
            unassigned=unassigned_points,
        )
    
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
