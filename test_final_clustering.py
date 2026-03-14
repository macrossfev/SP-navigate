#!/usr/bin/env python3
"""
采样点分组算法 - 最终实用版本
针对长寿区特点：
1. 先排除异常远点
2. 按经度切片（东西向分布）
3. 组间边界清晰（按经度范围）
"""
import pandas as pd
import numpy as np
from typing import List, Dict
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


def detect_outliers(points: List[dict], threshold_km: float = 20.0) -> tuple:
    """检测异常点（基于到质心的距离）"""
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


def geographic_fence_clustering(points: List[dict], 
                                 target_groups: int = 5,
                                 max_points: int = 15) -> List[List[int]]:
    """
    地理围栏法 - 按经度切片
    
    针对长寿区沿长江东西向分布的特点
    组间边界 = 经度线，天然不重叠
    """
    n = len(points)
    
    # 按经度排序
    sorted_indices = sorted(range(n), key=lambda i: points[i]['lng'])
    
    # 计算每组点数
    points_per_group = max(1, (n + target_groups - 1) // target_groups)
    
    # 切片分组
    clusters = []
    for i in range(0, n, points_per_group):
        cluster = sorted_indices[i:i + points_per_group]
        if cluster:
            clusters.append(cluster)
    
    return clusters


def evaluate(points: List[dict], clusters: List[List[int]]) -> dict:
    """评估聚类质量"""
    n = len(points)
    
    # 基础统计
    sizes = [len(c) for c in clusters]
    metrics = {
        'num_clusters': len(clusters),
        'cluster_sizes': sizes,
        'avg_size': np.mean(sizes),
        'max_size': max(sizes),
        'min_size': min(sizes),
        'size_std': np.std(sizes),
    }
    
    # 组内紧凑度
    intra_dists = []
    for cluster in clusters:
        if len(cluster) < 2:
            intra_dists.append(0)
        else:
            max_d = 0
            for i in range(len(cluster)):
                for j in range(i+1, len(cluster)):
                    d = haversine(
                        points[cluster[i]]['lat'], points[cluster[i]]['lng'],
                        points[cluster[j]]['lat'], points[cluster[j]]['lng']
                    )
                    max_d = max(max_d, d)
            intra_dists.append(max_d)
    
    metrics['avg_intra_max_km'] = np.mean(intra_dists)
    metrics['max_intra_max_km'] = max(intra_dists)
    
    # 组间分离度
    inter_dists = []
    for i in range(len(clusters)):
        for j in range(i+1, len(clusters)):
            min_d = float('inf')
            for p1 in clusters[i]:
                for p2 in clusters[j]:
                    d = haversine(
                        points[p1]['lat'], points[p1]['lng'],
                        points[p2]['lat'], points[p2]['lng']
                    )
                    min_d = min(min_d, d)
            inter_dists.append(min_d)
    
    if inter_dists:
        metrics['avg_inter_min_km'] = np.mean(inter_dists)
        metrics['min_inter_min_km'] = min(inter_dists)
        metrics['separation_ratio'] = metrics['avg_inter_min_km'] / metrics['avg_intra_max_km'] if metrics['avg_intra_max_km'] > 0 else 0
    
    # 组间经度重叠检测
    bounds = []
    for cluster in clusters:
        lngs = [points[i]['lng'] for i in cluster]
        bounds.append((min(lngs), max(lngs)))
    
    has_overlap = False
    for i in range(len(bounds)):
        for j in range(i+1, len(bounds)):
            # 检查经度范围是否重叠
            if bounds[i][0] < bounds[j][1] and bounds[j][0] < bounds[i][1]:
                has_overlap = True
                break
    
    metrics['has_lng_overlap'] = has_overlap
    
    # 效率评分
    score = 100
    score -= metrics['avg_intra_max_km'] * 2  # 组内距离惩罚
    score += metrics.get('separation_ratio', 0) * 10  # 分离度奖励
    score -= metrics['size_std'] * 5  # 不均衡惩罚
    if has_overlap:
        score -= 20  # 重叠惩罚
    metrics['efficiency_score'] = max(0, score)
    
    return metrics


def visualize(points: List[dict], clusters: List[List[int]], outliers: list, output: str):
    """生成 HTML 可视化"""
    import folium
    
    # 中心（排除异常点）
    normal_points = [p for i, p in enumerate(points) if not any(i == o[0] for o in outliers)]
    center_lat = np.mean([p['lat'] for p in normal_points]) if normal_points else np.mean([p['lat'] for p in points])
    center_lng = np.mean([p['lng'] for p in normal_points]) if normal_points else np.mean([p['lng'] for p in points])
    
    m = folium.Map(location=[center_lat, center_lng], zoom_start=11)
    
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD']
    
    for idx, cluster in enumerate(clusters):
        color = colors[idx % len(colors)]
        cluster_points = [points[i] for i in cluster]
        
        # 计算边界
        lats = [p['lat'] for p in cluster_points]
        lngs = [p['lng'] for p in cluster_points]
        
        # 绘制多边形边界
        if len(cluster_points) >= 3:
            # 按经度排序形成简单多边形
            sorted_pts = sorted(cluster_points, key=lambda p: p['lng'])
            poly_lats = [sorted_pts[0]['lat']] + [p['lat'] for p in sorted_pts] + [sorted_pts[0]['lat']]
            poly_lngs = [sorted_pts[0]['lng']] + [p['lng'] for p in sorted_pts] + [sorted_pts[0]['lng']]
            
            # 简化为矩形边界
            folium.Rectangle(
                bounds=[[min(lats), min(lngs)], [max(lats), max(lngs)]],
                color=color,
                weight=2,
                fill=True,
                fillColor=color,
                fillOpacity=0.15,
                popup=f"组{idx+1}: {len(cluster)}点，经度{min(lngs):.3f}-{max(lngs):.3f}"
            ).add_to(m)
        
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
    
    # 绘制异常点（红色）
    for i, p, d in outliers:
        folium.CircleMarker(
            location=[p['lat'], p['lng']],
            radius=10,
            color='#FF0000',
            fill=True,
            fillColor='#FF0000',
            fillOpacity=0.8,
            popup=f"{p['name']}<br>异常点 (距中心{d:.1f}km)"
        ).add_to(m)
    
    m.save(output)
    print(f"  可视化：{output}")


def main():
    print("=" * 70)
    print("采样点分组算法 - 地理围栏法（最终版）")
    print("=" * 70)
    
    # 加载数据
    print("\n[1] 加载数据...")
    points = load_data("地址修正表.xlsx")
    print(f"  唯一点位：{len(points)} 个")
    
    # 检测异常点
    print("\n[2] 检测异常点...")
    outliers, normal_indices = detect_outliers(points, threshold_km=20.0)
    print(f"  异常点：{len(outliers)} 个")
    for i, p, d in outliers:
        print(f"    - {p['name']} (距中心 {d:.1f}km)")
    
    # 只对正常点聚类
    print(f"\n[3] 对 {len(normal_indices)} 个正常点分组...")
    normal_points = [points[i] for i in normal_indices]
    
    # 计算目标组数
    n = len(normal_indices)
    target_groups = max(4, n // 12)  # 每组约 12 点
    
    clusters_normal = geographic_fence_clustering(normal_points, target_groups, max_points=15)
    
    # 映射回原始索引
    clusters = []
    for cluster in clusters_normal:
        original = [normal_indices[i] for i in cluster]
        clusters.append(original)
    
    # 评估
    print("\n[4] 评估结果...")
    metrics = evaluate(points, clusters)
    
    print(f"""
分组结果:
  组数：{metrics['num_clusters']}
  各组大小：{metrics['cluster_sizes']}
  平均大小：{metrics['avg_size']:.1f}
  大小标准差：{metrics['size_std']:.2f}

组内紧凑度:
  组内最大距离 (平均): {metrics['avg_intra_max_km']:.2f} km
  组内最大距离 (最大): {metrics['max_intra_max_km']:.2f} km

组间分离度:
  组间最小距离 (平均): {metrics.get('avg_inter_min_km', 0):.2f} km
  分离度比率：{metrics.get('separation_ratio', 0):.2f}

边界清晰:
  经度重叠：{metrics['has_lng_overlap']}
  效率评分：{metrics['efficiency_score']:.1f}
""")
    
    # 打印每组详情
    print("[分组详情]")
    for i, cluster in enumerate(clusters):
        lngs = [points[j]['lng'] for j in cluster]
        lats = [points[j]['lat'] for j in cluster]
        names = [points[j]['name'][:12] for j in cluster[:5]]
        print(f"  组{i+1} ({len(cluster)}点): 经度{min(lngs):.3f}-{max(lngs):.3f}, 纬度{min(lats):.3f}-{max(lats):.3f}")
        print(f"         {', '.join(names)}{'...' if len(cluster)>5 else ''}")
    
    # 可视化
    print("\n[5] 生成可视化...")
    os.makedirs("output/final_clustering", exist_ok=True)
    visualize(points, clusters, outliers, "output/final_clustering/result.html")
    
    # 保存结果
    result = {
        'metrics': metrics,
        'outliers': [{'name': p['name'], 'lng': p['lng'], 'lat': p['lat'], 'distance_km': d} for i, p, d in outliers],
        'clusters': [
            {
                'cluster_id': i,
                'size': len(c),
                'lng_range': [min(points[j]['lng'] for j in c), max(points[j]['lng'] for j in c)],
                'lat_range': [min(points[j]['lat'] for j in c), max(points[j]['lat'] for j in c)],
                'points': [{'name': points[j]['name'], 'lng': points[j]['lng'], 'lat': points[j]['lat']} for j in c]
            }
            for i, c in enumerate(clusters)
        ]
    }
    
    with open("output/final_clustering/result.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n结果保存到：output/final_clustering/")
    print("=" * 70)


if __name__ == "__main__":
    main()
