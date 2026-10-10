"""IP-FC-17: the cowl's interior surface, and the shelled solid it closes.

Implements [doc/design/cowl_interior_surface.md](../../../doc/design/cowl_interior_surface.md),
which is IP-FC-16 and states the method. This module is the construction; that document is
the specification, and where the two disagree the document is right and this is a defect.

**What this produces is the solid representation, never the print export.** Cowls print in
spiral vase mode, which spirals one contour per layer and admits no interior geometry at all,
so a cowl given a modelled inner surface is no longer vase-printable (OQ-DES-CW6,
[cowl.md](../../../doc/design/cowl.md) section 6.4). The un-shelled notched blank stays what
UC-1 exports. That is why the shelled cowls are separate *kinds* -- `nose_cowl_shell` and
`tail_shell` -- rather than an improvement applied to `nose_cowl` and `tail`: two kinds cannot
be mistaken for one another by a downstream consumer, where a flag on one kind can.

The construction, all of it in section 4 of the algorithm document:

    exterior A, notches B
      -> stations z0 ... zn          4.1  feature stations, then refined by 5
      -> sections A(z), B(z)
      -> eroded contours Cin(z)      4.2  by the morphological identity, in the layer plane
      -> consistent parameterization 4.3  arc-length from a geometric anchor
      -> fitted interior surface     4.4  C2 approximation, one patch per feature interval
      -> closed cavity, and the wall 4.5

**A is the un-notched masked body, and it is already in the tree.** Both cowls are built by
masking the scaled OML and then cutting a symmetry cell, so `Lower` -- the blank met with
`lower_mask` -- is the whole body before any notch reaches it, for the nose and the tail
alike. The mirrors that take the cut cell out to the whole part put the notches back over
exactly the region `Lower` already covers, so nothing has to be mirrored a second time to
recover A.

**The OCC entry point is chosen here because the algorithm document deliberately does not
choose one** (its section 8): it states the requirement and the acceptance test, and says an
API named without being measured would read as decided. Measured 2026-09-02 on FreeCAD 1.1.3,
fitting a 24-station superelliptic stack:

    Continuity  DegMax   result
    C1          3        GeomAPI_PointsToBSplineSurface: Surface not done
    C2          3        Surface not done
    C1          5        ok, degree 3, worst point deviation 0.00052 mm
    C2          5        ok, degree 5, worst point deviation 0.00049 mm   <- here
    C2          8        ok, degree 8, worst 0.00077 mm

So `Part.BSplineSurface.approximate` is the entry point, and **C2 is only reachable at
DegMax >= 5** -- the API says so and the measurement agrees, which means a *cubic* C2 fit is
not available through it at all. The interior therefore carries a higher degree than the
cubic exterior it is offset from, and the wall-thickness check is what establishes that this
does not matter in the one place it could.

`ParamType` is left unset deliberately. Naming any of the three -- Uniform, Centripetal,
ChordLength -- made the same fit sixteen times worse (0.0082 against 0.00049), because the
keyword selects a different overload of the underlying algorithm rather than a parameter of
the one above.
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import FreeCAD as App
import Part


#: Section 5: the tolerance on the **wall**, in millimetres, and **absolute at every `U`**.
#: The wall is `n_p * w` thick at every scale because extrusion width is a property of the
#: machine, so a tolerance that scaled with `U` would be 2% of the wall at U=0.5 and 67% of it
#: at U=4. The algorithm document states the reasoning and IP-FC-56 is the precedent for
#: getting it backwards.
#:
#: **What this bounds is the perimeter width, not the distance between two curves.** It used
#: to be the Hausdorff distance from the fitted contour to an ideal eroded contour, which is a
#: proxy: it bounds the wall only indirectly, and it made the acceptance test in
#: `check_cowl_interior` measure a different quantity from the one refinement converged on.
#: Section 5 measures the wall itself -- in the layer plane, from the fitted interior out to the
#: exterior -- so the criterion and the acceptance test measure the same *quantity*.
#:
#: **They are not the same number, and an earlier version of this note said they were.**
#: Corrected 2026-10-05: this is the *convergence criterion* for the fit -- how close the
#: construction has to get before `_refine` stops subdividing -- and `WALL_TOL` below is the
#: *acceptance tolerance* on the finished wall. Measuring one quantity does not make one
#: threshold serve both purposes: a convergence criterion may be as loose as the construction's
#: own budget allows, but the acceptance tolerance is set by what the slicer does with a thin
#: perimeter, and that is five times tighter. Keeping them equal meant the acceptance test
#: inherited the construction's budget instead of the part's requirement, which is backwards.
TAU = 0.05

#: Section 6: the acceptance tolerance on the **finished wall's own thickness**, in millimetres.
#:
#: **One-sided, and five times tighter than `TAU`.** The failure mode this bounds is the slicer
#: declining to lay a perimeter down at all: that decision is near-binary in the wall's measured
#: thickness, and a cowl prints in spiral-vase mode with a single perimeter and no second wall to
#: fall back on (cowl.md section 7), so a wall that comes out materially under `n_p * w` does not
#: print thin -- it prints with a hole. A 25% reduction, 0.6 mm to 0.45 mm, is enough to flip it.
#: That is why this is 0.01 mm and not the 0.1 mm that governs *positional* tolerance on these
#: parts, where bolt clearances are about 0.1 mm and the layer height is 0.2 mm. Position and
#: thickness are different questions with different answers.
#:
#: **One-sided because only the thin side is a defect.** A sample over a rib legitimately reads
#: more than `n_p * w`, because the wall follows the notch in and back out again and the inner
#: contour dips with it -- `check_cowl_interior.wall_thickness` says so, and the real sections
#: read up to 0.69 mm against a 0.6 mm wall for exactly that reason. Only `measured < t - WALL_TOL`
#: is a failure.
#:
#: **Known to be unmet at 11 of the 12 configurations measured, 2026-10-06 -- and met at one.**
#: The full soak corpus (cowl_interior_surface.md section 9.9: both kinds, `U` in {0.5, 1.0, 1.5,
#: 2.0, 3.0, 4.0}, 28 builds) puts `worst_wall_error` between 0.0234 and 0.1506 mm everywhere
#: except the nose at `U` = 3.0, which reads 0.0067 mm and is therefore *inside* this tolerance.
#: An earlier version of this note said "on both kinds, at every `U` measured", which that one
#: reading falsifies. It is corrected here rather than left standing, because the exception is
#: the only direct evidence so far that this construction can reach this tolerance at all.
#:
#: **That single pass does not relax the requirement, because the error is not monotone in `U`.**
#: The same kind one `U` higher reads 0.0495 mm, five times the tolerance, so 0.0067 mm is not
#: the start of a trend to extrapolate -- it is one configuration whose error happens to land
#: low, between neighbours that do not. This constant is the requirement, not a description of
#: what the construction currently achieves; see cowl_interior_surface.md section 6 and
#: [OQ-DES-CW21] for the gap and what is being done about it. It is deliberately recorded as the
#: requirement anyway: a tolerance loosened until the part passes is not a tolerance, and
#: IP-FC-56 is this project's own precedent for that mistake.
WALL_TOL = 0.01

#: The hard floor on interval length, below which `_refine` will not subdivide. **Reaching it is
#: a failure to report, not a result to accept** -- section 5 -- because it means the fitted
#: surface does not represent the erosion there and nothing downstream would know. Since
#: IP-FC-144 both refinement passes *measure* such an interval and report it, where they
#: previously skipped it before measuring; only the subdivision is refused.
#:
#: **This is not the station-seeding floor.** That one is tied to the wall thickness -- see
#: `station_floor()` -- because two stations closer together than the wall they are building
#: make the axial pole track near-degenerate (OQ-DES-CW24, cowl_interior_surface.md section 4.1).
MIN_INTERVAL = 0.20

#: Circumferential spacing, in millimetres, for the grid the surface is **fitted through**,
#: and the range the resulting count is clamped to.
#:
#: **This is set by the shape being fitted, and that shape is smooth.** The surface follows the
#: eroded *body* only; the ribs are applied afterwards, as a solid, so no rib corner is ever
#: fitted through. What is left is a rounded rectangle, and interpolating one needs the points
#: a rounded rectangle needs.
#:
#: It used to be 0.075 mm, derived from the 1.3 mm rib gap the erosion leaves at a notch --
#: an argument about how finely the result must be *checked*, applied to how finely it is
#: *built*. That conflation is what made the construction unaffordable. Every comparison in
#: section 5 is a product of two sample counts, so the cost is quadratic in this number:
#: measured 2026-09-03 on the nose at U = 1, dropping it 32x took the cavity from 5266 s to
#: 30 s.
FIT_ARC = 1.0
FIT_MIN = 120
FIT_MAX = 1200

#: Circumferential spacing, in millimetres, for **evaluating** the fitted surface against the
#: wall tolerance, and the range that count is clamped to.
#:
#: **This is the one the rib sets.** A check that steps over a rib cannot see a wall violation
#: inside it, and the gap the erosion leaves at a notch is `t_cut + 2*n_p*w` = 1.3 mm, so the
#: spacing has to resolve that. 0.20 mm puts six or seven evaluation points across the
#: narrowest feature that can carry a violation.
#:
#: Evaluating is not fitting, and it is far cheaper: a point-to-curve distance against a
#: polyline, not an interpolation through a grid. Spending the samples here rather than in
#: `FIT_ARC` is the whole point of keeping the two apart.
CHECK_ARC = 0.20
CHECK_MIN = 480
CHECK_MAX = 6000

#: How many directions the ribs are dilated in. See `dilated_notches`: the structuring element
#: is a horizontal disc, and it is approximated by an inscribed regular polygon with this many
#: sides.
#:
#: **Chosen against the rib gap, which is the thing it has to get right.** Measured 2026-09-03
#: on the tail's first side slab at U = 1, whose 0.1004 mm section the exact 2-D offset dilates
#: to a 1.3004 mm gap:
#:
#:     n = 32    gap 0.3670 mm    volume 10543.589    <- wrong shape, not merely coarse
#:     n = 48    gap 1.3004 mm    volume 11096.319    4.0 s a tool
#:     n = 64    gap 1.3004 mm    volume 11097.462    8.6 s a tool
#:     n = 96    gap 1.3004 mm    volume 11098.575   23.6 s a tool
#:
#: 48 is the first count that reproduces the exact offset's gap, and going further buys three
#: parts in ten thousand of volume for twice the time.
#: **48 is a floor, not a tuning knob.** The copies sit on a circle of radius `t`, so adjacent
#: ones are `2*t*sin(pi/N)` apart, and their union is a solid only while that is smaller than
#: the slab's in-plane thickness. The thinnest cut here is 0.1 mm, which needs
#: `N > pi / asin(0.1 / 1.2)` = 37.6, so **38 facets minimum and 48 leaves 26 % headroom**.
#: Below the floor the union is a comb and the wall comes out with material missing -- measured
#: at N = 24, where the tail lost 1332 mm3 and two stations reported 0.1035 mm of wall. The
#: check in `dilated_notches` derives this per tool rather than trusting the number here.
#:
#: The count is also what makes the polygon approximate a disc: inscribed, it under-dilates by
#: `t * (1 - cos(pi/N))` at the facet midpoints, which is 0.0013 mm at 48 against a 0.05 mm wall
#: tolerance. That error is negligible at any N the floor above permits, so it is the floor and
#: not the accuracy that decides the count.
RIB_FACETS = 48

#: Below this, a cutting slab's plane is horizontal and P4 is violated.
#:
#: **A numerical guard, not a design threshold.** The value is the sine of the angle between
#: the cut plane and the layer plane, so 1 is a vertical cut and 0 is a horizontal one; this
#: only separates "horizontal" from "not horizontal" through floating-point noise, and it is
#: deliberately not a limit on how shallow a cut may be. P4 says no notch *lies in* the layer
#: plane, because a rib forms only where the perimeter can walk into the notch and back out
#: within a layer -- a horizontal notch offers no such path and comes out malformed under
#: thin-wall perimeter slicing. It does not say a 5-degree cut is acceptable and a 4-degree one
#: is not. Nothing in the design is shallower than the tail's 30-degree diagonal, no minimum
#: angle is stated anywhere, and picking one here would be inventing a design decision in a
#: constant. If a floor is ever wanted it is an open question, not a number in this file.
#: Meanwhile `dilated_notches` reports the shallowest cut it saw, so a shallow one is visible
#: rather than silent.
FLAT_TOL = 1.0e-9

#: How much dilated rib may remain inside the finished cavity, in cubic millimetres.
#:
#: **Zero is the right answer and the measured one.** `cavity` subtracts the dilated ribs from
#: the smooth interior, so afterwards the two must not intersect at all: on a correct build,
#: measured 2026-09-04 on the tail at U = 1, `cavity.common(ribs)` is 0.000000 mm3 in 0 solids.
#:
#: **And this is the check that catches the failure the others miss.** The rib cut fails
#: *partially*, which nothing downstream notices. Measured on the same part: the wall is
#: 23745.5810 mm3 in one solid when every rib forms, 17041.8581 mm3 in five when the ribs are
#: not cut at all, and the bad builds came out around 22000 in five -- about a quarter of the
#: 6703.7229 mm3 of rib material missing. The ribs are what bridge the buttress slots, so
#: losing some of them is what separates the wall into pieces, and the partition identity in
#: `shell_solid` cannot see it because the result is still self-consistent: the cavity is
#: simply larger, and it eats the wall.
#:
#: The floor is five orders below that failure and three above the kernel's own reproducibility
#: on these operands.
RIB_RESIDUE = 1.0e-2

#: A small fuzzy-boolean tolerance for the rib cut (`smooth.cut`) and its retry, and for the
#: residue check (`common`) that reads them. **Not a design dimension -- a numerical-robustness
#: setting for one specific, reproduced boolean-kernel failure.**
#:
#: Found 2026-09-21 at the tail's `U` = 0.75: `cavity()` refuses a cavity split into more than
#: one solid (there is no scale at which that is legitimate -- a rib is what bridges a buttress
#: slot, so a split cavity means one did not), and this `U` split. Traced to a single tool,
#: `Diag12Safe`, in isolation from the other ten: cutting `smooth` by its dilation alone
#: reproduces the identical split, a genuine zero-volume sliver (`0.000000` mm3, bounding box
#: 0.17 mm wide) pinched off where the dilated diagonal grazes the interior surface at a shallow
#: near-tangent angle. This is not rib crowding -- the same mechanism IP-FC-137's synthetic H3
#: test found and then ruled out against real geometry -- it is one tool's own boundary nearly
#: touching the cavity's, the same class of near-coincident-geometry degeneracy this module
#: already works around for the mirror step (`_strip_seam`) and the cell-level cut
#: (`_extend_across_cell`), here inside the ordinary rib cut instead.
#:
#: **Chosen empirically, and it is not free of side effects at any size.** `1.0e-6` left the
#: split in place; `1.0e-5` closed it into one valid solid with the real piece's volume moved by
#: 0.0006 mm3 in 122902.77 (4.9e-9 relative) -- a snap of the near-tangent geometry together, not
#: a bulk change; `1.0e-4` and above moved the volume by tens of mm3, well past what a tangency
#: snap should cost. `1.0e-5` is three orders below `RIB_RESIDUE` and four below `TAU`, so it
#: cannot be mistaken for tolerating a real gap.
RIB_CUT_FUZZ = 1.0e-5

#: How many times `cavity` will re-cut the finished wall against section 5's second pass
#: (IP-FC-143, OQ-DES-CW21) before giving up and raising `Unconverged`.
#:
#: **A round count, not a station count, because the expensive step it bounds is the cut, not
#: the fit.** The smooth-surface pass already has its own station budget (`budget`, the
#: parameter); this loop can insert well inside that budget and still be expensive, because
#: every round re-runs the rib cut and its residue/connectivity checks -- the ~150-350 s step
#: IP-FC-116 measured, not the cheaper surface fit.
#:
#: **The gap this pass exists for does not close quickly.** Tested directly before this was
#: written (IP-FC-143, 2026-09-25): uniformly tightening `tau` 5x moved most flagged stations
#: toward `t` but left the single worst one barely changed (+0.0012 mm of a 0.0531 mm deficit).
#: A handful of rounds is enough to see whether targeted insertion is converging at all without
#: paying for an open-ended retry loop on a build that will not close the gap regardless.
POST_CUT_ROUNDS = 6

#: How close (mm) a discretised section point may sit to a cell construction plane before
#: section 5's second pass drops it, on both sides of every comparison it makes.
#:
#: **Shared by `_finished_wall_gap`'s own default and `cavity`'s `finished_outer_at`, and it
#: must stay shared.** Both slice a cell-shaped solid and discretise the whole closed loop
#: rather than `open_arc`'s stripped one -- `_finished_wall_gap` for the cavity's own boundary,
#: `finished_outer_at` for the buttress-cut cell's exterior -- so the same zone has to be
#: excluded from each side of the same comparison, or the surviving points on one side would be
#: measured against a polyline whose closing chord, on the other side, still crosses it.
FINISHED_PLANE_TOL = 0.5

#: How far (mm) each side of a notch tool's own edge (ramp start/end, cut plane -- read via
#: `feature_stations`) section 5's second pass samples extra finely, and how far apart (mm)
#: those extra samples sit.
#:
#: **Additive, not a replacement for the uniform scan.** The uniform ~1 mm grid still runs
#: everywhere, so a defect at some other, not-yet-seen location is still caught; this only adds
#: density exactly where the mechanism this item's own investigation found (IP-FC-143) says the
#: sharp local peak actually lives -- a notch tool's own boundary, not its interior. Measured
#: 2026-09-25/26: even a 1 mm-spaced uniform scan alone landed 0.0453-0.0471 mm against the
#: acceptance check's own 0.0531 mm at the one real flagged station measured this closely --
#: consistently short by about the same amount a scan missing a sharp peak by a millimetre or
#: two would be, not a difference in what is being measured (that question is settled: section 5
#: now measures against `notched`'s real exterior, not `body`'s). Getting closer requires finer
#: sampling exactly at the peak, not everywhere -- a uniform grid fine enough to guarantee that
#: unaided (sub-millimetre, over a whole 300 mm patch) would multiply this pass's own cost by an
#: order of magnitude for resolution almost none of the patch needs.
#: **The edge, not the notch's interior.** `feature_stations` already returns exactly the
#: axial positions a rib's own ramp starts, ends, or meets the cut plane -- the points a smooth
#: fitted surface cannot help but approximate least well, the same reason `_patches` treats them
#: as patch boundaries for the pre-cut fit. The window is centred on each one.
#: **Coarsened, 2026-09-27 (OQ-DES-CW22), now that the fit itself is front-loaded with these same
#: edges.** At 2.0/0.25 this scan alone measured 373-442 points a patch -- more than the rib cut
#: it was meant to be cheap next to -- and that was before OQ-DES-CW22 found the *uniform* scan
#: dominates the real cost anyway. Once `_refine`'s own seed already carries every notch edge
#: (added the same day, above), the fitted surface is already well-resolved there before the
#: first cut ever happens, so this scan's own job shrinks from "find the peak" to "confirm it",
#: which does not need the same density.
EDGE_SCAN_MARGIN = 1.0
EDGE_SCAN_STEP = 0.5

#: How far (mm) each side of an inserted station section 5's second pass re-scans on the round
#: that follows, instead of the whole patch.
#:
#: **Measured, not assumed (OQ-DES-CW22, 2026-09-26).** One properly-bisected insertion's effect
#: on the finished wall's own thickness, on `tail_shell` `U` = 1.0: -0.023 to -0.024 mm within a
#: millimetre of it, -0.005 to -0.01 mm by 9 mm, under +-0.005 mm by 14 mm, and at most
#: +-0.0012 mm (2.4% of `TAU`) anywhere past 20 mm -- consistent with numerical noise at that
#: range, not a continuing effect. 20 mm keeps a margin over the 14-15 mm the effect actually
#: reached in that measurement.
#: **Why re-scanning at all is safe to skip beyond this window.** Patches are independent: a
#: change to one patch's own fit and cut cannot move another patch's cavity boundary, since each
#: contributes its own closed solid to the fuse and the fuse cannot alter geometry outside the
#: piece that changed. Within one patch, the same locality this margin measures is what makes it
#: safe to stop looking past it.
POST_CUT_RESCAN_MARGIN = 20.0

#: How many times finer the polyline a distance is *measured against* is than the sample set.
#:
#: **Three, not eight, because the sample set now carries the resolution.** When `CHECK_ARC`
#: was 0.3 mm this factor had to make up the difference on its own; at 0.075 mm a factor of 3
#: already puts 0.025 mm between the chords being measured against, which is a fiftieth of
#: `TAU`. Eight cost 40,832 points per contour on the tail -- one `discretize` and one polyline
#: build of that size for every station -- and measured 463 s a contour for accuracy nothing
#: needed.
#: **The measurement is curve-to-curve and the discretisation error has to sit well below
#: `TAU`.** Measured 2026-09-02: comparing 160 sampled points against a 160-point
#: parameter-spaced polyline of the same contour reported 0.076 mm where the true deviation
#: was 0.003 mm -- twenty-five times over, and over `TAU`, so the refinement chased its own
#: chord error down to the interval floor and reported a part that does not converge.
#: `discretize` spaces by *parameter*, not arc length, so its chords cut the corners wherever
#: the curve's speed varies, which on a rounded-rectangle section is everywhere.
DENSE_FACTOR = 3

#: Stations seeded in a patch before section 5 refines it, per millimetre of patch length,
#: and the range that is clamped to. **The seed is deliberately thin and the criterion is the
#: arbiter**, which is what "spacing is derived, not tuned" means: a patch seeded with two
#: stations and left there is one where the midpoint check found the surface already within
#: `TAU` of the erosion. Seeding six everywhere instead cost 23 minutes a part on a tail whose
#: 59 feature stations make 60 patches, most of them a fraction of a millimetre long, and
#: bought nothing the criterion did not already guarantee.
#: A patch at least this long is seeded with the six stations a C2 fit needs; a shorter one is
#: seeded with its two ends and left for section 5 to subdivide if the erosion turns out not to
#: be straight across it. Below six rows `approximate` cannot produce C2 at all -- it raises
#: `NCollection_Array1::Value`, measured 2026-09-02 -- so this is where the continuity ladder
#: in `_fit` gets its rows from.
SEED_LONG_MM = 3.0
SEED_MIN = 2
SEED_MAX = 6

#: Target spacing, in millimetres, for the uniform samples a section is refit through, and the
#: range the resulting count is clamped to. See `eroded_body` for why the spacing has to be
#: uniform and why there is a ladder above it.
SAMPLE_SPACING = 0.25
SAMPLE_MIN = 400
SAMPLE_MAX = 3000

#: How far a section may move when it is refit as one B-spline, in millimetres. A tenth of
#: `TAU`, because the refit is of the *exterior* the wall is measured from: an error here is
#: not a fitting error to be refined away but a changed part, and it would show up in the
#: wall-thickness check as a bias no station disagrees with.
REFIT_TOL = 0.005

#: Fuzzy tolerances tried, in order, for the one boolean that needs one: taking the dilated
#: notches out of the eroded section. Millimetres. Unused since the ribs became a 3-D cut; see
#: ladder climbed against the result rather than a single value.
#:
#: The ceiling is a fifth of `TAU`, which bounds the whole mechanism: whichever rung answers,
#: the section cannot have moved by more than that, and `TAU` is itself a twelfth of the wall.
CUT_FUZZ_LADDER = (1.0e-5, 1.0e-4, 1.0e-3, 1.0e-2)

#: Below this area, in square millimetres, a clipped notch section is a tangency artifact and
#: not a notch. The narrowest notch the design has is `buttress_cut_thickness` = 0.1 mm wide,
#: so even a 0.1 mm long one encloses 0.01 mm2 -- four orders above this.
SLIVER_AREA = 1.0e-6

#: Below this perimeter, in millimetres, a loop left by the notch subtraction is boolean debris
#: rather than a hole. See `_one_region`, which records why the floor sits where it does and
#: what it is checked against.
SLIVER_LENGTH = 0.01

#: How far inside its own end a station may sit. Sectioning exactly at a planar end returns the
#: end face's boundary rather than the body's, which is the same curve for a prismatic part and
#: not for this one.
END_INSET = 1.0e-3

#: How far past each open end the cavity is carried, so the ends are actually open. Any value
#: clear of `END_INSET` does; 1 mm is far enough to be unambiguous and short enough to stay
#: inside the blank's own bounding box arithmetic.
END_OVERRUN = 1.0

#: Two stations closer than this are one station.
Z_TOL = 1.0e-6

#: Slack on the P1 slope assertion, in degrees, for the discretisation the check runs on.
SLOPE_SLACK = 0.5

#: Angular half-window, in bins of one degree, searched when measuring a point against a
#: polyline. Both contours are star-shaped about the section centroid -- a 1.3 mm slot in a
#: body tens of millimetres across leaves them so -- which makes the nearest segment a local
#: one and turns an O(n*m) scan into an O(n) one. 25 degrees is far wider than any nearest
#: point observed and is what makes the pruning safe rather than merely fast.
ANGLE_WINDOW = 25

#: Metric A's thin-wall flag threshold (mm), `clearance_margin_scan`'s own criterion
#: (OQ-DES-CW24, cowl.md) -- **not** the project's usual 0.1 mm print-accuracy figure.
#:
#: That 0.1 mm is a *positional* tolerance -- where a bolt-clearance feature sits -- and does
#: not apply here. Wall *thickness* is a different quantity: these cowls print in spiral vase
#: mode, a single extrusion perimeter with no redundancy, and the slicer makes a near-binary
#: decision whether to extrude a perimeter at all based on its thickness. A 0.1 mm change (e.g.
#: 0.4 mm to 0.3 mm, a 25% reduction) can flip that decision and drop the wall entirely, so
#: 0.1 mm is too coarse a flag line for this check. 0.01 mm sits comfortably above every
#: confirmed single-rib near-tangency this item measured (48 nm to 4.1 um across both cowl
#: kinds and two `U` values) and far below the scale at which a slicer's own perimeter decision
#: is at risk.
#:
#: **Flag-only, never a gate.** A single rib's own near-tangency to the surface was tested
#: directly (`debug_single_rib_fragility.py`, three points, the full 0.001-0.1 mm perturbation
#: range) and stayed one valid solid throughout, with no `Unconverged` and no sign reversal.
#:
#: **What this distance physically bounds is not established, 2026-10-03.** It is an in-plane
#: distance from the candidate surface's slice to a tool's slice, and nothing checks whether the
#: minimum lies on the tool's *cut floor* -- the face that actually limits the finished wall --
#: or on a flank, which limits nothing. Measured against the real `wall_thickness()` at four
#: stations, this number varied by a factor of 2.5 (0.085222 to 0.213606 mm) while the real wall
#: varied by 4.9% (0.562703 to 0.589999 mm), and the two orderings disagree. Treat it as a
#: rib-cut clearance diagnostic, not as a wall-thickness measurement, until that is resolved.
#:
#: **It does not predict construction failure, and was never meant to.** An earlier version of
#: this note said crowding -- two tools comparably close at once -- is what causes the
#: construction to fail. That attribution is withdrawn (OQ-DES-CW24, 2026-10-03): it rested on a
#: companion ratio, "Metric B", which compared distances to the *surface* and never the tools to
#: each other; it was removed outright on 2026-10-04 (IP-FC-147). At `z` = -60.0000 on
#: `tail_shell` `U` = 3.0 this metric reads 0.097097 mm -- comfortably passing, as did the ratio
#: at 5.950x -- and a 0.01 mm row displacement there still severs the wall. `shell_solid()`'s own
#: solid-count and partition checks catch that; this constant does not and should not be expected
#: to.
#:
#: **Whether this metric is kept at all is OQ-DES-CW25**, which turns on a measurement nobody has
#: taken: only a tool's cut floor bounds the wall, its flanks bound nothing, and the minimum here
#: is taken against the whole tool section without distinguishing them.
CLEARANCE_MARGIN_MM = 0.01


# **Do not test a section for emptiness with `Face.Area`.** A planar face built on a single
# closed periodic B-spline -- which is exactly what `smoothed()` produces and what every
# section here is -- reports an area that is simply wrong, while its geometry is right.
# Measured 2026-09-02 at three stations on the tail:
#
#     station     wire signed area   Face.Area    offset(-0.6) area
#     -97.9004         9912.153       7588.258         9683.637
#     -60.0000         7048.147       5800.412         6856.579
#     -42.5001         5045.318       5029.483         4883.383
#
# The signed area of the wire matches the un-refit section to 1e-5 relative, the perimeter
# matches to 1e-5, and the offsets match the un-refit section's offsets to 1e-5 -- so nothing
# about the curve is wrong. Only `Face.Area` is, and it is wrong by up to 23% and by a
# different amount at every station, which makes it read as a real geometric signal. This is
# `Shape.Volume` on a NURBS solid one dimension down (OQ-DES-CW12). Count faces, or take the
# signed area of the discretised wire.


def note(text):
    """One progress line, to stderr, flushed.

    **A build that says nothing for twenty minutes is indistinguishable from a hung one**, and
    this one legitimately takes that long: every station is three kernel booleans on a NURBS
    section, and a cowl has scores of them. Without this the only way to tell work from a hang
    is to watch the process's CPU time from outside, which is not a thing anyone should have to
    do to find out whether their machine is busy on purpose.
    """
    sys.stderr.write('    %s\n' % text)
    sys.stderr.flush()


class PreconditionFailed(Exception):
    """A property section 2 relies on does not hold of this input.

    Raised rather than worked around. Each of the three is a statement about the *design*,
    not about the kernel, so one failing means a part is outside the domain the method was
    written for and the answer is to say which station and stop -- not to emit the knife edge,
    which renders, exports, passes `isValid()` and resurfaces as a stress singularity in a
    UC-8 result nobody re-derives by hand.
    """


class Unconverged(Exception):
    """Section 5's floor was reached with the deviation still above `TAU`."""


