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
| [test_coverage.md](test_coverage.md) | Retrofitting real unit/integration test coverage across both interpreter tiers (`tests/` pytest and `freecad/check_*.py`); closes the standing gap that verification has been ad hoc and uncommitted. | Active |
| [geometry_bridge.md](geometry_bridge.md) | The adaptation library that lets `pytest` drive FreeCAD and OpenVSP across a process boundary, so the project's Python version is free of both vendors' build choices. Resolves OQ-ARCH-22. | Active |
| [wall_thickness_measure.md](wall_thickness_measure.md) | Settle by measurement whether the finished cowl wall meets `WALL_TOL`, and build the instrument that can say so. **Answered:** the measure is the corner-excluded minimum indexed by sample *spacing*. On a station grid placed from the real axial extent, **5 of the 12 distinct walls meet the tolerance and 7 do not** — every `tail_shell` fails at every `U` (0.013–0.047 mm) and the only nose failure is `U` = 4. The rib cut is verified to trim without refitting — identical control nets, a patch interior flat at 1e-15 mm, normals at 0.0000° — so neither the rib edges nor a boundary-value error at them is the mechanism. A **1 704-station** dense ring scan of all twelve walls at 1 mm axially finds **no severed section anywhere**, closing OQ-DES-CW26's axial-sampling bound and leaving its input-space bound. Supersedes IP-FC-151; withdrew OQ-DES-CW23. | Active |

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
published off that and both are withdrawn. **`check_cowl_interior` has the same defect and it is
not yet fixed** (`AROUND` = 240, 8.7 mm apart at `U` = 4), which is IP-WTM-25 and now blocks
IP-WTM-10. Four items remain, three of them measurements.

**`geometry_bridge.md` changes where new geometry tests go, so it interacts with
`test_coverage.md` without depending on it.** OQ-GB-2 made a new geometry check a bridge-tier
`pytest` test rather than a `check_*.py` entry, so `test_coverage.md`'s remaining
`freecadcmd`-tier items should be read as paying down the existing backlog in place, not as the
pattern for new work. One item overlaps outright: `geometry_bridge.md`'s IP-GB-22 moves the nine
`check_*.py` scripts that import no FreeCAD into `tests/`, which is test-placement work that
`test_coverage.md` would otherwise have reached eventually. It is listed in the bridge plan
because the survey behind that plan is what found them.
