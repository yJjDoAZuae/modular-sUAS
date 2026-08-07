# Geometry Refactor — Implementation Plan

**Scope:** Deduplication, interface, and robustness work on the OpenSCAD geometry
modules and the Python that drives them, from a review of `src/Fuselage/scad/*.scad`
and `fuselage_variants.py` on 2026-08-06. Every item is behaviour-preserving: the
generated geometry must not change, and each item states how that is proven.

This is roadmap [Phase 2](../roadmap.md) work — "Refactor and improve the OpenSCAD
implementation" — and it is unblocked because Phase 1 delivered the verification it
depends on (`mesh_stats.py`, `sweep_check.py`).

**Design authority:** [doc/design/bulkhead.md](../design/bulkhead.md) and
[doc/design/corner.md](../design/corner.md), written as IP-GEO-11. They are reconstructed
from the implementation rather than inherited, so they mark inference as inference — read
the preamble of either before relying on a "why".

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
| IP-GEO-14 | done | End-to-end sweep verification — [`verify_sweep_change.py`](../../src/Fuselage/tools/verify_sweep_change.py) | — |
| IP-GEO-15 | done | Render every GUI driver and treat warnings as failures — [`verify_drivers.py`](../../src/Fuselage/tools/verify_drivers.py) | — |
| IP-GEO-9 | done | `through_cut()` and `mask_reach()` replacing 11 raw multipliers | IP-GEO-13 |
| IP-GEO-10 | superseded | Group SCAD parameters so `bulkhead_section_full` takes ~8 arguments instead of 28. Dropped per OQ-GEO-1: the work does not survive the FreeCAD port. Replaced by IP-GEO-16. | — |
| IP-GEO-16 | done | Replace the nested parameter dicts with typed dataclasses in Python — the same idea on the side that survives Phase 3 | — |
| IP-GEO-17 | done | Revert the partially-applied greeble grouping pilot | — |
| IP-GEO-18 | done | Fix `nose_cowl.scad` and `tail_cowl.scad`: they named the OML mesh without its `../oml/` prefix, so neither had rendered since the meshes moved. Pre-existing, found by IP-GEO-15 | IP-GEO-15 |
| IP-GEO-11 | done | [`doc/design/bulkhead.md`](../design/bulkhead.md) and [`doc/design/corner.md`](../design/corner.md) — a design authority for this work | — |
| IP-GEO-12 | done | Repair `test_fuse.ipynb`. The stated cause was wrong — previews were never broken; the notebook had drifted years behind the API | IP-GEO-16 |
| IP-GEO-21 | done | Resolve OQ-DES-B6: drop `greeble_tolerance` from the bulkhead side — the post is nominal by construction, so it was a knob that could not do anything | IP-GEO-11 |
| IP-GEO-22 | done | Resolve OQ-DES-C1: derive `greeble_nub_thickness` from `greeble_thickness` through a named formula in Python, instead of computing both from the same expression | IP-GEO-11 |
| IP-GEO-23 | done | Drop `unit_length` from the bulkhead modules and drivers. Passed through three signatures, used by none — it asserted a dependence on bay length that the design exists to avoid. Found via OQ-DES-C3 | IP-GEO-11 |
| IP-GEO-24 | done | Rename `nozzle_diameter` → `extrusion_width`. Every use was extrusion-width semantics; the name described the wrong physical quantity | — |
| IP-GEO-25 | done | Add `slots=True` to the parameter dataclasses. Without it a plain dataclass accepts undeclared attributes silently — IP-GEO-16 did not deliver what it claimed | IP-GEO-16 |
| IP-GEO-20 | done | Correct the greeble's mating direction in comments and design docs — it is the **positive post on the bulkhead**, not a nub on the corner | IP-GEO-11 |
| IP-GEO-19 | withdrawn | Validate threaded-insert depth against `bulkhead_thickness`. Raised on a wrong assumption — the insert is set from the interior face and may stand proud of it, so it need not fit within the thickness. No check is warranted. See OQ-DES-B5 | IP-GEO-11 |

> **IP-GEO-10 blocked reason (historical):** Regrouping 28 positional parameters is the
> change most able to silently transpose two same-typed floats. Keyword arguments
> (IP-GEO-2) make each move checkable at the call site and turn a mistake into a
> `TypeError`, so that landed first. IP-GEO-10 was then superseded outright — see
> OQ-GEO-1.

### IP-GEO-17 — done 2026-08-06: the revert, and how it was proven

The pilot had migrated `fuselage_corner_geometry.scad`, `fuselage_bulkhead_geometry.scad`
and the `fuselage_corner.scad` driver to a single `greeble` vector, while
`fuselage_variants.py` and the other drivers still passed four scalars. Reverted:
`make_greeble()` and the four accessors are gone from `shape_modifier_utils.scad`, and
every signature is back to `greeble_thickness, greeble_nub_thickness, greeble_tolerance`
(plus `greeble_opening_angle` on the bulkhead side).

**IP-GEO-7 is untouched.** `greeble_radius_of()`, `greeble_nub_radius_of()` and
`greeble_nub_height_of()` remain — they took scalar arguments before the pilot and take
scalar arguments again. The pilot changed how they were *called*, never why they exist.

**Proven by the diff, not by rendering.** The pilot was entirely uncommitted, so the
whole of it reverts to HEAD — which is IP-GEO-9's verified state. What remains different
from HEAD across all four files is **two comments and no code**, and OpenSCAD discards
comments before evaluation, so the geometry is unchanged by construction. Both comments
were kept deliberately: the bulkhead's now says *why* the greeble tolerance is zeroed
(the clearance is taken entirely on the corner's bore, so splitting it would make the
joint carry it twice), which the original one-liner did not.

Both of those comments were subsequently corrected — they described the greeble as a
feature of the corner mating into a bulkhead pocket, which is backwards. See IP-GEO-20.

Corroborated by IP-GEO-15 anyway. Every driver that the pilot had broken is now clean,
and `fuselage_corner.scad` — the one driver the pilot had migrated *consistently*, so it
rendered correctly throughout — reports 10,932 triangles before and after:

