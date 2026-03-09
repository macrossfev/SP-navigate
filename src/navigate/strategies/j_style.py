"""
J-Style Algorithm: Constrained Clustering with Minimum Enclosing Circle Optimization

固定圆数量、单圆最小点数约束下，以总面积最小为目标的约束聚类 + 最小包围圆组合优化算法

学术表述：带基数约束（每个簇大小≥m）的 K-聚类优化问题，目标函数为各簇最小包围圆面积之和最小
"""
from __future__ import annotations

import random
import numpy as np
from typing import List, Optional, Tuple, TYPE_CHECKING

from .base import BaseStrategy
from .registry import register
from ..core.models import DayPlan, PlanResult

if TYPE_CHECKING:
    from ..core.models import Point, DistanceMatrix
    from ..core.config import NavigateConfig


@register("j_style")
class JStyleStrategy(BaseStrategy):
    """
    J-Style Constrained Clustering with Minimum Enclosing Circle
    
    Algorithm:
    1. Initialize K clusters using K-Means++
    2. Enforce minimum points constraint (m points per cluster)
    3. Compute Minimum Enclosing Circle (MEC) for each cluster
    4. Optimize: minimize sum of MEC areas
    5. Iteratively reassign points to reduce total area
    """
    
    name = "j_style"
    
    def __init__(self, config: "NavigateConfig"):
        super().__init__(config)
    
    def plan(self, points: List["Point"],
             dist_matrix: "DistanceMatrix") -> PlanResult:
        try:
            from sklearn.cluster import KMeans
        except ImportError:
            raise ImportError("J-Style strategy requires scikit-learn")
        
        n = len(points)
        print(f"\n[J-Style Algorithm] {n} points")

        # Get parameters
        k_clusters = self.config.strategy.options.get("j_style_k_clusters", 5)
        min_points_per_cluster = self.config.strategy.options.get("j_style_min_points", 10)
        max_points_per_cluster = self.config.strategy.options.get("j_style_max_points", 50)
        max_iterations = self.config.strategy.options.get("j_style_max_iterations", 50)

        # Adjust k if needed (support min_points=1)
        min_points_per_cluster = max(1, min_points_per_cluster)
        max_points_per_cluster = max(min_points_per_cluster, max_points_per_cluster)
        k_clusters = min(k_clusters, n // min_points_per_cluster) if min_points_per_cluster > 0 else k_clusters
        k_clusters = max(1, k_clusters)

        print(f"  K clusters: {k_clusters}")
        print(f"  Min points per cluster: {min_points_per_cluster}")
        print(f"  Max points per cluster: {max_points_per_cluster}")
        print(f"  Max iterations: {max_iterations}")
        
        # Convert points to numpy array
        coords = np.array([[p.lat, p.lng] for p in points])
        
        # Step 1: Initialize with K-Means++
        print("\n[Step 1] Initializing with K-Means++...")
        kmeans = KMeans(n_clusters=k_clusters, init='k-means++', n_init=10, random_state=42)
        labels = kmeans.fit_predict(coords)
        
        # Step 2: Enforce minimum and maximum points constraint
        print("\n[Step 2] Enforcing min/max points constraint...")
        labels = self._enforce_min_max_constraint(labels, coords, k_clusters, min_points_per_cluster, max_points_per_cluster)
        
        # Step 3: Compute initial MEC for each cluster
        print("\n[Step 3] Computing Minimum Enclosing Circles...")
        circles = []
        for k in range(k_clusters):
            cluster_points = coords[labels == k]
            if len(cluster_points) > 0:
                center, radius = self._minimum_enclosing_circle(cluster_points)
                circles.append((center, radius))
            else:
                circles.append((cluster_points.mean(axis=0), 0))
        
        initial_area = sum(np.pi * r**2 for _, r in circles)
        print(f"  Initial total area: {initial_area:.2f} km²")
        
        # Step 4: Optimize - Iteratively reassign points to reduce total area
        print(f"\n[Step 4] Optimizing (max {max_iterations} iterations)...")
        for iteration in range(max_iterations):
            improved = False

            # Try moving each point to neighboring clusters
            for i in range(n):
                current_cluster = labels[i]

                # Check if we can move this point (maintain min constraint)
                if sum(labels == current_cluster) <= min_points_per_cluster:
                    continue

                # Try moving to each other cluster
                best_cluster = current_cluster
                best_area_reduction = 0

                for k in range(k_clusters):
                    if k == current_cluster:
                        continue

                    # Check max constraint for target cluster
                    if sum(labels == k) >= max_points_per_cluster:
                        continue

                    # Temporarily move point
                    test_labels = labels.copy()
                    test_labels[i] = k

                    # Check constraint
                    if sum(test_labels == k) < min_points_per_cluster:
                        continue

                    # Compute new total area
                    test_area = self._compute_total_area(coords, test_labels, k_clusters)
                    current_area = self._compute_total_area(coords, labels, k_clusters)

                    area_reduction = current_area - test_area
                    if area_reduction > best_area_reduction:
                        best_area_reduction = area_reduction
                        best_cluster = k

                # Apply best move
                if best_cluster != current_cluster and best_area_reduction > 0.01:
                    labels[i] = best_cluster
                    improved = True
            
            # Compute new circles
            circles = []
            for k in range(k_clusters):
                cluster_points = coords[labels == k]
                if len(cluster_points) > 0:
                    center, radius = self._minimum_enclosing_circle(cluster_points)
                    circles.append((center, radius))
                else:
                    circles.append((cluster_points.mean(axis=0) if len(cluster_points) > 0 else np.array([0, 0]), 0))
            
            total_area = sum(np.pi * r**2 for _, r in circles)
            print(f"  Iteration {iteration + 1}: Total area = {total_area:.2f} km²")
            
            if not improved:
                print(f"  Converged at iteration {iteration + 1}")
                break
        
        final_area = sum(np.pi * r**2 for _, r in circles)
        print(f"\n  Final total area: {final_area:.2f} km²")
        print(f"  Area reduction: {(initial_area - final_area) / initial_area * 100:.1f}%")
        
        # Build result
        days = []
        mat = dist_matrix.to_list()
        
        for cluster_idx in range(k_clusters):
            cluster_indices = [i for i in range(n) if labels[i] == cluster_idx]
            cluster_points = [points[i] for i in cluster_indices]
            
            if len(cluster_points) == 0:
                continue
            
            # Optimize order within cluster
            optimized_indices = self._optimize_order(cluster_indices, mat)
            optimized_points = [points[i] for i in optimized_indices]
            
            # Calculate distance
            drive_dist = sum(mat[optimized_indices[i]][optimized_indices[i + 1]]
                           for i in range(len(optimized_indices) - 1))
            drive_time_s = self._estimate_drive_time_s(drive_dist)
            stop_min = len(optimized_points) * self.config.constraints.stop_time_per_point_min
            total_s = drive_time_s + stop_min * 60 + self.config.constraints.roundtrip_overhead_seconds
            
            # Get MEC info
            center, radius = circles[cluster_idx]

            days.append(DayPlan(
                day=cluster_idx + 1,
                points=optimized_points,
                drive_distance_km=round(drive_dist, 1),
                drive_time_min=round(drive_time_s / 60, 1),
                stop_time_min=stop_min,
                total_time_hours=round(total_s / 3600, 1),
            ))
        
        return PlanResult(
            strategy_name=f"J-Style(K={k_clusters},min={min_points_per_cluster})",
            days=days,
            all_points=points,
            metrics={
                "total_area_km2": round(final_area, 2),
                "k_clusters": k_clusters,
                "min_points_per_cluster": min_points_per_cluster,
            }
        )
    
    def _enforce_min_max_constraint(self, labels, coords, k_clusters, min_points, max_points):
        """Enforce minimum and maximum points per cluster constraint."""
        n = len(coords)
        labels = labels.copy()

        for iteration in range(100):  # Max iterations
            improved = False

            # Step 1: Find clusters violating min constraint
            violating_min = [k for k in range(k_clusters) if sum(labels == k) < min_points]

            if violating_min:
                # For each violating cluster, steal points from largest cluster
                for k in violating_min:
                    largest_k = max(range(k_clusters), key=lambda x: sum(labels == x))
                    if largest_k == k:
                        continue

                    # Find points closest to violating cluster center
                    cluster_center = coords[labels == k].mean(axis=0) if sum(labels == k) > 0 else coords[labels == largest_k].mean(axis=0)
                    candidate_indices = [i for i in range(n) if labels[i] == largest_k]

                    # Sort by distance to violating cluster center
                    candidate_indices.sort(key=lambda i: np.sum((coords[i] - cluster_center)**2))

                    # Move points
                    points_to_move = min(min_points - sum(labels == k), len(candidate_indices))
                    for i in candidate_indices[:points_to_move]:
                        labels[i] = k
                        improved = True

            # Step 2: Find clusters violating max constraint
            violating_max = [k for k in range(k_clusters) if sum(labels == k) > max_points]

            if violating_max:
                # For each violating cluster, move excess points to ANY cluster that can accept
                for k in violating_max:
                    # Find points furthest from cluster center
                    cluster_center = coords[labels == k].mean(axis=0)
                    candidate_indices = [i for i in range(n) if labels[i] == k]

                    # Sort by distance to cluster center (furthest first)
                    candidate_indices.sort(key=lambda i: np.sum((coords[i] - cluster_center)**2), reverse=True)

                    # Move excess points one by one
                    excess = sum(labels == k) - max_points
                    for idx_to_move in candidate_indices[:excess]:
                        # Find best target cluster (can accept point and closest)
                        point_coord = coords[idx_to_move]
                        best_target = None
                        best_distance = float('inf')

                        for target_k in range(k_clusters):
                            if target_k == k:
                                continue
                            # Check if target can accept
                            if sum(labels == target_k) >= max_points:
                                continue

                            # Calculate distance to target center
                            target_center = coords[labels == target_k].mean(axis=0) if sum(labels == target_k) > 0 else point_coord
                            distance = np.sum((point_coord - target_center)**2)

                            if distance < best_distance:
                                best_distance = distance
                                best_target = target_k

                        # Move to best target
                        if best_target is not None:
                            labels[idx_to_move] = best_target
                            improved = True

            print(f"  Iteration {iteration + 1}: improved={improved}, cluster_sizes={[sum(labels == k) for k in range(k_clusters)]}")

            if not improved:
                # Check if all constraints are satisfied
                final_sizes = [sum(labels == k) for k in range(k_clusters)]
                violating_final_min = [k for k in range(k_clusters) if final_sizes[k] < min_points]
                violating_final_max = [k for k in range(k_clusters) if final_sizes[k] > max_points]

                if violating_final_min or violating_final_max:
                    print(f"  Warning: Could not satisfy all constraints")
                    print(f"    Final sizes: {final_sizes}")
                    print(f"    Min violations: {violating_final_min}")
                    print(f"    Max violations: {violating_final_max}")
                break

        return labels
    
    def _minimum_enclosing_circle(self, points):
        """
        Compute Minimum Enclosing Circle using Welzl's algorithm (iterative approximation).
        
        Returns: (center, radius)
        """
        if len(points) == 0:
            return np.array([0, 0]), 0
        elif len(points) == 1:
            return points[0], 0
        elif len(points) == 2:
            center = (points[0] + points[1]) / 2
            radius = np.linalg.norm(points[0] - points[1]) / 2
            return center, radius
        
        # Iterative approximation
        # Start with bounding circle of first 3 points
        center = points[:3].mean(axis=0)
        radius = max(np.linalg.norm(points[i] - center) for i in range(3))
        
        # Iteratively expand to include all points
        for _ in range(100):
            # Find point furthest from center
            distances = [np.linalg.norm(p - center) for p in points]
            max_idx = np.argmax(distances)
            max_dist = distances[max_idx]
            
            if max_dist <= radius:
                break
            
            # Expand circle to include this point
            furthest_point = points[max_idx]
            direction = furthest_point - center
            direction = direction / np.linalg.norm(direction)
            
            # Move center towards furthest point
            center = center + direction * (max_dist - radius) / 2
            radius = max_dist
        
        return center, radius
    
    def _compute_total_area(self, coords, labels, k_clusters):
        """Compute total MEC area for all clusters."""
        total_area = 0

        for k in range(k_clusters):
            cluster_points = coords[labels == k]
            if len(cluster_points) > 0:
                _, radius = self._minimum_enclosing_circle(cluster_points)
                total_area += np.pi * radius**2

        return total_area
    
    def _optimize_order(self, indices: List[int], dist_matrix: List[List[float]]) -> List[int]:
        """Optimize visit order within a cluster using nearest neighbor heuristic."""
        if len(indices) <= 2:
            return indices
        
        remaining = set(indices)
        order = [indices[0]]
        remaining.remove(indices[0])
        
        while remaining:
            current = order[-1]
            nearest = min(remaining, key=lambda j: dist_matrix[current][j])
            order.append(nearest)
            remaining.remove(nearest)
        
        return order
