"""
Data model for the dependency universe.

The input format (see examples/*.json) looks like:

{
  "root": {
    "A": ">=1.0.0",
    "B": "*"
  },
  "packages": {
    "A": {
      "1.0.0": {"C": ">=2.0.0"},
      "1.1.0": {"C": ">=2.0.0"}
    },
    "B": {
      "1.0.0": {"C": "<2.0.0"}
    },
    "C": {
      "1.5.0": {},
      "2.0.0": {},
      "2.1.0": {}
    }
  }
}
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List

from .version import Version, ConstraintSet


@dataclass
class Requirement:
    package: str
    constraint: ConstraintSet


@dataclass
class PackageVersion:
    name: str
    version: Version
    dependencies: List[Requirement] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"{self.name}=={self.version}"


@dataclass
class Universe:
    """The full set of known packages, versions, and their dependencies."""

    root: List[Requirement]
    packages: Dict[str, List[PackageVersion]]

    @classmethod
    def from_dict(cls, data: dict) -> "Universe":
        packages: Dict[str, List[PackageVersion]] = {}
        for name, versions in data.get("packages", {}).items():
            pkg_versions = []
            for ver_str, deps in versions.items():
                requirements = [
                    Requirement(dep_name, ConstraintSet(dep_constraint))
                    for dep_name, dep_constraint in deps.items()
                ]
                pkg_versions.append(
                    PackageVersion(name, Version(ver_str), requirements)
                )
            # Try highest version first — a common, sensible default policy.
            pkg_versions.sort(key=lambda pv: pv.version, reverse=True)
            packages[name] = pkg_versions

        root = [
            Requirement(name, ConstraintSet(constraint))
            for name, constraint in data.get("root", {}).items()
        ]
        return cls(root=root, packages=packages)
