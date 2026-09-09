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


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve package version constraints.")
    parser.add_argument("input", help="Path to a JSON file describing packages and root requirements")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show search step count")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    universe = Universe.from_dict(data)
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
