#!/usr/bin/env python3
"""
采样点分组算法 - 每组最多 6 点
核心目标：
1. 每组最多 6 个点（硬性约束）
2. 组内点真正临近
3. 组间边界清晰（不重叠）
"""
import pandas as pd
import numpy as np
from typing import List, Tuple
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
# 算法 1: 贪心最近邻聚类（每组最多 6 点）
# ============================================================
def greedy_neighbor_clustering(points: List[dict], 
                                dist_matrix: np.ndarray,
                                max_points: int = 6) -> List[List[int]]:
    """
    贪心最近邻聚类
    
    核心思想：
    1. 从未分配点中选择最孤立的点作为种子
    2. 贪心添加最近的点，直到达到 6 点上限
    3. 重复直到所有点分配完毕
    
    优点：组内点真正临近
    """
    n = len(points)
    unassigned = set(range(n))
    clusters = []
    
    while unassigned:
        # 步骤 1: 选择种子点（最孤立的点优先）
        if len(unassigned) == 1:
            seed = list(unassigned)[0]
        else:
            # 计算每个未分配点到其他未分配点的平均距离
            isolation_scores = []
            for i in unassigned:
                dists = [dist_matrix[i][j] for j in unassigned if j != i]
                avg_dist = np.mean(dists) if dists else 0
                isolation_scores.append((i, avg_dist))
            
            # 选择最孤立的点作为种子
            seed = max(isolation_scores, key=lambda x: x[1])[0]
        
        # 步骤 2: 贪心生长
        cluster = [seed]
        unassigned.remove(seed)
        
        while len(cluster) < max_points and unassigned:
            # 找到离当前簇最近的点
            best_point = None
            best_dist = float('inf')
            
            for i in unassigned:
                # 计算到簇内所有点的最小距离
                min_d = min(dist_matrix[i][j] for j in cluster)
                if min_d < best_dist:
                    best_dist = min_d
                    best_point = i
            
            if best_point is not None:
                cluster.append(best_point)
                unassigned.remove(best_point)
            else:
                break
        
        clusters.append(cluster)
    
    return clusters


# ============================================================
# 算法 2: K-Means 约束聚类（每组最多 6 点）
# ============================================================
def constrained_kmeans_clustering(points: List[dict],
                                   dist_matrix: np.ndarray,
                                   max_points: int = 6) -> List[List[int]]:
    """
    约束 K-Means 聚类
    
    核心思想：
    1. 计算需要的簇数量 K = 总点数 / 6
    2. 运行 K-Means
    3. 拆分超过 6 点的簇
    """
    from sklearn.cluster import KMeans
    
    n = len(points)
    coords = np.array([[p['lat'], p['lng']] for p in points])
    
    # 计算需要的簇数
    num_clusters = (n + max_points - 1) // max_points
    
    # K-Means 聚类
    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(coords)
    
    # 转换为簇列表
    clusters = []
    for k in range(num_clusters):
        cluster = [i for i in range(n) if labels[i] == k]
        if cluster:
            clusters.append(cluster)
    
    # 拆分超过 max_points 的簇
    final_clusters = []
    for cluster in clusters:
        if len(cluster) <= max_points:
            final_clusters.append(cluster)
        else:
            # 按空间位置拆分
            sub_clusters = split_spatial(points, cluster, dist_matrix, max_points)
            final_clusters.extend(sub_clusters)
    
    return final_clusters


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
# 算法 3: 层次聚类（每组最多 6 点）
# ============================================================
def hierarchical_clustering(points: List[dict],
                            dist_matrix: np.ndarray,
                            max_points: int = 6,
                            max_linkage_km: float = 5.0) -> List[List[int]]:
    """
    层次聚类
    
    核心思想：
    1. 自底向上合并
    2. 当簇大小达到 6 点时停止合并
    3. 当簇间距离超过阈值时停止合并
    """
    n = len(points)
    
    # 初始化：每个点一个簇
    clusters = [[i] for i in range(n)]
    
    # 反复合并最近的簇
    while len(clusters) > 1:
        # 找到最近的两个簇
        min_dist = float('inf')
        merge_i, merge_j = -1, -1
        
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                # 检查合并后的大小
                if len(clusters[i]) + len(clusters[j]) > max_points:
                    continue
                
                # 计算簇间最小距离
                d = min(dist_matrix[p1][p2] 
                       for p1 in clusters[i] 
                       for p2 in clusters[j])
                
                if d < min_dist:
                    min_dist = d
                    merge_i, merge_j = i, j
        
        # 如果最小距离超过阈值，停止合并
        if min_dist > max_linkage_km or merge_i < 0:
            break
        
        # 合并
        clusters[merge_i] = clusters[merge_i] + clusters[merge_j]
        clusters.pop(merge_j)
    
    return clusters


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
    
    # 检查点数约束
    metrics['violates_max_points'] = any(s > 6 for s in sizes)
    
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
    score -= metrics['avg_intra_max_km'] * 5  # 组内距离惩罚
    score += metrics.get('separation_ratio', 0) * 10  # 分离度奖励
    score -= metrics['size_std'] * 5  # 不均衡惩罚
    if metrics['violates_max_points']:
        score -= 50  # 违反约束严重惩罚
    metrics['efficiency_score'] = max(0, score)
    
    return metrics