```text
  OK       fuselage_boom_bulkhead.scad  (2,364 tris)
  OK       fuselage_bulkhead.scad  (3,272 tris)     <- was 292 warnings, 1,960 tris
  OK       fuselage_corner.scad  (10,932 tris)      <- unchanged across the revert
  OK       fuselage_cowling_bulkhead.scad  (2,712 tris)  <- was warnings + non-manifold
  OK       fuselage_oml.scad  (1,372 tris)
  FAILED   nose_cowl.scad / tail_cowl.scad          <- pre-existing, IP-GEO-18
```

The Python side needed no change: `fuselage_variants.py` was never migrated, which is
what made the tree inconsistent in the first place and what now makes it consistent
again.

### IP-GEO-18 — done 2026-08-06: the cowl drivers had not rendered in months

`nose_cowl.scad` and `tail_cowl.scad` set `oml_filename = "vsp_nose.stl"`, but the
`import()` that consumes it lives in `cowl_geometry.scad`, and OpenSCAD resolves
`import()` against the file containing the call — so the name had to be `../oml/...`
from the moment the meshes moved into `oml/`. Fixed by adding the prefix in both
drivers, with a comment pointing at `oml_ref()` in `fuselage_variants.py`, which is the
Python half of the same rule.

The sweep never noticed because `oml_ref()` supplies the prefix; only the interactive
path was broken, and nothing rendered the interactive path until IP-GEO-15 existed.
All eight drivers now render:

```text
  OK  fuselage_boom_bulkhead (2,364)   OK  fuselage_bulkhead (3,272)
  OK  fuselage_corner (10,932)         OK  fuselage_cowling_bulkhead (2,712)
  OK  fuselage_oml (1,372)             OK  nose_cowl (21,092)
  OK  tail_cowl (89,910)               --  fuselage_geometry (aggregator, skipped)
```

There is no reference to compare the two cowls against — they had no working output to
be a baseline. What is established is that the OML import resolves and the boolean
tree completes; the shapes themselves are unreviewed, and IP-GEO-11's design documents
are where that would be settled.

### IP-GEO-25 — done 2026-08-07: the dataclasses were not doing what they claimed

**IP-GEO-16's central claim was false.** It says a misspelled *write* — the hazard the
whole conversion existed to close — "raises `AttributeError` at the line that made it".
A plain dataclass does no such thing. Instances carry a `__dict__`, and Python will
happily add an attribute to it:

```python
@dataclass
class Plain:
    extrusion_width: float = 0.4

p = Plain()
p.nozzle_diameter = 0.6     # accepted in silence
p.extrusion_width           # still 0.4
```

That is the *dict* behaviour, verbatim. The conversion changed the syntax of the failure
and not the failure.

**How it surfaced, which is the part worth keeping.** IP-GEO-24 renamed
`nozzle_diameter` to `extrusion_width`. A verification script still setting the old name
kept running, silently left `extrusion_width` at its 0.4 default instead of the sweep's
0.6, and rendered five bulkheads that came out **13–30 % off in volume**. The comparison
reported five DIFFERENT parts and briefly looked like a geometry regression in the rename.

It was not. It was the exact failure mode IP-GEO-16 was introduced to prevent, reproduced
by the code that was supposed to prevent it, and caught only because a geometric check
happened to be pointed at it. Had the rename been verified by drivers alone — which
passed, with unchanged triangle counts — nothing would have noticed.

**Fixed** by `@dataclass(slots=True)` on all nineteen parameter classes. `__slots__`
removes the instance `__dict__`, so an undeclared name raises at the assignment. Verified
on both a top-level field and a nested group:

```text
'PrinterSettings' object has no attribute 'nozzle_diameter' and no __dict__ ...
'GreebleParameters' object has no attribute 'thicknes' and no __dict__ ...
```

Nothing else changed: `field(default_factory=...)` is unaffected by slots, and the
`setattr()` loops in `derived_cowl_parameters()` iterate `fields()`, so they only ever
write declared names.

**The general lesson, recorded in the guidelines:** a safety property that has not been
*tested* is a claim, not a property. This one was written into a comment, a design
document, and a guideline, and was wrong in all three for a day.

### IP-GEO-24 — done 2026-08-07: `nozzle_diameter` never meant nozzle diameter

Every use of the field was extrusion-width semantics — a wall *N* beads thick, or *N* beads
of margin — and none referred to the nozzle's bore. The two are numerically close, which is
why it went unnoticed, and conceptually different, which is why it mattered.

Renamed across 36 sites in `scad/`, 20 in the Python, and 35 in the notebook.

**Why rename code that Phase 3 replaces?** The standing guideline is to weigh a refactor
against what replaces it, and this one survives that test on an argument specific to
naming: the FreeCAD port will be written by *reading* this code. A field called
`nozzle_diameter` gets ported as nozzle diameter — and then UC-4's cowl interior surface
needs an extrusion width, adds one, and the model carries two parameters differing by
10–20 % where the design has one. The rename costs an afternoon now and prevents a
duplicated parameter that would be genuinely hard to unpick later. See
[freecad_migration.md](../architecture/freecad_migration.md).

**Two regressions surfaced, both mine, neither caused by the rename.** The notebook still
passed `unit_length` and `greeble_tolerance` to `bulkhead_section_full` — arguments removed
by IP-GEO-23 and IP-GEO-21, *after* IP-GEO-12 had repaired those cells. Fixing the notebook
and then changing the signatures it calls left it broken again, and nothing noticed because
nothing checks the notebook.

That gap is worth naming. `verify_drivers.py` covers the `.scad` drivers; the notebook is a
third caller class with no coverage at all, and solid2's imported modules accept
`(*args, **kwargs)`, so a wrong keyword is invisible until OpenSCAD runs. A static check
comparing the notebook's keywords against the `.scad` signatures found all three call sites
at once — see the note under *How each item is proven behaviour-preserving*.

**Verification.** The generated `.scad` text changes by construction, so the check is
geometric: all seven drivers render warning-free with unchanged triangle counts, all 21
non-sweep notebook cells execute, and the five bulkhead types were re-rendered and compared
against the IP-GEO-21 reference.

### IP-GEO-23 — done 2026-08-06: the bulkhead does not know how long the bay is

Came out of OQ-DES-C3's answer, which is worth quoting because it is the sharper form of
the design rule:

> Different bay lengths share the same bulkhead design. That is why `FX` is a separate
> parameter and the bulkhead does not reference it.

Checking that against the code turned up a defect. `unit_length` was threaded through
`bulkhead_section_full` → `_octant` → `_section` and **used by none of them**, and both
GUI drivers computed it — `unit_length = 100*U*FX` — solely to pass it in.

