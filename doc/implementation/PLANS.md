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
| [wall_thickness_measure.md](wall_thickness_measure.md) | Settle by measurement whether the finished cowl wall meets `WALL_TOL`, and build the instrument that can say so — no measure available today both converges and sees a local thin spot. Supersedes IP-FC-151. | Active |

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

**`wall_thickness_measure.md` is a measurement plan, and two design documents are waiting on its
output rather than the reverse.** It supersedes `freecad_migration.md`'s IP-FC-151, and
OQ-DES-CW23 and OQ-DES-CW26 cannot be decided on present evidence because the instrument behind
every thinness figure in the project does not converge. It depends on `geometry_bridge.md` only
for finished items, and it requires no cowl build: the 2026-10-06 soak saved all 28 finished walls
as BREP, so real geometry is re-measurable from file.

**`geometry_bridge.md` changes where new geometry tests go, so it interacts with
`test_coverage.md` without depending on it.** OQ-GB-2 made a new geometry check a bridge-tier
`pytest` test rather than a `check_*.py` entry, so `test_coverage.md`'s remaining
`freecadcmd`-tier items should be read as paying down the existing backlog in place, not as the
pattern for new work. One item overlaps outright: `geometry_bridge.md`'s IP-GB-22 moves the nine
`check_*.py` scripts that import no FreeCAD into `tests/`, which is test-placement work that
`test_coverage.md` would otherwise have reached eventually. It is listed in the bridge plan
because the survey behind that plan is what found them.