# ============================================================
# 可视化
# ============================================================
def visualize(points: List[dict], clusters: List[List[int]], 
              outliers: list, output: str):
    """生成 HTML 可视化"""
    import folium
    
    # 中心
    normal_indices = [i for i in range(len(points)) if not any(i == o[0] for o in outliers)]
    center_lat = np.mean([points[i]['lat'] for i in normal_indices]) if normal_indices else np.mean([p['lat'] for p in points])
    center_lng = np.mean([points[i]['lng'] for i in normal_indices]) if normal_indices else np.mean([p['lng'] for p in points])
    
    m = folium.Map(location=[center_lat, center_lng], zoom_start=12)
    
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', 
              '#DDA0DD', '#F1948A', '#D2B4DE', '#A9DFBF', '#F9E79F']
    
    for idx, cluster in enumerate(clusters):
        color = colors[idx % len(colors)]
        cluster_points = [points[i] for i in cluster]
        
        # 计算边界
        lats = [p['lat'] for p in cluster_points]
        lngs = [p['lng'] for p in cluster_points]
        center = (np.mean(lats), np.mean(lngs))
        max_dist = max(haversine(center[0], center[1], p['lat'], p['lng']) for p in cluster_points) if cluster_points else 0
        
        # 绘制边界圆
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
        
        # 绘制点
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
    
    # 绘制异常点
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
    print("采样点分组算法对比 - 每组最多 6 点")
    print("=" * 70)
    
    # 加载数据
    print("\n[1] 加载数据...")
    points = load_data("地址修正表.xlsx")
    print(f"  唯一点位：{len(points)} 个")
    
    # 检测异常点
    print("\n[2] 检测异常点...")
    outliers, normal_indices = detect_outliers(points, threshold_km=15.0)
    print(f"  异常点：{len(outliers)} 个")
    for i, p, d in outliers:
        print(f"    - {p['name']} (距中心 {d:.1f}km)")
    
    # 只对正常点聚类
    print(f"\n[3] 对 {len(normal_indices)} 个正常点分组 (每组≤6 点)...")
    normal_points = [points[i] for i in normal_indices]
    normal_dist_matrix = build_distance_matrix(normal_points)
    
    # 运行 3 种算法
    algorithms = [
        ("贪心最近邻", lambda: greedy_neighbor_clustering(normal_points, normal_dist_matrix, max_points=6)),
        ("约束 K-Means", lambda: constrained_kmeans_clustering(normal_points, normal_dist_matrix, max_points=6)),
        ("层次聚类", lambda: hierarchical_clustering(normal_points, normal_dist_matrix, max_points=6, max_linkage_km=5.0)),
    ]
    
    results = []
    
    for name, func in algorithms:
        print(f"\n  运行：{name}")
        clusters_normal = func()
        
        # 映射回原始索引
        clusters = []
        for cluster in clusters_normal:
            original = [normal_indices[i] for i in cluster]
            clusters.append(original)
        
        # 评估
        metrics = evaluate(points, clusters, build_distance_matrix(points))
        metrics['name'] = name
        metrics['clusters'] = clusters
        results.append(metrics)
        
        print(f"    分组数：{metrics['num_clusters']}")
        print(f"    各组大小：{metrics['cluster_sizes']}")
        print(f"    违反≤6 约束：{metrics['violates_max_points']}")
        print(f"    组内最大 (平均): {metrics['avg_intra_max_km']:.2f}km")
        print(f"    分离度：{metrics.get('separation_ratio', 0):.2f}")
        print(f"    效率评分：{metrics['efficiency_score']:.1f}")
    
    # 排名
    results.sort(key=lambda x: x['efficiency_score'], reverse=True)
    
    print("\n" + "=" * 70)
    print("算法排名")
    print("=" * 70)
    
    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r['name']}")
        print(f"   效率评分：{r['efficiency_score']:.1f}")
        print(f"   分组数：{r['num_clusters']}")
        print(f"   各组大小：{r['cluster_sizes']}")
        print(f"   违反≤6 约束：{r['violates_max_points']}")
        print(f"   组内最大距离：{r['avg_intra_max_km']:.2f}km")
        print(f"   分离度：{r.get('separation_ratio', 0):.2f}")
    
    # 可视化
    print("\n[4] 生成可视化...")
    os.makedirs("output/max6_clustering", exist_ok=True)
    
    for r in results:
        safe_name = r['name'].replace(" ", "_")
        visualize(points, r['clusters'], outliers, 
                 f"output/max6_clustering/{safe_name}.html")
    
    # 保存结果
    with open("output/max6_clustering/comparison.json", 'w', encoding='utf-8') as f:
        json.dump([{
            'rank': i + 1,
            'name': r['name'],
            'efficiency_score': r['efficiency_score'],
            'num_clusters': r['num_clusters'],
            'cluster_sizes': r['cluster_sizes'],
            'violates_max_points': r['violates_max_points'],
            'avg_intra_max_km': r['avg_intra_max_km'],
            'separation_ratio': r.get('separation_ratio', 0)
        } for i, r in enumerate(results)], f, indent=2, ensure_ascii=False)
    
    print(f"\n结果保存到：output/max6_clustering/")
    print("=" * 70)


if __name__ == "__main__":
    main()
