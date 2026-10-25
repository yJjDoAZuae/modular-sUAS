# Implementation Plans — master index

Every implementation plan is listed here, one line each. Cross-plan dependency analysis
starts from this table.

Plans are dependency-ordered work items derived from a settled design; they are not
design documents. See [doc/roadmap.md](../roadmap.md) for what is being built and why,
and the `/impl` skill for the plan format.

| Plan file | Scope | Status |
| --- | --- | --- |
| [geometry_refactor.md](geometry_refactor.md) | Deduplication, interface, and robustness work on the OpenSCAD modules and the Python driving them. Roadmap Phase 2. | Complete |
| [freecad_migration.md](freecad_migration.md) | Porting the generators to FreeCAD and the capabilities that port enables — the nine use cases. Roadmap Phases 3–7. | Active |
| [test_coverage.md](test_coverage.md) | Retrofitting real unit/integration test coverage across both interpreter tiers (`tests/` pytest and `freecad/check_*.py`); closes the standing gap that verification has been ad hoc and uncommitted. **The documents are now checked the same way** (IP-TEST-12): `tools/doc_check.py` enforces the bookkeeping these plans and the design documents carry by convention -- anchors resolve, an open-question table lists exactly what is open, a blocked item names a blocker that is really open, a plan's header count matches its table -- and `tests/test_doc_check.py` asserts the tree is clean. Its first run found 320 findings, 27 of them its own false positives and the other 293 real. **And the same rule now reaches the code** (IP-TEST-13): `tools/source_spelling.py` shares that dictionary and corrects comments, docstrings, messages and identifier names -- 410 words and 31 renames across 98 files -- renaming a compound only where it is listed, and reporting rather than changing any it does not know. | Active |
| [geometry_bridge.md](geometry_bridge.md) | The adaptation library that lets `pytest` drive FreeCAD and OpenVSP across a process boundary, so the project's Python version is free of both vendors' build choices. Resolves OQ-ARCH-22. | Active |
| [wall_thickness_measure.md](wall_thickness_measure.md) | Settle by measurement whether the finished cowl wall meets `WALL_TOL`, and build the instrument that can say so. **Answered:** the measure is the corner-excluded minimum indexed by sample *spacing*. On a station grid placed from the real axial extent, **5 of the 12 distinct walls meet the tolerance and 7 do not** — every `tail_shell` fails at every `U` (0.013–0.047 mm) and the only nose failure is `U` = 4. The rib cut is verified to trim without refitting — identical control nets, a patch interior flat at 1e-15 mm, normals at 0.0000° — so neither the rib edges nor a boundary-value error at them is the mechanism. A **1 704-station** dense ring scan of all twelve walls at 1 mm axially finds **no severed section anywhere**, closing OQ-DES-CW26's axial-sampling bound; **its input-space bound is now closed too**, by a second scan of 36 purpose-built walls moving one design input at a time — **1 638 more stations, 0 severed, 0 confirmed gaps**, 6 h 56 min of machine time. **Its two-input interaction bound is closed on the nose**, by a third corpus of 86 walls moving two design inputs together — **3 612 more stations, every one a healthy annulus, 0 refused** — which leaves the tail's 242 pairs unrun at about 42 h of builds. **And the selected measure is now surveyed at the breadth that rejected its predecessor**, settling at **24 of 24** stations against the incumbent's **6 of 24**, so OQ-DES-CW26's alternative 3 is no longer waiting on an instrument. The gate now samples by **spacing** (0.125 mm, not 240 points) and reports both measures, which disagree about whether a nose complies — OQ-DES-CW29. **Tightening the fit's criterion is measured to fix a nose and to be refused by a tail**, at two configurations: at `TAU` = 0.02 and 0.01 a `tail_shell` raises `Unconverged` against the 64-station patch budget at `U` = 0.5 and again at `U` = 2.0, with pass 2's own worst gap unchanged across the whole fivefold range both times, so on a tail `TAU` is not the lever and the residual's mechanism (IP-WTM-26) is the critical path. **Pass 1 converges to 0.0073 mm, inside `WALL_TOL`, and the finished wall does not move** — the two passes measure out to different exteriors by necessity, the un-notched OML and the notched one, which diverge by up to 26.5 mm. The two thresholds also turn out to be compared against two *different* measures, 2.80x apart on that wall, essentially all of it corner exclusion rather than sampling. **And every figure above is in-plane, which the plan's last measurement shows is the wrong direction**: the surface carrying the wall is inclined 21.5–30.8° to the section plane, so an in-plane reading is `thickness / cos θ`, and measured along the surface's own normal instead, **66 readings across three walls are every one confirmed thin and none exonerated** — worst deficits 0.0943 / 0.0790 / 0.0645 mm, six to nine times `WALL_TOL`, where the in-plane figures read 0.0135 / 0.0140 / 0.0226. So the compliance answer stands in its *ordering* and understates its *magnitude*. Supersedes IP-FC-151; withdrew OQ-DES-CW23; raised OQ-DES-CW28 through OQ-DES-CW33, which are six open decisions and the whole of what the plan is now waiting on. | Active |

Status values: `Draft`, `Active`, `Complete`, `Superseded`.

