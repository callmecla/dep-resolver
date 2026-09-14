import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from resolver.markers import MarkerEnvironment, MarkerSyntaxError, parse_marker


def _env(**overrides):
    base = dict(
        python_version="3.12", python_full_version="3.12.0", os_name="posix",
        sys_platform="linux", platform_system="Linux", platform_machine="x86_64",
        implementation_name="cpython",
    )
    base.update(overrides)
    return MarkerEnvironment(**base)


def test_simple_equality():
    env = _env(sys_platform="win32")
    assert env.marker_applies('sys_platform == "win32"')
    assert not env.marker_applies('sys_platform == "linux"')


def test_version_comparison_numeric_not_lexicographic():
    env = _env(python_version="3.10")
    # lexicographically "3.10" < "3.9" as strings, but numerically 3.10 > 3.9
    assert env.marker_applies('python_version >= "3.9"')
    assert not env.marker_applies('python_version < "3.9"')


def test_and_or_precedence():
    env = _env(sys_platform="linux", python_version="3.12")
    assert env.marker_applies('sys_platform == "linux" and python_version >= "3.8"')
    assert not env.marker_applies('sys_platform == "win32" and python_version >= "3.8"')
    assert env.marker_applies('sys_platform == "win32" or python_version >= "3.8"')


def test_parentheses_grouping():
    env = _env(sys_platform="linux", python_version="3.12")
    assert env.marker_applies(
        '(sys_platform == "win32" or sys_platform == "linux") and python_version >= "3.10"'
    )


def test_extra_defaults_to_excluded():
    env = _env()  # no extras requested
    assert not env.marker_applies('extra == "docs"')


def test_extra_included_when_requested():
    env = _env(extras=frozenset({"docs"}))
    assert env.marker_applies('extra == "docs"')
    assert not env.marker_applies('extra == "test"')


def test_in_operator():
    env = _env(sys_platform="linux")
    assert env.marker_applies('"lin" in sys_platform')
    assert not env.marker_applies('"win" in sys_platform')


def test_unparseable_marker_raises():
    try:
        parse_marker("this is not >< a valid marker (((")
        assert False, "expected MarkerSyntaxError"
    except MarkerSyntaxError:
        pass


def test_unknown_variable_raises_at_eval_time():
    env = _env()
    try:
        env.marker_applies('nonexistent_var == "x"')
        assert False, "expected MarkerSyntaxError"
    except MarkerSyntaxError:
        pass


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
