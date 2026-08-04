# General Coding and Development Guidelines

## Development Philosophy

### Project Lifecycle Phase

modular-sUAS is in **initial development**, and additionally in an **adoption** phase: the
Python generators and OpenSCAD geometry under `src/Fuselage/` were copied in from another
repository and are being brought up to standard here. Every interface, parameter file, and
output convention is subject to change without notice.

Consequences for the current phase:

| Rule | Rationale |
| ---- | --------- |
| **Never add backward-compatibility shims** — when an interface changes, update every call site directly and delete the old form completely. | No external consumers exist. Compatibility layers are dead weight. |
| **Never reference a previous design in documentation or comments** — describe only the current state. | History lives in version control. Stale design notes mislead future readers. |
| **Generated output is disposable; hand-authored geometry is not.** | `variant_output/` is regenerable by re-running the sweep. `parts/`, `cad/`, and `blender/` contain irreplaceable hand-modeled work. |

Note on the adoption phase specifically: code copied in from the source repository may
contain comments and docstrings that reference commits, paths, or decisions from *that*
repository's history, which did not come across. Treat such references as unverified until
checked against this repository.

---

### Test-Driven Development (TDD)

New functionality follows the **Red-Green-Refactor** cycle:

1. **Red** — Write a failing test that defines the desired behavior.
2. **Green** — Write the minimal code required to pass the test.
3. **Refactor** — Clean up the implementation without changing behavior, keeping all tests green.

Rules:

- No production code is written without a failing test that motivates it.
- Each test covers exactly one behavior or requirement.
- Tests must be fast, isolated, repeatable, and self-validating.
- Aim for a test pyramid: many unit tests, fewer geometry tests, few full-sweep tests.

**Adoption-phase exception.** The inherited generator code has no test suite, and writing
tests for it requires a way to generate a single part in isolation — which does not exist
yet (`main()` runs the entire full-factorial sweep). Until that entry point exists, TDD
applies to *new* code; retrofitting tests onto inherited code is tracked as roadmap Phase 1
work, not treated as a precondition for every edit.

### Testing geometry generators

Geometry code cannot be tested the way ordinary functions can. The rules that matter here:

- **Assert on measured model properties**, never on byte-identical `.scad` or `.stl` output.
  Generated output is not stable across library versions, floating-point rounding, or
  facet-count settings. Assert on bounding box, overall dimensions, volume, triangle count
  within a tolerance, and the presence or absence of a feature.
- **Never verify by running the full sweep.** It is expensive and it overwrites
  `variant_output/`. Tests operate on a single parameter combination.
- **Pin the parameter combination** that exposed any bug you fix, as a regression test.
- Floating-point comparisons use an explicit tolerance appropriate to the geometry —
  an explicit tolerance meaningful at the scale of the feature being measured. At SI scale a
  part dimension is order 0.1 m and a print tolerance is order 1e-4 m, so a default relative
  tolerance is usually wrong — state the absolute tolerance.

### SOLID Principles

| Principle | Summary |
| --- | --- |
| Single Responsibility | A module or function has one reason to change. |
| Open/Closed | Open for extension, closed for modification. |
| Liskov Substitution | Subtypes must be substitutable for their base types. |
| Interface Segregation | Prefer narrow, focused interfaces over wide ones. |
| Dependency Inversion | Depend on abstractions, not concretions. |

---

## Naming Standards

Clear, unambiguous naming is mandatory. Names must communicate intent without requiring a comment.

### General Rules

- Names must be descriptive and self-documenting.
- Abbreviations are forbidden. The only permitted abbreviations are those that are the
  canonical name in this domain: `oml` (outer mold line), `maus` (Modular Airframe Unitized
  System), `fos` (Fuselage Outer Standard), `suas` (small uncrewed aircraft system), `stl`,
  `csg`, `vsp` (OpenVSP), `cad`, `fem`. The unit multiplier `U` is an established project
  symbol and is permitted. All other abbreviations are forbidden, including informal
  shorthand (`bulk`, `param`, `tmp`, `geom`) and single-letter identifiers.
