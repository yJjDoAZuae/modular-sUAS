# FreeCAD Migration — Implementation Plan

**Scope:** Roadmap Phases 3–7 — porting the generators to FreeCAD and the capabilities that
port enables. Plan abbreviation `FC`.

**Design authority:**
[doc/architecture/freecad_migration.md](../architecture/freecad_migration.md) for the system
shape and the nine use cases; [corner.md](../design/corner.md),
[bulkhead.md](../design/bulkhead.md) and [cowl.md](../design/cowl.md) for the geometry being
ported. All three parts now have one — `cowl.md` was written as IP-FC-7, immediately
unblocked IP-FC-16, and raised seven open questions about the cowl. **Five of those were
answered on 2026-08-09**, closing the last blocking cowl question (OQ-DES-CW6) and adding
IP-FC-42, IP-FC-43 and IP-FC-44.

**Last updated:** 2026-08-09

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
| IP-FC-9 | done | Port the bulkhead, forming the greeble by cutting with the corner's end **section description re-evaluated at greeble tolerance 0** — never with the corner's built shape, which carries the fit clearance. **The whole octant is done and verified** — sixteen modules, then assembled as `bulkhead_section` against the real module at +0.00011% (§IP-FC-9 progress), which is what binds the two inline-geometry transcriptions. The assembly caught a reading error no isolated reference could: the plate and longeron flange sit inside `if (is_cowling)`. The `octant_to_full` tiling is done too -- `bulkhead_full.py` at +0.00011%, and the corner checked at the **swept** values for the first time at +0.00041% | IP-FC-5 | [bulkhead.md §The greeble is a positive post](../design/bulkhead.md) |
| IP-FC-10 | done | `--backend freecad` renders the corner and the bulkhead through `freecad/build_part.py`, one `freecadcmd` per part. The queue, worker budget, atomic write, serial-retry recovery and previews were **not modified** -- `solid_render` split into `render_definition` plus two four-line backends. Verified against the sweep's own OpenSCAD output at +0.00035% (bulkhead) and +0.00121% (corner), bounding boxes identical. **That verification was one part per kind, and two defects survived it** — IP-FC-46 and IP-FC-47, both found later by enumerating the swept space | IP-FC-1, IP-FC-9 | [freecad_migration.md §What must be preserved](../architecture/freecad_migration.md) |
| IP-FC-11 | done | Geometry-code version added to `--resume`'s staleness key, **on both backends**. Found while checking the FreeCAD side: the generated `.stl.scad` is a `use <>` line and a call, so the OpenSCAD path had the same blind spot since `--resume` was written — an edit to `fuselage_bulkhead_geometry.scad` left every definition byte-identical. `tools/geometry_version.py` walks the `use`/`include` closure of the generated file and the import closure of the builder, and stamps a digest into the definition both backends already compare. Verified in both directions on three backend/kind pairs | IP-FC-10 | [freecad_migration.md §What must be preserved](../architecture/freecad_migration.md) |
| IP-FC-12 | in progress | **Unblocked 2026-08-10** by IP-FC-4 and IP-FC-10, re-blocked the same day on [OQ-DES-B11](../design/bulkhead.md), and unblocked again when that was decided: **split by intent** — true fillets on the key, the morphological chain for the region-wide remainder. The key's direct construction landed in the OpenSCAD path first and is verified across all 24 distinct swept key geometries at a worst 0.00522% symmetric difference, with `boom_key_validity_check()` enforcing the domain. [`boom_key.py`](../../src/Fuselage/freecad/boom_key.py) then ports it — the first module built **in the plane**, which established that coplanar unions must be built from cuts rather than fuses or every offset downstream is wrong by hundreds of percent (§IP-FC-12 progress). Port the boom bulkhead and the cowls. Preserve the OML transform algebra verbatim, including `offset_x_m` preceding the scale. Note what IP-FC-46 through IP-FC-49 cost the two kinds already ported: run `compare_backends.py` against each new kind across the swept space, not at one point. **The boom bulkhead is built almost entirely from 2D offsets** — `fillet_inner`, `fillet_outer` and plain `offset(r=±)` strokes — and three of its four `fillet_inner` uses wrap a whole compound region rather than a named corner, so the route is not the one the frame bulkhead's four true fillets settled. **Done pending that answer:** [`ref_boom_bulkhead.scad`](../../src/Fuselage/freecad/ref_boom_bulkhead.scad) isolates the part and twelve sub-shapes at swept parameters taken from `derived_parameters()` rather than typed, and the swept space is enumerated at 132 valid variants, none of them on the offset degeneracy (§IP-FC-12 progress). **The part itself is ported and agrees to 0.00039%** as of 2026-08-11 — [`boom_bulkhead.py`](../../src/Fuselage/freecad/boom_bulkhead.py), one profile and one `Part::Extrusion`. `boom_make_lower_web` followed the same day, so all three swept boom types are covered — `center_single` is checked against its own reference at 0.00040%. **The harness wiring landed 2026-08-11**: the two bulkhead sweeps are now described by one `BULKHEAD_FAMILIES` table that `render_variant.py`, `export_parameters.py` and `compare_backends.py` all read, the export carries a named `boom_parameters` table, and the kind is swept and compared like any other (§IP-FC-12 progress). Sweeping it immediately found two defects the two-point check could not: IP-FC-52, a +0.167% error at one variant in eight, and IP-FC-54, a null offset that stopped three variants building. and IP-FC-57, two more null offsets that came down to how a shape had been built rather than what it was. **All 132 valid boom variants now build and agree with OpenSCAD — worst deviation 0.00110% against a 0.010% tolerance, across U = 0.5 to 4.0, all nine panels and all three boom types, every bounding box exact.** What remains on this item is the cowls | IP-FC-10, IP-FC-4, OQ-DES-B11 | [bulkhead.md §OQ-DES-B11](../design/bulkhead.md), [cowl.md §2](../design/cowl.md), [cowl.md §6.3](../design/cowl.md) |
| IP-FC-13 | in progress | [`compare_backends.py`](../../src/Fuselage/tools/compare_backends.py) renders the same variants through both engines and compares measured geometry, with the two tiers below and a guard that refuses to count a part FreeCAD never built. Usable now for the corner, the frame bulkhead and — since 2026-08-14 — the boom bulkhead, and `--kinds` sweeps one kind exhaustively without paying for the others. **Sampling is not enough and this item now has the evidence**: eight boom bulkheads spread across the range found IP-FC-52 at one of them, 0.167% against 0.0006% for its seven neighbours, and the exhaustive run then found IP-FC-54 and IP-FC-57 at five variants the sample never visited — four of which did not build at all, so no tolerance would have caught them. The boom bulkhead is the first kind swept exhaustively: **132 of 132, worst 0.00110%**. Whole-corpus coverage is still blocked on IP-FC-12, which needs the cowls. Full-sweep equivalence against the OpenSCAD corpus by volume, bounding box and hole positions — **not** triangle count. **Two tiers, per OQ-DES-B9:** parts whose geometry is exactly reproducible (the corner) stay strict; parts carrying real fillets need a stated deviation tolerance and a comparison that measures deviation rather than volume equality. Interface dimensions are strict in both tiers — no interface is set by a fillet. **The boom bulkhead lands in the strict tier**, settled by [OQ-DES-B11](../design/bulkhead.md): its one true-fillet feature is the key, and replacing the key's morphological rounding moved the whole part by 0.00008% — two orders inside the strict tolerance — so the split does not cost a tier | IP-FC-12 | [freecad_migration.md §Equivalence between toolchains](../architecture/freecad_migration.md), [bulkhead.md §OQ-DES-B9](../design/bulkhead.md), [bulkhead.md §OQ-DES-B11](../design/bulkhead.md) |
| IP-FC-34 | blocked (IP-FC-13) | Retire the OpenSCAD implementation. Re-check the three design documents against the code **before** removing it, then delete `scad/` and the OpenSCAD driver path — history retains it | IP-FC-13 | [freecad_migration.md §OQ-ARCH-4](../architecture/freecad_migration.md) |
| IP-FC-14 | blocked (IP-FC-13) | UC-2 — export `.FCStd` per part from the sweep | IP-FC-13 | [freecad_migration.md §Use cases](../architecture/freecad_migration.md) |
| IP-FC-15 | blocked (IP-FC-13) | UC-3 — export `.step` per part from the sweep | IP-FC-13 | [freecad_migration.md §Use cases](../architecture/freecad_migration.md) |
| IP-FC-16 | todo | Write the cowl interior-surface algorithm document. Method decided: per-layer 2D inset, **curvature-adaptive** section spacing with a deviation-based termination test, surface **fit** with G1 tangency (threshold) and G2 curvature (objective), bidirectional curvature, **never ruled**. The open part is the near-horizontal material rule | IP-FC-7 | [freecad_migration.md §OQ-ARCH-5](../architecture/freecad_migration.md), [cowl.md §6.2](../design/cowl.md) |
| IP-FC-28 | todo | OQ-DES-CW2 resolved 2026-08-09: `cone_angle` is the **overhang angle measured from the print bed**, 35°, and both call sites are correct — the complementary spellings meet the same face because the radius lies in the bed plane and the axis is normal to it. What is left: rename to `overhang_angle_from_bed` and move it into `PrinterSettings`, since it is material-dependent process, not cowl shape. Per-feature overrides are open — the achievable angle depends on span, surface type and whether the face mates | IP-FC-12, IP-FC-42 | [cowl.md §OQ-DES-CW2](../design/cowl.md) |
| IP-FC-30 | done | Establish each station's active section type. Resolved from the XML: read `<Type>` element TEXT, not the ParmContainer name, which is stale on 10 of 16 stations | — | [cowl.md §1.2](../design/cowl.md) |
| IP-FC-44 | done | OQ-DES-CW1 resolved 2026-08-09 (alternative 1): the three metre-valued OML fields renamed to `oml_length_m`, `oml_offset_x_m` and `oml_scale_m_per_mm` across the SCAD signatures, `OmlParameters` and both cowl JSON files. `_m_per_mm` not `_m_per_unit` — "unit" already means `U`/`unit_width`/`unit_length` here. Verified geometry-identical by `verify_sweep_change.py`, which is the check this case needs: the signatures move, so `scad_snapshot.py` reports DIFF by construction | — | [cowl.md §OQ-DES-CW1](../design/cowl.md) |
| IP-FC-31 | done | OQ-DES-CW7 addressed: `oml_export.py --check` verifies the exported OML against a SHA-256 of the committed `.vsp3`, recorded in `oml/oml_provenance.json`. Exits non-zero when stale; needs no OpenVSP install, so it runs anywhere | — | [cowl.md §OQ-DES-CW7](../design/cowl.md) |
| IP-FC-29 | todo | OQ-DES-CW3 resolved 2026-08-09: `buttress.thickness` is the **cut** that produces the rib through slicing; the printed rib is `2·w·n_perimeters + t_cut`. Unscaled treatment confirmed correct. What is left here is the rename to `buttress_cut_thickness` — JSON schema, `ButtressSet`, eight SCAD signatures — deferred to the port so it is not done twice | IP-FC-12 | [cowl.md §OQ-DES-CW3](../design/cowl.md) |
| IP-FC-42 | todo | Adopt `n_perimeters` into `PrinterSettings`. The cowl rib's thickness depends on it and it exists only in a slicer profile outside the repository — the same class of gap OQ-DES-CW7 closed for the OML. Prerequisite of any modelled rib | — | [cowl.md §OQ-DES-CW6](../design/cowl.md) |
| IP-FC-43 | todo | Settle the buttress cut's factor of two: every call site extrudes `height = 2*buttress_thickness`, so the cut is 0.1 mm where the parameter says 0.05. Half-thickness-per-side convention or error — a question of intent, not measurable. **The port reproduces the doubling until it is settled** | IP-FC-29 | [cowl.md §OQ-DES-CW3](../design/cowl.md) |
| IP-FC-45 | done | The kind→module table was briefly in two places — `build_part.KINDS` and the driver's copy for the IP-FC-11 digest — because `build_part.py` imports `FreeCAD` at module scope and cannot be read from the project virtualenv. `freecad/part_kinds.py` now states it once and imports nothing that imports FreeCAD; `build_part.py` imports it normally, `freecad_render.py` loads it by file path rather than putting `freecad/` on `sys.path`, where `parameters.py` would shadow. A copy that names the wrong module would give the digest of the wrong closure — a staleness key that looks like it works and tracks the wrong files | IP-FC-11 | — |
| IP-FC-46 | done | **Degenerate tools at zero-size parameters.** The `0mm` panel row is the no-panel variant — thickness, tolerance and overlap all zero — and it is valid by `bulkhead_validity_check`. OpenSCAD renders the zero-extent slot as the empty set and the difference is a no-op; `Part::Box` yields a **null shape** and nulls the whole cut chain, surfacing six features away as `BRepCheck_Analyzer::Init() - NULL shape`. `corner_tree._degenerate()` now omits the feature, which is what "no panel" means. Found by IP-FC-11's end-to-end test, which rendered the sweep's *first valid combination* rather than the one part IP-FC-10 was measured on | IP-FC-10 | [freecad_migration.md §IP-FC-46](../implementation/freecad_migration.md) |
| IP-FC-47 | done | **The FreeCAD backend dropped the bulkhead type flags.** `bulkhead_render`'s OpenSCAD call passes `is_interconnect` and `is_cowling`; the FreeCAD branch passed neither, and `bulkhead_full.emit()` takes neither — only the end type is ported. So `--backend freecad` rendered all five swept types as end bulkheads: 60 of 148 wrong, under the right filename, with a plausible volume. `_backend_for(kind, supported=)` now routes the unported types to OpenSCAD, the same fallback every unported kind already gets, and `_variant_note` carries `type_name` so two types cannot produce identical definition files | IP-FC-10 | [freecad_migration.md §IP-FC-47](../implementation/freecad_migration.md) |
| IP-FC-48 | done | **The seed did not supply everything the expression rows read, and nothing checked.** `seeded()` replaces literal rows only, so a row the port states as a relationship — `corner_radius` = `=U * 10`, `longeron_radius` = `=U * 2`, `unit_length` = `=U * FX * 100` — keeps its expression and evaluates from whatever the sheet holds. Neither `U` (bulkhead) nor `FX` (corner) was in the seed, so both stayed at their literal 1.0: **every FreeCAD corner was built at FX=1.0 and every FreeCAD bulkhead at U=1.0**, with the authority's correct values sitting unused in the parameter file. Exact at U=1/FX=1 — the one part IP-FC-10 measured — and wrong by up to 115% elsewhere. Both are now seeded, and `build_part.build()` runs `check_seed` on every build instead of leaving it to a check script nobody ran | IP-FC-10 | [freecad_migration.md §IP-FC-48](../implementation/freecad_migration.md) |
| IP-FC-49 | done | The bulkhead could not be tiled at U ≥ 2.5: the octant and its mirror were each valid and only their **fuse** was not. Cause was the `eps` overlap that makes the octant interpenetrate its mirror — 0.01 mm absolute, 4e-5 of a 250 mm part, under what OCCT's booleans resolve. **The overlap exists for OpenSCAD's union and OCCT does not need it at all**: a solid fused with its own mirror about the touching plane is valid and volume-exact at 10, 100, 250 and 400 mm with no overlap. Now `mask_eps = 0`, separate from `eps` so cut overshoot is untouched. Every U from 0.5 to 4.0 tiles into one valid solid, the part is dimensionally unchanged, and `full == 8 × octant` becomes exact — a stronger tiling check than the one it replaces | IP-FC-48 | [freecad_migration.md §IP-FC-49](../implementation/freecad_migration.md) |
| IP-FC-50 | done | **Audited every `eps` in the port and measured what each one is for.** IP-FC-49 had zeroed the *union overlap*; this asks the same of the other two jobs the constant was doing. [`spike_eps.py`](../../src/Fuselage/freecad/spike_eps.py) measures flush-versus-padded cuts and abutting-versus-overlapped fuses at 10, 100, 250 and 400 mm. **Cut overshoot buys nothing** — a tool cap coplanar with the face it exits through is exact to machine precision and yields the same or *fewer* faces — so the ±eps pad on every section cut tool in `corner_tree._section` is gone, verified inert by the four section volumes and the 52-face count coming back byte-identical. `boom_oml` was still carrying the old mask overlap and now uses `mask_eps` like `bulkhead_cuts`. **The exception is tangency**: safe when incidental, but where a boolean *depends* on a tangent face OCCT under-removes — the greeble wedge's flanks lose 0.0199 mm³ without their eps, so that one stays. Forcing all corner `eps` to zero moves the assembled part by −9e-6% and drops 4 faces, but that near-cancellation hides two errors of opposite sign, which is why the audit is per-site rather than global. **Found OQ-DES-B12 on the way** | IP-FC-49 | [freecad_migration.md §IP-FC-50](../implementation/freecad_migration.md), [bulkhead.md §OQ-DES-B12](../design/bulkhead.md) |
| IP-FC-51 | done | **The OQ-DES-B12 fix, decided and implemented 2026-08-11 as alternative 1.** `corner_end` now takes an explicit `overshoot` argument, defaulting to 0, that moves the extrusion and the greeble bore and sizes nothing; `bulkhead_section` calls it with the true thickness and an overshoot of `eps` instead of inflating the thickness. **The overshoot had to reach the bore, not just the extrusion** — the bore's z extent is dimensioned from the same argument, so extending only the extrusion would have silently un-overshot the post. The z extent of the tool is unchanged and only the rib moved: **2.00667 → 2.000, equal to the corner post's**, now asserted rather than printed. Regenerated: greeble tool 557.746362 → 557.804925, octant 865.3140969 → 865.2850690, part 6922.5048968 → 6922.2726731. Two checks say the fix landed the same way on both kernels: `ref_end` — the corner's own end section — is **bit-identical** across the change, and OpenSCAD and FreeCAD agree on the *size* of the octant's change (−0.0290279 against −0.0290299) to 2e-6 mm³. The part lost exactly 8× the octant's change, so the tiling is untouched. Found on the way: five scripts read freecadcmd's `--pass` token as their first argument, now filtered once in `corner_common.script_args()` | IP-FC-50, OQ-DES-B12 | [bulkhead.md §OQ-DES-B12](../design/bulkhead.md) |
| IP-FC-52 | done | **An outward `Part::Offset2D` does not merge faces that grow into overlap, and the overlap is then counted twice.** FreeCAD offsets each face of a multi-face source independently — correct while the faces stay apart, which is why `plane2d.fragmented()` deliberately allows several faces — but a *positive* offset can grow two of them into each other, and the result keeps both. Found by IP-FC-13 at U=0.75 / 1/8 in panel / `dual`, the one sampled boom bulkhead where the inner web's erosion pinches into pieces closer together than twice the fillet radius: `offset(−r)` split it into four faces, `offset(+2r)` regrew them overlapping at 467.4780 mm² against OpenSCAD's 458.4831, the inner web came out 1.56% small, and the finished part came out **+0.167% — sixteen times the tolerance**, while the other seven sampled variants agreed to 0.0006%. Fixed by merging the dilation through the same `R − (R − X)` complement `plane2d.union` already uses, at both fillet functions' dilation steps — the two places an offset is applied to a shape the same function just produced. An inward offset cannot create an overlap, so only the outward direction needs it. The failing variant went **+0.16731% → +0.00086%**, and every previously verified reference number is bit-identical, the merge being a no-op on a single face. `compare_backends.py` gained `--kinds` so a newly ported kind can be swept exhaustively without paying for the ones already covered | IP-FC-12, IP-FC-13 | |
| IP-FC-53 | done | **A seed was only checked in one direction.** `check_seed` walks the values the *authority supplied* and confirms the sheet reproduces each, so a literal row the parameter file failed to supply was never looked at — and a literal row is configuration by the port's own rule (`corner_common.is_literal`), so the part was built with the module's own reference value silently substituted for the variant's. `check_unseeded` is the other half: every literal row must be supplied or be named in `corner_common.UNSEEDED` with a reason. Run from `build_sheet`, so it covers every route to a seeded sheet rather than just `build_part.py`, and skipped when there is no seed at all, that being the reference check where the literals are the measurement. Verified by removing two rows from a parameter file: refused by name, no part written | IP-FC-41, IP-FC-48 | |
| IP-FC-54 | done | **`Part::Offset2D` returns a null shape on the frame web's erosion, and takes the whole part with it.** Found by the IP-FC-12 sweep: three of 132 boom bulkheads failed to build at U=0.75 with a 3 mm panel. The source erodes the OML *with its bores already cut*, and there the longeron bore — which is concentric with the corner arc — grows past the shrinking arc while the panel notch, 4.4 mm deep, is crossed by a 4.5 mm erosion. Not a tangency a nudge would clear: every erosion from 3.0 to 5.0 mm is null there while 6.0 mm succeeds. Fixed by the morphological identity `erosion(A − B, w) == erosion(A, w) − dilation(B, w)`, whose right-hand side is well conditioned in both halves — the outline erodes cleanly and dilating eight separated circles is trivial. **Exact, not an approximation**: where the direct form works the two agree to the last digit, 5770.975162 either way at U=1.0, and every reference number is unchanged. Generalised to any number of subtracted regions as `plane2d.erode_difference` when IP-FC-57 needed the same move on a three-operand difference | IP-FC-12, IP-FC-13 | |
| IP-FC-55 | in progress | **Per-site audit of the `eps` sites IP-FC-50 left, and one removal declined on the evidence.** Each site is a spreadsheet row, so it can be rewritten on a built document and recomputed -- one site at a time, no source edit. Measured at U=1, 3/16 in: the corner's **axial section overlap** (`end_h`, `mid_z0`, `mid_h`) moves the assembled part by −0.0006 mm³ and changes no face; the corner's **relief cut overshoot** leaves +0.0306 mm³ behind without it; the bulkhead's **flange relief overshoot** is volume-neutral but costs 4 extra faces flush. The last two stay, now with a measurement saying why rather than an assumption. **The axial overlap stays too, and that reverses this item's own first plan.** It was written up as the one clear removal — union slop for a kernel we no longer use, which is what IP-FC-49 established. Reading the source settled it the other way: `corner_end` extrudes `bulkhead_thickness + eps` and `corner_middle` starts at `2*bt - eps` and is `2*eps` taller, so **the overlap is stated by the authority, not added by the port**. Removing it is therefore a deliberate divergence, and it costs something real — `EndCutGroove` moves −0.17% and `MidSection` −0.05% against their OpenSCAD references, which would take `EndCutGroove` outside the 0.1% check and turn two cross-kernel comparisons into FreeCAD-measured constants. It buys −4e-8 of the assembled part. **Weakening a check against the authority while the authority still stands is the wrong trade**; the case for removal is real but it is IP-FC-34's, once OpenSCAD is retired and the cross-kernel argument no longer exists. That distinguishes it from `mask_eps`, which diverges because OCCT actively *failed* with the source's value, and from IP-FC-50's cut overshoots, whose removal left every checked volume byte-identical. What remains: `bulkhead_cuts.clean_r`, the one site that is not slop at all but 0.01 mm off a real bore radius, being measured across all 148 valid bulkhead variants | IP-FC-50 | |
| IP-FC-56 | todo | **The bulkhead's sheet carries rows no bulkhead reads.** `bulkhead_section` merges `corner_tree.PARAMS` to reuse `corner_end`, and `FX`, `unit_length`, `greeble_tolerance`, `mid_h` and `mid_z0` come with it. Measured, not assumed: setting FX to 7.0 on a built bulkhead and recomputing leaves the volume unchanged to the last digit, and so does perturbing each of the others. **A bulkhead is independent of bay length (OQ-DES-C3)** — there is no `dp.bulkhead.FX` field, which is that decision written into the data model — so exporting a value for the row would assert the opposite; they are exempted in `corner_common.UNSEEDED` for now instead. **The checker is built** — [`check_unread_rows.py`](../../src/Fuselage/freecad/check_unread_rows.py), 2026-08-14. It perturbs each row up and down, recomputes, and compares volume, face count and bounding box. All three, because IP-FC-55 found an eps whose removal left the volume identical to the last digit and added four faces: a checker watching volume alone would have called that row unread and invited its deletion. **It was wrong twice before it was right, and both failures are worth recording.** It first reported "183 rows, 0 read by nothing" having tested nothing at all — FreeCAD returns a text cell's contents with a literal-marker apostrophe attached, so every alias lookup missed and every row was skipped silently; it now counts skips and fails if it tested nothing. It then perturbed only upward and called 13 corner rows unread, most of them tool dimensions that are generous on purpose — a cut sized to pass clear through material does not care about being made longer. Bidirectional perturbation took that to 7. **Results so far: corner 53 rows, 7 unread; bulkhead 183 rows, 87 unread.** The bulkhead number is not a finding yet and must not be read as one — most of it is `corner_tree`'s own rows (`wedge_*`, `nub_*`, `mouth_*`) describing sections the bulkhead legitimately never builds, and the rest is the same generous-tool insensitivity. **"Unread" here means the part is insensitive to the perturbation, which is necessary evidence for "vestigial" and not sufficient.** **What remains, in order.** (1) Triage those 87 into inherited-and-unbuilt, insensitive-but-read, and genuinely vestigial. (2) Prune what it finds, following the **expression graph and not a name list** — `greeble_radius` and `relief_depth` both reference `greeble_tolerance`, so dropping that row without dropping its dependents breaks the sheet, and dropping its dependents needs them to be unread too. (3) Delete the four inherited entries from `corner_common.UNSEEDED`, which is the check that the prune actually landed: those exemptions exist only to describe this defect, so the list shrinking is the evidence. **Do not simply exclude `corner_tree.PARAMS` from the merge** — the bulkhead genuinely needs most of it to build `corner_end`, which is the whole reason the merge is there | IP-FC-53 | [bulkhead.md §OQ-DES-C3](../design/bulkhead.md) |
| IP-FC-57 | done | **The no-panel boom bulkheads could not be built: `Part::Offset2D` returned a null shape, twice, for two different reasons that look identical from outside.** Both are the last variants standing after IP-FC-54, both are the `0mm` panel where `panel_thickness`, `panel_overlap` and `panel_tolerance` are all zero and the OML's panel notch degenerates, and in both the failing shape is one OCCT had just produced itself. **(a) `dual` — the closing erosion.** The fillet chain's `2r` dilation yields a shape its own `offset(-r)` cannot consume. Fixed by performing that dilation as two dilations of `r`: the same operation, and the same result to every measurable digit — area 7009.984015 mm², 5 faces, 78 edges either way — but only the split one erodes. **(b) `offset_single` — the leading erosion.** `offset(-r)` of `OML − MATERIAL` is null, and that one is a *boolean* result rather than an offset result, so splitting does not apply. Fixed with the IP-FC-54 identity, which is now the shared `plane2d.erode_difference`: the region is `oml_outer − bores − material`, so erode the outline and dilate the two subtracted regions. Every operand offsets without complaint; their difference does not. **What made both diagnosable was the same negative result**: null at *every* distance, down to 0.01 mm, under all three `Join` settings, after `removeSplitter`, after rebuilding the face from its wires, and in half-steps. A shape that is genuinely wrong has a distance that works; uniform failure means the representation, not the geometry — confirmed by reassembling one failing wire from its own edges, which offsets fine and reproduces the identity's answer to 1e-7. Both parts now agree with OpenSCAD, +0.00078% and +0.00068%, with identical bounding boxes, and every previously verified reference number is bit-identical | IP-FC-12, IP-FC-13, IP-FC-54 | |
| IP-FC-58 | todo | **One frame bulkhead variant builds to zero solids.** `1.5 end_anchor 0mm` — a valid swept combination, an end type, so FreeCAD is the backend that builds it — produces no solid at all; `build_part` refuses it loudly rather than writing a bad mesh, which is the guard working, but the part cannot be made. **Found because the frame bulkhead had never been swept exhaustively**: every check on it has been a sample, and `--kinds`, which makes exhaustive coverage of one kind affordable, only existed from 2026-08-14. Scope is now measured rather than feared — **87 of the 88 end-type variants build as one valid solid**, so this is one point and not a class. The `0mm` panel is where `panel_thickness`, `panel_overlap` and `panel_tolerance` are all zero and several tools degenerate (IP-FC-46 is the same corner of the space), and `end_anchor` at U=1.5 is the only combination that tips over. Next step is the IP-FC-57 diagnostic routine — find which node first goes null or invalid, then read the spread of failing parameter values to tell a geometry problem from a representation one | IP-FC-13 | |
| IP-FC-59 | todo | **Implement OQ-DES-B13: compute the corner cleanup's real intersection instead of standing in for it with `eps`.** Decided 2026-08-14. The cleanup tool that forms the bulkhead's corner cut-out is dimensioned from `flat_x`, the corner's *cut polygon* extent, while the corner's *material* ends one `panel_tolerance` inboard at `rect_edge`. The tool therefore overhangs the material it cleans by exactly `panel_tolerance`, and the `eps` in `clean_r` makes that overhang bite — cutting `eps` below the nominal panel seat across the overhang, leaving a step `eps` deep and `panel_tolerance` long through the full thickness, eight times per part. Measured on the built solid, the two dimensions track their inputs exactly and independently. **The fix is to terminate the cleanup at `x = flat_offset - seat`**, the true crossing of the diagonal face `x + y = flat_offset` with the seat plane. **Two cases, both real**: the longeron-chamfer term governs on 136 of 148 variants and gives a genuine crossing inboard of `flat_x`; the panel term governs on the other 12, where `flat_y == seat` to machine precision and the diagonal begins *on* the seat, so the intersection is a vertex-on-vertex coincidence that is real geometry and cannot be designed away. **This changes the OpenSCAD authority, not the port** — the port transcribes `clean_r` faithfully and will follow — and it moves 28 of 148 swept parts by 0.032 to 0.048 mm³ each, on parts that have been printed and flown, so it wants a print check even though it removes material that should never have been removed | IP-FC-13, OQ-DES-B13 | [bulkhead.md §OQ-DES-B13](../design/bulkhead.md) |
| IP-FC-17 | blocked (IP-FC-16) | Implement cowl interior surfaces. **OQ-DES-CW6 resolved 2026-08-09 and no longer blocks this** — but it attaches a constraint: the interior is *additive*, and the UC-1 print export must keep coming from the un-shelled notched blank, because cowls print in spiral vase mode and a modelled wall destroys that. Model the rib at `2·w·n_perimeters + t_cut`. The sweep's printing output must be verifiable as unchanged by this work | IP-FC-16, IP-FC-14, IP-FC-42 | *(IP-FC-16 output)*, [cowl.md §6.4](../design/cowl.md) |
| IP-FC-18 | blocked (IP-FC-14) | Model the non-printed components — longeron, panel, threaded insert, bolt — derived from the clearances that already receive them | IP-FC-14 | [freecad_migration.md §UC-8](../architecture/freecad_migration.md) |
| IP-FC-19 | blocked (IP-FC-17) | UC-4 — assemblies with FreeCAD Assembly joints for unit, nose, tail and full fuselage. Includes asserting each solved placement against the placement constructed from parameters | IP-FC-17, IP-FC-18, IP-FC-35 | [freecad_migration.md §OQ-ARCH-6](../architecture/freecad_migration.md) |
| IP-FC-35 | done | The Assembly workbench drives headless. `freecad/spike_assembly.py` creates an `Assembly::AssemblyObject`, grounds one part, adds a Fixed joint with no task dialog, solves, and reads the placement back — a displaced box lands with its mated face **0.000000000 mm** from its target. Three API details are not optional and none are documented for scripting: joints must be created *inside* the assembly, both references go in through `setJointConnectors` (assigning them directly leaves the JCS at identity and the solve mates the part origins), and the sub list needs two entries, not one | — | [freecad_migration.md §OQ-ARCH-6](../architecture/freecad_migration.md) |
| IP-FC-20 | blocked (IP-FC-18) | UC-8 tier 1 — mass properties: densities per component, mass, CG, inertia tensor | IP-FC-18 | [freecad_migration.md §UC-8 is a ladder](../architecture/freecad_migration.md) |
| IP-FC-21 | blocked (IP-FC-14) | UC-7a — part drawings as a **family drawing**: lettered dimension callouts plus a per-variant value table. Dimensions are named expressions over parameters, bound to topological references; interface dimensions are the required floor | IP-FC-14, IP-FC-36 | [freecad_migration.md §OQ-ARCH-7](../architecture/freecad_migration.md) |
| IP-FC-36 | todo | Define the dimension scheme: enumerate the interface expressions (starting from those already derived in the design documents), state the completeness test, and decide whether internal structure is dimensioned or shown as reference | — | [freecad_migration.md §OQ-ARCH-7](../architecture/freecad_migration.md), [bulkhead.md](../design/bulkhead.md), [cowl.md §4.1](../design/cowl.md) |
| IP-FC-22 | blocked (IP-FC-19, IP-FC-21) | UC-7b — assembly drawings | IP-FC-19, IP-FC-21 | [freecad_migration.md §OQ-ARCH-7](../architecture/freecad_migration.md) |
| IP-FC-23 | blocked (IP-FC-19) | UC-8 tier 2 — isotropic FEM with bonded interfaces as assembly properties | IP-FC-19, IP-FC-20 | [freecad_migration.md §UC-8 is a ladder](../architecture/freecad_migration.md) |
| IP-FC-24 | blocked (IP-FC-23) | UC-8 tier 3 — orthotropic material per part from the recorded print orientation | IP-FC-23 | [freecad_migration.md §UC-8 is a ladder](../architecture/freecad_migration.md) |
| IP-FC-25 | blocked (IP-FC-4) | UC-9b — drive OpenVSP for parametric nose and tail generation; VSPAERO force and moment on the fuselage | IP-FC-4 | [freecad_migration.md §UC-9](../architecture/freecad_migration.md) |
| IP-FC-26 | blocked (IP-FC-13) | UC-5 — Blender export path, explode transforms, animation paths | IP-FC-13 | [freecad_migration.md §Use cases](../architecture/freecad_migration.md) |
| IP-FC-27 | blocked (IP-FC-13) | UC-6 — new components, starting with one panel and its 2D vector cutting template | IP-FC-13 | [freecad_migration.md §Use cases](../architecture/freecad_migration.md) |