# --------------------------------------------------------------------------------
# Plane geometry, in the layer plane
# --------------------------------------------------------------------------------

def _signed_area(pts):
    """Twice the signed area of a closed polyline, positive counter-clockwise about +z."""
    total = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        total += x1 * y2 - x2 * y1
    return total


def _wire_area(wire, n=200):
    """The area a closed wire encloses, from its own points rather than from `Face.Area`."""
    pts = [(p.x, p.y) for p in wire.discretize(Number=n)]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return abs(_signed_area(pts)) / 2.0


def _seg_distance(px, py, ax, ay, bx, by):
    """Distance from a point to a segment. Point-to-segment rather than point-to-point
    because section 5 measures against `TAU` = 0.05 mm and the sampling interval is 1 mm."""
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    if den <= 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / den
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class _Polyline(object):
    """A polyline you can measure many points against at once, closed by default.

    **Vectorised because the measurement, not the geometry, was the cost.** Section 5 compares
    every sample of a contour against a dense polyline of another, both sides, at every
    midpoint of every patch -- and the sampling has to resolve a 1.3 mm rib, which puts
    thousands of points on each side. In pure Python that measured 70 s per contour and made
    the whole construction unaffordable at the resolution it actually needs. The arithmetic is
    a point-to-segment distance, which is the same three lines for every pair, so it belongs in
    numpy rather than in a loop.

    **`closed=False` for an open cell arc, and that is not optional.** The default wraps the
    last point back to the first with `np.roll`, which is right for a full loop and wrong for
    an open one: it silently adds a chord straight across the two cut-plane ends, and a point
    near that end -- which is exactly where an eroded interior arc's own ends sit, by
    construction -- then measures as a few nanometres from the *chord* rather than from the
    true exterior, reporting a wall gap of zero instead of `t`. Measured on the tail at
    `U` = 0.5: the worst wall error read exactly 0.6000 mm, unmoving across four refinement
    passes, because the check was seeing the chord, not the surface.

    Queries run in chunks: the full (points x segments) matrix would be hundreds of megabytes
    at the resolutions this now uses, and nothing is gained by materialising it at once.
    """

    CHUNK = 256

    def __init__(self, pts, closed=True):
        self.pts = pts
        a = np.asarray(pts, dtype=float)
        b = np.roll(a, -1, axis=0)
        if not closed:
            a = a[:-1]
            b = b[:-1]
        self.ax, self.ay = a[:, 0], a[:, 1]
        self.dx, self.dy = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1]
        self.den = self.dx * self.dx + self.dy * self.dy
        self.den[self.den <= 0.0] = 1.0e-300

    def distances(self, points):
        """Distance from each of `points` to this polyline, as an array."""
        q = np.asarray(points, dtype=float)
        out = np.empty(len(q))
        for lo in range(0, len(q), self.CHUNK):
            hi = min(lo + self.CHUNK, len(q))
            px = q[lo:hi, 0][:, None]
            py = q[lo:hi, 1][:, None]
            t = ((px - self.ax) * self.dx + (py - self.ay) * self.dy) / self.den
            np.clip(t, 0.0, 1.0, out=t)
            ex = px - (self.ax + t * self.dx)
            ey = py - (self.ay + t * self.dy)
            out[lo:hi] = np.sqrt(np.min(ex * ex + ey * ey, axis=1))
        return out

    def distance(self, px, py):
        return float(self.distances([(px, py)])[0])

    def closest(self, points):
        """The single nearest pair over `points`, as `(distance, query_point, point_on_self)`.

        `distances` reduces away the one thing IP-FC-148 needs. It keeps each query point's own
        minimum distance, which is all a clearance number requires, but OQ-DES-CW25 turns on
        *where* on the tool that minimum lands, and a scalar cannot say. Same point-to-segment
        arithmetic and the same chunking; only the bookkeeping differs, so the distance this
        returns is the distance `distances` would have returned for the same inputs.
        """
        q = np.asarray(points, dtype=float)
        best = None
        for lo in range(0, len(q), self.CHUNK):
            hi = min(lo + self.CHUNK, len(q))
            px = q[lo:hi, 0][:, None]
            py = q[lo:hi, 1][:, None]
            t = ((px - self.ax) * self.dx + (py - self.ay) * self.dy) / self.den
            np.clip(t, 0.0, 1.0, out=t)
            cx = self.ax + t * self.dx
            cy = self.ay + t * self.dy
            d2 = (px - cx) ** 2 + (py - cy) ** 2
            flat = int(np.argmin(d2))
            i, j = flat // d2.shape[1], flat % d2.shape[1]
            if best is None or d2[i, j] < best[0]:
                best = (float(d2[i, j]), lo + i, (float(cx[i, j]), float(cy[i, j])))
        if best is None:
            return None
        return (math.sqrt(best[0]), (float(q[best[1], 0]), float(q[best[1], 1])), best[2])


def hausdorff(a_samples, a_dense, b_samples, b_dense):
    """The two-sided Hausdorff distance between two closed contours.

    **Two-sided, per section 5 step 4.** One-sided misses a fitted contour that bulges outward
    where the true one has no material: every point of the true contour still has a fitted
    point near it, and the excursion goes unmeasured.

    Each side's *samples* are measured against the other side's *dense* polyline, so what is
    reported is the distance between the curves and not the distance between two coarse
    approximations of them.
    """
    return max(float(b_dense.distances(a_samples).max()),
               float(a_dense.distances(b_samples).max()))


def _min_wire_distance(wires_a, wires_b):
    """Minimum in-plane distance between two sets of wires at the same station, each wire's
    own closed loop measured separately.

    **Never flatten more than one wire into one `_Polyline` call.** `_Polyline` defaults to
    `closed=True`, wrapping the last point of its own argument back to the first -- correct for
    one real closed loop, but when the points of two or more separate wires are concatenated
    first, that wraparound manufactures a phantom chord connecting the end of one loop to the
    start of an unrelated one. That chord can cut straight across the middle of a cross-section
    and read as an arbitrarily small "distance" with no geometric meaning at all -- found
    investigating OQ-DES-CW24 (cowl.md): a fused multi-rib tool's own slice has 6 to 57 separate
    wire loops at a typical station, not one, and every clearance figure measured against it
    this way was retracted and re-measured once this was found. Each wire here closes correctly
    on its own, and only the per-wire minimum is finally reduced.
    """
    if not wires_a or not wires_b:
        return None
    a_pts = []
    for w in wires_a:
        a_pts.extend((p.x, p.y) for p in w.discretize(Number=200))
    if not a_pts:
        return None
    best = None
    for w in wires_b:
        pts = [(p.x, p.y) for p in w.discretize(Number=400)]
        if len(pts) < 2:
            continue
        d = float(min(_Polyline(pts).distances(a_pts)))
        if best is None or d < best:
            best = d
    return best


def _min_wire_contact(wires_a, wires_b):
    """`_min_wire_distance`'s own minimum, with the pair of points that realizes it.

    Sampled exactly as `_min_wire_distance` samples -- 200 points per `wires_a` loop, 400 per
    `wires_b` loop, each loop closed on its own and never flattened together, for the reason
    that function's own note gives -- so the distance returned here is the number Metric A
    reports and not a second, differently-sampled approximation of it.

    Returns `(distance, (ax, ay), (bx, by))`, or `None` where `_min_wire_distance` returns it.
    """
    if not wires_a or not wires_b:
        return None
    a_pts = []
    for w in wires_a:
        a_pts.extend((p.x, p.y) for p in w.discretize(Number=200))
    if not a_pts:
        return None
    best = None
    for w in wires_b:
        pts = [(p.x, p.y) for p in w.discretize(Number=400)]
        if len(pts) < 2:
            continue
        got = _Polyline(pts).closest(a_pts)
        if got is not None and (best is None or got[0] < best[0]):
            best = got
    return best


# --------------------------------------------------------------------------------
# Sections and the erosion
# --------------------------------------------------------------------------------

def _slice_wires(shape, z):
    return shape.slice(App.Vector(0, 0, 1), z)


def smoothed(wire, n, tol=REFIT_TOL):
    """One closed cubic B-spline through a section, replacing the fragment chain OCC returns.

    **This is what makes the erosion possible at all, and it is not a nudge.** Sectioning the
    conditioned blank returns the section as one edge per surface patch -- 64 of them on the
    tail -- and on the smaller forward sections the shortest of those is under 0.05 mm. OCC's
    2-D offset refuses that input: measured 2026-09-02 over 81 stations, 19 returned
    `makeOffset2D: result of offsetting is null!`, every one of them forward of z = -42.5 where
    the section has shrunk enough to bring the fragments below a tenth of a millimetre. Neither
    join style, nor `intersection`, nor `removeSplitter`, nor a 1600-point polygon changed any
    of them; a single B-spline through the same points offset correctly on the first try.

    That is IP-FC-54's failure exactly -- the algorithm document's section 7 predicts it and
    warns that hunting for an offset distance that works leaves the defect in place. The defect
    here is the fragmentation, so the fragmentation is what is fixed.

    **Every station is smoothed, not only the ones that fail.** Two constructions across a stack
    of contours would put a systematic step between a station offset directly and its neighbour
    offset from a refit, and the path that runs on 62 stations of 81 is not the path that gets
    exercised when something breaks.

    The refit is *verified*, which is the whole difference between substituting a curve and
    assuming one: the original wire is sampled densely and every sample must lie within `tol`
    of the new curve, or the build stops. Without that this would be a silent change to the
    exterior the wall is measured from.
    """
    pts = wire.discretize(Number=n)
    if pts[0].distanceToPoint(pts[-1]) < Z_TOL:
        pts = pts[:-1]
    curve = Part.BSplineCurve(pts, None, None, True, 3, None, False)
    shape = curve.toShape()

    # Measured against a dense polyline of the new curve rather than by `distToShape` per
    # point: the curve interpolates the `n` samples exactly, so what is being checked is what
    # it does *between* them, and 4n `distToShape` calls on a B-spline cost more than the
    # erosion they are guarding.
    dense = _Polyline([(p.x, p.y) for p in shape.discretize(Number=4 * n)])
    worst = float(dense.distances(
        [(p.x, p.y) for p in wire.discretize(Number=2 * n)]).max())
    return Part.Wire(shape), worst


def eroded_body(wire, t, z, tol=REFIT_TOL):
    """The refit section, its face, and the face eroded by `t` -- refining until all three work.

    **Superseded 2026-09-21 by the cell/arc method (`cell_boundary_planes`, `open_arc`,
    `eroded_arc`) and not safe to call on a symmetry-cell section.** `cavity()` no longer calls
    this: `wire` here is fit as one periodic B-spline through every point of the raw loop, which
    is only correct for a genuinely closed, construction-boundary-free exterior. A cell's own
    section (`half`/`octant`, `tip.Body`) is a closed loop only topologically -- part of it is
    the cell's own straight construction edge -- and fitting a single periodic curve through
    that is exactly the anti-pattern `cell_boundary_planes`'s own comment names: it cannot hold
    the straight edge straight and the curved OML edge curved at the same point, so it rounds
    the corner. `check_cowl_interior.rib_gap()` called this on cell input until that was found
    to be the cause of a P3 failure on essentially every real station (0.016-0.026 mm, not
    converging with more samples, because the corner it was rounding is a fixed feature of the
    section rather than a sampling shortfall) -- fixed by moving `rib_gap()` to `open_arc` /
    `eroded_arc`, the same route `cavity()` takes. Kept here, unused, only because it remains a
    correct implementation of the different problem it was written for: a wire with no
    construction boundary at all.

    **Uniform sampling, and a ladder rather than one attempt.** Measured 2026-09-02 on the nose
    at z = -29.79, a 355 mm section, every refit verified against the original wire:

        413 points spaced by deflection    moved 0.0027 mm   offset FAILED
        300 points spaced uniformly        moved 0.0219 mm   offset ok
        600 points spaced uniformly        moved 0.0065 mm   offset ok
       1200 points spaced uniformly        moved 0.0019 mm   offset ok

    Deflection sampling puts points where the curvature is, which is the right instinct and the
    wrong result: the uneven spacing leaves the interpolant with local wiggles, and a 0.6 mm
    offset of a wiggle self-intersects and returns null. The count is not what decides it --
    413 uneven points fail where 300 even ones succeed -- so the fix is the spacing, and the
    ladder is there because the *deviation* still needs enough points to come inside `tol`.

    Both conditions are checked on every rung, and reaching the end of the ladder is a failure
    to report rather than a coarser answer to accept.
    """
    n0 = max(SAMPLE_MIN, min(SAMPLE_MAX, int(wire.Length / SAMPLE_SPACING)))
    why = None
    for n in (n0, 2 * n0, 4 * n0):
        refit, moved = smoothed(wire, n, tol)
        if moved > tol:
            why = ('refitting at %d points moved the section %.6f mm, over the %.6f mm '
                   'allowed' % (n, moved, tol))
            continue
        face = Part.Face(refit)
        try:
            inner = face.makeOffset2D(-t, 0, False, False, True)
        except Exception as exc:                       # noqa: BLE001 -- reported below
            why = 'the refit at %d points (%.6f mm) would not offset: %s' % (n, moved, exc)
            continue
        if inner is None or not inner.Faces:
            why = 'the refit at %d points offset to nothing' % n
            continue
        return refit, face, inner
    raise PreconditionFailed(
        'P3: no refit of the %.3f mm section at z = %.4f both reproduced it and eroded by '
        '%.4f mm. Last: %s. The wall is measured from this curve, so a refit that does not '
        'reproduce the section is a changed exterior, and one that will not offset is the '
        'IP-FC-54 failure.' % (wire.Length, z, t, why))


