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
| IP-GEO-2 | done | Convert the seven `scad_module` invocations from positional to keyword arguments | IP-GEO-1 |
| IP-GEO-3 | done | Resolve the greeble-thickness formula duplicated between Python and commented-out SCAD | IP-GEO-1 |
| IP-GEO-4 | done | Hoist `import math` to module level; name the hardcoded "fixed parameters" | — |
| IP-GEO-5 | done | Use the existing `mirror_xy()` at the **four** open-coded sites in `fuselage_corner_geometry.scad` | IP-GEO-13 |
| IP-GEO-6 | done | Extract `octant_tiled()` and use it in the four wrapper bodies | IP-GEO-13 |
| IP-GEO-7 | done | Extract greeble dimensions as SCAD functions | IP-GEO-13 |
| IP-GEO-8 | done | Single shared `geometry_eps()`, replacing 12 per-module redeclarations | IP-GEO-13 |
| IP-GEO-13 | done | Geometric verification harness for `.scad` changes — [`verify_scad_change.py`](../../src/Fuselage/tools/verify_scad_change.py) | — |
| IP-GEO-9 | todo | Named helper for oversized cutting solids, replacing ad-hoc `3*bulkhead_thickness` / `2*corner_radius` multipliers | IP-GEO-1 |
| IP-GEO-10 | blocked (IP-GEO-2) | Group parameters so `bulkhead_section_full` takes ~8 arguments instead of 28 | IP-GEO-2 |
| IP-GEO-11 | todo | Write `doc/design/bulkhead.md` and `doc/design/corner.md` to give this work a design authority | — |
| IP-GEO-12 | todo | Repair `test_fuse.ipynb`: its preview cells broke when `solid_render` stopped writing PNGs | — |

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
parameter names — only the Python call sites were positional.

**Done 2026-08-06.** Seven invocations converted, not five — `nose_render` makes three
(`nose_cowl`, `nose`, `nose_plate`) depending on which part it is building. Argument
counts: 28 (`bulkhead_section_full`), 25 (`boom_bulkhead`), 23 (`tail_cowl`), 14
(`fuselage_corner`), 14 (`nose_cowl`), 13 (`nose`), 5 (`nose_plate`).

`scad_snapshot.py compare` reports IDENTICAL across all 576 parts, so the change
provably altered no geometry.

Two hazards this removed, both invisible positionally:

- `nose` takes **no** `oml_length`, while `nose_cowl` and `tail_cowl` both do — so the
  same conceptual argument list is off by one between neighbouring calls in the same
  function, with every surrounding argument the same type.
- `tail_cowl` carries eighteen buttress floats in four groups distinguished only by
  prefix (`side_`, `top_`, `bottom_`, `top_diag_`). Transposing two was a silent
  geometry change; it is now a `TypeError`.

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
silently change every part.

**Resolved: the `sqrt` is current and deliberate; the SCAD line is a stale ancestor.**
An abandoned scratch copy, `tools/tmp.py` (last modified 2025-08-20, since deleted),
carried `2*U` — matching the commented-out SCAD. So `2*U` was the original in both
languages, the Python was later changed to `2*sqrt(U)`, and the SCAD copy was commented
out rather than updated and has disagreed ever since.

The action is therefore to **delete the commented SCAD lines**, not to reconcile toward
them. Every rendered part in `variant_output` and `variant_output_baseline` was built
with `sqrt`, so restoring `2*U` would silently change all of them.

### IP-GEO-5 — a library function that exists and is not used

`shape_modifier_utils.scad` defines `mirror_xy()` as exactly
`union() { children(); mirror([1,-1,0]) children(); }`, and
`fuselage_corner_geometry.scad` open-codes that union rather than calling it.

**Done 2026-08-06.** Two corrections to the finding as originally written:

- It was **four** sites, not three. The fourth sits at a deeper indentation inside
  `corner_transition`, so a whitespace-exact replace-all converted only three and
  reported success. Counting the remaining `mirror([1,-1,0])` occurrences afterwards
  is what caught it.
- `fuselage_corner_geometry.scad` had **no includes at all**, so `mirror_xy()` was not
  in scope there. It resolved only when the file was pulled in via
  `fuselage_bulkhead_geometry.scad`, and not when used standalone — which is exactly
  how `corner_render` uses it. An `include <shape_modifier_utils.scad>` was added;
  OpenSCAD renders clean with no duplicate-definition warnings, even though
  `fuselage_geometry.scad` already pulls `corner_geometry` in three separate ways.

Verified with `verify_scad_change.py`: 10 parts across all five kinds and two U scales,
identical triangle count, volume and bounding box.

### IP-GEO-6 — four structurally identical wrappers

`bulkhead_oml_shape`, `bulkhead_oml_outer_shape`, `bulkhead_oml_inner_shape`, and
`bulkhead_web_inner_shape` (lines 711-749) share one body, differing only in which
`_octant` module they call:

