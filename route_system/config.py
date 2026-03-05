"""
参数配置体系
所有可调参数集中管理，支持 JSON 文件加载和命令行覆盖
"""
import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class RouteConfig:
    """路径规划参数体系"""

    # ====== 基本设置 ======
    strategy: str = "tsp"               # 策略: "tsp"(全局TSP优化) / "cluster"(最近邻聚类)
    base_point: str = "中共重庆市自来水有限公司委员会"  # 起止基地地址
    amap_key: str = "b6410cb1a118bad10e6d1161d6e896f7"

    # ====== 时间约束 ======
    max_daily_hours: float = 4.0        # 每天最大工作时长（小时）
    stop_time_per_point_min: int = 15   # 每个采样点停留时间（分钟）
    roundtrip_overhead_min: int = 155   # 往返基地固定开销（分钟），如从南岸到长寿区
    break_time_min: int = 0             # 每天午休/休息时间（分钟）
    start_time: str = "08:00"           # 每日出发时间（用于报告展示）
    buffer_factor: float = 1.0          # 时间缓冲系数（1.2=预留20%余量）

    # ====== 点位约束 ======
    max_daily_points: int = 5           # 每天最多采样点数
    min_daily_points: int = 1           # 每天最少采样点数（避免过少）

    # ====== 距离约束 ======
    max_daily_distance_km: float = 0    # 每天最大行驶距离（km），0=不限
    avg_speed_kmh: float = 35.0         # 城区平均车速（km/h），用于估算

    # ====== 路线优化 ======
    tsp_2opt_iterations: int = 1000     # 2-opt优化最大迭代次数
    use_amap_driving: bool = True       # 是否调用高德API获取实际驾车路线
    amap_request_delay: float = 0.5     # 高德API请求间隔（秒）

    # ====== 聚类策略专用 ======
    cluster_seed_method: str = "nearest_to_base"  # 聚类种子选择: "nearest_to_base" / "centroid" / "geographic_scan"
    cluster_sort_by: str = "base_distance"         # 天的排序: "base_distance" / "cluster_center"
    outlier_threshold_km: float = 5.0              # 离群点阈值: 离最近邻距离超过此值视为离群点, 0=不过滤

    # ====== 输出设置 ======
    output_dir: str = "/root/projects/navigate/route_system/output"
    generate_images: bool = True        # 是否生成导航图片
    generate_word: bool = True          # 是否生成Word报告
    generate_excel: bool = True         # 是否生成Excel总表
    image_width: int = 1200             # 导航图宽度
    image_height: int = 800             # 导航图高度
    include_base_in_image: bool = False # 图片中是否包含基地往返路线

    # ====== 数据文件路径 ======
    address_file: str = "/root/projects/navigate/最终地址列表.xlsx"
    survey_file: str = "/root/projects/navigate/长寿区二次供水现状摸排统计2024.10.16(3).xls"
    fix_address_file: str = "/root/projects/navigate/地址修正表.xlsx"

    @property
    def max_daily_seconds(self) -> float:
        return self.max_daily_hours * 3600

    @property
    def stop_time_seconds(self) -> float:
        return self.stop_time_per_point_min * 60

    @property
    def roundtrip_overhead_seconds(self) -> float:
        return self.roundtrip_overhead_min * 60

    @property
    def available_field_seconds(self) -> float:
        """每天在现场可用的时间（扣除往返开销和��息）"""
        total = self.max_daily_seconds
        total -= self.roundtrip_overhead_seconds
        total -= self.break_time_min * 60
        return total / self.buffer_factor

    def to_dict(self) -> dict:
        d = asdict(self)
        d["_computed"] = {
            "max_daily_seconds": self.max_daily_seconds,
            "available_field_seconds": round(self.available_field_seconds),
            "available_field_minutes": round(self.available_field_seconds / 60, 1),
        }
        return d

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "RouteConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.pop("_computed", None)
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def summary(self) -> str:
        lines = [
            "=" * 55,
            " 路径规划参数配置",
            "=" * 55,
            f" 策略:          {self.strategy}",
            f" 基地:          {self.base_point}",
            f" 每日最大时长:  {self.max_daily_hours} 小时",
            f" 每点停留:      {self.stop_time_per_point_min} 分钟",
            f" 往返开销:      {self.roundtrip_overhead_min} 分钟",
            f" 休息时间:      {self.break_time_min} 分钟",
            f" 缓冲系数:      {self.buffer_factor}",
            f" → 现场可用:    {self.available_field_seconds/60:.0f} 分钟",
            f" 每日最多点位:  {self.max_daily_points}",
            f" 每日最大距离:  {'不限' if self.max_daily_distance_km == 0 else f'{self.max_daily_distance_km} km'}",
            f" 平均车速:      {self.avg_speed_kmh} km/h",
            f" 2-opt迭代:     {self.tsp_2opt_iterations}",
            "=" * 55,
        ]
        return "\n".join(lines)