# --------------------------------------------------------------------------------
# The symmetry cell -- design authority is cowl_interior_surface.md section 4.5
# --------------------------------------------------------------------------------
#
# **Every operation below runs on the un-mirrored cell body, never on a full or reconstructed
# part.** `body` is `half` for the tail and `octant` for the nose -- a real solid, cut from the
# blank by the same masks that bound the cutting tools, so its section at any station is a
# closed loop only because it carries the cell's own flat construction faces alongside the true
# OML arc. Two prior attempts (`lower_sym`, and mirroring the finished cavity after fitting one
# periodic surface through the whole loop) both treated that loop as if it were the true
# exterior and fitted a closed, periodic surface through it -- which cannot hold a straight
# construction edge straight and a curved OML edge curved at the same point, so it rounds the
# corner, and the two halves' surfaces then meet only approximately once mirrored back
# together. That approximate meeting is what `removeSplitter` could not clean up: a near-zero
# area sliver face at the seam, and a `fuse`/cut that failed on it with `ValueError: Null shape`
# even though each half was individually valid.
#
# The fix removes the corner from the problem rather than refining against it: the cell's own
# flat faces are found directly from its geometry (`cell_boundary_planes`), the construction
# edges they contribute to each section are stripped out before anything is fitted
# (`open_arc`), and the surface fitted through what remains is genuinely open -- no periodic
# flag, no seam. The flat boundary is restored afterwards as its own exact flat face
# (`_lid`, `_side_caps`), which is what makes the later mirror-fuse exact rather than
# approximate: a mirror of an exact flat face is that same face, not a near-duplicate of it.


def cell_boundary_planes(cell, tol=1.0e-6):
    """The symmetry cell's own flat construction faces, as unit normals through the origin.

    **Found from the cell's own geometry, not from the mirror chain that reassembles it.** The
    nose's octant is bounded by two of its three eventual mirrors -- the diagonal and the `x`
    plane -- and not by the third, `y = 0`, which only becomes a boundary once the diagonal
    mirror has already produced a quadrant. Reading the planes off `cell` directly is what makes
    this correct for both cowls without having to say, in code, which mirrors are cell walls and
    which are reassembly steps.

    A cell wall is planar, perpendicular to the layer plane (its normal has no `z` component --
    every wall here contains the part's own axis), and passes through the origin, which is what
    tells it apart from the two z-end mask faces (planar but normal along `z`) and from the OML
    itself (never planar). `octant_mask`'s own size limit contributes a fourth planar face on
    some builds; it survives the `common` only where the mask happens to reach past the real
    body, and even then it fails the origin test, so it is excluded without having to be named.
    """
    planes = []
    for f in cell.Faces:
        if not isinstance(f.Surface, Part.Plane):
            continue
        normal = f.Surface.Axis
        normal.normalize()
        if abs(normal.z) > tol:
            continue
        if abs(f.Surface.Position.dot(normal)) > tol:
            continue
        if not any((normal - p).Length < tol or (normal + p).Length < tol for p in planes):
            planes.append(normal)
    if not planes:
        raise PreconditionFailed(
            'the body has no flat face through its own axis and perpendicular to the layer '
            'plane -- it was not reduced to a symmetry cell before this ran '
            '(cowl_interior_surface.md section 4.5)')
    return planes


def _on_plane(edge, planes, tol):
    lo, hi = edge.FirstParameter, edge.LastParameter
    for i in range(7):
        p = edge.valueAt(lo + (hi - lo) * i / 6.0)
        if not any(abs(p.x * n.x + p.y * n.y + p.z * n.z) < tol for n in planes):
            return False
    return True


def _chain(edges, tol=1.0e-6):
    """`edges` reordered tail to head into one open run, or a failure if they do not chain.

    Not assumed of `wire.Edges` order, because what is being reordered here is *the edges left
    after removing some of a closed wire's edges* -- a subset the wire's own traversal order
    was never a promise about once part of it is gone.
    """
    remaining = list(edges)
    chain = [remaining.pop(0)]
    while remaining:
        tail = chain[-1].Vertexes[-1].Point
        for i, e in enumerate(remaining):
            a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
            if tail.distanceToPoint(a) < tol:
                chain.append(remaining.pop(i))
                break
            if tail.distanceToPoint(b) < tol:
                chain.append(e.reversed())
                remaining.pop(i)
                break
        else:
            raise PreconditionFailed(
                'a cell section\'s arc edges do not chain into one open run once its '
                'construction boundaries are removed')
    return chain


def open_arc(wire, planes, tol=1.0e-6):
    """The true-exterior portion of a cell section: `wire` with its construction edges removed.

    Returns `(arc, plane_at_start, plane_at_end, flip)`. For the tail's one plane the two ends
    are the same plane, by construction -- the half's section is a "D", cut once. For the
    nose's two planes the ends differ, and `plane_at_start` is always `planes[0]` -- but which
    physical end of `arc` that actually is depends on wherever OCC happened to start it, which
    is not a promise this function relies on.

    **`flip` says whether a caller's own discretisation of `arc` needs reversing to reach that
    order, and every caller must apply it themselves rather than trust `arc`'s own vertex order
    or a `reversed()` copy of it.** Measured on the nose's octant: `Part.Wire`, both as built
    here and after calling its own `.reversed()`, can report `Vertexes[0]` at the same physical
    point regardless of the edge order or orientation handed to the constructor -- so neither
    the edge list going in nor the wire's topological orientation coming out is a reliable
    handle on which end its own `Vertexes`/`discretize` will call first. A plain Python list of
    points has no such ambiguity, which is why every consumer here (`_smoothed_open`,
    `open_contour`, `eroded_arc`) discretizes `arc` itself and then reverses the *list*, once,
    using `flip`, rather than asking a wire to have been built facing the other way.
    """
    keep = [e for e in wire.Edges if not _on_plane(e, planes, tol)]
    if not keep:
        raise PreconditionFailed(
            'a cell section has no arc left once its %d construction boundary(ies) are '
            'removed -- every edge of this section lies in a cell plane' % len(planes))
    arc = Part.Wire(_chain(keep, tol))
    if arc.isClosed():
        raise PreconditionFailed(
            'a cell section\'s arc came back closed once its construction boundaries were '
            'removed -- the body was not actually reduced to a cell')
    if len(planes) == 1:
        return arc, planes[0], planes[0], False

    def which(point):
        for i, n in enumerate(planes):
            if abs(point.x * n.x + point.y * n.y + point.z * n.z) < 1.0e-3:
                return i
        raise PreconditionFailed(
            'a cell arc\'s end at (%.4f, %.4f, %.4f) is not on any of its %d construction '
            'planes to 1e-3 mm' % (point.x, point.y, point.z, len(planes)))

    probe = arc.discretize(Number=10)
    i0, i1 = which(probe[0]), which(probe[-1])
    if i0 == i1:
        raise PreconditionFailed(
            'a cell arc\'s two ends are both on the same construction plane, but the cell has '
            '%d of them -- each end should sit on a different one' % len(planes))
    return arc, planes[0], planes[1], i0 != 0


def _resample_open(dense, n):
    """`n` points along the open polyline `dense`, evenly spaced by arc length, ends preserved
    exactly -- the open-arc counterpart of `contour`'s arc-length resampling."""
    cum = [0.0]
    for i in range(len(dense) - 1):
        x1, y1 = dense[i]
        x2, y2 = dense[i + 1]
        cum.append(cum[-1] + math.hypot(x2 - x1, y2 - y1))
    total = cum[-1]
    if total <= 0.0:
        raise PreconditionFailed('a cell arc has zero length')
    out = []
    j = 0
    for k in range(n):
        target = total * k / float(n - 1)
        while j + 2 < len(dense) and cum[j + 1] < target:
            j += 1
        span = cum[j + 1] - cum[j]
        f = 0.0 if span <= 0.0 else (target - cum[j]) / span
        x1, y1 = dense[j]
        x2, y2 = dense[j + 1]
        out.append((x1 + f * (x2 - x1), y1 + f * (y2 - y1)))
    return out


def _disc(wire, n, flip):
    """`wire.discretize(Number=n)`, reversed if `flip` -- see `open_arc`."""
    pts = wire.discretize(Number=n)
    return list(reversed(pts)) if flip else pts


def open_contour(wire, n, flip=False):
    """`n` points along an open arc, evenly spaced by arc length, and the dense polyline they
    were taken from -- the open-arc counterpart of `contour`, with no anchor or wraparound
    needed, since the two ends are already the cell's own construction boundary."""
    dense = [(p.x, p.y) for p in _disc(wire, max(DENSE_FACTOR * n, 400), flip)]
    return _resample_open(dense, n), _Polyline(dense, closed=False)


def _smoothed_open(wire, n, flip, tol=REFIT_TOL):
    """`smoothed`'s open counterpart: one open cubic B-spline through `n` points of `wire`,
    verified the same way."""
    pts = _disc(wire, n, flip)
    curve = Part.BSplineCurve(pts, None, None, False, 3, None, False)
    shape = curve.toShape()
    dense = _Polyline([(p.x, p.y) for p in shape.discretize(Number=4 * n)], closed=False)
    worst = float(dense.distances([(p.x, p.y) for p in _disc(wire, 2 * n, flip)]).max())
    return Part.Wire(shape), worst


def eroded_arc(arc, t, z, p_start, p_end, flip, tol=REFIT_TOL):
    """The open arc, refit and offset inward by `t`, its two ends snapped exactly onto the
    cell's own planes.

    **Snapped, not trusted.** An inward 2-D offset moves each point along the curve's own local
    normal, which for a genuinely symmetric exterior crossing its own cell plane head-on is
    already that plane's direction -- but `body` is not guaranteed exactly symmetric (IP-FC-138
    is the separate, still-open investigation into why), and the offset has no way to know the
    plane exists at all. Projecting the two ends onto it exactly is what makes the eventual
    mirror-fuse exact rather than approximate: both halves' surfaces then meet at bit-identical
    points, not merely close ones.

    **The refit curve is built by `_smoothed_open` from `arc` in the already-canonical order**
    (`flip` applied there), so its own start and end need no further reordering here -- only the
    offset's own start/end get snapped, to `p_start`/`p_end` respectively.
    """
    n0 = max(SAMPLE_MIN, min(SAMPLE_MAX, int(arc.Length / SAMPLE_SPACING)))
    why = None
    for n in (n0, 2 * n0, 4 * n0):
        refit, moved = _smoothed_open(arc, n, flip, tol)
        if moved > tol:
            why = ('refitting the arc at %d points moved it %.6f mm, over the %.6f mm '
                   'allowed' % (n, moved, tol))
            continue
        try:
            offset = refit.makeOffset2D(-t, 0, False, True, True)
        except Exception as exc:                        # noqa: BLE001 -- reported below
            why = 'the arc refit at %d points (%.6f mm) would not offset: %s' % (n, moved, exc)
            continue
        if offset is None or not offset.Edges:
            why = 'the arc refit at %d points offset to nothing' % n
            continue
        # `refit` was built directly from the canonically-ordered points above, so its own
        # offset's discretisation needs no `flip` -- it already starts at the `p_start` end.
        pts = [App.Vector(p.x, p.y, z) for p in offset.discretize(Number=max(2 * n, 400))]
        for i, plane in ((0, p_start), (-1, p_end)):
            d = pts[i].dot(plane)
            pts[i] = pts[i] - plane * d
        return [(p.x, p.y) for p in pts]
    raise PreconditionFailed(
        'P3: no refit of the %.3f mm cell arc at z = %.4f both reproduced it and eroded by '
        '%.4f mm. Last: %s.' % (arc.Length, z, t, why))


def _side_caps(surf, planes):
    """The flat face(s) that close a patch across the cell's construction boundary(ies), along
    its whole axial run -- the long edges `_lid` does not reach.

    One plane (the tail's half): both long edges already sit on it, so one face bounded by both
    of them, plus a straight closer at each end, closes the whole run at once.

    Two planes (the nose's octant): the long edges sit on two different planes that meet only
    at the part's own axis, so a single face across both would cut the near-axis corner off.
    Each edge instead gets its own face, closed at each end by a line to the axis point there --
    the two faces then share that axis line, which is ordinary shell topology, not a defect.
    """
    u0, u1, v0, v1 = surf.bounds()
    edge_lo = surf.vIso(v0).toShape()
    edge_hi = surf.vIso(v1).toShape()
    p_lo, p_hi = edge_lo.Vertexes[0].Point, edge_lo.Vertexes[-1].Point
    q_lo, q_hi = edge_hi.Vertexes[0].Point, edge_hi.Vertexes[-1].Point
    if len(planes) <= 1:
        wire = Part.Wire([edge_lo, Part.makeLine(p_hi, q_hi), edge_hi.reversed(),
                          Part.makeLine(q_lo, p_lo)])
        return [Part.Face(wire)]
    axis_lo, axis_hi = App.Vector(0, 0, p_lo.z), App.Vector(0, 0, p_hi.z)
    wire_a = Part.Wire([edge_lo, Part.makeLine(p_hi, axis_hi),
                       Part.makeLine(axis_hi, axis_lo), Part.makeLine(axis_lo, p_lo)])
    wire_b = Part.Wire([edge_hi, Part.makeLine(q_hi, axis_hi),
                       Part.makeLine(axis_hi, axis_lo), Part.makeLine(axis_lo, q_lo)])
    return [Part.Face(wire_a), Part.Face(wire_b)]


def slab_normal(tool):
    """The unit normal of a cutting slab's own plane, or `None` if it has no planar face.

    A slab's two largest faces are the pair that give it its thickness, so their normal is the
    direction the slab is thin in, and `hypot(n.x, n.y)` is the sine of the angle between the
    slab's plane and the layer plane -- 1 for a vertical cut, 0 for a horizontal one.
    """
    planar = [f for f in tool.Faces if isinstance(f.Surface, Part.Plane)]
    if not planar:
        return None
    n = max(planar, key=lambda f: f.Area).Surface.Axis
    n.normalize()
    return n


def dilated_notches(notches, t, report=None):
    """`dilate(B, t)` as a list of solids, built once for the part: section 4.2's right-hand
    term.

    **The ribs are applied to the cavity, not fitted into its surface, and that is the whole
    change.** The identity is exact --

        erode(A - B, t) == erode(A, t) - dilate(B, t)

    -- and it was previously evaluated station by station in 2-D: erode the body section,
    dilate the notch sections, subtract, and fit a smooth surface through the creased contour
    that came out. A single periodic B-spline cannot represent a crease. It overshoots at every
    rib corner, and the overshoot is what produced self-intersecting wires, unorientable faces,
    and a final fuse that landed 9x off its own volume from identical inputs (measured
    2026-09-03 on the nose at U = 1: 323372, 326795 and 35828 mm3 from the same 14 stations).

    Evaluating the same identity in 3-D removes the cause rather than refining against it. The
    surface is fitted through `erode(A, t)` alone, which on these cowls is a rounded rectangle
    with no crease anywhere in it, and `dilate(B, t)` is subtracted afterwards as a solid. The
    creases then arrive as the edges of a boolean between two well-formed solids, which is
    where a crease belongs.

    It also removes a correction the 2-D form needed and the 3-D form does not. A tool that
    does not reach the body at a station still has a section there, and dilating that section
    in-plane reached back across the boundary and bit material the part has -- so the 2-D code
    clipped each tool against the body and used the clip as a predicate. In 3-D no clip is
    needed: a tool outside the body is at least `t` from `erode(A, t)`, so its dilation meets
    the cavity in nothing.

    **The structuring element is a horizontal disc, not a ball.** Perimeter width is what one
    layer lays down, so the wall is measured in the layer plane and the erosion that defines it
    is a 2-D one -- which is what `eroded_body` already computes with `makeOffset2D`. Dilating
    by the same element keeps the identity's two halves consistent.

    **And the dilation is a union of translates, not a loft through offset sections.** Both
    reproduce the geometry; only one of them does it without introducing features that break
    the boolean afterwards. Lofting the offset sections needs the sections taken a hair inside
    each end -- slicing a polyhedron on one of its own vertex planes returns that face's edges
    rather than a section, measured on the tail as zero closed loops at z = -98.0120 and again
    at z = -94.8136 -- and the slivers that have to be extruded back on to close the gap leave
    edges 1e-4 mm long. Measured 2026-09-03 on the tail's two congruent side slabs, same volume
    and same z range:

        loft with sliver caps   4 short edges   cut valid on one slab, INVALID on the other
        loft without the caps   0 short edges   cut valid on both, but the spans no longer meet
        union of translates     0 short edges   cut valid on both

    The invalid one reported "Bad orientation of sub-shape", and no fuzzy tolerance rescues it
    honestly: at fuzz 1e-3 the cut returns *valid* and the cavity comes out 588610 mm3 from a
    588454 mm3 interior -- larger after a cut than before it.

    A union of translates has none of that. Every piece is the original polyhedron, so nothing
    can be degenerate that was not degenerate already, and `RIB_FACETS` records how the count
    was chosen against the 1.3 mm rib gap.

    `Part.makeOffsetShape`, the obvious alternative, is not usable either: it dilates the
    nose's slab correctly (424.570 -> 5702.021 mm3) and returns a null shape on the first tail
    tool.

    Returned as a list, which `cavity` then fuses into a single tool before cutting with it.
    An earlier version of this note said fusing "bought nothing" because it cost 260 s and the
    cut looked the same; that was wrong, and `cavity`'s own comment records what it buys --
    cutting with twenty-two separate tools succeeds on some and fails on others, silently, and
    the wall comes out in pieces because the ribs are what bridge the buttress slots.
    """
    grown = []
    angles = []
    for tool in notches.Solids:
        # **P4: no notch lies in the layer plane.** A rib forms because the slicer's single
        # perimeter walks into the notch and back out again *within* a layer; a notch lying in
        # the layer plane offers no such path, so the feature would have to be formed between
        # layers instead, which thin-wall perimeter slicing cannot do, and it comes out
        # malformed. Horizontal ribs are therefore not used, which is also what keeps the rib
        # thickness `2*n_p*w + t_cut / sin(theta)` away from its singularity
        # (cowl.md section 6.4).
        #
        # Asserted here rather than left true: this is the one place that sees every cutting
        # tool. It used to be visible only to `check_cowl_interior.in_plane_width`, which
        # returned `None` for a horizontal cut and whose caller answered with `continue` -- so
        # a design-domain violation was dropped from the rib check without comment and the
        # build reported OK.
        normal = slab_normal(tool)
        if normal is None:
            raise PreconditionFailed(
                'a cutting tool spanning z %.4f..%.4f has %d faces and not one of them is '
                'planar, so it is not a slab and its thickness has no direction. P4 cannot be '
                'evaluated on it and neither can the rib it is supposed to leave.'
                % (tool.BoundBox.ZMin, tool.BoundBox.ZMax, len(tool.Faces)))
        flat = math.hypot(normal.x, normal.y)
        if flat < FLAT_TOL:
            raise PreconditionFailed(
                'P4: a cutting tool spanning z %.4f..%.4f lies in the layer plane -- its own '
                'plane is %.3e from horizontal. A rib forms where the perimeter walks into the '
                'notch and back out within a layer, and a horizontal notch offers no such '
                'path, so this one would come out malformed rather than as a rib. Horizontal '
                'ribs are outside the design.' % (tool.BoundBox.ZMin, tool.BoundBox.ZMax, flat))
        angles.append(math.degrees(math.asin(min(1.0, flat))))

        # **The facet count has a floor set by this tool, and below it the dilation is a comb.**
        # The copies sit on a circle of radius `t`, so adjacent ones are `2*t*sin(pi/N)` apart.
        # Their union is a solid only while that spacing is smaller than the slab's own in-plane
        # thickness; once it is larger the copies stop touching and the "dilated" tool has gaps
        # in it. Nothing downstream notices -- the tool is still a valid solid, the rib gaps it
        # leaves still measure correctly, and the wall simply comes out with material missing
        # where the gaps fell.
        #
        # Measured 2026-09-05 on the tail at `U` = 1 with `RIB_FACETS` = 24: spacing 0.157 mm
        # against a 0.1 mm axial cut, wall 22348.60 mm3 instead of ~23680, and two stations
        # reporting 0.1035 mm of wall where 0.6 is wanted. The 0.2 mm diagonal cuts passed --
        # they need only 19 facets -- which is why the failure appeared at some stations and not
        # others. At 48 the spacing is 0.0785 mm and every tool overlaps.
        span = [v.Point.x * normal.x + v.Point.y * normal.y + v.Point.z * normal.z
                for v in tool.Vertexes]
        in_plane = (max(span) - min(span)) / flat
        spacing = 2.0 * t * math.sin(math.pi / RIB_FACETS)
        if spacing >= in_plane:
            raise PreconditionFailed(
                'RIB_FACETS = %d puts adjacent copies %.4f mm apart while this tool is only '
                '%.4f mm thick in the layer plane, so the copies do not overlap and their '
                'union has gaps in it. The tool spans z %.4f..%.4f. It needs at least %d '
                'facets: N > pi / asin(w / 2t) with w = %.4f and t = %.4f.'
                % (RIB_FACETS, spacing, in_plane, tool.BoundBox.ZMin, tool.BoundBox.ZMax,
                   int(math.ceil(math.pi / math.asin(min(1.0, in_plane / (2.0 * t))))) + 1,
                   in_plane, t))

        copies = [tool.translated(App.Vector(t * math.cos(2.0 * math.pi * i / RIB_FACETS),
                                             t * math.sin(2.0 * math.pi * i / RIB_FACETS),
                                             0.0))
                  for i in range(RIB_FACETS)]
        solid = copies[0].fuse(copies[1:]).removeSplitter()
        if not solid.isValid() or not solid.Solids:
            raise PreconditionFailed(
                'dilating a cutting tool by %.4f mm produced %d solids, valid=%s. The tool '
                'spans z %.4f..%.4f with %d faces.'
                % (t, len(solid.Solids), solid.isValid(), tool.BoundBox.ZMin,
                   tool.BoundBox.ZMax, len(tool.Faces)))
        grown.append(solid)

    if report is not None:
        report.update(dilated_tools=len(grown),
                      dilated_volume=sum(g.Volume for g in grown),
                      shallowest_cut_deg=min(angles) if angles else None)
    # The shallowest angle is reported, not bounded -- see `FLAT_TOL`. A cut at theta leaves a
    # rib of `2*n_p*w + t_cut / sin(theta)`, so this number is the one to look at if a rib ever
    # measures wider than expected.
    note('ribs: %d tools dilated by %.4f mm in %d directions; shallowest cut plane %.2f deg '
         'from the layer plane' % (len(grown), t, RIB_FACETS,
                                   min(angles) if angles else float('nan')))
    return grown


