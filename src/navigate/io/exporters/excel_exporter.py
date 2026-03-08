"""Excel result exporter with configurable columns."""
from __future__ import annotations

import os
from typing import Any, List, TYPE_CHECKING

import pandas as pd

from .base import BaseExporter

if TYPE_CHECKING:
    from navigate.core.models import PlanResult, Point
    from navigate.core.config import NavigateConfig, ExportColumnDef, ExportFormatConfig


def _resolve_field(point: "Point", day: int, index: int, source: str) -> Any:
    """Resolve a field value from a point using dot notation."""
    if source == "day":
        return day
    if source == "index":
        return index
    if source == "name":
        return point.name
    if source == "id":
        return point.id
    if source == "lng":
        return point.lng
    if source == "lat":
        return point.lat
    if source == "coordinates":
        return f"{point.lng},{point.lat}"
    if source.startswith("metadata."):
        key = source[len("metadata."):]
        return point.metadata.get(key, "")
    return ""


class ExcelExporter(BaseExporter):
    """Export plan results as Excel spreadsheet."""

    def export(self, result: "PlanResult", output_dir: str, **kwargs) -> str:
        os.makedirs(output_dir, exist_ok=True)
        tag = kwargs.get("tag", "")
        suffix = f"_{tag}" if tag else ""
        fmt_config = kwargs.get("format_config")
        path = os.path.join(output_dir, f"plan_summary{suffix}.xlsx")

        if fmt_config and fmt_config.columns:
            rows = self._build_rows_from_config(result, fmt_config.columns)
        else:
            rows = self._build_default_rows(result)

        pd.DataFrame(rows).to_excel(path, index=False, engine="openpyxl")
        print(f"[Export] Excel: {path}")
        return path

    def _build_rows_from_config(self, result: "PlanResult",
                                 columns: List["ExportColumnDef"]) -> list:
        rows = []
        for d in result.days:
            for idx, pt in enumerate(d.points):
                row = {}
                for col in columns:
                    row[col.header] = _resolve_field(pt, d.day, idx + 1, col.source)
                # Add daily totals on first row
                if idx == 0:
                    row["_distance_km"] = d.drive_distance_km
                    row["_total_hours"] = d.total_time_hours
                rows.append(row)
        return rows

    def _build_default_rows(self, result: "PlanResult") -> list:
        rows = []
        for d in result.days:
            for idx, pt in enumerate(d.points):
                row = {
                    "Day": d.day,
                    "Index": idx + 1,
                    "Name": pt.name,
                    "Lng": pt.lng,
                    "Lat": pt.lat,
                }
                row.update(pt.metadata)
                if idx == 0:
                    row["Distance(km)"] = d.drive_distance_km
                    row["Total(h)"] = d.total_time_hours
                rows.append(row)
        return rows