That is the same shape as OQ-DES-B6 but worse in kind. A dead `greeble_tolerance` merely
did nothing. A dead `unit_length` *asserted a dependency on bay length*, which is exactly
what the parameterisation is built to avoid: it invited the next reader to believe a
bulkhead has to be regenerated per `FX`, when the whole point is that one bulkhead serves
every bay length.

The demonstration was already sitting in the tree: `fuselage_cowling_bulkhead.scad` set
`FX = 0.5` while `fuselage_bulkhead.scad` set `FX = 1`, and both produced identically
shaped bulkheads.

Removed from three signatures, four internal call sites, both drivers (along with their
now-purposeless `FX`), and `bulkhead_render()`. The sweep already agreed with the design
and needed no change: `FX` appears only in `corner_size_variants.csv`, so bulkheads are
generated once per (panel, type, size) and reused across bay lengths, while corners carry
`FX` in their filenames.

**Verification.** A signature moved, so `scad_snapshot.py` reports DIFF by construction
and the check is geometric. All seven drivers render warning-free with unchanged triangle
counts, and one bulkhead of each of the five types was re-rendered through the sweep path
and compared against the IP-GEO-21 reference — **all five identical** in triangle count,
enclosed volume and bounding box, to the same figures quoted for IP-GEO-21 below
(`end_bolt` 30,392 tris / 7122.0821, `interconnect` 25,608 / 7259.7447, and the rest).

That the numbers are unchanged across *both* signature removals is the point: neither
parameter was ever reaching the geometry.

### IP-GEO-22 — done 2026-08-06: one wall thickness, not two

Closes OQ-DES-C1. `greeble_thickness` and `greeble_nub_thickness` were computed from the
*same expression, written out twice* — so they were not independent in fact, only in
form, and nothing stopped one being edited without the other. They are the mating halves
of a snap fit, so drift between them means parts that do not assemble.

Now `greeble_nub_thickness_of(greeble_thickness)` in `fuselage_variants.py`, identity
today. Written as a formula rather than collapsed to a single value deliberately: scale
problems may yet want the rib thicker or thinner than the seat wall, and that fix belongs
in one function rather than in the reintroduction of a second parameter.

**Python owns the formula, not OpenSCAD.** Both languages need the value — SCAD to build
the geometry, Python for the panel-clearance validity checks — so the choice was which
side is authoritative. Python, on the same grounds as OQ-GEO-1: the geometry modules take
both values as arguments and derive neither, so the relationship is stated in exactly one
place, and it is the place that survives the FreeCAD port. The cost is that the SCAD
signatures keep both arguments and the hand-edited GUI drivers can still set them
inconsistently; those now read `greeble_nub_thickness = greeble_thickness` with a comment
pointing at the formula, which makes the intent visible at the only site that can get it
wrong.

**Verification.** No signature changed, so this is the case `scad_snapshot.py` proves
outright: all 576 parts across all five sweeps generate **byte-identical `.scad`**. All
seven GUI drivers render warning-free with unchanged triangle counts.

### IP-GEO-21 — done 2026-08-06: a parameter that could not do anything

Closes OQ-DES-B6, and with it the refactor. `greeble_tolerance` was threaded positionally
through `bulkhead_section_full` → `_octant` → `bulkhead_section` and then thrown away:
`greeble_tolerance_local = 0` was what reached `corner_end()`.

**Chosen: drop the parameter, not honour it.** Both options were behaviour-identical
today, since every caller passed zero. The deciding argument is that *the greeble post is
nominal* is an **invariant, not a setting** — all fit clearance lives on the corner's
bore because splitting it makes the joint carry it twice. A module that accepts a
tolerance it must ignore in order to stay correct advertises control it does not have,
and the person most likely to reach for it is someone whose parts will not snap together:
they would change the number, see nothing happen, and conclude the geometry was at fault.
Honouring the caller would have bought that knob back at the price of re-opening the
double-clearance failure mode the design deliberately closed.

Removed from three SCAD signatures and four internal call sites, from
`fuselage_bulkhead.scad` and `fuselage_cowling_bulkhead.scad`, from `bulkhead_render()`,
and from the Python constants — `GREEBLE_TOLERANCE_BULKHEAD_MM` is gone and
`derived_parameters()` no longer sets `greeble.tolerance` for bulkheads. The literal `0`
now sits at the `corner_end()` call with the invariant stated beside it.

**Verification.** `scad_snapshot.py` cannot speak to this one — a signature change alters
the generated text by construction — so the check is geometric, per
*How each item is proven behaviour-preserving* below:

- `verify_drivers.py`: all seven drivers render warning-free, with **identical triangle
  counts** to before the change (`fuselage_bulkhead` 3,272; `fuselage_cowling_bulkhead`
  2,712).
- One bulkhead of each of the five types rendered through the real sweep path
  (`derived_parameters` → `bulkhead_render`) before and after, compared by triangle
  count, enclosed volume and bounding box — **all five identical**:

```text
  IDENTICAL  cowling_anchor   36,704 tris  vol 10211.8535
  IDENTICAL  cowling_bolt     34,256 tris  vol  9854.7238
  IDENTICAL  end_anchor       32,008 tris  vol  7391.2568
  IDENTICAL  end_bolt         30,392 tris  vol  7122.0821
  IDENTICAL  interconnect     25,608 tris  vol  7259.7447
```

### IP-GEO-12 — done 2026-08-06: the notebook, and a wrong diagnosis

**The item's stated cause was wrong.** It read *"its preview cells broke when
`solid_render` stopped writing PNGs"*. `solid_render` never stopped: `_PREVIEWS`
defaults to `True` and the render queue defaults to serial, so the preview is written
from the finished STL before the call returns. Verified by rendering — every
`Image(filename=png_filename)` cell finds its PNG.

The real problem was drift. The notebook predates several refactors; its stored outputs
still show `BulkheadType.END_BOLT`, an enum member that no longer exists. What was
actually broken:

