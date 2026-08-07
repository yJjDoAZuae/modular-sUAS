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

## Four types

`BulkheadType` distinguishes them, and `encode_bulkhead_type()` resolves the boolean
columns from the variation table into exactly one:

| Type | What it is | Distinguishing geometry |
| --- | --- | --- |
| `END` | Closes the end of a bay | Bolt bosses; greeble posts; optional web |
| `INTERCONNECT` | Joins two bays back to back | Two sections stacked, `2·bt` overall; **no bolt bosses** |
| `COWLING` | Mates a bay to a nose or tail cowl | Flange ring, plate, cowl lip; **no panel** |
| `TAIL_BOOM` | Carries a tail boom tube | Adds the collet and key features of `fuselage_boom_bulkhead_geometry.scad` |

`NULL` exists as the unset default and never reaches geometry.

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

**One open: B3**, and it is not a defect — it needs a decision, not an answer, because
the original intent is not recoverable.

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

**OQ-DES-B3 — Should the web be a variant rather than a flag?** — **Original intent is
not recoverable** (2026-08-06): whether `make_web` was meant to allow lighter bulkhead
variants or was only ever a mechanization of the differences between bulkhead types is
not remembered. Recorded so nobody spends time trying to recover it. What the code
establishes is still worth stating, because it constrains the decision:

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

The question is therefore not *what was meant* but *what it should be*. Leaving it as a
positional flag is defensible and cheapest; making it a variant would want the boom
bulkhead's columns as the precedent to follow.

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

Honouring the caller instead would have been behaviour-identical today, since every
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

## See also

- [corner.md](corner.md) — the mating half; the greeble; where the fit clearance lives.
- [geometry_refactor.md](../implementation/geometry_refactor.md) — IP-GEO-6
  (`octant_tiled`), IP-GEO-8 (`geometry_eps`), IP-GEO-9 (`through_cut`, `mask_reach`),
  IP-GEO-16 (the parameter dataclasses).
- [fuselage_folder_summary.md](../../src/Fuselage/docs/fuselage_folder_summary.md) — how
  the sweep drives all of this.
