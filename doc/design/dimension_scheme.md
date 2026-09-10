# The dimension scheme

*IP-FC-36. Written 2026-08-21.*

Which dimensions a generated drawing carries, and how to know the set is complete.

[OQ-ARCH-7](../architecture/freecad_migration.md#open-questions) decided the shape of this on
2026-08-07: **dimension the interfaces first, grow into a full parameter-driven scheme second.**
It named one prerequisite — *"agreement on what belongs to the interface"* — and assigned it to
`doc/architecture/overview.md`, which does not exist. This document supplies that agreement
from the design authorities that do exist, so the prerequisite is met by enumeration rather
than by waiting.

## 0. Who the drawing is for

Stated 2026-08-22, and everything below is judged against it:

> **The drawing user wants to understand the impact of the part design on their integration
> with the structure.** What size longerons are used, and what are the tolerances on that
> dimension? What size panels, and what are its tolerances? What size bolts and bolt anchors?
> What is the interior dimension of the structural cell — the bulkhead interior aperture? How
> much volume does each part use, which translates to mass?

**This is an integration drawing, not an inspection drawing**, and the distinction is not
cosmetic. An inspector wants the feature as built — the 4.10 mm bore. An integrator wants the
hardware the feature is cut for — the 4.00 mm longeron and the 0.10 mm of clearance. The design
puts the whole fit clearance inside the mating face, so those are different numbers *by
construction*.

**[OQ-DES-D2](#open-questions) decided how one annotation carries both, on 2026-08-22: the
dimension gives the feature as built and a callout beside it names the hardware.** So the bore
reads `⌀4.10 BORE / FOR ⌀4.00 LONGERON / 0.10 DIA CLEARANCE`, and the two numbers cannot drift
apart because both come from the same expression.

Two of the five questions above are not answered by any dimension as the rule stood, because
the cell aperture is a hole nothing in the model mates with and material is not a distance at
all. **[OQ-DES-D3](#open-questions) decided both on 2026-08-22**: the aperture *is* a dimension
— the span between two real interior faces — so the rule gains a clause for it below, and
volume goes in a data block rather than being annotated at all.

**Panel dimensions are a stated requirement, 2026-08-22**, and they reach further than the
frame. Panels are to be given their own OML allocation with panel shapes designed inside it, so
that designs can be interchanged. Every boundary of that allocation is determined by the frame
and verified, and it is in §2's register — including the length, which is the full bay: the
bulkhead is cut back by exactly the panel pocket so the panel runs over it unbroken.
**[OQ-DES-D4](#open-questions) decided on 2026-08-22 that the OML itself becomes a part**, so a
candidate panel can be checked against it by containment rather than against transcribed
numbers.

---

## 1. The membership test

A part has hundreds of dimensionable edges and a useful drawing carries a dozen. The question
is not "which are interesting" — that is taste, and taste does not scale to 576 variants.

> **A dimension belongs to the interface set if another part's geometry depends on it, or if
> it bounds a space the airframe encloses.**

That is mechanical, not aesthetic. It also has a convenient property in this project:
**the clearance parameters already enumerate the joints.** Every entry in
`design_constants.json`'s `tolerances` group exists because two parts meet somewhere. There are
seven, and there are seven joints.

**What section 2 is, decided in [OQ-DES-D9](#open-questions) on 2026-08-28: it is an analysis
of the implementation, not a specification the implementation is built to.** The sentence that
stood here until then said the register *"is a reading of a file the sweep already validates on
every run"*, and that is true of three of its rows. Measured 2026-08-28, `design_constants.json`
carries a governing expression in its `why` field for **three of the seven joints** —
`boom_tolerance`, `cowl_flange_tolerance` and `nose_flange_tolerance`, which rows 6, 7 and 8
quote verbatim. For the other four the `why` is prose: rows 2, 3 and 5 faithfully reproduce that
prose, and **rows 1 and 4 carry expressions that appear in no design document at all** — they
were written by reading the parts. Not one term of rows 1 to 5's expressions appears in the
corresponding `why`.

So the register's authority is the geometry, and **where the register and a part disagree, the
part is right and the register is corrected.** That is what makes
[OQ-DES-D8](#open-questions) a transcription fix rather than a defect in every corner.

**This is a statement of what the document is, not of what the project needs.** What is needed
is a derivation of the fundamental design relationships, written so that the implementation —
the OpenSCAD geometry, together with the corrections the FreeCAD migration turned up — *follows
from* it. **That document was written on 2026-08-28 under IP-FC-87 and is
[design_basis.md](design_basis.md)**, which holds the argument.

**The requirements themselves are stated in
[system_requirements.md](system_requirements.md)**, written 2026-08-29 — each once, with its
parent, its verification method, and whether that verification has been run. Two groups of it
come from this document. **The ten joints this section's register enumerates are `INT-1` …
`INT-10` there**, in the same order, so a row of the register and a requirement now share an id.
And **section 5.2's five hard constraints are `DRW-1` … `DRW-5`**, with the rest of section 5 —
the fail-loud rule, determinism, the independent checker — as `DRW-6` through `DRW-8`, and
section 3's completeness test as `DRW-12`. Section 5.3's soft costs are ranked preferences and
are deliberately **not** requirements.

**The architectural requirements are a separate document and a separate level**, adopted into
this repository on 2026-08-29 under OQ-DES-DB5 as
[doc/architecture/requirements.md](../architecture/requirements.md). An architectural
requirement constrains any compliant implementation; a design requirement constrains this one.
Together they are the prerequisite
[OQ-ARCH-7](../architecture/freecad_migration.md#open-questions) named — *"agreement on what
belongs to the interface"* — with the architectural half in `doc/architecture/` and the design
half here.

**What that changes for this section, and what it does not.** No reading of the register
establishes that a part is built as intended; it establishes that a drawing states what the
part measures, which is what it is for. The other claim now has somewhere to be made: the
derivation states each relationship as a requirement and checks it, over every variant for the
parameters and by sample for the faces. Where the two disagree the derivation is the one that
says a part is wrong — and where it and the register disagree, as they did over row 4, the part
settles it.

**The second clause was added on 2026-08-22 and it is deliberately narrow.** The first clause
is a test about *joints*, and it misses the one thing that decides whether anything fits inside
the airframe: the bulkhead's interior aperture. Nothing in the model mates with that opening —
it is what is left after the ring and the webs — so the joint test cannot see it, while a
battery, a wiring loom, a servo and a hand with a nut driver all depend on it and none of them
is a part in this model.

The clause is a **closed list, not an open invitation**, and that is what keeps the completeness
test a lookup rather than a judgment. It admits exactly the enclosed span of each part that has
one, by name:

| Part | Enclosed span | Value at 1U, 3/16 in |
| --- | --- | --- |
| frame bulkhead | `unit_width − 2·(panel_thickness + panel_tolerance) − 2·flange_thickness` | 87.875 |
| boom bulkhead | `unit_width − 2·(panel_thickness + panel_tolerance) − 2·web_width` | 78.275 |

Both are the distance between a real pair of parallel planar faces — 247.3 mm² each on the
frame bulkhead, 93.7 mm² on the boom — so each dimensions like any other and needs no new
convention. The last term differs because the ring's inner boundary is set by the flange on a
frame bulkhead and by the web on a boom bulkhead.

**On a boom bulkhead the span and the clear opening are two different numbers.** The span
between the interior faces is 78.275 both ways; the clear opening is 78.275 × 66.402, because
the boom collet intrudes from one side. The dimension is the span, and the obstruction is
visible in the view — but a reader asking "what fits through" has to look at the view and not
only at the number, and this is the one part where those differ.

---

## 2. The interface register

`U` is the size multiplier, `w` is `extrusion_width`, `n_p` is `cowl_n_perimeters`.

**The carried-by column names a part, and where a joint belongs to one *type* of a
part it names the type.** Row 7 reads *cowling bulkhead* rather than *bulkhead*,
decided in [OQ-DES-D6](#open-questions) on 2026-08-28: the cowl flange is a
`linear_extrude` whose height is zero on the end and interconnect types, so it is
not a feature those parts have, and section 3 was obliging their drawings to state
`cowl_n_perimeters` — a parameter that is not even a row on their parameter sheet.
An obligation no correct drawing can discharge costs the completeness test its
meaning.

**Row 10 reads *bolted bulkhead* for the same reason, found and fixed under
[IP-FC-133](../implementation/freecad_migration.md) on 2026-09-08.** The interconnect type has
no bolt at all — `bulkhead_section.emit()` skips `bolt_positives` outright and
`bulkhead_positive.flange_positive()` skips both bolt fillets and the greeble web that would
reach one, since an interconnect bolts to its neighbor rather than carrying a bolt of its own —
so `bolt_offset` is not a feature that part has, the same shape of gap `cowl_n_perimeters` was
on the end and interconnect types before row 7 was restricted. Found by running
`drawing_families.py`'s own completeness report after IP-FC-132 ported `is_interconnect`'s
annotation set (`sheet_annotations.py`'s `has_bolt` flag) to stop stating a bolt that is not
there: the report immediately named `bolt_offset` unstated on all three interconnect family
sheets, which an unrestricted *bulkhead* carrier could not tell from a drawing that had simply
forgotten it. The cowling type keeps the obligation — it has a real bolt hole and boss, just
none of the fillets or web that reach it on the end type.

**Row 5 reads *panelled bulkhead*, decided generally rather than for this row alone under
[OQ-DES-D12](#open-questions) on 2026-09-06.** A bulkhead with no panel — the 0 mm families
`bulkhead-end_anchor_end_bolt-257941` and `bulkhead-interconnect-b591ef` — has no panel-to-flange
joint to state, but `panel_offset` is not the zero that would have said so: it keeps an ordinary
nonzero value whether or not a panel is fitted, since it positions the corner rather than being
set by the panel interface. The structural-zero rule tests each name in a row for being zero and
cannot see this, because the row's *joint* is absent while most of its *names* are not.
Restricting the carrier the way rows 7 and 10 already do closes it the same way: a family with
no panel is not asked to explain a flange it does not have.

**The register's carrier column was split in two under [OQ-DES-D10](#open-questions), decided
2026-09-09.** *Carried by* had meant two different things — which part's geometry the gap is
cut out of, and which drawing is obliged to state the joint — and row 3 was the one place they
disagreed: the clearance is carried entirely on the corner, but the bulkhead has always
dimensioned the same four faces too (`corner_seat_offset`, decided under
[OQ-DES-D6](#open-questions)). **Clearance on** keeps the manufacturing fact; **Stated by**
lists every drawing the completeness test in section 3 obliges to state the row, and is read by
`CARRIED_BY` in [`tools/drawing_families.py`](../../src/Fuselage/tools/drawing_families.py). A
row may name more than one drawing there, comma-separated; row 3 is the only one that does today.

| # | Joint | Governing expression | Clearance | Clearance on | Stated by |
| --- | --- | --- | --- | --- | --- |
| 1 | longeron tube → corner bore | bore radius = `longeron_radius + longeron_tolerance`; lead-in chamfer = `w` | `longeron_tolerance` 0.05 | corner | corner |
| 2 | bulkhead greeble post → corner socket | socket radius = `longeron_radius + longeron_tolerance + greeble_thickness + greeble_tolerance`; post radius = `longeron_radius + longeron_tolerance + greeble_thickness`, the same sum without the clearance — so the whole fit is cut out of the corner | `greeble_tolerance` 0.05 | corner | corner |
| 3 | corner seating faces → bulkhead | `flat_offset = −max(longeron_radius + longeron_tolerance + extrusion_width, (panel_overlap + panel_offset) − (corner_radius − panel_thickness − panel_tolerance)) + corner_tolerance·√2`; `flat_x = −(panel_overlap + panel_offset) + corner_tolerance` | `corner_tolerance` 0.0 | corner | corner, seated bulkhead |
| 4 | panel → corner | seat at `corner_radius − panel_thickness − panel_tolerance`, a rebate `panel_thickness + panel_tolerance` deep from the mold line; end stop at `panel_offset − panel_tolerance`; extension `panel_overlap + panel_offset` | `panel_tolerance` 0.1 | corner | corner |
| 5 | panel → bulkhead flange | outer face, which is the panel's seating surface, at `unit_width/2 − panel_thickness − panel_tolerance`; exposed span `unit_width − 2·(corner_radius + panel_offset) − 2·panel_overlap` | `panel_tolerance` 0.1 | panelled bulkhead | panelled bulkhead |
| 6 | boom tube → boom bulkhead collet | `collet_radius = boom_diameter/2 + boom_collet_thickness + boom_tolerance` | `boom_tolerance` 0.2 | bulkhead | bulkhead |
| 7 | cowl → cowling bulkhead flange | flange outer radius = `corner_radius − n_p·w − cowl_flange_tolerance`; flange height `2·U` | `cowl_flange_tolerance` 0.2 | cowling bulkhead | cowling bulkhead |
| 8 | nose closure → cowl shell | base offset = `n_p·w + nose_flange_tolerance` | `nose_flange_tolerance` −0.1 | nose closure | nose closure |
| 9 | nose plate → nose closure | pocket radius = `plate_diam/2 + plate_tol`, relieved at `overhang_angle_from_bed` | `plate.tolerance` 0.1 | nose closure | nose closure |
| 10 | bolt or insert → bulkhead | `bolt_offset = 8·U` on the diagonal; `bolt_radius` = `diameter/2`, or the insert bore from [`threaded_insert_dimensions.csv`](../../src/Fuselage/tools/threaded_insert_dimensions.csv) | — | bolted bulkhead | bolted bulkhead |

**Rows 7 and 8 have not been reviewed for the same divergence row 3 had.** OQ-DES-D10's own
scope note flagged both as candidates — each names a fit between two parts that both get
drawings — and neither is known to diverge; row 3 is the only one measured to. Reviewing them is
follow-on work, not assumed clean.

**Row 4 was corrected on 2026-08-28, and it was not a wrong requirement — it was not a
requirement at all.** It read *"slot `2·panel_thickness + 2·panel_tolerance` deep"*, which is
the size of the **cutting primitive**: the square is drawn twice the pocket tall so that it
overshoots the material, and twice the overlap long so it opens through the end of the arm. The
material it is cut from ends at the mold line, so what is left is a rebate
`panel_thickness + panel_tolerance` deep with the panel's outer face exposed. Measured on the
built corner at 1U with a 3/16 in panel: the seat is a face at 5.1375 of 486.2500 mm², which is
`panel_overlap + panel_tolerance` times the part length, and no material stands outboard of it.

**An overshoot is an implementation artifact, and this one is sized from the feature it cuts**,
which is why it scaled convincingly across 264 variants and got recorded here as the joint's own
dimension. [design_basis.md section 7](design_basis.md#7-what-is-neither-implementation-artifacts)
states the rule that keeps the two apart and lists the artifacts the project already handles
correctly; IP-FC-88 is the change that stops this one reading like a design quantity. The
register carries **requirements**, so what belongs in this row is the rebate.

### The panel allocation, which joints 4 and 5 pin without stating

Panel dimensions have to be on the drawings, and the frame determines all of them. Joints 4 and
5 give the *interface* — the slot, the seat, the clearance — but not the panel's own size, and
the panel's own size is what a panel designer needs. It falls out of the same parameters:

| | Expression | At 1U, 3/16 in |
| --- | --- | --- |
| width, corner to corner | `unit_width − 2·(corner_radius + panel_offset)` | 75.000 |
| exposed span between corners | `width − 2·panel_overlap` | 65.475 |
| entry into each corner | `panel_overlap` | 4.7625 |
| thickness | `panel_thickness` | 4.7625 |
| pocket it seats in | `panel_thickness + panel_tolerance` | 4.8625 |
| inner face, from the airframe axis | `unit_width/2 − panel_thickness − panel_tolerance` | 45.1375 |
| outer face | the mold line, `unit_width/2` | 50.000 |
| length along the bay | `unit_length`, the full bay | 100.000 |

**The width expression is confirmed by a clearance, not by a face, and that is the stronger
check.** Take the panel to be 75.000 wide and its edge lands at corner-local x = −2.5000
against a slot bottom at −2.4000. The gap is 0.1000 — `panel_tolerance` exactly. No other width
fits the slot the corner was actually cut with.

**The panel runs the full bay length, and the bulkhead is cut out to let it.** That was settled
on 2026-08-22 and the geometry states it twice over. The bulkhead's outer profile sits at
45.1375 from the airframe axis, which is 4.8625 inboard of the mold line — exactly
`panel_thickness + panel_tolerance`, the panel pocket. And one of its outer flat faces measures
**392.850 mm²**, which is `65.475 × 6`: the panel's exposed span times the bulkhead thickness.
So the bulkhead's outer flat face *is* the panel's seating surface, cut back by precisely the
panel it seats and running precisely as far.

That is the reason a panel is not interrupted at a station: the bulkhead gives way to it rather
than the other way round. `unit_length − 2·bulkhead_thickness` = 88.000 was the alternative
reading, and it is wrong.

**The envelope becomes a part**, decided in [OQ-DES-D4](#open-questions) on 2026-08-22, so a
candidate panel design is checked against it by containment rather than by someone comparing it
against the expressions above.

### What the assembly drawing carries

Stated 2026-08-22, and it is a requirement rather than a preference: **the assembly drawings
show the projection of the panel and the corner onto the bulkhead top view.** On that view,

- the **panel width** and the **panel thickness** are dimensions;
- **`panel_tolerance`** and **`corner_tolerance`** are dimension callouts.

The bulkhead top view is the right carrier for this and not an arbitrary choice: it is the one
view where all three parts appear in the same plane. The bulkhead's outer flat face *is* the
panel's seating surface, and the corner's panel extension lands on that same view as a real
feature — the corner's extension face sits at 32.7375 from the airframe axis and the bulkhead
has a face there too. So the projection is of parts that genuinely share the plane rather than
a construction.

**The `corner_tolerance` callout will read 0.00, and that is the point of putting it there.**
[OQ-DES-C5](corner.md#open-questions) resolved on 2026-08-14 by creating the parameter and
holding it at 0, and recorded the residual plainly: *"if these faces are bonded, 0 leaves no
bond line."* A callout naming the clearance and showing 0.00 puts that in front of whoever is
assembling the airframe. This is **not** §2's structural-zero case — the joint exists and the
clearance was chosen — so the rule about omitting a dimensioned zero does not apply, and
omitting it would hide a live question rather than avoid a false claim.

### Three things the drawing has to say that a dimension alone does not

**Which part carries the clearance.** Joints 2 and 3 are both carried *entirely on the corner*
— the bulkhead re-evaluates the same shape and passes 0, so the joint takes the clearance once.
A drawing that dimensions both sides at nominal is not wrong about either part and is wrong
about the joint. An inspector measuring the bulkhead's post against a drawing that showed a
clearance would reject a good part.

**Which zeros are structural.** `panel_tolerance` is 0 on a cowling bulkhead and on the 0 mm
panel variants; `cowl_flange_tolerance` is 0 on every non-cowling type; `plate.tolerance` is 0
on `tail_high_open`, where the plate is inactive. **These are not settings at their minimum —
they are the absence of the joint.** A generated drawing must omit the dimension, not print
`0.0`, because a dimensioned zero asserts a coincident fit that was designed and inspectable,
and here there is nothing to inspect.

**Which constraint governs, when more than one can.** The corner's flat face is

```
flat_offset = -max(longeron_radius + longeron_tolerance + longeron_chamfer,
                   (panel_overlap + panel_offset) - (corner_radius - panel_thickness - panel_tolerance))
```

— a two-sided constraint. The face must clear the longeron bore *and* sit outside wherever the
panel interface has been pushed to, and **whichever binds, wins**. Which one binds changes
across the family. OQ-ARCH-7 chose a family drawing with a per-variant value table, so the
table carries the number; the note has to carry *which term produced it*, or a reader takes the
wrong design intent away from a correct number.

---

## 3. The completeness test

> **The set is complete when, for every entry in `design_constants.json`'s `tolerances` group,
> the drawing carries every dimension that entry's expression consumes — and, for a part that
> encloses a space, the span §1 names for it.**

Mechanical, and checkable against a file that already exists and is already validated —
`load_constants()` refuses a missing name and refuses an unrecognized one, so the group cannot
silently drift out from under the test.

The second clause was added with §1's on 2026-08-22 and costs the test nothing, because §1's
list is closed: two parts have an enclosed span, both are named there with their expressions,
and a part not on that list is not asked for one. What the clause buys is that a bulkhead
drawing missing its aperture now *fails* the test rather than passing it.

Worked: joint 7's expression consumes `corner_radius`, `n_p`, `w` and `cowl_flange_tolerance`.
The drawing carries the resulting flange radius and the clearance. `n_p·w` is the radial room
the **cowl's** wall occupies, so a drawing of the *bulkhead* that dimensions the flange without
saying what the subtraction is for leaves its most important number unexplained — the reason
the flange is where it is lives in another part.

> **A fourth gap, and it is larger than the three below.** Measured on the built
> parts on 2026-08-22, **6 of 22 interface parameters exist as a distance anywhere
> on their own part** — and one of those six is a value-matching coincidence. The
> rest are off by exactly a clearance, because §2's own principle puts the whole fit
> clearance inside the mating face. So "carries every dimension the expression
> consumes" is not satisfiable by dimension *lines*, and
> [OQ-DES-D2](#open-questions) settled what satisfies it instead: the dimension
> carries the feature and its callout carries the parameter, so the sheet states
> both and the test reads the pair rather than the dimension alone.

**Five known gaps in the test, stated rather than left to be discovered.** The last two were opened on 2026-08-30 by IP-FC-107 completing the register's expressions, which is the test finding work rather than the test breaking: both are reported on named families and neither affects a part.

1. **Joint 9's clearance is not in the group.** `plate.tolerance` lives in the per-cowl-type
   parameter files. That is defensible and follows the structural-zero pattern — it is 0.1 on
   `nose_round_plate` and 0 on `tail_high_open`, where there is no plate — but it means the
   test must read the cowl type files too, not only `design_constants.json`.
2. **Joint 10 has no clearance parameter at all.** A bolt through a hole and a heat-set insert
   in a bore are different fits, and neither is named. The insert bore comes from
   `threaded_insert_dimensions.csv`, which is the authority for insert geometry and must not be
   re-derived; the bolt clearance is not written down anywhere.
3. **`corner_tolerance` is 0 and its own note flags why that may be wrong.** [OQ-DES-C5](corner.md#open-questions)
   resolved on 2026-08-14 by creating the parameter and holding it at 0, which is what every
   flown part was built at. The entry records the residual plainly: *"if these faces are bonded,
   0 leaves no bond line."* That is the same question [OQ-DES-CW10](cowl.md#open-questions)
   answered for the nose base joint on 2026-08-21, and it is unanswered here. **A drawing
   generated today says nothing whatever about this fit** — corrected 2026-08-30, having
   previously read *"will dimension a zero-clearance fit"*. It does not dimension it: no quantity
   on the corner's sheet or the bulkhead's carries `corner_tolerance`, and both the
   structural-zero filter and section 5.2's H5 drop it while it is 0. A reader of the sheet has
   no way to learn that these faces meet line-to-line, or that they may need a bond line.
   [OQ-DES-D12](#open-questions), decided 2026-09-06, covers why the filter behaves this way — and does not fix this direction of it, which is [IP-FC-112](../implementation/freecad_migration.md).

4. **No bulkhead sheet dimensions the panel's exposed seating width**, which row 5 now states and
   the test therefore demands. Reported on four bulkhead families; two others are clean only
   because an unrelated dimension happens to be computed from the same two parameters on those
   variants. [OQ-DES-D11](#open-questions).
5. **A bulkhead with no panel is asked for `panel_offset`.** The structural-zero rule drops a
   row's parameters when they are zero on the family, and `panel_offset` is not zero on a
   panel-less bulkhead even though the panel joint is absent from it. Two families carry an
   obligation no correct drawing can discharge, which is the error [OQ-DES-D6](#open-questions)
   was decided to remove. **Answered by [OQ-DES-D12](#open-questions) on 2026-09-06**: a row's parameters drop when the row's joint is absent from the family, rather than when their values happen to be zero. Implementation is [IP-FC-110](../implementation/freecad_migration.md).

---

## 4. Internal structure is reference geometry

OQ-ARCH-7 chose alternative 3 first: **dimension the interfaces, show internal structure as
non-dimensioned reference geometry.** Nothing in this document reopens that.

The reasoning is worth restating because it is easy to read as a shortcut and it is not one.
Internal structure here — webs, fillets, greeble nubs, buttress ramps — is **derived**, not
chosen. `web.fillet_radius` is `2·U`, `bulkhead_flange.chamfer` is `1·U`,
`plate.thickness` is `ceil(4·U)·layer_height`. Dimensioning a derived quantity on a drawing
duplicates a formula that already exists in one place, and a duplicate that can disagree is
worse than an absence. The variant table carries the value; the formula stays in
`derived_parameters()`.

**What promotes an internal dimension to the interface set** is the membership test in §1 and
nothing else: another part's geometry coming to depend on it. That is not hypothetical —
`n_p·w` began as a property of the cowl's wall and now sets the *bulkhead's* flange radius
(joint 7), and the same count reaches the nose closure's base offset (joint 8). When that
happens the dimension moves into the register and the drawing gains it.

---

## 5. Placing the dimensions

Knowing *which* dimensions to carry is half the problem. A drawing whose dimensions overlap
each other, sit on top of an edge, or run off the sheet is not a drawing — and unlike a wrong
model, nothing downstream catches it. It renders, it exports, it prints, and then someone reads
`12.5` as `12.6` and makes a part.

**These cannot be hand-placed.** Placement has to be a rule set with a machine-checkable
outcome, for the same reason the rest of this project's decisions are: taste does not survive
regeneration.

### 5.1 Two products, and only one of them is solved once per family

[OQ-ARCH-7](../architecture/freecad_migration.md#open-questions) chose **lettered callouts plus
a per-variant value table**, and that choice does most of the work here: the letters are placed
once against the drawn representative view, and the table carries the numbers. One solve per
drawing, not 576.

**[OQ-DES-D1](#open-questions) added a second product on 2026-08-22, and it does not inherit
that property.** Alongside the family sheets the build emits **single-variant drawing sets**,
keyed on `U` and panel thickness — **72 sets of 11 drawings**, each drawing its own file, the files of a set collocated
so the set can be delivered together. A set holds every part needed to build a fuselage at that
size and panel, **including the whole `FX` range** — but `FX` is carried by a table rather than by
six corner sheets, because with `U` and panel fixed exactly one dimension moves with it. Those 792
sheets carry values on the view rather than callouts, so each is placed on its own: **792 solves,
not one**. That is affordable — the solver is
arithmetic over a dozen rectangles — but it is a different claim from the one this section
opened with, and the difference is load-bearing for §5.2's extent bound.

**The family table is factored by axis**, per OQ-DES-D1: one short table per size axis rather
than one row per variant, plus a small matrix for each field that follows two axes. What makes
that possible is measured rather than assumed — asking, for each dimension, which axes it is
actually a function of over the whole family.

**But the family must be partitioned by topology, not by size.** A no-panel variant and a
panelled one cannot share a sheet, because a callout pointing at a feature that is not there is
worse than no drawing at all — the reader trusts it. This is §2's structural-zero rule
reappearing at the sheet level: where a dimension is absent because the *joint* is absent, that
is a different drawing, not a blank cell in the table. Size, by contrast, changes only the
values, which is exactly what the table is for.

### 5.1a What the partition and the factoring actually come to

Both were estimated when OQ-DES-D1 was filed and both are now computed, by
[`drawing_families.py`](../../src/Fuselage/tools/drawing_families.py). **Three of the numbers
the question was decided on were wrong, and none of them reverses the decision** — the
factoring works better than claimed, not worse. They are corrected here because a reader
otherwise takes the estimates for measurements.

| | Filed as | Measured 2026-08-22 |
| --- | --- | --- |
| Family sheets | 18 | **13** |
| Fields needing two axes | 2 | **5** |
| Rows an ANSI A sheet holds | "about 25" | **19** |
| Families that overflow one sheet | 12 of 18 | **0 of 13** |

**Thirteen sheets rather than eighteen, because two type axes are not topology.** The
partition is taken from the *features a resolved part has*, not from the names on its type
axis, and two distinctions that read as separate parts are not. `end_bolt` and `end_anchor`
reach the same OpenSCAD module with the same arguments and differ in exactly one number —
`bolt_hole_radius`, 1.95 mm against 1.50 mm at `U` = 0.5 — so under §1 they are one part in two
sizes. `offset_single` and `dual` likewise: the boom bulkhead has no mirrored second boom, and
the two differ only in where the single boom sits. The cowling types account for the rest, and
for a different reason: `bulkhead_validity_check` refuses a cowling row with a panel, so a
panelled cowling family does not exist to be drawn.

**Five coupled fields rather than two, and the three new ones are the same finding.** Demoting
a type axis from a sheet to a table column is what makes `bolt_hole_radius`, `boom_y_position`
and `boom_z_position` follow two axes — they were single-axis while the type was a sheet, and
they are `U` × type now. The original two, `panel_offset` on `U` × panel and `unit_length`
(the corner's bay length) on `U` × `FX`, are unchanged.

**Nineteen rows rather than about twenty-five, because the sheet was measured.** The column a
value table gets is the frame's top edge down to the title block — 139.0 mm on the pinned ANSI
A landscape template — and at the 7.0 mm row pitch the drawing standard used then, that is 19
rows. [OQ-DES-D5](#open-questions) later gave the table its own 2.5 mm text at ISO 3098's
1.4 h line spacing, and moved it beside the title block; the figures in this section are left
at the size and placement they were measured on. The
"about 25" was a guess at a sheet nobody had opened.

**Every family fits down the page, and five of them fit exactly.** What closes the gap is that
tables sharing a leading axis are **one block**, not several: a `U` table and a `U` × panel
matrix put the same eight values of `U` down the left, so printed separately that column is
printed twice. Merged, the single-axis fields are ordinary columns and each coupled field is a
band of columns inside the same table. The panelled corner then costs a 10-row `U` block and a
9-row panel block — 19 of 19, with **nothing spare**. That is a fit in the arithmetic and not on
paper: one more dimension, one more panel stock, or a title row above the table puts them on a
second sheet.

**Across the page it did not fit, and the reason was the layout rather than the factoring —
[OQ-DES-D5](#open-questions), decided 2026-08-22.** The rows were the only budget the factoring
was ever checked against. Measured, the table as first laid out cost **a third of the frame**;
compacted and packed abreast it costs **a ninth**, printing the same values.

**So the row figures above are an artifact of stacking the blocks**, and so is the budget they
were measured against. Packed abreast the panelled corner costs **10 rows, not 19** — and under
the decided layout the table sits *beside* the title block rather than above it, so the budget
is the band's depth rather than a full column. At the table's own 2.5 mm text and ISO 3098's
1.4 h line spacing the band holds **13 rows**, and no family needs more than 10. The figures in
the table above are left as they were measured, because they are what OQ-DES-D1 was decided
against; the sheet is laid out to OQ-DES-D5.

### 5.2 Hard constraints — violation fails the build

Every one of these is checkable on the produced drawing. None is a preference.

**These are `DRW-1` … `DRW-5` in
[system_requirements.md section 6](system_requirements.md#6-drawing-requirements)**, where H1 is
DRW-1 and so on in order. They were unnumbered here until 2026-08-29, and a hard constraint that
fails the build is a requirement whether or not it has an id.

| | Constraint | Why it is hard rather than soft |
| --- | --- | --- |
| **H1** | **Containment.** The full extent of every dimension — text box, dimension line, arrowheads, witness lines, any leader — lies inside the view frame and inside the sheet's printable area. | A dimension partly off-sheet is not a dimension. |
| **H2** | **Text does not touch text.** No two dimension text boxes intersect, and the clear gap between them is at least one text height. | A smaller gap reads as a single block of digits. |
| **H3** | **Text does not touch geometry.** No text box intersects a visible edge, a hidden edge, a centre line, or a hatch region. | Text over a line is the most common way a digit is misread. |
| **H4** | **A witness line does not cross a dimension line.** Crossing another *witness* line is conventional and permitted. | At the crossing the reader cannot tell which extension belongs to which measurement. |
| **H5** | **No structurally-zero dimension is placed at all.** | §2. A dimensioned zero asserts an inspectable coincident fit; where the joint is absent there is nothing to inspect. |

**How an annotation's extent is known, since nothing headless renders it.** H1, H2 and H3
all test the rectangle an annotation occupies. Measured 2026-08-21 under `freecadcmd`
([`spike_techdraw.py`](../../src/Fuselage/freecad/spike_techdraw.py)): the dimension line
reads back exactly, but `getArrowPositions()` returns the origin for both arrowheads, and
no call reports the text's rendered width — both are computed by the GUI-side view
provider. **On a family sheet, §5.1 is what makes this a bound rather than a problem.** The text on such
a view is a single lettered callout, so the set of strings the drawing can contain is 26 items
known before any variant is built. Measured across the three candidate fonts at a 3.5 mm text
height, a capital spans 0.772 mm (`I` in osifont) to 3.461 mm (`W` in DejaVu Sans), and the
worst spread for any one letter is 1.270 mm. So **every callout is bounded by the widest
letter in the widest font**, and because they are all the same length that bound is uniform
— it shifts the layout without distorting it, which a bound on variable-length value text
would not. Arrowheads take a fixed multiple of the text height, being identical on every
annotation. Witness-line extent is exact, from `getLinearPoints()` and the referenced
points.

**Single-variant sheets do not get that bound, and must not be given it.** Their views carry
the value rather than a letter — `112.50 mm` is 5.3 times the width of `W`, and value strings
differ from one another — so there is no uniform number that is both safe and useful. Their
annotation widths are **measured exactly** from the pinned font instead, which costs a lookup
per string and is what [OQ-ARCH-18](../architecture/freecad_migration.md#open-questions)
recommended before it was withdrawn as unnecessary for the product that existed then. The two
products place under two extent models and collapsing them into one would silently mis-size
every annotation on 792 sheets.

Two conditions ride on the callout bound and neither is automatic. **The font and its size must
be project data** — TechDraw's preference groups are empty, so today the text is drawn with a
compiled-in default a user setting can silently change, and a bound taken from a font the
reader's machine does not use is not a bound. And **the value table is not covered by
it**: its columns hold variant values, whose widths do vary. That is a grid-sizing problem
— each column as wide as its widest cell — and not the collision problem this section is
about, but it is the one place on the sheet where value text still has to be measured.

This was filed as a blocking open question (OQ-ARCH-18) and withdrawn on 2026-08-22: the
question had measured `20.00 mm` and `112.50 mm`, which §5.1 had already moved off the view.

### 5.3 Soft costs, minimized in this order

1. **Nest by magnitude — smaller dimensions inboard, larger outboard.** This heads the list
   because it is not aesthetic: it is the arrangement under which witness lines do not *need*
   to cross dimension lines, so it is what makes **H4** satisfiable rather than a constraint to
   fight. Get this wrong and the solver spends its effort escaping a problem it created.
2. **Fewest witness-line crossings with geometry edges.**
3. **Fewest lanes.** Dimensions sharing an offset share a lane; fewer lanes means shorter
   witness lines and a tighter drawing.
4. **Text nearest the feature it dimensions**, subject to everything above.
5. **Balance across the sides of the view**, rather than stacking on one.

### 5.4 Two numbers, and everything else derived

Lanes are regular: the first dimension line stands off the outline by a gap `g`, and successive
lanes are spaced by `s`. **`g` and `s` are the only tunables in the whole placement scheme** —
every other position is derived from the geometry, the lane index, and the rules above. Keeping
it to two is deliberate and follows the same reasoning as the interior surface's single
tolerance ([cowl_interior_surface.md §5](cowl_interior_surface.md)): a scheme with a dozen
knobs is a scheme nobody can reason about, and the knobs get tuned per drawing until the rules
no longer mean anything.

Both scale with text height, not with `U`. The reader's eye does not get bigger when the part
does.

### 5.5 Determinism

**The same family produces byte-identical placement on every run.** No unseeded randomness, no
dependence on dictionary or set iteration order, and every tie broken by a stated total order —
callout letter is the obvious one.

This is not fastidiousness. A generator whose output moves between runs makes *"did this
drawing change?"* unanswerable, and a drawing set that cannot be diffed cannot be reviewed. The
same problem already bites elsewhere in this project: OpenSCAD emits the same mesh with a
different facet order on every run, so STL bytes are not a comparison basis on that path. Do
not introduce a second instance of it somewhere a human is the consumer.

### 5.6 Fail rather than emit an unreadable drawing

If the hard constraints cannot all be satisfied, **the build fails and names the dimensions
that could not be placed.** It does not relax a constraint, shrink the text, or emit the
overlap.

The escape hatch when a view genuinely cannot hold its dimensions is to **split the view or add
a detail view** — a drafting decision, made deliberately — not to accept a worse drawing.

**The checker is independent of the placer.** It reads the produced drawing, re-derives every
constraint in §5.2 from the placed annotations and the projected geometry, and fails on
violation. Independent because a placer that certifies its own output has only proved it is
self-consistent, which is not the claim anyone needs.

### 5.7 What to test it against

Not "does it look right". Every constraint in §5.2 is machine-checkable, so the acceptance test
is that the checker passes over a corpus — and the corpus is chosen for difficulty rather than
for coverage:

- **The smallest variant**, where there is least room and the drawing is densest.
- **The largest**, where witness lines are longest and containment binds first.
- **Each topology class** — no-panel, anchor versus bolt, cowling versus not — since §5.1 makes
  each of these a separate sheet, and the sparse ones are where a stale callout would survive.

- **A single-variant sheet at the largest `U`**, where the annotation text is widest — the one
  case the family sheets cannot exercise at all, since their views carry one letter regardless
  of variant. Measured 2026-08-22: the dense twelve-dimension case places in four lanes as both
  products, at 2.66 mm annotation width as a family sheet and 5.75–9.22 mm as a single-variant
  sheet, so widening the text cost no lane. That is the current state and not a guarantee —
  it is exactly the measurement to repeat when the dimension set grows.
- **A corner sheet from a single-variant set**, which is the only case that mixes both extent
  models on one sheet — measured values everywhere and one lettered callout for the `FX`-tabled
  length. It places clean in four lanes, with the tabled length taking the outermost lane on its
  own because it has the widest span. A sheet carrying only one kind of annotation cannot catch
  a bound applied to the wrong kind.

Sweeping the size axis alone will not reach the cases that break this. The topology boundaries
have to be walked deliberately, from both sides.

---

## 6. Scope

This document owns the enumeration (§2), the completeness test (§3), the reference-geometry
rule (§4), and the placement rules and their acceptance test (§5).

It does not own sheet size, title block, projection convention (first or third angle), line
weights, or standards compliance — none of which are decided.

**§1 and §2 are a placeholder for a section of a document that does not exist.** OQ-ARCH-7
assigns interface conventions to `doc/architecture/overview.md`. When that is written they
belong in its interface-conventions section, and what stays here is the drawing-specific part:
§3's completeness test, §4's reference-geometry rule, and §5's placement rules.

## Open questions

| ID | Question | Blocking |
| --- | --- | --- |


### ~~OQ-DES-D1 — What carries the size variation, when the largest family is 384 variants?~~ — DECIDED 2026-08-22: factor the table by axis, and add a second product

**Chosen: alternative 2, plus alternative 5 as a companion rather than a competitor.**

**The family drawing factors its table by axis.** One short table per size axis with each callout
labelled by the axis it follows, plus a small matrix for each coupled field. The corner's 384-row
table becomes an 8-row `U` table, a 6-row `FX` table and an 8-row panel table — 22 rows — with an
8 × 6 matrix for `corner.length` and an 8 × 8 matrix for `panel.offset`. The measurement that
supports this is recorded in §5.1: across every part family in the sweep the entire coupled
surface is those two fields, and the two cowling bulkheads are coupled to nothing at all.

> **The counts in this note are the ones the question was decided on, and three of them were
> estimates that turned out wrong. §5.1a carries the measured figures** — 13 family sheets rather
> than 18, five coupled fields rather than two, and 19 rows to a sheet rather than about 25. The
> decision stands on all three: every family fits one sheet, which is more than the question asked
> for. The note is left as written because it records what was decided and why; §5.1a is where the
> numbers now live.

**And the build also emits single-variant drawing sets.** A set is keyed on **`U` and panel
thickness**, and it holds a drawing for every part needed to build a fuselage at that size and
panel — **including the whole `FX` range**, because a fuselage uses more than one bay length and
a set that carried only one would not be a build kit. Each drawing is its own file, and the files
of a set are collocated so the set can be delivered as a unit.

**`FX` is carried by a table, not by six corner sheets.** The corner is drawn once at `FX = 1.0`
and the dimensions that move with `FX` are tabled. That is not a compromise on this part, because
of how little moves: with `U` and panel fixed, **exactly one dimension varies with `FX`** —
`corner.length`, which is `100·U·FX` — `unit_length` is 100 mm at 1U, and it is the one standard value `FX` scales. The only other field that changes is `corner.FX` itself,
which is the axis parameter and not a dimension. Measured across `U = 0.5`, `1.0` and `4.0`; the
result is the same at each. So a corner sheet carries values everywhere and **one lettered callout
over a six-row table**, and a set holds 11 drawings rather than 16.

| | Family drawings | Single-variant sets |
| --- | --- | --- |
| Keyed on | topology (§5.1's partition) | `U` × panel thickness |
| Count | 13 sheets (18 as estimated; see §5.1a) | 72 sets |
| Contents | one part kind, all sizes in a table | 11 drawings: 1 corner (drawn at `FX = 1.0`, `FX` tabled), 5 bulkheads, 3 boom bulkheads, nose, tail |
| View carries | a lettered callout | the value, except where a dimension is tabled |
| Total sheets | 13 | 792 |

The five bulkheads and three boom bulkheads do **not** collapse the same way, and the reason is
not the one first given here. It is not that every type axis is topology — §5.1a measures that
two of them are not — but that a set is a **build kit**: `end_bolt` and `end_anchor` are two
parts a builder installs in two places, and they need two sheets whether or not their *family*
sheets merge. Sharing a family sheet and needing separate single-variant sheets are compatible,
because the family sheet carries a callout and the single-variant sheet carries the number.
11 is the floor, not a first cut.

**Why both, and why that is not redundancy.** They answer different questions. The family drawing
is the reference document: it shows that the scheme is complete, that a dimension is an expression
over parameters, and how a value moves with each axis — which is what a reviewer and a designer
need. The single-variant sheet is what a shop receives: one number per callout, no lookup, no
chance of reading the wrong row. Alternative 2's one real drawback was that a per-axis lookup asks
the reader to combine tables correctly; the second product removes that from the person least
placed to absorb it.

**A consequence that has to be carried, because it reverses a simplification.**
[OQ-ARCH-18](../architecture/freecad_migration.md#open-questions) was withdrawn on the grounds
that a view carries only a lettered callout, so every annotation is the same width and one
conservative bound covers all of them. **That reasoning holds for the family drawing and does not
hold for the single-variant sheet**, whose view carries the value: `112.50 mm` is 5.3 times the
width of `W`, and value strings differ from each other, so no uniform bound is both safe and
useful. This does not reopen the question — the measurement it asked for is available exactly as
it recommended, from the font file through `fontTools` — but the two products now place under two
different extent models, and that must not be quietly collapsed into one.

Measured rather than assumed: the dense twelve-dimension case places in four lanes both ways, with
annotation widths of 2.66 mm as a family sheet and 5.75–9.22 mm as a single-variant sheet across
the `U` range. Widening the text did not cost a lane, because lane assignment here is driven by
span nesting rather than by text collision. A corner sheet **mixes both** — ten measured values and
one tabled callout — and places clean in four lanes, with the tabled overall length falling to the
outermost lane on its own, since it has the widest span and §5.3's nesting rule puts it there.

**One thing the `FX` table demands that this document does not own.** A view drawn at `FX = 1.0`
with `corner.length` tabled is **not to scale for five of the six rows** — at `U = 1.0` the part
is 100 mm as drawn and 300 mm at `FX = 3.0`. Drafting standards require a not-to-scale dimension to
be marked, and this sheet has exactly one. Which convention marks it — an underlined value, a
general note, a symbol — belongs to the standards-compliance question §6 lists as undecided. It is
recorded here because the `FX` decision is what creates the requirement, and an unmarked
not-to-scale dimension on an otherwise true-scale sheet is a drawing that lies quietly.

**Alternative 3 was rejected rather than deferred**, on the reasoning given when the question was
filed: promoting a size axis to a sheet axis buys a fitting table by making the partition mean
nothing, and §5.1's rule is what lets a reader trust that a callout points at a feature the part
actually has.

*Implementation: IP-FC-21 (family drawings), IP-FC-84 (single-variant sets).*

### ~~OQ-DES-D2 — How does a dimension state a joint, when the reader is integrating rather than inspecting?~~ — DECIDED 2026-08-22: the dimension is the feature as built, and a callout beside it names the hardware

**Chosen: alternative 3.** A dimension gives the feature the way the part actually is, and the
callout beside it says what the feature is for:

```
⌀4.10 BORE
FOR ⌀4.00 LONGERON
0.10 DIA CLEARANCE
```

Both readers are served by one annotation, and the two numbers cannot drift apart, because the
callout and the dimension are generated from the same expression.

**Why the other three lost, which the drawings made plain in a way the prose had not.**
Dimensioning only the features as built states none of the three hardware sizes and not by
arithmetic either — the clearance is the term that would let a reader work backwards, and it
never appears on the sheet. Dimensioning the nominals instead, to the mating parts drawn as
reference geometry, states every hardware size and leaves every dimension disagreeing with the
part: a caliper on the bore reads 4.10 against a drawing that says 4.00. Moving the hardware
into a schedule beside the view works, and it costs table rows the sheets do not have — five of
the thirteen family sheets measure 19 of 19 available rows with nothing spare (§5.1a — under
OQ-DES-D5's layout every family measures 10 of 10, which is the same finding at a different
budget). The
callout costs nothing off the view.

**The risk this takes on, stated because it is real and not yet measured.** §5.2's hard
constraints are about the rectangle an annotation occupies, and a three-line callout is several
times a bare dimension's extent. Whether a whole part's worth of them places without collision
is measurable with what is already built — `drawing_standard.text_width_mm` measures arbitrary
strings from the pinned font — and has not been measured. **If they do not place, alternative 4
becomes the answer and the sheet size becomes the question**, which is the right order: a larger
sheet is a smaller decision than a drawing that does not say what it is for.

**A finding this surfaced that the decision does not fix.** The bolt hole is ⌀4.00 for a
nominal 4 mm bolt — a line-to-line fit with no clearance at all, because joint 10 is the one
interface in the register with no clearance parameter (§3, gap 2). What the callout does is
make that *visible*: it prints the fastener beside the hole, where a bare `⌀4.00` says nothing
and a reader has no way to notice the bolt will not pass.

*The alternatives as drawn are in
[`draw_dimension_alternatives.py`](../../src/Fuselage/tools/draw_dimension_alternatives.py),
which annotates the corner's mid-bay section four ways from geometry traced off the built
solid. Implementation: IP-FC-21.*

### ~~OQ-DES-D3 — The drawing's rule for what to dimension can only see parts that are in the model~~ — DECIDED 2026-08-22: the aperture is a dimension and goes on the drawings; volume goes in a data block

**The aperture span is a dimension, and it is worth having on the drawings.** It is not a
special case needing a new kind of annotation: it is the distance between two real, parallel,
planar faces, and it dimensions exactly like the bore or the panel pocket does.

Measured on the built parts to confirm that before generating it, because a dimension across a
bounding box that merely touches at some corner feature would not be one:

| Part | Interior faces | Area of each | Span |
| --- | --- | --- | --- |
| frame bulkhead | ±43.9375 in **both** axes | 247.3 mm² | **87.875** |
| boom bulkhead | ±39.1375 in both axes | 93.7 mm² | **78.275** |

**And it is an expression over the parameters, not a measurement** — which matters, because a
dimension bound to a measured face is bound to the topology, and IP-FC-5 established that face
counts move with `U`. Both check exactly against the faces above:

```
frame bulkhead   unit_width - 2*(panel_thickness + panel_tolerance) - 2*flange_thickness
                 100 - 2*(4.7625 + 0.1) - 2*1.2   = 87.875
boom bulkhead    unit_width - 2*(panel_thickness + panel_tolerance) - 2*web_width
                 100 - 2*(4.7625 + 0.1) - 2*6.0   = 78.275
```

The two differ in their last term because the ring's inner boundary is set by the flange on a
frame bulkhead and by the web on a boom bulkhead. That is a real difference between the parts,
not a naming inconsistency.

**A caveat the boom bulkhead needs and the frame bulkhead does not.** On a boom bulkhead the
span between the interior faces is 78.275 in both axes, but the *clear* opening is
78.275 × 66.402, because the boom collet intrudes from one side. The dimension is the span; the
obstruction is visible in the view. A reader asking "what fits through" needs to look at the
view and not only at the number, and on this part alone those are two different answers.

**What this changes in §1.** The membership test was *dimension it if another part's geometry
depends on it*, which is a test about joints. The aperture has no joint — nothing in the model
mates with it — and everything the airframe carries depends on it. The rule gains a second
clause and stays closed rather than open-ended: the enclosed span of each part that has one, by
name, so the completeness test remains a lookup rather than a judgment.

**Volume goes in a data block.** Either a data area or a callout was acceptable; the block is
chosen because a callout points *at* a feature and volume is a property of the whole part, so a
leader would have nothing to land on. It carries the solid volume and the wall area, which are
the two numbers that let a reader work out material for their own slicing — and neither of them
depends on a slicing choice, which is what makes them safe to print. **Mass stays off**: it
needs a filament density and the reader's perimeter count, and the design constrains neither.

On a single-variant sheet the block is three lines. On a family sheet, volume and wall area vary
with every size axis, so they become two more columns in the factored tables — which costs sheet
*width* rather than rows, and width has not been budgeted the way §5.1a budgeted rows.

*Implementation: IP-FC-21.*

### ~~OQ-DES-D4 — Panels are to get their own OML allocation, and nothing in the model owns one~~ — DECIDED 2026-08-22: the panel OML becomes a part

**Chosen: the allocated envelope itself becomes a part, and panel designs are then made to fit
within it.** That is not one of the four alternatives as filed — those offered a derivation, a
*panel* part, a data file, or nothing — and it is better than any of them for one reason: an
envelope that is a part can be checked against **geometrically**, by containment, rather than
by a person comparing a candidate against numbers somebody transcribed. Interchange is the
stated purpose, and a containment test is what interchange actually needs.

It also keeps the panel itself out of the printed-part pipeline, which was the real cost of
making the *panel* a sweep part: a panel is cut sheet, not a print, and it does not fit the
assumptions the rest of the sweep carries. The OML part is not a manufactured object at all —
it is the space a panel is allowed to occupy.

**The envelope is complete and every boundary of it is verified.** All of it is in §2's
register, and each figure is an expression over parameters that a built face confirms:

| | Expression | At 1U, 3/16 in |
| --- | --- | --- |
| width, corner to corner | `unit_width − 2·(corner_radius + panel_offset)` | 75.000 |
| exposed span between corners | `width − 2·panel_overlap` | 65.475 |
| entry into each corner | `panel_overlap` | 4.7625 |
| thickness | `panel_thickness` | 4.7625 |
| pocket | `panel_thickness + panel_tolerance` | 4.8625 |
| inner face from the airframe axis | `unit_width/2 − panel_thickness − panel_tolerance` | 45.1375 |
| outer face | the mold line, `unit_width/2` | 50.000 |
| length along the bay | `unit_length`, the full bay | 100.000 |

**A claim made twice while this was open, and wrong both times.** It was asserted here that the
four faces of a bay are not alike — that a boom passes through one and a cowling station closes
an end. Neither holds, and both were checked only after being written down:

- **The cowl closes an end of the airframe**, perpendicular to the fuselage axis. It never
  touches a side face where a panel sits. That was a confusion between the end of the fuselage
  and a face of a bay.
- **The boom runs parallel to the fuselage axis, inside the airframe.** `boom_key_shape` is
  inside the `linear_extrude`, so the boom hole is a 2D feature extruded through the bulkhead's
  thickness. It reaches 32.20 mm off-axis against a panel inner face at 45.1375 — it clears the
  panel by **12.94 mm** and never reaches a side face at all.

**So there is no evidence the four faces of a bay differ**, and the allocation is one envelope.
That is also what the decision implies: the OML is a part, and what differs between faces is the
*panel design* fitted into it, which is exactly the interchange the allocation exists to allow.

**One real difference between stations, which is not a difference between faces.** The boom
bulkhead presents a 75.000 mm seating face to the panel where the frame bulkhead presents
65.475 mm — measured as 150.000 mm² and 392.850 mm² over thicknesses of 2 and 6. Different
stations give the same panel different amounts of seat. Worth knowing; it does not bear on the
envelope, which is set by the corner.

*Implementation: IP-FC-85 for the OML part, IP-FC-22 for the assembly drawings it appears on.*

### ~~OQ-DES-D5 — How is the value table laid out, when the view must have three quarters of the frame?~~ — DECIDED 2026-08-22: compact the table, and draw our own title block

**Chosen: alternative 2.** The value table is compacted and its blocks packed abreast, and the
sheet gets a title block of this project's own rather than the stock ASME one.

**The requirement the decision serves**, stated 2026-08-22: *the drawn view takes at least 75 %
of the frame, and the title block and the values share what is left.* Read as the frame rather
than the paper, since 75 % of an ANSI A sheet is more than the whole frame.

**Compaction, which prints the same numbers in under a third of the area.** Worst of the
thirteen families, carrying §3's interface floor, from **14 949 mm² to 4 329** — 33.3 % of the
frame to **9.7 %** — and the next largest is 1 329 mm², 3.0 %. Each step is a layout choice and
none removes a value:

| | Decided as |
| --- | --- |
| decimals | per column, at the fewest places that loses nothing. `DECIMAL_PLACES` is a **bound** on the precision a value may carry, not an instruction to print that many places whatever the value is |
| band headings | the stock name without its unit — `3/16` — with the unit stated once above the band |
| column gutter | **1.0 mm**, not one text height. §5.2's H2 governs annotations floating on a view with nothing between them; a ruled table has a rule between its columns. **The rule is drawn and checked for**, not assumed — `sheet_table.check_layout` refuses a table whose cells are closer than H2's clearance with nothing between them |
| text height | **2.5 mm**, one size down from the view's 3.5 in ISO 3098's preferred series. The table had simply inherited the view's height because there was one constant, and a table setting smaller than the annotations around it is what every title block and parts list does |
| row pitch | **1.4 text heights** — ISO 3098's minimum line spacing for type B lettering, the same rule the leader notes follow. It was 2, matching the dimension lanes' pitch, which is an argument about how the sheet looks; then 1.3, which fit the band and is **below the standard's floor** |
| packing | blocks **abreast**, not stacked. Two blocks on different axes have nothing to do with each other, and stacking adds their row counts where placing them side by side takes the larger |

**And the view's share is a packing result, not an area subtraction** — a view is a projection
with a bounding box, so what it gets is the largest *rectangle* left once the title block and
the table are placed. Only two placements leave one: a **band** across the bottom carrying the
title block and the table with the view full width above, or a **column** up one side with the
view full height beside. The column is as wide as the *wider* of the two, so a table narrower
than the title block gains nothing by being narrower.

**Which is why the title block is what binds, and it binds twice.** At 146.66 × 48.074 mm it is
7 051 mm² — **63 % of everything that is not the view**, larger than every family's table put
together. Its depth caps the view at **74.3 % with no table on the sheet at all**, so the
requirement is unreachable on the stock template whatever the table does; and its width leaves
91.9 mm beside it, where the compacted table is 95.1, so the band placement is unavailable and
the layout falls back to a column giving the view 38.4 %.

**What the decision specifies is an envelope, not a size.** For the view to reach 75 %:

> **the title block fits inside 132.7 × 46.8 mm.**

Any block inside that envelope gives the same view share, because past the point where the block
is shallower than the table the band's depth *is* the table — which is why 120 × 40 and 100 × 32
measure identically at 75.7 %. So the size is free within the envelope and should be settled by
what the block has to hold. **The stock block misses it by 3.2 mm of width and 1.3 mm of depth**,
which is how close the sheet came to working untouched.

**That figure was 143.4 × 46.8 mm until 2026-08-27 and it was measured against the wrong
table.** It came from the widest *parameter mapping* any family carries at §3's floor, 95.1 mm,
which is what the compaction ladder measures because that is the content OQ-DES-D1 was decided
on. What a sheet prints is its **quantity** table — the columns the view's callout letters
point at — and the widest of those is the panelled corner's at **105.8 × 35.0 mm**, 10 mm
wider. The envelope narrows to match. The pinned block is 130.0 × 46.0 and still fits, with
**2.7 mm of width and 0.8 mm of depth to spare**, so the decision holds; the margin is simply
smaller than the number said, and a margin quoted from a table nobody prints is not a margin.

**A defect this fixes that is not a layout problem.** The sheet states its units nowhere: cells
are bare numbers, annotations are bare numbers, and the stock template has no field for a unit.
A drawing whose numbers are millimeters and does not say so is wrong in a way no compaction
reaches, and the block is where that field goes.

**Two things the alternatives ruled out.** A larger sheet buys room by making the paper bigger
rather than the layout better, which the compaction shows was never necessary — and it leaves
the same stock block, so the sheet still states no units. Presenting `panel_offset` as an
expression rather than a band removes the most millimeters for the least work and removes them
from a dimension §2's register names and §3 obliges the sheet to carry; if a printed expression
satisfies §3 that is a change to §3 and should be argued as one.

**The reserve, if a later dimension does not fit:** make panel stock a sheet axis for the
corner, which is the only family with a wide band. It costs sheets, which are cheap, rather than
legibility, which is not.

**Two of the numbers above were corrected on 2026-08-27, and the correction is part of the
resolution rather than a footnote to it.** The row pitch was set to **1.3 text heights** to make
the band arithmetic work — below ISO 3098's 1.4 h minimum for type B lettering, while the same
1.4 was cited three files away as the floor for note line spacing. That is precisely what §5.4
warns of: *the knobs get tuned per drawing until the rules no longer mean anything*.

The squeeze that forced it came from a second choice nobody had made: **the table was setting at
the view's 3.5 mm**, because there was one text-height constant and the table inherited it. A
value table sets one size smaller than the annotations around it, which is what every title
block and parts list does. At **2.5 mm with the standard's 1.4 h spacing** the table is smaller
on both axes than it was at 3.5 mm and 1.3 h, so the sheet obeys the lettering standard *and*
has more room than the version that broke it. The band holds **13 rows, not 10**.

*Implementation: IP-FC-21 for the compaction, IP-FC-86 for the title block and template.*

### ~~OQ-DES-D6 — The completeness test asks what a mapping carries, not what the geometry consumes~~ — DECIDED 2026-08-28: name the type in the register, and state joint 3 on the bulkhead

**Resolution note.** Both alternatives 2 and 3 were taken, and they are not competing: the one
error message covered two different problems.

**Alternative 2 — the register's carried-by column names a type where a type owns the joint.**
Row 7 now reads *cowling bulkhead*. The cowl flange is a `linear_extrude` whose height is zero
on the end and interconnect types, so it is not a feature those parts have, and section 3 was
obliging their drawings to state `cowl_n_perimeters` — which is not even a row on their
parameter sheet. `CARRIED_BY_TYPES` carries the restriction and `interface_fields` takes the
family's type names. Four family sheets stop being asked for something no correct drawing can
give; the cowling family keeps the obligation, and its two remaining names are unfinished work
under IP-FC-12 rather than an unanswerable demand.

**Alternative 3 — the bulkhead states joint 3.** `extrusion_width` reaches the frame bulkhead
through `longeron_chamfer` into the floor in `nominal_flat_offset`, which sets the **corner
seating faces**. The sheet said nothing about them. It now dimensions the offset those faces
sit at from the longeron axis, with a note saying what it clears.

**The rule alternative 3 asked for, and it turns out to be one this document already had.**

> **A feature that is absent on some members of a family means the family is mis-partitioned,
> not that the dimension needs a table convention.** Section 5.1's membership test is that two
> variants share a drawing when they have the same *features*. A dimension that section 5.2's
> H5 would refuse on some members and not others is evidence the partition missed a split:
> put the governing condition in the topology signature and let the family divide. Each
> resulting sheet then carries the dimension unconditionally, and its view is right for every
> variant on it.

The alternative was a table convention — a dash, or a zero, in the cells where the feature is
missing — and that is the wrong answer for a reason worth stating: **the view is wrong too.**
A family sheet showing an outline that some of its variants do not have is not repaired by
annotating the table.

Measured, which is what settled it. The seating flat's span is `max(a, b) - b` of the two
branches of that floor, so it is **exactly zero when the panel branch wins**, and the face is
gone rather than narrow: the corner goes from 54 faces to 52 and the bulkhead from 187 to 179,
losing four flats of 3.15 mm² each. Three of the thirteen families held both kinds of part —
**24 of the panelled corner's 216, 8 of the panelled end bulkhead's 72, and 4 of the panelled
interconnect's 36**. Splitting them takes the drawing set from **13 family sheets to 16**, and
that is the price of the sheets being true.

**Two things the implementation had to get right, both of which failed first.**

*The condition is read from the part's own parameter mapping, not from the resolved object.*
Every kind's flat parameters carry `printer.extrusion_width`, including kinds whose geometry
never sees it — `boom_bulkhead_parameters` does not pass it and no boom module mentions
`longeron_chamfer`, so a boom bulkhead has no flat of this kind to have. Gating on the resolved
object split the boom bulkhead's four families into eight for a distinction its parts do not
have, and the set came out at 18 rather than 16.

*The dimension is the seat's offset, not the flat's span.* The span follows `U` and the panel
stock both, so it prints as a band of eight columns and the panelled end bulkhead's table came
to **158.6 mm** against a 108.5 mm band. The same face located from the longeron axis instead
of measured across it is `max(a, b)`, and where the bore branch wins — which is every member
of a family the flat exists on, by construction — that is a function of `U` alone. One column.
The table is **105.8 mm** and every one of the ten families with an annotation set fits.

The verification is the same shape as the rest of this section: the diagonal seating face sits
at that offset over root two from the longeron axis, measured on built solids at **1.8738 mm**
for 1U with 3/16 in panel where the bore branch wins and **2.0153 mm** for 0.5U with 1 mm panel
where the panel branch does.

**Alternative 1 remains the better question and is not foreclosed.** Asking what the geometry
consumes rather than what the mapping carries is the general form, `check_unread_rows.py`
(IP-FC-56) already measures it by perturbation, and the only thing missing is a decision on
whether a family's obligation is the union or the intersection over its members. Nothing in
this resolution depends on that. **Alternative 4 was rejected**: it closes the test by printing
a sentence about a cowl on the drawing of a part no cowl attaches to.

**A note on the register.** Joint 3's expression names only `corner_tolerance`, its clearance,
and not the terms that set the nominal offset — so nothing in section 3 demanded joint 3 be
stated on either part, and it was not. The bulkhead now states it because the part needs it
said, not because the test asked. Whether the register's expressions should name the nominal
as well as the adjustment is a question this resolution does not settle.

*Implementation: IP-FC-21. Reported by `tools/drawing_families.py`; the condition is
`freecad/sheet_annotations.corner_seat_span`, read from both sides; the reachability record is
`freecad/check_unread_rows.py` (IP-FC-56).*

### ~~OQ-DES-D7 — Some register rows give the whole size of a fit, others only the clearance gap, and one check reads them all the same way~~ — DECIDED 2026-08-30: write the whole size in every row, then make the expressions executable

**Resolution note.** Alternatives **1 and 5**, in that order, as recommended — 5 is not an
alternative to 1 but the thing 1 unlocks.

**What was decided.**

1. **Every row of the interface register states the whole size of its fit**, not just the
   clearance. Rows 2, 3 and 5 are rewritten; rows 1, 4, 6 and 7 already do it. `check_register`
   gains a refusal for any row whose expression names no parameter beyond its own clearance, so
   the column cannot drift back — the refusal is the part that matters, because rows 2, 3 and 5
   came to differ from the others by rows being added in a hurry, and nothing was watching.
2. **The expressions then become executable and are checked against the built parts.** A row is
   evaluated on a variant's parameters and compared with a measured feature, the way
   `check_drawing` already compares a dimension against the parameters that produced it. This
   needs a new per-row statement of *which measured feature* each expression is the size of,
   which the register does not have today.

**Why this and not the others.** The column is already the completeness test's input, so the
choice was between making it say what the test reads it to say and adding a second column that
has to be kept in step. One column that must be complete is easier to trust than two that must
agree. Accepting the column as it stood (alternative 4) looked free and was not: it would have
locked in two joints whose coverage is coincidental, and *"satisfied for the wrong reason"* is
the one defect a completeness test cannot report about itself. Measuring the parts instead
(alternative 3) answers a **different** question — which parameters reach a part — and does not
compete, because it cannot say which fit a parameter belongs to. It remains worth doing on its
own account.

**What this costs. The estimate made before deciding was too low, and the correction is
recorded here rather than quietly absorbed.** The estimate was *three names, all already on the
sheets, no drawing changes*. Built on 2026-08-30 under IP-FC-107, it is **five**:
`greeble_thickness` of the corner, and `unit_width`, `panel_thickness`, `panel_offset` and
`panel_overlap` of the bulkhead.

The estimate counted only row 5's *position*. This decision also has row 5 state its **extent**,
the exposed span, because that is the half of the joint `corner_radius` is actually owed for —
and the span brings `panel_offset` and `panel_overlap` with it. Three of the five were satisfied
by declaring what existing dimensions already consume; **two were not, and they are a genuine
gap**: no bulkhead sheet dimensions the panel's exposed span, so the completeness test now
reports it on four families. That is the test doing its job, and closing it is
[OQ-DES-D11](#open-questions). A second thing surfaced with it: `panel_offset` is demanded of
bulkheads that have **no panel**, because it is not zero on them and so escapes the
structural-zero rule — [OQ-DES-D12](#open-questions), decided 2026-09-06 in favour of dropping a row's parameters when its joint is absent.

**No drawn sheet changed**, which was the part of the estimate that held. Every family's quantity
column count, block count and row count is identical before and after, verified 2026-08-30.

Row 3's expression becomes the longest line in the register at 146 characters, and it is also the
row that gains no names — the length cost and the benefit land on different rows.

**One caveat carried forward.** Making section 2 complete does not make it a *derivation*.
[OQ-DES-D9](#open-questions) settled on 2026-08-28 that the register is an analysis of the
implementation, so filling in the missing expressions is finishing that analysis, not promoting
it to a specification. For rows 1 and 4 in particular, alternative 5's check compares two
readings of one geometry — both the expression and the sheet annotation were written by
measuring the same parts — so it confirms the drawing matches the part, not that the part is
what was intended. The derivation that would give the geometry something to be checked *against*
is IP-FC-87 and is separate work.

**What the figures established, and they stay.** Drawn 2026-08-30 by
[`tools/draw_register_rows.py`](../../src/Fuselage/tools/draw_register_rows.py), reproducing the
measured values: the greeble socket is
`longeron_radius + longeron_tolerance + greeble_thickness + greeble_tolerance` = **3.3000 mm** at
1U, four terms stacking outward, of which the register named one; and the bulkhead's outer face
sits at `unit_width/2 − panel_thickness − panel_tolerance` = **45.1375 mm**, which uses no
`corner_radius` at all, while the joint does consume `corner_radius` through the face's *extent*
— `unit_width − 2·(corner_radius + panel_offset) − 2·panel_overlap`, a built face of
392.8500 mm². That gap between what the register said and why the parameter was owed is the
clearest single argument for alternative 1: an expression the geometry evaluates cannot be right
by accident, and a sentence about it can.

![row 2, the greeble socket as four radial terms](img/register_rows/row2_greeble_socket.svg)

![row 5, the bulkhead outer face against the flat mold line](img/register_rows/row5_bulkhead_face.svg)

**Row 3 needs no figure.** It is `flat_offset`, drawn with both branches of its `max` in
[design_basis.md INT-3](design_basis.md#int-3--corner-seating-faces--bulkhead).

**No answer here could have broken a drawing**, which is why the change is safe to make.
Demonstrated 2026-08-28 by mutating the parsed register and diffing every family's drawn output:
emptying every row, and giving every row every parameter name, both left the drawn sheets
byte-identical and changed only the completeness report.

**What this decision did not settle**, and it is now [OQ-DES-D10](#open-questions): row 3 says it
is *carried by: corner*, and the seating faces are on both parts. The recommendation asked for it
to be settled at the same time; it is a question about which drawing owns a two-part joint, and
that is a separate decision rather than a consequence of this one.

*Implementation: `tools/drawing_families.read_register` and `check_register`, and section 2's
register table. Tracked as IP-FC-107 (alternative 1) and IP-FC-108 (alternative 5).*

### ~~OQ-DES-D8 — The register and the built corner disagree about the panel extension by one clearance~~ — DECIDED 2026-08-28: the register is corrected; the part is right

**Resolution note.** Determined by [OQ-DES-D9](#open-questions) rather than decided separately:
section 2 is an analysis of the implementation, so where it and a part disagree the part is
right and the register is corrected. Alternative 1.

Row 4's expression read `panel_overlap + panel_offset − panel_tolerance`. The built corner's end
face is at `panel_overlap + panel_offset` — measured **7.2625 against 7.1625** at 1U with 3/16 in
panel and **14.3500 against 14.2500** at 4U with 1/4 in, one `panel_tolerance` out on both. The
geometry is self-consistent: the slot mouth is at `panel_offset − panel_tolerance`, the slot
bottom at `panel_overlap + panel_offset`, and the slot is therefore
`panel_overlap + panel_tolerance` deep — the panel's entry plus its fit. The register's shorter
extension would have put the end face inside the slot bottom and opened the slot through the end
of the part.

**What this does not settle, and where it goes instead.** Whether that 0.1 mm *should* be there
is a question about intent, and correcting an analysis to match a part cannot answer it. It is
one of the relationships **IP-FC-87** has to derive: if the design says the corner ends at the
slot bottom, the geometry follows and the register was a transcription slip; if it says the
corner should stop a clearance short, the part is wrong and this closure will need reopening
against the derivation rather than against the part.

*Implementation: section 2's register table. No code depends on the difference — both forms name
the same parameters, which is why section 3's completeness test could never have caught it.*

### ~~OQ-DES-D9 — Is section 2 the interface design, or an analysis of the implementation?~~ — DECIDED 2026-08-28: it is analysis, and the derivation it is not is now tracked work

**Resolution note.** Section 2 **is** an analysis of the implementation as written, and section
1 now says so instead of claiming to be a reading of `design_constants.json`. Measured
2026-08-28: that file carries a governing expression for **three of the seven joints** — rows 6,
7 and 8 quote theirs verbatim — and prose for the other four, of which rows 2, 3 and 5
faithfully reproduce the prose while **rows 1 and 4 carry expressions that appear in no design
document at all**, having been written by reading the parts. Not one term of rows 1 to 5's
expressions appears in the corresponding `why`.

The consequences are taken rather than left implicit: the register's authority is the geometry,
so where the two disagree the part is right and the register is corrected — which determines
[OQ-DES-D8](#open-questions) — and completing rows 2, 3 and 5's expressions under
[OQ-DES-D7](#open-questions) is *finishing the analysis*, not promoting it to a specification — which is how that question was decided on 2026-08-30.

**What the project actually needs, and this is the substance of the decision rather than a
footnote to it.** A derivation of the fundamental design relationships, documented so that
**the implementation follows from it** — the OpenSCAD geometry as it stands, together with the
corrections the FreeCAD migration turned up. The test of that document is derivability: if a
relationship in it cannot produce the part, one of the two is wrong and the disagreement is
visible. That is a different and much stronger thing than either alternative this question
offered, both of which took the existing rows as the material to be relabelled. **Ratifying an
expression read off the geometry as design intent was the move to avoid**, and deriving the
relationship instead is what avoids it.

It is tracked as **IP-FC-87**, and until it exists no reading of section 2 establishes that a
part is built as intended — only that a drawing states what the part measures. This is the
prerequisite [OQ-ARCH-7](../architecture/freecad_migration.md#open-questions) named on
2026-08-07 and assigned to `doc/architecture/overview.md`, which section 1 met "by enumeration
rather than by waiting". The enumeration was the right thing to do at the time and it is not the
derivation.

**The loop this closes.** For rows 1 and 4 the chain was: the OpenSCAD geometry → section 2 (by
reading) → section 3's completeness test → the drawings, which are generated from
`freecad/sheet_annotations.py`, written by measuring the same geometry. Two readings of one
source, compared. That catches a transcription slip and cannot in principle catch the geometry
departing from intent — which is exactly why the test could not see OQ-DES-D8. Declaring what
section 2 is does not remove the loop; it stops the loop being read as evidence it never was.
**IP-FC-87 is what breaks it**, by giving the geometry something to be derived from.

*Implementation: IP-FC-87 for the derivation; section 1 carries the statement of what section 2
is.*

### ~~OQ-DES-D10 — The register's *Carried by* column also means two things, and one joint is where they come apart~~ — DECIDED 2026-09-09: alternative 2, split into two columns

**Resolution note.** **Alternative 2.** Section 2's register now carries *Clearance on* (which
part's geometry the gap is cut out of) and *Stated by* (every drawing section 3's completeness
test obliges to state the joint) as two columns instead of one. Row 3 is the only row known to
diverge: *Clearance on* stays `corner`, and *Stated by* becomes `corner, seated bulkhead`,
matching what the bulkhead's sheet has done since OQ-DES-D6 (`corner_seat_offset`) — the register
now says so rather than leaving the drawing ahead of the obligation. Every other row carries the
same value in both columns, since no other divergence is established; rows 7 and 8 were flagged
as candidates worth the same review and have not had it.

**`seated bulkhead`, not the bare `bulkhead` row 6 already uses.** Found 2026-09-09 while giving
the boom bulkhead its own annotation set (IP-FC-21): `CARRIED_BY['bulkhead']` names both the
frame and boom families, and `CARRIED_BY_FEATURE` gates by the carrier phrase, not by row. Naming
row 3's second carrier plain `bulkhead` would have let a boom bulkhead's sheet inherit row 3's
demand too — and a boom bulkhead has no corner-seating flat to have (`corner_seat_span` returns
`None` for it; the feature is `'absent'`, not merely small). Row 6's collet joint has nothing to
do with that feature and must stay ungated for both families, so the two can't share one phrase.
`seated bulkhead` is `CARRIED_BY['bulkhead', 'boom_bulkhead']` gated by
`CARRIED_BY_FEATURE['corner seating flat', (True,)]` — the same feature `topology_of()` already
computes for the corner's own partition, referred to rather than restated, which is the same
discipline OQ-DES-D12 applied one row over.

**The rationale.** The two facts are genuinely different — one is how the geometry is built (why
`corner_middle_shape` takes a `corner_tolerance` argument the bulkhead passes as zero), the other
is what the completeness test enforces — and both are used elsewhere in this document. Collapsing
them into one column is what produced the question; alternative 1 would have resolved it by
discarding the gap-attribution fact, which is load-bearing for a reader working from the geometry
rather than the drawings.

**Why not alternative 3** (split row 3 into two rows, one per part): it turns one fit into two
register entries and forces a decision about where the clearance value goes on a row that no
longer has a single part to carry it — worth revisiting if OQ-DES-D7's alternative 5 is ever
adopted, not before.

*Implementation: section 2's register table (done, above), and `CARRIED_BY`/`read_register` in
[`tools/drawing_families.py`](../../src/Fuselage/tools/drawing_families.py) — the register now
parses six columns and a *Stated by* cell may name more than one part.*

### ~~OQ-DES-D11 — No bulkhead drawing says how wide the panel's seating surface is~~ — DECIDED 2026-09-09: alternative 1, dimension the exposed width

**Resolution note.** **Alternative 1.** Each bulkhead sheet gains a dimension across the panel
seating face's actual exposed span — `unit_width − 2·(corner_radius + panel_offset) −
2·panel_overlap`, 65.475 mm at 1U with a 3/16 in panel — with a callout naming the four
parameters that set it. This closes the completeness gap on all four families that had it and
removes the "clean by accident" coverage: the width is now stated because it is the width, not
because an unrelated dimension's `max` happened to pick the panel branch.

**The rationale.** Alternative 3 (drop the width back out of row 5) would have made the report
green by deleting the obligation OQ-DES-D7 was just decided to add — rejected for the same reason
one row over. Alternative 2 (a table entry with no dimension line) would have weakened
OQ-DES-D2's pair rule — a dimension carrying the feature, a callout carrying the parameter — for
every joint, not just this one, to save one dimension line.

**Alternative 4 is the better long-run home and is deferred, not rejected.** The panel became a
part in its own right under OQ-DES-D4, and the width is arguably its dimension to carry rather
than the bulkhead's. But the panel has no drawing family in the partition today, so putting it
there is new IP-FC work rather than a documentation change — revisit once that exists.

**The placement question inside alternative 1** — this dimension spans the full width of the
part, so where it goes relative to the busiest region of the view is section 5.2's placement
rule to apply, not a further decision.

*Implementation: [`freecad/sheet_annotations.py`](../../src/Fuselage/freecad/sheet_annotations.py)'s
bulkhead quantities and dimensions (done, `panel_span`) — unblocks
[IP-FC-109](../implementation/freecad_migration.md).*

### ~~OQ-DES-D12 — A bulkhead with no panel is asked to explain the panel joint~~ — DECIDED 2026-09-06: a row applies to the families that have its joint

**Resolution note.** **Alternative 1**, let a register row be restricted by feature rather than
only by type — **described as alternative 3**, which is the same mechanism arriving as a
statement about the rule rather than about the register.

**The rationale.** The structural-zero filter was always a *proxy* for "the joint is not there",
and this is the case where the proxy fails: `panel_offset` keeps an ordinary non-zero value on a
bulkhead that has no panel, so the row is demanded and no correct drawing can supply it. The fix
is to say what was meant. Stated as alternative 3 the rule reads as one idea — **a row's
parameters drop when the row's joint is absent from the family** — instead of as a test on a
value that stands in for it.

**Doing it generally rather than for row 5 was part of the choice.** The family partition
already computes the predicate, so covering every row costs little more than covering one, and
[OQ-DES-D6](#open-questions)'s row 7 can move onto it too — replacing a list of type names with
the thing the list was standing in for.

**The constraint the decision carries, and it is the whole of what was left to decide.**
Alternative 1's own drawback was that the condition has to live somewhere a document and a tool
can both read, with the risk of **stating it twice and having the two disagree**. So it is
written **once**: the family partition owns the predicate and the register *refers* to it. A
register that carried its own copy of "has a panel seating face" would be a second statement of
the partition, and the one that moved would win silently — which is the failure this document
has now spent three questions on.

**Alternative 2 is explicitly rejected**, and for the reason the recommendation gave rather than
on cost: it would put a not-a-type into `CARRIED_BY_TYPES`, a structure whose name and contents
say *type*. That is exactly how the *Governing expression* column came to mean two things, which
[OQ-DES-D7](#open-questions) was spent correcting. Alternative 4, recording the gap and leaving
it, is rejected because a report with a permanent known-false entry trains its readers to skim
it.

**What this does not settle.** The `corner_tolerance` direction of the same proxy — a parameter
that is 0 on *every* part, so the filter drops it and H5 refuses to place it, leaving a
line-to-line fit undrawn and unmentioned — is a different failure of the same test and is
[IP-FC-112](../implementation/freecad_migration.md), not this. This question is about a row that
is demanded where its joint is absent; that one is about a fit that is real and invisible.

*Implementation: [IP-FC-110](../implementation/freecad_migration.md), now unblocked —
`tools/drawing_families.py`'s `CARRIED_BY_TYPES` and the structural-zero filter, and section 2's
register table.*

---

### ~~OQ-DES-D13 — Nine dimensions can be governed by either of two requirements, and the drawing says which for none of them~~ — DECIDED 2026-09-06: a `GOVERNED BY` column in the value table

**Resolution note.** **Alternative 1**, one extra column in the value table carrying the
requirement id that produced each variant's value, **with alternative 3's marker held as the
fallback** if a second column is ever needed.

**The rationale, and it is not a preference.** All nine dimensions with two governing
requirements split *inside* a family — on the corner sheet 240 variants take the longeron branch
and 24 the panel branch — so **the answer varies by row of the value table, exactly as the value
does**. An annotation that cannot vary per variant cannot state what DES-9 asks for, which rules
out every fixed-text candidate on the family sheet. The column also reuses table generation that
already runs per variant, and it survives the count growing from nine, which it will: 14
conditional branches are unexamined and the build layer is untouched.

**It fits, measured.** A column of requirement ids is **6.92 mm** against the **12.0 mm** of
table width the band layout has spare, leaving 5.1 mm. A column of branch *names* is 15.33 mm and
does not fit — and overrunning by 3.3 mm is not a small penalty but a cliff, dropping the drawn
view from 75.4 % to 45.3 % as the layout falls back to a column.

**The constraint this decision was recorded with has been measured away.** It said a single
column must serve the whole sheet, so its cells would have to name the *dimension* as well as
the requirement, and that the widened cell was the thing to measure before building. Both halves
were wrong, and the table's own factoring is why.

**The family table is factored by axis — one block per distinct axis set — and no block carries
more than one branching dimension.** Measured 2026-09-06: on the corner the three shown
branching dimensions sit in three *different* blocks (`greeble_thickness` in `('U',)`,
`panel_offset` in `('U', 'panel')`, `panel_overlap` in `('panel',)`), and the two bulkhead
sheets likewise. So the column is unambiguous where it sits and **needs no dimension label**;
the 6.92 mm figure stands as measured, and the 5.1 mm margin is not spent.

**Every branch also factors onto the same axes as the value it explains, or fewer** — checked
with `drawing_families.minimal_axes`, the same function that decides the table's shape — so each
`GOVERNED BY` column rides in the block its value is already in, and no new block, axis set or
row is needed anywhere.

**The count is also smaller than this question was decided against, and for a reason worth
keeping:** DES-9 is about the value *shown*, and only some of the nine branching dimensions are
printed on a sheet. Seven columns are needed in total — three on the corner, two on each
bulkhead sheet. The rest, `flat_offset` among them, are not dimensioned at all, which is
[OQ-DES-D14](#open-questions).

**Alternative 2 is rejected for the family sheet on measurement rather than taste.** A leader
note is fixed text, so on a sheet where 240 variants go one way and 24 the other it would have to
describe both cases and when each applies — a sentence, on the one document whose text-extent
argument assumes single letters, which is the unmeasured risk [OQ-DES-D2](#open-questions)
recorded when it chose that annotation. Alternative 4 (single-variant sheets only) is rejected
because it defers DES-9 behind [IP-FC-84](../implementation/freecad_migration.md) and leaves the
family sheet — the document a reviewer reads — silent about the thing DES-9 exists to surface.
Alternative 5 (a bigger frame) is rejected because it reopens [OQ-DES-D5](#open-questions) for
one requirement. Alternative 6 is rejected because DES-9 says *the drawing* states it, and the
honest form of that alternative is to amend DES-9 rather than to declare the register sufficient.

**What this rests on that was itself corrected.** The budget above is not the one this question
was framed against: the sheet was believed to have no spare table rows and to lose the view at an
eleventh, and it has **three spare rows** and loses nothing until the fourteenth
([IP-FC-128](../implementation/freecad_migration.md)). Depth is cheap because the table sits
beside a title block deeper than it is; **width** is where this sheet is tight.

*Implementation: [IP-FC-99](../implementation/freecad_migration.md) step three.*


### OQ-DES-D14 — DES-9's own evidence is a quantity no drawing shows

**Resolved 2026-09-06: alternative 1, as recommended.** DES-9 reaches *shown values* only,
so `flat_offset` is out of scope for the `GOVERNED BY` note: it is not a dimension any sheet
prints, and the corner sheet carries the eleven parameters that feed it, which is what
section 3's completeness test asks for and what an inspector measures.

`flat_offset` is therefore **deliberately unannotated**, and that is recorded here rather
than left to be rediscovered. The seven `GOVERNED BY` columns that do have shown values are
unblocked (IP-FC-99 step three): corner 3, bulkhead 2, boom_bulkhead 2.

**The doubt this leaves standing**, from the question as filed: the requirement then does not
cover the case it was drafted from, and 24 corner sheets stay silent about a real geometry
difference. The evidence that would reopen it is a reviewer being misled by one of those 24
sheets. That evidence has not been sought.

### OQ-DES-D15 — The value table does not fit the layout OQ-DES-D5 chose

**Resolved 2026-09-07: alternative 5, reduce the table lettering, decided by the user on
review.** The sheets are drawn on ANSI A, in OQ-DES-D5's band layout, and what gives is the
size of the text in the blocks beside the title block.

The decision was made in these terms: *"I told you I wanted the drawing itself taking up 75 %
of the area of the page"* and *"the table font size is much less important than being able to
tell what the hell the drawing is supposed to be showing"*. The stacked strip — the third
placement these sheets had been drawn in since the text metric was corrected — was giving the
view **52.4 %** of the frame, and the recommendation above (ANSI B) would have bought the
space by changing the paper. The user's reading is that the requirement is about the drawing
and the table is what should pay for it.

**What it costs, measured.** `drawing.sheet_blocks` searches
`drawing_standard.TABLE_TEXT_HEIGHTS_MM` from 2.5 mm downward for the largest lettering at
which the three blocks — the value table, the dimension key and the sheet-coverage statement —
pack into the 108.5 × 46.0 mm band beside the title block. Across the six drawable family
sheets it settles at **1.0 to 1.6 mm**, and every sheet's view region comes out at
**75.4 %** of the frame. 1.0 mm is well below ISO 3098's smallest defined height of 2.5 mm,
and that is the price the decision accepts.

The arithmetic behind those numbers: the frame is 44,834 mm², the title block takes 5,980 of
it, and the three blocks come to about 11,600 mm² at 2.5 mm lettering. For the view to have
75 % the blocks must fit 5,229 mm², which is 45 % of the area and so 67 % of the linear size —
about 1.7 mm — and packing waste takes it to between 1.0 and 1.6 depending on the family.

**Two things this also settled.**

*The view region is not the drawing.* A region can be 75 % of the frame with a postage stamp
in the middle of it, which is what a scale search that shrinks the part until its own
annotations fit produces. `drawing.SCALE_FLOOR_FRACTION` now stops the search a quarter below
the largest scale the *geometry* fits its region at, and a view that cannot carry its
annotations within that is split rather than shrunk — which is what a detail view is for.

*Two views fit after all.* Before the lettering search the view region was 239.5 × 98.1 mm and
a bulkhead's plan and corner detail fitted neither as columns (the detail gets 119.3 mm and
its five leader notes need more at **any** scale, since note text does not shrink with the
part) nor as rows (57.7 mm of height, same result). At 239.5 × 141.2 both place, and every
bulkhead family sheet now carries a plan and a `DETAIL A`.

### ~~OQ-DES-D16 — A leader can cross a witness line, and nothing checks for it~~ — DECIDED 2026-09-07: alternative 4, a one-bend router

**Chosen: alternative 4**, over alternative 3's recommendation. `dimension_placement._route_leaders`
runs once every dimension on a view has been placed (so every witness line exists), finds the
first dimension line or witness a note's straight leader crosses, and tries bending the leader
through one elbow past whichever end of that obstacle is nearer — `_elbow_candidates` gives the
two candidate points, `_leader_clear` re-verifies the bent leader crosses nothing else and stays
in frame before it is accepted. `PlacedNote.leader` is now two points or three; `drawing.bind_notes`
already drew `DrawLeaderLine.WayPoints` as a list, so the third point cost nothing there.

**Measured working**: on the panelled bulkhead's `DETAIL A`, the `bore` note's leader — which
used to run straight from (58.7, 62.8) to (94.6, 16.0), crossing `G`'s witness at (60.0, 61.1)
— now bends through (60.0, 58.2) and clears it.

**Kept deliberately narrow.** The hard constraint stayed dimension-line-only, exactly as before
this alternative existed — it was **not** widened to witness lines, because a leader that
crosses more than one obstacle is not always reachable by the single bend this router tries
(it stops at the first obstacle found and does not search a second elbow around a second one).
Tried widening it anyway and rebuilt the set: `corner-corner-1b4844` — a sheet that had built
clean on every run before this alternative existed — refused, because the `bore` note's leader
there crosses an extension line the router's one bend cannot also clear. The gate was reverted
to dimension-line-only so routing improves every leader it can reach without making a leader it
cannot reach a new way to fail a sheet that never needed reaching for. A leader that still
crosses a witness line after this is exactly as visible, or invisible, as it was before
OQ-DES-D16 was filed — the router is strictly additive, not a new constraint.

### ~~OQ-DES-D17 — A dimension can inherit an unrelated note's whole band~~ — DECIDED 2026-09-07: alternative 3, tried and measured not to reach the case it was filed on

**Chosen: alternative 3.** `_attempt` now builds both of section 5.3 item 5's balancings for
an axis group of two or more — the ranked assignment and its mirror — scores each by
`_witness_length` (total length of every witness line the group draws), and keeps the shorter
one, but only if `_group_fits` says the swap does not push anything outside the frame the
unswapped arrangement was inside. Implemented, and safe: the full six-sheet set still builds
and `check_placement_determinism.py` still reports one digest across four hash seeds.

**Measured not to fix the case that motivated the question.** On `corner-corner-7faa02`, `F`
(`panel_pocket`) and `A` (`corner_radius`) are the vertical-axis group. The default assignment
— `F` left, `A` right — draws 262.97 mm of total witness for the pair; the swap — `F` right,
`A` left — draws 332.97 mm, so the code correctly keeps the default and `F`'s witness stays
87.65 mm long. The reason is not the note band this question was filed against: `F`'s own
feature sits at `x = -17.5`, close to the geometry's left edge, so moving `F` to the
note-free right side trades a short walk past a wide note band for a long walk **across the
entire part** to a dimension line on the far side — 78 mm versus the 70.99 mm it already
costs on the left. The metric alternative 3 scores (total group witness length) is answering
correctly; the swap this specific case wants is not the cheaper one by that metric, because
`F`'s side was never determined by the note band alone.

**What this leaves standing.** The 87.65 mm witness measured when this question was filed is
unchanged by this decision. Alternative 3 is not wasted — it will take the shorter side
whenever a swap's savings are not outweighed by moving the dimension's own feature further
from its line, which did not happen to be true here — but a case like `F`'s, where the
feature itself sits nearer the crowded side, needs one of alternatives 2, 4 or 5 from the
original list, or a different question, to actually shorten. Left as a finding rather than a
new question because no further decision has been asked for.

## See also

- [freecad_migration.md](../architecture/freecad_migration.md) — OQ-ARCH-7, the decision this
  implements; UC-7, the use case it serves
- [system_requirements.md](system_requirements.md) — the requirement set: section 2's ten
  joints as INT-1 … INT-10, section 5's hard constraints as DRW-1 … DRW-5, and the verification
  status of each; OQ-DES-SR2, which asks what verifies DRW-7
- [design_basis.md](design_basis.md) — what the interfaces are *meant* to be, which this section
  analyzes rather than specifies; OQ-DES-D9's answer
- [corner.md](corner.md) — the cross-section, the panel offset derivation, OQ-DES-C5
- [bulkhead.md](bulkhead.md) — derived dimensions, bolts and anchors
- [cowl.md](cowl.md) — OQ-DES-CW9 through CW11, joints 7 and 8
- [freecad_migration.md](../implementation/freecad_migration.md) — IP-FC-21 (the family
  drawing), IP-FC-22 (assembly drawings)
