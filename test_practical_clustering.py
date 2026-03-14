#!/usr/bin/env python3
"""
采样点分组算法 - 实用版本
核心目标：
1. 组间地理边界清晰（无重叠）
2. 每组点数可控
3. 组内点真正临近
"""
import pandas as pd
import numpy as np
from typing import List, Tuple
import json
import os


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
# 算法 1: 改进的网格法 - 合并相邻网格
# ============================================================
def improved_grid_clustering(points: List[dict],
                             target_groups: int = 6,
                             max_points_per_group: int = 15) -> List[List[int]]:
    """
    改进的网格聚类 - 合并相邻网格直到达到目标组数
    
    步骤：
    1. 初始网格划分
    2. 合并小网格（优先合并最近的相邻网格）
    3. 拆分大网格
    """
    n = len(points)
    
    # 计算网格范围
    lats = [p['lat'] for p in points]
    lngs = [p['lng'] for p in points]
    
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    
    # 动态计算网格大小
    lat_range = max_lat - min_lat
    lng_range = max_lng - min_lng
    
    # 初始网格数 = 目标组数的 2 倍（给合并留空间）
    initial_grids = target_groups * 2
    lat_grids = int(np.sqrt(initial_grids * lat_range / lng_range)) + 1
    lng_grids = int(initial_grids / lat_grids) + 1
    
    lat_step = lat_range / lat_grids
    lng_step = lng_range / lng_grids
    
    # 分配点到网格
    grid_map = {}
    for i, p in enumerate(points):
        grid_lat = int((p['lat'] - min_lat) / max(lat_step, 0.0001))
        grid_lng = int((p['lng'] - min_lng) / max(lng_step, 0.0001))
        grid_key = (grid_lat, grid_lng)
        
        if grid_key not in grid_map:
            grid_map[grid_key] = []
        grid_map[grid_key].append(i)
    
    # 转换为簇列表
    clusters = list(grid_map.values())
    print(f"  初始网格数：{len(clusters)}")
    
    # 合并相邻网格直到达到目标组数
    while len(clusters) > target_groups:
        # 找到最近的两个簇
        min_dist = float('inf')
        merge_i, merge_j = 0, 1
        
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                # 计算簇间最小距离
                d = min(haversine(
                    points[a]['lat'], points[a]['lng'],
                    points[b]['lat'], points[b]['lng']
                ) for a in clusters[i] for b in clusters[j])
                
                if d < min_dist:
                    min_dist = d
                    merge_i, merge_j = i, j
        
        # 合并
        clusters[merge_i] = clusters[merge_i] + clusters[merge_j]
        clusters.pop(merge_j)
    
    # 拆分过大的簇
    final_clusters = []
    for cluster in clusters:
        if len(cluster) <= max_points_per_group:
            final_clusters.append(cluster)
        else:
            # 按空间拆分
            sub_clusters = split_spatial(points, cluster, max_points_per_group)
            final_clusters.extend(sub_clusters)
    
    return final_clusters


def split_spatial(points: List[dict], cluster: List[int], max_size: int) -> List[List[int]]:
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
# 算法 2: 改进的 Voronoi - 带边界缓冲
# ============================================================
def improved_voronoi(points: List[dict],
                     target_groups: int = 6,
                     max_points_per_group: int = 15) -> List[List[int]]:
    """
    改进的 Voronoi 分区
    
    步骤：
    1. 选择 K 个种子点（相互距离最远）
    2. 每个点分配到最近的种子
    3. 后处理：平衡大小
    """
    n = len(points)
    
    # 选择种子点
    seeds = []
    remaining = set(range(n))
    
    # 第一个种子：最靠近中心
    center_lat = np.mean([p['lat'] for p in points])
    center_lng = np.mean([p['lng'] for p in points])
    first_seed = min(range(n), key=lambda i: haversine(points[i]['lat'], points[i]['lng'], center_lat, center_lng))
    seeds.append(first_seed)
    remaining.remove(first_seed)
    
    # 后续种子：离已有种子最远
    while len(seeds) < target_groups and remaining:
        best_candidate = None
        best_min_dist = -1
        
        for i in remaining:
            min_dist = min(haversine(
                points[i]['lat'], points[i]['lng'],
                points[s]['lat'], points[s]['lng']
            ) for s in seeds)
            if min_dist > best_min_dist:
                best_min_dist = min_dist
                best_candidate = i
        
        if best_candidate:
            seeds.append(best_candidate)
            remaining.remove(best_candidate)
    
    print(f"  种子点数：{len(seeds)}")
    
    # 分配点到最近的种子
    clusters = {i: [] for i in range(len(seeds))}
    
    for i in range(n):
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
    
    # 平衡大小
    result = balance_clusters(points, result, max_points_per_group)
    
    return result


