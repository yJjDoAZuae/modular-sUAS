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

1. **Carries the longeron.** A tube passes through the bore that runs the full length of
   the part. The corner is not itself the primary bending member — the longeron is — so
   the corner is better understood as the fitting that locates everything else onto that
   tube. Note that it *locates* rather than *retains*: the tube is snapped in and held by
   the bulkhead's greeble, which is a C with a mouth narrower than the tube. See
   [bulkhead.md](bulkhead.md#the-longeron-snaps-into-the-greeble).
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

## Open questions

| ID | Status | Question |
| --- | --- | --- |
| C1 | ~~resolved~~ 2026-08-06 | Are `greeble_thickness` and `greeble_nub_thickness` meant to be independent? |
| C2 | ~~resolved~~ 2026-08-06 | What is the greeble actually toleranced for? |
| C3 | ~~resolved~~ 2026-08-06 | Is the corner's dependence on `bulkhead_thickness` the right interface? |

**No open questions.** C1 became one parameter plus a formula (IP-GEO-22); C2 was closed
by test prints at both ends of the range, U=0.5 and U=4; C3 was closed by the observation
that the corner and its bulkhead are not independent designs at all.

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
their *cross-section and joint* parameters by construction — modelling them as separate
parts that happen to agree would need a constraint to hold them together, and constraints
can be violated — while bay length stays a parameter of the corner only.

The original wording of this question follows.

---

**OQ-DES-C3 — Is the corner's dependence on `bulkhead_thickness` the right interface?**
Three of the corner's `z` dimensions derive from a parameter that belongs to the bulkhead.
It is correct — they mate — but it means the corner cannot be reasoned about alone, and
the FreeCAD port will have to decide whether the joint is a first-class object with its
own parameters or stays as two parts that each know a dimension of the other.

## See also

- [bulkhead.md](bulkhead.md) — the mating half, and the pocket that receives the greeble.
- [geometry_refactor.md](../implementation/geometry_refactor.md) — IP-GEO-3 (the thickness
  formula), IP-GEO-7 (the dimension functions), OQ-GEO-1 (why the parameters are grouped
  in Python and not in OpenSCAD).
