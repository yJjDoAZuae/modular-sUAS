# FreeCAD Migration — Implementation Plan

**Scope:** Roadmap Phases 3–7 — porting the generators to FreeCAD and the capabilities that
port enables. Plan abbreviation `FC`.

**Design authority:**
[doc/architecture/freecad_migration.md](../architecture/freecad_migration.md) for the system
shape and the nine use cases; [corner.md](../design/corner.md),
[bulkhead.md](../design/bulkhead.md) and [cowl.md](../design/cowl.md) for the geometry being
ported. All three parts now have one — `cowl.md` was written as IP-FC-7 and immediately
unblocked IP-FC-16 and produced two new items, IP-FC-28 and IP-FC-29.

**Last updated:** 2026-08-07

---

> **The hand drivers are not a source of truth about parameters.** `fuselage_corner.scad` and
> `fuselage_bulkhead.scad` each exercise one hand-written configuration, and their constants
> disagree with what the sweep derives — `extrusion_width` 0.4 against 0.6, `panel_offset` 0
> against 2.5, `panel_overlap` 4 against 4.7625. Several are not free at all: `panel.offset`
> and `panel.overlap` are computed by `derived_parameters()`, so setting one and not the
> others produces a combination the sweep would never generate, which renders without
> complaint and is wrong. Read design questions against derived values, and render variants
> with [`render_variant.py`](../../src/Fuselage/tools/render_variant.py) rather than `-D`
> overrides. Comparisons in this plan that use driver values are valid as *port equivalence*
> tests — identical inputs on both sides — and say nothing about design intent.

## Reading this plan

Items are ordered by dependency, not by phase. The first six are **unblocked and can start
in any order, today** — they were chosen deliberately: each one either answers an open
question that shapes later work, or delivers value that does not depend on the port at all.

Three things are worth noticing about the shape of the plan:

- **IP-FC-4 (OML as a surface) is on the critical path and depends on nothing.** Until the
  OML is a surface rather than a 36 MB tessellated mesh, the cowls cannot be solid models,
  and Phases 4–6 would deliver B-rep export, assemblies and drawings with the cowls
  silently excluded.
- **IP-FC-1 decides an architecture, not a setting.** If `freecadcmd` startup is small next
  to a part's build time, the entire existing sweep driver survives with one call swapped.
  If it is not, the queue, the worker budget, the atomic writes and the retry path all need
  rework. Measure before building.
- **Four items are blocked only by open questions**, not by other work. Those OQs are
  answerable by design decisions rather than by code, so they are the cheapest way to widen
  the front.

---

## Work items