- Boolean names must read as a predicate: `is_anchor`, `has_boom`, `can_print_unsupported`.
- Names must not encode type information (no Hungarian notation).
- Acronyms are treated as words in `PascalCase` identifiers: `OmlMesh`, not `OMLMesh`.

### Naming by Category

| Category | Convention | Example |
| --- | --- | --- |
| Python classes / types | `PascalCase` | `BulkheadType`, `CowlDefinition` |
| Python functions / variables | `snake_case` | `run_bulkhead_parametric_sweep()`, `corner_radius` |
| Python constants | `SCREAMING_SNAKE_CASE` | `SCAD_DIR`, `PARAM_DIR` |
| Python private attributes | `_snake_case` | `_here`, `_root` |
| Python modules / packages | `snake_case`, lowercase | `fuselage_variants.py` |
| OpenSCAD modules and functions | `snake_case` | `fuselage_corner_geometry()` |
| OpenSCAD file names | `snake_case.scad` | `shape_modifier_utils.scad` |
| Parameter CSV columns | `snake_case`, `VID_` prefix for the variant ID | `VID_bulkhead_type`, `bulkhead_type_name` |
| Test files | `test_<module>.py` | `test_fuselage_variants.py` |

### Unit Encoding in Names

When units are not obvious from context, encode them in the name:

```python
corner_radius_m: float
overhang_angle_rad: float
nozzle_diameter_m: float
```

The unit multiplier `U` is dimensionless — name what it scales, not `U` itself.

---

## Units — SI Is the Project Standard

**Every internally stored value uses SI base units: meters (m), seconds (s), kilograms
(kg), and radians (rad).**

This applies to every variable, field, parameter, function argument, and return value in
the project. Non-SI units exist **only at the immediate file interface** — the narrow layer
that reads a parameter file or writes a geometry file — and never propagate inward.

| Quantity | Unit | Symbol |
| --- | --- | --- |
| Length / distance | meter | m |
| Angle | radian | rad |
| Time | second | s |
| Mass | kilogram | kg |
| Area | square meter | m² |
| Volume | cubic meter | m³ |
| Force | newton | N |
| Pressure / stress | pascal | Pa |
| Density | kilogram per cubic meter | kg/m³ |

### The file interface — where conversion is allowed

Conversion happens at exactly these boundaries, and nowhere else:

| Boundary | Direction | Conversion |
| --- | --- | --- |
| Reading a parameter CSV or shape JSON | in | Declared unit → m, rad |
| Emitting `.scad` source | out | m → mm, rad → deg |
| Reading or writing STL / 3MF | both | m ↔ mm |
| FreeCAD scripting (Phase 3) | both | m ↔ mm; FEM additionally N/mm² ↔ Pa |
| Display, reports, drawings | out | m → whatever the reader needs |

**Exported meshes must be in millimeters.** STL and 3MF carry no unit metadata — a slicer
interprets the numbers as millimeters, full stop. An STL exported in meters loads as a part
1/1000 of its intended size and is silently unprintable. This is a hard output requirement,
not a convention that can be revisited.

So the emission layer scales SI → mm on the way out, and that conversion belongs in **one
named function** in the render path, not scattered through geometry code. Round-trip any
mesh the project re-imports (the OML meshes in `oml/` are millimeters on disk) back to SI on
the way in.

FreeCAD's FEM stack works in mm/N/MPa, which is internally self-consistent
(`1 MPa = 1 N/mm²`). Treat that whole stack as file-interface: convert to SI on the way out
of it, and never let mm/MPa values into project code.

### Enforcement

- Variable names **should** encode units when not obvious: `corner_radius_m`,
  `overhang_angle_rad`.
- Imperial parameter axes exist (`imperial` panel variants, fractional-inch panel
  thicknesses). Convert to meters **at the point the CSV is read**, and carry only SI
  thereafter. Never propagate a mixed-unit value inward.