def tool_clearance_ranked(surf_shape, tool_shapes, z):
    """OQ-DES-CW24's raw per-tool measurement at one station: the in-plane clearance from the
    candidate interior surface's own slice to each individual dilated rib tool's own slice,
    ranked nearest first.

    **Per-tool, not fused first.** Slicing each tool individually and ranking the results
    measured ~15% faster than fusing them into one tool before slicing (4.28 s/point against
    5.01 s/point over a 50 mm window, `debug_check_design_close.py`) and is inherently safe from
    the multi-loop hazard `_min_wire_distance` guards against: an individual tool's own slice
    essentially never has more than one wire loop, where the fused compound almost always does.
    It is also what Metric B needs directly -- the ranked list's own second entry -- which a
    fused slice cannot produce at all.

    Returns a list of `(index, distance)` into `tool_shapes`, sorted nearest first. A tool with
    no section at `z` is simply absent from the list, not reported at distance zero.
    """
    s_wires = [w for w in _slice_wires(surf_shape, z) if w]
    if not s_wires:
        return []
    out = []
    for i, shape in enumerate(tool_shapes):
        tool_wires = [w for w in _slice_wires(shape, z) if w]
        d = _min_wire_distance(s_wires, tool_wires)
        if d is not None:
            out.append((i, d))
    out.sort(key=lambda id_: id_[1])
    return out


#: How parallel a face normal must be to the slab's own normal for that face to be a cheek, as
#: a dot product. 0.9 is 26 degrees; the two cheeks are exactly parallel to it by construction,
#: and no other face of either profile comes within 60 degrees, so nothing here is marginal.
CHEEK_DOT = 0.9

#: How many points of a tool's own section to test against the interior candidate solid when
#: deciding whether the two cross at a station. 120 around a section a few millimetres across
#: resolves a crossing at a fraction of a millimetre, which is all this has to distinguish; the
#: in-plane distance itself is still measured at `_min_wire_distance`'s own 400.
CROSSING_SAMPLES = 120

#: How closely a contact's measured offset back to the undilated tool must match that face's own
#: predicted dilation offset for the contact to be *on that face's image*, as a fraction of `t`.
#:
#: **This is what separates a contact on a face from one on an edge**, and it needs a real
#: threshold rather than an exact comparison. The dilation moves a face with outward normal `n`
#: out by exactly `t·hypot(n.x, n.y)`, so a contact sitting on that face's dilated image reproduces
#: the figure; one sitting on a facet that bridges two faces does not, and reads somewhere between
#: the two faces' own offsets. 1 % of `t` is 0.006 mm, which is coarse enough to absorb the
#: discretisation of the section wires and far finer than the 0.04 mm discrepancies an edge
#: contact actually produces.
FACE_IMAGE_TOL = 0.01

#: How far along the cut direction a face normal must point to be floor rather than an end cap,
#: as a dot product.
#:
#: **0.5 (60 degrees) is deliberately loose, because of the overhang ramps.** Two of the
#: six-sided profile's edges step inward over a rise of
#: `buttress_r_inset * tan(overhang_angle_from_bed)` -- cowl.md section 4.1 is what they are for
#: -- so at the 35 degree print angle their own normals sit about 55 degrees off the cut
#: direction. They are floor: they are part of the cut's innermost boundary, and the material
#: between them and the interior surface is wall. A tighter cutoff would label them `end`, which
#: would be wrong in exactly the place a thin spot is most likely.
FLOOR_DOT = 0.5


#: How far to step off a face to decide which way is out of the solid, in millimetres.
#:
#: It has to stay well inside the thinnest dimension the solid has, which for a cutting tool is
#: `buttress_cut_thickness` = 0.1 mm between its two cheeks: a step of half that or more would
#: land on or past the opposite cheek and read as outside from either side.
OUTWARD_STEP_MM = 1.0e-3


def _outward_normal(face, solid, step=OUTWARD_STEP_MM):
    """A face's own outward normal -- the one that leaves `solid`.

    **Read by displacement, not from `Face.Orientation`.** The orientation flag does not survive
    the way these tools are built: measured 2026-10-04 on `tail_shell`'s eleven cutting tools,
    every slab reports *both* of its cheeks as `Forward`, so flipping on the flag returns the
    same normal for two opposite faces of one solid -- impossible, and it mislabelled the cut
    floor as the far face on every tool. Stepping off the face and asking the solid which side
    the point is on cannot be fooled that way.

    Raises if neither direction leaves the solid, rather than guessing: that would mean `step`
    is too large for the solid's own thickness, which is exactly the failure this is replacing.
    """
    point = face.CenterOfMass
    if isinstance(face.Surface, Part.Plane):
        n = App.Vector(face.Surface.Axis)
    else:
        u0, u1, v0, v1 = face.ParameterRange
        n = face.normalAt(0.5 * (u0 + u1), 0.5 * (v0 + v1))
    n.normalize()
    out_plus = not solid.isInside(point + n * step, 0.5 * step, True)
    out_minus = not solid.isInside(point - n * step, 0.5 * step, True)
    if out_plus == out_minus:
        raise PreconditionFailed(
            'stepping %.1e mm either way off a face of a solid spanning z %.4f..%.4f lands %s '
            'it both times, so the face has no outward direction to read. The step has to be '
            'smaller than the solid\'s own thinnest dimension.'
            % (step, solid.BoundBox.ZMin, solid.BoundBox.ZMax,
               'outside' if out_plus else 'inside'))
    return n if out_plus else n * -1.0


def tool_face_roles(raw_tool):
    """Label every face of one undilated buttress cutting tool by what it bounds: OQ-DES-CW25.

    A buttress tool is a slab -- a six-sided or rectangular profile extruded through
    `buttress_cut_thickness` -- and the distinction the geometry makes, which
    `tool_clearance_ranked` cannot, is that only part of its boundary bounds the finished wall:

      * ``cheek`` -- one of the two broad faces, `buttress_cut_thickness` apart. These are the
        slit's own side walls. The wall continues past them: the material beyond a cheek is the
        rib, and the rib's thickness is set at `t` by `dilated_notches` by construction, not by
        any distance measured against this face.
      * ``floor`` -- the innermost reach of the cut, including the two overhang ramps. This is
        the only part of the tool that bounds the wall's own radial thickness, so it is the only
        part whose distance to the interior surface says anything about the wall.
      * ``end`` -- the two axial end caps, closing the ends of the slit's run.
      * ``outer`` -- the profile's far edge, which sits outside the blank entirely and cuts
        nothing. A minimum landing here would mean the measurement is reading a face the part
        does not have.

    Labelled from the geometry rather than from the construction, so a tool built another way
    still classifies. `e` is `slab_normal`: the slab's own thin direction. `a` is the direction
    from the tool toward the part's own z axis, projected perpendicular to `e` -- every buttress
    cut enters from outside the blank and reaches inward, so that is the direction the cut
    deepens in. A normal along +/-`e` is a cheek, one along +`a` is floor, along -`a` is outer,
    and anything else is an end cap.

    Returns one dict per face of `raw_tool`, in face order, carrying the role, the outward
    normal, the two dot products the role was read from, and the face's area.
    """
    e = slab_normal(raw_tool)
    if e is None:
        raise PreconditionFailed(
            'a cutting tool spanning z %.4f..%.4f has no planar face, so it is not a slab and '
            'its faces have no cheek direction to be classified against.'
            % (raw_tool.BoundBox.ZMin, raw_tool.BoundBox.ZMax))
    com = raw_tool.CenterOfMass
    a = App.Vector(-com.x, -com.y, 0.0)
    a = a - e * a.dot(e)
    if a.Length > 1.0e-9:
        a.normalize()
    else:
        a = App.Vector(0, 0, 0)
    out = []
    for face in raw_tool.Faces:
        n = _outward_normal(face, raw_tool)
        d_cheek, d_floor = n.dot(e), n.dot(a)
        if abs(d_cheek) >= CHEEK_DOT:
            role = 'cheek'
        elif d_floor >= FLOOR_DOT:
            role = 'floor'
        elif d_floor <= -FLOOR_DOT:
            role = 'outer'
        else:
            role = 'end'
        out.append(dict(role=role, normal=n, dot_cheek=d_cheek, dot_floor=d_floor,
                        area=face.Area))
    return out


def clearance_face_scan(surf_shape, tool_shapes, raw_tools, body, t, zs):
    """IP-FC-148: at each station in `zs`, which face of the nearest buttress tool carries
    Metric A's own minimum, and what that face bounds.

    This is the measurement OQ-DES-CW25 turns on. `clearance_margin_scan` reports the smallest
    in-plane distance from the interior surface's section to the nearest dilated tool's section,
    and takes that minimum over the *whole* tool section -- so a minimum on the cut floor, which
    bounds the wall's radial thickness, and a minimum on a cheek, which bounds nothing because
    the wall continues past it as the rib, come out as the same number. `tool_face_roles`
    records what the difference is; this locates which one each reported minimum actually is.

    **The contact is found on the dilated tool and classified against the undilated one.** The
    dilation is a union of `RIB_FACETS` translates (`dilated_notches`), so the grown tool's own
    boundary is a comb of offset copies of the original faces plus the facets that bridge them,
    and a face index into it means nothing stable. The original slab has eight faces with fixed
    meanings. Because the dilation is a horizontal disc, a face with outward normal `n` moves
    out by exactly `t * hypot(n.x, n.y)`, which `expected_offset` records beside the measured
    `offset`: the two agreeing is what confirms the contact really does lie on that face's own
    dilated image rather than on a bridging facet.

    **`second_role` is not redundant.** Where the two nearest faces are the same distance away,
    the contact is on the edge between them rather than on either face, which is the
    near-tangency signature IP-FC-137 describes -- and a minimum of a few nanometres on a
    tool edge means something different from one on a tool face.

    **`crossing` is the field that decides what the whole metric is worth, and it is not a
    refinement of the face question but a prior one.** `tool_clearance_ranked` measures wire to
    wire, which cannot tell a tool section sitting just clear of the interior surface from one
    already biting into it: both report a positive boundary-to-boundary distance. So each tool
    section's own sample points are tested against the interior candidate *solid*. Points all
    outside means the tool is clear there and the distance is a real clearance. Points on both
    sides means the tool's boundary crosses the surface at this station -- the true in-plane
    distance is zero, the cut is actively removing material, and whatever small number the scan
    reports is the distance from the sampled station to a geometric crossing rather than a
    clearance. A dilated tool is *supposed* to cross: that is how the rib gets its `t` of material
    (section 4.2's identity). The crossing has to be somewhere along every slot that enters the
    wall band at all, so finding the scan's minima at one is a property of the sampling.

    **A face only bounds the wall where it lies inside the blank, so that is tested at the
    contact rather than assumed from the role.** Measured 2026-10-04 on `tail_shell`: the core
    cut (`cowl_tree.core`, the region the buttress cuts may not enter) splits the cut floor of
    each of the two long diagonal tools into an 8.4 mm2 piece inside the blank and a 1.4 mm2
    piece outside it, and leaves sub-0.02 mm2 slivers on three of the side tools whose normals
    read as floor while sitting outside the part entirely. Both are genuine faces of the real
    tool; neither bounds any wall where it sits. `in_blank` settles that per contact, and
    `bounds_wall` is the single answer OQ-DES-CW25 asks for: floor, and inside the part.

    Returns one dict per station, in the order `zs` gives them. A station where no tool has a
    section, or where the surface has none, is absent rather than present with a null distance.
    """
    rows = []
    roles_cache = {}
    for z in zs:
        ranked = tool_clearance_ranked(surf_shape, tool_shapes, z)
        if not ranked:
            continue
        index, metric_a = ranked[0]
        s_wires = [w for w in _slice_wires(surf_shape, z) if w]
        t_wires = [w for w in _slice_wires(tool_shapes[index], z) if w]
        got = _min_wire_contact(s_wires, t_wires)
        if got is None:
            continue
        dist, p_surf, p_tool = got
        if index not in roles_cache:
            roles_cache[index] = tool_face_roles(raw_tools[index])
        roles = roles_cache[index]
        vertex = Part.Vertex(App.Vector(p_tool[0], p_tool[1], z))
        near = sorted((face.distToShape(vertex)[0], fi)
                      for fi, face in enumerate(raw_tools[index].Faces))
        offset, fi = near[0]
        entry = roles[fi]
        n = entry['normal']
        gap = App.Vector(p_surf[0] - p_tool[0], p_surf[1] - p_tool[1], 0.0)
        if gap.Length > 0.0:
            gap.normalize()
        # A hair along -n, so the sample sits in the material this face's own cut takes out
        # rather than on the blank's skin.
        probe = raw_tools[index].Faces[fi].distToShape(vertex)[1][0][0] \
            - n * (2.0 * OUTWARD_STEP_MM)
        in_blank = bool(body.isInside(probe, OUTWARD_STEP_MM, True))
        inside_n, total_n = 0, 0
        for w in t_wires:
            for p in w.discretize(Number=CROSSING_SAMPLES):
                total_n += 1
                if surf_shape.isInside(p, OUTWARD_STEP_MM, True):
                    inside_n += 1
        # **Three states, not two.** An earlier version of this reported only `crossing`, which
        # conflated the two ways of not crossing: a tool entirely outside the surface, where the
        # reported figure is a real clearance, and one entirely inside it, where there is no
        # clearance at all and the cut is removing material along the tool's whole section.
        # Measured 2026-10-04, both occur -- `nose_cowl_shell` has one station at 0.0 % inside and
        # `tail_shell` one at 100.0 % -- so collapsing them would have called a fully engulfed tool
        # a clearance.
        if inside_n == 0:
            engagement = 'clear'
        elif inside_n == total_n:
            engagement = 'engulfed'
        else:
            engagement = 'crossing'
        row = dict(z=z, tool=index, metric_a=metric_a, contact_distance=dist,
                   engagement=engagement, crossing=bool(engagement == 'crossing'),
                   is_clearance=bool(engagement == 'clear'),
                   fraction_inside=(float(inside_n) / total_n) if total_n else None,
                   p_surf=p_surf, p_tool=p_tool, face=fi, role=entry['role'],
                   normal=(n.x, n.y, n.z), dot_cheek=entry['dot_cheek'],
                   dot_floor=entry['dot_floor'], offset=offset,
                   expected_offset=t * math.hypot(n.x, n.y),
                   normal_dot_gap=gap.dot(n), in_blank=in_blank)
        row['on_face_image'] = bool(
            abs(row['offset'] - row['expected_offset']) <= FACE_IMAGE_TOL * t)
        # Only a contact that is *on* a floor's dilated image, inside the blank, is a distance to
        # something that bounds the wall. A contact on the facet bridging two faces is a distance
        # to an edge of the tool, and which of the two faces happens to be nearest is then an
        # accident of the bridge's geometry rather than a fact about the wall.
        row['bounds_wall'] = bool(entry['role'] == 'floor' and in_blank
                                  and row['on_face_image'])
        if len(near) > 1:
            second = roles[near[1][1]]
            row.update(second_face=near[1][1], second_role=second['role'],
                       second_offset=near[1][0],
                       second_expected=t * math.hypot(second['normal'].x, second['normal'].y))
        rows.append(row)
    return rows


def clearance_margin_scan(surf_shape, tool_shapes, z_lo, z_hi,
                           coarse_step=1.0, refine_window=1.0, refine_step=0.05, n_worst=15):
    """OQ-DES-CW24's scan of a candidate interior surface against the individual rib tools that
    will be cut into it: Metric A (the nearest tool's own clearance) and Metric B (the ratio
    between the two nearest tools' clearances), adaptively sampled.

    **Metric B does not measure crowding, and should be retired rather than given a cutoff
    (OQ-DES-CW24, re-review 2026-10-03).** It compares how far each tool is from the *surface*
    and never compares the tools to each other, so two tools on opposite sides of the part score
    as maximally crowded whenever their clearances happen to be similar. At `z` = -283.9951 on
    `tail_shell` `U` = 3.0 -- the station the whole crowding argument was derived from -- the
    three tools it ranks as crowded have their own nearest points 87.7, 89.2 and 176.9 mm apart
    on a 300 mm part. Measured directly, the real dilated tool set's largest pairwise *overlap*
    is 0.59% of the smaller tool, against the ~40% that produced the pathological topology in
    IP-FC-137's synthetic test, so the mechanism this metric was built to detect is not present
    in the real part at that magnitude. The earlier claim here -- "crowding, not raw thinness, is
    what the evidence ties to the severe failure mode" -- is withdrawn.

    **Neither metric predicts the construction failure.** At `z` = -60.0000 Metric A reads
    0.097097 mm and Metric B reads 5.950x, both comfortably passing, and a 0.01 mm row
    displacement there severs the wall into two solids with a 99.3% partition slip. What catches
    that is `shell_solid()`'s own solid-count and partition checks, not this scan. Metric A's own
    standing is narrower than it was: see `CLEARANCE_MARGIN_MM` for what its distance is and is
    not known to bound.

    **Two stages, not one fixed grid.** A `coarse_step` pass finds candidate thin points, then a
    `refine_step` pass re-scans a `refine_window` around each of the worst `n_worst` coarse
    points. A fixed grid at any affordable spacing was measured to understate the true thinness
    minimum by one to two orders of magnitude at exactly the points that matter
    (`debug_full_tail_fine_survey_FIXED.py`: a 1 mm coarse grid read 180x high at one station a
    0.02 mm scan found), and a uniformly fine grid everywhere costs on the order of 19 hours for
    one whole-tail build -- not viable as a per-build check.

    Returns the refined worst points as a list of `(z, metric_a)`, nearest-clearance first.

    **Metric B was removed here, 2026-10-04** (IP-FC-147, OQ-DES-CW24 alternative 3). It was a
    ratio between the two nearest tools' distances to the *interior surface*, reported alongside
    Metric A under the name "crowding". It never compared the tools to one another, so two tools
    on opposite sides of the part scored as maximally crowded whenever their clearances happened
    to be similar: at the station the whole crowding argument was built on, the three tools it
    ranked as crowded had their nearest points 87.7-176.9 mm apart on a 300 mm part, and the real
    dilated tools' largest pairwise overlap is 0.59% of the smaller tool. It was removed rather
    than given a cutoff because no cutoff on a quantity with no geometric meaning is sound --
    this was never the threshold problem it was described as. Its non-reproducibility between
    identical builds followed from the same defect rather than being separate evidence.

    This function reports; it does not gate.
    """
    def sample(z):
        ranked = tool_clearance_ranked(surf_shape, tool_shapes, z)
        if not ranked:
            return None
        return ranked[0][1]

    n_coarse = max(int((z_hi - z_lo) / coarse_step), 1)
    coarse = []
    for k in range(n_coarse + 1):
        z = z_lo + (z_hi - z_lo) * k / float(n_coarse)
        got = sample(z)
        if got is not None:
            coarse.append((z, got))
    coarse.sort(key=lambda row: row[1])

    results = []
    for z_center, _a in coarse[:n_worst]:
        fine_lo = max(z_lo, z_center - refine_window)
        fine_hi = min(z_hi, z_center + refine_window)
        n_fine = max(int((fine_hi - fine_lo) / refine_step), 1)
        best = None
        for k in range(n_fine + 1):
            z = fine_lo + (fine_hi - fine_lo) * k / float(n_fine)
            got = sample(z)
            if got is not None and (best is None or got < best[1]):
                best = (z, got)
        if best is not None:
            results.append(best)
    results.sort(key=lambda row: row[1])
    return results


def _one_region(shape, z, fuzz):
    """P2: the eroded section is a single closed loop. Returns its face.

    **Asserted against the loops that are geometry, not against the ones that are boolean
    debris.** Cutting the dilated notches out of the eroded section leaves micro wires at the
    dent tips -- measured on the nose at z = -10.10, three of them beside a correct 284.92 mm
    outer boundary, and so degenerate that `Wire.discretize` on one brings the kernel down with
    an access violation rather than returning points. They are not holes and the cavity does not
    have them.

    The floor is two orders below the narrowest feature the design has -- a notch is
    `buttress_cut_thickness` = 0.1 mm wide -- and two orders above the debris, so it cannot
    swallow a real loop. It would not have swallowed the ones that mattered either: when
    unclipped tools were biting spurious pinholes into the tail, those loops measured 0.603 and
    0.522 mm, and this floor reports both.
    """
    where = 'z = %.4f' % z + ('' if fuzz is None else ' (fuzz %g)' % fuzz)
    faces = [f for f in shape.Faces if f.OuterWire.Length > SLIVER_LENGTH]
    if len(faces) != 1:
        raise PreconditionFailed(
            'P2: the eroded section is %d regions at %s, not one -- the erosion pinched it '
            'apart' % (len(faces), where))
    loops = [w for w in faces[0].Wires if w.Length > SLIVER_LENGTH]
    if len(loops) != 1:
        raise PreconditionFailed(
            'P2: the eroded section at %s has %d loops, not one (lengths %s)'
            % (where, len(loops), ', '.join('%.4f' % w.Length for w in loops)))
    return faces[0]


def fit_samples(perimeter):
    """How many points of this contour go into the fit grid. See `FIT_ARC`."""
    return max(FIT_MIN, min(FIT_MAX, int(perimeter / FIT_ARC)))


