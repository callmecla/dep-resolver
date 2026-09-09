"""
Minimal semantic version parsing and constraint checking.

Supports versions like "1.2.3" (any number of numeric parts) and
constraints like ">=1.2.0", "<2.0.0", "==1.0.0", "!=1.5.0".
Multiple constraints can be combined with commas, e.g. ">=1.0.0,<2.0.0".
"""

from __future__ import annotations
from functools import total_ordering
from typing import List, Tuple


@total_ordering
class Version:
    def __init__(self, raw: str):
        self.raw = raw
        self.parts: Tuple[int, ...] = tuple(int(p) for p in raw.split("."))

    def __eq__(self, other: "Version") -> bool:
        return self._padded(other) == other._padded(self)

    def __lt__(self, other: "Version") -> bool:
        a, b = self._padded(other), other._padded(self)
        return a < b

    def _padded(self, other: "Version") -> Tuple[int, ...]:
        length = max(len(self.parts), len(other.parts))
        return self.parts + (0,) * (length - len(self.parts))

    def __repr__(self) -> str:
        return self.raw

    def __hash__(self):
        return hash(self.parts)


_OPS = {
    ">=": lambda v, c: v >= c,
    "<=": lambda v, c: v <= c,
    "==": lambda v, c: v == c,
    "!=": lambda v, c: v != c,
    ">": lambda v, c: v > c,
    "<": lambda v, c: v < c,
}

# Order matters: check two-character operators before one-character ones.
_OP_TOKENS = [">=", "<=", "==", "!=", ">", "<"]


class Constraint:
    """A single comparator, e.g. '>=1.2.0'."""

    def __init__(self, raw: str):
        raw = raw.strip()
        for token in _OP_TOKENS:
            if raw.startswith(token):
                self.op = token
                self.version = Version(raw[len(token):].strip())
                self.raw = raw
                return
        raise ValueError(f"Unrecognized constraint syntax: {raw!r}")

    def satisfied_by(self, version: Version) -> bool:
        return _OPS[self.op](version, self.version)

    def __repr__(self) -> str:
        return self.raw


class ConstraintSet:
    """One or more comma-separated constraints, all of which must hold."""

    def __init__(self, raw: str):
        self.raw = raw.strip()
        if self.raw in ("", "*"):
            self.constraints: List[Constraint] = []  # "*" / empty = any version
        else:
            self.constraints = [
                Constraint(part) for part in self.raw.split(",") if part.strip()
            ]

    def satisfied_by(self, version: Version) -> bool:
        return all(c.satisfied_by(version) for c in self.constraints)

    def __repr__(self) -> str:
        return self.raw or "*"
