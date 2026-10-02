# Cowl interior surface — the algorithm

*IP-FC-16. Written 2026-08-21, once [OQ-ARCH-17](../architecture/freecad_migration.md#open-questions)
removed the last undecided item.*

The cowl today is a solid blank with channels cut into it. It has no wall
([cowl.md §6.2](cowl.md)), which is sufficient for printing and insufficient for everything
else: a blank has no mass to report, no wall to analyse, and nothing to assemble against.
This document states the method that gives it one.

It is an **algorithm** document. It says what to build and how to know the result is right.
It does not choose an OCC entry point, because the acceptance tests below are what a choice of
API has to satisfy, and an API named here without being measured would read as decided.

---

## 1. What this produces, and what it must never become

The output is the **solid representation** of [cowl.md §6.4](cowl.md): the notched blank,
shelled, with the rib modelled where each notch is. It serves **UC-2, UC-3, UC-4, UC-7 and
UC-8**.

> **The UC-1 print export continues to come from the un-shelled notched blank.** Cowls are
> printable in spiral vase mode, which spirals one contour per layer and admits no interior
> geometry at all, so a cowl that has been given a modelled inner surface is no longer
> vase-printable ([OQ-DES-CW6](cowl.md#open-questions)). Shelling is a downstream operation for
> the other use cases and **never a replacement for the blank**. A port that "improves" the
> cowl by giving it a proper wall and exports that for printing has silently removed a
> printing capability, and nothing in the geometry flags it — the STL looks better and slices
> worse.

Both representations come from one parametric source. This document describes the branch that
produces the second one.

---

## 2. Preconditions

These are properties of the input the algorithm relies on. **Each is asserted at run time, not
assumed.** A precondition that is merely true today is an accident waiting to be inherited.

### P1 — Every section is steeper than `overhang_angle_from_bed`

The interior is a *horizontal* inset, so on a wall tilted by α from vertical it leaves a
perpendicular wall of `t·cos α`, which is zero at a horizontal face. The cowl design avoids
near-horizontal geometry deliberately — the nose closure is split off as `nose_nose` and
`nose_plate` so the body never turns over, the tail is open at both ends, and every internal
relief is cut at `overhang_angle_from_bed` — so the degenerate case is outside the design
domain rather than a case to survive
([OQ-ARCH-17](../architecture/freecad_migration.md#open-questions)).

The shallowest surface the design permits is 35° from the bed, or **55° from vertical**, which
still leaves

    0.6 mm × cos 55° = 0.344 mm

of wall: 57 % of nominal, and about seven times the 0.05 mm floor below which nothing in this
project means anything.

**Assert it.** A section whose local slope is shallower than `overhang_angle_from_bed` is a
design violation upstream. The build stops and names the station. It must not emit the knife
edge, which renders, exports, passes `isValid()`, and resurfaces later as a stress singularity
in a UC-8 result nobody re-derives by hand. This assertion is also one of the few places the
**unenforced** couplings on `overhang_angle_from_bed` would actually surface — that value has
to agree with where the nose/cowl break line falls and with the buttress ramps, and nothing in
the code enforces either ([OQ-DES-CW11](cowl.md#open-questions)).

### P2 — The eroded section is a single closed loop

Erosion can pinch a region into pieces or annihilate it entirely, and OCC's behaviour when it
does is not a clean failure. See §7. Assert one loop per station.

### P3 — The exterior is available as a surface, not only as a mesh

Sectioning a tessellated OML gives polylines whose vertices are mesh artifacts, and a surface
fitted through them inherits the tessellation. This is what IP-FC-4's STEP export exists for.

### P4 — No notch lies in the layer plane

A rib forms because the slicer's single perimeter walks into the notch and back out again
**within a layer**. A notch lying in the layer plane offers no such path: the feature would have
to be formed between layers instead of within one, which thin-wall perimeter slicing cannot do,
and it comes out malformed. **So horizontal ribs are not used** — this is a property of the
design, stated 2026-09-04, and it is what keeps §4.2's `t_cut / sin θ` away from its
singularity. The shallowest cut the design contains is the tail's 30° diagonal, at 1.4 mm.

This is P1's sibling and a different object: P1 says the *body* is nowhere shallower than
`overhang_angle_from_bed`, because a horizontal surface leaves no wall; P4 says no *notch* is
horizontal, because a horizontal notch leaves no rib.

**Asserted 2026-09-04, in the build and not only in the check** (IP-FC-118).
`cowl_interior.dilated_notches` sees every cutting tool, so it is where P4 lives: a tool whose
own plane is horizontal is refused, and so is one with no planar face at all, which is not a
slab and whose thickness has no direction. Every build reports the shallowest cut plane it saw
— 90° on the nose, 30° on the tail — because the assertion deliberately separates *horizontal*
from *not horizontal* and says nothing about *shallow*: no minimum angle is stated anywhere in
the design, and choosing one in a constant would be inventing a design decision. If a floor is
ever wanted it is an open question, not a number in that file.

It had been true and unchecked, which is what P1's own paragraph warns about. Worse, the one
place that could have seen it looked away: `check_cowl_interior.in_plane_width` returned
`None` for a horizontal cut and `rib_gap` answered with `continue`, so the notch dropped out of
the rib check without comment and the part reported `OK`. Both now raise, and P4 joins P1 and
P2 in the block of preconditions the acceptance test requires to fire.

---

## 3. Inputs

| Symbol | Source | Value at the sweep |
| --- | --- | --- |
| `S` | the exterior, as surfaces | `oml/vsp_nose.step`, `oml/vsp_tail.step` |
| `n_p` | `slicing.cowl_n_perimeters` | 1 |
| `w` | `printer.extrusion_width` | 0.6 mm |
| `t = n_p · w` | derived | 0.6 mm — **the inset** |
| `t_cut` | `buttress_cut_thickness` | 0.1 mm |
| feature stations | the buttress parameters | see §4.1 |

`t` is the *horizontal* inset, and it is the cowl's own perimeter count in the same sense
`cowl_n_perimeters` is used everywhere else — see [OQ-DES-CW9](cowl.md#open-questions).

---

## 4. The construction

    exterior S
      → stations ζ₀ … ζₙ            §4.1  adaptive, derived not tuned
      → sections C(ζ) = S ∩ {z = ζ}
      → eroded contours Cin(ζ)      §4.2  2-D, in the layer plane
      → consistent parameterization §4.3
      → fitted interior surface     §4.4  G1 threshold, G2 objective
      → closed solid                §4.5

### 4.1 Stations

Start from the stations that already carry meaning, then refine by measurement (§5).

**Seed stations.** The OML's own defining sections ([cowl.md §1.2](cowl.md)), plus every
**feature station** — the axial positions where the exterior itself has an edge:

- each buttress ramp's start and end, where `r_inset · tan(overhang_angle_from_bed)` brings
  the notch to full depth or takes it away;
- the cut plane, `cut_len`;
- the base flange, for the nose.

**Feature stations are patch boundaries, not interior knots.** The exterior has a genuine
crease there, and §4.4's continuity requirement applies *within* a patch. Demanding G2 across
a rib end would smooth away a feature the part really has — and matching the exterior's
continuity class is the actual requirement that G1/G2 is a statement of
([OQ-ARCH-5](../architecture/freecad_migration.md#open-questions)).

### 4.2 Eroding a section

For station ζ, take `C(ζ) = S ∩ {z = ζ}` **with the buttress notches already cut**, and erode
by `t`:

    Cin(ζ) = erode( C(ζ), t )

**Erode the notched section by the morphological identity, not directly.** Where the section
is the blank minus the notches, `A − B`, use

    erode(A − B, t)  ==  erode(A, t) − dilate(B, t)

The right-hand side is well conditioned; the left-hand side is the exact shape that returned a
**null shape** from `Part::Offset2D` in IP-FC-54 and took the whole part with it. That was a
different part — the boom bulkhead's web — but the same operation on the same kind of input,
and the failure was not a tangency a nudge would clear: every erosion from 3.0 to 5.0 mm was
null while 6.0 mm succeeded.

**The rib falls out of this and is not modelled separately.** The notch is `t_cut` = 0.1 mm
wide. Eroding by `t` removes a `t`-neighbourhood of it from each side, so the gap the erosion
leaves is

    t_cut + 2·n_p·w  =  0.1 + 1.2  =  1.3 mm

which is exactly the rib thickness [OQ-DES-CW3](cowl.md#open-questions) states. The wall
follows the notch in and back out, and the material between the two passes *is* the rib. That
is the whole reason the notch exists — it buys a rib inside a single-wall print, under a mode
that permits no other mechanism ([cowl.md §6.4](cowl.md)) — so the algorithm reproducing it
for free is the confirmation that the erosion is the right operation.

**1.3 mm is the vertical-cut case, and not every cut is vertical.** The tail's diagonal buttress
slabs are extruded to `t_cut` and then rotated 30°, so the slab is 0.1 mm thick normal to its
own plane and a layer plane cuts through it `t_cut / sin 30°` = 0.2 mm wide -- making the rib
there 1.4 mm. Measured to four decimals at every diagonal, and resolved as
[OQ-DES-CW19](cowl.md#open-questions) on 2026-09-04: **the cut's thickness is fixed whatever its
orientation, and a perimeter's width is evaluated parallel to the build plate**, so the rib is

    2·n_p·w + t_cut / sin θ

with θ the angle between the cut plane and the layer plane. The construction above is the
θ = 90° case of it, and **P4 is what keeps θ away from 0**, where the expression diverges: a
horizontal notch would leave no rib at all, so the design does not contain one. Anything checking a rib has to carry the angle: a flat 1.3 mm expectation
reports correct geometry as an error, which is what §6's first version did.

### 4.3 Contour correspondence

A surface fitted through a stack of contours needs each contour parameterized **consistently**
with its neighbours, or the surface twists between stations. This is the classic loft failure
and it does not announce itself: the result is a valid, closed, plausible solid.

- Anchor the parameter origin to a **feature**, not to whatever the sectioning returned first.
  The rounded-rectangle sections ([OQ-DES-CW5](cowl.md#open-questions)) have four corner arcs;
  use one of them, consistently, and a fixed traversal direction.
- Distribute the remaining parameter by **arc-length fraction**, so a station with a notch and
  a station without still correspond.
- Where a notch is present at one station and absent at the next, the correspondence is not
  well defined — which is why those are patch boundaries (§4.1), not points to interpolate
  through.

### 4.4 The surface

Fit a surface **through** the eroded contours with continuity conditions imposed. The four
requirements are [OQ-ARCH-5](../architecture/freecad_migration.md#open-questions)'s and are not
re-opened here:

1. **Curvature-aware adaptive spacing** — §4.1 and §5.
2. **Bidirectional curvature.** Doubly curved, circumferentially *and* axially. Not
   developable, not ruled.
3. **G1 tangency is the threshold, G2 curvature is the objective**, across every join within a
   patch.
4. **Not a ruled surface with tangency discontinuity.**

**What this excludes.** A `ruled=True` loft is excluded outright by (4). So is a `ruled=False`
loft that merely interpolates the section curves without tangency constraints — it satisfies
neither (3) nor generally (2). What is wanted is an **approximation with continuity
constraints**, the same class of construction OpenVSP uses for the exterior, applied to the
interior.

**Why this is not cosmetic.** Wall thickness is the *difference* between the exterior and the
interior. The exterior is a piecewise cubic Bézier carrying G2 across several stations by
design. If the interior is only C0 at its joins, **wall thickness is discontinuous at every
join** — a thickness step at a seam the exterior does not have — even though each surface is
individually acceptable. That is a stress raiser for UC-8 and a visible artifact in UC-4 and
UC-7.

### 4.5 Closing the solid

The wall is bounded by the exterior, the interior, and an annulus at each open end. Both cowls
are open — the tail at both ends, the nose body where it is cut to the closure parts — so
there is no cap to construct and no turnover to handle.

**Both cowls are one symmetry cell, not a full body — [cowl.md OQ-DES-CW20](cowl.md#open-questions).**
The tail is built as its `y ≥ 0` half, the nose as one octant; every step above — the sections,
the erosion, the surface fit, the notch cuts, the wall — runs entirely inside that cell, bounded
by the cell's own construction planes, and produces a cell-local result only. A full, mirrored
body is never constructed as an intermediate at any point in this construction.

**Mirroring happens exactly once, as the very last step, to the finished wall — never earlier,
and never to any other intermediate.** The cavity is cut out of the cell's own notched body while
still inside the cell; the resulting wall is what gets carried out to the whole part, by the same
mechanism and in the same mirror order the outer OML solid already uses to build itself from that
same cell. Nothing here mirrors a partial result — the cavity, the un-notched body, or any other
earlier intermediate — and finishes construction on it afterward: a boolean between two shapes
that were each already carried out to the whole part by an independent mirror step is not
trustworthy regardless of whether both are exactly symmetric, since OCC's boolean kernel is free
to introduce asymmetry or fail outright on a full-size operation even when its inputs are exact,
and this project has measured it doing both. One symmetry cell, one deferred mirror, one code
path for both cowls, differing only in which cell and how many mirrors — never in order of
operations.

**Mirroring a solid that still carries the flat cap where it was cut from its cell is itself not
safe to do by an ordinary boolean fuse.** Two solids that share their entire boundary over exactly
one face and nothing else are a degenerate case for OCC's general boolean intersector, measured to
fail outright (`ValueError: Null shape`) even when that shared face is exact to machine precision.
The cap is instead stripped from the finished wall, the remaining open shell mirrored, and the two
open shells sewn together along their now-identical shared edge — construction, not a boolean
asked to discover a relationship its two inputs already have exactly.

---

## 5. The refinement criterion

**Spacing is derived, not tuned.** Refine until the fitted surface agrees with the *true*
per-layer erosion, then stop. That replaces an arbitrary interval with one tolerance that
means something physical.

Between each adjacent pair of stations:

1. Take the midpoint ζ_m.
2. Compute the **true** contour there — section `S` at ζ_m and erode by `t` (§4.2).
3. Compute the **fitted** surface's contour at ζ_m.
4. Measure the deviation `d` between them: the two-sided Hausdorff distance, sampled densely
   along both. One-sided is not enough — it misses a fitted contour that bulges outward where
   the true one has no material.
5. If `d > τ`, insert ζ_m as a station and recurse on both halves.

Terminate when every interval passes. A floor on interval length guards against a
non-converging feature; **reaching the floor is a failure to report, not a result to accept**,
because it means the surface does not represent the erosion at that station and nothing
downstream will know.

### The tolerance, and why it is absolute

    τ = 0.05 mm

**It does not scale with `U`, and that is the opposite of the project's usual rule** — for a
stateable reason. `compare_backends.bbox_tol()` scales with `U` because it measures agreement
between two engines on a whole part, and a whole part gets bigger. This tolerance measures
whether a **wall** is in the right place, and the wall is `n_p · w` = 0.6 mm at every `U`,
because extrusion width is a property of the machine. A tolerance that grew with `U` would be
2 % of the wall at U = 0.5 and 67 % of it at U = 4.

0.05 mm is the smallest linear dimension that means anything in this project, and it is 8 % of
the wall. **Getting absolute-versus-relative backwards here is not hypothetical**: IP-FC-56
used an absolute 1e-9 mm³ volume tolerance on parts of very different sizes, which is 6e-14 of
a bulkhead, and it cost two silent forty-minute runs before the cause was found. The rule is
that the tolerance is relative to *the thing being measured*. Here that thing is the wall.

### A gap this criterion does not cover, and the fix decided for it

**Steps 1-5 above run entirely before the rib cut.** They measure the fitted surface against the
true per-layer erosion of `S` — §4.2's smooth interior, with no notch subtracted from it yet.
`dilated_notches()`'s rib cut happens afterward, in `cavity()`, and nothing in this criterion or
anywhere else in the construction re-measures the *finished*, rib-cut wall against τ.

**That gap is real, not theoretical: found 2026-09-23, root-caused 2026-09-25
([OQ-DES-CW21](cowl.md#open-questions), full evidence in
[freecad_migration.md IP-FC-143](../implementation/freecad_migration.md)).** The finished wall
reads thinner than τ at the tail's shallow-angle (30°) diagonal buttresses, growing with `U` from
a few thousandths of a millimetre at `U` = 1 to 0.150 mm — three times τ — at `U` = 4, confirming
what §10's `U` = 4 prediction below already expected of this construction. Five direct
measurements ruled out every candidate that would have meant this criterion's own convergence was
at fault (`RIB_CUT_FUZZ`, `RIB_FACETS`'s polygon approximation, a coverage gap in step 5's own
bisection, cross-mirror rib overlap at the tail's seam) and instead found the smooth surface
already clean at the exact point the finished wall reads thin — the rib cut itself removes
measurably more material there than the smooth surface's own offset predicts. **This criterion is
correct as far as it goes; it simply does not go far enough**, because a rib boundary at a
shallow cut angle is a case §4.2's erosion identity does not by itself protect.

**Decided, 2026-09-25: extend this criterion with a second pass evaluated after the rib cut, not
work around the gap by bounding `U` or widening τ.** The termination structure is the same as
steps 1-5 — measure the deviation, insert a station and recurse where it exceeds τ, stop when
every interval passes — but run a second time against the *finished* solid's own wall thickness
near each notch boundary, rather than against the pre-rib fitted surface. A build only converges
once both passes are inside tolerance.

**Correction, 2026-09-26: the second pass cannot run inside `cavity()` at all, and an initial
implementation there was wrong for exactly that reason.** `cavity()` is only ever given `body` —
`cowl_tree.pieces()`'s `cell_body`, the *un-notched* cell — because that is the correct, and only,
reference for steps 1-5's own pre-rib fit. The finished wall's true exterior is not `body`; it is
`notched` (`cell_cut`, "that same cell with its buttress tools already cut into it"), which
`shell_solid()` alone holds, and only after computing `inside = cavity(...)`. A `cavity()`-internal
attempt at this second pass measured the rib-cut cavity against `body`'s exterior — the only
exterior it has ever had — and at a station where a buttress cut removes exterior material, that
reference is measurably wrong: a direct check (`tail_shell`, `U` = 3.0, `z` = -217.727) found the
real wall's exterior loop 0.56 mm from the true thin point, while `body`'s own exterior at the same
(x, y) was 26.5 mm away, a different surface entirely. **The second pass belongs in
`shell_solid()`, evaluated directly on `wall = notched.cut(inside)`** — both the exterior and the
cavity boundary then come from the same finished, cell-sized solid, which is exactly what
[§6](#6-verification)'s wall check already does on the whole part and what this function's own
docstring already argues is strictly better done at cell size, before mirroring. Full evidence
trail in [freecad_migration.md IP-FC-143](../implementation/freecad_migration.md).

**Correction, 2026-09-26: not by cutting `notched` a second time.** Implemented instead by
slicing `notched` directly at each candidate `z` and comparing that contour against the cavity's
own boundary — the same "two already-sliced contours" pattern `outer_at` already uses against
`body`, never a second, independent boolean between `notched` and the cavity. A second cut here
would repeat the exact "two shapes each independently built, then a boolean between them" mistake
`shell_solid`'s own docstring already recounts three instances of; `shell_solid`'s own
`notched.cut(inside)` remains the one authoritative cut. This still needed `open_arc`'s stripped
polyline discipline reproduced without `open_arc` itself — `notched`'s section does not always
chain the way `body`'s does — and, once reproduced, built open rather than closed, since a closed
polyline's wraparound chord across the excluded construction-plane strip cuts straight across the
cell's full width and reads spuriously close to legitimate points nowhere near a real notch.
Both are recorded in full in [freecad_migration.md IP-FC-143](../implementation/freecad_migration.md).

**Correction, 2026-09-27, per [cowl.md OQ-DES-CW22](cowl.md#open-questions): the second pass does
not re-scan the whole patch on every round.** Verified correct but measured unaffordable: re-checking
every point across the full patch, every one of up to six rounds, cost 9.5 hours without finishing
the `U` = 3.0 target once the pass actually needed multiple rounds to converge, rather than the
zero-insertion pass every case tried before OQ-DES-CW21 happened to take. **Decided: round 0 still
scans the whole patch, front-loaded with stations placed at the notch topology's own edges (already
read for the edge-focused scan) rather than left to discover them one bisection at a time; round 1
onward re-scans only a ±15-20 mm window around that round's own insertions**, a width measured
directly from how far one properly-bisected insertion's effect on the finished wall actually
reaches (decaying from -0.023 to -0.024 mm within a millimetre of the insertion to at most
±0.0012 mm, 2.4 % of τ, beyond 20 mm), not assumed. **Implemented and verified 2026-09-27**: both
`tail_shell` `U` = 1.0 (765 s, zero refinement rounds needed) and `U` = 3.0 (4,277 s, six rounds)
now converge without raising `Unconverged`, a large improvement over the 9.5-hour build this
replaced. Full numbers in [IP-FC-143](../implementation/freecad_migration.md).

**A residual gap, found immediately on that same verification, is not this pass's convergence
failing to run long enough — see [cowl.md OQ-DES-CW23](cowl.md#open-questions).** This pass's own
comparison (`_finished_wall_gap`/`finished_outer_at`) measures distance between two independently-
sliced contours -- the candidate surface's own slice and `notched`'s -- and never performs the real
`notched.cut(inside)` boolean itself, by design (a second boolean here would repeat the "two shapes
each independently built, then a boolean between them" mistake `shell_solid()`'s own docstring
already records three instances of). That prediction does not always match what the real boolean
produces: even a completely unconverged, round-0 candidate already shows the real, external
`wall_thickness()` check reading 0.0534 mm thin at `tail_shell` `U` = 3.0's worst station, at the
same time this pass's own distance-based check reports that station clear. **An initial hypothesis
that the gap came from `FINISHED_PLANE_TOL`'s exclusion band hiding a defect near a cell-boundary
plane was tested directly and refuted**: the real worst point there sits 78.688 mm from the tail's
one cell-boundary plane, thirty times the 0.5 mm tolerance -- nowhere near it. The real, external
check already catches this correctly; the gap is between what this pass converges to internally
and what that check finds, not a gap in acceptance testing.

**Characterized further, and a fix attempted directly, 2026-09-27 — see [cowl.md OQ-DES-CW23](cowl.md#open-questions)
for the full evidence and recommendation.** The gap, measured across all 12 real acceptance
stations on the same build, is signed both ways and present at every station (roughly ±0.01-0.04 mm),
not a rare, isolated defect. Inserting a station at the exact point the real (not predicted)
measurement says is worst — the most favorable case for closing the gap by refinement — moved the
real thickness there by only 3 % of the deficit, against roughly fourteen times that effect on the
*predicted* thickness for the same kind of insertion (the measurement behind this section's own
windowed re-scan sizing above). Station insertion is a weak lever on the real result, which this
pass has no other lever to pull; recommended there (not yet decided) to document this pass as a
best-effort predictor and rely on the existing external check as authoritative, rather than pursue
further refinement.

**A separate, more serious finding, 2026-09-28 — see [cowl.md OQ-DES-CW24](cowl.md#open-questions).**
Investigating whether the residual above reflects unreliable measurement, five independent fresh
builds confirmed the real reading is exactly reproducible (0.546556 mm to six decimal places,
every time). But nudging every point in one "row" -- `_fit()`'s term for the ring of sample points
that defines the cross-section at one fixed `z`; the whole surface is a stack of these rings, one
per station, fit together -- outward by a small (sub-0.1 mm), physically-plausible amount, applied
at a notch-tool-edge station specifically, was found to flip `shell_solid()`'s real construction
(`notched.cut(inside)` plus `mirror_across_cell`) between a normal result, an outright caught
failure ("5 disconnected shells"), and a result two orders of magnitude larger and opposite in sign
from the surrounding trend -- the last of which raises no exception at all. The same test on two
ordinary (non-notch-edge) rings found only clean, linear sensitivity, with no failures. This is a
construction-reliability question at notch-edge stations specifically, independent of which check
reads the result, and does not change this section's own OQ-DES-CW23 recommendation -- the ring
nearest OQ-DES-CW23's own target station tested clean.

**[Every specific clearance number from here through this section's end is retracted, 2026-10-01 --
see the correction note in cowl.md OQ-DES-CW24. A measurement bug (a `_Polyline` defaulting to
`closed=True` across multiple disconnected wire loops) made clearance numbers against the fused rib
tool unreliable; a corrected re-measurement is in progress. The qualitative conclusion that some
stations are much thinner than others likely survives; the specific numbers do not.]**

**Root cause confirmed and found to be live, not synthetic-only, 2026-09-28.** The fragile ring is
exactly one rib tool's own `z`-minimum, in a region where four separate tools overlap across most
of the tail's length -- the "rib crowding near a corner" mechanism IP-FC-137 raised as a hypothesis
(H3) against synthetic geometry, now confirmed against the real construction. A direct,
*unperturbed* survey of the real round-0 candidate's own clearance to the dilated tool set across
that region found the minimum was 0.000759 mm -- under a micron, on the actual build this whole
item has used throughout, not a deliberately perturbed one -- with ten of 96 sampled stations under
0.01 mm. `RIB_CUT_FUZZ` snaps these into a clean cut indistinguishable from a comfortable one; the
pipeline does not currently report the difference between a build that cleared by 0.6 mm and one
that cleared by a fraction of a micron. See [cowl.md OQ-DES-CW24](cowl.md#open-questions) for the
full evidence and a recommendation to pursue a build-time clearance-margin check.

**The thinnest clearances are not concentrated at notch edges.** A follow-up check compared the
survey's worst 15 stations against the same build's `feature_stations()` values (26 edges): only 2
of the 15 fall within 1 mm of one, and the single worst station (0.000759 mm) sits 9.3 mm from the
nearest edge. Sensitivity-to-perturbation and raw-clearance-minimum are two different questions with
two different answers -- the first is concentrated at notch edges, the second is not -- and a
build-time check needs to sample the whole rib-crowded region, not the edge stations alone. See
[cowl.md OQ-DES-CW24](cowl.md#open-questions) for the resulting concrete check design (metric,
domain, and a threshold candidate of 0.01 mm; sampling density and failure behavior still open).

**A genuine free-parameter screen, 2026-09-30, corrected what "perturbation" had tested so far.**
Everything above perturbed the already-fitted surface's own output points, not an actual free
parameter -- a real but different question. Re-running the full, independent construction from
scratch for 13 cases (eight real design parameters from `PARAMS_TAIL`, four algorithmic knobs: `TAU`
and notch-edge seeding standoff) found no construction failure anywhere, unlike the row-nudge test --
but at magnitudes (0.5 degrees, 0.5-1 mm) larger than the 0.6 mm wall itself, so this is not yet a
like-for-like comparison against the row-nudge test's 0.01 mm failure threshold. `top1_angle` and
`top_diag_angle` are real levers on the crowding (worsened the minimum 23-26%, and `top_diag_angle`
also moved which station is worst); seeding standoff -- alternative 4's own idea -- was tested
directly and did not help, finding a thinner minimum instead of a safer one.

**A finer-magnitude follow-up, matching the row-nudge test's own ~0.01 mm/0.01 degree scale, found a
second, more acute near-tangency.** Seven of eight finer dimensional cases changed nothing, but
`top_diag_angle` at +0.01 degrees -- one-fiftieth the earlier test's size -- dropped the minimum
clearance to 0.000009 mm, under `RIB_CUT_FUZZ` itself, at a station (`z` ~ -192) no other case in
this item has flagged. `RIB_CUT_FUZZ` caught it (the cut still came back one valid solid), but this
is a real, previously-unseen near-tangency, and the non-monotonic relationship to perturbation size
(a 0.01 degree nudge lands on it; a 0.5 degree nudge in the same direction mostly moves past it) is
consistent with the unperturbed design already sitting within a hundredth of a degree of it. This is
a new, uncharacterized lead, not yet investigated to confirm whether `U` = 3.0 already approaches it
unperturbed. See [cowl.md OQ-DES-CW24](cowl.md#open-questions) for the full comparison table.

**That lead was investigated, 2026-10-01, and found something broader.** A dense re-scan of the
unperturbed baseline near `z` ~ -192 found the design does not sit close to that specific tangency --
but a different one 14 mm away, `z` = -206.22, reads 15 nm, 1.5x `RIB_CUT_FUZZ`'s own threshold,
missed entirely by every coarser survey this item had run. A full-tail follow-up then found this is
not an isolated second point: **at least six distinct near-zero clearance points (27-285 nm) recur
from `z` = -286 to `z` = -25**, several of them outside the one rib-crowded corner this section's
root cause explains, and even a 0.05 mm fine pass understates some of them (the `z` ~ -206 feature
needed 0.02 mm to find its true floor). A brute-force grid fine enough to find all of these reliably
would cost on the order of 19 hours per build at the sampling rate measured here -- this is now a
materially harder problem than "one crowded corner is thin," and the build-time check OQ-DES-CW24
recommends needs an adaptive search, not a fixed grid.

**Corrected, 2026-10-01: the `z` ~ -192/-206.22 near-tangency itself was a measurement bug, not a
real feature -- but the broader picture survives at a less extreme scale.** A `_Polyline` defaulting
to `closed=True` across multiple disconnected wire loops (the fused tool's slice has 6-57 separate
loops, not one) manufactured phantom chords that read as meaningless near-zero distances. With that
fixed, `z` ~ -206 does not rank among the whole tail's worst 15 points at all. The corrected survey
found instead: **minimum clearance 0.000060 mm (60 nm, 6x `RIB_CUT_FUZZ`, not under it) at
`z` = -134.498, with 15 genuine points from 60 nm to 4113 nm scattered from `z` = -268.85 to
`z` = -14.45** -- still wider than the one corner this section's root cause explains, still
under-resolved by any affordable fixed grid, and still ~19 hours to find by brute force (a timing
fact the bug never affected). See [cowl.md OQ-DES-CW24](cowl.md#open-questions) for the full detail.

---

## 6. Verification

| Check | What it catches |
| --- | --- |
| **Perpendicular wall** at sampled points equals `t·cos α` within τ | the erosion was applied as a 3-D normal offset instead of a 2-D inset — a different surface, and the exact error mode this whole method exists to avoid |
| **Rib thickness** measures `2·n_p·w + t_cut / sin θ` -- 1.3 mm at a vertical cut, 1.4 mm at the tail's 30° diagonals ([OQ-DES-CW19](cowl.md#open-questions)) | the notch eroded as a notch rather than being smoothed away. **Write the angle into the expectation:** a flat 1.3 mm here reports correct geometry as an error, which it did |
| **Volume** equals exterior minus interior cavity | the solid closed the way it was meant to |
| **G1 across every join within a patch** | requirement (3), the one a plausible-looking loft silently fails |
| **Surface distance** from the fitted surface to a densely re-eroded reference, via [`surface_distance.py`](../../src/Fuselage/tools/surface_distance.py) | a fit that passes at the sampled stations and wanders between them |
| **P1, P2 assertions fire** on a deliberately shallow section | the preconditions are checked rather than documented |

The wall and rib checks are the load-bearing ones. Volume agreement says two solids enclose the
same space; it does not say the wall is where it should be, and a wall in the wrong place with
compensating error elsewhere passes on volume alone.

That is about what a volume check cannot *see*. There is a second problem with it, in the
number itself, and §9.6 carries it: `Shape.Volume` is wrong on solids of this kind by a
fraction of a percent, by an amount that depends on how the solid happens to be cut into
faces. **A volume here is only meaningful as a difference between volumes taken the same way
over the same operands** — which is what the row above and both identities in §9.6 are. A
volume compared against an expected value, or between two independently built solids, has to
come from [`solid_measure.py`](../../src/Fuselage/freecad/solid_measure.py) instead.

---

## 7. Failure modes to expect

**`Part::Offset2D` returns a null shape.** Seen in IP-FC-54, where every erosion from 3.0 to
5.0 mm was null and 6.0 mm succeeded — so a "nudge the value" workaround finds a value that
works and leaves the defect. Use the morphological identity (§4.2) and assert P2.

**An outward offset does not merge faces that grow into overlap.** FreeCAD offsets each face
of a multi-face source independently, and a *positive* offset can grow two into each other and
keep both, double-counting the overlap (IP-FC-52). Relevant wherever a dilation appears — the
right-hand side of the identity in §4.2 has one.

**The twisted loft.** §4.3. Produces a valid closed solid with a plausible volume. Caught by
the wall-thickness check and by nothing else in this table.

**Smoothing away a rib end.** Fitting one G2 surface across a feature station removes the
feature and the result looks *better*. Caught by the rib-thickness check at stations either
side of the ramp end.

**The same wire, in a different order.** `makeOffset2D` returns a wire whose edge list may be
*rotated* between processes — same edges, same lengths, same curve to 65 nanometres, different
starting edge. `Wire.discretize` allocates its points per edge, so on a wire whose edges run
from 0.04 mm to 152 mm that slides every sample along the curve by up to 0.068 mm. Anything
downstream that uses a sample *index* — a centroid taken as an unweighted mean, a parameter
origin snapped to the nearest sample — inherits it, and the station count then moves between
runs of identical code. Use arc length, never the index. This is invisible within one process:
repeats inside a single run agree exactly, and only separate processes differ.

**A boolean that fails partially and reports success.** Cutting with a list of separate tools
can succeed on most and fail on some. The result is still a valid closed solid, so nothing
downstream objects; the cavity is simply larger than it should be and eats the wall. On the tail
this cost about a quarter of the rib material and split the wall into five pieces, because the
ribs are what bridge the buttress slots. Fuse the tools into one before cutting, and check the
operation's own postcondition — §9's rib-residue and partition checks — rather than the
plausibility of the result.

---

## 8. Deliberately not specified here

- **The OCC entry point for the fit.** §4.4 states the requirement and §6 states the
  acceptance test. Naming an API here without measuring it would read as decided. **Now
  measured — see §9, which records what was built and where it departs from §4 and §5.**
- **Section count.** Derived by §5. If it is being chosen, something has gone wrong.
- **Anything about the print representation.** §1.

---

## 9. As built

*IP-FC-17, 2026-09-04. Built as
[`cowl_interior.py`](../../src/Fuselage/freecad/cowl_interior.py), with
[`check_cowl_interior.py`](../../src/Fuselage/freecad/check_cowl_interior.py) running §6.*

Sections 1 to 8 stand. **§§9.1 to 9.5 are the five places the construction had to be more specific
than they are, and in two of those different from what they say**; §9.6 adds the two acceptance
checks §6 turned out to need, and §9.7 is what the parts measure. Both cowls go through the **same
construction functions** — the nose and tail entry points differ only in which blank they ask
for — so each of these applies to both.

### 9.1 The identity is evaluated in 3-D, not per station in 2-D

§4.2 writes `erode(A − B, t) == erode(A, t) − dilate(B, t)` as an operation on each section.
Built that way, every contour handed to the fit already has the notches cut into it, and §4.4's
smooth surface is then asked to run across the crease each notch makes. That is §7's *smoothing
away a rib end* arriving by another route — not at the ramp ends but at every station, in the
circumferential direction.

What is built instead: fit the surface through the **eroded blank alone**, whose sections are
smooth and have no creases in them, then subtract the **dilated notches as solids** from the
finished interior. It is the same identity evaluated once in three dimensions instead of once
per station in two. The crease is then a boolean edge, which is what it is on the part.

### 9.2 The structuring element is a horizontal disc, not a ball

Following from §9.1: dilating a *solid* invites a solid offset, and a solid offset grows the
notch by `t` in every direction including along the surface normal, which would take `t` of wall
off the ends of every rib. The dilation is done by sweeping the notch solid around a **horizontal
circle** of radius `t`, so the growth is in the layer plane and nowhere else. Perimeter width is
an in-plane measurement, so both halves of the identity have to be in-plane — this is the same
requirement §6's first row states for the wall, applied to the tool.

### 9.3 Fitting spacing and checking spacing are two different numbers

§5 has one spacing, which conflates two jobs. **The tolerance is on the printed perimeter
width**, so the sampling that has to be fine is the sampling the *wall* is evaluated at; the
sampling the surface is *defined* from only has to capture the shape. As built these are
separate: the surface is fitted at 1.0 mm of arc (120 to 1200 samples per contour) and the wall
is evaluated at 0.20 mm (480 to 6000).

This is not a refinement of an implementation detail. The criterion's cost is **quadratic** in
the sample count — it is a points-by-segments distance matrix — so a single spacing makes the
fit as expensive as the check for nothing, and it is what makes the difference between testing
the method in half a minute and testing it in an hour and a half.

### 9.4 τ measures the wall, not the surface

§5 compares the fitted contour against a re-eroded reference contour by two-sided Hausdorff
distance. As built, the number compared to τ is

    | distance(outer contour, fitted contour) − t |

measured in the layer plane at the midpoint station: **the error in the wall itself**, not the
disagreement between two constructions of the same curve. This is the same tolerance with a more
direct meaning. §5's own justification for 0.05 mm is that it measures *"whether a wall is in the
right place"* — this measures that, rather than a proxy for it.

### 9.5 Periodicity has to be built, not declared

A section is a closed loop, and the surface through a stack of them has to be periodic in the
circumferential direction or the seam is a discontinuity. **`Part.BSplineSurface.interpolate`
has no periodic option, and calling `setVPeriodic()` afterwards only relabels the seam** — the
surface is still built as though it had two ends. Measured at the seam: 0.1552 mm of error,
against 0.0039 mm for a genuinely periodic skin. It is worst exactly where it is least
acceptable, because §4.3 anchors the parameter origin to a corner arc, which is where the seam
therefore falls.

As built, each row is a `Part.BSplineCurve.interpolate(..., PeriodicFlag=True)`, and the surface
is skinned from those curves' poles with `buildFromPolesMultsKnots(..., vperiodic=True)`.

**This section describes the tail's pre-2026-09-20 architecture, superseded under
[cowl.md OQ-DES-CW20](cowl.md#open-questions) — see §4.5 above for the construction that replaced
it.** Periodicity was a requirement of fitting one continuous 360° surface directly, not of the
geometry itself — it existed only because the construction this section describes always worked
on the full, both-sides body. The fit that replaced it (`cowl_interior.open_arc`, `_fit` with
`PeriodicFlag=False`) builds an *open* patch bounded by the cell's own construction planes
instead, and the seam this section measures is produced once, by mirroring the finished wall
(§4.5), rather than by declaring a surface periodic. This section stays as the record of why the
previous, full-body architecture needed periodicity at all; implementation status and verification
numbers are tracked in [freecad_migration.md IP-FC-139](../implementation/freecad_migration.md),
not here.

### 9.6 Two acceptance checks §6 does not have

§6's table checks properties of the finished wall. Both of the defects found while building this
produced a wall whose properties were fine — see
[freecad_migration.md, IP-FC-17 findings](../implementation/freecad_migration.md). These two
check what an *operation* promised instead, and they are the reason the build is trustworthy:

| Check | What it catches |
| --- | --- |
| **Rib residue** — after the ribs are cut, `cavity ∩ ribs` is empty | a boolean that cut some tools and not others. Measured 0.000000 mm³ on a correct build; the failure left about a quarter of 6703.72 mm³ of rib behind and split the wall into five pieces, and every check in §6 passed it |
| **Partition identity** — `notched − cavity` and `notched ∩ cavity` add back up to `notched` | a cut that lost material. Caught a nose build that returned a **415.54 mm³** wall where every other run gives 9713.4 — which §6 passed as `OK`, because a wall that is mostly missing still measures 0.600 mm wherever it survives |

Neither is a tolerance on the answer. Both are identities that the operation has to satisfy, and
that is the whole point: a wrong cavity and a right one are both valid closed solids.

Both are computed from `Shape.Volume`, which IP-FC-119 has since measured as wrong by 0.16 to
0.24 % on solids of this kind. They are differences of volumes taken the same way over
overlapping geometry, where that error should largely cancel — and the measured partition slips
of ~1e-6 say it does.

**The audit ran (IP-FC-120, 2026-09-05), and it neither cleared nor condemned them.** What it
established is that the error is a property of the **face partition** rather than of the solid:
merging 535 faces into 449 on the nose moved `Shape.Volume` by 91.08 mm³ — 0.94 % — without
moving the solid at all. It is also not *predictable* from the partition, because two walls
with those same differing partitions had meshes agreeing to 3.3e-6. So the cancellation these
two identities rely on cannot be derived; it can only be observed, and it is observed.

Two things make that acceptable here. Both identities subtract shapes produced by the same
booleans over the same operands, which is the case where a shared partition is likely rather
than accidental. And **the direction of a failure is safe**: a partition effect would make a
zero identity read nonzero, which is a check firing, not a check passing something bad. The
rule that follows is for reading the result rather than for the build — **a residue or slip
that is small but not zero is not evidence of lost material until it has been re-measured**
by `solid_measure.converged_difference`, which cancels discretisation between matched
partitions and refuses mismatched ones, or by `solid_measure.surface_difference`, which is
indifferent to face layout altogether.

**That rule was exercised for real, not just stated, 2026-09-21 — the tail at `U` = 1.0 fired
the partition-slip check at 3.593e-04, over the floor in force at the time.** Two fuzzy-boolean
numerical-robustness interventions were tried first and neither explained it: the same small
tolerance that cleanly fixed a genuine, unrelated disconnection defect at `U` = 0.75 (a single
buttress tool's dilation grazing the interior surface at a near-tangent angle, pinching off a
literal zero-volume sliver) barely moved this slip when applied to the rib cut and did not move
it at all when applied to the wall cut — a real defect would be expected to respond to exactly
that kind of intervention, and this did not. Measured instead with `solid_measure.converged_volume`
on the wall, the kept material, and the cell body independently: the slip by converged
tessellation is **1.614e-05** (4.79 mm³), 22 times smaller than `Shape.Volume`'s reading of the
identical partition, and itself inside the 1.6e-3 ceiling already named below. `PARTITION_TOL`
is raised to `2.0e-3` in consequence — above the measured noise ceiling rather than below it, so
a real gross failure (415 mm³ against 9713, 1.6e-2) still fires and a measured noise level does
not.

**Two further limits on the above, measured 2026-09-11 under IP-FC-117.**

**The partition identity's blind spot grows linearly with `U`.** `PARTITION_TOL` is taken
against the **blank**, and the wall is a shrinking share of the blank as the part grows: the
wall goes as `U²`, because `n_p·w` = 0.6 mm is a property of the nozzle and not of the
airframe, while the blank goes as `U³`. So the *pre-2026-09-21* 1e-4 was **37.6 mm³ at `U` = 1,
0.39 % of that nose wall, and 2408 mm³ at `U` = 4, 1.54 % of that one** — four times less
sensitive, for the same reason the shell is proportionally thinner. Nothing is failing: the slips actually
measured are ~1e-6, three orders inside. What it says is that the identity's power to catch
*lost wall material* decays as parts grow, so at the large end it is a gross-failure detector
and nothing more. (An earlier draft of this paragraph put the `U` = 4 figure at 16 %, by
dividing into `Shape.Volume`'s own reading of the wall — which is exactly the instrument the
next paragraph says is unusable there. 1.54 % is against the wall's real volume.)

**And the two instruments named above are not equally safe.** `converged_difference` reaches
the geometry through `mesh_volume`, which integrates the divergence theorem and therefore needs
a **closed** tessellation — and on these shells at `U` ≥ 2 a fixed 0.001 mm tessellation came
back with **1200–1400 unpaired edges**, every such reading wrong by two to four orders of
magnitude while every closed one was sane. Refining does not rescue it: 0.00025 mm took the
count to **12320**, about ten times worse, because a finer mesh has more facets and so more
places to leave a gap. `surface_difference` samples points on the surface and calls
`distToShape`; it never integrates, so an open mesh cannot corrupt it. **Where the mesh may be
open — which is the large end of the `U` range — `surface_difference` is the one to reach
for**, and a mesh-volume figure should not be believed without its unpaired-edge count.

### 9.7 Measured, at `U` = 1

| | nose | tail |
| --- | --- | --- |
| stations, by refinement | 9 | 16 |
| worst wall error against τ = 0.05 mm | 0.0374 mm | 0.0480 mm |
| wall | 9714.2617 mm³ | 23685.2264 mm³ |
| solids / faces | 1 / 503 | 1 / 2480 |
| rib residue | 0.000000 mm³ | 0.000000 mm³ |

### 9.8 A disconnected cavity or wall is refused at any scale, not accommodated

**There is no `U` or condition under which the cavity or the wall is legitimately more than one
solid.** A rib is what bridges a buttress slot across the erosion identity in §4.2 — where
`dilate(B, t)` locally consumes all of `erode(A, t)` at a station, the identity's result there
is zero width, not a thin one, and if that zero-width point is the only thing connecting two
otherwise-separate regions, the result comes apart. An earlier version of `cavity()` and
`mirror_across_cell` treated a multi-solid result as legitimate — solidifying each disconnected
shell and returning a `Part.Compound` when there was more than one — on the grounds that the
tail's own rib slots can split a cavity into disconnected pieces. **That is wrong, corrected
2026-09-21: a disconnected result means a rib failed to bridge, and refusing it is what makes
that visible instead of printing a part that is missing a piece.** `cavity()` now raises if its
own cut does not close into exactly one solid, checked separately from the rib-residue identity
above because a rib can be volumetrically fully removed and still fail to bridge — disconnection
is a topology defect, not a volume one. `mirror_across_cell` and `_extend_across_cell` raise the
same way rather than solidify a multi-shell sew result.

**Found this way, at the tail's `U` = 0.75: a single buttress tool's dilation grazing the
interior surface at a near-tangent angle, not rib crowding.** Traced to `Diag12Safe` in
isolation from the other ten real tools — cutting the smooth interior by its dilation alone
reproduces the identical split, a literal zero-volume sliver (`0.000000` mm³, a 0.17 mm wide
bounding box) pinched off where the tool's boundary nearly touches the cavity's. This is not the
rib-crowding-near-a-corner mechanism IP-FC-137's synthetic H3 test found and then ruled out
against real geometry — it is the same class of near-coincident-geometry degeneracy this section
already documents for the mirror step (§4.5) and the cell-level cut, here inside the ordinary
rib cut instead, one tool at a time rather than between two full-part shapes. Fixed the same way
those were: not by discarding the artefact, but by making the boolean itself robust to it — a
small fuzzy tolerance (`cowl_interior.RIB_CUT_FUZZ`, chosen empirically at the smallest value
that closed this case, three orders below `RIB_RESIDUE`) on `cavity()`'s rib cut and its retry.

**That fuzzy tolerance has its own side effect, found the same day: it can split one contiguous
cell-boundary cap into several coplanar pieces.** At the tail's `U` = 0.5 and 0.75, the fuzzy
rib cut left the cap as two adjacent faces (1857.29 + 151.93 mm² instead of one 2009.22 mm² face)
— same combined area, same plane, sharing an edge that is an artefact of the cut rather than a
real boundary. `_extend_across_cell` extends every cap face it finds independently before
sewing, so two pieces of one true cap produced two overlapping lateral walls along their shared
artefact edge, and the sewn result no longer solidified validly — a second, distinct defect from
the disconnection above, surfaced only because the fix for the first one changed the cap's own
topology. Fixed by merging same-plane cap faces (`.fuse()` then `.removeSplitter()` — a plain
coplanar merge, not the near-tangent 3-D case this module otherwise avoids) back into as few
faces as the true boundary has, before extending any of them. Verified end to end after all
three fixes: both cowls build a valid, exactly symmetric wall at every one of the eight swept
`U` values, 16 of 16.

---

## 10. Known limits

None of these stops the parts being built or used. They are the shape of what has *not* been
established, and each is a work item in
[freecad_migration.md](../implementation/freecad_migration.md).

- **Both candidate constructions have now run, and the one in use is the better of the two**
  (IP-FC-115, measured 2026-09-05). The cavity is assembled by cutting the dilated ribs out of
  the smooth interior and then cutting that out of the blank. The same set can be had by
  cutting the smooth interior out of the blank and fusing back the part the ribs occupy. Both
  were run on one saved set of operands, so the comparison is of the assembly and not of the
  parts. They build the same wall — the symmetric difference is empty in both directions and
  2003 sampled boundary points of each lie on the other's faces to within 6e-10 mm — and the
  one in use is **316 s against 723 s** on the tail. The reason the alternative was expected to
  be easier does not hold: its two halves *overlap*, because the shell already contains whatever
  rib material lies outside the smooth interior, so the fuse that joins them is a union of two
  intersecting multi-solid sets and is the most expensive single operation in either route at
  165 s. It also depends on `removeSplitter`, which raises `Bnd_Box is void` on the tail's
  fused wall. Nothing in this section changes.
- **The dilation is brute force** (IP-FC-116). §9.2's horizontal disc is built by fusing 48
  translated copies of each notch solid. It is correct, and it makes a rib solid of roughly 250
  faces where an offset section would give about 15, which every boolean downstream then
  carries. **The cost is downstream of it, not in it**: one instrumented tail build at `U` = 1
  spends 194 s on the surface fit, **72 s on the dilation** and **337 s fusing the dilated tools,
  cutting with them and checking the residue**, 609 s in all. An earlier version of this bullet
  read the 337 s as the dilation and called it more than half the build; it is 12 %. The 48-gon
  is also only an approximation of the disc — inscribed radius `t·cos(π/48)` = 0.99786 `t`, so
  0.0013 mm short at the facet midpoints, inside τ but not exact. **48 facets is a floor rather
  than a choice**, and that part is settled: the copies sit on a circle of radius `t`, so adjacent
  ones are `2·t·sin(π/N)` apart and their union is solid only while that is under the slab's
  in-plane thickness. The 0.1 mm axial cut needs `N > π/asin(w/2t)` = 37.6, so 38 minimum;
  `RIB_FACETS` = 24 built a wall 1332 mm³ light with two stations at 0.1035 mm **while the rib
  gaps still measured 1.3000 and 1.4000 mm exactly**. `dilated_notches` now derives the floor per
  tool and refuses to dilate below it.
- **Verified at `U` = 1 only** (IP-FC-117). Both kinds have been built repeatedly at `U` = 1
  and never at any other scale. **The run-to-run volume spread that used to be recorded here is
  withdrawn**: measured 2026-09-05, two builds of the tail agree to 0.006 mm³ — 2.6e-7 relative
  — when their volume is measured by refining a tessellation, and their surfaces agree to about
  a micron. The spread of up to 0.58 % previously reported was `Shape.Volume` misreporting these
  B-spline solids by 0.16 to 0.24 %, which is IP-FC-119. The builds reproduce.

  **The 0.006 mm³ understates the disagreement by two orders of magnitude, and that is now
  measured too.** A difference of volumes lets a surface that wanders out and back cancel
  itself. The symmetric difference adds both excursions, and between the same two builds it is
  **2.08 mm³** — 260 times the difference of totals, and still only 8.8e-5 of the part.

  **There is a tolerance for the soak to judge against**, decided 2026-09-06 under
  [OQ-ARCH-19](../architecture/freecad_migration.md): two builds are the same part when the
  symmetric difference over `A · 100U` is at most **1.0e-6** and no sampled surface gap exceeds
  **5.0e-5** of `100U`. The pair above measures 2.45e-7 and 1.28e-5 — both about four times
  inside. Where they disagree is measured as well: **65.5 % of the surface is bit-identical**,
  and 5 % of it carries 83 % of the difference, sitting at the **corners of the section**,
  radius 62–66 mm, spread along the whole length rather than at the ends or at any one rib.
  That reads as an adaptive fit diverging where curvature is highest while agreeing exactly on
  the flats — noise to be bounded, not a defect with an address.

  What remains is that **no scale but one has been tried**, and that is what would overturn the
  reading above: the same corners moving the same way at every build and growing with `U` would
  be a systematic bias rather than noise, and the two thresholds come from one pair of builds
  at `U` = 1. **`U` = 4 is where to expect
  trouble**: the wall is `n_p·w` = 0.6 mm at every `U`, because extrusion width is a property of
  the machine, so at `U` = 4 that same 0.6 mm wraps a part four times the size — proportionally
  the thinnest shell, and the most surface to hold inside a fixed 0.05 mm tolerance. The OML
  blank conditioning that makes the tail correct above `U` = 1 landed under IP-FC-12 and has
  never been exercised through the shell path.

- **A second scale has now been tried, and the tail has a floor rather than a single working
  point** (IP-FC-137, measured 2026-09-11 through 2026-09-12). At `U` = 0.5 the smooth interior
  fuses clean and then the rib cut
  leaves **5540.9 mm³** of rib inside the cavity against `RIB_RESIDUE`'s 0.01 — 554 000× over
  — so `cavity`'s single retry fires, and that retry returns a **null shape**. Reproduced four
  times from identical inputs, agreeing to four decimals. The nose builds clean at the same
  `U`, so this is the tail's 22-tool cut rather than the shared path. Two things follow for
  this document. **§9.6's rib residue did its job** — it is an identity, not a tolerance, and
  it refused a cavity that had a quarter of its rib material still inside rather than passing a
  wall that would have come apart. **But the repair path is not specified here and is not
  sound**: §4.2 says what the cut must achieve and says nothing about what to do when it does
  not, and the one retry that exists in the implementation can return a null shape, which
  reaches the caller as an *empty part* rather than as a failure, because `execute()` cannot
  raise through `recompute()`.

  **Settled 2026-09-12, by stating the domain rather than fixing the cut — nobody has a fix.**
  Walking the size axis (IP-FC-137) found the failure is not confined to `U` = 0.5 and does not
  shrink gracefully toward it: `U` = 0.6 built inconsistently from identical inputs (residue 0,
  681.8 and 4082.6 mm³ across three tries, one of the clean ones failing one step later instead,
  at the wall cut rather than the rib cut), and `U` = 0.7 failed *harder* than 0.5 — residue
  15982.45 mm³, agreeing to five figures across three builds, not noise. `U` = 0.75, the sweep's
  own second CSV row and the one value in the gap that mattered, also failed, three of three.
  `U` = 0.8, 0.9 and 1.0 each built cleanly every time tried. **The floor is `U` ≥ 0.8** — the
  lowest value measured to work, not a derived bound — enforced in `cowl_tail_shell.py`'s
  `emit`, the one function every caller of this kind goes through, before the expensive build
  ever starts. A `tail_shell` request under the floor is refused in under a second with a named
  reason, not built into a null shape forty minutes later. **The empty-part risk above is also
  closed, one level up**: the refusal is `PreconditionFailed`, which was going uncaught in
  `build_part.py`'s entry point and exiting 0 regardless — measured before the fix — so it is
  now caught there and reported the same way an invalid shape already was, which incidentally
  closes the identical gap for P1, P2 and P4. So `U` ≥ 0.8 is a fact about where this
  construction has been found to work, and the nose is untouched by any of it — confirmed clean
  at `U` = 0.5 in the same reproduction, so the floor lives beside the tail's own parameters and
  not in the shared tree.

  **The leading hypothesis for *why* was tested directly, 2026-09-12/13, and it is wrong —
  wrong in its own predicted direction.** If a fixed 0.6 mm rib dilation against a local
  curvature radius that shrinks with `U` were the mechanism, a *thicker* dilation should need
  proportionally *larger* `U` to clear the same ratio: doubling it should double the floor.
  Measured instead: `U` = 0.8 and `U` = 2.0 both built cleanly at double thickness (1.2 mm), on
  every attempt, including `U` = 0.8 — the exact case the hypothesis said would now break. A
  facet-count confound in that test (doubling the dilation also trips `dilated_notches`'s own
  comb-degeneracy floor, IP-FC-116, forcing more facets alongside the thickness) was ruled out
  rather than assumed away: `U` = 0.7 at the *original* 0.6 mm with the same extra facets and no
  thickness change still failed, three of three, the same magnitude as before. **So thickness
  itself is the lever, and it runs the other way from the hypothesis** — a thicker dilation makes
  the cut more robust, not less, which turns "does a thicker wall need a bigger `U`" into "does a
  thicker wall tolerate a smaller one." **Tested against `U` = 0.5, the worst case measured: it
  still fails, but the margin it fails by collapses.** Residue 354.09 mm³, agreeing to four
  decimals across three builds, against ~5540.9 mm³ at the original 0.6 mm — a 15.6× drop for a
  2× increase in dilation, steeper than linear, but still about 35 000× over the identity's
  tolerance. So the same thickness that was already enough at `U` = 0.8 is not enough at 0.5:
  the margin a given `t` buys is not uniform across `U`, which reads as 0.5 being a genuinely
  harder case rather than as thickness being beside the point. Whether a larger `t` than double
  would clear it, and what shape that falloff actually has with only two points on it, is
  untested. Either way, the ratio-to-curvature story is ruled out as stated, and no curvature
  has still ever been measured at any station.

- **The `U` = 4 trouble the IP-FC-117 bullet above predicted arrived, and it is a gap in §5's
  criterion, not in this section's own reasoning** (IP-FC-143, OQ-DES-CW21, 2026-09-23 through
  2026-09-25). Run across the full swept range, both cowl kinds, the finished wall reads thinner
  than τ at three of sixteen builds, all at the largest sizes tried: `tail_shell` `U` = 3.0 and
  4.0, `nose_cowl_shell` `U` = 4.0 — worst 0.150 mm, three times τ, at `tail_shell` `U` = 4.0. The
  same bias exists in miniature at every smaller `U` this construction has ever built, always at
  the tail's shallow-angle (30°) diagonal buttresses, just too small to cross τ until now. Five
  measurements pinned the mechanism precisely rather than leaving it a guess: the deviation is
  absent from the pre-rib fitted surface at the exact point the finished wall later reads thin,
  is not moved by `RIB_CUT_FUZZ` or by `RIB_FACETS`, and is not the cross-mirror rib overlap a
  different symptom of IP-FC-137 found elsewhere in this same construction — it is a real,
  bounded, deterministic consequence of the dilated rib tool meeting the fitted surface at a
  shallow angle, the same kind of case §4.2's erosion identity was never asked to cover. **Decided
  rather than worked around**: bounding `U` was rejected outright as a standing project policy (a
  `U` limit is only for an actual geometric constraint, which can only occur at the minimum `U`,
  and this project's floor there is already settled at IP-FC-137's `U` ≥ 0.8 above); widening τ
  for these stations was rejected for contradicting this section's own reasoning for keeping τ
  absolute. §5's new subsection records the fix decided instead: a second refinement pass,
  evaluated after the rib cut, with the same termination structure as steps 1-5. **Correction,
  2026-09-26: that pass has to run in `shell_solid()`, against `notched.cut(inside)`, not inside
  `cavity()` against `body` — `cavity()` never holds `notched`, the post-buttress-cut cell whose
  boundary is the finished wall's real exterior, only the un-notched cell steps 1-5 need.**
  **Correction, 2026-09-27 (OQ-DES-CW22): re-scanning the whole patch every round of that pass
  measured unaffordable (hours, not minutes) once real convergence was actually exercised — §5's
  subsection now also records a windowed re-scan sized from a direct measurement, combined with
  front-loading round 0 from the notch topology.** Built and verified 2026-09-27. **A residual gap
  found on that same verification is tracked separately, not by this pass's convergence** — its
  check predicts the finished wall by distance between two independently-sliced contours rather
  than by the real boolean cut, and that prediction does not always match what the real cut
  produces; see [cowl.md OQ-DES-CW23](cowl.md#open-questions). **A separate finding while
  investigating it, 2026-09-28 (OQ-DES-CW24): the real construction itself (`notched.cut(inside)`
  plus `mirror_across_cell`) is fragile at rib-crowded corners, confirmed live on the real,
  unperturbed build (clearances under a micron found there directly, not only under deliberate
  perturbation) rather than a synthetic-only concern** — a sub-0.1 mm difference in the candidate
  surface there can flip the result between normal, a caught failure, and an unflagged result two
  orders of magnitude off, and nothing in the pipeline today reports how close to that edge a
  successful build actually was. A build-time clearance-margin check is recommended, sampled across
  wherever the dilated rib tools' own `z`-spans overlap (not at notch edges alone -- the thinnest
  points measured were mostly elsewhere) against a threshold candidate of 0.01 mm; its sampling
  density and its behavior on violation are undesigned. **A genuine free-parameter screen,
  2026-09-30 (as opposed to the output-point nudge above), found no construction failure across 13
  cases perturbing real design parameters and algorithmic knobs, though at magnitudes larger than the
  wall itself, and found that seeding standoff (one candidate fix) does not help -- it surfaces a
  thinner minimum, not a safer one. A finer-magnitude follow-up at the row-nudge test's own ~0.01 mm
  scale found a second, uncharacterized near-tangency (9 nm clearance from a 0.01-degree
  `top_diag_angle` nudge, at a station no other test has flagged). **That specific lead was a
  measurement bug (a `_Polyline` wrapping across multiple disconnected wire loops) -- corrected,
  2026-10-01, the `z` ~ -192/-206 region does not rank among the whole tail's worst points at all.
  The corrected, whole-tail picture is less extreme but still real: minimum clearance 60 nm (6x
  `RIB_CUT_FUZZ`, not under it) at `z` = -134.498, with 15 genuine points (60 nm-4 um) scattered from
  `z` = -268.85 to `z` = -14.45, still wider than the one corner this section's root cause explains,
  and still ~19 hours to find by brute force.** See [cowl.md OQ-DES-CW24](cowl.md#open-questions).

## See also

- [cowl.md](cowl.md) — §1.2 the exterior's construction, §6.2 the requirement, §6.4 the two
  representations
- [freecad_migration.md](../architecture/freecad_migration.md) — OQ-ARCH-5 the method,
  OQ-ARCH-17 the precondition
- [freecad_migration.md](../implementation/freecad_migration.md) — IP-FC-17 implements this,
  IP-FC-52 and IP-FC-54 the offset failures
- [freecad_migration.md](../implementation/freecad_migration.md) — **IP-FC-17 findings**,
  the two defects §9.6 exists because of; IP-FC-115, IP-FC-116 and IP-FC-117, the three
  work items §10 names
