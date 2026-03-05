"""
路径规划策略基类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List
from ..config import RouteConfig
from ..data_loader import SamplingPoint


@dataclass
class DayPlan:
    """单日计划"""
    day: int
    point_indices: List[int]         # 在points列表中的索引
    points: List[SamplingPoint] = field(default_factory=list)
    # 以下为实际路线计算后填入
    drive_distance_km: float = 0
    drive_time_min: float = 0
    stop_time_min: float = 0
    total_time_hours: float = 0
    route_polyline: list = field(default_factory=list)  # [(lat,lng),...]


@dataclass
class PlanResult:
    """规划结果"""
    strategy_name: str
    config: RouteConfig
    days: List[DayPlan]
    points: List[SamplingPoint]
    outliers: list = field(default_factory=list)  # [(SamplingPoint, nn_dist_km), ...]

    @property
    def total_days(self) -> int:
        return len(self.days)

    @property
    def total_points(self) -> int:
        return sum(len(d.point_indices) for d in self.days)

    @property
    def total_distance_km(self) -> float:
        return sum(d.drive_distance_km for d in self.days)

    @property
    def total_hours(self) -> float:
        return sum(d.total_time_hours for d in self.days)

    @property
    def max_day_points(self) -> int:
        return max(len(d.point_indices) for d in self.days) if self.days else 0

    @property
    def avg_day_distance(self) -> float:
        return self.total_distance_km / self.total_days if self.total_days else 0

    def summary(self) -> str:
        lines = [
            f"\n{'=' * 55}",
            f" 规划结果 — 策略: {self.strategy_name}",
            f"{'=' * 55}",
            f" 总点位: {self.total_points}",
            f" 总天数: {self.total_days}",
            f" 总距离: {self.total_distance_km:.1f} km",
            f" 总时间: {self.total_hours:.1f} 小时",
            f" 平均每天距离: {self.avg_day_distance:.1f} km",
            f"{'=' * 55}",
        ]
        for d in self.days:
            flag = ""
            if d.total_time_hours > self.config.max_daily_hours:
                flag = " ⚠超时"
            lines.append(
                f" 第{d.day:>2d}天: {len(d.point_indices)}个点 | "
                f"{d.drive_distance_km:>6.1f}km | "
                f"驾车{d.drive_time_min:>5.0f}min | "
                f"总{d.total_time_hours:.1f}h{flag}"
            )
        lines.append(f"{'=' * 55}")
        return "\n".join(lines)


class BaseStrategy(ABC):
    """策略基类"""

    name: str = "base"

    def __init__(self, config: RouteConfig):
        self.config = config

    @abstractmethod
    def plan(self, points: List[SamplingPoint],
             dist_matrix: List[List[float]]) -> PlanResult:
        """执行路径规划，返回结果"""
        ...

    def _estimate_drive_time_s(self, dist_km: float) -> float:
        """根据平均车速估算驾车时间（秒）"""
        return dist_km / self.config.avg_speed_kmh * 3600
