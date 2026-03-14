#!/usr/bin/env python3
"""
采样点分组算法对比测试
目标：组间不重叠，临近点聚合，方便划定采样路线

测试 4 种算法：
1. 网格划分法 - 用地理网格切割
2. Voronoi 多边形法 - 基于种子点的自然划分
3. 河流/道路约束聚类 - 沿主要走向分组
4. 约束 K-Means - 强制分离的 K-Means
"""
import pandas as pd
import numpy as np
from typing import List, Tuple, Dict
import json
import os


# ============================================================
# 数据加载
# ============================================================
def load_data(excel_path: str) -> List[dict]:
    """从 Excel 加载坐标数据"""
    df = pd.read_excel(excel_path)
    valid = df[df['坐标'].notna()].copy()
    
    points = []
    for idx, row in valid.iterrows():
        coord_str = row['坐标']
        if isinstance(coord_str, str) and ',' in coord_str:
            lng, lat = map(float, coord_str.split(','))
            points.append({
                'id': idx,
                'name': row['原始地址'],
                'lng': lng,
                'lat': lat
            })
    
    # 去重
    seen = set()
    unique_points = []
    for p in points:
        key = (p['lng'], p['lat'])
        if key not in seen:
            seen.add(key)
            unique_points.append(p)
    
    print(f"加载了 {len(points)} 个点，去重后 {len(unique_points)} 个唯一点位")
    return unique_points


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点间的球面距离 (km)"""
    R = 6371.0
    lat1_rad = np.radians(lat1)
    lat2_rad = np.radians(lat2)
    delta_lat = np.radians(lat2 - lat1)
    delta_lng = np.radians(lng2 - lng1)
    
    a = (np.sin(delta_lat / 2) ** 2 + 
         np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lng / 2) ** 2)
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    
    return R * c


def build_distance_matrix(points: List[dict]) -> np.ndarray:
    """构建距离矩阵"""
    n = len(points)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine(
                points[i]['lat'], points[i]['lng'],
                points[j]['lat'], points[j]['lng']
            )
            matrix[i, j] = d
            matrix[j, i] = d
    return matrix


# ============================================================
# 算法 1: 网格划分法
# ============================================================
def grid_partition(points: List[dict], 
                   grid_size_km: float = 5.0,
                   max_points_per_group: int = 15) -> List[List[int]]:
    """
    网格划分法
    
    原理：将地理区域划分为网格，每个网格内的点为一组
    优点：组间天然不重叠（按网格边界）
    缺点：网格边缘的点可能被分开
    """
    # 计算网格范围
    lats = [p['lat'] for p in points]
    lngs = [p['lng'] for p in points]
    
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    
    # 计算网格大小（度数）
    lat_step = grid_size_km / 111.0  # 1 度纬度≈111km
    lng_step = grid_size_km / (111.0 * np.cos(np.radians(np.mean(lats))))
    
    # 分配点到网格
    grid_map = {}
    for i, p in enumerate(points):
        grid_lat = int((p['lat'] - min_lat) / lat_step)
        grid_lng = int((p['lng'] - min_lng) / lng_step)
        grid_key = (grid_lat, grid_lng)
        
        if grid_key not in grid_map:
            grid_map[grid_key] = []
        grid_map[grid_key].append(i)
    
    # 合并小网格（如果网格内点数太少，合并到相邻网格）
    clusters = list(grid_map.values())
    
    # 拆分大网格
    final_clusters = []
    for cluster in clusters:
        if len(cluster) <= max_points_per_group:
            final_clusters.append(cluster)
        else:
            # 按空间位置拆分
            sub_clusters = split_cluster_spatial(points, cluster, max_points_per_group)
            final_clusters.extend(sub_clusters)
    
    return final_clusters


def split_cluster_spatial(points: List[dict], 
                          cluster: List[int], 
                          max_size: int) -> List[List[int]]:
    """空间拆分大组"""
    if len(cluster) <= max_size:
        return [cluster]
    
    from sklearn.cluster import KMeans
    
    coords = np.array([[points[i]['lat'], points[i]['lng']] for i in cluster])
    k = (len(cluster) + max_size - 1) // max_size
    
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(coords)
    
    sub_clusters = []
    for i in range(k):
        sub = [cluster[j] for j in range(len(cluster)) if labels[j] == i]
        if sub:
            sub_clusters.append(sub)
    
    return sub_clusters


# ============================================================
# 算法 2: Voronoi 多边形法
# ============================================================
def voronoi_partition(points: List[dict],
                      num_seeds: int = 6,
                      max_points_per_group: int = 15) -> List[List[int]]:
    """
    Voronoi 多边形法
    
    原理：选择 K 个种子点，每个点分配到最近的种子
    优点：组间边界清晰（Voronoi 边界），天然不重叠
    缺点：需要选择合适的种子点
    """
    n = len(points)
    
    # 选择种子点（相互距离最远的 K 个点）
    seeds = []
    remaining = set(range(n))
    
    # 第一个种子：最靠近中心
    center_lat = np.mean([p['lat'] for p in points])
    center_lng = np.mean([p['lng'] for p in points])
    first_seed = min(range(n), key=lambda i: haversine(points[i]['lat'], points[i]['lng'], center_lat, center_lng))
    seeds.append(first_seed)
    remaining.remove(first_seed)
    
    # 后续种子：离已有种子最远
    while len(seeds) < num_seeds and remaining:
        best_candidate = None
        best_min_dist = -1
        
        for i in remaining:
            min_dist_to_seeds = min(haversine(
                points[i]['lat'], points[i]['lng'],
                points[s]['lat'], points[s]['lng']
            ) for s in seeds)
            if min_dist_to_seeds > best_min_dist:
                best_min_dist = min_dist_to_seeds
                best_candidate = i
        
        if best_candidate is not None:
            seeds.append(best_candidate)
            remaining.remove(best_candidate)
    
    # 分配每个点到最近的种子
    clusters = {i: [] for i in range(len(seeds))}
    
    for i in range(n):
        if i in seeds:
            seed_idx = seeds.index(i)
            clusters[seed_idx].append(i)
        else:
            # 找到最近的种子
            best_seed = 0
            best_dist = float('inf')
            for seed_idx, seed_i in enumerate(seeds):
                d = haversine(
                    points[i]['lat'], points[i]['lng'],
                    points[seed_i]['lat'], points[seed_i]['lng']
                )
                if d < best_dist:
                    best_dist = d
                    best_seed = seed_idx
            clusters[best_seed].append(i)
    
    result = list(clusters.values())
    
    # 处理过大的组
    final_clusters = []
    for cluster in result:
        if len(cluster) <= max_points_per_group:
            final_clusters.append(cluster)
        else:
            sub_clusters = split_cluster_spatial(points, cluster, max_points_per_group)
            final_clusters.extend(sub_clusters)
    
    return final_clusters


# ============================================================
# 算法 3: 河流/道路约束聚类（针对长寿区沿长江分布）
# ============================================================
def river_constrained_clustering(points: List[dict],
                                  max_points_per_group: int = 15,
                                  river_direction: str = 'east-west') -> List[List[int]]:
    """
    河流/道路约束聚类
    
    原理：沿主要走向（如长江东西向）切片分组
    优点：符合地理特征，组间天然分离
    缺点：需要知道主要走向
    
    长寿区特点：沿长江东西向带状分布
    """
    n = len(points)
    
    if river_direction == 'east-west':
        # 按经度排序（东西向）
        sorted_indices = sorted(range(n), key=lambda i: points[i]['lng'])
    else:
        # 按纬度排序（南北向）
        sorted_indices = sorted(range(n), key=lambda i: points[i]['lat'])
    
    # 计算总点数和组数
    num_groups = max(1, (n + max_points_per_group - 1) // max_points_per_group)
    points_per_group = (n + num_groups - 1) // num_groups
    
    # 按顺序切片
    clusters = []
    for i in range(0, n, points_per_group):
        cluster = sorted_indices[i:i + points_per_group]
        if cluster:
            clusters.append(cluster)
    
    return clusters


# ============================================================
# 算法 4: 约束 K-Means（强制分离）
# ============================================================
def constrained_kmeans(points: List[dict],
                       num_clusters: int = 6,
                       max_points_per_group: int = 15,
                       separation_penalty: float = 2.0) -> List[List[int]]:
    """
    约束 K-Means
    
    原理：在 K-Means 基础上添加分离惩罚，强制簇间距离
    优点：可调节分离度
    缺点：需要调参
    """
    from sklearn.cluster import KMeans
    
    n = len(points)
    coords = np.array([[p['lat'], p['lng']] for p in points])
    
    # 多次运行 K-Means，选择分离度最好的
    best_labels = None
    best_separation = -1
    
    for seed in range(10):
        kmeans = KMeans(n_clusters=num_clusters, random_state=seed, n_init=10)
        labels = kmeans.fit_predict(coords)
        
        # 计算分离度
        centroids = kmeans.cluster_centers_
        min_centroid_dist = float('inf')
        for i in range(num_clusters):
            for j in range(i + 1, num_clusters):
                d = np.linalg.norm(centroids[i] - centroids[j])
                min_centroid_dist = min(min_centroid_dist, d)
        
        # 计算簇内半径
        max_radius = 0
        for k in range(num_clusters):
            cluster_points = coords[labels == k]
            if len(cluster_points) > 0:
                centroid = centroids[k]
                radius = max(np.linalg.norm(p - centroid) for p in cluster_points)
                max_radius = max(max_radius, radius)
        
        # 分离度 = 质心最小距离 / 最大半径
        separation = min_centroid_dist / max_radius if max_radius > 0 else 0
        
        if separation > best_separation:
            best_separation = separation
            best_labels = labels
    
    # 转换为簇列表
    clusters = []
    for k in range(num_clusters):
        cluster = [i for i in range(n) if best_labels[i] == k]
        if cluster:
            clusters.append(cluster)
    
    # 处理过大的组
    final_clusters = []
    for cluster in clusters:
        if len(cluster) <= max_points_per_group:
            final_clusters.append(cluster)
        else:
            sub_clusters = split_cluster_spatial(points, cluster, max_points_per_group)
            final_clusters.extend(sub_clusters)
    
    return final_clusters


# ============================================================
# 评估指标
# ============================================================
def evaluate_clustering(points: List[dict], 
                       clusters: List[List[int]], 
                       dist_matrix: np.ndarray) -> dict:
    """评估聚类质量"""
    if not clusters:
        return {}
    
    n = len(points)
    metrics = {
        'num_clusters': len(clusters),
        'total_points': sum(len(c) for c in clusters),
        'cluster_sizes': [len(c) for c in clusters],
        'avg_cluster_size': np.mean([len(c) for c in clusters]),
        'max_cluster_size': max(len(c) for c in clusters),
        'min_cluster_size': min(len(c) for c in clusters),
    }
    
    # 大小均衡性
    sizes = metrics['cluster_sizes']
    metrics['size_std'] = np.std(sizes)
    metrics['size_variance_ratio'] = metrics['size_std'] / metrics['avg_cluster_size'] if metrics['avg_cluster_size'] > 0 else 0
    
    # 组内最大距离
    intra_cluster_max = []
    for cluster in clusters:
        if len(cluster) < 2:
            intra_cluster_max.append(0)
        else:
            max_d = max(dist_matrix[i][j] for i in cluster for j in cluster if i < j)
            intra_cluster_max.append(max_d)
    
    metrics['avg_intra_cluster_max_km'] = np.mean(intra_cluster_max)
    metrics['max_intra_cluster_max_km'] = max(intra_cluster_max)
    
    # 组间最小距离
    inter_cluster_min = []
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            min_d = min(dist_matrix[p1][p2] for p1 in clusters[i] for p2 in clusters[j])
            inter_cluster_min.append(min_d)
    
    if inter_cluster_min:
        metrics['avg_inter_cluster_min_km'] = np.mean(inter_cluster_min)
        metrics['min_inter_cluster_min_km'] = min(inter_cluster_min)
        
        # 分离度比率
        if metrics['avg_intra_cluster_max_km'] > 0:
            metrics['separation_ratio'] = (
                metrics['avg_inter_cluster_min_km'] / 
                metrics['avg_intra_cluster_max_km']
            )
    
    # 计算重叠检测
    metrics['has_overlap'] = check_cluster_overlap(points, clusters, dist_matrix)
    
    # 效率评分（综合指标）
    # 理想：组内紧凑 + 组间分离 + 大小均衡
    efficiency_score = 100
    efficiency_score -= metrics['avg_intra_cluster_max_km'] * 5  # 组内距离越小越好
    efficiency_score += metrics.get('separation_ratio', 0) * 20  # 分离度越高越好
    efficiency_score -= metrics['size_variance_ratio'] * 30  # 越均衡越好
    if metrics['has_overlap']:
        efficiency_score -= 20  # 有重叠惩罚
    metrics['efficiency_score'] = max(0, efficiency_score)
    
    return metrics


def check_cluster_overlap(points: List[dict], 
                         clusters: List[List[int]], 
                         dist_matrix: np.ndarray,
                         overlap_threshold_km: float = 1.0) -> bool:
    """
    检查簇是否有重叠
    
    定义：如果两个簇的各一点之间距离小于阈值，则认为可能重叠
    """
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            min_d = min(dist_matrix[p1][p2] for p1 in clusters[i] for p2 in clusters[j])
            if min_d < overlap_threshold_km:
                return True  # 有重叠
    return False


# ============================================================
# 可视化
# ============================================================
def generate_visualization(points: List[dict],
                          clusters: List[List[int]],
                          algorithm_name: str,
                          output_path: str):
    """生成 HTML 可视化"""
    import folium
    
    center_lat = np.mean([p['lat'] for p in points])
    center_lng = np.mean([p['lng'] for p in points])
    
    m = folium.Map(location=[center_lat, center_lng], zoom_start=11)
    
    colors = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
        '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'
    ]
    
    for cluster_idx, cluster in enumerate(clusters):
        color = colors[cluster_idx % len(colors)]
        cluster_points = [points[i] for i in cluster]
        
        # 计算凸包边界（更精确的组边界）
        lats = [p['lat'] for p in cluster_points]
        lngs = [p['lng'] for p in cluster_points]
        
        # 绘制点
        for p in cluster_points:
            folium.CircleMarker(
                location=[p['lat'], p['lng']],
                radius=8,
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.8,
                popup=f"{p['name']}<br>组 {cluster_idx + 1}"
            ).add_to(m)
        
        # 绘制组边界（使用多边形）
        if len(cluster_points) >= 3:
            from scipy.spatial import ConvexHull
            coords = np.array([[p['lat'], p['lng']] for p in cluster_points])
            try:
                hull = ConvexHull(coords)
                hull_points = coords[hull.vertices]
                
                folium.Polygon(
                    locations=hull_points.tolist(),
                    color=color,
                    weight=2,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.15,
                    popup=f"组 {cluster_idx + 1}: {len(cluster)} 个点"
                ).add_to(m)
            except:
                pass
    
    m.save(output_path)
    print(f"  可视化：{output_path}")


# ============================================================
# 主测试
# ============================================================
def run_comparison():
    print("=" * 70)
    print("采样点分组算法对比测试")
    print("=" * 70)
    
    # 加载数据
    print("\n[1] 加载数据...")
    points = load_data("地址修正表.xlsx")
    
    # 构建距离矩阵
    print("\n[2] 构建距离矩阵...")
    dist_matrix = build_distance_matrix(points)
    
    # 运行 4 种算法
    print("\n[3] 运行算法对比...")
    
    algorithms = [
        ("网格划分法 (5km 网格)", lambda: grid_partition(points, grid_size_km=5.0, max_points_per_group=15)),
        ("Voronoi 多边形法 (6 组)", lambda: voronoi_partition(points, num_seeds=6, max_points_per_group=15)),
        ("河流约束聚类 (东西向)", lambda: river_constrained_clustering(points, max_points_per_group=15)),
        ("约束 K-Means (6 组)", lambda: constrained_kmeans(points, num_clusters=6, max_points_per_group=15)),
    ]
    
    results = []
    
    for algo_name, algo_func in algorithms:
        print(f"\n  运行：{algo_name}")
        clusters = algo_func()
        metrics = evaluate_clustering(points, clusters, dist_matrix)
        metrics['algorithm'] = algo_name
        metrics['clusters'] = clusters
        results.append(metrics)
        
        print(f"    分组数：{metrics['num_clusters']}")
        print(f"    组大小：{metrics['cluster_sizes']}")
        print(f"    组内最大距离 (平均): {metrics['avg_intra_cluster_max_km']:.2f} km")
        print(f"    分离度比率：{metrics.get('separation_ratio', 0):.2f}")
        print(f"    有重叠：{metrics['has_overlap']}")
        print(f"    效率评分：{metrics['efficiency_score']:.1f}")
    
    # 排序
    results.sort(key=lambda x: x['efficiency_score'], reverse=True)
    
    # 打印排名
    print("\n" + "=" * 70)
    print("算法排名 (按效率评分)")
    print("=" * 70)
    
    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r['algorithm']}")
        print(f"   效率评分：{r['efficiency_score']:.1f}")
        print(f"   组内最大距离：{r['avg_intra_cluster_max_km']:.2f} km")
        print(f"   分离度比率：{r.get('separation_ratio', 0):.2f}")
        print(f"   大小变异系数：{r['size_variance_ratio']:.2f}")
        print(f"   有重叠：{r['has_overlap']}")
    
    # 生成可视化
    print("\n[4] 生成可视化...")
    os.makedirs("output/algorithm_comparison", exist_ok=True)
    
    for r in results:
        safe_name = r['algorithm'].replace(" ", "_").replace("(", "").replace(")", "")
        output_path = f"output/algorithm_comparison/{safe_name}.html"
        generate_visualization(points, r['clusters'], r['algorithm'], output_path)
    
    # 保存结果
    output_data = {
        'rankings': [
            {
                'rank': i + 1,
                'algorithm': r['algorithm'],
                'efficiency_score': r['efficiency_score'],
                'metrics': {
                    'num_clusters': r['num_clusters'],
                    'cluster_sizes': r['cluster_sizes'],
                    'avg_intra_cluster_max_km': r['avg_intra_cluster_max_km'],
                    'separation_ratio': r.get('separation_ratio', 0),
                    'size_variance_ratio': r['size_variance_ratio'],
                    'has_overlap': r['has_overlap']
                }
            }
            for i, r in enumerate(results)
        ]
    }
    
    with open("output/algorithm_comparison/comparison_result.json", 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n结果保存到：output/algorithm_comparison/")
    print("=" * 70)
    
    return results


if __name__ == "__main__":
    run_comparison()
