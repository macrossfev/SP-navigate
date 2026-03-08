"""JSON result exporter."""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from .base import BaseExporter

if TYPE_CHECKING:
    from navigate.core.models import PlanResult
    from navigate.core.config import NavigateConfig


class JsonExporter(BaseExporter):
    """Export plan results as JSON."""

    def export(self, result: "PlanResult", output_dir: str, **kwargs) -> str:
        os.makedirs(output_dir, exist_ok=True)
        tag = kwargs.get("tag", "")
        suffix = f"_{tag}" if tag else ""
        path = os.path.join(output_dir, f"plan_result{suffix}.json")

        data = {
            "strategy": result.strategy_name,
            "total_points": result.total_points,
            "total_days": result.total_days,
            "total_distance_km": round(result.total_distance_km, 1),
            "total_hours": round(result.total_hours, 1),
            "days": [],
        }
        for d in result.days:
            data["days"].append({
                "day": d.day,
                "point_count": d.point_count,
                "points": [p.name for p in d.points],
                "drive_distance_km": d.drive_distance_km,
                "drive_time_min": d.drive_time_min,
                "stop_time_min": d.stop_time_min,
                "total_time_hours": d.total_time_hours,
            })
        if result.unassigned:
            data["unassigned"] = [
                {"name": p.name, "nearest_km": round(dist, 1)}
                for p, dist in result.unassigned
            ]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[Export] JSON: {path}")
        return path
