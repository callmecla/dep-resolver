import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from resolver import Universe, resolve

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


def load(name):
    with open(os.path.join(EXAMPLES, name)) as f:
        return Universe.from_dict(json.load(f))


def test_simple_ok_resolves():
    universe = load("simple_ok.json")
    result = resolve(universe)
    assert result.success
    assert str(result.assignment["A"].version) == "1.1.0"
    assert str(result.assignment["C"].version) == "2.1.0"


def test_simple_conflict_fails_clearly():
    universe = load("simple_conflict.json")
    result = resolve(universe)
    assert not result.success
    assert result.conflict.package == "C"
    assert "requires" in result.conflict.reason


def test_deep_chain_backtracks_to_valid_solution():
    universe = load("deep_chain_backtrack.json")
    result = resolve(universe)
    assert result.success
    # Must have backtracked away from the highest-version chain (A 2.0.0)
    # down to the one whose transitive D constraint is compatible with root.
    assert str(result.assignment["A"].version) == "1.0.0"
    assert str(result.assignment["D"].version) == "2.5.0"
    assert result.steps > 1  # proves backtracking actually happened


def test_unknown_package_reports_clearly():
    universe = Universe.from_dict({"root": {"Ghost": "*"}, "packages": {}})
    result = resolve(universe)
    assert not result.success
    assert "Unknown package" in result.conflict.reason


if __name__ == "__main__":
    # Allow running without pytest installed: `python tests/test_solver.py`
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