def check_samples(perimeter):
    """How many points of this contour the wall is evaluated at. See `CHECK_ARC`."""
    return max(CHECK_MIN, min(CHECK_MAX, int(perimeter / CHECK_ARC)))


def contour(face_or_wire, n, anchor=0.0):
    """Section 4.3: `n` points around a closed contour, in consistent correspondence, and the
    dense polyline they were taken from.

    **Anchored to a geometric feature and traversed in a fixed direction**, then distributed
    by arc-length fraction, so a station with a notch and a station without still correspond.
    Without this the surface twists between stations, and the result is a valid, closed,
    plausible solid -- the classic loft failure, which announces itself nowhere.

    The anchor is the contour's crossing of the +x ray from its own centroid. The algorithm
    document suggests one of the four corner arcs of the rounded-rectangle section; those are
    not usable here because the 2-D offset and the notch subtraction rebuild the contour's
    edge list, so the arc that was a corner on the exterior is not identifiable as one on the
    eroded contour. The ray is a feature of the section rather than of its edge list, which is
    the property the document is asking for, and it is stable across stations because the
    cowl's axis is the z axis by construction.
    """
    wire = face_or_wire if isinstance(face_or_wire, Part.Wire) else face_or_wire.OuterWire
    dense = [(p.x, p.y) for p in wire.discretize(Number=max(DENSE_FACTOR * n, 400))]
    if len(dense) > 1 and dense[0] == dense[-1]:
        dense.pop()
    if _signed_area(dense) < 0.0:
        dense.reverse()

    m = len(dense)
    # **Weighted by arc length, because the plain mean of the samples is a property of the
    # sampling and not of the curve.** `makeOffset2D` hands back a wire whose edge list starts
    # wherever the kernel left it, and `Wire.discretize` allocates its points per edge, so a
    # rotated edge list slides every sample along the curve -- measured 2026-09-04 on the tail,
    # up to 0.068 mm on a contour identical to 65 nanometres. An unweighted centroid moves with
    # that, the anchor ray swings with the centroid, and the parameter origin slides. It showed
    # up as the two end rows of a patch differing between processes by 0.0570 and 0.0169 mm
    # with the mean equal to the maximum -- every point shifted by the same amount, which is a
    # rigid twist of the correspondence rather than a change of shape. Weighting by segment
    # length makes the centroid the curve's, so redistributing the samples leaves it alone.
    seg = [math.hypot(dense[(i + 1) % m][0] - dense[i][0],
                      dense[(i + 1) % m][1] - dense[i][1]) for i in range(m)]
    total_len = sum(seg)
    if total_len <= 0.0:
        raise PreconditionFailed('a section at has zero perimeter')
    cx = sum(0.5 * (dense[i][0] + dense[(i + 1) % m][0]) * seg[i]
             for i in range(m)) / total_len
    cy = sum(0.5 * (dense[i][1] + dense[(i + 1) % m][1]) * seg[i]
             for i in range(m)) / total_len

    # The crossing of the ray at `anchor` radians from the centroid: a fixed direction, so the
    # same place on the section at every station.
    #
    # **The direction is chosen away from every notch, and that is not a detail.** The nose's
    # eight buttresses sit exactly on the +-x and +-y axes -- measured, their sections span
    # x = -0.050..0.050 and y = -0.050..0.050 -- so anchoring on +x put the parameter origin
    # inside a dent. As the dent's depth ramps between stations the crossing jumps from one
    # side of it to the other, the arc-length parameterisation rotates by that much between
    # neighbouring rows, and the fitted surface twists so badly that a z plane no longer cuts
    # it in one closed loop. The refinement then subdivides forever at a *measured gap of
    # zero*, because the intervals never reach the deviation test.
    #
    # The tail never showed it: its notches sit at 5, 12.5, 20 and 30 degrees, so +x happened
    # to land on clean surface. A default that works on one part and silently destroys the
    # other is the kind of thing section 4.3 is warning about when it says to anchor to a
    # feature rather than to whatever the sectioning returned.
    # **The origin is the crossing itself, not the sample before it, and that is what makes
    # the build reproducible.** `makeOffset2D` returns the eroded contour as a wire whose edge
    # list starts wherever the kernel left it: measured 2026-09-04 on the tail at z = -59.9996,
    # two processes produced the same ten edges with the same lengths and the same start points
    # to nine decimals, rotated by one position. The curve is identical -- 65 nanometres between
    # the two point sets -- but `Wire.discretize` allocates its points per edge, and this wire's
    # edges run from 0.0417 mm to 151.9 mm, so the rotation slides every sample along the curve
    # by up to 0.068 mm.
    #
    # Snapping the origin to the nearest sample turned that slide into a parameter shift of up
    # to one dense spacing, *different at every station*, which is a twist in the correspondence
    # rather than a shift of it: the rows no longer line up, the fitted surface moves, and the
    # measured wall error came out 0.5974, 0.6096 or 0.6439 mm from six identical seeded
    # stations depending on the run. Downstream that decided whether the tail's wall closed as
    # one solid or five.
    #
    # Interpolating the crossing removes the quantisation outright. The anchor is a geometric
    # feature of the section, so the origin it defines is exact, and what remains is the dense
    # polyline's chord error -- 1e-4 mm at this spacing, three orders under `TAU`.
    ux, uy = math.cos(anchor), math.sin(anchor)
    start = 0
    cross = None
    for i in range(m):
        c1 = (dense[i][0] - cx) * -uy + (dense[i][1] - cy) * ux
        j = (i + 1) % m
        c2 = (dense[j][0] - cx) * -uy + (dense[j][1] - cy) * ux
        if c1 <= 0.0 < c2 and ((dense[i][0] - cx) * ux + (dense[i][1] - cy) * uy) > 0.0:
            start = i
            span = c2 - c1
            f = 0.0 if span <= 0.0 else -c1 / span
            cross = (dense[i][0] + f * (dense[j][0] - dense[i][0]),
                     dense[i][1] + f * (dense[j][1] - dense[i][1]))
            break
    if cross is None:
        raise PreconditionFailed(
            'the contour at this station never crosses the anchor ray at %.4f rad. The '
            'correspondence has no origin, and every row would be parameterised from wherever '
            'the sectioning happened to start.' % anchor)
    # The crossing replaces the sample it fell between, so the list still has `m` points and
    # begins exactly on the ray.
    dense = [cross] + dense[start + 1:] + dense[:start + 1]
    m = len(dense)

    cum = [0.0]
    for i in range(m):
        x1, y1 = dense[i]
        x2, y2 = dense[(i + 1) % m]
        cum.append(cum[-1] + math.hypot(x2 - x1, y2 - y1))
    total = cum[-1]
    if total <= 0.0:
        raise PreconditionFailed('a section at has zero perimeter')

    samples = []
    j = 0
    for k in range(n):
        target = total * k / float(n)
        while j + 1 < len(cum) and cum[j + 1] < target:
            j += 1
        span = cum[j + 1] - cum[j]
        f = 0.0 if span <= 0.0 else (target - cum[j]) / span
        x1, y1 = dense[j % m]
        x2, y2 = dense[(j + 1) % m]
        samples.append((x1 + f * (x2 - x1), y1 + f * (y2 - y1)))
    return samples, _Polyline(dense)


def _check_slope(lower, upper, z_lo, z_hi, limit):
    """P1: every section steeper than `overhang_angle_from_bed`.

    Checked on the **un-notched** body, which is where section 4.2's `erode(A, t)` applies and
    where the `t*cos(alpha)` reasoning holds. The notch ramps are cut at this same angle by
    design and are handled by the dilation of B, so including them here would fire the
    assertion on the feature the design intends.
    """
    dz = abs(z_hi - z_lo)
    if dz <= 0.0:
        return
    worst = None
    at = 0.0
    for (x1, y1), (x2, y2) in zip(lower, upper):
        dr = math.hypot(x2 - x1, y2 - y1)
        ang = math.degrees(math.atan2(dz, dr))
        if worst is None or ang < worst:
            worst = ang
            at = math.atan2(y1, x1)
    if worst is not None and worst < limit - SLOPE_SLACK:
        raise PreconditionFailed(
            'P1: the body is %.2f deg from the bed between z = %.4f and %.4f, at %.1f deg '
            'around the section -- shallower than overhang_angle_from_bed = %.2f. The inset '
            'leaves t*cos(alpha) of perpendicular wall, so this station would emit a knife '
            'edge.' % (worst, z_lo, z_hi, math.degrees(at), limit))


# --------------------------------------------------------------------------------
# Stations
# --------------------------------------------------------------------------------

def _tessellated_interior(body, sections, deflection=0.1):
    """A z the body really does section at, found from a mesh rather than from a box.

    Only called when `z_extent`'s probes of the bounding box have all missed, which happens
    when that box is much larger than the part. A tessellation is bounded by the part itself,
    so its z range cannot be an over-estimate the way the box can, and the middle of that
    range is interior for any body whose material is z-connected -- which every part here is.
    The fractions are tried in the same order as above for the same reason: if the middle is
    somehow not interior, near-middle is the next most likely place.

    Returns `None` if even that finds nothing, so the caller can say so rather than guess.
    """
    lo = hi = None
    for face in body.Faces:
        points, _facets = face.tessellate(deflection)
        for point in points:
            lo = point.z if lo is None else min(lo, point.z)
            hi = point.z if hi is None else max(hi, point.z)
    if lo is None or hi <= lo:
        return None
    for f in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
        z = lo + (hi - lo) * f
        if sections(z):
            return z
    return None


def z_extent(body, tol=END_INSET):
    """The body's real axial extent, found by asking it where it sections.

    **`Shape.BoundBox` is not tight on these solids, and taking it at its word puts stations
    outside the part.** Measured 2026-09-02 on the nose at U = 1: `Lower` is the scaled OML met
    with a mask running z = -50 to -6, and it reports a bounding box of -100 to 0 -- the whole
    un-masked blank. Sectioning at -61.16, which that box calls interior, returns no loops at
    all. The box is computed from the B-spline geometry rather than from the trimmed result, so
    it is an outer bound and nothing more. The tail survived it only because its mask happens to
    span the whole OML.

    An earlier version read the extent off the faces perpendicular to z, which is exact and
    free -- and wrong, because only the nose has two of them. The tail's forward end is the mask
    cut but its aft end is the OML's own closure (OQ-DES-CW13), so that version found one plane
    and refused. Bisection makes no assumption about how either end is bounded, and it is the
    same path for both cowls, which is the property that matters more than the cost: an outer
    bound plus a predicate is all this needs, and both are reliable.

    **The probe has to be able to find the part, and on one kind it could not.** The seven
    fractions below are of the *bounding box*, so how well they work depends on how loose it
    is. Measured 2026-09-06: the nose cowl's box is 139 % of the part and every fraction still
    lands inside it, but the nose tip is 7.000 mm tall inside a box of 61.159 -- **874 %** --
    and all seven miss, whereupon this raised `the body does not section anywhere in its own
    bounding box`, which is a false statement about the body. Nothing calls it on the tip
    today, since only cowls are shelled; it would have been inherited by the next caller. A
    tessellation cannot miss, so it is the fallback, and it is only reached when the cheap
    probes have all failed. **The returned extent is unchanged either way** -- the bisection
    below converges on the real boundary from any interior point, and the fallback supplies
    only a starting point.

    About 34 sections at roughly 0.7 s each, once per part.
    """
    def sections(z):
        try:
            return len(_slice_wires(body, z)) >= 1
        except Exception:                              # noqa: BLE001 -- a miss is a miss
            return False

    box = body.BoundBox
    lo, hi = box.ZMin, box.ZMax
    inside = None
    for f in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
        z = lo + (hi - lo) * f
        if sections(z):
            inside = z
            break
    if inside is None:
        inside = _tessellated_interior(body, sections)
    if inside is None:
        raise PreconditionFailed(
            'the body does not section anywhere in its own bounding box, %.4f to %.4f, nor '
            'anywhere in the z range of its own tessellation' % (lo, hi))

    def edge(outside, within):
        while abs(within - outside) > tol:
            mid = 0.5 * (outside + within)
            if sections(mid):
                within = mid
            else:
                outside = mid
        return within

    return edge(lo, inside), edge(hi, inside)


def feature_stations(notches, z_lo, z_hi):
    """Section 4.1: the axial positions where the exterior itself has an edge.

    **Derived from the geometry rather than restated from the parameters.** Every buttress
    ramp start and end, and the cut plane, appear as vertices of the notch solids, so reading
    them off the tools gets all of them and cannot fall out of step with the tools that made
    them. A list rebuilt from the sheet would be a second statement of one design, and the one
    that moved would win silently.

    These are **patch boundaries, not interior knots**: the exterior has a genuine crease
    there, and demanding continuity across a rib end would smooth away a feature the part
    really has.
    """
    seen = sorted(v.Point.z for v in notches.Vertexes
                  if z_lo + MIN_INTERVAL < v.Point.z < z_hi - MIN_INTERVAL)
    out = []
    for z in seen:
        if not out or abs(z - out[-1]) > max(Z_TOL, MIN_INTERVAL):
            out.append(z)
    return out


def _patches(z_lo, z_hi, features):
    edges = [z_lo] + list(features) + [z_hi]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)
            if edges[i + 1] - edges[i] > MIN_INTERVAL]


def _seed(z_lo, z_hi, inset_lo, inset_hi):
    n = SEED_MAX if (z_hi - z_lo) >= SEED_LONG_MM else SEED_MIN
    zs = [z_lo + (z_hi - z_lo) * i / float(n - 1) for i in range(n)]
    # Only the part's own ends are inset. An internal patch boundary is a station the patches
    # on both sides must sample at *exactly* the same z, or their two approximations of it are
    # separated by the inset.
    if inset_lo:
        zs[0] += END_INSET
    if inset_hi:
        zs[-1] -= END_INSET
    return zs


def station_floor(t):
    """Section 4.1: the minimum separation two fit stations may have.

    **Tied to the wall, not to a fixed number** (IP-FC-144, OQ-DES-CW24 alternative 2). Two
    stations closer together than the wall they are building carry very nearly the same eroded
    contour, so the fit is asked to interpolate a near-duplicate and the axial pole track through
    them is near-degenerate. `MIN_INTERVAL` remains a hard geometric floor underneath, for a wall
    thinner than it.
    """
    return max(t, MIN_INTERVAL)


def _thin_stations(zs, floor):
    """Drop stations that sit closer than `floor` to the one before them.

    **This is the filter the per-patch union never had.** `feature_stations()` already
    deduplicates its own output, and `_patches()` already refuses a patch shorter than
    `MIN_INTERVAL`, but the uniform seed stations and the notch edges are independent sets:
    neither contains a close pair on its own, and their union can. That is how the real
    `tail_shell` fit at `U` = 3.0 reached a station pair 0.0009 mm apart -- 670 times finer than
    the wall -- from two individually legitimate stations.

    **Both end stations are preserved exactly.** A patch boundary is a station the patches on
    both sides must sample at the same `z`, or their two approximations of it are separated by
    this filter rather than meeting (see `_seed`'s own note on `END_INSET`). The last station is
    therefore restored even when the greedy pass would have dropped it, displacing its neighbour
    instead.
    """
    if len(zs) < 2:
        return list(zs)
    out = [zs[0]]
    for z in zs[1:]:
        if z - out[-1] >= floor:
            out.append(z)
    if out[-1] != zs[-1]:
        # keep the end; drop whatever the greedy pass kept too close in front of it
        while len(out) > 1 and zs[-1] - out[-1] < floor:
            out.pop()
        out.append(zs[-1])
    return out


# --------------------------------------------------------------------------------
# The fit
# --------------------------------------------------------------------------------

def _fit(rows):
    """Section 4.4: a C2 approximation through the eroded contours of one patch.

    Not a loft. A `ruled=True` loft is excluded by requirement (4), and a `ruled=False` loft
    that interpolates the section curves without tangency constraints satisfies neither (3)
    nor generally (2). What the requirement asks for is an approximation with continuity
    constraints, which is the class of construction OpenVSP uses for the exterior.

    **The surface is open in the circumferential direction, not periodic** (section 4.5). Each
    row is the cell's own open arc, bounded at both ends by a construction plane rather than
    wrapping onto itself, so there is no seam to hold continuous and no anchor needed: the two
    ends are already fixed, at the cell's own boundary, the same one at every station. This
    replaced a genuinely periodic fit through the *whole* body (`cowl_interior_surface.md`
    section 9.5, now superseded): that surface had no way to keep a construction edge straight
    and an OML edge curved at the same point, and the two halves it produced met only
    approximately once mirrored back together -- an approximation `removeSplitter` could not
    clean up, surfacing as a near-zero-area seam face and a `fuse`/cut that failed on it. An open
    fit has nothing to round, because the boundary it is asked to hold is a real edge of the
    thing being fitted, not an artefact of how the loop was closed.

    The periodicity comes from curves that really have it, and is carried into the surface by
    `buildFromPolesMultsKnots`. Every row carries the same number of points and is given the
    same explicit parameterisation, so every row curve comes out with the same knot vector and
    the same pole count -- which is what makes a pole track something it is meaningful to
    interpolate along.

    A patch seeded with two stations comes out degree 1 in the axial direction. That is not a
    violation of requirement (4): a patch is bounded by two genuine creases in the exterior,
    continuity is required *within* one, and a two-station patch has no interior join to be
    continuous across. It survives only because section 5's midpoint check found it already
    within `TAU` of the erosion.
    """
    zs = [z for z, _pts in rows]
    n = len(rows[0][1])

    # V: one open curve per row, its two ends the cell's own construction plane. The
    # parameterisation is given explicitly rather than left to chord length so that every row
    # lands on the same knot vector -- rows differ in perimeter, and chord length would give
    # each its own.
    vparams = [i / float(n - 1) for i in range(n)]
    curves = []
    for z, pts in rows:
        curve = Part.BSplineCurve()
        curve.interpolate(Points=[App.Vector(x, y, z) for x, y in pts],
                          PeriodicFlag=False, Parameters=vparams)
        curves.append(curve)

    # U: interpolate each pole track through the stations. Same argument for giving the
    # parameters explicitly -- every track must share a knot vector for the poles to assemble
    # into a grid.
    lo, hi = zs[0], zs[-1]
    span = hi - lo
    uparams = [(z - lo) / span for z in zs]
    poles = [curve.getPoles() for curve in curves]
    tracks = []
    for j in range(len(poles[0])):
        track = Part.BSplineCurve()
        track.interpolate(Points=[poles[i][j] for i in range(len(rows))], Parameters=uparams)
        tracks.append(track)

    grid = [[track.getPoles()[i] for track in tracks] for i in range(tracks[0].NbPoles)]
    surf = Part.BSplineSurface()
    surf.buildFromPolesMultsKnots(
        grid,
        tracks[0].getMultiplicities(), curves[0].getMultiplicities(),
        tracks[0].getKnots(), curves[0].getKnots(),
        False, False,
        tracks[0].Degree, curves[0].Degree)
    return surf


def _lid(surf, u, z, planes):
    """A patch's cap at one of its two axial ends, taken from the surface's own iso curve and
    closed across the cell's construction boundary(ies) (section 4.5).

    From the surface rather than from the sample polygon, so the cap edge *is* the surface edge
    and the piece closes without a tolerance argument. `surf.uIso(u)` is now open, not closed --
    its two ends are the cell's own construction plane(s), not a wrap of the same point -- so
    closing it is never optional the way the old wire's own occasional non-closure was.

    One plane (the tail's half): both ends already sit on it, so a single straight chord between
    them closes the loop, in the plane, exactly. Two planes (the nose's octant): the ends sit on
    two different planes that share only the part's own axis, so a chord would cut that corner
    off; the wedge closes correctly by routing through the axis point at this station instead,
    one straight segment in each plane.
    """
    wire = Part.Wire([surf.uIso(u).toShape()])
    a, b = wire.Vertexes[0].Point, wire.Vertexes[-1].Point
    if len(planes) <= 1:
        closers = [Part.makeLine(b, a)]
    else:
        axis = App.Vector(0, 0, z)
        closers = [Part.makeLine(b, axis), Part.makeLine(axis, a)]
    wire = Part.Wire(wire.Edges + closers)
    try:
        return Part.Face(wire)
    except Exception:                                  # noqa: BLE001 -- non-planar boundary
        return Part.makeFilledFace(wire.Edges)


