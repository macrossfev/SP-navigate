#!/usr/bin/env python3
"""
Test script for improved J-Style algorithm.
Generates 80 random points simulating Changshou district distribution and tests the clustering.
"""
import numpy as np
import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from navigate.core.models import Point, DistanceMatrix, PlanResult
from navigate.core.config import NavigateConfig, StrategyConfig, ConstraintsConfig, DistanceConfig, DataConfig, ExportConfig
from navigate.strategies.j_style import JStyleStrategy
from navigate.strategies.cluster import ClusterStrategy


def generate_changshou_like_points(n=80, seed=42):
    """
    Generate points simulating Changshou district's band-like distribution along the Yangtze River.
    
    Changshou characteristics:
    - Band-like distribution along the river (about 60km east-west)
    - Some clusters around town centers
    - Some scattered points
    """
    np.random.seed(seed)
    
    # Base coordinates (center of Changshou)
    base_lat = 29.85
    base_lng = 107.08
    
    points = []
    
    # Generate 5-6 clusters along a band (simulating towns along the river)
    n_clusters = 6
    cluster_centers = []
    
    # Create band-like distribution (east-west elongated)
    for i in range(n_clusters):
        # Along the river (east-west direction, longer spread)
        lng_offset = np.random.uniform(-0.4, 0.4)  # ~40km east-west
        # Perpendicular to river (north-south direction, shorter spread)
        lat_offset = np.random.uniform(-0.1, 0.1)  # ~10km north-south
        cluster_centers.append((base_lat + lat_offset, base_lng + lng_offset))
    
    # Distribute points among clusters
    points_per_cluster = n // n_clusters
    remaining = n % n_clusters
    
    point_id = 0
    for i, (lat_c, lng_c) in enumerate(cluster_centers):
        # Number of points in this cluster
        n_pts = points_per_cluster + (1 if i < remaining else 0)
        
        # Generate points around cluster center
        for j in range(n_pts):
            # Cluster spread (about 2-5km radius)
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
    
    # Add some scattered points (outliers)
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
    """Calculate haversine distance between two points in km."""
    R = 6371  # Earth's radius in km
    
    lat1_rad = np.radians(lat1)
    lat2_rad = np.radians(lat2)
    delta_lat = np.radians(lat2 - lat1)
    delta_lng = np.radians(lng2 - lng1)
    
    a = np.sin(delta_lat / 2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lng / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    
    return R * c


def build_distance_matrix(points):
    """Build distance matrix using haversine distance."""
    n = len(points)
    matrix = np.zeros((n, n))
    
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_distance(points[i].lat, points[i].lng, points[j].lat, points[j].lng)
            matrix[i, j] = d
            matrix[j, i] = d
    
    return matrix


def compute_cluster_metrics(points, labels, dist_matrix):
    """Compute clustering quality metrics."""
    n = len(points)
    k_clusters = len(set(labels))
    
    metrics = {
        "n_points": n,
        "k_clusters": k_clusters,
        "cluster_sizes": [],
        "intra_cluster_distances": [],
        "inter_cluster_separations": [],
        "overlap_analysis": []
    }
    
    for k in range(k_clusters):
        cluster_indices = [i for i in range(n) if labels[i] == k]
        cluster_size = len(cluster_indices)
        metrics["cluster_sizes"].append(cluster_size)
        
        if cluster_size < 2:
            metrics["intra_cluster_distances"].append(0)
            continue
        
        # Intra-cluster distance (max pairwise distance)
        max_dist = 0
        for i in range(len(cluster_indices)):
            for j in range(i + 1, len(cluster_indices)):
                d = dist_matrix[cluster_indices[i], cluster_indices[j]]
                max_dist = max(max_dist, d)
        metrics["intra_cluster_distances"].append(round(max_dist, 2))
    
    # Inter-cluster separation (min distance between cluster centroids)
    centroids = []
    for k in range(k_clusters):
        cluster_indices = [i for i in range(n) if labels[i] == k]
        if cluster_indices:
            avg_lat = np.mean([points[i].lat for i in cluster_indices])
            avg_lng = np.mean([points[i].lng for i in cluster_indices])
            centroids.append((avg_lat, avg_lng))
    
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            d = haversine_distance(centroids[i][0], centroids[i][1], centroids[j][0], centroids[j][1])
            metrics["inter_cluster_separations"].append(round(d, 2))
    
    return metrics


def visualize_clusters(points, labels, circles, title="Clustering Result", output_file="cluster_visualization.html"):
    """Generate HTML visualization of clustering result."""
    import folium
    
    # Compute center
    avg_lat = np.mean([p.lat for p in points])
    avg_lng = np.mean([p.lng for p in points])
    
    m = folium.Map(location=[avg_lat, avg_lng], zoom_start=11)
    
    # Color palette
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
    
    # Plot circles
    for k, (center, radius) in enumerate(circles):
        color = colors[k % len(colors)]
        
        # Circle boundary
        folium.Circle(
            location=[center[0], center[1]],
            radius=radius * 1000,  # Convert to meters
            color=color,
            weight=2,
            fill=True,
            fillColor=color,
            fillOpacity=0.15
        ).add_to(m)
    
    # Save
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
    m.save(output_file)
    print(f"  Visualization saved to: {output_file}")
    
    return output_file


def run_test():
    """Run the clustering test."""
    print("=" * 60)
    print("J-Style Algorithm Improved Test")
    print("=" * 60)
    
    # Generate test points
    print("\n[1] Generating 80 test points (Changshou-like distribution)...")
    points = generate_changshou_like_points(n=80, seed=42)
    print(f"  Generated {len(points)} points")
    
    # Build distance matrix
    print("\n[2] Building distance matrix...")
    dist_matrix_np = build_distance_matrix(points)
    
    # Create DistanceMatrix object
    class SimpleDistanceMatrix:
        def __init__(self, matrix):
            self._matrix = matrix
        
        def to_list(self):
            return self._matrix.tolist()
    
    dist_matrix = SimpleDistanceMatrix(dist_matrix_np)
    
    # Create config
    config = NavigateConfig(
        base_point={"name": "Base", "lng": 107.08, "lat": 29.85},
        strategy=StrategyConfig(
            name="j_style",
            options={
                "j_style_k_clusters": 5,
                "j_style_min_points": 10,
                "j_style_max_points": 20,
                "j_style_max_iterations": 50,
                "j_style_overlap_penalty": 0.5
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
        distance=DistanceConfig(
            provider="haversine",
            avg_speed_kmh=35.0
        ),
        data=DataConfig(points={"file": "", "format": "excel"}),
        export=ExportConfig(output_dir="./output/test_j_style", formats=[])
    )
    
    # Run J-Style algorithm
    print("\n[3] Running J-Style Algorithm (Improved)...")
    strategy = JStyleStrategy(config)
    result = strategy.plan(points, dist_matrix)
    
    # Extract labels from result
    labels = np.zeros(len(points), dtype=int)
    for day in result.days:
        for point in day.points:
            idx = points.index(point)
            labels[idx] = day.day - 1
    
    # Compute metrics
    print("\n[4] Computing clustering metrics...")
    metrics = compute_cluster_metrics(points, labels, dist_matrix_np)
    
    print("\n" + "=" * 60)
    print("Clustering Results Summary")
    print("=" * 60)
    print(f"  Number of points: {metrics['n_points']}")
    print(f"  Number of clusters: {metrics['k_clusters']}")
    print(f"  Cluster sizes: {metrics['cluster_sizes']}")
    print(f"  Intra-cluster max distances (km): {metrics['intra_cluster_distances']}")
    print(f"  Inter-cluster separations (km): {metrics['inter_cluster_separations']}")
    
    # Print metrics from result
    if hasattr(result, 'metrics') and result.metrics:
        print("\n  Algorithm Metrics:")
        for key, value in result.metrics.items():
            print(f"    {key}: {value}")
    
    # Visualize
    print("\n[5] Generating visualization...")
    circles = []
    coords = np.array([[p.lat, p.lng] for p in points])
    for k in range(metrics['k_clusters']):
        cluster_points = coords[labels == k]
        if len(cluster_points) > 0:
            # Compute MEC for visualization
            center = cluster_points.mean(axis=0)
            max_dist = max(np.linalg.norm(p - center) for p in cluster_points)
            circles.append((center, max_dist))
    
    viz_file = visualize_clusters(points, labels, circles, 
                                  title="J-Style Improved Clustering",
                                  output_file="./output/test_j_style/clustering_result.html")
    
    # Save result JSON
    result_path = "./output/test_j_style/test_result.json"
    os.makedirs(os.path.dirname(result_path), exist_ok=True)
    
    result_data = {
        "algorithm": "J-Style Improved",
        "metrics": metrics,
        "algorithm_metrics": result.metrics if hasattr(result, 'metrics') else {},
        "days": [
            {
                "day": d.day,
                "points": [p.name for p in d.points],
                "drive_distance_km": d.drive_distance_km,
                "total_time_hours": d.total_time_hours
            }
            for d in result.days
        ]
    }
    
    with open(result_path, 'w') as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    print(f"  Result saved to: {result_path}")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)
    
    return result, metrics


if __name__ == "__main__":
    run_test()
