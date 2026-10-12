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

**Rib edges are interior knots, not patch boundaries — and that is the reverse of what this
section said before §4.2 moved to the three-dimensional identity.** While the surface was fitted
through *notched* contours, a rib edge was a crease in the thing being fitted, so splitting there
was the only way to keep §4.4's continuity requirement from smoothing away a feature the part
really had. The surface now follows the **un-notched** blank and the ribs are subtracted from the
finished cavity as solids, so the fitted surface has no crease at a rib edge to preserve: the
blank genuinely is smooth there, and demanding C² across it smooths away nothing. The crease the
part really has still arrives, as the boundary of a boolean between two well-formed solids, which
is where a crease belongs (§4.2). Splitting at every rib end is instead what made the tail 60
patches.

So the two readings of `feature_stations()` do opposite jobs, by which solid they are given:

| Called on | Returns | Used as |
| --- | --- | --- |
| `body` (un-notched blank) | the blank's own creases | **patch boundaries**, via `_patches` |
| `notches` (the dilated tools) | every ramp start, ramp end, cut-plane crossing | **interpolation rows** — the fit's seed is front-loaded with all of them ([OQ-DES-CW22](cowl.md#open-questions)), and §5's second pass scans finely around each |

**Measured 2026-10-11: the blank has no interior crease in any configuration built so far.** All
twelve walls in the soak corpus (§6.4) — both kinds, `U` = 0.5 through 4.0 — report `patch 1/1`,
so `_patches` returns a single span every time and the multi-patch machinery below it is dormant.
The notch-edge count over the same twelve is 4 for the nose and 19–26 for the tail. Everything
below about patch boundaries therefore describes a path no current build takes; it is kept because
a future cell with a genuine axial crease in its blank — a step, a second flange — would take it.