def _refine(fit_at, outer_at, zs, t, tau, budget, n_check):
    """Section 5: refine until the fitted interior holds the wall, then stop.

    **The criterion is the wall, measured in the layer plane.** At each candidate station the
    fitted surface is sectioned, the section is sampled at `CHECK_ARC`, and every sample's
    distance to the exterior is compared with `t`. What is reported is the worst departure of
    the perimeter width from the width it is supposed to be.

    It used to be the two-sided Hausdorff distance between the fitted contour and an ideal
    eroded contour. That is a proxy for the wall rather than the wall: it bounds the width only
    indirectly, it made section 5 converge on a different quantity from the one
    `check_cowl_interior` accepts the part on, and because both of its sides scaled with the
    sample count it made the whole construction quadratic in a number the rib had set. A
    distance from points to one polyline is linear in the same number, which is what makes it
    affordable to check at the resolution a 1.3 mm rib actually needs.

    Spacing is still derived, not tuned. The tolerance is now the physical one.
    """
    rows = [(z, fit_at(z)) for z in zs]

    while True:
        surf = _fit(rows)
        face = surf.toShape()
        wanted = []
        worst = 0.0
        unsliceable = 0
        shapes = []
        at_floor = 0
        worst_at_floor = 0.0
        for i in range(len(rows) - 1):
            z_a, z_b = rows[i][0], rows[i + 1][0]
            # **Measuring an interval and subdividing it are separate decisions** (IP-FC-144,
            # OQ-DES-CW24). A short interval must not be split -- bisecting it drives the fit
            # further into the near-degenerate condition it is already in -- but it must still
            # be measured, or the worst-conditioned interval in the patch is the one place no
            # number is ever taken. This guard used to `continue` before measuring, which is
            # how a near-duplicate pair could sit in the station set unmeasured at every stage.
            divisible = (z_b - z_a) > 2 * MIN_INTERVAL
            z_m = 0.5 * (z_a + z_b)
            # **An insertion has two possible causes and they are not the same failure.**
            # Either the wall is measurably wrong -- which more stations fix -- or the surface
            # would not section into one open arc at all, which more stations do not fix and
            # which subdividing turns into a silent loop that runs to the budget. They are
            # counted apart so the progress line can say which is happening. The surface is open
            # now, not periodic, so the wanted section is the one open wire, not a closed one.
            sliced = _slice_wires(face, z_m)
            cut = [w for w in sliced if not w.isClosed()]
            if len(cut) != 1:
                unsliceable += 1
                shapes.append('%d wire(s), %d open' % (len(sliced), len(cut)))
                if divisible:
                    wanted.append((i, z_m))
                else:
                    at_floor += 1
                continue
            here, _dense = open_contour(cut[0], n_check)
            gap = float(np.abs(outer_at(z_m).distances(here) - t).max())
            worst = max(worst, gap)
            if gap > tau:
                if divisible:
                    wanted.append((i, z_m))
                else:
                    # Section 5: reaching the floor is a failure to *report*, not a result to
                    # accept. It is reported rather than raised because promoting it to a
                    # refusal is a separate decision nobody has made.
                    at_floor += 1
                    worst_at_floor = max(worst_at_floor, gap)
        if at_floor:
            note('    %d interval(s) at the %.3f mm subdivision floor could not be split; '
                 'worst wall error measured across them %.4f mm against %.3f'
                 % (at_floor, 2 * MIN_INTERVAL, worst_at_floor, tau))
        if not wanted:
            return rows, surf, worst
        note('    refining: %d stations -> %d, worst wall error %.4f mm over %.3f%s'
             % (len(rows), len(rows) + len(wanted), worst, tau,
                '' if not unsliceable else
                '   [%d of %d from a surface that would not section: %s]'
                % (unsliceable, len(wanted), '; '.join(sorted(set(shapes))))))
        if len(rows) + len(wanted) > budget:
            raise Unconverged(
                'section 5 wanted more than %d stations between z = %.4f and %.4f. Worst '
                'measured wall error %.4f mm against %.3f; %d of the %d insertions were not '
                'from a measured wall at all but from a fitted surface that would not section '
                'into one closed loop (%s). Subdividing does not fix that second kind, so if '
                'it dominates here the station count is a symptom and not the problem.'
                % (budget, rows[0][0], rows[-1][0], worst, tau, unsliceable, len(wanted),
                   '; '.join(sorted(set(shapes))) or 'none'))
        for offset, (i, z_m) in enumerate(wanted):
            rows.insert(i + 1 + offset, (z_m, fit_at(z_m)))


def _finished_wall_gap(solid, z, t, outer_at, planes, n_check, plane_tol=FINISHED_PLANE_TOL):
    """Section 5's second pass (IP-FC-143, OQ-DES-CW21): how much *thinner* than `t` the
    finished, rib-cut wall gets at `z`, measured directly against the cut solid instead of the
    smooth pre-rib surface `_refine` checks above.

    **The minimum distance, not the worst absolute deviation -- the same asymmetry
    `check_cowl_interior.wall_thickness` already has, and for the same reason.** Wherever a rib
    bridges, `solid` (the cavity) retreats well inward, and a point on that retreat legitimately
    reads *farther* from the exterior than `t` -- that is the rib doing its job, not a defect.
    Measured 2026-09-25: an early version of this function used the worst *absolute* deviation
    and reported 5-9 mm 'gaps' at essentially every station inside every notch's z-span, because
    it was scoring the rib's own retreat as a failure. Only a point that reads *closer* to the
    exterior than `t` -- the wall thinner than it should be -- is the failure this pass exists
    to catch, exactly as the finished-wall acceptance check itself already treats it.

    **Whole loop, filtered, not `open_arc`.** `solid` here is the multi-patch fused-and-capped
    cavity (the same topology `smooth` has, since cutting the rib tool leaves everything outside
    its own footprint unchanged) -- and `open_arc`'s chain assembly is built for a single raw cut
    body's section, not this shape's. Measured 2026-09-25: calling it here raises
    `PreconditionFailed` (the section's arc edges do not chain into one open run) at the first
    station tried, on a shape that plainly does have a well-formed interior boundary. The whole
    closed loop is discretised instead, and points within `plane_tol` of a construction plane --
    the straight edge `open_arc` would otherwise have stripped -- are dropped before measuring.
    Confirmed against `distToShape` and raw coordinates on the same shape before being trusted
    for this measurement.

    Returns `None` when the section is not exactly one closed loop, or when every discretised
    point falls within `plane_tol` of a construction plane. Both are rare and left unconverted
    rather than raised: this is an additional safety measurement layered on top of section 5's
    existing one, and a station it cannot evaluate is not evidence the wall there is wrong.
    """
    wires = [w for w in _slice_wires(solid, z) if w.isClosed()]
    if len(wires) != 1:
        return None
    pts = wires[0].discretize(Number=n_check)
    inner = [(p.x, p.y) for p in pts
             if all(abs(p.x * n.x + p.y * n.y) > plane_tol for n in planes)]
    if not inner:
        return None
    thinnest = float(np.min(outer_at(z).distances(inner)))
    return max(0.0, t - thinnest)


# --------------------------------------------------------------------------------
# The wall
# --------------------------------------------------------------------------------

