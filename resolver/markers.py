"""
A small parser/evaluator for PEP 508 environment markers — the
`; sys_platform == "win32"` style conditions attached to a dependency.

Supported grammar (a practical subset of PEP 508's marker grammar):

    marker      := and_expr ('or' and_expr)*
    and_expr    := term ('and' term)*
    term        := '(' marker ')' | comparison
    comparison  := operand OP operand
    operand     := VARIABLE | STRING
    OP          := '==' | '!=' | '<=' | '>=' | '<' | '>' | 'in' | 'not in'

This is a real tokenizer + recursive-descent parser + tree evaluator —
no `eval()` involved, so a malicious or malformed marker string can't
execute arbitrary code.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Union

from .version import Version

# Environment variables PEP 508 markers are allowed to reference.
MARKER_VARIABLES = {
    "python_version", "python_full_version", "os_name", "sys_platform",
    "platform_release", "platform_system", "platform_version",
    "platform_machine", "platform_python_implementation",
    "implementation_name", "implementation_version", "extra",
}

_TOKEN_RE = re.compile(r"""
    \s*(?:
        (?P<STRING>'[^']*'|"[^"]*")
      | (?P<OP><=|>=|==|!=|<|>)
      | (?P<AND>\band\b)
      | (?P<OR>\bor\b)
      | (?P<NOT_IN>\bnot\s+in\b)
      | (?P<IN>\bin\b)
      | (?P<LPAREN>\()
      | (?P<RPAREN>\))
      | (?P<VAR>[A-Za-z_][A-Za-z0-9_.]*)
    )