> **IP-FC-10 note:** Both blockers cleared -- IP-FC-1 measured startup and confirmed
> subprocess-per-part, and IP-FC-9 delivered two whole parts. The thread pool stayed: a
> pool of threads waiting on subprocesses is the right shape whichever binary the
> subprocess is, and that is why the swap touched none of it.

> **IP-FC-11 correction, 2026-08-09.** This note previously said the hole was a FreeCAD
> regression -- that a parameter JSON does not contain the geometry where a generated
> `.scad` does. **The second half of that was wrong, and it was wrong about the older
> path.** A generated `.stl.scad` is one `use <>` line and one call with the parameters
> substituted in; it contains no geometry either. So `--resume` had been unable to see an
> edit to any `.scad` module since the day it was written, and the FreeCAD backend did not
> introduce the failure, it made it visible by prompting the question. Both paths are
> stamped now, by the same module, and the correction is left here rather than edited away
> because the reasoning that produced it -- inferring a file's contents from its extension
> instead of opening one -- is the kind worth being able to recognise again.

> **IP-FC-12 blocked reason:** The cowls additionally need the OML as a surface (IP-FC-4)
> and a design document (IP-FC-7). Porting them against a tessellated mesh would produce
> parts that can never satisfy UC-2, UC-3, UC-4 or UC-7. *Both of those cleared 2026-08-10.*
>
> The **boom bulkhead** half is now blocked on **OQ-DES-B11**, opened 2026-08-10. OQ-DES-B9
> had chosen real fillets over reproducing OpenSCAD's morphological `fillet_inner`, and one of
> its stated grounds was that `Part::Offset2D` could not reproduce it. It can, to 0.00456% —
> the earlier 19% was read at a single parameter value where the test polygon is degenerate.
> That decision may still stand on the grounds that do not depend on the measurement, but it
> was argued over the frame bulkhead's four *named corners*, and the boom bulkhead instead
> applies `fillet_inner` to whole compound regions, where the real-fillet route means
> enumerating concave edges whose count moves with the parameters. A different trade than the
> one that was decided, so it goes back to the design authority rather than being settled here.