def cavity(body, notched, notches, t, overhang_deg, tau=TAU, budget=64, report=None,
           clearance_check=False):
    """The solid the wall encloses, entirely within the symmetry cell: sections 4 and 4.5.

    `body` is the un-mirrored symmetry cell before any notch reached it (`half` for the tail,
    `octant` for the nose), and `notches` the cutting tools that were built in
    that same cell, never mirrored. The tools are taken as given rather than recovered as
    `body - notched`, where `notched` is the cell's own buttress-cut body (`cut`/`OctantCut`
    in `cowl_tree`, `shell_solid`'s own first argument): that difference is the same set inside
    the body, and measured 2026-09-02 it costs 47 s a part to compute and leaves a 202-face
    solid that is slower to section than the tools are.

    **`notched` is also taken directly, since 2026-09-26, for one purpose only: the finished
    wall's true exterior for section 5's second pass, below.** `body`'s own exterior is correct
    for the *first* pass -- the smooth surface must be a valid offset of the un-notched OML,
    since no buttress cut exists yet when it is fitted -- but it is the wrong reference for the
    *second*: wherever a buttress tool has already removed exterior material, `body`'s exterior
    and the finished part's no longer agree. Found by direct measurement (IP-FC-143): at the
    worst point of a real thin station, `body`'s own section was 26.5 mm from the point the real,
    finished wall's exterior passed only 0.56 mm from -- two different surfaces, not a sampling
    or tolerance difference. **Read by slicing `notched` directly, never by cutting it against
    the cavity here.** A second, slightly different boolean between `notched` and this
    function's own cavity would be exactly the "two shapes each independently ... then a
    boolean between them" trap `shell_solid`'s own docstring already recounts three instances
    of -- the one authoritative cut stays `shell_solid`'s `notched.cut(inside)`, and this
    function only ever compares two already-sliced contours, the same way `outer_at` below
    already does against `body`.

    **Every station's section is a cell, not a full loop, and it is treated as one.** `body` is
    a real solid with a flat construction face wherever it was cut to make the cell, so its
    section is a closed loop only in the topological sense; the loop's straight portion is that
    construction cut, not part of the OML. `open_arc` removes it before anything is fitted, and
    the flat cap that restores it (`_lid`, `_side_caps`) is added back afterwards as its own
    exact planar face, so the fitted surface itself is genuinely open with two ends, never
    periodic. `shell_solid` cuts this cavity out of the cell's own buttress-cut body first, and
    mirrors the finished cell wall -- not this cavity, and not the cell's un-notched body --
    across the same planes exactly once; an exact flat face mirrors onto itself, which is what
    makes that mirror-sew exact instead of the near-miss the two superseded attempts left at the
    seam.

    **Two steps, not one, within the cell.** The surface is fitted through the eroded cell body
    -- an open rounded-rectangle arc, smooth everywhere but at its own two known ends -- and the
    ribs (the cell's own tools only) are then subtracted from the closed result as a solid.
    `dilated_notches` records what fitting a surface through the creased contour instead cost,
    and why the identity is evaluated in 3-D here rather than station by station in 2-D.

    **Section 5 runs twice, against two different shapes (IP-FC-143, OQ-DES-CW21).** The first
    pass, `_refine`, converges the smooth surface above against the true erosion before any rib
    reaches it, seeded with every notch edge up front so its own bisection has less to find later
    (OQ-DES-CW22) -- but that convergence is not sufficient on its own: the *finished*, rib-cut
    wall can read thinner than `tau` at a station the smooth surface already passes, because the
    rib cut removes measurably more material there than the smooth offset predicts, near the
    shallow-angle end of this construction's notch angles. The second pass, after the rib cut
    below, re-measures the finished wall on an independent grid -- a uniform pass everywhere plus
    extra density around each notch edge (`EDGE_SCAN_MARGIN`/`EDGE_SCAN_STEP`), not merely
    `_refine`'s own row midpoints, which a real build was found to miss the defect at entirely --
    and, where a scanned point exceeds `tau`, inserts the midpoint of the two already-adjacent
    rows that bracket it and re-cuts. Round 0 scans every patch in full; every round after only
    re-scans a `POST_CUT_RESCAN_MARGIN` window around that round's own insertions, sized from a
    direct measurement of how far one such insertion's effect actually reaches (OQ-DES-CW22) --
    bounded by `POST_CUT_ROUNDS`, since evidence gathered before this was written shows the gap
    does not always close quickly, and an unconverged build raises rather than ships a wall this
    pass has already measured as thin.

    **`clearance_check`, opt-in, off by default (OQ-DES-CW24).** Runs `clearance_margin_scan`
    against the converged smooth surface and the individual dilated ribs once the cut above has
    succeeded, and reports Metric A's flagged stations through `report`, the same callback
    `disconnected_pieces` and `smooth_shape` already use. Never raises and never changes `solid`:
    flag-only. The companion ratio once reported beside it, "Metric B", was removed on 2026-10-04
    (IP-FC-147) because it did not measure crowding -- see `clearance_margin_scan`. Metric A
    survives as a rib-cut clearance diagnostic only; its description as a wall-thickness signal is
    withdrawn, and whether it is kept at all is OQ-DES-CW25, which turns on a floor-versus-flank
    measurement nobody has taken. **This is not a construction-failure check** -- the checks that
    catch a severed wall are `shell_solid()`'s own solid-count and partition tests. Left off by
    default because the scan itself costs on the order of an hour on top of an ordinary build.
    """
    planes = cell_boundary_planes(body)
    lo, hi = z_extent(body)
    z_lo, z_hi = lo + END_INSET, hi - END_INSET

    arcs = {}
    outers = {}
    fits = {}
    finished_outers = {}

    def key(z):
        return round(z / Z_TOL)

    def body_arc(z):
        """`(open arc, plane at its start, plane at its end, flip)`, cached -- every user of a
        station's true exterior goes through this, so the cell's construction edges are
        stripped out, and the arc's orientation fixed, exactly once per station."""
        k = key(z)
        if k not in arcs:
            wires = _slice_wires(body, z)
            if len(wires) != 1:
                raise PreconditionFailed(
                    'P2: the cell body sections into %d loops at z = %.4f, not one'
                    % (len(wires), z))
            arcs[k] = open_arc(wires[0], planes)
        return arcs[k]

    # **One sample count for the whole part, taken from its widest section.** The fit needs a
    # rectangular grid, so every station in a patch must carry the same number of points; taking
    # it from the widest section makes the spacing finest where the contour is longest and never
    # coarser than `FIT_ARC` anywhere.
    widest = max(body_arc(z)[0].Length
                 for z in (z_lo, 0.5 * (z_lo + z_hi), z_hi))
    n_fit = fit_samples(widest)
    n_check = check_samples(widest)

    def fit_at(z):
        """The eroded cell arc at `z`, at fit resolution: one row of the grid."""
        k = key(z)
        if k not in fits:
            arc, p_start, p_end, flip = body_arc(z)
            fits[k] = _resample_open(eroded_arc(arc, t, z, p_start, p_end, flip), n_fit)
        return fits[k]

    def outer_at(z):
        """The exterior at `z` as a dense polyline: what the wall is measured out to.

        **`body`'s exterior, correct only before any buttress cut.** Section 5's first pass
        uses this -- the smooth surface must offset the un-notched OML, since no cut exists yet
        when it is fitted. `finished_outer_at` below is the post-cut equivalent, and the two
        must never be swapped."""
        k = key(z)
        if k not in outers:
            arc, _p0, _p1, flip = body_arc(z)
            outers[k] = open_contour(arc, n_check, flip)[1]
        return outers[k]

    def finished_outer_at(z):
        """The *finished* exterior at `z`, from `notched`, not `body`: section 5's second pass.

        **Sliced directly, never by cutting `notched` against this function's own cavity.**
        Wherever a buttress tool has already removed exterior material, `body`'s exterior and
        the real, finished part's diverge -- measured 26.5 mm apart at one real thin station's
        worst point, against the 0.56 mm the finished wall's own exterior actually reads there
        (IP-FC-143). A fresh boolean between `notched` and the cavity here would risk exactly
        the "two independently-built shapes, then a boolean between them" mistake
        `shell_solid`'s docstring already recounts three times; comparing two already-sliced
        contours instead is the same safe pattern `outer_at` above already uses.

        **Whole loop, filtered, not `open_arc` -- the same reason and the same fix
        `_finished_wall_gap` already needed for `solid`'s own section.** Tried `open_arc` first
        and it failed the same way: measured 2026-09-26, `_chain` raises `PreconditionFailed`
        ("do not chain into one open run") at the very first station tried, on `tail_shell`
        `U` = 1.0 -- a build with no buttress cut anywhere near a construction plane, so a
        notched cell's section cannot be relied on to chain cleanly even where `body`'s always
        did. The whole closed loop is discretised instead, with points near a construction plane
        dropped exactly as `_finished_wall_gap` already drops them from `inner`.

        **Built open (`closed=False`), never closed, and that is the whole fix.** A first version
        of this passed the filtered points to `_Polyline` at its default `closed=True`, on the
        reasoning that both sides of every comparison exclude the same zone so the closing chord
        could never be nearest to a surviving point -- wrong, measured the same day: the tail's
        one construction plane is the cell's flat diameter side, so the excluded strip spans the
        section's full width (x = -50 to +50 at this build's scale), and the closing chord across
        it is a near-straight line at `y` just above `FINISHED_PLANE_TOL` from one side to the
        other -- which sits *close to*, not far from, a legitimate kept point anywhere along that
        same flat side. Measured directly: this gave `_finished_wall_gap` a 'thinnest' of
        0.006-0.09 mm (a 0.59-0.55 mm 'gap') at *every* station near the cell's open end on a
        `U` = 1.0 build previously always clean, because the closing chord passed within a tenth
        of a millimetre of real, legitimate interior points nowhere near any actual notch.
        `outer_at` above never had this failure because `open_contour` already builds its
        polyline `closed=False` -- the same discipline, applied here without `open_arc`'s own
        chain-assembly step, which is what could not be reused in the first place.

        **The filtered points are rotated to start inside the excluded run, not assumed to
        already start there.** `wire.discretize` begins at whatever parameter OCC happens to
        pick, so the excluded construction-plane strip can land split across the start and end of
        the raw point list rather than as one contiguous block in the middle; naively slicing
        would then treat it as if there were two separate exteriors. Rotating so index 0 is
        inside the first excluded run makes everything after it, up to the next excluded run, the
        one true open arc.

        **May see more than one wire where `body_arc` only ever saw one.** A buttress slot can
        make the cell's own exterior boundary trace in and back out around it without splitting
        the wire, but is not guaranteed to -- so, unlike `body_arc`'s strict P2, the largest
        enclosed area (by `_wire_area`, the same measure `check_cowl_interior.wall_thickness`
        was corrected to sort by, IP-FC-143) is taken as the true exterior when there is more
        than one. **A second, separate exclusion run is refused, not merged.** The tail's single
        cell plane crosses the loop's boundary along one contiguous run; the nose's two planes
        have never been exercised through this path, and a second run there would need
        stitching into the comparison rather than being silently dropped."""
        k = key(z)
        if k not in finished_outers:
            wires = [w for w in _slice_wires(notched, z) if w.isClosed()]
            if not wires:
                raise PreconditionFailed(
                    'P2: the buttress-cut cell has no closed section at z = %.4f' % z)
            wire = wires[0] if len(wires) == 1 else max(wires, key=lambda w: abs(_wire_area(w)))
            pts = wire.discretize(Number=n_check)

            def excluded(p):
                return not all(abs(p.x * n.x + p.y * n.y) > FINISHED_PLANE_TOL for n in planes)

            exc_idx = [i for i, p in enumerate(pts) if excluded(p)]
            if not exc_idx:
                raise PreconditionFailed(
                    'P2: no construction-plane crossing found in the buttress-cut cell\'s '
                    'section at z = %.4f' % z)
            rotated = pts[exc_idx[0]:] + pts[:exc_idx[0]]
            kept, runs = [], 0
            prev_excluded = True
            for p in rotated:
                exc = excluded(p)
                if not exc:
                    kept.append((p.x, p.y))
                    if prev_excluded:
                        runs += 1
                prev_excluded = exc
            if not kept:
                raise PreconditionFailed(
                    'P2: every discretised point of the buttress-cut cell\'s section at '
                    'z = %.4f falls within %.2f mm of a construction plane' % (z, FINISHED_PLANE_TOL))
            if runs > 1:
                raise PreconditionFailed(
                    'P2: the buttress-cut cell\'s section at z = %.4f crosses a construction '
                    'plane in %d separate places, not one -- only a single contiguous exterior '
                    'run is handled here' % (z, runs))
            finished_outers[k] = _Polyline(kept, closed=False)
        return finished_outers[k]

    note('interior: z %.3f .. %.3f, %d fit points (%.3f mm apart), %d check points '
         '(%.3f mm apart), %d cell plane(s)'
         % (z_lo, z_hi, n_fit, widest / n_fit, n_check, widest / n_check, len(planes)))

    # **The body's own creases, not the notches'.** The surface follows the un-notched blank
    # now, so a rib start is not a boundary for it -- the rib is subtracted afterwards and
    # brings its own edges. Splitting at every rib end is what made the tail 60 patches.
    features = feature_stations(body, z_lo, z_hi)
    patches = _patches(z_lo, z_hi, features)

    # **The notches' own edges, this time -- for section 5's second-pass scan, not for
    # patching.** The same function, called against the actual tools instead of `body`, reads
    # off exactly where a rib's own ramp starts, ends, or meets the cut plane: the axial
    # positions `EDGE_SCAN_MARGIN`/`EDGE_SCAN_STEP` sample finely around, below.
    notch_edges = feature_stations(notches, z_lo, z_hi)
    if not patches:
        raise PreconditionFailed('the part is shorter than the %.2f mm interval floor'
                                 % MIN_INTERVAL)

    # **One closed solid per patch, fused, rather than one sewn shell.** Interpolation makes
    # adjacent patches pass exactly through the station they share, so their edges now coincide
    # rather than merely agreeing to a fitting tolerance -- but capping each patch and fusing is
    # kept regardless. A sew has to be told how far apart two edges may be before it joins them,
    # and a number that is wrong in either direction fails silently: too small and the shell
    # stays open, too large and it welds across a gap that was real. The fuse needs no such
    # number.
    def assemble_patch(surf, rows, is_lo_end, is_hi_end):
        """One patch's closed solid plus its outward end-overrun piece(s), from an already-fit
        surface. Split out from the patch loop below so a post-cut re-fit (section 5, second
        pass) can rebuild one patch without repeating `_refine`'s own convergence."""
        u0, u1, _v0, _v1 = surf.bounds()
        lids = [_lid(surf, u0, rows[0][0], planes), _lid(surf, u1, rows[-1][0], planes)]
        sides = _side_caps(surf, planes)
        main = Part.Solid(Part.Shell([surf.toShape()] + lids + sides))
        extra = []
        # **The two open ends are extended past the part, not stopped at it.** A station may
        # not sit exactly on a planar end -- sectioning there returns the end face's boundary
        # rather than the body's -- so the cavity stops `END_INSET` short at each end, and a
        # cavity that stops short leaves a film of solid material closing the very opening the
        # cowl is open at. It renders, it is valid, and it is a cowl with its ends skinned
        # over. Extending the end caps outward removes it, and the extension falls outside the
        # blank so it cuts nothing else.
        if is_lo_end:
            extra.append(lids[0].extrude(App.Vector(0, 0, -END_OVERRUN)))
        if is_hi_end:
            extra.append(lids[1].extrude(App.Vector(0, 0, END_OVERRUN)))
        return main, extra

    patch_entries = []
    started = time.time()
    for index, (p_lo, p_hi) in enumerate(patches):
        at = time.time()
        zs = _seed(p_lo, p_hi, p_lo <= z_lo, p_hi >= z_hi)
        # **Front-loaded with the notch topology's own edges (OQ-DES-CW22).** Section 5's second
        # pass used to discover every station it needed one bisection at a time, which is what
        # made real convergence expensive (IP-FC-143): up to six rounds, each re-scanning the
        # whole patch, to reach a station `_refine`'s own uniform seed was never going to suggest
        # on its own. Seeding `_refine` with every notch edge inside this patch up front, before
        # its own convergence ever runs, lets its existing bisection discipline (never an
        # arbitrary station, only ever the exact midpoint of two already-adjacent rows) settle
        # around them from the start -- this is not the "insert an arbitrary station into an
        # already-converged fit" case measured catastrophic before this pass was written; it is a
        # richer starting seed for a convergence that has not run yet.
        zs = sorted(set(zs) | {e for e in notch_edges if p_lo < e < p_hi})
        # **The union is where a near-duplicate pair gets in** (IP-FC-144, OQ-DES-CW24
        # alternative 2). The seed stations and the notch edges are filtered against
        # themselves but never against each other, so two individually legitimate stations
        # can land arbitrarily close. Measured: this costs no accuracy -- same worst wall
        # error, 0.0496 mm, at 30 rows instead of 36 and 416.9 s instead of 539.8 s.
        kept = _thin_stations(zs, station_floor(t))
        if len(kept) != len(zs):
            note('    patch %d: %d stations -> %d on the %.3f mm floor'
                 % (index, len(zs), len(kept), station_floor(t)))
        zs = kept

        # P1 over the patch, on the un-notched cell body, before anything is fitted. The two
        # contours being compared must be in the same order -- point i means the same place on
        # the section at both z -- which is exactly what `flip` guarantees across stations.
        prev = None
        for z in zs:
            arc, _p0, _p1, flip = body_arc(z)
            here, _d = open_contour(arc, n_check, flip)
            if prev is not None:
                _check_slope(prev[1], here, prev[0], z, overhang_deg)
            prev = (z, here)

        rows, surf, worst = _refine(fit_at, outer_at, zs, t, tau, budget, n_check)
        # Section 4.5: both cowls are open axially -- the tail at both ends, the nose body where
        # it is cut to the closure parts -- so a patch is closed by the two contours it already
        # has and there is no turnover to handle. The caps come from the fitted surface's own iso
        # curves rather than from the sample polygon, so the cap edge *is* the surface edge and
        # the piece closes without a tolerance argument. `_side_caps` closes the *other* pair of
        # free edges, along the cell's construction plane(s), which `_lid` does not reach.
        is_lo_end, is_hi_end = p_lo <= z_lo, p_hi >= z_hi
        main, extra = assemble_patch(surf, rows, is_lo_end, is_hi_end)
        patch_entries.append({'p_lo': p_lo, 'p_hi': p_hi, 'is_lo_end': is_lo_end,
                              'is_hi_end': is_hi_end, 'rows': rows, 'main': main,
                              'extra': extra})

        note('patch %d/%d  z %9.4f .. %9.4f (%6.3f mm)  %2d seeded -> %2d stations  '
             'worst wall %.4f  %5.1f s  [%.0f s total]'
             % (index + 1, len(patches), p_lo, p_hi, p_hi - p_lo, len(zs), len(rows),
                worst, time.time() - at, time.time() - started))
        # **The positions, in the log and not only in the report.** Two builds that both settle
        # on the same number of stations have not necessarily settled on the same stations, and
        # a build that lands elsewhere produces a different surface, different end caps and a
        # different wall while the progress line above reads identically.
        note('    at %s' % ' '.join('%.4f' % z for z, _pts in rows))

    def fuse_smooth(entries):
        pieces = []
        for entry in entries:
            pieces.append(entry['main'])
            pieces.extend(entry['extra'])
        note('fusing %d pieces' % len(pieces))
        at = time.time()
        fused = pieces[0]
        for piece in pieces[1:]:
            fused = fused.fuse(piece)
        fused = fused.removeSplitter()
        note('smooth interior: %d solids, valid=%s, %.4f mm3, %.0f s to fuse'
             % (len(fused.Solids), fused.isValid(), fused.Volume, time.time() - at))
        return fused

    smooth = fuse_smooth(patch_entries)

    # Section 4.2's right-hand term, applied here rather than fitted into the surface above.
    # **Fused into one tool, and the result verified against it.** Cutting with a list of
    # twenty-two separate tools is what the earlier code did, and it succeeds on one surface
    # and partially fails on another -- the failure is silent, because a cavity with a rib left
    # in it is still a valid closed solid. Fusing first costs a few seconds and gives the
    # kernel one boolean to reason about instead of twenty-two.
    #
    # **IP-FC-116's route (a) -- cut one tool at a time with the residue check after each --
    # was tried here and reverted, 2026-09-11.** The item cites a harness measurement of 202 s
    # against 256 s for cutting one at a time. Run end to end on the real tail at `U` = 1
    # instead of in that harness, cutting one at a time cost **485 s** against this route's
    # **330 s** -- 47% slower, not faster, and a second attempt deferring `removeSplitter` to
    # once after the loop, in case 22 cleanup passes over a growing shape were the cause,
    # measured 498 s, no better. **What says the geometry was unaffected is the residue and
    # the topology, not the volume**: both variants closed with 0.000000 mm3 of rib left
    # inside, one valid solid, and a worst wall error matching this route's to the fourth
    # decimal (0.0480 against 0.0479). Their `Shape.Volume` figures agree to 0.07% as well,
    # but that is not evidence and is recorded only so the numbers are not mistaken for it --
    # IP-FC-119 measured `Shape.Volume` wrong by 0.16 to 0.24% on exactly these B-spline
    # solids, so a 0.07% agreement sits *inside* the instrument's own error and would look
    # the same whether the walls matched or not. So the geometry was never in question on
    # the evidence that can carry it, only the time, and cutting one
    # tool at a time against a solid whose face count grows with every prior cut is simply
    # more expensive than fusing the tools first and handing the kernel one clean cut against
    # the pristine interior. The harness that produced 202/256 was not this function and
    # evidently was not representative of it; kept as the reference for what to re-examine if
    # this is revisited, not as a result to trust unverified again.
    #
    # **Computed once, outside the post-cut refinement loop below.** The dilated tool depends
    # only on `notches` and `t`, neither of which the loop below ever changes -- only the
    # smooth surface it cuts does -- so re-dilating and re-fusing it on every round would repeat
    # the single most expensive step in the whole build (IP-FC-116: ~72 s dilating, ~260 s
    # fusing at `U` = 1, both growing with `U`) for no reason.
    ribs = dilated_notches(notches, t, report)
    tool = ribs[0] if len(ribs) == 1 else ribs[0].fuse(ribs[1:]).removeSplitter()

    def cut_and_check(smooth_shape):
        """One rib cut plus its two existing identity checks (section 4.2's residue, and the
        cavity's own connectivity), factored out so the post-cut refinement loop below can
        redo just this step -- the expensive dilation above is not repeated."""
        at = time.time()
        cut = smooth_shape.cut((tool,), RIB_CUT_FUZZ).removeSplitter()
        left = cut.common((tool,), RIB_CUT_FUZZ)
        if left.Volume > RIB_RESIDUE:
            note('    %.4f mm3 of rib survived the cut; taking it out again' % left.Volume)
            cut = cut.cut((left,), RIB_CUT_FUZZ).removeSplitter()
            left = cut.common((tool,), RIB_CUT_FUZZ)
        if left.Volume > RIB_RESIDUE:
            raise Unconverged(
                '%.4f mm3 of dilated rib is still inside the cavity after the cut and one '
                'retry, in %d piece(s). The cavity is therefore larger than the erosion allows '
                'and the wall will be thin or missing wherever that rib should have been -- '
                'and since the ribs are what bridge the buttress slots, the wall comes out in '
                'pieces. Nothing downstream catches this: the cavity is a valid closed solid '
                'either way.' % (left.Volume, len(left.Solids)))
        if len(cut.Solids) != 1:
            if report is not None:
                report.update(disconnected_pieces=[(s.Volume, s.BoundBox) for s in cut.Solids],
                              rib_tool=tool)
            raise Unconverged(
                '%d disconnected solids where the cavity should be one. There is no zero rib '
                'residue reading that makes this acceptable: a rib is what bridges a buttress '
                'slot, so a cavity split into pieces means a rib did not form a connection '
                'somewhere, not that the geometry has a legitimate second piece. This is '
                'checked separately from the residue above because a rib can be volumetrically '
                'fully removed and still fail to bridge -- disconnection is a topology defect, '
                'not a volume one, and a disconnected result is refused at any `U`, never '
                'accepted as one more shape mirroring has to handle.' % len(cut.Solids))
        note('ribs cut in %.0f s, %.6f mm3 left inside' % (time.time() - at, left.Volume))
        return cut, left.Volume

    solid, rib_residue = cut_and_check(smooth)

    # **Section 5's second pass: the finished, rib-cut wall, not only the smooth surface above.**
    # Everything up to here converges the smooth interior against the true erosion (section 4.2)
    # before any rib is cut into it -- proven correct by IP-FC-143's own investigation to be
    # insufficient on its own: the finished wall can read thinner than `tau` at a station the
    # smooth surface already passes cleanly, specifically near the tail's shallow-angle diagonal
    # buttresses, because the rib cut removes measurably more material there than the smooth
    # surface's own offset predicts -- a real, bounded property of the dilated rib tool meeting
    # the fitted surface at a shallow angle, not a defect in the fit above.
    #
    # **Extends the existing bisection discipline; does not invent a new one.** Tested directly
    # before this was written: forcing an extra station at an arbitrary `z` -- one that is not
    # the exact midpoint of two already-adjacent rows -- made the finished wall dramatically
    # *thinner* everywhere in the patch (0.10-0.35 mm worse at every flagged station, tail
    # `U` = 3.0), not better. Only a station inserted the same way `_refine` already inserts one
    # -- the exact midpoint of two rows that are already adjacent -- keeps the fit's own row
    # spacing regular enough not to damage it. So this loop checks the same candidate points
    # `_refine` would (every current midpoint, per patch), against a different measurement: the
    # finished solid's own section, not the smooth surface's.
    #
    # **Bounded by round count as well as by station count.** Uniformly tightening `tau` 5x
    # (IP-FC-143, 2026-09-25) moved most flagged stations toward `t`, but the single worst one
    # barely moved (+0.0012 mm of a 0.0531 mm deficit) even at that much finer a grid -- so full
    # convergence at the hardest station is not guaranteed cheaply, and `POST_CUT_ROUNDS` exists
    # so a build that is not converging raises `Unconverged` (refusing to silently ship a wall
    # this pass has caught) rather than repeating the single most expensive step in this
    # function -- the cut, not the dilation, which is cached above -- an unbounded number of
    # times.
    # **Scanned on a grid independent of the smooth-fit rows, not just at their own midpoints.**
    # Checking only the current rows' midpoints (as `_refine`'s own pre-cut pass does) missed the
    # defect entirely, tested 2026-09-25: `tail_shell` `U` = 3.0's rows never happen to bracket
    # z = -217.7270 at a midpoint, so a version of this loop that only checked existing midpoints
    # converged after zero rounds while the acceptance check's own, differently-spaced 12-station
    # grid still read that station 0.0531 mm thin. A failing scan point still only ever causes a
    # midpoint insertion, never a station at the failing point itself -- test 2 in this item's
    # own pre-implementation check showed exactly why that discipline matters -- it is looked up
    # against the two already-adjacent rows that bracket it and *their* midpoint is what gets
    # inserted, same as `_refine` would do if it had found the same interval wanting.
    # **The scan grid itself, built once, not every round.** Each patch's outer bound (its
    # first and last row) never moves once `_refine` has converged -- a round only ever inserts
    # *interior* rows -- so the set of z's worth checking is round-invariant, even though which
    # row-pair brackets each one is not. Uniform coverage stays everywhere a defect could in
    # principle be found anywhere; the extra density around each notch edge targets exactly
    # where this item's own investigation says the sharp local peak actually lives, and does not
    # replace the uniform pass's own coverage of everywhere else.
    round0_scan_by_patch = {}
    for ei, entry in enumerate(patch_entries):
        z0, z1 = entry['rows'][0][0], entry['rows'][-1][0]
        # **1 mm apart, not tied to the row count.** A 76-point scan (4x this patch's own 19
        # rows) missed the defect at `z` = -217.7270 by 2 mm and read 0.0430 mm there against
        # the acceptance check's own 0.0531 mm at the exact station -- close enough that the
        # cause was under-sampling a real, fairly sharp local peak, not a difference in what
        # is being measured.
        n_scan = max(min(int((z1 - z0) / 1.0), 500), 40)
        zs = [z0 + (z1 - z0) * k / float(n_scan - 1) for k in range(n_scan)]
        n_edge = 0
        for edge in notch_edges:
            if not (z0 < edge < z1):
                continue
            lo_m = max(z0, edge - EDGE_SCAN_MARGIN)
            hi_m = min(z1, edge + EDGE_SCAN_MARGIN)
            steps = max(int((hi_m - lo_m) / EDGE_SCAN_STEP), 2)
            zs.extend(lo_m + (hi_m - lo_m) * m / float(steps) for m in range(steps + 1))
            n_edge += steps + 1
        round0_scan_by_patch[ei] = sorted(set(zs))
        note('    patch %d/%d scan: %d uniform + %d edge-focused (%d notch edge(s)) -> %d points'
             % (ei + 1, len(patch_entries), n_scan, n_edge, len(notch_edges),
                len(round0_scan_by_patch[ei])))

    # **Round 0 scans every patch in full; round 1 onward only re-scans a window around that
    # round's own insertions (OQ-DES-CW22).** A patch with no entry in `current_scan` is not
    # scanned at all that round -- correct, not just cheap, because patches are independent: a
    # change to one patch's fit and cut cannot move another patch's cavity boundary (each
    # contributes its own closed solid to the fuse, which cannot alter geometry outside the piece
    # that changed), and within the *same* patch, `POST_CUT_RESCAN_MARGIN` is itself the measured
    # distance beyond which one insertion's own effect is indistinguishable from noise.
    current_scan = round0_scan_by_patch
    worst_finished = 0.0
    for round_ in range(POST_CUT_ROUNDS + 1):
        insertions = {}                                   # (ei, i) -> worst gap seen in that interval
        worst_finished = 0.0
        for ei, entry in enumerate(patch_entries):
            rows = entry['rows']
            i = 0
            for z in current_scan.get(ei, ()):
                while i < len(rows) - 2 and rows[i + 1][0] <= z:
                    i += 1
                z_a, z_b = rows[i][0], rows[i + 1][0]
                # **Measure first, decide about splitting second** (IP-FC-144, OQ-DES-CW24).
                # This guard used to skip before `_finished_wall_gap` was ever called, so the
                # *finished* wall was never measured across a short interval and
                # `worst_finished` could not include it -- the same blind spot `_refine` had,
                # one pass later and on the real cut rather than the smooth surface.
                divisible = (z_b - z_a) > 2 * MIN_INTERVAL
                gap = _finished_wall_gap(solid, z, t, finished_outer_at, planes, n_check)
                if gap is None:
                    continue
                worst_finished = max(worst_finished, gap)
                if gap > tau and not divisible:
                    note('    patch %d: finished wall %.4f mm over %.3f at z = %.4f, in an '
                         'interval at the %.3f mm subdivision floor; reported, not split'
                         % (ei, gap, tau, z, 2 * MIN_INTERVAL))
                if gap > tau and divisible:
                    # **`slot`, not `key`.** `cavity()` already has a `key(z)` helper in this
                    # same scope (the station-position cache above), and reusing that name for
                    # this tuple silently shadowed it for the rest of the function's execution --
                    # found 2026-09-26 when `finished_outer_at` (which calls `key(z)`) started
                    # raising `TypeError: 'tuple' object is not callable` the first time this
                    # branch ever actually ran, since every earlier test of this loop had zero
                    # insertions and never reached this line.
                    slot = (ei, i)
                    insertions[slot] = max(insertions.get(slot, 0.0), gap)
        if not insertions:
            break
        if round_ == POST_CUT_ROUNDS:
            raise Unconverged(
                'section 5\'s second pass wanted more stations after %d round(s) of re-cutting '
                'the finished wall, worst measured gap %.4f mm against %.3f, in %d interval(s). '
                'The smooth surface passes its own criterion already -- this is the rib cut '
                'removing measurably more material than the smooth offset predicts, near a '
                'shallow-angle notch boundary, and more stations have not closed it.'
                % (POST_CUT_ROUNDS, worst_finished, tau, len(insertions)))
        note('    post-cut refine: round %d, worst finished-wall gap %.4f mm over %.3f, '
             'inserting %d station(s)' % (round_ + 1, worst_finished, tau, len(insertions)))
        by_patch = {}
        for (ei, i) in insertions:
            by_patch.setdefault(ei, []).append(i)
        next_scan = {}
        for ei, indices in sorted(by_patch.items()):
            entry = patch_entries[ei]
            rows = entry['rows']
            midpoints = [0.5 * (rows[i][0] + rows[i + 1][0]) for i in indices]
            new_zs = sorted(set([z for z, _pts in rows] + midpoints))
            if len(new_zs) > budget:
                raise Unconverged(
                    'section 5\'s second pass wanted more than %d stations in the patch z '
                    '%.4f..%.4f, driven by the finished wall rather than the smooth surface.'
                    % (budget, entry['p_lo'], entry['p_hi']))
            new_rows = [(z, fit_at(z)) for z in new_zs]
            surf2 = _fit(new_rows)
            main2, extra2 = assemble_patch(surf2, new_rows, entry['is_lo_end'],
                                           entry['is_hi_end'])
            patch_entries[ei] = dict(entry, rows=new_rows, main=main2, extra=extra2)
            z0p, z1p = new_rows[0][0], new_rows[-1][0]
            window_zs = []
            for mz in midpoints:
                lo_w = max(z0p, mz - POST_CUT_RESCAN_MARGIN)
                hi_w = min(z1p, mz + POST_CUT_RESCAN_MARGIN)
                steps = max(int((hi_w - lo_w) / 1.0), 10)
                window_zs.extend(lo_w + (hi_w - lo_w) * m / float(steps) for m in range(steps + 1))
            next_scan[ei] = sorted(set(window_zs))
        current_scan = next_scan
        smooth = fuse_smooth(patch_entries)
        solid, rib_residue = cut_and_check(smooth)

    # **OQ-DES-CW24's clearance-margin scan, opt-in and off by default.** `ribs` (the unfused,
    # per-tool dilation list, computed once above) is exactly what Metric B needs and the fused
    # `tool` cannot give: which *second* tool is nearest, not only the nearest overall. Run
    # after the post-cut loop above has already converged, against the final `smooth` -- the
    # same candidate surface section 5 itself just finished checking -- so this never measures
    # a surface the rest of `cavity` has already moved past.
    if clearance_check:
        margin = clearance_margin_scan(smooth, ribs, z_lo, z_hi)
        thin = [(z, a) for z, a in margin if a < CLEARANCE_MARGIN_MM]
        # **IP-FC-148: what each reported minimum is a distance to, if anything.** The scan above
        # takes its minimum over the whole tool section and cannot say either whether the tool is
        # clear of the surface at that station -- if it is not, there is no clearance there to
        # measure -- or which face carries the minimum, of which only the cut floor bounds the
        # finished wall. `clearance_face_scan` answers both and `tool_face_roles` defines the
        # face roles; section 6.3 of cowl_interior_surface.md is the authority on what the
        # answers mean. Run here rather than in a separate pass because this is the one point
        # where the final candidate surface and the per-tool dilation list are both already in
        # hand; it costs one extra slice pair per already-reported station, against the scan's
        # own hundreds.
        faces = clearance_face_scan(smooth, ribs, notches.Solids, body, t,
                                    [z for z, _a in margin])
        for row in faces:
            note('      z %9.4f %-4s %.6f mm -> tool %2d %s %-5s in_blank=%-5s '
                 'bounds_wall=%-5s %-8s inside=%5.1f%%  offset %.4f/%.4f  '
                 'n.gap %+.3f  dot_floor %+.3f'
                 % (row['z'], 'FLAG' if row['metric_a'] < CLEARANCE_MARGIN_MM else '',
                    row['metric_a'], row['tool'],
                    ('face %-2d' % row['face']) if row['on_face_image']
                    else ('EDGE %d/%s' % (row['face'], row.get('second_face'))),
                    row['role'] if row['on_face_image']
                    else '%s|%s' % (row['role'], row.get('second_role')),
                    row['in_blank'], row['bounds_wall'], row['engagement'],
                    100.0 * (row['fraction_inside'] or 0.0),
                    row['offset'], row['expected_offset'], row['normal_dot_gap'],
                    row['dot_floor']))
        tally, engaged = {}, {}
        for row in faces:
            if not row['on_face_image']:
                key = 'an edge between %s and %s' % (row['role'], row.get('second_role'))
            else:
                key = row['role'] + ('' if row['in_blank'] else ' (outside the blank)')
            tally[key] = tally.get(key, 0) + 1
            engaged[row['engagement']] = engaged.get(row['engagement'], 0) + 1
        note('    clearance margin: the minimum lands on %s; %d of %d bound the finished wall, '
             'and the tool is %s -- only a `clear` station reports a clearance at all '
             '(IP-FC-148, OQ-DES-CW25)'
             % ('; '.join('%d x %s' % (tally[k], k) for k in sorted(tally)) or 'nothing',
                sum(1 for row in faces if row['bounds_wall']), len(faces),
                ', '.join('%s at %d' % (k, engaged[k]) for k in sorted(engaged))))
        if report is not None:
            report.update(clearance_faces=faces)
        if thin:
            note('    clearance margin: %d station(s) under the %.3f mm thin-wall flag '
                 '(worst %.6f mm at z = %.4f, flag-only)'
                 % (len(thin), CLEARANCE_MARGIN_MM, thin[0][1], thin[0][0]))
        else:
            note('    clearance margin: no station under the %.3f mm thin-wall flag '
                 '(worst found %.6f mm)' % (CLEARANCE_MARGIN_MM, margin[0][1] if margin else
                                            float('nan')))
        if report is not None:
            report.update(clearance_margin=margin, thin_wall_flags=thin)

    if report is not None:
        # **The shape as well as its measure, and deliberately.** IP-FC-115 compares two ways of
        # assembling the same set -- cut the ribs out of this and cut the result out of the
        # blank, or cut this out of the blank and fuse back the part the ribs occupy -- and the
        # comparison only means anything if both are assembled from the *identical* operands.
        # Handing the surface out here is what makes that one fit instead of two.
        #
        # **Production does pass a report, since 2026-09-11** -- `cowl_tree._CowlShell` wants
        # `partition_slip` out of `shell_solid` for IP-FC-117's soak, and this is the channel
        # that already existed for it. It was true until then that nothing in production
        # passed one, and the note is kept rather than deleted because what it was guarding
        # still holds: everything put in here is either already computed for the `note` below
        # or a length, so a report costs a build nothing measurable, and it must stay that
        # way. The shapes handed out are references, dropped when the caller's dict goes.
        report.update(smooth_volume=smooth.Volume, smooth_faces=len(smooth.Faces),
                      smooth_shape=smooth)
    if report is not None:
        report.update(rib_residue=rib_residue, cavity_volume=solid.Volume,
                      cavity_faces=len(solid.Faces), rib_tool=tool)

    # **`worst_wall` now reports the finished-wall criterion, not the smooth-surface one.**
    # The smooth surface passing its own criterion no longer means the finished wall does --
    # that gap is exactly what this section exists to close -- so the number worth reporting
    # (and worth a future soak comparing against) is the one actually gating convergence here:
    # `worst_finished` from the last, passing round of the loop above.
    stations = sum(len(entry['rows']) for entry in patch_entries)
    chosen = [z for entry in patch_entries for z, _pts in entry['rows']]
    worst_wall = worst_finished
    note('cavity closed: %d solids, valid=%s, %.4f mm3, worst finished wall error %.4f mm, '
         '%.0f s in all' % (len(solid.Solids), solid.isValid(), solid.Volume, worst_wall,
                            time.time() - started))
    if report is not None:
        # **`station_positions`, not `stations`.** The count already has that name below, and an
        # earlier version of this function set `stations` to this same list first and then
        # overwrote it with the count a few lines later -- a real footgun, found 2026-09-24 when
        # a diagnostic script trying to read the positions got the count instead and crashed on
        # it. Given a distinct name here instead of fixed in place, since the count is what every
        # existing caller and report field actually means by `stations`.
        report.update(station_positions=chosen)
        report.update(patches=len(patches), stations=stations, features=len(features),
                      solids=len(solid.Solids), valid=solid.isValid(),
                      worst_wall=worst_wall, fit_points=n_fit, check_points=n_check)
    return solid


