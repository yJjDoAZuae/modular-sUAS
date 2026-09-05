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

### 9.7 Measured, at `U` = 1

| | nose | tail |
| --- | --- | --- |
| stations, by refinement | 9 | 16 |
| worst wall error against τ = 0.05 mm | 0.0374 mm | 0.0480 mm |
| wall | 9714.2617 mm³ | 23685.2264 mm³ |
| solids / faces | 1 / 503 | 1 / 2480 |
| rib residue | 0.000000 mm³ | 0.000000 mm³ |

---

## 10. Known limits

None of these stops the parts being built or used. They are the shape of what has *not* been
established, and each is a work item in
[freecad_migration.md](../implementation/freecad_migration.md).

- **Only one of the two candidate constructions has ever run** (IP-FC-115). The cavity is
  assembled by cutting the dilated ribs out of the smooth interior and then cutting that out of
  the blank. The same set can be had by cutting the smooth interior out of the blank and fusing
  back the part the ribs occupy, which asks the kernel for two easy booleans and a fuse instead
  of one cut between doubly curved NURBS solids 0.6 mm apart. That comparison was attempted and
  the harness crashed, so it produced nothing. The construction in use is reproducible; it has
  not been shown to be the better of the two.
- **The dilation is brute force** (IP-FC-116). §9.2's horizontal disc is built by fusing 48
  translated copies of each notch solid. It is correct and it is slow: 315 to 336 s of a 571 to
  597 s tail build, and a rib solid of roughly 250 faces where an offset section would give
  about 15. The 48-gon is also only an approximation of the disc — inscribed radius
  `t·cos(π/48)` = 0.99786 `t`, so 0.0013 mm short at the facet midpoints, inside τ but not
  exact.
- **Verified at `U` = 1 only, on three verification builds per kind plus the delivered one** (IP-FC-117). Four full tail builds from
  identical code gave 23623.14, 23623.73, 23627.59 and 23685.23 mm³. **The first three agree
  to 0.019 % and the fourth is 0.26 % away from them, and the two groups are not yet
  comparable:** the three ran `check_cowl_interior.py`, which builds at `cowl_tree`'s own
  parameter rows, and the fourth ran `build_part.py`, which builds at the sweep's overlay. The
  overlay matches those rows on every key the render recorded, so the parts should be the same
  part -- but *should be* is the thing to measure, and until it is measured the 0.26 % is as
  likely to be a difference between two entry points as run-to-run variance. **What is ruled
  out is the obvious explanation:** all four builds chose the same 16 stations, so this is not
  refinement stopping somewhere different. Nothing bounds the spread either way, and §6 measures
  thickness at 12 stations by 240 samples, which cannot see a quarter of a percent spread over
  the whole part. **Isolating that is the first step of this item**, and it is cheap: build the
  same kind through both entry points and difference them. **`U` = 4 is where to expect trouble**: the wall is `n_p·w` = 0.6 mm at every
  `U`, because extrusion width is a property of the machine, so at `U` = 4 that same 0.6 mm
  wraps a part four times the size — proportionally the thinnest shell, and the most surface to
  hold inside a fixed 0.05 mm tolerance.

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
