"""DBSCAN density-based clustering strategy for route planning.
Automatically discovers clusters of arbitrary shape.
"""
from __future__ import annotations

from typing import List, Optional, Tuple, TYPE_CHECKING

from .base import BaseStrategy
from .registry import register
from ..core.models import DayPlan, PlanResult

if TYPE_CHECKING:
    from ..core.models import Point, DistanceMatrix
    from ..core.config import NavigateConfig


@register("dbscan")
class DbscanStrategy(BaseStrategy):
    """DBSCAN density-based clustering strategy."""
    
    name = "dbscan"
    
    def __init__(self, config: "NavigateConfig"):
        super().__init__(config)
    
    def plan(self, points: List["Point"],
             dist_matrix: "DistanceMatrix") -> PlanResult:
        try:
            from sklearn.cluster import DBSCAN
            import numpy as np
        except ImportError:
            raise ImportError("DBSCAN requires scikit-learn. Install with: pip install scikit-learn")
        
        n = len(points)
        print(f"\n[DBSCAN] {n} points")
        
        # Get parameters
        eps_km = self.config.strategy.options.get("dbscan_eps_km", 5.0)
        min_samples = self.config.strategy.options.get("dbscan_min_samples", 3)
        
        # Convert eps from km to radians (for haversine metric)
        eps_rad = eps_km / 6371.0
        
        print(f"  eps: {eps_km} km ({eps_rad:.6f} rad)")
        print(f"  min_samples: {min_samples}")
        
        # Prepare coordinates (convert to radians for haversine metric)
        coords = np.array([[p.lat, p.lng] for p in points])
        coords_rad = np.radians(coords)
        
        # Run DBSCAN
        db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric='haversine', n_jobs=-1)
        labels = db.fit_predict(coords_rad)
        
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
        mat = dist_matrix.to_list()
        
        for cluster_idx, indices in enumerate(clusters.items()):
            label, point_indices = indices
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
            print(f"  Outliers: {len(outliers)}")
            for idx in outliers:
                nn_dist = min(mat[idx][j] for j in range(n) if j != idx)
                print(f"    - {points[idx].name} (nearest: {nn_dist:.1f}km)")
        
        return PlanResult(
            strategy_name=f"DBSCAN(eps={eps_km}km, min={min_samples})",
            days=days,
            all_points=points,
            unassigned=unassigned,
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