#: How much of the blank a cut may fail to account for, as a fraction of the blank.
#:
#: **The check it feeds is an identity, not a tolerance on the answer.** Cutting a solid in two
#: partitions it: `notched - cavity` and `notched & cavity` must together be exactly `notched`.
#: A boolean that drops material breaks that, and nothing else in this construction notices --
#: measured 2026-09-04, a nose build produced a 415.5423 mm3 wall where every other run gave
#: 9713.4 mm3, and the section-6 acceptance test passed it `OK` because a wall that is mostly
#: *missing* still measures 0.600 mm wherever it happens to exist.
#:
#: The floor is what the kernel's own reproducibility costs: repeated cuts of one fixed pair of
#: operands agreed to 0.25 mm3 in 581652 mm3, four parts in ten million, so 1e-4 leaves three
#: orders of headroom over that and still catches a loss of a tenth of a percent.
#:
#: **What this check cannot resolve, measured 2026-09-05 under IP-FC-119.** Both sides of the
#: identity come from `Shape.Volume`, which is wrong by 0.16 to 0.24 % on these B-spline solids,
#: and *its error does not reliably cancel across a partition*. Splitting this wall with a plane
#: and adding the pieces back up leaves a slip of **1.604e-03** by `Shape.Volume` where the same
#: partition measured by tessellation slips only 4.4e-05 -- so 38 mm3 of that is the instrument,
#: not the boolean.
#:
#: The slips actually seen on the cavity cut are ~1e-6, three orders inside this tolerance, so
#: nothing is failing. But the resolution here is not the floor below -- it is whatever
#: `Shape.Volume` happens to do on the two operands, and 1.6e-3 has been measured. **Read this
#: check as a gross-failure detector** -- it caught a wall that came out at 415 mm3 instead of
#: 9713, which is 1.6e-2 and unmissable -- and if it ever fires marginally, suspect the
#: measurement before the boolean. A check with real resolution would take its volumes from
#: `solid_measure.converged_difference`, at a cost of minutes per build.
#:
#: **That suspicion was confirmed directly, 2026-09-21, not just theorised.** The tail at
#: `U` = 1.0 fired this check at 3.593e-04 (106.68 mm3 of a 296939.56 mm3 cell body) under the
#: corrected cell-level construction (OQ-DES-CW20) -- real enough to investigate, since it is
#: over the floor this constant used to hold. Two numerical-robustness interventions were tried
#: first and neither explains it: a fuzzy-boolean tolerance that cleanly fixed an unrelated,
#: genuine disconnection defect at `U` = 0.75 (`RIB_CUT_FUZZ`) barely moved this slip when
#: applied to the rib cut (3.593e-04 -> 3.233e-04) and did not move it at all when applied to
#: the wall cut itself -- a real geometric defect would be expected to respond to exactly this
#: kind of intervention the way the `U` = 0.75 one did, and this did not. Measured independently
#: instead, per this constant's own prescription: `solid_measure.converged_volume` on `wall`,
#: `kept` and the cell body separately (2707448 triangles at 0.00025 mm for the wall, converged)
#: gives a slip of **1.614e-05** (4.79 mm3) -- 22x smaller than `Shape.Volume`'s reading of the
#: same partition, and itself inside the 1.6e-3 ceiling this constant's own docstring already
#: named. No independent measurement anywhere in this item shows real lost material; every one
#: shows the instrument. **The floor is raised accordingly, to sit above the measured ceiling
#: rather than below it**, so a real gross failure still fires while this specific, now-measured
#: noise level does not.
PARTITION_TOL = 2.0e-3


def _extend_across_cell(solid, normal, depth=2.0, tol=1.0e-6):
    """`solid`, continued a short distance past its own exact flat cap(s) at the cell boundary
    plane(s) through the origin.

    **Why this exists.** Cutting `solid` out of another solid that carries that identical exact
    cap is the same degeneracy `_strip_seam`/`mirror_across_cell` already work around for a
    *fuse*, just surfacing in a *cut* instead: two solids meeting at exactly one shared planar
    face and nowhere else is a degenerate case for OCC's general boolean intersector, measured
    2026-09-21 to fail the same way here (`ValueError: Null shape`) when `shell_solid` first
    tried to cut the cell-local cavity straight out of the cell-local buttress-cut body -- both
    of them capped at the identical plane by construction (`_lid`/`_side_caps`, `half_mask`/
    `octant_mask`). Extruding the cap a short distance past the plane turns that cut into an
    ordinary "one solid pokes through a face of the other" boolean, which is not degenerate,
    because the cut's own boundary there no longer coincides with anything in the tool.

    **This cannot leak material the cut should not remove.** A cut only ever removes material the
    base solid already has; extending the *tool* past the base solid's own boundary adds nothing
    the base solid did not already lack there. `body`/`notched` have no material at all past their
    own cell-boundary plane (that is what bounds them to a cell in the first place), so the
    extension contributes nothing to a `.cut()` or `.common()` against them -- the result is
    exactly what a direct cut against the un-extended cavity would have been, had that cut been
    possible.

    **Built by sewing, not by fusing a prism onto the cap.** The first attempt did exactly that --
    `solid.fuse(cap.extrude(...))` -- and hit the identical `ValueError: Null shape`, because a
    prism extruded from `solid`'s own cap face necessarily shares that entire face with `solid`
    itself: fusing it back on is the same degenerate shared-face case this function exists to
    avoid, self-inflicted. Instead the cap is discarded, a far cap and a lateral wall are built
    from its own boundary wires (which is all `f.extrude` on a *wire* gives -- no coincident
    face), and the whole set is sewn: the same construction `mirror_across_cell` already uses,
    linear instead of mirrored.
    """
    n = App.Vector(normal)
    n.normalize()
    keep, caps = [], []
    for f in solid.Faces:
        if not isinstance(f.Surface, Part.Plane):
            keep.append(f)
            continue
        axis = f.Surface.Axis
        axis.normalize()
        if abs(abs(axis.dot(n)) - 1.0) < tol and abs(f.Surface.Position.dot(n)) < tol:
            caps.append(f)
        else:
            keep.append(f)
    if not caps:
        return solid
    if len(caps) > 1:
        # **A fuzzy-boolean cut can split one contiguous cap into several coplanar pieces.**
        # Measured 2026-09-21 at the tail's `U` = 0.5/0.75: `cavity()`'s rib cut, with
        # `RIB_CUT_FUZZ` applied to resolve a real near-tangency defect (see that constant),
        # left the cell-boundary cap as two adjacent faces (1857.29 + 151.93 mm2) instead of the
        # one contiguous face (2009.22 mm2) a plain cut produces -- same combined area, same
        # plane, sharing an edge that is an artefact of the cut, not a real boundary. Extending
        # each piece separately would extrude a lateral wall along that shared edge twice, once
        # from each side, which is why the very first version of this fix produced a shell that
        # sewed but did not solidify validly. Coplanar faces fuse and merge cleanly -- unlike the
        # near-tangent 3-D fuses this module avoids elsewhere -- so the fix is to merge them back
        # into as few faces as the true boundary actually has, before extending any of them.
        merged = caps[0]
        for f in caps[1:]:
            merged = merged.fuse(f)
        caps = merged.removeSplitter().Faces
    extra = []
    for f in caps:
        far = f.copy()
        far.translate(n * -depth)
        extra.append(far)
        for w in f.Wires:
            extra.append(w.extrude(n * -depth))
    sewn = Part.makeCompound(keep + extra)
    sewn.sewShape()
    shells = [s for s in sewn.Shells if s.isClosed()]
    if not shells:
        raise Unconverged(
            'extending the cell result past its own boundary plane %s did not close into any '
            'shell at all' % normal)
    if len(shells) != 1:
        raise Unconverged(
            'extending the cell result past its own boundary plane %s produced %d disconnected '
            'shells, not one -- `solid` was already more than one piece, which is refused '
            'upstream, or this extension broke a connection that was there before it.'
            % (normal, len(shells)))
    solid = Part.Solid(shells[0])
    if not solid.isValid():
        raise Unconverged(
            'extending the cell result past its own boundary plane %s produced a closed shell '
            'that did not solidify validly' % normal)
    return solid


def _strip_seam(solid, normal, tol=1.0e-6):
    """`solid`'s own faces, minus every exact flat cap lying in the mirror plane through the
    origin -- the open shell a mirror should be sewn onto rather than fused against
    (`mirror_across_cell`).

    **Sewn, not fused, and that is the fix for the seam OQ-DES-CW20 kept finding.** A plain
    `fuse` of two solids that meet only at one shared face routinely returned `ValueError: Null
    shape` here even though the shared face is exact by construction (measured 2026-09-20: one
    planar face at 0.000000000 mm from the origin, area 2009.22 mm2, both operands individually
    valid) -- the boolean kernel's general-purpose intersection machinery is simply not the
    robust path for a case this degenerate, two solids abutting over their *entire* shared
    boundary with zero overlap. Removing that face from each side first and sewing the two open
    shells along their now-open edge is the operation this case actually is: not an
    intersection to compute, but two boundaries that are already identical to be zipped
    together.

    **Every** matching face is removed, not exactly one. The tail's half ever has one cap per
    plane, but the nose's octant, three mirrors in, can carry two: mirroring doubles a plane's
    own cap along with everything else, so by the third step (`x = 0`) there is the octant's
    original cap and a second one produced by mirroring it across `y = 0` in the second step,
    both in the same plane and both due to cancel.
    """
    keep = []
    removed = 0
    for f in solid.Faces:
        if not isinstance(f.Surface, Part.Plane):
            keep.append(f)
            continue
        axis = f.Surface.Axis
        axis.normalize()
        if abs(abs(axis.dot(normal)) - 1.0) < tol and abs(f.Surface.Position.dot(normal)) < tol:
            removed += 1
        else:
            keep.append(f)
    if removed < 1:
        raise PreconditionFailed(
            'expected at least one flat cap face in the mirror plane %s, found none -- the '
            'cell cavity was not closed the way section 4.5 requires' % normal)
    return keep


def mirror_across_cell(cell_result, normal):
    """`cell_result` carried one mirror step further: its cell-boundary cap removed, the open
    shell mirrored, and the two sewn together along their now-identical shared edge.

    **This is the one mirror section 4.5 allows, and it runs on the finished cell wall, not on
    the cavity.** An earlier version of this function ran on the cavity instead -- mirroring the
    interior void out to the whole part and only then cutting it out of the separately-mirrored
    outer solid (`notched.cut(...)` in `shell_solid`) -- which is exactly the "boolean between
    two already-full shapes that were each independently mirrored into existence" section 4.5
    forbids, just one level removed from the two attempts it already names: `notched` there is
    `tip`, mirrored by `cowl_tree`'s own `_mirror_union`, and cutting it against a second,
    independently-mirrored full solid is no safer than fusing two of them would have been.
    Measured on the tail at `U` = 1.0, 2026-09-20/21: that version's partition slip was
    2.622e-04, over `PARTITION_TOL`, coinciding with a rib-cut retry -- initially read as
    `Shape.Volume` measurement noise (IP-FC-119's own error on this geometry is ten times
    larger), which is the wrong lesson to have drawn from a build that was never running the
    order the resolution describes. `shell_solid` now cuts the cavity out of the cell's own
    buttress-cut body *before* calling this function at all, so the only thing ever mirrored
    into a full-part shape is the one, already-finished wall -- this function is generic in
    what it mirrors and does not care which.

    See `_strip_seam` for why this sews rather than fuses the capped solid against its mirror.

    **`cell_result` is expected to be one solid, and mirroring it into more than one is refused,
    not accommodated.** An earlier version of this function treated a multi-shell sew result as
    legitimate -- built one `Part.Solid` per closed shell and returned a `Part.Compound` when
    there was more than one, on the reasoning that the tail's own rib slots can split a cell's
    cavity into several disconnected pieces. **That reasoning was wrong, corrected 2026-09-21:
    there is no scale or condition under which a disconnected wall is legitimate geometry** -- a
    rib is what bridges a buttress slot (`cavity`'s own rib-residue check), so a cavity or wall
    that comes apart into pieces means a rib failed to bridge somewhere, not that the part
    legitimately has a second piece. `cavity()` now refuses a multi-solid cavity outright, so by
    the time this function runs, `cell_result` should already be single. If mirroring it still
    produces more than one shell here, that is new evidence of a defect at the seam itself, not a
    second-order case to solidify and pass along -- refusing is what makes it visible instead of
    printing a part that is missing a piece.
    """
    n = App.Vector(normal)
    n.normalize()
    faces = _strip_seam(cell_result, n)
    mirrored = [f.mirror(App.Vector(0, 0, 0), n) for f in faces]
    sewn = Part.makeCompound(faces + mirrored)
    sewn.sewShape()
    shells = [s for s in sewn.Shells if s.isClosed()]
    if not shells:
        raise Unconverged(
            'mirroring the cell result about %s produced no closed shell at all, from %d '
            'faces -- the two open halves did not sew together anywhere.' % (normal, len(faces)))
    if len(shells) != 1:
        raise Unconverged(
            'mirroring the cell result about %s produced %d disconnected shells, not one. A '
            'mirrored part is never legitimately more than one piece -- this is new evidence of '
            'a defect at the seam itself, not a shape to solidify piece by piece and pass '
            'along.' % (normal, len(shells)))
    solid = Part.Solid(shells[0])
    if not solid.isValid():
        raise Unconverged(
            'mirroring the cell result about %s produced a closed shell that did not solidify '
            'validly. The two open shells should meet exactly along their shared edge -- the '
            'same curve, mirrored onto itself -- so a failure here means that edge is not as '
            'exact as section 4.5 assumes.' % normal)
    return solid


def shell_solid(notched, body, notches, t, overhang_deg, mirrors, tau=TAU, report=None,
                 clearance_check=False):
    """The wall: `notched` with its cavity removed, mirrored out to the whole part.

    Bounded by the exterior, the interior, and an annulus at each open end -- which is what
    cutting the closed cavity out of the closed blank leaves, without the annuli having to be
    constructed.

    **`notched` is the cell's own buttress-cut body -- `cut`/`OctantCut` in `cowl_tree`, the
    same object the outer print solid mirrors into `tip` -- never the full part.** The cavity
    is cut out of it *before* any mirroring happens, entirely within the symmetry cell, and only
    the one resulting wall is ever carried out to the whole part. **Correction, 2026-09-21: an
    earlier version of this function did the opposite, and it was wrong in exactly the way
    section 4.5 warns against.** It mirrored the *cavity* out to the whole part first
    (`mirror_cavity`, now `mirror_across_cell`), then cut that full mirrored cavity out of
    `tip` -- the outer solid, itself already mirrored by `cowl_tree`'s own, separate
    `_mirror_union` step. That final cut was a boolean between two shapes that had each been
    independently carried out to the whole part by their own mirror step, which is precisely the
    "boolean between two already-full shapes that were each independently mirrored into
    existence" the resolution names and rejects -- it was simply one level removed from the two
    attempts already documented there, not a third way around the same problem. Measured on the
    tail at `U` = 1.0 under that wrong order: partition slip 2.622e-04, over `PARTITION_TOL`,
    coinciding with a rib-cut retry -- at the time read as plausible `Shape.Volume` measurement
    noise (IP-FC-119 measured an error on this geometry ten times larger), which was the wrong
    conclusion to draw from a build that was never running the order this resolution describes.
    The fix moves the cut earlier, not just the mirror later: `body.cut`/`body.common` never
    happen here at all, `notches` is subtracted from `body` inside `cavity` alone, and the one
    cut this function performs -- `notched.cut(inside)`, cell-sized -- happens before `mirrors`
    is ever consulted.

    **The cut is verified against the partition identity before it is mirrored.** This boolean
    is between two NURBS solids `t` apart, which is the hardest thing asked of the kernel here,
    and it is not reliable: the same code has produced a correct 23745.581 mm3 tail wall from
    one converged surface and a 21995 mm3 one in five pieces from another, both surfaces
    measured inside `TAU` at every station and between them. Checking it at cell size, before
    mirroring, is strictly better than checking the old full-part cut ever was: a defect here is
    caught while `wall`/`kept` are still half or an octant, cheaper to compute and with nothing
    from the mirror step yet able to hide or compound it.

    **`mirrors` is the same ordered list of normals that assembled `notched` from its own cell**
    (one for the tail's half, three for the nose's octant -- `cowl_tree.pieces`), applied here to
    the *finished wall* in that identical order, the same way `_mirror_union` already carries
    `cut` out to `tip`. Each of the wall's flat cell-boundary faces is exact, so its mirror image
    is that same face, not a near-duplicate of it -- but even so, a plain `fuse` of the capped
    wall against its own mirror was measured to fail (`ValueError: Null shape`) on exactly this
    exact-face case when tried against the cavity, and there is no reason to expect the wall's
    own copy of that same face to fare differently: `mirror_across_cell` sews the two open
    shells instead, which is what `_strip_seam` records the reasoning for.

    **The cut against `notched` is not a plain `.cut(inside)` either, for the identical reason.**
    `inside` carries the same exact cell-boundary cap `notched` does, so cutting one straight out
    of the other is the same degenerate shared-face case as the mirror step above, just as a
    `cut` instead of a `fuse` -- measured 2026-09-21 to fail the same way (`ValueError: Null
    shape`). `_extend_across_cell` continues `inside` a short distance past that cap first, which
    cannot change the result (`notched` has no material past its own cell boundary to begin with)
    but does stop the two operands from sharing an exact face at all.
    """
    inside = cavity(body, notched, notches, t, overhang_deg, tau=tau, report=report,
                     clearance_check=clearance_check)
    for plane in cell_boundary_planes(body):
        inside = _extend_across_cell(inside, plane)
    wall = notched.cut(inside)
    if len(wall.Solids) != 1:
        raise Unconverged(
            'the cell wall came out as %d disconnected solids, not one, even though its cavity '
            'did not. There is no scale or condition under which a disconnected wall is '
            'legitimate: refused here rather than mirrored piece by piece into a part that is '
            'missing a piece.' % len(wall.Solids))
    kept = notched.common(inside)
    total = wall.Volume + kept.Volume
    slip = abs(total - notched.Volume) / notched.Volume
    if report is not None:
        report.update(cell_wall_volume=wall.Volume, partition_slip=slip)
    note('cell wall: %.4f mm3 in %d solid(s); the cut and the common account for %.6f%% of the '
         'cell\'s own buttress-cut body' % (wall.Volume, len(wall.Solids), 100.0 * (1.0 - slip)))
    if slip > PARTITION_TOL:
        raise Unconverged(
            'the cell wall and the material it was cut from do not add up to the cell\'s own '
            'buttress-cut body: %.4f + %.4f = %.4f against %.4f, off by %.4f mm3 (%.4f%%). '
            'Cutting a solid in two partitions it, so this boolean lost material, and the wall '
            'it returned is not the cell. Section 6 would not catch it -- a wall that is mostly '
            'missing still measures %.3f mm thick wherever it survives.'
            % (wall.Volume, kept.Volume, total, notched.Volume,
               abs(total - notched.Volume), 100.0 * slip, t))

    for normal in mirrors:
        wall = mirror_across_cell(wall, normal)
    if report is not None:
        report.update(wall_volume=wall.Volume, wall_solids=len(wall.Solids))
    note('wall: %.4f mm3 in %d solid(s) after %d mirror step(s)'
         % (wall.Volume, len(wall.Solids), len(mirrors)))
    return wall
