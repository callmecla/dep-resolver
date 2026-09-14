#!/usr/bin/env python3
"""
CLI entry point.

Usage:
    python resolve.py examples/simple_ok.json
    python resolve.py examples/simple_conflict.json --verbose
"""

import argparse
import json
import sys

from resolver import Universe, resolve
from resolver.pypi_source import build_universe_from_pypi, PyPIError


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve package version constraints.")
    parser.add_argument("input", nargs="?", help="Path to a JSON file describing packages and root requirements")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show search step count")
    parser.add_argument(
        "--from-pypi", metavar="PACKAGE[==CONSTRAINT]", nargs="+",
        help="Resolve real packages from PyPI instead of a JSON file, "
             "e.g. --from-pypi requests \"urllib3<2.0.0\"",
    )
    parser.add_argument("--max-versions", type=int, default=6, help="Max versions fetched per PyPI package (default 6)")
    parser.add_argument("--max-packages", type=int, default=40, help="Max total packages crawled from PyPI (default 40)")
    parser.add_argument("--max-depth", type=int, default=4, help="Max transitive dependency depth from PyPI (default 4)")
    args = parser.parse_args()

    if args.from_pypi:
        root_packages = {}
        for entry in args.from_pypi:
            if "==" in entry or ">=" in entry or "<=" in entry or "<" in entry or ">" in entry or "!=" in entry:
                for op in ("==", ">=", "<=", "!=", ">", "<"):
                    if op in entry:
                        name, constraint = entry.split(op, 1)
                        root_packages[name.strip()] = f"{op}{constraint.strip()}"
                        break
            else:
                root_packages[entry.strip()] = "*"

        try:
            universe = build_universe_from_pypi(
                root_packages,
                max_versions_per_package=args.max_versions,
                max_packages=args.max_packages,
                max_depth=args.max_depth,
                progress_callback=(print if args.verbose else None),
            )
        except PyPIError as e:
            print(f"PyPI fetch failed: {e}")
            return 1
    elif args.input:
        with open(args.input) as f:
            data = json.load(f)
        universe = Universe.from_dict(data)
    else:
        parser.error("Provide either an input JSON file or --from-pypi PACKAGE...")
        return 2

    result = resolve(universe)

    if result.success:
        print("Resolution succeeded:\n")
        for name, pv in sorted(result.assignment.items()):
            print(f"  {name} -> {pv.version}")
        if args.verbose:
            print(f"\n(search steps: {result.steps})")
        return 0
    else:
        print("Resolution FAILED:\n")
        print(f"  Package:  {result.conflict.package}")
        print(f"  Reason:   {result.conflict.reason}")
        if args.verbose:
            print(f"\n(search steps: {result.steps})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
