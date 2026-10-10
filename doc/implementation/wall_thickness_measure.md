# A Wall-Thickness Measure That Converges — Implementation Plan

**Scope:** Settle, by measurement, whether the finished cowl wall meets `WALL_TOL` = 0.01 mm — and
build the instrument that can say so. Today nothing can: the acceptance gate's nearest-point
minimum does not converge, the local-normal variant oscillates, the one measure that does converge
is a mean and cannot see a local thin spot, and the morphological candidate is refuted on
performance. So every thinness figure this project has recorded, including the whole 28-build soak
corpus, is a reading from an instrument that cannot settle, and the compliance question is open for
want of evidence rather than for want of a decision. This plan supersedes
[IP-FC-151](freecad_migration.md#work-items), which named the problem and left "what to try
instead" open.

**This plan contains no open questions, by design.** The requirements on the instrument follow from
`WALL_TOL` and from how a single-perimeter spiral-vase wall fails — they are not matters of taste —
and they are written as the five pass/fail gates in the Notes below, fixed before any candidate is
run. A candidate either passes all five or it does not. Where more than one passes, the tie-break
is also pre-committed (cost). Nothing here is waiting on a design choice.

**The expensive part is already paid.** The 2026-10-06 soak saved all 28 finished walls as BREP —
412 MB in `src/Fuselage/freecad/out/soak/shapes/`, both kinds at `U` ∈ {0.5, 1, 1.5, 2, 3, 4}, with
five repeats at two of them. A new instrument is validated and run against real geometry by loading
those files, not by rebuilding: the tail at `U` = 4 cost 4 870 s a build and costs a file read now.
No item in this plan requires a cowl build.

**Design authority:** [cowl_interior_surface.md §5 "The three convergences, and where the chain
breaks"](../design/cowl_interior_surface.md#the-three-convergences-and-where-the-chain-breaks),
[§6.1 Measurement cautions](../design/cowl_interior_surface.md),
[cowl.md OQ-DES-CW23 and OQ-DES-CW26](../design/cowl.md#open-questions),
[`cowl_interior.WALL_TOL`](../../src/Fuselage/freecad/cowl_interior.py)

**Last updated:** 2026-10-10

---

## Work Items

| ID | Status | Title | Depends on | Design refs |
| --- | --- | --- | --- | --- |
| IP-WTM-1 | todo | Build the synthetic ground-truth fixtures: a uniform tube, a tube with a milled patch of known depth and known extent, and a tube with a known concave crease, each with its true local thickness in closed form | — | [§5 chain](../design/cowl_interior_surface.md#the-three-convergences-and-where-the-chain-breaks) |
| IP-WTM-2 | todo | Add a section-extraction helper that returns a station's wires as plain coordinate arrays through the bridge, so a candidate measure runs client-side in `numpy` with no vendor call per sample | IP-WTM-1 | [geometry_bridge.md §4.8](../architecture/geometry_bridge.md) |
| IP-WTM-3 | todo | Write the five-gate screening harness — locality, convergence, ground-truth accuracy, discrimination, cost — that scores any candidate measure and prints a pass/fail table | IP-WTM-1, IP-WTM-2 | [§6.1](../design/cowl_interior_surface.md), this plan's Notes |
| IP-WTM-4 | todo | Score the incumbent `wall_thickness` nearest-point minimum against all five gates, to fix the baseline the candidates are compared against | IP-WTM-3 | [§5 chain](../design/cowl_interior_surface.md#the-three-convergences-and-where-the-chain-breaks) |
| IP-WTM-5 | todo | Candidate C1 — inscribed-circle local thickness (largest circle fitting inside the ribbon at each boundary point), computed from the polyline without rasterizing | IP-WTM-3 | [§6.1](../design/cowl_interior_surface.md) |
| IP-WTM-6 | todo | Candidate C2 — windowed-normal ray cast: estimate the boundary normal by least squares over an arc-length window rather than from adjacent samples, then cast to the far boundary | IP-WTM-3 | [§6.1](../design/cowl_interior_surface.md) |
| IP-WTM-7 | todo | Candidate C3 — polygon morphological erosion: discretize the section to a polygon first, then erode by `(t - WALL_TOL)/2` and test connectivity, the route IP-FC-151 left open | IP-WTM-3 | [§6.1](../design/cowl_interior_surface.md), [IP-FC-151](freecad_migration.md#work-items) |
| IP-WTM-8 | todo | Candidate C4 — corner-excluded nearest-point minimum: detect concave-corner-adjacent samples and drop them, testing whether the incumbent is salvageable rather than replaceable | IP-WTM-3 | [§6.1](../design/cowl_interior_surface.md) |
| IP-WTM-9 | todo | Publish the screening result: one table of four candidates against five gates, in `cowl_interior_surface.md` §6, naming which measure the evidence selects and which gate each loser failed | IP-WTM-4, IP-WTM-5, IP-WTM-6, IP-WTM-7, IP-WTM-8 | [§6](../design/cowl_interior_surface.md) |
| IP-WTM-10 | todo | Adopt the selected measure in `check_cowl_interior.wall_thickness` beside the incumbent, reporting both, and keep the incumbent's figure in the printed output for one corpus so the two can be compared | IP-WTM-9 | [§6](../design/cowl_interior_surface.md) |
| IP-WTM-11 | todo | Re-measure all 28 saved soak walls with the selected measure and answer the compliance question corpus-wide: at which kind and `U` does the wall actually meet `WALL_TOL` | IP-WTM-10 | [§9.9](../design/cowl_interior_surface.md), [`soak_cowl_shell.py`](../../src/Fuselage/freecad/soak_cowl_shell.py) |
| IP-WTM-12 | todo | Correct every recorded thinness figure that the re-measurement supersedes — `WALL_TOL`'s own note, §9.9's corpus table, and OQ-DES-CW23's 0.0534 mm — or confirm each one stands | IP-WTM-11 | [§9.9](../design/cowl_interior_surface.md), [cowl.md OQ-DES-CW23](../design/cowl.md#open-questions) |
| IP-WTM-13 | todo | Re-measure OQ-DES-CW23's 12-station prediction-versus-real gap with the selected measure, since the recorded 0.0121 mm mean is a comparison against a non-converging instrument | IP-WTM-11 | [cowl.md OQ-DES-CW23](../design/cowl.md#open-questions) |
| IP-WTM-14 | todo | Report to OQ-DES-CW23 and OQ-DES-CW26 what the new evidence does to each one's premises, so both can be decided on measurements rather than on an instrument known to drift | IP-WTM-12, IP-WTM-13 | [cowl.md OQ-DES-CW23, OQ-DES-CW26](../design/cowl.md#open-questions) |

---

## Notes

### The five gates, fixed before any candidate runs

A candidate is the instrument if it passes all five. These are derived from the requirement and
from the failure mode, not chosen, which is why this plan needs no open question.

| gate | threshold | why this threshold |
| --- | --- | --- |
| **G1 Local** | responds to a thin patch whose extent along the station is one extrusion width — 0.6 mm — with at least 80% of that patch's true depth | The cowl wall is `cowl_n_perimeters * extrusion_width` = 1 × 0.6 mm, so it is **one** perimeter 0.6 mm wide, and the slicer drops it or not at a point. A patch shorter than one extrusion width is below what the path planner resolves; a patch that long must be seen. This is the gate the converged area mean fails. |
| **G2 Convergent** | the reported value moves by ≤ 0.001 mm between the two finest refinement levels, and the trend is flat rather than drifting | A tenth of `WALL_TOL`, so the instrument's own residual cannot be confused with the quantity. The incumbent was still drifting 0.0015–0.0079 mm per doubling at 3 840 samples, 17 of 24 stations. |
| **G3 Accurate on ground truth** | within 0.001 mm of the closed-form thickness on IP-WTM-1's uniform tube | Convergence alone only shows a measure settles; it can settle on the wrong number. **No candidate, including the incumbent, has ever been checked against a known answer.** |
| **G4 Discriminating** | reports the milled patch's depth to within 0.002 mm and localizes it to within 2 mm along the station | The converse test. The area mean reads identically on a healthy and a damaged wall, which is how it passes G2 and is still useless. |
| **G5 Affordable** | ≤ 60 s for all 12 stations of a real `tail_shell` wall at `U` = 4, the largest in the corpus | The gate must run in the build and in the suite. `Face.makeOffset2D` on a real section did not finish in six minutes for one call, which is what closed that route. |

**Tie-break, also pre-committed:** if more than one candidate passes all five, take the cheapest by
G5; if two are within 2× on cost, take the one with the smaller G2 residual. No judgment call is
reserved.

**If no candidate passes**, that is itself the answer to report, and the next step follows from
*which* gate every candidate failed — it does not become a matter of preference. A universal G5
failure means the measure must move off the exact B-spline section; a universal G1 failure means
local thickness is not recoverable from a planar section at all and the measure has to be 3-D.

### Why ground truth comes first

IP-WTM-1 is first because **every measure in this subsystem has been judged by whether it agrees
with itself under refinement, and none by whether it agrees with a known answer.** That is how a
measure that converges on the wrong number — the area mean on a non-uniform section, reading
0.4753 mm where the wall is 0.6 mm — survived as a candidate. A tube with a milled patch has a
closed-form local thickness everywhere, so G3 and G4 are checkable arithmetic.

The fixtures are cheap: `tests/test_geometry_bridge_cowl_checks.py` already builds a 0.6 mm-walled
tube and a two-arc broken ring in about 0.1 s each, and IP-WTM-1 is those plus a patch of known
depth.

### Why the bridge matters here

IP-WTM-2 exists because the candidates are numerical work over coordinate arrays, and a
round trip per sample would make the screening itself the bottleneck — the incumbent's own
convergence study needed 3 840 samples a station. The section wires are extracted once in the
worker and cross as plain values; every candidate then runs client-side in `numpy`, in the fast
test tier, at no vendor cost per sample. `project` already reads N points in one trip.

`scipy` and `shapely` are **absent** from the venv, and no item here needs them: the inscribed-circle
and windowed-normal candidates are plain `numpy`, and C3's polygon erosion can use the kernel on a
discretized polygon, which is the cheap case. If a candidate would be materially better with
`shapely`, adding it is a packaging matter and not a reason to hold the screening.

### What this plan does not do

It does not change the construction. Whether the wall is thin and whether it is *measured* as thin
are separate questions, and only the second is in scope. If IP-WTM-11 finds the wall compliant all
along, the construction work queued behind OQ-DES-CW23 and OQ-DES-CW26 shrinks rather than grows —
which is exactly why it is worth measuring before building anything else.

### Cross-plan

**Supersedes IP-FC-151** in `freecad_migration.md`, which should be marked superseded and point
here. IP-FC-152 is blocked on OQ-DES-CW26, and OQ-DES-CW26's own choice between "adopt the annulus
identity", "build the thickness measure" and "rely on the external check" is partly waiting on this
plan's IP-WTM-14.

**Uses `geometry_bridge.md`'s library** but does not depend on unfinished items in it: IP-GB-16's
facades and IP-GB-21's tube fixtures are both done.