def balance_clusters(points: List[dict], 
                    clusters: List[List[int]], 
                    max_size: int) -> List[List[int]]:
    """平衡簇大小"""
    clusters = [c.copy() for c in clusters]
    
    # 迭代直到所有簇满足约束
    for _ in range(50):
        # 找到过大和过小的簇
        too_large = [(i, c) for i, c in enumerate(clusters) if len(c) > max_size]
        too_small = [(i, c) for i, c in enumerate(clusters) if len(c) == 0]
        
        if not too_large and not too_small:
            break
        
        # 处理过大的簇
        for idx, cluster in too_large:
            if len(cluster) <= max_size:
                continue
            
            # 找到最近的可以接收点的簇
            excess = len(cluster) - max_size
            
            # 按距离排序簇内点（离簇中心最远的先移出）
            cluster_coords = np.array([[points[i]['lat'], points[i]['lng']] for i in cluster])
            center = np.mean(cluster_coords, axis=0)
            dists = [np.linalg.norm(cluster_coords[j] - center) for j in range(len(cluster))]
            sorted_indices = sorted(range(len(cluster)), key=lambda j: dists[j], reverse=True)
            
            for pos in sorted_indices[:excess]:
                point_idx = cluster[pos]
                
                # 找到最近的非过大簇
                best_target = -1
                best_dist = float('inf')
                for target_idx, target_cluster in enumerate(clusters):
                    if target_idx == idx:
                        continue
                    if len(target_cluster) >= max_size:
                        continue
                    
                    # 计算点到目标簇的距离
                    if target_cluster:
                        d = min(haversine(
                            points[point_idx]['lat'], points[point_idx]['lng'],
                            points[t]['lat'], points[t]['lng']
                        ) for t in target_cluster)
                    else:
                        d = 0
                    
                    if d < best_dist:
                        best_dist = d
                        best_target = target_idx
                
                if best_target >= 0:
                    cluster.remove(point_idx)
                    clusters[best_target].append(point_idx)
    
    # 移除空簇
    return [c for c in clusters if c]


# ============================================================
# 算法 3: 链式生长 - 真正临近聚合
# ============================================================
def chain_growth_clustering(points: List[dict],
                            target_groups: int = 6,
                            max_points_per_group: int = 15) -> List[List[int]]:
    """
    链式生长聚类
    
    核心思想：
    1. 选择 K 个种子点（相互距离最远）
    2. 每个种子独立生长，只吸收最近的未分配点
    3. 生长直到达到点数上限
    4. 剩余点分配到最近的簇
    
    优点：组内点真正链式临近
    """
    n = len(points)
    
    # 选择种子点
    seeds = []
    remaining = set(range(n))
    
    # 第一个种子：最靠近中心
    center_lat = np.mean([p['lat'] for p in points])
    center_lng = np.mean([p['lng'] for p in points])
    first_seed = min(range(n), key=lambda i: haversine(points[i]['lat'], points[i]['lng'], center_lat, center_lng))
    seeds.append(first_seed)
    remaining.remove(first_seed)
    
    # 后续种子：离已有种子最远
    while len(seeds) < target_groups and remaining:
        best_candidate = None
        best_min_dist = -1
        
        for i in remaining:
            min_dist = min(haversine(
                points[i]['lat'], points[i]['lng'],
                points[s]['lat'], points[s]['lng']
            ) for s in seeds)
            if min_dist > best_min_dist:
                best_min_dist = min_dist
                best_candidate = i
        
        if best_candidate:
            seeds.append(best_candidate)
            remaining.remove(best_candidate)
    
    print(f"  种子点数：{len(seeds)}")
    
    # 初始化簇
    clusters = [[s] for s in seeds]
    assigned = set(seeds)
    unassigned = set(range(n)) - assigned
    
    # 并行生长
    target_size = n // target_groups
    
    while unassigned:
        grown = False
        
        # 按簇大小排序，优先生长小的
        order = sorted(range(len(clusters)), key=lambda c: len(clusters[c]))
        
        for cluster_idx in order:
            if not unassigned:
                break
            
            cluster = clusters[cluster_idx]
            
            # 如果已经达到目标大小，跳过
            if len(cluster) >= target_size + 2:
                continue
            
            # 找到最近的未分配点
            best_point = None
            best_dist = float('inf')
            
            for i in unassigned:
                # 计算到簇内所有点的最小距离
                min_d = min(haversine(
                    points[i]['lat'], points[i]['lng'],
                    points[j]['lat'], points[j]['lng']
                ) for j in cluster)
                
                if min_d < best_dist:
                    best_dist = min_d
                    best_point = i
            
            if best_point is not None:
                cluster.append(best_point)
                unassigned.remove(best_point)
                grown = True
        
        if not grown:
            break
    
    # 处理剩余点
    for i in list(unassigned):
        best_cluster = 0
        best_dist = float('inf')
        
        for c_idx, cluster in enumerate(clusters):
            if cluster:
                d = min(haversine(
                    points[i]['lat'], points[i]['lng'],
                    points[j]['lat'], points[j]['lng']
                ) for j in cluster)
                if d < best_dist:
                    best_dist = d
                    best_cluster = c_idx
        
        clusters[best_cluster].append(i)
        unassigned.remove(i)
    
    return clusters