| | |
| --- | --- |
| `fgeom.fuselage_corner` did not exist | `fuselage_geometry.scad` is three `include` lines. Imported with `use_not_include` it exposes **no modules at all**, so every `fgeom.*` call failed. Now imports the geometry files directly through `fv.scad_module()`, which also fixes the cwd-dependent bare filenames. |
| Dict access on dataclasses | `printer_settings["nozzle_diameter"]`, `dp["panel"]["offset"]` — four cells, broken by IP-GEO-16. |
| Stale signatures | `fuselage_corner` missing `U` and both greeble thicknesses; `bulkhead_section_full` missing both, three times; `boom_bulkhead` passing a `plate_thickness` that is not a parameter and omitting four that are; `derived_parameters` missing `is_bulkhead`; `tail_cowl` missing `oml_reversed`. |
| The IP-GEO-18 bug again | The cowl cells named the OML as bare `"vsp_nose.stl"`. Now `fv.oml_ref()`. |
| Cell 3 entirely stale | Wrong CSV axes, and `is_nose_cowl`/`is_nose_nose`/`is_nose_plate` columns that no longer exist. Rewritten around `derived_cowl_parameters` and `dp.nose.active` / `dp.plate.active`. |
| `unit_frame()` leaked globals | It read `cowl_flange_height` and `cowl_flange_tolerance` from module scope, inheriting whatever the cowling cell above had left behind — a plain bay grew a cowling lip if that cell had been run. Now self-contained. |

All the long calls are now **keyword arguments**, so the next signature change is an
error rather than a silent shift — the same reasoning as IP-GEO-2, applied to the caller
that had already been bitten by it.

**A hazard removed on judgement, not on request.** Cells 7–11 ran full sweeps into
`'variant_output'`. A stray *Run All* would have overwritten the protected output. They
now write to an `OUTPUT_DIR` constant set to `test_fuse_output`, with a pointer to the
CLI for real sweeps.

**Jupyter is now a dev dependency.** The notebook imports `IPython.display.Image` and
the project environment did not have IPython, so it could not be opened at all —
repairing the cells without that would have fixed nothing.

**Verified by executing it.** All 21 non-sweep cells run to completion; cells 14–20 and
22 were rendered live and each produced its preview PNG. The five sweep cells were not
run — they are the hours-long ones — but they differ from the CLI only in the output
directory.

### IP-GEO-20 — done 2026-08-06: the greeble points the other way

Corrected on report from the design owner. Every comment and document that described the joint had it
inverted: the greeble was described as a nub on the *corner* snapping into a *pocket* in
the bulkhead. It is the reverse. **The greeble is the positive annular post on the
bulkhead, with the snap rib around it; the corner carries the bore and the internal
groove.**

The code was always right — only the prose was wrong, so no geometry changed and none of
the verification above is affected.

**Why it was easy to get backwards, which is worth recording because the next reader will
hit the same trap.** The line that creates the greeble is

```scad
corner_end(U, bulkhead_thickness + 2*eps, …, greeble_tolerance_local, …);
```

and it sits inside the *negative* half of `bulkhead_section()`'s `difference()`. Read
casually, a corner shape in the subtraction list is cutting a corner-shaped pocket. But
`corner_end()` is itself mostly a difference — the corner's end section is a bore of
`greeble_radius` with a groove out to `greeble_nub_radius` through its middle third —
so subtracting it removes bulkhead material where the corner is solid and leaves it where
the corner is hollow. What survives is the post.

The naming settles it independently. `greeble_bolt_web` is commented "greeble to bolt
web"; three fillet modules speak of "the side wall of the flange **at the greeble**".
Those are all locations on the bulkhead, and none of them would parse if the greeble
lived on the corner.

**Corrected in:** `fuselage_bulkhead_geometry.scad`, `fuselage_corner_geometry.scad` and
`fuselage_corner.scad` (comments), `fuselage_variants.py` (the tolerance constants),
`corner.md`, `bulkhead.md`, `fuselage_folder_summary.md`, and two places in this file.

**A second finding fell out of it:** `greeble_tolerance` is threaded through four bulkhead
module signatures and then discarded by a local zero, so it has no effect on anything.
OQ-DES-B6.

### IP-GEO-16 — done 2026-08-06: the parameter groups are dataclasses

Twenty groups across two trees — `Parameters` for the bulkhead and corner sweeps,
`NoseParameters` for the cowls — replacing the `null_*_parameters()` dicts. The
constructors remain, one line each, so every existing call site still reads
`null_greeble_parameters()`; what changed is that the thing returned has declared
fields. 332 subscripts became attribute access.

**The hazard this closes is assignment, not lookup.** A dict already raised `KeyError`
on a misspelled *read*. On a *write* it silently accepted the new key, left the real
field at its default, and produced a part wrong by exactly the amount the assignment
was meant to change.

> **Correction, 2026-08-07.** This paragraph originally ended by claiming that
> `c.greeble.thicknes = 1.2` "now raises `AttributeError` at the line that made the
> mistake". **It did not.** A plain dataclass accepts undeclared attributes exactly as the
> dict did, so this item closed the *read* half of the hazard and left the *write* half
> open — while asserting the opposite in a comment, a design document and a guideline.
> `slots=True` was added in IP-GEO-25, and the claim is true now.

**It found one immediately.** `derived_parameters()` sets and reads
`c["bolt"]["diameter"]`, but `null_bolt_parameters()` never declared it — the field
existed only because a dict accepted it. It is real and load-bearing (`bolt.radius` is
derived from it, differently for an anchor), so it is now a declared field with a
comment saying where it came from. Nothing else in either tree turned out to be
undeclared; the runtime dump of all twelve groups was checked field by field against
the new definitions.

**Where the dicts stayed.** Only the parameter *groups* were converted. `src` and
`b_src` in `derived_cowl_parameters()` are parsed JSON, the CSV rows are pandas records,
and `standard_values()` / `scaled_standard_values()` are flat constant tables written
once in the function that returns them. Converting those would mean asserting a schema
over data this code does not own.

Two generic copy loops needed rewriting rather than translating. `for k in c["oml"]`
became `for f in fields(c.oml)`, and the buttress loop the same. The behaviour is
preserved exactly — a key missing from the JSON is still a `KeyError`, an extra key in
the file is still ignored — but the schema being iterated is now the dataclass
declaration rather than whatever the dict happened to have been initialised with.

**Proven by `scad_snapshot.py`.** All 576 parts across all five sweeps — corner,
bulkhead, boom, nose, tail — generate byte-identical `.scad` before and after. This is
the case the text diff proves outright and the case its blind spot does not touch: no
`.scad` file was edited, so nothing about it depends on library contents.

