# FreeCAD Migration — Architecture

**Scope.** The target architecture for roadmap [Phase 3](../roadmap.md): generating parts
through FreeCAD's Python API instead of by emitting OpenSCAD source. This document covers
what changes, what does not, and what the change costs — particularly in verification,
where the migration starts by losing a capability.

**Status.** Written 2026-08-06, before any port work. The measurements in it were taken on
this machine; the design arguments follow from decisions already made and recorded in
[corner.md](../design/corner.md) and [bulkhead.md](../design/bulkhead.md).

**Relationship to `overview.md`.** The `/arch` skill defines `doc/architecture/overview.md`
as the primary system architecture document, with a module registry, the MAUS unit
standard, and interface conventions. **It does not exist yet.** This document is scoped to
the migration only and deliberately does not duplicate what belongs there. When
`overview.md` is written, the toolchain diagram below belongs in its *Generator toolchain*
section and the open questions here become system-level OQs.

Dimensions are stated in SI unless marked. Where a quantity is millimeters — the FreeCAD
API, the OpenSCAD path, exported meshes — that is called out, because the unit boundary is
the single easiest place in this project to be silently wrong by a factor of 1000.

---

## Use cases

Six anticipated uses of the FreeCAD generation tools. They are listed first because they
set the scope of everything below, and because **three of them are not achievable in
OpenSCAD at any effort** — which is the actual justification for the migration.

### Actors

| Actor | Wants |
| --- | --- |
| Airframe designer | To change a parameter and see the consequence, interactively |
| Build engineer | Printable meshes and cut templates for a specific airframe size |
| Analyst | Mass properties, FEM on load-bearing structure |
| Downstream CAD consumer | Neutral solid geometry that opens in other CAD systems |
| Documentation / visualization | Assembly views, exploded views, animation |

### The use cases

| ID | Use case | Terminal artifact | Kind | Possible today? |
| --- | --- | --- | --- | --- |
| **UC-1** | Headless parameter sweep producing printable meshes | `*.stl` (mm) | mesh | **Yes** — this is the current system |
| **UC-2** | Headless sweep producing native FreeCAD solid models | `*.FCStd` | B-rep | **No** |
| **UC-3** | Headless sweep producing STEP solid models | `*.step` | B-rep | **No** |
| **UC-4** | Solid assemblies with defined joints — fuselage unit, nose, tail, full fuselage | `*.FCStd` assembly | B-rep | **No** |
| **UC-5** | Blender mesh assemblies: full fuselage, units, exploded, exploded with animation paths | `*.blend` | mesh | Partly — `blender/splode.blend` exists |
| **UC-6** | New components: printable panels, panel cutting templates, wing joiners, boom collet and clamp, landing-gear bulkheads and structural blocks | solid + 2D vector | mixed | No — new design work |
| **UC-7** | High-quality dimensioned engineering drawings, of both individual parts and assemblies | `*.pdf` / `*.svg` drawing | drawing | **No** |
| **UC-8** | Structural analysis — mass properties, deformation, stress, yield margin — including the components the model does not yet contain | analysis results | analysis | **No** |
| **UC-9** | Aerodynamic analysis via OpenVSP — parametric nose and tail generation, fuselage force and moment, building toward full-configuration analysis | OML surfaces + aero coefficients | analysis | Partly — OpenVSP is already the OML source, driven by hand |

**UC-2, UC-3, UC-4 and UC-7 are blocked by OpenSCAD's representation, not by its
interface.** OpenSCAD has no boundary representation. Its solid model is a polyhedral
mesh — a `cylinder()` *is* a prism of `$fa`/`$fs` facets, not a cylindrical surface — so
there is no curved geometry to write into a STEP file, nothing for an assembly constraint
to attach to, and **no circle for a drawing to dimension**. **No amount of work on the
OpenSCAD path reaches these four.** That is a stronger argument for the port than
convenience, and it bounds the argument too: UC-1 alone would not justify the migration.

UC-7 is worth spelling out because it is the least obvious of the four. A dimensioned
drawing needs to attach a diameter callout to a *cylindrical face* and a radius to an
*arc*. Projecting OpenSCAD's output gives a 360-sided polygon: every "circle" is a chain
of short line segments, so there is no arc to select, no center to reference, and a
diameter callout has nothing to bind to. The drawing would have to be dimensioned by hand
against coordinates, which is exactly the manual step the generator exists to remove.

**Mesh is not acceptable as an intermediate for UC-2, UC-3 or UC-4.** Tessellating and
re-fitting a surface would produce a nominally-solid model whose faces are approximations
of approximations. The solid must stay a B-rep from construction to export.

### Consequence: the solid is the hub, not the mesh

Today the pipeline is linear and terminates in a mesh. It has to become a hub with
several leaves, and the mesh becomes one leaf among four artifact kinds:

```mermaid
flowchart LR
    params["Parameters<br/>(dataclasses)"] --> build["geometry construction"]
    build --> solid["solid — B-rep<br/><b>the hub</b>"]

    solid --> fcstd["*.FCStd<br/>UC-2"]
    solid --> step["*.step<br/>UC-3"]
    solid --> asm["assembly + joints<br/>UC-4"]
    solid --> tess["tessellate"]
    solid --> draw["TechDraw<br/>UC-7 drawings"]
    solid --> flat["2D vector<br/>UC-6 templates"]
    asm --> draw

    tess --> stl["*.stl (mm)<br/>UC-1"]
    tess --> blend["Blender<br/>UC-5"]

    style solid fill:#d24b38,color:#fff
    style tess fill:#a6c6e6,color:#000
```

Two rules follow, and both are architectural:

- **Tessellation happens once, at the leaf.** Nothing downstream of it feeds back into a
  solid path.
- **The four artifact kinds — B-rep, mesh, 2D vector, drawing — are exports of one solid,
  never conversions of each other.**

### New geometry capability: cowl interior surfaces (UC-4)

The nose and tail cowls are currently modeled as an outer surface only. Present practice
is to let the slicer create the interior by slicing with zero infill. A CAD assembly needs
the interior as real geometry, so the cowl generator gains an interior surface.

**It is a per-layer 2D inset, not a 3D shell offset.** The interior surface is produced
the way a slicer produces it: within each extrusion layer, offset the exterior cross
section inward by a fixed multiple of the extrusion width. That is deliberately *not*
`Part::Offset` or `makeThickness`, which offset perpendicular to the surface.

The two differ on every sloped surface, and the difference is not small. For a surface
tilted by angle α from vertical, a horizontal inset `t` leaves a wall whose perpendicular
thickness is `t·cos α`. So a per-layer inset **thins toward horizontal surfaces** — the
nose tip and the tail cap get progressively thinner walls, reaching zero at a horizontal
face.

That is correct and intended: it reproduces what the printer actually lays down, which is
the whole point of modeling the interior rather than assuming a uniform shell. It will
nonetheless look like a defect to anyone who expects constant wall thickness, so it is
recorded here as designed behavior. Where a real part needs material at a near-horizontal
surface, a slicer supplies it with top and bottom solid layers, and the CAD model needs
the equivalent rule rather than relying on the inset alone.

**The parameter already exists — it was misnamed.** `PrinterSettings` carried a field
called `nozzle_diameter`, but every use of it in the codebase was extrusion-width
semantics: a wall *N* beads thick, or *N* beads of margin. Not one referred to the
nozzle's bore.

| Use | What it means |
| --- | --- |
| `greeble_thickness = max(2·√U·w, 2·w)` | a wall *N* beads thick, floored at two |
| `flange_thickness = max(⌈3U⌉·w, 3·w)` | a whole number of beads |
| `longeron_chamfer = w` | one bead |
| `corner_radius − w − cowl_flange_tolerance` | one bead of setback |
| `panel_clearance_radius + 2·w` | two beads of margin |

Renamed to `extrusion_width` throughout (IP-GEO-24). The rename was worth doing in code
that Phase 3 replaces precisely *because* Phase 3 replaces it: the port will be written by
reading this code, and a field named `nozzle_diameter` gets ported as nozzle diameter —
after which this use case adds a *second* `extrusion_width` field and the model carries two
parameters, differing by 10–20 %, where the design has one.

