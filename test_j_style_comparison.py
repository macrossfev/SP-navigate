#!/usr/bin/env python3
"""
Comparison test: Original J-Style vs Improved J-Style
Generates 80 random points and compares both algorithms.
"""
import numpy as np
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from navigate.core.models import Point
from navigate.core.config import NavigateConfig, StrategyConfig, ConstraintsConfig, DistanceConfig, DataConfig, ExportConfig
from navigate.strategies.cluster import ClusterStrategy


def generate_changshou_like_points(n=80, seed=42):
    """Generate points simulating Changshou district's band-like distribution."""
    np.random.seed(seed)
    
    base_lat = 29.85
    base_lng = 107.08
    
    points = []
    n_clusters = 6
    cluster_centers = []
    
    for i in range(n_clusters):
        lng_offset = np.random.uniform(-0.4, 0.4)
        lat_offset = np.random.uniform(-0.1, 0.1)
        cluster_centers.append((base_lat + lat_offset, base_lng + lng_offset))
    
    points_per_cluster = n // n_clusters
    remaining = n % n_clusters
    
    point_id = 0
    for i, (lat_c, lng_c) in enumerate(cluster_centers):
        n_pts = points_per_cluster + (1 if i < remaining else 0)
        
        for j in range(n_pts):
            r = np.random.uniform(0, 0.03)
            theta = np.random.uniform(0, 2 * np.pi)
            
            lat = lat_c + r * np.cos(theta)
            lng = lng_c + r * np.sin(theta)
            
            points.append(Point(
                id=f"point_{point_id}",
                name=f"采样点 {point_id + 1}",
                lat=lat,
                lng=lng,
                metadata={"address": f"重庆市长寿区采样点 {point_id + 1}"}
            ))
            point_id += 1
    
    # Add scattered points
    n_scattered = 5
    for i in range(n_scattered):
        lat = base_lat + np.random.uniform(-0.5, 0.5)
        lng = base_lng + np.random.uniform(-0.5, 0.5)
        
        points.append(Point(
            id=f"point_{point_id}",
            name=f"采样点 {point_id + 1}",
            lat=lat,
            lng=lng,
            metadata={"address": f"重庆市长寿区采样点 {point_id + 1}"}
        ))
        point_id += 1
    
    return points


