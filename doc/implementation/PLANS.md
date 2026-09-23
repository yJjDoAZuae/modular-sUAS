# Implementation Plans — master index

Every implementation plan is listed here, one line each. Cross-plan dependency analysis
starts from this table.

Plans are dependency-ordered work items derived from a settled design; they are not
design documents. See [doc/roadmap.md](../roadmap.md) for what is being built and why,
and the `/impl` skill for the plan format.

| Plan file | Scope | Status |
| --- | --- | --- |
| [geometry_refactor.md](geometry_refactor.md) | Deduplication, interface, and robustness work on the OpenSCAD modules and the Python driving them. Roadmap Phase 2. | Complete |
| [freecad_migration.md](freecad_migration.md) | Porting the generators to FreeCAD and the capabilities that port enables — the nine use cases. Roadmap Phases 3–7. | Draft |
| [test_coverage.md](test_coverage.md) | Retrofitting real unit/integration test coverage across both interpreter tiers (`tests/` pytest and `freecad/check_*.py`); closes the standing gap that verification has been ad hoc and uncommitted. | Active |

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
