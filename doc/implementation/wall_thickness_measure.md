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

**Answered, 2026-10-10 — and the answer had to be corrected twice the same day, both times because
of this plan's own instrument.** The measure is `candidates.corner_excluded_min`, which passes all
five gates and the disqualifying converse; that selection stands. What took two corrections is the
*absolute* reading.

The first corpus run discretized each section at a fixed 1 440 samples. A cowl's perimeter scales
with `U` while its wall stays an absolute 0.6 mm, so that count bought 0.30 mm of circumferential
spacing at `U` = 1 and 1.45 mm at `U` = 4, and the readings above `U` = 2 were dominated by it. Two
findings were published off that run and **both are withdrawn**: a corpus worst of 0.2136 mm at
`tail_shell` `U` = 4, and a "regime change" in which pass 2's prediction went optimistic by
0.11–0.17 mm above `U` = 2.

Re-measured at a fixed 0.125 mm spacing, refined until the reading settled:

| | published at 1 440 samples | refined at 0.125 mm |
| --- | --- | --- |
| `tail_shell` `U` = 1.0 | 0.0282 | 0.0286 |
| `tail_shell` `U` = 3.0 | 0.1514 | 0.0481 |
| `tail_shell` `U` = 4.0 | 0.2136 | **0.0347** |

**What stands.** The tolerance is unmet on every fully measured wall, by three to five times, and
**consistently at every `U` rather than worsening with it**. Pass 2's prediction tracks the real wall
to within 0.0039 mm. Every station measured is a healthy annulus. **OQ-DES-CW23 is still withdrawn,
but for the opposite reason from the one first recorded**: its "small residual gap" is real and
small, and knowing its size is what finally let its alternatives be scored.

**The finding that replaces them** is that the wall is about as thin as `TAU` = 0.05 mm permits,
which is a binding criterion rather than a construction defect — and that
`check_cowl_interior.wall_thickness` has the same fixed-count defect this plan's own sweep had
(`AROUND` = 240, 8.7 mm apart at `U` = 4), so the production gate's readings above `U` = 2 are not
sound either. That is IP-WTM-22.

**The expensive part is already paid.** The 2026-10-06 soak saved all 28 finished walls as BREP —
412 MB in `src/Fuselage/freecad/out/soak/shapes/`, both kinds at `U` ∈ {0.5, 1, 1.5, 2, 3, 4}, with
five repeats at two of them. A new instrument is validated and run against real geometry by loading
those files, not by rebuilding: the tail at `U` = 4 cost 4 870 s a build and costs a file read now.
No item in this plan requires a cowl build.

