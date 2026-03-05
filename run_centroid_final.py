#!/usr/bin/env python3
"""最终方案: 质心聚类 + 离群点排除 + 点位图"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from route_system.config import RouteConfig
from route_system.data_loader import DataLoader, build_distance_matrix
from route_system.amap_api import AmapAPI
from route_system.strategies.cluster import ClusterStrategy
from route_system.image_gen import ImageGenerator
from route_system.report_gen import ReportGenerator

config = RouteConfig()
config.strategy = "cluster"
config.cluster_seed_method = "centroid"
config.outlier_threshold_km = 5.0
config.use_amap_driving = False  # 点位图，不画路线
config.output_dir = "/root/projects/navigate/route_system/output/最终方案_质心聚类"

print(config.summary())

loader = DataLoader(config)
points = loader.load_all()
dist_matrix = build_distance_matrix(points)

api = AmapAPI(config.amap_key)
base_coord = api.geocode(config.base_point)

strategy = ClusterStrategy(config, base_coord=base_coord)
result = strategy.plan(points, dist_matrix)
print(result.summary())

if result.outliers:
    print(f"\n离群点 ({len(result.outliers)} 个):")
    for sp, nn in result.outliers:
        print(f"  - {sp.short_name} (最近邻 {nn:.1f}km)")

img_gen = ImageGenerator(config)
img_gen.generate_all(result)

rpt_gen = ReportGenerator(config)
rpt_gen.generate(result, tag="最终方案")