Matching the exterior's continuity class remains the actual requirement that G1/G2 is a statement
of ([OQ-ARCH-5](../architecture/freecad_migration.md#open-questions)). Under the 3-D identity the
exterior whose continuity the fit must match is the blank's, not the notched part's.

**Axial spacing has a floor, and the floor is a design parameter.** `MIN_INTERVAL` = 0.20 mm is
the smallest axial gap the construction will *create*, and it is exactly `t`/3 — three station
rows across the thickness of the wall being built. It is enforced in one place only: §5's
subdivision refuses to split an interval narrower than `2 · MIN_INTERVAL`, so refinement cannot
manufacture a tight pair.

**Two separations are enforced, and the one that matters is not.** `feature_stations()`
deduplicates its *own* output — successive notch edges closer than `max(Z_TOL, MIN_INTERVAL)` are
collapsed — and `_patches()` drops any patch shorter than `MIN_INTERVAL`. But the stations a patch
is actually seeded with are the union

    _seed(p_lo, p_hi)  ∪  {notch edges strictly inside the patch}

and **that union applies no separation filter at all.** The uniform seed stations and the notch
edges are independent sets, so a seed station can land arbitrarily close to a notch edge even
though neither set contains a close pair on its own. That is how the real `tail_shell` fit at
`U` = 3.0 ends up with a pair **0.0009 mm** apart — 220 times finer than the floor, and 670 times
finer than the wall it is building — from two stations that are each individually legitimate.

Two rows that close carry very nearly the same eroded contour, so the fit is asked to interpolate
a near-duplicate, and the axial pole track through them is near-degenerate (§4.4, §6.2).

**Decided 2026-10-04** ([OQ-DES-CW24](cowl.md#open-questions), alternative 2) and **built the same
day** ([IP-FC-144](../implementation/freecad_migration.md#work-items)): the per-patch union carries
a separation filter, and the floor is `station_floor(t)` = `max(t, MIN_INTERVAL)` — the wall, with
the old constant surviving as a hard under-floor for a wall thinner than it. Both end stations are
preserved exactly, because a patch boundary is a station the patches on either side must sample at
the same `z`; the filter displaces a crowding neighbour rather than the end.

It costs no accuracy, as measured and then confirmed on the rebuilt part: at `tail_shell`
`U` = 3.0 the station set goes 32 to 27 on the floor and refines to **30 rows at worst wall error
0.0496 mm**, against 36 rows at the same 0.0496 mm before — with the tightest remaining gap
0.6516 mm, and `z` = -60.0000 no longer present beside `z` = -60.0009.

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

**The identity is evaluated in three dimensions, and that is where the creases come from.** The
surface is fitted through `erode(A, t)` alone — the un-notched blank, which on these cowls is a
rounded rectangle with no crease anywhere in it — and `dilate(B, t)` is subtracted afterwards as a
solid. A rib's crease therefore arrives as the boundary of a boolean between two well-formed
solids, rather than as a feature a single periodic B-spline is asked to represent. The 2-D
predecessor did the latter and failed badly: it overshot at every rib corner, producing
self-intersecting wires, unorientable faces, and a fuse that landed **9× off its own volume** from
identical inputs. This is also why a rib edge is not a patch boundary (§4.1) — there is no crease
in the fitted surface to split at.

**That says where a crease comes from, not that the one the kernel returned is in the right
place**, and the two were conflated until 2026-10-11. §6.9 measures it.

### 4.3 Contour correspondence

A surface fitted through a stack of contours needs each contour parameterized **consistently**
with its neighbours, or the surface twists between stations. This is the classic loft failure
and it does not announce itself: the result is a valid, closed, plausible solid.

- Anchor the parameter origin to a **feature**, not to whatever the sectioning returned first.
  The rounded-rectangle sections ([OQ-DES-CW5](cowl.md#open-questions)) have four corner arcs;
  use one of them, consistently, and a fixed traversal direction.
- Distribute the remaining parameter by **arc-length fraction**, so a station with a notch and
  a station without still correspond.
- Where a notch is present at one station and absent at the next, the correspondence would not
  be well defined. **Under §4.2's three-dimensional identity the case does not arise**: the
  contours being fitted are the *un-notched* blank's, so no contour in the stack has a notch in
  it and every one of them corresponds to its neighbors by arc-length fraction. This bullet
  previously concluded that such stations are patch boundaries rather than points to interpolate
  through; they are now interpolation rows, by design (§4.1).

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

**As built, the continuity is C² in both directions, and the axial fit is global within a patch.**
`_fit` interpolates each eroded contour with `GeomAPI_Interpolate` and no tangent constraints,
giving a C² cubic row curve; it then interpolates each *pole track* across the patch's stations the
same way, giving a C² cubic axially. The patch surface is bicubic and C² throughout, and because
evaluating an interpolated pole track at its own parameter returns the original pole, the surface
passes through the input contours exactly.

**That makes one station's data a global constraint, not a local one.** A C² cubic interpolating
spline is a tridiagonal solve over all of a patch's stations, so moving one row changes every
coefficient in that patch. The influence decays geometrically along the knot sequence with
alternating sign — for uniform knots the ratio is 2 − √3 ≈ 0.268 per span, about 3.7× attenuation
per station. So on the knot sequence it is global in principle but short-ranged in practice: five
stations away, a 0.01 mm displacement is of order 10⁻⁵ mm.

**That figure describes the spline's own coefficients and does not bound the finished wall's
measured sensitivity — measured 2026-10-04, it understates it by three orders of magnitude.**
Displacing one row of the input contours and measuring the real cut wall 7.5 station intervals away
gives a gain of **0.408 mm per mm**, reproduced to three figures at δ = 0.001, 0.003 and 0.01 mm
(§7.1). That implies about 1.12× attenuation per station where the coefficient decay predicts 3.7×.
Whatever closes that gap — the cut geometry, the lids and side caps rebuilt from the changed
surface, or something else — is not the tridiagonal solve, and is not established. **So a
perturbation response reaching far down the part is not by itself evidence against the fit**, and an
earlier version of this paragraph which said it was has been withdrawn.

**Patch boundaries are hard stops.** Patches are split at the *body's* own creases, each is fit
separately, and adjacent patches are made to pass through their shared station exactly — which is
why `END_INSET` is applied only at the part's own two ends (§4.1). A perturbation inside one patch
cannot reach another patch's surface at all.

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

**As built the floor is also a blind spot, which is a defect.** Step 1 is skipped outright for any
interval already narrower than `2 · MIN_INTERVAL`: the midpoint is not taken, the wall is not
measured there, and nothing is reported. So an interval too short to subdivide is also an interval
this criterion never looks at.

**Both passes do it.** The pre-cut fit refinement skips before measuring the fitted wall, and the
post-cut scan skips before calling `_finished_wall_gap`, so the *finished* wall is not measured
across such an interval either and `worst_finished` never includes it. A near-duplicate pair is
therefore unmeasured at every stage.

Where §4.1's unfiltered station union has put two rows 0.0009 mm apart, that is simultaneously the
interval the C² system is worst conditioned across (§6.2) and the one place no convergence
measurement runs. Refusing to *subdivide* a short interval is correct — subdividing it is exactly
what would make things worse. Declining to *measure* it is not, and the two were conflated into a
single guard.

**Decided and built 2026-10-04** ([OQ-DES-CW24](cowl.md#open-questions) alternative 2,
[IP-FC-144](../implementation/freecad_migration.md#work-items)): the two behaviours are separated.
Both passes now compute the interval's divisibility and measure regardless; an interval that
exceeds τ but sits at the subdivision floor is **reported** rather than silently skipped. It is
reported and not raised, because promoting it to a refusal is a separate decision nobody has made.

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
failing to run long enough — §6.5 is the measurement, and it is larger and more structured than
this paragraph was first written to describe.** This pass's own
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

**Characterized further, and a fix attempted directly, 2026-09-27.** Inserting a station at the exact
point the real (not predicted) measurement says is worst — the most favorable case for closing the
gap by refinement — moved the real thickness there by only 3 % of the deficit, against roughly
fourteen times that effect on the *predicted* thickness for the same kind of insertion (the
measurement behind this section's own windowed re-scan sizing above). Station insertion is a weak
lever on the real result, and this pass has no other lever to pull.

**Where this pass actually stands, measured corpus-wide 2026-10-10 — §6.5.** The 2026-09-27 study
described the gap as signed both ways and present at every station at roughly ±0.01-0.04 mm, and
concluded it was pervasive noise rather than a targetable defect. **Measured properly, that was the
right order of magnitude:** this pass's prediction and the real wall differ by at most 0.0039 mm
across the six fully measured `tail_shell` walls, and at four of the six the prediction is
conservative. The quantity this pass converges is very nearly the quantity that matters.

An intermediate version of this paragraph, written earlier on 2026-10-10, reported instead that the
pass was "conservative below `U` = 3 and optimistic above it" by 0.1084 and 0.1743 mm, and that
tightening τ could not help. **Both are withdrawn.** The real side of that comparison was sampled at
a fixed 1 440 points a loop, which on a section whose perimeter scales with `U` is 1.45 mm apart at
`U` = 4 on a 0.6 mm wall; §6.6 is the measurement. There is no regime change, and τ has not been
ruled out as a lever — whether tightening it yields a compliant wall is being tested directly by
`freecad/tau_study.py`.

**A separate, more serious finding, 2026-09-28, re-reviewed and substantially corrected
2026-10-03.** Investigating whether the residual above reflects unreliable measurement, five
independent fresh builds confirmed the real reading is exactly reproducible (0.546556 mm to six
decimal places, every time). But the §6.2 probe — displacing one row of the fit's *input* contours
by a sub-0.1 mm amount — breaks `shell_solid()`'s construction at two stations, reproducibly.
**That failure is `notched.cut(inside)` returning the cell wall in more than one solid, and §7
carries its full current account**: both signatures, the figures, and what is and is not
established about it.

Two corrections belong here, because this subsection is where the errors were made.

**It is not a mirror-step failure.** Earlier versions attributed it to `mirror_across_cell`
("5 disconnected shells"); that was an artefact of the test harness, which called the mirror
directly and so skipped `shell_solid()`'s own earlier `len(wall.Solids)` check — the mirror was
reporting a wall that had already come apart one step before.

**The "rib crowding" explanation is withdrawn.** It rested on a ratio between two tools' distances
to the *interior surface*, which never compares the tools to one another; at the station it was
derived from, the three tools it called crowded have their own nearest points 87.7-176.9 mm apart
on a 300 mm part. Measured directly 2026-10-03, the real dilated tool set's largest pairwise
overlap is 382.5 mm³ — 0.59% of the smaller tool — against the ~40% that produced the pathological
topology in IP-FC-137's synthetic H3 test, and the three Side tools named as "the real crowding" do
not overlap each other at all. **§9.8's reading is the correct one: that mechanism is not present
in the real part.**

![The tools Metric B calls crowded, sectioned at the station it was derived from](img/cowl_rib_cut/cw24_crowding_section.png)

*The real blank and the real tools, sectioned at `z` = -283.9951 and seen down the axis. The black
outline is the half cell; each coloured bar is one tool's section, and the spheres are the nearest
points the ranking was read from. The three `Side` tools ranked as maximally crowded sit at
opposite ends of the top face.*

A mechanism is now established for one of the two stations and not the other: `z` = -60.0000 is the
near-duplicate station pair of §4.1, acting through the C² forcing term of §6.2. `z` = -294.1530 is
still unexplained, and three candidate predictors — absolute clearance, crowding ratio and row
spacing — have each been proposed and refuted by testing.

![The largest real pairwise tool overlap, rendered](img/cowl_rib_cut/cw24_overlap_context.png)

*The two real dilated tools with the largest mutual overlap — `Top1Safe` (blue) and a diagonal
(yellow) — with their intersection in red. They cross transversally, and the intersection is a
307 x 1.8 x 1.9 mm sliver: 382.5 mm³, 0.59% of the smaller tool. IP-FC-137's synthetic case paired
nearly-coincident slabs overlapping by about 40%, which is a different arrangement, not a smaller
amount of the same one.*

**What survives from the clearance surveys.** The corrected per-wire re-measurement — after the
`_Polyline` multi-loop bug that `_min_wire_distance` now guards against — found a minimum clearance
of 60 nm at `z` = -134.498, with 15 points from 60 nm to 4.1 um scattered across nearly the whole
length, recurring at a second `U` and on `nose_cowl_shell`'s octant, so it is a property of the
construction generally rather than one cowl or one `U`. A single rib binds at every one of those
points, and all three tested with the row-nudge protocol stayed stable across the full 0.001-0.1 mm
range. **What that in-plane clearance physically bounds is unverified**: whether its minimum lies on
a tool's cut floor, which bounds the wall, or on a flank, which bounds nothing, has never been
checked, and across four stations measured both ways it varied by a factor of 2.5 while the real
`wall_thickness()` varied by 4.9%.

**The two-metric check design is not closed.** Metric A ships opt-in and flag-only
(`CLEARANCE_MARGIN_MM` = 0.01 mm, for the reason in the next paragraph). Metric B is computed but
enforced nowhere, and on the 2026-10-03 evidence should be retired rather than given a cutoff: at
`z` = -60.0000 both metrics pass — Metric A 0.097097 mm, Metric B 5.950x — and the wall severs
anyway.

**The thin-wall threshold is 0.01 mm, not the coarser 0.1 mm print-accuracy figure first proposed.**
That 0.1 mm is a positional tolerance (where a feature sits); wall thickness is a different quantity,
and a single spiral-vase perimeter's thickness is exactly where a small absolute change can flip the
slicer's decision to extrude it at all. That reasoning is unaffected by the corrections above.

### The three convergences, and where the chain breaks

Three convergences run between a candidate surface and a verdict on the part, and **each one hands
off across a change of quantity**. Written out because the individual facts are recorded above and
in §6.1 but the chain they form is not, and most of the confusion about this construction has been
confusion about which link is which — including in
[OQ-DES-CW23](cowl.md#oq-des-cw23--cavitys-post-cut-check-predicts-the-finished-walls-thickness-rather-than-measuring-the-real-cut--withdrawn-2026-10-10-not-a-design-choice),
which was withdrawn once the links were measured separately. §6.4 and §6.5 carry those
measurements.

| stage | what it measures | criterion | does that quantity converge? |
| --- | --- | --- | --- |
| **Pass 1**, `_refine` | the *smooth* fitted surface against the true per-layer erosion, Hausdorff, before any rib | τ = 0.05 mm | **Yes.** Bisection to a floor; reaching the floor is reported, not accepted |
| **Pass 2**, the post-cut loop | a *prediction* of the finished wall's thinness: slice-to-slice distance between `notched` and the candidate, never the real boolean | τ = 0.05 mm | **Yes**, within `POST_CUT_ROUNDS` = 6 on all 28 soak builds, worst 0.0484 mm |
| **Acceptance**, `wall_thickness` | the *real* cut, mirrored wall: a nearest-point minimum from the inner contour to the outer | `WALL_TOL` = 0.01 mm | **No.** Still falling at 3840 inner samples at 17 of 24 stations; the check runs at `AROUND` = 240. **Superseded as the gate's measure by §6.4's C4**, which does converge |
| *(candidate)* area-based mean | (outer area − inner area) / mean ring length on the same section | — | **Yes**, to 1e-6 mm from 16000 area points — but a mean cannot see a local thin spot |

Four consequences follow, and they are what make this a design problem rather than a tuning one.

**τ is not `WALL_TOL`, and the gap between them is deliberate.** τ is what the two refinement
passes stop at; `WALL_TOL` is what the part is held to, five times tighter. A candidate can satisfy
both passes and still fail acceptance, by construction and not by error — "The tolerance, and why
it is absolute" above, and the two constants' own notes in `cowl_interior.py`, say why one may be
as loose as the construction's budget allows while the other is set by what the slicer does with a
thin perimeter.

**Pass 2's prediction tracks the real wall closely, and the hand-off is not where the chain
breaks.** §6.5 is the measurement, over every build the soak recorded rather than the 12 stations of
one. Across the six fully measured `tail_shell` walls the prediction differs from the real wall by at
most **0.0039 mm** — under half of `WALL_TOL`, under a tenth of τ — and at four of the six it is
conservative, reporting more thinness than is there. Station insertion is independently measured to
move the real wall by about 1/14 of what it moves the prediction, so this pass has little lever on
the part; it does not need one, because it is not where the error is.

**Two earlier readings of this consequence are superseded, in opposite directions.** The first,
from one build's 12 stations with the real side read by the non-converging nearest-point minimum,
called the gap pervasive measurement noise at a mean absolute 0.0121 mm. The second, 2026-10-10,
called it a regime change — zero below `U` = 3 and 0.11–0.17 mm above it — and concluded that no
tightening of τ could certify the part. **The second was the worse error:** its real side was
discretized at a fixed 1 440 samples a loop, which scales to 1.45 mm between samples at `U` = 4 on a
0.6 mm wall (§6.6). The first was closer to right. What is actually true is that the gap is small,
and that `TAU` remains an untested lever rather than a ruled-out one.

**The acceptance metric had no settled value to converge to, and now there is one.** `worst_low`
drifts one way — thinner — with sampling, so under it a reading over `WALL_TOL` did not show the
wall was that thin and a reading under it did not show compliance; `check_cowl_interior` prints
exactly that, reporting a failure as "`WALL_TOL` compliance is not demonstrated". §6.4 replaces it:
C4, the corner-excluded minimum, converges on a real section, is accurate against closed-form truth,
and is not blind at a corner. **It rescues the nose and not the tail.** Of the twelve distinct
walls, five meet `WALL_TOL` and all five are `nose_cowl_shell` at `U` ≤ 3; every `tail_shell`
configuration fails, reading 0.0134 to 0.0469 mm, one and a half to five times over, and so does the
nose at `U` = 4. At `tail_shell` `U` = 1.5 and `U` = 3.0 it reports *exactly* what the incumbent
does,
and since its samples are a subset of the incumbent's that equality means the incumbent's own worst
sample survived the corner exclusion — so the tail's thin spot is not at a corner and no
corner-based fix reaches it. On the nose the exclusion matters a great deal (§6.4).

The 16× disagreement once recorded at one station between the nearest-point minimum (0.0534 mm)
and the area mean (0.0033 mm) is a disagreement between two unsound measures, and neither figure
survives as a reading of that wall.

**Which figures in this document are settled, and which are not.** §6.4, §6.5 and §6.6 are
measured with the selected instrument at a sampling density refined until the reading stopped moving,
and they stand. [IP-FC-151](../implementation/freecad_migration.md#work-items) is superseded by
[wall_thickness_measure.md](../implementation/wall_thickness_measure.md).

**Two classes of figure elsewhere in this document do not stand.** Anything built on `worst_low`,
including §9.9's whole corpus table, is a reading from a measure that does not converge. And
**anything taken at a fixed sample count rather than a fixed spacing is wrong by a factor that grows
with `U`** — up to six at `U` = 4 — which is §6.6 and which withdrew two findings published earlier
on 2026-10-10. Where this document quotes a figure from either class it now says so in place.

**The nose is now judged, and it mostly passes.** Figures recorded before 2026-10-10 placed its
stations across a bounding box up to twice the part's length and reached only 5 to 9 of 12; on the
wall's real extent all six nose walls section at 12 of 12, and five of the six meet `WALL_TOL` with
margin. §6.7 carries that and what the nose/tail asymmetry implies about the mechanism.

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
| **The cavity closes to exactly one solid** (`cavity()`), and the mirror sews to one (`mirror_across_cell`, `_extend_across_cell`) | a rib that failed to bridge the erosion identity. §9.8 is why this is refused at any scale rather than accommodated |
| **The cell wall closes to exactly one solid** (`shell_solid()`, `len(wall.Solids) != 1`) | `notched.cut(inside)` returning the wall in pieces. This is a *separate* check from the cavity's, at a later step, and it is the one that catches a wall that came apart at the shell cut rather than at the rib cut |
| **Partition identity**: the cut and its complement re-add to the blank within `PARTITION_TOL` = 2.0e-3 | the cut losing or inventing material. Independent of the solid count — a wall can come apart with the partition intact, and the partition can collapse without the solid count being unusual |

The last three are **construction-integrity** checks: they do not ask whether the wall is in the
right *place*, only whether the construction produced a coherent solid at all. The solid-count and
partition checks are independent and both are needed — a wall can sever while cut and complement
still sum to the blank to 2.05e-05, and the partition can slip by 0.993 without the solid count
being unusual.

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

### 6.1 Measurement cautions

Fifteen ways a measurement of this geometry has misled this work, each one paid for:

- **A bounding box is not evidence of where material is.** A failed wall piece's box read
  `x` = -164.89 against the blank's -150.25, suggesting material outside the solid it was cut
  from; sampled every millimetre, no section lay outside the blank. Reading the same solid through
  two different FreeCAD calls can also give boxes that disagree by several millimetres.
- **`Shape.slice()` can return nothing at one exact plane.** The healthy wall returns no section at
  `z` = -141.0000 and a normal one at ±0.05 mm. A gap in a section sweep must be confirmed by
  volume before it is called a hole. **Met again on 2026-10-11, and the second time it nearly read
  as a defect**: a 298-station dense scan of `tail_shell` at `U` = 3.0 reported one `no_wall` at
  `z` = -293.98226487, and the kernel *agreed* — worthlessly, because with zero wires the nesting
  test and `Part.makeFace` are both answering "not an annulus" about the same empty input, so they
  cannot disagree. Re-probed at six offsets the wall returns a 2-loop annulus at every one, ±0.01,
  ±0.05 and ±0.20 mm, each with ~5 742 samples on a ~1 150 mm perimeter. **A cross-check between
  two measures of an empty input confirms nothing**; only a neighbouring plane does, which is what
  `locate.nearby_states` and `is_slice_artifact` now ask automatically. **It is deterministic and it
  is rare**, both measured when the scan was extended to the whole corpus the same day: that wall
  scanned twice, hours apart in separate processes, gave the identical `z` to the last printed digit
  with the identical six healthy neighbours, so this is a property of that plane against that
  geometry rather than an intermittent flake — and it is the only occurrence in **1 704** stations
  across all twelve distinct walls. The distinction matters for how far the re-probe can be trusted:
  an intermittent failure could in principle also strike a neighbour, a deterministic one cannot.
- **`distToShape()` returns a minimum.** It reads 0.0000 for any face that merely touches a solid
  at an edge, so it cannot decide whether a face lies *on* that solid. That needs the face sampled
  across its area.
- **The display mesher is not the geometry.** Redundant topology can make the viewport draw a solid
  several times its true size while `Shape.tessellate()`, `MeshPart.meshFromShape()` and STL export
  all return its correct extent — a display artefact, not an export defect.
- **`Face.Area` is unreliable on B-spline faces** (§9.6); use the wire signed area.
- **A station named by its printed value is not that station, and adding it to a station set
  manufactures a near-duplicate pair.** Stations here are notch edges carried at full double
  precision, and a probe that wants "the station at `z` = -283.9951" and unions that literal into
  the seed set does not select the existing station — it adds a second one 0.0000339 mm from the
  real edge at -283.9951338812. That is 28× tighter than the 0.0009433 mm pair §4.1's floor exists
  to remove, and it puts δ/h ≈ 885 into §6.2's forcing term at δ = 0.03 mm against 11.1 at the pair
  already established as causal. **Select a station by searching for the nearest existing one and
  print what was found**; never name one by a rounded literal.
- **A nearest-point minimum is not a converged wall thickness, and at `WALL_TOL` it is not a
  measurement at all.** `wall_thickness` samples the inner contour and takes each sample's distance
  to the nearest point of the outer one. Measured 2026-10-05 on `nose_cowl_shell` at `U` = 1, that
  minimum does not settle: at **17 of 24 stations it was still falling at 3840 samples**, drifting
  0.0015 to 0.0079 mm per doubling — for instance `z` = -43.5213 reading 0.5830, 0.5792, 0.5774,
  0.5661, 0.5606 as the count goes 240 → 3840. It is not noise and not discretization of the outer
  curve: the outer polyline is 0.0125 mm per segment, whose chord bias is under 1e-6 mm, and a
  remeasure of the worst station returns the identical value to ten decimals. The measure itself is
  the problem — a nearest-point distance at a **concave corner cuts across the corner rather than
  across the wall**, and this section has such a corner at every slot mouth, so denser sampling
  keeps landing nearer one. A minimum that falls with every doubling cannot be compared against a
  0.01 mm tolerance in either direction. **Measuring along the contour's own local normal does not
  fix it** — tried the same day, it oscillates instead of drifting, by up to 0.0139 mm per doubling,
  because the tangent estimate at a crease is itself unstable. What does converge is the
  **area-based mean**, (outer area − inner area) / mean ring length: 0.556253, 0.590421, 0.595922,
  0.596701, 0.596704, 0.596705, 0.596704 mm as the area discretization goes 200 → 64000, settled to
  1e-6 mm from 16000 on. Note the first of those: **`_wire_area`'s own default of 200 points is
  0.044 mm wrong**, 4.4× `WALL_TOL`, so any 0.01 mm work must pass an explicit count. Both kinds
  behave the same way — `tail_shell` at `U` = 1 also had 17 of 24 stations unsettled at 3840 samples,
  with its own worst reading 0.0555 mm at `z` = -30.8264 — so this is a property of the measure on
  this geometry and not of one part.
- **Ask the kernel before building an instrument — but only one of its four routes to these
  questions survives this geometry.** Everything above was built by hand, and each hand-built
  measure needed its own convergence study. OCC answers some of it topologically, with no sampling
  and no threshold. Measured 2026-10-05 on a 2464-face `tail_shell` wall:

  | route | result |
  | --- | --- |
  | `Part.makeFace(wires, 'Part::FaceMakerBullseye')` | **works, 0.6 s.** Resolves the section's wires into regions and reports one face with two wires for a continuous ring, several one-wire faces for a broken one. `Part::FaceMakerCheese` agrees exactly; `Part::FaceMakerSimple` does not resolve nesting and returns the two enclosed areas' sum, 150914 mm², instead of the 958.819 mm² between them |
  | `solid.common(planar_face)` | **unusable.** Would answer the same question, and did not finish in nine minutes |
  | `Edge.Continuity` | **the wrong quantity.** It reports the edge *curve's* own smoothness, not the continuity between the two faces across the join: a box's sharp creases, a filleted box's tangent joins and a cylinder's periodic seam all read `CN`. FreeCAD's Python API does not expose `BRep_Tool::Continuity(E, F1, F2)`, so §6's G1 requirement cannot be read off the built shape this way |
  | `Face.makeOffset2D(-d)` | **exact on clean geometry, unusable here.** On a 0.6 × 100 mm polygon ribbon the erosion is textbook — 1.9884 mm² at d = 0.290, 0.0000 at 0.300, `CADKernelError` at 0.310, the transition exactly at the half-width — and on the real section's convoluted B-spline boundary one call did not finish in six minutes |

  So the ring-continuity question is best asked of the kernel, and `Face.Area` on the resulting
  nested face is a better material area than a difference of two separately-integrated wire areas:
  958.819 mm² against 954.742 mm² by hand, 0.43 % apart, and the kernel's figure needs no
  discretization choice. **The morphological thickness measure, which was the standing candidate for
  a converged local thickness, is refuted on real geometry by the last row.**
- **A mean thickness from area is only trustworthy where the two loops are near-equal in length.**
  `area / mean(boundary)` reads 0.5993 mm at the reference station, where the loops are 1601.8 and
  1598.2 mm — 0.0007 mm from nominal, the best figure any measure here produces. At `z` = -25 on the
  same part it reads 0.4753 mm, and reads **identically on a healthy and a damaged wall**, so that
  is the estimator failing and not a defect: a convoluted boundary adds length without adding area
  and depresses the ratio. Use it where the section is a thin near-uniform ribbon, and nowhere else.
- **Twelve stations is too few to find this check's own failures, independently of the measure.**
  `STATIONS` = 12 is what `check_cowl_interior` and `soak_cowl_shell` sample. Re-run at 24 on
  `tail_shell` at `U` = 1, **three stations fail even the old `TAU` = 0.05 mm** — the 12-station
  default reports the same build `OK`. Whatever is decided about the tolerance and the measure, the
  station count is a separate coverage gap: a quantity that varies along the part is not bounded by
  twelve samples of it.
- **`Shape.tessellate(deflection)` does not re-mesh a shape it has already meshed, so a second
  convergence run on the same object converges on nothing.** FreeCAD caches a shape's
  triangulation. Measured 2026-10-06 on a cylinder: a *fresh* shape gives 500, 1 672 and 5 024
  facets at deflections 0.02, 0.005 and 0.001, and the **same** shape asked again gives 5 024 at
  all three — including when a coarser deflection is requested after a finer one.
  `solid_measure.converged_volume` walks the deflections coarse to fine on one shape, so its first
  run is sound: each request really is finer than what is cached. A second run on that shape
  compares identical volumes, declares convergence immediately, and reports `DEFLECTIONS[1]` — the
  *coarsest* comparison — as the deflection it converged at. With `tol` = 0 the same call raises
  `NotConverged` and then succeeds. The volume returned is still the finest mesh's and therefore
  right; it is the reported deflection, and any convergence *claim*, that is not. The production
  path is unaffected because `soak_cowl_shell.py` reads `mesh_volume` at one fixed deflection on a
  freshly built shape. **Measure a convergence on a shape that has not been tessellated before**,
  and treat a convergence report from a reused shape as unsound. Whether `solid_measure` should
  defeat the cache, and what that costs on a real cowl, is OQ-DES-CW27 in
  [cowl.md](cowl.md#open-questions).
- **A fixed sample count is not a fixed accuracy on a part that scales, and it silently became the
  largest error in this subsystem's measurements.** `unit_width` = `U` * 100, so a section's
  perimeter grows with `U` while the wall stays an absolute 0.6 mm. Discretizing a loop at a fixed
  `Number` therefore buys a circumferential spacing proportional to `U`: `check_cowl_interior`'s
  `AROUND` = 240 is 1.8 mm apart on a `tail_shell` at `U` = 1 and **8.7 mm at `U` = 4**, fourteen
  times the wall being measured, and the first corpus sweep's 1 440 samples were 0.30 mm and
  1.45 mm. Measured 2026-10-10 at `U` = 4: a station reading 0.2136 mm thin at 1 440 samples reads
  **0.00264 mm** at a fixed 0.125 mm spacing, and that wall's worst station falls from 0.2136 to
  0.0347 mm. **Index a reading by spacing in millimetres, never by sample count**, and refine the
  spacing until the reading settles before quoting it. §6.6 is the measurement and the two published
  findings it withdrew. `cowl_interior`'s own `check_samples` already does this correctly at
  `CHECK_ARC` = 0.20 mm; the things that measure its output did not.
- **A bounding box is not the part, and a station grid placed across one samples empty space.** This is the first caution above in a second guise, and it cost more: `z_extent` exists precisely because `Shape.BoundBox` is computed from the untrimmed B-spline geometry, and measured 2026-10-10 a `nose_cowl_shell` wall at `U` = 4 has a box of `z` -400 to -12 where the part spans -200 to -24 -- **twice its length**. A box-based grid found 5 of 12 stations on that wall; a grid on the real extent finds 12 of 12. Every nose figure recorded before that was measured at 5 to 9 stations and excluded from every verdict, which is why the nose went **unjudged for a day while being compliant**. The tail was never affected, its mask spanning the whole OML -- so the kind that fails the tolerance is the kind the box happens to fit, and nothing flagged the difference. **Place stations from a sectioning extent** (`corpus.sectioning_extent`), never from a box. §6.7 is the measurement. **Found a third time on 2026-10-11**, in `locate.dense_grid` — the one function whose whole purpose is a scan dense enough to find a break between the gate's stations, placing them across the box. On a nose wall at `U` = 4 that spends half the scan on empty space and classifies it `no_wall`, which is a *false positive* in the tool meant to find a broken ring. Three recurrences in one module is the measure of how natural the mistake is: `Shape.BoundBox` is the obvious call, it never fails, and it is wrong by 100 % on a real part. **The fix is confirmed on the wall that exposed it**: scanned later that day over its sectioning extent, that same `nose_cowl_shell` at `U` = 4 returns 174 stations and **not one** `no_wall`, where a box-placed grid would have put roughly half of some 390 stations outside the material and called every one of them a hole.
- **A point sampled from a tessellation is not on the face it came from, and a reconstruction of a
  surface is not that surface.** §6.9's check had to be wrong four times before it was right, and
  all four were the same mistake in different clothes — a point or a surface that *looked* like the
  one being asked about. Face **vertices** are shared with neighboring faces, so probing there
  classified 35 of a nose cavity's 60 faces as lying on more than one operand, and an end-lid edge
  22.5 mm from the nearest tool was reported as a rib crease. A facet **centroid** is on a chord,
  so it sits inside a curved face by up to the tessellation deflection — exact for a plane, 0.1 mm
  off a B-spline at the deflection first used, against a 1e-5 mm tolerance; that put **zero** of
  the same cavity's faces on the fitted surface. `Surface.projectPoint(Method='LowerDistance')`,
  and `parameter()` plus `value()` behind it, put the rib edges **2.411 mm** off a surface the
  kernel put them 6.9e-18 mm from — the interior surface is periodic in `u`, and a parameter solve
  returning a local minimum looks exactly like that. `Surface.toShape()` reproduced the same
  2.411 mm, rebuilding the surface over its own natural parameter range rather than the fit's.
  **Measure against the operand the kernel was actually handed, and snap a sampled point onto its
  face with `distToShape` before measuring from it.** None of the four raised anything.
- **A `distToShape` against a whole solid's faces answers a different question than one against the
  face you mean, and the whole-boundary answer is the reassuring one.** The same nose rib edges read
  6.9e-18 mm from `smooth.Faces` and 2.411 mm from the fitted B-spline alone, because they lie on a
  **side cap** — they are where the rib cut runs out to the cell boundary, not creases in the
  interior surface. Measuring against the whole boundary would have passed the check while
  measuring none of the 45 edges the question was about. **Name the face class you mean**: the
  fitted surface, its closing lids and caps, and the `SurfaceOfExtrusion` end-overrun walls are
  three different things on one operand's boundary.

### 6.2 Conditioning: the row-nudge probe, and what it can establish

A robustness probe rather than a correctness check, recorded here because the verification method
is itself a design decision.

**Procedure.** Build the surface normally. Take the converged stack of eroded contours — §4.2's
output, which is §4.4's *input* — scale one row radially by δ, refit through the modified stack,
and run the same cut production performs. The question it asks is whether the construction's output
is continuous in its own input: a δ well inside the error the fit already accepts (worst wall error
0.0496 mm, against δ = 0.01 mm) should not change the *topology* of the result.

**Its validity domain is narrow, and stating it is part of the method.** Displacing one row while
its neighbours stay fixed is not the same as a surface uniformly δ off — it is a one-station kink,
and its severity is δ *relative to the neighbouring row gap*, not δ itself. Against a 0.0009 mm
gap, δ = 0.01 mm asks the fitted surface for a local slope near 11:1 and the probe is manufacturing
the failure it then reports; against gaps of 0.2 mm and wider the ratio is 0.045 or less and the
probe is measuring what it claims to. **A result from this probe is uninterpretable without that
ratio quoted beside it.**

**Why the ratio and not the displacement: it is the forcing term of the C² system.** For a cubic
interpolating spline the junction equation at interior knot `i`, with interval lengths `h`, is

    h(i-1)·M(i-1) + 2·(h(i-1) + h(i))·M(i) + h(i)·M(i+1)
        = 6 · [ (y(i+1) - y(i)) / h(i)  -  (y(i) - y(i-1)) / h(i-1) ]

A displacement δ applied at station `i` enters the right-hand side as δ/h. At h = 0.0009 mm and
δ = 0.01 mm that term is ≈ 11, which is exactly the tabulated ratio — the ratio is not a heuristic
chosen to separate the cases, it is what the C² constraint actually sees. The second derivative the
fit must then carry scales as δ/h², of order 10⁴ mm⁻¹: the surface is being asked for a near-cusp.
**That is a statement about the station set, not about the cut**, which is why the `z` = -60.0000
result belongs to §4.1 and not to the boolean.

**No real build performs this operation**, so a failure it produces is evidence about conditioning,
not a prediction that a build will fail. The complementary test — varying genuine design inputs and
letting the fit reconverge, 21 cases — is reported separately and has never produced a construction
failure. **Whether the probe corresponds to anything a real build can do is not established**, and
it is the reason a failure it produces is not by itself grounds for a build-time check.

### 6.3 Rib-cut clearance: what the scan measures, and what it does not

`cavity()` can additionally run a **rib-cut clearance scan** (`clearance_margin_scan`, opt-in
through `clearance_check`, off by default because it costs on the order of an hour). At each
sampled station it reports the smallest in-plane distance between the fitted interior candidate's
own section and the nearest **dilated** buttress tool's section, and flags any station under
`CLEARANCE_MARGIN_MM` = 0.01 mm. It reports; it never fails a build.

**A figure from it has to pass two prior questions before it means anything, and the distance
itself answers neither.**

**(1) Is it a clearance at all?** The scan measures wire to wire, which cannot distinguish a tool
sitting just clear of the surface from one already cutting into it — both give a positive
boundary-to-boundary distance. So each tool section's own points are tested against the interior
candidate *solid*, giving three states rather than two:

| state | what the reported figure is |
| --- | --- |
| **clear** — no part of the tool's section is inside the surface | a real clearance |
| **crossing** — part in, part out | zero. The reported figure is the distance from the sampled station to a geometric crossing: a property of where the sampling landed |
| **engulfed** — the whole section is inside the surface | zero, and the cut is removing material along the tool's entire section |

**A dilated tool is supposed to cross.** §4.2's identity forms the rib by removing `dilate(B, t)`
from the cavity, so a tool that reaches the wall band at all must cross the surface somewhere along
its run, and every crossing is a station where this metric reads near zero by construction.

**(2) If it is a clearance, does it bound the wall?** A buttress tool is a slab — a six-sided or
rectangular profile extruded through `buttress_cut_thickness` — and only part of its boundary bounds
the finished wall:

| Face | What it bounds |
| --- | --- |
| **cheek** — the two broad faces, `buttress_cut_thickness` apart | the slit's own side walls, and nothing about the wall's thickness. The material beyond a cheek is the rib, whose thickness the dilation sets at `t` by construction rather than by any distance measured here |
| **floor** — the innermost reach of the cut, including both overhang ramps | the wall's radial thickness. The only part of the tool whose distance to the interior surface says anything about the wall |
| **end** — the two axial caps | the ends of the slit's run |
| **outer** — the profile's far edge | nothing. It sits outside the blank entirely and cuts no material |

A floor bounds wall only **where it lies inside the blank**, which is not everywhere: the protected
core (`cowl_tree.core`, the region the buttress cuts may not enter) splits each long diagonal tool's
floor into an 8.4 mm² piece inside the blank and a 1.4 mm² piece outside it, and leaves sub-0.02 mm²
slivers on three of the side tools whose normals read as floor while sitting outside the part
entirely. Both are genuine faces of the real tool; neither bounds any wall where it sits. So this is
tested per contact rather than inferred from the role.

There is a third possibility, and measurement says it is the common one: **the minimum lands on no
face's own surface at all.** The dilated boundary reproduces each face's offset over that face's own
extent, but near an edge of the original slab it is whatever the 48 translated copies bridge the
corner with — so a contact there is not a distance to either adjacent face, and which of the two
happens to be nearest is an accident of the bridge rather than a fact about the wall.

`tool_face_roles` labels the faces from the geometry rather than from the construction — the slab's
own normal gives the two cheeks, and the direction from the tool toward the part's `z` axis
separates floor from far — and `clearance_face_scan` locates each reported minimum, attributes it to
a face of the **undilated** tool, and answers all three questions above. **The attribution is
self-checking, and that is what distinguishes a face contact from an edge contact.** Because §9.2's
structuring element is a horizontal disc, a face with outward normal `n` moves out by exactly
`t·hypot(n.x, n.y)`; a contact on that face's own dilated image reproduces the figure, and one on a
bridging facet does not. Measured on the nose, cheek contacts reproduce it exactly — 0.6000 against
0.6000 — while the contacts the role test called floor read 0.5490 to 0.5524 against a predicted
0.5901, which is how the edge contacts were found. `FACE_IMAGE_TOL` = 1 % of `t` is the threshold,
coarse against the section discretisation and twenty times finer than the 0.04 mm discrepancies an
edge contact actually produces.

**`Face.Orientation` cannot be used to find a face's outward normal on these tools.** Measured
2026-10-04 on `tail_shell`'s eleven: every slab reports *both* of its cheeks as `Forward`, so
flipping the surface normal on that flag returns the same direction for two opposite faces of one
solid — impossible, and it labelled the cut floor as the far face on all eleven. The outward
direction is read by stepping off the face and asking the solid which side the point is on, with the
step kept well inside `buttress_cut_thickness` so it cannot cross to the opposite cheek.

**Measured 2026-10-04 on both kinds at `U` = 1. Of the 15 stations the scan flags under 0.01 mm on
each, not one is a distance to anything that bounds the finished wall.**

| | `nose_cowl_shell` | `tail_shell` |
| --- | --- | --- |
| tools | 1 | 11 |
| worst figure reported | 0.000081 mm at `z` = -36.9470 | 0.000047 mm at `z` = -78.9869 |
| **land on a cut floor** | **0** | **0** |
| land on a cheek | 7 | 11 |
| land on no face's own dilated surface | 8 | 4 |
| **crossing** (no clearance exists) | **14** | **14** |
| **clear** (a real clearance) | 1 | **0** |
| **engulfed** (no clearance exists) | 0 | 1 |

- **Zero land on a cut floor, on either kind.** The cheek contacts bound the rib, not the wall. The
  others have a floor as their nearest face but an offset that disagrees with that floor's own
  dilated image — 0.5490 to 0.5524 mm against 0.5901 on the nose, 0.5213 to 0.5595 against 0.5560
  and 0.6000 on the tail — so the contact is on the dilation's treatment of the floor-to-cheek
  corner and not on the floor itself.
- **The tail has no genuine clearance at all among the fifteen.** Its one non-crossing station,
  `z` = -83.7372, is `engulfed`: 100 % of the tool's section lies inside the surface. The nose's one
  non-crossing station, `z` = -8.0479 at 0.000611 mm, is the only real clearance measured on either
  kind, and even that one is not a floor contact.
- **What those contacts sit on is not established.** The offsets match neither the adjacent faces'
  images nor an arc of radius `t` about the shared edge, which would read 0.6000, so the simple
  corner-arc account of the 48-gon's envelope does not fit them either. What the measurement
  establishes is the negative: a contact whose offset disagrees with its nearest face's predicted
  image is not on that face. Identifying the surface they *are* on needs the dilated tool's own face
  carrying each contact, which has not been recorded.
- On the nose the flagged stations arrive in pairs about 0.027 mm apart with opposite gap-direction
  sign — `z` = -34.5506/-34.5774, -39.3934/-39.3665, -27.5384/-27.5115, -36.9470/-36.9702 — which is
  the refinement pass bracketing one crossing from both sides rather than finding four thin places.
- **The figures are not reproducible between builds at the same station.** Two `tail_shell` builds
  at `U` = 1, measured at the identical 15 stations, give 0.000068 and 0.000108 mm at
  `z` = -66.1661 — 59 % apart — and 0.000282 against 0.000352 mm at `z` = -96.3180. The
  non-reproducibility previously attributed to Metric B's own defect is present in Metric A too, and
  follows from the same cause: near a crossing the figure is set by how close the station happens to
  land, which a rebuilt surface moves.

**Eight of the fifteen figures are smaller than the dilation's own approximation error.** §10 records
that the 48-gon is inscribed in the disc at `t·cos(π/48)` = 0.99786 `t`, so the dilated boundary
falls 0.0013 mm short of the true offset at each facet midpoint. The reported minima run from
0.000081 mm to 0.006470 mm, and the first eight are below that 0.0013 mm: **the scan is resolving
distances finer than the faceting of the tool it measures against**, which is independent of both
questions above and true of the figures that pass them.

**One caution on the containment figure itself.** It is tested with a 1e-3 mm tolerance and boundary
points counted as inside, so a station reading a few percent inside is at or very near the tangency
rather than deep past it. That does not change the reading — at or near a crossing there is still no
clearance to measure — but a `fraction_inside` of 0.8 % is not a 0.8 % bite.

**Not measured.** The single worst clearance on record, 60 nm at `z` = -134.498, came from a
`tail_shell` build above `U` = 1 and is not re-measured here. The crossing mechanism is a property of
§4.2's identity rather than of scale, so there is no reason to expect it to differ there — but that
is an expectation, not a measurement.

Whether the metric is kept at all is [OQ-DES-CW25](cowl.md#open-questions), and §10 carries what
remains unestablished about it.

### 6.4 Which measure reads the wall, and what it says the wall is

This section is the artifact of
[wall_thickness_measure.md](../implementation/wall_thickness_measure.md): the instrument the
acceptance gate should use, chosen against requirements fixed before any candidate ran, and what
that instrument then says about the 28 walls the 2026-10-06 soak saved.

**Why a screening was needed.** Every measure in this subsystem had been judged by whether it agreed
with itself under refinement, and none by whether it agreed with a known answer. The incumbent —
`check_cowl_interior.wall_thickness`'s `worst_low`, a nearest-point minimum — does not converge: at
a concave corner the nearest-point distance cuts *across* the corner rather than through the wall,
so denser sampling keeps finding a shorter path. It was still falling at 3 840 samples at 17 of 24
stations while the gate samples 240. So no thinness figure this project had recorded was a settled
number, and §6.1's own cautions could not say which way the error ran.

**The five requirements, derived rather than chosen.** Each follows from `WALL_TOL` = 0.01 mm or from
how a single-perimeter spiral-vase wall fails, so they are not matters of taste. The cowl wall is
`cowl_n_perimeters * extrusion_width` = 1 × 0.6 mm — **one** perimeter — and the slicer drops it or
keeps it at a point.

| | requirement | threshold | why that threshold |
| --- | --- | --- | --- |
| G1 | **Local** — sees a thin patch one extrusion width long | ≥ 80 % of the patch's true depth | A patch shorter than one extrusion width is below what the path planner resolves; one that long must be seen. This is the requirement the converged area mean fails. |
| G2 | **Convergent** on a real saved section | step ≤ 0.001 mm between the two finest levels, **and** each step ≤ 0.6× the one before | A tenth of `WALL_TOL`, so the instrument's own residual cannot be confused with the quantity. Contraction is required separately because a measure drifting 0.0009 mm per doubling in small, non-growing steps otherwise passes. |
| G3 | **Accurate against closed-form truth** | within 0.001 mm on a uniform tube | Convergence shows a measure settles, not that it settles on the right number. The area mean reading 0.4753 mm where the wall is 0.6 mm is this project's own example. |
| G4 | **Discriminating** | patch depth to 0.002 mm, located to 2 mm | The converse of G1. The area mean reads identically on a healthy and a damaged wall. |
| G5 | **Affordable** | ≤ 60 s for 12 stations of the largest wall | The gate runs in the build and in the suite. `Face.makeOffset2D` on a real section did not finish in six minutes for one call, which is what closed that route. |

**G2 has to be screened on a real section, and that was a defect in the first design of this
screening.** Concentric circular boundaries make a nearest-point distance exactly radial and exactly
equal to the wall, so no diagonal shortcut across a corner exists to be found. Screening convergence
on a fixture passes the very measure being replaced. The fixtures remain the authority for G1, G3 and
G4, which need closed-form truth a real wall cannot give.

**The screening.** G2 on `nose_cowl_shell` at `U` = 1, `z` = −44.8421; G1/G3/G4 on the fixtures.

| candidate | G1 | G2 | G3 | G4 | G5 | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| C0 nearest-point minimum (incumbent) | pass 1.000 | **fail 0.019808** | pass 0.000006 | pass 0.000006 | pass 16.9 s | rejected on G2 |
| C1 inscribed circle | — | fail 0.021283 | fail 0.312292 | — | pass 25.3 s | **untested, not refuted** — see below |
| C2 windowed normal | pass 1.000 | **fail 0.006784** | **fail 0.028952** | pass 0.000006 | pass 13.6 s | rejected on G2, G3 |
| C3 polygon erosion | — | n/a | — | n/a | **9.5 s a station** | rejected on G5 — ≈114 s for 12 stations |
| C4 corner-excluded minimum | pass 1.000 | pass 0.000425 | pass 0.000006 | pass 0.000006 | pass 13.6 s | **passes all five** |

C0's rejection is the screening's own control: it passes every synthetic requirement cleanly — locality
1.000041, accuracy 0.000006 mm, convergence 0.000018 mm contracting about 4× a doubling — and fails
on the real section, running 0.4735 → 0.5921 → 0.5873 → 0.5675 → 0.5632 while its *median* moves
0.000027 mm. The quantity that is unstable is the minimum, not the wall.

C1 is recorded as **untested rather than refuted**, because reporting "the inscribed circle does not
work" from this run would be false. Its first implementation aimed the normal at the outer loop's
centroid, which on an annulus is the axis, so it reported ≈0 everywhere. Fixed, its G2 residual
(0.021283 mm) is within 14 % of its own walk discretization (0.018750 mm), fixed at 33 steps and so
unable to refine when the sampling does — the measure cannot converge below its own step size. And
the formulation degenerates: along a normal on locally flat wall, `max min(t, gap − t)` peaks at
`gap`/2, so what it returns is the ray distance and the measure reduces to C2. A genuine
inscribed-circle measure is a distance transform or a medial axis, which is different machinery and
is not implemented. If C4 is ever disqualified, that is the route to build next.

C2 is worth keeping on the record as a **directional confirmation**: its deltas contract
(0.058572 → 0.025239 → 0.006784) where the incumbent's do not, so widening the tangent window does
address the instability it was aimed at. It buys partial progress and not an instrument.

**C4 was not adopted on the screening alone, because passing it was ambiguous.** Dropping samples
within 0.3 mm of a concave corner makes the real section read exactly nominal — which is either the
answer (the corners were the artefact) or exactly the failure this screening predicted in writing:
*excluding the corners removes the places a wall is thinnest.* Nothing in the screening distinguishes
those, because every fixture puts its thin patch on smooth wall. So a disqualifying converse was
added: a 0.15 mm patch one extrusion width wide placed **at** the re-entrant corner a rib leaves in
the bore, held to the same 80 % G1 asks on smooth wall. **C4 reports 100 % of that defect's depth**,
from 2 819 surviving samples of 2 880; the exclusion discards 61. The incumbent is the control, since
it excludes nothing and a universal pass would otherwise be unreadable.

Two limits of the selection, stated rather than implied. *How* C4 sees a defect centred on its own
blind spot is not traced — a surviving sample just outside the exclusion zone can reach the recessed
surface diagonally, the same cutting-across mechanism that makes the incumbent non-convergent, here
landing on about the right answer because the thinning is real. That it works is measured; why it
works is not. And a defect **narrower** than one extrusion width, lying wholly inside the exclusion
zone with no diagonal access, is untested — and out of scope by G1's own definition.

**The first corpus run's figures are withdrawn, and §6.6 is why.** They were taken at a fixed 1 440
samples a loop, which is a sample *count*, so the circumferential spacing it bought was proportional
to the section's perimeter and therefore to `U`. Re-measured at a fixed 0.125 mm spacing,
`tail_shell` at `U` = 4 reads 0.0347 mm where that run reported 0.2136 mm, and at its own worst
station the reading falls from 0.2136 to **0.00264 mm**. The withdrawn figures were:

| | incumbent C0 | selected C4 |
| --- | --- | --- |
| walls measured at all 12 stations | 14 | 14 |
| of those, meeting `WALL_TOL` = 0.01 mm | 0 | 0 |
| worst, **superseded** | `tail_shell` `U` = 4.0 at 0.2765 mm | `tail_shell` `U` = 4.0 at 0.2136 mm |

**What survives that correction, and what does not.** The screening above stands: it compared
candidates against each other and against closed-form truth at one `U`, where the sampling was
adequate, and C4 is still the selected measure. What does not stand is any *absolute* reading taken
at a fixed sample count on a large-`U` wall, and the corrected figures are in §6.6.

**One claim in particular was wrong, and it is the third time this question has turned over.** This
section previously said "the thin readings were not mostly instrument artefact," against three
earlier hints that they were. **At large `U` they mostly were.** The honest statement is that the
answer depends on `U` because the instrument's own spacing depended on `U`: at `tail_shell` `U` = 1
the published 0.0282 mm becomes 0.0286 mm properly sampled and nothing changes, while at `U` = 4 the
0.2136 mm becomes 0.0347 mm and 84 % of it was the instrument. A figure quoted from that run cannot
be read without knowing which end of the range it came from, which is why `sweep.sweep` now records
its own sampling in every row.

**The nose walls were long unjudged, and the reason was a bad station grid rather than anything
about the nose.** They sectioned at only 5 to 9 of 12 stations, which excluded every one of them from
every verdict. That was blamed here on the corpus saving the wall while the gate places stations from
the *body*'s z extent -- a real difference, but not this one. The actual cause is that the grid came
from `Shape.BoundBox`, which on a nose wall is up to **twice the part's length**; placed across the
wall's *real* extent instead, all six nose walls section at 12 of 12. **Measured properly, five of
the six meet `WALL_TOL` with margin** -- §6.7 has the figures and what they imply about where the
defect lives. `soak_cowl_shell` also records the bounds it used (IP-WTM-18), which remains the way to
reproduce the gate's own stations exactly.

**A "`U` break" read off those figures is withdrawn too.** This section previously reported that the
nose showed the same rise with `U` that the tail did, and took the agreement between the two kinds as
evidence that the break was a property of the construction. Both columns came from the same
fixed-count sampling, so the rise with `U` is the instrument's and the agreement between kinds is
what two readings sharing one artefact look like. §6.6 has what is left of it.

**What the corrected sweep does show about the corners is a clean split between the two kinds.**
C4 differs from the incumbent only by discarding samples within 0.3 mm of a concave corner, so it
takes its minimum over a subset of the same distances and can never report more thinness. The size
of that difference says where the corner artefact lives:

| | incumbent C0 | selected C4 | difference |
| --- | --- | --- | --- |
| `nose_cowl_shell`, `U` = 0.5 to 4.0 | 0.0294 – 0.0380 mm | **0.0011 – 0.0140 mm** | 0.015 – 0.037 mm |
| `tail_shell`, `U` = 0.5 to 4.0 | 0.0366 – 0.0469 mm | 0.0134 – 0.0469 mm | 0.000 – 0.023 mm |

**On the nose the incumbent's reading is mostly corner artefact; on the tail it is not.** At several
tail stations the two agree *exactly*, and because C4's samples are a subset of C0's, equality means
C0's own worst sample survived the exclusion — the thin spot there is not at a concave corner at all,
so no corner-based fix can reach it. Five of the six nose walls read inside `WALL_TOL` under C4,
which is why judging the nose on a complete station grid (IP-WTM-21) now matters: on the stations
that do section, the nose may already be compliant.

### 6.5 Pass 2's prediction against the real wall

§5's "three convergences" table states that pass 2 converges on a *prediction* of the finished wall
rather than on the wall. This section measures how far that prediction is from the part.

**Both sides are on disk, so this costs no build.** Pass 2's own final figure is printed per build by
`cavity()` as `worst finished wall error` — `worst_finished` from the last, passing round — so a
build that returns a solid carries pass 2's guarantee that its predicted thinness is at most
`TAU` = 0.05 mm everywhere it scanned. The real side is §6.6's sweep. The join lives in
`wall_measure.prediction`.

**The comparison is one-sided, because the two sides are maxima over different grids.** Pass 2 scans
142 to 529 points a build, so its maximum is close to the whole wall's true worst; a 12-station sweep
gives a *lower bound* on the real worst. That asymmetry can only hide real thinness, never invent it,
so "the real wall is thinner somewhere than pass 2 predicted anywhere" is sound while the reverse is
not, and the shortfall is clamped at zero rather than reported signed. These are not per-station gaps.

**This section previously reported a regime change at `U` ≥ 3, and it is withdrawn.** It had pass 2
optimistic by 0.11 to 0.17 mm above `U` = 2, from a real side read at a fixed 1 440 samples a loop.
§6.6 shows that sampling is the dominant error at large `U`. Re-measured at a fixed 0.125 mm spacing:

| build | pass 2 predicted | real, refined | shortfall | rounds |
| --- | --- | --- | --- | --- |
| `tail_shell` `U` = 1.0 | 0.0481 | 0.0286 | none | 0 |
| `tail_shell` `U` = 3.0 | 0.0430 | 0.0469 | 0.0039 | 5 |
| `tail_shell` `U` = 4.0 | 0.0393 | 0.0347 | none | 2 |

**So pass 2's prediction is sound, and the withdrawn finding was measuring the instrument.** The
largest shortfall left is 0.0039 mm at `U` = 3.0 — under a tenth of pass 2's own `TAU` and under half of
`WALL_TOL`. At `U` = 1 and `U` = 4 the prediction is conservative, reporting more thinness than is
there. The claim that "no tightening of `TAU` can certify this part", which rested on the withdrawn
numbers, does not hold: pass 2 is tracking the part closely.

**What that leaves is a much simpler statement, and an actionable one.** Properly sampled, every
`tail_shell` wall's worst reading sits between 0.028 and 0.048 mm — above `WALL_TOL` = 0.01 mm by
three to five times, consistently, at every `U`. Pass 2 stops at `TAU` = 0.05 mm, and the walls come
out just inside it. **The wall is about as thin as pass 2's criterion permits**, which is what a
binding constraint looks like rather than what a construction defect looks like. The chain §5
describes is not broken at the hand-off; it is converging to a criterion five times looser than the
part's tolerance, exactly as `TAU`'s own note says it does by design.

**What is not established, and how it is being settled.** Whether tightening `TAU` toward
`WALL_TOL` actually produces a compliant wall is unmeasured. `TAU` is what pass 1 and pass 2 both
stop at, so tightening it adds fit rows and re-cut rounds to every build, and the `U` = 3.0 build
already spent 5 of its 6 allowed rounds. **That is a measurement, not a design choice, and it is being taken.** `freecad/tau_study.py` builds one part at several `TAU` and measures the resulting wall, the fit rows and the rounds spent, so the three possible answers are all readable off the same run: the wall gets thinner in proportion and `TAU` is the lever; or the build raises `Unconverged` because pass 2 cannot reach the criterion inside `POST_CUT_ROUNDS` = 6, which the `U` = 3.0 build makes a live possibility at 5 of 6 already; or the wall does not improve at all, which refutes the reading above and sends the search back to the mechanism. Cost is an output of that test rather than a reason to defer it.

#### What was established about the mechanism at `tail_shell` `U` = 3.0

Carried here from the open question this measurement closed, because these are findings about the
construction and they would otherwise be lost. All concern the single worst station of one
`tail_shell` `U` = 3.0 build, `z` = −217.726 mm.

**Why pass 2 predicts instead of measuring.** Pass 2 slices `notched` and the candidate at each
station and measures contour to contour; it never performs `shell_solid()`'s real
`notched.cut(inside)`. That was deliberate. Cutting a second, independent copy of the candidate
every round repeats the "two shapes each independently built, then a boolean between them" mistake
`shell_solid()`'s own docstring records three instances of, and a NURBS-solid boolean at this scale
is itself unreliable enough that the docstring documents two *differently shaped* results
(23 745.581 mm³ in one solid against 21 995 mm³ in five) from two surfaces that both measured inside
tolerance beforehand. The real check also cost 53–54 s a round on top of the round's existing
118–150 s refit-and-cut.

**The discrepancy is complete at round 0.** A *round-0 candidate* is one pass 1 has fully converged
and pass 2 has not yet changed — zero insertions, zero re-cuts. On such a candidate, pass 2's own
distance check read 0.5851 mm (0.0149 mm thin, comfortably inside τ and nothing it would act on),
while replaying the real downstream pipeline — `_extend_across_cell`, `notched.cut(inside)`,
`mirror_across_cell` — and measuring the result read 0.5466 mm, thin by 0.0534 mm. That matched the
final reading of a build that ran all six rounds (0.0534 mm) and the first historical reading of the
whole investigation (0.0531 mm). Since the discrepancy is fully present before a single station is
inserted, the windowed re-scan cannot explain it and cannot close it by tuning.

**It is reproducible to six decimals, and ordinary in its sensitivity.** Five independent, fresh,
identically parametrized builds all read that station's real thickness as exactly 0.546556 mm. A
small absolute perturbation applied 22 mm away, at an ordinary non-notch-edge row, produced a clean
linear response at every magnitude tested. The residual at this station is bounded sensitivity, not
instability. Instability does exist in this construction, but specifically at notch-tool-edge
stations, which this one is not — [OQ-DES-CW24](cowl.md#open-questions).

**One hypothesis was tested and refuted, recorded so the wrong turn is not repeated.** The
hypothesis was that `finished_outer_at`'s exclusion of every point within `FINISHED_PLANE_TOL`
= 0.5 mm of a cell-boundary/mirror plane — needed to strip the flat construction face the cell was
cut from, or the check reads a spurious near-zero gap — was also discarding a real defect near that
plane. The real wall's own worst point, located explicitly on the finished, mirrored wall, sits at
`x` = 134.319, `y` = 78.688 mm: 78.688 mm from the tail's one cell-boundary plane (`y` = 0), thirty
times `FINISHED_PLANE_TOL`. No plausible tolerance change would have included or excluded a point
that far away. Refuted by measurement, not merely unconfirmed. That the worst point lies on the same
side of the cell as the un-mirrored original geometry also makes the mirror step an unlikely
contributor.

**Guiding insertion by the real cut was tested directly and does not work.** One station was inserted
at the exact bisected midpoint the existing algorithm would choose, but selected using the *real*
boolean-cut measurement rather than the prediction — the most favourable case, since the insertion is
informed by the real defect rather than guessed. The real thickness moved from 0.5466 to 0.5483 mm:
**+0.0017 mm**, closing 3 % of the deficit. The same insertion moves the *predicted* thickness by
−0.023 to −0.024 mm at the same distance, about fourteen times more. Station insertion is strongly
coupled to the prediction and weakly coupled to the part, which is why this item's history shows the
predicted reading moving substantially (0.0083 mm at an early wrong-reference implementation, to
0.0430 mm after six rounds against the right one) while the real reading barely moved at all across
the entire investigation (0.0531 to 0.0534 mm). Tightening the candidate surface's own resolution
relies on the same mechanism and inherits the same weak coupling.

**One figure above is superseded as a reading of the wall.** The 0.0534 mm is a nearest-point
minimum at 240 samples, from a measure since shown not to converge. §6.4's selected measure reads
that wall's worst at 0.1514 mm on the corpus's own grid. What the round-0 finding establishes is not
the size of the deficit but that prediction and reality part company before pass 2 acts at all —
and that conclusion is unaffected, since both figures exceed τ while the prediction stayed inside it.

---

### 6.6 Sampling density: a fixed sample count on a part that scales

**The cowl scales with `U` and its wall does not.** `unit_width` = `U` * 100, and every length on a
cowl's parameter sheet is a fraction of it except two: `cowl_n_perimeters` and `extrusion_width` are
absolute, because a nozzle does not scale with an airframe. Their product is the wall, 0.6 mm at
every `U`. So a `tail_shell` section's perimeter runs from about 430 mm at `U` = 1 to 2 088 mm at
`U` = 4 while the quantity measured across it stays fixed.

**Every measurement of that wall fixed the sample count, so the spacing scaled with `U`.** The
realized circumferential spacing, on the station this was measured at:

| | section perimeter | gate inner, `AROUND` = 240 | gate outer, 8x | first corpus sweep, 1 440 |
| --- | --- | --- | --- | --- |
| `tail_shell` `U` = 1 | 428.3 mm | 1.785 mm | 0.223 mm | 0.297 mm |
| `tail_shell` `U` = 4 | 2 088.4 mm | **8.702 mm** | 1.088 mm | 1.450 mm |

The gate puts its inner samples **fourteen times the wall thickness apart** at `U` = 4, and nothing
in it reports that. `cowl_interior`'s own `check_samples` is the one figure in this subsystem already
expressed as a spacing rather than a count — `CHECK_ARC` = 0.20 mm — and pass 2's scan density is
measured to hold at exactly 0.200 mm at `U` = 3 and 4. **The inconsistency is between the
construction and the things that measure its output.**

**What it costs, measured by refining the spacing rather than the count.** `wall_measure.density`
sweeps a station through six spacings from 2.0 to 0.0625 mm, so a reading is indexed by millimetres
and is comparable across `U`. At `tail_shell` `U` = 4's worst station under the selected measure:

| spacing, mm | 2.0 | 1.0 | 0.5 | 0.25 | 0.125 | 0.0625 |
| --- | --- | --- | --- | --- | --- | --- |
| thinness, mm | 0.2467 | 0.0232 | 0.0332 | 0.0346 | 0.0346 | 0.0347 |

Settled by 0.25 mm and moving 0.00008 mm per halving thereafter. **84 % of the coarse reading was
the instrument.** That series was taken before `corner_excluded_min`’s own resampling defect was
found (§6.4), which moves a tail reading by about 0.001 mm; its endpoint matches the corrected
sweep’s 0.0347 mm for this wall, and the trend is what the table is for. Re-measuring all twelve stations at a fixed 0.125 mm spacing:

| | published, 1 440 samples | refined, 0.125 mm | stations over `WALL_TOL` |
| --- | --- | --- | --- |
| `tail_shell` `U` = 1.0 | 0.0282 | **0.0286** | 3 of 12 |
| `tail_shell` `U` = 3.0 | 0.1514 | **0.0469** | 4 of 12 |
| `tail_shell` `U` = 4.0 | 0.2136 | **0.0347** | 4 of 12 |

At `U` = 1 nothing changes, because 1 440 samples was already 0.30 mm there. At `U` = 4 the figure
falls by a factor of six, and at that wall's own worst station — `z` = -362.8182, the station the
published number came from — it falls from 0.2136 to **0.00264 mm**. Every station of every wall
measured is a healthy annulus, so these are thin walls and not severed ones.

**Three conclusions, and the first two are corrections.** The apparent regime change at `U` ≥ 3
(§6.5) was the instrument. The claim that the thin readings "were not mostly instrument artefact"
(§6.4) was wrong at large `U` and right at small `U`, because the instrument's own error scaled with
`U`. What survives is that **the wall is genuinely 0.028 to 0.048 mm thin at its worst, at every `U`,
over `WALL_TOL` by three to five times** — and that figure is now consistent across the range rather
than growing.

**The mechanism is not identified, and two candidate explanations are refuted rather than merely
untested.**

- **Smooth-arc chord sag is far too small.** A coarsely sampled outer polyline's chords lie inside
  the true curve, so an inner sample measures to a chord and reads closer. That is real, exactly
  predictable as `s^2 / (8R)`, and confirmed to grow linearly in `U` at fixed count — and at the
  spacing the corpus sweep used on a `U` = 4 section it is about **0.0005 mm against the 0.18 mm
  observed, four hundred times too small**. Correct arithmetic over the wrong geometry. Two synthetic
  reproductions, including one with absolute-sized notches, also failed to produce the error.
- **Curvature does not predict the thin spot, and at large `U` it is anti-correlated.** Measured as a
  percentile rank of local curvature at the thin spot, with inside-tolerance stations as controls:
  the worst stations rank 0.31 to 0.67 while the *controls* rank 0.81, 0.95 and 0.96, with local
  radii of 1.6 to 1.8 mm. The sharpest places on a `U` = 3 or `U` = 4 section carry essentially no
  thinning (0.0006 to 0.0043 mm). At `U` = 1 the ranks are mixed — 0.94, 0.12, 0.50 at the thin
  stations — so curvature fails as a predictor in both directions.

What is known about where the defect is: the thin spots sit at **scale-invariant angular positions**,
nearly identical station for station between `U` = 3 and `U` = 4 (142.73 against 142.72, -147.07
against 147.05, -156.83 against -156.81, 52.22 against 52.24), which follows from every buttress
position being a fraction of `unit_width`. At `U` = 4 the worst spots hold `x` within 1 mm of
-197.7 across three stations, close to the half-width. That is a lead, not a mechanism.

**The fix in the library, and the one still owed to production.** `sweep.measure_wall` and
`sweep.sweep` now take `spacing` and derive the count per station from that station's own perimeter,
and every result row records which of the two it used, so a figure can never be read without knowing
how it was sampled. `locate` was caught by the same bug from the other side: at 720 points it
classified a healthy `U` = 4 annulus as severed, which the kernel contradicted at `z` = -285.2857.
**`check_cowl_interior`'s own `AROUND` = 240 is still a fixed count**, and on the evidence here its
readings above `U` = 2 are not sound; replacing it with an arc-length spacing is the production half
of this finding.

### 6.7 The station grid: a bounding box is not the part

**`Shape.BoundBox` on these solids is an outer bound and nothing more**, and §5's own `z_extent`
records why: the box is computed from the untrimmed B-spline geometry rather than from the trimmed
result. Measured 2026-10-10 on the saved corpus, the gap is not subtle:

| saved wall | bounding box, `z` | real extent, by sectioning | stations found, box | real |
| --- | --- | --- | --- | --- |
| `nose_cowl_shell` `U` = 0.5 | -50.00 .. -1.50 | -25.00 .. -3.00 | 5 of 12 | **12 of 12** |
| `nose_cowl_shell` `U` = 2.0 | -200.00 .. -6.00 | -100.00 .. -12.00 | 5 of 12 | **12 of 12** |
| `nose_cowl_shell` `U` = 4.0 | -400.00 .. -11.99 | -199.99 .. -24.00 | 5 of 12 | **12 of 12** |
| `tail_shell`, every `U` | tight to 0.001 mm | same | 12 of 12 | 12 of 12 |

A nose wall's box is **twice the part's length**. A grid placed across it puts its end stations in
empty space, which is why every earlier nose figure in this document was taken at 5 to 9 of 12
stations and was therefore excluded from every verdict. The tail was never affected, its mask
spanning the whole OML -- which is exactly the asymmetry `z_extent`'s docstring warned about, and
the reason this went unnoticed: the kind that fails the tolerance is the kind the box fits.

`wall_measure.corpus.sectioning_extent` probes interior fractions of the box for one that sections
and then bisects outward to each real end, the same idea as `z_extent` reimplemented where it can be
used without importing a vendor module. `measurable_station_grid` places stations across that, and
`sweep` now uses it.

**So the nose is judged, for the first time, and it is compliant below `U` = 4.** The corpus sweep
re-run on the real extent reaches **12 of 12 stations on all twelve distinct walls**, so for the
first time every configuration has a verdict rather than an exclusion:

| | `tail_shell` | `nose_cowl_shell` |
| --- | --- | --- |
| `U` = 0.5 | 0.0134 | **0.0011** meets |
| `U` = 1.0 | 0.0286 | **0.0031** meets |
| `U` = 1.5 | 0.0421 | **0.0038** meets |
| `U` = 2.0 | 0.0345 | **0.0050** meets |
| `U` = 3.0 | **0.0469** worst | **0.0083** meets |
| `U` = 4.0 | 0.0347 | 0.0140 |

**Five of twelve walls meet `WALL_TOL`; seven do not.** That replaces "no wall meets the tolerance",
which was true of what had been *judged* -- and what had been judged was the tail, because the
tail's bounding box is tight and the nose's is not. The kind that fails is the kind the grid defect
never touched, which is why it went unnoticed.

The defect is now precisely located: **every `tail_shell` configuration fails, at every `U`, and the
only nose configuration that fails is `U` = 4.** Under the incumbent measure nothing passes at all
(0 of 12), because its readings are dominated by corner artefact on the nose -- 0.029 to 0.038 mm
where the selected measure reads 0.001 to 0.014.

**And it is the strongest mechanism evidence so far, because it is a converse.** The nose cell is an
octant with two construction planes and **no diagonal buttresses**; the tail is a half cell with one
plane and the 30° diagonals of `top_diag_angle`. The construction *without* the diagonals meets the
tolerance at four `U` values out of six; the construction with them fails at all six. That implicates
the diagonal buttresses specifically, rather than the erosion identity, the rib dilation or the
boolean, all of which both kinds share. It is consistent with
[OQ-DES-CW21](cowl.md#open-questions)'s own large-`U` thinning being pinned to the diagonals, and
with the tail's thin spots clustering near 140-157° -- the mirror of 30° is 150°. Confirming it means
measuring the tail's thin-spot angles against its buttress angular positions directly, which is
cheap on a saved wall.

**The two kinds also scale differently, and that was invisible until the grid was fixed.** With all
twelve of the nose's stations reachable, its thinning is **strictly monotonic in `U`** while the
tail's is not monotonic at all:

| `U` | 0.5 | 1.0 | 1.5 | 2.0 | 3.0 | 4.0 | ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `nose_cowl_shell` | 0.00115 | 0.00310 | 0.00376 | 0.00504 | 0.00829 | 0.01403 | **12.2x**, monotonic |
| `tail_shell` | 0.01345 | 0.02862 | 0.04208 | 0.03449 | **0.04689** | 0.03468 | 3.5x, peak at `U` = 3.0 |

A factor of 12.2 across a factor of 8 in `U` is very nearly linear, and nothing in the nose's
construction is supposed to scale that way: the wall is an absolute 0.6 mm at every `U`. So the two
kinds are not one phenomenon at two magnitudes. **The tail is already twelve times the nose at
`U` = 0.5, where the nose's own scaling term has barely started** — which says the diagonals
contribute a large `U`-independent part, and something else contributes a part that grows with the
part. Both belong to IP-WTM-26, and the nose is the cheaper one to chase: 38 to 117 s a build
against 727 to 4 525 s.

### 6.7.1 The ribs are not where the wall is thin

The nose/tail asymmetry above points at the tail's four diagonal buttresses, and the tail's
thin-spot angles rotate monotonically with `z` -- 142.7° through 160.1° across six stations at
`U` = 0.5 -- which is what the trace of a plate tilted 30° about X does. So the obvious hypothesis is
that `dilate(B, t)` is wrong where the diagonals cluster: a disc dilation rounds every convex edge by
`t`, and clustered tools' envelopes merge.

**Two parts of that are ruled out by arithmetic, before any measurement.**

- **Faceting is 0.0013 mm.** `dilated_notches` builds the dilation as a union of `RIB_FACETS` = 48
  translates on a circle of radius `t`, so a true offset point whose direction falls between two
  translates is still covered unless the tool's own boundary turns away from it; at a sharp convex
  corner the chord sags by `t(1 - cos(π/48))` = 0.00128 mm. That is twenty-five times smaller than
  the thinning. The *gross* faceting mode is a different thing and is guarded: at `RIB_FACETS` = 24
  adjacent copies stop overlapping, and the measured result was 0.1035 mm of wall where 0.6 was
  wanted, which `dilated_notches` now refuses with `PreconditionFailed`.
- **Merging introduces nothing.** A Minkowski sum distributes over union --
  `dilate(A ∪ B, t)` = `dilate(A, t) ∪ dilate(B, t)` exactly -- so two dilated envelopes meeting is
  the exact dilation of both, however tight the cluster.

**And the measurement refutes the rest of it.** `freecad/rib_proximity.py` finds each station's
thinnest point and reports its distance to all eleven buttress tools by name, raw and dilated. On
`tail_shell` at `U` = 0.5:

| `z` | thin, mm | nearest tool | distance to the raw tool | to its dilated envelope |
| --- | --- | --- | --- | --- |
| -35.909 | **0.01153** | `Side1Safe` | 3.729 mm | 3.132 mm |
| -22.818 | **0.01163** | `Diag22Safe` | 0.543 mm | 0.243 mm |
| -5.364 | **0.01346** | `Bot1Safe` | 6.735 mm | 6.401 mm |
| -31.545 | 0.00402 | `Diag11Safe` | 0.612 mm | 0.312 mm |
| -1.001 | 0.00072 | `Bot2Safe` | 15.115 mm | 14.700 mm |

**Ten of the twelve thin spots sit more than 3`t` from any rib, and the worst one is 6.7 mm away --
eleven times `t`.** If the dilation were thinning the wall, the thin spots would sit *on* the
dilated envelopes' boundaries. Two do, at 0.243 and 0.312 mm inside a diagonal's envelope, and they
read 0.01163 and 0.00402 mm -- one marginally over tolerance and one comfortably inside it, which is
the same spread the far stations show. The nearest rib is a diagonal at six of twelve stations, but
four diagonals among eleven tools span most of the part, so that is what proximity alone predicts.

The envelopes do merge, and the overlaps are small: the largest is a top/diagonal pair at 64.6 mm³,
**3.55 % of the smaller tool**, and diagonal-to-diagonal pairs share 29.3 mm³ (1.61 %) and 4.0 mm³
(0.22 %). [IP-FC-137](../implementation/freecad_migration.md#work-items)'s synthetic pathology needed
roughly **40 %** overlap, so the real construction is an order of magnitude away from that condition
at this `U`.

**What the diagonals plausibly still do, and it is not about their dilation.** A first version of
this paragraph said every notch edge is a patch boundary, so four diagonals would multiply the
patches and shorten the intervals within them. **That was wrong, and the log says so directly:
every one of the twelve builds reports `patch 1/1`.** `_patches` is fed the un-notched blank's
creases, of which these cells have none, so the diagonals add no patch boundary at all (§4.1).

What they do add is **interpolation rows**, because the fit's seed is front-loaded with every notch
edge. The tail's 19–26 notch edges go into a single patch's station set, where `station_floor(t)`
then drops five or six of them as too close to a neighbor — 25→19, 28→23, 32→27. So the diagonals
act on the fit by crowding its rows, not by subdividing its domain, and crowded rows are exactly
the condition `station_floor` exists to limit (§4.1, §6.2). That still makes the diagonals matter
through the *fit* rather than through the cut, which is consistent with §6.8's result that
tightening `TAU` improves the wall proportionally, and with the thin magnitudes being the same
order as `TAU` itself. The sharper version of the test is to compare each thin spot's magnitude
against the local fit row spacing — a cheap addition to this same tool.

One cross-check worth recording: this build measured 0.01346 mm at `U` = 0.5 against the saved
corpus wall's 0.01345 mm -- a fresh build, a different grid and a different code path, agreeing to
five decimals.

### 6.8 Tightening the criterion: measured, not argued

Every `tail_shell` wall reads three to five times `WALL_TOL`, and §5's two refinement passes both
stop at `TAU` = 0.05 mm, so the walls come out just inside the criterion they were converged to. That
reading says `TAU` is the binding constraint. **Whether it is, and what tightening it costs, is a
measurement**, and `freecad/tau_study.py` takes it: it builds one part once, then re-cuts the wall by
calling `shell_solid` directly at each `TAU`, and measures each result. Three outcomes were possible
and the rig prefers none of them -- the wall improves, the build raises `Unconverged` against
`POST_CUT_ROUNDS` = 6, or the wall does not move at all.

`nose_cowl_shell` at `U` = 4, the cheapest configuration that fails the tolerance (117 s a build
against 4 525 s for the largest tail):

| `TAU` | fit rows | pass 2 predicted | real wall | stations over `WALL_TOL` | build |
| --- | --- | --- | --- | --- | --- |
| 0.05 (current) | 11 | 0.01530 | 0.01403 | 2 of 12 | 117 s |
| 0.02 | 15 | 0.00393 | **0.00378** | **0 of 12** | 133 s |
| 0.01 | 17 | 0.00393 | **0.00187** | **0 of 12** | 138 s |

**The part becomes compliant at `TAU` = 0.02, for four extra fit rows and 14 % more build time.**
At 0.01 it has five times the margin. Neither tightening raised `Unconverged`, and neither exhausted
the round budget -- the outcome that looked most likely beforehand, given that `tail_shell` at
`U` = 3.0 already spends 5 of its 6 rounds at `TAU` = 0.05. Pass 1's log shows it doing exactly what
the criterion asks: *"refining: 10 stations -> 16, worst wall error 0.0519 mm over 0.010"*, then
16 -> 17 at 0.0181 mm.

Two independent checks that this is the wall and not the rig: the `TAU` = 0.05 row reads 0.01403 mm,
and the *saved* `U` = 4 nose wall from the soak -- a different build, four days earlier, measured
through a different code path -- reads 0.01403 mm on the same grid. And every station of every wall
is a healthy annulus at all three criteria.

**What this does not yet show.** It is one configuration of one kind, and the nose was already
within a hair of tolerance before tightening, so the lever had little work to do. The `tail_shell`
is where the wall is three to five times over, and its cheapest build is 727 s; confirming the same
proportional improvement there is the measurement that matters, and it is not done. Nor is the cost
on a tail known: the nose's +14 % came with 4 extra rows on a patch of 176 mm, while a tail at
`U` = 4 already carries 32 rows over 400 mm and spends rounds the nose never needed.

**What `TAU` should then be set to is a decision, and it is filed as
[OQ-DES-CW28](cowl.md#open-questions).** Tightening it was never the design question — that was
settled as a measurement and taken — but *which* value to adopt is a trade between build time and
compliance, and the two are not separable by measurement alone: a criterion looser than `WALL_TOL`
cannot guarantee `WALL_TOL`, a criterion equal to it may not converge on a tail inside
`POST_CUT_ROUNDS`, and a fifth option is to leave `TAU` alone and remove the residual's mechanism
instead (§6.7, IP-WTM-26 and IP-WTM-36). That question records the alternatives and states plainly
that its own recommendation is not decidable until IP-WTM-28 reports.

### 6.9 The shape of the rib edges

§4.2 moves the rib creases out of the fitted surface and into a boolean, on the grounds that "the
creases then arrive as the edges of a boolean between two well-formed solids, which is where a
crease belongs". **That is an argument about where a crease comes from, and until 2026-10-11
nothing checked that the one the kernel returned is where it should be.** The set identity the
construction rests on is

    ∂(S − T)  ⊆  ∂S ∪ ∂T

and a rib edge is specifically the intersection ∂S ∩ ∂T — so every point of one must be on the
fitted interior surface **and** on a face of the dilated tool, at once.

**What `cavity` checks after the cut is a volume and a count**, neither of which constrains
geometry: at most `RIB_RESIDUE` = 0.01 mm³ of tool left inside, and exactly one solid. A trimming
curve that has wandered 0.05 mm off the surface it should lie on changes the residue by nothing
measurable, splits nothing, and leaves the wall 0.05 mm wrong along its whole length.
[IP-FC-137](../implementation/freecad_migration.md#work-items)'s synthetic result is the precedent:
a genuinely invalid five-face sliver "passed the existing volume-only OK/retry check" at
0.000000 mm³. And three steps in the cut are entitled to move geometry — the **fuzzy** boolean
(`RIB_CUT_FUZZ` = 1e-5 mm, whose own note records it snapping near-tangent geometry together),
`removeSplitter()`, which refits what it merges and runs on both operands as well as the result,
and the documented near-tangency between a dilated diagonal and the interior surface, which is
where a trimming curve is worst determined.

`wall_measure/boolean_edges.py` measures it and `freecad/rib_edge_check.py` runs it. The tool is a
union of translated polyhedra, so every face of it is planar and the distance to one is a dot
product; the fitted interior is a single B-spline, so the distance to it is one kernel call. Both
operands come out of `cavity`'s existing `report` (`smooth_shape`, `rib_tool`) beside the cavity it
returns, so the builder needed no change.

| | nose `U` = 0.5 | tail `U` = 0.5 |
| --- | --- | --- |
| buttress tools | 1 | 11, four of them diagonal at a 30° cut |
| notch edges | 4 | 19 |
| cut faces / edges | 60 / 174 | 1 060 / 3 164 |
| tool faces (all planar) | 152 | 2 740 |
| **rib edges** (`surface` meets `tool`) | **45**, 21.67 mm | **831**, 623.29 mm |
| samples at 0.20 mm | 187 | 4 540 |
| worst distance to the fitted surface | **5.265e-08 mm** | **2.972e-04 mm** |
| worst distance to a tool face plane | 7.247e-16 mm | 2.132e-14 mm |
| at the kernel's own tolerance (1e-07) | 187 of 187 | 4 298 of 4 540 |
| within `RIB_CUT_FUZZ` (1e-05) | 187 of 187 | 4 503 of 4 540 |
| over `RIB_CUT_FUZZ` | 0 | 37 |
| **over `WALL_TOL`** | **0** | **0** |

**The edges conform.** The tool side is exact to 2e-14 mm — it is a plane, and the boolean put the
edge on it. The surface side is at the kernel's own coincidence tolerance for 95 % of the tail's
samples and all of the nose's, and its worst departure anywhere is **0.3 µm**: 34 times under
`WALL_TOL` and 170 times under `TAU`. **So this is not the mechanism behind the residual
0.013–0.047 mm** (§6.4) — it is forty-five times too small at the one `U` where both were measured,
and that is a refutation with a number rather than an argument.

**The 37 that exceed the fuzz are all edge *endpoints*, in two bands.** Every one is sample `i` = 0
or 1 of its edge, and they cluster at `z` ≈ −1.57 to −1.84 and `z` ≈ −10.0 to −10.2 — just past the
fit stations at `z` = −1.5000 and −10.0011, both of which are notch edges carried into the seed by
[OQ-DES-CW22](cowl.md#open-questions)'s front-loading. A vertex is where three surfaces meet rather
than two, so it is the least constrained point on a trimming curve; at 0.1–0.3 µm this is the
kernel resolving that, not a defect.

Two things worth recording that the check turned up on the way:

- **Two tool faces are coincident with a cell construction plane to 1.9e-6 and 5.9e-6 mm** — inside
  `RIB_CUT_FUZZ`, which is why they classify as `ambiguous` rather than as `tool`. That is exactly
  the near-coincident-geometry class `RIB_CUT_FUZZ` was introduced for (its own note records the
  `Diag12Safe` sliver at `U` = 0.75), now located and quantified rather than inferred. A rib tool
  that reaches the cell boundary will have a face in that plane, so this is expected; what was not
  known is how close.
- **One of the tail's 3 164 edge groups is not shared by exactly two faces.** On a closed solid
  every edge has two, and the nose has no such group. A periodic seam, which one face meets twice,
  and a degenerate edge would both look like this; which it is has not been established. It is one
  edge in 3 164 and it is a `lid` group, not a rib edge, so it does not touch the result above.

The cheap measures agree with `distToShape` to every printed digit on all sixteen of the worst
samples in both runs, which is the only reason the figures above are quotable: both are optimistic
in a known direction (§6.1), and the agreement is checked rather than assumed.

#### The surface, not the edge

An edge in exactly the right place says nothing about the surface it is drawn on. The position check
above constrains the **trim curve**; `removeSplitter` (`ShapeUpgrade_UnifySameDomain`) refits what it
merges, and a refit that reproduces the trim boundary to the kernel's tolerance can still differ
from the original in the patch *interior*, where nothing pins it. That is a boundary-value problem,
and its signature is a displacement in the middle of a patch rather than at the edge where it was
introduced. Three tests, strongest first.

**1. The control nets are identical, which settles it outright.** `surface_identity` compares
degrees, pole counts, knots, multiplicities, weights and periodicity, and then every pole. On both
kinds:

    cut face 0   IDENTICAL   degrees True  poles True  knots True
                 weights True  periodic True  worst pole 0.000e+00 mm

Not "within tolerance" — **no pole moved at all**, on the tail as well as the nose, with eleven
tools, 1 050 tool faces and 831 rib edges cut into it. The boolean trimmed and did not refit, so
nothing is imposed on the surface at a patch edge and nothing can propagate inward: a trim cannot
move the surface it trims. The cut carries **three** faces on that one surface at the tail;
`bspline_surfaces` groups by control net rather than by face, so that is one surface, not three.

**2. Measured independently, the patch interior is flat.** 600 probes on the nose and 829 on the
tail, each one's distance to the pre-cut face tabulated by its distance to the nearest rib edge —
which is where propagation would show:

| distance to the nearest rib edge | tail probes | worst deviation | worst normal angle |
| --- | --- | --- | --- |
| 0.00 – 0.10 mm | 4 | 0.000e+00 mm | 0.0072° |
| 0.10 – 0.50 mm | 93 | 3.553e-15 mm | 0.0000° |
| 0.50 – 2.00 mm | 360 | 7.324e-15 mm | 0.0000° |
| 2.00 mm – ∞ | 372 | 7.944e-15 mm | 0.0000° |

Every band at double-precision noise, with no trend in distance. The nose is the same: 3.553e-15,
3.553e-15 and 7.944e-15 mm over its three populated bands.

**3. The normals agree, which is the sensitive test.** A normal difference is first order in a
surface perturbation where a position difference is second order, so two surfaces can match to
1e-14 mm in position and still disagree visibly in slope. They do not: 0.0000° mean over 150 nose
and 345 tail probes. **The one non-zero reading, 0.0072°, is not a measurement.** It sits in the
nearest-edge band, where a probe has the fewest usable offsets, and it is **three times below
`face_normal`'s own resolution floor** — the method's coplanarity residual gives a median 0.0214° on
this very run — so it is instrument noise, as it has to be when the control nets are bit-identical.

**What the normals did find is the crease angle, and the tail's is shallow.** The angle between the
fitted surface and the tool's cutting plane is a design quantity the position check cannot reach,
and 0° is the tangency `RIB_CUT_FUZZ` exists for — its note records a dilated diagonal grazing the
interior surface "at a shallow near-tangent angle" and pinching off a zero-volume sliver at
`U` = 0.75. Over 200 rib-edge samples, ranked worst-conformance first:

| | nose `U` = 0.5 | tail `U` = 0.5 |
| --- | --- | --- |
| **minimum crease angle** | 54.731° | **18.258°** |
| median | 89.739° | 81.923° |
| maximum | 90.000° | 89.997° |
| samples under 40° | 0 of 187 | 5 of 200 |
| samples under 60° | 4 of 187 | 34 of 200 |

The tail comes **three times closer to tangency than the nose**, and its five shallowest creases are
18.3°, 25.3°, 31.3°, 36.0° and 39.9°. Nothing here failed, so this is not a defect — but it is the
first direct reading of the quantity the documented degeneracy is a limit of, and it is one cheap
scalar per build. **If the minimum crease angle collapses toward 0 near `U` = 0.75, where
`Diag12Safe`'s sliver actually occurred, it is a predictor of that failure rather than a description
of it** — and the fuzzy boolean would then have something to be checked against instead of only
tuned by hand. That is the sharpest form of IP-WTM-34 and the reason to pay for a sweep.

**What this does not cover.** One `U` per kind, and the cheapest of each. The tail's cost is two
cavities — 741 s each, because `build_cell`'s recompute is what produces the cell shapes the second
one needs — so a sweep across `U` is a real expense and was not paid. The 37 over-fuzz samples grew
from 0 on the nose to 37 on the tail, and whether that count grows with `U` is unmeasured; so is
whether the worst departure does, and so is whether the minimum crease angle does.

**And it covers `cavity` only.** `shell_solid` then runs `_extend_across_cell`,
`notched.cut(inside)`, `_strip_seam` and `mirror_across_cell`, each with its own boolean and its own
`removeSplitter`, and none is tested here — so "the boolean preserved the surface" is *established*
for the rib cut and *assumed* for the four steps after it. The mirror step needs no build to check:
a finished wall's interior B-spline copies should be exact images of one surface under the mirror
transforms, so `surface_identity` across a saved wall's own faces would test it on all twelve corpus
walls for free. That is IP-WTM-38.

## 7. Failure modes to expect

**The shell cut returns the wall in more than one solid.** `notched.cut(inside)` can sever the
cell wall. Reproduced 2026-10-03 on `tail_shell` at `U` = 3.0 under the §6.2 probe at δ = 0.01 mm,
with **two signatures that are not the same failure**:

| station | result | partition slip | signature |
| --- | --- | --- | --- |
| *(unperturbed)* | 1 solid, 107228.9 mm³ | 2.83e-05 | healthy; sections to exactly 1 loop at every `z` |
| `z` = -294.1530 | 3 solids: 90900.3, 4349.3, 718.2 mm³ | 2.05e-05 | the wall came apart; cut and complement still sum to the blank |
| `z` = -60.0000 | 2 solids: 51916.6, 4349.5 mm³ | 0.993 | the partition identity itself collapsed |

**Both are caught** — the solid-count check catches both and the partition check independently
catches the second (§6).

**The wall's own volume drops in both, but that drop is not material the boolean lost, and the
figure itself is not trustworthy.** Measured again 2026-10-04 on a fresh build at `z` = -294.1530:
the partition identity holds at **2.409e-05**, and the blank's two shares move by the same amount in
opposite directions — the wall's reading falls 16648 mm³ while the cavity's rises 16614 mm³. So the
cut accounted for the blank; the cavity simply took more of it. What cannot be quantified is the
wall's volume itself. `solid_measure.converged_volume` does not converge on the severed result at
all, returning **3171671.63 mm³ at two of the five deflections tried** — thirty times the whole part
— against 110019.53, 107691.06 and 95131.36 at the other three, on a tessellation with 946 unpaired
edges. §6.1's rule applies with force here: a volume from a failed wall is not a measurement, and
the partition identity is the only volume statement this failure supports.

Seen square on the failing `x` ≈ -150 face, with `z` across the page and each returned solid in its
own colour, against the healthy wall for reference:

![The healthy cell wall, square on the x = -150 face](img/cowl_rib_cut/cw24_wall_healthy_faceon.png)

![The severed wall, each returned solid in its own colour](img/cowl_rib_cut/cw24_wall_severed_faceon.png)

![The second failure, against a ghost of the healthy wall](img/cowl_rib_cut/cw24_wall_corrupt_faceon.png)

*Top: healthy. Middle: `z` = -294.1530 — blue stays attached, orange and green detach; the red bar
is the displaced row. Bottom: `z` = -60.0000 — white is the healthy wall ghosted, for everything
the cut failed to return.*

The same two failures in three dimensions, which shows how little of the wall the second one
returns:

![The severed wall, three solids, isometric](img/cowl_rib_cut/cw24_wall_severed.png)

![The second failure, isometric, against the ghosted healthy wall](img/cowl_rib_cut/cw24_wall_corrupt.png)

Three properties of this failure are measured and worth knowing when diagnosing one:

- **It does not occur at the perturbed station.** The row displaced at `z` = -294.1530 produces
  detached pieces at `z` -240…-90 and -122…-66. The same two pieces detach when a different station
  is perturbed instead (§7.1), so the location is a property of the geometry rather than of the
  perturbation. **This was previously argued from §4.4's attenuation instead — that the fit could
  not propagate 0.01 mm that far — and that argument is withdrawn**, because the measured
  station-to-station gain is three orders of magnitude larger than the coefficient decay predicts.
  The conclusion stands on the repeated-piece evidence, which does not depend on it.
- **The detached piece is the same piece in both signatures** — volumes 4349.266 and 4349.504 mm³,
  areas 14723.0 and 14723.1 mm², centres of mass agreeing to 0.0025 mm, 12 of 16 vertices
  bit-identical.
- **It is bounded by slot cuts and nothing else.** Sampling its ten faces against the real cutter,
  four faces totalling 225.46 mm² lie on buttress slot cuts and the remaining 14497.57 mm² is
  exactly twice its own 7248.7 mm² wall surface. It is the wall region the slots already very
  nearly isolate.

![The detached piece and the slots that enclose it](img/cowl_rib_cut/cw24_strip_cage_faceon.png)

**A returned solid can have a void in it and still report as one solid.** The `z` = -60.0000 result
has **zero volume between `z` = -54 and -52**, with 2958.9 mm³ in the millimetre below and
4581.8 mm³ above, measured as thin-slab volume rather than by sectioning (the healthy wall returns
190.4 mm³ in the same band). A connected solid cannot do that, and nothing in the current checks
looks for it.

### 7.1 The cut can break the wall's section ring, and nothing catches it

**Reproduced 2026-10-04, characterized 2026-10-05, and this is the one failure mode nothing in the
construction catches.**

On `tail_shell` at `U` = 3.0, displacing the row at the notch-edge station `z` = -283.9951339 by
δ = 0.03 mm — a station whose nearest neighbouring row is **0.4311 mm** away, so δ/gap = **0.0696**
and §6.2's probe is inside its own validity domain — returns:

| | healthy (δ = 0) | δ = 0.03 mm |
| --- | --- | --- |
| section at `z` = -217.7261 | **annulus**, 200/200 of the inner loop inside the outer | **two separate strips**, 0/200 inside |
| ring length | 1600.027 mm | **1506.831 mm — 93.2 mm missing** |
| material area in section | 954.742 mm² | 922.450 mm² |
| wall thickness there | **0.5967 mm** | **0.6120 and 0.6132 mm — nominal** |
| solids returned | 1 | 1 |
| `isValid()` | True | True |
| partition slip | 2.831e-05 | **2.396e-05** |
| mirror/sew | 1 closed shell of 1 | 1 closed shell of 1 |
| verdict | OK | **OK** |

**It is not a thin wall. It is a wall of correct thickness with a hole in it.** The cross-section
ring comes apart into a 1293 mm arc and a 213 mm arc, each measuring 0.61 mm across against a
0.6 mm nominal, with about 93 mm of the 1600 mm ring simply absent. On a part that prints in
spiral-vase mode with a single perimeter (cowl.md §7) that is an open wall, not a thin one.

**And the existing check reports it as a thickness of 0.355705 mm**, which is why it read as a
thinning for a day. `check_cowl_interior.wall_thickness` sorts a section's closed loops by enclosed
area, takes the two largest and measures the distance from the second to the first — correct when
they are an outer/inner pair, and meaningless when they are two disjoint arcs, where the same code
measures **the gap between the broken ends**. The 0.355705 mm figure is that gap. The loop-ordering
fix recorded in that function's own docstring addressed outer-versus-inner; it does not address
disjointness, and nothing downstream asks whether the section is the annulus the measure assumes.

**The break is at the diagonal buttresses, and mirror-symmetric.** Sampling the gap around the
section puts every reading under tolerance inside **30.37°–30.56°** and **329.46°–329.66°** about
the `z` axis — two arcs 0.19° and 0.20° wide, 0.46° and 0.44° from `top_diag_angle` = 30°. Those
are the two break locations, which is why there are exactly two arcs. The isolated 213 mm arc is
the same region that detaches outright as the 718 mm³ piece when the cut severs instead (§7), so
the severed and silent outcomes are the same geometry failing two different ways.

The healthy reference is not in doubt: the 0.546556 mm nearest-point reading reproduces to six
decimals across five fresh builds in one session and two independently-fitted station sets in
another, and IP-FC-144's station set reads 0.546559 mm — 3e-6 mm away on 30 rows against 35. What
that number *is*, however, is a nearest-point distance and not a converged thickness; §6.1's
seventh caution has what it is worth.

**Every check means every check, and that is measured rather than assumed.** The probe reproduces
`shell_solid`'s sequence *and* `cavity`'s own `cut_and_check`, which measures §4.2's rib residue
against `RIB_RESIDUE` = 0.01 mm³ and the cavity's connectivity before the wall cut happens. At
δ = 0.03 mm the rib residue is **0.000000 mm³** and the rib cut returns one valid solid, so
`cut_and_check` passes; then the wall cut returns one solid, the partition identity reads 2.396e-05,
and the mirror sews to one closed shell. Six checks, all passing, on a 0.355705 mm wall.

**The dose series, run as one fresh sequence:**

| δ | rib residue | `cut_and_check` | wall | thickness | change | caught by |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 0.000000 mm³ | passes | 1 solid | 0.546556 mm | — | — |
| 0.001 mm | 0.000000 mm³ | passes | 1 solid | 0.546964 mm | +0.000408 mm | — |
| 0.003 mm | 0.000000 mm³ | passes | 1 solid | 0.547781 mm | +0.001225 mm | — |
| 0.01 mm | 0.000000 mm³ | passes | 1 solid | 0.550640 mm | +0.004084 mm | — |
| **0.03 mm** | **0.000000 mm³** | **passes** | **1 solid** | **0.355705 mm** | **-0.190851 mm** | **nothing** |
| 0.1 mm | 0.000000 mm³ | passes | 5 solids | — | — | solid count |

**The construction is linear and well behaved right up to the break.** The first three
displacements give 0.000408, 0.001225 and 0.004084 mm — a gain of **0.408 mm per mm at every one of
them**, to three figures. Extrapolating that line to δ = 0.03 mm predicts +0.0123 mm. The measured
value is **-0.190851 mm**: sixteen times the magnitude and the opposite sign. So this is not a
gradual degradation that a tighter tolerance would have caught earlier — it is a discontinuity, and
**it lies between δ = 0.01 mm and δ = 0.03 mm**, which is as far as the bracket has been narrowed.

**δ = 0.01 mm is not reproducible between processes.** This sequence reads +0.004084 mm and passes
everything; a different process reading the same cached rows severed the wall into three solids at
the same δ. Both are recorded; neither is treated as the outcome. δ = 0.03 mm, by contrast,
reproduced at **0.355705 mm in three independent processes**, and §6.1's note on the kernel
reproducibility floor is where that distinction belongs.

**Whether the fit carries the displacement is now open rather than settled.** This section
previously argued it could not: the measured station is 66 mm from the perturbed row, about 7.5
station intervals, so §4.4's 3.7× per-station attenuation would deliver a 0.03 mm displacement as
roughly 4e-6 mm, against 0.19 mm measured. But the *linear* regime refutes the same argument.
A gain of 0.408 mm per mm at that distance implies an attenuation of about **1.12× per station**, not
3.7×, so §4.4's figure understates the station-to-station sensitivity actually measured here by
three orders of magnitude. **The attenuation argument therefore cannot be used to rule the fit out**,
and why the measured gain is so much larger than the per-station decay predicts is itself
unexplained.

**The same region detaches regardless of which station is perturbed.** The 4349–4370 mm³ piece and
the 718.17–718.19 mm³ piece appear in the severed results at `z` = -283.9951339 and at
`z` = -294.1530459 alike. The detaching geometry is a property of the part, not of the perturbation.

**And the thin spot is not spread out — it is two arcs a fifth of a degree wide, on the diagonal
buttresses.** Measuring the silent wall's own section at `z` = -217.7261 all the way round, rather
than reducing it to one minimum, puts every sample under tolerance inside **30.37°–30.56°** and
**329.46°–329.66°** about the `z` axis: 13 samples of 2000, 0.7 % of the loop, in two arcs 0.19° and
0.20° wide, minimum 0.1035 mm. The healthy wall measured the same way has **no** sample under
tolerance anywhere, reading 0.577 to 0.737 mm. Three things follow:

- **The two arcs are mirror images** about the tail's one cell-boundary plane, 30.46° and 329.56°,
  so this is a geometric cause occurring twice and not a single kernel accident.
- **They sit on the diagonal buttress placement.** `top_diag_angle` is 30°, and the arc centres are
  0.46° and 0.44° from it. That is the same angular location [OQ-DES-CW21](cowl.md#open-questions)
  pinned its large-`U` wall thinning to, and the same place §6.5's round-0 measurement independently
  located this station's worst point — `x` = 134.319 mm, `y` = 78.688 mm, which is 30.4°.
- **So the global surface motion is beside the point.** Sampling one wall's surface for containment
  in the other found the inner surface displaced over much of the part — 46.15 % of points outside —
  but it found 30.07 % for a build that *held*, so the absolute figure localizes nothing, and the
  defect itself occupies 0.7 % of one section. What that sampling *does* separate is the asymmetry
  between its two directions: 46.15 % against 7.75 % for the failure, a ratio of 5.95, versus
  30.07 % against 26.73 % for the control, a ratio of 1.12. The failed wall is largely contained
  within the healthy one — material gone — where the control merely differs from it. That agrees
  with the partition identity, which holds at 2.409e-05 while the cavity's share of the blank grows
  by 16614 mm³.

**What this measurement cannot say.** The silent wall's section is topologically *different* from the
healthy one — two wires of 2586.876 and 426.785 mm against 1601.839 and 1598.215 mm — so pairing
"outer loop against inner loop" is valid for the healthy section and not for the silent one. The
minimum distance and its angular position are sound; the per-band figures away from the thin arcs,
which read 1.6 mm to 55 mm, are measuring unpaired curves and mean nothing.

**The originally recorded conditions for this result were wrong, and that matters for reproducing
it.** The claim was logged against `z` = -283.9951 — the four-decimal printing of the real notch
edge — and a harness that unions that literal into the seed set manufactures a station pair
0.0000339 mm apart there (§6.1). Run that way, with δ/h = 885, the same δ = 0.03 mm raises
`Unconverged` three times out of three and δ = 0.01 mm raises `ValueError: Null shape`: the forced
station fails loudly and never silently. The silent result belongs to the **real** station with its
ordinary 0.4311 mm gap.

What to do about a failure mode that passes every existing check is a design decision, not a
measurement, and it is [OQ-DES-CW26](cowl.md#open-questions).

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

**The ring break now has a reproduction that costs 0.1 s instead of 4 446 s, 2026-10-06.** The
failure in §7.1 was characterized on a real `tail_shell` at `U` = 3.0. It reproduces on a 20 mm
tube with a 0.6 mm wall and two opposing partial-height slots: the wall stays one solid, joined
above and below the slots, and its section at the slot station comes apart into two arcs — which
is the configuration `wall_thickness`'s annulus guard exists for, since the two loops are beside
each other rather than nested and the distance between them is the gap across the break, not a
thickness. `tests/test_geometry_bridge_cowl_checks.py` holds it.

**Two distinctions that reproduction pins down, both easy to get wrong.** The slots must be
*partial* height: full-height slots split the tube into two separate solids, and `wall_thickness`
loops over `wall.Solids` and measures each one on its own, so each arc is a single-loop strip and
reads a correct 0.586 mm with the guard never engaging — the function behaving properly on two
pieces, not the defect. And the guard only engages at **two or more** loops, so a ring broken by a
*single* slot leaves one C-shaped loop, takes the strip estimator, and also reads correctly. The
defect needs one solid whose section has two non-nested loops, which is what the real cowl
presented and what the synthetic case now presents for a thousandth of the cost.

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

### 9.9 Measured, the full soak corpus

**28 builds, 11.6 hours, both kinds, `U` in {0.5, 1.0, 1.5, 2.0, 3.0, 4.0}, with five repeats
at `U` = 1.0 and `U` = 4.0 on each kind.** Run 2026-10-06 by `soak_cowl_shell.py` (IP-FC-117),
one build per `freecadcmd` process, judged afterwards by `soak_compare.py` against
[OQ-ARCH-19](../architecture/freecad_migration.md)'s pairwise criterion. **This replaces the
corpus of 2026-09-23, which carried no measurements at all** — all 28 of its records were
`PreconditionFailed`, so every number below is new. Both earlier generations are kept beside it,
as `soak_results.superseded-2026-10-06.jsonl` and `soak_results.superseded-2026-09-11.jsonl`.

**Read the "worst wall error" column only through §6.4.** It is `wall_thickness`'s `worst_low`, a
nearest-point minimum, which does not converge — these are lower bounds from an unsettled
instrument, not measured deviations. §6.4 re-measures all 28 of these walls with a measure screened
against closed-form truth, and the figures move: `tail_shell` at `U` = 3.0 goes from 0.0534 to
0.1514 mm and at `U` = 4.0 from 0.1506 to 0.2136 mm. Every other column here — volume, rib residue,
partition slip, timings — is unaffected, and the reproducibility result the soak existed to produce
(16 of 16 repeat pairs bit-identical by canonical hash) does not depend on this column at all.

| kind | `U` | wall, mm³ | worst wall error, mm | rib residue, mm³ | partition slip | elapsed, s |
| --- | --- | --- | --- | --- | --- | --- |
| nose | 0.5 | 2 407.0057 | 0.0384 | 0.000000 | 1.04e-07 | 88 |
| nose | 1.0 | 9 710.4721 | 0.0256 | 0.000000 | 8.38e-07 | 106–139 |
| nose | 1.5 | 21 916.1456 | 0.0271 | 0.000000 | 3.55e-07 | 122 |
| nose | 2.0 | 39 029.8101 | 0.0234 | 0.000000 | 1.23e-07 | 136 |
| nose | 3.0 | 87 996.2569 | **0.0067** | 0.000000 | 1.28e-07 | 172 |
| nose | 4.0 | 156 532.6015 | 0.0495 | 0.000000 | 4.36e-07 | 246–259 |
| tail | 0.5 | 5 851.3872 | 0.0342 | 0.000000 | 3.64e-06 | 874 |
| tail | 1.0 | 23 704.2956 | 0.0243 | 0.000000 | **3.66e-04** | 1 209–1 227 |
| tail | 1.5 | 53 531.0114 | 0.0360 | 0.000000 | 2.44e-07 | 1 424 |
| tail | 2.0 | 95 633.1602 | 0.0319 | 0.000000 | 2.75e-07 | 2 139 |
| tail | 3.0 | 215 743.4480 | 0.0534 | 0.000000 | 2.83e-05 | 4 446 |
| tail | 4.0 | 384 172.2640 | **0.1506** | 0.000000 | 3.20e-07 | 4 861–4 875 |

Every one of the 28 builds returned exactly **one solid, zero open edges in the tessellation, a
reliable volume, and zero stations with no wall material found**. Volume is `mesh_volume` at the
fixed `VOLUME_DEFLECTION` = 0.001 mm rung, never `Shape.Volume` (IP-FC-119), at 668 k to 3.71 M
facets.

**Cross-process reproducibility is exact at all four repeated configurations.** 16 pairs
compared, 16 identical `canonical_hash` — the screen ended every comparison and nothing reached
the `XOR / (A · 100U)` and surface-gap thresholds. Since that hash can report "different" about
parts that agree but never "same" about parts that differ, an equal hash is conclusive. The
repeated configurations include both kinds' largest case, so this is not a result confined to
cheap geometry. It neither confirms nor disturbs the separate finding that reproducibility
breaks down *near a degenerate configuration*: none of the four is near one.

**`worst_wall_error` is not monotone in `U`, on either kind.** The nose runs 0.0384, 0.0256,
0.0271, 0.0234, 0.0067, 0.0495 and the tail 0.0342, 0.0243, 0.0360, 0.0319, 0.0534, 0.1506 — both
turn around more than once, and both are worst at `U` = 4.0. So the gap against `WALL_TOL` cannot
be read as a resolution effect that finer stations would close — refining makes it worse as often
as better. On the tail, `U` = 3.0 is 2.2 times worse than `U` = 1.0 and `U` = 4.0 is 6.2 times
worse, both finer constructions than the one they lose to.

**Superseded 2026-10-10 by the corpus re-measurement.** Every figure in the table above is
`worst_wall_error` from the nearest-point minimum, on the body-based station grid. A converging
measure run over all 28 saved walls on a grid that reaches the thin regions puts **none of the 14
fully measured walls inside `WALL_TOL`**, and puts the nose at `U` = 3.0 — the one column entry
that read inside tolerance here — at 0.0519 mm rather than 0.0067 mm. The table stands as what the
soak recorded; it is not a statement about compliance. See
[§6.1's convergence entry](#61-measurement-cautions) and
[wall_thickness_measure.md](../implementation/wall_thickness_measure.md).

**One configuration reads inside `WALL_TOL` — the nose at `U` = 3.0, at 0.0067 mm against 0.01 mm
— and that is not evidence of compliance.** It falsifies a claim that stood in
`cowl_interior.WALL_TOL`'s own note until this run, that the tolerance was unmet "at every `U`
measured", and the note is corrected. But the first correction overstated the other way, calling
this reading evidence that the construction can reach the tolerance, and **§6.1 is why it is not**:
`worst_wall_error` is `max(0, t - worst_low)`, and `worst_low` is a nearest-point minimum that does
not converge on these sections — still falling at 3840 inner samples at 17 of 24 stations, while
this check samples `AROUND` = 240. The drift runs one way, toward thinner, so a reading *under* the
tolerance at 240 samples is a lower bound that would be expected to rise past 0.01 mm under finer
sampling, exactly as every other station's did. Read the whole column as "`WALL_TOL` compliance is
not demonstrated", which is what `check_cowl_interior` itself prints, and not as twelve verdicts of
which one passed. What the non-monotonicity above removes is the belief that the gap is uniform;
what §6.1 removes is the belief that any of these figures is a settled deviation.

**`partition_slip` remains unusable as a quality indicator, and this corpus adds a second reason
why.** §6.1 already records that it moved monotonically *toward* zero as a known defect worsened.
Here it spans three and a half decades across the corpus with no relation to wall error: its
largest value, the tail's 3.66e-04 at `U` = 1.0, belongs to that kind's *second best* wall error
(0.0243 mm), while the tail's worst wall error by a factor of three (0.1506 mm at `U` = 4.0) has
a slip of 3.20e-07, among the lowest recorded. Read it as a boolean on the partition having
closed at all, nothing more.

**Measurement cost is now the tail's problem, not the nose's.** Nose builds take 38–117 s to
build and 50–140 s to measure; the tail takes 727–4 530 s to build against 146–346 s to measure.
The five tail repeats at `U` = 4.0 are 4 870 s each and are 58 % of the corpus's total wall-clock
on their own. Any future soak that adds configurations should add them on the nose, or add
repeats only where a specific pair is in question.

**This supersedes §9.7's `U` = 1 column**, which predates the three fixes in §9.8 and reports a
different wall for both kinds (9 714.2617 and 23 685.2264 mm³ against 9 710.4721 and
23 704.2956). §9.7's station counts are refinement stations; the 12 stations this corpus records
per build are `check_cowl_interior.STATIONS`, the fixed measurement grid, and carry no
information about the construction.

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
  produces. **Measured corpus-wide in §6.5:** the prediction is conservative at `U` ≤ 2 and
  optimistic by 0.11–0.17 mm at `U` ≥ 3, so what remains a limit is not the residual's size but
  that nothing in this pass detects which regime it is in.

- **`shell_solid()`'s cut can return the cell wall in more than one solid.** §7 carries the failure
  itself; what remains a *limit* is that only one of the two reproduced stations has a mechanism.
  `z` = -60.0000 is the near-duplicate station pair of §4.1 acting through §6.2's C² forcing term,
  and alternative 2 of [OQ-DES-CW24](cowl.md#open-questions) (closed 2026-10-04) fixes it.
  **`z` = -294.1530 is unexplained**, and three candidate predictors — absolute clearance, crowding
  ratio and row spacing — have each been proposed and refuted by testing. Nothing is to be built as
  a check against it until the mechanism is characterized; that is alternative 4, and the work item
  is [IP-FC-146](../implementation/freecad_migration.md#work-items).

- **The silent failure mode is reproduced, and the existing checks are therefore not sufficient**
  (IP-FC-145, 2026-10-04). A 0.03 mm row displacement at the real notch-edge station
  `z` = -283.9951339, whose nearest neighbouring row is 0.4311 mm away, returns a wall reading
  0.355705 mm against a 0.546556 mm reference — 0.244 mm under nominal, nearly five times the
  tolerance — with one valid solid, a healthy 2.396e-05 partition slip, a mirror that sews closed
  and no exception anywhere. §7.1 carries the full dose series, the switch behaviour, and the
  arithmetic ruling out the fit as the mechanism. Two things follow. **The claim's recorded
  conditions were wrong**: at the forced four-decimal station the original harness used, the same
  displacement fails loudly instead (`Unconverged`, three of three). And **no statement that the
  construction's checks catch its failures can stand** — one of them does not. What to do about it
  is [OQ-DES-CW26](cowl.md#open-questions).

- **The clearance metrics measure less than their names claim.** A corrected per-wire survey (after
  the `_Polyline` multi-loop bug) does show real thin points — 60 nm worst at `z` = -134.498, 15
  points from 60 nm to 4.1 µm, recurring at a second `U` and on `nose_cowl_shell`'s octant — but a
  single rib binds at each, every one tested is stable, and what that in-plane distance physically
  bounds is unverified. **Metric B is retired** (OQ-DES-CW24 alternative 3): it compares each
  tool's distance to the *surface* and never the tools' positions, so it cannot represent crowding,
  and at one reproduced failure both metrics pass. **Metric A** stays opt-in and flag-only at
  0.01 mm as a rib-cut clearance diagnostic, with its wall-thickness description withdrawn; whether
  it is kept at all depends on a measurement not yet taken, which is
  [OQ-DES-CW25](cowl.md#open-questions).

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
