# System requirements — fuselage

**Status:** the normative requirement set. Written 2026-08-29. This is the document a reviewer
signs and the checkers are run against: it states each requirement once, with its parent, what
verifies it, and whether that verification has actually been run.

**It is not the argument.** Why each requirement is what it is — the measurements, the
reconstructions that turned out wrong, the places the implementation disagreed with the intent —
is in [design_basis.md](design_basis.md) for the airframe and in
[dimension_scheme.md](dimension_scheme.md) for the drawing set. Every entry below names where it
is argued. Nothing is restated in both places.

**The architectural requirements are [doc/architecture/requirements.md](../architecture/requirements.md)**,
which is authoritative in its own right and is not restated here.

Millimeters and degrees throughout, which is what the OpenSCAD path uses. Where a quantity is a
print setting rather than an airframe dimension, the unit is stated with it.

---

## 1. Scope, and how the set is bounded

**Fifty requirements in five groups**, and the groups are not topics — each is a different
thing that can be wrong.

| Group | Id | What can be wrong | Where it is argued |
| --- | --- | --- | --- |
| [Design](#4-design-requirements) | `DES-n` | the airframe is the wrong shape | [design_basis.md](design_basis.md) |
| [Interface](#5-interface-requirements) | `INT-n` | two parts do not fit | [design_basis.md section 5](design_basis.md#5-why-each-interface-is-what-it-is) |
| [Drawing](#6-drawing-requirements) | `DRW-n` | the drawing is unreadable, or says something untrue | [dimension_scheme.md section 5](dimension_scheme.md) |
| [Model](#7-model-requirements) | `MDL-n` | the delivered `.FCStd` is a dead artifact rather than a parametric model | [freecad_migration.md](../implementation/freecad_migration.md) IP-FC-38, 56, 73 |
| [Equivalence](#8-equivalence-requirements) | `EQV-n` | the two geometry paths have silently diverged, or a sweep is quietly short | IP-FC-5, `sweep_check.py` |

**The last three groups were missing until 2026-08-29.** The first version of this document was
built from `design_basis.md` alone, so its completeness test was *"does it cover the derivation"*,
which proves only that it copied one. The set was completed the other way round instead: **every
checker in the repository was read, and each was asked what requirement it enforces.** Eleven
checkers, twenty-five requirements that nobody had written down — including every hard
constraint on a drawing, and every property that makes the delivered model editable.

**What is deliberately not here.** Sheet size, projection convention, line weights and standards
compliance, none of which are decided ([dimension_scheme.md section 6](dimension_scheme.md)). The
wing interface, which is not a fuselage part. And **givens** — a stock size, a standard, a tuned
value, a clearance — which are decisions rather than requirements and are enumerated in
[design_basis.md section 3](design_basis.md#3-what-is-chosen).

---

## 2. Tiers, and the citation policy

| Tier | Cites | Where |
| --- | --- | --- |
| Architectural (`AR-`) | nothing — it is the source | [doc/architecture/requirements.md](../architecture/requirements.md) |
| Design (`DES-`) | zero or more `AR-` | section 4 |
| Below (`INT-`, `DRW-`, `MDL-`, `EQV-`) | one or more `DES-` | sections 5 to 8 |

**A design requirement may cite an architectural requirement, and does not have to.** Decided
2026-08-29 under [OQ-DES-DB5](design_basis.md#open-questions). Where it cites nothing it is
**derived** in the sense INCOSE, ARP4754A and DO-178C use — traceable to no higher-level
requirement, arising from the design solution itself — and carries its own rationale instead.
That is a review obligation, not a defect, and for this project it is the expected case in one
area: MAUS‑FOS excludes dimensional tolerances as *"considered application dependent and
therefore not included in the standard"*, so a decision about where a clearance sits has nothing
above it by the standard's own construction.

**Three of the fifteen cite nothing: DES-4, DES-7 and DES-9.**

**A requirement below the design tier may not cite nothing.** A rule about the drawing set or the
delivered model that answers to nothing above it is a requirement nobody asked for. It **may**
cite an architectural requirement directly, and that is a **level skip**: allowed, because
forbidding it would only mean inventing a middle statement to launder the citation through, and
**reported**, because a skip means either the design tier has a hole or the architectural
requirement is really a design one. **There are none.** There was one — INT-9 reached AR-PRT-3
directly — and [OQ-DES-SR1](#open-questions) closed it on 2026-08-30 by adding the design
requirement that was missing underneath it, which is what a reported skip is for.

**Nothing here was invented while writing it.** Every requirement below the architecture names a
`source`: the document, decision or work item that already said it. A requirement with no source
fails the register check.

---

## 3. Verification methods

| Code | Method | What it means here |
| --- | --- | --- |
| **A** | Analysis | a tool re-derives the required value from the requirement and compares it against what the model built, across every variant — never by reading the model's own answer back |
| **I** | Inspection | a tool measures the **built solid**: a face's position, its area, whether it exists at all |
| **D** | Demonstration | the artifact is produced, or the operation is performed and the result observed |
| **R** | Review | no tool applies and none could |
| **—** | none | nothing applies it. A finding, not a state of affairs |

| Verifier | Runs under | Covers |
| --- | --- | --- |
| [`tools/check_derivation.py`](../../src/Fuselage/tools/check_derivation.py) | the virtualenv, seconds | 33 relations over **560 variants** — corner 264, bulkhead 148, boom bulkhead 132, nose 8, tail 8 — plus coverage: a numeric field that is neither a stated choice nor a derived relation fails |
| [`tools/requirements.py`](../../src/Fuselage/tools/requirements.py) | the virtualenv | the register itself: citations resolve to a tier above, sources exist, verifiers exist, and this document states the same set |
| [`freecad/check_derived_geometry.py`](../../src/Fuselage/freecad/check_derived_geometry.py) | `freecadcmd` | 5 predicted faces over 8 sampled cases chosen to reach the topology boundaries |
| [`freecad/check_dimension_placement.py`](../../src/Fuselage/freecad/check_dimension_placement.py) | `freecadcmd` | the placer's output against the hard constraints, re-derived independently |
| [`freecad/check_drawing.py`](../../src/Fuselage/freecad/check_drawing.py) | `freecadcmd` | a generated sheet on a real part, end to end |
| [`freecad/check_sheet_standard.py`](../../src/Fuselage/freecad/check_sheet_standard.py) | `freecadcmd` | the sheet pin, over the real template and four deliberately broken ones |
| [`freecad/check_tangency.py`](../../src/Fuselage/freecad/check_tangency.py) | `freecadcmd` | the solved fillet centers, and what makes the model editable |
| [`freecad/check_tree.py`](../../src/Fuselage/freecad/check_tree.py) | `freecadcmd` | regenerate by spreadsheet edit, and survival across save and reload |
| [`freecad/check_unread_rows.py`](../../src/Fuselage/freecad/check_unread_rows.py) | `freecadcmd` | which parameter rows reach the geometry, by perturbation |
| [`freecad/check_regenerate.py`](../../src/Fuselage/freecad/check_regenerate.py) | `freecadcmd` | agreement with the OpenSCAD render across U |
| [`tools/sweep_check.py`](../../src/Fuselage/tools/sweep_check.py) | the virtualenv | family completeness, mesh integrity, reference agreement |
| [`tools/verify_scad_change.py`](../../src/Fuselage/tools/verify_scad_change.py) | the virtualenv | that a library change altered no geometry |
| [`tools/verify_drivers.py`](../../src/Fuselage/tools/verify_drivers.py) | the virtualenv | that every GUI driver still renders |

**Sampling is stated, not hidden.** `check_derivation.py` is exhaustive over the sweep;
`check_derived_geometry.py` is not, because building a solid costs seconds where checking a
parameter costs microseconds. Where a status says *sampled*, that is what it means.

---

## 4. Design requirements

Rules over the whole fuselage design. Argued in [design_basis.md section 4](design_basis.md#4-why-each-design-requirement-is-what-it-is).

| ID | Requirement | Cites | V | Verified by | Status |
| --- | --- | --- | :-: | --- | --- |
| **DES-1** | Airframe dimensions **shall** be proportional to U and **shall** scale freely with it, including below their 1U value. `unit_length` **shall** additionally scale with FX, and nothing else **shall** respond to FX | AR-MOD-8, AR-MOD-10 | A | `check_derivation.py` | verified, 15 relations, 560 variants |
| **DES-2** | A feature whose size the print process governs **shall** be sized in whole extrusion widths or whole layer heights | AR-PRT-1 | A | `check_derivation.py` | verified, 4 relations |
| **DES-3** | Every part reaching the outer surface **shall** land on the mold line, and a joint's clearance **shall** be taken inboard of it. No material **shall** stand outboard of a bought panel | AR-MOD-4, AR-MOD-5 | A, I | `check_derived_geometry.py` | verified; geometry sampled, 8 cases |
| **DES-4** | A **joint**'s clearance **shall** appear once, on one named side; the other side **shall** be nominal | — *(a)* | A | `check_derivation.py` | verified — the invariant holds on all 280 bulkhead variants |
| **DES-5** | A bought part **shall** be treated as nominal, and the printed part it mates with **shall** carry the fit | AR-CON-1 | A, I | `check_derivation.py` | verified; **the allocation is not** — *(b)* |
| **DES-6** | At the corner/bulkhead interface the **corner** **shall** carry the clearance, so the bulkhead's dimensions stay consistent across variants | AR-MOD-9 | A | `check_derivation.py` | verified |
| **DES-7** | Where a joint does not exist its clearance **shall** be zero, and that zero **shall** be the absence of the joint rather than a fit set to nothing: the drawing omits the dimension, the geometry merges or closes the feature | — *(c)* | A, I | `check_derived_geometry.py` | verified, sampled — the 0 mm panel is in the sample for this |
| **DES-8** | No part **shall** intrude on the volume swept by another part's assembly motion | AR-ASM-1 | A | `check_derivation.py` | verified on 528 non-cowling variants — *(d)* |
| **DES-9** | Where more than one requirement can govern a dimension, the drawing **shall** state which one produced the value shown | — *(e)* | **—** | **nothing** | **not verified** — [OQ-DES-SR2](#open-questions) |
| **DES-10** | The panel envelope **shall** be fixed by the frame and stated without reference to any panel design | AR-MOD-1, AR-MOD-5 | I | `check_derived_geometry.py` | verified indirectly, through INT-5 |
| **DES-11** | Where a feature's function is set by something that does not scale with the airframe, its size **shall** be floored at what that function requires | AR-PRT-1 | A | `check_derivation.py` | verified, 7 relations; **3 of the 7 floors are justified nowhere** |
| **DES-12** | A cowl **shall** remain printable in spiral vase mode: the solid exported for printing carries one closed contour per layer and no interior geometry whatsoever | AR-PRT-1 | **—** | **nothing** | **not verified** — [OQ-DES-SR2](#open-questions) |
| **DES-13** | A printed part **shall** be modelled in the orientation it prints in — the print bed is the x/y plane and +z the build direction — and that orientation **shall** be chosen so the layer orientation carries the load the part is designed for | AR-PRT-2 | R | review | **partially verifiable** — *(n)* |
| **DES-14** | A printed part **shall** build without support material: no downward-facing surface leans shallower than `overhang_angle_from_bed` from the bed | AR-PRT-3 | A | **nothing yet** | **not verified, but verifiable** — *(o)*, [IP-FC-95](../implementation/freecad_migration.md) |
| **DES-15** | At a bay end, the features that mate with the adjoining bay — the OML perimeter, the longeron positions and sizes, and the fastener positions and sizes — **shall** be identical across every bay of the same size. **The interior aperture is not one of those features** and **shall** be free to vary | AR-MOD-1, AR-MOD-2, AR-MOD-3 | I | **nothing yet** | **not verified, but verifiable** — *(p)*, [IP-FC-100](../implementation/freecad_migration.md) |

**Rationale, where a requirement cites nothing**

*(a)* **DES-4.** A joint has to accommodate print variation and bond thickness, and MAUS‑FOS
excludes dimensional tolerances as application dependent, so nothing above says the
accommodation is single-sided — splitting it across both halves would comply equally. Putting it
on one side is a design decision, and its reason is on record: the joint would otherwise take
the clearance twice. **The unit is the joint, not the parameter** — `panel_tolerance` is carried
by both the corner and the bulkhead, which is two joints against the same bought panel and not a
violation.

*(c)* **DES-7.** A dimensioned zero asserts a coincident fit that was designed and is
inspectable, and here there is nothing to inspect.

*(e)* **DES-9.** The drawing set has no architectural parent at all — the architecture says
nothing about documentation, and an earlier version of this set invented one. The reason stands
on its own: the value table carries the number, and something has to carry which term produced
it.

**Notes**

*(b)* **DES-5's allocation is inferred.** AR-CON-1 names which parts are bought. It does not say
the clearance therefore goes *wholly* on the printed side rather than being split, and MAUS‑FOS
excludes tolerances, so nothing above says that either. This is the most exposed statement in
the set.

*(d)* **DES-8 binds more often than the alternative.** One quantum less than the built
`panel_offset` violates a requirement on all 528; this one is the binding requirement on **468**,
the panel-thickness requirement on 60.

**DES-12 restates a decision, it does not make one** — OQ-DES-CW6, stated in
[cowl.md](cowl.md) as a constraint over the whole interior-surface section. It is in this set
because nothing enforced it and nothing named it as a requirement.

*(n)* **DES-13's orientation is recorded by construction, and its correctness is only half
checkable.** Every existing part is modelled in its print orientation, so **the model is the
record** — there is no separate orientation field that can go stale, and no part can be
"oriented wrongly" in the file without being wrong geometry. What cannot be checked today is
whether the chosen orientation is the *right* one: that is **partly an overhang evaluation**,
which DES-14 covers and which is computable, and **partly a stress analysis, for which the
project does not yet have the tools.** So this requirement is held by review, and it says why
rather than claiming a verification it does not have.

*(o)* **DES-14 is the half that can be measured.** `overhang_angle_from_bed` is **35° from the
bed** — the shallowest a face may lean and still print unsupported, so 0 is a flat ceiling and
90 a vertical wall (OQ-DES-CW2 settled the sense, OQ-DES-CW11 made it one value for the
project). It already governs the nose plate's pocket and every cowl buttress. **Nothing
evaluates it across the built parts yet**, which is a missing tool rather than an open question:
[IP-FC-95](../implementation/freecad_migration.md) is the work item.

*(p)* **DES-15's exclusion is the requirement, as much as its inclusion is.** Sameness holds
for the OML perimeter, the longerons and the fasteners. It does **not** hold for the bulkhead's
interior aperture, which varies with offsets and which on a boom bulkhead — and on other planar
bulkheads that may yet be defined — is neither a standard dimension nor a standard shape. That
exclusion is **AR-MOD-1 doing its job**: a minimally constraining physical interface constrains
what must be shared and deliberately nothing else. A requirement demanding a uniform end *face*
would have been false the day it was written, and would have forbidden parts the design intends.

**DES-13 and DES-14 are deliberately two requirements, not one.** Decided in
[OQ-DES-SR1](#open-questions) on 2026-08-30. They interact — the orientation that prints most
easily is often not the strongest — and merging them would put that trade behind a single id and
behind a single verification status, when one half is computable today and the other is not.

---

## 5. Interface requirements

The ten joints of [dimension_scheme.md section 2](dimension_scheme.md)'s register, in the same
order. Argued, with the measured evidence, in
[design_basis.md section 5](design_basis.md#5-why-each-interface-is-what-it-is).

| ID | Joint | Requirement | Cites | V | Status |
| --- | --- | --- | --- | :-: | --- |
| **INT-1** | longeron tube → corner bore | The corner **shall** locate the tube over the full length of the part without retaining it, and its inboard boundary **shall** leave the bore's mouth open | DES-5, DES-8 | A | verified, 264 variants |
| **INT-2** | greeble post → corner socket | The corner **shall** accept the post in a socket cut from the greeble's own profile grown by `greeble_tolerance`; the post **shall** be built at nominal | DES-4, DES-6 | A | verified — the tolerance is 0 on all 280 bulkhead variants |
| **INT-3** | corner seating faces → bulkhead | The corner **shall** plug into a socket cut from its own description. The bounding diagonal **shall** leave one extrusion width outside the bore and **shall not** rise above the panel seat | DES-4, DES-6, DES-9 | A, I | verified — the flat measures 52.5000 mm², exactly 0.525 × the part length |
| **INT-4** | panel → corner | The corner **shall** capture the panel in a **rebate**, not a slot: the panel's outer face is exposed and is airframe surface | DES-3, DES-5, DES-10 | A, I | verified — all four faces to 1e-6 mm, at 0.5U, 1U, 4U and 0 mm panel |
| **INT-5** | panel → bulkhead flange | The panel **shall** run a full bay uninterrupted at a station; the bulkhead's outer face **shall** be set back by the panel pocket and run the panel's exposed span | DES-3, DES-10 | A, I | verified — 45.1375 and 392.8500 mm² |
| **INT-6** | boom tube → collet | A printed collet **shall** grip the bought tube, taking the clearance in its bore, and its wall **shall** scale with no floor | DES-1, DES-5 | A | verified, 132 variants — *(f)* |
| **INT-7** | cowl → cowling bulkhead flange | The cowl **shall** slide over a flange inboard of the mold line by the cowl's own printed wall plus the fit; where there is no cowl the flange **shall** be absent rather than zero-height | DES-3, DES-7 | A | verified |
| **INT-8** | nose closure → cowl shell | The nose **shall** seat on the cowl's shell as a lap joint, taking alignment from the fit and bond from the seating face; the fit **shall** be a nominal interference | DES-3 | A | verified, 16 variants |
| **INT-9** | nose plate → nose closure | A printed plate **shall** close the nose tip, its pocket relieved at `overhang_angle_from_bed` so the closure prints without support | DES-7, DES-14 | A | verified, 16 variants — *(h2)* |
| **INT-10** | bolt or insert → bulkhead | Bays **shall** bolt end to end, one end a bolt through a clearance hole and the other a threaded insert, the fastener on the diagonal and its boss floored | DES-1, DES-5, DES-11, DES-15 | A | verified, 280 variants — *(g)* |

*(f)* **INT-6's clearance is measured, not derived.** `boom_tolerance` 0.2 is four times the
longeron's 0.05, and the constants file says the number has never been justified in writing. It
was **set by a fit check on a printed prototype** (OQ-DES-DB3, 2026-08-29) — a real origin that
supports no extrapolation: a new tube size or a different printer needs another fit check.

*(h2)* **INT-9 cited AR-PRT-3 directly until 2026-08-30**, skipping the design tier, because
nothing at that tier said parts print without support. DES-14 now does, and this joint is an
ordinary decomposition again.

*(g)* **INT-10 has an undetermined dimension.** Where the fillet between the bulkhead flange and
the bolt boss lands relative to the bolt axis is the difference of four independently chosen
dimensions and takes whatever value they leave. OQ-DES-B14, deliberately measured and reported
rather than constrained.

---

## 6. Drawing requirements

The drawing set. **DRW-1 through DRW-5 are the hard constraints of
[dimension_scheme.md section 5.2](dimension_scheme.md) — violation fails the build, and none is
a preference.** The soft costs of §5.3 are ranked preferences and are deliberately not
requirements.

| ID | Requirement | Cites | V | Verified by | Status |
| --- | --- | --- | :-: | --- | --- |
| **DRW-1** | H1 **Containment.** The full extent of every dimension — text box, dimension line, arrowheads, witness lines, any leader — **shall** lie inside the view frame and inside the sheet's printable area | DES-9 | A | `check_dimension_placement.py` | verified on a corpus chosen for difficulty |
| **DRW-2** | H2 **Text does not touch text.** No two dimension text boxes **shall** intersect, and the clear gap between them **shall** be at least one text height | DES-9 | A | `check_dimension_placement.py` | verified |
| **DRW-3** | H3 **Text does not touch geometry.** No text box **shall** intersect a visible edge, a hidden edge, a center line, or a hatch region | DES-9 | A | `check_dimension_placement.py` | verified |
| **DRW-4** | H4 **A witness line shall not cross a dimension line.** Crossing another witness line is conventional and permitted | DES-9 | A | `check_dimension_placement.py` | verified — *(h)* |
| **DRW-5** | H5 **No structurally-zero dimension shall be placed at all** | DES-7, DES-9 | A | `check_dimension_placement.py` | verified |
| **DRW-6** | Where the hard constraints cannot all be satisfied the build **shall** fail and name the dimensions it could not place. It **shall not** relax a constraint, shrink the text, or emit the overlap | DES-9 | A | `check_dimension_placement.py` | verified |
| **DRW-7** | The same family **shall** produce byte-identical placement on every run: no unseeded randomness, no dependence on dictionary or set iteration order, every tie broken by a stated total order | DES-9 | **—** | **nothing** | **not verified** — [OQ-DES-SR2](#open-questions) |
| **DRW-8** | The checker that re-derives the hard constraints **shall** be independent of the placer that satisfies them | DES-9 | R | `check_dimension_placement.py` | held — *(h)* |
| **DRW-9** | The drawn view **shall** occupy at least three quarters of the sheet frame | DES-9 | A | `check_dimension_placement.py` | verified — 75.4 % against the pinned title block |
| **DRW-10** | The sheet **shall** state its units, as fixed text rather than an editable field | DES-9 | A | `check_sheet_standard.py` | verified — the check fails a template with the statement removed |
| **DRW-11** | The sheet template and the font **shall** be project data, pinned by id, and a build against a substituted one **shall** fail loudly | DES-9 | A | `check_sheet_standard.py` | verified — five refusals, each exercised against a deliberately broken copy |
| **DRW-12** | For every clearance in the register, the drawing **shall** carry every dimension that entry's governing expression consumes | DES-9, DES-10 | A | `check_drawing.py` | **partial** — the register was completed 2026-08-30 (IP-FC-107); two of the five names it now demands are on no sheet, IP-FC-109 and IP-FC-110 |

*(h)* **DRW-8 is why DRW-4 is trustworthy.** The placer's original lane rule let a small
dimension and a larger one containing it share lane 0, because their *text* did not collide —
drawing two collinear dimension lines with a witness line through one. The independent checker
named it as H4. A placer certifying its own output would have reported success.

**DRW-12 is partial, the cause was decided, and building the fix moved where the partiality
lives.** The register's *governing expression* column used to mean two different things in
different rows — the whole size of the fit in some, only the clearance gap in others — so the
completeness test under-demanded parameters and covered two joints only by coincidence.
**OQ-DES-D7 decided on 2026-08-30** that every row states the whole size, and **IP-FC-107 built
it the same day**: rows 2, 3 and 5 rewritten, and `check_register` now refuses a row that names
nothing beyond its own clearance.

**Five names became newly demanded, not the three that were estimated.** Three of them were
already on the sheets and needed only to be declared — the corner's socket and post are both
computed from `greeble_thickness`, and the bulkhead's mold half width **is** `unit_width / 2`.
**Two are on no sheet at all**: `panel_offset` and `panel_overlap`, which row 5 now demands
because it states the seating face's width and not only its position. So DRW-12 stays *partial*,
and the reason has changed from *the register under-asks* to *two sheets do not answer*. That is
a better failure: it names four specific family sheets rather than a whole column, and closing it
is **IP-FC-109** and **IP-FC-110**, both blocked on drawing decisions
([OQ-DES-D11](dimension_scheme.md#open-questions), [OQ-DES-D12](dimension_scheme.md#open-questions)).

**No drawn sheet changed**, verified by comparing every family's quantity column count, block
count and row count before and after.

---

## 7. Model requirements

The delivered FreeCAD document, which is not the airframe. **A generated model is not only a
mesh source: someone opens it and changes a parameter**, and every requirement here exists
because a way of failing that would pass a volume check.

| ID | Requirement | Cites | V | Verified by | Status |
| --- | --- | --- | :-: | --- | --- |
| **MDL-1** | The delivered `.FCStd` **shall** stay editable: a parameter change re-solves every sketch and rebuilds the part, headless, without the GUI | DES-1 | D | `check_tangency.py` | verified for every rounded corner |
| **MDL-2** | A parameter change **shall** be made by editing the parameter sheet and recomputing, not by re-running the generator | DES-1 | D | `check_tree.py` | verified across four U |
| **MDL-3** | The document **shall** still be a live parametric tree after a save and reload | DES-1 | D | `check_tree.py` | verified — that is the file the user opens |
| **MDL-4** | An unsatisfiable configuration **shall** be refused by name, naming the sub-system that could not be solved | DES-1 | D | `check_tangency.py` | verified — *(i)* |
| **MDL-5** | A feature the variant does not have **shall** be left out, not relocated, and no sketch **shall** carry a construction element for it | DES-7 | I | `check_tangency.py` | verified, both sides of the existence boundary |
| **MDL-6** | No geometry **shall** be constrained to a modeling convenience: moving a construction element whose extent means nothing **shall** move no solved position | DES-1 | A | `check_tangency.py` | verified — three of the sketch's four features are segments whose endpoints mean nothing |
| **MDL-7** | Every row on a part's parameter sheet **shall** reach that part's geometry | DES-1 | A | `check_unread_rows.py` | **known violations** — *(j)* |

*(i)* **MDL-4 is the whole point of solving rather than computing.** The `max(...; 0)` these
replaced used to clamp and return a plausible wrong center. All four corners share one sketch
since OQ-ARCH-14, so a refusal saying only *"the sketch failed"* would be **weaker** than the
four separate sketches it replaced.

*(j)* **MDL-7 does not hold today, and the violations are known.** `bulkhead_section` merges
`corner_tree.PARAMS` so it can reuse `corner_end`, and `FX`, `unit_length`, `greeble_tolerance`,
`mid_h` and `mid_z0` come along with it; nothing the bulkhead builds reads any of them. Pruning
is IP-FC-56 and has an order that has to be followed — *unread* is the evidence needed before
pruning, not the pruning itself. **The method is perturbation, not analysis**, on volume, face
count *and* bounding box: a row is unread only when none of the three moves.

---

## 8. Equivalence requirements

The two geometry paths, and the sweep as a whole. **Generated output is not stable byte for
byte** — OpenSCAD emits the same mesh with a different facet order on every run — so every
requirement here is stated over measured geometry rather than over files.

| ID | Requirement | Cites | V | Verified by | Status |
| --- | --- | --- | :-: | --- | --- |
| **EQV-1** | The FreeCAD part and the OpenSCAD render of the same variant **shall** agree by measured geometry — volume, bounding box, face count — and not by bytes | DES-1 | A | `check_regenerate.py` | verified across U |
| **EQV-2** | An agreement tolerance **shall** be relative to the quantity it bounds, and where it is a length **shall** scale with U | DES-1 | A | `check_tangency.py` | verified — *(k)* |
| **EQV-3** | Every scaling family in a sweep **shall** carry the same set of parts, where a family is one U scale plus one panel stock | DES-1 | A | `sweep_check.py` | verified — that is what makes a set of parts mutually buildable |
| **EQV-4** | Every exported mesh **shall** parse as a whole mesh | DES-1 | A | `sweep_check.py` | verified — a killed render leaves a partial file that existence checks treat as finished |
| **EQV-5** | A change to a shared library **shall** be shown to alter no geometry by re-rendering real parts, not by inspecting the diff | DES-1 | D | `verify_scad_change.py` | verified — *(l)* |
| **EQV-6** | Every GUI driver **shall** render | DES-1 | D | `verify_drivers.py` | verified — *(m)* |

*(k)* **EQV-2's tolerances are not fits.** A part's coordinates are proportional to U, and the
residual a solver stops on is proportional to the magnitude of the numbers it works in, so a
fixed millimeter figure is four times stricter at U=4 than at U=1. These bound **agreement
between two engines**; a printed clearance is about 0.1 mm and is a design quantity. Confusing
the two would either loosen a fit or make an equivalence check unpassable.

*(l)* **EQV-5 exists because a text comparison is blind to it.** A generated `.scad` names its
library by path and contains none of its text, so editing a module under `scad/` leaves every
generated file byte-identical.

*(m)* **EQV-6 is about the path, not the values.** The drivers set concrete parameter values,
and those values are **not** a source of truth about design choices — several are development
numbers. What this requirement protects is that the interactive path a person opens a part
through does not break silently while the sweep passes.

---

## 9. Traceability

### 9.1 Architecture → requirements

**Thirteen of the nineteen architectural requirements are reached, and there are no gaps left.**
The six that are not cited each have a stated reason below, and none of them is *"nobody has
written it"*. The two Printability gaps closed under [OQ-DES-SR1](#open-questions) and the two
Modularity gaps under [OQ-DES-SR3](#open-questions), both on 2026-08-30. Generated by `python requirements.py --report`.

| Architectural | Reached by | Reading |
| --- | --- | --- |
| AR-OBJ-1 … AR-OBJ-4 | — | **expected.** The objectives are refined by the Modularity, Printability, Construction and Assembly groups, not decomposed directly into design rules |
| AR-MOD-1 | DES-10, DES-15 | DES-15 cites it for what it *excludes*: the bulkhead aperture is left free because the interface is minimally constraining |
| AR-MOD-2 | DES-15 | the bay end's mating features are identical across bays, which is what lets any two be interchanged |
| AR-MOD-3 | DES-15 | the same requirement delivers re-ordering; DES-15 also cites AR-MOD-1 for what it deliberately leaves free |
| AR-MOD-4 | DES-3 | |
| AR-MOD-5 | DES-3, DES-10 | |
| AR-MOD-6 | — | **out of scope.** The wing interface is not a fuselage part |
| AR-MOD-7 | — | covered by a *given* rather than a requirement — `unit_length`, cited in [design_basis.md section 3](design_basis.md#3-what-is-chosen) |
| AR-MOD-8 | DES-1 | also cited by four givens |
| AR-MOD-9 | DES-6 | |
| AR-MOD-10 | DES-1 | |
| AR-PRT-1 | DES-2, DES-11, DES-12 | |
| AR-PRT-2 | DES-13 | held by review; the structural half needs analysis tools the project lacks |
| AR-PRT-3 | DES-14 | computable, and not yet computed — [IP-FC-95](../implementation/freecad_migration.md) |
| AR-CON-1 | DES-5 | |
| AR-ASM-1 | DES-8 | also cited by two givens |

### 9.2 Design → everything below

| | INT | DRW | MDL | EQV |
| --- | --- | --- | --- | --- |
| **DES-1** | 6, 10 | | 1, 2, 3, 4, 6, 7 | 1, 2, 3, 4, 5, 6 |
| **DES-2** | | | | |
| **DES-3** | 4, 5, 7, 8 | | | |
| **DES-4** | 2, 3 | | | |
| **DES-5** | 1, 4, 6, 10 | | | |
| **DES-6** | 2, 3 | | | |
| **DES-7** | 7, 9 | 5 | 5 | |
| **DES-8** | 1 | | | |
| **DES-9** | 3 | 1–12 | | |
| **DES-10** | 4, 5 | 12 | | |
| **DES-11** | 10 | | | |
| **DES-12** | | | | |
| **DES-13** | | | | |
| **DES-14** | 9 | | | |
| **DES-15** | 10 | | | |

**DES-2, DES-12 and DES-13 reach nothing below.** For DES-2 that is correct: sizing in whole
extrusions governs *walls*, which are internal structure and therefore reference geometry rather
than interface, and it is checked on the parameters instead. **DES-13 is correct for a different
reason** — it constrains how a part is *placed* rather than what any two parts do to each other,
so it has no joint to reach. **For DES-12 it is not correct**: nothing below it and nothing
verifying it is the same finding twice.

### 9.3 Verification status

**Forty-five of the fifty requirements have a verifier. Five have none, and two have a verifier
that does not fully hold. Every one of the five is now a work item with a named approach** —
decided 2026-08-30 under [OQ-DES-SR2](#open-questions) and
[OQ-DES-SR3](#open-questions), which is the change that matters more than the count.

| | Count | Which |
| --- | ---: | --- |
| Verified, exhaustive over the sweep | 24 | most of DES and INT |
| Verified, sampled by construction | 9 | the geometry and drawing checkers, on corpora chosen for difficulty |
| Verified by demonstration | 8 | MDL-1 to MDL-4, EQV-5, EQV-6 |
| Held by review | 2 | DRW-8; **DES-13**, whose remaining half needs stress analysis the project has no tools for |
| **Partial or violated** | 2 | **DRW-12** (IP-FC-109, IP-FC-110), **MDL-7** (IP-FC-56) |
| **Verified by nothing, work item raised** | 5 | **DRW-7** (IP-FC-97), **DES-12** (IP-FC-98), **DES-9** (IP-FC-99), **DES-14** (IP-FC-95), **DES-15** (IP-FC-100) |

**The last two rows are the whole value of writing the set down**, and as of 2026-08-30 the last
row is a queue rather than a question. Every entry has a named approach and a work item; what
remains is to build them.

**The order is set by dependency, not by cost.**

```
IP-FC-97  DRW-7   placer run twice, bytes compared          -- no dependency
IP-FC-98  DES-12  cowl export: one contour per layer        -- no dependency
IP-FC-95  DES-14  overhang angle per face against the bed   -- no dependency
IP-FC-100 DES-15  bay-end mating features compared          -- no dependency
IP-FC-99  DES-9   which branch produced a dimension, noted  -- AFTER IP-FC-97
```

**Only one edge is real, and it is a real one.** DES-9's note has to be placed on a sheet, which
moves every other annotation on that sheet. Until DRW-7 is verified, a diff between two runs
cannot be attributed — it might be the new note or it might be nondeterminism that was always
there. Verifying determinism first makes the note's effect on the layout readable, and that is
the whole of the ordering constraint.

---

## 10. How this document is kept true

**The register is data.** [`tools/requirements.py`](../../src/Fuselage/tools/requirements.py)
carries all six tables. Six things fail it:

- a citation that resolves to no requirement;
- a citation to the wrong tier — a drawing rule citing another drawing rule says nothing about
  why the drawing set exists;
- a requirement below the design tier citing nothing at all;
- a design requirement citing nothing **and** carrying no rationale;
- a requirement below the architecture with no **source**, which would mean somebody wrote it
  while writing a register;
- a **verifier naming a file that is not in the repository** — the cheapest way to catch a
  specification claiming a check that does not exist.

**This document is checked against it**, by id set and not by wording, because a checker that
compared prose would either be defeated by a rephrasing or forbid one.

Two things are reported as **notes** rather than failures, because both are findings a person
must decide about: a **level skip**, and a requirement with **no verifier**.

```
python src/Fuselage/tools/requirements.py            # the register, and this document
python src/Fuselage/tools/requirements.py --report   # the coverage matrix, generated
python src/Fuselage/tools/check_derivation.py        # every parameter of every variant
freecadcmd src/Fuselage/freecad/check_derived_geometry.py --pass params.json kind=corner
```

**What is checked by nothing.** The architecture. A green run means the implementation follows
from these requirements and that they are anchored where they claim to be — not that they are
the right requirements.

---

## Open questions

**None. All three are decided**, on 2026-08-30, and the resolution notes stay below in numerical
order because what each decided is why several parts of this document read the way they do.

**What replaced them is a queue, not an absence.** The three questions were about requirements
nothing verified, a printability tier with a hole in it, and a modularity claim nothing stated.
All three are now requirements with named checks that **have not been written**:
[section 9.3](#93-verification-status) lists five, with their work items and the one dependency
edge between them. That is a better state than three open questions and a worse state than a
green run, and the table says which it is.

**The live questions elsewhere are all in
[dimension_scheme.md](dimension_scheme.md#open-questions).** **OQ-DES-D11** and **OQ-DES-D12**
both hold DRW-12 at *partial*: no bulkhead sheet says how wide the panel's seating surface is,
and a bulkhead with no panel is nonetheless asked to explain the panel joint. **OQ-DES-D10**, the
*Carried by* column meaning two things, affects no requirement's status.

Two closed on 2026-08-30. **OQ-DES-D7** — the *governing expression* column meaning two things,
which is why DRW-12 is partial — was decided: every row states the whole size, then the
expressions become executable and are checked against the parts. **OQ-DES-DB7** was withdrawn:
it asked whether `longeron_chamfer` should be renamed because it chamfers nothing, and it does
chamfer something.

### ~~OQ-DES-SR1 — Two printability requirements have nothing above the joint~~ — DECIDED 2026-08-30: two requirements, DES-13 and DES-14, kept separate

**Resolution note.** Alternative 2: one requirement for orientation, one for support.

**They are two concerns and they get two requirements.** Merging them into one — which was this
document's recommendation — would have put a real trade behind a single id: the orientation that
prints most easily is often not the one that carries load best. It would also have merged two
different verification states, and that is the sharper reason, because one half is computable
today and the other is not.

| | **DES-13** — orientation | **DES-14** — support |
| --- | --- | --- |
| Cites | AR-PRT-2 | AR-PRT-3 |
| Says | the part is modelled in the orientation it prints in, bed = x/y plane, +z = build direction, chosen so the layers carry the load | no downward-facing surface leans shallower than `overhang_angle_from_bed` from the bed |
| Recorded how | **by construction** — every existing part is already modelled in its print orientation, so the model *is* the record | `overhang_angle_from_bed` = 35°, one value for the project, reason in the constants file |
| Verified | **held by review**, and only half checkable even in principle | **computable, not yet computed** — IP-FC-95 |

**Orientation is recorded by construction, which answers the drawback this question raised.**
The recommendation for a merged requirement worried that *"nothing records a part's build
orientation anywhere"*, so an orientation requirement would be review-only and empty. That was
wrong: all existing parts are oriented for print by construction, with the print bed as the x/y
plane. There is no separate field to go stale, and a part cannot be oriented wrongly in the file
without being wrong geometry.

**What *is* only half checkable is whether the orientation chosen is the right one.** That
splits cleanly: **partly an overhang evaluation**, which is DES-14 and is computable; **partly a
stress analysis, for which the project does not yet have the tools.** DES-13 is held by review
and says so, rather than claiming a verification it does not have — which is exactly the failure
the Status column was added to expose.

**The level skip is closed.** INT-9 cited AR-PRT-3 directly because nothing at the design tier
said parts print without support; it now cites DES-14, and `requirements.py` reports no level
skips. **That is what a reported skip is for** — it named a hole at the tier above rather than a
fault at the joint, and the hole is filled.

**Coverage went from ten of nineteen architectural requirements reached to eleven**, with both
Printability gaps closed. What remains uncited is the four objectives — refined by the groups
rather than decomposed directly — and AR-MOD-2, AR-MOD-3, AR-MOD-6 and AR-MOD-7.

*Implementation: `requirements.py` gains DES-13 and DES-14 and re-cites INT-9; section 4 gains
two rows and two notes; IP-FC-95 is the overhang checker DES-14 needs.*

### ~~OQ-DES-SR2 — Three requirements are verified by nothing~~ — DECIDED 2026-08-30: build all three, ordered by dependency

**Resolution note.** Alternative 1: all three checks are to be built. The ordering is set by
dependency rather than by cost, and only one dependency edge exists.

**A phrase in this question's alternative 2 was hollow and is withdrawn.** It offered *"does not
force a drafting decision under time pressure"* as a benefit of deferring DES-9. **There is no
time pressure**, and there never was — the phrase was carried over from AP-3's reasoning, where
the concern had been manufacturing a justification for the cross section rather than admitting a
gap. It does not transfer. What was left underneath it, once the invented urgency is removed, is
a single true observation: **DES-9's cost is sheet real estate rather than code**, so building it
entails a layout decision that the other two do not. That is a dependency, not a reason to defer,
and it is what sets the order below.

**What each check is.**

| | Requirement | The check |
| --- | --- | --- |
| [IP-FC-97](../implementation/freecad_migration.md) | **DRW-7** — byte-identical placement | run the placer twice on the same family and compare bytes. A dozen lines, no new machinery |
| [IP-FC-98](../implementation/freecad_migration.md) | **DES-12** — cowl stays vase-mode printable | section the exported cowl solid over a sampled z and assert one closed contour per layer and no interior face |
| [IP-FC-99](../implementation/freecad_migration.md) | **DES-9** — the drawing says which requirement governed | sweep for every dimension whose derivation branches; emit the governing branch as a note; fail a sheet carrying such a dimension without one |

**The one dependency: IP-FC-99 comes after IP-FC-97.** DES-9's note has to go somewhere on the
sheet, and adding it moves every other annotation. Until placement is known to be deterministic,
a diff between two runs cannot be attributed — it might be the note, or it might be
nondeterminism that was always there and nobody had looked for. Doing DRW-7 first makes the
note's effect on the layout readable. The other three are independent of each other and of these.

**DES-12 is still the one with a live failure mode**, and that is a reason to weight it, not to
reorder: a modelling change that gives the cowl a wall destroys vase-mode printability while the
part still builds, still exports and still measures correctly.

**DES-14 and DES-15 join the same queue**, from [OQ-DES-SR1](#open-questions) and
[OQ-DES-SR3](#open-questions). Section 9.3 now lists all five together, because after this
decision they are the same kind of thing: a requirement with a known check that nobody has
written. The distinction this document drew a day earlier — between *"we do not know what would
verify this"* and *"nobody has written it yet"* — has collapsed in the useful direction, since
the first category is now empty.

### ~~OQ-DES-SR3 — Interchange and re-ordering are delivered but not required~~ — DECIDED 2026-08-30: DES-15, scoped to the mating features only

**Resolution note.** Alternative 1, with a correction to the requirement this document drafted.

**The draft was wrong, and the correction is the substance of the decision.** It proposed that
*"every bay presents the same forward end interface as every other bay, and likewise aft"*.
Sameness holds for the **OML perimeter**, the **longeron positions and sizes**, and the
**fastener positions and sizes**. It does **not** hold for the **bulkhead's interior aperture**,
which is not constrained, varies with offsets, and on a boom bulkhead — and on other planar
bulkheads that may yet be defined — is neither a standard dimension nor a standard shape. A
requirement over the whole end face would have been false on the day it was written and would
have forbidden parts the design intends to have.

**DES-15 is therefore stated over the mating features and says outright what it excludes.** The
exclusion is not a concession to the current implementation; it is **AR-MOD-1**, a minimally
constraining physical interface, which means constraining what has to be shared and deliberately
nothing else. That is why DES-15 cites AR-MOD-1 alongside AR-MOD-2 and AR-MOD-3: two of its
parents say what must be the same, and the third says why the rest must not be.

**What this closes.** AR-MOD-2 and AR-MOD-3 were reached by nothing, so a change making one bay
end differ from another would have violated the architecture and passed every check in the
repository — INT-10 is about the fastener, not about the end interface being repeatable. INT-10
now cites DES-15 as well. **Coverage rises to thirteen of nineteen architectural requirements,
with no gaps left**: the six uncited are the four objectives, which the groups refine rather than
decompose; AR-MOD-6, the wing interface, which is not a fuselage part; and AR-MOD-7, carried by a
given.

**It is verifiable and not yet verified.** The two ends of a built bay can be compared for
fastener positions, bolt circle, longeron positions and OML perimeter — the same kind of
face-level test `check_derived_geometry.py` already does — while the aperture is excluded from
the comparison by the requirement itself.
[IP-FC-100](../implementation/freecad_migration.md) is the work item, and it joins the queue in
[section 9.3](#93-verification-status).


---

## See also

- [design_basis.md](design_basis.md) — why each design and interface requirement is what it is, with
  the measurements; the givens; the implementation artifacts. It has **no open questions left**
  as of 2026-08-30; what remains in its section 8 is a queue of things to ask, not to decide
- [dimension_scheme.md](dimension_scheme.md) — where DRW-1 … DRW-12 are argued: the interface
  register, the completeness test, the placement rules and their acceptance corpus; OQ-DES-D10,
  D11 and D12
- [doc/architecture/requirements.md](../architecture/requirements.md) — the architectural
  requirements, and the cross-section trade
- [cowl.md](cowl.md) — DES-12's source, and the interior surface that must not become the print
  export
- [freecad_migration.md](../implementation/freecad_migration.md) — IP-FC-5, 38, 56, 73 and 86,
  where the model, equivalence and drawing requirements were decided
