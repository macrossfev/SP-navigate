#!/usr/bin/env python3
"""
采样点分组算法 - 最终版（每组 4-6 点）
核心目标：
1. 每组最多 6 个点（硬性约束）
2. 每组最少 4 个点（避免单点组）
3. 组内点真正临近
4. 组间边界清晰
"""
import pandas as pd
import numpy as np
from typing import List
import json
import os


def load_data(excel_path: str) -> List[dict]:
    """加载数据"""
    df = pd.read_excel(excel_path)
    valid = df[df['坐标'].notna()]
    
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
    unique = []
    for p in points:
        key = (p['lng'], p['lat'])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    
    return unique


def haversine(lat1, lng1, lat2, lng2) -> float:
    """计算距离 (km)"""
    R = 6371.0
    lat1_rad = np.radians(lat1)
    lat2_rad = np.radians(lat2)
    delta_lat = np.radians(lat2 - lat1)
    delta_lng = np.radians(lng2 - lng1)
    a = np.sin(delta_lat/2)**2 + np.cos(lat1_rad)*np.cos(lat2_rad)*np.sin(delta_lng/2)**2
    c = 2*np.arctan2(np.sqrt(a), np.sqrt(1-a))
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


def detect_outliers(points: List[dict], threshold_km: float = 15.0) -> tuple:
    """检测异常点"""
    center_lat = np.mean([p['lat'] for p in points])
    center_lng = np.mean([p['lng'] for p in points])
    
    outliers = []
    normal = []
    
    for i, p in enumerate(points):
        d = haversine(center_lat, center_lng, p['lat'], p['lng'])
        if d > threshold_km:
            outliers.append((i, p, d))
        else:
            normal.append(i)
    
    return outliers, normal


# ============================================================
# 优化后的贪心算法（每组 4-6 点）
# ============================================================
def optimized_greedy_clustering(points: List[dict], 
                                 dist_matrix: np.ndarray,
                                 min_points: int = 4,
                                 max_points: int = 6) -> List[List[int]]:
    """
    优化的贪心聚类
    
    步骤：
    1. 贪心生长（每组最多 6 点）
    2. 后处理：合并小组（<4 点）到相邻大组
    3. 后处理：拆分超大组
    """
    n = len(points)
    unassigned = set(range(n))
    clusters = []
    
    # 步骤 1: 贪心生长
    while len(unassigned) >= min_points:
        # 选择种子点（最孤立的点）
        if len(unassigned) <= max_points:
            # 剩余点不多，直接作为一组
            cluster = list(unassigned)
            unassigned.clear()
            clusters.append(cluster)
            break
        
        # 计算孤立分数
        isolation_scores = []
        for i in unassigned:
            dists = [dist_matrix[i][j] for j in unassigned if j != i]
            avg_dist = np.mean(dists) if dists else 0
            isolation_scores.append((i, avg_dist))
        
        seed = max(isolation_scores, key=lambda x: x[1])[0]
        
        # 贪心生长
        cluster = [seed]
        unassigned.remove(seed)
        
        while len(cluster) < max_points and unassigned:
            best_point = None
            best_dist = float('inf')
            
            for i in unassigned:
                min_d = min(dist_matrix[i][j] for j in cluster)
                if min_d < best_dist:
                    best_dist = min_d
                    best_point = i
            
            if best_point:
                cluster.append(best_point)
                unassigned.remove(best_point)
        
        clusters.append(cluster)
    
    # 处理剩余点
    if unassigned:
        remaining = list(unassigned)
        # 分配到最近的簇
        for i in remaining:
            best_cluster = 0
            best_dist = float('inf')
            
            for c_idx, cluster in enumerate(clusters):
                if len(cluster) < max_points:
                    d = min(dist_matrix[i][j] for j in cluster)
                    if d < best_dist:
                        best_dist = d
                        best_cluster = c_idx
            
            clusters[best_cluster].append(i)
        unassigned.clear()
    
    # 步骤 2: 合并小组
    clusters = merge_small_clusters(points, clusters, dist_matrix, min_points)
    
    # 步骤 3: 拆分大组
    clusters = split_large_clusters(points, clusters, dist_matrix, max_points)
    
    return clusters


