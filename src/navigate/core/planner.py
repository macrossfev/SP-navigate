"""
Main orchestrator: load config -> load data -> build matrix -> run strategy -> export.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, TYPE_CHECKING

from .config import NavigateConfig
from .models import DistanceMatrix, Point, PlanResult

if TYPE_CHECKING:
    pass


class Planner:
    """Main entry point for route planning."""

    def __init__(self, config: NavigateConfig):
        self.config = config

    def run(self, tag: str = "") -> PlanResult:
        """Execute the full planning pipeline."""
        print(self.config.summary())

        # 1) Load data
        points = self._load_points()
        print(f"\n[Data] {len(points)} points loaded")

        # 2) Build distance matrix
        print(f"[Matrix] Building {len(points)}x{len(points)}...")
        dist_matrix = self._build_matrix(points)
        print("  Done")

        # 3) Run strategy
        result = self._run_strategy(points, dist_matrix)
        print(result.summary())

        # 4) Export results
        self._export(result, tag)

        return result

    def compare(self, strategies: Optional[List[str]] = None) -> Dict[str, PlanResult]:
        """Run multiple strategies and compare results."""
        if strategies is None:
            strategies = ["tsp", "cluster"]

        print(self.config.summary())

        # Load data once
        points = self._load_points()
        print(f"\n[Data] {len(points)} points loaded")

        print(f"[Matrix] Building {len(points)}x{len(points)}...")
        dist_matrix = self._build_matrix(points)
        print("  Done")

        results = {}
        for strategy_name in strategies:
            self.config.strategy.name = strategy_name
            result = self._run_strategy(points, dist_matrix)
            print(result.summary())
            self._export(result, tag=strategy_name)
            results[strategy_name] = result

        # Print comparison
        self._print_comparison(results)

        # Save comparison JSON
        output_dir = self.config.export.output_dir
        os.makedirs(output_dir, exist_ok=True)
        compare_data = {}
        for name, r in results.items():
            over = sum(1 for d in r.days
                       if d.total_time_hours > self.config.constraints.max_daily_hours)
            compare_data[name] = {
                "total_days": r.total_days,
                "total_distance_km": round(r.total_distance_km, 1),
                "total_hours": round(r.total_hours, 1),
                "avg_day_distance_km": round(r.avg_day_distance, 1),
                "overtime_days": over,
            }
        path = os.path.join(output_dir, "compare_result.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(compare_data, f, ensure_ascii=False, indent=2)
        print(f"\nComparison saved: {path}")

        return results

    def _load_points(self) -> List[Point]:
        """Load points from configured data sources."""
        from navigate.io.loaders import ExcelLoader, SurveyLoader

        data_cfg = self.config.data
        if not data_cfg.points:
            raise ValueError("data.points configuration is required")

        loader = ExcelLoader()
        points = loader.load(data_cfg.points)

        # Load and match survey data if configured
        if data_cfg.survey and data_cfg.survey.file:
            print("[Data] Loading survey data...")
            survey_loader = SurveyLoader()
            survey_loader.load_and_match(
                data_cfg.survey, points,
                corrections=data_cfg.corrections,
            )

        return points

    def _build_matrix(self, points: List[Point]) -> DistanceMatrix:
        """Build distance matrix using configured provider."""
        from navigate.distance import PROVIDERS
        from navigate.distance.haversine import haversine

        provider_name = self.config.distance.provider
        if provider_name == "haversine":
            # Use fast direct calculation
            def dist_func(a, b):
                return haversine(a.lat, a.lng, b.lat, b.lng)
            return DistanceMatrix.from_points(points, dist_func)
        else:
            # Use configured provider
            provider_cls = PROVIDERS.get(provider_name)
            if not provider_cls:
                raise ValueError(f"Unknown distance provider: {provider_name}")
            opts = self.config.distance.options
            if provider_name == "amap":
                provider = provider_cls(
                    api_key=opts.get("amap_key", ""),
                    request_delay=opts.get("request_delay", 0.5),
                )
            else:
                provider = provider_cls(**opts)

            def dist_func(a, b):
                r = provider.get_distance(a, b)
                return r.distance_km
            return DistanceMatrix.from_points(points, dist_func)

    def _run_strategy(self, points: List[Point],
                      dist_matrix: DistanceMatrix) -> PlanResult:
        """Run the configured strategy."""
        # Import all strategies to ensure they are registered
        from navigate.strategies import STRATEGIES
        from navigate.strategies.tsp import TspStrategy
        from navigate.strategies.cluster import ClusterStrategy
        from navigate.strategies.overnight import OvernightStrategy

        strategy_name = self.config.strategy.name
        strategy_cls = STRATEGIES.get(strategy_name)
        if not strategy_cls:
            raise ValueError(f"Unknown strategy: {strategy_name}. "
                             f"Available: {list(STRATEGIES.keys())}")

        if strategy_name == "cluster":
            base_coord = self._get_base_coord()
            strategy = strategy_cls(self.config, base_coord=base_coord)
        elif strategy_name == "overnight":
            base_coord = self._get_base_coord()
            bp_name = self.config.base_point.name or "公司"
            strategy = strategy_cls(self.config, base_coord=base_coord, base_name=bp_name)
        else:
            strategy = strategy_cls(self.config)

        return strategy.plan(points, dist_matrix)

    def _get_base_coord(self):
        """Get base point coordinates, geocoding if needed."""
        bp = self.config.base_point
        if bp.lng is not None and bp.lat is not None:
            return (bp.lng, bp.lat)

        if bp.name:
            opts = self.config.distance.options
            amap_key = opts.get("amap_key", "")
            if amap_key:
                from navigate.geocoding.amap import AmapGeocoder
                geocoder = AmapGeocoder(amap_key)
                result = geocoder.geocode(bp.name)
                if result:
                    return result
        return None

    def _export(self, result: PlanResult, tag: str = ""):
        """Export results in all configured formats."""
        from navigate.io.exporters import EXPORTERS

        output_dir = self.config.export.output_dir
        if tag:
            output_dir = os.path.join(output_dir, tag)
        os.makedirs(output_dir, exist_ok=True)

        # Save config
        import yaml
        config_path = os.path.join(output_dir, "config_used.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(self.config.summary())

        # Get distance provider for map generation
        distance_provider = None
        if self.config.distance.provider == "amap":
            opts = self.config.distance.options
            amap_key = opts.get("amap_key", "")
            if amap_key:
                from navigate.distance.amap import AmapProvider
                distance_provider = AmapProvider(
                    api_key=amap_key,
                    request_delay=opts.get("request_delay", 0.5),
                )

        for fmt in self.config.export.formats:
            exporter_cls = EXPORTERS.get(fmt.type)
            if not exporter_cls:
                print(f"[Export] Unknown format: {fmt.type}, skipping")
                continue
            exporter = exporter_cls(self.config)
            kwargs = {"tag": tag, "format_config": fmt}
            if fmt.type == "map":
                kwargs["distance_provider"] = distance_provider
            exporter.export(result, output_dir, **kwargs)

    def _print_comparison(self, results: Dict[str, PlanResult]):
        names = list(results.keys())
        max_hours = self.config.constraints.max_daily_hours
        print(f"\n{'=' * 60}")
        print(" Strategy Comparison")
        print(f"{'=' * 60}")
        header = f"{'Metric':<20}"
        for n in names:
            header += f" {n:<18}"
        print(header)
        print("-" * 60)

        metrics = [
            ("Days", lambda r: r.total_days),
            ("Points", lambda r: r.total_points),
            ("Distance(km)", lambda r: round(r.total_distance_km, 1)),
            ("Hours", lambda r: round(r.total_hours, 1)),
            ("Avg dist/day(km)", lambda r: round(r.avg_day_distance, 1)),
            ("Max pts/day", lambda r: r.max_day_points),
            ("Overtime days", lambda r: sum(1 for d in r.days
                                             if d.total_time_hours > max_hours)),
        ]
        for label, fn in metrics:
            line = f"{label:<20}"
            for n in names:
                line += f" {fn(results[n]):<18}"
            print(line)
        print(f"{'=' * 60}")