`fuselage_splode.py` also constructs parameters and was updated with the module; it runs
and returns its five sets. `test_fuse.ipynb` uses no dict-style parameter access, so
IP-GEO-12 inherits nothing new from this.

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

Quoted as it stood in 2026-08-06. `nozzle_diameter` was later renamed `extrusion_width`
(IP-GEO-24) and the second formula replaced by `greeble_nub_thickness_of()` (IP-GEO-22);
the discrepancy this item is about is unaffected.

`fuselage_variants.py` computed, under a comment reading *"recreate derived dimensions
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
greeble is a *mating* feature, and the bulkhead's post must agree exactly with the
corner's bore or the parts do not assemble.

Now three functions in `fuselage_corner_geometry.scad`. `greeble_nub_radius_of()` is
written in terms of `greeble_radius_of()` plus the nub thickness, rather than repeating
the five-term sum — the snap feature sits one wall thickness outboard of the greeble
body, and stating it that way makes the relationship impossible to break by editing one
and not the other.

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

### IP-GEO-9 — done 2026-08-06: the extents were already safe

Two helpers in `shape_modifier_utils.scad`, replacing 11 raw multipliers:

- `through_cut(extent) = 3 * extent` — length for a *centred* cutting solid that must
  pass entirely through material of depth `extent`. 7 call sites.
- `mask_reach(extent) = 2 * extent` — distance to place a mask vertex so it lies off
  the part. 4 call sites.

**The margins were measured, not assumed.** Walking all 412 valid combinations of the
swept parameter space:

| Check | Worst case | Verdict |
| --- | --- | --- |
| `mask_reach` vs the shape's reach (`panel_offset + panel_overlap`) | +3.25 mm at U=0.5, 1 mm panel: mask at 10.0 mm, shape reaches 6.75 mm | safe, and the gap widens with U |
| `through_cut` vs the material it spans | +0.5 × `bulkhead_thickness` everywhere | safe, scales with the part |

So this item is **naming, not repair** — no current parameter combination is marginal.
That was worth establishing rather than assuming, because the change looks identical
either way: if a multiplier had been too small, `verify_scad_change.py` would report
DIFF, and that would have been a *bug found* rather than a refactor failed.

An intermediate version of the margin analysis reported the depth check as
UNDER-COVERING by 8 mm at U=4.0. That was a fault in the analysis, not the geometry: it
compared the half-cut against the 2 × `bulkhead_thickness` interconnect stack, but those
cuts live inside `bulkhead_section`, which is one `bulkhead_thickness` tall, and the two
sections are stacked *after* their cuts are applied. The stack is not what a cut has to
span.

Two of the 11 sites were found only on a second pass: they wrote `bulkhead_thickness*3`
rather than `3*bulkhead_thickness`, and the search pattern had assumed one ordering.
Same class of miss as the whitespace-dependent replace in IP-GEO-5.

### IP-GEO-9 — the original finding

Cuts are oversized by ad-hoc multipliers: `3*bulkhead_thickness`, `2*corner_radius`,
`unit_width`. Each is a guess at "big enough," and each is a silent failure waiting for
a parameter combination that exceeds it. A helper taking the actual bounding extent
makes the intent explicit and removes the class.

### IP-GEO-10 — the 28-parameter signatures

The root cause of most of the above. Parameters already arrive grouped in Python
(`dp["panel"]`, `dp["greeble"]`, `dp["bolt"]`), and that grouping is flattened at the
boundary and never reconstructed.

#### The verification gap this item opens

Every item so far changed one language at a time, and each had a tool that proved it.
This one changes **both at once** — the SCAD signatures and the Python that calls them —
and neither existing tool covers that:

- `scad_snapshot.py` reports DIFF **by construction**: the generated call text is exactly
  what changes. A DIFF here carries no information.
- `verify_scad_change.py` **stops working**: it re-renders the `.stl.scad` files already
  in the output tree, and those contain calls in the *old* signature. After the refactor
  they name parameters that no longer exist, so it fails to render rather than reporting
  a difference.

The check that still means something is end-to-end: run the real sweep with the new code
for a sample of combinations, and compare the resulting **STLs** against the reference
tree by measured geometry. Signatures and generated text are free to change; the solid
must not. That is IP-GEO-14.

#### The trap in the obvious design

OpenSCAD has no records, so "grouping" means passing vectors:

```scad
module bulkhead_section_full(panel, greeble, bolt, ...) { ... panel[0] ... }
```

That trades 28 *named* parameters for a handful of vectors whose elements are accessed
**positionally** — reintroducing, inside the SCAD, exactly the transposition hazard
IP-GEO-2 just removed at the Python boundary. `panel[0]` versus `panel[1]` is no safer
than argument 7 versus argument 8, and is harder to spot.

The grouping is only worth doing with **named accessor functions** alongside it:

```scad
function panel_thickness(p) = p[0];
function panel_offset(p)    = p[1];
```

so no module indexes a vector directly. That is the design, and it is what makes this a
net safety gain rather than a lateral move.

#### Order of work

One group at a time, each independently verifiable. A single flag-day rewrite is not
verifiable in any useful sense: if the geometry moves, nothing localises which group
caused it.

#### Scale, measured

Across **65 module definitions** in `*_geometry.scad`:

| Group | Signatures | Occurrences | Members |
| --- | --- | --- | --- |
| panel | 25 | 164 | 4 |
| bolt | 20 | 112 | 3 |
| longeron | 17 | 77 | 2 |
| web | 10 | 78 | 2 |
| flange | 8 | 121 | 3 |
| greeble | 6 | 50 | 4 |

Roughly 600 occurrences in total.

#### What the greeble pilot found

`greeble` was migrated first as the smallest blast radius — fewest signatures, while
still exercising a four-member group. Three findings, each of which changes the estimate
for the remaining five groups:

**1. `undef` propagates silently.** After converting the signatures, five bare
`greeble_*` references survived in polygon coordinates and an extrude height. In
OpenSCAD a bare identifier with no matching variable evaluates to `undef` with a
*warning*, not an error — so a missed reference produces wrong geometry that still
renders. They were caught only by explicitly grepping for non-accessor references
afterwards. **That grep is mandatory for every group**, not optional diligence.

**2. The GUI drivers are a third class of caller, and were not in the 65.** The scale
table above counts `*_geometry.scad` only. `fuselage_corner.scad`,
`fuselage_bulkhead.scad` and `fuselage_cowling_bulkhead.scad` each call these modules
with flat parameters too. The Python sweep would have verified clean while all three
interactive drivers were broken.