def merge_small_clusters(points: List[dict], clusters: List[List[int]], 
                         dist_matrix: np.ndarray, min_size: int) -> List[List[int]]:
    """合并小于最小值的簇"""
    clusters = [c.copy() for c in clusters]
    
    for _ in range(20):
        # 找到所有小组
        small_indices = [i for i, c in enumerate(clusters) if len(c) < min_size and len(c) > 0]
        
        if not small_indices:
            break
        
        merged = False
        for small_idx in small_indices:
            small_cluster = clusters[small_idx]
            if not small_cluster:
                continue
            
            # 找到最近的可以接收的大组
            best_target = -1
            best_dist = float('inf')
            
            for target_idx, target_cluster in enumerate(clusters):
                if target_idx == small_idx:
                    continue
                if len(target_cluster) >= 6:  # 不能超过最大值
                    continue
                
                # 计算簇间最小距离
                d = min(dist_matrix[i][j] for i in small_cluster for j in target_cluster)
                if d < best_dist:
                    best_dist = d
                    best_target = target_idx
            
            if best_target >= 0:
                # 合并
                clusters[best_target].extend(small_cluster)
                clusters[small_idx] = []
                merged = True
        
        # 移除空簇
        clusters = [c for c in clusters if c]
        
        if not merged:
            break
    
    return clusters


def split_large_clusters(points: List[dict], clusters: List[List[int]], 
                         dist_matrix: np.ndarray, max_size: int) -> List[List[int]]:
    """拆分超过最大值的簇"""
    result = []
    
    for cluster in clusters:
        if len(cluster) <= max_size:
            result.append(cluster)
        else:
            # 按空间拆分
            sub_clusters = split_spatial(points, cluster, dist_matrix, max_size)
            result.extend(sub_clusters)
    
    return result


def split_spatial(points: List[dict], cluster: List[int], 
                  dist_matrix: np.ndarray, max_size: int) -> List[List[int]]:
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
# 评估
# ============================================================
def evaluate(points: List[dict], clusters: List[List[int]], 
             dist_matrix: np.ndarray) -> dict:
    """评估聚类质量"""
    if not clusters:
        return {}
    
    sizes = [len(c) for c in clusters]
    metrics = {
        'num_clusters': len(clusters),
        'cluster_sizes': sizes,
        'avg_size': np.mean(sizes),
        'max_size': max(sizes),
        'min_size': min(sizes),
        'size_std': np.std(sizes),
    }
    
    # 检查约束
    metrics['violates_max'] = any(s > 6 for s in sizes)
    metrics['has_very_small'] = any(s < 4 for s in sizes)
    metrics['violates_constraint'] = metrics['violates_max'] or metrics['has_very_small']
    
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
    
    # 效率评分
    score = 100
    score -= metrics['avg_intra_max_km'] * 5
    score += metrics.get('separation_ratio', 0) * 10
    score -= metrics['size_std'] * 5
    if metrics['violates_constraint']:
        score -= 50
    metrics['efficiency_score'] = max(0, score)
    
    return metrics


# ============================================================
# 可视化
# ============================================================
def visualize(points: List[dict], clusters: List[List[int]], 
              outliers: list, output: str):
    """生成 HTML 可视化"""
    import folium
    
    normal_indices = [i for i in range(len(points)) if not any(i == o[0] for o in outliers)]
    center_lat = np.mean([points[i]['lat'] for i in normal_indices]) if normal_indices else np.mean([p['lat'] for p in points])
    center_lng = np.mean([points[i]['lng'] for i in normal_indices]) if normal_indices else np.mean([p['lng'] for p in points])
    
    m = folium.Map(location=[center_lat, center_lng], zoom_start=12)
    
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', 
              '#DDA0DD', '#F1948A', '#D2B4DE', '#A9DFBF', '#F9E79F']
    
    for idx, cluster in enumerate(clusters):
        color = colors[idx % len(colors)]
        cluster_points = [points[i] for i in cluster]
        
        lats = [p['lat'] for p in cluster_points]
        lngs = [p['lng'] for p in cluster_points]
        center = (np.mean(lats), np.mean(lngs))
        max_dist = max(haversine(center[0], center[1], p['lat'], p['lng']) for p in cluster_points) if cluster_points else 0
        
        folium.Circle(
            location=center,
            radius=max_dist * 1000,
            color=color,
            weight=2,
            fill=True,
            fillColor=color,
            fillOpacity=0.15,
            popup=f"组{idx+1}: {len(cluster)}点"
        ).add_to(m)
        
        for p in cluster_points:
            folium.CircleMarker(
                location=[p['lat'], p['lng']],
                radius=8,
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.9,
                popup=f"{p['name']}"
            ).add_to(m)
    
    for i, p, d in outliers:
        folium.CircleMarker(
            location=[p['lat'], p['lng']],
            radius=10,
            color='#FF0000',
            fill=True,
            fillColor='#FF0000',
            fillOpacity=0.8,
            popup=f"{p['name']}<br>异常点 ({d:.1f}km)"
        ).add_to(m)
    
    m.save(output)
    print(f"  可视化：{output}")


