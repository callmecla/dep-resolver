import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from resolver.pypi_source import _parse_requirement, _is_stable, _normalize
from resolver.version import ConstraintSet, Version


def test_parse_requirement_no_parens():
    assert _parse_requirement("charset_normalizer<4,>=2") == ("charset_normalizer", "<4,>=2")


def test_parse_requirement_with_parens():
    assert _parse_requirement("requests-toolbelt (<1.0.0,>=0.9.1)") == (
        "requests-toolbelt", "<1.0.0,>=0.9.1"
    )


def test_parse_requirement_no_constraint():
    assert _parse_requirement("colorama") == ("colorama", "*")


def test_parse_requirement_skips_extras_marker():
    assert _parse_requirement('PySocks!=1.5.7,>=1.5.6; extra == "socks"') is None


def test_parse_requirement_skips_platform_marker():
    assert _parse_requirement('win-inet-pton; sys_platform == "win32"') is None


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
