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
| IP-FC-5 | todo | Prototype the corner **both ways** — `Part::` primitives with booleans *and* `PartDesign::` bodies with sketches. Each must match the OpenSCAD reference by volume and bounding box; report whether `PartDesign::` can form the greeble by reusing the corner's end section, and how each survives a parameter regenerate across several `U`. **No other part is ported until this reports** | — | [corner.md](../design/corner.md), [freecad_migration.md §OQ-ARCH-1](../architecture/freecad_migration.md) |
| IP-FC-32 | todo | Measure whether identical parameters yield byte-identical BREP serialization; if so, build a BREP-compare tier beside the parameter snapshot | — | [freecad_migration.md §OQ-ARCH-2](../architecture/freecad_migration.md) |
| IP-FC-33 | todo | Survey and trial every other shape-comparison method that could apply — mesh-to-B-rep deviation, section-curve compare, mass-property compare. Keep what works; deprecate only with a recorded demonstration that a method cannot be made to work | — | [freecad_migration.md §OQ-ARCH-2](../architecture/freecad_migration.md) |
| IP-FC-6 | todo | Survey permissively-licensed tooling for non-uniform printed-material analysis; record the finding either way | — | [freecad_migration.md §OQ-ARCH-8](../architecture/freecad_migration.md) |
| IP-FC-7 | done | Write [`doc/design/cowl.md`](../design/cowl.md) — the cowl had no design authority, and it is the subject of the most blocking work in this plan | — | [cowl.md](../design/cowl.md) |
| IP-FC-8 | todo | Write the SI↔mm conversion layer as one named module; verify by the bounding-box-÷1000 test | — | [general.md §Units](../guidelines/general.md) |
| IP-FC-9 | blocked (IP-FC-5) | Port the bulkhead, forming the greeble by cutting with the corner's end section | IP-FC-5 | [bulkhead.md §The greeble is a positive post](../design/bulkhead.md) |
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

> **IP-FC-9 blocked reason:** The bulkhead's greeble is formed by cutting with the corner's
> end section, so the corner must exist as a FreeCAD shape first. This is also the step that
> proves the chosen paradigm can express the joint — if `Part::` cannot reuse a shape as a
> cutting tool cleanly, that is the point to find out, before more parts are ported.

> **IP-FC-10 blocked reason:** Whether the driver keeps its thread pool or needs
> multiprocessing depends on IP-FC-1's measurement, and there must be at least one ported
> part to render.

> **IP-FC-12 blocked reason:** The cowls additionally need the OML as a surface (IP-FC-4)
> and a design document (IP-FC-7). Porting them against a tessellated mesh would produce
> parts that can never satisfy UC-2, UC-3, UC-4 or UC-7.

> **IP-FC-16 blocked reason:** OQ-ARCH-5's parameter half is settled — extrusion width
> already exists, renamed in IP-GEO-24. The *method* half is not: how layers are sliced,
> how each is inset, how the sections are joined into a solid, and what supplies material
> where a horizontal surface would leave none.

> **IP-FC-17, IP-FC-19 blocked reason:** A cowl cannot close as a solid without its
> interior surface, and an assembly of open shells is not an assembly.

> **IP-FC-19 blocked reason (OQ-ARCH-6):** Whether parts are placed by construction from
> shared parameters, or by FreeCAD Assembly joints, is unresolved — and the two produce
> different failure modes in a batch context.

> **IP-FC-21 blocked reason:** OQ-ARCH-7 — which dimensions a generated drawing carries is
> a design-intent question, not a geometry one, and it must be answered before a drawing
> generator is written.

> **IP-FC-24 blocked reason:** The layer axis per part is now recorded (IP-FC-3, done), so
> this waits only on the isotropic model it refines.


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

| OQ | Blocks | What it needs |
| --- | --- | --- |
| [OQ-ARCH-5](../architecture/freecad_migration.md#open-questions) | IP-FC-16, IP-FC-17 | The interior-surface *method* — the parameter half is already settled |
| [OQ-ARCH-6](../architecture/freecad_migration.md#open-questions) | IP-FC-19 | Placement by construction vs Assembly joints; measure whether the Assembly workbench scripts under `freecadcmd` |
| [OQ-ARCH-7](../architecture/freecad_migration.md#open-questions) | IP-FC-21, IP-FC-22 | Which dimensions a generated drawing carries |

OQ-ARCH-1, -2, -3, -4 and -8 are open but do not block: each has an item in this plan whose
purpose is to answer it.

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
