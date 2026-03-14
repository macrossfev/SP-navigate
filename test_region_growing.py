#!/usr/bin/env python3
"""
Region Growing Clustering Algorithm Test - v3
基于区域生长的聚类算法 - 最终版本
改进：
1. 自动调整分组数量，避免单点组
2. 增加簇间分离度约束
3. 后处理：合并单点组
"""
import pandas as pd
import numpy as np
from typing import List, Tuple
import json
import os


def load_data(excel_path: str):
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
    
    print(f"加载了 {len(points)} 个点")
    return points


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


def detect_outliers(
    points: List[dict],
    dist_matrix: np.ndarray,
    threshold_km: float = 20.0
) -> Tuple[List[int], List[int]]:
    """检测异常点（基于到质心的距离）"""
    center_lat = np.mean([p['lat'] for p in points])
    center_lng = np.mean([p['lng'] for p in points])
    
    outliers = []
    normal = []
    
    for i, p in enumerate(points):
        d = haversine(center_lat, center_lng, p['lat'], p['lng'])
        if d > threshold_km:
            outliers.append(i)
        else:
            normal.append(i)
    
    return outliers, normal


def region_growing_with_balance(
    points: List[dict],
    dist_matrix: np.ndarray,
    target_groups: int = 6,
    max_radius_km: float = 8.0
) -> List[List[int]]:
    """
    区域生长算法（平衡分组版本）
    
    核心思路：
    1. 先计算理想的每组点数
    2. 选择 K 个初始种子点（相互距离最远）
    3. 并行生长，直到达到目标大小
    """
    n = len(points)
    target_size = n // target_groups  # 每组目标点数
    
    # 步骤 1: 选择 K 个初始种子点（相互距离最远）
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
            min_dist_to_seeds = min(dist_matrix[i][s] for s in seeds)
            if min_dist_to_seeds > best_min_dist:
                best_min_dist = min_dist_to_seeds
                best_candidate = i
        
        if best_candidate is not None:
            seeds.append(best_candidate)
            remaining.remove(best_candidate)
        else:
            break
    
    print(f"  初始种子点：{len(seeds)} 个")
    
    # 步骤 2: 初始化簇
    clusters = [[s] for s in seeds]
    assigned = set(seeds)
    unassigned = set(range(n)) - assigned
    
    # 步骤 3: 并行生长
    max_iterations = n * 2
    iteration = 0
    
    while unassigned and iteration < max_iterations:
        iteration += 1
        grown = False
        
        # 按簇大小排序，优先生长小的簇
        cluster_order = sorted(range(len(clusters)), key=lambda c: len(clusters[c]))
        
        for cluster_idx in cluster_order:
            if not unassigned:
                break
            
            cluster = clusters[cluster_idx]
            
            # 如果已经达到目标大小，跳过
            if len(cluster) >= target_size + 2:
                continue
            
            # 计算簇中心
            cluster_lats = [points[i]['lat'] for i in cluster]
            cluster_lngs = [points[i]['lng'] for i in cluster]
            cluster_center = (np.mean(cluster_lats), np.mean(cluster_lngs))
            
            # 找到最近的未分配点
            best_point = None
            best_dist = float('inf')
            
            for i in unassigned:
                # 检查半径约束
                d_to_center = haversine(
                    cluster_center[0], cluster_center[1],
                    points[i]['lat'], points[i]['lng']
                )
                
                if d_to_center > max_radius_km:
                    continue
                
                # 计算到簇内所有点的平均距离
                avg_dist = np.mean([dist_matrix[i][j] for j in cluster])
                
                if avg_dist < best_dist:
                    best_dist = avg_dist
                    best_point = i
            
            if best_point is not None:
                cluster.append(best_point)
                unassigned.remove(best_point)
                grown = True
        
        if not grown:
            break
    
    # 步骤 4: 处理剩余未分配点
    for i in unassigned:
        # 分配到最近的簇
        best_cluster = 0
        best_dist = float('inf')
        
        for c_idx, cluster in enumerate(clusters):
            min_dist = min(dist_matrix[i][j] for j in cluster)
            if min_dist < best_dist:
                best_dist = min_dist
                best_cluster = c_idx
        
        clusters[best_cluster].append(i)
    
    # 步骤 5: 后处理 - 合并太小的簇
    clusters = merge_small_clusters(clusters, dist_matrix, min_size=3)
    
    return clusters


def merge_small_clusters(
    clusters: List[List[int]],
    dist_matrix: np.ndarray,
    min_size: int = 3
) -> List[List[int]]:
    """合并小于最小值的簇到最近的较大簇"""
    result = [c.copy() for c in clusters if len(c) >= min_size]
    small_clusters = [c.copy() for c in clusters if len(c) < min_size]
    
    for small in small_clusters:
        if not small:
            continue
        
        # 找到最近的较大簇
        best_cluster_idx = 0
        best_dist = float('inf')
        
        for i, cluster in enumerate(result):
            min_dist = min(dist_matrix[s][c] for s in small for c in cluster)
            if min_dist < best_dist:
                best_dist = min_dist
                best_cluster_idx = i
        
        # 合并
        result[best_cluster_idx].extend(small)
    
    return result


