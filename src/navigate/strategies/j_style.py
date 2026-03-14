"""
J-Style Algorithm: Constrained Clustering with Minimum Enclosing Circle Optimization

固定圆数量、单圆最小点数约束下，以总面积最小为目标的约束聚类 + 最小包围圆组合优化算法

学术表述：带基数约束（每个簇大小≥m）的 K-聚类优化问题，目标函数为各簇最小包围圆面积之和最小

改进版本 (v4):
- 所有可调参数集中在 Step 4
- 使用真正的 Welzl 算法计算最小包围圆
- 添加簇间重叠惩罚到目标函数
- 添加空间连续性约束（点只能移动到地理相邻的簇）
- 约束执行阶段也使用空间邻近原则
- 添加簇间分离度优化
- 后处理消除重叠
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
    J-Style Constrained Clustering with Minimum Enclosing Circle (Improved v4)
    
    =====================================================================
    Step 4 可调参数说明 (在配置文件中设置):
    =====================================================================
    
    j_style_max_iterations: int = 50
        Step 4 主优化循环的最大迭代次数
        增加可以提高优化质量，但会增加计算时间
        推荐范围：20-100
    
    j_style_overlap_penalty: float = 5.0
        重叠惩罚权重 λ
        公式：cost += λ × overlap²
        值越大，越倾向于避免重叠（可能导致簇间距离增大）
        推荐范围：1.0-10.0 (严格无重叠用 10.0)
    
    j_style_separation_weight: float = 0.8
        簇间分离度权重
        公式：cost += w × separation_score
        separation_score = sum((radius_i + radius_j) / centroid_distance)
        值越大，簇间距离越远
        推荐范围：0.3-1.0
    
    j_style_post_process_iterations: int = 20
        Step 5 后处理消除重叠的最大迭代次数
        推荐范围：10-50
    
    j_style_overlap_tolerance: float = 1e-6
        重叠判断的容忍度（弧度）
        小于此值的重叠将被忽略
        推荐范围：1e-8 - 1e-4
    
    j_style_points_per_move: int = 5
        后处理中每次尝试移动的最大点数
        值越大，后处理越激进
        推荐范围：3-10
    
    j_style_use_squared_overlap: bool = True
        是否使用重叠的平方进行惩罚
        True: cost += λ × overlap² (严厉惩罚)
        False: cost += λ × overlap (线性惩罚)
        推荐：True (严格无重叠)
    
    j_style_adjacency_k: int = 3
        每个簇的相邻簇数量（用于限制点的移动范围）
        推荐范围：2-5
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
        print(f"\n[J-Style Algorithm v4] {n} points")

        # Get base parameters
        k_clusters = self.config.strategy.options.get("j_style_k_clusters", 5)
        min_points_per_cluster = self.config.strategy.options.get("j_style_min_points", 10)
        max_points_per_cluster = self.config.strategy.options.get("j_style_max_points", 50)

        # Adjust k if needed (support min_points=1)
        min_points_per_cluster = max(1, min_points_per_cluster)
        max_points_per_cluster = max(min_points_per_cluster, max_points_per_cluster)
        k_clusters = min(k_clusters, n // min_points_per_cluster) if min_points_per_cluster > 0 else k_clusters
        k_clusters = max(1, k_clusters)

        print(f"  K clusters: {k_clusters}")
        print(f"  Min points per cluster: {min_points_per_cluster}")
        print(f"  Max points per cluster: {max_points_per_cluster}")

        # Convert points to numpy array
        coords = np.array([[p.lat, p.lng] for p in points])

        # Step 1: Initialize with K-Means++ but with spatial awareness
        print("\n[Step 1] Initializing with spatially-aware K-Means++...")
        labels = self._spatial_kmeans_init(coords, k_clusters)

        # Step 2: Enforce minimum and maximum points constraint with spatial awareness
        print("\n[Step 2] Enforcing min/max points constraint (spatial-aware)...")
        labels = self._enforce_min_max_constraint_spatial(coords, k_clusters,
                                                           min_points_per_cluster,
                                                           max_points_per_cluster, labels)

        # Step 3: Compute initial MEC for each cluster using Welzl's algorithm
        print("\n[Step 3] Computing Minimum Enclosing Circles (Welzl's algorithm)...")
        circles = []
        for k in range(k_clusters):
            cluster_points = coords[labels == k]
            if len(cluster_points) > 0:
                center, radius = self._welzl_mec(cluster_points)
                circles.append((center, radius))
            else:
                circles.append((coords.mean(axis=0), 0))

        initial_area = sum(np.pi * r**2 for _, r in circles)
        initial_overlaps = self._compute_total_overlap(circles)
        initial_separation = self._compute_cluster_separation(coords, labels, k_clusters)
        
        print(f"  Initial total area: {initial_area:.4f}")
        print(f"  Initial total overlap: {initial_overlaps:.4f}")
        print(f"  Initial separation score: {initial_separation:.4f}")

        # ================================================================
        # Step 4: 优化阶段 - 所有可调参数在这里使用
        # ================================================================
        print(f"\n[Step 4] Optimizing...")
        
        # --- 可调参数开始 (从配置文件读取) ---
        max_iterations = self.config.strategy.options.get("j_style_max_iterations", 50)
        overlap_penalty = self.config.strategy.options.get("j_style_overlap_penalty", 5.0)
        separation_weight = self.config.strategy.options.get("j_style_separation_weight", 0.8)
        adjacency_k = self.config.strategy.options.get("j_style_adjacency_k", 3)
        use_squared_overlap = self.config.strategy.options.get("j_style_use_squared_overlap", True)
        # --- 可调参数结束 ---
        
        print(f"  Parameters:")
        print(f"    max_iterations: {max_iterations}")
        print(f"    overlap_penalty (λ): {overlap_penalty}")
        print(f"    separation_weight: {separation_weight}")
        print(f"    adjacency_k: {adjacency_k}")
        print(f"    use_squared_overlap: {use_squared_overlap}")

        # 计算初始成本
        initial_cost = self._compute_total_cost(
            coords, labels, k_clusters, overlap_penalty, separation_weight, use_squared_overlap
        )
        print(f"  Initial cost: {initial_cost:.4f}")

        # 优化循环
        best_labels = labels.copy()
        best_cost = initial_cost

        for iteration in range(max_iterations):
            improved = False

            # 构建簇邻接图
            cluster_adjacency = self._build_cluster_adjacency(coords, labels, k_clusters, adjacency_k)

            # 尝试移动每个点到相邻簇
            for i in range(n):
                current_cluster = labels[i]

                # 检查是否可以移动（保持 min 约束）
                if sum(labels == current_cluster) <= min_points_per_cluster:
                    continue

                # 获取相邻簇
                adjacent_clusters = cluster_adjacency[current_cluster]

                # 尝试移动到相邻簇
                best_cluster = current_cluster
                best_cost_reduction = 0

                for k in adjacent_clusters:
                    if k == current_cluster:
                        continue

                    # 检查 max 约束
                    if sum(labels == k) >= max_points_per_cluster:
                        continue

                    # 临时移动点
                    test_labels = labels.copy()
                    test_labels[i] = k

                    # 检查约束
                    if sum(test_labels == k) < min_points_per_cluster:
                        continue

                    # 计算新成本
                    test_cost = self._compute_total_cost(
                        coords, test_labels, k_clusters, overlap_penalty, separation_weight, use_squared_overlap
                    )
                    current_cost = self._compute_total_cost(
                        coords, labels, k_clusters, overlap_penalty, separation_weight, use_squared_overlap
                    )

                    cost_reduction = current_cost - test_cost
                    if cost_reduction > best_cost_reduction:
                        best_cost_reduction = cost_reduction
                        best_cluster = k

                # 应用最佳移动
                if best_cluster != current_cluster and best_cost_reduction > 0.0001:
                    labels[i] = best_cluster
                    improved = True

            # 重新计算圆
            circles = []
            for k in range(k_clusters):
                cluster_points = coords[labels == k]
                if len(cluster_points) > 0:
                    center, radius = self._welzl_mec(cluster_points)
                    circles.append((center, radius))
                else:
                    circles.append((coords.mean(axis=0), 0))

            total_area = sum(np.pi * r**2 for _, r in circles)
            total_overlaps = self._compute_total_overlap(circles)
            total_separation = self._compute_cluster_separation(coords, labels, k_clusters)
            total_cost = self._compute_total_cost(
                coords, labels, k_clusters, overlap_penalty, separation_weight, use_squared_overlap
            )
            
            print(f"  Iteration {iteration + 1}: Area={total_area:.4f}, Overlap={total_overlaps:.4f}, "
                  f"Sep={total_separation:.4f}, Cost={total_cost:.4f}")

            if total_cost < best_cost:
                best_cost = total_cost
                best_labels = labels.copy()

            if not improved:
                print(f"  Converged at iteration {iteration + 1}")
                break

        # 使用最佳标签
        labels = best_labels

        # Step 5: 后处理 - 消除剩余重叠
        print(f"\n[Step 5] Post-processing to resolve overlaps...")
        
        # --- 可调参数开始 (从配置文件读取) ---
        post_process_iterations = self.config.strategy.options.get("j_style_post_process_iterations", 20)
        overlap_tolerance = self.config.strategy.options.get("j_style_overlap_tolerance", 1e-6)
        points_per_move = self.config.strategy.options.get("j_style_points_per_move", 5)
        # --- 可调参数结束 ---
        
        print(f"  Parameters:")
        print(f"    post_process_iterations: {post_process_iterations}")
        print(f"    overlap_tolerance: {overlap_tolerance}")
        print(f"    points_per_move: {points_per_move}")
        
        labels, circles = self._resolve_remaining_overlaps(
            coords, labels, k_clusters, 
            min_points_per_cluster, max_points_per_cluster,
            post_process_iterations, overlap_tolerance, points_per_move
        )
        
        # 重新计算最终指标
        final_area = sum(np.pi * r**2 for _, r in circles)
        final_overlaps = self._compute_total_overlap(circles)
        final_separation = self._compute_cluster_separation(coords, labels, k_clusters)
        final_cost = self._compute_total_cost(
            coords, labels, k_clusters, overlap_penalty, separation_weight, use_squared_overlap
        )
        
        print(f"\n  Final Results:")
        print(f"    Total area: {final_area:.4f}")
        print(f"    Total overlap: {final_overlaps:.4f}")
        print(f"    Separation: {final_separation:.4f}")
        print(f"    Cost: {final_cost:.4f}")
        
        improvement = (initial_cost - final_cost) / initial_cost * 100 if initial_cost > 0 else 0
        overlap_reduction = (initial_overlaps - final_overlaps) / max(initial_overlaps, 0.0001) * 100
        print(f"    Cost reduction: {improvement:.1f}%")
        print(f"    Overlap reduction: {overlap_reduction:.1f}%")

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

            days.append(DayPlan(
                day=cluster_idx + 1,
                points=optimized_points,
                drive_distance_km=round(drive_dist, 1),
                drive_time_min=round(drive_time_s / 60, 1),
                stop_time_min=stop_min,
                total_time_hours=round(total_s / 3600, 1),
            ))

        return PlanResult(
            strategy_name=f"J-Style v4(K={k_clusters},min={min_points_per_cluster})",
            days=days,
            all_points=points,
            metrics={
                "total_area": round(final_area, 4),
                "total_overlap": round(final_overlaps, 4),
                "separation_score": round(final_separation, 4),
                "total_cost": round(final_cost, 4),
                "k_clusters": k_clusters,
                "min_points_per_cluster": min_points_per_cluster,
                "overlap_penalty": overlap_penalty,
                "separation_weight": separation_weight,
            }
        )

    def _spatial_kmeans_init(self, coords, k_clusters):
        """Initialize clusters using spatially-aware K-Means."""
        from sklearn.cluster import KMeans
        
        best_labels = None
        best_score = float('inf')
        
        for seed in range(5):
            kmeans = KMeans(n_clusters=k_clusters, init='k-means++', n_init=10, 
                           random_state=42+seed, max_iter=100)
            labels = kmeans.fit_predict(coords)
            score = self._compute_cluster_separation(coords, labels, k_clusters)
            
            if score < best_score:
                best_score = score
                best_labels = labels
        
        return best_labels

    def _enforce_min_max_constraint_spatial(self, coords, k_clusters, min_points, max_points, labels):
        """Enforce min/max constraint with spatial awareness."""
        n = len(coords)
        labels = labels.copy()
        
        # Compute centroids
        centroids = []
        for k in range(k_clusters):
            cluster_points = coords[labels == k]
            centroids.append(cluster_points.mean(axis=0) if len(cluster_points) > 0 else coords.mean(axis=0))
        centroids = np.array(centroids)
        
        # Compute centroid distance matrix
        centroid_dist = np.zeros((k_clusters, k_clusters))
        for i in range(k_clusters):
            for j in range(i + 1, k_clusters):
                d = np.linalg.norm(centroids[i] - centroids[j])
                centroid_dist[i, j] = d
                centroid_dist[j, i] = d
        
        for iteration in range(100):
            improved = False
            
            # Handle min constraint violations
            violating_min = [k for k in range(k_clusters) if sum(labels == k) < min_points]
            if violating_min:
                for k in violating_min:
                    if sum(labels == k) >= min_points:
                        continue
                    
                    cluster_center = coords[labels == k].mean(axis=0) if sum(labels == k) > 0 else coords.mean(axis=0)
                    
                    # Find nearest cluster with excess
                    nearest_source = None
                    nearest_dist = float('inf')
                    for source_k in range(k_clusters):
                        if source_k == k or sum(labels == source_k) <= min_points:
                            continue
                        dist = centroid_dist[k, source_k]
                        if dist < nearest_dist:
                            nearest_dist = dist
                            nearest_source = source_k
                    
                    if nearest_source:
                        candidate_indices = [i for i in range(n) if labels[i] == nearest_source]
                        candidate_indices.sort(key=lambda i: np.sum((coords[i] - cluster_center)**2))
                        
                        points_to_move = min(
                            min_points - sum(labels == k),
                            sum(labels == nearest_source) - min_points,
                            len(candidate_indices)
                        )
                        for i in candidate_indices[:points_to_move]:
                            labels[i] = k
                            improved = True
            
            # Handle max constraint violations
            violating_max = [k for k in range(k_clusters) if sum(labels == k) > max_points]
            if violating_max:
                for k in violating_max:
                    cluster_center = coords[labels == k].mean(axis=0)
                    candidate_indices = [i for i in range(n) if labels[i] == k]
                    candidate_indices.sort(key=lambda i: np.sum((coords[i] - cluster_center)**2), reverse=True)
                    
                    excess = sum(labels == k) - max_points
                    for idx_to_move in candidate_indices[:excess]:
                        point_coord = coords[idx_to_move]
                        best_target = None
                        best_distance = float('inf')
                        
                        # Sort by centroid distance
                        cluster_distances = [(centroid_dist[k, target_k], target_k) 
                                            for target_k in range(k_clusters) if target_k != k]
                        cluster_distances.sort()
                        
                        for _, target_k in cluster_distances:
                            if sum(labels == target_k) >= max_points:
                                continue
                            target_center = coords[labels == target_k].mean(axis=0) if sum(labels == target_k) > 0 else point_coord
                            distance = np.sum((point_coord - target_center)**2)
                            if distance < best_distance:
                                best_distance = distance
                                best_target = target_k
                        
                        if best_target is not None:
                            labels[idx_to_move] = best_target
                            improved = True
            
            if not improved:
                break
        
        return labels

    def _welzl_mec(self, points):
        """Compute Minimum Enclosing Circle using Welzl's algorithm."""
        if len(points) == 0:
            return np.array([0.0, 0.0]), 0.0
        elif len(points) == 1:
            return points[0].copy(), 0.0
        
        points_list = [p.copy() for p in points]
        random.shuffle(points_list)
        
        def _welzl_recursive(P, R, n):
            if n == 0 or len(R) == 3:
                return self._mec_from_boundary(R)
            p = P[n - 1]
            circle = _welzl_recursive(P, R, n - 1)
            if self._is_inside(p, circle):
                return circle
            return _welzl_recursive(P, R + [p], n - 1)
        
        return _welzl_recursive(points_list, [], len(points_list))
    
    def _mec_from_boundary(self, boundary):
        """Compute MEC from boundary points (1-3 points)."""
        if len(boundary) == 0:
            return (np.array([0.0, 0.0]), 0.0)
        elif len(boundary) == 1:
            return (boundary[0], 0.0)
        elif len(boundary) == 2:
            center = (boundary[0] + boundary[1]) / 2
            radius = np.linalg.norm(boundary[0] - boundary[1]) / 2
            return (center, radius)
        else:
            return self._circumcircle(boundary[0], boundary[1], boundary[2])
    
    def _is_inside(self, point, circle):
        """Check if point is inside or on the circle."""
        center, radius = circle
        return np.linalg.norm(point - center) <= radius + 1e-10
    
    def _circumcircle(self, a, b, c):
        """Compute circumcircle of three points."""
        d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
        if abs(d) < 1e-10:
            points = [a, b, c]
            max_dist = max(np.linalg.norm(points[i] - points[j]) for i in range(3) for j in range(i+1, 3))
            pair = max(((i, j) for i in range(3) for j in range(i+1, 3)), 
                      key=lambda p: np.linalg.norm(points[p[0]] - points[p[1]]))
            center = (points[pair[0]] + points[pair[1]]) / 2
            return (center, max_dist / 2)
        
        ux = ((a[0]**2 + a[1]**2) * (b[1] - c[1]) + (b[0]**2 + b[1]**2) * (c[1] - a[1]) + 
              (c[0]**2 + c[1]**2) * (a[1] - b[1])) / d
        uy = ((a[0]**2 + a[1]**2) * (c[0] - b[0]) + (b[0]**2 + b[1]**2) * (a[0] - c[0]) + 
              (c[0]**2 + c[1]**2) * (b[0] - a[0])) / d
        
        center = np.array([ux, uy])
        radius = np.linalg.norm(center - a)
        return (center, radius)

    def _compute_total_overlap(self, circles):
        """Compute total overlap area between all pairs of circles."""
        total_overlap = 0.0
        n = len(circles)
        
        for i in range(n):
            for j in range(i + 1, n):
                c1, r1 = circles[i]
                c2, r2 = circles[j]
                d = np.linalg.norm(c1 - c2)
                
                if d >= r1 + r2:
                    continue
                if d <= abs(r1 - r2):
                    total_overlap += np.pi * min(r1, r2)**2
                    continue
                
                r1_sq, r2_sq = r1**2, r2**2
                alpha = 2 * np.arccos((d**2 + r1_sq - r2_sq) / (2 * d * r1))
                beta = 2 * np.arccos((d**2 + r2_sq - r1_sq) / (2 * d * r2))
                total_overlap += 0.5 * r1_sq * (alpha - np.sin(alpha)) + 0.5 * r2_sq * (beta - np.sin(beta))
        
        return total_overlap

    def _compute_cluster_separation(self, coords, labels, k_clusters):
        """Compute cluster separation score (lower is better)."""
        centroids, radii = [], []
        for k in range(k_clusters):
            cluster_points = coords[labels == k]
            if len(cluster_points) > 0:
                centroids.append(cluster_points.mean(axis=0))
                radii.append(max(np.linalg.norm(p - centroids[-1]) for p in cluster_points))
            else:
                centroids.append(coords.mean(axis=0))
                radii.append(0)
        
        separation = 0.0
        for i in range(k_clusters):
            for j in range(i + 1, k_clusters):
                d = np.linalg.norm(centroids[i] - centroids[j])
                if d > 0:
                    separation += (radii[i] + radii[j]) / d
        return separation

    def _compute_total_cost(self, coords, labels, k_clusters, overlap_penalty, separation_weight, use_squared):
        """Compute total cost = area + λ×overlap^(1 or 2) + w×separation."""
        circles = []
        for k in range(k_clusters):
            cluster_points = coords[labels == k]
            center, radius = self._welzl_mec(cluster_points) if len(cluster_points) > 0 else (coords.mean(axis=0), 0)
            circles.append((center, radius))
        
        total_area = sum(np.pi * r**2 for _, r in circles)
        total_overlaps = self._compute_total_overlap(circles)
        total_separation = self._compute_cluster_separation(coords, labels, k_clusters)
        
        overlap_term = overlap_penalty * (total_overlaps ** 2 if use_squared else total_overlaps)
        return total_area + overlap_term + separation_weight * total_separation

    def _build_cluster_adjacency(self, coords, labels, k_clusters, adjacency_k=3):
        """Build adjacency graph based on centroid proximity."""
        adjacency = {k: set() for k in range(k_clusters)}
        
        centroids = []
        for k in range(k_clusters):
            cluster_points = coords[labels == k]
            centroids.append(cluster_points.mean(axis=0) if len(cluster_points) > 0 else coords.mean(axis=0))
        centroids = np.array(centroids)
        
        for k in range(k_clusters):
            distances = [np.linalg.norm(centroids[k] - centroids[j]) for j in range(k_clusters)]
            nearest = np.argsort(distances)[1:adjacency_k+1]
            for j in nearest:
                adjacency[k].add(j)
                adjacency[j].add(k)
        
        return adjacency

    def _resolve_remaining_overlaps(self, coords, labels, k_clusters, min_pts, max_pts, 
                                     max_iterations, tolerance, points_per_move):
        """Post-processing to resolve remaining overlaps."""
        n = len(coords)
        labels = labels.copy()
        
        for iteration in range(max_iterations):
            circles = []
            for k in range(k_clusters):
                cluster_points = coords[labels == k]
                center, radius = self._welzl_mec(cluster_points) if len(cluster_points) > 0 else (coords.mean(axis=0), 0)
                circles.append((center, radius))
            
            # Find overlapping pairs
            overlapping_pairs = []
            for i in range(k_clusters):
                for j in range(i + 1, k_clusters):
                    c1, r1 = circles[i]
                    c2, r2 = circles[j]
                    d = np.linalg.norm(c1 - c2)
                    if d < r1 + r2 - tolerance:
                        overlapping_pairs.append((i, j, r1 + r2 - d))
            
            if not overlapping_pairs:
                print(f"  ✓ No overlapping clusters after {iteration} iterations")
                break
            
            overlapping_pairs.sort(key=lambda x: x[2], reverse=True)
            improved = False
            
            for i, j, overlap_depth in overlapping_pairs:
                size_i, size_j = sum(labels == i), sum(labels == j)
                center_i, radius_i = circles[i]
                center_j, radius_j = circles[j]
                
                # Find points in overlap region
                overlap_points_i = [(idx, np.linalg.norm(coords[idx] - center_j)) 
                                   for idx in range(n) if labels[idx] == i and np.linalg.norm(coords[idx] - center_j) < radius_j]
                overlap_points_j = [(idx, np.linalg.norm(coords[idx] - center_i)) 
                                   for idx in range(n) if labels[idx] == j and np.linalg.norm(coords[idx] - center_i) < radius_i]
                
                # Move points from i to j
                if overlap_points_i:
                    overlap_points_i.sort(key=lambda x: x[1])
                    for idx, _ in overlap_points_i[:points_per_move]:
                        if size_i <= min_pts:
                            break
                        if size_j >= max_pts:
                            if overlap_points_j and size_j > min_pts:
                                swap_idx, _ = overlap_points_j[0]
                                labels[swap_idx] = i
                                labels[idx] = j
                                size_i -= 1
                                size_j += 1
                                improved = True
                            continue
                        labels[idx] = j
                        size_i -= 1
                        size_j += 1
                        improved = True
                
                # Move points from j to i
                if overlap_points_j:
                    overlap_points_j.sort(key=lambda x: x[1])
                    for idx, _ in overlap_points_j[:points_per_move]:
                        if size_j <= min_pts or size_i >= max_pts:
                            continue
                        labels[idx] = i
                        size_j -= 1
                        size_i += 1
                        improved = True
            
            if not improved:
                print(f"  ⚠ Could not resolve more overlaps after {iteration + 1} iterations")
                break
        
        # Final circles
        circles = []
        for k in range(k_clusters):
            cluster_points = coords[labels == k]
            center, radius = self._welzl_mec(cluster_points) if len(cluster_points) > 0 else (coords.mean(axis=0), 0)
            circles.append((center, radius))
        
        return labels, circles

    def _optimize_order(self, indices: List[int], dist_matrix: List[List[float]]) -> List[int]:
        """Optimize visit order within a cluster using nearest neighbor."""
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
