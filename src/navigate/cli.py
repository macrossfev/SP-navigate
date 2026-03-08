"""Command-line interface for navigate."""
from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Navigate - Multi-point route planning system",
        prog="navigate",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # plan command
    plan_parser = subparsers.add_parser("plan", help="Run route planning")
    plan_parser.add_argument("--config", required=True, help="YAML config file path")
    plan_parser.add_argument("--set", action="append", default=[],
                             dest="overrides",
                             help="Override config values (e.g. --set constraints.max_daily_points=6)")
    plan_parser.add_argument("--tag", default="", help="Output tag/label")

    # compare command
    cmp_parser = subparsers.add_parser("compare", help="Compare multiple strategies")
    cmp_parser.add_argument("--config", required=True, help="YAML config file path")
    cmp_parser.add_argument("--strategies", default="tsp,cluster",
                            help="Comma-separated strategy names (default: tsp,cluster)")
    cmp_parser.add_argument("--set", action="append", default=[],
                            dest="overrides",
                            help="Override config values")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    from navigate.core.config import NavigateConfig
    from navigate.core.planner import Planner

    # Load config
    config = NavigateConfig.from_yaml(args.config)

    # Apply overrides
    if args.overrides:
        override_dict = {}
        for item in args.overrides:
            if "=" in item:
                k, v = item.split("=", 1)
                override_dict[k] = v
        config.apply_overrides(override_dict)

    planner = Planner(config)

    if args.command == "plan":
        planner.run(tag=args.tag)
    elif args.command == "compare":
        strategies = [s.strip() for s in args.strategies.split(",")]
        planner.compare(strategies)


if __name__ == "__main__":
    main()
