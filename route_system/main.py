#!/usr/bin/env python3
"""
采样路径自动分配系统 — 主入口
用法:
  python -m route_system.main                     # 使用默认参数(TSP策略)
  python -m route_system.main --strategy cluster   # 使用聚类策略
  python -m route_system.main --config config.json # 从配置文件加载
  python -m route_system.main --compare            # 两种策略对比
"""
import argparse
import json
import os
import sys

# 确保可以从项目根目录导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from route_system.config import RouteConfig
from route_system.data_loader import DataLoader, build_distance_matrix
from route_system.amap_api import AmapAPI
from route_system.strategies import STRATEGIES
from route_system.strategies.cluster import ClusterStrategy
from route_system.image_gen import ImageGenerator
from route_system.report_gen import ReportGenerator


def run_strategy(config: RouteConfig, points, dist_matrix, tag=""):
    """运行单个策略"""
    strategy_cls = STRATEGIES[config.strategy]
    if config.strategy == "cluster":
        api = AmapAPI(config.amap_key)
        base_coord = api.geocode(config.base_point)
        strategy = strategy_cls(config, base_coord=base_coord)
    else:
        strategy = strategy_cls(config)

    result = strategy.plan(points, dist_matrix)
    print(result.summary())

    # 设置输出目录
    if tag:
        config.output_dir = config.output_dir.rstrip("/") + f"/{tag}"
    os.makedirs(config.output_dir, exist_ok=True)

    # 保存配置
    config.save(os.path.join(config.output_dir, "config.json"))

    # 保存规划结果JSON
    result_json = {
        "strategy": result.strategy_name,
        "total_points": result.total_points,
        "total_days": result.total_days,
        "total_distance_km": round(result.total_distance_km, 1),
        "total_hours": round(result.total_hours, 1),
        "days": [],
    }
    for d in result.days:
        result_json["days"].append({
            "day": d.day,
            "point_count": len(d.point_indices),
            "points": [p.name for p in d.points],
            "drive_distance_km": d.drive_distance_km,
            "drive_time_min": d.drive_time_min,
            "stop_time_min": d.stop_time_min,
            "total_time_hours": d.total_time_hours,
        })
    with open(os.path.join(config.output_dir, "plan_result.json"), "w", encoding="utf-8") as f:
        json.dump(result_json, f, ensure_ascii=False, indent=2)

    # 生成图片
    if config.generate_images:
        img_gen = ImageGenerator(config)
        img_gen.generate_all(result)

    # 生成报告
    if config.generate_word or config.generate_excel:
        rpt_gen = ReportGenerator(config)
        rpt_gen.generate(result, tag=tag)

    return result


