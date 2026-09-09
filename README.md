# dep-resolver

A small dependency version resolver — the kind of thing `pip`, `npm`, or
`cargo` runs under the hood every time you install something.

Given a set of packages, the versions available for each, and what each
version depends on, `dep-resolver` finds a combination of versions that
satisfies every constraint — or explains clearly *why* no such combination
exists.

## Why

Every real package manager solves this problem, and it's a classic example
of constraint satisfaction: hard in general, but tractable for realistic
inputs. This is a from-scratch implementation of the core idea — no
external solver libraries — using backtracking search.

## Usage

```bash
python resolve.py examples/simple_ok.json
python resolve.py examples/simple_conflict.json --verbose
```

### Example: successful resolution

```json
{
  "root": { "A": ">=1.0.0", "B": "*" },
  "packages": {
    "A": { "1.0.0": {"C": ">=2.0.0"}, "1.1.0": {"C": ">=2.0.0"} },
    "B": { "1.0.0": {"C": ">=2.0.0,<3.0.0"} },
    "C": { "1.5.0": {}, "2.0.0": {}, "2.1.0": {} }
  }
}
```

```
$ python resolve.py examples/simple_ok.json
Resolution succeeded:

  A -> 1.1.0
  B -> 1.0.0
  C -> 2.1.0
```

### Example: unsatisfiable constraints

```
$ python resolve.py examples/simple_conflict.json
Resolution FAILED:

  Package:  C
  Reason:   B==1.0.0 requires C<2.0.0, but C==2.0.0 was already chosen to
            satisfy an earlier requirement
```

## Input format

A JSON file with two top-level keys:

- `root` — the packages you want installed, with a constraint for each
  (`">=1.0.0"`, `"==2.1.0"`, `"*"` for any version, or comma-separated for
  multiple constraints like `">=1.0.0,<2.0.0"`).
- `packages` — every known package, each with a map of version string to
  its own dependencies (in the same constraint syntax).

See `examples/` for full samples, including `deep_chain_backtrack.json`,
which requires the solver to backtrack four levels deep before finding a
valid solution.

## How it works

The resolver does a depth-first backtracking search:

1. Start from the root requirements.
2. For each unresolved package, try its versions from highest to lowest.
3. Picking a version adds its own dependencies to the list of things to
   satisfy.
4. If a later requirement conflicts with a version already chosen earlier,
   backtrack and try the next candidate for the package that caused the
   conflict.
5. If every candidate for a package fails, the search reports the most
   specific conflict it found.

This is the same family of algorithm real package managers used before
moving to SAT-based solvers for performance at scale (e.g., pip's newer
resolver, Cargo). Backtracking is simple to reason about and fine for
small-to-medium dependency graphs; it can blow up combinatorially on
pathological inputs, which is a known, intentional tradeoff for v1.

## Running tests

```bash
python -m pytest tests/
# or, without pytest installed:
python tests/test_solver.py
```

## Roadmap (v2 ideas)

- Real semver ranges (`^1.2.3`, `~1.2.3`) instead of basic comparators
- Conflict-driven clause learning / SAT-based solving for larger graphs
- Pull real dependency data from PyPI instead of synthetic JSON
- Caching / incremental re-resolution when only one constraint changes

## License

MIT
