"""
Backtracking dependency resolver.

Strategy: maintain a partial assignment (package name -> chosen version).
Process requirements one at a time. When a package is first requested,
try its versions in order (highest first) and recurse. If a later
requirement conflicts with an already-chosen version, backtrack and try
the next candidate. If no candidate works, report a clear conflict.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

from .model import Universe, Requirement, PackageVersion


@dataclass
class Conflict:
    package: str
    reason: str


@dataclass
class Resolution:
    success: bool
    assignment: Dict[str, PackageVersion]
    conflict: Optional[Conflict] = None
    steps: int = 0

    def __repr__(self) -> str:
        if self.success:
            picks = ", ".join(str(v) for v in self.assignment.values())
            return f"Resolved: {picks}"
        return f"Unresolvable: {self.conflict.reason}"


class ResolverError(Exception):
    pass


def resolve(universe: Universe, max_steps: int = 50_000) -> Resolution:
    assignment: Dict[str, PackageVersion] = {}
    # requirements still to satisfy, each tagged with who asked for it
    queue: List[tuple] = [(req, "root") for req in universe.root]
    state = {"steps": 0}

    conflict = _backtrack(universe, queue, assignment, state, max_steps)
    if conflict is None:
        return Resolution(True, dict(assignment), steps=state["steps"])
    return Resolution(False, {}, conflict=conflict, steps=state["steps"])


def _backtrack(
    universe: Universe,
    queue: List[tuple],
    assignment: Dict[str, PackageVersion],
    state: dict,
    max_steps: int,
) -> Optional[Conflict]:
    if not queue:
        return None  # everything satisfied

    state["steps"] += 1
    if state["steps"] > max_steps:
        return Conflict("*", "Exceeded max search steps — possible cycle or huge search space")

    (req, requested_by), rest = queue[0], queue[1:]

    # Already assigned? Just check it satisfies this requirement.
    if req.package in assignment:
        chosen = assignment[req.package]
        if req.constraint.satisfied_by(chosen.version):
            return _backtrack(universe, rest, assignment, state, max_steps)
        return Conflict(
            req.package,
            f"{requested_by} requires {req.package}{req.constraint}, "
            f"but {chosen} was already chosen to satisfy an earlier requirement",
        )

    candidates = universe.packages.get(req.package)
    if not candidates:
        return Conflict(req.package, f"Unknown package '{req.package}' required by {requested_by}")

    matching = [c for c in candidates if req.constraint.satisfied_by(c.version)]
    if not matching:
        available = ", ".join(str(c.version) for c in candidates)
        return Conflict(
            req.package,
            f"{requested_by} requires {req.package}{req.constraint}, "
            f"but only these versions exist: {available}",
        )

    last_conflict: Optional[Conflict] = None
    for candidate in matching:
        assignment[req.package] = candidate
        new_reqs = [(dep, f"{candidate}") for dep in candidate.dependencies]
        result = _backtrack(universe, rest + new_reqs, assignment, state, max_steps)
        if result is None:
            return None  # success down this branch
        last_conflict = result
        del assignment[req.package]  # backtrack

    return last_conflict