- Conversion helpers live in one module. Never call a conversion function inside geometry
  or analysis code — if you need one there, the boundary is in the wrong place.
- The unit multiplier `U` is dimensionless; what it scales is in meters.

### Scope — what this standard governs, and what it does not

The SI standard above applies to:

- **All new code**, from the first line.
- **The FreeCAD port** (roadmap Phase 3), which is new code and is where the standard
  actually lands across the geometry pipeline.
- **Analysis, optimization, and solver work** in any language.
- **Any future refactoring target** — when a module is genuinely rewritten, it comes back SI.

It does **not** apply to the existing OpenSCAD generator path.

### ⚠ The OpenSCAD path stays in millimeters. Do not convert it.

The generators copied in from the source repository work in **millimeters throughout** —
`standard_values()` returns `unit_width = 100`, `corner_radius = 10`, `nozzle_diameter =
0.4`, and every parameter axis CSV is populated to match.

That is a **deliberate exemption, not technical debt.** The OpenSCAD implementation is
transitional: Phase 3 replaces it with Python-driven FreeCAD. Converting code that is
scheduled for replacement spends real risk for no benefit — the unit regime is load-bearing
across Python, every `.scad` module, every CSV axis, and every JSON shape definition at
once, and a partial conversion produces geometry that is wrong by a factor of 1000 in one
dimension, renders cleanly, and exports without error.

**Rules:**

- **Never convert existing sweep code to SI**, as a task or as a side effect of one.
- **Do not "fix" a `_mm` name to `_m`** in that code. The name is accurate; the value really
  is millimeters.
- New code that *consumes* the sweep's output converts mm → m at its own boundary and says
  so, rather than reaching in and changing the source.
- When touching an inherited file, state its unit regime in a comment at the top rather
  than assuming a reader will know.

The divergence is recorded in the roadmap so it reads as a decision rather than an
oversight.

---

## Parametric Generation — Reproducibility Rules

These rules are specific to this project and exist because each has already caused a real
failure.

### Anchor every path to `__file__`, never to the working directory