# ============================================================
# 算法 4: 地理围栏法 - 基于主要道路/河流
# ============================================================
def geographic_fence_clustering(points: List[dict],
                                 target_groups: int = 6,
                                 max_points_per_group: int = 15) -> List[List[int]]:
    """
    地理围栏法
    
    针对长寿区特点：沿长江东西向分布
    按经度切片，每组一个经度范围
    """
    n = len(points)
    
    # 按经度排序
    sorted_indices = sorted(range(n), key=lambda i: points[i]['lng'])
    
    # 计算每组点数
    points_per_group = (n + target_groups - 1) // target_groups
    
    # 切片分组
    clusters = []
    for i in range(0, n, points_per_group):
        cluster = sorted_indices[i:i + points_per_group]
        if cluster:
            clusters.append(cluster)
    
    return clusters


# ============================================================
# 评估
# ============================================================
def evaluate(points: List[dict], clusters: List[List[int]], dist_matrix: np.ndarray) -> dict:
    """评估聚类质量"""
    if not clusters:
        return {}
    
    metrics = {
        'num_clusters': len(clusters),
        'total_points': sum(len(c) for c in clusters),
        'cluster_sizes': [len(c) for c in clusters],
        'avg_cluster_size': np.mean([len(c) for c in clusters]),
        'max_cluster_size': max(len(c) for c in clusters),
        'min_cluster_size': min(len(c) for c in clusters),
    }
    
    # 均衡性
    sizes = metrics['cluster_sizes']
    metrics['size_std'] = np.std(sizes)
    metrics['size_variance_ratio'] = metrics['size_std'] / metrics['avg_cluster_size'] if metrics['avg_cluster_size'] > 0 else 0
    
    # 组内最大距离
    intra_max = []
    for cluster in clusters:
        if len(cluster) < 2:
            intra_max.append(0)
        else:
            max_d = max(dist_matrix[i][j] for i in cluster for j in cluster if i < j)
            intra_max.append(max_d)
    
    metrics['avg_intra_max_km'] = np.mean(intra_max)
    metrics['max_intra_max_km'] = max(intra_max)
    
    # 组间最小距离
    inter_min = []
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            min_d = min(dist_matrix[p1][p2] for p1 in clusters[i] for p2 in clusters[j])
            inter_min.append(min_d)
    
    if inter_min:
        metrics['avg_inter_min_km'] = np.mean(inter_min)
        metrics['min_inter_min_km'] = min(inter_min)
        metrics['separation_ratio'] = metrics['avg_inter_min_km'] / metrics['avg_intra_max_km'] if metrics['avg_intra_max_km'] > 0 else 0
    
    # 重叠检测（严格）
    metrics['has_overlap'] = check_overlap(clusters, dist_matrix, threshold=0.5)
    
    # 效率评分
    score = 100
    score -= metrics['avg_intra_max_km'] * 3
    score += metrics.get('separation_ratio', 0) * 10
    score -= metrics['size_variance_ratio'] * 20
    if metrics['has_overlap']:
        score -= 30
    metrics['efficiency_score'] = max(0, score)
    
    return metrics


def check_overlap(clusters: List[List[int]], dist_matrix: np.ndarray, threshold: float = 0.5) -> bool:
    """检查是否有重叠（严格定义）"""
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            min_d = min(dist_matrix[p1][p2] for p1 in clusters[i] for p2 in clusters[j])
            if min_d < threshold:
                return True
    return False