**Cross-plan note.** `freecad_migration.md` depends on `geometry_refactor.md` being
complete, not merely mostly done: the parameter dataclasses (IP-GEO-16, IP-GEO-25) are the
layer that survives the port untouched, and the `extrusion_width` rename (IP-GEO-24) exists
specifically so the port does not reproduce a misnamed parameter.

**`test_coverage.md` is orthogonal to the other two**, not sequenced after them: its
`freecadcmd`-tier items (IP-TEST-7 through IP-TEST-11) apply to FreeCAD code that already
exists regardless of how much of `freecad_migration.md` is done, and its pytest-tier items
(IP-TEST-2 through IP-TEST-6) apply to `src/Fuselage/tools/` code that predates both plans.
New work items in either other plan are expected to carry their own test sub-item per the
TDD rule in [general.md](../guidelines/general.md#test-driven-development-tdd) rather than
deferring to this plan — `test_coverage.md` exists to pay down the *existing* backlog, not
to be where future work's tests live.

**`wall_thickness_measure.md` is a measurement plan, and two design documents were waiting on its
output rather than the reverse.** It supersedes `freecad_migration.md`'s IP-FC-151. It required no
cowl build: the 2026-10-06 soak saved all 28 finished walls as BREP and prints pass 2's own
prediction per build in its log, so both sides of every comparison were re-measurable from file.

**That stopped being true at IP-WTM-41, and the exception is worth recording for the next plan that
budgets off this one.** Every question answerable from the saved corpus is a question about walls
that vary in `U` alone, because that is the only axis the soak swept. Asking about any other design
input means building walls that do not exist: IP-WTM-41 built 36 of them and spent **6 h 56 min** of
machine time, of which the `tail_shell` population alone is 6 h 16 min. The resulting walls are saved
beside the soak's, in their own directory and under their own filename pattern, so the two
populations can be scanned and reported separately rather than merged into one figure.

**Delivered 2026-10-10, and it withdrew one of the two open questions rather than informing it.**
OQ-DES-CW23 asked how to handle a "small residual gap" between `cavity()`'s post-cut prediction
and the real cut. Measured, that gap is at most 0.0039 mm — small, as the item said — and knowing
its size is what finally let its four alternatives be scored. It was missing information rather
than a design choice. OQ-DES-CW26 stays open, because which check to adopt against a broken
section ring genuinely is a choice; the plan reported its evidence there and delivered
IP-FC-152's named prerequisite survey of 336 station readings with no false positive.

**Its own instrument was the biggest thing it found, and that cost two withdrawn findings.** The
plan's first corpus figures fixed the sample *count* at 1 440 a loop. A cowl scales with `U`
while its 0.6 mm wall does not, so that bought 0.30 mm of circumferential spacing at `U` = 1 and
1.45 mm at `U` = 4, and a station reading 0.2136 mm thin there reads 0.00264 mm at a fixed
0.125 mm spacing. A corpus worst of 0.2136 mm and a "regime change above `U` = 2" were both
published off that and both are withdrawn. `check_cowl_interior` had the same defect
(`AROUND` = 240, 8.7 mm apart at `U` = 4); that is **fixed** under IP-WTM-25, which sets
`WALL_ARC` = 0.125 mm derived per station, and IP-WTM-10 is no longer blocked.

**The instrument stayed the biggest thing it found, right to the end.** The last and largest
instrument finding is that every measure in the subsystem is **in-plane** while the surface carrying
the wall is inclined 21.5–30.8° to the section plane, so every figure the plan published reads
`thickness / cos θ` and understates the deficit. Measured along the surface's own normal, 66
readings across three walls are every one confirmed thin, worst deficits 0.0943 / 0.0790 /
0.0645 mm against in-plane figures of 0.0135 / 0.0140 / 0.0226 at the same samples. That is
OQ-DES-CW33. Two things make this the pattern rather than an incident: it is the **third** time a
sampling or tolerance choice inside the instrument moved a published figure by more than the
quantity being measured, and like the other two it was found by asking what the instrument could not
see rather than by a disagreement between runs.

**Status 2026-10-16: 42 of 49 items done, 1 `todo`, 6 blocked on open questions.** The plan has run
out of work that is its own to do. Every blocked item waits on one of OQ-DES-CW28 through
OQ-DES-CW33 — six decisions the plan raised, each with its evidence gathered and its alternatives
priced, none waiting on further measurement. The one `todo`, IP-WTM-49, is a measurement and needs
no decision: *why* the interior surface is inclined where the wall is thin, which is the one
quantity the plan measured and did not explain, and which could retire OQ-DES-CW33 rather than
answer it.

**`geometry_bridge.md` changes where new geometry tests go, so it interacts with
`test_coverage.md` without depending on it.** OQ-GB-2 made a new geometry check a bridge-tier
`pytest` test rather than a `check_*.py` entry, so `test_coverage.md`'s remaining
`freecadcmd`-tier items should be read as paying down the existing backlog in place, not as the
pattern for new work. One item overlaps outright: `geometry_bridge.md`'s IP-GB-22 moves the nine
`check_*.py` scripts that import no FreeCAD into `tests/`, which is test-placement work that
`test_coverage.md` would otherwise have reached eventually. It is listed in the bridge plan
because the survey behind that plan is what found them.