**3. Nothing in the verification tooling renders those drivers.** All three tools work
through the sweep or through generated `.stl.scad` files. The drivers are the
"interactive knobs" path and are unverified by construction — see IP-GEO-15.

The pilot is **partially applied and currently does not build**: `fuselage_bulkhead.scad`
and `fuselage_cowling_bulkhead.scad` still pass flat greeble parameters, and the Python
side still passes four keyword arguments. Finish or revert before running a sweep.

---

## Open questions

Implementation-planning questions, in the `/oq` format — questions about *how to carry
out this refactor*, all now resolved. They stay here rather than moving into the design
documents IP-GEO-11 created, because they are about the work and not about the parts.

Questions about the *design* live in [corner.md](../design/corner.md#open-questions) and
[bulkhead.md](../design/bulkhead.md#open-questions) as the OQ-DES series. Writing those
documents raised ten, none of which this refactor introduced. **Nine are now closed. One
remains — OQ-DES-B3 — and it is not a defect:** it needs a decision about whether the
bulkhead web should be a variation axis, and the original intent turned out not to be
recoverable, so there is nothing to look up.

Seven were answered from design knowledge that had never been written down, and three of
those corrected a wrong inference rather than merely filling a gap:

- **OQ-DES-B1** — the 35° opening angle is a **half**-angle, tuned by experiment, and the
  70° mouth it produces is how the longeron snaps into the greeble. So the greeble retains
  the longeron as well as registering the corner, and its wall thickness is not free to be
  tuned for either job alone.
- **OQ-DES-B2** — the interconnect's trapezoidal cut is a **mass reduction**, not a
  clearance: full `2·bt` depth only at the corners where the load is, narrowed to `1·bt`
  between them. I had guessed it was relief for the panel to pass between bays.
- **OQ-DES-B4 and OQ-DES-B7** — the swept range is validated in hardware at **both**
  ends: a U=4 bulkhead assembled with 16 mm longerons and a corner, and a U=0.5 part with
  the tolerances working. These are the only physical test results anywhere in the
  repository, and between them they close OQ-DES-C2 as well.

  Worth recording *why* C2 was wrong, since the instinct behind it is a common one: it
  assumed a fit clearance ought to scale with the part. It should not. A snap fit is
  governed by what the printer can hold and what the material will flex, neither of which
  cares how large the airframe is — the same reasoning that keeps `longeron_tolerance`
  and `panel_tolerance` unscaled. Two prints settled an argument the geometry could not.

Both answers are recorded at the geometry as well as in the design documents, since that
is where someone would otherwise re-derive them wrongly.

**OQ-DES-B5 has also been answered, and withdrawn.** I had reported it as a defect — an
anchor bulkhead at U = 0.5 being 4 mm thick while the shortest M3 insert it is bored for
is 4.5 mm long. The premise was wrong: the insert is set from the interior face and may
stand proud of it, so it never needed to fit within the thickness. IP-GEO-19 is
withdrawn, and no validity check is warranted.

**Two genuine defects came out of the design documents, and both were dead parameters on
the bulkhead's interface** — found by writing down what the parts are for and then
checking the code against it, which is the whole argument for IP-GEO-11 existing:

- **OQ-DES-B6** — `greeble_tolerance`, threaded through four signatures and discarded by
  a local zero. Fixed in IP-GEO-21.
- **OQ-DES-C3** — `unit_length`, threaded through three signatures and used by none.
  Worse in kind than B6: it did not merely do nothing, it asserted that a bulkhead
  depends on bay length, which is the one thing the parameterisation exists to avoid.
  Fixed in IP-GEO-23.

**OQ-DES-B3 has a third kind of answer: the intent is not recoverable.** Whether the
`make_web` flag was meant to allow lighter bulkhead variants or was only ever a
mechanization of the type differences is not remembered. That is recorded in the design
document as an answer, not left looking pending, so nobody spends time trying to recover
it. The question survives as a forward decision rather than an archaeology problem.

**Worth noting about the pattern.** Of the questions answered so far, four corrected an
inference of mine rather than filling a blank, and one of those inferences had been
promoted to a work item. Reconstructed *structure* — what the code does, the transforms,
the dimension chains — has held up under every answer. Reconstructed *intent* has not.
The inference markers in the design documents should be read as a genuine warning rather
than a formality, and "the designer does not recall" is a legitimate terminal state for
one of these.

*No open questions — all three are resolved, and each note stays in numerical position
with its original analysis retained below the resolution.*

### ~~OQ-GEO-1 — Is grouping worth its cost for every group?~~ — RESOLVED 2026-08-06

**Chosen: alternative 4 — drop the grouping entirely and revert the greeble pilot.**
IP-GEO-10 is superseded; IP-GEO-16 and IP-GEO-17 replace it.

**Rationale.** The question as originally posed — *which* groups are worth converting —
was the wrong question. Assessed against Phase 3, the answer is none of them, because
none of the work survives.

The parameter groups **already exist in Python**: `null_parameters()` returns twelve of
them. They are flattened only to cross into OpenSCAD. So the refactor would not have
created structure; it would have built an *encoding* of existing structure in OpenSCAD
vectors, plus accessor functions to make that encoding safe. Both are workarounds for
OpenSCAD's lack of records. FreeCAD is driven from Python, where a group is a dataclass
and no encoding is needed, so the vector machinery *and* the Python change that feeds it
are discarded at the port.

This is the same call the project already made for units. `doc/guidelines/general.md`
exempts the OpenSCAD path from the SI standard because *"converting code that is
scheduled for replacement spends real risk for no benefit"* — with a worse risk profile
here, since a missed reference yields `undef` and renders anyway rather than failing.

**Caveats attached to the decision.**

- This does **not** apply retroactively to IP-GEO-2 through IP-GEO-9. Those were either
  Python-side, or small and verified, and justified by making the current path safe to
  *operate* through Phases 1 and 2 — a different rationale from readability.
- The pilot was not wasted. It produced three findings that stand independently: the
  `undef` propagation hazard, the GUI drivers as an uncounted third caller class, and
  OQ-GEO-2. The last of those is a live gap regardless of this decision.
- The general principle is now recorded in `doc/guidelines/general.md` under *Weigh a
  refactor against what replaces the code*, because the same question applies to every
  remaining Phase 2 item.

The original analysis follows, retained because the measured costs inform IP-GEO-16 and
any future decision of this shape.

---

Each parameter group can be collapsed into one vector argument with named accessor
functions. The pilot established what that costs: for `greeble`, 36 references across
two geometry files plus three GUI drivers, with five near-misses that would have
produced silently wrong geometry.

The benefit is not uniform across groups. Collapsing `greeble` removes 3 parameters from
each of 6 signatures. Collapsing `panel` removes 3 from each of 25. The cost, meanwhile,
scales with *occurrences* — 50 for greeble, 164 for panel — and so does the number of
places a bare reference can hide.

There is also a cost the signature count does not show: module bodies get noisier.
`greeble_thickness` becomes `greeble_thickness(greeble)` at every use.

**Alternatives**

1. **All six groups.** Signatures drop from 28 parameters to roughly 8.
   *Benefits:* uniform convention; the stated goal of IP-GEO-10 fully met.
   *Drawbacks:* ~600 references to convert, each a chance to leave an `undef`; bodies
   noticeably noisier; several days of careful work with a silent failure mode.
   *Prerequisites:* OQ-GEO-2 resolved, so drivers are verifiable.

2. **Only the high-signature groups — `panel`, `bolt`, `longeron`.** Covers 62 of the 86
   signature slots.
   *Benefits:* most of the readability gain for roughly half the risk; `bulkhead_section_full`
   still drops from 28 parameters to about 15.
   *Drawbacks:* mixed convention — some groups passed as vectors, others flat — which is
   itself a readability cost and a thing to explain.
   *Prerequisites:* same as 1.

3. **Stop after the greeble pilot; revert it.** Keep flat parameters throughout.
   *Benefits:* no further risk; the Python→SCAD boundary is already safe via keyword
   arguments (IP-GEO-2), which was the actual hazard. The remaining pain is verbosity in
   pass-through, which is mechanical and visible rather than silently wrong.
   *Drawbacks:* 28-parameter signatures remain; adding a parameter still means editing
   every level.
   *Prerequisites:* none.

4. **Drop IP-GEO-10 and revert the greeble pilot.** Keep flat named parameters in SCAD.
   *Benefits:* no further risk; consistent with how the project already treats this code.
   *Drawbacks:* 28-parameter signatures remain for the life of the OpenSCAD path.
   *Prerequisites:* none.

#### Assessed against Phase 3 — the FreeCAD port

The question that settles this is not "is grouping better?" but "does it survive?"

**It does not. IP-GEO-10 is entirely SCAD-side work on code scheduled for deletion.**

The parameter groups **already exist in Python**. `null_parameters()` returns twelve of
them — `corner`, `bulkhead`, `boom_bulkhead`, `panel`, `longeron`, `bolt`, `greeble`,
`plate`, `web`, `bulkhead_flange`, `cowl_flange`, `printer`. The structure this item
proposes to introduce is already there on the durable side; it is flattened only to
cross into OpenSCAD.

So what IP-GEO-10 actually builds is an *encoding* of that structure in OpenSCAD
vectors, plus accessor functions to make the encoding safe. Both are workarounds for
OpenSCAD's lack of records. FreeCAD is driven from Python, where the structure is a
dataclass and needs no encoding at all. Every line of the vector/accessor machinery is
discarded at the port, and the Python change — building vectors instead of passing
keywords — is discarded with it.

This is the same category the project has already ruled on. `doc/guidelines/general.md`
exempts the OpenSCAD path from the SI unit standard on exactly these grounds:
*"a deliberate exemption, not technical debt. The OpenSCAD implementation is
transitional: Phase 3 replaces it with Python-driven FreeCAD. Converting code that is
scheduled for replacement spends real risk for no benefit."* Grouping is that argument
again, with a worse risk profile: the unit conversion at least had a mechanical check,
whereas a missed reference here yields `undef` and renders anyway.

**Recommendation: alternative 4 — drop IP-GEO-10, revert the greeble pilot.**

What *would* serve the port, and is now tracked separately:

- **IP-GEO-16** — replace the nested parameter dicts with typed dataclasses in Python.
  This is the same structural idea applied to the side that survives, and it is the
  interface the FreeCAD generators will be written against. It also gets static checking,
  which the dict form cannot have.
- **IP-GEO-11** — the design documents. For a port, a written statement of what each part
  *is* and why is worth more than any amount of tidying of the implementation being
  replaced. This is the highest-value remaining item in the plan.

The work already completed under IP-GEO-2 through IP-GEO-9 is not affected by this
reasoning. Those were either Python-side (surviving), or small, verified, and aimed at
making the current path safe to *operate* through Phases 1 and 2 — which is a different
justification from making it nicer to read.

### ~~OQ-GEO-2 — How are the GUI driver files verified?~~ — RESOLVED 2026-08-06

**Chosen: alternative 1 — render each driver and treat failure *or warning* as an
error.** Built as [`verify_drivers.py`](../../src/Fuselage/tools/verify_drivers.py),
IP-GEO-15.

**Rationale.** "Does it still render" is most of the value for almost none of the cost —
a driver takes no arguments, so it is one `openscad -o` per file. Stored reference STLs
(alternative 2) were rejected because the drivers are hand-edited for experimentation, so
references would go stale legitimately and constantly.

**One change from the alternative as written: warnings count as failures.** OpenSCAD
reports an unknown identifier as a *warning* and carries on, substituting `undef`. The
driver still renders, still produces a shape, and still exits zero — just the wrong
shape. Checking only the exit code would have passed every case this tool exists to
catch.

**What it found on the first run** — all four genuine, none of them hypothetical:

| Driver | Finding |
| --- | --- |
| `fuselage_bulkhead.scad` | 292 warnings — "too many unnamed arguments", then `undef` propagating through `fuselage_corner_geometry.scad`. **Rendered 1,960 triangles and exited zero.** The half-applied greeble pilot; IP-GEO-17 clears it. |
| `fuselage_cowling_bulkhead.scad` | Same argument-count breakage, plus `Object may not be a valid 2-manifold and may need repair!` |
| `nose_cowl.scad` | **Pre-existing.** `Can't open import file 'vsp_nose.stl'` — byte-identical to HEAD, so not caused by this work. |
| `tail_cowl.scad` | **Pre-existing**, same cause. |

The cowl breakage is the clearest vindication of the item. Those drivers name their OML
mesh as `vsp_nose.stl`, resolved relative to `scad/`, but the meshes live in `../oml/`.
The sweep works because `oml_ref()` prepends `../oml/`; the GUI drivers were never
updated when the meshes moved, and nothing has rendered them since. Tracked as
IP-GEO-18.

**A caveat about the tool itself.** Its first version misclassified the two broken cowl
drivers as harmless aggregators: a failed import leaves no top-level geometry, OpenSCAD
exits non-zero on empty output, and the aggregator branch swallowed it. That is a
verification tool failing in the dangerous direction — reporting clean over a real
breakage — and it is the fourth time this project has seen that shape of bug. The
discriminator is now the warning list, checked first: empty output counts as an
aggregator only when nothing was reported.

The original analysis follows, retained because it records what the gap was before the
tool existed.

---

`fuselage_corner.scad`, `fuselage_bulkhead.scad`, `fuselage_cowling_bulkhead.scad`,
`fuselage_boom_bulkhead.scad`, `nose_cowl.scad`, `tail_cowl.scad` and
`fuselage_oml.scad` set concrete values and call one geometry module each. They are the
interactive path — how a person opens the geometry in OpenSCAD to look at it.

**No tool renders them.** `scad_snapshot.py` and `verify_sweep_change.py` drive the
Python sweep; `verify_scad_change.py` re-renders generated `.stl.scad` files. All three
reach the geometry modules only through the sweep's call path. A signature change can
therefore be verified as geometry-preserving while leaving every driver broken, which is
precisely what the greeble pilot was about to do.

This originally blocked IP-GEO-10, which is now superseded — but resolving that did not
resolve this. The gap is in the *tooling*, not in any one refactor: the drivers are
unverified today, and will stay unverified through every remaining change to
`src/Fuselage/scad/`, including IP-GEO-17's revert. It also applies to hand edits made
while working in the OpenSCAD GUI, which is how the geometry is actually developed.

The question therefore stands on its own merits and remains open.

**Alternatives**

1. **Render each driver to STL in CI-style verification** (IP-GEO-15). A driver takes no
   arguments, so this is one `openscad -o` per file.
   *Benefits:* directly tests the real interactive path; catches `undef` breakage, since
   an `undef` dimension makes the render fail or produce a measurably different solid;
   cheap to write.
   *Drawbacks:* the drivers set their own fixed parameters, so this tests one point per
   driver rather than a range; roughly 7 extra renders per verification run.
   *Prerequisites:* none.

2. **Compare driver output against stored reference STLs.** As above, plus geometry
   comparison rather than "did it render".
   *Benefits:* catches silent geometry change, not just failure.
   *Drawbacks:* needs reference STLs committed or generated once and trusted; the
   drivers are edited by hand for experimentation, so references would go stale
   legitimately and often.
   *Prerequisites:* a decision on where those references live.

3. **Delete the drivers**, on the grounds that the sweep supersedes them.
   *Benefits:* removes the whole class of problem.
   *Drawbacks:* loses the only way to open a part interactively and adjust it, which is
   how geometry is actually developed. Almost certainly wrong.
   *Prerequisites:* confirmation they are genuinely unused.

**Recommendation:** alternative 1, as IP-GEO-15, before any further work on IP-GEO-10.
"Does it still render" is most of the value and nearly free; a render failure is the
signature of exactly the `undef` breakage this refactor risks. Alternative 2 can follow
if it proves insufficient.

### ~~OQ-GEO-3 — What enforces the cross-language field order?~~ — RESOLVED 2026-08-06

**Chosen: alternative 1, strengthened — document on both sides, *and test both sides*.**
Alternative 1 as originally written was "accept it, documented as a contract in both
files", with no guard. The decision keeps the documentation requirement and adds the
test, because documentation alone does not survive the failure it guards against: a
reordered field produces plausible numbers in the correct units on both sides, and
nothing but an assertion notices.

**The standing rule.** Any parameter group crossing a language boundary positionally must

1. state its field order in a comment on **both** sides, each naming the other as its
   counterpart, and
2. carry a test that constructs the group on one side and asserts the fields arrive where
   intended on the other.

**This is dormant today.** `make_greeble()` was the only such contract and IP-GEO-17
removes it, after which nothing is encoded positionally anywhere — so there is no
documentation to write and no test to build right now. The rule goes live again the
moment the FreeCAD port serializes parameters positionally, which is exactly when it will
be least obvious that it applies. Recorded now rather than rediscovered then.

The original analysis follows.

---

`make_greeble(thickness, nub_thickness, tolerance, opening_angle)` defines the field
order in SCAD, and Python must build the same vector in the same order. Nothing checks
that they agree. Reorder one side and every part changes silently — the values are all
plausible numbers in the same units.

**Alternatives**

1. **Accept it**, documented as a contract in both files.
   *Benefits:* no work. *Drawbacks:* a silent failure mode with no guard.
2. **A round-trip test**: build a group in Python, render a fixture that echoes each
   field, assert the values land where intended.
   *Benefits:* actually enforces it. *Drawbacks:* needs an echo fixture per group.
3. **Have Python read the order from the SCAD source** and construct accordingly.
   *Benefits:* one source of truth. *Drawbacks:* parsing SCAD from Python is fragile and
   introduces a new failure mode to solve an old one.

---

## How each item is proven behaviour-preserving

Three independent checks, cheapest first. Each covers something the others structurally
cannot, so none of them substitutes for another.

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

**GUI driver render — [`verify_drivers.py`](../../src/Fuselage/tools/verify_drivers.py).**
Both checks above reach the geometry modules through the sweep's call path only. The
hand-edited driver `.scad` files are a second caller class with its own argument lists,
and a signature change can be proven geometry-preserving for every one of the 576 swept
parts while leaving every driver broken.

```text
uv run python src/Fuselage/tools/verify_drivers.py
```

**A warning is a failure here.** OpenSCAD reports an unknown identifier as a warning,
substitutes `undef`, renders a shape, and exits zero. On the run that found the
half-applied greeble pilot, `fuselage_bulkhead.scad` emitted 292 warnings and produced
1,960 triangles of wrong geometry with a clean exit status. Exit codes alone would have
reported success.

Cheap enough to run on every `.scad` edit: a driver takes no arguments, so it is one
render per file.

