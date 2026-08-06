# Geometry Refactor — Implementation Plan

**Scope:** Deduplication, interface, and robustness work on the OpenSCAD geometry
modules and the Python that drives them, from a review of `src/Fuselage/scad/*.scad`
and `fuselage_variants.py` on 2026-08-06. Every item is behaviour-preserving: the
generated geometry must not change, and each item states how that is proven.

This is roadmap [Phase 2](../roadmap.md) work — "Refactor and improve the OpenSCAD
implementation" — and it is unblocked because Phase 1 delivered the verification it
depends on (`mesh_stats.py`, `sweep_check.py`).

**Design authority:** None yet. The findings below are the authority; a `doc/design/`
document for the bulkhead and corner modules would be the proper home and is item
IP-GEO-11.

**Last updated:** 2026-08-06

---

## Work Items

| ID | Status | Title | Depends on |
| --- | --- | --- | --- |
| IP-GEO-1 | done | `.scad`-text snapshot harness — [`scad_snapshot.py`](../../src/Fuselage/tools/scad_snapshot.py) | — |
| IP-GEO-2 | todo | Convert the five `scad_module` call sites from positional to keyword arguments | IP-GEO-1 |
| IP-GEO-3 | todo | Resolve the greeble-thickness formula duplicated between Python and commented-out SCAD | IP-GEO-1 |
| IP-GEO-4 | todo | Hoist `import math` to module level; name the hardcoded "fixed parameters" | — |
| IP-GEO-5 | todo | Use the existing `mirror_xy()` at the three open-coded sites in `fuselage_corner_geometry.scad` | IP-GEO-1 |
| IP-GEO-6 | todo | Extract `octant_tiled()` to replace four structurally identical wrapper modules | IP-GEO-1 |
| IP-GEO-7 | todo | Extract greeble dimensions (`greeble_radius`, `greeble_nub_radius`, `greeble_nub_height`, `longeron_chamfer`) as SCAD functions | IP-GEO-1 |
| IP-GEO-8 | todo | Single shared `eps`, replacing the per-module redeclarations | IP-GEO-1 |
| IP-GEO-9 | todo | Named helper for oversized cutting solids, replacing ad-hoc `3*bulkhead_thickness` / `2*corner_radius` multipliers | IP-GEO-1 |
| IP-GEO-10 | blocked (IP-GEO-2) | Group parameters so `bulkhead_section_full` takes ~8 arguments instead of 28 | IP-GEO-2 |
| IP-GEO-11 | todo | Write `doc/design/bulkhead.md` and `doc/design/corner.md` to give this work a design authority | — |

> **IP-GEO-10 blocked reason:** Regrouping 28 positional parameters is the change most
> able to silently transpose two same-typed floats. Keyword arguments (IP-GEO-2) make
> each move checkable at the call site and turn a mistake into a `TypeError`, so that
> lands first.

---

## Findings behind each item

### IP-GEO-2 — positional arguments (highest value)

`bulkhead_render` passes **28 positional floats** to `bulkhead_section_full`;
`corner_render` passes 14. OpenSCAD has no types, so transposing two arguments yields
valid-looking geometry that is silently wrong.

Verified that solid2 accepts keyword arguments, emits **byte-identical** output,
is order-independent, and raises `TypeError` on a misspelled name. The generated
`.scad` already reads `fuselage_corner(U = 4.0, ...)`, so solid2 has always known the
parameter names — only the Python call sites are positional.

### IP-GEO-3 — a formula duplicated across the language boundary, and the copies disagree

`fuselage_variants.py` computes, under a comment reading *"recreate derived dimensions
from corner_end()"*:

```python
greeble_thickness = max(2*math.sqrt(U)*nozzle_diameter, 2*nozzle_diameter)
```

while `fuselage_corner_geometry.scad` carries the commented-out original:

```scad
//    greeble_thickness = max(2*U*nozzle_diameter, 2*nozzle_diameter);
```

`2*U` against `2*sqrt(U)`. The dead code is not merely dead — re-enabling it would
silently change every part. Delete it, or make one side authoritative and have the
other read from it.

### IP-GEO-5 — a library function that exists and is not used

`shape_modifier_utils.scad` defines `mirror_xy()` as exactly
`union() { children(); mirror([1,-1,0]) children(); }`.
`fuselage_corner_geometry.scad` open-codes that union three times, at lines 34-39,
97-102, and 140-145.

### IP-GEO-6 — four structurally identical wrappers

`bulkhead_oml_shape`, `bulkhead_oml_outer_shape`, `bulkhead_oml_inner_shape`, and
`bulkhead_web_inner_shape` (lines 711-749) share one body, differing only in which
`_octant` module they call:

```scad
octant_to_full() { corner_translate(unit_width, corner_radius) { <X>_octant(...) } }
```

One `children()`-based module replaces all four and deletes four 10-parameter
signatures:

```scad
module octant_tiled(unit_width, corner_radius) {
    octant_to_full() corner_translate(unit_width, corner_radius) children();
}
```

### IP-GEO-9 — cutting solids sized by guesswork

Cuts are oversized by ad-hoc multipliers: `3*bulkhead_thickness`, `2*corner_radius`,
`unit_width`. Each is a guess at "big enough," and each is a silent failure waiting for
a parameter combination that exceeds it. A helper taking the actual bounding extent
makes the intent explicit and removes the class.

### IP-GEO-10 — the 28-parameter signatures

The root cause of most of the above. Parameters already arrive grouped in Python
(`dp["panel"]`, `dp["greeble"]`, `dp["bolt"]`), and that grouping is flattened at the
boundary and never reconstructed.

---

## How each item is proven behaviour-preserving

Two independent checks, cheapest first.

**Generated-text diff — [`scad_snapshot.py`](../../src/Fuselage/tools/scad_snapshot.py).**
solid2 emits named parameters, so if the `.scad` text generated for every variant is
byte-identical before and after, the geometry is unchanged without rendering anything.
This proves the Python-side items (IP-GEO-2, IP-GEO-3, IP-GEO-4) outright, in seconds.

```text
uv run python src/Fuselage/tools/scad_snapshot.py capture before.json
# ...make the change...
uv run python src/Fuselage/tools/scad_snapshot.py capture after.json
uv run python src/Fuselage/tools/scad_snapshot.py compare before.json after.json
```

Verified against itself: two captures of unmodified code report IDENTICAL across all
576 parts. The snapshots are **disposable build artifacts** — roughly half a megabyte
each, regenerate rather than commit them.

**Geometric comparison.** The SCAD-side items (IP-GEO-5 through IP-GEO-9) change the
`.scad` text by construction, so the text diff cannot prove them. Render a sample and
compare with:

```text
uv run python src/Fuselage/tools/sweep_check.py <output> --reference <baseline>
```

which compares triangle count, enclosed volume, and bounding box per part. A refactor
that changes no geometry can be *proven* to change no geometry — that is what makes
this phase safe to attempt at all, and it is why it waited for Phase 1.

Note that triangle count is the strictest of the three and will shift if a refactor
alters the order of boolean operations, even when the solid is identical. A volume and
bounding-box match with a changed triangle count is a result to investigate, not an
automatic failure.