`solid2.import_scad()` resolves a bare filename against the process working directory and
then calls `.absolute()` unconditionally. That absolute path becomes what is written into
generated `.scad` files as `use <...>`. A previous sweep, run from a mapped drive, baked a
now-dead `R:\` path into all 1774 files it produced — none of them can be re-rendered.

- Anchor every input path to the module's own location.
- Generated geometry must contain **relative** references only.
- A sweep must produce identical output regardless of the directory it is launched from.

### Resolution rules that are easy to get wrong

| Mechanism | Resolves against |
| --- | --- |
| `include <x.scad>` / `use <x.scad>` | The directory of the **including file** |
| `import("mesh.stl")` | The directory of the file containing the `import()` call, then the root document's directory — **not** the working directory |
| `solid2.import_scad("x.scad")` | The process working directory, then `OPENSCADPATH` |

A duplicate mesh left anywhere on the search path will **silently shadow** the intended one.
Never leave a stale copy.

### Data-level file references

Some filenames live in *data*, not code: a `*_type_variants.csv` row names a JSON by
filename, and that JSON names an OML mesh by filename. Code and data must change in
lockstep. These couplings are invisible to static analysis and break silently — document
them in the relevant schema document.

### External tool dependencies

The generators shell out to the OpenSCAD binary, located via the `OPENSCADPATH` environment
variable. Note that this is a **non-standard use** — `OPENSCADPATH` is normally OpenSCAD's
library search path, but here it holds the binary directory and `solid_render()` depends on
that. Do not "correct" it without changing the call sites.

Environment requirements that a package manager cannot capture must be documented and
validated with a clear error, never left to fail with an obscure exception deep in a sweep.

---

## Error Handling

- Raise specific exceptions with descriptive messages that name the failing parameter
  combination or file.
- **Never catch bare `Exception` to keep a sweep running.** A geometry failure that gets
  swallowed produces a silently wrong part file, which is worse than a crash. Let it raise,
  or catch the specific exception and record the failed combination explicitly.
- Validate parameters where they are read from CSV or JSON, not deep inside geometry code
  where the error message loses the row that caused it.
- Do not silence exceptions with bare `except:` clauses.

---

## Architectural Design Patterns

### Separation of Concerns

The generator toolchain is structured in layers, each with one responsibility:

```text
┌──────────────────────────────────────────────┐
│  Parameter layer (CSV axes, shape JSON)       │  ← unit conversion lives here
├──────────────────────────────────────────────┤
│  Sweep layer (Python: iterate, name, write)   │
├──────────────────────────────────────────────┤
│  Geometry layer (OpenSCAD modules)            │  ← millimeters — see note
├──────────────────────────────────────────────┤
│  Render layer (OpenSCAD binary, STL/PNG out)  │
└──────────────────────────────────────────────┘
```

The geometry layer is OpenSCAD source, which is conventionally millimeters. That makes the
**sweep layer's emission step the file interface**: it converts SI to millimeters on the way
into generated `.scad`, in one named function. Everything above that line is SI.

- Geometry modules take parameters and produce shapes. They do no file I/O and know nothing
  about sweeps.
- Sweep functions handle iteration, naming, and output paths. They contain no geometry
  construction.
- Prefer pure functions that take parameters and return values. Reserve side effects (file
  writes, subprocess calls) for thin, clearly named boundary functions.

### Parameter passing

Parameters currently travel as loosely structured nested dicts assembled in Python. Making
this contract explicit is roadmap Phase 2 work. Until then, do not deepen the coupling:
new code should take explicit named parameters rather than reaching further into the dict.

---

## External Dependencies and Licensing

### License Policy

**Default to permissive open-source libraries.**

| License | Notes |
| --- | --- |
| MIT | Preferred. |
| BSD-2/3-Clause, Clear BSD | Preferred. |
| Apache 2.0 | Preferred. Includes explicit patent grant. |
| ISC | Preferred. Functionally equivalent to MIT. |
| LGPL (any) | Acceptable for a separate-process tool; avoid for linked libraries. |
| GPL (any) | Avoid for libraries. Note that OpenSCAD and FreeCAD are themselves GPL/LGPL applications invoked as **separate processes**, which does not propagate to this project's code. |
| Proprietary | Avoid unless no open-source alternative exists and explicit approval is obtained. |

### Dependency Selection Criteria

1. **License** — must be permissive (see above).
2. **Maintenance** — active development or stable/complete.
3. **Minimal footprint** — prefer focused, single-purpose libraries.
4. **Source availability** — prefer source-distributed libraries over binary blobs.

Python dependencies are managed with **uv** and declared in `pyproject.toml`. See
[python.md](python.md).

---

## Code Review Standards

Review checklist:

- [ ] Tests present and meaningful, asserting on measured properties rather than exact output
- [ ] Naming follows standards
- [ ] SI (m, s, kg, rad) used throughout internal code; imperial and millimeter values converted at the file interface only
- [ ] Exported STL/3MF is in millimeters — verify by measuring, not by inspection
- [ ] Every path anchored to `__file__`; no working-directory dependence
- [ ] Generated geometry contains relative references only — no absolute paths
- [ ] No bare `except:` and no `except Exception` that swallows a geometry failure
- [ ] Data-level file references (CSV → JSON → mesh) updated in lockstep
- [ ] No hardcoded magic numbers (use named constants)
- [ ] No backward-compatibility shims, deprecated aliases, or forwarding wrappers
- [ ] New dependency license is permissive and declared in `pyproject.toml`
- [ ] No full-sweep run required to verify the change

---

## Version Control

- **Claude does not commit.** Alex performs all commits, merges, and pushes. Claude uses
  read-only git only. See [CLAUDE.md](../../../CLAUDE.md) for the full rule.
- Commit messages use imperative mood: "Anchor sweep paths to `__file__`" not "Anchored…".
- Each commit is self-contained and leaves the repository in a runnable state.
- Do not commit commented-out code. Delete unused code; version control preserves history.
- Never commit regenerable output: `variant_output/`, `variant_output_original/`,
  `tools/test_fuse_output/`, `__pycache__/`, `.venv/`.
- Do commit hand-modeled geometry. Note that the stock Python `.gitignore` template's
  `parts/` and `lib/` rules silently match `src/Fuselage/parts/` and would exclude
  irreplaceable CAD — verify with `git check-ignore -v` before assuming a file is tracked.

---

## Documentation and Math Formatting

### LaTeX / KaTeX in Markdown

All documentation math is rendered by KaTeX. KaTeX does not support arbitrary Unicode
inside math mode — non-ASCII characters embedded raw in math expressions cause render
errors.

**Rule: never embed non-ASCII characters inside a math span (`` $…$ `` or `$$…$$`),
including inside `\text{}` and `\mathrm{}` blocks.**

| Instead of (raw Unicode) | Use (KaTeX command) |
| --- | --- |
| `\text{mm²}` | `\text{mm}^2` |
| `\text{mm³}` | `\text{mm}^3` |
| `\text{N·mm}` | `\text{N}{\cdot}\text{mm}` |
| `\text{45°}` | `45^\circ` |

The pattern is: break `\text{}` around the special character and replace the character
with its KaTeX counterpart (`{\cdot}`, `^2`, `^3`, `^\circ`, subscripts, Greek letters).

Non-ASCII characters are allowed in **plain prose** (outside math spans): writing "mm³" or
"45°" in a sentence or table cell is fine because it is rendered as HTML, not processed by
KaTeX.

### Markdown Lint Standards

All documentation files should be free of markdownlint warnings before being presented for
review.

**Disabling rules is not permitted.** Fix the underlying formatting issue. The only rule
disabled project-wide is MD013 (line length), because the 80-character default is
unworkable for tables — suppress it in `.markdownlint.json`, not inline.

| Rule | Description | Fix |
| --- | --- | --- |
| MD024 | No two headings may have identical text | Make headings unique |
| MD031 | Fenced code blocks must be surrounded by blank lines | Add a blank line before the opening fence and after the closing fence |
| MD032 | Lists must be preceded and followed by a blank line | Add a blank line before the first list item |
| MD040 | Fenced code blocks must declare a language | Add a specifier: ` ```python `, ` ```scad `, ` ```text `, ` ```mermaid ` |
| MD060 | Table separator rows must use spaced pipes | Use `\| --- \| --- \|` — never `\|---\|---\|` |
| Mermaid syntax | Diagrams must use valid Mermaid edge syntax | Use `-- "label" -->` for labeled directed edges |

**Canonical lint tool (run from the repo root):**

```text
npx markdownlint-cli2 "doc/**/*.md"
```

### Numerical Substitution in Derivations

Substitute numerical values for constants only in **worked examples** — never in derivation
steps or general formulae. Premature substitution obscures the mathematical structure and
makes the formula inapplicable to other parameter regimes.

- **Derivation:** keep symbols — $w = U \cdot w_{\mathrm{unit}}$
- **Example:** substitute — $w = 0.150\,\text{m}$ at $U = 1.5$, $w_{\mathrm{unit}} = 0.100\,\text{m}$

### Document types and where they live

| Type | Location | Skill |
| --- | --- | --- |
| Roadmap | `doc/roadmap.md` | `/roadmap` |
| Architecture | `doc/architecture/` | `/arch` |
| Module design | `doc/design/` | `/design` |
| Algorithms | `doc/algorithms/` | `/algo` |
| Parameter schemas | `doc/schemas/` | `/schema` |
| Implementation plans | `doc/implementation/` | `/impl` |
| Open questions | inside design documents | `/oq` |
| Coding guidelines | `doc/guidelines/` | — |

Narrative design rationale lives in the **wiki**, a separate repository
(`modular-sUAS.wiki`). The wiki is not a design authority: where it and a design document
disagree, the design document wins and the wiki is corrected.