# ============================================================
# 主测试
# ============================================================
def main():
    print("=" * 70)
    print("采样点分组算法 - 最终版（每组 4-6 点）")
    print("=" * 70)
    
    print("\n[1] 加载数据...")
    points = load_data("地址修正表.xlsx")
    print(f"  唯一点位：{len(points)} 个")
    
    print("\n[2] 检测异常点...")
    outliers, normal_indices = detect_outliers(points, threshold_km=15.0)
    print(f"  异常点：{len(outliers)} 个")
    for i, p, d in outliers:
        print(f"    - {p['name']} (距中心 {d:.1f}km)")
    
    print(f"\n[3] 对 {len(normal_indices)} 个正常点分组 (每组 4-6 点)...")
    normal_points = [points[i] for i in normal_indices]
    normal_dist_matrix = build_distance_matrix(normal_points)
    
    clusters_normal = optimized_greedy_clustering(
        normal_points, normal_dist_matrix, 
        min_points=4, max_points=6
    )
    
    # 映射回原始索引
    clusters = []
    for cluster in clusters_normal:
        original = [normal_indices[i] for i in cluster]
        clusters.append(original)
    
    print("\n[4] 评估结果...")
    metrics = evaluate(points, clusters, build_distance_matrix(points))
    
    print(f"""
分组结果:
  组数：{metrics['num_clusters']}
  各组大小：{metrics['cluster_sizes']}
  平均大小：{metrics['avg_size']:.1f}
  大小范围：[{metrics['min_size']}, {metrics['max_size']}]
  违反约束：{metrics['violates_constraint']}

组内紧凑度:
  组内最大距离 (平均): {metrics['avg_intra_max_km']:.2f} km
  组内最大距离 (最大): {metrics['max_intra_max_km']:.2f} km

组间分离度:
  组间最小距离 (平均): {metrics.get('avg_inter_min_km', 0):.2f} km
  分离度比率：{metrics.get('separation_ratio', 0):.2f}
  效率评分：{metrics['efficiency_score']:.1f}
""")
    
    # 打印每组详情
    print("[分组详情]")
    for i, cluster in enumerate(clusters):
        names = [points[j]['name'][:10] for j in cluster]
        lats = [points[j]['lat'] for j in cluster]
        lngs = [points[j]['lng'] for j in cluster]
        print(f"  组{i+1} ({len(cluster)}点): 经度{min(lngs):.4f}-{max(lngs):.4f}, 纬度{min(lats):.4f}-{max(lats):.4f}")
        print(f"         {', '.join(names)}")
    
    # 可视化
    print("\n[5] 生成可视化...")
    os.makedirs("output/final_max6", exist_ok=True)
    visualize(points, clusters, outliers, "output/final_max6/result.html")
    
    # 保存结果
    result = {
        'metrics': metrics,
        'outliers': [{'name': p['name'], 'lng': p['lng'], 'lat': p['lat'], 'distance_km': d} for i, p, d in outliers],
        'clusters': [
            {
                'cluster_id': i,
                'size': len(c),
                'points': [{'name': points[j]['name'], 'lng': points[j]['lng'], 'lat': points[j]['lat']} for j in c]
            }
            for i, c in enumerate(clusters)
        ]
    }
    
    with open("output/final_max6/result.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n结果保存到：output/final_max6/")
    print("=" * 70)


if __name__ == "__main__":
    main()
