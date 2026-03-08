"""
YAML-based configuration system.
Supports environment variable substitution and CLI overrides.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def _resolve_env_vars(value: Any) -> Any:
    """Replace ${ENV_VAR} patterns with environment variable values."""
    if isinstance(value, str):
        def replacer(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return re.sub(r'\$\{(\w+)\}', replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


@dataclass
class BasePointConfig:
    name: str = ""
    lng: Optional[float] = None
    lat: Optional[float] = None


@dataclass
class ConstraintsConfig:
    max_daily_hours: float = 8.0
    max_daily_points: int = 10
    min_daily_points: int = 1
    stop_time_per_point_min: int = 15
    roundtrip_overhead_min: int = 0
    break_time_min: int = 0
    buffer_factor: float = 1.0
    max_daily_distance_km: float = 0  # 0 = unlimited
    
    # Overnight trip settings
    overnight_threshold_km: float = 0.0  # Distance threshold for overnight trips
    overnight_hotel_radius_km: float = 3.0  # Hotel search radius
    single_day_max_hours: float = 0.0  # Max hours for single-day trips (0 = use max_daily_hours)

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
        """Time available on-site per day (excludes commute and breaks)."""
        total = self.max_daily_seconds
        total -= self.roundtrip_overhead_seconds
        total -= self.break_time_min * 60
        return total / self.buffer_factor


@dataclass
class StrategyConfig:
    name: str = "tsp"
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DistanceConfig:
    provider: str = "haversine"
    avg_speed_kmh: float = 35.0
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ColumnMapping:
    """Maps source columns to Point fields."""
    id: Optional[str] = None
    name: str = "name"
    lng: Optional[str] = None
    lat: Optional[str] = None
    coordinates: Optional[str] = None  # combined "lng,lat" column
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class DataSourceConfig:
    file: str = ""
    format: str = "excel"  # excel, csv, json
    column_mapping: Optional[ColumnMapping] = None
    skip_rows: int = 0
    match_key: Optional[str] = None
    match_mode: str = "exact"  # exact, fuzzy
    strip_prefix: str = ""


@dataclass
class DataConfig:
    points: Optional[DataSourceConfig] = None
    survey: Optional[DataSourceConfig] = None
    corrections: Optional[DataSourceConfig] = None


@dataclass
class ExportColumnDef:
    header: str = ""
    source: str = ""  # "name", "lng", "lat", "day", "index", "metadata.xxx"


@dataclass
class ExportFormatConfig:
    type: str = "json"  # json, excel, docx, map
    columns: List[ExportColumnDef] = field(default_factory=list)
    title: str = ""
    include_maps: bool = True
    detail_fields: List[ExportColumnDef] = field(default_factory=list)
    format: str = "html"  # for map: html, png
    image_width: int = 1200
    image_height: int = 800


@dataclass
class ExportConfig:
    output_dir: str = "./output"
    formats: List[ExportFormatConfig] = field(default_factory=list)


@dataclass
class NavigateConfig:
    """Top-level configuration."""
    base_point: BasePointConfig = field(default_factory=BasePointConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    constraints: ConstraintsConfig = field(default_factory=ConstraintsConfig)
    distance: DistanceConfig = field(default_factory=DistanceConfig)
    data: DataConfig = field(default_factory=DataConfig)
    export: ExportConfig = field(default_factory=ExportConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "NavigateConfig":
        """Load configuration from YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw = _resolve_env_vars(raw)
        return cls._from_dict(raw, base_dir=str(Path(path).parent))

    @classmethod
    def _from_dict(cls, data: dict, base_dir: str = ".") -> "NavigateConfig":
        config = cls()

        # base_point
        if "base_point" in data:
            bp = data["base_point"]
            config.base_point = BasePointConfig(
                name=bp.get("name", ""),
                lng=bp.get("lng"),
                lat=bp.get("lat"),
            )

        # strategy
        if "strategy" in data:
            s = data["strategy"]
            if isinstance(s, str):
                config.strategy = StrategyConfig(name=s)
            elif isinstance(s, dict):
                config.strategy = StrategyConfig(
                    name=s.get("name", "tsp"),
                    options=s.get("options", {}),
                )

        if "strategy_options" in data:
            config.strategy.options.update(data["strategy_options"])

        # constraints
        if "constraints" in data:
            c = data["constraints"]
            config.constraints = ConstraintsConfig(**{
                k: v for k, v in c.items()
                if k in ConstraintsConfig.__dataclass_fields__
            })

        # distance
        if "distance" in data:
            d = data["distance"]
            config.distance = DistanceConfig(
                provider=d.get("provider", "haversine"),
                avg_speed_kmh=d.get("avg_speed_kmh", 35.0),
                options={k: v for k, v in d.items()
                         if k not in ("provider", "avg_speed_kmh")},
            )

        # data
        if "data" in data:
            dd = data["data"]
            config.data = DataConfig()
            for section in ("points", "survey", "corrections"):
                if section in dd:
                    src = dd[section]
                    file_path = src.get("file", "")
                    if file_path and not os.path.isabs(file_path):
                        file_path = os.path.join(base_dir, file_path)
                    cm = None
                    if "column_mapping" in src:
                        cm_raw = src["column_mapping"]
                        meta = cm_raw.pop("metadata", {})
                        cm = ColumnMapping(
                            **{k: v for k, v in cm_raw.items()
                               if k in ColumnMapping.__dataclass_fields__ and k != "metadata"}
                        )
                        cm.metadata = meta
                    ds = DataSourceConfig(
                        file=file_path,
                        format=src.get("format", "excel"),
                        column_mapping=cm,
                        skip_rows=src.get("skip_rows", 0),
                        match_key=src.get("match_key"),
                        match_mode=src.get("match_mode", "exact"),
                        strip_prefix=src.get("strip_prefix", ""),
                    )
                    setattr(config.data, section, ds)

        # export
        if "export" in data:
            ex = data["export"]
            output_dir = ex.get("output_dir", "./output")
            if not os.path.isabs(output_dir):
                output_dir = os.path.join(base_dir, output_dir)
            formats = []
            for fmt in ex.get("formats", []):
                columns = [ExportColumnDef(**c) for c in fmt.get("columns", [])]
                detail_fields = [ExportColumnDef(**c) for c in fmt.get("detail_fields", [])]
                formats.append(ExportFormatConfig(
                    type=fmt.get("type", "json"),
                    columns=columns,
                    title=fmt.get("title", ""),
                    include_maps=fmt.get("include_maps", True),
                    detail_fields=detail_fields,
                    format=fmt.get("format", "html"),
                    image_width=fmt.get("image_width", 1200),
                    image_height=fmt.get("image_height", 800),
                ))
            config.export = ExportConfig(output_dir=output_dir, formats=formats)

        return config

    def apply_overrides(self, overrides: Dict[str, Any]):
        """Apply dot-notation overrides like 'constraints.max_daily_points=6'."""
        for key, value in overrides.items():
            parts = key.split(".")
            obj = self
            for part in parts[:-1]:
                obj = getattr(obj, part)
            field_name = parts[-1]
            current = getattr(obj, field_name)
            if isinstance(current, int):
                value = int(value)
            elif isinstance(current, float):
                value = float(value)
            setattr(obj, field_name, value)

    def summary(self) -> str:
        c = self.constraints
        lines = [
            "=" * 55,
            " Route Planning Configuration",
            "=" * 55,
            f" Strategy:        {self.strategy.name}",
            f" Base point:      {self.base_point.name}",
            f" Max daily hours: {c.max_daily_hours}",
            f" Stop per point:  {c.stop_time_per_point_min} min",
            f" Roundtrip:       {c.roundtrip_overhead_min} min",
            f" Buffer factor:   {c.buffer_factor}",
            f" -> Field time:   {c.available_field_seconds / 60:.0f} min",
            f" Max daily pts:   {c.max_daily_points}",
            f" Max daily dist:  {'unlimited' if c.max_daily_distance_km == 0 else f'{c.max_daily_distance_km} km'}",
            f" Avg speed:       {self.distance.avg_speed_kmh} km/h",
            f" Distance:        {self.distance.provider}",
            "=" * 55,
        ]
        return "\n".join(lines)