def generate_visualization(
    points: List[dict],
    clusters: List[List[int]],
    outliers: List[int],
    output_path: str
):
    """生成 HTML 可视化"""
    import folium
    
    normal_points = [p for i, p in enumerate(points) if i not in outliers]
    if normal_points:
        center_lat = np.mean([p['lat'] for p in normal_points])
        center_lng = np.mean([p['lng'] for p in normal_points])
    else:
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
        
        lats = [p['lat'] for p in cluster_points]
        lngs = [p['lng'] for p in cluster_points]
        center = (np.mean(lats), np.mean(lngs))
        max_dist = max(
            haversine(center[0], center[1], p['lat'], p['lng'])
            for p in cluster_points
        ) if cluster_points else 0
        
        folium.Circle(
            location=center,
            radius=max_dist * 1000,
            color=color,
            weight=2,
            fill=True,
            fillColor=color,
            fillOpacity=0.15,
            popup=f"组 {cluster_idx + 1}: {len(cluster)} 个点"
        ).add_to(m)
        
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
    
    for i in outliers:
        p = points[i]
        folium.CircleMarker(
            location=[p['lat'], p['lng']],
            radius=10,
            color='#FF0000',
            fill=True,
            fillColor='#FF0000',
            fillOpacity=0.8,
            popup=f"{p['name']}<br>异常点"
        ).add_to(m)
    
    m.save(output_path)
    print(f"可视化保存到：{output_path}")


def evaluate_clustering(
    points: List[dict],
    clusters: List[List[int]],
    dist_matrix: np.ndarray
) -> dict:
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
        
        if metrics['avg_intra_cluster_max_km'] > 0:
            metrics['separation_ratio'] = (
                metrics['avg_inter_cluster_min_km'] / 
                metrics['avg_intra_cluster_max_km']
            )
    
    # 均衡性评分
    sizes = metrics['cluster_sizes']
    if sizes:
        metrics['size_std'] = np.std(sizes)
        metrics['size_variance_ratio'] = metrics['size_std'] / metrics['avg_cluster_size']
    
    return metrics


if __name__ == "__main__":
    print("=" * 60)
    print("区域生长聚类算法测试 v3 (平衡分组)")
    print("=" * 60)
    
    # 加载数据
    print("\n[1] 加载数据...")
    points = load_data("地址修正表.xlsx")
    
    # 构建距离矩阵
    print("\n[2] 构建距离矩阵...")
    dist_matrix = build_distance_matrix(points)
    
    # 检测异常点
    print("\n[3] 检测异常点...")
    outliers, normal_indices = detect_outliers(
        points, dist_matrix, 
        threshold_km=20.0
    )
    
    print(f"  异常点：{len(outliers)}")
    for i in outliers:
        d = haversine(
            np.mean([p['lat'] for p in points]),
            np.mean([p['lng'] for p in points]),
            points[i]['lat'], points[i]['lng']
        )
        print(f"    - {points[i]['name']} (距中心 {d:.1f}km)")
    
    # 对正常点聚类
    print(f"\n[4] 对 {len(normal_indices)} 个正常点进行聚类...")
    normal_points = [points[i] for i in normal_indices]
    normal_dist_matrix = dist_matrix[np.ix_(normal_indices, normal_indices)]
    
    # 估算合适的分组数
    n = len(normal_indices)
    target_groups = max(5, n // 12)  # 每组约 12 个点
    print(f"  目标分组数：{target_groups}")
    
    idx_map = {old: new for new, old in enumerate(normal_indices)}
    
    clusters_normal = region_growing_with_balance(
        normal_points, normal_dist_matrix,
        target_groups=target_groups,
        max_radius_km=10.0
    )
    
    # 映射回原始索引
    reverse_map = {new: old for old, new in idx_map.items()}
    clusters = []
    for cluster in clusters_normal:
        original_indices = [reverse_map[i] for i in cluster]
        clusters.append(original_indices)
    
    # 评估
    print("\n[5] 评估聚类质量...")
    metrics = evaluate_clustering(points, clusters, dist_matrix)
    
    print("\n" + "=" * 60)
    print("聚类结果")
    print("=" * 60)
    print(f"  分组数量：{metrics['num_clusters']}")
    print(f"  总点数：{metrics['total_points']} (正常点)")
    print(f"  异常点数：{len(outliers)} (单独处理)")
    print(f"  平均每组点数：{metrics['avg_cluster_size']:.1f}")
    print(f"  最大组：{metrics['max_cluster_size']} 点")
    print(f"  最小组：{metrics['min_cluster_size']} 点")
    print(f"  组内最大距离 (平均): {metrics['avg_intra_cluster_max_km']:.2f} km")
    print(f"  组间最小距离 (平均): {metrics['avg_inter_cluster_min_km']:.2f} km")
    if 'separation_ratio' in metrics:
        print(f"  分离度比率：{metrics['separation_ratio']:.2f}")
    if 'size_variance_ratio' in metrics:
        print(f"  大小变异系数：{metrics['size_variance_ratio']:.2f} (越小越均衡)")
    
    print(f"\n  各组大小：{metrics['cluster_sizes']}")
    
    # 打印每组详情
    print("\n[分组详情]")
    for i, cluster in enumerate(clusters):
        names = [points[j]['name'][:15] for j in cluster]
        print(f"  组 {i+1} ({len(cluster)}点): {', '.join(names[:5])}{'...' if len(names)>5 else ''}")
    
    # 可视化
    print("\n[6] 生成可视化...")
    os.makedirs("output/region_growing_test", exist_ok=True)
    generate_visualization(
        points, clusters, outliers,
        "output/region_growing_test/clustering_result_v3.html"
    )
    
    # 保存结果
    result = {
        'metrics': metrics,
        'outliers': [
            {'name': points[i]['name'], 'lng': points[i]['lng'], 'lat': points[i]['lat']}
            for i in outliers
        ],
        'clusters': [
            {
                'cluster_id': i,
                'size': len(c),
                'points': [
                    {'name': points[j]['name'], 'lng': points[j]['lng'], 'lat': points[j]['lat']}
                    for j in c
                ]
            }
            for i, c in enumerate(clusters)
        ]
    }
    
    with open("output/region_growing_test/clustering_result_v3.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n结果保存到：output/region_growing_test/")
    print("=" * 60)