| ID | Status | Title | Depends on | Design refs |
| --- | --- | --- | --- | --- |
| IP-FC-1 | done | Measured `freecadcmd` startup at **0.24 s**; a boolean-heavy part builds in ~0.5 s. **Subprocess-per-part confirmed** — whole-sweep startup overhead is ~2.3 min | — | [freecad_migration.md §What must be preserved](../architecture/freecad_migration.md) |
| IP-FC-2 | done | [`params_snapshot.py`](../../src/Fuselage/tools/params_snapshot.py) — captures all 576 variants' parameter trees and diffs them to the field. Self-tested in both directions: identical code → 0 differences; a perturbed constant → exactly the 264 corner parts, naming `greeble.tolerance` | — | [freecad_migration.md §Verification](../architecture/freecad_migration.md) |
| IP-FC-3 | done | Record each part's print orientation. Confirmed: the modeled frame **is** the print frame, model `+z` is the build direction and corresponds to aircraft body `x`, and the per-part `z` sign is recorded in each design document | — | [bulkhead.md](../design/bulkhead.md), [corner.md](../design/corner.md), [cowl.md §7](../design/cowl.md) |
| IP-FC-4 | done | [`oml_export.py`](../../src/Fuselage/tools/oml_export.py) drives the committed `.vsp3` headlessly and writes real surfaces — 8 and 12 `BSplineSurface` faces, zero planar, 1.4 MB against 36 MB of STL. Scale resolved (IP-FC-37). **Do not repoint `oml_ref()`** — OpenSCAD cannot import STEP, so the STL stays until IP-FC-34 retires the OpenSCAD path. STEP now written to `oml/` beside the STL, with provenance recorded | IP-FC-37 | [cowl.md §1](../design/cowl.md), [freecad_migration.md §UC-9](../architecture/freecad_migration.md) |
| IP-FC-37 | done | Resolved the OML STEP export scale. OpenVSP is **dimensionless** — the header's `FOOT` label is an exporter artifact, not adjustable via `CADLenUnit`. The project convention (1 model unit = 1 m) is applied on import as `STEP_IMPORT_SCALE = 3.28084` | — | [cowl.md §2.1](../design/cowl.md) |
| IP-FC-5 | done | Prototyped the corner **both ways**. Both reproduce the OpenSCAD reference and each other; the greeble is the discriminator. See §IP-FC-5 findings below | — | [corner.md](../design/corner.md), [freecad_migration.md §OQ-ARCH-1](../architecture/freecad_migration.md) |
| IP-FC-38 | done | Re-emit the corner as a **parametric `Part::` CSG document tree** — document objects with expressions over a `Spreadsheet::Sheet`, not static shapes. Verify against the same OpenSCAD references and the same regenerate sweep the static port passed, then confirm the saved `.FCStd` is still editable after reload. Also settle the **downstream-edit workflow**: whether hand work lives in a separate document referencing the generated one (`App::Link` / `SubShapeBinder`) rather than editing it in place, since the sweep overwrites what it emits. This is what makes UC-2 real; the static `part_*.py` port stays as the verified reference | IP-FC-5 | [freecad_migration.md §OQ-ARCH-1](../architecture/freecad_migration.md), §IP-FC-5 findings |
| IP-FC-41 | active | **Sheet merge done** — one sheet per assembly, asserting no alias is defined two different ways; found two collisions across 96 aliases on first run. **Data hop done** — `derived_parameters()` now reaches FreeCAD as JSON, and all seven checked bulkhead modules' literals verify against it, with `corner_tree`'s six disagreements enumerated (§IP-FC-41). **Seeding done** — `build_sheet(doc, params, seed)` replaces every literal row from the authority and leaves the `=` rows, so a generator feeding the sweep no longer carries `fuselage_corner.scad`'s constants; run standalone with no seed it still reproduces its isolated reference. Where a module states a relationship (`corner_radius = U * 10`) against another's literal, the relationship wins and `check_seed` verifies it reproduces the authority's number. Reference `.scad` values are checked against the authority too | IP-FC-38 | [render_variant.py](../../src/Fuselage/tools/render_variant.py) |
| IP-FC-40 | done | `_sketch()` raises unless `FullyConstrained`, and `check_tree.py` re-asserts it at every size — not only the one the sketch was authored at. An under-constrained sketch deforms silently under a parameter change and still yields a valid solid | IP-FC-38 | §IP-FC-38 |
| IP-FC-39 | done | Write the user guide for the FreeCAD workflows — [doc/guide/freecad_workflows.md](../guide/freecad_workflows.md). Covers the derived-part workflow, linking, the four quiet failure modes, and which workflow serves which use case. Written ahead of the implementation deliberately: the design was chosen to serve these workflows, so they are the acceptance criteria. **Revisit as each capability lands** — the output table names the item that delivers each row | IP-FC-38 | [freecad_workflows.md](../guide/freecad_workflows.md) |
| IP-FC-32 | todo | Measure whether identical parameters yield byte-identical BREP serialization; if so, build a BREP-compare tier beside the parameter snapshot | — | [freecad_migration.md §OQ-ARCH-2](../architecture/freecad_migration.md) |
| IP-FC-33 | todo | Survey and trial every other shape-comparison method that could apply — mesh-to-B-rep deviation, section-curve compare, mass-property compare. Keep what works; deprecate only with a recorded demonstration that a method cannot be made to work | — | [freecad_migration.md §OQ-ARCH-2](../architecture/freecad_migration.md) |
| IP-FC-6 | todo | Survey permissively-licensed tooling for non-uniform printed-material analysis; record the finding either way | — | [freecad_migration.md §OQ-ARCH-8](../architecture/freecad_migration.md) |
| IP-FC-7 | done | Write [`doc/design/cowl.md`](../design/cowl.md) — the cowl had no design authority, and it is the subject of the most blocking work in this plan | — | [cowl.md](../design/cowl.md) |
| IP-FC-8 | todo | Write the SI↔mm conversion layer as one named module; verify by the bounding-box-÷1000 test | — | [general.md §Units](../guidelines/general.md) |
| IP-FC-9 | active | Port the bulkhead, forming the greeble by cutting with the corner's end **section description re-evaluated at greeble tolerance 0** — never with the corner's built shape, which carries the fit clearance. **The whole octant is done and verified** — sixteen modules, then assembled as `bulkhead_section` against the real module at +0.00011% (§IP-FC-9 progress), which is what binds the two inline-geometry transcriptions. The assembly caught a reading error no isolated reference could: the plate and longeron flange sit inside `if (is_cowling)`. What remains is the `octant_to_full` tiling | IP-FC-5 | [bulkhead.md §The greeble is a positive post](../design/bulkhead.md) |
| IP-FC-10 | blocked (IP-FC-1, IP-FC-9) | Swap the render call in the sweep driver, keeping the queue, worker budget, atomic writes and previews | IP-FC-1, IP-FC-9 | [freecad_migration.md §What must be preserved](../architecture/freecad_migration.md) |
| IP-FC-11 | blocked (IP-FC-10) | Replace `--resume`'s staleness key: hash the parameter object plus a geometry-code version, since no generated text exists to compare | IP-FC-10 | [freecad_migration.md §What must be preserved](../architecture/freecad_migration.md) |
| IP-FC-12 | blocked (IP-FC-10, IP-FC-4) | Port the boom bulkhead and the cowls. Preserve the OML transform algebra verbatim, including `offset_x` preceding the scale | IP-FC-10, IP-FC-4 | [cowl.md §2](../design/cowl.md), [cowl.md §6.3](../design/cowl.md) |
| IP-FC-13 | blocked (IP-FC-12) | Full-sweep equivalence against the OpenSCAD corpus by volume, bounding box and hole positions — **not** triangle count. **Two tiers, per OQ-DES-B9:** parts whose geometry is exactly reproducible (the corner) stay strict; parts carrying real fillets need a stated deviation tolerance and a comparison that measures deviation rather than volume equality. Interface dimensions are strict in both tiers — no interface is set by a fillet | IP-FC-12 | [freecad_migration.md §Equivalence between toolchains](../architecture/freecad_migration.md), [bulkhead.md §OQ-DES-B9](../design/bulkhead.md) |
| IP-FC-34 | blocked (IP-FC-13) | Retire the OpenSCAD implementation. Re-check the three design documents against the code **before** removing it, then delete `scad/` and the OpenSCAD driver path — history retains it | IP-FC-13 | [freecad_migration.md §OQ-ARCH-4](../architecture/freecad_migration.md) |
| IP-FC-14 | blocked (IP-FC-13) | UC-2 — export `.FCStd` per part from the sweep | IP-FC-13 | [freecad_migration.md §Use cases](../architecture/freecad_migration.md) |
| IP-FC-15 | blocked (IP-FC-13) | UC-3 — export `.step` per part from the sweep | IP-FC-13 | [freecad_migration.md §Use cases](../architecture/freecad_migration.md) |
| IP-FC-16 | todo | Write the cowl interior-surface algorithm document. Method decided: per-layer 2D inset, **curvature-adaptive** section spacing with a deviation-based termination test, surface **fit** with G1 tangency (threshold) and G2 curvature (objective), bidirectional curvature, **never ruled**. The open part is the near-horizontal material rule | IP-FC-7 | [freecad_migration.md §OQ-ARCH-5](../architecture/freecad_migration.md), [cowl.md §6.2](../design/cowl.md) |
| IP-FC-28 | todo | Resolve OQ-DES-CW2: what `cone_angle` measures, and whether it is a printability constraint. It is used as complementary angles at its two call sites | — | [cowl.md §4.2](../design/cowl.md) |
| IP-FC-30 | done | Establish each station's active section type. Resolved from the XML: read `<Type>` element TEXT, not the ParmContainer name, which is stale on 10 of 16 stations | — | [cowl.md §1.2](../design/cowl.md) |
| IP-FC-31 | done | OQ-DES-CW7 addressed: `oml_export.py --check` verifies the exported OML against a SHA-256 of the committed `.vsp3`, recorded in `oml/oml_provenance.json`. Exits non-zero when stale; needs no OpenVSP install, so it runs anywhere | — | [cowl.md §OQ-DES-CW7](../design/cowl.md) |
| IP-FC-29 | todo | Resolve OQ-DES-CW3: is `buttress.thickness = 0.05 mm` a wall or a cut clearance? Unscaled, and one eighth of an extrusion width | — | [cowl.md §4.1](../design/cowl.md) |
| IP-FC-17 | blocked (IP-FC-16) | Implement cowl interior surfaces | IP-FC-16, IP-FC-14 | *(IP-FC-16 output)* |
| IP-FC-18 | blocked (IP-FC-14) | Model the non-printed components — longeron, panel, threaded insert, bolt — derived from the clearances that already receive them | IP-FC-14 | [freecad_migration.md §UC-8](../architecture/freecad_migration.md) |
| IP-FC-19 | blocked (IP-FC-17) | UC-4 — assemblies with FreeCAD Assembly joints for unit, nose, tail and full fuselage. Includes asserting each solved placement against the placement constructed from parameters | IP-FC-17, IP-FC-18, IP-FC-35 | [freecad_migration.md §OQ-ARCH-6](../architecture/freecad_migration.md) |
| IP-FC-35 | todo | Confirm the Assembly workbench scripts under `freecadcmd` — create an assembly, add joints, solve, and read back placements, all headless. Prerequisite of IP-FC-19, no longer a gate on the decision | — | [freecad_migration.md §OQ-ARCH-6](../architecture/freecad_migration.md) |
| IP-FC-20 | blocked (IP-FC-18) | UC-8 tier 1 — mass properties: densities per component, mass, CG, inertia tensor | IP-FC-18 | [freecad_migration.md §UC-8 is a ladder](../architecture/freecad_migration.md) |
| IP-FC-21 | blocked (IP-FC-14) | UC-7a — part drawings as a **family drawing**: lettered dimension callouts plus a per-variant value table. Dimensions are named expressions over parameters, bound to topological references; interface dimensions are the required floor | IP-FC-14, IP-FC-36 | [freecad_migration.md §OQ-ARCH-7](../architecture/freecad_migration.md) |
| IP-FC-36 | todo | Define the dimension scheme: enumerate the interface expressions (starting from those already derived in the design documents), state the completeness test, and decide whether internal structure is dimensioned or shown as reference | — | [freecad_migration.md §OQ-ARCH-7](../architecture/freecad_migration.md), [bulkhead.md](../design/bulkhead.md), [cowl.md §4.1](../design/cowl.md) |
| IP-FC-22 | blocked (IP-FC-19, IP-FC-21) | UC-7b — assembly drawings | IP-FC-19, IP-FC-21 | [freecad_migration.md §OQ-ARCH-7](../architecture/freecad_migration.md) |
| IP-FC-23 | blocked (IP-FC-19) | UC-8 tier 2 — isotropic FEM with bonded interfaces as assembly properties | IP-FC-19, IP-FC-20 | [freecad_migration.md §UC-8 is a ladder](../architecture/freecad_migration.md) |
| IP-FC-24 | blocked (IP-FC-23) | UC-8 tier 3 — orthotropic material per part from the recorded print orientation | IP-FC-23 | [freecad_migration.md §UC-8 is a ladder](../architecture/freecad_migration.md) |
| IP-FC-25 | blocked (IP-FC-4) | UC-9b — drive OpenVSP for parametric nose and tail generation; VSPAERO force and moment on the fuselage | IP-FC-4 | [freecad_migration.md §UC-9](../architecture/freecad_migration.md) |
| IP-FC-26 | blocked (IP-FC-13) | UC-5 — Blender export path, explode transforms, animation paths | IP-FC-13 | [freecad_migration.md §Use cases](../architecture/freecad_migration.md) |
| IP-FC-27 | blocked (IP-FC-13) | UC-6 — new components, starting with one panel and its 2D vector cutting template | IP-FC-13 | [freecad_migration.md §Use cases](../architecture/freecad_migration.md) |