```scad
octant_to_full() { corner_translate(unit_width, corner_radius) { <X>_octant(...) } }
```

A `children()`-based module in `shape_modifier_utils.scad` carries that body once:

```scad
module octant_tiled(unit_width, corner_radius) {
    octant_to_full() corner_translate(unit_width, corner_radius) children();
}
```

**Done 2026-08-06 — and narrower than this item originally proposed.** The original
plan was to delete the four wrappers and inline `octant_tiled(...)` at every call,
"deleting four 10-parameter signatures". Checking the call sites first showed why that
is wrong: there are **seven**, and **five of them are in
`fuselage_boom_bulkhead_geometry.scad`**, a different file.

Inlining would have made all seven more verbose and leaked the tiling mechanism into
callers. The wrappers are a real abstraction — they name the full shape as distinct
from the octant. What was duplicated is the three-line *body*, not the interface, and
that is what was removed. Reducing those signatures is IP-GEO-10's job, applied
uniformly rather than ad-hoc to four modules.

The `octant_to_full()` calls that remain are genuinely different patterns, not misses:
`cowl_geometry.scad:5`, and `bulkhead_section_full` which tiles without a
`corner_translate`.

Verified with `verify_scad_change.py`: 10 parts, identical geometry.

### IP-GEO-12 — the notebook's preview cells are broken

`test_fuse.ipynb` uses `png_filename` eleven times as `Image(filename=png_filename)`.
`solid_render` still returns that path, but nothing writes a file there any more:
OpenSCAD's second `--render` invocation was removed, and previews are now rasterized
from the finished STL. Every one of those cells raises on a missing file.

The fix is one added line per cell:

```python
import stl_preview
(scad_filename, stl_filename, png_filename) = fv.solid_render(corn, 'test_fuse_output', 'tmp_corner.scad')
stl_preview.render_stl_to_png(stl_filename, png_filename)
Image(filename=png_filename)
```

Two things to settle while in there. The notebook is tracked and ~1.5 MB with outputs
embedded, so cell outputs should be cleared before it is committed again. And its
scratch directory `tools/test_fuse_output/` holds 36 files and 106 MB last written
2025-08-23; it is now gitignored, and can be deleted once the notebook can regenerate
it — which is what this item unblocks.

### IP-GEO-7 and IP-GEO-8 — done 2026-08-06

**Greeble dimensions.** `corner_end()` and `corner_transition()` each computed
`greeble_radius`, `greeble_nub_radius` and `greeble_nub_height` from the same sums, so
the two could drift apart silently. That matters more than ordinary duplication: the
greeble is a *mating* feature, and the corner's nub must agree exactly with the
bulkhead's pocket or the parts do not assemble.

Now three functions in `fuselage_corner_geometry.scad`. `greeble_nub_radius_of()` is
written in terms of `greeble_radius_of()` plus the nub thickness, rather than repeating
the five-term sum — the nub stands proud of the seat by exactly its own thickness, and
stating it that way makes the relationship impossible to break by editing one and not
the other.

`longeron_chamfer = nozzle_diameter` was left as a local alias. It is a rename, not a
derivation, and a function wrapping a single parameter would obscure rather than clarify.

**Shared epsilon.** Twelve modules across four files each declared `eps = 0.01` (one as
`eps=0.01`). All twelve now call `geometry_eps()`, defined once in
`shape_modifier_utils.scad`.

A *function*, deliberately, not a top-level variable: `use <...>` exports functions but
not top-level variable assignments, and the sweep reaches these files through `use`
rather than `include`. A shared variable would have resolved when a file was included
and silently failed when it was used — the same class of scope-dependent breakage as
IP-GEO-5, where `mirror_xy()` was visible only on the include path.

Keeping the local `eps = geometry_eps();` in each module leaves every usage site
untouched, so this change is one line per module rather than a rewrite of every
`+eps` in the file.

Both verified with `verify_scad_change.py`: 10 parts, identical geometry.

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

### ⚠ The text diff is blind to `.scad` library files — do not use it for IP-GEO-5..9

A generated `.scad` contains only a `use <...>` line and the module call:

```scad
use <../../../../../scad/fuselage_corner_geometry.scad>;
$fn = 0; $fa = 1; $fs = 0.05;
fuselage_corner(U = 1.0, bulkhead_thickness = 6, ...);
```

The library's *contents* are referenced by path, never captured. So editing a `.scad`
module does not merely leave the text diff unable to prove the change — **the diff will
report IDENTICAL even if the edit destroyed the geometry.** That is a false negative, not
an absence of evidence, and it is the one way this tooling could actively mislead.

Use it only for changes to the Python that builds the call. For anything under
`src/Fuselage/scad/`, the geometric comparison below is the only check that means
anything.

(The exception is deleting a *comment* from a `.scad` file, as IP-GEO-3 does: OpenSCAD
discards comments before evaluation, so that is safe by construction rather than by test.)

**Geometric comparison.** Render a sample and compare with:

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

