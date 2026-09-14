import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from resolver.pypi_source import _parse_requirement, _is_stable, _normalize
from resolver.version import ConstraintSet, Version


def test_parse_requirement_no_parens():
    assert _parse_requirement("charset_normalizer<4,>=2") == ("charset_normalizer", "<4,>=2", None)


def test_parse_requirement_with_parens():
    assert _parse_requirement("requests-toolbelt (<1.0.0,>=0.9.1)") == (
        "requests-toolbelt", "<1.0.0,>=0.9.1", None
    )


def test_parse_requirement_no_constraint():
    assert _parse_requirement("colorama") == ("colorama", "*", None)


def test_parse_requirement_captures_extras_marker():
    name, constraint, marker = _parse_requirement('PySocks!=1.5.7,>=1.5.6; extra == "socks"')
    assert name == "PySocks"
    assert constraint == "!=1.5.7,>=1.5.6"
    assert marker == 'extra == "socks"'


def test_parse_requirement_captures_platform_marker():
    name, constraint, marker = _parse_requirement('win-inet-pton; sys_platform == "win32"')
    assert name == "win-inet-pton"
    assert marker == 'sys_platform == "win32"'


def test_is_stable_filters_prereleases():
    assert _is_stable("2.31.0")
    assert not _is_stable("2.31.0rc1")
    assert not _is_stable("2.31.0.dev0")
    assert not _is_stable("2.31.0b2")


def test_normalize_lowercases():
    assert _normalize("Flask") == "flask"
    assert _normalize("  Requests ") == "requests"


def test_compatible_release_operator_parses():
    cs = ConstraintSet("~=1.4.2")
    assert cs.satisfied_by(Version("1.4.9"))
    assert not cs.satisfied_by(Version("1.5.0"))
    assert not cs.satisfied_by(Version("1.4.1"))


def test_marker_gated_dependency_included_when_marker_applies():
    """Live integration check: virtualenv has mutually-exclusive
    python_version branches for filelock. On whatever Python runs this
    test, exactly the applicable branch should be pulled in — proving
    marker evaluation actually changes real resolution, not just parsing."""
    from resolver.pypi_source import build_universe_from_pypi
    universe = build_universe_from_pypi(
        {"virtualenv": "*"}, max_versions_per_package=1, max_depth=2, max_packages=10
    )
    assert "filelock" in universe.packages, "a real, always-needed dependency was wrongly excluded"


def test_extras_marker_still_excluded_by_default():
    """tqdm's 'requests; extra == \"discord\"' should NOT appear since we
    didn't request that extra — this must keep working after the marker fix."""
    from resolver.pypi_source import build_universe_from_pypi
    universe = build_universe_from_pypi(
        {"tqdm": "*"}, max_versions_per_package=1, max_depth=2, max_packages=10
    )
    assert "requests" not in universe.packages
    assert "slack-sdk" not in universe.packages


if __name__ == "__main__":
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