> **IP-FC-10 blocked reason:** Whether the driver keeps its thread pool or needs
> multiprocessing depends on IP-FC-1's measurement, and there must be at least one ported
> part to render.

> **IP-FC-12 blocked reason:** The cowls additionally need the OML as a surface (IP-FC-4)
> and a design document (IP-FC-7). Porting them against a tessellated mesh would produce
> parts that can never satisfy UC-2, UC-3, UC-4 or UC-7.

> **IP-FC-16 note:** OQ-ARCH-5 is decided — adaptive slice-and-fit. What remains is
> writing the algorithm down: how layers are sliced, how each is inset, how the sections
> are joined into a solid, and what supplies material where a horizontal surface would
> leave none. That last clause is the only part still genuinely open.

> **IP-FC-17, IP-FC-19 blocked reason:** A cowl cannot close as a solid without its
> interior surface, and an assembly of open shells is not an assembly.

> **IP-FC-19 note (OQ-ARCH-6):** Decided — Assembly joints, with each solved placement
> asserted against the placement constructed from parameters. IP-FC-35 confirms the
> workbench scripts headlessly; it is a prerequisite, not a gate on the decision.

> **IP-FC-21 note:** OQ-ARCH-7 is decided — a family drawing, lettered callouts over a
> per-variant value table, interface dimensions as the required floor. IP-FC-36 turns that
> into a concrete dimension scheme. Note IP-FC-5's finding that face count varies with `U`:
> dimensions must bind to expressions over parameters, never to face names.

> **IP-FC-24 blocked reason:** The layer axis per part is now recorded (IP-FC-3, done), so
> this waits only on the isotropic model it refines.


---

## IP-FC-5 findings — the corner, built both ways

Recorded 2026-08-08. Both paradigms reproduce the corner. The decision between them is
therefore not about capability, and the differences that do matter are listed below.

### Both match the OpenSCAD reference

Each section was isolated in OpenSCAD at the driver's parameters and compared by volume.
The residual is uniformly positive and proportional to volume, which is the expected
inscribed-polygon bias: OpenSCAD's `cylinder()` is a prism, so curved material renders
slightly small.

| Section | OpenSCAD mm³ | `Part::` mm³ | Delta |
| --- | --- | --- | --- |
| `corner_middle` | 4041.5795 | 4041.5808 | +0.000033% |
| `corner_end` | 551.8157 | 551.8276 | +0.0021% |
| `corner_transition` | 607.6699 | 607.6802 | +0.0017% |
| `fuselage_corner` | 10395.9609 | 10396.0066 | +0.0004% |

`PartDesign::` reaches the same numbers. Its octant matched the `Part::` half at
2020.790419 with a delta of **exactly zero**, and the finished `corner_end` matched the
`Part::` port to 2.5 × 10⁻⁷ mm³ — the two paradigms are computing the same solid, not
merely similar ones.

### A single volume is not enough on its own

`corner_end` was also compared band by band, at the heights the snap groove is defined by,
because a groove placed at the wrong height can still total correctly.

| Band | z | OpenSCAD mm³ | `Part::` mm³ | Rel |
| --- | --- | --- | --- | --- |
| bore | 0–1.2 | 115.132303 | 115.135458 | +0.0027% |
| lower ramp | 1.2–2 | 73.257081 | 73.258500 | +0.0019% |
| groove | 2–4 | 174.077455 | 174.080217 | +0.0016% |
| upper ramp | 4–4.8 | 73.257138 | 73.258500 | +0.0019% |
| bore | 4.8–6.01 | 116.091751 | 116.094920 | +0.0027% |

The two ramps agree with each other to six decimals in both tools, which is what confirms
the groove is centred rather than merely the right size. This is the embryo of IP-FC-33's
section-compare tier and it should be generalised there.

### The parameter regenerate

The whole corner was rebuilt at U = 0.5, 1, 2 and 4, with `bulkhead_thickness` from
`bulkhead_size_variants.csv` and a panel thickness legal at each size. All four produce one
valid solid matching OpenSCAD within 0.0041%, in about 0.6 s each.

**`Part::` has nothing to regenerate.** Parameters are a value object and a rebuild is a
re-run, so there is no stored feature tree to go stale. That is the paradigm's main
practical advantage in a 576-variant sweep.

**Face count is not stable across the range** — 52, 52, 52, then 32 at U = 4, as features
merge. Nothing may bind to a face name: not drawing dimensions (IP-FC-21), not assembly
joints (IP-FC-19), not fillets. This is the topological naming problem arriving on schedule,
and it argues for expressions over parameters everywhere.

### Where the paradigms actually differ

**The greeble is the discriminator, as expected.** Its snap groove is a full revolution
*interrupted* by a wedge, so the cutting tool is itself a boolean. `PartDesign::Groove`
revolves a sketch and has no way to trim its own tool; the closest native feature is a full
360° groove, which is wrong by 278 mm³ — half the part. Expressing it needs
`PartDesign::Boolean` cutting with a `Part::Feature`, which works and reloads clean.

**This answers the question IP-FC-9 was waiting on**, but not in the shape it was asked.
Cutting with an externally-supplied solid works in both paradigms. What must *not* happen is
reusing the corner's built shape — see below.

### The greeble is cut nominal, not from the corner's shape

`bulkhead_section()` cuts with `corner_end(...)` passing a literal `0` for the greeble
tolerance, against the corner's own `GREEBLE_TOLERANCE_CORNER_MM`. The comment in
`fuselage_bulkhead_geometry.scad` states the reason as an invariant: the post is nominal by
construction and all of the fit clearance is taken on the corner's bore, *because split
across both halves the joint would carry it twice*.

So "reuse the corner's end section" means reuse the **description**, re-evaluated at
tolerance zero — a second call to the same builder with different parameters. It does not
mean reuse the corner's solid, which is 0.05 mm oversize on the bore by design; cutting the
bulkhead with it would apply the clearance a second time and leave the snap loose.

**This rules out the natural `PartDesign::` idiom.** Reusing another Body's geometry there
is a `SubShapeBinder`, and a binder delivers the corner's *actual* shape — the toleranced
one. The tolerance would have to be re-applied as an offset afterwards, which is a second
representation of a dimension the parameters already carry. Both paradigms must instead
call the shared section builder twice with different tolerance arguments, which is exactly
what `corner_common.Params` already supports and what the OpenSCAD source does today.

This is a case where the automated tiers would not have caught the error: cutting with the
corner's own shape produces a valid solid, one solid, a plausible volume, and a 0.05 mm
loose fit that only shows up in a printed part.

**`mirror_xy` needs `TransformMode = 'Whole shape'`.** OpenSCAD's `mirror_xy()` wraps the
entire half-expression, so mirroring each feature individually is not equivalent — the
mirrored diagonal mask would trim the octant that just survived. Measured: `'Features'`
leaves the octant at 2020.790419, `'Whole shape'` gives 4041.580837, matching `Part::`.

### Three traps, all of which report success

Recorded because each produces wrong geometry silently, and the sweep must not rely on a
human noticing:

1. **`PartDesign::Pocket` cuts against its sketch normal.** A pocket on the same plane the
   pad grew from removes nothing and still reports `isValid() == True`, unchanged volume.
   Volume comparison catches it; nothing else in the tree does.
2. **A `Mirrored` whose `Originals` include itself** creates a dependency cycle that
   survives into the saved `.FCStd` and throws on any forced recompute. `body.addObject()`
   puts the feature in `body.Group`, so collect the originals *before* adding it.
3. **`if __name__ == '__main__'` does not work under `freecadcmd`.** It imports the script
   as a module named after the file, so `__name__` is `'part_end'` and the guard silently
   suppresses the entire script. Every ported entry point needs an argv-based check.

Measurements during construction are also untrustworthy while anything is touched; the only
figure worth reporting is one taken after a reload and a forced recompute, which is what the
sweep does anyway.

### "`Part::`" names two different things, and only one of them is editable

