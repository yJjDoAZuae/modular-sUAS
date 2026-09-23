# Python Coding Guidelines

Refer to [general.md](general.md) for project-wide standards on TDD, naming, units,
reproducibility, and architecture. This document covers Python-specific conventions.

---

## Language and Tooling

- **Python 3.13**, pinned by `.python-version` at the repo root.
- **Environments are managed with `uv`**, not conda and not bare `pip`. `pyproject.toml`
  and `uv.lock` are the definition; `uv sync` reproduces it.
- **Type hints are mandatory** on all public function signatures.
- `ruff` for linting **and** formatting (`ruff format` — the project does not use `black`;
  ruff's formatter is black-compatible and one tool is better than two).
- `mypy` for static type checking.
- `pytest` as the test framework.

### Running anything

```text
uv sync                                    # reproduce the environment
uv run python src/Fuselage/tools/<script>  # run a script
uv run python -m pytest                    # run tests -- see the note below, never bare `uv run pytest`
uv run ruff check .                        # lint
uv run ruff format .                       # format
uv run mypy src                            # type check
```

Do not call `pip`, do not activate `.venv` by hand, and do not add dependencies except
through `uv add` (`--dev` for tooling). The bare `python` command is not on `PATH` on the
development machine and hits a Microsoft Store shim.

### Environment caveats on this project

- The working tree is on a **UNC network share**, so uv cannot hardlink from its cache and
  falls back to copying. A first `uv sync` takes several minutes. That is expected, not a
  hang. `UV_LINK_MODE=copy` silences the warning.
- `pandas` is deliberately pinned `<3`. The inherited generator code was written against
  pandas 2.x, and 3.0 changes string dtype and copy-on-write defaults in ways that affect
  CSV reading. Revisit only once geometry regression tests exist to catch the difference.
- `OPENSCADPATH` must point at the OpenSCAD **binary directory**. uv cannot capture this;
  see [general.md](general.md#external-tool-dependencies).

---

## Naming Conventions (Python)

| Category | Convention | Example |
| --- | --- | --- |
| Classes | `PascalCase` | `BulkheadType`, `CowlDefinition` |
| Functions / Methods | `snake_case` | `run_bulkhead_parametric_sweep()` |
| Variables | `snake_case` | `corner_radius_m`, `panel_thickness_m` |
| Constants | `SCREAMING_SNAKE_CASE` | `SCAD_DIR`, `PARAM_DIR`, `OUTPUT_DIR` |
| Private attributes | `_snake_case` | `_here`, `_root` |
| Modules / Packages | `snake_case`, lowercase | `fuselage_variants.py` |
| Type aliases | `PascalCase` | `ParameterRow = dict[str, float \| str]` |

### Units and unit encoding in names

**New Python code is SI** — meters, seconds, kilograms, radians. Encode units when not
obvious from context:

```python
corner_radius_m: float
overhang_angle_rad: float
extrusion_width_m: float
```

Name the quantity you mean: that last field was called `nozzle_diameter` until IP-GEO-24,
while every use of it was a wall *N* extrusions thick. See
[general.md](general.md#units--si-is-the-project-standard).

**The existing OpenSCAD sweep code is millimeters and stays that way.** It is transitional —
roadmap Phase 3 replaces it with FreeCAD — so it is explicitly exempt from the SI standard.
Do not convert it, and do not rename its `_mm` identifiers. See
[general.md](general.md#-the-openscad-path-stays-in-millimeters-do-not-convert-it).

Which regime applies:

| Code | Units |
| --- | --- |
| `src/Fuselage/tools/` sweep path and everything it calls | millimeters, degrees |
| The FreeCAD port (Phase 3) | SI, converting at the FreeCAD boundary |
| Analysis, optimization, solvers, new standalone tooling | SI |

New SI code that consumes the sweep's output converts mm → m at its own boundary and names
the conversion. Do not reach into the sweep to change its regime.

The unit multiplier `U` is dimensionless — name what it scales, not `U` itself.

---

## Path Handling — The Most Important Rule Here

Every path must be anchored to the module's own location, never to the working directory.
See [general.md](general.md#anchor-every-path-to-__file__-never-to-the-working-directory)
for why: a previous sweep permanently baked a dead drive mapping into 1774 generated files.

Use `pathlib.Path` for new path code:

```python
from pathlib import Path

_HERE = Path(__file__).resolve().parent      # .../Fuselage/tools
_ROOT = _HERE.parent                          # .../Fuselage

PARAM_DIR = _ROOT / "variant_param"
SCAD_DIR = _ROOT / "scad"
INSERT_TABLE = _HERE / "threaded_insert_dimensions.csv"
```

The existing `os.path` usage in `fuselage_variants.py` is correct and does the same thing.
Match local style rather than converting a file wholesale mid-task; convert only when you
are already rewriting the surrounding code.

When emitting a path **into** generated geometry, always emit a relative path:

```python
def oml_ref(filename: str) -> str:
    """An OML mesh named the way cowl_geometry.scad will resolve it."""
    return "../oml/" + filename.replace("\\", "/").lstrip("/")
```

---

## Type Hints

- All public function signatures must have complete type hints.
- Use `from __future__ import annotations` for forward references.
- Use `dataclasses` for structured parameter objects.
- Prefer `Sequence` over `list` and `Mapping` over `dict` in signatures where read-only
  access is sufficient.
- Do not add `Any` to silence a checker — either type it honestly or leave it untyped and
  say why.

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CornerParameters:
    unit_width_mm: float
    corner_radius_mm: float
    longeron_radius_mm: float
    bolt_offset_mm: float
```

The inherited code passed parameters as loosely structured nested dicts. IP-GEO-16
replaced them with dataclasses — `Parameters`, `NoseParameters` and the twenty groups
below them in `fuselage_variants.py`. Follow that pattern; do not reintroduce a dict of
parameters.

The reason is assignment. A dict raises `KeyError` on a misspelled *read*, so lookups
were already safe, but it accepts a misspelled *write* in silence: the new key lands
beside the real field, the real field keeps its default, and the result is off by
exactly the amount the assignment was meant to apply. The conversion found a field that
had existed for exactly that reason — `bolt["diameter"]`, assigned and read for years,
never declared in the constructor.

**Use `@dataclass(slots=True)`, and treat it as load-bearing rather than a micro-
optimization.** A *plain* dataclass does not close the hazard above at all: instances
carry a `__dict__`, so `c.greeble.thicknes = 1.2` is accepted in silence exactly as the
dict was. `__slots__` removes that `__dict__` and turns the typo into an `AttributeError`
at the assignment.

This is not hypothetical. IP-GEO-16 converted the dicts to plain dataclasses and stated in
three places that misspelled writes now raised — they did not, and a script assigning a
renamed field went on silently using a default, producing parts 13–30 % wrong in volume
until a geometric check caught it. See IP-GEO-25.

---

## Enumerations

Use `enum.Enum` for closed sets of variants. No bare int or string magic values.

```python
from enum import Enum

class BulkheadType(Enum):
    NULL         = 0
    END          = 1
    INTERCONNECT = 2
    COWLING      = 3
    TAIL_BOOM    = 4
```

---

## Parameter Files

Parameter axes are CSV; shape definitions are JSON. Both are **inputs only** — nothing
round-trips, and there is no serialization framework in this project.

### Rules

- Convert imperial values to millimeters at the point the CSV is read. Never carry a
  mixed-unit value into geometry code.
- Validate at the read boundary, where the failing row is still identifiable — not deep in
  geometry code where the error message loses the row that caused it.
- A filename appearing in CSV or JSON *data* is a real dependency that static analysis
  cannot see. When a referenced file moves, the data must change in lockstep.
- Document any parameter file with more than ten columns using the `/schema` skill.

---

## Testing (Python)

Use **pytest**, for the tier of this codebase that pytest can actually reach: everything
importable in the project venv, under `src/Fuselage/tools/`. FreeCAD-dependent code under
`src/Fuselage/freecad/` is a separate tier, tested with `freecadcmd`-run `check_*.py`
scripts instead, because `FreeCAD`/`Part` are not importable from the venv pytest runs in.
See [general.md](general.md#two-test-tiers-because-two-python-interpreters-are-involved)
for the full split and [general.md](general.md#testing-geometry-generators) for the
geometry testing rules — they matter more than the mechanics below.

### Structure

```python
# tests/test_corner_geometry.py

import pytest
from fuselage_variants import standard_values

@pytest.fixture
def baseline_params() -> dict:
    return standard_values()


class TestCornerGeometry:

    def test_corner_scales_with_unit_multiplier(self, baseline_params) -> None:
        """A U=2 corner is twice the width of a U=1 corner."""
        ...

    def test_fillet_radius_never_exceeds_wall(self, baseline_params) -> None:
        """Regression: U=0.5 with a 3/16in panel produced a self-intersecting fillet."""
        ...
```

### Rules — Testing

- Test names: `test_<subject>_<condition>_<expected>`.
- Assert on **measured model properties** — bounding box, dimensions, volume, feature
  presence — never on byte-identical `.scad` or `.stl` output.
- Use `pytest.approx` with a tolerance meaningful at millimeter scale for all
  floating-point comparisons.
- Tests operate on a **single parameter combination**. Never run the full factorial sweep
  from a test: it is expensive and it overwrites `variant_output/`.
- Every bug fixed in the sweep gets a regression test pinning the parameter combination
  that exposed it, with the combination named in the docstring.
- Tests are independent; fixtures handle setup.
- `pythonpath` is set in `pyproject.toml` so tests can import the generator modules.

`src/Fuselage/tools/test_fuse.py` — a three-line scratch file that was never a test
suite — was deleted 2026-09-22 when `tests/` was stood up for real ([IP-TEST-1](../implementation/test_coverage.md)).

**Run tests as `uv run python -m pytest`, never bare `uv run pytest`, on this machine.**
The bare form fails with `ImportError: ... numpy ... DLL load failed while importing
_multiarray_umath: The parameter is incorrect`. Root cause, confirmed 2026-09-22: the venv
lives on a network share (`\\mrhorse\Archive\...`), and `uv run pytest` executes the
compiled console-script stub `.venv/Scripts/pytest.exe` directly. That stub resolves its
own interpreter path in Windows' extended-length UNC form
(`\\?\UNC\mrhorse\Archive\...\python.exe` — visible in the failing import's own
self-report), and numpy's Windows DLL loader calls `os.add_dll_directory()` on its install
path at import time, which Win32's `AddDllDirectory()` rejects for any path beginning with
`\\?\` (`ERROR_INVALID_PARAMETER`, exactly the "parameter is incorrect" text). `uv run
python -m pytest` invokes `python.exe` with `-m` instead of going through the compiled
stub, never produces the `\\?\` form, and imports numpy cleanly. This is narrow to
packages that register a DLL directory at import (numpy, and transitively pandas) —
`uv run ruff` and `uv run mypy` are unaffected, so this is not a reason to avoid `uv run`
for other console scripts, only for anything that imports numpy/pandas from this venv.

A second, separate network-share issue: pytest's cache plugin cannot atomically write
`.pytest_cache` here (`WinError 6`/`5`), and silently leaves an orphaned, undeletable
`pytest-cache-files-<random>/` directory at the repo root on every run — deleting one fails
client-side with "access is denied"/"the handle is invalid" via `rm`, PowerShell
`Remove-Item -Force`, and `cmd rmdir`, consistent with a stuck server-side SMB lock rather
than anything fixable here. `pyproject.toml`'s `addopts` disables the cache plugin
(`-p no:cacheprovider`), so this no longer happens; nothing in this project's workflow uses
`--lf`/`--ff`/`--cache-clear`, so there is no cost to that.

---

## Code Style

- Indentation: **4 spaces** (no tabs).
- Line length: **100 characters**, configured in `pyproject.toml`.
- Use `ruff format` for formatting and `ruff check` for linting.
- Import order (handled by ruff's `I` rules): standard library → third-party → local.
- Do not reformat files you were not asked to touch — it buries the real diff.

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "SIM", "PTH", "RET"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src/Fuselage/tools"]
```

---

## Docstrings

Public modules and functions must have docstrings.

**Docstrings state *why*, not what the code plainly says.** The best examples in this
codebase record the constraint that forced the design and the evidence for it — see
`oml_ref()` and `relativize_scad_references()` in `fuselage_variants.py`, which document
tested path-resolution behavior and the specific failure that motivated the code. Match
that standard.

```python
def oml_ref(filename: str) -> str:
    """An OML mesh named the way cowl_geometry.scad will resolve it.

    The `import()` call lives in scad/cowl_geometry.scad, and OpenSCAD resolves
    import() against the file containing the call -- not the root document and
    not the working directory.

    Kept relative rather than absolute on purpose: an absolute path is what put
    a long-dead `R:\\` drive mapping into every file the 2025-09-22 sweep wrote.
    """
```

Use Google style for parameter documentation where a function's arguments are not
self-evident from their names and types.

---

## Error Handling

- Raise specific exceptions (`ValueError`, `TypeError`, `RuntimeError`, `FileNotFoundError`)
  with messages that name the failing parameter combination or file.
- Use `ValueError` for bad parameter data; `FileNotFoundError` for an unresolvable
  reference; `RuntimeError` for an external tool failing.
- **Never catch bare `Exception` to keep a sweep running.** A swallowed geometry failure
  produces a silently wrong part file. Let it raise, or catch the specific exception and
  record the failed combination explicitly.
- Validate at public boundaries; trust internal calls within the module.
- An unset required environment variable must fail with a named, actionable error — not
  with a `TypeError` from `os.path.join(None, ...)` deep inside a render call.

---

## Notebooks (Jupyter)

Notebooks are for analysis and visualization only — not for production code.

- All production logic lives in `src/Fuselage/tools/`, not in notebooks.
- Notebooks import the generator modules like any other consumer.
- Notebooks are not subject to the same coverage requirements but must follow naming and
  unit conventions.
- Clear cell outputs before committing. Note that `src/Fuselage/tools/test_fuse.ipynb` is
  currently tracked — check its outputs are clean before editing it.
