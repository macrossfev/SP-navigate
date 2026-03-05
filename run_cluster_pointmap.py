#!/usr/bin/env python3
"""按距离聚类策略生成采样方案 — 点位图（无路径导航线）"""
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
config.use_amap_driving = False  # 不画驾车路线，只标点位
config.output_dir = "/root/projects/navigate/route_system/output/聚类方案_点位图"

print(config.summary())

# 加载数据
loader = DataLoader(config)
points = loader.load_all()

print(f"\n[距离矩阵] 构建 {len(points)}x{len(points)} ...")
dist_matrix = build_distance_matrix(points)

# 获取基地坐标
api = AmapAPI(config.amap_key)
base_coord = api.geocode(config.base_point)

# 运行聚类策略
strategy = ClusterStrategy(config, base_coord=base_coord)
result = strategy.plan(points, dist_matrix)
print(result.summary())

# 生成点位图
img_gen = ImageGenerator(config)
img_gen.generate_all(result)

# 生成报告
rpt_gen = ReportGenerator(config)
rpt_gen.generate(result, tag="聚类方案")
