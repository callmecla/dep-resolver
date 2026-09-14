"""
Builds a `Universe` from real PyPI package data, so the exact same
backtracking solver in `solver.py` can resolve real-world dependencies —
not just synthetic JSON scenarios.

Dependencies gated by a PEP 508 environment marker (e.g.
`; sys_platform == "win32"`) are evaluated against a target environment
(see markers.py) and included only if the marker is satisfied — the same
behavior `pip` uses during a real install.

Deliberate v3 limitations (documented, not silently wrong):
  - Pre-releases, dev releases, and post-releases are excluded; only plain
    "X.Y.Z"-style stable versions are considered.
  - The crawl is bounded (max versions per package, max depth, max total
    packages) so a popular package with a huge transitive tree doesn't
    turn a demo into a multi-minute fetch storm.
"""

from __future__ import annotations
import json
import re
import urllib.request
import urllib.error
from typing import Callable, Dict, List, Optional, Set, Tuple

from .model import Universe, PackageVersion, Requirement
from .version import Version, ConstraintSet
from .markers import MarkerEnvironment, MarkerSyntaxError

PYPI_BASE = "https://pypi.org/pypi"

_STABLE_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")
_REQ_RE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*(?:\[[^\]]*\])?\s*(\([^)]*\)|[^;]*)?\s*(;.*)?$"
)

ProgressCallback = Optional[Callable[[str], None]]


class PyPIError(Exception):
    pass


def _normalize(name: str) -> str:
    """PyPI package names are case-insensitive; normalize so 'Flask' and
    'flask' resolve to the same graph node."""
    return name.strip().lower()


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "dep-resolver/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise PyPIError(f"PyPI request failed ({e.code}) for {url}") from e
    except urllib.error.URLError as e:
        raise PyPIError(f"Could not reach PyPI: {e.reason}") from e


def _is_stable(version_str: str) -> bool:
    return bool(_STABLE_VERSION_RE.match(version_str))


def _parse_requirement(raw: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """Parse one requires_dist entry into (name, constraint_str, marker_str
    or None). Returns None only if the line is unparseable."""
    m = _REQ_RE.match(raw)
    if not m:
        return None
    name, spec, marker = m.groups()
    name = name.strip()
    spec = (spec or "").strip()
    if spec.startswith("(") and spec.endswith(")"):
        spec = spec[1:-1].strip()
    marker_str = marker[1:].strip() if marker else None  # strip leading ';'
    return name, spec or "*", marker_str


def fetch_package_versions(name: str, max_versions: int = 6) -> Dict[str, list]:
    """Return up to `max_versions` most recent stable releases of `name`,
    each mapped to its raw requires_dist list."""
    data = _http_get_json(f"{PYPI_BASE}/{name}/json")
    releases = data.get("releases", {})

    stable = [
        v for v, files in releases.items()
        if _is_stable(v) and files and not all(f.get("yanked") for f in files)
    ]
    stable.sort(key=lambda v: Version(v), reverse=True)
    chosen = stable[:max_versions]

    out: Dict[str, list] = {}
    for v in chosen:
        detail = _http_get_json(f"{PYPI_BASE}/{name}/{v}/json")
        out[v] = detail.get("info", {}).get("requires_dist") or []
    return out


def build_universe_from_pypi(
    root_packages: Dict[str, str],
    max_versions_per_package: int = 6,
    max_packages: int = 40,
    max_depth: int = 4,
    progress_callback: ProgressCallback = None,
    environment: Optional[MarkerEnvironment] = None,
) -> Universe:
    """
    Crawl PyPI starting from root_packages ({name: constraint_str}) and
    build a Universe. Bounded by max_packages/max_depth so real-world
    dependency trees stay tractable. `environment` controls which
    environment-marker-gated dependencies get included (defaults to the
    machine running this code).
    """
    env = environment or MarkerEnvironment.current()

    def report(msg: str):
        if progress_callback:
            progress_callback(msg)

    packages: Dict[str, List[PackageVersion]] = {}
    seen: Set[str] = set()
    queue: List[Tuple[str, int]] = [(name, 0) for name in root_packages]

    while queue and len(seen) < max_packages:
        name, depth = queue.pop(0)
        key = _normalize(name)
        if key in seen:
            continue
        seen.add(key)
        if depth > max_depth:
            continue

        report(f"Fetching {name} from PyPI…")
        try:
            raw_versions = fetch_package_versions(name, max_versions_per_package)
        except PyPIError as e:
            report(f"  skipped {name}: {e}")
            continue

        if not raw_versions:
            report(f"  no stable releases found for {name}")
            continue

        pkg_versions: List[PackageVersion] = []
        for ver_str, requires_dist in raw_versions.items():
            deps: List[Requirement] = []
            for raw_req in requires_dist:
                parsed = _parse_requirement(raw_req)
                if not parsed:
                    continue
                dep_name, dep_constraint, marker_str = parsed

                if marker_str:
                    try:
                        if not env.marker_applies(marker_str):
                            continue  # marker not satisfied — correctly excluded
                    except MarkerSyntaxError:
                        continue  # unparseable marker — skip rather than guess

                try:
                    deps.append(Requirement(_normalize(dep_name), ConstraintSet(dep_constraint)))
                except ValueError:
                    continue  # unparseable constraint syntax — skip rather than crash
                if depth + 1 <= max_depth and _normalize(dep_name) not in seen:
                    queue.append((dep_name, depth + 1))
            pkg_versions.append(PackageVersion(key, Version(ver_str), deps))

        pkg_versions.sort(key=lambda pv: pv.version, reverse=True)
        packages[key] = pkg_versions

    root = [
        Requirement(_normalize(name), ConstraintSet(constraint))
        for name, constraint in root_packages.items()
    ]
    return Universe(root=root, packages=packages)
