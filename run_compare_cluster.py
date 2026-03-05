#!/usr/bin/env python3
"""对比两种聚类模式: chain(旧) vs centroid(新)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from route_system.config import RouteConfig
from route_system.data_loader import DataLoader, build_distance_matrix
from route_system.amap_api import AmapAPI
from route_system.strategies.cluster import ClusterStrategy

config = RouteConfig()
loader = DataLoader(config)
points = loader.load_all()
dist_matrix = build_distance_matrix(points)
api = AmapAPI(config.amap_key)
base_coord = api.geocode(config.base_point)

# 旧方案: chain
print("\n" + "=" * 55)
print(" 旧方案: 链式贪心 (chain)")
print("=" * 55)
config_old = RouteConfig()
config_old.cluster_seed_method = "nearest_to_base"
s_old = ClusterStrategy(config_old, base_coord=base_coord)
r_old = s_old.plan(points, dist_matrix)

# 新方案: centroid
print("\n" + "=" * 55)
print(" 新方案: 最远点种子 + 质心聚拢 (centroid)")
print("=" * 55)
config_new = RouteConfig()
config_new.cluster_seed_method = "centroid"
s_new = ClusterStrategy(config_new, base_coord=base_coord)
r_new = s_new.plan(points, dist_matrix)

# 对比
print("\n" + "=" * 55)
print(" 聚类方案对比")
print("=" * 55)
print(f"{'指标':<20} {'旧(chain)':<15} {'新(centroid)':<15} {'差异'}")
print("-" * 55)
metrics = [
    ("总天数", r_old.total_days, r_new.total_days, "天"),
    ("点间总距离(km)", r_old.total_distance_km, r_new.total_distance_km, "km"),
    ("总工时(h)", r_old.total_hours, r_new.total_hours, "h"),
    ("日均距离(km)", r_old.avg_day_distance, r_new.avg_day_distance, "km"),
]
for name, a, b, unit in metrics:
    diff = b - a
    sign = "+" if diff > 0 else ""
    print(f"{name:<20} {a:<15.1f} {b:<15.1f} {sign}{diff:.1f}{unit}")

# 逐天对比最大跨度
print(f"\n{'天':<6} {'旧-距离':<10} {'旧-跨度':<10} {'新-距离':<10} {'新-跨度':<10}")
print("-" * 46)
for d_old, d_new in zip(r_old.days, r_new.days):
    g_old = d_old.point_indices
    g_new = d_new.point_indices
    sp_old = max((dist_matrix[g_old[i]][g_old[j]]
                  for i in range(len(g_old)) for j in range(i+1, len(g_old))), default=0)
    sp_new = max((dist_matrix[g_new[i]][g_new[j]]
                  for i in range(len(g_new)) for j in range(i+1, len(g_new))), default=0)
    print(f"第{d_old.day:<3d}天 {d_old.drive_distance_km:<10.1f} {sp_old:<10.2f} "
          f"{d_new.drive_distance_km:<10.1f} {sp_new:<10.2f}")
# 处理天数不等的情况
for d in r_new.days[len(r_old.days):]:
    g = d.point_indices
    sp = max((dist_matrix[g[i]][g[j]]
              for i in range(len(g)) for j in range(i+1, len(g))), default=0)
    print(f"第{d.day:<3d}天 {'-':<10} {'-':<10} {d.drive_distance_km:<10.1f} {sp:<10.2f}")
print("=" * 55)