The prototype above used the **Part module Python API** — `Part.makeCylinder`, `.cut`,
`.fuse` — which returns a `TopoShape`: a solid with no history. It satisfies UC-1 and UC-3
and **fails UC-2**, because a `.FCStd` containing a static shape offers a downstream editor
nothing to edit. That is a property of the API chosen, not of `Part::`.

**`Part::` document objects are a different thing with the same name.** `Part::Cylinder` has
live `Radius` and `Height` properties, `Part::Cut` has `Base` and `Tool`, and together they
form a parametric CSG tree — the same structure as the OpenSCAD source, one node per
operation. Measured 2026-08-08:

- built headless, with every dimension an **expression** over a `Spreadsheet::Sheet`, so the
  parameters are a visible editable table rather than baked numbers;
- exact — agreement with the closed form to 10⁻¹¹ mm³ across U = 0.5, 1, 2, 4;
- **survives save and reload with expressions intact** (`Outer.Radius` reloads as
  `Params.U * 10`), and recomputes correctly when the spreadsheet is edited afterwards;
- a downstream editor can clear one expression, set that primitive by hand, and the rest of
  the tree stays live and driven.

### How a hand edit interacts with a generated tree

Measured 2026-08-08, because "editable downstream" is worth nothing if the first edit fights
the generator. A CSG tree and a hand edit **coexist structurally** — but on three specific
terms, none of which is announced.

**A node added downstream of the generated tip survives and recomputes.** A user `Part::Cut`
taking the generated tip as its `Base` stays valid and follows a parameter change. What it
does *not* do is follow it meaningfully: with hard-coded dimensions, the user's 5×5 box
removed 248.67 mm³ at U=1 and **0.00 mm³ at U=2**, because the enlarged bore swallowed it.
The edit persists and silently loses its intent. A hand edit has to bind to the parameter
table the same way the generator does, or it is only correct at the size it was made.

**Writing a property that carries an expression is silently discarded.** The assignment
raises nothing and reads back as the new value — `Radius` reported 25.0 — and the next
recompute reverts it to 10.0. Anyone editing a bound dimension in the GUI sees their change
take and then vanish.

**Clearing an expression is permanent and invisible.** Once unbound, that dimension stops
tracking the table with no marker distinguishing it from one that never was: at U=4,
`Outer.Radius` held 25.0 while `Bore.Radius` correctly followed to 8.0. Two dimensions that
were coupled diverge with nothing recording that a decision was made.

**None of this is specific to CSG trees** — `PartDesign::` has identical expression
semantics. The genuine conflict is at the *file* level: the sweep re-emitting
`corner_U1_FX1.FCStd` destroys whatever a human put in it, whichever paradigm wrote it. The
mitigations are the sweep's staleness key (IP-FC-11) and the derived-part workflow below.

### The derived part: two mechanisms, and only one does both jobs

The wanted workflow is a modified part that starts from a generated one, where the user can
**both** re-parameterise the original — a tolerance, a bolt diameter — **and** add or
subtract their own geometry, such as a mounting bracket or a clearance notch. Both
mechanisms were measured 2026-08-08.

**`App::Link` gives geometry reuse, and only that.** The link resolves across documents,
follows the source live when its parameters change, and accepts user geometry fused or cut
onto it. What it cannot do is let the referencing document drive the source's parameters:
the only route is re-pointing the *source's* expression at the user document
(`<<linked_user>>#MyParams.U`), which works but edits the generated file — the exact thing
the sweep overwrites. Note also that an external link requires the **linking** document to
already exist on disk; a derived part can never be a scratch document.

**Re-running the generator into the user's document does both.** The user's file owns a
parameter sheet, the generated CSG nodes, and their own features. Measured: changing
`longeron_tolerance` 0.05 → 0.25, `bolt_diameter` 4 → 6 and `U` 1 → 1.5 each propagated
through to the final solid, with a user bracket fused on and a user notch cut out, all
valid, and all surviving save and reload with expressions intact.

Two properties make repeated generation safe, and both are required:

1. **Generated objects carry a `Generator` tag**, so a regenerate can tell its own nodes
   from the user's and touch only its own. Re-running produced **0 duplicate nodes**, left
   all four user nodes in place, and did not undo the user's parameter overrides —
   parameter *values* are written only when the sheet is first created.
2. **The tree terminates in a stable tip.** User features bind to `Tip` and nothing else,
   so the generated internals can restructure — which IP-FC-5 showed they do, face count
   moving 52 → 32 across `U` — without invalidating anything downstream. After a
   regenerate, `UserFuse.Base` was still `Tip`.

**Use both, for different jobs.** `App::Link` where you want one source of truth and
automatic propagation and do not need to re-parameterise — assemblies (UC-4) especially,
which should reference the real generated parts. The derived-part regenerate where the point
is a modified variant of a part.

The caveat from the hand-edit measurement applies here too: user geometry must bind to the
parameter table to stay meaningful. A hard-coded bracket is correct only at the size it was
drawn.

---

## IP-FC-38 — the corner as a CSG tree

Recorded 2026-08-08. **Complete.** The whole corner — end, transition, middle, and the
mirrored half — is emitted as a live document tree of 82 nodes and 2 sketches, and every
section matches both the OpenSCAD reference and the static `Part::` port.

| Node | Tree mm³ | OpenSCAD mm³ | Rel | Static port mm³ |
| --- | --- | --- | --- | --- |
| `EndCutGroove` | 551.827595 | 551.815740 | +0.0021% | 551.827595 |
| `TransCutRelief` | 607.680165 | 607.669902 | +0.0017% | 607.680165 |
| `MidSection` | 4041.580837 | 4041.579501 | +0.0000% | 4041.580837 |
| `Tip` | 10396.006622 | 10395.960897 | +0.0004% | 10396.006622 |

Bit-identical to the static port at the driver's parameters, with the same 52 faces. Across
the regenerate the two diverge very slightly at the largest size — 585955.230 against
585955.545 at U=4, 5 × 10⁻⁷ relative, with 34 faces against 32 — so the booleans resolve
marginally differently there. Both are within 0.004% of OpenSCAD and both are one valid
solid.

### The profile decomposes into primitives — no sketches needed

Not obvious from the source, and worth recording because it is what makes the tree simple.
Each polygon mask in `corner_middle_shape` is a union of half-planes:

- the **longeron chamfer**, `[(0,0), (-far,0), (-far,-far), (0,-far)]`, is the third
  quadrant — one axis-aligned box;
- the **mirror-line mask**, `[(-far,-far), (far,far), (far,-far)]`, is the half-plane
  `y < x` — one box rotated −45°;
- the **bulkhead boundary** is an 8-gon whose vertices `(-4, 1.55)`, `(-2.45, 0)`,
  `(0, -2.45)` and `(1.55, -4)` are **collinear** on `x + y = flat_offset`. It is therefore
  the union of three half-planes — `x < flat_x`, `y < flat_x`, `x + y < flat_offset` — so
  three boxes, one rotated 45°.

So every mask is a `Part::Box` whose size and placement are expressions. Nothing is baked.
The half-plane placements are derived **in the spreadsheet** rather than in expressions on
the objects, so the trigonometry is visible to whoever opens the file.

### Verified to the same bar as the static port

| U | bt | pt | OpenSCAD mm³ | tree mm³ | Rel | Faces |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 | 4 | 2 | 567.06317 | 567.01817 | −0.0079% | 14 |
| 1 | 6 | 4.77 | 4228.64541 | 4228.65064 | +0.0001% | 14 |
| 2 | 8 | 4.77 | 35184.49573 | 35185.52607 | +0.0029% | 14 |
| 4 | 16 | 4.77 | 246622.72699 | 246632.74517 | +0.0041% | 10 |

At the driver's parameters the tree gives **4041.580837** — bit-identical to the static
`Part::` port. A regenerate is now editing a spreadsheet cell and recomputing, not re-running
a script, and all four sizes stay one valid solid with no stale nodes. Reloaded, the document
is still a live tree, expressions intact; changing `longeron_tolerance` from 0.05 to 0.25
moved the volume by −54.99 mm³, and a user bracket bound to `Params.corner_radius` followed
across sizes (276.65 mm³ at U=1, 271.66 at U=2) instead of vanishing the way the hard-coded
one did.

### Sketches, for the polygons that do not decompose

