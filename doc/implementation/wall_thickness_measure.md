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

**Choosing the instrument needed no open question, by design.** The requirements on the instrument
follow from `WALL_TOL` and from how a single-perimeter spiral-vase wall fails — they are not matters
of taste — and they are written as the five pass/fail gates in the Notes below, fixed before any
candidate is run. A candidate either passes all five or it does not. Where more than one passes, the
tie-break is also pre-committed (cost).

**That is no longer the whole plan, and the header said otherwise until 2026-10-16.** It read
"this plan contains no open questions" and "nothing here is waiting on a design choice", which was
true when the plan was filed and stopped being true as the measurements landed. **Six design
questions have since been raised *by* this plan's own output — OQ-DES-CW28 through OQ-DES-CW33 —
and six work items wait on them.** None is waiting on evidence about the wall; each is a trade whose
terms are now measured and whose resolution belongs to the person who owns the design. The
distinction the original wording was reaching for still holds and is worth keeping: *selecting* a
measure was decidable from requirements, while *what the acceptance gate should do about what the
measure found* is not.

**Status, 2026-10-16: 42 items done, 1 `todo`, 6 blocked on open questions, 0 `active`.** The one
`todo` is IP-WTM-49, which is a measurement and needs no decision.

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
| `tail_shell` `U` = 3.0 | 0.1514 | 0.0469 |
| `tail_shell` `U` = 4.0 | 0.2136 | **0.0347** |

The `U` = 3.0 refined figure read 0.0481 here until 2026-10-16, which is a **pass 2 prediction**
figure from the `TAU` study rather than a finished-wall reading; 0.0469 is what §6.6, §6.4, §6.5,
§6.7 and §6.8.1 all carry, and what this plan's own Notes carry twice.

**What stands.** Pass 2's prediction tracks the real wall to within 0.0039 mm. **Every station
measured is a healthy annulus — 3 342 of them now**, 1 704 across the `U` axis (IP-WTM-40) and
1 638 across the design-input axis (IP-WTM-41), with 0 severed and 0 confirmed gaps. **OQ-DES-CW23
is still withdrawn, but for the opposite reason from the one first recorded**: its "small residual
gap" is real and small, and knowing its size is what finally let its alternatives be scored.

**One sentence here read "the tolerance is unmet on every fully measured wall" and is withdrawn.**
Judged on a station grid placed from the real axial extent rather than a bounding box (IP-WTM-21),
**5 of the 12 distinct walls meet `WALL_TOL` and 7 do not**: every `tail_shell` fails at every `U`,
at 0.0134 to 0.0469 mm, and the only failing nose is `U` = 4.0. The kinds differ, and saying they do
not hid where the defect lives.

**The explanation that replaced those figures has itself been superseded twice, and both
supersessions are findings rather than corrections.** This header said the wall was "about as thin
as `TAU` = 0.05 mm permits, a binding criterion rather than a construction defect".

- **On a tail that is refuted.** `TAU` is not the lever: pass 2's worst gap is **invariant across a
  fivefold range of it** — 0.0601 mm at every criterion at `U` = 0.5, 0.0481 at `U` = 2.0 — and
  tightening it to 0.02 or 0.01 does not produce a wall at all but raises `Unconverged` against
  `cavity`'s 64-station patch budget, at both configurations (IP-WTM-28, IP-WTM-44).
- **On a nose it was the wrong constant.** The cause is `_seed` taking a fixed **count**, so the
  axial spacing grows 2.44 → 17.60 mm over an eightfold `U` range and the wall's error tracks it to
  ±13 % (IP-WTM-36). `TAU` is the floor *underneath* that, and it is a two-position switch: at any
  `TAU` ≤ 0.02 the `U` = 4 nose reaches **0.00268 mm**, 3.7× inside tolerance (IP-WTM-26).

**And every figure above is in-plane, which is the plan's last and largest finding.** A plane cutting
a slab inclined at θ reads `thickness / cos θ`, always thicker than the slab is. The interior surface
is inclined 21.5–30.8° where the wall is thin, and measured along its own normal instead, **66
readings across three walls are every one confirmed thin and thinner than the plane said, none
exonerated** — worst deficits **0.0943, 0.0790 and 0.0645 mm, six to nine times `WALL_TOL`**, where
the in-plane figures at those same samples read 0.0135, 0.0140 and 0.0226 (IP-WTM-26, §6.8.2.2).
So the 0.0134–0.0469 mm range above is a **lower bound on the deficit**, not a measurement of it, and
the tolerance is unmet by more than any in-plane number in this plan says. What the gate should do
about that is OQ-DES-CW33.

**Separately, `check_cowl_interior.wall_thickness` had the same fixed-count defect this plan's own
sweep had** (`AROUND` = 240, 8.7 mm apart at `U` = 4), so the production gate's readings above
`U` = 2 were not sound either. That was IP-WTM-22 and IP-WTM-25, and it is fixed: the gate samples at
`WALL_ARC` = 0.125 mm, derived per station from that station's own perimeter.

**The expensive part was already paid, for every question about the `U` axis.** The 2026-10-06 soak
saved all 28 finished walls as BREP — 412 MB in `src/Fuselage/freecad/out/soak/shapes/`, both kinds
at `U` ∈ {0.5, 1, 1.5, 2, 3, 4}, with five repeats at two of them. A new instrument is validated and
run against real geometry by loading those files, not by rebuilding: the tail at `U` = 4 cost 4 870 s
a build and costs a file read now.

**"No item in this plan requires a cowl build" was in this header and is withdrawn.** It held for
every item through IP-WTM-25, and the saved corpus is still the right first resort. But the corpus
varies in `U` **alone**, so three classes of question fall outside it and each has now been paid for
in machine time: changing a construction constant (IP-WTM-27, IP-WTM-28, IP-WTM-36, IP-WTM-44 — the
`TAU` and seed studies, 3 827 s, 2 154 s, 5 656 s and 1 799 s for single builds), moving a design
input off the parameter sheet (IP-WTM-41, **6 h 56 min** for 36 walls, of which the `tail_shell`
population alone is 6 h 16 min), and measuring a saved wall in 3-D rather than in-plane (IP-WTM-26,
about 2 s a sample, 770 s for twelve stations of twelve). The rule worth carrying to the next plan is
narrower than the one stated here: **a question about `U` is answerable from file; a question about
anything else is a build.**