""", re.VERBOSE)


class MarkerSyntaxError(Exception):
    pass


def _tokenize(raw: str) -> List[Tuple[str, str]]:
    tokens = []
    pos = 0
    while pos < len(raw):
        m = _TOKEN_RE.match(raw, pos)
        if not m or m.end() == pos:
            if raw[pos:].strip() == "":
                break
            raise MarkerSyntaxError(f"Unexpected character in marker at position {pos}: {raw[pos:pos+10]!r}")
        pos = m.end()
        kind = m.lastgroup
        text = m.group(kind)
        tokens.append((kind, text))
    return tokens


# AST node types (simple tuples for compactness):
#   ('or', left, right) | ('and', left, right)
#   ('cmp', op, left_operand, right_operand)
# operand := ('var', name) | ('str', value)
Node = Union[tuple]


class _Parser:
    def __init__(self, tokens: List[Tuple[str, str]]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _advance(self):
        tok = self._peek()
        self.pos += 1
        return tok

    def parse(self) -> Node:
        node = self._parse_or()
        if self.pos != len(self.tokens):
            raise MarkerSyntaxError(f"Unexpected token: {self._peek()}")
        return node

    def _parse_or(self) -> Node:
        left = self._parse_and()
        while self._peek()[0] == "OR":
            self._advance()
            right = self._parse_and()
            left = ("or", left, right)
        return left

    def _parse_and(self) -> Node:
        left = self._parse_term()
        while self._peek()[0] == "AND":
            self._advance()
            right = self._parse_term()
            left = ("and", left, right)
        return left

    def _parse_term(self) -> Node:
        kind, text = self._peek()
        if kind == "LPAREN":
            self._advance()
            node = self._parse_or()
            if self._peek()[0] != "RPAREN":
                raise MarkerSyntaxError("Expected closing ')'")
            self._advance()
            return node
        return self._parse_comparison()

    def _parse_comparison(self) -> Node:
        left = self._parse_operand()
        kind, text = self._peek()
        if kind == "OP":
            self._advance()
            right = self._parse_operand()
            return ("cmp", text, left, right)
        if kind == "IN":
            self._advance()
            right = self._parse_operand()
            return ("cmp", "in", left, right)
        if kind == "NOT_IN":
            self._advance()
            right = self._parse_operand()
            return ("cmp", "not in", left, right)
        raise MarkerSyntaxError(f"Expected a comparison operator, got: {(kind, text)}")

    def _parse_operand(self) -> Node:
        kind, text = self._advance()
        if kind == "STRING":
            return ("str", text[1:-1])
        if kind == "VAR":
            return ("var", text)
        raise MarkerSyntaxError(f"Expected a variable or string, got: {(kind, text)}")


def parse_marker(raw: str) -> Node:
    return _Parser(_tokenize(raw)).parse()


def _looks_like_version(s: str) -> bool:
    return bool(re.fullmatch(r"\d+(\.\d+)*", s))


def _resolve(node: Node, env: Dict[str, str]) -> str:
    kind = node[0]
    if kind == "str":
        return node[1]
    if kind == "var":
        name = node[1]
        if name not in MARKER_VARIABLES:
            raise MarkerSyntaxError(f"Unknown marker variable: {name!r}")
        return env.get(name, "")
    raise MarkerSyntaxError(f"Cannot resolve node as a value: {node!r}")


def evaluate_marker(node: Node, env: Dict[str, str]) -> bool:
    kind = node[0]
    if kind == "and":
        return evaluate_marker(node[1], env) and evaluate_marker(node[2], env)
    if kind == "or":
        return evaluate_marker(node[1], env) or evaluate_marker(node[2], env)
    if kind == "cmp":
        op, left_node, right_node = node[1], node[2], node[3]
        left = _resolve(left_node, env)
        right = _resolve(right_node, env)

        if op == "in":
            return left in right
        if op == "not in":
            return left not in right

        # Numeric/version comparison when both sides look like dotted
        # version numbers (e.g. python_version >= "3.8"); otherwise
        # fall back to plain string comparison.
        if _looks_like_version(left) and _looks_like_version(right):
            lv, rv = Version(left), Version(right)
            return {
                "==": lv == rv, "!=": lv != rv,
                ">=": lv >= rv, "<=": lv <= rv,
                ">": lv > rv, "<": lv < rv,
            }[op]

        return {
            "==": left == right, "!=": left != right,
            ">=": left >= right, "<=": left <= right,
            ">": left > right, "<": left < right,
        }[op]

    raise MarkerSyntaxError(f"Unknown node kind: {kind!r}")


@dataclass
class MarkerEnvironment:
    """The target environment a marker is evaluated against. Defaults to
    the machine actually running the resolver — mirrors how `pip` behaves
    when it evaluates markers during a real install."""

    python_version: str
    python_full_version: str
    os_name: str
    sys_platform: str
    platform_system: str
    platform_machine: str
    implementation_name: str
    extras: frozenset = frozenset()  # extras the caller actually requested

    @classmethod
    def current(cls) -> "MarkerEnvironment":
        import sys
        import os
        import platform
        v = sys.version_info
        return cls(
            python_version=f"{v.major}.{v.minor}",
            python_full_version=f"{v.major}.{v.minor}.{v.micro}",
            os_name=os.name,
            sys_platform=sys.platform,
            platform_system=platform.system(),
            platform_machine=platform.machine(),
            implementation_name=sys.implementation.name,
        )

    def as_dict(self, requested_extra: str = "") -> Dict[str, str]:
        return {
            "python_version": self.python_version,
            "python_full_version": self.python_full_version,
            "os_name": self.os_name,
            "sys_platform": self.sys_platform,
            "platform_system": self.platform_system,
            "platform_machine": self.platform_machine,
            "implementation_name": self.implementation_name,
            "extra": requested_extra,
        }

    def marker_applies(self, marker_str: str) -> bool:
        """True if this marker string is satisfied by this environment.
        If the marker references `extra`, it's checked against each
        requested extra (or "" if none were requested — matching a plain
        `pip install pkg` with no extras)."""
        node = parse_marker(marker_str)
        candidates = self.extras if self.extras else frozenset({""})
        return any(evaluate_marker(node, self.as_dict(e)) for e in candidates)
