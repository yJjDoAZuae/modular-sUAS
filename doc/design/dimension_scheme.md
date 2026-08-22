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
`design_constants.json`'s `tolerances` group exists because two parts meet somewhere, and its
`why` names the joint and gives the expression. There are seven, and there are seven joints.

The register below is therefore not a new list to be maintained beside the code — it is a
reading of a file the sweep already validates on every run.

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

| # | Joint | Governing expression | Clearance | Carried by |
| --- | --- | --- | --- | --- |
| 1 | longeron tube → corner bore | bore radius = `longeron_radius + longeron_tolerance`; lead-in chamfer = `w` | `longeron_tolerance` 0.05 | corner |
| 2 | bulkhead greeble post → corner socket | socket opened out by the clearance; **post stays nominal** | `greeble_tolerance` 0.05 | corner |
| 3 | corner seating faces → bulkhead | `flat_x += corner_tolerance`, `flat_offset += corner_tolerance·√2` | `corner_tolerance` 0.0 | corner |
| 4 | panel → corner | slot `2·panel_thickness + 2·panel_tolerance` deep, outer face at `corner_radius − panel_thickness − panel_tolerance`; extension `panel_overlap + panel_offset − panel_tolerance` | `panel_tolerance` 0.1 | corner |
| 5 | panel → bulkhead flange | standoff so the panel's outer surface lands on the mold line at `corner_radius` | `panel_tolerance` 0.1 | bulkhead |
| 6 | boom tube → boom bulkhead collet | `collet_radius = boom_diameter/2 + boom_collet_thickness + boom_tolerance` | `boom_tolerance` 0.2 | bulkhead |
| 7 | cowl → cowling bulkhead flange | flange outer radius = `corner_radius − n_p·w − cowl_flange_tolerance`; flange height `2·U` | `cowl_flange_tolerance` 0.2 | bulkhead |
| 8 | nose closure → cowl shell | base offset = `n_p·w + nose_flange_tolerance` | `nose_flange_tolerance` −0.1 | nose closure |
| 9 | nose plate → nose closure | pocket radius = `plate_diam/2 + plate_tol`, relieved at `overhang_angle_from_bed` | `plate.tolerance` 0.1 | nose closure |
| 10 | bolt or insert → bulkhead | `bolt_offset = 8·U` on the diagonal; `bolt_radius` = `diameter/2`, or the insert bore from [`threaded_insert_dimensions.csv`](../../src/Fuselage/tools/threaded_insert_dimensions.csv) | — | bulkhead |

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

**Three known gaps in the test, stated rather than left to be discovered.**

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
   generated today will dimension a zero-clearance fit that may be a bonded joint.**

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
A landscape template — and at the drawing standard's 7.0 mm row pitch that is 19 rows. The
"about 25" was a guess at a sheet nobody had opened.

**Every family fits, and five of them fit exactly.** What closes the gap is that tables sharing
a leading axis are **one block**, not several: a `U` table and a `U` × panel matrix put the same
eight values of `U` down the left, so printed separately that column is printed twice. Merged,
the single-axis fields are ordinary columns and each coupled field is a band of columns inside
the same table. The panelled corner then costs a 10-row `U` block and a 9-row panel block — 19
of 19, with **nothing spare**. That is a fit in the arithmetic and not on paper: one more
dimension, one more panel stock, or a title row above the table puts it onto a second sheet.

### 5.2 Hard constraints — violation fails the build

Every one of these is checkable on the produced drawing. None is a preference.

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

None open.

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
the thirteen family sheets measure 19 of 19 available rows with nothing spare (§5.1a). The
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

---

## See also

- [freecad_migration.md](../architecture/freecad_migration.md) — OQ-ARCH-7, the decision this
  implements; UC-7, the use case it serves
- [corner.md](corner.md) — the cross-section, the panel offset derivation, OQ-DES-C5
- [bulkhead.md](bulkhead.md) — derived dimensions, bolts and anchors
- [cowl.md](cowl.md) — OQ-DES-CW9 through CW11, joints 7 and 8
- [freecad_migration.md](../implementation/freecad_migration.md) — IP-FC-21 (the family
  drawing), IP-FC-22 (assembly drawings)