def haversine_distance(lat1, lng1, lat2, lng2):
    R = 6371
    lat1_rad = np.radians(lat1)
    lat2_rad = np.radians(lat2)
    delta_lat = np.radians(lat2 - lat1)
    delta_lng = np.radians(lng2 - lng1)
    
    a = np.sin(delta_lat / 2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lng / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    
    return R * c


def build_distance_matrix(points):
    n = len(points)
    matrix = np.zeros((n, n))
    
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_distance(points[i].lat, points[i].lng, points[j].lat, points[j].lng)
            matrix[i, j] = d
            matrix[j, i] = d
    
    return matrix


class SimpleDistanceMatrix:
    def __init__(self, matrix):
        self._matrix = matrix
    
    def to_list(self):
        return self._matrix.tolist()


def compute_overlap_score(coords, labels, k_clusters):
    """
    Compute overlap score between clusters.
    Higher score = more overlap (worse).
    """
    # Compute cluster centroids and radii
    clusters_info = []
    for k in range(k_clusters):
        cluster_points = coords[labels == k]
        if len(cluster_points) > 0:
            centroid = cluster_points.mean(axis=0)
            max_dist = max(np.linalg.norm(p - centroid) for p in cluster_points)
            clusters_info.append((centroid, max_dist))
    
    # Compute pairwise overlap
    total_overlap = 0.0
    n_clusters = len(clusters_info)
    
    for i in range(n_clusters):
        for j in range(i + 1, n_clusters):
            c1, r1 = clusters_info[i]
            c2, r2 = clusters_info[j]
            
            d = np.linalg.norm(c1 - c2)
            
            # Check for overlap
            if d < r1 + r2:
                # Overlap exists, compute overlap ratio
                overlap_depth = (r1 + r2 - d)
                total_overlap += overlap_depth
    
    return total_overlap


def compute_spatial_continuity_score(coords, labels, k_clusters):
    """
    Compute spatial continuity score.
    Lower score = better continuity (points closer to their cluster centroid).
    """
    total_distance = 0.0
    
    for k in range(k_clusters):
        cluster_points = coords[labels == k]
        if len(cluster_points) > 0:
            centroid = cluster_points.mean(axis=0)
            for p in cluster_points:
                total_distance += np.linalg.norm(p - centroid)
    
    return total_distance / len(coords)


def run_comparison():
    print("=" * 70)
    print("J-Style Algorithm: Original vs Improved Comparison")
    print("=" * 70)
    
    # Generate test points
    print("\n[1] Generating 85 test points...")
    points = generate_changshou_like_points(n=80, seed=42)
    print(f"  Generated {len(points)} points")
    
    # Build distance matrix
    print("\n[2] Building distance matrix...")
    dist_matrix_np = build_distance_matrix(points)
    dist_matrix = SimpleDistanceMatrix(dist_matrix_np)
    
    coords = np.array([[p.lat, p.lng] for p in points])
    
    # Create config
    config = NavigateConfig(
        base_point={"name": "Base", "lng": 107.08, "lat": 29.85},
        strategy=StrategyConfig(
            name="cluster",
            options={
                "cluster_method": "centroid",
                "outlier_threshold_km": 50.0
            }
        ),
        constraints=ConstraintsConfig(
            max_daily_hours=8,
            max_daily_points=20,
            min_daily_points=1,
            stop_time_per_point_min=15,
            roundtrip_overhead_min=60,
            max_daily_distance_km=0
        ),
        distance=DistanceConfig(provider="haversine", avg_speed_kmh=35.0),
        data=DataConfig(points={"file": "", "format": "excel"}),
        export=ExportConfig(output_dir="./output/test_comparison", formats=[])
    )
    
    # Run original algorithm (centroid clustering)
    print("\n[3] Running Original Algorithm (Centroid Clustering)...")
    strategy_orig = ClusterStrategy(config)
    result_orig = strategy_orig.plan(points, dist_matrix)
    
    # Extract labels from original result
    labels_orig = np.zeros(len(points), dtype=int)
    for day in result_orig.days:
        for point in day.points:
            idx = next(i for i, p in enumerate(points) if p.id == point.id)
            labels_orig[idx] = day.day - 1
    
    k_orig = len(set(labels_orig))
    overlap_orig = compute_overlap_score(coords, labels_orig, k_orig)
    continuity_orig = compute_spatial_continuity_score(coords, labels_orig, k_orig)
    
    # Run improved J-Style algorithm
    print("\n[4] Running Improved J-Style Algorithm v4...")
    from navigate.strategies.j_style import JStyleStrategy
    
    # Use more clusters to reduce overlap
    k_improved_target = k_orig + 1  # One more cluster gives more flexibility
    
    config_j = NavigateConfig(
        base_point={"name": "Base", "lng": 107.08, "lat": 29.85},
        strategy=StrategyConfig(
            name="j_style",
            options={
                "j_style_k_clusters": k_improved_target,
                "j_style_min_points": 8,  # Lower min for more flexibility
                "j_style_max_points": 20,
                # Step 4 可调参数
                "j_style_max_iterations": 50,          # Step 4 最大迭代次数
                "j_style_overlap_penalty": 5.0,        # 重叠惩罚权重 (越高越避免重叠)
                "j_style_separation_weight": 0.8,      # 分离度权重 (越高簇间距离越大)
                "j_style_adjacency_k": 3,              # 相邻簇数量
                "j_style_use_squared_overlap": True,   # 是否使用重叠平方
                # Step 5 可调参数
                "j_style_post_process_iterations": 20, # 后处理迭代次数
                "j_style_overlap_tolerance": 1e-6,     # 重叠容忍度
                "j_style_points_per_move": 5,          # 每次移动最大点数
            }
        ),
        constraints=ConstraintsConfig(
            max_daily_hours=8,
            max_daily_points=25,
            min_daily_points=1,
            stop_time_per_point_min=15,
            roundtrip_overhead_min=60,
            max_daily_distance_km=0
        ),
        distance=DistanceConfig(provider="haversine", avg_speed_kmh=35.0),
        data=DataConfig(points={"file": "", "format": "excel"}),
        export=ExportConfig(output_dir="./output/test_comparison", formats=[])
    )
    
    strategy_improved = JStyleStrategy(config_j)
    result_improved = strategy_improved.plan(points, dist_matrix)
    
    # Extract labels from improved result
    labels_improved = np.zeros(len(points), dtype=int)
    for day in result_improved.days:
        for point in day.points:
            idx = next(i for i, p in enumerate(points) if p.id == point.id)
            labels_improved[idx] = day.day - 1
    
    k_improved = len(set(labels_improved))
    overlap_improved = compute_overlap_score(coords, labels_improved, k_improved)
    continuity_improved = compute_spatial_continuity_score(coords, labels_improved, k_improved)
    
    # Print comparison results
    print("\n" + "=" * 70)
    print("COMPARISON RESULTS")
    print("=" * 70)
    
    print("\n📊 Cluster Statistics:")
    print(f"  {'Metric':<35} | {'Original':<15} | {'Improved':<15}")
    print(f"  {'-'*35}-+-{'-'*15}-+-{'-'*15}")
    print(f"  {'Number of clusters':<35} | {k_orig:<15} | {k_improved:<15}")
    
    cluster_sizes_orig = [sum(labels_orig == k) for k in range(k_orig)]
    cluster_sizes_improved = [sum(labels_improved == k) for k in range(k_improved)]
    print(f"  {'Cluster sizes':<35} | {str(cluster_sizes_orig):<15} | {str(cluster_sizes_improved):<15}")
    
    print(f"\n📐 Spatial Quality Metrics:")
    print(f"  {'Metric':<35} | {'Original':<15} | {'Improved':<15}")
    print(f"  {'-'*35}-+-{'-'*15}-+-{'-'*15}")
    print(f"  {'Overlap score (lower=better)':<35} | {overlap_orig:<15.4f} | {overlap_improved:<15.4f}")
    print(f"  {'Spatial continuity (lower=better)':<35} | {continuity_orig:<15.4f} | {continuity_improved:<15.4f}")
    
    # Calculate improvement
    overlap_improvement = (overlap_orig - overlap_improved) / overlap_orig * 100 if overlap_orig > 0 else 0
    continuity_improvement = (continuity_orig - continuity_improved) / continuity_orig * 100 if continuity_orig > 0 else 0
    
    print(f"\n📈 Improvement:")
    print(f"  Overlap reduction: {overlap_improvement:+.1f}%")
    print(f"  Spatial continuity improvement: {continuity_improvement:+.1f}%")
    
    # Algorithm-specific metrics
    if hasattr(result_improved, 'metrics') and result_improved.metrics:
        print(f"\n🔷 J-Style Improved Algorithm Metrics:")
        for key, value in result_improved.metrics.items():
            print(f"    {key}: {value}")
    
    # Save comparison result
    os.makedirs("./output/test_comparison", exist_ok=True)
    
    # Convert numpy types to Python native types for JSON serialization
    def convert_to_native(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: convert_to_native(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_native(i) for i in obj]
        return obj
    
    comparison_data = {
        "original": {
            "algorithm": "Centroid Clustering",
            "k_clusters": int(k_orig),
            "cluster_sizes": [int(x) for x in cluster_sizes_orig],
            "overlap_score": float(overlap_orig),
            "spatial_continuity": float(continuity_orig),
            "days": [
                {
                    "day": int(d.day),
                    "points": [p.name for p in d.points],
                    "drive_distance_km": float(d.drive_distance_km)
                }
                for d in result_orig.days
            ]
        },
        "improved": {
            "algorithm": "J-Style Improved (with overlap penalty)",
            "k_clusters": int(k_improved),
            "cluster_sizes": [int(x) for x in cluster_sizes_improved],
            "overlap_score": float(overlap_improved),
            "spatial_continuity": float(continuity_improved),
            "metrics": convert_to_native(result_improved.metrics) if hasattr(result_improved, 'metrics') else {},
            "days": [
                {
                    "day": int(d.day),
                    "points": [p.name for p in d.points],
                    "drive_distance_km": float(d.drive_distance_km)
                }
                for d in result_improved.days
            ]
        },
        "improvement": {
            "overlap_reduction_pct": float(overlap_improvement),
            "continuity_improvement_pct": float(continuity_improvement)
        }
    }
    
    with open("./output/test_comparison/comparison_result.json", 'w', encoding='utf-8') as f:
        json.dump(comparison_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: ./output/test_comparison/comparison_result.json")
    
    # Generate visualizations
    print("\n[5] Generating visualizations...")
    import folium
    
    def create_visualization(points, labels, title, output_file):
        avg_lat = np.mean([p.lat for p in points])
        avg_lng = np.mean([p.lng for p in points])
        
        m = folium.Map(location=[avg_lat, avg_lng], zoom_start=10)
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', 
                  '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9']
        
        # Plot points
        for i, point in enumerate(points):
            cluster_id = labels[i]
            color = colors[cluster_id % len(colors)]
            
            folium.CircleMarker(
                location=[point.lat, point.lng],
                radius=6,
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.7,
                popup=f"{point.name}<br>Cluster: {cluster_id}"
            ).add_to(m)
        
        # Plot cluster boundaries (convex hull approximation)
        for k in range(max(labels) + 1):
            cluster_indices = [i for i, l in enumerate(labels) if l == k]
            cluster_points = coords[cluster_indices]
            
            if len(cluster_points) > 0:
                centroid = cluster_points.mean(axis=0)
                max_dist = max(np.linalg.norm(p - centroid) for p in cluster_points)
                
                color = colors[k % len(colors)]
                folium.Circle(
                    location=[centroid[0], centroid[1]],
                    radius=max_dist * 1000,
                    color=color,
                    weight=2,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.15
                ).add_to(m)
        
        m.save(output_file)
        return output_file
    
    viz_orig = create_visualization(
        points, labels_orig, 
        "Original Centroid Clustering",
        "./output/test_comparison/original_result.html"
    )
    print(f"  Original visualization: {viz_orig}")
    
    viz_improved = create_visualization(
        points, labels_improved,
        "Improved J-Style Clustering",
        "./output/test_comparison/improved_result.html"
    )
    print(f"  Improved visualization: {viz_improved}")
    
    print("\n" + "=" * 70)
    print("Comparison test completed!")
    print("=" * 70)
    
    return comparison_data


if __name__ == "__main__":
    run_comparison()