**Design authority:** [cowl_interior_surface.md §5 "The three convergences, and where the chain
breaks"](../design/cowl_interior_surface.md#the-three-convergences-and-where-the-chain-breaks),
[§6.1 Measurement cautions](../design/cowl_interior_surface.md),
[§6.4 Which measure reads the wall](../design/cowl_interior_surface.md#64-which-measure-reads-the-wall-and-what-it-says-the-wall-is)
and [§6.5 Pass 2's prediction against the real wall](../design/cowl_interior_surface.md#65-pass-2s-prediction-against-the-real-wall),
which this plan produced and which are now the authority for both,
[§6.8.2.2 The wall measured perpendicular to itself](../design/cowl_interior_surface.md#6822-the-wall-measured-perpendicular-to-itself-and-the-two-populations-it-separates)
and [§6.8.2.3 In-plane severity is an inverted selector](../design/cowl_interior_surface.md#6823-in-plane-severity-is-an-inverted-selector-measured),
which this plan also produced and which bound how any in-plane figure above may be read,
[cowl.md OQ-DES-CW26](../design/cowl.md#open-questions) and
[OQ-DES-CW28 through OQ-DES-CW33](../design/cowl.md#open-questions),
[`cowl_interior.WALL_TOL`](../../src/Fuselage/freecad/cowl_interior.py)

**Last updated:** 2026-10-16

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
| IP-WTM-13 | done | Re-measure OQ-DES-CW23's prediction-versus-real gap with the selected measure, since the recorded 0.0121 mm mean is a comparison against a non-converging instrument | IP-WTM-11 | [§6.5](../design/cowl_interior_surface.md#65-pass-2s-prediction-against-the-real-wall) |
| IP-WTM-14 | done | Report to OQ-DES-CW23 and OQ-DES-CW26 what the new evidence does to each one's premises — withdrawing CW23, whose premise the evidence refutes, and reporting to CW26 and IP-FC-152 | IP-WTM-12, IP-WTM-13 | [cowl.md OQ-DES-CW23, OQ-DES-CW26](../design/cowl.md#open-questions) |
| IP-WTM-20 | done | Settle whether the `U` ≥ 3 tail walls are thin or severed, by reading section-ring connectivity rather than thickness at those stations on the already-saved walls | IP-WTM-13 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales), [cowl.md OQ-DES-CW26](../design/cowl.md#open-questions) |
| IP-WTM-21 | done | Judge the nose on a grid placed from the wall’s **real** extent rather than its bounding box — no rebuild needed, since `Shape.BoundBox` on these solids is an outer bound only and sectioning recovers 12 of 12 stations | — | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-22 | done | Parameterize `sweep.measure_wall`/`sweep.sweep` by circumferential **spacing** rather than sample count, and record in every result row which was used | IP-WTM-13 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-23 | done | Bound `candidates._segment_distances` in memory by chunking, since a refinement study at 0.03 mm spacing on a `U` = 4 section asks for a 68 000 x 68 000 distance matrix | IP-WTM-22 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-24 | done | Re-measure the corpus at a fixed spacing and withdraw every absolute figure taken at a fixed count, in `cowl_interior_surface.md`, `cowl.md` OQ-DES-CW23 and `WALL_TOL`’s own note | IP-WTM-22 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales), [§6.4](../design/cowl_interior_surface.md#64-which-measure-reads-the-wall-and-what-it-says-the-wall-is) |
| IP-WTM-25 | done | Replace `check_cowl_interior`’s fixed `AROUND` = 240 with an arc-length spacing, the way `cowl_interior.check_samples` already uses `CHECK_ARC` = 0.20 mm, since at `U` = 4 that count is 8.7 mm apart on a 0.6 mm wall. **`WALL_ARC` = 0.125 mm, one spacing for both loops**, the outer loop’s 8× densification retired on the chord-sag arithmetic; the gate’s `tail_shell` `U` = 4 mid-station thinning falls from 0.1546 to 0.0325 mm | IP-WTM-24 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-10 | done | Adopt the selected measure in `check_cowl_interior.wall_thickness` beside the incumbent, reporting both, and keep the incumbent’s figure in the printed output for one corpus so the two can be compared. **`station_measures` computes both from one section at one sampling**, so the subset identity `selected >= incumbent` holds and is checked on every run; the incumbent still gates. On a real nose build they disagree about the verdict — 0.0376 mm and failing against 0.0031 mm and passing — which is filed as OQ-DES-CW29 | IP-WTM-9, IP-WTM-25 | [§6.4](../design/cowl_interior_surface.md#64-which-measure-reads-the-wall-and-what-it-says-the-wall-is) |
| IP-WTM-27 | done | Test whether tightening `TAU` yields a compliant wall and at what cost, by building one part at several `TAU` through `freecad/tau_study.py` | IP-WTM-24 | [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales) |
| IP-WTM-28 | done | Confirm the `TAU` result on a `tail_shell`, the kind that fails at every `U`, since the nose was already within a hair of tolerance before tightening; `U` = 0.5 is the cheapest tail build at 727 s. **This is the measurement OQ-DES-CW28 is waiting on** — it is a prerequisite of that question, not blocked by it. **Measured 2026-10-12 and it refutes the premise**: at `TAU` = 0.02 and 0.01 the build raises `Unconverged` against `cavity`'s 64-station patch budget (not `POST_CUT_ROUNDS`), after 3 827 s and 2 154 s, and pass 2's worst gap is **0.0601 mm at all three criteria** while pass 1's own prediction falls 0.0286 → 0.0122 → 0.0081 mm. On a tail `TAU` is not the lever. Also found: `TAU` and `WALL_TOL` are compared against two *different* measures, 2.81x apart on this wall, which is `locate.criterion_split` and `freecad/criterion_check.py` | IP-WTM-27 | [§6.8](../design/cowl_interior_surface.md#68-tightening-the-criterion-measured-not-argued), [§6.8.1](../design/cowl_interior_surface.md#681-tau-and-wall_tol-are-thresholds-on-two-different-measures), [cowl.md OQ-DES-CW28](../design/cowl.md#open-questions) |
| IP-WTM-29 | done | Test whether the tail’s diagonal buttresses are the mechanism, given the nose cell has none and is compliant at `U` ≤ 3 — measured through `freecad/rib_proximity.py`, and refuted: 10 of 12 thin spots sit more than 3`t` from any rib | IP-WTM-24 | [§6.7.1](../design/cowl_interior_surface.md#671-the-ribs-are-not-where-the-wall-is-thin) |
| IP-WTM-30 | done | Test the refined hypothesis that the diagonals matter through the **fit** rather than the cut, by comparing each thin spot’s magnitude against the local fit row spacing and patch length. **Refuted in its sign, 2026-10-13**: crowding predicts thinner wall where rows are *tighter*, and `locate.row_spacing_split` on a `tail_shell` `U` = 0.5 build (21 rows, intervals 0.99–10.00 mm) gives Spearman rho of **+0.556** incumbent and **+0.599** crease-excluded — thinner where rows are *further apart*, the same direction as the nose (§6.8.3). So the diagonals do not thin the wall by crowding rows. At n = 12 that rho is marginal; the stronger reading is that narrow intervals **bound** the error (every interval under 1.7 mm reads under 0.0031 mm) while wide ones do not determine it, which matches §6.8.3's saturation from the other side | IP-WTM-29 | [§6.7.1](../design/cowl_interior_surface.md#671-the-ribs-are-not-where-the-wall-is-thin), [§6.8.3](../design/cowl_interior_surface.md#683-the-noses-u-trend-is-the-axial-seed-being-a-count-and-it-has-a-floor-underneath) |
| IP-WTM-31 | done | Remove `cowl_interior.hausdorff`, dead since `_refine`’s criterion became the in-plane wall width — no callers in `src/` or `tests/`. **§5 still specified it as the criterion** and is corrected to state what the code applies, with §6.7’s stage table and §9.4 brought into line | — | [§5](../design/cowl_interior_surface.md#5-the-refinement-criterion) |
| IP-WTM-32 | done | Correct the stale claim that notch edges are patch boundaries, in `feature_stations`’ and `EDGE_SCAN_MARGIN`’s notes and in §4.1, §4.3 and §6.7.1 — under §4.2’s three-dimensional identity they are interpolation rows, and every build reports `patch 1/1` | — | [§4.1](../design/cowl_interior_surface.md#41-stations), [§4.2](../design/cowl_interior_surface.md#42-eroding-a-section) |
| IP-WTM-33 | done | Check that the rib cut’s own boundary edges lie on both surfaces they are the intersection of — `wall_measure/boolean_edges.py` plus the `freecad/rib_edge_check.py` driver, since `cavity` checks only the residue volume and the solid count after the cut | — | [§4.2](../design/cowl_interior_surface.md#42-eroding-a-section), [§6.9](../design/cowl_interior_surface.md#69-the-shape-of-the-rib-edges) |
| IP-WTM-37 | done | Check that the rib cut returns the surface it was *given*, not only an edge in the right place — `boolean_edges.surface_identity` on the control nets, `patch_deviation` over the patch interior banded by distance to a rib edge, and `face_normal`/`crease_angles` for the first-order test and the tangency reading | IP-WTM-33 | [§6.9](../design/cowl_interior_surface.md#69-the-shape-of-the-rib-edges) |
| IP-WTM-34 | done | Run `rib_edge_check.py` across `U` on both kinds — chiefly to see whether the **minimum crease angle** collapses toward 0 near `U` = 0.75, where `Diag12Safe`'s sliver occurred, which would make it a predictor of that degeneracy rather than a description of it; also whether the over-fuzz sample count and the worst departure are flat in `U`. **Refuted with the sign reversed, 2026-10-13**: the tail's minimum crease angle *rises* monotonically — **18.258° at `U` = 0.5, 35.478° at 0.75, 43.078° at 1.0** — so it is nearly twice as far from tangency at the degenerate configuration as at a sound one, and is anti-correlated with the failure rather than predictive of it. Neither other quantity is flat: over-fuzz grows on the tail (37 → 56 → 90) and stays 0 on the nose, while the worst departure *falls* (2.972e-04 → 1.935e-04 → 1.431e-04 mm). **And `tail_shell` at `U` = 0.75 now builds cleanly** — one valid solid, `rib_residue` 0.0, no anomalous edge group — which measures the claim that retired the `MIN_U` = 0.8 floor | IP-WTM-37 | [§6.9](../design/cowl_interior_surface.md#69-the-shape-of-the-rib-edges) |
| IP-WTM-35 | done | Identify the tail’s one edge group not shared by exactly two faces — a periodic seam and a degenerate edge both look like this, and the nose has none. **It is neither: a genuine open boundary**, 1.05867 mm, one face, a non-periodic `SurfaceOfExtrusion`, with the kernel’s own adjacency agreeing and a pole, a keying artifact and a stray face all excluded. `Shape.isValid()` passes it, so the construction’s `valid=True` is not a closed-shell test; the finished walls are clean (0 such groups on all twelve). What the construction should refuse is OQ-DES-CW30 | IP-WTM-33 | [§6.9.1](../design/cowl_interior_surface.md#691-the-tails-one-odd-edge-group-and-a-proxy-caught-overruling-the-kernel), [cowl.md OQ-DES-CW30](../design/cowl.md#open-questions) |
| IP-WTM-36 | done | Chase the nose’s `U`-linear thinning, now that the two kinds are known to scale differently and the nose is forty times cheaper to build than the tail. **Found, 2026-10-13, via `freecad/seed_density.py`**: `_seed` takes a fixed **count** (`SEED_MAX` = 6 for any patch over 3 mm), so a nose patch of 22 mm and one of 176 mm get the same 10–11 stations and the axial spacing grows 2.44 → 17.60 mm; the finished wall's error tracks that spacing to within ±13 % across an eightfold `U` range. `FIT_ARC`/`CHECK_ARC` are excluded — both already spacings, so they saturate at `U` = 3 while the thinning does not. **The converse confirms cause and bounds the fix**: at fixed `U` = 4, `SEED_MAX` = 12 takes the wall 0.01530 → 0.00733 mm, *passing* `WALL_TOL`, at no measurable build cost; 24 gives 0.00710, so it saturates at a **0.0071 mm floor** that seeding does not reach. What to do is OQ-DES-CW31; the floor stays with IP-WTM-26 | IP-WTM-21 | [§6.8.3](../design/cowl_interior_surface.md#683-the-noses-u-trend-is-the-axial-seed-being-a-count-and-it-has-a-floor-underneath), [cowl.md OQ-DES-CW31](../design/cowl.md#open-questions) |
| IP-WTM-40 | done | Close OQ-DES-CW26 alternative 1's axial-sampling bound with a dense ring scan on the saved walls — `locate.state_profile`/`nearby_states` plus `freecad/ring_scan.py`, no build. **All twelve distinct walls, both kinds across `U` = 0.5 to 4.0, at 1 mm axially: 1 704 stations, 1 703 healthy annuli, 0 severed, 0 confirmed gaps**, in 3 h 4 min. The one `no_wall` is the `U` = 3.0 slice artifact, reproduced to the last digit on a second scan hours later | IP-WTM-20 | [cowl.md OQ-DES-CW26](../design/cowl.md#open-questions), [§6.1](../design/cowl_interior_surface.md#61-measurement-cautions) |
| IP-WTM-39 | blocked (OQ-DES-CW28) | Adopt the decided interior-fit convergence criterion in `cowl_interior.TAU`, and expose it as a `Tau` property plus a parameter-sheet column if that alternative is chosen — the sheet column being a separate item from the generator change that reads it | IP-WTM-28 | [§6.8](../design/cowl_interior_surface.md#68-tightening-the-criterion-measured-not-argued), [cowl.md OQ-DES-CW28](../design/cowl.md#open-questions) |
| IP-WTM-41 | done | Extend the dense ring scan past the `U` axis, which is the bound IP-WTM-40 leaves: its 1 704 stations cover twelve walls that vary in `U` **alone**, every other design input at the parameter sheet's values. The 21-case free-parameter screen tested construction *validity* (`isValid()`) on the **round-0** construction and saved nothing, so the walls had to be built — `wall_measure/inputs.py` (the case list, the override arithmetic and the vacuity guard), `freecad/input_screen.py` (a process a case), `corpus.screen` (a second corpus, kept apart from the soak's) and `ring_scan.py --family=screen`. **Measured 2026-10-14, 6 h 56 min of machine time (the tail alone is 6 h 16 min): 42 cases, 36 built, 6 refused, 36 scanned, 1 638 stations at 1 mm, 0 severed, 0 confirmed gaps, 0 kernel disagreements** — `nose_cowl_shell` at `U` = 1.0 (18 cases, 630 stations) and `tail_shell` at `U` = 0.5 (24 cases, 1 008 stations), reported as two populations rather than one. **0 unmoved**, so the coverage is real. The baseline is a control and it passes exactly: the nose's `wall_hash` equals all five 2026-10-06 soak repeats'. The six refusals are one cause, `RIB_FACETS` = 48, which is OQ-DES-CW32 and IP-WTM-47 | IP-WTM-40 | [cowl.md OQ-DES-CW26](../design/cowl.md#open-questions), [cowl.md OQ-DES-CW32](../design/cowl.md#open-questions), [§6.2](../design/cowl_interior_surface.md#62-conditioning-the-row-nudge-probe-and-what-it-can-establish) |
| IP-WTM-42 | blocked (OQ-DES-CW29) | Make the decided wall-thickness measure the one that gates `check_cowl_interior`, leaving the other printed beside it — a one-line change once the question is answered, and deliberately not taken with it open, since the two disagree about whether a `nose_cowl_shell` complies | IP-WTM-10 | [§6.4](../design/cowl_interior_surface.md#64-which-measure-reads-the-wall-and-what-it-says-the-wall-is), [cowl.md OQ-DES-CW29](../design/cowl.md#open-questions) |
| IP-WTM-43 | blocked (OQ-DES-CW30) | Add the decided shell-closedness check — reported at `cavity`, asserted on the finished wall, or both — through `boolean_edges.anomalous_edges`, which already answers it on a saved wall | IP-WTM-35 | [§6.1](../design/cowl_interior_surface.md#61-measurement-cautions), [cowl.md OQ-DES-CW30](../design/cowl.md#open-questions) |
| IP-WTM-44 | done | Re-run the `TAU` study on a tail at `U` = 2.0 or 3.0, where pass 2's measure and the gate's agree closely rather than the 2.81x they differ by at `U` = 0.5, since IP-WTM-28's refusal was not separated from that mismatch. **Premise checked and held** (`criterion_check` on the saved `U` = 2.0 wall: pass 2 0.03801 against the selected measure's 0.03449, **1.10x**, reproducing the published 1.06x), then measured: **both tightened values raise `Unconverged` at `U` = 2.0 too**, same 64-station patch budget, after 5 656 s and 1 799 s, with pass 2's round-1 gap flat at 0.0481 mm against 0.0508 at `TAU` = 0.05. So IP-WTM-28's conclusion is not an artifact of a cheap configuration. **New and sharper:** pass 1 converges to **0.0073 mm**, inside `WALL_TOL`, and the finished wall is unmoved — because the two passes measure out to different exteriors by necessity (`outer_at` the un-notched OML, `finished_outer_at` the notched one, recorded as 26.5 mm apart at one station), which hands IP-WTM-26 a starting point | IP-WTM-28 | [§6.8](../design/cowl_interior_surface.md#68-tightening-the-criterion-measured-not-argued), [§6.8.1](../design/cowl_interior_surface.md#681-tau-and-wall_tol-are-thresholds-on-two-different-measures), [cowl.md OQ-DES-CW28](../design/cowl.md#open-questions) |
| IP-WTM-46 | blocked (OQ-DES-CW31) | Adopt the decided axial seed in `cowl_interior._seed` — a larger `SEED_MAX`, or a `SEED_ARC` spacing with its own clamp — and re-measure the corpus, since every recorded wall figure in this plan is taken at the current seeding | IP-WTM-36 | [§6.8.3](../design/cowl_interior_surface.md#683-the-noses-u-trend-is-the-axial-seed-being-a-count-and-it-has-a-floor-underneath), [cowl.md OQ-DES-CW31](../design/cowl.md#open-questions) |
| IP-WTM-45 | done | Settle whether pass 2's large notch-referenced readings are a thin wall or an in-plane measurement artifact at a notch junction. **Needed no build**: a saved wall's outer loop *is* the notched exterior, so `candidates.outer_corner_excluded_min` (new) asks it from a file — the incumbent minimum with samples whose nearest point on the **outer** contour sits at a crease dropped, which is a different exclusion from `corner_excluded_min`'s inner concave turns. **Measured on `tail_shell` `U` = 0.5, 214 s: 546 creases found, 2 852 samples dropped, and the worst reading falls 0.03663 → 0.01345 mm, a 63 % reduction.** The two exclusions agree to 1e-5 mm at 7 of 12 stations, nowhere differ by more than 0.00065, and agree exactly on the worst figure and its station — they are excluding the same samples, which are at notch junctions. Does **not** prove material is present: both measures are in-plane | IP-WTM-44 | [§6.8.2.1](../design/cowl_interior_surface.md#6821-two-independent-exclusions-converge-on-the-same-wall-ip-wtm-45), [cowl.md OQ-DES-CW29](../design/cowl.md#open-questions) |
| IP-WTM-26 | done | Find the mechanism behind the 0.028–0.048 mm thinning that survives correct sampling, given that smooth-arc chord sag is 400x too small and local curvature is uncorrelated (anti-correlated at `U` ≥ 3). **IP-WTM-28 puts this on the critical path and narrows it**: station insertion is not a lever on the residual — pass 2's worst gap is unchanged across a fivefold range of `TAU`, and 77 of its over-tolerance stations sit at the 0.400 mm subdivision floor where it cannot split further — so the mechanism has to be removed rather than converged away. **IP-WTM-44 narrowed it and the converse has now been measured (§6.8.2), which splits this item in two.** On a `nose_cowl_shell` at `U` = 4.0 the reference surface explains **nothing** — 0 of 20 over-tolerance stations, the two worst readings agreeing to 0.00003 mm — and its thin stations are a **10 mm band**, `z` = -104.9 to -115.0. On a `tail_shell` at `U` = 0.5 it explains 106 of 114, leaving **8 stations at 0.0103–0.0185 mm** against the OML in three short clusters. So the remaining target is not "the 0.028–0.048 mm thinning" but **two separate residuals with different causes**. **What four measurements have since removed from it:** the reference surface accounts for 106 of the tail's 114 over-tolerance stations and none of the nose's (§6.8.2); of what remains on the tail, 63 % is read at a notch junction and both independent exclusions put the real worst at **0.01345 mm** (§6.8.2.1, IP-WTM-45); axial row spacing bounds the error on both kinds and tightening it helps until a floor (§6.8.3, IP-WTM-36); and the diagonals do **not** act by crowding rows, which is refuted in its sign (IP-WTM-30). **The nose half is now closed, 2026-10-14**: the "floor" at 0.0071 mm was `TAU` — `_refine` stops at the first subdivision inside it, and the `SEED_MAX` = 24 run is that caught in the act, 26 seeded stations becoming 26 with pass 1 pinned at 0.04991 just under 0.05. At any `TAU` ≤ 0.02 the `U` = 4 nose reaches **0.00268 mm**, which *is* a floor: `TAU` = 0.02, 0.01 and 0.004 all land on it with 28, 28 and 63 stations, and `TAU` = 0.002 raises `Unconverged` against the same 64-station budget that stops the tails. Two further refutations came with it — the circumferential fit resolution is uninvolved (a 6.4x range of `FIT_ARC` moves the wall 4.7e-6 mm, including the coarse direction), and the finished-wall figure is nearly converged at `CHECK_ARC` = 0.2, which adds 1.9 % against 0.05 (§6.8.3). **The tail half is now closed too, 2026-10-15, with the 3-D normal-distance measure §6.8.2.1 called for and said did not exist** — `wall_measure/normal_distance.py` plus `freecad/normal_check.py`, verified against `truth`'s closed-form fixtures (0.6 mm on a uniform tube, 0.45 in an outer patch, 1.0 mm on an inner rib) before being pointed at the question. Measured on four saved walls: the under-tolerance readings split into two populations with **opposite** biases. Those on planar rib-slot cheeks run across a slot mouth at 15–73° to the surface's own normal, read 0.68–3.0 mm along their normals and **none is confirmed thin** — the incumbent's worst tail figure, 0.56337, is one of these. Those on the fitted interior surface are the only readings that are wall thicknesses, and **66 of them across three walls are every one confirmed thin and thinner than the plane said, none exonerated**: worst deficits **0.0943 mm (tail `U` = 0.5), 0.0790 (nose `U` = 4.0), 0.0645 (tail `U` = 1.0) — six to nine times `WALL_TOL`** — against in-plane figures of 0.0135, 0.0140 and 0.0226 at the same samples. The surface is inclined 21.5–30.8° and `normal / cos θ` reproduces every in-plane figure to 0.0037 mm; independently, the in-plane column reproduces IP-WTM-45's 0.01345 and OQ-DES-CW28's 0.01403. **Not localized**: on the tail at `U` = 1.0, 1 954 of one station's 4 267 samples are thin on the fitted surface, 46 % of the circumference. Invisible to every in-plane measure including both of OQ-DES-CW29's candidates. That is OQ-DES-CW33 | IP-WTM-24, IP-WTM-45 | [§6.8.2.2](../design/cowl_interior_surface.md#6822-the-wall-measured-perpendicular-to-itself-and-the-two-populations-it-separates), [cowl.md OQ-DES-CW33](../design/cowl.md#open-questions), [§6.6](../design/cowl_interior_surface.md#66-sampling-density-a-fixed-sample-count-on-a-part-that-scales), [§6.8](../design/cowl_interior_surface.md#68-tightening-the-criterion-measured-not-argued), [§6.8.2](../design/cowl_interior_surface.md#682-the-two-exteriors-measured-against-each-other-and-what-survives-the-swap) |
| IP-WTM-38 | done | Extend the same surface-identity check to the steps *after* `cavity` — `_extend_across_cell`, `notched.cut(inside)`, `_strip_seam` and `mirror_across_cell` each carry their own boolean and `removeSplitter`, and none is covered by IP-WTM-37. **The mirror step is done, 2026-10-12, and needed no build**: `boolean_edges.congruent_identity`/`mirror_families` plus `freecad/wall_surface_check.py` over all twelve saved walls — **780 mirrored copies of a fitted patch, every one congruent**, worst internal step mismatch 8.5e-14 mm on a nose and exactly 0 on every tail, and no wall's test was vacuous. **The three pre-mirror booleans are now done too, 2026-10-13**, through an opt-in `stages` list on `shell_solid` and `boolean_edges.stage_identity`: on a `tail_shell` at `U` = 0.5 and a `nose_cowl_shell` at `U` = 1.0, **every transition carries the fitted surface through at exactly 0.000e+00 with nothing lost** — 3 transitions on the tail, 6 on the nose. A finished wall could not have answered this: `congruent_identity` compares mirrored copies against each other, so a refit applied *before* the mirror leaves every copy equally refit and passes | IP-WTM-37 | [§6.9](../design/cowl_interior_surface.md#69-the-shape-of-the-rib-edges), [§6.9.2](../design/cowl_interior_surface.md#692-the-three-booleans-after-cavity-and-a-test-applied-to-the-wrong-step) |
| IP-WTM-48 | blocked (OQ-DES-CW33) | Adopt the decided treatment of the in-plane measures' inclination bias in `check_cowl_interior` — a face-class filter ahead of a 3-D pass, the documented bias alone, or a bounded sample reported as a bound — through `wall_measure/normal_distance.py`, which already measures it and is verified against closed form. **The prerequisite CW33's alternative 2 named is done, 2026-10-16, and it refutes that alternative**: in-plane severity ranks the readings that are wall thicknesses *last* on every wall that has any (ranks 38–52 of 55, 48–58 of 62, 14–35 of 36, 12–87 of 88, 19–2 016 of 2 017), because an artifact is wrong by a slot width and a real reading only by the inclination factor, so a worst-`N` pass selects against the defect by construction — at `N` = 12 the first run re-measured 111 samples and found none of the 24 that mattered (§6.8.2.3) | IP-WTM-26 | [§6.8.2.2](../design/cowl_interior_surface.md#6822-the-wall-measured-perpendicular-to-itself-and-the-two-populations-it-separates), [§6.8.2.3](../design/cowl_interior_surface.md#6823-in-plane-severity-is-an-inverted-selector-measured), [cowl.md OQ-DES-CW33](../design/cowl.md#open-questions) |
| IP-WTM-47 | blocked (OQ-DES-CW32) | Adopt the decided rib-dilation facet count in `cowl_interior.RIB_FACETS` — derived per tool from its own in-plane thickness and `t`, or raised to one larger fixed value — and re-run the three design-input cases it currently refuses, which are the holes IP-WTM-41's screen cannot fill. Separately, hoist the precondition above pass 1 if that part is accepted, since a refused configuration currently pays for a full interior fit first: 38–40 s on a nose and about 700 s on a tail | IP-WTM-41 | [cowl.md OQ-DES-CW32](../design/cowl.md#open-questions), [§4.2](../design/cowl_interior_surface.md#42-eroding-a-section) |
| IP-WTM-49 | todo | Find why the fitted interior surface is inclined 21.5–30.8° to the layer plane exactly where the wall is thin, which is the one quantity in [§6.8.2.2](../design/cowl_interior_surface.md#6822-the-wall-measured-perpendicular-to-itself-and-the-two-populations-it-separates) that is measured and unexplained. The obliquity is not incidental to the defect, it **is** the defect: the wall measured along its own normal is thinner than the in-plane figure by exactly `1 / cos θ`, so a surface that met the layer plane squarely would be compliant at the same in-plane reading. Three candidate mechanisms are already distinguishable from the saved walls and need no build — that the inclination is the cone angle of the OML itself (predicting it tracks `cone_angle` and appears on both kinds), that it is the dilated rib tool’s ramp where a shallow-angle notch meets the interior (predicting it concentrates near `feature_stations` and is absent on a nose cell with no diagonals), or that it is the fit relaxing between widely spaced axial rows (predicting it tracks the local row interval, which [§6.8.3](../design/cowl_interior_surface.md#683-the-noses-u-trend-is-the-axial-seed-being-a-count-and-it-has-a-floor-underneath) already measures as bounding the error). `normal_distance.station_normals` reports the angle per sample today, and `locate.row_spacing_split` and `rib_proximity` are the two correlates to split it against. **Not blocked by OQ-DES-CW33 and able to moot it:** CW33 asks what the gate should do about the bias, and a mechanism that removes the inclination removes the bias rather than measuring around it — the same relationship IP-WTM-26 has to OQ-DES-CW28 | IP-WTM-26 | [§6.8.2.2](../design/cowl_interior_surface.md#6822-the-wall-measured-perpendicular-to-itself-and-the-two-populations-it-separates), [§6.8.3](../design/cowl_interior_surface.md#683-the-noses-u-trend-is-the-axial-seed-being-a-count-and-it-has-a-floor-underneath), [§6.7.1](../design/cowl_interior_surface.md#671-the-ribs-are-not-where-the-wall-is-thin), [cowl.md OQ-DES-CW33](../design/cowl.md#open-questions) |

> **IP-WTM-42 blocked reason:** which measure gates is a judgment about what `WALL_TOL` means at a concave corner of a 0.6 mm wall, not a measurement — both measures are implemented, tested and run on real builds, and no further data separates them on accuracy. OQ-DES-CW29 is where it is filed. Switching the gate would turn a failing `nose_cowl_shell` into a passing one, which is the one change here that later evidence cannot undo, so it waits for the decision rather than for more evidence.

> **IP-WTM-48 blocked reason:** the measure exists and is verified and its one measurable prerequisite has been run, so nothing here is waiting on evidence about the wall — it is waiting on what the gate should do about a bias whose sign, magnitude and consequence are all now measured. What is left is a genuine trade with no cheap option: documenting the bias is free and changes no verdict but leaves a 0.065–0.094 mm defect invisible; filtering by face class selects correctly and is nearly free on three of four walls but leaves 2 018 samples and about 67 minutes on the `tail_shell` at `U` = 1.0, where the defect is worst; and measuring a bounded sample reports a bound rather than a worst, which is weaker but honest. OQ-DES-CW33 is that choice, and it should be made deliberately rather than by letting a sample count decide it silently.

> **IP-WTM-47 blocked reason:** the arithmetic is already written — it is the expression inside the `PreconditionFailed` message that refuses the build — but which form to adopt decides what every build pays for. `RIB_FACETS` drives the dilation boolean directly, measured at 4.0 s a tool at 48, 8.6 s at 64 and 23.6 s at 96, and a tail has eleven tools; deriving the count makes build time a function of the design inputs, while raising it to one fixed value makes every build pay for a configuration nobody is using. OQ-DES-CW32 is that choice, and it also holds the separate question of whether the check should move above the interior fit. Writing either form now would be making the decision by implementing it.

> **IP-WTM-46 blocked reason:** the change is one constant or one small function, but it alters every build of both kinds, so it supersedes every wall figure this plan has recorded and needs the corpus re-measured behind it. Which form to adopt is a trade between build time and accuracy — `SEED_MAX`'s own note prices generous seeding at 23 minutes a part on a tail with 60 patches — and the tail price of a spacing is unmeasured. OQ-DES-CW31 is that decision. Implementing one form now would be making it by writing it.

> **IP-WTM-43 blocked reason:** the check itself is a few lines, but *where* it runs decides whether it rejects builds that currently produce sound parts: asserted at `cavity` it fails every `tail_shell` today, asserted on the finished wall it passes all twelve corpus walls. OQ-DES-CW30 is that choice. Implementing one placement now would be making the decision by writing it.

> **IP-WTM-39 blocked reason:** what `TAU` should be is a trade between build time and compliance, not a measurement, and OQ-DES-CW28 is where it is filed. Its blocking measurement, IP-WTM-28, has now reported, and it removed the two settings the item was written to adopt rather than choosing between them: `TAU` = 0.01 and `TAU` = 0.02 both raise `Unconverged` on the cheapest tail, so there is no value to go and set. What remains for the question is a choice among accepting the wall as built, an adaptive criterion, raising the refiner's own limits, and removing the residual's mechanism (IP-WTM-26, IP-WTM-36) — and the last of those would make the whole question moot. A further reason not to pick a number yet: `TAU` and `WALL_TOL` are compared against two different measures, 2.81x apart on the measured wall, so any numeric relationship between them means something different depending on how OQ-DES-CW29 is answered.

> **IP-WTM-10's former blocked reason, kept because it is why the order was this way round:** adopting a second measure in the acceptance gate was not worth doing while the gate discretized each section at a fixed `AROUND` = 240 samples, 8.7 mm apart on a `tail_shell` at `U` = 4 against a 0.6 mm wall. Both measures would have inherited that error, and the figures printed beside each other would have differed by less than either differed from the truth. IP-WTM-25 has now replaced the count with an arc-length spacing, so the item is unblocked.

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
wall was a measurement rather than a design choice, and `freecad/tau_study.py` took it by building
one part at several `TAU` and reading the resulting wall, the fit rows and the rounds spent. Three
answers were possible and the rig preferred none: the wall thins in proportion; the build raises
`Unconverged` against `POST_CUT_ROUNDS` = 6; or the wall does not move at all.

**The two kinds answered differently, which is why this took two items.** IP-WTM-27 measured the
nose: compliant at `TAU` = 0.02 for 14 % more build time, neither tightening raising `Unconverged`.
IP-WTM-28 measured the tail, and got the second and third answers at once — the wall does not move
(pass 2's worst gap is 0.0601 mm at all three criteria) and the build then refuses to converge, at
the 64-station patch budget rather than the round budget. On a tail `TAU` is not the lever, so the
"finding is about `TAU`" framing above holds for the nose only.

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

### The gate's sampling, and both measures in it (IP-WTM-25, IP-WTM-10)

**The gate sampled by count, and the count was the last place this error lived.**
`check_cowl_interior.wall_thickness` discretized the inner contour at a fixed `AROUND` = 240 points
and the outer at eight times that, at every `U`. A cowl's perimeter grows roughly linearly with `U`
while its wall stays an absolute 0.6 mm, so that bought a spacing of 1.8 mm on a `tail_shell`
section at `U` = 1 and **8.7 mm at `U` = 4 — fourteen times the wall being measured**. It is now
`WALL_ARC` = **0.125 mm**, derived per station from that station's own perimeter: 2 164 to 14 238
samples where there were 240.

**0.125 mm is the measured figure.** `density.sweep_by_spacing` settles by 0.25 mm and moves
0.00008 mm per halving after it, two orders inside `WALL_TOL`; 0.125 mm is one halving past settled
and is the spacing the whole corpus was re-measured at, so a gate reading and a corpus reading are
comparable rather than merely both fine.

**The outer loop's eight-fold densification is retired, and the arithmetic is why.** It existed so
the outer polyline's chords would not cut inside the true boundary and make the wall read thin.
That error is `s^2 / (8R)`, which `wall_measure.density` measured at about 0.0005 mm for the 1.45 mm
spacing the published sweep used — so at 0.125 mm it is about **4e-6 mm**, four orders inside
`WALL_TOL`. Keeping the factor would also have cost what it no longer buys: at `U` = 4 it means a
14 238 x 113 904 distance matrix instead of 14 238 squared. And dropping it makes the gate sample
the way `sweep.measure_wall` does, one spacing for both loops, so a gate figure and a corpus figure
are not confounded by their discretization.

**What it moves.** Measured at the mid station of the saved walls:

| saved wall | old density | 0.125 mm | samples |
| --- | --- | --- | --- |
| `tail_shell` `U` = 4.0 | 0.4454 | **0.5675** | 1 440 → 14 238 |
| `tail_shell` `U` = 1.0 | 0.5722 | **0.5667** | 1 440 → 3 559 |
| `nose_cowl_shell` `U` = 4.0 | 0.5381 | **0.5787** | 1 440 → 12 429 |

At `U` = 4 the thinning the gate reports falls from 0.1546 to 0.0325 mm on the tail — the same
correction §6.6 measured on the corpus, now in the check that judges a build. **At `U` = 1 it moves
the other way**, by 0.0055 mm, and that direction matters: a coarse spacing both under-reports
thinness, by sampling the inner loop too sparsely to land on a thin spot, and over-reports it, by
measuring to outer chords. The synthetic tests hold both directions deliberately — a pocket on a
tube's outer face isolates the first (a coarse 2.5 mm spacing reads 0.0486 mm too *thick*, nearly
five times `WALL_TOL` of thinning simply not seen), while the real sections are dominated by the
second. A test that only ever saw one direction would license the wrong conclusion about the other.

**Both measures now run from one section (IP-WTM-10), and the reason to compute them together is an
identity rather than the cost.** `corner_excluded_min` minimizes over a *subset* of the incumbent's
distances — the samples not within 0.30 mm of a concave turn of the inner contour — so
`selected >= incumbent` is structural. Computing them from separate sections would both double the
slicing and destroy the identity, and a violation of it once revealed a real defect: an earlier
version of that measure resampled the loop first, making the two different point sets, and reported
0.04806 against 0.04689 mm on a real `tail_shell`. The gate checks the identity on every run and
prints `SUSPECT` if it ever fails, which is the only way a sampling mistake in either measure would
announce itself.

**The identity held at all 12 stations of a real nose build, and the two measures still disagreed
about the verdict** — 0.0376 mm and failing against 0.0031 mm and passing, the whole difference
accounted for by 100 to 230 excluded samples of about 3 000 per station. That is not a defect in
either; it says the incumbent's minimum on a nose sits at a concave corner at nearly every station,
which is where its own known failure lives. Which measure should gate is **OQ-DES-CW29** — a design
judgment about what the requirement means at a corner, not a measurement, and filed rather than
decided here. The incumbent continues to gate in the meantime, because changing a failing verdict to
a passing one is the one move that cannot be undone by later evidence.

**The synthetic geometry is two fixtures and the difference between them was found by a failing
test.** A pocket milled into a tube's *outer* face leaves the inner contour a plain circle, convex
everywhere — so `corner_excluded_min` excludes nothing, 2 516 of 2 516 samples kept, and any test of
the exclusion built on it is vacuous. The real sections' concave turns are on the *inner* contour,
because the wall follows each notch in and back out; `notched_tube` reproduces that and is what the
identity is tested on. Worth recording because the first version of that test asserted the exclusion
had happened and was wrong about where corners come from, not about the exclusion.

### The tail's odd edge group, and the proxy that nearly overruled the kernel (IP-WTM-35)

**Both hypotheses on record were wrong.** §6.9 listed a periodic seam and a degenerate edge as the
two things the tail's one non-two-faced group of 3 164 could be. `boolean_edges.anomalous_edges`
separates the four cases a one-face group can be, and on `tail_shell` at `U` = 0.5 it is neither:
one face carrying one edge **once**, **1.05867 mm** long, on a `SurfaceOfExtrusion` face — an
end-overrun wall, the class that is neither B-spline nor plane. A seam carries its edge twice; a
pole has zero length.

**Why a count left this undiagnosed from the day it was first observed.** `face_adjacency` records
a face index once per group, so a periodic surface's closing seam presents as a one-face group
*identically* to a genuinely open edge. Counting occurrences inside that one face is the only thing
that separates them, and the adjacency never did it.

**The reported answer then contradicted the kernel, and that is the part worth recording.** The same
shape reports `cavity: 1 solids, valid=True` on every build, and a closed valid solid cannot carry
an edge with one face. Both cannot be true, and the proxy is the more likely to be wrong because it
has a mechanism for exactly this failure: `_edge_key` includes `valueAt(0.5 * (First + Last))`,
which is a **parameter** and not a position, so two differently-parameterized representations of one
shared curve key apart and each half looks like an open boundary.

So the measurement was changed rather than the claim defended:

* `anomalous_edges` takes `Part` and puts every anomaly to `ancestorsOfType` — the kernel's own
  adjacency, which the keying is a proxy for — reclassifying as `keyed_apart` any edge the kernel
  says is shared normally. That is a defect in the instrument, reported as its own kind rather than
  folded into either verdict.
* `loose_faces` counts the faces belonging to no solid, because a stray face left beside a solid by
  a boolean has free edges by definition and would read as an open boundary with the solid
  perfectly closed.
* `edge_anomaly_verdict` marks an un-cross-checked row `unchecked` as well as serious. **An
  unchecked suspicion is neither a clean bill nor a confirmed defect**, and conflating those two is
  this subsystem's recurring error.

**The kernel-checked re-run settled it: the open boundary is real.** `ancestorsOfType` independently
reports **one** face for that edge, and 1 060 of 1 060 faces belong to a solid, so it is neither a
keying artifact nor a stray face. Every figure in the run reproduced the first one exactly, down to
the 2.972e-04 mm worst edge departure and the 37 over-fuzz samples.

**And the discriminator itself turned out to be unsound, which is the second error here.** The
classifier separated a seam from an open boundary by counting how many times the one adjacent face
carries the edge — twice for a seam — on the assumption that `Face.Edges` lists a seam once per
orientation. Put to the kernel, that is **false**: a cylinder's lateral face lists its seam exactly
once. So the count cannot carry the distinction, and neither can `ancestorsOfType`, which returns
distinct ancestors and answers "one face" either way. The sound discriminator is the surface's
**periodicity**, since a seam can exist nowhere else, and that is what the classification uses now.
The conclusion did not move — the face is non-periodic on either account — but it had been reached
by an argument that does not hold, and the assumption had only ever been checked against a fake that
supplied the edge twice by construction. `test_geometry_bridge_cowl_checks` now asks the kernel, and
§6.1 carries it as a caution.

**So `Shape.isValid()` passes a solid with an open shell.** That is the part with consequences past
this one edge: `cavity: valid=True` does not mean the cavity is closed, and closedness has to be
asked for separately. What to do about it is OQ-DES-CW30 — a decision rather than an item, because
adding the check would fail every `tail_shell` build today on configurations whose finished walls
are sound.

**And the finished part is clean either way.** All twelve saved walls have **zero** edge groups not
shared by exactly two faces — no seam, no pole, no open boundary, either kind, any `U` — so whatever
this is, it lives on `cavity`'s intermediate output and a later step resolves it. That is the
question that actually bears on a shipped cowl, and it is answered.

### The tail refuses the tighter criterion, and `TAU` was never the same measure as `WALL_TOL` (IP-WTM-28)

IP-WTM-27 measured `TAU` on a `nose_cowl_shell` and found a clean lever: compliant at 0.02, five
times the margin at 0.01, 14 % more build time. This item asked the same question of the kind that
actually fails. `tail_shell` at `U` = 0.5, one build for the cell shapes and one `shell_solid`
re-cut per criterion, 1 h 52 min in one process:

| `TAU` | pass 1 stations | pass 1's worst | pass 2's round-1 gap | outcome | real wall | over `WALL_TOL` | re-cut |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.05 | 19 | 0.0286 | 0.0601 | converged, 21 rows | 0.01346 | 3 of 12 | 711 s |
| 0.02 | 20 | 0.0122 | 0.0601 | `Unconverged` | — | — | 3 827 s |
| 0.01 | 23 | 0.0081 | 0.0601 | `Unconverged` | — | — | 2 154 s |

**The rig was written to be indifferent between three outcomes and it returned two of them at
once.** The wall does not improve — pass 2's first-round gap is 0.0601 mm at every criterion, to the
four decimals the log prints, while pass 1's own prediction falls 0.0286 → 0.0122 → 0.0081 mm — and
the build then refuses. **Neither refusal is the round budget**, which is what the item was written
expecting: `POST_CUT_ROUNDS` = 6 is never reached, and both stop against `cavity`'s `budget` = 64
stations in one patch (20 → 36 → 62 → 94 at 0.02, and 23 → 43 → 77 at 0.01).

Two mechanistic details make the negative result usable rather than merely discouraging. **The rows
a tighter criterion buys are in the wrong place**: `TAU` = 0.01's four extra rows land at
`z` = -34.9993, -23.7718, -8.3134 and -6.6258, in the sparse middle of the patch, while the stations
pass 2 reports over tolerance cluster at -16.3 to -12.0 and -3.1 to -1.9 where rows are already 0.7
to 1.6 mm apart. And **where pass 2 wants to split it increasingly cannot**: 77 over-tolerance
stations at `TAU` = 0.02 sit at the 0.400 mm subdivision floor, `2 · MIN_INTERVAL`, with gaps in the
same 0.020–0.055 mm band as the residual itself. Station insertion is not a lever on this residual,
which puts IP-WTM-26 on the critical path.

**A second finding, not anticipated by the item: the two thresholds are not on the same measure.**
`_finished_wall_gap` is a plain minimum with no corner exclusion at `CHECK_ARC` = 0.20 mm; the
published wall figure is `corner_excluded_min` at 0.125 mm. Those are OQ-DES-CW29's incumbent and
selected measures, and that question is open. `locate.criterion_split` plus
`freecad/criterion_check.py` attribute the difference on the saved `U` = 0.5 wall, 12 stations in
285 s: worst pass 2 **0.03763**, worst incumbent **0.03663**, worst selected **0.01345**, a factor
of 2.80, reproducing `tau_study`'s own figures to within 0.0003 mm from a different code path. The
**sampling term is small and signed both ways** (-0.0068 to +0.0086 mm) and the **corner term
carries all of it** (to 0.0326 mm, 0.019–0.033 at nine of twelve stations). So `TAU` = `WALL_TOL`
never asked for a 0.01 mm wall; it asked pass 2's measure to reach 0.01 mm.

**Two things this measurement should not be read as establishing.** `U` = 0.5 was chosen for being
the cheapest tail and turns out to be the corpus's extreme for that measure mismatch — 2.81x where
the other five tail configurations run 0.92x to 1.68x — so "`TAU` = 0.01 is unreachable on a tail"
is established there and not separated from the mismatch; that is IP-WTM-44. And the corner term's
size on a *convex synthetic* annulus is zero by construction, which was confirmed numerically while
writing the tests: the exclusion drops samples and never moves the minimum, because a step's own
height is charged against the arc-length margin and the reading on a narrow step's flat top is a
real perpendicular wall thickness. That is the same trap §6.4 already records for gate G2, met from
a new direction, and it is why the corner term is tested here for its arithmetic and its subset
guard and measured on a real wall for its magnitude.

**One published claim is withdrawn.** OQ-DES-CW29 and §5's "three convergences" subsection both
said that on the tail the two measures agree closely, so the tail's thin spot is not at a corner and
no corner-based fix reaches it. The exact agreement at `U` = 1.5 and 3.0 stands; the generalization does not. At `U` = 0.5 the
incumbent's worst station is **89 % corner term** while the selected measure's worst station has a
corner term of 0.0002 mm and is a genuine thin wall — the station §6.7.1 records as 6.7 mm from the
nearest rib. The two measures are not a pessimistic and an optimistic reading of one thin spot on
that wall; they are reporting two different places for two different reasons.

### The same refusal at a configuration that was not confounded (IP-WTM-44)

IP-WTM-28 left a hole it named itself: it ran at `U` = 0.5 because that is the cheapest tail, and
that configuration turned out to be the corpus's extreme for the measure mismatch, so asking pass 2
for 0.01 mm there was asking for about 0.0036 mm by the gate's measure. A refusal under that request
does not establish much.

**The premise was checked before the hours were spent, and it held.** `criterion_check` on the
*saved* `U` = 2.0 wall — no build, 12 stations in 492 s — reads pass 2 at 0.03801 against the
selected measure's 0.03449, **1.10x**, reproducing the published 1.06x under the instrument actually
in use. At `U` = 2.0 a `TAU` of 0.01 therefore asks for about 0.0091 mm by the gate's measure: a
hard but fair requirement. `U` = 2.0 was taken over `U` = 3.0 on cost, 1 864 s a build against
4 170 s.

**The construction refuses anyway**, and the 0.05 re-cut was skipped because `build_cell`'s own
recompute already runs the wall at the module default and the saved corpus wall supplies the
baseline:

| `TAU` | pass 1 stations | pass 1's own worst | pass 2's round-1 gap | outcome | stations when it stopped |
| --- | --- | --- | --- | --- | --- |
| 0.05 | 25 → 27 | 0.0497 | 0.0508 | converged, wall 0.0366 | 28 |
| 0.02 | 25 → 30 | 0.0169 | **0.0481** | `Unconverged`, 5 656 s | 30 → 57 → 106 |
| 0.01 | 25 → 40 | 0.0073 | **0.0481** | `Unconverged`, 1 799 s | 40 → 76 |

So IP-WTM-28's result is a property of the kind, not of the cheap configuration. Two details are
new. The station counts **diverge** rather than approach a ceiling (30 → 57 → 106), so there is no
visible budget to raise `budget` to — which is the evidence OQ-DES-CW28's alternative 7 was missing.
And at `TAU` = 0.02 the worst gap **rose** across a round that inserted 27 stations, 0.0481 to
0.0514 mm, though that comparison carries OQ-DES-CW22's caveat: rounds after the first re-scan only
windows around their own insertions, so the later figure is taken over a deliberately adverse
subset.

**The sharpest result is the pair of pass-1 numbers.** Pass 1 converges to **0.0073 mm**, inside
`WALL_TOL`, and the finished wall it hands over still reads 0.0481. The fit can be made to meet the
part's own tolerance and it changes the finished wall by nothing measurable.

**And the reason is structural rather than a defect, which `cavity` half-documents already.** The
two passes measure out to different exteriors by necessity: `outer_at` is `body`'s **un-notched
OML**, because no cut exists when the surface is fitted, and `finished_outer_at` is `notched`'s real
exterior — whose own note records the two diverging by **26.5 mm** at one real thin station's worst
point. Pass 1 converges the OML-referenced wall; pass 2, the gate's incumbent and the gate's
selected measure are all referenced to the notched exterior. Tightening `TAU` tightens a quantity
the part is not held to. That is a third sense in which two figures here are not one measurement,
after the sampling and corner terms of §6.8.1, and the deepest: a different *reference surface*
rather than a different instrument on one surface.

**What it does not establish, stated because the lead is attractive enough to be dangerous.** It
does not say what makes the notch-referenced wall thin: the notch tools are dilated by exactly `t`,
so the wall against a notch face should be `t` by construction to within the dilation's 0.00128 mm
faceting (§6.7.1). And the converse is untested — whether pass 2's gap is absent at stations with no
notch within reach. That needs the notch tools in hand, so it needs a build, and it belongs to
IP-WTM-26.

### The converse, measured: the two exteriors against each other (IP-WTM-26, in part)

IP-WTM-44 left a lead strong enough to be dangerous: pass 1 converges to 0.0073 mm against the
un-notched OML while the finished wall, referenced to the notched exterior, stays at 0.0481 mm. The
weak form of that claim is trivially true — two reference surfaces give two numbers — so the test
had to be the **converse**: at a station where the two exteriors coincide there is no notch within
reach, so a station thin against *both* is one no reference surface explains.

`cavity` gained an opt-in `exterior_split` list; round 0 of the post-cut loop appends
`(z, gap_to_notched, gap_to_oml)` using **the same `_finished_wall_gap` call with the exterior
swapped**, inside `cavity` where both closures live. Nothing is rebuilt: rebuilding an operand is
how `projectPoint`, `toShape`, face vertices and facet centroids each gave a plausible wrong number
earlier in this subsystem. Round 0 only, because it is the one round that scans every patch in full.
`locate.exterior_verdict` buckets the stations; `freecad/exterior_split.py` drives it.

| build | stations | coincident | explained | **thin against both** | worst to notched | worst to OML |
| --- | --- | --- | --- | --- | --- | --- |
| `nose_cowl_shell` `U` = 4.0 | 195 | 32 | **0** | **20** | 0.01530 | 0.01528 |
| `tail_shell` `U` = 0.5 | 142 | 5 | **106** | **8** | 0.06005 | 0.01848 |

**The two kinds answer differently, which is the finding.** On the nose the reference surface
explains nothing — the two worst readings agree to 0.00003 mm, so where its wall is thin the two
exteriors are one surface — and its thin stations are a 10 mm band, not a spread. On the tail it
explains 106 of 114, and at those stations the OML-referenced wall is 0.00065 to 0.00402 mm against
0.044 to 0.060 notch-referenced, a factor of 15 to 90. Eight tail stations survive the swap at
0.0103 to 0.0185 mm.

**The decisive station is pass 2's own worst.** At `z` = -15.27863 the notch-referenced reading is
0.06005 mm — the figure invariant in `TAU` that refuses the build at 0.02 and 0.01 — and the
OML-referenced reading there is **0.00175 mm**. The fit is near-exact exactly where pass 2 will not
converge, which is why `TAU` has no purchase on it.

**Whether that 0.0601 is a thin wall or an in-plane artifact is deliberately left open, as
IP-WTM-45.** `dilate(B, t)` rounds a notch tool's convex edges to radius `t`, so where a notch
emerges through the OML the cavity boundary lies `t` from a three-dimensional edge, and an in-plane
nearest-point distance from such a sample can read shorter than `t` with no material missing.
`_finished_wall_gap` applies no corner exclusion. Three figures on one wall fit that: 0.0601
notch-referenced, 0.0185 OML-referenced, 0.01345 corner-excluded at the gate — the two corner-free
ones agree within 0.005 mm while the corner-inclusive one is three to four times either. Attractive,
untested, cheap to test.

**One defect in the instrument, caught by running it.** The first run was `nose_cowl_shell` at
`U` = 1.0, and it returned 63 stations whose worst reading was **0.0037 mm** against a 0.01 mm
tolerance. A compliant build. With no station over tolerance, `explained` and `unexplained`
were both empty and `exterior_verdict` reported **CLEAN** — a pass from a specimen that cannot test
an explanation of non-compliance. `clean` now requires a thin station to exist as well as a
coincident one, the two vacuity reasons are reported separately, and both have tests. That is the
**seventh** instance of this subsystem cross-checking two measures of an effectively empty input
(§6.1), and the first run of a new instrument found it, which is the argument for running a new
instrument on a known-healthy specimen first.

### Two exclusions, built on different criteria, leaving the same wall (IP-WTM-45)

§6.8.2 narrowed pass 2's unexplained 0.0601 mm to a single question: thin wall, or in-plane distance
taken across the crease where a notch face meets the OML? `candidates.outer_corner_excluded_min`
answers it, and **it needed no build** — a saved wall's outer loop already *is* the notched
exterior, so the question that looked like it needed `notched` in hand could be asked from a file.

The measure drops inner samples whose nearest point on the **outer** contour lies within 0.30 mm of
a crease. Implementing it needed `_segment_nearest`, which adds the nearest-segment index to
`_segment_distances`' existing arithmetic and is tested against it so two implementations of one
calculation cannot drift.

On `tail_shell` `U` = 0.5, 12 stations, 214 s: **546 creases found, 2 852 samples dropped, worst
reading 0.03663 → 0.01345 mm, a 63 % reduction.** The counts matter as much as the figure, because
the exclusion only fires where the exterior turns sharply enough to register — measured on a
synthetic notch, an 8-degree span yields no crease while a 2-degree span yields three — so a reading
that had not moved would have been ambiguous rather than a refutation.

**The strong part is the convergence.** Against `criterion_split`'s selected measure on the same
wall and the same stations:

| | worst | station |
| --- | --- | --- |
| incumbent | 0.03663 | `z` = -31.545 |
| inner concave turns excluded (the selected measure) | 0.01345 | `z` = -5.364 |
| outer creases excluded (new) | 0.01345 | `z` = -5.364 |

The two agree to 1e-5 mm at **7 of 12** stations, differ nowhere by more than 0.00065 mm, and agree
exactly on the worst figure and the station it sits at. One keys on the inner contour and never
looks at the exterior; the other keys on the exterior and never looks at the inner contour. They are
excluding the same samples, because at a notch the inner contour turns concavely and the exterior
carries the junction crease in the same place.

That retires a specific doubt in OQ-DES-CW29 rather than the whole question: the selected measure's
0.30 mm margin was screened rather than derived, and the worry was that it discards the places a
wall is genuinely thinnest. On this wall what it discards is reached independently from the other
side.

**Two limits, stated because the result is tempting.** Neither measure proves material is present —
both are in-plane, the surfaces at a junction are inclined to the layer plane, and a 3-D normal
distance would be needed to settle it; none exists in this subsystem. And this is one wall. What it
does establish is that **pass 2's criterion is compared against a figure that is 63 % junction
artifact here**, which is why `TAU` has no purchase on it and why the station that blocks
convergence is one where the fit is accurate to 0.00175 mm.

**One fixture error, caught by its own test.** The first version of the unit tests used a square
outer contour with a circular inner loop, on the reasoning that a square has four unambiguous
creases. It does — but a square's corners are the *farthest* part of it from anything inside, so no
sample's nearest exterior point is ever a corner, nothing was dropped, and the assertion failed.
A crease can only be excluded where it is **nearest**, which means a notch cut inward. That is the
third fixture in this plan built on an assumption about the geometry rather than on the geometry
(after concentric circles for gate G2, and a pocket on the outer face for IP-WTM-10's exclusion),
and the first to be caught by the test rather than by a reviewer.

### The last three booleans, and a test pointed at the wrong step (IP-WTM-38)

The mirror half was done from saved walls. The three remaining — `_extend_across_cell`,
`notched.cut(inside)`, and `_strip_seam` inside the first `mirror_across_cell` — could not be,
and the reason is worth keeping: `congruent_identity` compares a finished wall's mirrored copies
against *one another*, so a refit applied before the mirror leaves every copy equally refit, every
copy congruent, and the check passing. `shell_solid` gained an opt-in `stages` list and
`boolean_edges.stage_identity` compares consecutive stages, matched by `parameterization_key`
rather than face index.

| build | transitions | worst | lost | verdict |
| --- | --- | --- | --- | --- |
| `tail_shell` `U` = 0.5 | 3 | 0.000e+00 mm | 0 | clean |
| `nose_cowl_shell` `U` = 1.0 | 6 | 0.000e+00 mm | 0 | clean |

**Nothing in the construction after `_fit` moves a pole**, on either kind. With §6.9's rib-cut
result that closes the whole question: no boundary-value error can enter the patch at any step
between the fit and the finished wall.

**The instrument's first run reported a refit that was not one.** On the nose — three mirror steps —
the two mirror-to-mirror transitions came back at a worst pole displacement of exactly
**1.000e+02 mm**, which is a reflection distance, not a refit. After a mirror the shape carries the
original and its image under the same parameterization key, so matching by key and comparing poles
compared a copy against its own reflection. `congruent_identity` exists for exactly that and its
docstring says so; the error was applying the *identity* test to the one step already known to need
the *congruence* test — a warning written into `wall_surface_check.py` by hand and then violated
three functions later. `ISOMETRY_STAGES` now names the rigid steps, each row carries which test was
applied, and the converse is pinned too: a bodily translation by a step meant only to trim must
still fail.

**The tail did not show the fault and the nose did**, because the tail mirrors once — a single
mirror transition, whose surface ordering happened to match. Running both kinds is what exposed it,
the same lesson the two-exterior measurement produced from the other direction.

### The crease angle is not a predictor, and the sign is the reason (IP-WTM-34)

§6.9 found the tail's rib cuts three times closer to tangency than the nose's — minimum crease angle
18.258° against 54.731° — and proposed the sharp form of this item: **if that angle collapses toward
0 near `U` = 0.75, where `Diag12Safe`'s zero-volume sliver occurred, it predicts the degeneracy
rather than describing it**, and `RIB_CUT_FUZZ` would have something to be checked against instead
of only hand-tuned.

Three `U` on each kind, four new builds (`U` = 0.5 was already recorded):

| | nose 0.5 | nose 0.75 | nose 1.0 | tail 0.5 | tail 0.75 | tail 1.0 |
| --- | --- | --- | --- | --- | --- | --- |
| minimum crease angle | 54.731° | 66.427° | 66.427° | **18.258°** | **35.478°** | **43.078°** |
| over-fuzz samples | 0 | 0 | 0 | 37 | 56 | 90 |
| worst departure, mm | — | 4.745e-08 | 6.060e-08 | 2.972e-04 | 1.935e-04 | 1.431e-04 |

**Refuted, and not narrowly.** The angle rises monotonically with `U` and is shallowest at
`U` = 0.5, which builds cleanly. At the degenerate `U` it is 35.478° — nearly twice as far from
tangency as at a sound one. The quantity is *anti-correlated* with the failure, so no threshold on
it could have caught the sliver, and a guard built on it would have fired on the wrong
configurations. That is a cheaper outcome than it looks: the hypothesis was attractive, it was one
scalar a build, and it is now closed rather than carried.

**Both of the item's secondary questions answered, and both negatively for "flat".** The over-fuzz
count grows on the tail faster than `U` does (37, 56, 90 across 0.5, 0.75, 1.0) and is exactly 0 on
the nose at every `U`. The worst departure moves the *other* way, falling from 2.972e-04 to
1.431e-04 mm, so the two are not two readings of one thing.

**The by-product is worth more than the hypothesis.** `tail_shell` at `U` = 0.75 — the configuration
the retired `MIN_U` = 0.8 floor existed for — builds cleanly: one valid solid, `rib_residue` exactly
0.0, no edge group not shared by two faces, nothing over `WALL_TOL` on the rib edges. IP-FC-139/140/141
retired that floor on the grounds that the defect no longer reproduced; this measures it on the
geometry instead of inferring it from a sweep that passed, and it holds.

**No code changed for this item**, so the suite was not re-run: `rib_edge_check.py` already existed
from IP-WTM-33 and IP-WTM-37, and this was four invocations of it.

### The input axis, and the constant that bounds it (IP-WTM-41)

IP-WTM-40 scanned every saved wall at 1 mm axially and found no severed ring in 1 704 stations. The
bound it recorded with that result is that its twelve walls **vary `U` alone**, with every other
design input at the parameter sheet's literal — while the severed ring is a property of the rib cut,
whose tools are placed and sized by rows `U` never touches. This is that axis, and it needed a second
corpus: the 21-case free-parameter screen of 2026-09-30 tested construction *validity* on the
**round-0** construction and saved nothing, and `ring_scan` reads a finished wall off disk.

**The result, 2026-10-14, 6 h 56 min of machine time:**

| population | cases | built | refused | scanned | stations | annulus | severed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `nose_cowl_shell` `U` = 1.0 | 18 | 15 | 3 | 15 | 630 | **630** | 0 |
| `tail_shell` `U` = 0.5 | 24 | 21 | 3 | 21 | 1 008 | **1 008** | 0 |

Every station on every wall is a healthy annulus — not merely "not severed": there is not even a
`no_wall` reading, where IP-WTM-40's corpus had one slice artifact in 1 704. No kernel disagreement,
because the proxy flagged nothing to escalate.

**The control passes exactly, and that is what lets the rest of the table mean anything.** The nose
baseline — the sheet's own configuration, built by this harness eight days after the soak and from a
different script — hashes to `9c2ddcc8…74dab`, identical to all five 2026-10-06 repeats. So a
difference a case shows is the case's, not the harness's. It is also a sixth repeat for OQ-ARCH-19's
reproducibility result, free.

**Coverage is checked rather than claimed: 0 unmoved.** Each of the 14 built excursions on the nose
and 20 on the tail changed the built wall, by a fingerprint of solids, faces, edges, bounding box and
raw volume. The spread is not marginal — tail volumes run 3936.05 to 6351.51 mm³ against the
baseline's 5850.92, and tail face counts 2262 to 2930 against 2416. On the nose `butt_angle` at ±5°
takes the face count to 312 and 928 from 536, a real topology change in both directions that the ring
survives.

**The guard that establishes that was wrong when first written, and its own data caught it.** The
first report named 7 of 15 nose cases `unmoved`, including `extrusion_width_lo` — which takes the
wall from 0.6 mm to 0.4 mm. A thinner wall keeps the same outer surface, so the same faces, the same
edges and the same bounding box; none of the four fields fingerprinted could see it. The fix adds
`Shape.Volume`, used strictly as a difference detector: IP-FC-119 measured it wrong by 0.16–0.24 % on
these solids, but that defect is a deterministic bias, so asking it whether two walls are the same
shape is sound where asking it how big either one is would not be. `input_screen.py --refingerprint`
filled the field in off the 15 saved walls for 0.2 s each rather than rebuilding them. A record
without the field now reports as **uncomparable** instead of falling back to the weaker four, because
a silently weakened vacuity guard is the failure the guard exists to prevent.

**A second reporting defect, same shape, one layer up.** The first combined report folded both kinds
into one verdict — which gives two records named `base`, so `unmoved` picks whichever came off disk
first and compares the other kind's cases against it, and every shared case name prints twice in the
refusal list. It happened to give the right answer only because a nose wall and a tail wall never
fingerprint alike. `screen_verdict` now refuses records spanning more than one `(kind, U)` and
`populations` is how a caller splits them, which is the same separation `corpus.screen` and
`corpus.available` already keep at the file level.

**What the screen found is not about the ring. It is `RIB_FACETS`.** Six cases — three on each kind,
the same three rows — are refused by `dilated_notches`' facet precondition rather than scanned. The
dilation is a union of `RIB_FACETS` = 48 copies on a circle of radius `t`, so it is a solid only
while `in_plane / t > 2·sin(π/48)` = 0.130806. The sheet sits at 0.166667, 1.274× the floor, and a
single-parameter excursion crosses it either way: `buttress_cut_thickness` 0.1 → 0.07 mm, 55 facets
needed; `extrusion_width` 0.6 → 0.8 mm, 52; `cowl_n_perimeters` 1 → 2, 77. So the bounds are
`buttress_cut_thickness` > 0.0785 mm and `cowl_n_perimeters × extrusion_width` < 0.7644 mm, and **a
two-perimeter cowl does not build at all**. The third case was added mid-run specifically to test the
closed form away from the two failures either side of the sheet, and it predicted both the refusal and
the facet count exactly. On the tail the prediction is not arithmetic already done — a tail's slabs
are tilted, so `in_plane` is `buttress_cut_thickness / sin θ`, and the tool that trips the check is an
axial slab reading **0.1004 mm**, not the nose's exact 0.1000. The 30° diagonals carry twice an axial
slab's in-plane thickness and are nowhere near the floor. This is the sixth place in this subsystem
where a fixed count stands against a quantity that varies, and the first where it bounds what can be
**built** rather than biasing what is measured. It is OQ-DES-CW32 and IP-WTM-47, and those three
points of the input space stay uncovered until it is answered.

**A thin-wall sampling qualification, retired by measurement rather than argued away.**
`extrusion_width_lo` has a 0.4 mm wall, so the scan's 0.2 mm circumferential spacing is half that
wall rather than the third `locate.TARGET_SPACING` is set for. Re-scanned at 0.133 mm: 42 stations,
all annulus, 0 severed, 61 s — the same verdict, so the reading is not an artifact of under-sampling
a thinner wall.

**The measured cost, because it is what makes a further run schedulable** — and OQ-DES-CW26's own
estimate for a scan was once wrong by orders of magnitude for want of exactly this:

| | `nose_cowl_shell` `U` = 1.0 | `tail_shell` `U` = 0.5 |
| --- | --- | --- |
| build, a case | 37–54 s, median 43 | 525–856 s, median 700 |
| **refused**, a case | 36–38 s | 83–99 s |
| scan, a wall | 35–89 s, median 59 | 242–359 s, median 258 |
| s a station | 0.83–2.12 | 5.05–7.48 |
| stations a wall | 40–44 | 48 |

A refusal costs nearly a whole build on the nose and about an eighth of one on the tail, of which
pass 1's 25.3 s is the only hoistable part — which is the measurement that demoted alternative 4 of
OQ-DES-CW32 after it had been written on the expectation of a ~700 s saving. The six refusal costs
had to be recaptured to say that: the first version of the error record carried no `build_s`, so the
figure existed only in a driver's progress log, which is not an artifact anything regresses.

**What this does not establish.** One input moves at a time, at one `U` per kind. An **interaction**
between two inputs is untested, as is any interaction between an input and a large `U` — and
`tail_shell` at `U` = 3.0, the configuration OQ-DES-CW26's break was reproduced on, is covered only
along the `U` axis. Scanning the screen at `U` = 3.0 would be about 1.8 h a case against 16 min at
`U` = 0.5, so a second population there is a day of machine time, not an evening.

### The nose's floor was the criterion, and two of this question's premises were stale (IP-WTM-26)

IP-WTM-36 left a floor: raising `SEED_MAX` at fixed `U` = 4 took the nose from 0.01530 to 0.00733 mm
and then saturated at **0.00710**, which was recorded as the part of the residual still belonging to
this item. Three candidates were tested for it, in increasing order of what they would have meant.

**1. The circumferential fit resolution — refuted, and the coarse direction is what settles it.**
§6.8.3 excluded `FIT_ARC` as a cause of the `U` *trend* because it saturates; a quantity that
saturates is the right shape for a *floor*, which is the opposite claim and had never been tested.
Holding `U` = 4 and `SEED_MAX` = 24 and moving `FIT_ARC` through 2.0, 1.0, 0.5 and 0.25 — an
achieved spacing of 1.595 down to 0.250 mm, 2.7x the wall thickness down to 0.4x — moves the
finished wall from 0.0071043 to 0.0071032 mm. **4.7e-6 mm across a 6.4x range.** Loosening it does
not degrade the wall either, so this is not a saturated mechanism but an uninvolved one.

**2. The instrument — nearly converged, with a caution for anyone loosening it.** `CHECK_ARC` =
0.4 / 0.2 / 0.1 / 0.05 gives 0.00947 / 0.00710 / 0.00697 / 0.00697. So the figure converges to
**0.00697 mm** and the default sampling adds 1.9 %, while 0.4 mm would add **36 %**. Coarse reads the
wall *thinner*, which is the wrong direction for under-sampling a minimum and the right one for
discretizing the exterior: both contours are polylines at `n_check`, and a coarse outer polyline's
chords cut inside the true curve. This sweep is **structurally confounded** — `n_check` feeds
`_refine` as well as `_finished_wall_gap`, so it is control loop and ruler at once — and the
confound was measured inactive here: all four runs report 26 seeded stations becoming 26, pass 1
identical to five decimals, so bisection never subdivided and `n_check` changed nothing it did.

**3. `TAU` — and this is what the floor was.** `_refine` stops at the **first** subdivision inside
`TAU`, so once the seed is dense enough that the as-seeded fit already passes, bisection does nothing
at all. The `SEED_MAX` = 24 row is that caught in the act: 26 seeded to 26 stations, pass 1 pinned at
0.04991 immediately under 0.05.

| `SEED_MAX` | `TAU` | seeded → stations | pass 1 | finished wall |
| --- | --- | --- | --- | --- |
| 6 | 0.05 | 10 → 11 | 0.03083 | **0.01530**, fails |
| 6 | 0.02 | 10 → 15 | 0.00752 | **0.00393** |
| 6 | 0.01 | 10 → 17 | 0.00748 | **0.00393** |
| 24 | 0.05 | 26 → 26 | 0.04991 | **0.00710** |
| 24 | 0.02 | 26 → 28 | 0.00428 | **0.00268** |
| 24 | 0.01 | 26 → 28 | 0.00428 | **0.00268** |
| 24 | 0.004 | 26 → **63** | 0.00512 | **0.00268** |
| 24 | 0.002 | — | — | **`Unconverged`**, 64-station budget |

The first row reproduces IP-WTM-36's 0.01530 exactly, which is the control that lets the rest be read
beside it. **`TAU` is a two-position switch, not a dial**: 0.02 and 0.01 produce the same build, and
0.004 produces 63 stations against 28 and the same wall. So **0.00268 mm is a real floor**, 3.7x
inside `WALL_TOL`, reached by three criteria spanning fivefold and unmoved by 2.25x the stations.
Pass 1 has its own floor about twice as high — at `TAU` = 0.004 it reaches only 0.00512 and cannot
get to the 0.004 asked for — which is §6.8.2 again: the two passes measure to different exteriors, so
their floors have no reason to agree. And `budget` = 64 stops `TAU` = 0.002, the same limit
IP-WTM-28 and IP-WTM-44 found on tails, so it binds on both kinds rather than being a tail symptom.

**Two of OQ-DES-CW31's premises were stale, and correcting them changed its recommendation.**

- *The floor.* It read the 0.0071 mm saturation as a construction floor left to this item. It is
  `TAU`, and either lever alone makes the nose compliant — `TAU` = 0.02 does it at the seed as it
  stands, for 19 s more build.
- *The cost.* Its central objection quotes `SEED_MAX`'s note: 23 minutes a part on "a tail whose 59
  feature stations make 60 patches". **`cavity` no longer patches that way.** It takes its features
  from `feature_stations(`**`body`**`, …)` — the un-notched blank, which carries no rib edges — where
  the 60-patch regime read the *notches*, and the code's comment at that line says so in the past
  tense. Every current build of both kinds reports `patch 1/1`, confirmed on a real tail and a real
  nose log. Re-measured with one patch: **+23 % on a nose, +33 % on a tail.** `SEED_MAX`'s note is
  corrected in place, including its second claim — generous seeding *does* buy something the
  criterion does not guarantee, precisely because `_refine` accepts the first subdivision that passes.

**The tail prerequisite CW31 named is measured, and it answers both halves.** At `U` = 0.5 with
`SEED_MAX` 6 → 24: the wall goes 0.03794 → 0.03346 mm, **12 %**, still 3.3x over tolerance, while
**pass 1 improves 4.9x to 0.00579 mm — inside `WALL_TOL`**. The fit becomes five times more accurate
and the wall does not follow. So two independent sampling levers now fail on the tail and work on the
nose, for two different reasons: `TAU` fails by not building, the seed fails by building fine and not
helping. A residual that resists both is not a sampling problem.

**A defect in this plan's own driver, found by disagreeing with the soak.** `seed_density.one` builds
the wall **twice** — `cowl_tree.emit` plus `recompute` runs the shell node's `execute()`, which calls
`shell_solid`, and the driver calls it again because the node exposes no `report`. A `tail_shell` at
`U` = 0.5 reported 1 464 s against the soak's 727 s for the identical configuration (2.01x) and a
nose at `U` = 4 reported 226 s against 117 s (1.93x), so the halving is measured rather than assumed.
**Every `seconds` figure this driver printed before 2026-10-14 is two builds, IP-WTM-36's included**;
those conclusions are ratios and wall figures and are unaffected. The driver now times the two
phases separately.

**One trap avoided rather than paid for, and then pinned so the next driver author does not pay for
it either.** `--tau` was nearly implemented as a module-constant override like `--seed-max`. It would
have been a silent null experiment: `cavity` and `shell_solid` both declare `tau=TAU` as a **default
argument**, bound once at import, so setting `ci.TAU` does nothing and the driver would have printed
the value it meant to test while building at 0.05. There is no symptom — the build succeeds, the
numbers are plausible, and the conclusion is confidently wrong. `TAU` is passed as an argument
instead, and `seed_density.NOT_OVERRIDABLE` records why.

The hazard is the **shape of the binding**, not `TAU`, so the set of constants with that shape is now
a test: `tests/test_cowl_interior_constants.py` parses `cowl_interior.py` — which cannot be imported
without FreeCAD — and finds every default argument bound to a module-level constant. There are
**nine, over five constants**: `REFIT_TOL` four times, plus `OUTWARD_STEP_MM`, `END_INSET`,
`FINISHED_PLANE_TOL` and `TAU` twice. So a driver trying to sweep any of those four others would hit
the same silent null. The test asserts that none of the six constants `seed_density.py` *does* sweep
by `setattr` has become a frozen default, and that the recorded set has not grown — a new entry being
a notification rather than a defect. Its own detector is tested against synthetic sources, including
the positional-alignment case where a mis-attribution would be silent, because a detector that
quietly found nothing would make the whole guard vacuous.

The four constants that *are* swept are safe because each is read inside a function body at call
time, and the achieved spacings moving with the override confirms that empirically rather than by
inspection.

### The wall measured perpendicular to itself, and three corrections to the instrument (IP-WTM-26)

§6.8.2.1 ended with a sentence naming the one thing that would settle the tail's residual: "a 3-D
normal-distance measurement would settle it and none exists in this subsystem." This built it —
`wall_measure/normal_distance.py` and `freecad/normal_check.py`, 46 tests.

**It had to be the normal distance, and a 3-D *minimum* would have been worse than useless.** The
in-plane figure is a minimum over the inner loop within one plane; the 3-D minimum from the same
point to the same surface is a minimum over a strictly larger set, so it is always **smaller** and
could only ever make a thin reading thinner. It could not exonerate a wall even in principle. What an
in-plane nearest-point measure gets wrong at a junction is its *direction*, so the direction is the
measurement: leave the inner surface along its own outward normal and bisect `Shape.isInside` for
where the solid ends.

**Checked against closed form before being pointed at the question**, which is this plan's own
standing lesson: the incumbent was trusted for months and does not converge. On `truth`'s fixtures it
reads 0.6 mm on a uniform tube, 0.45 inside a patch cut into the **outer** surface, and **1.0 mm on a
rib raised 0.4 mm off the inner** one — that last being the case a measure which always started from
the nominal bore radius would fail while passing the other two. It declines rather than guessing in
five named ways, and `normal_verdict` refuses to call a run established when every thin sample
declined, because "the measure cannot see here" and "the material is present" are different answers.

**Six corrections, each caught by the instrument's own output rather than by review.** Three were
found before the first real result and three after it, and **two of the latter changed the answer**
— which is the argument for re-reading a new instrument's output rather than its verdict.

1. **Selecting every sample "under nominal" picked all 360 on an exactly-0.6 mm tube.** Both loops
   are polygons, so the outer one's chords cut inside the true circle: 0.000381 mm of sag at `R` = 10
   with 360 points, making every reading 0.59962. "Thin" has to mean "fails the gate",
   `nominal - WALL_TOL`, or the sample set is sub-micron noise. Same bias §6.8.3 measures on
   `CHECK_ARC`, this time in the sample selection.
2. **A 1.05 mm reading on a 0.6 mm wall was about to be reported as exoneration.** The first nose run
   returned normals of exactly `(1, 0, 0)` at points where the outward direction is `-y`: rib-slot
   cheeks, planar because the side slabs sit at constant `x`. A depth perpendicular to a slot cheek
   is the material *across the slot*. The measure now records the angle between the surface normal
   and the in-plane path — 15 to 73° on those samples — and refuses to let an oblique reading correct
   an in-plane one.
3. **The exit classification used the entry's tolerance**, so all four real readings reported
   `off_surface`. The entry point comes off a section wire and lies on its face to 1e-6 mm; the exit
   point is wherever bisection stopped, within `DEPTH_TOL_MM` = 1e-4 of the boundary — a hundred
   times further out. With the tolerance matched, all four exit through a B-spline face, the OML, so
   they are thicknesses to the exterior and not webs into a slot.

4. **A guard read the wrong source**: the vacuity checks counted `rows`, which is capped at `worst`,
   so a station with twelve thin samples all on cut faces reported "no sample is thin in-plane". They
   read the station totals now. A related hole in the same guard: `census_settles` required only that
   nothing was placed *on* the fitted surface, so a wall with twenty unplaced samples would have been
   called settled — and an unplaced sample is precisely one never asked the question. It now blocks on
   unplaced and ambiguous samples too, and on a loosely placed fitted one.
5. **`ON_FACE_TOL` = 1e-6 mm was biased against the one class that matters, and this changed the
   answer.** `distToShape` to a planar face returns an exact distance; to a trimmed B-spline it is an
   iterative solve that stops at its own tolerance. So the threshold **placed cheek samples and
   rejected fitted-surface ones.** Of the samples no face claimed at 1e-6, every single one lands on
   a B-spline at 1e-4 — 20 of 20, 86 of 86, 336 of 336 across three walls — taking the fitted share
   from 1 % to 6.5 % on the tail at `U` = 0.5 and from **3 % to 37 %** on the nose at `U` = 4.0. The
   retry runs only where the strict pass finds nothing, and a loose placement keeps a separate
   `(loose)` label; keeping the two apart is what exposed the bias in the first place.
6. **`ALIGN_DEG` = 30° was discarding real readings, and this changed the answer too.** The five
   worst samples on the tail at `U` = 0.5 sit at 30.1–30.8° and were being thrown out by a hair. The
   angle **does not separate the populations** — 3.1–30.7° on the fitted surface against 33.2–50.8°
   on cheeks, a 2.5° gap — whereas the inclined-slab identity separates them by 350×: a cos residual
   of 0.0002–0.0020 mm on the fitted surface against 0.688–0.737 mm on cheeks. `CONSISTENCY_TOL`
   replaced the cutoff with the relationship, which is measurable rather than chosen, and sits 5×
   above the worst real residual and 69× below the best cheek one. Recovering those five samples took
   the tail's worst deficit from 0.0550 mm to **0.0943 mm**. A smaller bug inside the same fix:
   `cos <= 0.0` never fired, because `cos(radians(90))` is 6.12e-17, so an orthogonal normal returned
   9.8e15 instead of `inf` — classified correctly by luck and informative to nobody.

**The result, across four saved walls at 12 stations each, 0.125 mm circumferentially, no build.**
The first question asked of every under-tolerance reading is which **face class** it sits on, which
is cheap enough to ask of all of them and is the decisive half. **The two classes have opposite
biases**, which is why no single exclusion rule was ever going to fix the figure:

| wall | thin | on cut faces | **on the fitted interior surface** |
| --- | --- | --- | --- |
| `nose_cowl_shell` `U` = 1.0 | 109 | 109 | **0** |
| `tail_shell` `U` = 0.5 | 372 | 348 | **24** (6.5 %) |
| `nose_cowl_shell` `U` = 4.0 | 251 | 157 | **94** (37 %) |
| `tail_shell` `U` = 1.0 | 2 456 | 438 | **2 018** (82 %) |

**Reading one wall as representative would have been wrong in both directions**, and the first pass
at this did exactly that. A compliant nose's thin readings are *entirely* artifact; on a tail at
`U` = 1.0 four fifths are real, and one station there has 2 017 of its 4 267 samples under tolerance
with **1 954 on the fitted surface — 46 % of the circumference**.

The cut-face readings are **pessimistic artifacts**: their in-plane path crosses a slot mouth whose
coordinate is exactly `buttress_cut_thickness`/2 = 0.05 mm, and along their own normals they read
0.68 to 3.0 mm, **none confirmed thin**. One nose sample makes it unmistakable: its path runs purely
in `x` from 0.650 to 0.050, exactly **0.60000 mm**, nominal to five decimals, across the gap.

The fitted-surface readings are **the wall, and there the plane is optimistic. 66 were measured and
every one is confirmed thin and thinner than the plane said; none was exonerated:**

| wall | station | samples | worst in-plane | **worst normal** | obliquity | ratio |
| --- | --- | --- | --- | --- | --- | --- |
| `tail_shell` `U` = 0.5 | -5.3636 | 5 | 0.58655 | **0.50570** | 30.1–30.8° | **7.0x** |
| `nose_cowl_shell` `U` = 4.0 | -104.0907 | 14 | 0.58597 | **0.52098** | 27.2–27.3° | **5.6x** |
| `tail_shell` `U` = 1.0 | -72.2723 | 14 | 0.57742 | **0.53554** | 21.5–21.9° | **2.9x** |

**Two independent checks.** A plane cutting a slab inclined at θ reads `thickness / cos θ`, and all
66 satisfy that to **0.0037 mm or better**, most under 0.0005 — between a 2-D polyline minimum in
`numpy` and a 3-D bisection in the kernel, so two unrelated instruments agree through a trigonometric
identity rather than one agreeing with itself. And the **in-plane** column reproduces figures already
in the record from separate work: 0.01345 mm is exactly IP-WTM-45's crease-excluded worst, 0.01403 mm
exactly OQ-DES-CW28's nose figure at `U` = 4. The old half agrees with what was known; the normal
column is the new information.

**So the cowl wall is genuinely thin on both kinds, by 0.065 to 0.094 mm — six to nine times
`WALL_TOL` — and it is not localized.** The hope that the residual was entirely artifact is refuted,
and so is this measurement's own first reading, which put the tail's defect at 4 samples and
0.0550 mm before corrections 5 and 6 above.

Two consequences for the open questions: OQ-DES-CW29 is choosing between two measures that are
**both** optimistic where it matters and neither of which sees any of this, and what the gate should
do about it is OQ-DES-CW33 and IP-WTM-48.

**And CW33's own prerequisite is answered, against the alternative that named it.** That alternative
keeps the in-plane measure as a cheap search and re-measures the worst `N` samples a station.
In-plane severity ranks the real readings **last**, on every wall that has any:

| wall | station | thin | fitted | their ranks | `N` needed |
| --- | --- | --- | --- | --- | --- |
| `tail_shell` `U` = 0.5 | -35.9086 | 55 | 14 | 38–52 | **53** |
| `tail_shell` `U` = 0.5 | -22.8179 | 62 | 5 | 48–58 | **59** |
| `nose_cowl_shell` `U` = 4.0 | -119.9087 | 36 | 22 | 14–35 | **36** |
| `nose_cowl_shell` `U` = 4.0 | -104.0907 | 88 | 72 | 12–87 | **88** |
| `tail_shell` `U` = 1.0 | -72.2723 | 2 017 | 1 954 | 19–2 016 | **2 017** |

Artifacts occupy the top twelve to nineteen ranks and real readings everything below, out to the last
one; on three of five stations `N` would have to be *every* thin sample. **The cause is structural, so
it should be expected to hold:** an artifact is wrong by a slot width — up to 0.73 mm — while a real
reading is wrong only by the inclination factor of 1.08–1.16, so it sits just under tolerance.
Sorting by severity sorts artifacts first by construction. The first run demonstrated it
accidentally: at `N` = 12 a station it re-measured 111 samples on a `tail_shell` and found **none**
of the 24 that were wall thicknesses.

### Cross-plan

**Supersedes IP-FC-151** in `freecad_migration.md`, which is marked superseded and points here.

**IP-FC-152's prerequisite measurement is delivered by IP-WTM-14** — the annulus test's
false-positive rate across both kinds and the swept `U` range, 336 station readings with no false
positive, recorded in that item's blocked-reason note. It stays blocked on OQ-DES-CW26 all the same,
because which check to adopt is a choice and not a measurement.

**Uses `geometry_bridge.md`'s library** but does not depend on unfinished items in it: IP-GB-16's
facades and IP-GB-21's tube fixtures are both done.