def run_compare(base_config: RouteConfig, points, dist_matrix):
    """对比两种策略"""
    print("\n" + "=" * 60)
    print(" 两种策略对比运行")
    print("=" * 60)

    # 策略A: TSP
    config_a = RouteConfig(**{k: v for k, v in base_config.__dict__.items()})
    config_a.strategy = "tsp"
    config_a.output_dir = base_config.output_dir.rstrip("/")
    result_a = run_strategy(config_a, points, dist_matrix, tag="策略A_TSP")

    # 策略B: 聚类
    config_b = RouteConfig(**{k: v for k, v in base_config.__dict__.items()})
    config_b.strategy = "cluster"
    config_b.output_dir = base_config.output_dir.rstrip("/")
    result_b = run_strategy(config_b, points, dist_matrix, tag="策略B_聚类")

    # 对比报告
    print("\n" + "=" * 60)
    print(" 策略对比结果")
    print("=" * 60)
    print(f"{'指标':<20} {'策略A(TSP)':<18} {'策略B(聚类)':<18} {'差异'}")
    print("-" * 60)

    metrics = [
        ("总天数", result_a.total_days, result_b.total_days, "天"),
        ("总点位", result_a.total_points, result_b.total_points, "个"),
        ("点间总距离(km)", result_a.total_distance_km, result_b.total_distance_km, "km"),
        ("总工时(h)", result_a.total_hours, result_b.total_hours, "h"),
        ("日均距离(km)", result_a.avg_day_distance, result_b.avg_day_distance, "km"),
        ("单日最多点", result_a.max_day_points, result_b.max_day_points, "个"),
    ]
    for name, va, vb, unit in metrics:
        diff = vb - va
        sign = "+" if diff > 0 else ""
        print(f"{name:<20} {va:<18.1f} {vb:<18.1f} {sign}{diff:.1f}{unit}")

    # 超时天数
    over_a = sum(1 for d in result_a.days if d.total_time_hours > base_config.max_daily_hours)
    over_b = sum(1 for d in result_b.days if d.total_time_hours > base_config.max_daily_hours)
    print(f"{'超时天数':<20} {over_a:<18} {over_b:<18}")
    print("=" * 60)

    # 保存对比JSON
    compare_json = {
        "策略A_TSP": {
            "total_days": result_a.total_days,
            "total_distance_km": round(result_a.total_distance_km, 1),
            "total_hours": round(result_a.total_hours, 1),
            "avg_day_distance_km": round(result_a.avg_day_distance, 1),
            "overtime_days": over_a,
        },
        "策略B_聚类": {
            "total_days": result_b.total_days,
            "total_distance_km": round(result_b.total_distance_km, 1),
            "total_hours": round(result_b.total_hours, 1),
            "avg_day_distance_km": round(result_b.avg_day_distance, 1),
            "overtime_days": over_b,
        },
    }
    with open(os.path.join(base_config.output_dir, "compare_result.json"), "w", encoding="utf-8") as f:
        json.dump(compare_json, f, ensure_ascii=False, indent=2)
    print(f"\n对比结果已保存: {base_config.output_dir}/compare_result.json")

    return result_a, result_b


def main():
    parser = argparse.ArgumentParser(description="采样路径自动分配系统")
    parser.add_argument("--config", help="配置文件路径(JSON)")
    parser.add_argument("--strategy", choices=["tsp", "cluster"], help="策略")
    parser.add_argument("--compare", action="store_true", help="对比两种策略")
    parser.add_argument("--max-daily-hours", type=float, help="每天最大时长")
    parser.add_argument("--max-daily-points", type=int, help="每天最多点位")
    parser.add_argument("--stop-time", type=int, help="每点停留(分钟)")
    parser.add_argument("--roundtrip", type=int, help="往返开销(分钟)")
    parser.add_argument("--buffer", type=float, help="缓冲系数")
    parser.add_argument("--avg-speed", type=float, help="平均车速(km/h)")
    parser.add_argument("--max-distance", type=float, help="每日最大距离(km)")
    parser.add_argument("--no-images", action="store_true", help="不生成图片")
    parser.add_argument("--no-word", action="store_true", help="不生成Word")
    parser.add_argument("--output", help="输出目录")
    args = parser.parse_args()

    # 加载配置
    if args.config:
        config = RouteConfig.load(args.config)
    else:
        config = RouteConfig()

    # 命令行参数覆盖
    if args.strategy:
        config.strategy = args.strategy
    if args.max_daily_hours:
        config.max_daily_hours = args.max_daily_hours
    if args.max_daily_points:
        config.max_daily_points = args.max_daily_points
    if args.stop_time:
        config.stop_time_per_point_min = args.stop_time
    if args.roundtrip:
        config.roundtrip_overhead_min = args.roundtrip
    if args.buffer:
        config.buffer_factor = args.buffer
    if args.avg_speed:
        config.avg_speed_kmh = args.avg_speed
    if args.max_distance:
        config.max_daily_distance_km = args.max_distance
    if args.no_images:
        config.generate_images = False
    if args.no_word:
        config.generate_word = False
    if args.output:
        config.output_dir = args.output

    print(config.summary())

    # 加载数据
    loader = DataLoader(config)
    points = loader.load_all()

    print(f"\n[距离矩阵] 构建 {len(points)}x{len(points)} ...")
    dist_matrix = build_distance_matrix(points)
    print("  完成")

    if args.compare:
        run_compare(config, points, dist_matrix)
    else:
        run_strategy(config, points, dist_matrix)


if __name__ == "__main__":
    main()