`corner_end`'s wedge is a non-convex hexagon with no collinear vertices and no nice angles;
it will not decompose. Sketches are the answer, and they work: a sketch's raw coordinates are
not expression-bindable but its **constraints** are, and an expression-driven sketch
recomputes correctly headless and survives save and reload.

**With one absolute requirement: the sketch must be fully constrained.** Six lines are 24
degrees of freedom; closing the chain into a loop removes only 12. An under-constrained
sketch whose driven dimensions change lets the solver deform everything else to suit, and it
does so silently — the extrusion is still a valid solid of the wrong shape. Measured: the
same polygon gave 28.00 mm² fully constrained and 28.48 mm² under-constrained at the *same
nominal values*, drifting further with every edit. Generated sketches must assert
`FullyConstrained` before use.

**A parameter alias may not collide with a unit symbol.** `w` (watt) and `h` (hour) are both
rejected as `Invalid alias`. Name parameters in full.

The snap groove decomposed as predicted — bore cylinder, expanding cone, rib cylinder,
contracting cone, fused — so only two polygons in the whole corner needed sketches:
`corner_end`'s wedge and `corner_transition`'s relief. Both are generated fully constrained
and both reproduce their `Part::` equivalents to **exactly zero**.

### The regenerate, on the whole corner

| U | bt | pt | OpenSCAD mm³ | Tree mm³ | Rel | Faces |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 | 4 | 2 | 1569.70900 | 1569.60773 | −0.0065% | 52 |
| 1 | 6 | 4.77 | 10887.97936 | 10888.03662 | +0.0005% | 52 |
| 2 | 8 | 4.77 | 83209.34993 | 83211.84701 | +0.0030% | 52 |
| 4 | 16 | 4.77 | 585931.71560 | 585955.23049 | +0.0040% | 34 |

Zero failures, and the checks now include *every sketch still being fully constrained* at
every size, not just at the one it was authored at. Reloaded, the document is still live:
`greeble_tolerance` 0.05 → 0.25 moved the volume by −47.27 mm³, and a user bracket bound to
`Params.corner_radius` followed across sizes.

### Two traps found by building it

**A duplicate node name silently becomes a dependency cycle.** `_section()` already owns
`tag + 'CutBore'` for the longeron bore, and reusing that name for the greeble bore re-fetched
the existing node and re-pointed its `Base` at a descendant. FreeCAD reports only
`The graph must be a DAG`, after which recompute order is wrong and unrelated shapes come
back null — the visible symptom was `EndSection: Base shape is null`, four nodes away from
the cause. `_owned()` now asserts each name is touched exactly once per `emit()`.

**`Placement.Base` of a rotated box is the corner *after* rotation.** This differs from
`Part.makeBox(...).rotate(origin, axis, angle)`, which turns an already-placed box about the
world origin. Giving the mouth its unrotated corner put it 4 mm out and removed 12.07 mm³ too
much — a valid solid, one solid, 2.19% wrong. The two diagonal masks were already derived in
the rotated frame, which is why the middle section had matched all along and hid the problem.
The unrotated corner must be rotated into place: `(-2r, -r)` becomes `(-r, -3r)/sqrt(2)`.

---

## IP-FC-9 progress — the greeble-forming tool

Recorded 2026-08-08. The bulkhead is a much larger port than the corner — 849 lines and 24
modules, with webs, flanges and four fillet modules. The part of it that carries risk is the
*interface*, so that was built and verified first; the rest is more of the decomposition
already proven on the corner.

**The tool matches.** 557.758041 against the OpenSCAD reference's 557.746362, **+0.0021%** —
the same inscribed-polygon bias as every other section — spanning z −0.0100 to 6.0200
exactly, one valid solid.

**Reading the call site closely mattered.** `bulkhead_section()` passes two arguments that
differ from the corner's own end section, and only one of them was in the plan text:

| | Corner's socket | Bulkhead's post tool |
| --- | --- | --- |
| greeble tolerance | 0.05 | **0** (literal, not a parameter) |
| bulkhead thickness | `bt` | **`bt + 2*eps`** |
| bore radius | 2.90 | 2.85 |
| rib height (`bt/3`) | 2.0000 | **2.0067** |

The thickness bump is not decoration: it changes the rib height and every nub z level, and
the whole shape is then shifted down by `eps` to clean up the bottom of the cutout. A port
that copied only the tolerance would have been wrong by a rib height.

**The clearance is asserted to appear once.** `corner bore − post bore = 0.0500 =
greeble_tolerance`, checked in the script rather than left to inspection. This is the
invariant the design document states — split across both halves, the joint would carry it
twice.

**Structurally, this is what "reuse the description" means.** `corner_tree.greeble_socket()`
and `end_section()` now take an alias prefix, so the same builders are evaluated against a
second set of spreadsheet rows (`gt_*`) derived from the shared ones. The post and socket
cannot drift apart because both come from the same expressions. Referencing the corner's
*built shape* — the natural `PartDesign::` idiom, a `SubShapeBinder` — would deliver the
toleranced solid and silently apply the clearance twice.

### `Part::Offset2D` matches a single offset and diverges on the fillet chain

Measured next, because the bulkhead's web is built with `offset(r = -web_width)` and
`fillet_inner(web_fillet_radius)`, and everything downstream depends on those porting
faithfully. `fillet_inner` is itself a morphological construction:

```scad
intersection() { offset(-r) offset(2r) offset(-r) children; children; }
```

Isolated on a polygon with both convex and concave corners:

| Step | OpenSCAD | `Part::Offset2D` | Delta |
| --- | --- | --- | --- |
| raw | 750.000000 | 750.000000 | 0 |
| `offset(r=-3)` | 309.865500 | 309.862833 | −0.00086% |
| then `offset(-2)` | 60.734761 | 60.730092 | −0.0077% |
| then `offset(+4)` | **453.820893** | **384.092910** | **−15.4%** |
| then `offset(-2)` | 244.711834 | 197.278760 | −19.4% |

**A single offset is faithful.** Both the erosion steps match to under 0.01%, and the
bounding boxes agree exactly — [5,35] × [5,15] eroded, [1,39] × [1,19] dilated — so the
offset *distance* is right and this is not a join-style or units problem.

**The divergence appears once the intermediate shape fragments.** The erosion leaves two
disjoint islands, and the dilation of those islands differs: FreeCAD's total is 69.73 mm²
short. Every `Join` and `Fill` combination was tried — `Tangent` fails outright with
"offset result has no wires", `Intersection` gets closest at 397.83 and is still 12% short.
Offsetting each island in isolation and fusing gives byte-identical areas (127.0465,
257.0465), so FreeCAD is not clipping them against each other; its dilations are simply
smaller. Matching bounding boxes with smaller area means the two disagree about the shape's
interior, not its extent.

**This was not a defect to fix but a semantic difference to decide about**, and it is
decided: OpenSCAD's `fillet_inner` is an *approximation* of a fillet, built from offsets
because OpenSCAD has no fillet operation. FreeCAD has one, so the port uses **real fillets**
that closely resemble the OpenSCAD version without matching it to hundredths of a
millimetre. See [OQ-DES-B9](../design/bulkhead.md).

The single offset stays — `Part::Offset2D` reproduces `offset(r = -web_width)` to 0.01%, so
only the morphological *fillet* chain is replaced, not the erosion that precedes it.

### `Part::Fillet` is safe for dimension changes and fails loudly on topology changes

Measured once OQ-DES-B9 settled on real fillets, because `Part::Fillet` stores its targets as
edge references and IP-FC-5 already showed edge counts moving with `U`. A fillet that
silently relocated to a different edge would be the worst version of the topological naming
problem — a stress-relief feature in the wrong place.

It does not do that.

| Change | Result |
| --- | --- |
| `slot_w` 10 → 16, topology constant | **Correct.** Volume tracks 7058.58 → 6488.58, still four arcs at r=2, stored references still name the concave verticals |
| `slot_d` 20 → 45, slot breaks through | **Fails visibly.** `Missing edge link`, state `['Touched', 'Invalid']`, recompute reports failure |

FreeCAD stores a *topological name*, not a raw index — `;Edge3;:M;CUT;:Hd8a:7,E.Edge21` —
and when it cannot resolve one it errors instead of guessing. That is the opposite of the
silent failures catalogued above, and it makes real fillets usable in a generated document.