> **IP-FC-16 note:** OQ-ARCH-5 is decided — adaptive slice-and-fit. What remains is
> writing the algorithm down: how layers are sliced, how each is inset, how the sections
> are joined into a solid, and what supplies material where a horizontal surface would
> leave none. That last clause is the only part still genuinely open.

> **IP-FC-17, IP-FC-19 blocked reason:** A cowl cannot close as a solid without its
> interior surface, and an assembly of open shells is not an assembly. Both were also
> blocked on OQ-DES-CW6, which is resolved as of 2026-08-09; IP-FC-16 is now the only
> gate on IP-FC-17.

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

### `Part::Offset2D` reproduces the whole offset chain, including `fillet_inner`

Measured because the bulkhead's web is built with `offset(r = -web_width)` and
`fillet_inner(web_fillet_radius)`, and everything downstream depends on those porting
faithfully. `fillet_inner` is itself a morphological construction:

```scad
intersection() { offset(-r) offset(2r) offset(-r) children; children; }
```

**Corrected 2026-08-10.** This section previously reported a 15% divergence on the dilation
and a 19% divergence on the full chain, and that reading was wrong — an artifact of reading
one value of one parameter, on a polygon that happens to be degenerate at exactly that
value. The measurement now sweeps it. Away from the degeneracy:

| shrink | `offset(-s)` | `offset(-r)` | `offset(+2r)` | `offset(-r)` | `fillet_inner(r)` |
| --- | --- | --- | --- | --- | --- |
| 2.0 | −0.00061% | −0.00375% | +0.00105% | −0.00122% | +0.00049% |
| 2.5 | −0.00072% | −0.00456% | +0.00107% | −0.00007% | +0.00060% |
| **3.0** | −0.00086% | −0.00769% | **−15.36%** | **−19.38%** | **−19.38%** |
| 3.5 | −0.00107% | −0.00428% | −0.00102% | −0.00091% | −0.00049% |
| 4.0 | −0.00143% | −0.00348% | +0.00201% | +0.00216% | +0.00243% |