**Design authority:** [cowl_interior_surface.md §5 "The three convergences, and where the chain
breaks"](../design/cowl_interior_surface.md#the-three-convergences-and-where-the-chain-breaks),
[§6.1 Measurement cautions](../design/cowl_interior_surface.md),
[§6.4 Which measure reads the wall](../design/cowl_interior_surface.md#64-which-measure-reads-the-wall-and-what-it-says-the-wall-is)
and [§6.5 Pass 2's prediction against the real wall](../design/cowl_interior_surface.md#65-pass-2s-prediction-against-the-real-wall-sound-below-u--2-broken-above),
which this plan produced and which are now the authority for both,
[cowl.md OQ-DES-CW26](../design/cowl.md#open-questions),
[`cowl_interior.WALL_TOL`](../../src/Fuselage/freecad/cowl_interior.py)

**Last updated:** 2026-10-11

---

## Work Items

| ID | Status | Title | Depends on | Design refs |
| --- | --- | --- | --- | --- |
| IP-WTM-1 | done | Build the synthetic ground-truth fixtures: a uniform tube, a tube with a milled patch of known depth and known extent, and a tube with a known concave crease, each with its true local thickness in closed form | — | [§5 chain](../design/cowl_interior_surface.md#the-three-convergences-and-where-the-chain-breaks) |
| IP-WTM-2 | done | Add a section-extraction helper that returns a station's wires as plain coordinate arrays through the bridge, so a candidate measure runs client-side in `numpy` with no vendor call per sample | IP-WTM-1 | [geometry_bridge.md §4.8](../architecture/geometry_bridge.md) |
| IP-WTM-3 | done | Write the five-gate screening harness — locality, convergence, ground-truth accuracy, discrimination, cost — that scores any candidate measure and prints a pass/fail table | IP-WTM-1, IP-WTM-2 | [§6.1](../design/cowl_interior_surface.md), this plan's Notes |
| IP-WTM-4 | done | Score the incumbent `wall_thickness` nearest-point minimum against all five gates, to fix the baseline the candidates are compared against | IP-WTM-3 | [§5 chain](../design/cowl_interior_surface.md#the-three-convergences-and-where-the-chain-breaks) |
| IP-WTM-15 | done | Move the convergence gate onto a **real** saved section and keep the synthetic fixture only as the smooth-case contrast, because the fixtures cannot reproduce the non-convergence | IP-WTM-4 | [§6.1](../design/cowl_interior_surface.md), this plan's "What the first screening run established" |
| IP-WTM-5 | done | Candidate C1 — inscribed-circle local thickness (largest circle fitting inside the ribbon at each boundary point), computed from the polyline without rasterizing | IP-WTM-3, IP-WTM-15 | [§6.1](../design/cowl_interior_surface.md) |
| IP-WTM-6 | done | Candidate C2 — windowed-normal ray cast: estimate the boundary normal by least squares over an arc-length window rather than from adjacent samples, then cast to the far boundary | IP-WTM-3 | [§6.1](../design/cowl_interior_surface.md) |
| IP-WTM-7 | done | Candidate C3 — polygon morphological erosion: discretize the section to a polygon first, then erode by `(t - WALL_TOL)/2` and test connectivity, the route IP-FC-151 left open | IP-WTM-3 | [§6.1](../design/cowl_interior_surface.md), [IP-FC-151](freecad_migration.md#work-items) |
| IP-WTM-8 | done | Candidate C4 — corner-excluded nearest-point minimum: detect concave-corner-adjacent samples and drop them, testing whether the incumbent is salvageable rather than replaceable | IP-WTM-3 | [§6.1](../design/cowl_interior_surface.md) |
| IP-WTM-17 | done | Add the decisive converse fixture: a thin patch placed **at** a concave corner, and disqualify any measure that misses it — C4 excludes corner-adjacent samples and must be shown not to be blind where the wall is weakest | IP-WTM-8 | [§6.1](../design/cowl_interior_surface.md), this plan's "The screening run" |
| IP-WTM-16 | done | Fix `candidates.inscribed_circle`, which reports about zero thickness everywhere; the method is untested, not refuted | IP-WTM-5 | [§6.1](../design/cowl_interior_surface.md) |
| IP-WTM-18 | done | Save the cowl **body**'s z extent beside the wall in `soak_cowl_shell.py`, so a later sweep can reproduce the acceptance check's own station grid instead of a different one | — | [`soak_cowl_shell.py`](../../src/Fuselage/freecad/soak_cowl_shell.py), this plan's "The station grid was wrong" |
| IP-WTM-9 | done | Publish the screening result: one table of four candidates against five gates, in `cowl_interior_surface.md` §6, naming which measure the evidence selects and which gate each loser failed | IP-WTM-4, IP-WTM-5, IP-WTM-6, IP-WTM-7, IP-WTM-8, IP-WTM-16, IP-WTM-17 | [§6.4](../design/cowl_interior_surface.md#64-which-measure-reads-the-wall-and-what-it-says-the-wall-is) |
| IP-WTM-11 | done | Re-measure all 28 saved soak walls with the selected measure and answer the compliance question corpus-wide: at which kind and `U` does the wall actually meet `WALL_TOL` | IP-WTM-9 | [§6.4](../design/cowl_interior_surface.md#64-which-measure-reads-the-wall-and-what-it-says-the-wall-is), [`soak_cowl_shell.py`](../../src/Fuselage/freecad/soak_cowl_shell.py) |
| IP-WTM-12 | done | Correct every recorded thinness figure that the re-measurement supersedes — `WALL_TOL`'s own note, §9.9's corpus table, and OQ-DES-CW23's 0.0534 mm — or confirm each one stands | IP-WTM-11 | [§9.9](../design/cowl_interior_surface.md), [cowl.md OQ-DES-CW23](../design/cowl.md#open-questions) |
| IP-WTM-19 | done | Settle how a station with no closed section counts in a sweep verdict: adopt the acceptance gate's own convention, since a sweep exists to say whether the part would pass that gate | IP-WTM-11 | [check_cowl_interior.py](../../src/Fuselage/freecad/check_cowl_interior.py) |
| IP-WTM-13 | done | Re-measure OQ-DES-CW23's prediction-versus-real gap with the selected measure, since the recorded 0.0121 mm mean is a comparison against a non-converging instrument | IP-WTM-11 | [§6.5](../design/cowl_interior_surface.md#65-pass-2s-prediction-against-the-real-wall-sound-below-u--2-broken-above) |
| IP-WTM-14 | done | Report to OQ-DES-CW23 and OQ-DES-CW26 what the new evidence does to each one's premises — withdrawing CW23, whose premise the evidence refutes, and reporting to CW26 and IP-FC-152 | IP-WTM-12, IP-WTM-13 | [cowl.md OQ-DES-CW23, OQ-DES-CW26](../design/cowl.md#open-questions) |
| IP-WTM-20 | done | Settle whether the `U` ≥ 3 tail walls are thin or severed, by reading section-ring connectivity rather than thickness at those stations on the already-saved walls | IP-WTM-13 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales), [cowl.md OQ-DES-CW26](../design/cowl.md#open-questions) |
| IP-WTM-21 | done | Judge the nose on a grid placed from the wall’s **real** extent rather than its bounding box — no rebuild needed, since `Shape.BoundBox` on these solids is an outer bound only and sectioning recovers 12 of 12 stations | — | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-22 | done | Parameterize `sweep.measure_wall`/`sweep.sweep` by circumferential **spacing** rather than sample count, and record in every result row which was used | IP-WTM-13 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-23 | done | Bound `candidates._segment_distances` in memory by chunking, since a refinement study at 0.03 mm spacing on a `U` = 4 section asks for a 68 000 x 68 000 distance matrix | IP-WTM-22 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-24 | done | Re-measure the corpus at a fixed spacing and withdraw every absolute figure taken at a fixed count, in `cowl_interior_surface.md`, `cowl.md` OQ-DES-CW23 and `WALL_TOL`’s own note | IP-WTM-22 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales), [§6.4](../design/cowl_interior_surface.md#64-which-measure-reads-the-wall-and-what-it-says-the-wall-is) |
| IP-WTM-25 | todo | Replace `check_cowl_interior`’s fixed `AROUND` = 240 with an arc-length spacing, the way `cowl_interior.check_samples` already uses `CHECK_ARC` = 0.20 mm, since at `U` = 4 that count is 8.7 mm apart on a 0.6 mm wall | IP-WTM-24 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-10 | blocked (IP-WTM-25) | Adopt the selected measure in `check_cowl_interior.wall_thickness` beside the incumbent, reporting both, and keep the incumbent’s figure in the printed output for one corpus so the two can be compared | IP-WTM-9, IP-WTM-25 | [§6.4](../design/cowl_interior_surface.md#64-which-measure-reads-the-wall-and-what-it-says-the-wall-is) |
| IP-WTM-26 | todo | Find the mechanism behind the 0.028–0.048 mm thinning that survives correct sampling, given that smooth-arc chord sag is 400x too small and local curvature is uncorrelated (anti-correlated at `U` ≥ 3) | IP-WTM-24 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-27 | done | Test whether tightening `TAU` yields a compliant wall and at what cost, by building one part at several `TAU` through `freecad/tau_study.py` | IP-WTM-24 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-28 | todo | Confirm the `TAU` result on a `tail_shell`, the kind that fails at every `U`, since the nose was already within a hair of tolerance before tightening; `U` = 0.5 is the cheapest tail build at 727 s. **This is the measurement OQ-DES-CW28 is waiting on** — it is a prerequisite of that question, not blocked by it | IP-WTM-27 | [§6.8](../design/cowl_interior_surface.md#68-tightening-the-criterion-measured-not-argued), [cowl.md OQ-DES-CW28](../design/cowl.md#open-questions) |
| IP-WTM-29 | done | Test whether the tail’s diagonal buttresses are the mechanism, given the nose cell has none and is compliant at `U` ≤ 3 — measured through `freecad/rib_proximity.py`, and refuted: 10 of 12 thin spots sit more than 3`t` from any rib | IP-WTM-24 | [§6.7.1](../design/cowl_interior_surface.md#671-the-ribs-are-not-where-the-wall-is-thin) |
| IP-WTM-30 | todo | Test the refined hypothesis that the diagonals matter through the **fit** rather than the cut, by comparing each thin spot’s magnitude against the local fit row spacing and patch length | IP-WTM-29 | [§6.7.1](../design/cowl_interior_surface.md#671-the-ribs-are-not-where-the-wall-is-thin) |
| IP-WTM-31 | todo | Remove `cowl_interior.hausdorff`, dead since `_refine`’s criterion became the in-plane wall width — no callers in `src/` or `tests/` | — | [§5](../design/cowl_interior_surface.md#5-the-refinement-criterion) |
| IP-WTM-32 | done | Correct the stale claim that notch edges are patch boundaries, in `feature_stations`’ and `EDGE_SCAN_MARGIN`’s notes and in §4.1, §4.3 and §6.7.1 — under §4.2’s three-dimensional identity they are interpolation rows, and every build reports `patch 1/1` | — | [§4.1](../design/cowl_interior_surface.md#41-stations), [§4.2](../design/cowl_interior_surface.md#42-eroding-a-section) |
| IP-WTM-33 | done | Check that the rib cut’s own boundary edges lie on both surfaces they are the intersection of — `wall_measure/boolean_edges.py` plus the `freecad/rib_edge_check.py` driver, since `cavity` checks only the residue volume and the solid count after the cut | — | [§4.2](../design/cowl_interior_surface.md#42-eroding-a-section), [§6.9](../design/cowl_interior_surface.md#69-the-shape-of-the-rib-edges) |
| IP-WTM-37 | done | Check that the rib cut returns the surface it was *given*, not only an edge in the right place — `boolean_edges.surface_identity` on the control nets, `patch_deviation` over the patch interior banded by distance to a rib edge, and `face_normal`/`crease_angles` for the first-order test and the tangency reading | IP-WTM-33 | [§6.9](../design/cowl_interior_surface.md#69-the-shape-of-the-rib-edges) |
| IP-WTM-34 | todo | Run `rib_edge_check.py` across `U` on both kinds — chiefly to see whether the **minimum crease angle** collapses toward 0 near `U` = 0.75, where `Diag12Safe`'s sliver occurred, which would make it a predictor of that degeneracy rather than a description of it; also whether the over-fuzz sample count (0 on the nose, 37 on the tail at `U` = 0.5) and the worst departure are flat in `U` | IP-WTM-37 | [§6.9](../design/cowl_interior_surface.md#69-the-shape-of-the-rib-edges) |
| IP-WTM-35 | todo | Identify the tail’s one edge group not shared by exactly two faces — a periodic seam and a degenerate edge both look like this, and the nose has none | IP-WTM-33 | [§6.9](../design/cowl_interior_surface.md#69-the-shape-of-the-rib-edges) |
| IP-WTM-36 | todo | Chase the nose’s `U`-linear thinning, now that the two kinds are known to scale differently and the nose is forty times cheaper to build than the tail | IP-WTM-21 | [§6.7](../design/cowl_interior_surface.md#67-the-station-grid-a-bounding-box-is-not-the-part) |
| IP-WTM-40 | done | Close OQ-DES-CW26 alternative 1's axial-sampling bound with a dense ring scan on the saved walls — `locate.state_profile`/`nearby_states` plus `freecad/ring_scan.py`, no build. **All twelve distinct walls, both kinds across `U` = 0.5 to 4.0, at 1 mm axially: 1 704 stations, 1 703 healthy annuli, 0 severed, 0 confirmed gaps**, in 3 h 4 min. The one `no_wall` is the `U` = 3.0 slice artifact, reproduced to the last digit on a second scan hours later | IP-WTM-20 | [cowl.md OQ-DES-CW26](../design/cowl.md#open-questions), [§6.1](../design/cowl_interior_surface.md#61-measurement-cautions) |
| IP-WTM-39 | blocked (OQ-DES-CW28, IP-WTM-28) | Adopt the decided interior-fit convergence criterion in `cowl_interior.TAU`, and expose it as a `Tau` property plus a parameter-sheet column if that alternative is chosen — the sheet column being a separate item from the generator change that reads it | IP-WTM-28 | [§6.8](../design/cowl_interior_surface.md#68-tightening-the-criterion-measured-not-argued), [cowl.md OQ-DES-CW28](../design/cowl.md#open-questions) |
| IP-WTM-41 | todo | Extend the dense ring scan past the `U` axis, which is the bound IP-WTM-40 leaves: its 1 704 stations cover twelve walls that vary in `U` **alone**, every other design input at the parameter sheet's values. The 21-case free-parameter screen tested construction *validity* (`isValid()`) and did not save its walls, so this needs them built and saved before `ring_scan` can read them — **21 builds at 80–150 s on a nose and 727 s or more on a tail, plus the scan**, so it is machine time to be scheduled rather than spent unasked | IP-WTM-40 | [cowl.md OQ-DES-CW26](../design/cowl.md#open-questions), [§6.2](../design/cowl_interior_surface.md#62-conditioning-the-row-nudge-probe-and-what-it-can-establish) |
| IP-WTM-38 | todo | Extend the same surface-identity check to the steps *after* `cavity` — `_extend_across_cell`, `notched.cut(inside)`, `_strip_seam` and `mirror_across_cell` each carry their own boolean and `removeSplitter`, and none is covered by IP-WTM-37. The mirror step needs no build: a finished wall's interior B-spline copies should be exact images of one surface under the mirror transforms, so `surface_identity` across a saved wall's own faces tests it on all 12 corpus walls for free | IP-WTM-37 | [§6.9](../design/cowl_interior_surface.md#69-the-shape-of-the-rib-edges) |

> **IP-WTM-39 blocked reason:** what `TAU` should be is a trade between build time and compliance, not a measurement, and OQ-DES-CW28 is where it is filed. The measurement that makes the question decidable is IP-WTM-28 — a `tail_shell` is the kind that fails at every `U` and the only kind whose convergence cost at a tighter criterion is unknown. Until that reports, three of the question's alternatives are live for reasons that have nothing to do with taste: a criterion looser than `WALL_TOL` cannot guarantee it, a criterion equal to it may exhaust `POST_CUT_ROUNDS` on a tail, and removing the residual's mechanism instead (IP-WTM-26, IP-WTM-36) would make the whole question moot.

> **IP-WTM-10 blocked reason:** adopting a second measure in the acceptance gate is not worth doing while the gate still discretizes each section at a fixed `AROUND` = 240 samples, which is 8.7 mm apart on a `tail_shell` at `U` = 4 against a 0.6 mm wall. Both measures would inherit that error, and the figures printed beside each other would differ by less than either differs from the truth. IP-WTM-25 replaces the count with an arc-length spacing first.

---

## Notes

### The five gates, fixed before any candidate runs

A candidate is the instrument if it passes all five. These are derived from the requirement and
from the failure mode, not chosen, which is why this plan needs no open question.

| gate | threshold | why this threshold |
| --- | --- | --- |
| **G1 Local** | responds to a thin patch whose extent along the station is one extrusion width — 0.6 mm — with at least 80% of that patch's true depth | The cowl wall is `cowl_n_perimeters * extrusion_width` = 1 × 0.6 mm, so it is **one** perimeter 0.6 mm wide, and the slicer drops it or not at a point. A patch shorter than one extrusion width is below what the path planner resolves; a patch that long must be seen. This is the gate the converged area mean fails. |
| **G2 Convergent** | the reported value moves by ≤ 0.001 mm between the two finest refinement levels **and each step contracts to ≤ 0.6 of the one before**, measured on a real saved section (IP-WTM-15) | A tenth of `WALL_TOL`, so the instrument's own residual cannot be confused with the quantity. The incumbent was still drifting 0.0015–0.0079 mm per doubling at 3 840 samples, 17 of 24 stations. |
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

### What the first screening run established, 2026-10-10

IP-WTM-3 and IP-WTM-4 are done, and the baseline run produced two results that change this plan.

**The incumbent passes all four synthetic gates, cleanly.** On the fixtures it reads locality
1.000041 of the patch depth, accuracy 0.000006 mm, discrimination 0.000006 mm of depth error
located 0.021 mm from the patch centre, and convergence 0.000018 mm contracting about 4x a
doubling. The measure the project is replacing is, on analytic geometry, excellent.

**On a real saved wall the same measure does not converge at all.** `nose_cowl_shell` at `U` = 1,
one interior station, the minimum against sample count:

| samples | 360 | 720 | 1440 | 2880 | 5760 |
| --- | --- | --- | --- | --- | --- |
| reported minimum, mm | 0.473496 | 0.592148 | 0.587314 | 0.567506 | 0.563182 |
| step, mm | — | +0.118652 | −0.004834 | −0.019808 | −0.004324 |

Non-monotone, not contracting, and **still moving 0.0043 mm at 5 760 samples — 4.3x `WALL_TOL`**.
That reproduces the behaviour recorded in §6.1 (0.0015 to 0.0079 mm per doubling) from a different
direction, on a wall built four days earlier, and it settles that the non-convergence is real and
not an artefact of how it was first measured.

**So gate G2 cannot be screened synthetically, and that is a defect in this plan's own first
design.** Concentric circular boundaries make a nearest-point distance exactly radial and exactly
equal to the wall, so no diagonal shortcut across a corner exists to be found; the real sections
are convoluted B-splines with a concave corner at every slot mouth. Screening convergence on a
fixture would have passed the very measure this plan exists to replace. IP-WTM-15 moves G2 onto a
real section and keeps the fixture result as the smooth-case contrast — a candidate that converges
on the smooth case and not the real one has at least localized its own weakness. The fixtures
remain the authority for G1, G3 and G4, which need closed-form truth that a real wall cannot give.

**A lead for IP-WTM-11, not a conclusion.** Across that whole refinement sweep the *median*
thickness sat at 0.600076 to 0.600103 mm and moved by 2.7e-5 mm in total, against a 0.6 mm
nominal. The quantity that is unstable is the minimum, not the wall. That is consistent with the
converged area-based mean reading 0.0033 mm from nominal where the incumbent reads 0.0534 mm, and
it is the first independent hint that these walls may be compliant and the thin readings may be
instrument artefacts. It is not evidence of compliance — a median cannot see a local thin spot, as
gate G1 exists to say — but it is a reason to expect IP-WTM-11 to matter.

**Cost is not going to be the obstacle.** Loading a saved wall takes 0.2 s, and one station costs
1.6 s at 360 samples to 6.0 s at 5 760. Twelve stations at the working density is well inside gate
G5's 60 s, so the corpus-wide re-measurement in IP-WTM-11 is affordable on every one of the 28
walls.

### The screening run, 2026-10-10 — one candidate passes, and it is not yet selected

Gates scored with G2 on a real saved section (`nose_cowl_shell` at `U` = 1, `z` = −44.8421) and
G1/G3/G4 on the fixtures:

| candidate | G1 locality | G2 convergence | G3 accuracy | G4 discrimination | G5 cost | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| C0 nearest-point minimum | pass 1.000 | **FAIL 0.019808** | pass 0.000006 | pass 0.000006 | pass 16.9 s | rejected: G2 |
| C1 inscribed circle | pass 4.000 | pass 0.000000 | **FAIL 1.000000** | **FAIL 0.450000** | pass 25.3 s | **implementation defect, not a verdict on the method** |
| C2 windowed normal | pass 1.000 | **FAIL 0.006784** | **FAIL 0.028952** | pass 0.000006 | pass 13.6 s | rejected: G2, G3 |
| C4 corner-excluded minimum | pass 1.000 | pass 0.000425 | pass 0.000006 | pass 0.000006 | pass 13.6 s | passes all five |
| C3 erosion guard | — | n/a | — | n/a | 9.5 s a station | correct, but 12 stations is ≈114 s against a 60 s budget |

**C0's rejection confirms this plan's premise.** The incumbent's minimum runs 0.473496, 0.592148,
0.587314, 0.567506 across the sweep — non-monotone, not contracting — while its median moves
0.000027 mm. It passes every synthetic gate and fails the real one, which is why IP-WTM-15 moved
the gate.

**C1 did not fail the method, it failed my implementation of it.** It reports ≈0 thickness almost
everywhere: median error 0.600000 against a 0.6 mm wall, and a "convergence" to 0.000000 that is
the constant zero converging to itself. The inscribed-circle definition is the textbook one and the
one a slicer's behaviour follows, so it remains a live candidate; the walk-along-the-normal search
in `candidates.inscribed_circle` is what is wrong. Re-opened as IP-WTM-16 rather than recorded as a
negative result, because reporting "the inscribed circle does not work" off this run would be
false.

**C1, re-run after the fix (IP-WTM-16), is still not a test of the method.** The zero-reporting bug was real and is fixed: the normal was being aimed at the *outer* loop's centroid, which on an annulus is the axis, so it pointed inward, the ray missed the far boundary and the walk never left the inner boundary where the distance to itself is zero. Re-scored, C1 reads a real thickness and fails G2 at 0.021283 mm and G3 at 0.312292 mm. **Neither figure is a verdict on the inscribed circle.** Its G2 residual is within 14% of its own walk discretization (`gap`/32 = 0.018750 mm), which is fixed at 33 steps and so cannot refine when the boundary sampling does -- the measure is incapable of converging below its own step size. And the formulation is the wrong one for the definition: along a normal on locally flat wall, `max min(t, gap - t)` peaks at `gap`/2, so the diameter it returns is just the ray distance and the measure degenerates to C2 with a discretization penalty. A genuine inscribed-circle measure is a distance transform or a medial axis, which is different machinery and is not implemented. Recorded as untested rather than refuted, and **not** pursued further, because C4 already passes every gate -- if C4 is ever disqualified, this is the route to build next.

**C2 improved on the incumbent and is still not converged.** Its deltas contract
(0.058572 → 0.025239 → 0.006784) where the incumbent's do not, so widening the tangent window does
address the instability it was aimed at — the oscillation cause is real and the fix is
directional. But 0.006784 mm is still two-thirds of `WALL_TOL`, and it fails accuracy at
0.028952 mm beside the rib, so this buys partial progress and not an instrument.

**C4 passes all five gates and converges to exactly 0.600000 on a real wall — which is why it
cannot be selected yet.** Dropping samples within 0.3 mm of a concave corner makes the real section
read exactly nominal. That is either the answer (the corners were the whole artefact and the wall
was compliant all along, consistent with the stable median and with the converged area mean's
0.0033 mm) or it is the failure this plan predicted in writing: *excluding the corners removes the
very places a wall is thinnest.* **Nothing measured so far distinguishes those two**, because every
fixture puts its thin patch on smooth wall. A measure blind exactly where the part is weakest would
pass this screening and ship a hole.

IP-WTM-17 was the decisive converse: a thin patch placed **at** a concave corner, held to the same
80% of the defect's depth that gate G1 asks on smooth wall, so a corner gets no easier standard.

**Result, 2026-10-10: C4 is not blind.** On `corner_patch_tube` — a 0.15 mm deep patch one
extrusion width wide, centred on the re-entrant corner a rib leaves in the bore — C4 reports
**100% of the defect's depth** from 2 819 surviving samples of 2 880; the exclusion discards 61.
Every candidate sees it, the incumbent included, and the incumbent is the control here: it excludes
nothing, so without it a universal pass would be unreadable.

C4 therefore passes all five gates and the disqualifying converse, and the pre-committed tie-break
selects it. **Two residuals are worth stating rather than leaving implied.** First, *how* C4 sees a
defect centred on its own blind spot has not been traced — a surviving sample just outside the
exclusion zone can reach the recessed surface diagonally, which is the same cutting-across
mechanism that makes the incumbent non-convergent, here landing on approximately the right answer
because the thinning is real. That it works is measured; why it works is not. Second, a defect
**narrower** than one extrusion width, lying wholly inside the exclusion zone with no diagonal
access, is untested — and is out of scope by G1's own definition, which sets one extrusion width as
the shortest thin spot a single-perimeter wall can fail at. Both belong in IP-WTM-9's write-up as
limits of the selection, not as reasons to withhold it.

**C3 reopens the morphological route and does not fit the cost budget.** It answers correctly —
survives on a compliant wall, fails on the thin patch, and flips with the target rather than with
the shape — and on a polygon it completes in 9.5 s a station where IP-FC-151 measured over 360 s
for one call on the exact B-spline. Better by a factor of forty, and still ≈114 s for 12 stations
against a 60 s gate. Whether a coarser polygon fits while still deciding a 0.01 mm question is
untested.

### The corpus answer, 2026-10-10 — **withdrawn the same day; see the next section**

The figures in this section were taken at a fixed 1 440 samples a loop and are wrong by up
to a factor of six above `U` = 2. They are kept because two published findings rested on
them and the withdrawal needs its subject on the page. Read "Sampling was the error" below
instead.


Both measures over all 28 saved walls, on **identical** stations:

| | incumbent C0 | selected C4 |
| --- | --- | --- |
| walls with all 12 stations sectioned | 14 | 14 |
| of those, meeting `WALL_TOL` = 0.01 mm | **0** | **0** |
| worst | `tail_shell` `U` = 4.0 at 0.2765 mm | `tail_shell` `U` = 4.0 at 0.2136 mm |

**The thin readings were not mostly instrument artefact.** That was the direction three separate
hints pointed — the stable median, the area mean's 0.0033 mm, C4 converging to exactly 0.600000 on
one section — and the corpus refutes it. Removing the corner artefact does move the numbers:
`tail_shell` at `U` = 0.5 goes 0.0397 to 0.0142 mm. It never moves a fully measured wall inside the
tolerance. At `tail_shell` `U` = 3.0 both measures report an **identical 0.1514 mm**, so that wall's
worst point is not at a corner at all and no corner-based fix could reach it.

**A claim about the nose was withdrawn here on measurement.** An earlier version of this paragraph
said "the nose walls move far more" between the two measures. They do not: the nose deltas run
0.0000 to 0.0652 mm and the tail's run 0.0000 to 0.0629 mm — comparable, not larger. The figure had
been carried over from the first sweep, whose nose rows were taken on a different station set.

**A "`U` break on both kinds" read off these rows is withdrawn as well.** This section reported that
the nose showed the same rise with `U` the tail did — 0.0010 to 0.0050 mm at `U` ≤ 2 against
0.0519 mm at `U` = 3.0 and 0.0701 mm at `U` = 4.0 — and took the agreement between kinds as evidence
the break was a property of the construction. Both columns came from the same fixed-count sampling,
so the rise is the instrument's; two readings sharing one artefact agree by construction. Measured
at a fixed 0.125 mm spacing the nose reads **0.0011 to 0.0115 mm** across the whole `U` range, five
of six inside `WALL_TOL`, with no break.

**The 14 nose walls are not judged.** They sectioned at only 5 to 9 of 12 stations on this grid, so
they are excluded rather than passed — the unmeasured stations are exactly where a defect could
hide. Every one of the 8 verdict disagreements between the two measures is a nose wall, and every
one is excluded for coverage, so no disagreement survives into the conclusion.

**One figure is now doubly corrected.** `WALL_TOL`'s own note was changed on 2026-10-06 to point at
the soak's 0.0067 mm for the nose at `U` = 3.0 as evidence the construction can reach the
tolerance. Both instruments read **0.0519 mm** on that same wall when stations reach the thin
region. The 0.0067 mm was a station-placement artefact of the body-based grid, not a compliant
configuration — a different failure from the measure-artefact one that note was written to warn
about.

**What this does not establish.** The grid is not the acceptance gate's own, so these are absolute
readings on a defensible grid rather than reproductions of the gate's number — IP-WTM-18 fixes that
for future walls and IP-WTM-21 recovers it for the nose. And nothing here says *why* the wall is
thin. **That is a measurement, not a decision**, and IP-WTM-20 is the next one: the `U` ≥ 3 readings
sit at or above the 0.19 mm that a severed section ring was once misreported as a thickness, so the
first thing to settle is whether those walls are thin or broken, by reading ring connectivity rather
than thickness on walls already saved.

### Sampling was the error, 2026-10-10 — and it cost two withdrawn findings

**The defect.** `unit_width` = `U` * 100, so a cowl's section perimeter scales with `U`, while
`cowl_n_perimeters` and `extrusion_width` are absolute and their product is the 0.6 mm wall. Every
measurement in this plan, and the production gate, fixed the sample *count*, so the circumferential
spacing scaled with `U`:

| | perimeter | gate, `AROUND` = 240 | this plan's sweep, 1 440 |
| --- | --- | --- | --- |
| `tail_shell` `U` = 1 | 428.3 mm | 1.785 mm | 0.297 mm |
| `tail_shell` `U` = 4 | 2 088.4 mm | **8.702 mm** | 1.450 mm |

`cowl_interior.check_samples` had it right all along at `CHECK_ARC` = 0.20 mm, and pass 2's scan
density was measured to hold at exactly 0.200 mm at `U` = 3 and 4. **The construction was correct
and the things measuring its output were not.**

**The correction.** Re-measured at a fixed 0.125 mm spacing, refined through six levels until the
reading settled (0.00008 mm per halving at the end):

| | published, 1 440 samples | refined, 0.125 mm | over `WALL_TOL` |
| --- | --- | --- | --- |
| `tail_shell` `U` = 0.5 | 0.0142 | 0.0135 | yes |
| `tail_shell` `U` = 1.0 | 0.0282 | 0.0286 | yes |
| `tail_shell` `U` = 1.5 | 0.0399 | 0.0421 | yes |
| `tail_shell` `U` = 2.0 | 0.0337 | 0.0345 | yes |
| `tail_shell` `U` = 3.0 | 0.1514 | **0.0469** | yes |
| `tail_shell` `U` = 4.0 | 0.2136 | **0.0347** | yes |

At `U` = 4's own worst station the reading falls from 0.2136 to **0.00264 mm**.

**Two findings withdrawn.** The corpus worst of 0.2136 mm, and the "regime change" in which pass 2
went optimistic by 0.11–0.17 mm above `U` = 2. **There is no `U` trend on the tail**: the whole tail
range lies in one band and the worst wall is `U` = 3.0, not `U` = 4.0. Pass 2's prediction tracks
the real wall to within 0.0039 mm, mean 0.0003 mm, and no build's real wall exceeds `TAU` = 0.05 mm.

**But there is one on the nose, and it was invisible until the station grid was fixed** (IP-WTM-21).
The nose's thinning is strictly monotonic in `U` — 0.00115, 0.00310, 0.00376, 0.00504, 0.00829,
0.01403 mm over `U` = 0.5 to 4.0, a factor of 12.2 across a factor of 8 — while the tail's peaks at
`U` = 3.0 and is not monotonic. The two kinds are therefore not one phenomenon at two magnitudes,
and the tail already reads twelve times the nose at `U` = 0.5 where the nose's scaling term has barely
started. [§6.7](../design/cowl_interior_surface.md#67-the-station-grid-a-bounding-box-is-not-the-part)
carries the table; it splits IP-WTM-26 into a `U`-independent part that tracks the diagonals and a
part that grows with the part, and the nose is forty times cheaper to chase.

**What survives.** Every fully measured tail wall is over `WALL_TOL` by three to five times, at
every `U`, and every station is a healthy annulus rather than a severed ring (IP-WTM-20). The wall
is about as thin as `TAU` permits, which is a binding criterion rather than a construction defect.

**The corpus count changed with the grid, and four tests had to be re-pointed at the new answer.**
Under the bounding-box grid no wall met `WALL_TOL`; on the real extent **five of the twelve distinct
walls do**, all of them noses, and the finding is now a shape rather than a count — every
`tail_shell` fails at every `U` and the only nose failure is `U` = 4. The incumbent C0 still reports
none of the twelve compliant, and that is not a second opinion: C0 reads 0.0294–0.0380 mm on every
nose build across an 8× range of `U`, a 1.3× band, because it is reading a corner. A test requiring
pass 2's shortfall to stay inside `WALL_TOL` *under both measures* was therefore asserting something
about C0's blindness, not about pass 2; it is now scoped to the selected measure, with the converse
asserted beside it.

**The mechanism of the residual 0.028–0.048 mm is not identified, and two candidates are refuted
rather than untested.** Smooth-arc chord sag is real, exactly `s^2 / (8R)`, and linear in `U` at
fixed count — and **400 times too small** (0.0005 mm against 0.18 mm observed). Two synthetic
reproductions, one with absolute-sized notches, also failed to produce the error. Local curvature
does not predict the thin spot and at `U` ≥ 3 is *anti*-correlated: the worst stations rank 0.31 to
0.67 by curvature percentile while inside-tolerance controls rank 0.81, 0.95 and 0.96 with local
radii of 1.6 to 1.8 mm. At `U` = 1 the ranks are mixed. That is IP-WTM-26.

**Three defects were found in this plan's own tools while chasing it**, all now fixed with
regression tests:

* `sweep.measure_wall` fixed the count. It takes `spacing` now and records which was used in every
  result row.
* `locate` at 720 points classified a healthy `U` = 4 annulus as **severed**, contradicted by the
  kernel at `z` = -285.2857. It derives its count from the station's own perimeter now.
* `candidates._segment_distances` was unbounded in memory — a refinement at 0.03 mm spacing on a
  `U` = 4 section asks for a 68 000 x 68 000 matrix, 37 TB, and the first run had to be stopped.
  Chunked now, verified exact against the single-block form at every block size.

**And one in the selected measure itself.** `corner_excluded_min` resampled the inner loop to
uniform arc spacing before subsetting, so it measured a different *point set* from the incumbent
rather than a subset of it — breaking the one structural relationship between them, that C4 can
never report more thinness than C0. It surfaced as C4 0.04806 against C0 0.04689 at `tail_shell`
`U` = 3.0. The resampling was also unnecessary: `Wire.discretize(Number=n)` was measured uniform to
within 0.1 % at every density. The measure now takes its samples as given and applies the margin
along true arc length. **A test had asserted this invariant and passed only because the old data
happened to comply.**

**Where the corner artefact actually lives, which the corrected sweep shows cleanly.** On
`nose_cowl_shell` the incumbent reads 0.027–0.039 mm where C4 reads 0.0010–0.0115 mm, so its reading
there is dominated by distances cutting across concave corners. On `tail_shell` the two agree
closely and at some stations **exactly** — which, given the subset relationship, means C0's own worst
sample survives the exclusion, so the tail's thinning is not at a corner and no corner-based fix
reaches it. Five of six nose walls read inside `WALL_TOL`, which is why IP-WTM-21 now matters.

### Pass 2's prediction against the real wall — IP-WTM-13's answer

The remaining question about `cavity()`'s post-cut pass was how far its *prediction* of the finished
wall sits from the part, and it needed **no build at all**: pass 2 prints its own final figure per
build (`cavity closed: ... worst finished wall error`, which is `worst_finished` from the last
passing round), so a build that returns a solid carries pass 2's guarantee that its predicted
thinness is at most `TAU` = 0.05 mm everywhere it scanned. The real side is the corrected sweep
above. `wall_measure.prediction` joins them and `tests/test_wall_measure_prediction.py` asserts it.

**The comparison is deliberately one-sided.** The two sides are maxima over different grids: pass 2
scans 142 to 529 points a build, so its maximum is near the wall's true worst, while a 12-station
sweep's maximum is a *lower bound* on it. That asymmetry can only hide real thinness, never invent
it, so "the real wall is thinner somewhere than pass 2 predicted anywhere" is sound while the
reverse is not. The shortfall is clamped at zero rather than reported signed, and these are not
per-station gaps.

| build | pass 2 predicted | real, refined | shortfall | rounds |
| --- | --- | --- | --- | --- |
| `tail_shell` `U` = 0.5 | 0.0379 | 0.0135 | none | 1 |
| `tail_shell` `U` = 1.0 | 0.0481 | 0.0286 | none | 0 |
| `tail_shell` `U` = 1.5 | 0.0484 | 0.0421 | none | 0 |
| `tail_shell` `U` = 2.0 | 0.0366 | 0.0345 | none | 1 |
| `tail_shell` `U` = 3.0 | 0.0430 | 0.0469 | **0.0039** | 5 |
| `tail_shell` `U` = 4.0 | 0.0393 | 0.0347 | none | 2 |

**Pass 2's prediction is sound, and an earlier version of this section said the opposite.** It
reported the gap as "a regime change, not noise" — zero below `U` = 3 and eleven to seventeen times
`WALL_TOL` above it — and concluded that no tightening of `TAU` could certify the part. Both
statements came from a real side sampled at a fixed count; see the previous section. The largest
shortfall is **0.0039 mm**, half of `WALL_TOL` and a tenth of pass 2's own criterion, and at four of
six builds the prediction is conservative. No build's real wall exceeds `TAU`.

**Pass 2's round count is a real signal that gates nothing.** The build that spent 5 of its 6
allowed rounds, `U` = 3.0, is also the only one with a shortfall and the worst wall in the corpus.
That correlation survived the correction, and the count is printed in the log and read by nothing.

**So the finding is about `TAU`, not about this gap.** Every tail wall reads 0.028 to 0.048 mm thin
at its worst, three to five times `WALL_TOL`, while pass 2 stops at `TAU` = 0.05 mm — the walls come
out just inside the criterion they were converged to. Whether tightening `TAU` yields a compliant
wall is unmeasured. It is what both passes stop at, so tightening it adds fit rows and re-cut rounds
to every build, and `U` = 3.0 already spends 5 of 6. **That is a measurement, not a design choice, and it is being taken.** `freecad/tau_study.py` builds one part at several `TAU` and measures the resulting wall, the fit rows and the rounds spent, so the three possible answers are all readable off the same run: the wall gets thinner in proportion and `TAU` is the lever; or the build raises `Unconverged` because pass 2 cannot reach the criterion inside `POST_CUT_ROUNDS` = 6, which the `U` = 3.0 build makes a live possibility at 5 of 6 already; or the wall does not improve at all, which refutes the reading above and sends the search back to the mechanism. Cost is an output of that test rather than a reason to defer it. That is IP-WTM-27.

### What this plan did to the two open questions

**OQ-DES-CW23 is withdrawn, 2026-10-10 — and the reason first recorded for withdrawing it was
itself wrong.** The item asked how to handle "the resulting small residual gap" between pass 2's
prediction and the real cut. It was missing information presented as a design choice: no instrument
could say how large the gap was, so none of its four alternatives could be scored.

The first withdrawal note said the premise was false and that the gap was a regime change of
0.11–0.17 mm above `U` = 2. That came from a real side sampled at a fixed count. Measured properly,
**the gap is at most 0.0039 mm — so the item's own description of it as small, and its original
±0.01–0.04 mm characterization, were accurate.** The item is still withdrawn, because knowing the
gap's *size* is what finally let its alternatives be scored, and that was a measurement rather than
a decision. But it was withdrawn for the opposite reason from the one written down first, and the
note in `cowl.md` has been corrected to say so.

How the alternatives stand: 3 and 4 remain ruled out on the station-insertion measurements, which no
change of instrument affects, and are now plainly not worth it against a 0.0039 mm gap. Alternative
1 — rely on the external check — is what the evidence supports, with one repair owed first: that
check's own `AROUND` = 240 is a fixed count and is 8.7 mm apart at `U` = 4, so it must be given an
arc-length spacing before it can be relied on. That is IP-WTM-25.

**OQ-DES-CW26 stays open, because its question really is a choice.** It asks which of three checks
to adopt against a wall whose section ring has broken, and that is not a measurement. Two findings
were reported to it, and one of them has since been corrected:

* **The false-positive survey it named as a prerequisite is delivered.** The annulus guard went into
  `wall_thickness` on 2026-10-05 and the soak ran the next day with it active, recording
  `missing_stations` = 0 across 28 builds at 12 stations each — **336 readings, no false positive**,
  where IP-FC-152 had only six spot checks.
* **The worry that large-`U` walls might be severed rather than thin is retired.** It rested on
  readings of 0.1514 and 0.2136 mm sitting near the 0.355705 mm a broken ring was once misreported
  as. Those readings were the instrument; properly sampled the walls read 0.0135–0.0481 mm, and
  every station of every wall examined is a healthy annulus (IP-WTM-20). A thickness figure and a
  broken ring are not confusable at these magnitudes after all.

### The station grid was wrong, and it invalidated the first sweep's comparison

**Found 2026-10-10, by its own symptom.** The first corpus sweep lost 3 to 7 of 12 stations on
every `nose_cowl_shell` wall, while the soak had recorded `missing_stations` = 0 for all 28 builds.
Both cannot be right about the same stations — and they were not the same stations.
`check_cowl_interior.main` and `soak_cowl_shell` both place their grid from **`ci.z_extent(body)`**,
the full cowl solid, inset 1 mm. The corpus saves only the finished **wall**, whose z extent is not
the body's, so `corpus.station_grid` produced a different set and its end stations fell where the
wall has no closed annular section.

Two consequences, both recorded rather than worked around.

**No figure from this grid may be differenced against a figure the soak recorded**, because they
are answers about different places. Measured directly: on the wall-based grid the incumbent reads
0.0395 mm on `nose_cowl_shell` `U` = 0.5 where the soak recorded 0.0384, and 0.0314 on `U` = 1
where the soak recorded 0.0256. The first sweep's entire delta column was that comparison, so it is
withdrawn. `sweep.sweep` now takes **several measures and runs them on identical sections**, which
is a comparison that holds without the body; the soak's figure is still carried and is never
differenced. IP-WTM-18 would let a future soak save the body so the gate's own grid is
reproducible.

**A wall with incomplete coverage cannot count as compliant.** The first sweep's `worst_thin`
ignored stations with no section, exactly as the soak's own `worst_wall_error` does — so a wall
measured at 5 of 12 stations reported a clean figure and would have counted as meeting the
tolerance. It has been shown nothing of the kind: the 7 unmeasured stations could be the thin ones,
and `check_cowl_interior` counts a station with no section as a failure (`bad += 1`), not as a
skip. `sweep.verdict` now excludes incomplete walls by default and reports how many it excluded.
Which convention is right is IP-WTM-19, and it changes the nose's answer.

### Every measurement here is a library tool, not a script

**Standing requirement, and this plan already broke it once.** The finding above — the incumbent
failing to converge on a real wall — was first produced by a throwaway heredoc. A number quoted in
a design document whose only provenance is a scratch script cannot be re-derived, cannot be
regression-tested, and cannot be run by anyone else; the value of a measurement is in being
repeatable, so the tool is the deliverable and not the number it printed.

Retrofitted under IP-WTM-15: the sweep is `gates.refinement_sweep`, the verdict is
`gates.converged`, the real-section gate is `gates.convergence_gate_on_section`, access to the 28
saved walls is `wall_measure.corpus`, and the claim is asserted in
`tests/test_wall_measure_corpus.py` — where a future change that makes the incumbent converge will
fail a test and send someone back to this plan's premise, which is what a test is for.

Every remaining item follows the same rule: the analysis goes in the package with tests, and the
scratchpad is only for exploration whose result moves into the library before being quoted.

**The rule bit a second time, in a milder form, and the entry point moved too.** The corpus sweep
that produced §6.4's table was run from a thin scratchpad script — every measurement inside the
library, which is better than a heredoc, but the command that produced a published table was still
not in the repository. Both halves are now `wall_measure.report`: `prediction_report` reproduces
§6.5 from the two artifacts on disk in under a second and needs no vendor module, and `sweep_report`
re-measures the saved walls given `Part` and `App`. So `python -m wall_measure.report` re-derives
every figure in §6.5, and the expensive half is one call away. The package's own AST test caught a
lazy `import FreeCAD` inside `report.main` while this was being written, which is what that test is
for.

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
are separate questions, and only the second was in scope. The answer came back the less convenient
way — the wall is thin, the thin readings were not mostly instrument artefact, and three hints that
had pointed the other way were all real and all insufficient — so the construction work this plan
hoped to shrink has instead been given a located boundary at `U` = 2 to start from. IP-WTM-20 and
IP-WTM-21 are the measurements that remain; the construction change itself belongs to another plan.

### The rib cut's own edges, and four measures that were wrong about them (IP-WTM-33)

§4.2's three-dimensional identity argues that a rib's crease belongs on the boundary of a boolean
rather than in a fitted surface. **Nothing checked that the boundary the kernel returned is in the
right place**, and `cavity`'s two post-cut checks cannot: a residue volume of 0.01 mm³ and a solid
count of one are both satisfied by a trimming curve 0.05 mm off the surface it should lie on.
IP-FC-137's synthetic invalid sliver is the precedent — it passed the volume check at 0.000000 mm³.

Measured 2026-10-11 through `wall_measure/boolean_edges.py` and `freecad/rib_edge_check.py`: a rib
edge is ∂S ∩ ∂T, so every sample on one must be on the fitted interior surface and on a dilated tool
face at once. **They are.** Worst departure from the fitted surface 5.3e-08 mm on the nose at
`U` = 0.5 (45 rib edges, 187 samples) and 2.972e-04 mm on the tail (831 edges, 4 540 samples); worst
departure from a tool plane 2.1e-14 mm; zero samples over `WALL_TOL` in either. **That refutes the
rib-edge shape as the mechanism behind the residual, by a factor of forty-five**, rather than
leaving it untested. §6.9 has the table and the two incidental findings (two tool faces coincident
with a cell plane to 6e-6 mm, and one tail edge group with the wrong face count).

**The check was wrong four times first, and every time the geometry was fine.** Worth recording as a
class, because all four returned a plausible number and raised nothing:

1. probing **face vertices** — shared with neighbors, so 35 of 60 faces read as lying on more than
   one operand and an end-lid edge 22.5 mm from any tool was called a rib crease;
2. probing **facet centroids** — on a chord, so up to the tessellation deflection inside a curved
   face: 0.1 mm against a 1e-5 mm tolerance, which put **zero** faces on the fitted surface;
3. **`projectPoint`/`parameter`** and then **`Surface.toShape()`** — both read the edges 2.411 mm
   off a surface the kernel put them 6.9e-18 mm from, the first because the surface is periodic in
   `u` and the second because it rebuilds over the natural parameter range, not the fit's;
4. **`distToShape` against all of `smooth.Faces`** — read 6.9e-18 mm for edges genuinely 2.411 mm
   from the fitted surface, because they lie on a *side cap*. That one would have passed the check
   while measuring none of the 45 edges in question.

What found each was the cheap-against-kernel cross-check and the face-classification tally, which is
why both are permanent parts of the tool rather than scaffolding. §6.1 carries the two reusable
cautions.

**The edge was in the right place; the surface underneath it was a separate question (IP-WTM-37).**
A trim curve sitting exactly on both surfaces constrains the curve, not the surface it is drawn on,
and `removeSplitter` refits what it merges — so a refit that reproduces the trim boundary could
still differ in the patch *interior*, which is a boundary-value problem whose signature is a
displacement in the middle of a patch. Three tests settled it, strongest first:

* **`surface_identity`: the control nets are identical.** Degrees, pole counts, knots,
  multiplicities, weights, periodicity, and **worst pole difference 0.000e+00 mm** — on the tail as
  well as the nose, with eleven tools and 831 rib edges cut into it. Not "within tolerance": no pole
  moved. The boolean trimmed and did not refit, so nothing is imposed at a patch edge and nothing
  can propagate inward. This test is exact and parameter-free, which makes the other two
  confirmation rather than evidence.
* **`patch_deviation`: the interior is flat.** 829 tail probes banded by distance to the nearest rib
  edge read 0.0, 3.6e-15, 7.3e-15 and 7.9e-15 mm from nearest to farthest — double-precision noise,
  with no trend in distance.
* **The normals agree**, 0.0000° mean over 345 tail probes. The single 0.0072° reading is in the
  nearest-edge band and sits three times under `face_normal`'s own measured resolution (median
  0.0214°), so it is instrument noise rather than a surface difference.

**What the normals did find is a number worth tracking: the crease angle.** The angle between the
fitted surface and the tool plane is 0° at a tangency, which is the degeneracy `RIB_CUT_FUZZ` exists
for. Minimum over 200 rib-edge samples: **54.7° on the nose, 18.3° on the tail** — three times
closer to tangency, with five tail samples under 40°. Nothing failed, so this is not a defect; it is
the first direct reading of the quantity the documented `Diag12Safe` sliver is a limit of, and it is
one cheap scalar per build. That reframes IP-WTM-34: if the minimum collapses toward 0 near
`U` = 0.75 where that sliver occurred, the crease angle is a *predictor* of the failure rather than
a description of it, and the fuzzy boolean gains something to be checked against instead of only
tuned by hand.

**A fifth wrong measure, in the same class as the four above, caught by its own test.** `_snap_to`
fell back to returning the point it was given when the kernel refused — right for `interior_probes`,
where losing a probe manufactures a `neither` classification, and wrong for `face_normal`, where six
unsnapped offsets are not on the face and the plane through them is a normal derived from the offset
*directions* alone. It came back as `[-0, -0, -1]`, a confident unit vector, with nothing to say it
was meaningless. `face_normal` now passes `strict` and drops what it cannot snap.

**One package rule was also broken and caught by an existing test.** `boolean_edges` first reached
the kernel through `import Part` inside the four functions that need it — the convention for a
vendor-side script, and wrong inside `wall_measure`, which must import on a sweep worker with no
FreeCAD. `test_wall_measure_sweep.TestThePackageIsPortableToTheWorker` walks every module's whole
AST and failed on all four; `Part` now arrives as an argument, as in `locate` and `corpus`. The
module's own no-vendor test had looked at `tree.body` alone and passed, and now walks the AST too.

### Closing OQ-DES-CW26 alternative 1's axial bound (IP-WTM-40)

That question asks whether an unperturbed build can reach the severed-ring state, and the answer so
far is "none has been caught, across 336 station readings" — with the item stating its own bound:
the acceptance grid's 12 stations are about 25 mm apart on a tail, the reproduced break's extent in
`z` was never measured, so an axially short break could sit between two of them. The item names the
closing move and **nothing was filed to do it**, in either plan.

It is now `freecad/ring_scan.py` over `locate.state_profile`, reading the saved `.brep` walls with
no build, scanning `tail_shell` at `U` = 3.0 first because that is the configuration the break was
reproduced on, and escalating any station it calls severed to the kernel before reporting it — the
nesting test is a proxy and has produced a false positive before.

**Three defects were found in the existing tools while building it.**

* **`locate.dense_grid` placed its stations from `Shape.BoundBox`** — the third recurrence of the
  caution §6.1 already carries twice, and the worst-placed one: a nose wall at `U` = 4 has a box
  twice the length of the part, so half such a scan would land on empty space and be classified
  `no_wall`, a false positive in the one function meant to find a broken ring. It now takes the
  sectioning extent, and is indexed by **axial spacing in millimetres** rather than a station
  count, for the standing reason that the part's length scales with `U` and a defect's extent does
  not.
* **`density.loop_lengths`' docstring said "outer first" while the function sorts by length** —
  and `sections.station_loops` documents the refutation of exactly that in the opposite direction:
  a rib detour can make the inner loop longer while enclosing far less, measured at two loops
  within 0.25 % in length with areas not close. Benign in effect, because the value only sets a
  sample count and longest is the right pick for that, but the two functions were asserting
  opposite things about the same geometry. Both now state their ordering and why it differs.
* **The scan sliced twice per station**, once through `density.section_perimeter` to size the
  sampling and once for the loops. `sections.loops_from_wires` splits the discretization out so a
  caller slices once, reads `Wire.Length` off those wires, and discretizes the same ones.

**The result, on the configuration that matters most: 0 severed stations.** `tail_shell` at
`U` = 3.0 — the wall this item's break was reproduced on — scanned at 1 mm axially across its real
sectioning extent, 298 stations: **297 healthy annuli, 0 severed, and 1 `no_wall` that resolved as
a slice artifact.** A break would have to be under a millimetre long in `z` to have hidden between
these stations, against the 93 mm of circumference the reproduced one spanned.

**A fourth defect, in this scan's own confirmation step, and it would have reported a healthy wall
as defective.** The one `no_wall` station got the kernel to *agree* with it — and that agreement
was worthless: with zero closed wires, `ring_state`'s nesting test and `Part.makeFace` are both
answering "not an annulus" about the same empty input, so they cannot disagree. §6.1's second
caution is the actual test, and re-probing six offsets returns a 2-loop annulus at **every** one
(±0.01, ±0.05, ±0.20 mm, ~5 742 samples on a ~1 150 mm perimeter). `locate.nearby_states` and
`is_slice_artifact` now run automatically for any `no_wall`, and `ring_scan` counts only severed
rings and confirmed gaps as findings. **A cross-check between two measures of an empty input
confirms nothing** — which is the same class as the five wrong measures recorded above, in its
sixth guise.

**And the cost estimate in OQ-DES-CW26 is wrong, refuted by a number already in that item.** It
calls the scan "a file read"; alternative 2 of the same item records "the slice costs about 7 s on a
2464-face wall", and a dense scan is a slice a station. **Measured 2026-10-11**: 16.3 s a station
(50 stations in 814 s) at 1 mm axially and 0.2 mm circumferentially, 298 stations, about **81
minutes for one wall**. The item has been corrected, and extending past the first wall was machine
time to be scheduled rather than spent unasked. It does not change that item's recommendation, which
was chosen on grounds independent of whether the failure is reachable.

### The whole corpus at 1 mm, and what it took to be worth running (IP-WTM-40)

**The result: 1 704 stations across all twelve distinct walls, 1 703 healthy annuli, 0 severed, 0
confirmed gaps.** Both kinds at `U` = 0.5, 1.0, 1.5, 2.0, 3.0 and 4.0, each across its own
sectioning extent, every station classified from that station's own loops at 0.2 mm circumferentially
— the same density the first wall was scanned at, so all twelve are one measurement rather than
twelve calibrations. The per-wall table is in
[cowl.md OQ-DES-CW26](../design/cowl.md#open-questions). Total **3 h 4 min**.

**What the kernel was and was not asked.** `confirm` escalates only the stations the scan flags, so
on the ten walls that flagged nothing the kernel was never consulted, and "no disagreement" means
"no disagreement at the one station where there was anything to disagree about". That is the design
— a kernel call a station would have multiplied the run — and it is sound here for a structural
reason rather than an empirical one: **whether the ring is severed is decided by the kernel's own
wire topology, not by the sampling.** A break leaves the section either one closed loop or two
non-nested ones, and the loop count comes straight from `Shape.slice()`; the 0.2 mm discretization
enters only the nesting decision between loops, where under-sampling's known failure direction is a
false *positive* (`locate.N_POINTS`, a healthy `U` = 4 annulus once read as severed) and not a
missed break.

**One wall was scanned twice, and that is the most informative thing in the run.** `tail_shell` at
`U` = 3.0 had been scanned earlier the same day; it was re-run rather than having its figures copied
into a result file, because a measurement artifact that no run produced is not evidence. It
reproduced exactly: 298 stations, 297 annuli, 0 severed, and the same single `no_wall` at
`z` = -293.98226487 to the last printed digit, with the same six neighbours all healthy annuli. **So
the slice artifact is deterministic, not an intermittent kernel flake** — which is what licenses the
re-probe as a test, since an intermittent failure could in principle also strike a neighbour.

**Three changes were needed before the corpus run was affordable or trustworthy.**

* **`dense_grid` was sectioning for the extent that `scan_wall` had already sectioned for.**
  `sectioning_extent` bisects each end to 1e-3 mm — about forty sections on a wall whose box spans
  400 mm, at seconds a section — so every wall paid for its extent twice. It now takes `extent` from
  a caller that has it. This is not a defect of correctness, which is why no test caught it; it was
  found by costing the run before committing to it.
* **One process a wall, each writing its own JSON.** `freecadcmd` exits 0 on an uncaught exception,
  so the artifact is the only honest record of how far a run got. At up to an hour a wall, a crash
  on the eleventh must not cost the ten already paid for. `ring_scan --json` writes after every
  wall and `--summarize` folds the files back into one verdict with no kernel and no walls, through
  `locate.scan_verdict`/`scan_table`.
* **A `no_wall` resolved as a slice artifact is counted apart from a finding.** Counting it would
  report the plane the scan happened to choose as a defect in the part; not reporting it at all
  would hide how often the slicer does this. It is one station in 1 704.

**The cost model, now that there is one.** Per station: 1.2 to 2.2 s on a `nose_cowl_shell`, 5.2 to
9.2 s on a `tail_shell`. The spread *within* a kind is only 1.8× across an eightfold range of `U`,
while the gap *between* kinds is about 4× — so the cost tracks the face count (536 against 2 464),
not the part's size, and a future scan should be budgeted by kind and station count rather than by
`U`. Dropping the second slice a station took the `U` = 3.0 wall from 16.3 s to 8.1 s, the 1.8×
the two-slice arithmetic predicted.

**What the run closes and what it does not.** It closes the axial bound OQ-DES-CW26 set itself: no
unperturbed wall in the corpus is severed anywhere at 1 mm resolution, against a reproduced break
spanning 93 mm of circumference. It does **not** close the input-space bound — all twelve walls vary
in `U` alone, with every other design input at the parameter sheet's values — and it says nothing
about the mechanism, which remains IP-FC-146. Those are different claims and the item is worded to
keep them apart.

### Cross-plan

**Supersedes IP-FC-151** in `freecad_migration.md`, which is marked superseded and points here.

**IP-FC-152's prerequisite measurement is delivered by IP-WTM-14** — the annulus test's
false-positive rate across both kinds and the swept `U` range, 336 station readings with no false
positive, recorded in that item's blocked-reason note. It stays blocked on OQ-DES-CW26 all the same,
because which check to adopt is a choice and not a measurement.

**Uses `geometry_bridge.md`'s library** but does not depend on unfinished items in it: IP-GB-16's
facades and IP-GB-21's tube fixtures are both done.