**One trap, and it is the familiar shape.** When the fillet fails, its `Shape` goes *stale*
rather than null: `Volume` still returns 6488.5841 and `isValid()` still returns `True`.
Only `State` records the failure. Anything that reads a generated shape must check `State`,
not `isValid()`.

Fillet targets are therefore selected by a **geometric predicate** at emit time — never a
hand-picked index — so re-running the generator re-derives them and a topology change is
repaired by regeneration rather than by hand.

### A positional-argument defect, and an audit for others

Porting means reading every call site against its signature, which is how OQ-DES-B10
surfaced: `greeble_bolt_web`'s single call passes its last three arguments in rotated order.
OpenSCAD matches positionally and reports nothing, and `plate_thickness` and
`flange_thickness` are both 0.8 at the driver's settings, so one of the three lands correctly
by coincidence and the result looks right. The effect is a diagonal web 25% thicker than the
flange thickness intends, in a load path — and it would change shape for no visible reason
the first time layer height or extrusion width moved.

**Fixed 2026-08-08.** The measured effect is narrower than it first looked: the module's
material is entirely absorbed by its neighbours at the smaller sizes, so those bulkheads are
bit-identical whether the call is corrected, left alone, or removed outright — confirmed at a
real swept variant (U=1.0 `end_bolt` 3/16 in, 6922.5048968 mm³, 29000 triangles, unchanged)
as well as at the driver's values. No part printed at U=1 was ever affected. Only at U=4,
where the bolt sits 32 mm out and the diagonal web is no longer covered, does the module
carry material (1584.75 mm³), and there the correction moves about 0.1% of the part.

**A correction to the first analysis: the hand drivers are not authoritative about
parameters.** `fuselage_bulkhead.scad` uses `extrusion_width = 0.4`, which makes
`flange_thickness` and `plate_thickness` both 0.8 and left one of the three rotated arguments
accidentally correct. The sweep derives `extrusion_width = 0.6` through
`derived_parameters()`, giving 1.2 and 0.8, and there **all three were wrong**. Every design
question must be read against derived values; a driver exercises one hand-written
configuration and its constants are not design intent.

Since one call had drifted, the rest were checked rather than assumed:
[`audit_call_args.py`](../../src/Fuselage/tools/audit_call_args.py) parses every module
signature and call site and flags **permutations** — a passed identifier that is itself one
of the callee's parameters, but not the one at that position. Callers using a more specific
name for a generic parameter (`web_fillet_radius` → `radius`) are normal and not flagged;
the first draft reported 14 of those and was refined until the signal was clean.

**Result: exactly one, across all of `src/Fuselage/scad`.** B10 is isolated, not a pattern.

### Ported so far

Built at the **derived** parameters for U=1.0 `end_bolt` 3/16 in, read off the `.scad` that
`render_variant.py` emits — not the hand driver's constants.

| Piece | Tree mm³ | OpenSCAD mm³ | Delta |
| --- | --- | --- | --- |
| greeble-forming tool | 557.758041 | 557.746362 | +0.0021% |
| flange base profile | 709.2890625 | 709.2890625 | **exact** |
| simple positives | 1090.6890692 | 1090.6367096 | +0.0048% |
| `bulkhead_web` | 223.8867259 | 223.8866978 | +0.0000% |
| `outer_corner_fillet` | 8.344397 | 8.346225 | −0.0219% |
| `bulkhead_flange_chamfer` | 151.536167 | 151.535166 | +0.0007% |
| `greeble_to_web_fillet` | 3.142761 | 3.143595 | −0.0265% |
| `greeble_bolt_web` | 55.4371716 | 55.4365498 | +0.0011% |
| `bulkhead_bolt_flange_fillet` | 38.156942 | 38.158240 | −0.0034% |
| `web_to_bolt_fillet` | 89.952582 | 89.953955 | −0.0015% |
| flange boss quadrant | 352.482196 | 352.464253 | +0.0051% |
| **`bulkhead_flange_positive` assembled** | **982.5070699** | **982.5042986** | **+0.00028%** |
| the five cut tools, union'd | 49813.5377750 | 49813.5203117 | +0.00004% |
| greeble tool, at the **swept** values | 733.0315637 | 733.0190085 | +0.0017% |
| **`bulkhead_section` assembled** | **865.7700557** | **865.7690714** | **+0.00011%** |
| **`bulkhead_section_full` — the whole part** | **6922.5127750** | **6922.5048968** | **+0.00011%** |
| **`fuselage_corner` at the swept values** | **14146.8943305** | **14146.8357350** | **+0.00041%** |

The fillets read **smaller** than OpenSCAD, which is the correct sign and worth noting:
they are a block minus a cylinder, so FreeCAD's true circle removes more material than
OpenSCAD's inscribed prism. Everywhere the part is bounded by curved *material* the sign is
the other way. A fillet whose delta came out positive would be evidence of an error, not of
tessellation.

The flange base is exact because it is entirely planar — no tessellation bias to absorb. The
other two carry curved surfaces and show the usual inscribed-polygon bias.

**The flange profile needs no sketch.** Its larger polygon,
`(0,0) (0,5.1375) (-40,5.1375) (-40,3.9375) (-8.5625,3.9375) (-8.5625,-8) (-8,-8)`, has
exactly one non-axis-aligned edge — the closing one, along `y = x`. So it is two boxes minus
the half-plane `x > y`. The second polygon is the flange strip again and lies wholly inside
the first; it is not redundant in the source, because a cowling bulkhead skips the first and
builds only that one.

The simple positives — bolt boss, its web and chamfer, the plate, the longeron flange and its
chamfer — are all cylinders, cones and boxes.

**Three profiles in a row have decomposed the same way**, and the pattern is worth naming:
these polygons are axis-aligned except for one closing edge along `y = x`, so each is a small
stack of boxes minus the half-plane `x > y`. It has held for the corner's section, the flange
base and the web. `bulkhead_web`'s profile also carries a deliberate step, which exists so the
fillet cylinder has material to round.

**OQ-DES-B9 turns out not to bear on the frame bulkhead at all.** `fillet_inner` is called
once in `fuselage_bulkhead_geometry.scad`, and the only path reaching it is the *boom*
bulkhead. `bulkhead_web` — which the end, interconnect and cowling bulkheads do use — already
makes a true fillet by subtracting a cylinder. So the decision governs the plate family, and
the frame bulkhead ports without it.

**Still no sketches.** Eleven modules in and every profile has decomposed into boxes,
cylinders and cones. `greeble_bolt_web`'s plan view is a *parallelogram* — a strip of width
`flange_thickness/2` laid along the corner-to-bolt diagonal — so it is a single box rotated
−135°. Where a prism runs off-axis, it is built in the frame the source draws it in and the
composed rotation applied to the result, rather than solving its cutting planes in world
coordinates; `corner_tree._relief()` set that pattern and it has held four times since.

**The two bolt fillets extrude a five-vertex polygon, but the fifth vertex carries no area.**
The source builds it as the fillet centre pushed one radius along the ray *from the bolt
centre*, so bolt centre, fillet centre and end point are collinear by construction and the
closing edge doubles back on the edge that reached it. The enclosed region is the
quadrilateral of the first four vertices at any parameters — a property of how the point is
defined, not an artifact of one parameter set. Taking the quad also sidesteps the case seen
at U = 1.0, where `x_corner_fillet_start` clamps to the bolt centre and two vertices
coincide: a sketch would need a zero-length edge, whereas the half-plane decomposition
degenerates to the triangle on its own.

Each quad is convex, so it is a box clipped by the half-planes of its non-axis-aligned edges.
The edge from bolt centre to fillet centre lies at no fixed angle, so **its clipping box takes
its rotation from an expression** — `atan2(dy; dx)` bound to `Placement.Rotation.Angle`. That
is the first node in the port whose *orientation* is parametric rather than a literal, and it
confirms the placement rotation can be expression-driven at the same time as `Placement.Base`,
with the axis preserved.

### `bulkhead_flange_positive` assembled — and what it proves