Worst |delta| off the degenerate row is **0.00456%**, inside the 0.0060% faceting floor that
[§Cross-engine equivalence](#ip-fc-13-progress--the-two-backends-measured-against-each-other)
uses. `Part::Offset2D` with `Join='Arc'` *is* OpenSCAD's `offset(r=)`, and the chain of four
of them *is* `fillet_inner`.

**Why the shrink = 3 row misleads.** The test polygon's bottom bar is exactly 10 wide, so
there the chained erosion of `shrink + fillet` is exactly half of it and the erosion of that
bar is a **hairline**: zero area, 20 mm long. The following `offset(+2r)` paints a hairline
into a band 8 mm wide, so a feature contributing no area at all beforehand contributes a
great deal afterwards, and whether it survives is a question about arithmetic rather than
about geometry. CGAL's exact rationals keep it; a floating-point offset does not.

OpenSCAD's own answer at that step is not stable enough to be a reference value:

| shrink | 2.980 | 2.999 | **3.000** | 3.001 | 3.020 |
| --- | --- | --- | --- | --- | --- |
| `offset(+2r)` | 576.845761 | 573.972886 | **453.820893** | 381.036874 | 367.480890 |

A 33% move across 0.002 mm, against a few units per 0.02 everywhere else — and 453.82 is
neither limit but a value in between. FreeCAD's 384.09 is essentially the limit from above.
Neither engine is wrong; the question has no stable answer there.

A raster settles it independently of both. Rasterising the exact signed distance to the
polygon, thresholding for each erosion and running a Euclidean distance transform for each
dilation reproduces the morphological definition with no CAD kernel in the loop; validated
on a disk and a square against `A + Pr + πr²` to −0.02%. It agrees with OpenSCAD to within
0.03–0.23% at every shrink off the degeneracy, and at shrink = 3 it does not converge at all
— 367.3, 382.7, 372.6, 376.2 as the cell size halves — which is what a hairline looks like
from a third direction.

**The general lesson is not about offsets.** A parameter value where a limb is exactly twice
the offset radius is a knife edge in *any* engine, and `fillet_inner(r)` applied where a limb
is exactly `2r` wide sits on one by construction. Sweeping caught it here for the same reason
sweeping caught IP-FC-46 through IP-FC-49: a single sample of a parameter is not a
measurement of a function of it.

**The boom bulkhead is structurally off that knife edge, at every `U`.** Its two offset
radii both scale with `U` and their ratio never moves:

| Derived | Value | Source |
| --- | --- | --- |
| `web.fillet_radius` | `2·U` | `derived_parameters` |
| `web.width` (boom) | `6·U` | `derived_parameters`, the `is_boom` branch |
| `web_width / (2 · web_fillet_radius)` | **1.5, always** | — |

So the stroke `offset(r = web_width/2)` lays down a limb `6·U` wide and `fillet_inner(2·U)`
erodes `4·U` of it, leaving `2·U`. The degenerate case is `1.0` and the sweep sits at `1.5`
with no parameter able to move it, because the two quantities are not independently
specified. This is a property of the parameter relationships, not of the values tried.

It does *not* clear the whole part: the region-wide `fillet_inner` in `boom_bulkhead` closes
gaps between features whose spacing does depend on panel thickness and boom position, and
any of those landing on `4·U` is the same knife edge. Those cannot be excluded by algebra,
which is what `compare_backends.py` across the boom sweep is for.

**What this changes.** Nothing already built — `fillet_inner` is reached only by
`bulkhead_web_inner_shape_octant`, which the non-interconnect path never calls, so the ported
bulkhead does not touch it. It changes what is available to IP-FC-12, whose boom bulkhead is
built almost entirely from offsets: the morphological route is now known to be both faithful
and fully parametric. See [OQ-DES-B9](../design/bulkhead.md), whose stated premise this
falsifies.

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

Both parts are done and verified against what the sweep produces.

---

## IP-FC-10 — the sweep drives FreeCAD

`--backend freecad` renders the corner and the bulkhead through FreeCAD, one `freecadcmd`
per part, in the sweep's own directory layout with its previews and its atomic writes.

| Part, at U=1 panel 3/16in | OpenSCAD | FreeCAD | Delta |
| --- | --- | --- | --- |
| `bulkhead_end_bolt` | 6922.5048968 mm³, 29 000 tris | 6922.5291739 mm³, 26 304 tris | **+0.00035%** |
| `corner_FX_1.0` | 14146.5851970 mm³, 11 932 tris | 14146.7564282 mm³, 11 976 tris | **+0.00121%** |

Bounding boxes identical in both cases, to four places.

### The swap touched none of the machinery, and that was the test of it

The item read "swap the render call, keeping the queue, worker budget, atomic writes and
previews." None of those needed changing, because the queue submits a **command** and a
callback that runs on success, and it never knew which binary it was running. `solid_render`
split into `render_definition` — resume comparison, atomic write, preview, submission, all
engine-independent — plus two small backends supplying the only things that actually differ:

| | Definition on disk | Command |
| --- | --- | --- |
| OpenSCAD | the generated `.stl.scad` | `openscad -o` |
| FreeCAD | the exported `.stl.json` | `freecadcmd build_part.py` |

A third backend would need nothing in `render_definition` at all. The thread pool stayed as
it was: a pool of threads waiting on subprocesses is the right shape whichever binary the
subprocess runs, and IP-FC-1's 0.24 s startup against a ~0.5 s part is what makes
process-per-part affordable. It also inherits the crash isolation for free — including the
serial-retry recovery, which exists because a large CGAL render can abort on memory
pressure and succeed alone.

### Keeping the definition on disk is what keeps `--resume` honest

The parameters play the role the generated `.scad` played. Self-tested in both directions,
as IP-FC-2 was: with nothing changed, both parts skip in 0.1 s; with `corner_radius`
perturbed by 0.001 mm, the corner re-renders and the bulkhead beside it still skips.

**The key was incomplete, and not only on the new path.** The obvious next thought was that
a parameter file cannot see an edit to `bulkhead_full.py` where a generated `.scad` contains
its geometry — so `--backend freecad --resume` would skip parts it ought to re-render. The
first half is right. The second half was an assumption, and opening one generated file
refuted it:

```openscad
use <../../../../../../scad/fuselage_bulkhead_geometry.scad>;
bulkhead_section_full(bolt_hole_radius = 2.0, bolt_offset = 8.0, ...);
```

That is a call, not geometry. Editing `fuselage_bulkhead_geometry.scad` leaves it byte for
byte identical, so **`--resume` had been blind to every change to the OpenSCAD geometry
modules since it was written**, and the FreeCAD backend did not introduce the failure — it
prompted the question that found it. Both paths are fixed together in IP-FC-11 below.

### Two findings about `freecadcmd` worth having written down

**Its exit code cannot be trusted.** An uncaught exception in the script it was handed prints
`Exception while processing file: ...` and **exits 0**. Worse, an explicit `sys.exit(n)` is
not stable: the same `sys.exit(3)` was observed returning 3 on one run and 1 on the next.
A queue that believes the status would record a clean render for a part that was never
built. So the success criterion is the **artifact**: `_finalize` checks the mesh exists and
fails with a sentence naming the part, rather than letting `os.replace` raise "cannot find
the file specified", which reads like a disk fault.

**Every argument has to go behind `--pass`.** `freecadcmd` parses the command line before
the script runs. An unrecognised `--flag` makes it print its own usage and stop without ever
calling the script — silently, if stdout is piped. A bare positional it tries to *open as a
document*, which on a `.json` fails inside the FEM mesh importer with `invalid literal for
int() with base 10: 'U'` — an error that names neither FreeCAD nor any real problem with the
file. `--pass` takes exactly one argument, so values are joined with `=`.

### The mesh is a setting, and finer is not better

Chosen by measurement rather than by taking the finest available, against a B-rep volume of
6922.5127750 mm³:

| Linear deflection | Facets | STL volume | Delta |
| --- | --- | --- | --- |
| 1e-2 | 7 264 | 6922.7192046 | +0.00298% |
| 3e-3 | 13 392 | 6922.5711638 | +0.00084% |
| **1e-3** | **26 304** | **6922.5291739** | **+0.00024%** |
| 1e-4 | 65 264 | 6922.4862676 | −0.00038% |
| 1e-5 | 173 408 | 6922.4794155 | −0.00048% |

**Refining past 1e-3 makes agreement worse and then stops improving.** That floor is the file
format, not the mesher: binary STL stores float32 coordinates, so a 45 mm part carries ~3e-6
mm of quantisation per vertex however many vertices there are. Past ~26k facets the extra
detail buys five times the meshing time and six times the file for a worse number. 1e-3 also
lands within a few percent of the OpenSCAD reference's facet count, which keeps IP-FC-13
comparing geometry rather than mesh density.

**Do not check any of this with `Mesh.Volume`.** It accumulates in single precision and gets
*worse* as the mesh gets finer — on the 173 408-facet mesh it reports 6921.9243164, which is
0.55 mm³ below what the same file measures at, twenty times the real tessellation error. Read
naively it says the fine mesh is the bad one, inverting the conclusion. Measure the written
STL in float64, which `measure.py` does.

## IP-FC-11 — what a definition file has to contain to be a staleness key

`--resume` skips a part when the definition file it would write now is byte-identical to the
one on disk and the STL beside it is a whole mesh. That is a complete test only if the
definition determines the part. It did not: on both backends the definition records the
**input** to a build and says nothing about the code that consumes it.

| | Definition | Sees a parameter change | Saw a geometry change |
| --- | --- | --- | --- |
| OpenSCAD | `use <>` line + call | yes | **no** |
| FreeCAD | parameter table | yes | **no** |

The fix goes where the existing comparison already looks, so nothing in `render_definition`
changes and neither backend gains a special case. [`tools/geometry_version.py`](../../src/Fuselage/tools/geometry_version.py)
walks a transitive closure and hashes it:

- **OpenSCAD** — roots taken from the generated file's own `use`/`include` lines, then
  followed through the sources. The bulkhead closes over three files
  (`fuselage_bulkhead_geometry` → `fuselage_corner_geometry` → `shape_modifier_utils`), the
  corner over two. Reading the roots out of the generated file rather than the call site is
  what makes this cover **every** part the sweep produces — cowls, tails, plates, booms —
  instead of only the kinds someone remembered to annotate. The digest lands as a comment
  line, so the file stays renderable and hand-runnable.
- **FreeCAD** — roots are the kind's top module and `build_part.py`, followed through
  sibling imports. `build_part.py` is a root because `LINEAR_DEFLECTION` lives in it, and the
  tessellation setting changes the exported mesh as surely as a sketch does. The digest and
  the module list land in the JSON.

**Deliberately over-sensitive.** The hash is over file bytes, so editing a docstring
re-renders parts whose geometry did not move. A false re-render costs minutes of CPU; a false
skip ships a part that does not match its own source and stays invisible until someone
measures it. Normalising — stripping comments, comparing ASTs — would trade a real guarantee
for a fragile one.

**The self-test found a bug the digest alone would have hidden.** OpenSCAD does not require a
semicolon after `use <x.scad>`, and not one hand-written module in `scad/` writes one. The
first regex required it, so the walk stopped at the first file and the bulkhead's closure came
back as one module instead of three — an edit to `fuselage_corner_geometry.scad`, which the
bulkhead includes, still looked like no change at all. A digest that changes when you edit the
obvious file looks correct from the outside; only walking a real dependency chain and editing
something two levels down exposed it. (`fuselage_variants._SCAD_REF_RE` can keep requiring the
semicolon — it only ever sees solid2's generated files, which emit it.)

Verified in both directions, 16/16 on the closure: an edit anywhere in a part's closure moves
its digest, an edit to a sibling outside it does not, and the digest is stable across repeats
(which `--resume` needs, since it compares byte for byte).

The end-to-end half — render, resume, edit, resume again — is what found IP-FC-46 below, so
its result is recorded there.

**The first `--resume` after this change re-renders everything**, on both backends. The
definition format gained a line, so nothing on disk matches what would be written now. That
is the mechanism working, not a fault, and it happens once.

The digest is also independent of *how* a source was reached. A generated file whose `use <>`
line is a relative path and one whose line is an absolute UNC path — which happens when the
output tree and `scad/` are on different shares, since `relativize_scad_references` leaves
those alone rather than mangling them — produce the same `674c5d02f681e02b`. Files are
identified by basename, so the digest is a property of the sources rather than of the machine
that ran the sweep, and two checkouts compare equal.

**Still outside the key:** assets referenced by value at render time rather than by source
text — today, the OML meshes a cowl imports. The filename is in the definition, the content is
not, so replacing `oml/nose_round.stl` in place remains invisible to a resume and `--force`
remains the answer for it. Narrower than the hole this closes, and recorded rather than left
implied.

## IP-FC-46 — a variant where the two toolchains disagree about nothing

IP-FC-11's end-to-end test renders a real part, resumes, edits a geometry module, resumes
again. It picked its part the way the sweep does — the **first valid combination** — rather
than the one IP-FC-10 was measured on, and it never got as far as testing resume:

```text
GTPanelSlot: Length of box too small          (×10, one per section)
Exception while processing file: build_part.py
  [class Standard_NullObject BRepCheck_Analyzer::Init() - NULL shape]
```

The `0mm` panel row is the **no-panel** variant: thickness, tolerance and overlap all zero.
It is not an edge case slipped past a filter — `bulkhead_validity_check` admits
`panel.thickness == 0` explicitly, and 40 of the swept bulkheads are built from it. So
`slot_w` and `slot_d` are both zero, and the two engines disagree about what a tool with no
extent means:

| | zero-extent tool | result |
| --- | --- | --- |
| OpenSCAD | `cube([0,0,h])` is the empty set | `difference()` is a no-op — no slot, which is correct |
| FreeCAD | `Part::Box` refuses to build | **null shape**, and a null tool nulls the whole cut chain |

The failure mode is worth noting on its own: the part does not come out wrong, it comes out
as *nothing*, and the error names `BRepCheck_Analyzer` six features downstream of the box
that actually failed. The `Length of box too small` warning that does name it goes to stderr
among the FreeCAD banner, and — per the finding above — the process still exits 0.

`corner_tree._degenerate()` reads the extents off the parameter sheet and omits the feature
when either is zero, which is exactly what OpenSCAD's empty set does. Reading the sheet
rather than the seed keeps the decision agreeing with the expressions that build the tool.

The cost is stated where it lands: a document generated at `0mm` has no slot feature to grow
if someone raises `panel_thickness` in the GUI. That is the one edit this variant does not
support, and it is one the sweep would refuse anyway — `panel_offset` and `panel_overlap` are
derived from the thickness and would no longer agree, which is what `render_variant.py`
exists for.

Zero is reachable by six swept parameters, not one. Enumerating the space rather than fixing
the case in hand:

| Parameter | Zero in | Of |
| --- | --- | --- |
| `panel_thickness`, `panel_tolerance`, `panel_overlap` | 88 | 412 |
| `panel_offset` | 16 | 412 |
| `cowl_flange_height`, `cowl_flange_tolerance` | 132 | 148 |

The `panel_*` group is this defect. `panel_offset` reaches zero only where `panel_overlap`
does not, so the extents it feeds stay non-zero. The `cowl_flange_*` pair is zero on every
non-cowling bulkhead, which is the majority — and the flange is already conditional, so it
does not bite. **New geometry built from a parameter that can reach zero needs the same
treatment**, and the table above is where to check that.

## IP-FC-47 — the backend rendered three bulkhead types as a fourth

Found by the same enumeration, one step further along. `bulkhead_render`'s OpenSCAD call
passes two flags that the FreeCAD branch does not:

```python
scadobj = fgeom.bulkhead_section_full(
    is_interconnect=is_interconnect, is_cowling=is_cowling, **bulkhead_parameters(dp))
```

`bulkhead_full.emit(doc, seed)` takes neither, because IP-FC-9 ported the **end** type and
only the end type. The parameter table cannot carry the difference either: `end_bolt` and
`interconnect` produce the same 24 numbers and differ only in which branch consumes them. So
under `--backend freecad` all five swept types were built as end bulkheads — 60 of 148 parts
wrong, each under the correct filename, each with a plausible volume and a valid single
solid. Nothing in the run would have looked unusual.

| Type | Parts | Routed to |
| --- | --- | --- |
| `end_bolt`, `end_anchor` | 88 | FreeCAD |
| `interconnect` | 44 | OpenSCAD (was: built as an end bulkhead) |
| `cowling_bolt`, `cowling_anchor` | 16 | OpenSCAD (was: built as an end bulkhead) |

`_backend_for(kind, supported=)` extends the fallback that already exists for unported
*kinds* down to unported *variants* of a ported kind. A part that falls back is still
rendered correctly; a part built from the wrong branch is one nobody has reason to
re-examine. `_variant_note` now carries `type_name` as well, so two types can no longer
produce byte-identical definition files — which `--resume` compares.

**What both findings say about the IP-FC-10 verification.** Two parts measured at +0.00035%
and +0.00121% established that the backends agree *where both produce the intended part*.
They could not establish that the backend produces the intended part across the swept space,
and it did not — once by failing loudly, once by succeeding quietly. Neither was visible from
a single part, and the quiet one would not have been visible from a hundred parts of the same
type. That is IP-FC-13's job, and the two classes to look for now have names: parameters that
reach zero, and branch flags the port has not taken.

## IP-FC-48 — the parameter file was right and the part was not

The IP-FC-46 fix made the no-panel bulkhead build, so the comparison could finally run across
a slice of the sweep instead of one part. It did not come back clean:

| Part | OpenSCAD mm³ | FreeCAD mm³ | Delta |
| --- | --- | --- | --- |
| `U_1.0 corner FX_1.0` | 16665.638272 | 16665.803569 | +0.00099% |
| `U_1.0 corner FX_0.5` | 8140.018855 | 16665.803569 | **+104.7%** |
| `U_1.0 corner FX_3.0` | 50768.115994 | 16665.803569 | **−67.2%** |
| `U_1.0 bulkhead 0mm` | 7122.082083 | 7122.102422 | +0.00029% |
| `U_0.5 bulkhead 0mm` | 2085.656423 | 2115.263149 | **+1.42%** |

Every corner produced **the same volume regardless of FX** — the FX=1.0 volume. The
definition files were not at fault; they carried `unit_length` of 25.0, 50.0 and 150.0
correctly. The value was being read and thrown away.

`seeded()` replaces **literal** rows only. That is deliberate and it is the right rule: a row
the port states as a *relationship* is what lets a generated document still follow a changed
U, and `merge_params` explicitly prefers the relationship over a constant for exactly that
reason. `corner_tree.PARAMS` states three of them —

```python
('corner_radius',   '=U * 10'),
('longeron_radius', '=U * 2'),
('unit_length',     '=U * FX * 100'),
```

— and an expression row survives seeding and evaluates from whatever `U` and `FX` the sheet
holds. `corner_parameters` supplies `U` but not `FX`; `bulkhead_parameters` supplies neither.
So `FX` and `U` stayed at their literal `1.0`, and:

- every FreeCAD **corner** was built one bay long, whatever FX said;
- every FreeCAD **bulkhead** was built with a 10 mm corner radius and a 2 mm longeron bore,
  whatever U said.

Both are exactly right at U=1, FX=1. That is the single combination IP-FC-10 measured.

Neither parameter can go in the shared mapping: `fuselage_corner` takes no `FX` and
`bulkhead_section_full` takes no `U` — both are handed the finished dimensions — so passing
them through `corner_parameters` would make the solid2 call a `TypeError`. They are added at
the FreeCAD branch of each render function, where the reason is written down.

**The fix that matters is the second one.** `check_seed` already existed, and its docstring
already described this case: *"the expression rows kept in preference to a literal: this is
where a derivation the port transcribed from the OpenSCAD source is measured against what
`derived_parameters()` computes."* It was called by the check scripts in `freecad/` and never
by `build_part.py`, so the sweep — the one path that builds parts anybody keeps — was the one
path that did not run it. It now runs on **every** build:

```text
build_part: bulkhead: the sheet disagrees with the parameter file on corner_radius, longeron_radius
  corner_radius          sheet 10   authority 25
  longeron_radius        sheet 2    authority 5
```

That is the diagnosis that was missing for the entire life of the backend. Written to stderr
and flushed, not raised as `SystemExit(message)` — freecadcmd discards the message either
way, and the first version of this guard refused silently, leaving nothing but a missing
mesh.

With `U` and `FX` seeded, the corner agrees with OpenSCAD across the whole FX axis:

| FX | 0.5 | 1.0 | 1.5 | 2.0 | 2.5 | 3.0 |
| --- | --- | --- | --- | --- | --- | --- |
| Delta | +0.00058% | +0.00028% | +0.00019% | +0.00015% | +0.00023% | +0.00019% |

and the no-panel bulkhead across U: −0.00081% at 0.5, −0.00031% at 0.75, +0.00023% at 1.0.

**The generalisable part.** An expression row is a claim that the port reproduces a
derivation. A seeded literal is a claim that it does not need to. Both are fine; what is not
fine is an expression row whose inputs the seed does not supply, because it then computes a
plausible number from the module's own defaults while the correct number sits in the file
two lines away. There is no geometric symptom — the part is valid, single-solid, and the
right shape — and the only reason this was found is that the comparison finally covered more
than one point in the space.

## IP-FC-35 — the Assembly workbench runs headless

IP-FC-19 wants assemblies built from parameters, solved, and then *checked* — each solved
placement asserted against the placement the parameters predict. That is only worth planning
if the whole loop runs without a window, because the sweep is a batch process.

It does. [`freecad/spike_assembly.py`](../../src/Fuselage/freecad/spike_assembly.py) creates
an `Assembly::AssemblyObject` under `freecadcmd`, grounds one box, adds a Fixed joint with no
task dialog, and solves. A box displaced to `(40, 25, −7)` and rotated 30° lands with its
mated face **0.000000000 mm** from the face it was joined to, and the placement reads back
from the document as data. The workbench imports fine headless despite living in `Mod/` and
pulling in coin and Qt.

Three API details are required and none of them are documented for scripting — the workbench
is written for the GUI, which happens to satisfy all three by construction:

- **Joints must be created inside the assembly**, via `assembly.newObject`, not added
  afterwards. `Joint.__init__` ends by calling `setJointConnectors`, which walks up to the
  owning assembly; created loose, that walk returns `None` and the constructor dies on
  `'NoneType' object has no attribute 'Type'`, naming neither the joint nor the assembly.
- **Both references go in through `setJointConnectors(joint, [ref1, ref2])`.** Assigning
  `Reference1`/`Reference2` directly appears to work — they read back correctly — but
  `Placement1` and `Placement2`, which are what the solver actually constrains, stay at the
  identity. The solve then converges immediately having been asked for nothing, and mates the
  two *part origins*: a wrong answer that reports success. Calling `setJointConnectors(joint,
  [])` afterwards to refresh the placements makes it worse, because the empty-list form is
  how the constructor *clears* the references.
- **The sub list needs two entries**, `['Face2', 'Face2']`, not one. `findPlacement` reads
  `ref[1][0]` as the element and `ref[1][1]` as the point on it — the GUI's click. With one
  entry the second read is empty, the function falls through to its whole-part branch and
  returns the identity, which is the same silent failure as above. Naming the face twice
  selects its centre of gravity, which is what a scripted assembly wants, having no click.

Referencing as `(part, [...])` rather than `(assembly, ['BoxA.Face2', ...])` also matters: the
path form assigns and reads back, but it makes a joint inside the assembly depend on the
assembly — `The graph must be a DAG`, and the joint stays touched after every recompute. The
path form is for reaching into a nested sub-assembly.

The pattern in all three: **the failure is a successful solve of the wrong constraint.** None
of them raise, and a spike that only asserted "the solver moved something" would have passed
on every one. The spike asserts the mated faces are coincident on the solved shapes instead,
which is a claim about the geometry rather than about the API having been called.

## IP-FC-49 — the tiling fuse stops working when the part gets big

With IP-FC-48 fixed, the bulkhead was built across the whole (U, panel) grid. The result is
a clean threshold:

| U | 0mm | 1/32in | 1/16in | 1/8in | 3/16in | 1/4in | 1mm | 3mm | 6mm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.5 – 2.0 | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| 2.5 – 4.0 | **FAIL** | — | — | **FAIL** | **FAIL** | **FAIL** | — | **FAIL** | **FAIL** |

(`—` is a combination `bulkhead_validity_check` rejects.) Every valid panel fails at U ≥ 2.5
and every one builds at U ≤ 2.0, so the panel has nothing to do with it. The corner is
unaffected across U = 1.0 … 4.0 at every FX.

The octant is valid. Its mirror is valid. **Only their fuse is invalid** — `TileXy`, and then
everything downstream of it. That points straight at the one thing the fuse depends on: the
`eps` overlap that `bulkhead_full` deliberately introduces so the two halves interpenetrate
rather than meet exactly. `eps` is an absolute 0.01 mm and does not scale, so on a 250 mm
part the sliver is 4 × 10⁻⁵ of the geometry and falls under what OCCT's boolean resolves.
Confirmed by raising it: at U=2.5, `eps` = 0.01 fails and 0.05, 0.1, 0.25 and 0.5 all
produce a valid single solid.

### The overlap should not be scaled — it should not be there

Raising `eps` was first recorded here as a decision with three costed alternatives
([OQ-ARCH-10](../architecture/freecad_migration.md), now withdrawn), all of which took for
granted that the fuse needs an overlap at all. **It does not.** The overlap was added so
*OpenSCAD's* union would resolve a mirrored solid reliably; whether OCCT wants the same
favour is a measurement, and it had not been made:

| Fuse of a solid with its own mirror about the touching plane | 10 mm | 100 mm | 250 mm | 400 mm |
| --- | --- | --- | --- | --- |
| No overlap at all | valid, exact | valid, exact | valid, exact | valid, exact |

So the mask's shift is now `mask_eps`, defaulting to `0`, and separate from `eps` — cut
overshoot still needs its 0.01 mm and is untouched. The row is named rather than deleted
because a bare `mask_lo` here would give a reader no way to know the OpenSCAD source says
`mask_lo + eps` deliberately.

| U | `mask_eps = 0` | `mask_eps = 0.01` |
| --- | --- | --- |
| 0.5 | valid, 2085.6395 | valid, 2085.6395 |
| 1.0 | valid, 7122.0983 | valid, 7122.0983 |
| 2.0 | valid, 39413.1120 | valid, 39413.1119 |
| 2.5 | valid, 76221.3114 | **fails** |
| 3.0 | valid, 129272.8964 | **fails** |
| 4.0 | valid, 304571.8350 | **fails** |

**Removing it does not move the part** — the full volume is identical to seven figures,
because the sliver really was being reclaimed by the union. OpenSCAD parity is unchanged at
+0.00023%.

What does change is the tiling check, and it gets stronger. `bulkhead_full`'s docstring used
to argue that the full part being *less* than eight octants is what makes the tiling
verifiable. With the overlap gone the relation is exact equality:

| U | full − 8 × octant, `mask_eps = 0` | with the overlap |
| --- | --- | --- |
| 1.0 | −0.0000 | −3.6477 |
| 2.0 | −0.0736 | −10.2960 |
| 4.0 | −0.3429 | would not build |

"Matches 6926.15" is a number with no independent meaning; "eight pieces tile with neither
gap nor overlap" is a statement about the geometry, and a mirror about the wrong plane still
fails it.

The (U, panel) grid that found this is now `ok` in every cell — all 88 FreeCAD-routed
bulkheads build, where U ≥ 2.5 was previously a total loss. The IP-FC-10 reference part is
unmoved: 6922.5296302 mm³ against OpenSCAD's 6922.5048968, **+0.000357%**, versus the
+0.00035% recorded when IP-FC-10 was verified.

**Three self-check constants moved, and the OpenSCAD numbers are no longer the right ones for
two of them.** The intermediate stages legitimately differ now — OpenSCAD's octant is
oversized by the sliver and FreeCAD's is exactly an eighth — while the finished part does
not:

| Module | Was (OpenSCAD) | Now (`mask_eps = 0`) | |
| --- | --- | --- | --- |
| `bulkhead_cuts` | 49813.5203117, bbox from −59.99 | 49811.7251270, bbox from −60.0 | tool, differs by construction |
| `bulkhead_section` | 865.7690714 | 865.3140969 | octant, differs by construction |
| `bulkhead_full` | 6922.5048968 | **unchanged** | the part, still +0.00011% |

*(All three moved again on 2026-08-11, when IP-FC-51 made the greeble tool's snap rib nominal:
the octant lost 0.0290279 and the part 0.2322237, exactly eight times it. The columns above are
left at the values that made **this** change legible.)*

The `−59.99` in the old expected bounding box is the clearest sign of what had happened: an
arbitrary-looking constant that is exactly `−60 + eps`, sitting in a check that was asserting
the workaround rather than the geometry.

**The generalisable part.** A constant carried across in a port is a claim about the *source*
toolchain. `eps` encodes what CGAL wanted; nothing had checked what OCCT wants. The question
worth asking of any such constant is not "what should its value be here" but "does it belong
here at all" — and the first version of this section skipped straight past that to costing
three ways of choosing a value. ⚠️ `eps` still has a second job, making cuts overshoot the
material they pass through, and that job is real on both kernels — which is why `mask_eps` is
a separate row rather than `eps` being set to zero.

> ⚠️ **The last sentence is falsified.** Cut overshoot is *not* real on both kernels: IP-FC-50
> measured it and OCCT does not need it either. The paragraph is left standing because its own
> lesson is the reason — it asked "does this constant belong here at all" of the overlap, then
> assumed the answer for the overshoot in the very next sentence without measuring it. The
> generalisation was right and it was not applied one line later.

## IP-FC-50 — asking the same question of the other two jobs

IP-FC-49 established the principle and applied it once. `eps` was doing three different things
under one name, and only one of them had been examined:

  **A. Union overlap** — two solids that meet on an exact shared plane are made to
  interpenetrate before being fused. Settled by IP-FC-49: OCCT does not want it.

  **B. Cut overshoot** — a subtractive tool is made to poke out past the face it cuts through
  rather than ending flush with it. Assumed real, never measured.

  **C. A real dimension** — `eps` appears inside an expression that sizes material, so removing
  it moves a surface. Not a robustness margin at all, and easy to mistake for one.

[`spike_eps.py`](../../src/Fuselage/freecad/spike_eps.py) measures B directly: a bore cut clean
through a slab and a notch cut in from a side, flush against padded, at 10, 100, 250 and 400 mm
— because IP-FC-49's failures were scale-dependent and 0.01 mm is 1e-3 of a 10 mm part and 4e-5
of a 250 mm one. **The pad buys nothing.** Identical volumes to machine precision, all valid,
one solid, and the same face count. The abutting fuse is likewise clean, and the *padded* fuse
carries two extra faces.

So the ±eps pad on every cut tool in `corner_tree._section` is gone. It could not have changed
the result — the tool already passed through the whole body, so it removes the same material at
0 as at 0.01 — and the verification confirms it: all four section volumes and the 52-face count
came back byte-identical. `boom_oml` was separately found still carrying IP-FC-49's mask overlap
and now uses a `mask_eps` row like `bulkhead_cuts`; there the shift could not move the answer
either way, since each octant's overhang past the mirror line lies inside its own mirror image.

### The exception, and why a clean spike result was nearly the wrong lesson

The spike also tests a tool face **tangent** to a curved one, since several sites size a
straight-edged tool exactly to a radius. That came back exact at every scale. It would have
been easy to stop there.

`corner_tree`'s greeble wedge is the counterexample. Its flanks sit at
`greeble_nub_radius + eps`, tangent-plus-a-hair to the nub cylinder they cut across. In exact
arithmetic the eps is unnecessary — a tangent flank still leaves the tool covering the whole
chord — so removing it should change nothing. **OCCT under-removes by 0.0199 mm³**, leaving
`EndCutGroove` at 551.847453 instead of 551.827595.

The difference is what the tangency is *doing*. In the spike the tangent plane bounds nothing
that gets removed, so no intersection curve is ever constructed and the answer is trivially
exact. In the wedge it bounds a cut region, so OCCT must intersect a plane with a cylinder it
only touches. **Tangency is safe when it is incidental and unsafe when the boolean depends on
it** — and a spike that measures only the incidental case will report that it is safe.

### Why the audit is per-site and not a single switch

Forcing every `eps` in `corner_tree` to zero moves the assembled part by −0.00094 mm³ on
10396 — −9e-6% — and drops it from 52 faces to 48. That looks like a licence to delete the
constant outright. It is not: the near-cancellation is two errors of opposite sign, the wedge's
under-removal against genuine losses elsewhere. Per section the same run moves `EndCutGroove` by
−0.17% and `MidSection` by −0.05%, because the three axial sections deliberately overlap
(`end_h = bt + eps`, `mid_z0 = 2·bt − eps`) and, unlike the octant mask, that overlap is *not*
free — where two cross-sections differ, sliding one by eps moves real material.

That axial overlap remains in place. Removing it is defensible on IP-FC-49's precedent and would
leave the finished part unchanged for practical purposes, but it turns two per-section references
into "deliberately not the OpenSCAD number", and no failure currently forces the question.

### Category C is where the real defect was

Two sites turned out to be C rather than B, and one of them was a genuine defect. The
greeble-forming tool calls `corner_end(U, bulkhead_thickness + 2*eps, …)` for overshoot — but
`corner_end` derives `greeble_nub_height = bulkhead_thickness/3` from that same argument, so the
overshoot inflates the snap rib to 2.00667 mm against the corner post's 2.00000. The `-eps`
shift afterwards nearly cancels it, leaving the nub band centred and only 0.0067 mm too tall,
which is why it had gone unnoticed. It is 3% of a layer height and no printed part is affected,
but the design states all snap clearance is carried once on the corner's bore, and the code
asserts exactly that for the bore while the rib quietly carried a second clearance.

Written up as [OQ-DES-B12](../design/bulkhead.md), decided the same day as alternative 1, and
implemented as IP-FC-51. **The fix lands in the OpenSCAD authority rather than the port**, even
though IP-FC-50 shows the FreeCAD path needs no overshoot at all, because IP-FC-13 compares the
two backends and correcting one alone leaves a standing divergence.

One thing only showed up in the doing. The obvious reading of "extend the extrusion only" is
wrong: `corner_end` dimensions the greeble **bore** from the same thickness argument, so an
overshoot that moved the body and not the bore would have left the post's ends formed flush
while appearing to preserve the old behaviour. The argument now reaches both and nothing else —
the four nub vertices stay dimensioned from the thickness.

Two independent checks say it landed correctly rather than merely plausibly. `ref_end`, the
corner's own end section, is **bit-identical** across the change at 551.815740, which is what
says the fix touched only the caller that was misusing the argument. And the two kernels agree
on the *size* of the octant's change — −0.0290279 against −0.0290299, to 2e-6 mm³ — which is a
stronger statement than either regenerated number on its own, because a regenerated reference
can always be made to agree with whatever the code now does. The assembled part lost exactly
eight times the octant's change, so the tiling was not disturbed.

The rib equality is **asserted** now, not printed. It was printed before, on every run, reading
`2` against `2.0066666666666664`, and that is how it survived.

The second C site, `bulkhead_cuts.clean_r`, pulls a cut tool's radius *in* by eps and has not
been measured. It may be an intended dimension or the same instinct to avoid a flush cut. It
should not be assumed to be either.

## IP-FC-13 — the comparison's floor is OpenSCAD's circle, and it is computable

[`compare_backends.py`](../../src/Fuselage/tools/compare_backends.py) renders the same
variants through both engines and compares measured geometry. Two things it does that the
three existing verification tools do not, both learned the hard way this session:

- **It refuses to count a part FreeCAD never built.** The backend falls back silently for an
  unported kind *or* an unported variant of a ported kind — an interconnect bulkhead, per
  IP-FC-47. Comparing OpenSCAD against OpenSCAD passes while proving nothing, so the tool
  checks for the `.stl.json` definition the FreeCAD path writes and reports fallbacks
  separately rather than as passes.
- **It samples from the real parameter derivation**, by running the sweeps with rendering
  stubbed, so the selection comes from `derived_parameters()` and the validity checks rather
  than from a guess about the space.

Its first run failed a corner at **+0.00222%** against a 0.002% tolerance. The tolerance was
wrong, not the geometry, and the reason is worth stating because it bounds every comparison
this project will make:

**This was already predicted; what was missing was the number.** [§Verification](#verification)
below states that the OpenSCAD corpus is faceted, that its `cylinder()` is an inscribed
prism, and that the difference is therefore systematic with a predictable sign. All true.
But a prediction of the *sign* does not let you set a tolerance — that needs the magnitude,
and the magnitude is computable rather than empirical.

`$fa=1` caps a circle at 360 segments, and an inscribed regular n-gon under-measures its
circle by `1 − (n/2π)·sin(2π/n)`:

| Segments | Area deficit |
| --- | --- |
| **360** (the cap, and so the floor) | **+0.005077%** |
| 720 | +0.001269% |
| 1440 | +0.000317% |

FreeCAD reads larger because its mesh is the more accurate one: the B-rep is exact, and
MeshPart at 1e-3 linear deviation puts the STL within +0.00024% of it. The measured corner
deltas sit under the floor and scale with how much of the part is round — +0.00121% at U=1,
+0.00222% at U=2.

So a tolerance tighter than ~0.005% does not detect modelling error; it detects OpenSCAD's
circle approximation. The tiers are now 0.006% for exactly-reproducible kinds and 0.010%
where real fillets add surface-vs-facet error on top. Bounding boxes stay at 5e-4 mm
absolute, which is the interface check standing in until IP-FC-36 enumerates the dimensions.

First clean run, 2026-08-10, spread across U and both kinds:

| Part | OpenSCAD mm³ | FreeCAD mm³ | Delta |
| --- | --- | --- | --- |
| `U_0.5 bulkhead_end_anchor 1/32in` | 2167.172203 | 2167.149964 | −0.00103% |
| `U_0.5 corner_FX_0.5 1/32in` | 1202.621364 | 1202.641361 | +0.00166% |
| `U_1.0 bulkhead_end_bolt 3mm` | 6781.365193 | 6781.380436 | +0.00022% |
| `U_1.0 corner_FX_2.5 3mm` | 35887.460602 | 35887.829500 | +0.00103% |
| `U_2.5 bulkhead_end_bolt 1/8in` | 74224.377841 | 74223.833140 | −0.00073% |
| `U_2.5 corner_FX_1.5 1/8in` | 329651.979897 | 329658.511523 | +0.00198% |

Two things in that table matter more than the pass.

**The U=2.5 bulkhead is a part that could not be built at all four fixes ago** — IP-FC-49
had the tiling fuse failing above U=2.0. It now agrees to −0.00073%.

**The sign splits by kind, and that is the model working rather than noise.** Corners run
positive, bulkheads negative. Faceting makes circular features smaller than the true circle,
so an *additive* cylinder (the corner's outer radius) makes OpenSCAD read low — positive
delta — while a *subtractive* one (the bulkhead's bores) removes less material and makes it
read high. §Verification's claim that the sign is predictable per feature holds, and it is
why a delta in the unexpected direction is worth investigating even when it is inside
tolerance.

**This also puts a ceiling on what IP-FC-34 can ever claim.** Retiring OpenSCAD on the
grounds that FreeCAD reproduces it cannot be demonstrated below the faceting floor by volume
comparison alone — past that, agreement has to be argued from the B-rep, or from section
curves and mass properties (IP-FC-33), not from meshes.

### One duplication removed on the way

`export_parameters.py` carried its own copies of the bulkhead and corner parameter mappings,
written when it was the only consumer. The sweep now drives both engines from the same two
mappings in `fuselage_variants.py`, and the export re-exports them. Two copies of a parameter
mapping is the divergence a port is most likely to introduce and least likely to notice:
both copies keep producing a part, and only the values drift.

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

## IP-FC-12 progress — the boom bulkhead is a different kind of part

Started 2026-08-10. The frame bulkhead and the corner are both **octant-and-mirror solids**:
an octant built from boxes, cylinders and cones, tiled by `octant_to_full`. The boom bulkhead
is a **flat profile extruded once**, and its profile is built almost entirely from
morphological offsets — `fillet_inner`/`fillet_outer` four times and plain `offset(r=)` five
more. Nothing ported so far uses either.

`ref_boom_bulkhead.scad` isolates the part and its sub-shapes, at the derived parameters for
U=1.0 `offset_single` 3 mm — one of the 132 valid swept variants, not the hand driver's
values, and taken from `derived_parameters()` directly rather than typed. The 2D shapes are
extruded 1 mm so the volume reads as the area:

| Mode | Shape | Area / volume | Bounding box | vs morphological key |
| --- | --- | --- | --- | --- |
| 0 | `upper_boom_support_centerline_shape` | 556.0000000 | [0, 25] × [40, 43.9] | — |
| 1 | `mirror_x` of it | 1112.0000000 | [−40, 25] × [40, 43.9] | — |
| 2 | `offset(+web_width/2)` — the stroke | 1668.0908114 | [−43, 22.0004] × [43, 46.9] | — |
| 3 | `offset(−web_width/2)` — the erosion | 616.9927776 | [−36.6573, 28.0709] × [36.6573, 40.9] | — |
| 4 | `boom_key_shape` | 166.8606422 | [−7.2000, 17.8000] × [7.2000, 34.2] | −0.00035% |
| 5 | `offset(+boom_key_web_width)` of it | 567.3076947 | [−13.1998, 11.8002] × [13.1998, 40.2] | −0.00067% |
| 6 | `boom_web_outer_shape` | 1899.6654770 | [−43, 11.8002] × [43, 46.9] | −0.00006% |
| 7 | `boom_web_inner_shape` | 411.5218898 | [−33.8288, 30.9520] × [33.8286, 40.9] | +0.00071% |
| 8 | `bulkhead_oml_shape` | 8856.3094939 | [−50, −50] × [50, 50] | — |
| 10 | `bulkhead_web_inner_shape` | 5700.1741175 | [−40.9, −40.9] × [40.9, 40.9] | — |
| 11 | `bulkhead_oml_inner_shape` | 103.0474738 | [−42.05, −42.05] × [42.05, 42.05] | — |
| 12 | `bulkhead_oml_outer_shape` | 8959.3433819 | [−50, −50] × [50, 50] | — |
| 9 | `boom_bulkhead` | **7433.4744903** | [−50, −50, 0] × [50, 50, 2] | −0.00008% |

The last column is the effect of OQ-DES-B11's direct fillet construction for the key, adopted
2026-08-10. Modes 0–3 and 8 do not involve the key and are bit-identical; the five that do move
by less than 0.0008%, and the part's bounding box does not move at all. **Mode 4's bounding box
is now exactly ±7.2000 where the morphological form gave ±7.1999.** 7.2 is
`boom_diameter/2 + collet_thickness + tolerance` — the surface that fits the boom tube — and the
closing was quietly eroding it by 1e-4 mm. Nothing depended on that, but a fit dimension being
exact rather than nearly right is the better of the two.

**The offset degeneracy cannot arise from the web.** `ref_offset2d.scad` documents a knife
edge where a limb is exactly twice the offset radius. Across all 132 valid variants
`web_width = 6U` and `web_fillet_radius = 2U`, so `web_width / (2 · web_fillet_radius)` is a
constant **1.5** — eight distinct parameter groups, none at 1.0. `boom_key_web_width` tracks
`web_width` exactly and `boom_key_radius` is `max(U/2, 1/2)`. The two quantities scale
together by construction, so this is a property of the parameter derivation rather than of
the values that happen to be swept.

**Which construction the profile uses was [OQ-DES-B11](../design/bulkhead.md), decided
2026-08-10: split by intent.** True fillets on `boom_key_shape`, which is a named corner round
with a fixed count of four; the morphological chain everywhere else, because the other four
sites apply the operator to whole compound regions whose concave-corner set moves with the
parameters. OQ-DES-B9 stays decided for what it actually governed — the frame bulkhead's four
named fillets and its chamfer, none of which reach `fillet_inner`.

### The key's fillets, direct — done in OpenSCAD first

The decision's own instruction was to change and verify the OpenSCAD path before porting
anything, which is the right order: it separates "is this the shape we want" from "does FreeCAD
reproduce it", and the second question is worthless while the first is open.

Reading the morphological pair is what makes the direct form obvious. `fillet_inner` is an
*opening* clipped to its input, so it rounds the tab's two **convex** top corners;
`fillet_outer` is a *closing* unioned with its input, so it fills the two **concave** junctions
where the tab meets the collet. Four arcs of one radius at four computable centres, and nothing
else — the junction gusset is a box `[a, a+r] × [ty, yc]` minus the collet and minus the fillet
disc, which needs no clipping of its own because its other three sides already lie inside one or
the other.

Measured against the shape it replaces, at all 24 distinct key geometries the sweep builds:

| | Worst | Tolerance |
| --- | --- | --- |
| Symmetric difference, as a fraction of area | **0.00522%** | 0.0060% |
| Whole part (`ref_boom_bulkhead` mode 9) | −0.00008% | — |
| Bounding box, whole part | **unchanged** | — |

Both halves of the symmetric difference are measured, not the net: equal amounts of added and
removed material would cancel in a volume comparison and read as a perfect match. The relative
error *falls* with `U`, 0.0052% at 0.5 down to 0.0004% at 4, which is fixed-angular
tessellation on a growing part rather than a construction error.

**The domain probe is the part worth keeping.** `boom_key_validity_check()` requires
`key_width` and `key_height` to be at least twice `key_radius`, and `key_width` below the
diameter of the hole the collet passes through — `2 · (boom_diameter/2 + collet_thickness +
tolerance)`, not the boom tube. Across the corpus those ratios are 2.000, 2.000 and 0.270; the
guard excludes none of the 132 variants, because `key_width` and `key_height` are both
`max(2·U, 2)` while `key_radius` is `max(U/2, 1/2)`, making each exactly four radii at every
`U`.

Each limit is where the construction stops existing rather than a chosen threshold. The width
limit *is* the singularity: `yc = sqrt((cr + r)² − (w/2 + r)²)` goes imaginary at exactly
`w = 2·cr`. The height limit is what holds the junction fillets clear of the cap fillets, since
the junction tangent point is at most `cr + r` and the cap starts at `cr + h − r`.

That the guard excludes nothing does not make it decorative, because **the two constructions
fail differently outside the domain.** Swept at `U` = 1 across `key_width / 2·key_radius`:

| `w / 2r` | 0.40 | 0.80 | 1.00 | 1.10 | 2.00 |
| --- | --- | --- | --- | --- | --- |
| direct | 164.7256 | 164.7427 | 164.8325 | 165.0331 | 166.8606 |
| morphological | 162.8630 | 162.9671 | 163.2665 | 165.0341 | 166.8612 |

The morphological form collapses to 162.86 — the bare collet, **tab deleted**, because an
opening removes any protrusion thinner than twice its radius. The direct form returns a defined
shape throughout, whose cap is simply wider than the tab it caps once the two corner arcs cross
over. Trading a loud failure for a plausible-looking wrong part is the trade this migration can
least afford, and it is why the check is enforced rather than documented.

One thing fell out that was not the point: `boom_key_shape`'s bounding box is now exactly
±7.2000 where the morphological form gave ±7.1999. That is
`boom_diameter/2 + collet_thickness + tolerance`, the surface that fits the boom tube, and the
closing had been eroding it by 1e-4 mm.

### Coplanar unions must be built from cuts, not fuses — and this is not an open question

The boom bulkhead is the first part built **in the plane** rather than in space, because
`Part::Offset2D` operates on faces. That turned out to expose a trap with the same shape as
IP-FC-46's null tool: a kernel behaviour that is silent until something several nodes away
consumes it.

**`Part::Fuse` and `Part::MultiFuse` over coplanar faces return a `Compound` of abutting faces,
not one face.** The key came out as 15 of them. Its total area was right to 0.005%, so every
check applied to that node passed. `Part::Offset2D` then offsets **each member of a compound
separately**, interior shared edges included:

| `boom_key_shape`, then `offset(r = 6)` | Faces | Result | vs OpenSCAD 567.3077 |
| --- | --- | --- | --- |
| fuse chain | 15 | 2434.8653 | **+329%** |
| this route | 1 | 567.3384 | **+0.0054%** |

The +329% comes back as a closed, valid, plausible region with no warning of any kind.

Nothing in the obvious set reaches one face. `Part::Refine` is `ShapeUpgrade_UnifySameDomain`
and **cannot unify across a compound**; `Part::MultiFuse` with `Refine = True` is still a
compound; `Part::FaceMakerBullseye`, `…Simple` and `…Cheese` each rebuild the 15 fragments,
because the union's outer boundary is itself split across several wires — `Part::Face` on the
longest wire gives one face of 148.51 mm², 11% short, since the longest wire is not the outer
boundary. Only the **scripted** `shape.multiFuse(…)` unifies: it returns a `Shell`, which
`removeSplitter()` collapses to exactly one face. The document objects never return a shell.

Baking that shell into a `Part::Feature` would work and is the wrong answer — it costs the
parametric editability the port exists to preserve, at nearly every union in the tree.

**`Part::Cut` does not fragment.** So De Morgan gets there in stock document objects: cut every
piece out of an enclosing rectangle, then cut that result back out of the same rectangle.
`R − ((R − a) − b − …)`. Two extra nodes per union, the tree stays live, and the result is one
face.

**The rectangle must strictly enclose every piece, in the frame the union happens in.** If it
does not, the union silently truncates to whatever the rectangle held — measured at −9.42% on a
first attempt that sized the rectangle for the placed key while the pieces were still in local
coordinates. `union_reach` is therefore built from every term that can push material outward and
then doubled, exactly as `mask_reach()` does in `shape_modifier_utils.scad`, and `boom_key.py`
asserts both invariants after recompute: one face, and clear of the rectangle's own edge.

This is a measurement rather than a decision, in the same way as OQ-ARCH-3, OQ-ARCH-8 and
OQ-ARCH-10. It was on its way to being written up as an open question about how to build 2D
profiles at all — sketches, a scripted feature, a 3D round trip — and none of that is needed.
The one thing worth carrying forward is the *convention*: **in 2D, union means cuts**, and any
2D node that yields more than one face is a defect, not a cosmetic difference.

`boom_key.py` is the first module built this way. It verifies against both of the reference
table's key rows: mode 4 at **+0.00516%** with an exact bounding box, and mode 5 — the same key
dilated by `boom_key_web_width` — at **+0.00541%**.

### The web spine — a sketch, and a vertex count that moves with the boom position

[`boom_web.py`](../../src/Fuselage/freecad/boom_web.py) ports
`upper_boom_support_centerline_shape` and the two shapes offset from it. The spine is a
**centreline**, not an outline: the web is what you get by stroking it to `web_width`, the way
a road is a centreline stroked to its width. So the port is one sketch and then offsets.

**It has to be a sketch.** `Part::Polygon` takes its vertices as a plain list of vectors, and a
list of vectors cannot carry expressions — every one of these seven vertices is a function of
the sheet. A fully constrained `Sketcher::SketchObject` with each vertex pinned by an
expression-driven `DistanceX`/`DistanceY` is the parametric equivalent, and `corner_tree._sketch`
already had it.

**Its first two vertices coincide whenever the boom sits on the centreline.** The source writes
`[0, z]` then `[boom_y_position, z]`, a zero-length edge at `y = 0` — harmless in OpenSCAD, an
unsolvable sketch here. Two of the three swept boom types (`offset_single`, `center_single`) sit
at `y = 0` and `dual` does not, so the spine genuinely has **six edges for two types and seven
for the third**. That is a topology change across the corpus, not a guard against nonsense, and
both branches are measured rather than one:

| Shape | `offset_single` (6 edges) | `dual` (7 edges) |
| --- | --- | --- |
| `centerline` | 556.0000000, **exact** | 756.0000000, **exact** |
| `mirror_x` of it | 1112.0000000, **exact** | 1512.0000000, **exact** |
| `offset(+web_width/2)` | +0.00035% | +0.00033% |
| `offset(−web_width/2)` | +0.00014% | +0.00003% |

The polygon areas are exact rather than merely close because nothing in them is curved — the
faceting floor only applies where a circle is involved. Every shape is a single face and clear
of its `union_reach` rectangle, both asserted after recompute.

### The two region-wide web shapes, and an invariant that was too strong

[`boom_webs.py`](../../src/Fuselage/freecad/boom_webs.py) ports the first two sites OQ-DES-B11
kept morphological — `fillet_outer` and `fillet_inner` applied to whole compound regions rather
than to named corners — as `Part::Offset2D` chains:

| Shape | FreeCAD | OpenSCAD | Delta |
| --- | --- | --- | --- |
| `boom_web_outer_shape` | 1899.6781134 | 1899.6654770 | +0.00067% |
| `boom_web_inner_shape` | 411.5121334 | 411.5218898 | −0.00237% |

**`boom_make_vert_web` swaps an erode with a mirror, and the two do not commute.** The source
builds the eroded web as `mirror_x(offset(−w/2)(spine))` when the flag is set and
`offset(−w/2)(mirror_x(spine))` when it is not. Eroding *before* mirroring erodes each half
against its own boundary, so material survives on the mirror line that eroding afterwards
removes — which is the vertical web the flag is named for. `offset_single` and `dual` set it,
`center_single` does not. Note that `ref_boom_bulkhead.scad` mode 3 is the **unset** ordering,
so it is deliberately not the shape the inner web starts from; reading it as such would have
produced a shape that verifies against the wrong reference.

**The one-face invariant was wrong, and the inner web is what showed it.** `plane2d.report`
flagged the inner web as fragmented at two faces. It is not fragmented — it is genuinely
**disconnected**, one island either side of the key pad, and OpenSCAD's is too. `Part::Offset2D`
handles disjoint islands correctly; what it gets wrong is *adjacency*, offsetting shared
interior edges as though they were boundary. So the invariant is **"no two faces share an
edge"**, not "exactly one face" — checked by comparing the faces' own edge totals against the
shape's unique edge count, which differ exactly when some edge is shared. Re-tested on all three
cases it has to separate: the fused compound of 15 abutting patches reports fragmented, the
cut-built union does not, and two disjoint circles do not. A face count would have rejected a
correct shape and taught the reader to expect the wrong thing.

### The OML outline, and where the port stands

[`boom_oml.py`](../../src/Fuselage/freecad/boom_oml.py) ports `bulkhead_oml_shape` in the plane
— the same outline the frame bulkhead reaches as a 3D octant through `bulkhead_cuts.py`, built
the way the source builds it: one octant in a corner-local frame, moved out to its corner, then
tiled by three nested mirror-unions. `mirror_xy` reflects across `y = x`, which is
`Part::Mirroring` with a normal of (1, −1, 0) — the one of the three that is not an axis plane.
It agrees at **−0.00029%** with an exact bounding box.

Seven of the reference table's ten rows are now ported and verified:

| Mode | Shape | Delta | Module |
| --- | --- | --- | --- |
| 0 | `upper_boom_support_centerline_shape` | **exact** | `boom_web.py` |
| 1 | `mirror_x` of it | **exact** | `boom_web.py` |
| 2 | `offset(+web_width/2)` — the stroke | +0.00035% | `boom_web.py` |
| 3 | `offset(−web_width/2)` — the erosion | +0.00014% | `boom_web.py` |
| 4 | `boom_key_shape` | +0.00516% | `boom_key.py` |
| 5 | `offset(+boom_key_web_width)` of it | +0.00541% | `boom_key.py` |
| 6 | `boom_web_outer_shape` | +0.00067% | `boom_webs.py` |
| 7 | `boom_web_inner_shape` | −0.00237% | `boom_webs.py` |
| 8 | `bulkhead_oml_shape` | −0.00029% | `boom_oml.py` |
| 10 | `bulkhead_web_inner_shape` | −0.00073% | `bulkhead_web.py` |
| 11 | `bulkhead_oml_inner_shape` | +0.02735% | `boom_oml.py` |
| 12 | `bulkhead_oml_outer_shape` | +0.00018% | `boom_oml.py` |
| 9 | `boom_bulkhead` | **−0.00039%** | `boom_bulkhead.py` |

Modes 10 and 11 were added to `ref_boom_bulkhead.scad` on 2026-08-11 and mode 12 the same day;
all three, and then the assembled part, were ported and verified on 2026-08-11.

**Mode 11 needs a looser tolerance than everything else here, and the reason is not
disagreement.** The 0.0060% floor is what `$fa = 1` costs when it caps a circle at 360 segments.
These circles are small enough that `$fs = 0.1` caps them near 128 instead, which puts the
polygon 0.04% under a true circle. In mode 8 those same bores are 1% of the area and the deficit
vanishes into 0.0003%; measured alone they are the whole shape and it does not. FreeCAD's circles
are exact, so the port reads high. `plane2d.report` now takes a tolerance, and `boom_oml.REFS`
is the only place that raises it.

**Mode 12 was added rather than inferred.** `bulkhead_oml_outer_shape` has no call site of its
own in the assembly, so the obvious move was to take it as mode 8 + mode 11. That would have been
wrong by 0.0136 mm²: the bores are not entirely interior to the outline, so the two do not simply
add. Small, but it is exactly the sort of number that later gets blamed on the kernel.

**Mode 10 is not shaped like the other four `fillet_inner` sites, and an earlier reading of why
was wrong.** The note here on 2026-08-10 said its `translate(−arm, −arm)` and `octant_tiled`'s
`corner_translate` do not cancel. They cancel exactly. What actually distinguishes it is that its
three operands are **region-wide** — the whole outer outline, `fillet_inner(web_fillet_radius)`
over `offset(−web_width)` of the whole OML, and a wedge triangle — so with the translates gone the
intersection is evaluated in world coordinates. Every other `*_octant` module in
`fuselage_bulkhead_geometry.scad` really is drawn corner-local; this one is a window onto a
whole-region computation.

That makes the tiling redundant, provably rather than approximately. The eight images of the
wedge tile the square of half-width `unit_width/2`, which contains the outline; the two
region-wide operands are each invariant under all eight symmetries; so the tiled union of the
clipped intersection is the unclipped intersection. `bulkhead_web.py` builds it region-wide on
that argument and the reference confirms it to 0.0007%.

The trap is the other direction, and it is the one this port keeps meeting: compute the operands
*locally*, one octant's worth of outline eroded on its own, then tile. That gives a closed, valid,
plausible region and a wrong one, because an erosion of one wedge sees boundary where the full
outline has none.

The assembly is `OML − fillet_inner(OML − MAT) − KEY`, where `MAT = (RIM ∪ WEBS) − BORES`,
`RIM = OML − mode 10`, and `WEBS = mode 6 − mode 7 − mode 4`. **The double negation is load-
bearing.** `MAT` is everything that must be kept, so `OML − MAT` is everything that may be
removed, and rounding *that* before subtracting it is what gives the lightening pockets their
radii and drops any sliver narrower than twice the radius instead of cutting it as a knife edge.
Subtracting `MAT` directly would give the same pockets with sharp corners. `BORES` comes off the
material rather than the profile for the same reason — the bores are places the pocket is allowed
to reach, not holes punched afterwards.

Every mode is inside its stated tolerance, and every 2D one satisfies both invariants: no two
faces sharing an edge, and clear of its own enclosing rectangle. The assembled part is one valid
solid with the reference's bounding box.

**Two ordering bugs, one lesson.** Both `bulkhead_web` and `boom_bulkhead` first wrote their tip
as `node.Base = build_the_operand(doc)`, which creates the consuming node *before* its dependency.
FreeCAD's first recompute pass then reaches the consumer while that dependency still holds a null
shape: `Access violation` and `No object linked` on stderr, after which a later pass quietly
recomputes it correctly. The final numbers were right in both cases, so the only symptom was a
line of stderr that is easy to read past. Build dependencies first.

### The lower web, and the second boom type

`boom_make_lower_web` was ported the same day. It adds a second pair of web shapes evaluated at
`−boom_z_position` and `180 − boom_key_angle` and mirrored in y, and **it is a second evaluation
of the web builders, not a mirror of the first** — the `bulkhead_tree` pattern. The key is what
makes the difference: at the reflected angle the tab faces the other way, so the pad the web
grows around it is a different shape.

That distinction is worth the space because a lower web built by mirroring the upper one lands
close enough to look right. At `center_single` the upper web's outer shape is 2868.85 and the
lower's is 2888.83 — 0.7% apart, on a term that is itself a fraction of the part. It would have
shown up in the assembled volume as a few tenths of a percent and been easy to blame on
faceting.

Only two inputs change, and every derived row in `boom_key` and `boom_web` is independent of
both — collet and tab dimensions, frame turning points, and a `key_reach` that takes an absolute
value. So the second evaluation reads the same sheet rows and adds two of its own,
`lw_boom_z_position` and `lw_boom_key_angle`. The builders gained a `tag` for node names and
expressions for those two inputs; nothing else moved.

[`ref_boom_bulkhead_center.scad`](../../src/Fuselage/freecad/ref_boom_bulkhead_center.scad) is
the second boom type, `center_single`, at `derived_parameters(1.0, 1.0, center_single, 3 mm)`.
Exactly three assignments differ from `offset_single` — `boom_z_position` 25 → 0,
`boom_make_vert_web` true → false, `boom_make_lower_web` false → true — and `boom_bulkhead.py`
carries the same three as a variant overlay that replaces those rows' *definitions*, so
everything derived from them follows rather than being restated. Its modes 16 and 17 are
transcriptions rather than module calls, because the mirrored web is written inline inside
`boom_bulkhead` and has no module of its own; they exist to localise a disagreement, and mode 9
is what binds the port.

| shape | FreeCAD | OpenSCAD | delta |
| --- | --- | --- | --- |
| `boom_bulkhead`, `offset_single` | 7433.4457899 | 7433.4744903 | −0.00039% |
| `boom_bulkhead`, `center_single` | 8296.0889991 | 8296.1222588 | −0.00040% |
| the lower web's outer shape | 2888.8591480 | 2888.8332161 | +0.00090% |
| the lower web's inner shape | 1265.7250873 | 1265.7236228 | +0.00012% |

`dual` shares `offset_single`'s flag settings, so all three swept boom types are now covered by
one or other of the two references.

### Wiring the kind into the sweep — the harness knew only one bulkhead

The geometry was ready before the harness was. All 25 parameters of the `boom_bulkhead()`
signature already existed in the sheet as seedable literals under their OpenSCAD names, and
`emit(doc, seed)` already took a seed. **The obstacle was upstream, in the export**, and it was
not a missing row in `part_kinds.KINDS`.

`render_variant.py` and `export_parameters.py` enumerated the *frame* bulkhead's three axes and
nothing else. `export_parameters.py` reached them by importing `combinations()` from
`render_variant.py`, which held a module-level `CSV_AXES` naming `bulkhead_type_variants.csv`.
So every boom variant answered "no such combination", and the only way to render one at a time
was to call `read_all_param_axes` / `flatten_param_space` / `derived_parameters` by hand — which
is what verifying `center_single` took.

**A bulkhead family is now a table row rather than a hard-coded axis tuple.**
`fuselage_variants.BULKHEAD_FAMILIES` states, for each of the two, its type axis, every validity
check its sweep applies, its parameter mapping, its render and filename functions, and the part
kind `build_part.py` knows it by. The two share the panel and size axes, which are stated once
as `SHARED_AXES` so no caller can assemble the frame bulkhead's panel axis with the boom's size
axis. Three tools read the table instead of carrying half of it.

The type name selects the family — `family_of()` reads both type CSVs and refuses a name that
appears on more than one — so `render_variant.py 1.0 end_bolt 3/16in` and
`render_variant.py 1.0 center_single 3mm` both work with no extra argument, and the no-argument
listing covers both families with a `family` column. The count is 132 valid boom variants out of
216, against the frame bulkhead's 148 of 360.

**`boom_bulkhead_render` was the last inline parameter list.** It named all 25 arguments in the
call, which is exactly the duplication `bulkhead_parameters` and `corner_parameters` exist to
prevent: two copies both keep producing a part and only the *values* drift.
`boom_bulkhead_parameters(dp)` now feeds the OpenSCAD call, the FreeCAD build and the export
from one definition. Unlike the frame bulkhead's mapping it carries the two flags,
`boom_make_vert_web` and `boom_make_lower_web`, because they come off the type axis as their own
CSV columns and the port reads them as ordinary sheet rows — leaving them out would hand the two
backends different information about the same part.

**The export's third table is named, not shared.** A boom variant writes `boom_parameters` and
neither `parameters` nor `corner_parameters`: it is one part, and it has no corner, because the
corner is a frame part that does not vary with where the boom sits. Reusing the name
`parameters` would have been less code and a worse failure — a boom bulkhead seeded from a frame
bulkhead's table would find none of its eleven boom rows in the seed, leave every one of them at
its module literal, and build the *reference* configuration under the swept variant's filename.
`check_seed` would not catch it, because it only compares aliases the seed actually supplies. A
separate name makes it a missing table instead, and `parameters.table_of` says which two files
were confused rather than raising a `KeyError` on a dict key.

That refusal is written to stderr and flushed before the exit rather than carried in the
`SystemExit`, for the reason `build_part.build` already records about `check_seed`: freecadcmd
discards the message either way, so the obvious spelling produces a part that silently never
appears. Told apart from a sweep-written definition by the presence of `kind`, which only the
sweep's document carries — the old test looked for `corner_parameters`, which a boom variant has
no reason to contain.

**Two checks needed a type gate, and the reason is new to this family.** `parameters.py`
compares each module's literals, and each reference `.scad`'s assignments, against the exported
set. The frame bulkhead's five types move no number between them — `end_bolt` and `interconnect`
differ in which branch consumes the values — so its modules and references agree at all five.
The boom bulkhead's three types move three numbers, so its modules can only be measured at the
type they are written at, and `ref_boom_bulkhead.scad` and `ref_boom_bulkhead_center.scad` each
have exactly one type they are true at. Measured against the other, each reports the other
variant's correct answer as an error. Both lists now carry that type, and entries the loaded
variant cannot speak to are skipped rather than failed — including across families, so a boom
export does not fail on the frame bulkhead's modules. What is skipped is said: `corner_tree`
prints "not measured — this variant carries no `corner_parameters` table" rather than a clean
zero, which would be a passing line for a check that never ran.

**The other type's values are checked too, and nothing checked them before.**
`boom_bulkhead.VARIANTS` carries `center_single`'s three overriding rows, hand-typed, and they
are the only statement on the FreeCAD side of what the second boom type is.
`check_variant_overlays` applies the overlay to the module's `PARAMS` and compares the *whole*
resulting literal set against the authority — not just the rows the overlay names, because a row
that should have been overridden and was not is the failure worth catching, and checking only
what the overlay states would confirm it and miss that. Verified by breaking one value: it
reports `boom_z_position` 5.0 against the derived 0.0.

`compare_backends.py` gained the third sweep and one fix that would have been silent. It decides
a part's kind by scanning its filename for a kind name, and both sweeps write into a `bulkhead`
directory — a boom part is `..._boom_bulkhead_offset_single.stl`. Scanning in table order would
have called every boom part a frame bulkhead and compared it at the frame bulkhead's tolerance
against a part the frame sweep never produced. It now matches the longest kind name first.

Measured end to end, `build_part.py` seeded from the export reproduces the module's own
reference numbers exactly — 7433.445790 mm³ at `offset_single`, 8296.088999 mm³ at
`center_single` — and the boom bulkhead now appears in `compare_backends.py` alongside the corner
and the frame bulkhead.

### The defect the sweep found — an outward offset that counts an overlap twice

Sweeping the kind was the point of the wiring, and the first sample it ran caught something.
Eight boom bulkheads spread across the range: seven agreed to 0.0006%, and one — U = 0.75, 1/8 in
panel, `dual` — was **+0.167%**, sixteen times the tolerance for a filleted part.

That shape of result is the informative one. A systematic porting error moves every variant; one
variant wrong by two orders more than its neighbours means a particular corner of the parameter
space, which is exactly what a comparison at a single point cannot find and what IP-FC-46 through
IP-FC-49 already cost this migration once each.

Working down the constituents at that variant located it immediately. The boom web's *inner*
shape was 1.56% small, 3.90 mm² short — and the finished part was 3.84 mm² of profile area large,
which is the same number: less material removed from the webs is a bigger part. Splitting
`fillet_inner` into its three offsets said which step:

| step | OpenSCAD | FreeCAD | |
| --- | --- | --- | --- |
| the shape before the fillet | 267.1895 | 267.1596 | agrees |
| `offset(−r)` | 82.4436 | 82.4187 | agrees — and splits 2 faces into 4 |
| `offset(+2r)` | 458.4831 | **467.4780** | +1.96% |
| `offset(−r)` | 250.5758 | 246.6740 | −1.56% |

**`Part::Offset2D` offsets each face of a multi-face source independently, and does not merge
faces that grow into each other.** That behaviour is correct while the faces stay apart — it is
why `plane2d.fragmented()` deliberately permits several faces and checks only for *shared edges*
— but a positive offset can grow two of them into overlap, and the result keeps both. The shared
area is then counted twice, and every consumer downstream sees a closed, valid, plausible region
that is too large.

It is `fillet_inner`'s dilation that is exposed, and by construction rather than by accident. The
erosion before it exists precisely to pinch the shape apart wherever it is narrower than
`2·radius`, so its output is multi-face whenever the fillet does anything at all — and the
dilation is then asked to grow those pieces back by twice what separated them. This variant is
the only one of the eight where the pieces land close enough to touch.

The fix is the complement trick the port already uses: `R − (R − X)` merges a shape's own
overlapping faces into one, exactly as `plane2d.union` merges separately built pieces. It is
applied at both fillet functions' dilation steps, those being the two places an offset is applied
to a shape the same function has just produced and so cannot assume is a single face. An inward
offset cannot create an overlap, so only the outward direction needs it.

| | before | after |
| --- | --- | --- |
| the failing part | +0.16731% | +0.00086% |

**Every previously verified number is bit-identical across the change** — `R − (R − X)` on a
single face returns that face, so the merge is a no-op everywhere the shape was already whole.
That is the check worth stating: a fix that moved the numbers it was not meant to move would be
indistinguishable, from the reference tables alone, from one that worked.

`compare_backends.py` gained a `--kinds` filter in the same pass, because exhaustive coverage of
*one* kind is the thing worth asking for after a port and `--all` could not express it. A newly
ported kind wants every variant compared; paying to re-render the two kinds already covered is
what makes that run unaffordable, and an unaffordable check is one that does not get run.

### What sweeping the kind turned up, and what is left

Wiring the kind in was worth it for the wiring, and then it paid again immediately. Three defects
that the two-point check the port was verified against could not reach:

| item | found at | cost |
| --- | --- | --- |
| **IP-FC-52** | one sampled variant in eight | +0.167% volume, sixteen times tolerance |
| **IP-FC-54** | three variants of 132 | the part did not build at all |
| **IP-FC-57** | two variants of 132, one cause each | the part did not build at all |

All three fixed, and the full space now passes: **132 of 132 compared, worst deviation 0.00110%
against a 0.010% tolerance**, every bounding box exact. The spread is worth reading — the worst
case is at U=1.0 with a 1 mm panel and the best at U=4.0, and nothing trends with size, which is
what says the remaining disagreement is faceting rather than modelling.

**All three are `Part::Offset2D` returning a null shape, and none of them has the same cause.**
The fix in each case is to compute the same region a different way; the three routes have almost
nothing in common. That is the part worth keeping, because the failure mode gives no hint which
one is needed.

**IP-FC-54 — a shape OCCT could not handle.** Eroding an outline whose holes are already cut,
at a variant where the holes grow past the shrinking boundary, is a question with no good
answer. The fix is an identity that never asks it: `erosion(A − B, r)` is `erosion(A, r) −
dilation(B, r)`, and each half alone is well conditioned. This one is real geometry, and it has
the signature of real geometry — a *band* of failing distances, 3.0 to 5.0 mm, with 6.0 mm
working.

**IP-FC-57(a) — a shape OCCT had made and could not read back.** The fillet chain's `2r`
dilation produced something its own `offset(-r)` rejected. Fixed by doing that dilation as two
dilations of `r` — the same operation, and the same result to every measurable digit, 7009.984015
mm² and 5 faces and 78 edges either way. Only the split one erodes.

**IP-FC-57(b) — the same, from a boolean instead of an offset.** `offset(-r)` of `OML −
MATERIAL` was null. Splitting does not apply, because nothing was split; the shape came out of a
`Part::Cut`. The IP-FC-54 identity did apply, once it was generalised to three operands: the
region is `oml_outer − bores − material`, so erode the outline and dilate the two subtracted
regions. Every operand offsets happily. Their difference does not.

**What separated (a) and (b) from IP-FC-54 was a negative result, not a positive one.** Both
failed at *every* distance — 2.0, 1.0, 0.5, 0.1, 0.01 — under all three `Join` settings, after
`removeSplitter`, after rebuilding the face from its wires, and in half-steps. Meanwhile every
direct measurement said the shape was fine: valid face, one closed wire, nearest non-adjacent
vertices 4.6 mm apart, no arc of the erosion's radius to collapse, no edge under a millimetre.
A shape that is genuinely wrong has a distance that works. Uniform failure means the
representation. The confirmation was reassembling one failing wire from its own edges — same
curves, new wire object — which offsets fine and reproduces the identity's answer to 1e-7.

Two transferable rules, then. When an offset chain fails, look at the *spread* of failing
distances first: a band means the geometry, everything means the representation. And an
equivalent decomposition — split a big offset into two, or push an offset through a difference —
costs one or two nodes, is exact, and is available in both cases.

One thing deliberately not done. The sweep raises on a failed render rather than comparing the
parts it did manage, so each of these was a separate investigation before any comparison numbers
existed at all. A `--keep-going` would have surfaced all three at once. It is worth adding now
that nothing is failing — but it was not worth adding while something was, because its only
effect then is to make a real failure easier to scroll past.

**Still to do on this item:** the cowls.

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

Two questions wanted answers that could not be read out of the code. **Both were answered
on 2026-08-09, along with CW1, CW4 and CW6** — five cowl questions closed in one pass, four
of them by the designer stating intent that the code could not have revealed:

| OQ | Item | Answer |
| --- | --- | --- |
| [OQ-DES-CW1](../design/cowl.md) | IP-FC-44 | Yes, suffix them. Renamed and verified geometry-identical — **done** |
| [OQ-DES-CW2](../design/cowl.md) | IP-FC-28 | `cone_angle` is the **overhang angle from the print bed**, 35°. Both call sites correct; the complementary spellings meet the same face |
| [OQ-DES-CW3](../design/cowl.md) | IP-FC-29 | `buttress.thickness` is the **cut** that produces the rib through slicing — a slicer tolerance, not part geometry. Printed rib is `2·w·n_perimeters + t_cut` |
| [OQ-DES-CW4](../design/cowl.md) | — | Buttress scaling is intended and already correct. Placement becomes a list at the port; general siting deferred |
| [OQ-DES-CW6](../design/cowl.md) | IP-FC-17 | Model the rib nominally, **keep the notched blank as the print export** — cowls print in spiral vase mode, which a modelled wall would destroy |

**The one that changes the plan is CW6.** It was the only blocking cowl question, and its
answer both unblocks IP-FC-17 and IP-FC-23 and constrains them: two representations of a
cowl from one parametric source, with the print path untouched. Nothing in the repository
recorded that cowls are vase-mode printable — the word does not appear anywhere in it — so
IP-FC-17 would have shelled the cowl, exported the shelled solid, and silently removed a
printing capability with no geometric signal that anything was wrong.

Three new items fell out: **IP-FC-42** (adopt `n_perimeters` — the rib's thickness depends
on a value held only in a slicer profile outside the repository), **IP-FC-43** (the buttress
cut's factor of two), and **IP-FC-44** (CW1, done).

**OQ-DES-B11** was raised and decided 2026-08-10 — split by intent, true fillets on the boom
key and the morphological chain for the region-wide remainder — and briefly re-blocked
IP-FC-12 in the process.

**OQ-DES-B12** was raised and decided 2026-08-11, out of the IP-FC-50 audit: the greeble
tool's overshoot argument was also driving the snap rib, giving the socket 0.0067 mm the
design never asked for. Decided as alternative 1 — separate the two meanings in `corner_end`.
The decision was to fix the **OpenSCAD authority** rather than the port, because IP-FC-13
compares the two backends. Implemented the same day as IP-FC-51, with all three affected
reference sets regenerated.

OQ-DES-B3 and B8 remain open and block nothing.

---

## Verification

The three-tier scheme from Phase 2 does not survive intact, and the change is planned rather
than discovered:

| Tier | Phase 2 | After the port |
| --- | --- | --- |
| Exact and cheap | `scad_snapshot.py` — byte-compare generated `.scad` | **Gone.** No generated text exists. Replaced one layer up by IP-FC-2's parameter snapshot |
| Geometric | `sweep_check.py` against a reference tree | Survives, minus triangle count — a tessellation setting, not a property |
| Caller coverage | `verify_drivers.py` | Becomes "does the generator script run", plus the notebook keyword check |
| **Cross-engine** | *(did not exist — nothing to compare against)* | `compare_backends.py` — renders the same variants through both engines and compares measured geometry, with a tessellation-derived tolerance and a guard against counting a part FreeCAD never built. This is IP-FC-13's instrument |

**The equivalence tolerance has two components, and only one shrinks with finer
tessellation.** The OpenSCAD corpus is *faceted* — its `cylinder()` is an inscribed prism —
so a ported part built on true cylindrical surfaces differs from it systematically, not
noisily. See
[freecad_migration.md §The reference corpus is faceted](../architecture/freecad_migration.md).
The sign is predictable per feature, which makes a difference in the *unexpected* direction
a genuine finding.

Quantified 2026-08-10: at `$fa=1` the cap is 360 segments and the deficit is **+0.005077%**
of a circular feature's area, which is the floor no volume comparison between the two engines
can beat. That is where `compare_backends.py`'s tolerances come from — see
[§IP-FC-13](#ip-fc-13--the-comparisons-floor-is-openscads-circle-and-it-is-computable).

Once IP-FC-13 is signed off, this tolerance disappears: within-FreeCAD comparison is B-rep
against B-rep, where volume is exact.
