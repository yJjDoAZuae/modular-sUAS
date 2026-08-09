# Bulkhead — Design

**Status:** Reconstructed from the implementation, 2026-08-06. This is the first design
authority the bulkhead has had; it was written by reading
[`fuselage_bulkhead_geometry.scad`](../../src/Fuselage/scad/fuselage_bulkhead_geometry.scad)
and the derivations in
[`fuselage_variants.py`](../../src/Fuselage/tools/fuselage_variants.py), not from an
existing specification.

**How to read it.** Statements about *what the geometry does* are read off the code and
are reliable. Statements about *why* are marked as inference where they are inference.
Where the intent could not be recovered, there is an open question rather than a guess.
The code is what builds parts; anything here that contradicts it is a bug in this
document.

The corner is the mating half — see [corner.md](corner.md), particularly the greeble.

---

## What the bulkhead is

The bulkhead is the transverse frame that closes a fuselage bay. It ties the four corners
into a rigid square, carries the bolts that join one bay to the next, and provides the
mounting surface for whatever the bay contains.

**A bulkhead does not know how long the bay is.** `FX`, the bay-length multiplier, scales
`unit_length`, and `unit_length` reaches the corner alone — so one bulkhead design serves
bays of every length. That is why `FX` appears only in `corner_size_variants.csv` and the
bulkhead sweep carries no `FX` axis: bulkheads are generated once per (panel, type, size)
and reused. See [OQ-DES-C3](corner.md#open-questions), and IP-GEO-23, which removed a
`unit_length` parameter that had been passed to these modules and never used.

**The greeble is the bulkhead's feature.** At each corner the bulkhead grows a positive
annular post with a snap rib around it; the corner is bored to receive it. Naming
throughout this file assumes that — "the flange at the greeble", "greeble to bolt web"
are locations *on the bulkhead*. See [the joint](#the-greeble-is-a-positive-post) below,
because the code makes the direction easy to read backwards.

It is **not a solid plate.** The default bulkhead is an open frame: a peripheral flange
that follows the outer mould line, four bolt bosses, and — optionally — a thin web that
spans between them. Nothing fills the middle unless a variant asks for it. *Inference:*
this is a mass decision. The bulkhead's structural job is edge stiffness and load
transfer into the bolts, neither of which the middle contributes to.

## The taxonomy: one peer axis, two cousins, two families

`BulkheadType` lists four values as though they were four kinds of the same thing. **They
are not, and the enum has the relationships close to backwards.**

### The only true peers are the fastener variants

`end_bolt` and `end_anchor` are the same part, differing only in whether the hole is sized
for a through-bolt or bored for a heat-set threaded insert. That is a genuine peer
relationship — two interchangeable options for one decision.

**And it is not in the enum.** It is `is_anchor`, a boolean, and it is *orthogonal* to the
type — the variation table applies it to both `end` and `cowling`:

| Variant | `is_end` | `is_interconnect` | `is_cowling` | `is_anchor` |
| --- | --- | --- | --- | --- |
| `end_bolt` | ✓ | | | |
| `end_anchor` | ✓ | | | ✓ |
| `cowling_bolt` | | | ✓ | |
| `cowling_anchor` | | | ✓ | ✓ |
| `interconnect` | | ✓ | | |

`interconnect` has no `is_anchor` variant because it has no bolt bosses at all — the axis
is *meaningless* there, not merely unused.

So **the one relationship that is a true peering is expressed as an attribute, while three
relationships that are not peerings are expressed as enum values.**

### Cousins — the structural unit cell

`END` and `INTERCONNECT` are **related but not peers.** Both exist to construct a fuselage
structural unit cell, and both carry the cell's full mating vocabulary: corners, greeble
posts, longeron bores, panel capture.

| Type | Role in the cell |
| --- | --- |
| `END` | Closes a unit. Bolt bosses; greeble posts; optional web |
| `INTERCONNECT` | Joins two units back to back. Two sections stacked, `2·bt`; **no bolt bosses** — captured between two bolted units rather than fastened |

### Family — the cowl interface

`COWLING` is a **distinct family**: used only with a cowl, never within a structural unit.
It substitutes the cowl joint for the panel joint — flange ring, plate, cowl lip, and **no
panel at all**, which `bulkhead_validity_check()` enforces.

### Family — inter-unit plates

`TAIL_BOOM` is a **second distinct family**: a flat plate used **between** structural units,
never within one. It does not participate in the cell.

**It is the first member of this family, not the last.** Landing-gear attachment bulkheads
and structural blocks are named in UC-6 of the
[migration architecture](../architecture/freecad_migration.md) and belong here.

Three properties follow from being an inter-unit plate rather than from the boom design:

- **Symmetric in `z`**, so print orientation carries no sign — unlike every cell bulkhead.
- **None of the cell's mating vocabulary**: no greeble, no panel slot, no cowl lip.
- **Separately generated already.** The boom bulkhead has its own geometry file
  (`fuselage_boom_bulkhead_geometry.scad`), its own sweep function, and its own variation
  table — the code has effectively separated this family already, while the *type enum*
  has not.

`NULL` exists as the unset default and never reaches geometry.

See [OQ-DES-B8](#open-questions) on whether the enum should be split to match.

The interconnect having no bolt bosses is the one that looks wrong and is not: it is
sandwiched between two bays that are themselves bolted, so it is captured rather than
fastened. It is also why it is twice as thick — it is two end-bulkhead sections mirrored
about their shared face:

```scad
bulkhead_section(true,  …)                       // z: 0 → bt, with web
mirror([0,0,-1]) translate([…, -2·bt])
    bulkhead_section(false, …)                   // z: bt → 2·bt, no web
```

Only the first section gets the web (`make_web`). *Inference:* a web on each half would
double the mass for no additional stiffness, since the two halves are fused.

`make_web` does more than add or omit the web. It also reaches
`bulkhead_flange_positive()` and `outer_corner_fillet()`, so it reads better as *"this is
the web-bearing face of the section"* than as a feature toggle — the flange and the outer
fillet change to suit. Nothing outside the geometry ever sets it; see OQ-DES-B3.

**It is not `2·bt` all the way round.** After stacking, a trapezoidal prism is subtracted
that removes the upper section everywhere inboard of the corner flange, so the full
double depth survives only *at the corners* and the runs between them drop back to a
single `bulkhead_thickness`:

```
        corner            mid-edge            corner
   ┌────────────┐                        ┌────────────┐   2·bt
   │            └──╲                  ╱──┘            │
   │               └──────────────────┘               │   1·bt
   └──────────────────────────────────────────────────┘
        ↑ full depth over the flange + its fillets
                    ↑ 45° ramp, one bt of run
```

**This is a mass reduction** (established 2026-08-06): the double depth is only needed where the
load is, at the corners where the longerons and the bolted joints land. Carrying it
around the whole circumference would add mass without adding strength.

The cut keeps full depth out to
`panel_offset + panel_overlap + flange_thickness + 2·flange_fillet_radius` — the flange's
inboard edge (`bulkhead_flange_positive()` places it at
`panel_offset + panel_overlap + flange_thickness`) plus two fillet radii of margin. So the
retained region is defined as "the flange and its fillets", not as an independent number.

The transition is a 45° ramp: the polygon's two inboard vertices differ by exactly
`bulkhead_thickness` in `x` over a `bulkhead_thickness` rise in `z`. *Inference:* a square
step would leave a horizontal overhang on the underside; 45° is the standard
self-supporting limit, so this prints without support in either orientation.

Reading the transform is the hard part. `rotate([90,0,0])` maps the polygon's `y` onto
model `z` and swings the extrusion axis onto `y`, so the polygon is drawn in the **x–z**
plane and swept across the full `unit_width`. Its `y` values — `bulkhead_thickness` and
`2·bulkhead_thickness` — are heights, not widths.

## Construction: one octant, mirrored

The bulkhead has eight-fold symmetry, and the code draws **one octant** and tiles it:

```scad
octant_tiled(unit_width, corner_radius)   //  = octant_to_full ∘ corner_translate
    → corner_translate  : move the drawing out to (unit_width/2 − corner_radius, …)
    → octant_to_full    : mirror_x ∘ mirror_y ∘ mirror_xy
```

Everything is therefore drawn in the neighbourhood of **one corner**, in that corner's
local frame, and the diagonal `mirror_xy()` produces the second half of the corner. This
is the single most important thing to know before reading the module: coordinates are not
measured from the centre of the bulkhead, and `x` and `y` are interchangeable by
construction.

The octant is trimmed by `octant_mask()`, a half-plane polygon subtracted after
everything else, so the drawing may overrun its wedge freely and be cut back at the end.
`mask_reach()` supplies the "far enough to be off the part" distance for those mask
vertices; `through_cut()` does the same for cutting solids that must pass all the way
through. Both were introduced by IP-GEO-9 to replace raw multipliers.

## Feature stack

Assembled as one `difference()`: a union of positive features, minus a set of cuts.

**Positive**

- `bulkhead_flange_positive` — the rim that follows the OML. Its inner edge sits at
  `corner_radius − panel_thickness − panel_tolerance`, i.e. flush behind the panel, and
  it is `flange_thickness` deep.
- `bolt_flange_positive`, `bolt_flange_fillet`, `bolt_web` — the boss around each bolt
  hole and the material tying it back into the rim. **Skipped for interconnects.**
- `bulkhead_web` — the thin span, `plate_thickness` tall, present only when `make_web`.
- Cowling-only: a flange ring (`corner_radius` less `flange_thickness`), a plate at
  `plate_thickness`, a longeron flange and chamfer, and the cowl lip extruded above the
  bulkhead by `cowl_flange_height`.

**Negative**

- **`corner_end()` itself**, subtracted — which is what *leaves* the greeble standing.
  See below.
- The longeron opening wedge — `greeble_opening_angle` (35°) **either side** of the
  diagonal, so a 70° mouth. This is what makes the greeble a **C** and lets the longeron
  snap in; see below.
- A cleanup cut on the outer faces of the corner cutout.
- The longeron bore, `longeron_radius + longeron_tolerance`.
- The bolt hole, at `(−bolt_offset, −bolt_offset)`, skipped for interconnects.
- `octant_mask`.

### The greeble is a positive post

```scad
greeble_tolerance_local = 0;
corner_end(U, bulkhead_thickness + 2·eps, …, greeble_tolerance_local, …);
```

The most consequential line in the file, and the one most likely to be misread. It sits
in the *negative* half of a `difference()`, so it looks like it cuts a pocket. It does
the opposite.

`corner_end()` is the corner's end section, and the corner's end section is *itself*
mostly a difference — a bore of `greeble_radius` with an annular groove out to
`greeble_nub_radius` through its middle third. Subtracting that solid from the bulkhead
removes bulkhead material wherever the corner has material, and leaves it wherever the
corner does not. What survives, standing out of the bulkhead face, is a post filling the
corner's bore with a rib filling the corner's groove.

So the bulkhead grows the greeble by subtracting the part that mates with it. The payoff
is that there is exactly **one** description of the joint: the two halves are complements
of a single shape and cannot drift apart. It is worth the moment of confusion.

The tolerance is forced to zero so the post comes out at nominal size; all fit clearance
is taken on the corner's bore instead. See
[corner.md](corner.md#where-the-clearance-lives) for why it is not split. Note that this
local zero also makes the module's own `greeble_tolerance` parameter dead — OQ-DES-B6.

The `+2·eps` and the `−eps` shift on the translate break coincident faces at the base of
the post. That is what `geometry_eps()` is for throughout.

### The longeron snaps into the greeble

The greeble is not a solid post. It is a **C**, split by a wedge cut on the diagonal —
and that wedge is how the longeron gets in.

```scad
// longeron opening cutout
polygon([[0,0],
         [sin(45−greeble_opening_angle)·corner_radius, cos(45−greeble_opening_angle)·corner_radius],
         [cos(45−greeble_opening_angle)·corner_radius, sin(45−greeble_opening_angle)·corner_radius]]);
```

**`greeble_opening_angle` is a half-angle.** The two vertices sit at 10° and 80°, so the
wedge removed spans **70°**, centred on the 45° diagonal. The tube is pressed in sideways
through that mouth rather than threaded in axially, and snaps home.

`GREEBLE_OPENING_ANGLE_DEG = 35` **was arrived at by experiment** (established 2026-08-06). It
is a tuned value. The geometry corroborates that it is doing snap-fit work rather than
merely providing clearance — the mouth is deliberately *narrower* than the tube:

| | chord across the mouth | tube diameter | mouth / diameter |
| --- | --- | --- | --- |
| any `U` | `2·r·sin 35°` | `2·r` | **57.4 %** |

where `r = longeron_radius + longeron_tolerance`. The ratio is scale-invariant because
the angle is, so the *proportional* interference is identical at every size — but the
*absolute* spread the arms must accept is not: 0.9 mm at U=0.5 against 6.9 mm at U=4.
Whether one experimentally-found angle can serve that whole range is
[OQ-DES-B7](#open-questions).

This also means the greeble does two jobs, and only one of them is the corner joint:

1. **Register the corner** — the post and its rib into the corner's bore and groove.
2. **Retain the longeron** — the C-shaped bore snapping onto the tube.

That is worth knowing before changing any greeble dimension. `greeble_thickness` sets the
wall that has to flex for job 2 while also setting the post diameter for job 1, so it is
not free to be tuned for either one alone.

## Derived dimensions

The bulkhead's own dimensions are computed in `derived_parameters()`, not chosen. The
pattern is that **structural dimensions scale with `U`, printed features scale in
extrusions and layers, and fit clearances do not scale at all.**

| Parameter | Formula | Reading |
| --- | --- | --- |
| `bolt.thickness` | `max(3·U, 3)` | Boss wall, floored at 3 mm |
| `bolt.radius` | `diameter/2`, or anchor bore | See below |
| `plate.thickness` | `ceil(4·U) · layer_height` | A whole number of layers |
| `web.fillet_radius` | `2·U` | |
| `web.width` | `6·U` if tail-boom else `3·U` | Boom bulkheads carry more load |
| `bulkhead_flange.thickness` | `max(ceil(3·U)·nozzle, 3·nozzle)` cowling, `max(ceil(2·U)·nozzle, 2·nozzle)` otherwise | A whole number of extrusions |
| `bulkhead_flange.fillet_radius` | `2·U` | |
| `bulkhead_flange.chamfer` | `1·U` | |
| `cowl_flange.height` | `2·U` when cowling, else 0 | |
| `cowl_flange.tolerance` | 0.2 mm when cowling | Does **not** scale |

The `ceil()` calls are the tell: a flange is a whole number of extrusion widths and a
plate a whole number of layers, because a wall 2.5 extrusions thick prints as either two
or three and the slicer decides which. Rounding up in the model takes that decision away
from the slicer. The cowling flange is one extrusion thicker than the standard one —
*inference:* it carries the cowl joint rather than just closing the bay.

### Bolts and anchors

`bolt.diameter` comes from the variation table. `bolt.radius` is then either half of it,
or — when `is_anchor` — the bore for a heat-set threaded insert, looked up by bolt size in
[`threaded_insert_dimensions.csv`](../../src/Fuselage/tools/threaded_insert_dimensions.csv).
That table is the authority for insert geometry; do not re-derive those numbers. Each row
carries a McMaster URL for both the standard and short insert.

**Only `anchor_diameter` is read.** The table also carries `anchor_depth_standard` and
`anchor_depth_short`; nothing anywhere in the repository consumes either. The depth
available for the insert is `bulkhead_thickness`, which is set by the size table with no
reference to the insert going into it.

**That is not an omission.** An insert longer than the bulkhead is thick is not a fault,
because **the insert is set from the interior side and may stand proud of that face.**
The interior is free space — nothing lands on it — so the surplus length simply sticks
out where it does not matter. The exterior face is the mating face and is what must stay
clear.

So the depth columns are informational rather than constraints, which is consistent with
nothing reading them. What matters is thread engagement in the material available, not
whether the insert is fully swallowed.

For reference, the relationship across the swept sizes:

| U | `bulkhead_thickness` | bolt | standard | short | insert stands proud by |
| --- | --- | --- | --- | --- | --- |
| 0.5 | 4 | M3 | 7 | 4.5 | 0.5 mm on the short |
| 0.75 | 5 | M3 | 7 | 4.5 | — |
| 1 | 6 | M4 | 7.5 | 5 | — |
| 1.5 | 6 | M4 | 7.5 | 5 | — |
| 2 | 8 | M5 | 9 | 6.5 | — |
| 2.5 | 10 | M6 | 9 | 7.5 | — |
| 3 | 12 | M6 | 9 | 7.5 | — |
| 4 | 16 | M8 | 14 | 7.5 | — |

The worst case is the smallest size, and it is 0.5 mm of a short M3 insert standing out
of the interior face. From U = 0.75 up the short insert is fully contained; the standard
insert is longer than the bulkhead below U = 2.5 and would stand proud accordingly.

Which of the two to fit at a given size is therefore a build choice, not something the
model constrains — and the table carries a URL for each.

`bolt.offset` is `8·U` from `standard_values()`, placing the bolt on the diagonal.

Note that `bolt.diameter` was, until IP-GEO-16, assigned to a dict that had never declared
it. It is a real field with a real consumer; it simply had no schema. That is the class of
defect the dataclass conversion closed.

## Validity

`bulkhead_validity_check()` rejects a combination when any of these fail:

```
panel_thickness == 0  or  panel_thickness ≥ 1·U           # not too thin to be worth it
panel_thickness ≤ corner_radius − (longeron_radius + longeron_tolerance
                                   + greeble_thickness + greeble_nub_thickness)
bulkhead_type != COWLING  or  panel_thickness == 0        # a cowling bulkhead has no panel
```

The first two are shared with the corner and mean the same things there. The third is
specific: **a cowling bulkhead never carries a panel**, because the cowl closes that end
of the airframe instead. A parameter row that asks for both is rejected rather than
reconciled.

The checks reject a large fraction of the Cartesian product, which is the expected
outcome of sweeping axes that are not independent (measured 2026-08-06):

| Sweep | Valid | Combinations |
| --- | --- | --- |
| corner | 264 | 432 |
| bulkhead | 148 | 360 |
| boom | 132 | 216 |

The 412 "valid combinations" quoted in `mask_reach()`'s justification comment is corner
plus bulkhead, 264 + 148 — not a figure for the whole sweep. The 576 parts a full run
produces is the *output* count across all five sweeps, cowls included, and is not
comparable to either.

## Print orientation

**Confirmed 2026-08-07 (IP-FC-3).**

**The modeled frame is the print frame.** The STLs the sweep produces are already in print
orientation — no rotation is applied between the model and the bed. That is a system-wide
rule, not a bulkhead one: *every* printable part in this system is designed so that model
`+z` is the build direction, and model `z` corresponds to the **aircraft body `x` axis**.

For the bulkhead specifically: **flat surface down.** Layers stack along model `z`, which
is the bulkhead's thickness direction.

That is what the geometry already implied — the part is drawn in `xy` and extruded by
`bulkhead_thickness`, the flange, web and bolt bosses all print without support in this
orientation, and the interconnect's depth change is a 45° ramp in the `x–z` plane, which is
self-supporting only if `z` is the build direction.

**Consequence for analysis (UC-8 tier 3): the bulkhead is weakest in through-thickness
tension** — separating one face from the other, across the layer interfaces. That is
exactly the direction a bolted joint loads it, and it is the single most important input to
an orthotropic model of this part.

**Z sign matters, and the rule is: flat surface down.** Most bulkheads are **not**
symmetric in `z`, and the geometry says so plainly — everything is built from the `z = 0`
face upward:

| Feature | `z` extent | Breaks symmetry because |
| --- | --- | --- |
| Flange, bolt bosses | `0 → bulkhead_thickness` | — |
| `bulkhead_web` | `0 → plate_thickness` | present only near the bottom face |
| `bolt_flange_fillet` | at `plate_thickness` | one-sided |
| Cowl flange lip | `bulkhead_thickness → + cowl_flange_height` | stands proud of the top face only |

So the `z = 0` face is the solid one — flange, web and bolt bosses all begin there — while
the far face carries the cowl lip and the open web cavity. That is the flat surface, and it
goes on the bed.

The only bulkhead that genuinely is `z`-symmetric is the **tail boom bulkhead**, which is a
flat plate. The interconnect is closer to symmetric than an end bulkhead, being two mirrored
sections, but only one of its halves carries the web (`make_web`), so it is not symmetric
either.

Getting this sign wrong would print the cowl lip into the bed and leave the web as an
unsupported ceiling. See [cowl.md](cowl.md#7-print-orientation) for the rest of the family.

## Open questions

| ID | Status | Question |
| --- | --- | --- |
| B1 | ~~resolved~~ 2026-08-06 | What sets `greeble_opening_angle = 35°`? |
| B2 | ~~resolved~~ 2026-08-06 | Is the interconnect's cut dimensioned or fitted? |
| B3 | **open** — intent unrecoverable | Should the web be a variant rather than a flag? |
| B4 | ~~resolved~~ 2026-08-06 | Have large-`U` bulkheads been printed? |
| B5 | ~~resolved~~ 2026-08-06 — not a defect | Should insert depth be a validity check? |
| B6 | ~~resolved~~ 2026-08-06 | `greeble_tolerance` was dead on the bulkhead side |
| B7 | ~~resolved~~ 2026-08-06 | Does one snap angle work at the *small* end? |
| B8 | **open** | Should `BulkheadType` be split to match the two families? |

**Two open: B3 and B8.** Neither is a defect — both need a decision rather than an answer.
B3's original intent is not recoverable; B8 is a forward-looking structural choice that
gets more expensive the longer it is deferred.

B4 and B7 together mean the swept range is validated in hardware at **both** ends, U=0.5
and U=4.

Resolved entries keep their full text below, in numerical position, with the reasoning
that produced the answer.

**~~OQ-DES-B1 — What sets `greeble_opening_angle = 35°`?~~ — RESOLVED 2026-08-06.**
It was **arrived at experimentally**, and what it does is let the longeron snap
into the greeble's centre hole. See [the longeron snap](#the-longeron-snaps-into-the-greeble)
above, which is written from that answer. It is a tuned value, not a derived one: do not
replace it with a formula.

**~~OQ-DES-B2 — Is the interconnect's relief cut dimensioned or fitted?~~ — RESOLVED
2026-08-06.** It is neither a relief nor a clearance: it is a **mass
reduction**. The interconnect's flange is only full `2·bt` depth at the corners, where
the longerons and the bolted joints put the load, and is narrowed to `1·bt` along the
runs between them. See [the interconnect](#four-types) above, rewritten from that answer.

The question was posed badly — I had guessed it was clearance for the panel to pass
between bays, which is wrong, and described it as a "relief cut", which named it after
the wrong purpose. The shape is a depth profile, not a clearance.

### OQ-DES-B3 — Should the web be a variant rather than a flag?

**Problem.** `make_web` is a boolean passed into the bulkhead geometry that decides whether
a section carries its internal web — the thin span, `plate_thickness` tall, that stiffens
the bulkhead between the bolt bosses and the flange.

**Original intent is not recoverable** (2026-08-06): whether it was meant to allow lighter
bulkhead variants, or was only ever a mechanization of the differences between bulkhead
types, is not remembered. Recorded so nobody spends time trying to recover it. What the
code establishes still constrains the decision:

- **Nothing ever chooses it.** `make_web` is `true` for every non-interconnect bulkhead
  and for exactly one half of every interconnect, fixed by position in
  `bulkhead_section_octant()`. No variation table has a column for it. Functionally it is
  a mechanization today, whatever it was intended to be.
- **But the idea exists elsewhere in the same family.**
  `boom_bulkhead_type_variants.csv` *does* carry `make_vert_web` and `make_lower_web` as
  variation columns. So "web presence as a variant" is realised for the boom bulkhead and
  not for the standard one — which is as consistent with an unfinished intent as with a
  deliberate difference.
- **It is not a simple on/off for one feature.** `make_web` reaches three places:
  `bulkhead_web()` itself, `bulkhead_flange_positive()`, and `outer_corner_fillet()`. It
  is closer to "this is the web-bearing face of the section", and the flange and fillet
  change to suit. Promoting it to a variation axis is therefore more than exposing a
  boolean — it changes three features at once, and the two halves of an interconnect must
  stay complementary.

The question is therefore not *what was meant* but *what it should be*.

**Alternatives**

1. **Leave it a positional flag**, and rename it to say so — `is_web_bearing_face` rather
   than `make_web`.
   *Benefits:* matches what it actually does today; no geometry change; removes the
   implication of configurability that the current name carries.
   *Drawbacks:* forecloses lighter bulkhead variants without deciding whether they are
   wanted.
   *Prerequisites:* none.

2. **Promote it to a variation-table column**, following `boom_bulkhead_type_variants.csv`,
   which already exposes `make_vert_web` and `make_lower_web`.
   *Benefits:* precedent exists in the same part family; enables a lighter end bulkhead as
   a swept variant; makes the two families consistent with each other.
   *Drawbacks:* it changes three features at once (`bulkhead_web()`,
   `bulkhead_flange_positive()`, `outer_corner_fillet()`), so it is not a simple boolean
   exposure; the two halves of an interconnect must stay complementary, which a free
   parameter does not guarantee; doubles the bulkhead sweep.
   *Prerequisites:* deciding whether a webless bulkhead is structurally acceptable — this
   is a strength question, not a plumbing one.

3. **Defer to the FreeCAD port**, where the section is an object and "web-bearing" is a
   property of it rather than an argument threaded four levels deep.
   *Benefits:* the awkwardness is an artifact of OpenSCAD's parameter passing and largely
   disappears; the port is rewriting this layer anyway.
   *Drawbacks:* the misleading name survives until then.
   *Prerequisites:* none.

**Recommendation: alternative 1 now, and revisit as alternative 2 only if a mass case is
made for a webless bulkhead.** The evidence says `make_web` describes *which face of a
section this is*, not a design choice — it is `true` everywhere except the mirrored half of
an interconnect, and no variation table asks for anything else. Renaming makes the code
honest at negligible cost. Promoting it to a variant is a real capability, but it should be
motivated by a mass or stiffness requirement rather than by the observation that the flag
exists.

**~~OQ-DES-B4 — Have large-`U` bulkheads been printed?~~ — RESOLVED 2026-08-06.**
Yes. **A U=4 bulkhead section has been printed and assembled** with 16 mm
longerons and a corner section. Both snap fits work: the longeron snaps into the greeble,
and the corner snaps onto it.

That is the top of the swept range, and it exercises both joints at once. It also
confirms the parametric standard is being followed in hardware — `longeron_radius = 2·U`
gives 8 mm at U=4, so a 16 mm tube is exactly the nominal size.

The other end is covered by [OQ-DES-B7](#open-questions): a U=0.5 part has also been
printed, with the tolerances working. Between them the swept range is validated in
hardware at both extremes — which is as much as two prints can establish, and more than
the rest of this document rests on. Everything else here is geometry that renders rather
than hardware that fits.

**~~OQ-DES-B5 — Should insert depth be a validity check?~~ — RESOLVED 2026-08-06. No.**
The question was based on a wrong assumption of mine: that the insert has to be contained
within the bulkhead's thickness. It does not. **It is set from the interior side and may
stand proud of that face** — the interior is free space, so the surplus goes where nothing
lands on it, and the mating face stays clear.

At the worst case in the swept range, U = 0.5, that surplus is 0.5 mm of a short M3
insert. Not a defect, and no validity check is warranted. The depth columns are reference
data for choosing a part, which is why nothing reads them.

I had recorded this as the one question describing a part that could not be assembled.
That was wrong, and there is now no such question here — everything else in this list is
a decision that was not written down rather than something broken.

**~~OQ-DES-B6 — `greeble_tolerance` is a dead parameter on the bulkhead side.~~ —
RESOLVED 2026-08-06.** It was threaded positionally through `bulkhead_section_full` →
`_octant` → `bulkhead_section`, and then discarded: `greeble_tolerance_local = 0` is what
reached `corner_end()`. The value the sweep passed (`GREEBLE_TOLERANCE_BULKHEAD_MM`,
itself zero) had no effect, and setting it non-zero would have done nothing at all.

**Chosen: drop the parameter** (IP-GEO-21), rather than honour the caller's value.

The deciding argument is that *the post is nominal* is an **invariant, not a setting**.
All greeble fit clearance lives on the corner's bore by design, because splitting it
across both halves makes the joint carry it twice. A module that accepts a tolerance it
must ignore in order to stay correct is advertising control it cannot offer — and the
person most likely to reach for it is someone whose parts do not snap together, who
would change the number, see no difference, and conclude the geometry is at fault.

Honouring the caller instead would have been behavior-identical today, since every
caller passes zero. It was rejected because it re-opens the double-clearance failure
mode the design deliberately closed, in exchange for a knob nobody should turn.

Removed from three SCAD signatures and four call sites, from both GUI drivers, from
`bulkhead_render()`, and from the Python constants. `bulkhead_section()` now passes a
literal `0` to `corner_end()` with the invariant stated beside it.

**~~OQ-DES-B7 — Does one snap angle work at the *small* end?~~ — RESOLVED 2026-08-06.**
Yes. **A U=0.5 part has been printed and the tolerances work.** With B4's U=4 result,
that is both ends of the swept range validated in hardware.

The concern was real but did not bite. Because `greeble_opening_angle` is an angle, the
mouth is 57.4 % of the tube diameter at every scale, while the wall doing the flexing
goes as `√U` — and below U = 1 it stops scaling at all, pinned at two extrusion widths by
the `max()` floor. The small sizes therefore have a proportionally *thicker*, stiffer
wall being asked to open by proportionally the same amount: 1.2 mm of wall spreading
0.9 mm at U = 0.5. That predicted a greeble too stiff to snap, or one that cracks. It
snaps.

So a single experimentally-tuned angle does hold across an 8× span of `U`, and the
`√U` thickness rule with its two-extrusion floor is doing the right thing at both
extremes. Nothing here needs a formula.

### OQ-DES-B8 — Should `BulkheadType` be split to match the two families?

**Problem.** The enum lists
`END`, `INTERCONNECT`, `COWLING` and `TAIL_BOOM` as peers, but the first three are frame
bulkheads and the fourth is an interstitial plate — a different kind of part with a
different mating vocabulary, different symmetry, its own geometry file, its own sweep
function and its own variation table. The code has already separated them everywhere except
in the type.

This matters now rather than later because **the plate family is expected to grow**: UC-6
names landing-gear attachment bulkheads and structural blocks, and the boom bulkhead is
explicitly the first of a set. Each addition made against a flat enum widens the gap between
how the parts are organized and how they are named.

**Alternatives**

1. **Split into two enums** — `FrameBulkheadType` and `PlateBulkheadType`.
   *Benefits:* the type says which family a part belongs to; validity checks and geometry
   dispatch stop needing to know that `TAIL_BOOM` is the odd one; new plate types are added
   without touching the frame path.
   *Drawbacks:* `derived_parameters()` and the filename scheme both branch on the single
   enum today, so both change; the variation tables' boolean columns need rethinking.
   *Prerequisites:* none.

2. **Keep one enum, add a family attribute** — a `family` field beside `type`.
   *Benefits:* smallest change; existing call sites keep working.
   *Drawbacks:* two things to keep in step, which is the failure mode this project has spent
   Phase 2 removing; nothing stops a mismatched pair.
   *Prerequisites:* none.

3. **Defer to the FreeCAD port**, and model the families as separate classes there.
   *Benefits:* the port is rewriting the parameter layer anyway, and Phase 3's guideline is
   not to refactor code scheduled for replacement.
   *Drawbacks:* every plate bulkhead designed before the port lands is built against the
   flat enum, so the cost of the eventual split grows with each one.
   *Prerequisites:* none.

**Recommendation: alternative 3 for the OpenSCAD path, alternative 1 in the port — but
decide the taxonomy now and record it here.** The naming does not need to change to make
the *design* explicit, and this document now states the two families regardless. What must
not happen is landing-gear bulkheads being designed as though they were peers of `COWLING`;
that is a design error the enum would quietly encourage, and it is not fixed by renaming
anything later.

### ~~OQ-DES-B9 — Is the morphological fillet the authority, or is a true fillet?~~ — DECIDED 2026-08-08: true fillets

**Decision.** The FreeCAD version uses **real fillets that make proper use of FreeCAD's
capabilities**. They should closely resemble the OpenSCAD version but **do not need to match
it to hundredths of a millimetre**.

**Scope, established 2026-08-09 while porting: this affects the boom bulkhead only.**
`fillet_inner` is called exactly once in `fuselage_bulkhead_geometry.scad`, inside
`bulkhead_web_inner_shape_octant`, and the only caller of the shape that reaches it is
`fuselage_boom_bulkhead_geometry.scad`. The frame bulkheads — end, interconnect, cowling —
never execute it. `bulkhead_web`, which they do use, already makes a **true fillet** by
subtracting a cylinder of `web_fillet_radius` at the re-entrant corner; the little step out
to `x = boss_x - web_fillet_radius` in its profile is exactly the material that cylinder
rounds. So the frame bulkhead ports with no fillet decision at all, and this question governs
the plate family.

This settles more than the web. It applies to all four fillet modules — `greeble_to_web_
fillet`, `bulkhead_bolt_flange_fillet`, `web_to_bolt_fillet` and `outer_corner_fillet` — and
to any other geometry where OpenSCAD approximates a feature it cannot express directly.

Two consequences follow, and both are load-bearing:

- **Equivalence for filleted parts is a deviation tolerance, not volume equality.** IP-FC-13
  cannot test the bulkhead the way it tests the corner. The corner remains strict; parts
  with fillets need a stated tolerance and a comparison that measures deviation.
- **The printed part changes slightly.** Parts printed before and after the port are not
  interchangeable at the fillet, though they are at every interface, since no interface
  dimension is set by a fillet.

The original question and its alternatives are kept below, because the reasoning for
rejecting a bit-exact reproduction is what justifies the tolerance.

---

**Problem.** The web's inner corners are rounded by `fillet_inner(web_fillet_radius)`, which
is not a fillet operation — OpenSCAD has none. It is a morphological approximation built
from three chained 2D offsets:

```scad
intersection() { offset(-r) offset(2r) offset(-r) children; children; }
```

Measured 2026-08-08, `Part::Offset2D` reproduces a *single* offset to under 0.01% but the
chain diverges by **19%** once the intermediate shape fragments into disjoint islands. The
bounding boxes agree exactly, so the offset distance is right; the two disagree about the
interior. No `Join` or `Fill` setting closes the gap, and offsetting the islands separately
gives identical results. See
[freecad_migration.md §IP-FC-9](../implementation/freecad_migration.md).

So the port cannot reproduce the current web shape by the current construction, and the
question is which shape is actually wanted. This blocks `bulkhead_web` and everything that
consumes its profile.

**What the geometry is for.** These are inner corners in a load-carrying web, so the radius
is there to reduce stress concentration. A morphological closing and a true fillet both do
that; they differ in what happens where features are closer together than `2*r` — which is
exactly the region where the two measurements diverged.

**Alternatives**

1. **A true fillet in the port** — round the inner corners with `Part::Fillet`, or with arcs
   constructed in the profile sketch.
   *Benefits:* it is what the feature means, and it is exact rather than approximate; a
   constant radius is what a drawing would dimension and what an analyst would expect; it
   does not degrade where features crowd.
   *Drawbacks:* the printed part changes shape slightly, so parts printed before and after
   the port are not identical; full-sweep equivalence (IP-FC-13) cannot use volume equality
   for the web and needs a stated tolerance instead.
   *Prerequisites:* a deviation tolerance for IP-FC-13.

2. **Reproduce the morphological result exactly**, by whatever means that takes.
   *Benefits:* comparable geometry across the migration; IP-FC-13 stays a strict test for
   this part as it is for the corner.
   *Drawbacks:* it preserves an approximation for its own sake, and the approximation is
   worst precisely where the fillet matters most; `Part::Offset2D` demonstrably will not do
   it, so this means writing the offset chain by hand.
   *Prerequisites:* establishing why the dilations differ, which is not yet known.

3. **Treat the current profile as incidental** and choose the radius afresh in the port.
   *Benefits:* no effort spent matching a shape nobody chose deliberately.
   *Drawbacks:* discards a shape that has been printed and flown; assumes the current
   geometry carries no tuning, which has been the wrong assumption before on this project.
   *Prerequisites:* confirmation that the web profile was never tuned by experiment.

**Recommendation: alternative 1, conditional on the web never having been tuned by
experiment.** The feature is a fillet and FreeCAD can make a fillet; carrying an
approximation forward because it is what the old tool could express is the wrong reason to
keep it. But this changes a part that has been printed, and OQ-DES-B1 above records that
geometry here is sometimes arrived at by experiment rather than derivation — the greeble
opening angle was exactly that. So whether the web profile was tuned needs answering before
the change, not after.

### ~~OQ-DES-B10 — `greeble_bolt_web` is called with three arguments in the wrong order~~ — FIXED 2026-08-08

**Decision.** The matching names are the correct interface association; the old alignment was
the accident. The call is corrected to
`(bulkhead_thickness, bolt_offset, plate_thickness, flange_thickness, flange_chamfer)`.
[`audit_call_args.py`](../../src/Fuselage/tools/audit_call_args.py) now reports zero
positional mismatches across `src/Fuselage/scad`.

**How wrong the arguments were depends on which parameters you feed it — and the hand driver
is not the authority.** `fuselage_bulkhead.scad` sets `extrusion_width = 0.4`, which makes
`flange_thickness = 0.8` equal to `plate_thickness = 0.8`, so one of the three slots landed
correctly there and the defect was partly self-cancelling. **The sweep uses
`extrusion_width = 0.6`**, giving `flange_thickness = 1.2`, and at those values *all three*
arguments were wrong:

| Parameter | Received (sweep) | Intended (sweep) |
| --- | --- | --- |
| `plate_thickness` | 1.2 | 0.8 |
| `flange_thickness` | 1.0 | 1.2 |
| `flange_chamfer` | 0.8 | 1.0 |

**Measured effect — still smaller than the analysis below suggested.** The module's own
output changes, but its material is *entirely absorbed* by the surrounding flange, web and
bolt flange at the smaller sizes, so the assembled part is bit-identical. Checked by removing
the call outright, at the driver's values *and* at a real swept variant:

| Case | Assembled bulkhead, with vs without the module |
| --- | --- |
| U=1.0 `end_bolt` 3/16 in, derived (`ew=0.6`) | **unchanged**, 6922.5048968 mm³, 29000 triangles |
| U=0.5, hand driver | **unchanged**, 1994.8939143 mm³ |
| U=1, hand driver | **unchanged**, 5733.5689982 mm³ |
| U=4, hand driver | changes — the module contributes 1584.75 mm³ |

So **no part printed at U=1 was affected**, at the swept parameters as well as the driver's.
At U=4 the bolt sits 32 mm out and the diagonal web is no longer covered by its neighbours,
so the module does carry material and the correction moves roughly 0.1% of the part.

So `greeble_bolt_web` is not dead code — it is dormant at small sizes and load-bearing at
large ones, which is also why the defect survived: every part small enough to print and fly
easily was immune to it.

---

**Original analysis, kept because it is what the decision was made against.**

### OQ-DES-B10 — `greeble_bolt_web` is called with three arguments in the wrong order

**Problem.** Found 2026-08-08 while porting. There is one call site and its last three
positional arguments are rotated against the signature:

```scad
module greeble_bolt_web(bulkhead_thickness, bolt_offset, plate_thickness, flange_thickness, flange_chamfer)

greeble_bolt_web(bulkhead_thickness, bolt_offset, flange_thickness, flange_chamfer, plate_thickness);
```

So inside the module, at the driver's values:

| Parameter | Receives | Value | Intended |
| --- | --- | --- | --- |
| `plate_thickness` | `flange_thickness` | 0.8 | 0.8 — correct **by coincidence** |
| `flange_thickness` | `flange_chamfer` | **1.0** | 0.8 |
| `flange_chamfer` | `plate_thickness` | **0.8** | 1.0 |

**The table above is at the hand driver's values, which are not authoritative.**
`fuselage_bulkhead.scad` sets `extrusion_width = 0.4`, making
`plate_thickness = 4 * layer_height = 0.8` and `flange_thickness = 2 * extrusion_width = 0.8`
equal, so one slot lands correctly there. The sweep derives its parameters through
`derived_parameters()` at `extrusion_width = 0.6`, where they are 0.8 and 1.2 and **nothing
cancels**. Design questions must be read against the derived values, not against a driver
written to exercise one configuration by hand.

**What it changes.** The diagonal web joining the greeble to the bolt flange:

- its width comes from `flange_thickness/(2*sqrt(2))`, so **0.3536 instead of 0.2828** — the
  web is 25% thicker than the flange thickness intends;
- its chamfered rib section is
  `[[0,0], [pt+fc,0], [pt+fc,-ft/2], [pt,-ft/2-fc], [0,-ft/2-fc]]`, built as
  `[[0,0], [1.6,0], [1.6,-0.5], [0.8,-1.3], [0,-1.3]]` where the intent is
  `[[0,0], [1.8,0], [1.8,-0.4], [0.8,-1.4], [0,-1.4]]`.

Both are small, and both are in a load path — this web is what carries load from the
longeron corner to the bolted joint.

**This is a question, not a defect report, because the parts have been printed and flown
with this geometry.** A thicker web is not obviously wrong; it may even be why the part
works. What is certainly wrong is that the geometry does not follow from the parameters,
so nobody could tune it deliberately.

**Alternatives**

1. **Fix the call, port the corrected geometry.**
   *Benefits:* the part follows its parameters again; changing extrusion width or layer
   height does what it says; the port has one description, not one plus an accident.
   *Drawbacks:* the printed part changes in a load path, so it wants a print and a fit check
   before it is trusted.
   *Prerequisites:* none.

2. **Fix the call and re-tune the constants** so the built geometry is unchanged — i.e.
   decide the current dimensions were right and express them deliberately.
   *Benefits:* keeps a flown geometry exactly while making it explicit and parametric.
   *Drawbacks:* needs a judgement about which of the current dimensions were wanted.
   *Prerequisites:* none.

3. **Port it faithfully, bug included**, and defer.
   *Benefits:* the port stays a pure translation and IP-FC-13 can compare strictly.
   *Drawbacks:* carries an accident into a new codebase where it will be much harder to
   notice, since the FreeCAD version has no positional call to misread.
   *Prerequisites:* none.

**Recommendation: alternative 2 if the current web dimensions are wanted, otherwise 1.**
Either way the call is fixed — alternative 3 preserves a defect precisely where it is
hardest to find later. The real question is only whether the *current* dimensions should be
kept, and that is a judgement about a flown part rather than about the code.

**Porting in the meantime follows alternative 3**, so the port continues and matches the
existing reference; switching later is a change to two constants.

## See also

- [corner.md](corner.md) — the mating half; the greeble; where the fit clearance lives.
- [geometry_refactor.md](../implementation/geometry_refactor.md) — IP-GEO-6
  (`octant_tiled`), IP-GEO-8 (`geometry_eps`), IP-GEO-9 (`through_cut`, `mask_reach`),
  IP-GEO-16 (the parameter dataclasses).
- [fuselage_folder_summary.md](../../src/Fuselage/docs/fuselage_folder_summary.md) — how
  the sweep drives all of this.
