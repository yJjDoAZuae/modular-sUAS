# Corner — Design

**Status:** Reconstructed from the implementation, 2026-08-06. This is the first design
authority the corner has had; it was written by reading
[`fuselage_corner_geometry.scad`](../../src/Fuselage/scad/fuselage_corner_geometry.scad)
and the derivations in
[`fuselage_variants.py`](../../src/Fuselage/tools/fuselage_variants.py), not from an
existing specification.

**How to read it.** Statements about *what the geometry does* are read directly off the
code and are reliable. Statements about *why* are marked as inference where they are
inference — the original intent was not recorded anywhere, and a plausible reconstruction
is not the same as the real reason. Where the intent genuinely could not be recovered,
there is an open question rather than a guess. Anything here that contradicts the code is
a bug in this document; the code is what builds parts.

---

## What the corner is

The corner is the longitudinal structural member at each of the four corners of a
fuselage unit. Four of them, plus a bulkhead at each end, make one bay. Each corner does
three jobs at once:

1. **Carries the longeron, and carries load in its own right.** A tube passes through the
   bore that runs the full length of the part. The longeron takes the pure axial tension
   and compression; the corner takes hoop and torsional load. See
   [§Load path](#load-path) — the division is not "tube carries, corner locates", which is
   the easy oversimplification.

   Note also that the corner *locates* the tube rather than *retaining* it: the longeron is
   snapped in and held by the bulkhead's greeble, a C with a mouth narrower than the tube.
   See [bulkhead.md](bulkhead.md#the-longeron-snaps-into-the-greeble).
2. **Registers onto the bulkheads.** Each end is bored to receive the bulkhead's
   *greeble* — the annular post that stands out of the bulkhead face — and carries an
   internal groove that the greeble's snap rib engages. The greeble is the bulkhead's
   feature; the corner is the socket half. This is the only thing that sets the corner's
   axial position.
3. **Retains the panels.** A slot along the outer face captures the edge of a skin panel;
   the corner is what holds the panel down at its corner.

It prints as a single piece, and its cross-section is constant over most of its length.

## Parametric basis

The corner inherits the MAUS unit standard. `U` is the scale multiplier and `FX` the
length multiplier; both come from the variation tables, not from this geometry.

| Quantity | Value | Where set |
| --- | --- | --- |
| `unit_width` | `100·U` mm | `standard_values()` × `U` |
| `corner_radius` | `10·U` mm | `standard_values()` × `U` |
| `longeron_radius` | `2·U` mm | `standard_values()` × `U` |
| `unit_length` | `100·U·FX` mm | `standard_values()` × `U` × `FX` |
| `longeron_tolerance` | 0.05 mm | `LONGERON_TOLERANCE_MM`, **not** scaled |

The last row is the pattern to notice: **fit clearances do not scale with `U`.** A 0.05 mm
sliding fit is a property of the printer and the tube, not of the airframe, and
multiplying it by four for a 4U aircraft would make the joint loose. The same holds for
`panel_tolerance` (0.1 mm) and the greeble tolerance.

Dimensions in this file are millimetres and degrees. That is the OpenSCAD path, which is
exempt from the project's SI standard — see
[general.md](../guidelines/general.md#units--si-is-the-project-standard).

## Longitudinal structure

`fuselage_corner()` builds one half and mirrors it about the midpoint, so the part is
symmetric end to end and either end mates with either bulkhead. Each half is three
sections stacked in `z`:

```
 z = unit_length
      ┌──────────────┐   mirrored copy of everything below
 …    │              │
      ├──────────────┤   unit_length/2
      │ corner_middle│   constant cross-section, the long run
 2·bt ├──────────────┤
      │corner_transi.│   greeble bore closes down to the bare longeron bore
 1·bt ├──────────────┤
      │  corner_end  │   the greeble socket: bore, snap groove, lead-in
 z = 0└──────────────┘
```

`bt` is `bulkhead_thickness`, which is a *bulkhead* parameter the corner must be told
about. That coupling is real and unavoidable: the greeble is a mating feature, so its
axial extent is set by the part it mates with, not by the corner. It is also the single
largest source of surprise when reading this module — every `z` dimension in
`corner_end()` and `corner_transition()` is a fraction of a dimension that belongs to
another part.

- **`corner_end`** (0 → `bt`) is one bulkhead thickness tall, because the bulkhead's
  greeble reaches through the bulkhead's full thickness when assembled.
- **`corner_transition`** (`bt` → `2·bt`) closes the greeble bore back down to the plain
  longeron bore, as a cone. *Inference:* a step here would be a stress riser and, printed
  in this orientation, an unsupported overhang; a cone is printable and spreads the
  section change.
- **`corner_middle`** (`2·bt` → `unit_length/2`) is the constant-section run, a straight
  extrusion of `corner_middle_shape()`.

## The greeble joint

**The greeble is the bulkhead's feature, not the corner's.** It is the positive annular
post standing out of the bulkhead face, with a snap rib around it. The corner's end is
the socket: a bore that receives the post, with an internal groove that the rib engages.

The direction is easy to get backwards from the code, because both halves are described
by the same three functions and those functions live in
`fuselage_corner_geometry.scad`. The reason they produce a post on one part and a bore on
the other is that `bulkhead_section()` subtracts `corner_end()` — the corner's whole end
section — from the bulkhead. Bulkhead material survives exactly where the corner has
none, so the corner's bore becomes the bulkhead's post and the corner's groove becomes
the bulkhead's rib. One description, two mating halves, and no possibility of them
disagreeing.

The radii therefore describe *the joint*, not either part:

```
greeble_radius     = longeron_radius + longeron_tolerance
                     + greeble_thickness + greeble_tolerance
greeble_nub_radius = greeble_radius + greeble_nub_thickness
greeble_nub_height = bulkhead_thickness / 3
```

Read outward from the tube: the longeron bore, its running clearance, the greeble wall,
and the fit clearance. `greeble_nub_radius` is one wall thickness further out — the rib
on the bulkhead's post, the groove in the corner's bore. It occupies the middle third of
the bulkhead's thickness, leaving a third of lead-in on each side for the joint to ride
over as it engages.

### Where the clearance lives

**All of the fit clearance is on the corner's bore. The bulkhead's greeble is at nominal
size.**

```python
GREEBLE_TOLERANCE_BULKHEAD_MM = 0.0
GREEBLE_TOLERANCE_CORNER_MM   = 0.05
```

The tolerance enters through `greeble_radius_of()`, so a non-zero value opens the radius
out. On a corner part that enlarges the bore; on a bulkhead part it would fatten the
post. Setting the corner's to 0.05 and the bulkhead's to zero puts the whole clearance in
the socket.

The bulkhead does not take a greeble tolerance at all: `bulkhead_section()` passes a
literal zero to `corner_end()`, because a nominal post is an invariant of the joint
rather than something to tune. It used to accept a parameter and discard it, which is
[OQ-DES-B6](bulkhead.md#open-questions).

This is a real design decision, not an accident: a snap fit tuned from both sides carries
the clearance twice and ends up twice as loose as either number suggests. Tuning from one
side means one number to change when the fit is wrong.

### The thickness formula

```python
greeble_thickness     = max(2·√U·extrusion_width, 2·extrusion_width)
greeble_nub_thickness = greeble_nub_thickness_of(greeble_thickness)
```

Two things are worth stating explicitly, because both look like mistakes and neither is:

- **`√U`, not `U`.** The greeble wall is a printed feature whose job is to survive a snap
  fit, so it is sized in extrusions rather than as a fraction of the airframe. A linear
  scaling would make the 4U wall twice as thick as it needs to be and the 0.5U wall too
  thin to print. The square root was established as authoritative from `tmp.py`
  (2025-08-20) — see IP-GEO-3 in the refactor plan, which resolved a disagreement between
  this formula and a commented-out copy in the SCAD.
- **The `max()` floor.** Below `U = 1` the formula would fall under two extrusion widths.
  Two is the floor because a one-extrusion wall has no interior and delaminates.

*Inference, not recorded intent:* the fact that `thickness` and `nub_thickness` share a
formula suggests they were meant to be one parameter. They are separate today and nothing
enforces their equality.

## Cross-section

`corner_middle_shape()` draws one octant in 2D; the caller mirrors it about the diagonal
with `mirror_xy()` and extrudes. Built as a difference:

**Added** — a circle of `corner_radius`, plus a rectangular extension reaching out by
`panel_overlap + panel_offset - panel_tolerance` to give the panel something to sit
against.

**Removed** —

- the longeron bore, `longeron_radius + longeron_tolerance`;
- the panel slot, `2·panel_thickness + 2·panel_tolerance` deep, positioned so its outer
  face lands at `corner_radius - panel_thickness - panel_tolerance`;
- a half-plane mask that trims the drawing to its octant;
- the diagonal mirror-line mask;
- a chamfer along the longeron opening.

The one line that carries real design content:

```scad
flat_offset = -max(longeron_radius + longeron_tolerance + longeron_chamfer,
                   (panel_overlap + panel_offset) - (corner_radius - panel_thickness - panel_tolerance));
```

This is a two-sided constraint written as a `max()`. The flat face where the corner meets
the bulkhead must clear the longeron bore *and* its chamfer, and it must also sit outside
wherever the panel interface has been pushed to. Whichever constraint binds, wins.
`longeron_chamfer` is `extrusion_width` — one extrusion — which is *inferred* to be the
smallest chamfer worth printing rather than a structural requirement.

## Panel offset

`panel_offset` is not free. `derived_parameters()` computes it, and the calculation is the
densest piece of design reasoning in the Python:

1. Establish `panel_clearance_radius` — how far out the panel's inside corner must stay to
   avoid the greeble perimeter: the longeron, its clearance, both greeble walls, and two
   extrusions of margin.
2. Find `panel_corner_y`, the lower edge of the panel.
3. If the clearance circle reaches past that edge, offset by the Pythagorean difference so
   the panel corner sits *on* the clearance circle rather than inside it.
4. Take the larger of that and a second bound that keeps the offset plus overlap clear of
   the greeble nub bevel, with `greeble_clearance_width = 1·U` of extra room so the corner
   can snap in from the back side.
5. Clamp to `√2 · corner_radius`, then round **up** to the next 0.25 mm.

Step 5's rounding direction matters: rounding down would eat the clearance the previous
four steps just established. Rounding up costs a quarter millimetre of panel width and
guarantees the constraint holds.

## Validity

`corner_validity_check()` rejects a combination when:

```
panel_thickness > corner_radius - (longeron_radius + longeron_tolerance
                                   + greeble_thickness + greeble_nub_thickness)
```

which is the statement that the panel slot cannot eat into the greeble stack — and, unless
the panel is absent entirely (`panel_thickness == 0`, a valid case meaning "no skin"),

```
panel_thickness ≥ 1·U
```

*Inference:* the lower bound reads as a structural minimum rather than a geometric one.
Nothing in the geometry fails at a thinner panel; it would simply be a panel too flimsy to
be worth the corner that holds it.

## Load path

**Recorded 2026-08-07.** The corner is not a passive fitting. Three load types reach it,
and they reach it in different directions relative to the printed layers — which is why
this section has to be read together with the next one.

| Load | Carried by | Direction relative to the corner's layers |
| --- | --- | --- |
| Axial tension and compression (body `x`) | **The longeron** | — |
| **Hoop**, around the longeron between the panels | **The corner** | **In-plane** — the strong direction |
| **Torsion**, fuselage twist | **The corner** | **Diagonally across the layer lines** |

**Hoop load is the corner's main structural job.** The panels pull on it from two
directions, and the corner reacts that circumferentially around the longeron bore — the
material between the bore and the panel slots is what closes that path. This is also the
load the `flat_offset` constraint and the `panel_clearance_radius` derivation exist to
protect: they keep the panel slot from eating into the material that carries hoop stress.

**Axial load goes to the longeron.** The tube takes pure `x` tension and compression at the
corner; the corner does not, and is not sized for it.

**Torsion is the awkward one.** Fuselage twist arrives at the corner as a diagonal load
across the layer lines — see the next section for why that direction is the one to watch.

### Why the split matters for analysis

An orthotropic model (UC-8 tier 3) that treats the corner as a general structural member
will mis-rank its margins in both directions: it will over-report axial capability the
corner is not asked for, and under-weight the hoop path that it is. The three rows above
are the correct load cases to check.

**The modeled frame is the print frame** — the STLs the sweep writes are already oriented
for the bed. System-wide, model `+z` is the build direction and corresponds to the
**aircraft body `x` axis**. The corner is **symmetric in `z`, so the sign does not matter**;
either end may go down.

So the corner **prints standing on end**, and the reading the geometry suggested is the
right one: the longeron bore is vertical — no bridging, no support, a round hole — and
`longeron_chamfer = extrusion_width` at the bore mouth is a lead-in for that vertical hole.

**The structural consequence, read against the load path.** Layers stack **along the
corner's length**, so every layer interface is a plane normal to the axis between
bulkheads, and the cross-section *is* the layer plane. Taking the three loads of
[§Load path](#load-path) in turn:

- **Axial** — the weak direction, and the corner is not asked to carry it. The longeron
  does. This is the one that looks alarming in an orthotropic model and is not.
- **Hoop** — carried **in-plane**, along the beads, in the strongest direction the process
  offers. The orientation is well chosen for the corner's main job: the load that matters
  most is the one the layers are best able to take.
- **Torsion** — **diagonally across the layer lines.** This is the direction to watch. A
  diagonal path puts shear across layer interfaces, which is where FDM is weakest and where
  a uniform-material analysis will be most optimistic.

So the print orientation is not a compromise forced by geometry — it is well matched to two
of the three load cases and exposed on the third. **Torsion is the load case that most
needs an orthotropic model rather than an isotropic one**, and it is the case a
uniform-material FEM will silently pass.

At `U·FX = 1` the part is 100 mm tall on a cross-section of roughly `2 × corner_radius`; at
`U = 4` it is 400 mm tall. Whether the largest sizes are printed whole or split is not
recorded — [OQ-DES-C4](#open-questions).

## Open questions

| ID | Status | Question |
| --- | --- | --- |
| C1 | ~~resolved~~ 2026-08-06 | Are `greeble_thickness` and `greeble_nub_thickness` meant to be independent? |
| C2 | ~~resolved~~ 2026-08-06 | What is the greeble actually toleranced for? |
| C3 | ~~resolved~~ 2026-08-06 | Is the corner's dependence on `bulkhead_thickness` the right interface? |
| C4 | ~~answered~~ 2026-08-07 | Are the largest corners printed whole, or split? Whole — splitting is unexplored |
| C5 | ~~resolved~~ 2026-08-14 | The corner/bulkhead interface carries no tolerance of its own. What should it be? |

C1 became one parameter plus a formula (IP-GEO-22); C2 was closed by test prints at both ends
of the range, U=0.5 and U=4; C3 was closed by the observation that the corner and its bulkhead
are not independent designs at all. C4 is *answered* rather than resolved — the answer is "not
currently possible", which names a future exploration rather than closing the subject.

**~~OQ-DES-C4 — whole or split at the large sizes?~~ — ANSWERED 2026-08-07: whole, for now.**
There is **no current method for printing large corners or bulkheads in pieces.** Splitting
is a future exploration rather than an existing capability, and the two parts differ sharply
in difficulty:

- **A split corner would be relatively easy**, because *the corner does not carry
  significant longitudinal loads.* A splice would not have to transmit much across the
  joint. Untried, but not structurally fraught.
- **A split bulkhead would likely require structural changes**, not merely a cut plane.

The first is worth recording beyond its own sake, because it independently confirms the load
path this document infers elsewhere. §Print orientation notes that layers stack along the
corner's length, leaving the part weakest along the axis the fuselage loads it — and what
makes that acceptable is that **the longeron carries the longitudinal load, not the
corner.** That same fact is what would make a splice tractable. Two different questions,
one underlying answer, arrived at independently.

Practical position: `unit_length = 100·U·FX` is the printed height — 100 mm at U·FX = 1,
**400 mm at U = 4**, more with `FX > 1` — so the large sizes need a printer whose Z envelope
accommodates them. If splitting is explored, the splice is new geometry, it belongs in this
document, and it interacts with the greeble at both ends.

Resolved entries keep their full text below, in numerical position, with the reasoning
that produced the answer.

**~~OQ-DES-C1 — Are `greeble_thickness` and `greeble_nub_thickness` intended to be
independent?~~ — RESOLVED 2026-08-06: no.** They are now **one parameter plus a formula
relating them** — `greeble_nub_thickness_of()` in `fuselage_variants.py`, identity today.
Written as a formula rather than collapsed into a single value on purpose: scale problems
may yet need the nub thicker or thinner than the seat wall, and when that happens the fix
should be a formula update in one place, not the reintroduction of a second independent
parameter that can drift.

**Python owns the formula.** Both languages need the value — SCAD to build the geometry,
Python for the panel-clearance checks — so the question was which side is authoritative.
Python, because the geometry modules take both values and derive neither, so the
relationship is stated exactly once, on the side that survives the FreeCAD port. The SCAD
signatures keep both arguments; the GUI drivers now read
`greeble_nub_thickness = greeble_thickness`, which is the only place a human can still
set them apart.

Implemented as IP-GEO-22. Proven geometry-neutral: all 576 parts generate byte-identical
`.scad`.

The original wording follows.

---

**OQ-DES-C1 — Are `greeble_thickness` and `greeble_nub_thickness` intended to be
independent?** They are computed by identical formulas from identical inputs and have
never differed in any swept variant. If they are meant to be one number, the pair is a
latent inconsistency: changing one and not the other produces a nub that does not match
its seat, and nothing would report it. If they are meant to be independent, no variation
table exercises that freedom. Deciding this is cheap now and expensive after the FreeCAD
port has copied the pair forward.

**~~OQ-DES-C2 — What is the greeble actually toleranced for?~~ — RESOLVED 2026-08-06.**
`GREEBLE_TOLERANCE_CORNER_MM = 0.05` is a single unscaled number applied at every `U`
from 0.5 to 4, while the engagement it governs — the bulkhead's rib in the corner's
groove — scales with wall thickness (`√U`) and diameter (`U`). The worry was that a
clearance right at one size could not be right across an 8× span.

**It is.** Both ends have been printed and assembled: U=4 with 16 mm longerons
([OQ-DES-B4](bulkhead.md#open-questions)) and U=0.5
([OQ-DES-B7](bulkhead.md#open-questions)), tolerances working in each case.

So a fixed 0.05 mm is the right *kind* of number here, and the instinct behind this
question — that a clearance ought to scale with the part — was wrong. It should not.
A snap fit is governed by what the printer can hold and what the material will flex,
neither of which cares how large the airframe is. That is the same reasoning that keeps
`longeron_tolerance` and `panel_tolerance` unscaled, and this is the first confirmation
of it in hardware rather than in argument.

**~~OQ-DES-C3 — Is the corner's dependence on `bulkhead_thickness` the right
interface?~~ — RESOLVED 2026-08-06.** Yes, and the question was posed from a wrong
premise. **The corner and the bulkhead it attaches to are not independent designs.**
They are two halves of one joint, so a shared dimension is not a leak across an
interface — there is no interface there to leak across. The three `z` dimensions in
`corner_end()` and `corner_transition()` are not the corner borrowing a number from
elsewhere; they are the joint's own geometry, seen from the corner's side.

**But the coupling is in the cross-section, not the length.** This is the part that
makes the parameter set the shape it is:

> **Different bay lengths share the same bulkhead design. That is why `FX` is a separate
> parameter and the bulkhead does not reference it.**

`FX` scales `unit_length`, `unit_length` reaches the corner, and the corner alone gets
longer. Everything the joint is made of — `corner_radius`, `longeron_radius`,
`bulkhead_thickness`, the greeble stack — is independent of it. So the right unit of
design is *not* the bay: it is the **cross-section plus the joint**, and bay length is a
free variable layered on top.

The sweep already reflects this and is worth reading as evidence. `FX` lives only in
`corner_size_variants.csv`; the bulkhead axes carry no `FX` column at all, so bulkheads
are generated once per (panel, type, size) and reused across every bay length, while
corners get an `FX` axis and carry it in their filenames.

**One thing did not reflect it.** `unit_length` was threaded through
`bulkhead_section_full` → `_octant` → `_section` and used by none of them — the same
defect as OQ-DES-B6, but worse in kind: a dead `greeble_tolerance` merely did nothing,
whereas a dead `unit_length` asserted a dependency on bay length that is precisely what
the design is built to avoid. Both bulkhead drivers computed it too, and
`fuselage_cowling_bulkhead.scad` did so with `FX = 0.5` against `fuselage_bulkhead.scad`'s
`FX = 1` — producing identically shaped bulkheads, which is as clean a demonstration as
the repository contains. Removed in IP-GEO-23.

**For the FreeCAD port** the consequence is that the corner and bulkhead should share
their *cross-section and joint* parameters by construction — modeling them as separate
parts that happen to agree would need a constraint to hold them together, and constraints
can be violated — while bay length stays a parameter of the corner only.

The original wording of this question follows.

---

**OQ-DES-C3 — Is the corner's dependence on `bulkhead_thickness` the right interface?**
Three of the corner's `z` dimensions derive from a parameter that belongs to the bulkhead.
It is correct — they mate — but it means the corner cannot be reasoned about alone, and
the FreeCAD port will have to decide whether the joint is a first-class object with its
own parameters or stays as two parts that each know a dimension of the other.

### ~~OQ-DES-C5 — The corner/bulkhead interface carries no tolerance of its own~~ — RESOLVED 2026-08-14

The corner seats against the bulkhead on two surfaces: the **diagonal face**, the plane
`x + y = flat_offset` in the corner-local frame, and the **flat face** at
`flat_x = -(panel_overlap + panel_offset)`. Neither carries any clearance. The bulkhead forms
its side of the joint by cutting itself with the *same polygon* the corner uses for its own
bulkhead boundary — the vertices `(flat_x, corner_radius)`, `(flat_x, flat_y)`,
`(flat_offset, 0)` and their mirror — so the two surfaces are coincident by construction and
no parameter exists that could separate them.

Measured on the built solids to confirm it is not an artifact of reading the code: sectioning
the corner's **end** at mid-bulkhead height and the bulkhead at the same height, in the same
frame, and stepping across each interface:

| Interface | Void between the parts |
| --- | --- |
| greeble, corner's socket against the bulkhead's post | 0.0500 mm |
| diagonal face, sampled at ¼, ½ and ¾ along | 0.0000 mm |
| flat face at `flat_x` | 0.0000 mm |

So the joint has exactly one clearance, `greeble_tolerance` = 0.05 mm, and it is carried
entirely on the corner's bore — which is correct and deliberate (see
[bulkhead.md](bulkhead.md), the greeble post is nominal by construction so the joint carries
the clearance once). Every other mating surface is nominal contact.

**The flat face used to have a step in it, and the step was `panel_tolerance`.** Tracing the
corner's outboard face against height on the built solid, it sat at `flat_x` over almost its
whole height — but in a thin band below the flange face the circle of `corner_radius` has
curved inside, the **rectangular extension** became the outermost feature, and because that
extension was dimensioned `panel_overlap + panel_offset - panel_tolerance` it stopped one
`panel_tolerance` short of `flat_x`. The bulkhead filled the notch and stood over the corner.

That was `panel_tolerance` leaking into a mating face it was never meant to define —
**confirmed 2026-08-14 that it was not intended as the corner/bulkhead clearance.** It was the
extension's own dimension, and the extension exists to give the panel something to sit against,
not to position the joint. **Fixed 2026-08-14 under [OQ-DES-B13](bulkhead.md):** `rect_w` now
reaches `flat_x`, so the corner meets its mating plane at every height and the interface is one
plane. That removed the bulkhead's overhang at the same time, because the bulkhead subtracts
this same section as its greeble tool.

The step is gone. **The question below is unchanged:** the interface still carries no clearance
of its own. Making the face clean did not give it a tolerance.

**Two printed parts meeting on coincident planes will interfere in practice.** Layer lines,
elephant's foot at the first layer, and the corner's own printed tolerance all act in the
direction that closes a zero gap. Nothing in the design records whether these are intended as
bearing faces — where zero is the right number and the fit is achieved by finishing — or
whether the interface has simply never been given a tolerance because the shared polygon made
one impossible to express.

**RESOLVED 2026-08-14: alternative 3, carried on the corner, implemented at 0.**

**What the tolerances at this joint are for.** Recorded 2026-08-14, and it was not written down
anywhere before: they accommodate **manufacturing variation and adhesive bond thickness**. They
are real, intentional spacing between surfaces — not dimensional allowances that happen to
leave room. That is what makes a mating pair with no gap a defect rather than a style: a
zero-gap pair has nowhere for the bond to go and nothing to absorb variation.

**The parameter.** `corner_tolerance` applies to both faces that seat against the bulkhead —
the flat at `flat_x` and the diagonal at `x + y = flat_offset` — over the corner's **full
height**. Each face moves inboard by the tolerance measured *normal to itself*, so:

```
flat_x      = -(panel_overlap + panel_offset) + corner_tolerance
flat_offset = nominal_flat_offset + corner_tolerance * sqrt(2)
```

The `sqrt(2)` is not a fudge: the diagonal runs at 45°, so shifting it by `corner_tolerance`
perpendicular moves its intercept by that times the tolerance. Dimension the two faces the same
way and they get different gaps.

**It is carried entirely on the corner**, which is alternative 3 and the same hand as the
greeble. When the bulkhead re-evaluates this description to cut its own socket it passes 0, so
the joint takes the clearance once. In the OpenSCAD authority that is an explicit trailing `0`
on the `corner_end` call, beside the greeble's literal 0. In the port it is structural: the
bulkhead's parameter set does not export the row at all, so the bulkhead's sheet holds the
literal 0 and there is no path by which the corner's value could reach it.

The drawback noted against alternative 3 — that the corner's polygon also generates its flat
*face*, so shrinking it moves a load-bearing surface — is real and is the reason the value is 0
rather than something larger. Moving the face is exactly what the parameter does; the question
is only how far.

**Where it is set.** The value is data, not code: `corner_tolerance` in
[`src/Fuselage/design_constants.json`](../../src/Fuselage/design_constants.json), beside every
other parameter the sweep holds constant — the five remaining clearances, two angles, and the
printer profile. `fuselage_variants.load_constants()` reads it once at import, and the sweep
exports the corner tolerance in the **corner's** parameter table only.

That file is not an axis. Everything in `variant_param/` is combined factorially, so a column
added there would make the clearance a swept dimension and multiply the variant count; the ten
numbers in that file are the same on every variant by design, and changing one moves the whole
sweep together. The loader refuses a missing key, an unrecognized one, a non-number and a negative,
rather than falling back to a default — a settings file that quietly substitutes its own value
builds every part at a clearance nobody chose and reports success. It is the same rule
`check_unseeded` enforces on the FreeCAD side, one layer further out.

Every OpenSCAD entry point that reaches the corner declares the row explicitly rather than
relying on the module default — `fuselage_corner.scad` and the six reference files in
`freecad/`. A default that nobody states is a parameter nobody can find, and `parameters.py`
can only check an assignment that is written down: it compares the reference files line by
line against the exported set and skips any row that is absent.

**The value is 0 for the sweep.** 0 is what every flown part was built at, and it is the only
value anything has evidence for. Verified 2026-08-14, four ways:

| Check | Result |
| --- | --- |
| 0 is a true no-op | `ref_corner_full` renders at 14146.8357350 mm³, the stored reference to the last digit |
| the parameter reaches the geometry | driving the full corner to 0.05 mm removes 55.6200845 mm³ at the driver's configuration |
| both backends respond identically | at 0.05 mm, agreement across 3 corners, worst delta 0.00198% |
| the bulkhead does not move | at 0.05 mm, 4 bulkheads render to the same figures as at 0, to the last digit |

The last row is the one that matters for "carried once": the sweep value was set to 0.05, the
bulkheads were rebuilt, and 2166.862256, 7111.092249, 37599.974537 and 74175.840334 mm³ came
back unchanged. The seed boundary holds, and nothing about the bulkhead depends on the corner's
clearance.

**Still open, and it follows directly from the rationale above:** if these faces are bonded,
0 leaves no bond line, and the right value is whatever the adhesive needs plus the print
variation of two mating faces. A 0.05 mm test build is drawn in the IP-FC-59 working reference
and costs the corner 27 to 217 mm³ depending on size. That the cost scales with the part while
the tolerance does not is worth settling before the value moves off 0 — nothing currently makes
it a function of `U`.

## See also

- [bulkhead.md](bulkhead.md) — the mating half, and the pocket that receives the greeble.
- [geometry_refactor.md](../implementation/geometry_refactor.md) — IP-GEO-3 (the thickness
  formula), IP-GEO-7 (the dimension functions), OQ-GEO-1 (why the parameters are grouped
  in Python and not in OpenSCAD).
