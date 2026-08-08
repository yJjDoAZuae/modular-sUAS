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
| IP-FC-40 | done | `_sketch()` raises unless `FullyConstrained`, and `check_tree.py` re-asserts it at every size — not only the one the sketch was authored at. An under-constrained sketch deforms silently under a parameter change and still yields a valid solid | IP-FC-38 | §IP-FC-38 |
| IP-FC-39 | done | Write the user guide for the FreeCAD workflows — [doc/guide/freecad_workflows.md](../guide/freecad_workflows.md). Covers the derived-part workflow, linking, the four quiet failure modes, and which workflow serves which use case. Written ahead of the implementation deliberately: the design was chosen to serve these workflows, so they are the acceptance criteria. **Revisit as each capability lands** — the output table names the item that delivers each row | IP-FC-38 | [freecad_workflows.md](../guide/freecad_workflows.md) |
| IP-FC-32 | todo | Measure whether identical parameters yield byte-identical BREP serialization; if so, build a BREP-compare tier beside the parameter snapshot | — | [freecad_migration.md §OQ-ARCH-2](../architecture/freecad_migration.md) |
| IP-FC-33 | todo | Survey and trial every other shape-comparison method that could apply — mesh-to-B-rep deviation, section-curve compare, mass-property compare. Keep what works; deprecate only with a recorded demonstration that a method cannot be made to work | — | [freecad_migration.md §OQ-ARCH-2](../architecture/freecad_migration.md) |
| IP-FC-6 | todo | Survey permissively-licensed tooling for non-uniform printed-material analysis; record the finding either way | — | [freecad_migration.md §OQ-ARCH-8](../architecture/freecad_migration.md) |
| IP-FC-7 | done | Write [`doc/design/cowl.md`](../design/cowl.md) — the cowl had no design authority, and it is the subject of the most blocking work in this plan | — | [cowl.md](../design/cowl.md) |
| IP-FC-8 | todo | Write the SI↔mm conversion layer as one named module; verify by the bounding-box-÷1000 test | — | [general.md §Units](../guidelines/general.md) |
| IP-FC-9 | todo | Port the bulkhead, forming the greeble by cutting with the corner's end **section description re-evaluated at greeble tolerance 0** — never with the corner's built shape, which carries the fit clearance. See §The greeble is cut nominal below. Unblocked by IP-FC-5: cutting with a separately-parameterised solid works in both paradigms | IP-FC-5 | [bulkhead.md §The greeble is a positive post](../design/bulkhead.md) |
| IP-FC-10 | blocked (IP-FC-1, IP-FC-9) | Swap the render call in the sweep driver, keeping the queue, worker budget, atomic writes and previews | IP-FC-1, IP-FC-9 | [freecad_migration.md §What must be preserved](../architecture/freecad_migration.md) |
| IP-FC-11 | blocked (IP-FC-10) | Replace `--resume`'s staleness key: hash the parameter object plus a geometry-code version, since no generated text exists to compare | IP-FC-10 | [freecad_migration.md §What must be preserved](../architecture/freecad_migration.md) |
| IP-FC-12 | blocked (IP-FC-10, IP-FC-4) | Port the boom bulkhead and the cowls. Preserve the OML transform algebra verbatim, including `offset_x` preceding the scale | IP-FC-10, IP-FC-4 | [cowl.md §2](../design/cowl.md), [cowl.md §6.3](../design/cowl.md) |
| IP-FC-13 | blocked (IP-FC-12) | Full-sweep equivalence against the OpenSCAD corpus by volume, bounding box and hole positions — **not** triangle count | IP-FC-12 | [freecad_migration.md §Equivalence between toolchains](../architecture/freecad_migration.md) |
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

### Recommendation

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
OQ-ARCH-3 and OQ-ARCH-8 withdrawn as work items rather than decisions. Nothing in this plan
is blocked on a judgement call; every remaining dependency is on other work in the plan.

Two design questions want an answer that cannot be read out of the code, and each has its
own work item rather than blocking anything:

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