The method belongs in an algorithm document (`doc/algorithms/`, per the `/arch` skill)
rather than here; this section states the requirement and the trap. Tracked as
[OQ-ARCH-5](#open-questions).

### UC-8: analysis needs a second class of model object

Every part the generator produces today is a **printed** part. Structural analysis needs
the whole load path, and most of it is missing:

| Component | In the model today | Needed for analysis |
| --- | --- | --- |
| Longeron | only its bore | the tube — the primary bending member |
| Panel | only its capture slot | the sheet, as a structural skin |
| Threaded insert | only the bore, and a dimension table | the insert as a stiff body |
| Bolt | only the hole | preload and shear path |
| Glue bond | nothing at all | the bonded interface |

The architectural point is that these are **not new designs**. The model already knows
their dimensions, because it cuts the clearances that receive them: `longeron_radius`,
`panel_thickness`, `bolt_hole_radius`, and the anchor diameter looked up from
[`threaded_insert_dimensions.csv`](../../src/Fuselage/tools/threaded_insert_dimensions.csv).

**So the non-printed components should be derived from the same parameters that create
their clearances, never specified separately.** That is the same argument the greeble
already settles for the joint: a bore and the thing that fills it are two views of one
dimension, and two independent statements of one dimension eventually disagree. A longeron
modeled at 16 mm against a bore cut for a 15.9 mm tube is a bug that no test would catch,
because both parts would be individually correct.

**Glue bonds are different in kind.** They are not solids; they are interfaces between
solids, and in analysis they are contact or tie conditions rather than geometry. They
therefore belong to the *assembly*, not to any part, which makes this part of UC-8 depend
on UC-4.

### UC-8 is a ladder, not a single capability

The four tiers differ by orders of magnitude in cost, and only the last is uncertain:

| Tier | Capability | Needs | Status |
| --- | --- | --- | --- |
| 1 | **Mass properties** — mass, center of gravity, inertia tensor | densities per component; the non-printed solids | Available immediately once the solids exist; FreeCAD computes these exactly from the B-rep, no solver involved |
| 2 | **Isotropic FEM** — deformation, stress, yield margin | tier 1, plus an assembly with loads, restraints and bonded interfaces | Reachable with the existing stack |
| 3 | **Orthotropic FEM** — printed parts as layered material, weak through the layer axis | tier 2, plus print orientation **stated** per part | Solver-side capability exists; the orientation is already designed in, it is simply not written down |
| 4 | **Mesostructure / toolpath-level** — bead geometry, infill pattern, layer adhesion as modeled features | tier 3, plus tooling that may not exist permissively | **Unverified** — see below |

Separating tier 1 matters. Mass properties are exact from a B-rep, need no solver, and
answer a question the project asks constantly — what does this airframe weigh, and where
is its CG. That is available as soon as the non-printed components are modeled, which is
work UC-8 needs anyway.

**Tier 3 is closer than it looks.** Treating a printed part as orthotropic — stiff along
the beads, weak across the layer interface — requires knowing which way the layers run.

**Every printable component in this system already has a print orientation by design.**
The parts are not shapes that might be printed any way up; each one was drawn for a
specific orientation, and the features that show it are already in the geometry — chamfers
sized to be self-supporting, the 45° ramp on the interconnect's depth change, the greeble's
lead-in. So the layer normal is a *known* property of every part.

What is missing is that it is nowhere **stated**. Nothing in the model or the design
documents says, for each part, which axis the layers stack along and whether the modeled
frame is the print frame or a rotation of it. That distinction matters — the `/arch`
convention already notes that assembly orientation and print orientation are not the same
thing — and an orthotropic material assignment needs the answer per part.

So tier 3's prerequisite is a **recording** task, not a design decision: write down what
was already decided, one line per part, in each part's design document. That is much
cheaper than adding a parameter someone has to choose.

**On licensing**, the project's policy already answers most of the question:

> GPL (any) — Avoid for libraries. Note that OpenSCAD and FreeCAD are themselves GPL/LGPL
> applications invoked as **separate processes**, which does not propagate to this
> project's code.

FreeCAD's FEM workbench drives **CalculiX**, a GPL solver, as a separate process — exactly
the pattern the policy already sanctions. Orthotropic elasticity is standard CalculiX
capability, so tier 3 does not require a new solver; what is unverified is whether
FreeCAD's material editor exposes it or whether the input deck must be written directly.

**Tier 4 is where I cannot give an answer.** Whether a mature, permissively-licensed tool
exists for bead-level or layer-adhesion modeling of FDM parts is a survey question, and it
should be answered by looking rather than by assuming in either direction. The commercially
established tools in this space are proprietary. Recorded as [OQ-ARCH-8](#open-questions)
rather than guessed at.

### UC-9: OpenVSP is already in the pipeline, one-way and by hand

This use case does not introduce OpenVSP — it closes a loop that already exists and is
currently manual. Today:

```mermaid
flowchart LR
    vsp3["cad/modular_sUAS_nose_tail.vsp3"] -. "opened by hand" .-> gui["OpenVSP GUI"]
    gui -. "exported by hand" .-> mesh["oml/vsp_nose.stl (12 MB)<br/>oml/vsp_tail.stl (24 MB)"]
    mesh --> cowl["cowl_geometry.scad<br/>import()"]
    cowl --> parts["cowl parts"]

    style gui stroke-dasharray: 4 4
```

The source model **is** version-controlled — `src/Fuselage/cad/modular_sUAS_nose_tail.vsp3`
— so the provenance exists. What does not exist is any automation between it and the
meshes, and no check that the committed meshes were exported from the committed model.

**The OML import is a third unit boundary, and the only metre-to-millimetre conversion in
the OpenSCAD path.** `body_blank_full()` applies `scale([U/oml_scale_m_per_mm, …])` with
`oml_scale_m_per_mm = 1e-3`, so the factor is `1000·U`: the exported mesh is in **meters** and the
model is in millimeters. The companion values in the cowl JSON are metres too —
`oml_length_m = 0.050` for the nose, `0.1` for the tail. Worth stating plainly, because it
is the one place the existing millimeter-throughout rule already meets SI data, and the
port has to keep the conversion rather than discover it.

### UC-9 has a hard dependency on UC-2 and UC-3

This is the interaction most likely to be missed, and it runs the opposite way to
intuition.

**A cowl built from an imported mesh cannot be a clean B-rep.** The cowls are currently
built by importing a tessellated STL and cutting it. Whatever comes out is a polyhedron —
so for the cowls specifically, UC-2 and UC-3 do not deliver true solid models even after
the port, and UC-7 cannot dimension a cowl's curvature, for the same reason it cannot
dimension OpenSCAD's faceted cylinders.

**OpenVSP can export STEP and IGES**, i.e. real surfaces rather than a tessellation. So
the fix is available and it belongs to UC-9: the OML should arrive as a *surface*, not a
mesh. That single change is what makes the cowls first-class in UC-2, UC-3, UC-4 and UC-7,
and it also removes 36 MB of committed mesh from the repository.

The corollary is a sequencing constraint: **the OML-as-surface part of UC-9 should land
before or with UC-2**, not after it. Otherwise the B-rep export ships with the cowls
quietly excluded, which is exactly the kind of partial capability that gets forgotten.

### What UC-9 needs

| Piece | Notes |
| --- | --- |
| Driven OpenVSP | The Python API drives the `.vsp3` model headlessly, so nose and tail shapes become generated artifacts with parameters rather than hand-exported files |
| OML as surface | STEP or IGES export instead of STL — see above |
| Configuration export | The fuselage geometry, and later the whole aircraft, presented to the aero solver |
| Force and moment | VSPAERO. Note that its vortex-lattice method models lifting surfaces; body force and moment want the panel solver, and fuselage-alone results should be treated as a step toward configuration analysis rather than an answer in themselves |

**Licensing: checked, and it is fine.** OpenVSP 3.50.5 is under the **NASA Open Source
Agreement v1.3**, whose obligations attach to *distribution* rather than to linkage — so
using it, in either pattern, imposes nothing on this project's code, and importing its
Python API is no different from spawning the binary. Details and the clause references are
in [OQ-ARCH-9](#open-questions), including the one clause that does deserve attention
(§4.B, an indemnity term about products built with the software, not about code).

### What each use case adds

| Use case | Beyond the port itself |
| --- | --- |
| UC-1 | Nothing — this *is* the port |
| UC-2 | An export step; the solid already exists |
| UC-3 | An export step |
| UC-4 | Cowl interior surfaces; joint/mate definitions; an assembly structure |
| UC-5 | A mesh export path to Blender; explode transforms and animation paths |
| UC-6 | Several new generators, and a 2D vector output kind that nothing currently produces. **Its landing-gear bulkheads and structural blocks are members of an existing family** — the interstitial plate bulkheads, of which the tail-boom bulkhead is the first. See [bulkhead.md](../design/bulkhead.md) |
| UC-7 | TechDraw pages, a dimensioning scheme, and a drawing template — and it consumes UC-4's assemblies, not just parts |
| UC-8 | **A second class of model object**: the non-printed components — longerons, panels, inserts, bolts — plus material data, bonded-interface definitions, and each part's print orientation written down |
| UC-9 | A driven OpenVSP path — parametric nose and tail generation, and configuration export for aero solving. The OML becomes a generated input rather than a committed mesh |

**UC-1 is the port. UC-2 through UC-6 are capabilities the port enables.** Keeping that
line sharp is what protects the migration from becoming an open-ended redesign: the
migration is done when UC-1 produces geometry verifiably equivalent to what it replaces,
and everything else is new work scheduled after it.

---

## The port is one layer, not the toolchain

This section is about **UC-1**, the port proper. The most important architectural fact
about it is how little of the system it touches. The generator is already layered, and
only two layers are OpenSCAD-specific:

| Layer | Today | After the port |
| --- | --- | --- |
| Parameter axes — `variant_param/*.csv`, `*.json` | pandas rows | **unchanged** |
| Derivation — `derived_parameters()` → `Parameters` dataclass | Python | **unchanged** |
| Validity — `corner_validity_check()`, `bulkhead_validity_check()` | Python | **unchanged** |
| Geometry construction | `solid2` → generated `.scad` text | **replaced** — FreeCAD Python API → in-memory `Shape` |
| Solid evaluation + export | `openscad.exe`, CGAL → `.stl` | **replaced** — OCC kernel → B-rep, tessellated to `.stl` at the leaf |
| Sweep driver — queue, workers, resume, atomic writes, previews, naming | Python | **unchanged in structure**, one call swapped |
| Verification | three tiers | **one tier is lost**, see below |

That the parameter layer survives untouched is not luck. It is the result of
[OQ-GEO-1](../implementation/geometry_refactor.md#open-questions), which rejected grouping
parameters inside OpenSCAD precisely because that work would be discarded here, and built
the typed dataclasses in Python instead. The same reasoning applies to anything still
tempting in the OpenSCAD path: it has one phase left to live.

```mermaid
flowchart LR
    csv["variant_param/*.csv"] --> flatten["flatten_param_space()"]
    json["cowl JSON"] --> derive
    flatten --> derive["derived_parameters()"]
    derive --> params["Parameters / NoseParameters<br/>(dataclasses)"]
    params --> valid{"validity_check()"}
    valid -- reject --> skip["skipped"]
    valid -- accept --> build["geometry construction"]
    build --> solid["solid (B-rep)"]
    solid --> stl["*.stl (mm)"]
    solid --> png["*.png preview"]

    style build fill:#d24b38,color:#fff
    style solid fill:#d24b38,color:#fff
```

Only the two red nodes are rewritten. Everything to their left is already in its final
form; everything to their right keeps its current contract.

---

## Verified: the headless path works

The roadmap requires the sweep to run headless, because the FreeCAD MCP drives a live GUI
session and a batch of thousands of parts must not. Confirmed on this machine, 2026-08-06:

```text
C:\Users\Alex\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe
    FreeCAD 1.1.1
    GuiUp = 0
```

A box with a cylindrical cut, built and measured entirely headless:

| Measurement | Result |
| --- | --- |
| `Shape.Volume` | 2230.353997 mm³ |
| Analytic volume, `20·20·6 − π·3²·6` | 2230.353997 mm³ |
| `Shape.BoundBox` | 20.000 × 20.000 × 6.000 mm |
| `Shape.isValid()` | `True` |
| `tessellate(0.1)` | 520 triangles |
| `tessellate(0.01)` | 932 triangles |
| Exported STL, mesh volume | 2230.375282 mm³ |

Three architectural consequences follow from that table, and they matter more than the
fact that it ran.

**`Volume` is exact, not sampled.** It agrees with the closed-form answer to all printed
digits, because it is integrated over the B-rep rather than summed over triangles. The
OpenSCAD path has no equivalent — there, volume is only ever a property of a mesh.

**Triangle count is a setting, not a property.** The same solid gives 520 or 932 triangles
depending on a deviation argument. In the OpenSCAD path triangle count is likewise set by
`$fa`/`$fs`/`$fn`, but it has been usable as a change-detector because those values are
held constant. **Across the two toolchains it is meaningless** — see the verification
section.

**Tessellation error is small but real.** The exported mesh measures 0.021 mm³ larger than
the exact solid, +0.001 % at deviation 0.01. The sign is right: the cut cylinder is
approximated by an inscribed prism, which removes slightly less material than the true
cylinder. Any equivalence test between the two toolchains inherits an error of this
character, so it needs a *relative* tolerance justified by tessellation — not an
arbitrary epsilon.

---

## The unit boundary

The project standard is SI (m, s, kg, rad). **FreeCAD's Python API is millimeters**, its
FEM stack is N/mm², and exported STL and 3MF must be millimeters because those formats
carry no unit metadata and a slicer will read them as mm regardless.

So the port has a real unit boundary, and it needs exactly one named conversion layer
rather than factors scattered through the geometry code:

```mermaid
flowchart LR
    subgraph si["SI — meters"]
        p["Parameters<br/>(ported to SI)"]
    end
    subgraph conv["conversion layer"]
        c["one named module"]
    end
    subgraph mm["millimeters"]
        fc["FreeCAD API"]
        ex["STL / 3MF export"]
    end
    p --> c --> fc --> ex
```

The roadmap already names the test that catches a mistake here: a ported part's bounding
box in meters must equal the OpenSCAD part's bounding box in millimeters divided by 1000.
It is worth restating why this deserves a dedicated check — a 1000× error still renders,
still exports, and still passes `isValid()`. It fails only at the printer.

**The existing OpenSCAD path stays in millimeters and is never converted.** It has one
phase left; converting it spends real risk for no benefit.

---

## What must be preserved

The sweep driver is not incidental scaffolding. Most of its behavior was built in response
to a specific failure, and each of those failures will recur if the port reimplements the
driver rather than reusing it:

| Capability | Why it exists |
| --- | --- |
| Bounded parallel workers | A worker count set from cores alone exhausted memory and crashed a sweep mid-run |
| Atomic writes — render to `*.partial.stl`, `os.replace` on success | An interrupted run left a convincing truncated part that a resume then skipped |
| `--resume` with staleness detection | Skipping on "the file exists" silently keeps stale parts after the geometry changes |
| Preview from the finished mesh | Previews used to cost a second full solid evaluation — the dominant cost of the sweep |
| Validity checks before construction | Roughly half of the Cartesian product is geometrically invalid and must never reach the kernel |
| Deterministic naming and directory scheme | The output tree is the reference corpus that equivalence testing compares against |

**Keep "render is a subprocess".** Today the driver shells out to `openscad.exe`, which is
why a thread pool works — the subprocess releases the GIL. Driving FreeCAD in-process
would hold it, and the whole `RenderQueue` design would need replacing with multiprocessing.
Spawning `freecadcmd.exe` per part instead preserves the queue, the memory budget, the
atomic writes, and the retry path exactly as they are, and swaps one command string.

The cost of that choice is process startup per part, which is higher for FreeCAD than for
OpenSCAD. **That was a measurement, not a design question** — and it has now been taken.

> **MEASURED 2026-08-07 (IP-FC-1): startup is 0.24 s. Subprocess-per-part it is.**
>
> `freecadcmd` on this machine — wall time minus in-script time, stable across runs:
>
> | Workload | In-script | Wall | Startup |
> | --- | --- | --- | --- |
> | Import only | 0.032 s | 0.27 s | **0.24 s** |
> | Box minus cylinder | 0.044 s | 0.40 s | ~0.24 s |
> | Boolean-heavy — 16 cuts, a fuse, 4-way mirror, `removeSplitter` | 0.60 s | 0.84 s | ~0.24 s |
>
> The decisive figure is not the per-part ratio but the **total**: 576 parts × 0.24 s is
> **about 2.3 minutes of startup across an entire sweep**, against a sweep that currently
> runs for hours. Negligible regardless of what a real ported part costs to build — which
> makes the conclusion robust to the one quantity still unknown.
>
> A caveat kept deliberately: the boolean-heavy case is a *synthetic* analogue at 7,776
> triangles, while real bulkheads run 25,000–37,000. A true part will build more slowly,
> which only strengthens the conclusion by raising the denominator.

The decision tree that measurement resolves, kept for the record:

| Measurement | Choose | Consequence |
| --- | --- | --- |
| Startup small next to a part's build time | **One `freecadcmd` per part** | Queue, worker budget, atomic writes, retry and resume all survive unchanged; crash isolation per part; threads keep working |
| Startup dominates | **One long-lived worker per thread** | Startup paid once per worker, but crash isolation is lost — a bad part takes its worker's whole batch — and document state leaks between parts unless each is closed explicitly |
| Neither acceptable | **In-process, multiprocessing** | Rewrites the queue; parameter objects must be picklable; the memory-budget logic changes shape |

These parts take seconds to minutes of kernel work each, so the first row is the likely
outcome. It costs one measurement to know, and rows two and three are progressively larger
rewrites that should not be entered speculatively.

**`--resume` needs a new staleness key.** It currently compares the freshly generated
`.scad` text against what is on disk, byte for byte. There is no generated text after the
port. The replacement has to key on the inputs instead: the parameter object plus a version
of the geometry code that produced it.

---

## Verification across the port

This is where the migration is most exposed, and the exposure is not obvious.

### The cheap exact tier does not survive

Verification today is three tiers, each covering what the others cannot:

| Tier | Mechanism | Survives the port? |
| --- | --- | --- |
| [`scad_snapshot.py`](../../src/Fuselage/tools/scad_snapshot.py) | Byte-compare the generated `.scad` for all 576 variants | **No** |
| [`sweep_check.py`](../../src/Fuselage/tools/sweep_check.py) / [`verify_sweep_change.py`](../../src/Fuselage/tools/verify_sweep_change.py) | Measured geometry against a reference tree | Yes, with changes |
| [`verify_drivers.py`](../../src/Fuselage/tools/verify_drivers.py) | Render every GUI driver, treat warnings as failures | Different shape |

The first tier is exact, runs in seconds, and proved most of the Phase 2 work outright —
including the parameter dataclass conversion, where all 576 parts came out byte-identical.
It works *because* the generated `.scad` is a complete written statement of the geometry.
**The port removes that artifact**: FreeCAD builds objects in memory and there is nothing
textual to diff.

Losing it means every Python-side change costs a full render to verify instead of a few
seconds of text comparison. Plan for the replacement rather than discovering the gap
mid-port.

### The replacement: snapshot the parameters, not the source

The cheap tier can be recovered one layer up. The `Parameters` and `NoseParameters`
dataclasses are the complete input to geometry construction and are shared by both
toolchains. Snapshot those for every variant and diff them, exactly as `scad_snapshot.py`
diffs generated text today.

That covers every layer above geometry construction — axes, derivation, validity, naming —
which is where most changes actually land. It does not cover the geometry code itself,
which is what the geometric tier is for. The division of labor is the same as today; only
the boundary moves.

### Equivalence between toolchains

The 576-part output tree is the golden reference. Comparing a ported part against it needs
care about which properties are portable:

| Property | Portable across toolchains? |
| --- | --- |
| Enclosed volume | **Yes** — with a tessellation tolerance |
| Bounding box | **Yes** |
| Hole positions and count | **Yes** |
| Triangle count | **No** — a tessellation setting, measured above at 520 vs 932 for one solid |

`sweep_check.py` compares all four today, and triangle count is currently its *strictest*
signal. That signal has to be dropped for cross-toolchain comparison and kept for
within-toolchain regression. Conflating the two would either mask real differences or
report false ones on every part.

### The reference corpus is faceted, and that is a real geometric difference

This is the subtlety most likely to be mistaken for a bug, and the use cases above are
what make it unavoidable.

OpenSCAD has no curved surfaces. Its `cylinder()` is an inscribed prism of `$fa`/`$fs`
facets, so the reference corpus is not an approximation *of* the intended solid — **it is
a different solid**, one whose round features are systematically smaller than round. The
ported part, built on true cylindrical surfaces, will not match it exactly no matter how
finely either side is tessellated.

The difference is not noise. It is **systematic, one-sided, and computable**: an inscribed
regular *n*-gon has area `(n / 2π)·sin(2π / n)` times the circle it approximates, so every
convex round feature in the reference is slightly undersized and every round hole slightly
oversized. At `$fa = 1` — 360 facets — that is about 0.005 % of area per feature, with the
sign depending on whether the feature adds or removes material.

Three consequences:

- **The equivalence tolerance has two components,** not one: tessellation error on the
  measurement (measured above at 0.001 %) *plus* the faceting bias of the reference. Only
  the first shrinks if you tessellate more finely.
- **The sign is predictable per feature,** so a difference in the unexpected direction is
  a genuine finding rather than a tolerance problem. That is worth more than a tighter
  bound.
- **This applies only to comparisons against the OpenSCAD corpus.** UC-2, UC-3 and UC-4
  compare B-rep against B-rep, where volume is exact on both sides and the tolerance
  collapses to floating point.

So the equivalence test is a one-time migration instrument, not a permanent fixture. Once
UC-1 is signed off, within-FreeCAD regression testing is strictly more precise than
anything available today.

---

## What the design documents constrain

Two findings from Phase 2 bear directly on how the port should be structured, and both
would be easy to lose.

**The joint is one description, not two.** The bulkhead's greeble is formed by subtracting
`corner_end()` — the corner's own end section — from the bulkhead. What survives is the
positive post that fills the corner's bore, with a rib filling the corner's groove. The two
mating halves are complements of a single shape and therefore *cannot* disagree. See
[bulkhead.md](../design/bulkhead.md).

Preserving that property is an architectural requirement, not a stylistic preference. If
the port models the corner's bore and the bulkhead's post as two independent features, a
constraint is needed to hold them together — and constraints can be violated, while
complements cannot.

**Corner and bulkhead share the cross-section, not the length.** They are not independent
designs; they are two halves of one joint. But bay length is *not* part of that coupling:
`FX` scales `unit_length`, which reaches the corner alone, which is why one bulkhead design
serves bays of every length and why the bulkhead sweep carries no `FX` axis. See
[OQ-DES-C3](../design/corner.md#open-questions).

The port should therefore share cross-section and joint parameters between the two parts by
construction, and keep bay length a parameter of the corner only.

---

## Migration sequence

Ordered so that each step's failure is cheap and legible:

1. **Measure `freecadcmd` startup and one part's build time.** Decides whether
   subprocess-per-part is viable, which decides whether the sweep driver survives intact.
   Everything else is easier to change than this.
2. **Port one part end to end** — the corner, which is the simpler of the two joint halves
   and has a design document. Compare against its OpenSCAD reference by volume and
   bounding box.
3. **Port the bulkhead, forming the greeble by cutting with the corner's end section.**
   This is the step that proves the paradigm can express the joint; if it cannot, that is
   the point to find out.
4. **Build the parameter snapshot tool** before porting anything further, so the remaining
   work has a cheap regression check.
5. **Swap the render call in the sweep driver**, keeping the queue, resume, atomic writes,
   and previews.
6. **Run the full sweep and compare against the reference tree** by portable properties.
   **UC-1 is complete here**, and the migration proper is done.
7. **Then, and only then, the capabilities the port existed to enable.** UC-2 and UC-3
   first — `.FCStd` and `.step` exports, both of them export steps on a solid that already
   exists, and the two use cases OpenSCAD could never reach.
8. **UC-4** — cowl interior surfaces first (the new geometry), then assemblies and joints.
9. **UC-5** — the Blender export path, explode transforms, animation.
10. **UC-6** — new components, in whatever order the airframe needs them. The 2D vector
    output kind for cutting templates has no precedent in the toolchain and should be
    prototyped on one panel before the others are designed around it.
11. **UC-7** — drawings. Part drawings can follow UC-2 directly; assembly drawings depend
    on UC-4, so the two halves of this use case land at different times and should be
    planned as such.
12. **UC-8** — analysis, in tiers. The non-printed components and mass properties (tier 1)
    are worth doing early and independently: they need no solver, they answer the weight
    and CG question the project asks constantly, and modeling the longerons and panels is
    prerequisite work for every later tier anyway. Stress analysis follows UC-4, because
    bonded interfaces are a property of the assembly.
13. **UC-9** — but **its first half belongs at step 7, not here.** Getting the OML as a
    STEP surface instead of a 36 MB mesh is what makes the cowls first-class in UC-2, UC-3,
    UC-4 and UC-7; deferred to the end, those four ship with the cowls quietly excluded.
    The aero half — driven generation, VSPAERO force and moment — has no such constraint
    and can follow at leisure.

Two orderings are deliberate. **Step 3 before step 4:** the greeble is the highest-risk
geometry in the project, and finding out it does not map cleanly is worth more than having
a faster test suite while porting parts that were never in doubt. **Steps 7–8 after step
6:** UC-2 and UC-3 cost almost nothing once UC-1 lands, so they should not be entangled
with it — but UC-4 pulls in new geometry and a new failure mode, and starting it before
the port is verified would make it impossible to tell which layer a discrepancy came from.

---

## Open questions

| ID | Status | Question |
| --- | --- | --- |
| ARCH-1 | ~~decided~~ 2026-08-07 | `Part::` or `PartDesign::`? — build both, then choose (IP-FC-5) |
| ARCH-2 | ~~decided~~ 2026-08-07 | What replaces the exact verification tier? — do both, plus every method that works |
| ARCH-3 | ~~withdrawn~~ 2026-08-07 | Not an open question — a measurement. See IP-FC-1 |
| ARCH-4 | ~~decided~~ 2026-08-07 | Retire it after IP-FC-13; FreeCAD becomes the definition of correctness |
| ARCH-5 | ~~decided~~ 2026-08-07 | Adaptive curvature-aware slice-and-fit; G1 threshold, G2 objective; never ruled |
| ARCH-6 | ~~decided~~ 2026-08-07 | FreeCAD Assembly joints, verified against the constructed placement |
| ARCH-7 | ~~decided~~ 2026-08-07 | Dimensions are expressions over parameters; interfaces are a floor; family drawing with a variant table |
| ARCH-8 | ~~withdrawn~~ 2026-08-07 | Not an open question — a survey. See IP-FC-6 |
| ARCH-9 | ~~resolved~~ 2026-08-07 | Is OpenVSP's license compatible with the project's policy, and in which usage pattern? |
| ARCH-10 | ~~withdrawn~~ 2026-08-09 | Not an open question — a measurement. OCCT needs no overlap at all; the premise was wrong. See IP-FC-49 |
| ARCH-11 | ~~decided~~ 2026-08-15 | Constraints. `PartDesign::` is the target state; staged, starting with constrained sketches for derived features |
| ARCH-12 | ~~decided~~ 2026-08-16 | `BBOX_TOL` scales with `U`. The reference is not re-rendered to binary; the limit expires with the OpenSCAD sweep |
| ARCH-13 | ~~decided~~ 2026-08-16 | Leave the construction for now and record that it is an OpenSCAD workaround; make it a real chamfer feature with the `PartDesign` move (IP-FC-78) |
| ARCH-14 | ~~decided~~ 2026-08-17 | Convert all four rounded corners, into one cohesive sketch carrying only the fillets active for the variant. Implemented the same day (IP-FC-73); the change to the flown part the decision accepted turned out to be **zero** in all 27 affected variants, since the omitted body lay inside the bolt hole |
| ARCH-15 | ~~decided~~ 2026-08-18 | The baseline does not move. Re-baselining lets every step pass while the total wanders, so `variant_output_baseline` stays the authority for the whole port and differences are enumerated in a ledger and justified, not absorbed. Retired only after the `PartDesign::` end state, on a reviewed sign-off (IP-FC-80, IP-FC-81) |
| ARCH-16 | ~~decided~~ 2026-08-18 | Both: fix the tolerances to the project's own rule — relative volume, `U`-scaled bbox, triangle count advisory — **and** add a surface distance computed on a sampled subset rather than every vertex. Cheap criteria screen, distance adjudicates (IP-FC-82, IP-FC-83) |

### ~~OQ-ARCH-1 — `Part::` or `PartDesign::`?~~ — DECIDED 2026-08-07: build both

The roadmap calls this the decision that shapes the whole phase. The geometry today is
CSG: unions and differences of primitives and extrusions, with masks trimming an octant and
mirrors tiling it.

**Alternatives**

1. **`Part::` primitives with booleans.**
   *Benefits:* maps directly onto the existing code, so the port is a translation rather
   than a redesign; a `Shape` is a value that can be reused as a cutting tool, which is
   exactly how the greeble is formed today; the octant-and-mirror construction carries over
   unchanged.
   *Drawbacks:* less idiomatic FreeCAD; fillets and drafts are applied to edges selected
   programmatically, which is fragile if edge ordering shifts.
   *Prerequisites:* none.

2. **`PartDesign::` bodies with sketches.**
   *Benefits:* idiomatic; proper parametric fillets and drafts; better suited to TechDraw
   and to later assembly work.
   *Drawbacks:* a body is a single contiguous solid, and reusing one body as a cutter for
   another is awkward — which is a direct problem for the greeble, whose whole safety
   property is that both halves are complements of one shape; sketches must be constructed
   programmatically, which is more code than the geometry warrants.
   *Prerequisites:* a way to express the joint that preserves the single-description
   property.

3. **`Part::` for the joint, `PartDesign::` for the rest.**
   *Benefits:* keeps the risky part in the paradigm that suits it.
   *Drawbacks:* two paradigms in one codebase, and the boundary between them is another
   thing to get wrong.
   *Prerequisites:* both of the above understood first.

**Recommendation was alternative 1.** The single-description property of the greeble is the
strongest constraint in the geometry and `Part::` preserves it for free. The fillet
fragility is real but confined to the flange and web features, which are the least
load-bearing geometry in the project.

---

**DECIDED 2026-08-07: build the parts *both* ways, then choose.** Neither alternative is
selected on paper. IP-FC-5 produces a `Part::` corner **and** a `PartDesign::` corner, and
the paradigm decision follows from comparing them.

This is a deliberate deferral, and it is bought rather than free — it costs a second
prototype. It is worth that because the roadmap calls this "the decision that shapes the
whole phase", and the arguments on each side are of a kind that prototypes settle and
reasoning does not:

- Whether `PartDesign::` can express the greeble's single-description property at all, or
  needs a constraint where `Part::` has an identity, is a question about how the workbench
  behaves — not about the geometry.
- Whether programmatic edge selection for fillets is as fragile as feared is a question
  about topological naming stability across a parameter sweep, which only a sweep answers.
- Whether sketch-based construction is genuinely a "bigger rewrite" is a question about how
  much of the octant-and-mirror structure survives, which is visible once one part exists
  in both forms.

**What the comparison must produce**, so it decides something rather than becoming two
prototypes nobody chooses between:

1. Identical measured geometry from both — volume and bounding box against the OpenSCAD
   reference, to prove both are correct before either is preferred.
2. A statement of whether the greeble can be formed in `PartDesign::` by reusing the
   corner's end section, and what it costs if not.
3. Line counts and, more importantly, how each behaves when a parameter changes — a
   regenerate across several `U` values, checking whether fillet references survive.

Until IP-FC-5 reports, no other part is ported. That is the point of the deferral.

### ~~OQ-ARCH-2 — What replaces the exact verification tier?~~ — DECIDED 2026-08-07: do both, and more

`scad_snapshot.py` is exact, runs in seconds, and disappears with the generated `.scad`.

**Alternatives**

1. **Snapshot the parameter dataclasses instead.**
   *Benefits:* same cost and exactness; covers axes, derivation, validity, and naming —
   where most changes land; toolchain-independent, so it works before, during, and after
   the port.
   *Drawbacks:* covers nothing below geometry construction, so geometry changes still cost
   a render.
   *Prerequisites:* none; the dataclasses already exist.

2. **Serialize each `Shape` to BREP and byte-compare.**
   *Benefits:* covers the geometry layer exactly.
   *Drawbacks:* BREP is not obviously stable across kernel versions or construction order,
   so a false difference is likely; unproven.
   *Prerequisites:* measure whether identical input yields identical BREP bytes.

3. **Accept the loss and rely on measured geometry alone.**
   *Benefits:* no work.
   *Drawbacks:* every Python-side change costs a full sweep; that is the situation Phase 1
   built tooling to escape.
   *Prerequisites:* none.

**Recommendation was alternative 1 now, alternative 2 opportunistically.** They compose —
parameters above, BREP below — and 1 is cheap enough to build before it is needed.

---

**DECIDED 2026-08-07: do both, and pursue every shape-comparison method available.**
Alternative 3 — accepting the loss — is rejected outright. The governing statement:

> **At this point we cannot afford to operate without verification coverage.**

That is a stronger position than any single alternative above, and it reframes the
question. The default is **not** "pick the cheapest adequate check". It is **try every
method, keep everything that works, and deprecate a method only after demonstrating it
cannot be made to work** — a failed attempt is evidence; an untried idea is not.

**What this commits to building:**

| Method | Layer it covers | Item |
| --- | --- | --- |
| Parameter snapshot | everything above geometry construction — axes, derivation, validity, naming | IP-FC-2 |
| BREP serialization compare | the geometry layer, exactly, within FreeCAD | IP-FC-32 |
| Measured geometry | cross-toolchain and within-toolchain | survives as `sweep_check.py` |
| Generator-script render | that every part still builds at all | successor to `verify_drivers.py` |

These are complements, not competitors. A parameter snapshot cannot see a geometry change; a
BREP compare cannot see a naming change; measured geometry sees both but costs a render.
**Layered coverage is the goal and redundancy between layers is a feature** — Phase 2 found
defects that only one of its three tiers could have caught, more than once, and the two dead
parameters (OQ-DES-B6, OQ-DES-C3) were invisible to *all* of them.

**Grounds for deprecating a method:** demonstrate that it produces false results or cannot
be made to work, and record the finding. "It seemed redundant" is not sufficient, because
redundancy is the property being bought.

**Why this matters more after the port than before.** Phase 2's cheapest tier was exact,
ran in seconds, and carried most of the verification load. The port deletes it. Replacing
one strong check with one weaker check would quietly reduce coverage at exactly the moment
the codebase is least trustworthy — a newly ported geometry engine with no track record.
Several partial checks is the right response, even though it is more work than the
arrangement it replaces.

### ~~OQ-ARCH-3 — Is subprocess-per-part viable?~~ — WITHDRAWN 2026-08-07: not an open question

**This was miscategorized.** An open question is a decision requiring judgment between
alternatives whose merits cannot be settled by looking. This is a **measurement** — take the
`freecadcmd` startup time and a single part's build time, and the answer follows
mechanically from the ratio. There is no design judgment in it.

The substance has moved to where it belongs:

- **The measurement** is [IP-FC-1](../implementation/freecad_migration.md), already an
  unblocked work item and the first thing in the plan.
- **The decision tree** — which architecture each outcome implies, and what each costs — is
  in [§What must be preserved](#what-must-be-preserved), beside the discussion of why the
  driver keeps its subprocess model.

Nothing is lost by withdrawing it; the ID is retained rather than renumbered so that
references elsewhere stay valid.

**Worth noting as a pattern**, since this document raised nine questions and one of them
was not a question: *"we do not know X"* is not sufficient grounds for an OQ. The test is
whether knowing X requires a **decision** or merely an **observation**. If an afternoon of
measurement settles it, it is a work item.

### ~~OQ-ARCH-4 — What becomes of the OpenSCAD implementation?~~ — DECIDED 2026-08-07: retire it

The roadmap says do not delete it before the FreeCAD path is proven across the full
parameter range, which settles the near term but not the end state.

**Alternatives**

1. **Retire it once equivalence is demonstrated.**
   *Benefits:* one implementation to maintain; no divergence.
   *Drawbacks:* loses the only independent check on the new geometry.
   *Prerequisites:* full-range equivalence.

2. **Keep it as a cross-check, run on demand.**
   *Benefits:* two independent implementations of the same geometry is a strong check —
   the current design documents were written partly by reading it.
   *Drawbacks:* every geometry change must be made twice or the check rots into a source of
   false alarms.
   *Prerequisites:* a decision about who keeps them in step.

3. **Freeze it as a reference corpus, not as code.**
   *Benefits:* keeps the 576-part output tree as the golden reference forever, at no
   maintenance cost; the `.scad` sources stay readable as documentation of intent.
   *Drawbacks:* the reference goes stale the moment the geometry legitimately changes.
   *Prerequisites:* none.

**Recommendation was alternative 3.** A frozen corpus captures nearly all the value of
alternative 2 — an independent statement of what the geometry was — without the standing
cost of maintaining two implementations, which alternative 2 will lose to entropy.

---

**DECIDED 2026-08-07: alternative 1 — retire it.** No new geometry will be developed in
OpenSCAD, and two implementations will not be maintained in parallel. **Once verified, the
FreeCAD implementation becomes the definition of correctness.**

That last clause settles it, and it is what my recommendation missed. Alternative 3 proposed
keeping the OpenSCAD output as a frozen reference corpus — but a corpus is only useful as a
*datum*, and there cannot be two definitions of correctness. The moment IP-FC-13 signs off
equivalence, the OpenSCAD tree stops being an independent check and becomes a second,
unmaintained answer to a question that now has an authoritative one. Keeping it invites
someone to read a disagreement as ambiguous when it is not.

**The corpus is therefore a migration instrument with a defined end of life, not an asset:**

| Phase | Role of the OpenSCAD output |
| --- | --- |
| Until IP-FC-13 | **The datum** — every ported part is checked against it |
| At IP-FC-13 | Equivalence demonstrated across the full parameter range |
| After IP-FC-13 | **Superseded** — FreeCAD defines correctness; the OpenSCAD implementation is removed |

**Deleting it is safer than it feels**, which is worth stating because working code is hard
to throw away: the implementation lives in git history and stays recoverable indefinitely.
Removing it from the working tree destroys nothing — it stops it being read, maintained, or
mistaken for authoritative. And the part that *would* genuinely have been lost, the design
intent the code was the only record of, is now in [corner.md](../design/corner.md),
[bulkhead.md](../design/bulkhead.md) and [cowl.md](../design/cowl.md).

**Two conditions on the removal**, both still binding:

1. **Not before the full parameter range is proven** — IP-FC-13, not the first part that
   matches.
2. **Not before the design documents are checked against it one last time.** They were
   reconstructed *from* this code; once it is gone, an error in them is no longer
   falsifiable against the original. This session found several such errors, so the risk is
   demonstrated rather than theoretical.

Tracked as IP-FC-34.

---

### ~~OQ-ARCH-5 — How is the cowl interior surface generated?~~ — DECIDED 2026-08-07: adaptive slice-and-fit

Required by UC-4. The interior must be a per-layer 2D inset matching slicer behavior, not
a perpendicular shell offset — see the use-case section for why the two differ and why the
difference is intended.

**The parameter question is settled.** Extrusion width already exists; it was stored under
the name `nozzle_diameter` and has been renamed (IP-GEO-24). No new field is needed, and —
more to the point — no new field should be *added*, because doing so would produce two
nearly-equal parameters where the design has one.

The offset should still be expressed as an explicit multiple, `n_perimeters ×
extrusion_width`, so the count and the width stay separately visible. That matches the
existing convention for `flange_thickness` and `plate_thickness`, which are already whole
multiples of extrusion width and layer height respectively.

**What remains open is the method** — how layers are sliced, how the inset is computed per
layer, how the sections are joined into a solid, and what supplies material at
near-horizontal surfaces where a horizontal inset leaves none.

**Alternatives**

1. **Slice-and-loft** — section the solid at `layer_height` intervals, offset each 2D
   contour inward by `n_perimeters × extrusion_width`, and loft the resulting contours.
   *Benefits:* directly mirrors what the slicer does, so the model matches the print by
   construction; each step uses standard 2D offset operations that OCC provides.
   *Drawbacks:* produces one contour per layer — thousands for a large cowl — so the loft
   is heavy and the resulting B-rep is large; contour topology can change between layers
   (a notch closing, a hole appearing) and a loft does not handle that gracefully.
   *Prerequisites:* none.

2. **Coarse slice-and-loft** — the same, at a spacing much larger than `layer_height`,
   chosen so the offset error stays within tolerance.
   *Benefits:* far cheaper; a smooth cowl needs few sections to capture an offset that
   varies slowly; the result is a clean surface rather than a staircase.
   *Drawbacks:* no longer exactly what the printer produces; needs a stated tolerance and
   a way to check it.
   *Prerequisites:* deciding the acceptable deviation from the true per-layer inset.

3. **3D shell offset with local correction** — use `Part::Offset`/`makeThickness` for the
   bulk, and correct where the surface approaches horizontal.
   *Benefits:* one kernel operation for most of the surface; robust and fast where the
   surface is steep.
   *Drawbacks:* offsets normal to the surface, which is *not* what the slicer does, so it
   is wrong by `1/cos α` everywhere the surface is not vertical — precisely the error this
   use case exists to avoid; the correction region is where the method is least reliable.
   *Prerequisites:* a criterion for where to switch methods.

4. **Two surfaces, explicitly** — model a nominal interior independent of slicer behavior,
   and record that it is an idealisation.
   *Benefits:* simplest to build and to reason about; adequate for mass properties and
   assembly clearance.
   *Drawbacks:* diverges from the printed part in a way that matters for UC-8; interacts
   with OQ-DES-CW6, where the ribs have the same problem.
   *Prerequisites:* ~~agreement on what the model is *for*~~ — settled by OQ-DES-CW6
   (2026-08-09): the solid model is for everything except printing, and the print keeps its
   own representation.

**Recommendation: alternative 2.** It keeps the mechanism that makes the result correct —
horizontal insets, matching the slicer — while avoiding a per-layer loft that no downstream
consumer needs at full resolution. Alternative 3 is the tempting one and should be
resisted: a normal offset is the exact error mode this use case was raised to prevent.
The near-horizontal rule needs deciding regardless of which is chosen, and it is the same
decision as the top-and-bottom-solid-layers rule a slicer applies.

**The full method belongs in an algorithm document**, not here — see IP-FC-16.

---

**DECIDED 2026-08-07: alternative 2, with four requirements on the surface it produces.**

1. **Curvature-aware, adaptive section spacing.** Not a fixed interval. Section density
   follows local curvature — close where the OML turns hard, sparse where it is nearly
   straight. Uniform spacing wastes sections on the parallel midbody and under-samples the
   nose radius, which is the one place accuracy matters.
2. **Bidirectional curvature.** The interior must be doubly curved — circumferentially
   *and* axially. Not developable, not ruled.
3. **Axial continuity: G1 tangency is the threshold, G2 curvature is the objective.**
   Tangency across every section join is the minimum acceptable result; curvature
   continuity is the goal to design toward.
4. **Explicitly not a ruled surface with tangency discontinuity.** A loft that
   straight-lines between adjacent contours and meets only C0 at each section is precisely
   the failure this requirement excludes.

**Why the continuity requirement is not cosmetic.** Wall thickness is the *difference*
between exterior and interior surfaces. The exterior is a piecewise cubic Bézier carrying
G2 across several stations by design (§1.2). If the interior is only C0 at its section
joins, then **wall thickness is discontinuous at every join** — a thickness step at a seam
the exterior does not have — even though each surface is individually acceptable. That is a
stress raiser for UC-8 and a visible artifact in UC-4 and UC-7.

Matching the interior's continuity class to the exterior's is the real requirement; G1
threshold / G2 objective is how it is stated.

**What this rules out in implementation.** A `ruled=True` loft is excluded by (4). So is a
`ruled=False` loft that merely interpolates the section curves without tangency
constraints, since that satisfies neither (3) nor generally (2). The method wants a surface
**fit** through the offset contours with continuity conditions imposed — the same class of
construction OpenVSP uses for the exterior, applied to the interior.

**Adaptive spacing has a natural termination test:** refine the interval until the deviation
between the fitted surface and the true per-layer offset falls below tolerance. That makes
spacing a derived quantity rather than a tuning knob, and gives the algorithm document a
convergence criterion to state.

The near-horizontal material rule — the equivalent of a slicer's top and bottom solid
layers — remains the main undecided item inside IP-FC-16.

**Amended 2026-08-09 by OQ-DES-CW6: this surface is not what gets printed.** Cowls are
printable in **spiral vase mode**, which permits one contour per layer and no interior
geometry at all, so a cowl carrying this interior surface is no longer vase-printable. The
interior therefore serves UC-2, UC-3, UC-4, UC-7 and UC-8, and the UC-1 export continues to
come from the un-shelled notched blank — two representations from one parametric source, as
[cowl.md §6.4](../design/cowl.md) records. Two consequences here. First, alternative 4's
"diverges from the printed part" drawback is no longer a drawback to be weighed: divergence
is the *design*, and the thing to guard is that the two paths stay separate. Second, the
interior's fidelity requirements above are unchanged but their justification narrows — they
matter because analysis and assembly need them, not because a printer will follow them.

### ~~OQ-ARCH-6 — How are assembly joints defined and stored?~~ — DECIDED 2026-08-07: Assembly joints

Required by UC-4: fuselage unit, nose, tail, and full fuselage assemblies with real joints.

The unresolved part is where the mating information lives. The geometry already knows how
the parts mate — the greeble post and its bore are complements of one shape, and the bolt
pattern is a shared parameter — so an assembly could in principle place parts by
construction rather than by constraint. That is the same argument that appears in
[OQ-DES-C3](../design/corner.md#open-questions) for the joint itself.

**Alternatives**

1. **Place parts by construction, from the parameters that already position them.**
   *Benefits:* cannot be inconsistent, for the same reason the greeble cannot; no
   constraint solver in the sweep path; headless-friendly.
   *Drawbacks:* not a FreeCAD Assembly document, so it does not interoperate with the
   Assembly workbench's tooling.
   *Prerequisites:* none.

2. **Use FreeCAD's Assembly workbench with real joints.**
   *Benefits:* idiomatic; interference checks and kinematics come free; exports as a
   proper assembly to STEP.
   *Drawbacks:* constraints can be violated or fail to solve, which is a new failure mode
   in a batch context; the solver's headless behavior is unverified.
   *Prerequisites:* confirm the Assembly workbench is scriptable under `freecadcmd`.

3. **Both — construction for placement, joints added for downstream use.**
   *Benefits:* placement stays deterministic while the assembly still carries joint
   semantics for consumers.
   *Drawbacks:* two representations of the same relationship, which is exactly the class
   of duplication this project has spent Phase 2 removing.
   *Prerequisites:* both of the above understood.

**Recommendation was to measure alternative 2's headless behavior first**, because it
decides whether the choice is real. If the Assembly workbench does not script cleanly under
`freecadcmd`, alternative 1 is the only option that runs in a sweep.

---

**DECIDED 2026-08-07: alternative 2 — FreeCAD Assembly with real joints.**

This buys what UC-4 and UC-7 actually need: interference checking, kinematics, and an
assembly that exports to STEP as an assembly rather than as a bag of solids.

**The headless question becomes a work item, not a decision gate.** Confirming that the
Assembly workbench scripts under `freecadcmd` is now a prerequisite task inside IP-FC-19
rather than a condition on the choice. If it turns out not to script, that is a problem to
solve — not a reason to revisit the decision.

**The one real objection to this option has a cheap mitigation, and it should be built in
from the start.** The drawback of joints over construction is that a constraint can fail to
solve, or solve to something unintended, and in a batch context nothing would notice.

But **the constructed placement remains computable from the parameters** — that is what
alternative 1 would have used, and those parameters do not go away. So:

> **Solve with joints; verify against the constructed placement.**
> For every assembly, compute where each part *should* sit from `unit_width`,
> `bulkhead_thickness`, `unit_length` and the rest, and assert the solver put it there
> within tolerance.

That converts the failure mode from silent into loud, at the cost of arithmetic that is
already available. It preserves the property [OQ-DES-C3](../design/corner.md#open-questions)
established — that parts sharing parameters cannot drift — while still producing a real
assembly with real joints.

**Note what this does and does not change about the geometry.** Parts still share their
cross-section and joint parameters by construction; the greeble is still formed by cutting
with `corner_end()`. Joints are an additional layer describing how parts relate, for the
benefit of downstream consumers. They are not a substitute for the parametric consistency
that makes the parts fit in the first place, and nothing here should be read as license to
let the two representations diverge.

### ~~OQ-ARCH-7 — What decides which dimensions a generated drawing carries?~~ — DECIDED 2026-08-07

Required by UC-7. Projecting a view is the easy part; TechDraw does it from any shape.
The hard part is *which* dimensions to place, and that is a question about design intent,
not geometry. A part has hundreds of dimensionable edges and a useful drawing carries a
dozen.

The observation that shapes this: **the parameter set already is the design intent.**
`corner_radius`, `bolt_offset`, `panel_thickness`, `bulkhead_thickness` are exactly the
quantities a reader of the drawing needs, and they are exactly what the geometry was
built from.

**Alternatives**

1. **Generate the dimension scheme from the `Parameters` object.**
   *Benefits:* a drawing is guaranteed to dimension the things that are actually
   parametric, and it cannot drift from the model — both come from one source; scales to
   every variant in the sweep for free.
   *Drawbacks:* needs a mapping from each parameter to the edges or faces that express it,
   which is per-part work and brittle if the topology changes.
   *Prerequisites:* stable topological references, which bears on OQ-ARCH-1.

2. **Hand-author a drawing template per part type**, reused across variants.
   *Benefits:* full control over layout and standards compliance; a draftsman's drawing
   rather than a generated one.
   *Drawbacks:* the template references specific edges, so it breaks when the geometry
   changes; one template per part type is real ongoing work.
   *Prerequisites:* none.

3. **Dimension only the interfaces** — bolt pattern, mating diameters, overall envelope —
   and treat internal structure as non-dimensioned reference geometry.
   *Benefits:* small, stable set; matches what the drawing is actually *for*, which is
   fit between parts and inspection of what mates.
   *Drawbacks:* not a manufacturing drawing in the full sense.
   *Prerequisites:* agreement on what belongs to the interface, which
   [overview.md](#relationship-to-overviewmd)'s interface-conventions section should own.

**Recommendation: alternative 3 first, then 1.** The interface dimensions are the ones
that matter and the ones that are already named as shared conventions, so they are both
the most valuable and the most stable. Growing that into a full parameter-driven scheme is
a natural second step; starting there risks spending the effort on internal dimensions
nobody reads.

Note that this use case does **not** change the OQ-ARCH-1 recommendation. TechDraw
projects any shape and does not require `PartDesign::` bodies or sketches — its dimensions
attach to projected edges and vertices, not to sketch constraints.

---

**DECIDED 2026-08-07: none of the three as posed.** The alternatives framed this as a choice
between dimensioning *interfaces* and dimensioning *parameters*. That framing is wrong twice
over.

**First: a dimension is an expression over parameters, not a parameter.** Some are a
parameter directly — `corner_radius`, `bolt_offset`. Many are *combinations*: the bulkhead's
flange inner edge sits at `corner_radius − panel_thickness − panel_tolerance`, its outer
flange face a further `flange_thickness` in. Neither is a parameter anyone set; both are
what a machinist or inspector needs.

The dimension scheme is therefore a set of **named expressions**, each bound to two
topological references. Alternative 1's "generate from the `Parameters` object" was too
literal — the object supplies the *inputs*, not the dimensions.

**A useful consequence:** the design documents already contain many of these expressions,
because documenting the geometry required deriving them.
`corner_radius − panel_thickness − panel_tolerance` appears in
[bulkhead.md](../design/bulkhead.md); the buttress profile vertices in
[cowl.md §4.1](../design/cowl.md) are expressions of exactly this kind. The scheme starts
from the design authority rather than blank.

**Second: interfaces are a floor, not the scope.** The physical interface must be documented
with dimensioning — that part of alternative 3 stands — but the drawing must also be
**complete**, and complete and **readable** pull against one another. That tension is the
real design problem and neither side is negotiable.

### What this implies

**Completeness has a testable definition** and should be stated as one: every dimension
needed to manufacture and inspect the part is present, and none is redundant.
Over-dimensioning — the same distance implied twice through different chains — is a genuine
defect rather than mere clutter, because the two chains can disagree once tolerances apply.

**The sweep makes readability easier, not harder.** 576 variants share one *scheme* and
differ only in *values*. That is exactly what classical drafting solves with a **family
drawing**: lettered callouts (A, B, C …) on the views and a table of values per variant. One
readable sheet replaces 576 crowded ones, completeness is checked once against the scheme
rather than per part, and a new variant adds a table row rather than a drawing.

That form also inverts the earlier worry about which dimensions to include: with values in a
table rather than on the view, an extra dimension costs a column instead of a crowded leader
line — so **completeness becomes affordable in a way it is not on a one-off drawing.**

**Still to settle**, and belonging to the drawing scheme's own design work:

1. Which expressions constitute the interface set — the floor, and something
   `overview.md`'s interface-conventions section should own once it exists.
2. What "complete" means for this family: fully defining every part, or fully defining
   every mating and inspected feature.
3. Whether internal structure — webs, fillets, chamfers — is dimensioned at all, or shown
   as reference geometry governed by the model.
4. How topological references survive a parameter change. This is the same edge-naming
   stability question IP-FC-5's two prototypes will answer, so it need not be solved twice.

### ~~OQ-ARCH-8 — Can printed parts be analyzed as non-uniform material?~~ — WITHDRAWN 2026-08-07: not an open question

**Miscategorized, in the same way as [OQ-ARCH-3](#open-questions).** The question was
"does a permissively-licensed tool exist for bead-level FDM analysis" — and I said in the
original text that it "should be answered by looking". That is the admission that it is a
**work item**: an observation, not a decision between alternatives.

It is [IP-FC-6](../implementation/freecad_migration.md), already an unblocked survey task.

The substance that was worth keeping is not the question but the **ladder it sat at the top
of**, and that is recorded in [§UC-8 is a ladder](#uc-8-is-a-ladder-not-a-single-capability):

- Tier 3 — orthotropic per part — is reachable with the stack already in use. CalculiX
  supports orthotropic elasticity, FreeCAD invokes it as a separate process, and the layer
  axis per part is now recorded (IP-FC-3).
- Tier 4 — bead-level or toolpath-resolved — depends on tooling whose existence is unknown.

**The decision that *would* have been an open question is a different one:** whether to
stop at tier 3 or pursue tier 4 at the cost of a heavy dependency. That question cannot be
posed usefully until the survey reports, because its alternatives depend on what the survey
finds. If IP-FC-6 turns up a viable tool, raise it then.

**Two of the nine questions in this document were work items** — this and OQ-ARCH-3. Both
had the same shape: *"we do not know the value of X"*, where X is discoverable by looking.
The test that separates them is whether resolution requires a **judgment** or an
**observation**. Recorded here because it is a cheap mistake to repeat.

### ~~OQ-ARCH-9 — Is OpenVSP's license compatible, and in which usage pattern?~~ — RESOLVED 2026-08-07

**Read from the installed copy:** `C:\Program Files\OpenVSP-3.50.5-win64\LICENSE` —
**NASA Open Source Agreement version 1.3** (3.47.0 is also installed, same terms).

**It is compatible, and the usage pattern does not matter.** NOSA's obligations key on
*distribution*, not on linkage:

| Clause | Says | Effect here |
| --- | --- | --- |
| §3.A | Obligations attach to "Distribution or Redistribution of the Subject Software" | We use OpenVSP; we do not ship it. **§3 does not bite.** |
| §3.I | A Recipient may combine Subject Software with software not governed by the Agreement and distribute the result as a single product, provided the OpenVSP portions remain under NOSA | Component-level, **not viral**. Our code keeps its own license even if OpenVSP were bundled. |
| §1.F | "the act of including Subject Software as part of a Larger Work does not in and of itself constitute a Modification" | Using it does not make us a Contributor with §3.C change-log duties. |
| §3.F | Registration "is requested" | A courtesy, not a condition. |

**So the distinction I drew between driving it as a process and importing its Python API
was wrong.** That distinction is the GPL/LGPL mental model, where linkage is what triggers
copyleft. NOSA has no such trigger — both patterns are equally fine, and the choice should
be made on engineering grounds alone. Importing the Python API is the better option for
UC-9's parametric generation, and there is no license reason to avoid it.

Two notes worth carrying forward:

- **§4.B is the clause that actually deserves thought**, and it is a liability term rather
  than a copyleft one: the Recipient waives all claims against the US Government and
  agrees to indemnify it for damages "from products based on, or resulting from,
  Recipient's use of the Subject Software", with the sole remedy being termination of the
  agreement. That is the commonly-cited objection to NOSA. It bears on shipping an
  *aircraft* designed with these tools, not on the code, and it is not a code-licensing
  question at all.
- **The Python tree is mixed-license, and OpenVSP states the split explicitly.**
  `python/openvsp/openvsp/LICENSE` opens: *"The base openvsp vsp api files (`_vsp.so`,
  `_vsp.pyd`, `vsp.py`) are distributed under the NOSA license listed below."* Everything
  else in `python/` — `utilities.py`, `parasite_drag.py`, `degen_geom_parse.py`,
  `surface_patches.py`, `facade.py`, and the sibling packages `AvlPy`, `CHARM`,
  `degen_geom`, `utilities` — is **MIT, Copyright 2018–2020 Uber Technologies**, and
  `python/openvsp/setup.py` declares `license='MIT', author='Uber Technologies'`.

  So the file you `import` for the API itself (`vsp.py`, wrapping the 30 MB `_vsp.pyd`) is
  **NOSA** — which is why the import-versus-subprocess question genuinely was a NOSA
  question, and why the answer above settles it. The higher-level helpers layered on top
  are MIT and unconditionally fine.

- **VSPAERO ships inside the Python package.** `vspaero.exe`, `vspaero_opt.exe`,
  `vsploads.exe` and `vspviewer.exe` sit in `python/openvsp/openvsp/`, so UC-9's aero half
  needs no separate install — and those are executables invoked as processes, the least
  encumbered pattern of all.

**The project's license table should gain a NOSA row**, since it now has a real dependency
under a license the table does not mention. Suggested wording: *acceptable as a separate
tool or an imported module; obligations attach only on redistribution; note the §4.B
indemnity.*

### ~~OQ-ARCH-10 — What replaces the absolute `eps` when the part gets big?~~ — WITHDRAWN 2026-08-09: not an open question

**Miscategorized, in the same way as [OQ-ARCH-3](#open-questions) and
[OQ-ARCH-8](#open-questions), and for a more interesting reason than either.** Those two were
*"we do not know the value of X"*. This one was *"we know X must exist, so how big should it
be"* — and the premise was false. The overlap does not need to exist.

The question as posed asked what should *replace* the 0.01 mm sliver, taking for granted that
a union of two solids meeting on a shared plane needs help. That is true of OpenSCAD, which
is why the overlap was added. It is not true of OCCT, and one measurement settles it:

| Fuse of a solid with its own mirror about the touching plane | 10 mm | 100 mm | 250 mm | 400 mm |
| --- | --- | --- | --- | --- |
| No overlap at all | valid, exact | valid, exact | valid, exact | valid, exact |

So the answer is not a scaled `eps`, a fuzzy tolerance, or a redesigned tiling — the three
alternatives this section originally weighed. It is `mask_eps = 0`. Every U from 0.5 to 4.0
tiles into one valid solid, the part is dimensionally unchanged (the sliver was being
reclaimed, so the full volume is identical to seven figures either way), OpenSCAD parity is
preserved at +0.00023%, and the `8 × octant` check gets stronger rather than weaker. Recorded
in [IP-FC-49](../implementation/freecad_migration.md).

**The generalisable mistake.** The earlier two work items failed the judgment-versus-
observation test outright. This one *looked* like a judgment because it presented as a
trade-off with three costed alternatives, and every one of those alternatives was real —
they were just all answers to the wrong question. A constant inherited from a port is a claim
about the *source* toolchain, and it needs re-measuring against the target before its size is
debated. The question that should have been asked first is not "how big" but "at all".

**Three of the ten questions in this document were not questions.** The test that separates
them still holds; what this adds is that it has to be applied to the premise as well as to
the question.

### ~~OQ-ARCH-10 (as originally posed)~~ — retained for the alternatives, none of which was needed

`geometry_eps()` is `0.01` mm, a constant of the OpenSCAD source, carried into the port
verbatim. Two jobs rest on it: making cuts overshoot the material they pass through, and
making the octant overlap its own mirror so the tiling fuse has something to work with.
`bulkhead_full`'s own docstring records the second — *"`octant_mask` is shifted by `eps`, so
adjacent octants overlap by a sliver and the union reclaims it"*.

That works in OpenSCAD, whose CGAL kernel is exact. It does not work in OCCT, whose booleans
work to a tolerance that scales with the shape. At U=2.5 the bulkhead is 250 mm across and
the sliver is 4 × 10⁻⁵ of it:

| U | Octant | Mirror | **Their fuse** |
| --- | --- | --- | --- |
| ≤ 2.0 | valid | valid | valid |
| ≥ 2.5 | valid | valid | **invalid** |

Only the fuse fails, and it fails for every panel — so it is a threshold in U and nothing
else. Raising `eps` at U=2.5 makes it valid again at 0.05 and every value above. The corner
is unaffected at every U up to 4.0, because the octant-and-mirror tiling is `bulkhead_full`'s
construction alone.

**`eps` is not free, which is what makes this a decision rather than a constant to raise.**
It changes the finished volume, because it is not purely internal — it also sets how far
cuts overshoot:

| U=2.0, `eps` | 0.01 | 0.05 | 0.1 | 0.25 | 0.5 |
| --- | --- | --- | --- | --- | --- |
| Volume mm³ | 39413.1119 | 39416.2807 | 39420.1978 | 39431.6900 | 39450.1504 |

**Alternatives**

1. **Scale `eps` with U.** One line, and it matches what the value is *for* — a sliver that
   has to stay resolvable relative to the part.
   *Drawbacks:* the port stops agreeing with `geometry_eps()`, so FreeCAD and OpenSCAD
   produce different volumes at every U ≠ 1, by roughly 0.01% at the sizes measured. That is
   above the tolerance IP-FC-13 has been holding the port to (0.0006%), so IP-FC-13 would
   need a stated exemption for it rather than a threshold that quietly absorbs it.
   *Prerequisite:* deciding whether OpenSCAD scales too, which changes the shipped parts.

2. **Give the boolean a fuzzy tolerance instead of moving geometry.** Tells OCCT to treat
   the faces as coincident, leaving the model dimensionally identical to OpenSCAD's.
   *Drawbacks:* `Part::Cut`/`Part::Fuse` document objects expose no fuzzy value —
   `Shape.fuse(other, tolerance)` does, but that returns a computed shape, not a feature, so
   the tiling would stop being a live parametric tree. That is the one property the port
   exists to preserve.

3. **Do not create the coincident seam.** Build the full section directly rather than an
   octant plus seven mirrors, so no boolean is ever asked about two faces on the same plane.
   *Drawbacks:* discards the construction the port is transcribing, and with it the check
   that makes the tiling verifiable — the eps overlap is why the full part is *not* eight
   times the octant, which is what proves the mirrors are about the right planes.

**None of the three was needed.** Each trades against something recorded as intent —
OpenSCAD parity, the live parametric tree, fidelity to the construction being ported — and
all three are answers to a question whose premise did not hold. Alternative 3's stated
drawback is the one to reread: it says the eps overlap *is* what proves the mirrors are about
the right planes. That was the assumption doing the damage. Removing the overlap makes the
full part exactly eight times the octant, which proves the same thing more directly.

Kept because the alternatives were correctly costed and the reasoning is sound given its
premise — which is exactly why it is worth being able to recognise this shape again.

---

### ~~OQ-ARCH-11 — Should geometric relationships be expressed as constraints, or stay solved into coordinates?~~ — DECIDED 2026-08-15: constraints, staged toward `PartDesign::`

A part in this port is a CSG tree of primitives whose positions and sizes are bound by
expression to a spreadsheet. One built frame bulkhead is 158 objects:

    Part::Box 39   Part::Cut 39   Part::Fuse 31   Part::Cylinder 20   Part::Refine 13
    Part::Cone 8   Part::Mirroring 4   Part::Common 1   Part::Extrusion 1
    Sketcher::SketchObject 1   Spreadsheet::Sheet 1

Roughly 192 `Placement` bindings plus `Height`, `Length`, `Width` and `Radius` expressions
place all of it. There is one sketch, and it exists only because a wedge profile did not
decompose into primitives.

**No geometric constraint is expressed anywhere in the port.** The complete constraint
vocabulary across every module is `Coincident`, `Horizontal`, `Vertical`, `PointOnObject`,
`DistanceX` and `DistanceY` — all of them on that single sketch. There is no `Tangent`, no
`Equal`, no `Symmetric`, no `Perpendicular`, no `Parallel`, no `Angle`, and no `Radius`
constraint in the project. Relationships that a CAD model would normally *state* are instead
*solved* in the spreadsheet and stored as coordinates.

The bolt-flange fillet is the clearest case. Its center must lie tangent to the ring of
material around the bolt, and that condition appears as a hand-solved quadratic:

    bbf_cy = sqrt(max(r_bolt_fillet ^ 2 - bbf_dx ^ 2; 0)) + bolt_c

which is "where the vertical line `x = bbf_cx` meets the circle of radius `r_bolt_fillet`
about the bolt center", evaluated to a number. See [OQ-DES-B14](../design/bulkhead.md), which
is one instance of this question.

**The variation argument does not settle it.** The obvious defence of coordinates is that the
geometry is not one shape but a family, and the relationships that hold are not the same at
every parameter value — a constraint set that is satisfiable at `U = 2` may not be at
`U = 0.5`. That is true, and it is *already represented*: it is exactly what the `max(...; 0)`
clamps, the `min`/`max` selections such as `bbf_sx = max(flange_inner_x; bolt_c)`, and the
branching in `derived_parameters()` encode. So the variation is not a reason to omit
constraints; it is the thing a constraint model would have to express, and the arithmetic is
already expressing it — just in a form nothing can inspect.

**The cost is that FreeCAD does not know what the geometry means.** The document records
where every face is and never why. Concretely:

- **Unsatisfiable configurations resolve silently.** A tangency the solver cannot satisfy is
  reported; `max(discriminant; 0)` returns a plausible wrong answer instead. Measured across
  the 88 valid end-type variants the clamp is never currently reached — closest approach is
  `|bbf_dx| / r_bolt_fillet = 0.9182` at `U=0.5 end_bolt 1mm`, discriminant 4.748 — so this is
  unguarded margin held by four independently chosen dimensions, not a designed limit.
- **Near-degenerate configurations are invisible.** IP-FC-58 was a boolean that touched a
  block at exactly one point and produced a negative-area face. A model that stated "this edge
  is tangent to that circle" has somewhere to check; a model of coordinates has nowhere.
- **Downstream features need topology, not numbers.** OQ-ARCH-7 already decided that drawing
  dimensions are named expressions *bound to topological references* (IP-FC-21), OQ-ARCH-6
  that assemblies use real joints verified against constructed placements (IP-FC-19), and
  IP-FC-36 that interface dimensions are enumerated. All three want to attach meaning to
  faces and edges of a tree that currently carries none, over a 158-node CSG history where
  topological names are least stable.
- **A hand edit has nothing to preserve.** Someone opening a generated document sees a box at
  x = −11.8 with no record that it is one fillet radius outboard of the flange face; move it
  and nothing objects.

**Alternatives**

1. **Keep coordinates everywhere.** Status quo. *Benefits:* fastest to build (~1.3 s/part),
   trivially diffable, and it is what made the port verifiable — every part could be compared
   numerically against the OpenSCAD original because both are pure functions of parameters.
   Editability in the sense that matters today is preserved: change `U` and everything
   follows. *Drawbacks:* every point above. *Prerequisites:* none.

2. **Express relationships as constraints only where a relationship exists.** Keep CSG for
   bulk material; use fully constrained sketches with real `Tangent`, `Perpendicular` and
   `Equal` constraints for the features whose position is *derived* from another feature —
   the fillets, the chamfers, the greeble interface. *Benefits:* the solver reports what the
   arithmetic clamps; the document states intent; drawing and assembly references attach to
   things that mean something. *Drawbacks:* sketches are slower to solve, and a solver can
   pick the wrong branch of a relationship that has two solutions — the other intersection of
   a line and a circle — which is a real risk and a detectable one. Variants where a
   relationship is unsatisfiable now *fail* rather than clamp, which is the point but changes
   the swept space. **It does not cost the OpenSCAD verification**, contrary to the first
   draft of this question: `compare_backends` measures the *built solid* — mesh volume and
   bounding box — and never needs a closed-form parameter-to-coordinate mapping, so a
   constrained feature is compared exactly as a computed one is. *Prerequisites:* deciding,
   per feature, what the relationship actually is — which is OQ-DES-B14 for the bolt-flange
   fillet, and is not recorded for the others either.

3. **Keep coordinates, add assertions.** Compute as now, but check the relationship the
   arithmetic is supposed to satisfy — assert tangency to a tolerance, assert discriminants
   are positive by a margin, assert no two construction planes are closer than some distance.
   *Benefits:* catches every failure mode listed above at build time, costs no solver time,
   changes no geometry, and is verifiable as a no-op. *Drawbacks:* does nothing for the
   downstream topology problem — drawings and assemblies still have nothing to bind to — and
   the assertions restate the intent in a third place rather than recording it once.
   *Prerequisites:* none technically; each assertion still needs the intent it is asserting.

4. **Move the whole port to `PartDesign::` with sketch-driven features.** Revisits OQ-ARCH-1,
   which chose `Part::` on the evidence of IP-FC-5. *Benefits:* the fullest expression of
   intent, and the native path for drawings and assemblies — **this is what a FreeCAD model of
   this part would look like if it had been authored in FreeCAD rather than translated into
   it.** *Drawbacks:* a rewrite of every ported module, and PartDesign's single-solid-per-body
   rule fits the octant-and-mirror construction badly — that constraint needs a real answer,
   not a workaround. *Prerequisites:* the OpenSCAD reference retired or frozen (see the
   staging below), and a resolution for the body rule against the tiling.

**Direction — decided 2026-08-15: stage toward Alternative 4, starting with Alternative 2**

**Alternative 4 is the target state, not a rejected option.** It is the true native FreeCAD
implementation, and the intent is to get there rather than to settle permanently for a
translated CSG tree. What follows is the route, and the first step is Alternative 2 —
relationships expressed as constraints FreeCAD can act on, not merely computed and stored.

Two facts make the staging principled rather than arbitrary:

- **Constraints do not cost the OpenSCAD verification.** `compare_backends` measures the built
  solid's volume and bounding box. Nothing in it requires geometry to be a closed-form
  function of the parameters, so a constrained feature is checked exactly as a computed one
  is. The first draft of this question claimed otherwise and was wrong; that error was the
  main reason it recommended deferring.
- **The OpenSCAD reference already has a planned retirement.** OQ-ARCH-4 decided on 2026-08-07
  to retire it once IP-FC-13 demonstrates equivalence across the parameter range, at which
  point FreeCAD becomes the definition of correctness. So the strongest objection to
  Alternative 4 — that a rewrite discards the verification chain — expires on a date the
  architecture has already chosen, rather than standing forever.

**Stage 1 — express the relationships (Alternative 2), OpenSCAD reference intact.**
Keep CSG for bulk material. Convert the features whose position is *derived* from another
feature — the five fillets and chamfers in `fillets.py` first, since that is where IP-FC-58
came from — to fully constrained sketches carrying the real relationship. Each conversion is
verified with the existing comparison, which continues to work unchanged. Each also forces the
intent question for that feature to be answered and written down, which is the part that has
no shortcut: OQ-DES-B14 is that question for the bolt-flange fillet and nothing equivalent is
recorded for the others. Exit criterion: every derived feature states its relationship, and
the whole corpus still agrees with OpenSCAD.

**Stage 2 — bind the downstream work to it.** With features carrying stable, meaningful
references, IP-FC-21's family drawings and IP-FC-19's assembly joints attach to geometry
rather than to positions in a 158-node boolean history. These are the features that make the
constraint work pay, and they should pull stage 1 forward for whatever they need first rather
than waiting for it to complete.

**Stage 3 — Alternative 4, gated on OQ-ARCH-4 firing.** When IP-FC-12 completes the cowls and
IP-FC-13 closes whole-corpus equivalence, OpenSCAD retires and a frozen FreeCAD corpus becomes
the reference — `compare_backends` compares meshes, so it retargets to that corpus with no
change to what it does. At that point PartDesign conversion is verifiable body by body against
frozen geometry, which is the safe way to do it, and stage 1 will already have produced the
constrained sketches PartDesign features need. The open item to resolve before stage 3 is the
single-solid-per-body rule against the octant-and-mirror construction — that is a real
architectural question and it should be raised on its own once stage 1 is under way.

**What is still genuinely open**, and should not be read as settled by the above: whether
stage 3 converts the whole corpus or only the parts that benefit; how a solver branch
ambiguity is guarded against in stage 1 (a constraint with two solutions can converge on the
wrong one, which the mesh comparison detects but does not prevent); and whether Alternative 3's
assertions are still worth adding as an interim measure for features not yet converted. The
first stage-1 conversion should be treated as answering those empirically.

**Superseded recommendation, kept because it was wrong in an instructive way.** The first
draft of this question recommended *Alternative 3 now, Alternative 2 only where IP-FC-21 and
IP-FC-19 force it, and not Alternative 4*, on the reasoning that constraints would cost the
numeric verification chain and that the chain is the only reason the port is trustworthy. **The
premise was false**: `compare_backends` compares built meshes, not coordinates, so constraints
cost it nothing. The conclusion inherited the error — it deferred the architecturally correct
move to protect something that was never at risk, and it treated as permanent an objection that
OQ-ARCH-4 had already scheduled to expire. Worth rereading whenever "we cannot do that, it
would break verification" is offered as an argument: check what the verification actually
measures first.

---

### ~~OQ-ARCH-12 — What carries the interface verification tier above 100 mm?~~ — DECIDED 2026-08-16: scale `BBOX_TOL` with `U`, and let the limit expire with the OpenSCAD sweep

**Resolution.** **Alternative 2** for the mechanism — `BBOX_TOL` becomes `5e-4 mm × U`, floored
at its historical value for `U` < 1 — together with **Alternative 4** for the disposition: the
underlying limit is accepted and allowed to lapse when OQ-ARCH-4 retires the OpenSCAD reference
after IP-FC-13. **Alternative 1 was explicitly declined**: the reference is *not* to be
re-rendered as binary STL, even though the measurement showed it would drive the difference to
exactly zero, because it invalidates every stored reference tree to improve a check that already
has a scheduled end. Alternative 3 was not taken up.

Implemented the same day in `compare_backends.py` as `bbox_tol(u)`, with `u_of(name)` reading
the size off the part filename the way `kind_of` already reads the kind — the comparison is
handed nothing but names and two rendered trees. A name whose `U` cannot be read raises rather
than defaulting, since assuming `U` = 1 would apply a threshold too tight for a large part and
report a failure that is not real.

**Extended 2026-08-18 to the FreeCAD-side checks, which had the same defect and had not been
covered by this decision.** The rule here is about *any* tolerance on a length, not only the one
in `compare_backends`: a part's coordinates are proportional to `U`, so a fixed millimetre figure
means something four times stricter at `U` = 4 than at `U` = 1. Three had been left absolute —
`check_tangency.TOL` and `SWEEP_TOL`, which measure how far a solved fillet center is from where
its tangencies put it, and the branch guard inside `fillets._fillet_tangency_sketch()`. All three
now scale linearly and are floored at `U` = 1, as `bbox_tol()` is, and `check_tangency.u_of()`
refuses a seed carrying no `U` for the reason `compare_backends.u_of()` does. `fillets.py` reads
the size as `unit_width / 100` because the octant's sheet carries only the rows it builds from and
`U` is not among them. The same pass made `check_unread_rows` scale its bounding-box tolerance and
made its *volume* tolerance relative to the part's own volume — which is this rule as `U`³, the
form that reads correctly for a volume, a threshold linear in `U` being wrong for a cubic
quantity. That one was not cosmetic: the absolute figure it replaced sat below the solid kernel's
own reproducibility and made every bulkhead run refuse, which IP-FC-56 records in full.

**Caveats attached to the choice, each of which is a thing this deliberately gives up.**

- **The interface tier is now size-dependent**, which is the drawback recorded under
  Alternative 2 and is accepted, not solved: at large `U` the threshold is a fraction of the
  part rather than a fixed distance, which is closer to what the volume tier already measures.
- **The relative component is set from the reference's file format, not from any design
  requirement.** `5e-4 × U` was chosen because it clears the six-significant-figure quantum at
  every swept size — 5.0× headroom at `U` ≤ 1, 10× at `U` = 2.0, and a thinnest 1.2× at
  `U` = 2.5, immediately after the quantum's decade step. It carries no other meaning.
- **The change can only loosen, never tighten**, which is why no corpus re-run was required to
  adopt it safely: with the floor at `U` = 1 the new threshold is greater than or equal to the
  old one at every swept size, so no part that passed before can fail now. The converse is the
  cost — parts whose bounding boxes differ by between 5e-4 mm and `5e-4 × U` will now pass
  silently. From the last full run only IP-FC-71's two bulkheads were anywhere near the old
  threshold, and both are explained.
- **Nothing physical is at stake in either direction**, which is what makes accepting the limit
  reasonable: the worst discrepancy involved is 1e-3 mm, 100× under a printed bolt clearance and
  200× under one layer.

**The question and its alternatives are kept below**, in this document's usual practice, because
the measurements in them are the justification for the number — particularly the binary-STL
result, which will be the right answer for anyone who revisits this before OQ-ARCH-4 fires.

---

**Not blocking, and the physical stakes are low.** No part is known to be wrong, the check is
sound on every part whose extents stay under about 100 mm — all of `U` ≤ 2.0 — and the largest
discrepancy involved, 1e-3 mm, is **100 times under a printed bolt clearance and 200 times under
one 0.2 mm layer**. Nothing here is a fit or airworthiness question. What is at stake is
*detection*: the strictest tier of the equivalence check quietly loses its resolution on the
largest parts, and nothing in the output says so.

**The setup, in full.** The port is verified by rendering the same variant with both geometry
engines and comparing the two solids. `compare_backends.py` applies two independent tolerances
per part: a **volume** tolerance, relative, 6e-5 for kinds that reproduce exactly and 1e-4 for
kinds carrying fillets; and a **bounding-box** tolerance, `BBOX_TOL`, **absolute at 5e-4 mm**
(0.5 µm). The two answer different questions. Volume asks whether the same amount of material is
present; the bounding box asks whether it is in the same *place*, since a part can be the right
size and have one face displaced. `BBOX_TOL` is deliberately absolute and deliberately strict in
both tiers, per OQ-DES-B9 in [bulkhead.md](../design/bulkhead.md), on the reasoning that **no
interface dimension is set by a fillet** — faceting error explains a volume difference and never
explains a moved interface.

**The problem is that the reference cannot express 5e-4 mm at the sizes involved.** OpenSCAD
emits an **ASCII STL**, which writes each coordinate at **six significant figures**. That is a
quantization whose absolute size grows with the coordinate:

| coordinate magnitude | ASCII STL quantum | against `BBOX_TOL` = 5e-4 mm |
| --- | --- | --- |
| 1 to 10 mm | 1e-5 mm | 50× finer than the tolerance — check is sound |
| 10 to 100 mm | 1e-4 mm | 5× finer — still sound |
| 100 to 1000 mm | 1e-3 mm | **2× coarser — the check cannot resolve its own tolerance** |

Measured on this build rather than derived from the format: writing 1.234565, 12.34565, 98.76545,
123.4565 and 234.5675 mm gives back `1.23457`, `12.3456`, `98.7654`, `123.456` and `234.568`.
The quantum steps by decade, so the boundary is sharp — a coordinate at 99 mm is checked five
times finer than its tolerance and one at 101 mm twice coarser.

FreeCAD writes a **binary STL**, whose float32 coordinates carry about seven significant figures
— 7.6e-6 mm at 120 mm and 1.5e-5 mm at 200 mm, comfortably inside the tolerance. So the two
meshes are not equally precise, and the less precise one is the authority. **The format, not the
engine, is what differs**: OpenSCAD writes binary STL to the same float32 precision when asked,
measured on this build (see Alternative 1), so this is a choice the port made rather than a
limitation of the reference implementation.

**Measured, not projected.** On `U_2.5 imperial 3/16in`, the plan half-extent is
`unit_width / 2 − (panel_thickness + panel_tolerance)` = 125 − 4.8625 = **120.1375 mm exactly**,
seven significant figures. OpenSCAD writes `120.137`; FreeCAD stores `120.137496948`, the nearest
float32 to the true value. **Both engines built the same geometry** — the entire 0.000497 mm
difference is how the number was written down. The same discrepancy appears on `U_3.0 3/16in` at
145.137 against 145.1375, **identical to the last digit** at 0.00049694824218704525 mm. Note the
imperial panel is the trigger only because it produces a seven-figure extent: 3/16 in is
4.7625 mm exactly, and 4.7625 + 0.1 mm of tolerance leaves a trailing 5 that the sixth figure
cannot hold. Metric panels at the same sizes land on shorter decimals and are unaffected.

**Why this surfaced now, and why it looked like a geometry defect.** Both variants were reported
as bounding-box failures at exactly 0.000500 mm (IP-FC-71), because the comparison rounded each
box to four decimal places before subtracting — landing 120.137 and 120.1375 on different grid
points — and the resulting subtraction of two ~120 mm doubles fell 2.4e-15 mm above the tolerance.
That rounding is fixed. What is left is the underlying limit, which the fix does not touch:
these parts now pass partly because OpenSCAD's sixth digit happened to round **down**. Had it
rounded up to `120.138`, the raw difference would be 0.000503 mm and the check would still fail
with the two models in exact agreement.

**The underlying mismatch is that the three quantities involved do not scale the same way,
and this was bound to break somewhere.** `unit_width` is `100 · U` exactly, so every plan
coordinate grows linearly with `U` and every volume grows as `U³`. Against that:

| quantity | how it is expressed | what happens as `U` grows |
| --- | --- | --- |
| volume tolerances (6e-5, 1e-4) | **relative** to the part's volume | absolute allowance grows as `U³` — tracks the part |
| ASCII STL precision | **relative** (six significant figures) | absolute quantum grows with the coordinate, by decade steps |
| `BBOX_TOL` (5e-4 mm) | **absolute** | unchanged — so it becomes *relatively stricter* |

In numbers, `BBOX_TOL` as a fraction of the part's own half-extent (`50 · U`) is 2.0e-5 at
`U` = 0.5, 1.0e-5 at `U` = 1.0, 4.0e-6 at `U` = 2.5 and 2.5e-6 at `U` = 4.0 — **eight times
stricter on the largest part than on the smallest**, while the reference's relative precision
stays flat at roughly six figures throughout. Two curves moving in opposite directions must
cross, and the crossing is exactly the 100 mm step in the table above: the extent is
`unit_width / 2 − (panel_thickness + panel_tolerance)`, which is 95.1375 mm at `U` = 2.0 and
120.1375 mm at `U` = 2.5.

**`BBOX_TOL` is a numerical agreement threshold, not a manufacturing tolerance, and reading it
as the latter leads to wrong conclusions.** It is worth being explicit, because the mistake is
easy: 5e-4 mm is **200 times tighter than a printed bolt clearance**, which is on the order of
0.1 mm, and **400 times finer than the 0.2 mm layer height**. No joint on this airframe is toleranced
anywhere near 5e-4 mm and none could be — the process cannot hold it. What OQ-DES-B9 actually
says is that parts built before and after the port are interchangeable *at every interface*,
"since no interface dimension is set by a fillet": fillets are the only thing the port changes,
so the **expected difference at an interface is exactly zero**. `BBOX_TOL` is therefore a noise
floor around that zero — set as low as the two meshes allow, to catch a modeling divergence
whose signature happens to be small — and not a statement about what a joint may be out by.

**That reframing sets the real severity, which is lower than a bounding-box failure suggests.**
The worst discrepancy this question concerns is the 1e-3 mm ASCII quantum, which is 100 times
under a bolt clearance and 200 times under one printed layer. **Nothing unfittable or unprintable
is hiding here.** What is at stake is evidence, not airworthiness: the check exists to notice
that a face moved at all, because on a part whose interfaces should reproduce exactly, a
sub-micron displacement can be the visible tip of a modeling difference that matters elsewhere.
Losing resolution costs detection, not fit.

**The absolute form is still the right one for a floor around zero** — a threshold that grows
with the part would stop meaning "these agree" and start meaning "these agree to within a
fraction," which is what the volume tier already measures. The defect is that the *reference's
precision* is relative while the *threshold* is absolute, so any absolute threshold whatsoever
fails once the part is large enough. Nothing about 5e-4 mm in particular is at fault; a 1e-3 mm
threshold would meet the same wall a decade further out.

**Affected and unaffected.** Affected: any extent whose value needs a seventh significant figure,
which in the swept space means `U` ≥ 2.5 on the imperial panels — measured at U = 2.5 and U = 3.0,
and predicted at U = 4.0 (195.1375 mm) by the same arithmetic. Unaffected: every metric panel,
every `U` ≤ 2.0, the volume tolerance at all sizes, and the FreeCAD side throughout. Also
unaffected is anything that reads the FreeCAD `.FCStd` rather than a mesh — the parametric
document carries doubles and is not involved.

#### Alternatives

1. **Export the OpenSCAD reference as binary STL.**
   OpenSCAD emits binary STL with `--export-format binstl`. **Measured 2026-08-16 on this build
   (OpenSCAD 2021.01), and it is better than "about seven significant figures":** exporting a
   solid whose extents are 120.1375, 145.1375 and 195.1375 mm — the three plan half-extents that
   need a seventh figure — the ASCII writer emits `120.137`, `145.137`, `195.137`, while the
   binary writer stores `120.13749694824219`, `145.1374969482422` and `195.1374969482422`. Those
   are **exactly the nearest float32 to each true value, and bit-identical to what FreeCAD's own
   binary STL stores.** The float32 quantum at these magnitudes is 7.6e-6 mm below 128 mm and
   1.5e-5 mm above it — **33 to 65 times finer than `BBOX_TOL`**, against the ASCII writer's
   1e-3 mm, which is twice coarser.
   *Benefits:* removes the limit rather than describing it, at every swept size; because both
   engines would then write the nearest float32 of the same true value, the bounding-box
   difference on the affected extents becomes **exactly zero rather than merely under tolerance**;
   `BBOX_TOL` and the OQ-DES-B9 position stay exactly as they are; no per-size special casing
   anywhere. **The comparison tooling needs no change** — `mesh_stats.load_triangles` already
   reads binary STL, since the FreeCAD side has always been binary, and nothing outside that
   module parses STL text.
   *Drawbacks:* changes the authority's output format, so every stored reference mesh is
   invalidated and `--reference` trees must be re-rendered; the ASCII form is human-readable and
   greppable, which has been useful in diagnosis — including this one, where reading the vertex
   line directly is what identified the cause; float32 is still not exact, so the limit is pushed
   out by four orders rather than removed in principle.
   *Prerequisites:* ~~confirm this OpenSCAD build's binary STL writer is float32~~ — **done, see
   above.** Remaining: the render command is `solid2`'s `openscad_stl_command` template, used at
   one call site in `fuselage_variants.py`, so the change is that template plus a full corpus
   re-render and comparison to confirm no verdict changes.

2. **Give `BBOX_TOL` a relative component sized to the reference's precision.**
   Replace the absolute 5e-4 mm with something like `max(5e-4, k · |coordinate|)`, where `k` is
   set from the six-significant-figure quantum.
   *Benefits:* keeps the strict absolute limit on the small parts, where it bites hardest and
   where interfaces are tightest; needs no change to the authority or to any stored mesh; states
   the limit in the check itself rather than leaving it implicit.
   *Drawbacks:* explicitly weakens the interface tier on the largest parts — at 120 mm the
   tolerance would have to reach about 1e-3 mm, twice its current value, to cover the quantum,
   and a real 1e-3 mm face displacement there would then pass; it encodes a property of the
   *reference's file format* into a tolerance that is supposed to express a *design* position,
   so the number stops meaning "these two agree" and starts meaning "these two agree to within a
   fraction of the part", which is what the volume tier already measures; the interface check
   then no longer has a form the volume check does not.
   *Prerequisites:* a value for the relative component, taken from the reference's six-figure
   precision rather than from any design requirement — which is the honest way to set it, and
   also the tell that it is compensating for a file format.
   *A drawback claimed here on 2026-08-16 and withdrawn the same day:* that a relative component
   "inverts the design intent" by letting the largest parts have the loosest joints. That reads
   `BBOX_TOL` as a manufacturing tolerance, which it is not — 5e-4 mm is 200 times tighter than a
   printed bolt clearance and could not be held by the process. It is a noise floor around an
   expected zero, and scaling a noise floor with the noise is coherent. The real objection to
   this alternative is the one above: it makes the interface tier a second volume tier.

3. **Compare each extent against its derived design value instead of mesh against mesh.**
   Express the expected bounding box as a function of the parameters — for the frame bulkhead,
   `unit_width / 2 − (panel_thickness + panel_tolerance)` and its counterparts — and check each
   mesh against that rather than against the other mesh.
   *Benefits:* the only option that inherits neither mesh's precision, so it is exact for both
   engines at every size; it also catches the case where *both* engines are wrong in the same
   way, which a mesh-to-mesh comparison can never detect; it makes the interface dimensions
   explicit as expressions, which is what OQ-ARCH-7 already decided drawing dimensions must be.
   *Drawbacks:* by far the most work, and the work is per kind — each part's extents must be
   derived and kept correct as geometry changes, which is a second implementation of the geometry
   that can itself be wrong; a wrong expression produces confident false failures.
   *Prerequisites:* the extents expressed as parameters for all five kinds; a way to keep them
   honest against the geometry modules, since a stale expression is worse than no check.

4. **Accept the limit and let it expire with the OpenSCAD reference.**
   Record the limit, leave the check as it is, and let it lapse when OQ-ARCH-4 fires and the
   OpenSCAD implementation is retired after IP-FC-13 — at which point there is no reference mesh
   and no cross-kernel bounding-box comparison at all.
   *Benefits:* costs nothing; touches neither the authority nor the tolerance nor the design
   position; matches the precedent set in IP-FC-55, where a real but non-urgent removal was
   deliberately deferred to IP-FC-34 rather than weakening a check against the authority while
   the authority still stood.
   *Drawbacks:* IP-FC-13 is the item this check exists to *serve*, so the weakened tier is in
   force for exactly the period it matters most — every remaining verdict on the largest parts is
   taken with a check that cannot resolve its own tolerance; if a genuine interface defect at
   1e-3 mm exists on a large part today, this option is the one that guarantees it is not found.
   *Prerequisites:* none, but it needs the limit recorded where a reader of a passing comparison
   will see it, not only here.

#### Recommendation

**Alternative 1, binary STL for the reference, with Alternative 4's reasoning as the reason not
to do more than that.**

It is the only option that restores the check to what it was supposed to be, and it does so
without touching `BBOX_TOL` or OQ-DES-B9 — the position is not in question here, only the file
format's ability to carry it. Because OQ-DES-B9's claim is that the expected interface
difference is **exactly zero**, and binary STL makes both engines write the same bits, this
alternative does not merely widen the margin — it lets the check assert the thing the design
position actually claims. Alternative 2 reaches the same verdicts by loosening the threshold
until the format's noise fits inside it, which works, but leaves the interface tier measuring a
fraction of the part — a second volume tier, in a check that already has one.
Alternative 3 is the right long-term answer for a different reason — it catches both engines
being wrong together, which nothing currently does — but it is a large piece of work whose
failure mode is confident false failures, and it should be justified on its own merits rather
than adopted as a fix for a six-digit export.

Alternative 4 is a serious contender and is what makes this "not blocking": the whole
cross-kernel comparison has a scheduled end, and spending heavily on it now is exactly the
mistake OQ-ARCH-11's superseded recommendation made in the other direction. That is the argument
against Alternatives 2 and 3, not against 1 — Alternative 1 is a change to a render flag and a
re-render, small enough that the retirement schedule does not argue against it.

**The measurement this recommendation was conditional on has been made, and it came back
favorable.** OpenSCAD 2021.01's binary writer stores full float32 — bit-identical to FreeCAD's,
33 to 65 times finer than `BBOX_TOL` at the magnitudes involved — so the conditional fallback to
Alternative 4 does not apply. It also strengthens the case beyond what was first written here:
the two engines would not merely agree within tolerance on the affected extents, they would write
**the same bits**, which is the strongest form this check can take. And the comparison tooling
already reads binary STL, so the change is a render flag rather than a porting job.

**What remains before closing is a decision, not a measurement**: whether re-rendering every
stored reference tree is worth spending on a check that OQ-ARCH-4 has scheduled for retirement.
That is the one real cost, and it is the question this alternative turns on.

---

### ~~OQ-ARCH-13 — Should the flange chamfer become a real chamfer feature?~~ — DECIDED 2026-08-16: yes, but with the `PartDesign` move; leave it alone until then

**Resolution.** **Alternative 1 now, alternative 3 later**, as recommended. The two-prism
construction stays for the present and `fillets.py` records beside it that the shape is a
workaround for OpenSCAD rather than a design, so the next reader does not mistake it for
intent the way the first draft of this question did. Converting it to a real chamfer
feature is scheduled as **IP-FC-78**, to be done with the move to `PartDesign` (IP-FC-75),
which is where edge references become stable enough to name one and where a chamfer
operation is the natural way to express the feature.

**Caveats carried by the choice.** The chamfer keeps its nine spreadsheet rows and its
rotated construction frame in the meantime, so a change to the flange outline still has to
be carried into those rows by hand and nothing will report it if it is not. The conversion
is also the one piece of this work that can move the flown part, so when IP-FC-78 is done
it needs a whole-corpus comparison rather than the bit-identical check the rounded corners
get, and the behavior where two runs meet at a corner has to be measured rather than
assumed. **The question and its alternatives are kept below**, in this document's usual
practice: the reasoning about why the construction is not evidence of intent is the part
worth having when IP-FC-78 comes up.

---

**Nothing is blocked by this today.** The three rounded corners still to be converted can be done
without an answer. The one thing it holds up is being able to say the work on the bulkhead is
finished, because that work was defined in a way that neither clearly includes nor clearly
excludes this one feature.

#### What the feature is

The bulkhead is a flat plate with a wall — the flange — standing up around its outer edge. Where
the inside of that wall meets the flat material inboard of it there is a sharp internal corner,
and the flange chamfer fills it with a 45 degree face. It is extra material, not a cut: it is one
of eight pieces union'd together to make the flange.

**What it is for, stated 2026-08-16:** it runs the full interior perimeter of the flange and
continues around the bolt or anchor, and its job is **strain relief** at that interior corner
between the flange and the web. That is a structural purpose, not a cosmetic break of a sharp
edge, and it is not recoverable from the code — the geometry says where the material is and
nothing says why.

Two things follow that matter here. The feature is **defined by the corner it follows**, so
wherever that corner goes the chamfer must go. And its **size is a structural quantity**, so it
is not free to be changed for modeling convenience.

The run, traced from the assembled part — along the inside of the flange, then turning in to the
bolt:

![Where the flange chamfer runs on the bulkhead](img/flange_chamfer/where.svg)

Sawn through square, at the place marked above, the flange is 1.2 mm thick and stands 6 mm up
from a plate 0.8 mm thick. The chamfer is the shaded wedge in the corner between them — 1.0 mm
along the flat and 1.0 mm up the wall, at 45 degrees:

![The flange sawn through, with the chamfer picked out](img/flange_chamfer/section.svg)

#### What the four rounded corners are

The same job — filling an internal corner between two surfaces — but with a circular arc instead
of a straight face. This one fills the corner between a wall that runs diagonally across the
bulkhead and the raised boss around a bolt hole:

![A rounded corner and the two surfaces it touches](img/flange_chamfer/rounded_corner.svg)

#### Why the chamfer sits awkwardly in this work

Both kinds of feature are defined against two surfaces, so the difference is not that one has a
relationship and the other does not. The difference is what has to happen before you can say
where it goes.

For a rounded corner of a given radius there is exactly one position where the circle touches
both surfaces, and finding it takes algebra. In the model as it stands that algebra was done by
hand and the answer stored as a pair of coordinates in a spreadsheet, so what survives is a
number and the reason for it is gone. That is what the work in progress is for: put the
requirement in a sketch, let FreeCAD find the position, and the reason is in the model again.

For the chamfer there is nothing to find. Its two ends are 1.0 mm from the corner along each
surface, which is a measurement, not a solution.

That is why the work these five features belong to describes what it covers in two ways that
disagree here, in a single sentence:

- **by what the feature is like** — the features whose position is worked out from where another
  feature ended up
- **by where the code lives** — the five fillets and chamfers in `freecad/fillets.py`

The four rounded corners match both. The chamfer matches the second and not the first.

#### What was measured

On 2026-08-16 each of the four rounded corners was checked, on all 148 buildable bulkheads,
against the claim that its position is exactly where the two surfaces it touches put it. All four
hold to within 3.6e-15 mm — so the coordinates in the spreadsheet today really are those contacts
worked out by hand, and replacing them with stated requirements will not move the part.
`tools/fillet_intent.py` is that check. The chamfer is absent from it because there is no
equivalent claim to test.

#### How the chamfer is built today, and why

Two prisms, one running along the flange and one turning in toward the bolt. Each is a
rectangular box with a second box, rotated 45 degrees, subtracted from it to take one corner off
— so a flat 45 degree face is expressed as the leftover of one box minus another. Nine
spreadsheet rows size and place those boxes, and it is the only feature in the file built in a
rotated frame of its own rather than in the part's coordinates.

**That construction is not a design decision — it is a workaround for OpenSCAD** (stated
2026-08-16). OpenSCAD has no way to point at an edge and chamfer it, the way a CAD package does,
so a chamfer has to be built as explicit geometry, in as many pieces as the corner has runs. The
FreeCAD port then transcribed that workaround faithfully, which was the right thing to do while
OpenSCAD was the authority.

**That reframes the question.** Two different things were lost getting these features into the
model, with different causes and different fixes:

| what was lost | how | which features |
| --- | --- | --- |
| the *reason* a position is what it is | a tangency solved by hand, the answer stored as coordinates | the four rounded corners |
| the *operation* the feature is | a tool that cannot chamfer an edge, so the shape is built by hand | the chamfer |

The work in progress addresses the first. The chamfer suffers the second. Both amount to "the
model no longer says what was meant", which is why grouping all five together looked reasonable —
but the fix for one is not the fix for the other, and only the chamfer's fix is blocked on
something outside itself.

#### Alternatives

1. **Leave the construction as it is, and write down why.**
   Record that this feature's position needs no solving and that its build is an OpenSCAD
   workaround, and leave it alone.
   *Benefits:* no work, and no risk to a part that is currently correct.
   *Drawbacks:* keeps a hand-built stand-in for an operation FreeCAD can perform directly, and
   keeps nine spreadsheet rows that must stay mutually consistent to produce one 45 degree face.
   *Prerequisites:* none.

2. **Draw its outline as a sketch.**
   Replace the box-minus-rotated-box with a five-corner sketch of the profile, dimensioned
   against the same spreadsheet rows and extruded to the same lengths.
   *Benefits:* the profile becomes a shape a reader can see rather than the residue of a
   subtraction. Two of the nine rows exist only to place the rotated cutting box and would go.
   *Drawbacks:* states nothing that was not already stated, and it is still a hand-built shape
   standing in for an operation.
   *Prerequisites:* none; the sketch conventions already exist in this file.

3. **Use a real chamfer feature.**
   Build the flange with a sharp internal corner, then apply FreeCAD's chamfer operation to that
   edge, sized by the one parameter that means "how much relief".
   *Benefits:* the only option where the model says what the feature is and does what it is for.
   One parameter replaces nine spreadsheet rows. The chamfer follows the corner wherever the
   corner goes, instead of being re-derived by hand if the flange outline changes. It also
   produces a named edge, which is what the later work on drawings and assembly joints needs.
   *Drawbacks:* it has to identify an edge of a shape produced by a boolean, and those names are
   not stable across a rebuild — the same instability already blocking that later work. The
   chamfer runs around corners where two runs meet, and whether FreeCAD produces the same shape
   there as the present construction is unknown. **This is the only alternative that can change
   the flown part**, so it needs a full comparison against OpenSCAD rather than the bit-identical
   check the rounded corners get.
   *Prerequisites:* a dependable way to name the edge; a whole-corpus comparison.

4. **Decide it later.**
   Leave it alone and revisit when the parts move to FreeCAD's `PartDesign` workbench, where the
   choice comes up anyway.
   *Benefits:* avoids doing the work twice. Costs nothing now.
   *Drawbacks:* the question stays open until then, and that move is itself blocked behind a
   whole-corpus comparison.

#### Recommendation

**Alternative 3 — a real chamfer feature — is the right end state, and alternative 1 is what to
do until it can be done safely.** So: leave the construction alone for now, write next to it in
`fillets.py` that it is an OpenSCAD workaround rather than a design, and do alternative 3 as part
of the work that makes edge references stable.

**This reverses the first recommendation written here, and the reason is worth keeping.** That
version argued for leaving the chamfer alone permanently, on the grounds that its position is
measured rather than solved, so it is simply not the kind of feature this work is about. The
first half of that is still true. The conclusion was wrong, because it reasoned from the
construction as though the construction were intended. Once it is known that the two-prism build
exists only because OpenSCAD cannot chamfer an edge, "not the kind of thing we are fixing" stops
holding: it is exactly the kind of thing — a feature the model no longer states, because the tool
of the day could not state it — and FreeCAD is the tool that can.

Three things make it the target rather than a nice-to-have:

- **The feature is defined by the edge it follows.** Its purpose is strain relief along the
  interior corner. A chamfer applied to that edge follows the corner wherever it goes; two
  hand-placed prisms have to be re-derived by hand if the flange outline changes, and nothing
  would report it if they were not.
- **Its size is structural.** One parameter meaning "how much relief" is safer than nine
  spreadsheet rows that must stay mutually consistent to produce it.
- **The reason for the workaround is being retired.** OQ-ARCH-4 already decided OpenSCAD goes
  once the comparison passes, after which FreeCAD is the definition of correctness. Carrying its
  limitations past that point is the opposite of the point of the migration.

**What holds it back is real and unchanged**: it needs to name an edge of a shape produced by a
boolean, those names are not stable across a rebuild, it is the only option here that can move
the flown part, and the behavior where two runs meet has to be measured rather than assumed. None
of that argues for never doing it. It argues for doing it with the work that solves edge naming,
and not before.

Alternative 2 is not worth doing on its own: it would move dimensions from one place to another
and still leave a hand-built shape standing in for an operation. If the remaining rounded corners
end up needing sketched profiles anyway it becomes nearly free, but it is a waypoint, not a
destination.

The figures are generated by `tools/draw_flange_chamfer.py`. The two that show the part are
traced from the assembled bulkhead for U = 1.0, bolt end, 3/16 in panel, from a snapshot written
by `chamfer_analysis/measure_chamfer_context.py`; re-run that if the geometry moves.

---

### ~~OQ-ARCH-14 — Do the last two fillets need converting, by the test just adopted?~~ — DECIDED 2026-08-17: convert all four, into one sketch carrying only the fillets active for that variant

**Alternative 1, with an addition that changes what the work is.** All four rounded corners are
converted. Rather than four sketches whose inactive elements are overlaid on variants that do
not use them, the four tangencies live in **one cohesive sketch, which carries only the fillets
active for the parameter set being built**.

That addition is what makes converting all four coherent rather than a list being finished. The
question spent three recommendations arguing whether each feature individually earned a
conversion — and the answer that settles it is not about any one of them. It is that "which
fillets exist here" is itself a property of the variant, currently expressed nowhere: the
greeble-to-web fillet's `max(...)` clamp is that question answered badly, by relocating a body
instead of omitting it. One sketch that contains what is active states it once, in the place a
reader would look.

**What this commits to, stated plainly because it looked like it changed the flown part.**
Omitting an inactive fillet means the 27 variants where the greeble-to-web clamp fires lose that
body. This section originally recorded that cost as *at most 0.042 mm³ per variant, a real
difference from the OpenSCAD reference that `compare_backends` would report*, and accepted it.
**Implementing it measured the figure properly and it is zero** — every one of the 27, to below
1e-6 mm³, on 2026-08-17 (`fillet_scope_analysis/sweep_clamped_gtw.py`).

The 0.042 mm³ was measured at the wrong stage, and the mistake is worth keeping because it is
easy to repeat. A fillet is a *positive*, fused into the flange **before** the bolt hole, the
corner socket and the octant mask are cut. 0.042 mm³ was this fillet's net share of the
**positive** — material no other positive supplied. But the clamp parks the body on the bolt
centerline, *inside the bolt hole*, so the hole cut then removes all of it. The material was
never in the finished part to lose. Measuring by fusing the body into the finished octant
instead makes the opposite error and reads 1.374 mm³, because at that stage the fuse fills the
hole back in. The only measurement that answers the question is building the octant both ways.

So the decision keeps its meaning and loses its cost: the port still agrees with OpenSCAD
everywhere, and the omission removes a body that had no effect on any part that was ever built.

**What decides "active" must not be the clamp wearing a different hat.** Deciding activity from
the same `max` comparison would move the defect rather than remove it. The predicate is a stated
geometric condition and the sketch refusing to solve stays a *check* that the predicate was
right, never the mechanism that produces it — the same branch-guard discipline IP-FC-76
established, applied to existence instead of position.

Implementation settled what that condition is, and it is **not** "whether the web emerges from
the corner block", which is what this section first guessed. `greeble_web.py` builds the web as
a 45° strip along the segment from the corner at the origin to the bolt center, and it stops
there. The flange's inner face is the plane `x = flange_inner_x`. The corner the fillet rounds
is where the two meet, so it exists exactly while that plane falls inside the segment's span —
**the flange face is inboard of the bolt center**. That is the same inequality the `max` tested,
and the honest description says so; what differs is what is done with it. The `max` used it to
pick a different face to measure from, putting the fillet somewhere it is tangent to nothing.
The predicate uses it to decide whether the corner is there.

**One more thing implementation found, which the question never thought to ask.** This section
argued at length about *which* of the four corners a variant has. It did not ask how often the
swept corpus actually visits the configurations where that answer changes, and the answer is:
almost never. Three switches decide what the sketch and the bodies look like —

| switch | what it decides | how close the corpus gets |
| --- | --- | --- |
| `flange_inner_x` vs `bolt_c` | greeble-to-web corner exists; bolt-flange profile is a quad or a triangle | **crosses it**, 27 of 148 variants, and comes within 0.05 mm |
| `bolt_boss_r` vs `flange_thickness / 2` | web-to-bolt fillet is placeable | never within a factor of **4.33** |
| bolt-flange reach vs its offset | bolt-flange fillet is placeable | within 0.45 mm, never crosses |

— so two of the three refusal paths were only ever reached by one synthetic edit, made from
whichever seed a check happened to be handed. Walking them deliberately, with deliberately thin
bolt bosses against thick greeble webs, found a band where the web-to-bolt tangency is
satisfiable and the body still cannot be built, failing several features downstream with a
message naming nothing. IP-FC-73 has the detail and the fix. The general lesson is worth
stating here rather than there: **a swept corpus is not a test suite**, and "every variant we
build works" says nothing about the configurations the sweep does not visit.

Carried to IP-FC-73, which is unblocked and rescoped by this. The evidence that produced the
decision follows.

#### Where this comes from

OQ-ARCH-13 asked whether the flange chamfer belonged in the work that replaces hand-worked-out
positions with stated geometric requirements. It was decided that it does not, on this test:

> a feature whose position has to be **worked out** from where another feature ended up belongs
> in the work; one whose position is simply **measured** from flat faces does not

That test was applied to the chamfer and it excluded it. It has not been applied to the four
rounded corners, because when it was written they were all assumed to be on the other side of
it. Two of them are not.

#### Where the four are

All four are small rounded corners inside the standing flange, repeated once per octant, so
there are thirty-two of them on a bulkhead. One sits where the flange wall turns the outer
corner; the other three are clustered around each bolt. At the scale of the whole part they are
marks rather than shapes, which is why the two details below are needed:

![The four flange fillets located on the bulkhead](img/fillet_scope/bulkhead.svg)

#### What the two already converted had to remove

The bolt-flange fillet's height was `sqrt(max(r_bolt_fillet^2 - dx^2; 0)) + bolt_c`, and the
web-to-bolt fillet's pair came out of the same shape of expression. Both are the leg of a right
triangle whose hypotenuse is the tangency distance: you cannot write the answer down without
solving for it, and both carried a `max(...; 0)` that returned a plausible wrong position
instead of reporting an impossible requirement. That defect is what started this work.

Nothing of that kind is left. After the two conversions, **no clamped square root remains
anywhere in `fillets.py`**. The `sqrt(2)`s that survive are the constant for a 45 degree line,
and the two surviving `max(...)` calls select between two candidate faces rather than clamping a
discriminant.

#### The outer corner fillet: measured, and doing real work

Its center is `flange_inner_x - flange_fillet_radius` and `flange_y - flange_fillet_radius`. The
two faces are at right angles, so each coordinate is one face minus the radius, and there is
nothing to solve:

![The outer corner fillet in the notch between two perpendicular flange faces](img/fillet_scope/outer_corner.svg)

It is also unambiguously a real feature. Fusing it into the flange adds between **0.75 and 163.9
mm³** that no other body supplies, across all 44 measured variants, growing with `U` as a
1.5 mm fillet on a 75 mm part should.

So by the test as written it belongs on the chamfer's side of the line: measured, not solved —
but it is genuinely part of the shape.

#### What the two web fillets are for

Recorded 2026-08-17, because it is not recoverable from the code and the first two attempts at
these figures were drawn without it.

A 45 degree web runs from the bolt boss to the greeble — the corner block the bulkhead's corner
socket is cut into. Where that web meets something at each end, there is a fillet:

- **the web-to-bolt fillet** rounds the **bolt end**, where the web meets the boss around the
  bolt hole;
- **the greeble-to-web fillet** rounds the **greeble end**, where the web runs into the corner
  block.

They are a pair, one per end of the same web, and the names say so. The web-to-bolt fillet is
frequently **hidden entirely by the bolt-flange fillet** — that is what its 7% net share at
U = 3.0 above means, and it is expected rather than a defect: at that flange thickness and
fillet radius the bolt-flange fillet already covers the web's bolt end.

#### The greeble-to-web fillet: the conditional is a clamp, and it fires into the bolt hole

Its x reference is

    gtw_start = max(flange_inner_x; -bolt_offset)

`flange_inner_x` is the corner block's side face, which is the surface the greeble end of the
web runs into — the junction this fillet exists to round. The `max` stops that reference running
*past the start of the web*, since the web begins at the bolt center and there is nothing to
fillet beyond it.

**When the clamp fires, there is little or no junction left.** If the corner block's face lies
outboard of the bolt, the block reaches past the bolt and swallows the web, so the web has no
greeble end to round. Measured across the 44 variants as the volume of web lying outside the
flange base:

| branch | variants | web outside the flange base |
| --- | --- | --- |
| flange face | 35 | 1.84 to 1199.7 mm³ — **always some** |
| bolt center, clamp fires by ≥ 2 mm | 5 | **0.00000** — the block has swallowed all of it |
| bolt center, clamp barely fires (≤ 0.56 mm) | 4 | 0.35 to 1.33 mm³ — a sliver survives |

In the flange-face branch the web emerges everywhere and the fillet lands on the junction. In the
bolt-center branch — 27 of the 148 valid variants — the clamp moves the reference onto the bolt
centerline and the fillet body goes with it, into the bolt hole. Where the clamp fires by a clear
margin there is genuinely nothing left to round. Where it barely fires a sliver of web still
emerges, and the fillet is *still* parked on the bolt centerline rather than on that sliver's
junction — so in neither case does it end up on the surface it exists for.

**This is the defect that started this work, in a different disguise.** A `max(...)` returning a
plausible position rather than reporting that the requirement cannot be met is exactly what the
clamped square roots did in the two fillets already converted. The difference is only that this
one clamps a *reference* rather than a discriminant.

![The greeble-to-web fillet in both branches of its conditional](img/fillet_scope/greeble_buried.svg)

Consistent with there being nothing for it to do, it contributes almost nothing anywhere. Over
the 44 variants measured by `fillet_scope_analysis/sweep_fillet_share.py`:

| variants | net material it contributes to the **positive** |
| --- | --- |
| 33 of 44 variants | **exactly nothing** — the fuse is identical without it |
| the other 11 | at most **0.042 mm³** |

For scale, the outer corner fillet's smallest contribution anywhere is 0.75 mm³, eighteen times
the greeble-to-web fillet's largest.

**That table is about the positive, not about the part, and the difference turned out to matter.**
The fillets are fused before the bolt hole and the corner socket are cut, so a body can be net
new material in the fuse and still be gone from the finished octant. Measured at the finished
stage after the decision was implemented, the clamped body's contribution is **zero in all 27
variants that have it** — it lies inside the bolt hole, which is cut afterwards. See the
correction at the head of this section.

**Two thirds of the body is not a fillet.** The shape in the figure is not a drawing error and
not a porting error — `fillets.py` reproduces the OpenSCAD polygon exactly, and that polygon is
squared off. The arc is correctly tangent to `x = gtw_start` at one end and to the greeble web's
45 degree face at the other, but the straight edges do not stop at the corner where those two
surfaces meet: one runs *past* it down the vertical face, and the other returns horizontally at
`y_corner_fillet_end`. Everything below the web face is inside the web already. Both areas are
exact multiples of the radius squared, with no dependence on `flange_thickness`, so the ratio is
the same in every variant:

| region | section area | share |
| --- | --- | --- |
| the body as built | `r²(1/√2 − 1/4 − π/8)` = 0.06441 `r²` | 100% |
| the fillet proper | `r²(√2 − 1 − π/8)` = 0.02151 `r²` | 33% |
| inside the greeble web | 0.04289 `r²` | 67% |

In a union that is harmless, and it is a reasonable CSG shortcut — the web supplies the excess,
so the extra material costs nothing to carry. It does mean the body cannot be read as a fillet
on its own, and that a conversion would be constraining a shape whose outline is two thirds
scaffolding.

**None of the four are shaped like fillets, and that is worth knowing before reading the
figures.** Each is a covering block clipped by a half-plane and a relief stack, anchored at the
bolt center or the flange corner, whose only functional part is the arc at the far end. Measured
as the share of each body that is material no other body already supplies, at U = 3.0, 1/8 in
panel:

| fillet | own volume, mm³ | net new | share |
| --- | --- | --- | --- |
| outer corner | 178.9 | 69.1 | 39% |
| bolt-flange *(converted)* | 1300.7 | 244.2 | 19% |
| web-to-bolt *(converted)* | 1182.9 | 87.6 | 7% |
| greeble-to-web | 70.9 | 0.0 | 0% |

The two already converted are on the same spectrum as the one in question — the web-to-bolt
fillet's body is 93% overlap. What separates the greeble-to-web fillet is that its share reaches
zero, not that it is the only wedge.

**What is *not* general: being cut away by the bolt hole.** In the two variants drawn above the
body lies inside the bolt hole and is removed wholesale when the hole is cut, leaving nothing at
all in the finished part. That is a small-`U` effect, not the rule — it happens in 5 of the 44,
all at `U ≤ 1.0`, and from `U = 1.5` up the entire body sits inside the part, reaching 168 mm³ at
`U = 4.0`. The corpus-wide fact is the one in the table above: whatever the fillet occupies, the
bodies around it already supply it.

**One bulkhead type was measured, not all five.** Both sides of the conditional are functions of
`U` and the panel only, so `end_bolt` visits every distinct corner geometry; the other four types
would re-measure the same corner. That is an assumption, stated here because it is the one thing
that would widen the result if it were wrong.

#### What it would cost to convert either

Each conversion is roughly what the last one was: a construction sketch, two `Tangent`
constraints, an entry in `check_tangency.py`, and verification that nothing moved. The
verification is the bulk of it.

Against that, the outer corner fillet has **no unsatisfiable configuration at all** — a circle of
any radius is tangent to two perpendicular lines — so one of the four permanent checks, that an
impossible setup is refused, has nothing to assert for it. A check table entry that silently
asserts less than it appears to is its own small liability.

And the greeble-to-web fillet needs a sketch that can express a reference which is sometimes not
there at all, and **refuse** rather than substitute one — which is more than either completed
conversion had to do, and is also the point of doing it.

#### Alternatives

1. **Convert both, finishing the list of four.**
   *Benefits:* all four rounded corners state their relationship; consistent to read.
   *Drawbacks:* the outer corner fillet has nothing to gain — no discriminant, no branch, no
   configuration that can fail — so this spends the expensive part, the verification, on a
   feature the adopted test already excludes.
   *Prerequisites:* establish how a sketch refuses when the web has no greeble end.

2. **Convert neither, and close the item at two of four.**
   *Benefits:* consistent with the decision made about the chamfer; no further work.
   *Drawbacks:* leaves a clamp that silently produces a meaningless body in 27 of 148 variants —
   the same class of defect this work exists to remove, left in place because it is small.
   *Prerequisites:* none.

3. **Convert the greeble-to-web fillet only, and have it refuse where the junction does not
   exist.** Replace `max(flange_inner_x; -bolt_offset)` with a tangency the sketch either
   satisfies or reports as unsatisfiable, and omit the body in the variants where the corner
   block has swallowed the web.
   *Benefits:* removes a clamp that returns a plausible wrong answer, which is the defect the
   whole item is about; states the junction the fillet is actually for; the 27 variants where it
   fires stop carrying a body that rounds nothing. Cheap to verify — the body contributes at
   most 0.042 mm³, so omitting it moves almost nothing.
   *Drawbacks:* three of four converted is a harder rule to state than all or none; changes the
   part, slightly, in the variants where the body is dropped; needs a refusal path the two
   completed conversions did not.
   *Prerequisites:* agreement that omitting the fillet where the web has no greeble end is
   correct rather than a regression against the OpenSCAD reference — it *will* show up as a
   difference in `compare_backends`.

4. **Convert neither, and raise the clamp as a design question instead.**
   Close this item at two of four, and ask separately, in the bulkhead design document, what the
   greeble-to-web fillet should do when there is no greeble end to fillet.
   *Benefits:* puts the question where it belongs if the answer is a change to the part rather
   than to how the part is expressed.
   *Drawbacks:* opens a second question rather than closing one, and the answer feeds straight
   back into this one; the mechanism that implements "refuse" is the conversion, so splitting
   them separates a question from its own remedy.
   *Prerequisites:* none. The behavior is inherited, not introduced —
   `fuselage_bulkhead_geometry.scad` computes the same `max` and builds the same polygon.

#### Recommendation *(superseded by the decision above — retained because it changed three times)*

The recommendation moved three times, and the reason each time was evidence rather than
argument. It first read *convert the greeble-to-web fillet only*, on the strength of its
conditional reference. Then *convert neither*, when measurement showed the body contributes
nothing anywhere. Then back to *the greeble-to-web fillet only*, once the recorded intent showed
the conditional is a clamp rather than a relationship. None of the three considered that "which
fillets are active" could be expressed directly, which is what the decision does.

The one argument in them that survives is against converting the outer corner fillet on its own
merits: its position is two perpendicular faces each minus a radius, with no discriminant, no
branch and no configuration that can fail, so a `Tangent` constraint states something already
obvious and one of the four permanent checks — that an impossible setup is refused — has nothing
to assert for it. It is converted anyway, because a single sketch that holds three of the four
and omits the fourth would need a reason a reader could not find in the geometry.

#### What the decision leaves to the implementation

- **A single sketch fails as a unit.** `solve()` and `FullyConstrained` are per sketch, so four
  tangency sub-systems in one object means one unsatisfiable sub-system reports as one failed
  sketch, losing which fillet caused it. `check_tangency.py` and the generator's own guard must
  identify the sub-system, or the refusal check gets weaker exactly as the number of things it
  covers goes up.
- **Reference-dimension names share one namespace.** `Constraints.<name>` is flat within a
  sketch. The existing prefixes (`bbf_`, `wtb_`) already keep them apart and must stay.
- **The two completed conversions are restructured, not left beside the new one.** `BffTangency`
  and `WtbTangency` merge into the cohesive sketch; both are bit-identical today and must stay
  so, which is the cheapest possible regression test for the merge itself.

The figures are generated by `tools/draw_fillet_scope.py`, traced from the assembled bulkhead by
`fillet_scope_analysis/measure_fillet_context.py` for U = 3.0 and U = 0.75, bolt end, 1/8 in
panel — one variant of each branch, same panel, so only the size flips the branch.

**The variants are chosen for separation, not convenience.** The first pair drawn here were
U = 0.75 and U = 0.5 at a 0 mm panel, where `flange_inner_x` is −5.95 against a bolt center at
−6.00. At 0.05 mm apart the two candidate references cannot be told from one another on the
page, and at that size the fillet vanishes into the bolt hole as well, so the figure showed a
degenerate case and read as an error in the geometry rather than as the geometry. These two
separate by 8.80 mm and 2.30 mm.

Two further conventions, both learned by getting them wrong:

- **The plan view shows each fillet intersected with the finished octant**, not the body as
  built. A fillet is a positive, fused before the bolt hole and the corner socket are cut, so
  drawing the body itself paints over holes the part has and reads as a placement error. The
  detail views show the body as built, because what the body overlaps is the question.
- **All four fillets carry their own color.** Drawn in one color the two already converted
  read as a single pinwheel around the bolt, and there is no way to check either against where
  it is supposed to be.

The volumes come from `fillet_scope_analysis/sweep_fillet_share.py`. Re-run both if the geometry
moves.

---

### ~~OQ-ARCH-15 — What is the reference corpus a reference *to*, and what keeps it current?~~ — DECIDED 2026-08-18: freeze the baseline, reason about the deltas

**The problem.** `verify_sweep_change.py` compares a freshly built sample against
`variant_output_baseline` (rendered 2026-08-02) and, run at HEAD on 2026-08-18 with no local
changes, reported three of five sampled parts differing. All three were investigated and all
three are intentional:

| Part | Difference | Bisected to | Cause |
| --- | --- | --- | --- |
| `corner_FX_0.5` | bbox −6.15 → −6.25 mm in *x* and *y*; volume +0.021%; 8 fewer triangles | `299633c` 2026-08-14 | `- panel_tolerance` removed from the panel rectangular extension so it reaches `flat_x`; the tolerance had been leaking into a mating face, leaving the corner cut off and the bulkhead standing over it (OQ-DES-C5, OQ-DES-B13) |
| `bulkhead_end_anchor` | volume −0.014%; 96 fewer triangles | `299633c` 2026-08-14 | the bulkhead eps notch fix the commit is named for |
| `boom_bulkhead_center_single` | 2,208 fewer triangles; volume differs by 9×10⁻⁴ mm³ on 1092 mm³, or 8×10⁻⁷ relative | `e11d04a` 2026-08-10 | fillet refactor; **no geometry change at all**, only retessellation — reported by the criterion rather than by the corpus, see [OQ-ARCH-16](#open-questions) |

The corner was bisected by extracting `src/Fuselage/scad/` at each candidate commit read-only
and rendering the same generated call against it. `9bc386b` reproduces the baseline exactly —
1202.6214 mm³, 17,324 triangles, bbox −6.15 — and `299633c`, the next commit to touch that
file, gives 1202.8714 mm³, 17,316 triangles, bbox −6.25.

**Decision: the baseline does not move.** `variant_output_baseline` stays the authority for
the whole of the port, and differences against it are *reasoned about* rather than absorbed.

**The reason is cumulative drift, and it rules out re-baselining outright.** Every alternative
that re-establishes the reference as work proceeds — regenerating the trees, or deriving the
reference on demand from the previous commit — compares each change against the state
immediately before it. Every individual step then passes, because every individual step is
small, while the total wanders arbitrarily far from the parts that were designed and flown.
The drift is undetectable precisely because no single comparison ever sees it. A frozen
reference is the only arrangement in which the accumulated distance from the original is
visible at all, and it is the accumulated distance that matters: the question is never "did
this commit move geometry" but "how far is the part now from the one that was reviewed".

This overrides the recommendation the question carried, which was to derive the reference on
demand from a named commit. That recommendation optimized for the comparison always being
runnable and was wrong about what the comparison is *for*.

**The baseline's known errors do not disqualify it.** It carries defects that have since been
corrected — the corner's `panel_tolerance` leak above is one — and that is not a reason to
replace it. A reference does not have to be right to be useful; it has to be *fixed*, so that
every departure from it is a departure someone chose. The corrections are recorded as
departures rather than folded silently into a new baseline.

**What this requires, and it is the real cost.** Differences against the baseline must be
enumerated and justified, not discovered one at a time by whoever next runs the tool. That
means:

- **A complete inventory, not a sample.** The three differences above come from a five-part
  sample. There are 576 parts, and nothing yet says how many of them differ or by how much.
  The inventory needs one full comparison run against the baseline.
- **A ledger of accepted departures**, each carrying the part, the measured difference, the
  commit that caused it, and why it is correct. Anything not in the ledger is a failure.
- **The comparison tools reading that ledger**, so a run is green when the only differences
  are accepted ones and red the moment a new one appears. Without this the tool stays unusable
  as a gate, which is the state that raised this question.

**When the baseline is retired.** Once the FreeCAD implementation is complete and the
`PartDesign::` end state is reached ([OQ-ARCH-11](#open-questions)), the full sweep gets
reviewed in detail — part by part, against the ledger — and only then is
`variant_output_baseline` declared no longer the authority. Retirement is a reviewed event with
a person signing off on the accumulated difference, not a side effect of a convenient moment.

**One thing to fix regardless.** `variant_output_baseline` is not a render of this repository:
its stored `.stl.scad` files name their library under the pre-migration
`Archive\Alex\Designs\modular_sUAS\Fuselage\` tree, and no tree in the corpus records the
commit that produced it. Freezing a reference makes recording its provenance more important
rather than less, since the ledger's entries are meaningless without knowing what they are
departures *from*. The manifest proposed as alternative 2 is therefore still wanted — not to
gate on drift, which is now the ledger's job, but to state what the frozen baseline is.

*Recorded as IP-FC-80 (inventory and ledger) and IP-FC-81 (baseline manifest).*

### ~~OQ-ARCH-16 — Is `same_geometry` the right test for "the same solid"?~~ — DECIDED 2026-08-18: fix the tolerances, and add a sampled surface distance

**The problem.** Every geometric comparison routes through `mesh_stats.same_geometry`, which
requires exact triangle-count equality, an **absolute** 1e-6 mm³ volume tolerance, and exact
float equality of the bounding box. Three criteria, three separate defects: the triangle count
rejects retessellation that moves no geometry — measured on 2026-08-18, the boom bulkhead at
22,680 against 20,472 triangles with volumes agreeing to 8×10⁻⁷ relative; the volume tolerance
does not scale with `U`, contradicting [OQ-ARCH-12](#open-questions) and amounting to bitwise
equality on a 1092 mm³ part; and the bounding box admits no tolerance at all on numbers from a
kernel that is not bit-reproducible.

**Decision: take both alternative 1 and alternative 3.** They answer different halves of the
question and neither is sufficient alone.

**Alternative 1 — bring the tolerances in line with the rest of the project.** Volume compared
relatively, bounding box compared against the `U`-scaled tolerance OQ-ARCH-12 already defines,
triangle count reported but not disqualifying. The constants exist already in
`compare_backends.bbox_tol()` and `check_unread_rows.VOLUME_TOL`; this finishes a decision
rather than making a new one, and it stops the tool rejecting the exact class of change —
fillet, chamfer and mask refactors — that it exists to bless.

**Alternative 3 — add a surface distance, computed on a sampled subset.** Volume and bounding
box are proxies: they can agree while a surface has moved, which is the hole alternative 1
leaves open. A distance in millimeters is the only measure on this list that can be compared
against what a printer can hold. **It is not computed over every vertex.** A sample is taken
from each mesh and each sampled point measured against the other surface, reporting the
maximum and the mean. The cost is then set by the sample size rather than by the mesh, which
matters directly here: cowls carry around 90,000 triangles and the full-sweep corpus is 576
parts.

**Why both.** Alternative 1 makes the existing criteria honest but leaves them proxies.
Alternative 3 measures the real quantity but is the expensive one, and on its own it discards
the cheap checks that catch gross errors instantly. Run together, the cheap criteria screen and
the distance adjudicates: volume and bounding box within their scaled tolerances and no sampled
point further than the distance threshold means the same solid; anything else is reported with
the number that failed.

**Left to implementation, then measured 2026-08-18.** How points are drawn was calibrated
against **0.05 mm, the smallest linear dimension this project cares about**, and the
measurement overturned the first implementation's default rather than confirming it.

*Uniform area sampling cannot find a small feature, by three to four orders of magnitude.* A
0.05 × 0.05 mm patch is 2.5×10⁻³ mm² against these measured surface areas, and a 95% chance
of landing on it needs:

| Part | Surface area | Samples for a 95% hit on a 0.05 mm patch |
| --- | --- | --- |
| corner, U = 0.5 | 1,174 mm² | 1.4 million |
| bulkhead end anchor, U = 0.5 | 3,354 mm² | 4.0 million |
| tail cowl, U = 0.5 | 13,541 mm² | 16.2 million |
| corner, U = 4.0 | 47,551 mm² | 57.0 million |

Uniform sampling scales with the **area a change affects, not its magnitude**. That is why it
caught the corner's `panel_tolerance` fix at 400 samples — that moved an entire face — and
why it would sail past an isolated feature. An elongated 0.05 × 20 mm slot is easier at
3,500–142,000, but the worst case is the one that governs.

*Vertices are where features are.* Tessellation places vertices on feature boundaries, so a
displaced 0.05 mm feature has vertices on it, and sampling them spends the budget where detail
lives instead of spreading it evenly over large flat faces. The sampler is therefore
vertex-biased, with a minority of area samples retained to cover the one case vertices miss:
two meshes whose vertices coincide but whose triangle interiors do not.

*What a subset buys is exactly its coverage, and the tool now says so.* Choosing k of V
vertices without replacement includes any particular one with probability k/V — arithmetic,
not an estimate. A U = 0.5 corner has 8,664 unique vertices, so a 2,000-point sample covers
17% and has a 17% chance of catching a single displaced vertex. Measured: with one vertex
displaced by 0.05 mm, both a 2,000-point area sample and a 2,000-point vertex subset **missed
it**, which is what 17% predicts. Full vertex coverage on the same mesh **found it**, at 67×
the threshold. The tool reports coverage alongside the distance and states that a clean result
means nothing was *found* to have moved, and offers `--all-vertices` to make the probability 1
for a vertex displacement.

*One number in that result is worth keeping, because it will otherwise be misread.* The 0.05 mm
displacement registered as **0.0337 mm** of surface distance, not 0.05. Surface distance is the
perpendicular distance to the nearest point of the other surface, so any part of a displacement
that runs *along* the surface does not appear in it — the vertex slid as much as it lifted. A
surface distance is therefore a lower bound on the displacement in two independent senses: the
sample may miss the feature, and even when it hits, a tangential component reads as nothing.
A threshold set from a physical dimension should allow for that gap rather than assume the two
numbers are the same quantity.

**The threshold was not changed and should not be.** At `5e-4 · max(u, 1)` mm it sits two
orders of magnitude below the 0.05 mm that matters, which is the right relationship: it
measures engine agreement rather than a fit, in the same sense `BBOX_TOL` does under
[OQ-ARCH-12](#open-questions). Printed clearances on this airframe are around 0.1 mm; a
verification tolerance is not one of them.

**What follows for the review this baseline is frozen for.** Screening runs use the subset and
report their coverage. The `PartDesign::` end-state sign-off in [OQ-ARCH-15](#open-questions)
is the one that has to be conclusive, and at ~1 minute per part for full vertex coverage it is
a run to schedule rather than one to take casually across 576 parts.

The retirement argument raised against alternative 3 — that the OpenSCAD mesh path ends with
IP-FC-34 — does not survive [OQ-ARCH-15](#open-questions)'s decision. A baseline frozen until
the `PartDesign::` end state means mesh comparison against `variant_output_baseline` is needed
for the whole remaining life of the port, and it is the measure that review will rest on.

*Recorded as IP-FC-82 (tolerances) and IP-FC-83 (sampled surface distance).*

## References

- [roadmap.md](../roadmap.md) — Phase 3 objectives and exit criteria
- [corner.md](../design/corner.md) — corner design authority; OQ-DES-C3 on the coupling
- [bulkhead.md](../design/bulkhead.md) — bulkhead design authority; the greeble as a
  positive post formed by cutting with `corner_end()`
- [geometry_refactor.md](../implementation/geometry_refactor.md) — Phase 2 plan; OQ-GEO-1
  on why the parameter groups were built in Python
- [general.md](../guidelines/general.md) — units standard and the OpenSCAD exemption
- [python.md](../guidelines/python.md) — dataclass conventions the ported code follows
- [fuselage_folder_summary.md](../../src/Fuselage/docs/fuselage_folder_summary.md) — how
  the current sweep is driven