# ============================================================
# 可视化
# ============================================================
def visualize(points: List[dict], clusters: List[List[int]], name: str, output: str):
    """生成可视化"""
    import folium
    from scipy.spatial import ConvexHull
    
    center_lat = np.mean([p['lat'] for p in points])
    center_lng = np.mean([p['lng'] for p in points])
    
    m = folium.Map(location=[center_lat, center_lng], zoom_start=11)
    
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD']
    
    for idx, cluster in enumerate(clusters):
        color = colors[idx % len(colors)]
        cluster_points = [points[i] for i in cluster]
        
        # 绘制凸包边界
        if len(cluster_points) >= 3:
            coords = np.array([[p['lat'], p['lng']] for p in cluster_points])
            try:
                hull = ConvexHull(coords)
                hull_points = coords[hull.vertices].tolist()
                
                folium.Polygon(
                    locations=hull_points,
                    color=color,
                    weight=3,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.2,
                    popup=f"组 {idx+1}: {len(cluster)}点"
                ).add_to(m)
            except:
                pass
        
        # 绘制点
        for p in cluster_points:
            folium.CircleMarker(
                location=[p['lat'], p['lng']],
                radius=7,
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.8,
                popup=f"{p['name']}"
            ).add_to(m)
    
    m.save(output)
    print(f"  {output}")


# ============================================================
# 主测试
# ============================================================
def main():
    print("=" * 70)
    print("采样点分组算法对比 - 实用版本")
    print("=" * 70)
    
    print("\n[1] 加载数据...")
    points = load_data("地址修正表.xlsx")
    n = len(points)
    
    print("\n[2] 构建距离矩阵...")
    dist_matrix = build_distance_matrix(points)
    
    # 配置
    target_groups = max(4, n // 12)  # 每组约 12 点
    max_points = 15
    
    print(f"\n[3] 运行算法 (目标{target_groups}组，每组≤{max_points}点)...")
    
    algorithms = [
        ("改进网格法", lambda: improved_grid_clustering(points, target_groups, max_points)),
        ("改进 Voronoi", lambda: improved_voronoi(points, target_groups, max_points)),
        ("链式生长", lambda: chain_growth_clustering(points, target_groups, max_points)),
        ("地理围栏", lambda: geographic_fence_clustering(points, target_groups, max_points)),
    ]
    
    results = []
    
    for name, func in algorithms:
        print(f"\n  运行：{name}")
        clusters = func()
        metrics = evaluate(points, clusters, dist_matrix)
        metrics['name'] = name
        metrics['clusters'] = clusters
        results.append(metrics)
        
        print(f"    分组：{metrics['num_clusters']}组")
        print(f"    大小：{metrics['cluster_sizes']}")
        print(f"    组内最大 (平均): {metrics['avg_intra_max_km']:.2f}km")
        print(f"    分离度：{metrics.get('separation_ratio', 0):.2f}")
        print(f"    重叠：{metrics['has_overlap']}")
        print(f"    评分：{metrics['efficiency_score']:.1f}")
    
    # 排名
    results.sort(key=lambda x: x['efficiency_score'], reverse=True)
    
    print("\n" + "=" * 70)
    print("算法排名")
    print("=" * 70)
    
    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r['name']}")
        print(f"   评分：{r['efficiency_score']:.1f}")
        print(f"   组内最大距离：{r['avg_intra_max_km']:.2f}km")
        print(f"   分离度：{r.get('separation_ratio', 0):.2f}")
        print(f"   大小变异：{r['size_variance_ratio']:.2f}")
        print(f"   重叠：{r['has_overlap']}")
        print(f"   分组：{r['cluster_sizes']}")
    
    # 可视化
    print("\n[4] 生成可视化...")
    os.makedirs("output/practical_comparison", exist_ok=True)
    
    for r in results:
        safe_name = r['name'].replace(" ", "_")
        visualize(points, r['clusters'], r['name'], f"output/practical_comparison/{safe_name}.html")
    
    # 保存
    with open("output/practical_comparison/comparison.json", 'w', encoding='utf-8') as f:
        json.dump([{
            'rank': i + 1,
            'name': r['name'],
            'efficiency_score': r['efficiency_score'],
            'num_clusters': r['num_clusters'],
            'cluster_sizes': r['cluster_sizes'],
            'avg_intra_max_km': r['avg_intra_max_km'],
            'separation_ratio': r.get('separation_ratio', 0),
            'has_overlap': r['has_overlap']
        } for i, r in enumerate(results)], f, indent=2, ensure_ascii=False)
    
    print("\n完成！结果：output/practical_comparison/")
    print("=" * 70)


if __name__ == "__main__":
    main()
