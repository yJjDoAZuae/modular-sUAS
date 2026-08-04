# OpenSCAD Coding Guidelines

Refer to [general.md](general.md) for project-wide standards on naming, units,
reproducibility, and architecture. This document covers OpenSCAD-specific conventions.

OpenSCAD geometry in `src/Fuselage/scad/` is the **source of truth** for part shape. When
Python and OpenSCAD disagree about a shape, fix the `.scad` module, not the Python that
calls it.

---

## Toolchain

- **OpenSCAD 2021.01** on the development machine, invoked as a separate process.
- Located via the `OPENSCADPATH` environment variable, which on this project holds the
  **binary directory** — a non-standard use that `solid_render()` depends on. See
  [general.md](general.md#external-tool-dependencies).
- Driven from Python through `solid2` (distribution name `solidpython2`), which generates
  `.scad` source and then shells out to render `.stl` and `.png`.

Hand-authored modules are written directly in OpenSCAD. Generated files (anything in
`variant_output/`, and any `*.stl.scad`) are disposable output — never edit them.

---

## File Organization

All hand-authored `.scad` files currently live as siblings in `src/Fuselage/scad/`, so
every `include`/`use` is a bare filename. **This is why they resolve at all.** Moving any
module into a subdirectory requires editing every include line that references it.

Two kinds of file live there, and the distinction should be preserved:

| Kind | Naming | Contains |
| --- | --- | --- |
| Geometry library | `*_geometry.scad`, `shape_modifier_utils.scad` | Reusable modules and functions; no top-level geometry |
| Part driver | `fuselage_corner.scad`, `nose_cowl.scad` | A single top-level part, built by calling library modules |

A library file must not emit geometry at the top level. A driver file emits exactly one
part.

---

## Path Resolution

These rules are verified behavior, not assumptions. Getting them wrong fails silently.

| Mechanism | Resolves against |
| --- | --- |
| `include <x.scad>` / `use <x.scad>` | The directory of the **including file** |
| `import("mesh.stl")` | The directory of the file containing the `import()` call, then the root document's directory — **not** the working directory |

Consequences:

- A mesh imported by `scad/cowl_geometry.scad` is referenced as `../oml/vsp_nose.stl` —
  relative to `cowl_geometry.scad`, not to whatever document is being rendered.
- **Shadowing is real.** When the same mesh exists in both the library directory and the
  root document's directory, the library directory wins. Never leave a stale duplicate.
- Never write an absolute path into a `.scad` file. See
  [general.md](general.md#anchor-every-path-to-__file__-never-to-the-working-directory).

---

## Naming

| Category | Convention | Example |
| --- | --- | --- |
| Modules | `snake_case` | `fuselage_corner_geometry()` |
| Functions | `snake_case` | `bolt_circle_radius()` |
| Parameters | `snake_case`, unit-suffixed where not obvious | `corner_radius_mm` |
| Files | `snake_case.scad` | `shape_modifier_utils.scad` |
| Special variables | OpenSCAD's own (`$fn`, `$fa`, `$fs`) | — |

Abbreviations follow [general.md](general.md#general-rules). `oml`, `stl`, and the unit
multiplier `U` are permitted; `bulk`, `geom`, and `tmp` are not.

---

## Module Interface

- **Every parameter gets a default.** A module that cannot be rendered standalone cannot be
  inspected or debugged in the OpenSCAD GUI.
- Group related parameters in the signature in a stable order: size, then feature toggles,
  then cosmetic.
- Prefer explicit named parameters over passing large vectors of unlabeled numbers.
- Boolean parameters read as predicates: `is_anchor`, `make_vert_web`.
- Document the parameter units in a comment above the module — OpenSCAD has no type system
  and no docstrings, so the comment is the only contract.

```scad
// Corner post for one MAUS fuselage unit.
// Units: millimetres and degrees (this is the file interface; callers work in SI).
//   unit_width_mm    : outer width of the unit cube
//   corner_radius_mm : outer fillet radius
//   is_anchor        : true to add threaded-insert bosses
module fuselage_corner(unit_width_mm = 100, corner_radius_mm = 10, is_anchor = false) {
    ...
}
```

The `_mm` and `_deg` suffixes are **mandatory** on every dimensional parameter in `.scad`,
precisely because this path diverges from the project's SI standard. A bare `corner_radius`
is ambiguous at exactly the boundary where ambiguity costs a factor of 1000. Note that much
inherited code does not carry these suffixes yet — add them when you are already editing a
signature, not as a sweep of its own.

---

## Geometry Practice

- **Millimetres and degrees throughout — the whole OpenSCAD path, not just the `.scad`.**
  OpenSCAD is nominally unitless, but `rotate()` takes degrees and every slicer reads an
  exported mesh as millimetres, so `.scad` is fixed to mm/deg. The Python sweep code that
  drives it is millimetres too.

  The project standard elsewhere is SI — see
  [general.md](general.md#units--si-is-the-project-standard) — but **this path is explicitly
  exempt.** It is transitional: roadmap Phase 3 replaces it with Python-driven FreeCAD, and
  SI arrives there, in new code. Do not convert this path, and do not "fix" a `_mm` name to
  `_m`; the name is accurate.

  New code that consumes this path's output converts mm → m at its own boundary rather than
  reaching in and changing the source.

  Exported STL and 3MF **must** be millimetres regardless of what the rest of the project
  does. Those formats carry no unit metadata; a mesh exported in metres loads at 1/1000
  scale and is silently unprintable.
- Build parts from named intermediate modules rather than one deeply nested
  `difference()`/`union()` expression. A reader must be able to render any intermediate
  stage on its own.
- **Avoid coincident faces in booleans.** Subtracting a cut that exactly meets a surface
  produces zero-thickness geometry and unpredictable rendering. Overshoot the cut by a
  small epsilon and name the constant.
- Keep `$fn` out of module bodies. Facet resolution is a render-time decision set globally
  by the caller (`solid2.set_global_fn/fa/fs`), not baked into geometry.
- Parameterize against the unit multiplier `U` rather than hardcoding sizes, so a module
  works across the whole size sweep.

---

## Printability

Geometry must be printable in the orientation the part is intended to print in. Record that
orientation in the module design document, not only in the slicer project.

- Respect the maximum unsupported overhang angle; state the assumed value where a feature
  depends on it.
- Minimum feature size is a multiple of nozzle diameter — do not emit a wall thinner than
  the extrusion width.
- Bridges and holes that print unsupported need a deliberate shape (teardrop, chamfered
  lead-in), not a circle that sags.
- The nozzle diameter and layer height are parameters (`null_printer_settings()` in the
  Python side), not constants baked into geometry.

---

## Validation and Rendering

- Syntax-check before rendering; render before generating a sweep.
- **Do not trust the OpenSCAD MCP's `validate_scad`** on this machine — it reports
  `valid: false` with an empty error list for everything, including a bare cube. Its
  render, analyze, and export tools also fail because the server's temp directory resolves
  to a UNC path. See [CLAUDE.md](../../../CLAUDE.md) for the current status. Until that is
  fixed, invoke `openscad.exe` directly with a local temp directory.
- Verify geometry by **measured properties** — bounding box, dimensions, volume — not by
  eye. See [general.md](general.md#testing-geometry-generators).

---

## Things That Silently Produce Wrong Geometry

Each of these has caused a real failure in this project or is a documented OpenSCAD trap:

- An SI value reaching a `.scad` module without conversion — the part renders at 1/1000
  scale, and an STL exported that way is silently unprintable rather than obviously broken.
  Most likely when new SI code calls into this millimetre path.
- An absolute path in a generated `use <...>` — unrenderable once the drive mapping changes.
- A stale duplicate mesh shadowing the intended one.
- A mesh filename changed in the `.scad` driver but not in the matching
  `variant_param/*.json`, which carries the same name as data.
- Coincident faces in a boolean, producing zero-thickness shells that slice unpredictably.
- An undefined variable, which OpenSCAD treats as `undef` and propagates silently rather
  than erroring — this is how the nose and tail sweeps broke.