The eight positives now fuse into the real module's shape at **+0.00028%**, one valid solid,
bounding box matching. This matters beyond the number: the quadrant boss is built *inline* in
the source rather than as a named module, so [`ref_flange_boss.scad`](../../src/Fuselage/freecad/ref_flange_boss.scad)
has to transcribe it, and on its own that file only proves the port matches the
transcription. The assembly reference goes through `bulkhead_flange_positive` itself, so a
transcription error would show up here as a volume divergence. Isolated references are the
convenient check; the assembled one is the binding check.

**IP-FC-41, partly done.** The constituents each carried their own parameter sheet, which was
fine in isolation and would have collided the moment two shared a document.
[`bulkhead_positive.py`](../../src/Fuselage/freecad/bulkhead_positive.py) merges them into one
and *asserts* no alias is defined two different ways. Running that check found exactly two
collisions across 96 aliases, both a name reused for a different quantity — `boss_r` (bolt
boss radius vs flange outer radius) and `flange_x` (the far end of the flange run vs the
flange's inner face). Both were renamed. The check is kept permanently rather than run once,
because the failure mode is silent: FreeCAD would take whichever definition landed in the row
and the geometry would quietly follow the wrong one. Seeding the merged sheet from
`derived_parameters()` rather than from literals is covered below.

### The cut side — and the last word on sketches

All five cut tools now port and verify as a union at **+0.00004%**, bounding box exact
([`bulkhead_cuts.py`](../../src/Fuselage/freecad/bulkhead_cuts.py)). Two of them are worth
recording.

**`octant_mask` is the `x > y` half-plane again.** Its three vertices —
`(R+eps, R)`, `(R+eps, -W/2-R)`, `(-W/2-R+eps, -W/2-R)` — look arbitrary until the deltas
come out equal on both axes, `2*corner_radius + unit_width/2`, which makes the hypotenuse the
line `y = x - eps`. So it is a box minus the same half-plane every other profile in this port
has needed, just shifted by `eps`.

**The opening wedge is the only shape in the whole bulkhead with genuinely arbitrary
angles** — two radial edges at `45 ± greeble_opening_angle` closing on a chord. It is still
not a sketch: being convex it is a covering box clipped by three half-planes, two of which
take their rotation from expressions. The chord's clip is a fixed −45°, because the chord is
normal to the diagonal whatever the opening angle is.

**So the entire bulkhead ports with no sketches of its own.** Sixteen modules, every profile
a decomposition into boxes, cylinders and cones. Worth stating plainly because it was not the
expected outcome — the working assumption at IP-FC-38 was that arbitrary polygons would force
sketches, and instead the half-plane decomposition has absorbed every one of them, including a
five-vertex polygon with a degenerate vertex and a triangle with no axis-aligned edge at all.

The assembled section does contain one sketch, and the exception is instructive rather than
awkward: the greeble tool *is* `corner_end`, and `corner_end`'s wedge is one of the corner's
two genuinely non-convex profiles. Reusing the corner's description brings the corner's sketch
with it. That is the design working as intended — one description, two mating halves — and it
is the only sketch in the part.

### `bulkhead_section` assembled — and the reading error it caught

The whole octant now matches the real module at **+0.00011%**, one valid solid, bounding box
exact ([`bulkhead_section.py`](../../src/Fuselage/freecad/bulkhead_section.py)). That binds
the `ref_bulkhead_cuts.scad` transcription the same way the positive assembly bound
`ref_flange_boss.scad`.

**It did not pass first time, and what it caught is the reason to build it.** The port carried
5.87 mm³ of extra material standing in the first quadrant. The cause: in `bulkhead_section`,
the plate, the longeron flange and the flange's chamfer are inside `if (is_cowling)`. The
brace opens forty lines above them, past two `intersection()` blocks, and nothing in their
immediate surroundings says so — an ordinary bulkhead has no longeron flange at all.

Comparing `simple_positives.py` against its own reference could never have found this:
[`ref_simple_positives.scad`](../../src/Fuselage/freecad/ref_simple_positives.scad)
transcribes the same three inline blocks and inherited the same misreading, so the two agreed
with each other while both were wrong. **An isolated reference checks a port against a reading
of the source; only the assembled one checks the reading.** The module now builds the six in
two groups — `bolt_positives` and `cowl_positives` — so the assembly takes only the three an
ordinary bulkhead is entitled to, and the reference still renders all six deliberately.

Localising it was worth recording as a technique. The failing bounding box said the excess sat
at x > 0; intersecting both the port and the OpenSCAD render with the same probe box narrowed
it to 5.87 mm³ between the 80° wedge ray and the nub radius; then measuring *each* positive
and *each* negative against the same box showed every cut tool agreeing to five decimals while
the positives filled the box on both sides. Since the source's result there was empty, the
error had to be a positive that should not exist — which pointed straight at the condition.

### The tiling, and the whole part

`octant_to_full()` is `mirror_x(mirror_y(mirror_xy(...)))` — three nested doublings about the
fuselage centre, which port as seven `Part::Mirroring` document objects and seven fuses. The
tiling stays in the parametric tree; nothing is rebuilt, so nothing can fall out of sync with a
downstream edit ([`bulkhead_full.py`](../../src/Fuselage/freecad/bulkhead_full.py)).

**The full part is not eight times the octant**, which is what makes this a real check rather
than an arithmetic one. `octant_mask` is shifted by `eps`, so adjacent octants overlap by a
sliver the union reclaims: 6922.50 against 8 × 865.77 = 6926.15, a 3.65 mm³ difference. A
mirror about the wrong plane would still give eight copies and a plausible volume — but not
this volume, and not one solid.

**`bulkhead_render()` calls `bulkhead_section_full` and nothing else, so this is the whole
part.** Running [`render_variant.py`](../../src/Fuselage/tools/render_variant.py) at
`1.0 end_bolt 3/16in` — which resolves the variant through `derived_parameters()` rather than
through any hand-typed `.scad` — gives **6922.5048968**, identical to the digit to
`ref_bulkhead_full.scad`. The reference chain is not merely internally consistent; it agrees
with what the sweep actually produces. The FreeCAD port matches it at **+0.00011%**, one valid
solid, bounding box exact.

### The corner, at the parameters it will actually be built at

`corner_render()` calls `fuselage_corner` and nothing else, and `corner_tree.py`'s tip already
*is* `fuselage_corner` — it mirrors the half-length run about mid-span internally. So the
corner needed no assembly module. What it did need was checking at the **swept** parameters,
which it had never had: every corner reference in the directory is at `fuselage_corner.scad`'s
hand-driver values. Seeded from the export it matches at **+0.00041%**, one valid solid,
bounding box exact. `corner_tree.py` now runs either way — with a `params.json` for the swept
set, without one for the driver's.

**The corner and the bulkhead are separate variants, and they disagree on purpose.**
`derived_parameters()` branches on `is_bulkhead`, and `greeble.tolerance` is 0.05 for the
corner and 0 for the bulkhead. That is the joint's defining asymmetry — the corner's bore
carries the whole fit clearance and the bulkhead's post is nominal, because split across both
halves the joint would take it twice. The first version of the export read the corner's
parameters off a *bulkhead* variant and got `greeble_tolerance = 0`, which would have built
the bore with no clearance at all and turned the snap into an interference fit. It now
resolves both and emits two tables, with the shared names — ten of them — checked to agree
and only `greeble_tolerance` exempt. `unit_length` is the other corner-only name, and for the
opposite reason: a bulkhead has no bay length, which is why one bulkhead design serves every
FX (OQ-DES-C3).

### Remaining

Both parts are done and verified against what the sweep produces. Next is IP-FC-10, the
driver swap.

### IP-FC-41 — the parameter set now crosses as data

`derived_parameters()` is the authority and cannot be called from FreeCAD's Python, which
ships without `solid2`. [`tools/export_parameters.py`](../../src/Fuselage/tools/export_parameters.py)
resolves a variant in the project virtualenv exactly as `render_variant.py` does and writes
the flat parameter set as JSON; [`freecad/parameters.py`](../../src/Fuselage/freecad/parameters.py)
reads it back. One authority, no second copy of the design intent.

```sh
python tools/export_parameters.py 1.0 end_bolt 3/16in params.json
freecadcmd parameters.py params.json
```

The flat names are **checked against the OpenSCAD module's own parameter list, read from the
source** — not from `inspect.signature` of the solid2 import, which wraps every imported
module behind a generic signature and would report every name as unknown. A renamed or
dropped OpenSCAD parameter would otherwise surface as a FreeCAD alias silently corresponding
to nothing.

`parameters.py` also compares each ported module's literals against the authority, which
means a module that has not been converted to seeded rows yet is still *verified* against the
real parameter set rather than assumed to agree with it. **All seven checked bulkhead modules
agree exactly** — independent confirmation that the values every port so far was written
against are the ones the sweep would actually use.

`corner_tree` disagrees in six places, which is the disagreement IP-FC-41 exists to resolve.
The report names them rather than hiding them, and there are two more than were previously
listed:

| alias | hand driver | derived |
| --- | --- | --- |
| `extrusion_width` | 0.4 | 0.6 |
| `greeble_thickness` | 0.8 | 1.2 |
| `greeble_nub_thickness` | 0.8 | 1.2 |
| `panel_offset` | 0.0 | 2.5 |
| `panel_overlap` | 4.0 | 4.7625 |
| `panel_thickness` | 4.77 | 4.7625 |

The greeble pair matters more than it looks: `greeble_thickness` sets the wall of the snap
post, so the hand driver builds it at two thirds the thickness the sweep does. Merging those
sheets by name would have silently built the post at two thirds thickness — which is exactly
why the merge assertion refuses rather than picks.

**The sheets are now seeded rather than merged.** `corner_common.build_sheet(doc, params,
seed)` replaces every *literal* row with the authority's value and leaves the `=` rows alone.
The split is the whole point: literal rows are one variant's configuration and belong to
`derived_parameters()`; `=` rows are the relationships the OpenSCAD source defines, which no
parameter set can supply and which still have to agree between modules. A module run on its
own passes no seed and behaves exactly as before, which is what keeps its isolated reference
meaningful.

Three things fell out of doing it:

**Where one module states a relationship and another states this variant's value, the
relationship wins.** `corner_radius` is `=U * 10` in `corner_tree` and `10.0` in the bulkhead
modules. Both are true, but only one survives the user changing `U`, and a sheet whose
`corner_radius` stops tracking `U` is a worse deliverable than one with a redundant row.

**That turns the seed into a check on the derivations, not just the constants.**
`check_seed` confirms every seeded alias on the finished sheet reproduces the authority's
number — so an expression kept in preference to a literal is now measured against
`derived_parameters()`. All of them agree.

**One more genuine name collision, and this one was load-bearing.** `far` meant `unit_width`
in six bulkhead modules and `mask_reach(corner_radius)` in `corner_tree` — two "big enough"
distances under one name. The trap was not `far` itself but `diag_len`, `diag_wid` and
`diag_base`, which are written `=far * 2` on *both* sides: textually identical, so they merge
without complaint while silently taking whichever `far` won. `corner_tree`'s rows are now
`mask_reach` and `mask_diag_*`, named for the function in `shape_modifier_utils.scad` that
defines them.

The reference `.scad` files are checked against the authority too. They are hand-typed, and a
mistyped value there is the worst kind of error to have: the port is compared against the
wrong shape, so it either fails for no reason or — if the same typo reached both sides —
agrees while both are wrong. Nine references, every assignment verified.

---

## Recommendation — the modeling paradigm

**A parametric `Part::` CSG document tree, with parameters in a spreadsheet.** It is the
only one of the three that serves both ends of the pipeline:

| | Static `Part` shapes | `Part::` CSG tree | `PartDesign::` body |
| --- | --- | --- | --- |
| Matches OpenSCAD structure | yes | **one node per operation** | no — sketches, not CSG |
| Editable downstream (UC-2, UC-6) | **no** | yes | yes |
| Parameters visible to an editor | no | **spreadsheet + expressions** | expressions |
| Regenerate risk in the sweep | none | properties only | feature tree, mirrors, cycles |
| Expresses the interrupted groove | yes | yes | needs a `Part::` tool anyway |

`PartDesign::` remains the right answer for a human authoring a *new* part from sketches,
which is UC-6's likely mode — nothing here argues against using it there. What this
measurement argues is that the **generated** parts should be a CSG tree: it is the structure
the source already has, it survives the sweep without a feature tree to corrupt, and it
hands a downstream editor live parameters rather than a dumb solid.

The ported `part_*.py` modules are therefore a *verified reference*, not the final
generator — their arithmetic is confirmed correct against OpenSCAD to 0.004%, and the
remaining work is emitting the same operations as document objects instead of shapes.

This is input to OQ-ARCH-1's final call, not the call itself.

---

## What is unblocked, and why these six

| ID | Why it is worth doing first |
| --- | --- |
| **IP-FC-1** | Decides whether the sweep driver survives intact. Cheapest possible answer to the most structural question in the plan. |
| **IP-FC-2** | Restores the cheap exact verification tier *before* it is lost, and works against today's code, so it is testable immediately. |
| **IP-FC-3** | Pure documentation of decisions already made. Unblocks the top of the analysis ladder for almost no effort. |
| **IP-FC-4** | On the critical path, depends on nothing, and deletes 36 MB of committed mesh. The single highest-leverage item here. |
| **IP-FC-5** | Settles OQ-ARCH-1, the decision the roadmap calls "the one that shapes the whole phase". |
| **IP-FC-6** | A survey, not a build. Bounds the analysis ladder before anyone plans around a rung that may not exist. |
| **IP-FC-7** | The cowl has no design authority and three items depend on one. Writing it is how they get unblocked. |
| **IP-FC-8** | Independent of everything, and the roadmap names the exact test that catches a 1000× error. |

## Open questions this plan is waiting on

**None.** All nine architecture open questions are closed — seven decided 2026-08-07,
OQ-ARCH-3 and OQ-ARCH-8 withdrawn as work items rather than decisions. OQ-DES-B9, raised and
decided 2026-08-08, briefly blocked IP-FC-9: **real fillets, closely resembling the OpenSCAD
version but not required to match it to hundredths of a millimetre.**

**OQ-DES-B10** was raised and fixed on 2026-08-08: the single call to `greeble_bolt_web`
passed its last three arguments rotated, and the matching names are the correct association.
Measured afterwards, the module's material is entirely absorbed at U=0.5 and U=1 — those
bulkheads are bit-identical with the call corrected, or removed altogether — and only at
U=4 does it carry material, where the fix moves about 0.1% of the part. The audit now reports
zero mismatches tree-wide.

Two questions want answers that cannot be read out of the code, and block nothing:

| OQ | Item | What it needs |
| --- | --- | --- |
| [OQ-DES-CW2](../design/cowl.md) | IP-FC-28 | What `cone_angle` measures. Used as complementary angles at its two call sites, so the code cannot disambiguate it |
| [OQ-DES-CW3](../design/cowl.md) | IP-FC-29 | Whether `buttress.thickness = 0.05 mm` is a wall or a cut clearance. Unscaled, and one eighth of an extrusion width |

OQ-DES-B3, B8, CW1, CW4 and CW6 remain open and block nothing.

---

## Verification

The three-tier scheme from Phase 2 does not survive intact, and the change is planned rather
than discovered:

| Tier | Phase 2 | After the port |
| --- | --- | --- |
| Exact and cheap | `scad_snapshot.py` — byte-compare generated `.scad` | **Gone.** No generated text exists. Replaced one layer up by IP-FC-2's parameter snapshot |
| Geometric | `sweep_check.py` against a reference tree | Survives, minus triangle count — a tessellation setting, not a property |
| Caller coverage | `verify_drivers.py` | Becomes "does the generator script run", plus the notebook keyword check |

**The equivalence tolerance has two components, and only one shrinks with finer
tessellation.** The OpenSCAD corpus is *faceted* — its `cylinder()` is an inscribed prism —
so a ported part built on true cylindrical surfaces differs from it systematically, not
noisily. See
[freecad_migration.md §The reference corpus is faceted](../architecture/freecad_migration.md).
The sign is predictable per feature, which makes a difference in the *unexpected* direction
a genuine finding.

Once IP-FC-13 is signed off, this tolerance disappears: within-FreeCAD comparison is B-rep
against B-rep, where volume is exact.
