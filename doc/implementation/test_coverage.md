# Test Coverage Retrofit — Implementation Plan

**Scope:** This repository has zero unit tests. `pytest` is a declared dev dependency and
`pyproject.toml` already configures `testpaths = ["tests"]`, but no `tests/` directory
exists. The one file in the tree named like a test (`src/Fuselage/tools/test_fuse.py`) is a
three-line scratch import, not a test. The 16 `check_*.py` scripts under
`src/Fuselage/freecad/` and `check_derivation.py` under `src/Fuselage/tools/` are real,
working integration-level checks and are already committed — that tier is not starting from
zero — but no code in the repository has function-level unit test coverage, and recent
sessions verified new FreeCAD geometry work with disposable scratchpad scripts that were
never committed, discovered and rejected 2026-09-22 (see
[general.md's TDD section](../guidelines/general.md#test-driven-development-tdd)).

This plan retrofits real coverage, in dependency order, across both interpreter tiers (see
[general.md](../guidelines/general.md#two-test-tiers-because-two-python-interpreters-are-involved)).
It also fulfills the long-unchecked roadmap item
"[Add regression tests](../roadmap.md)" under Phase 1.

No design decision is open here — this plan is process/quality work, not a port of
behavior — so no item is blocked on an `OQ-*`. Every item is blocked only on the harness
item that precedes it in its own tier, or on nothing.

**Design authority:** [doc/guidelines/general.md](../guidelines/general.md) (TDD and the
two-test-tier rules this plan exists to satisfy), [doc/guidelines/python.md](../guidelines/python.md)
(pytest mechanics and structure).

**Last updated:** 2026-09-22

---

## Work Items

| ID | Status | Title | Depends on | Design refs |
| --- | --- | --- | --- | --- |
| IP-TEST-1 | done | Create `tests/` matching `pyproject.toml`'s `testpaths`; delete or rename `src/Fuselage/tools/test_fuse.py` so no non-test file uses the `test_` prefix | — | [general.md §Two test tiers](../guidelines/general.md#two-test-tiers-because-two-python-interpreters-are-involved), [python.md §Testing](../guidelines/python.md#testing-python) |
| IP-TEST-2 | done | Unit tests for `src/Fuselage/tools/fuselage_variants.py` (108 functions — parameter dataclasses, CSV/JSON reads, sweep and render orchestration; largest single module in the repo). One deliberate exception: `freecad_render`'s own subprocess branch, which stays fake-queue-only — a real `freecadcmd` call costs ~8s each, incompatible with keeping the pytest tier fast, unlike OpenSCAD's ~0.13s which turned out cheap enough to test for real — see Notes | IP-TEST-1 | [general.md §TDD](../guidelines/general.md#test-driven-development-tdd), [python.md §Testing](../guidelines/python.md#testing-python) |
| IP-TEST-3 | done | Unit tests for the parameter/derivation cluster: `drawing_families.py`, `check_derivation.py`, `requirements.py`, `geometry_version.py`, `fillet_intent.py` — core logic of all five; `drawing_families.py`'s sheet-layout functions past `factor()` are presentation logic, noted as a deliberate remainder rather than picked up here | IP-TEST-1 | [general.md §TDD](../guidelines/general.md#test-driven-development-tdd) |
| IP-TEST-4 | done | Unit tests for the drawing/dimensioning tool cluster's live, reusable tools: `draw_set.py`, `draw_variant_set.py`, `branching_dimensions.py`, plus `freecad/sheet_naming.py` (a shared dependency). The one-off SVG-evidence generators in this cluster (`draw_bolt_flange_fillet.py`, `draw_dimension_alternatives.py`, `draw_corner_joint.py`, `draw_flat_offset.py`, `draw_flange_chamfer.py`, `draw_fillet_scope.py`, `draw_sheet_alternatives.py`, `draw_register_rows.py`) are deliberately not chased here — see Notes | IP-TEST-1 | [general.md §TDD](../guidelines/general.md#test-driven-development-tdd) |
| IP-TEST-5 | done | Unit tests for the verification/comparison tool cluster: `mesh_stats.py`, `baseline_ledger.py`, `baseline_manifest.py`, `surface_distance.py`, `stl_preview.py`, `brep_snapshot.py`, `scad_snapshot.py`, `params_snapshot.py`, `verify_sweep_change.py`, `verify_scad_change.py`, `verify_drivers.py`, `sweep_check.py`, `compare_backends.py` — all genuinely live verification infrastructure, not one-off tools; no scope-split like IP-TEST-4's needed here | IP-TEST-1 | [general.md §TDD](../guidelines/general.md#test-driven-development-tdd) |
| IP-TEST-6 | done | Unit tests for remaining `src/Fuselage/tools/` modules: `make_sheet_template.py`, `oml_export.py`, `render_variant.py`, `export_parameters.py`, `freecad_render.py`, `render_sheets.py`, `sweep_variant_sets.py`, `soak_shell_variants.py`, `audit_call_args.py`. `scan_octant_micro.py` (a one-off IP-FC-67 re-investigation script) and `fuselage_splode.py` (inherited scratch scaffolding with hardcoded magic indices, no real caller) are deliberately excluded — see Notes | IP-TEST-1 | [general.md §TDD](../guidelines/general.md#test-driven-development-tdd) |
| IP-TEST-7 | active | Audit `check_*.py` coverage against every function in the core FreeCAD geometry modules — `cowl_tree.py`, `cowl.py`, `cowl_interior.py`, `corner_tree.py`, `corner_common.py`, `oml_blank.py`, `boom_*.py`, `bulkhead_*.py`, `plane2d.py` (done), `flange_*.py`, `web.py`, `fillets.py`, `part_*.py` (already self-checking; found and fixed a real gap — see Notes) — and add a `check_*.py` regression for every function with none | — | [general.md §Two test tiers](../guidelines/general.md#two-test-tiers-because-two-python-interpreters-are-involved) |
| IP-TEST-8 | done | Audit and add `check_*.py` coverage for the drawing/TechDraw modules: `drawing.py`, `drawing_standard.py`, `dimension_placement.py`, `sheet_annotations.py`, `sheet_table.py` all already had coverage, audited and confirmed correct; `sheet_naming.py` already covered from the pytest tier (IP-TEST-4); `render_pages.py` had none and now does, run for real through `freecad.exe` with offscreen Qt -- see Notes. Two of the audited checks surfaced real, pre-existing product defects (not test-coverage gaps), also in Notes, left for Alex to triage | — | [general.md §Two test tiers](../guidelines/general.md#two-test-tiers-because-two-python-interpreters-are-involved) |
| IP-TEST-9 | done | Triage the `spike_*.py` exploratory modules (`spike_eps.py`, `spike_offset2d.py`, `spike_derived_part.py`, `spike_assembly.py`, `spike_fillet.py`, `spike_techdraw.py`, `spike_partdesign.py`, `spike_csg_tree.py`, `spike_sketch_expr.py`, `spike_hand_edit.py`, `spike_link.py`): each is either promoted to covered production code or moved to `src/Fuselage/archive/` with a note on why, per [general.md's adoption-phase note](../guidelines/general.md#project-lifecycle-phase) — do not add coverage to code that turns out to be a discarded experiment | — | [general.md §Weigh a refactor against what replaces the code](../guidelines/general.md#weigh-a-refactor-against-what-replaces-the-code) |
| IP-TEST-10 | done | Audit and add `check_*.py` coverage for remaining `src/Fuselage/freecad/` utility modules not covered above: `units.py`, `measure.py`, `solid_measure.py`, `mesh_to_brep.py`, `variants.py`, `preview.py`, `build_part.py`, `build_sheet.py`, `part_kinds.py`, `geometry_branches.py`, `pd_middle.py`, `pd_end.py`, `parameters.py` | — | [general.md §Two test tiers](../guidelines/general.md#two-test-tiers-because-two-python-interpreters-are-involved) |
| IP-TEST-11 | active | Historical audit: walk every completed item in [freecad_migration.md](freecad_migration.md), identify which ones were verified only by narrative description or scratchpad scripts with no corresponding committed `check_*.py`/`tests/` entry, and add the missing regression for each | — | [general.md §TDD](../guidelines/general.md#test-driven-development-tdd) |

---

## Notes

**Why pytest-tier items depend on IP-TEST-1 and freecadcmd-tier items do not.** The
`tests/` directory does not exist yet, so IP-TEST-2 through IP-TEST-6 have nothing to write
into until it does. The `check_*.py` convention under `src/Fuselage/freecad/` already
works and needs no harness — IP-TEST-7 through IP-TEST-10 can start independently and in
any order relative to each other.

**Sizing.** `fuselage_variants.py` alone has 108 top-level/method definitions — more than
every other `src/Fuselage/tools/` module combined. IP-TEST-2 is sized as one item now
because it is one coherent module, but is expected to be broken into sub-items (e.g. by
section: parameter dataclasses, CSV/JSON I/O, per-kind sweep functions, render
orchestration) once work on it actually starts, per the `/impl` skill's atomicity rule.
The `src/Fuselage/freecad/` tier is larger still (roughly 700 definitions across ~90
files); IP-TEST-7/8/10 group by subsystem rather than by file for the same reason, and will
split further as each is picked up.

**IP-TEST-9 exists because not everything under `freecad/` is production code.** The
`spike_*.py` files read as one-off exploratory scripts (the name is the tell). Writing
regression tests for an abandoned experiment is exactly the "capability in the throwaway
tool" mistake this project's own guidelines warn against in the other direction — the fix
here is to first decide, per file, whether it survives at all, before spending test-writing
effort on it. See [general.md's refactor-survival test](../guidelines/general.md#weigh-a-refactor-against-what-replaces-the-code).

**IP-TEST-1's outcome, 2026-09-22.** `tests/conftest.py` and `tests/test_environment.py`
now exist (3 tests, all passing) and `src/Fuselage/tools/test_fuse.py` is deleted.
`test_environment.py` is deliberately scoped to proving the harness itself works —
`pythonpath` resolves `fuselage_variants` from `tests/`, and `standard_values()` is
internally consistent — not to covering the rest of that module, which is IP-TEST-2.
Running it surfaced a real, separate infrastructure defect, root-caused the same day: bare
`uv run pytest` fails with `ImportError: ... numpy ... DLL load failed while importing
_multiarray_umath: The parameter is incorrect`, while `uv run python -m pytest` (same venv,
same command, invoked via `-m` instead of the console-script) passes clean. Cause: the venv
sits on a network share (`\\mrhorse\Archive\...`); `uv run pytest` executes the compiled
`.venv/Scripts/pytest.exe` stub directly, which resolves its own interpreter path in
Windows' extended-length UNC form (`\\?\UNC\...`), and numpy's Windows DLL loader calls
`os.add_dll_directory()` on its install path at import time — an API that rejects any path
starting with `\\?\`. `uv run ruff`/`uv run mypy` are unaffected because neither imports
numpy. Every work item below (and everyone running this repo's tests from this share) should
use `uv run python -m pytest`, never bare `uv run pytest`; `python.md` carries the full
explanation.

**IP-TEST-2's first pass, 2026-09-22.** `tests/test_fuselage_variants.py` now covers the
module's pure, deterministic logic: every filename generator, `scaled_standard_values`,
`greeble_nub_thickness_of`, the bulkhead type encode/decode pair, `lookup_anchor_diameter`,
`corner_validity_check`/`bulkhead_validity_check`/`boom_key_validity_check`,
`bolt_flange_fillet_gap`, `derived_parameters` (scaling, the cowling/non-cowling branch,
the boom/non-boom branch, the anchor/non-anchor branch, the bulkhead/corner branch, and the
zero-panel-thickness edge case), `derived_boom_bulkhead_parameters`, `flatten_param_space`,
the CSV/JSON readers and `relativize_scad_references` (via `tmp_path`), every
`_check_*` constant-group validator, `load_constants`, `axes`/`family_axes`/
`family_combinations`/`family_is_valid`/`family_of` (against the real, committed
`variant_param/` CSVs), and all 19 `null_*_parameters` constructors as one parametrized
sweep. 94 tests total (91 here plus IP-TEST-1's 3), all green, `ruff check` clean.

**Writing this test suite found a real, live bug** in `decode_bulkhead_type`: the
`TAIL_BOOM` and `else` (unrecognized type) branches assigned a local named `is_bolt`
instead of the `is_end` the function returns, a copy-paste typo from the branches above
them — `UnboundLocalError` on every call with `BulkheadType.TAIL_BOOM` or
`BulkheadType.NULL`. It never fired in the live sweep because no row in
`bulkhead_type_variants.csv` ever sets `is_boom=TRUE` (only
`boom_bulkhead_type_variants.csv` does, and `boom_bulkhead_parameters`/
`boom_bulkhead_render` never call `decode_bulkhead_type`) — but it was one stray CSV row
or one direct call away from crashing. Fixed alongside the test that caught it, same
commit boundary: both branches now assign `is_end` like every other branch. This is the
kind of defect this whole plan exists to make routine to catch.

**IP-TEST-2's second pass, 2026-09-22.** Added: `set_backend`/`_backend_for`/`set_resume`/
`set_previews`/`set_render_queue` (via a `restore_global_render_state` fixture, since these
mutate module globals and every test must leave them as it found them), `find_rendered_stls`,
`render_worker_budget`/`default_render_workers` (via the `FUSELAGE_RENDER_WORKERS` env
override, a clean deterministic seam), `corner_parameters`/`_variant_note`/`cowl_parameters`
(all four cowl kinds, including the shell-kind wall addition and the fraction-vs-absolute
split)/`_cowl_variant_note`, `solid_render`'s freecad-backend refusal branch, and
`render_definition`'s full file-management contract — atomic write (no `.partial*` left
behind), resume-skip on an unchanged definition with a complete mesh, and both ways a
renderer can exit zero while lying (no mesh at all; a mesh but a missing sidecar) — all
through a fake `RenderQueue` (`_ImmediateQueue`/`_RefusalRecordingQueue`) rather than a real
OpenSCAD/FreeCAD subprocess. 118 tests total, all green, `ruff check` clean.

**A pre-existing, unrelated gap surfaced while checking this pass**: `mypy` cannot resolve
`import fuselage_variants` from `tests/`, because `pythonpath = ["src/Fuselage/tools"]` in
`pyproject.toml` is pytest-only configuration that mypy does not read. Affects every test
file in `tests/`, including `test_environment.py` from IP-TEST-1, not something this pass
introduced. Not fixed here — needs its own small `mypy_path`/stub decision — noted so it
does not read as a regression later.

**Not yet covered, and staying in IP-TEST-2 rather than becoming a new item**:
`RenderQueue`'s own thread-pool behavior, the actual OpenSCAD subprocess branch inside
`solid_render` (past the freecad-backend refusal already covered), `freecad_render`'s own
wiring into `tools/freecad_render.py` (that backend module's `definition_text`/
`build_command` are separately in scope under IP-TEST-6, not here), and the top-level
orchestration (`sweep_session`, `main`, `_run_all_sweeps`, `run_*_parametric_sweep`). These
need heavier subprocess/FreeCAD mocking and are a deliberately separate follow-up pass
rather than something to rush into this one.

**IP-TEST-2's third pass, 2026-09-22.** Picked up four items from that deferred list that
turned out not to need subprocess mocking at all. `_available_memory_bytes` is checked
against real Windows state (a real
`GlobalMemoryStatusEx` call), the same "test the real thing when it's genuinely available"
approach used for OpenVSP and FreeCAD path resolution in IP-TEST-6.
`stamp_geometry_version` is real I/O plus a real `geometry_version.scad_version()` call
(already fully covered by IP-TEST-3), checked for header-prepending and correct module
naming. `_write_preview`/`render_preview_batch` turned out to be genuinely safe to run for
real too: `stl_preview`'s rasterizer is pure numpy with no OpenSCAD/FreeCAD dependency
(IP-TEST-5), so real STL fixtures rendered through a real `ProcessPoolExecutor` are fast and
self-contained -- including the documented Windows spawn/re-import `BrokenProcessPool`
fallback path, reproduced by monkeypatching the pool constructor itself to raise on
`__enter__` rather than needing to actually break multiprocessing. `rebuild_previews`,
which is pure orchestration around `render_preview_batch`, is tested with that call faked to
bound cost (missing-only vs. `--force`, the default-`OUTPUT_DIR` case, the
nothing-to-do-so-never-call-the-batch-function case, and failure reporting). 692 tests total
across all of `tests/`, all green, `ruff check` clean. Still deferred: `RenderQueue`'s own
thread-pool behavior, the real OpenSCAD subprocess branch, `freecad_render`'s wiring, and
top-level orchestration -- all genuinely need subprocess/FreeCAD mocking this pass avoided
needing.

**IP-TEST-2's fourth pass, 2026-09-22 -- closing the item.** A background audit agent for
IP-TEST-7 was launched and failed on a session-wide rate limit before producing a report
(see IP-TEST-7's Notes); rather than block on a retry, this pass continued directly with the
still-deferred items above, which turned out to be tractable after all. `RenderQueue`'s own
thread-pool/retry/`fail_fast` mechanics are exercised with real subprocess commands
(`sys.executable` one-liners standing in for an OpenSCAD invocation, decoupling the queue's
own logic from OpenSCAD specifically) -- including a real, load-bearing asymmetry this
testing surfaced: with `workers=1`, `submit()` calls the job inline with no `try`/`except` at
all, so a failing job's `CalledProcessError` propagates straight out of `submit()`, bypassing
the retry/`fail_fast`/`.failures` machinery entirely; that machinery exists only on the
`drain()` path (`workers > 1`). Not a bug -- every real caller either uses `workers=1`
deliberately serial or goes through `drain()` -- but a real behavior worth pinning rather
than leaving to be rediscovered by surprise. Once that was in hand, `solid_render`'s real
OpenSCAD backend branch turned out to be cheap enough to test for real too: a trivial
`solid2` cube renders through a genuine `openscad` subprocess in about 0.13 s, so real
end-to-end tests (correct volume/area, the geometry-version stamp header, a real preview PNG,
and a real resume-skip across two real calls) cost less than the fakes they replace would
have implied. `sweep_session`/`main` are tested with the actual per-part rendering faked
(`solid_render` for `sweep_session`, `_run_all_sweeps` itself for `main`, since a real full
sweep is hundreds of parts and explicitly out of bounds per this project's own sweep-cost
guidance) while everything around it runs for real: queue/resume/preview state set and
restored on both clean exit and an exception, the preview backfill (including a real
deferred-preview scenario read back off `_PREVIEW_BACKLOG`), backend restoration on both a
clean return and a raised exception, and every branch of the printed summary (`freecad` vs.
`openscad` banners, the resume note, `output_dir` resolution). 708 tests total across all of
`tests/`, all green, `ruff check` clean.

**IP-TEST-2 is complete**, with one deliberate, permanent exception: `freecad_render`'s own
subprocess branch stays covered only through the fake-`RenderQueue` contract test from the
first pass. A real `freecadcmd` call measured at ~8 s even for the smallest real bulkhead --
sixty times OpenSCAD's ~0.13 s -- which is the wrong side of the line for a tier whose whole
purpose is staying fast; unlike `RenderQueue`/`solid_render` above, trying it for real here
would not have paid for itself. That gap is exactly what IP-TEST-7 through IP-TEST-10 (the
`freecadcmd` tier, where the cost is already paid by every check) exist to close instead.

**IP-TEST-3's first pass, 2026-09-22.** `tests/test_geometry_version.py` (18 tests) covers
`geometry_version.py` completely -- `_digest`, `_resolved`, `_closure`, `_scad_dependencies`,
`_python_dependencies`, `scad_version`, `freecad_version`, `clear_cache` -- including the
module's own stated tradeoffs (over-sensitive to a comment edit, keyed by basename so a
move and a rename are treated oppositely, cached in-process so an uncleared edit is
invisible). `tests/test_fillet_intent.py` (11 tests) covers `fillet_intent.py`'s pure
geometry -- `point_to_line_45`, `derived`, and all four tangency-claim functions
(`outer_corner_fillet`, `greeble_to_web_fillet`, `web_to_bolt_fillet`,
`bolt_flange_fillet`) -- checked against a real `derived_parameters()` ->
`bulkhead_parameters()` -> `derived()` pipeline at one hand-picked configuration, holding
every claim to the module's own stated bound (`EPSILON`, 1e-9 mm) rather than a looser one.
`variants()` and `main()` (CLI/subprocess-shaped) are out of scope for this pass. 147 tests
total across all of `tests/`, all green, `ruff check` clean. `drawing_families.py` (1132
lines), `check_derivation.py` (695 lines) and `requirements.py` (762 lines) remain --
substantially larger than the two done here, and the next slice of this item.

**IP-TEST-3's second pass, 2026-09-22.** `check_derivation.py` and `requirements.py` are
both, in effect, already their own comprehensive checkers -- `check_derivation.check(kind)`
re-derives every design relation against the real `variant_param/` corpus, and
`requirements.check_register()`/`check_document()` verify the requirement register's own
structural properties. What was actually missing for both was not validation logic but
that nothing ran it as part of the committed test suite (`python check_derivation.py` /
`python requirements.py` had to be invoked by hand). `tests/test_check_derivation.py` (19
tests) wires `check(kind)` in for every real sweep kind (`corner`, `bulkhead`,
`boom_bulkhead`, `nose`, `tail` -- 560 real variants, ~0.5s, asserting zero complaints for
each) and `check_traceability()`, plus direct unit tests of `_floored`, `_extrusions`,
`agrees`, `check_coverage`, `derive_all`, `constants`, and `label`.
`tests/test_requirements.py` (18 tests) wires `check_register()`/`check_document()` in
against the real register, plus `resolve`/`order`/`coverage`, plus -- going further than
"the real data currently passes" -- a battery of tests against a small synthetic, broken
register (via `monkeypatch.setattr` on `rq.REGISTERS`/`rq.DESIGN`/`rq.ARCHITECTURE`) proving
`check_register()` actually detects each defect class it claims to: a dangling citation, a
citation to a disallowed tier, a sub-design requirement citing nothing, a design requirement
with neither a citation nor a rationale, a missing source, and a verifier naming a file that
does not exist -- a checker that always said "ok" would have passed the real-data tests too.
184 tests total across all of `tests/`, all green, `ruff check` clean. `drawing_families.py`
(1132 lines) is the one module left in this item's original cluster.

**IP-TEST-3's third pass, 2026-09-22.** `tests/test_drawing_families.py` (29 tests) covers
`drawing_families.py`'s correctness logic: `flatten`, `_identifiers`, `written`,
`sheet_rows`, `_sort_key`, `minimal_axes` and `factor` (via small synthetic fixtures,
including the "not a function of the declared axes" `RuntimeError` and the
constant/structural-zero/table split), `read_register`/`interface_fields` against the real
`dimension_scheme.md` register, `resolve` against the real corpus, and `topology_of` --
including a regression pin of the module's own headline finding that `end_bolt` and
`end_anchor` share one topology signature (they differ in exactly one number, not a
feature), that a cowling type's signature differs from an end type's, and that a field the
resolved object does not have at all reads as `'absent'` rather than `False`.
`check_register()` and `check_topology_fields()` -- already-comprehensive self-checks, like
`check_derivation.check()` and `requirements.check_register()` -- are wired in against the
real data for the same reason as those two: nothing ran them except a person invoking
`python drawing_families.py` by hand. Deliberately not covered: `block_columns`,
`sheet_blocks`, and the rest of the sheet-layout/page-rendering machinery past `factor()`
-- that is presentation logic (how a table's columns are laid out on a page) rather than
the correctness logic (which axes a field follows, which family a variant belongs to) this
pass focused on.

**IP-TEST-3 is complete for the cluster's original scope** -- all five listed modules now
have committed coverage of their core logic. 213 tests total across all of `tests/`, all
green, `ruff check` clean.

**IP-TEST-4, 2026-09-22.** Reading the whole `draw_*.py` cluster before writing anything
found that eight of its eleven modules (`draw_bolt_flange_fillet.py`,
`draw_dimension_alternatives.py`, `draw_corner_joint.py`, `draw_flat_offset.py`,
`draw_flange_chamfer.py`, `draw_fillet_scope.py`, `draw_sheet_alternatives.py`,
`draw_register_rows.py`) are one-off SVG-evidence generators, each built to answer one
specific (mostly already-resolved) open question -- `OQ-DES-B14`, `OQ-DES-D2`,
`OQ-DES-B13`, `OQ-ARCH-13`, `OQ-ARCH-14`, `OQ-DES-D5`, `OQ-DES-D7` -- and depended on by
nothing else in the codebase. Writing unit tests for those now is the same low-value move
`spike_*.py` triage (IP-TEST-9) exists to head off: proportionate effort on code whose
useful life is largely already spent, rather than a gap being glossed over. The remaining
three -- `draw_set.py` (IP-FC-114, the drawing-set driver), `draw_variant_set.py`
(IP-FC-84, the build-kit driver), and `branching_dimensions.py` (IP-FC-99, a real analysis
tool) -- are genuinely live and reusable, and got real coverage: `tests/test_draw_set.py`
(10 tests: `representative`'s nearest-U selection including its tie-breaks, `clear`'s
artifact removal via `tmp_path`, `export_for`'s real pure-Python parameter export),
`tests/test_draw_variant_set.py` (10 tests: the same `clear`/`export_for` contract this
module deliberately duplicates rather than imports, `pair_dir`, and a
`check_topology_fields`-style structural self-consistency check on `PARTS`/`FIXED_PANEL`),
and `tests/test_branching_dimensions.py` (18 tests: `axis_values`, `_tally`, `_verdict`,
the `_watching` call-interception mechanism directly, and `sweep()`/`uninstrumented()`
against the real corpus -- including that `sweep()` restores `check_derivation.max`/`.min`
to the plain builtins even when a relation raises partway through, the one safety guarantee
the whole monkeypatch-based instrument depends on). Also added
`tests/test_sheet_naming.py` (6 tests) for `freecad/sheet_naming.py`: it lives under
`src/Fuselage/freecad/` by location but, per its own module docstring, has no FreeCAD
import specifically so the venv-side `draw_set.py`/`draw_variant_set.py` can import it too
-- a real exception to "everything under freecad/ is freecadcmd-tier," worth flagging for
whoever picks up IP-TEST-7/8/10 later, in case there are others. None of the tools this
pass covers shell out to `freecadcmd` or the OpenSCAD binary in the parts tested;
`draw()`/`build_set()`/`main()` (subprocess orchestration) are deliberately out of scope,
the same class of thing IP-TEST-2 already deferred. 257 tests total across all of `tests/`,
all green, `ruff check` clean.

**IP-TEST-5's first pass, 2026-09-22.** Unlike IP-TEST-4's cluster, every module in this
one is genuinely live verification infrastructure -- no one-off/spike triage needed here.
`tests/test_mesh_stats.py` (33 tests) covers the module underlying every geometry
comparison in the project (already depended on by IP-TEST-2's `render_definition` tests via
`is_complete`): `load_triangles` for both binary and ASCII STL plus both formats'
truncation detection, `mesh_stats` and `canonical_hash` (order-invariant, winding-
preserving) against a hand-verified unit-cube fixture (12 triangles, volume 1.0, area 6.0)
written as real STL bytes, `same_geometry`'s hash-first short-circuit and its deliberate
disregard for triangle-count differences (OQ-ARCH-16), `describe_difference`, `bbox_tol`,
`u_of_name`, and `is_complete`. **Found and fixed a real discrepancy**: `volume_offset`'s
docstring promises `None` "when either measurement predates the `area` key," but the code
only ever checked the first argument's -- an asymmetric, order-dependent bug
(`volume_offset(a, b)` could disagree with `volume_offset(b, a)`) latent because the one
real caller (`compare_backends.py`) always passes two freshly-computed `mesh_stats()`
results that carry `area` together or not at all. Fixed to check both, matching the
documented contract, alongside the test that caught it -- the same Red-then-fix shape as
`decode_bulkhead_type` in IP-TEST-2. `tests/test_baseline_ledger.py` (8 tests) and
`tests/test_baseline_manifest.py` (9 tests) cover OQ-ARCH-15's departure-tracking pair
against real STL files and real manifest/ledger JSON under `tmp_path` (moved / missing /
added / unreadable / accepted-departure cases) -- mocking would have tested nothing here,
since both modules' whole job is measuring real geometry. 307 tests total across all of
`tests/`, all green, `ruff check` clean. Remaining in this item: `compare_backends.py` (724
lines, the largest single module left in the whole plan), `surface_distance.py`,
`stl_preview.py`, `brep_snapshot.py`, `scad_snapshot.py`, `params_snapshot.py`,
`verify_sweep_change.py`, `verify_scad_change.py`, `verify_drivers.py`, `sweep_check.py`.

**IP-TEST-5's second pass, 2026-09-22 -- the item's remaining nine smaller modules.**
`tests/test_surface_distance.py` (26 tests) covers `surface_distance.py`'s sampling and
closest-point kernel: `surface_tol`, `sample_surface`'s area-weighted sampling and its
zero-area fallback, `unique_vertices`' rounding-precision merge, `sample_points`' vertex/area
split and reported coverage fraction, and `distances_to_mesh`/`_closest_on_triangles` against
a single right triangle at hand-computed coordinates covering every clamp region (interior,
each of the three edges, a vertex, and forcing the `CHUNK`-boundary loop). `tests/test_stl_preview.py`
(36 tests) covers the whole software rasterizer: `load_stl`/`_load_ascii_stl`'s format
detection and truncation errors, `_rotation`'s orthogonality, `_shift`, `_smoothstep`,
`_occlusion` and `_edge_strength` against hand-built z/normal buffers, and
`render`/`_render_at`/`_rasterize` end to end with `rot_deg=(0,0,0)` (camera space equals
world space, so the front/back winding sign was worked out by hand rather than trusted from
the code), plus a byte-level `write_png` round trip decoded without any PNG library. **Found
and fixed a real bug** in `_shift`: a shift magnitude at or beyond the array's own size (the
occlusion radius reaches 16 px) raised `ValueError` from mismatched slice shapes instead of
correctly returning all-fill, because a negative Python slice stop was silently reinterpreted
as counting from the end rather than as "no elements" -- latent on any render narrower or
shorter than 32 px with occlusion enabled, caught by the first test against a small buffer.
Fixed by clamping the shift to the array's own size before slicing, the same Red-then-fix
shape as `decode_bulkhead_type` and `volume_offset`. `tests/test_brep_snapshot.py` (16
tests), `tests/test_scad_snapshot.py` (10 tests) and `tests/test_params_snapshot.py` (22
tests) cover the three snapshot/compare tool pairs -- real zip archives for the `.FCStd`
reader, and the real sweep machinery (restricted to one fast sweep kind via a monkeypatched
`SWEEPS`) for `capture()`'s monkeypatch-and-restore contract, exactly as `render_definition`'s
fakes did in IP-TEST-2, so nothing ever reaches OpenSCAD. `tests/test_verify_sweep_change.py`
(14 tests) and `tests/test_verify_scad_change.py` (15 tests) cover the pure sampling logic
(`sample_names`/`sample_parts`, including the `boom_bulkhead`-must-not-starve-`bulkhead`
exclusion rule) plus `build_sample`/`verify` exercised with `_render`/`fv.solid_render` faked
out so no OpenSCAD process is ever spawned, and `compare()`'s full geometry-comparison branch
set including the case its own docstring names: volume and bbox agree but the surface moved
(forced via a monkeypatched `same_geometry`, since constructing a real mesh pair with that
exact property is what `mesh_stats`'s own suite already exists to cover).
`tests/test_verify_drivers.py` (15 tests) covers `find_drivers`/`render` directly and reaches
the module's real classification logic -- which lives entirely inside `main()`'s nested
`run()` closure with no standalone function to call -- through `main()` itself with the
module-level `render` faked, including the regression the module's own comment names: a
broken driver that also produces empty output must be reported FAILED, not waved through as
a harmless aggregator, because of the `not notes` guard. `tests/test_sweep_check.py` (26
tests) covers `scaling_family`/`part_id`/`find_stls` directly, `check_families` against
synthetic relative-path strings (the function never reads the path half of its `entries`),
and `check_integrity`/`check_reference` against real STL fixtures. 466 tests total across all
of `tests/`, all green, `ruff check` clean (save the same two pre-existing,
deliberately-documented `os.path.join` exceptions in `test_geometry_version.py`).
`compare_backends.py` (724 lines) is the one module left in this item.

**IP-TEST-5's third pass, 2026-09-22 -- `compare_backends.py`, closing out the item.**
`tests/test_compare_backends.py` (45 tests) covers the module the project's own docstring
calls out as answering "the migration's actual question" rather than merely "did this one
change alter geometry." Direct unit tests for every pure function: `sweeps_for`/
`_drivers_for` (including that all three `nose_*` kinds and both `tail_*` kinds dedupe to one
driver call each), `bbox_tol`, `u_of`, `kind_of` (the longest-match-first rule that keeps
`boom_bulkhead`/`nose_cowl_shell`/`tail_shell` from being mis-read as their shorter
substrings), `used_freecad`, and `split_failures`. `wanted_parts` is exercised against the
real sweep machinery restricted to one fast kind, in the same style as `capture()` elsewhere
in this item. `unusable_dirs` and `ensure_wiped` are tested against real filesystem state,
with the Windows delete-pending case's *fallback* message path (an ordinary directory that
merely failed to delete) simulated by faking `shutil.rmtree` rather than needing to actually
hold a handle open. `report_builds` is tested against a hand-built sidecar-file tree
(`.stl.json` for FreeCAD-built, `.stl.scad` for a silent fallback, absence for missing or
refused) covering every classification branch and both return codes. `compare()` -- the
module's core -- is tested against hand-built STL pairs covering every kind category: a
bbox-preserving "dented cube" fixture (one non-extremal corner vertex pulled inward, verified
numerically to leave the bounding box exactly unchanged) isolates the volume criterion from
the bbox criterion, and a rigid translation (which leaves volume exactly invariant) isolates
the bbox criterion from the volume one. This proved the two-tier tolerance selection
directly: the identical volume delta that fails an exact kind at a tight `tol_exact` passes
the same pair once judged as a filleted kind under a loose `tol_filleted`, exactly the
OQ-DES-B9 mechanism the module exists to implement. Also covered: the freeform kind's fixed
`TOL_FREEFORM`, the shelled kind's offset criterion (`TOL_OFFSET`, via
`mesh_stats.volume_offset`) both failing and passing, the `offset is None` "no surface area
recorded" refusal-to-assume-agreement (forced via a monkeypatched `volume_offset`, since a
fresh `mesh_stats()` call cannot itself produce that state today), a part missing from one
side, an unreadable mesh, a part that fell back to OpenSCAD (no `.stl.json` sidecar) being
skipped rather than failed, an unported part being skipped rather than failed, and the
"nothing compared" case when every wanted part is skipped. `render()` and `main()` (real
OpenSCAD/FreeCAD subprocess orchestration and CLI/scratch-directory wiring) are out of scope,
the same class of thing every other render-shaped function in this plan has deferred.

**IP-TEST-5 is complete.** All twelve modules in the verification/comparison cluster now
have committed unit coverage. 532 tests total across all of `tests/`, all green, `ruff check`
clean (save the same two pre-existing, documented `os.path.join` exceptions).

**IP-TEST-6, 2026-09-22.** Before writing anything, `scan_octant_micro.py` and
`fuselage_splode.py` were read and triaged out of scope, the same judgment call IP-TEST-4
made for the eight one-off `draw_*.py` generators: `scan_octant_micro.py`'s own docstring
scopes it to re-checking one specific historical claim (IP-FC-67, "is the octant's
sub-micron geometry still there") and nothing else in the repository imports it as a
library; `fuselage_splode.py` has no docstring, hardcoded magic-index lookups into a
specific ordering of `all_combinations` (`k_panel_variant = 7 # len 9`), commented-out debug
prints, and its only reference anywhere in the tree is a scratch notebook
(`test_fuse.ipynb`) -- inherited adoption-phase scaffolding, not production code. The
remaining nine modules all got real coverage. `tests/test_make_sheet_template.py` (25 tests)
covers the SVG title-block generator -- `check_rows()` is wired in as a real self-check
against the committed constants (a regression pin for the module's own stated failure mode:
a caption/value overlap inside a title-block cell that no other check would ever see), and
because `out_path()` returns a hardcoded path into the real committed template,
`main()`'s non-`--check` write path is tested only via a monkeypatched `out_path` pointed at
`tmp_path` -- no test here ever touches the real `fuselage_ansi_a_landscape.svg`.
`tests/test_oml_export.py` (21 tests) covers the OpenVSP OML export end to end against real
geometry: OpenVSP turned out to be genuinely installed and importable on this machine (just
not on the venv's default `sys.path`, exactly the gap `import_vsp()`'s own search bridges),
so `import_vsp`/`list_model`/`export` are exercised for real against the real committed
`.vsp3`, writing into `tmp_path` rather than the real committed `oml/` tree -- the same "test
the real thing when it is genuinely available" call made for `freecad_render.py` below.
`tests/test_render_variant.py` (13 tests) and `tests/test_export_parameters.py` (22 tests)
cover the one-part render/export entry points against the real corpus (real valid and real
invalid `(U, type, panel)` combinations, confirmed against `fv.family_is_valid` first rather
than invented); `export_parameters.check_names`'s two failure branches are exercised by
monkeypatching `bulkhead_parameters` to inject an unknown/missing name, the same
defect-injection style IP-TEST-3 used for `requirements.check_register()`. The one branch
deliberately left uncovered in `render_variant.main()` is a genuinely valid combination
reaching an actual render, which constructs a real `fv.RenderQueue` -- out of scope for the
same reason IP-TEST-2 left `RenderQueue`'s own thread-pool behavior uncovered.
`tests/test_freecad_render.py` (19 tests) covers path resolution, `definition_text`
(real, deterministic, byte-for-byte -- what `--resume` depends on), and the IP-FC-69
`FCSTD_MAX` path-length regression; FreeCAD 1.1 is genuinely installed under
`%LOCALAPPDATA%\Programs` on this machine, so `freecadcmd_path`/`freecad_gui_path` are
checked against that real state as well as against monkeypatched failure paths.
`tests/test_render_sheets.py` (14 tests), `tests/test_sweep_variant_sets.py` (9 tests) and
`tests/test_soak_shell_variants.py` (17 tests) cover three render/batch-job orchestrators
whose expensive step (a GUI FreeCAD subprocess, a `freecadcmd` build, a multi-hour soak) is
always faked out while everything around it -- job planning, manifest/resume logic, JSON
structure, print formatting -- runs for real; `sweep_variant_sets.py`'s own docstring prices
a real run at ~2.5 hours and `soak_shell_variants.py`'s at ~5 hours, so neither is ever
actually invoked. `tests/test_audit_call_args.py` (6 tests) covers the one module in this
item with no function API at all -- a bare top-level script that runs its whole audit as
import-time code -- by invoking it as a real subprocess (cheap: it is pure Python with no
FreeCAD/OpenSCAD dependency, unlike every other subprocess this plan defers) against both the
real committed `.scad` corpus (clean, a regression pin) and a synthetic fixture reproducing
the exact historical bug shape it exists to catch (OQ-DES-B10's rotated call-site
arguments). 678 tests total across all of `tests/`, all green, `ruff check` clean.

**IP-TEST-6 is complete.**

**IP-TEST-7's first pass, 2026-09-22.** A background Explore agent was launched to audit
`check_*.py` coverage against every function in the core geometry module list and failed on
a session-wide rate limit before producing a report; rather than wait on a retry, this pass
picked the smallest, most self-contained module in the list -- `plane2d.py` (279 lines, 13
functions, confirmed to have no coverage at all, not even indirect, before this) -- and
wrote `check_plane2d.py` against it directly, to establish a real, working template for the
rest of the item rather than leave the audit as the only progress.

Every primitive got a hand-verified, closed-form expected value rather than a comparison
against another measurement of the same kind: `disc`/`rect` against circle/rectangle area
formulas; `union` against two overlapping and two disjoint rectangles (sum minus the exact
overlap, and sum with no shared edges, respectively); `offset` against a rectangle's outward
(rounded-corner) and inward (sharp-corner) growth; `erode_difference` against the
erosion/dilation identity for axis-aligned rectangles; `fillet_inner`/`fillet_outer` against
a bare rectangle specifically, which isolates each to the one corner case it has a closed
form for (opening rounds convex corners and ignores concave ones, closing is the reverse, and
a rectangle has four convex corners and none concave). `fragmented`, `area`, `enclosed`, and
`report` are exercised directly, including `report`'s own pass/fail verdict on both a correct
and a deliberately wrong reference.

**Two real defects were found and fixed while deriving those expected values, both in this
check itself rather than in `plane2d.py`** -- worth recording because they are exactly the
kind of mistake this project's TDD push exists to catch before it reaches a committed
assertion: (1) an outward offset's dilation was first modelled with sharp corners; OCCT's
`Part::Offset2D` rounds them (confirmed by the `offset` check two tests earlier in the same
file), so the `erode_difference` expected value was wrong until the dilation term was
corrected to include the same quarter-circle arcs. (2) `fillet_inner` was first tested
against an L-shape on the theory that "inner" fillets a concave corner; morphological opening
(erode-then-dilate) actually rounds *convex* corners and leaves concave ones untouched --
`fillet_outer` (dilate-then-erode, a closing) is the one that fills concave corners, exactly
backwards from the initial assumption. Both were caught by the check disagreeing with its own
prediction, not discovered by inspection, and both are now recorded as comments in
`check_plane2d.py` itself so the correction is not silently lost.

**A third, separate defect was found in production code while reading the `part_*.py`
cluster for the audit** (`part_corner.py`/`part_end.py`/`part_middle.py`/
`part_transition.py`, IP-FC-5's Part::-primitive build of the corner): each already builds
its part and calls `corner_common.report()` to compare its volume against a real OpenSCAD
reference -- but `report()` only ever printed the delta, with no tolerance, no verdict, and no
return value, so every one of these four scripts exited 0 regardless of whether the volume
actually matched. A real regression here was visible only to someone reading a percentage by
eye -- precisely the "ad hoc verification" this whole plan exists to eliminate, in code that
looked, at a glance, like it already had a check. Fixed: `report()` now takes a `tol`
(defaulting to `1e-4`, matching `check_tree.py`'s own bar for the same Part:: corner, of
which these four are the static-port ancestor), requires a valid single-solid shape, prints a
PASS/FAIL verdict, and returns it; all four callers' `main()` now propagate that as a process
exit code, with the same `sys.stdout.flush()`-before-`sys.exit()` pattern documented below.
Verified by re-running all four for real: all pass, deltas 0.0004% to 0.0021%, well inside
tolerance -- a genuine Green confirming the fix did not just move the false-pass somewhere
else.

**A real, reusable freecadcmd hazard was hit and documented while getting `check_plane2d.py`
itself to run.** `sys.exit(main())` at the bottom of the entry-point guard produced *no
output at all* under `freecadcmd check_plane2d.py` -- not even a traceback -- despite `main()`
genuinely running and printing its full report (confirmed by importing the module from a
throwaway wrapper script and calling `.main()` directly, which showed the real output).
`check_derived_geometry.py` already carries the fix and its own explanation in a comment
(`sys.stdout.flush()` before `sys.exit()`, because a `sys.exit` with buffered stdout loses it
entirely under `freecadcmd`'s embedding of Python) -- this pass just did not read it first.
`check_plane2d.py` and all four `part_*.py` fixes above now follow that pattern; any future
`check_*.py` in this item should copy it from the start rather than rediscover it.

**`flange_base.py` and `flange_boss.py` (IP-TEST-7, next pass): same silent-pass bug class as
`corner_common.report()`, found in two more places.** Both modules already had their own
`main()` acting as a de facto check script (each computes a volume delta against an OpenSCAD
reference and prints it) -- so the actual gap was not "no coverage," it was that neither
delta was ever compared to a tolerance or turned into a return value. `flange_base.main()`
printed `delta`/`%` with no verdict at all; `flange_boss.main()` went further and built a
`checks` list per part (`INVALID`, `solids=N`, `VOLUME`, `SIGN`) but never aggregated it into
an exit code, so a script that had just printed `VOLUME` in its own output still exited 0.
Fixed the same way as `corner_common.report()`: both now compute `ok`/`all_ok`, print a
PASS/FAIL line, `return 0 if ok else 1`, and use the flush-before-`sys.exit()` entry-point
guard. Confirmed the fix is load-bearing, not another silent pass, by forcing a wrong
reference value in each and checking the exit code actually goes nonzero (it does, `1` in
both cases) before restoring the real values.

While reading both modules for the audit, found two further branches with **zero** coverage,
not merely an unenforced one: `flange_base_interconnect()` (the `is_interconnect` branch
`bulkhead_positive.py` calls instead of `flange_base()`) and `flange_boss(doc,
make_web=False)` (the branch used for an interconnect's mirrored top half, no chamfer fuse).
Neither has a `ref_*.scad` to compare against, so each is checked against a hand-derived
closed form instead, same pattern as `check_plane2d.py`: the interconnect variant is two
non-overlapping boxes (`288 + 202.2890625 = 490.2890625`, confirmed exactly against the real
build); the `make_web=False` boss is a plain quarter cylinder (`pi * r^2 * h / 4`). Both new
checks are folded into their module's overall exit code. All four checks (the two existing
OpenSCAD-reference ones, now enforced, and the two new closed-form ones) verified PASS via
real `freecadcmd` runs.

**`web.py` (IP-TEST-7, next pass): same silent-pass fix on `bulkhead_web`'s existing OpenSCAD
check, plus a hand-derived closed form for `bulkhead_web_interconnect` (`bulkhead_positive.py`'s
`is_interconnect` branch), which had zero coverage before this.** The interconnect variant is
a polygon fused with a quarter-disk and cut by a fillet circle -- not simple boxes like
`flange_base`'s interconnect branch -- but three tangency identities that fall directly out of
how `ic_x_center`/`ic_y_end`/`ic_x_end` are solved in the module's own docstring make it
tractable by hand: (1) the polygon's closing vertex lies exactly on the ray from the origin
through the fillet centre (by construction, it is that point scaled by
`ic_big_r / (ic_big_r + web_fillet_radius)`), so the polygon/quarter-disk overlap is exactly
a circular sector; (2) `web_y_mid - step_y == web_fillet_radius` by definition, so the fillet
circle is exactly tangent to the adjacent horizontal edge at the vertex before it, meaning
that edge is a radius of the circle, not merely near it; (3) the same scale factor puts the
polygon's closing vertex at exactly `web_fillet_radius` from the fillet centre too, so the
other edge leaving that vertex is also a circle radius. Both edges leaving the vertex being
exact fillet-circle radii means the fillet cut removes exactly the sector spanning the
polygon's own interior angle there, with nothing else to clip against. Closed form: `polygon
(shoelace) + quarter_disk (pi/4 r^2) - overlap_sector - fillet_sector`, verified against the
real build to 10 significant figures before being written into `web.py` as
`_interconnect_ref_area()`. Same forced-wrong-reference negative-control check applied as
above; exit code correctly goes nonzero.

**The `boom_*.py` cluster (IP-TEST-7, next pass): the same silent-pass bug, five more times,
in a cluster that had already standardized on the right helper.** `boom_web.py`, `boom_webs.py`,
`boom_oml.py`, and `boom_bulkhead.py` all already call `plane2d.report()` (fixed and correct
since `check_plane2d.py`) and correctly AND the per-shape results into a local `ok` -- but none
of the four ever returned or exited on it, so all four always exited 0 regardless of a printed
`MISMATCH`. `boom_key.py` was one step further behind: it hand-rolled its own partial version
of `report()` (delta and bbox printed, FRAGMENTED/TRUNCATED checked) but never compared the
delta to a tolerance at all and built no verdict of any kind; rewritten to just call
`plane2d.report()` like the rest of the cluster, removing the duplicated logic rather than
patching it. All five now `return 0 if ok else 1` with the flush-before-`sys.exit()` guard.
Verified for real: all five PASS as committed, and a combined negative-control run (forcing one
reference wrong in each of the five simultaneously) confirmed all five exit codes go nonzero.
No branch in this cluster was found fully uncovered the way `flange_base_interconnect`/
`flange_boss(make_web=False)`/`bulkhead_web_interconnect` were -- `boom_bulkhead.py`'s own
`VARIANTS` already exercises both `offset_single` and `center_single`, and its `LOWER_REFS`
loop already covers the `boom_make_lower_web` path.

**The `bulkhead_*.py` cluster (IP-TEST-7, next pass): a mix of the same bug and, for the first
time in this item, files that were already correct.** `bulkhead_web.py` had the familiar
`plane2d.report()`-computed-but-never-returned gap. `bulkhead_tree.py` had a sharper version of
it: the OQ-DES-B12 clearance checks DID raise on failure, but via a bare `raise SystemExit(1)`
inside `main()` with no `sys.stdout.flush()` first -- the exact freecadcmd stdout-loss hazard,
live in an actual failure path, not just a hypothetical one -- and on top of that the volume
delta against `REF_TOOL` was printed but never checked against a tolerance at all. Both fixed:
folded into one `ok`, returned through the standard flush-before-`sys.exit()` guard.
`bulkhead_positive.py`, `bulkhead_cuts.py`, `bulkhead_full.py`, and `bulkhead_section.py`,
by contrast, were **already fully correct** -- real exit codes, already flushed, in
`bulkhead_full.py`/`bulkhead_cuts.py` even carrying the exact hazard-explaining comment inline
already. `bulkhead_full.py` and `bulkhead_section.py` need an external `params.json`
(`export_parameters.py`'s output) to run at all; confirmed this is an established, accepted
convention in this tier by checking `check_tangency.py`, which works the same way, so a bare
`freecadcmd bulkhead_full.py` printing usage and exiting 0 is correct behaviour, not a gap.

Two real branch-coverage gaps closed with lightweight **structural** checks (valid, single
solid, nonzero volume -- not a full closed form) rather than more hand-derivation: the
constituent pieces these two assemble are already unit-tested elsewhere, so re-deriving an
assembled closed form here would be duplicated effort for little new signal. `bulkhead_positive
.flange_positive()`'s `is_cowling`/`is_interconnect`/`make_web=False` combinations had zero
coverage (only the default combo was ever built); `bulkhead_cuts.cuts()`'s `is_cowling`/
`is_interconnect` branches were genuinely uncovered too, not merely indirectly covered --
`bulkhead_section.py`'s own `main()` honestly documents (rather than silently passing) that it
does not check volume/bbox for either type, only valid/solids=1, so this closes a gap that
module deliberately left open. All new structural checks folded into their module's overall
exit code and verified PASS for real.

**`corner_tree.py`/`corner_common.py` (IP-TEST-7, next pass): already the most heavily
indirectly-exercised modules in the tier (every other module in this whole item calls their
`_box`/`_cyl`/`_owned`/`tag()`/`build_sheet` helpers), but `check_tree.py` -- the one script
whose whole job is directly checking `corner_tree.emit()`, the actual corner assembly -- had
the sharpest-consequence bug this audit has found so far: a genuine "false pass".** The
`regen_U*.stl` reference meshes it compares against are build artifacts and correctly not
committed (per the module's own docstring); on a clean checkout none exist, every one of the
four `TABLE` sizes is skipped, `failures` stays empty because nothing ran, and `main()` printed
"regenerate: 0 failures" and exited 0 -- indistinguishable from every size having actually been
verified. `README.md`'s own Verification table promises the opposite in so many words: "they
skip any size whose reference is missing rather than reporting a false pass." The code did not
keep that promise; confirmed by running it bare (0 references present) and watching it print
"0 failures" and exit 0. Fixed by counting checked rows separately from skipped ones and
treating zero checked rows as a failure. Rather than fix this in the abstract, rendered all
four real reference STLs for real (`openscad ... ref_regenerate.scad` at each of `variants
.TABLE`'s four sizes, per the README's own documented command -- OpenSCAD genuinely installed
on this machine, consistent with this session's "test the real thing when it's genuinely
available" pattern) and confirmed `check_tree.py` now genuinely checks all four (deltas
0.0005%-0.0065%, well inside tolerance) and exits 0 for real, then re-hid the references with
a monkeypatch and confirmed the exit code goes back to 1 -- so the fix is verified against both
the true-positive and the true-negative case, not just made to look right. Two further gaps in
the same `main()`, printed but never checked, fixed the same pass: the post-reload volume
against the pre-save volume (a save/reload that silently changed the shape is exactly the kind
of regression this section exists to catch), and the derived-part demo's bracket volume, which
must be strictly positive at every size or the demo is not actually following the tip. All
folded into one return code with the standard flush-before-`sys.exit()` guard.

**New: `check_corner_common.py` (IP-TEST-7), the first dedicated unit-level check in this
whole tier for `corner_common.py`'s own functions rather than for a part they help build.**
`half_shape`/`section`/`prism`/`report` are already exercised for real by `part_end.py`/
`part_middle.py`/`part_transition.py`/`pd_middle.py`. What had never been exercised is the
FAILURE path of the functions whose own docstrings say the failure they guard against is
silent: `is_literal` (IP-FC-41's literal-vs-expression distinction), `check_unseeded`
(IP-FC-53 -- a parameter file missing a row silently built the module's own reference value
under the variant's name), `merge_params` (its conflicting-alias `RuntimeError`, described as
"kept as a permanent assertion... because the failure is silent" but never actually triggered
in any committed run, since every real parameter set is internally consistent by construction),
and `check_seed` (its drift-detection branch, likewise never hit for real). 24 checks, covering
both the success and the failure path of each, plus `is_entry_point`/`script_args` against a
controlled `argv` (the real `argv` only ever demonstrates one branch per run). One self-caught
bug in the check itself, not in the source, worth recording: the first draft faked a PARAMS
source module with `class _ModA: __name__ = 'mod_a'`, and `merge_params`'s conflict message
came back with the real Python class name instead of the intended fake one -- `__name__` set
in a class body does not shadow `type.__name__` (a data descriptor on the metaclass always
wins over the class's own dict). Fixed by using `SimpleNamespace` instead, which matches how a
real imported module's `__name__` actually behaves (an ordinary instance attribute). All 24
checks verified PASS for real, and a forced-wrong assertion confirmed the exit code goes
nonzero.

**`oml_blank.py` (IP-TEST-7, next pass): audited, already fully correct, no fix needed.**
`main()` already returns a real exit code, already orders its `sys.stdout.flush()` correctly
(inside `main()`, before the `return` that `raise SystemExit(main())` then consumes --
functionally identical to the flush-before-`sys.exit()` pattern used elsewhere, just spelled
differently), and already checks NOT CLOSED / solids count / bbox scale. Confirmed it runs for
real against the actual committed `vsp_nose.step`/`vsp_tail.step` surfaces (602 KB / 772 KB,
genuinely present in `src/Fuselage/oml/`) and passes: nose -0.0006%, tail +0.0012%.
`blank()`'s offset-before-scale composition (the one place this module's own docstring flags a
real ordering-bug risk, IP-FC-1/OQ-DES-CW1) is exercised via `cowl.py`'s real `offset_x_m =
-0.25` case rather than directly here -- left to the deferred `cowl_*.py` cluster rather than
duplicated.

**`fillets.py` (IP-TEST-7, next pass): the same silent-pass gap found one more time.**
`main()`'s per-tip `checks` list was correct but never aggregated into a return value, and
there was no flush-before-`sys.exit()` guard at all. Fixed the same way as everywhere else in
this tier. Verified for real: all four built fillets PASS (`GreebleToWebFillet` correctly
omitted, per its own documented 27-variant exception), and a forced-wrong reference confirmed
the exit code goes nonzero. `check_tangency.py`, which already exercises this module's
`_fillet_tangency_sketch()` directly and needs its own `params.json`, was already fully
correct -- audited, no fix needed.

**The `cowl_*.py` cluster audit (IP-TEST-7): started.** The six thin per-kind wrapper modules
(`cowl_nose_tip.py`, `cowl_nose_plate.py`, `cowl_nose_cowl.py`, `cowl_tail.py`,
`cowl_nose_cowl_shell.py`, `cowl_tail_shell.py`) were all already fully correct -- each
`main()` already returns a real exit code from `isValid()`/single-solid and already flushes
before `raise SystemExit(main())`. `cowl_tail_shell.py` also confirmed, by its own inline
comment, that IP-FC-137's `MIN_U` refusal floor was already retired 2026-09-21 (IP-FC-139/140/
141) once the underlying rib-cut defect was actually fixed rather than guarded around, closing
that thread referenced in this session's other open investigation.

**A real, previously-never-actually-exercised gap, found and closed: `bulkhead_full.py`'s
`is_cowling` and `is_interconnect` branches, and by extension `cowl_rim.py`, had no committed
fixture to run against.** `cowl_rim.py` deliberately has no standalone `main()` -- its own
docstring names `bulkhead_full.py`'s `is_cowling` branch as the binding check -- but that
branch needs an external `params.json`, and `out/` (correctly) keeps no fixtures committed, so
this path had, as far as the repository shows, never actually been run. Generated real fixtures
for real with `export_parameters.py` (the venv-tier tool, run via `uv run python` -- confirmed
`bulkhead 1.0 cowling_bolt 0mm` and `bulkhead 1.0 interconnect 3/16in` are valid combinations
via `render_variant.py`'s own listing) and ran all three `bulkhead_full.py` branches plus
`bulkhead_section.py`'s default for real: end/`is_cowling`/`is_interconnect` all PASS, matching
the exact reference figures already recorded in the module's own comments (`9854.8937182` for
`is_cowling`, "the first build that produced a valid single solid") -- confirming both that the
construction is still genuinely deterministic and that `cowl_rim.py`'s three shapes are correct
for real, not merely by unexercised assertion. One caveat found in passing: writing an
`export_parameters.py` output file to a UNC path (`\\mrhorse\...`) directly fails with
`FileNotFoundError` under plain `uv run python`, though the identical path works fine through
`freecadcmd`; routing through a local scratch path first and copying in was the workaround, not
a bug in the source worth chasing further.

**`cowl.py` (IP-TEST-7): audited, already fully correct, confirmed passing for real.**
`main()` already returns a real exit code, already flushes correctly (inside `main()`, before
`raise SystemExit(main())`), and already builds and checks all four kinds
(`nose`/`nose_nose`/`nose_plate`/`tail`) in one run with per-kind exception handling. Ran it
for real: all four PASS, exit 0. `check_cowl_nose_parametric.py` was likewise already fully
correct and confirmed passing for real (`cowl_tree.emit()` for `nose_plate`/`nose_tip` at two
`U` values each, plus an edited-in-place-vs-fresh resolve check). The four remaining
`cowl_tree.emit()` wrapper `main()`s not covered by that script
(`cowl_nose_cowl.py`/`cowl_tail.py`/`cowl_nose_cowl_shell.py`/`cowl_tail_shell.py`) had never
actually been run in this exact form before; ran all four for real and all PASS, including
`cowl_tail_shell.py`'s own ~140 s real build, which independently reconfirms IP-FC-139/140/141's
fix (ribs cut clean, `0.000000 mm3 left inside`).

**A real, significant finding: `check_cowl_interior.py`'s rib-gap acceptance check was a false
pass, caused by the already-documented "freecadcmd's exit code is unreliable" hazard rather
than a missing return value, and fixing it surfaced a genuine, 100%-reproducible failure in the
check's own methodology on current real geometry.** The module's own docstring calls the wall
and rib checks "the load-bearing ones" (IP-FC-17, the algorithm document's section 6 acceptance
tests). Running it for real (`--kind=tail_shell`, then `--kind=nose_cowl_shell`) showed the
real production build completes cleanly in both cases (`cowl_tail_shell.py`/
`cowl_nose_cowl_shell.py`'s own `main()`s, run separately, both PASS -- "ribs cut ..., 0.000000
mm3 left inside") but `check_cowl_interior.py`'s *own* `rib_gap()` function raises an uncaught
`ci.PreconditionFailed` ("P3") on its first real (non-synthetic) call, crashing the script
before it ever reaches its own final verdict line -- and `freecadcmd` swallows the uncaught
exception and exits 0 anyway (see [general.md](../guidelines/general.md) and the existing
memory of this exact hazard), so the crash read as a clean pass to anything checking only the
exit code. Fixed by wrapping that real (not the deliberately-synthetic P1/P2/P4 precondition
demonstrations later in the same function, which are correctly wrapped already) call in a
try/except that reports the failure into `bad` instead of crashing, so the script always
reaches its verdict line with a real, correct exit code.

Once fixed and re-run, the result is a genuine, reproducible **failure**, not a pass: **every
one of the 3 rib-gap stations checked, on both `tail_shell` and `nose_cowl_shell` (6/6 total)**,
fails the same P3 precondition -- a curve refit that is supposed to reproduce a real cross-
section within 0.005 mm actually moves it by 0.016-0.026 mm, consistently, at every station
tried on both parts. This is not the IP-FC-137 defect (that was in the production `cavity()`
rib-cut itself, already fixed by IP-FC-139/140/141, and the production build above confirms it
stays fixed) -- it is specific to `rib_gap()`'s own verification-only call to
`ci.eroded_body()`, a different code path from `wall_thickness()`'s direct polyline-distance
measurement, which has no refit step and passes cleanly at essentially every sample (233-240
of 240 within tolerance, at all 12 stations, both parts). Recorded here rather than
root-caused: understanding why the refit exceeds 0.005 mm on these specific real sections is a
real geometric investigation in `cowl_interior.py`'s curve-fitting code, adjacent to but
distinct from the `cowl_interior_surface.md` thread this session's other work touched, and is
Alex's call whether to promote it to a tracked `IP-FC-*` item, retune the 0.005 mm tolerance, or
something else -- not implied by anything here. What IS now true and load-bearing: the check
no longer lies about having passed.

Cross-checked whether this same unguarded-`PreconditionFailed` bug exists anywhere else:
grepped every call site in the tier. `build_part.py`'s `main()` already wraps it, with its own
inline comment already documenting this exact `freecadcmd` exit-code hazard (added 2026-09-12,
during IP-FC-137's own investigation -- "a `tail_shell` refused for being under IP-FC-137's `U`
floor printed its message and still exited 0"); `check_vase_printable.py`'s `report()` already
wraps it too. `check_cowl_interior.py`'s `rib_gap()` call was the one site that had not been,
which is now fixed to match the other two.

**`cowl_tree.py` and `cowl_interior.py` have no `main()`/entry point of their own -- both are
pure library modules** consumed by the six wrapper `cowl_*.py` files (all now confirmed run for
real) and by `check_cowl_interior.py`/`check_cowl_nose_parametric.py` (both confirmed correct
and passing, modulo the one real finding above). That removes the dominant bug class this whole
item has been finding elsewhere (a `main()` that computes a verdict and never returns it) as a
risk here by construction, and their combined real exercise across eight distinct callers is
comprehensive indirect coverage of both modules' core logic. Given that, and the size of what
remains (a full function-by-function NONE/INDIRECT/DIRECT audit across ~3100 lines with no
further `main()`-shaped bugs to find), this item is left `active` rather than `done` -- the
exhaustive audit the item's description calls for is not complete -- but the load-bearing gaps
(false passes, missing verdicts, and one genuine crashing check) that this pass exists to find
are closed everywhere they were found across the entire `freecad/` tier this session touched.

Remaining in this item: the rest of `cowl_tree.py` (1047 lines) and `cowl_interior.py` (2082
lines -- the two largest single modules in the whole freecadcmd tier) still needs auditing
function by function against the NONE/INDIRECT/DIRECT standard, the audit this item's own
description calls for and which the failed background agent did not get to finish.

**IP-TEST-8: audit started.** Of the seven modules the item names, five already had at least
one `check_*.py` covering them (`drawing.py`/`check_drawing.py`; `drawing_standard.py`,
`dimension_placement.py`/`check_dimension_placement.py`,`check_sheet_standard.py`,
`check_table_width.py`; `sheet_annotations.py`/`check_drawing.py`; `sheet_table.py`/
`check_drawing.py`,`check_table_width.py`). `sheet_naming.py` (45 lines) turned out to already
be covered too, just from the other tier -- `tests/test_sheet_naming.py`, from IP-TEST-4's
"plus `freecad/sheet_naming.py` (a shared dependency)". That leaves `render_pages.py`
(471 lines) as the one module with genuinely **no** coverage anywhere -- see below.

Audited all five existing TechDraw check scripts for the silent-pass bug class this whole plan
has been finding elsewhere: **none of them have it.** Every one already returns a real exit
code and already flushes correctly. Generated the real fixtures each needs to actually run
(`params.json` via `export_parameters.py`, `families.json` via `drawing_families.py`, both
venv-tier tools run through `uv run python`) and ran all five for real rather than trusting
that "already has the right shape" meant "currently passes."

**Two of the five turned up genuine, pre-existing, currently-real findings -- not test-coverage
gaps, since every check involved is already correctly wired, but real product-relevant defects
the existing (correct) tooling has been sitting on, apparently unexercised.** Confirmed neither
predates or was introduced by anything this session touched (`git log` shows no session
changes to `dimension_placement.py`, `sheet_annotations.py`, `drawing.py`, `drawing_standard.py`,
or `sheet_table.py`).

1. **`check_dimension_placement.py` genuinely fails (exit 1).** `VIEW_WIDTH_RECORDED_MM = 117.5`
   is a hand-recorded design constant, cross-referenced from `check_table_width.py`, with its
   own docstring explaining the pair exists exactly to catch this kind of drift (it already
   caught one such drift once before, 2026-09-07, when a text-width model fix moved this same
   figure from 84.5 to 117.5). It has drifted again: the real search now finds the family
   sheet's narrowest fitting view region is 116.5 mm, not 117.5. Isolated to the family sheet --
   the single-variant figure (136.0 mm, mentioned in a comment but not separately asserted in
   code) still matches. Not root-caused: `narrowest_view_width()` is a real geometric search,
   not a formula, so explaining the 1.0 mm shift needs tracing what changed in the family
   sheet's specific note/annotation content, which is real design-code archaeology, not test
   work. Recorded here rather than guessed at, per the same standard the 84.5 -> 117.5 fix set.

2. **`check_table_width.py` genuinely fails (exit 1), and reproduced directly through
   `check_drawing.py`'s own real sheet-build path, not just the abstract check.** Run for real
   against every family in the generated `families.json`, it reports 14 real failures, several
   severe: real family tables for `bulkhead end_anchor,end_bolt` (three separate panel
   thicknesses), `bulkhead cowling_anchor,cowling_bolt`, `bulkhead interconnect` (two
   thicknesses), `boom_bulkhead center_single`, and `boom_bulkhead dual,offset_single` all need
   between 17 and 232 mm more width than the 108.5 mm band beside the title block has -- plus
   `corner corner` at +56.2 mm. Two more failures are the check admitting its own blind spots
   in so many words ("accepts a cell wider than its column, so it cannot be read as evidence...",
   same for "a table drawn without rules"). Confirmed this is not an artifact of the abstract
   width check alone: ran `check_drawing.py --pass params.json families.json kind=bulkhead` for
   the `end_anchor,end_bolt` family specifically, and the real sheet-building path itself
   refuses, printing the same shortfall from first principles (the table needs 155.5-340.7 mm
   depending on lettering height tried, against the same 108.5 mm band) -- this is the real
   drawing pipeline correctly declining to produce a sheet it cannot lay out, not a check
   miscalibrated against a hypothetical. **A real, currently-unresolved defect affecting at
   least six real family/kind combinations, apparently never previously surfaced** -- not
   something to improvise a fix for (the resolution is a real design decision: widen the band,
   shrink the table, split it across sheets, or accept these combinations do not get a family
   table on the sheet), so left here as a clearly-characterized, reproducible finding for Alex
   to triage rather than guessed at.

(Testing note for future work on this item: piping a `freecadcmd` run through `grep`/`tail`
before reading `$?` captures the pipe's exit code, not `freecadcmd`'s -- caught myself doing
this twice while investigating the above, both times looking like a false pass on the first,
mis-piped read and resolving to the correct nonzero exit on a clean, unpiped re-run. Redirect
to a file and check `$?` immediately after the `freecadcmd` invocation itself.)

**`render_pages.py` (471 lines) is the one module in this item's list with no coverage at all,
anywhere, and it is a genuinely different, harder case than everything else this whole plan has
tested.** It cannot run under `freecadcmd` at all -- TechDraw's actual page renderer needs Qt,
which `freecadcmd` does not have, so this module is designed to run only under the full GUI
binary (`freecad.exe`, confirmed present alongside `freecadcmd.exe` on this machine) with
`QT_QPA_PLATFORM=offscreen`, driven by a `RENDER_JOB` env var naming a JSON job list and ending
in a hard `os._exit()` rather than a normal return (its own docstring explains why: closing the
window returns to the Qt event loop rather than ending the process). `render_sheets.py`
(IP-TEST-6, pytest tier) already spawns exactly this subprocess in production, but its own test
fakes that subprocess call out deliberately (documented, same reasoning as `freecad_render`'s
exception) -- so `render_pages.py` itself has never actually been exercised for real by
anything committed in this repository. Its own `main()` is already correct (real exit code,
`os._exit` makes the flush-before-exit question moot by construction) -- there is no
silent-pass bug to find here, only a real gap to close by actually running it, which needs a
real `.FCStd` document containing at least one built `TechDraw::DrawPage` as input.

**Closed for real.** Built a real single-variant corner sheet with `build_sheet.py --pass
params.json --pass kind=corner --pass out=...` (the production sheet-writing tool, run for
real under `freecadcmd`), wrote a `RENDER_JOB` job-list JSON naming it, and ran
`render_pages.py` for real under the full GUI binary: `QT_QPA_PLATFORM=offscreen
RENDER_JOB=<path> freecad.exe render_pages.py`. It genuinely succeeded -- "22 appearance
setting(s) applied", "107 view provider(s) shown", "403 scene item(s)", "rendered 1 of 1",
exit 0 -- and wrote real, valid `.svg` (57.5 KB), `.pdf` (157 KB, confirmed 1 page), and `.png`
(142 KB, 2200x1700 px, confirmed valid RGB PNG) files. Opened the PNG and confirmed it visually:
a correct, complete ANSI A drawing with its title block filled in (`CORNER`, scale 2:1),
correct dimension lines (4.86, 7.26, 10.00) and the five leader notes from the corner section
check, all legible and properly placed -- not merely "a file was produced" but "the file is the
drawing it is supposed to be." The startup log carries a wall of Qt/OpenGL warnings
("QOpenGLWidget is not supported on this platform", "No valid GL context found", an
"Unhandled std::exception... resource deadlock would occur" from `GUIApplication::notify`) that
look alarming on first read but are harmless offscreen-platform noise, not failures -- the real
output files and the correct rendered content are what settle it. This closes the one module in
this item's list that had zero coverage anywhere, and demonstrates the same "test the real thing
when it's genuinely available" principle established earlier in this session extends to a third
execution environment (`freecad.exe` with offscreen Qt), not just `freecadcmd` and the venv.

**IP-TEST-9: all 11 `spike_*.py` files triaged.** None is imported by any other module in the
tier (confirmed by grep across `src/Fuselage/freecad/*.py`), matching the item's own premise
that these are standalone exploratory scripts. Read every one and traced its conclusion to
where it landed in production:

| spike | superseded by |
| --- | --- |
| `spike_csg_tree.py` | `corner_tree.py`'s whole Part:: document-object CSG tree architecture |
| `spike_partdesign.py` | `pd_middle.py`/`pd_end.py`'s production PartDesign:: builds |
| `spike_hand_edit.py` | `check_tree.py`'s own "user bracket" derived-part demo |
| `spike_offset2d.py` | `plane2d.py`, with real coverage in `check_plane2d.py` (this session) |
| `spike_eps.py` | `corner_tree.py`/`bulkhead_cuts.py`'s eps/`mask_eps` handling |
| `spike_fillet.py` | `fillets.py`'s tangency-constraint sketches, checked by `check_tangency.py` |
| `spike_derived_part.py` | the tagged-generator/stable-tip convention, demoed in `check_tree.py` |
| `spike_sketch_expr.py` | `corner_tree._sketch()`, used throughout the tier |
| `spike_link.py` | the rejected alternative behind `spike_derived_part.py`'s conclusion |
| `spike_techdraw.py` | the whole drawing pipeline, confirmed working end to end in IP-TEST-8 |

**Ten superseded; kept in place rather than physically moved to `src/Fuselage/archive/`.**
Checked first whether anything currently links to them: `freecad_migration.md` and
`dimension_scheme.md` both carry real, clickable markdown links into several of these files as
historical evidence (e.g. `spike_techdraw.py`'s IP-FC-21 row). Moving the files would break
those without a corresponding link-fixing pass across both documents, which is more than this
item asks for. Judged that a clear, unambiguous docstring marker at the top of each file
("SUPERSEDED... do not add test coverage here", naming exactly what superseded it) delivers the
item's real intent -- nobody mistakes these for uncovered production code needing tests -- at
lower risk than a file move plus a documentation-repair pass. If Alex wants the physical
relocation done anyway, the ten files and their replacement targets are listed above and the
remaining work is purely mechanical (`git mv` plus updating the links this note found).

**One exception, marked differently: `spike_assembly.py` is not superseded.** It is IP-FC-35's
feasibility check for IP-FC-19 (automated assembly-and-check), and IP-FC-19 is still `blocked`
in `freecad_migration.md` -- there is no production code to point to because the capability has
not been built yet. Marked "NOT SUPERSEDED" rather than "SUPERSEDED", explaining why, so it
reads as live reference material for a still-pending item rather than as an oversight in this
triage.

**IP-TEST-10: audit and new coverage complete.** Of the 13 modules named, five already had
`check_*.py` coverage (`measure.py`, `variants.py`, `build_part.py`, `part_kinds.py`,
`parameters.py`); audited all of their check scripts' exit-code/flush correctness and ran all
six that could be exercised with the fixtures already in hand for real: `check_derived_geometry
.py`, `check_overhang_angle.py`, `check_reachable_rows.py`, `check_vase_printable.py` (real
`nose_cowl`/`tail` builds, 207/435 stations, one contour everywhere), and `check_unread_rows.py`
(a real 69-row perturbation sweep) all PASS for real, all already correct with no fix needed.
`check_bay_interchange.py` needs five distinct `ref_<type>.params.json` fixtures and was
audited (already correct) but not re-run, given the setup cost.

**Two more real, previously-hidden "always exits 0" bugs found and fixed, both worse than
anything found in IP-TEST-7 in one respect: neither even had a `main()` to return a verdict
from.** `check_end_bands.py` and `check_regenerate.py` were both pure top-level module code --
no function, no `is_entry_point` guard, nothing stopping Python's own "ran to completion, exit
0" default regardless of what `checks`/`failures` had accumulated. `check_regenerate.py` was
the more serious of the two: unlike `check_end_bands.py` (which at least wrote a message to
stderr before exiting 1 on a missing reference), it had no missing-reference guard at all --
`measure()` would have raised uncaught on a missing `regen_U*.stl`, and under freecadcmd's own
exit-code-on-exception hazard that would ALSO have silently reported success, the identical
"false pass" class `check_tree.py` had earlier in this pass. Fixed both: wrapped each in a real
`main()`, added a genuine tolerance-based verdict (`check_end_bands.py` per-band and total;
`check_regenerate.py` per-`U` and a "checked == 0" guard matching `check_tree.py`'s fix), and
the standard flush-before-`sys.exit()` guard. Rendered the real OpenSCAD references each needs
(`check_end_bands.py`'s five `band_*.stl`, via the exact command its own docstring gives;
`check_regenerate.py` reused the four `regen_U*.stl` already rendered earlier this session) and
ran both for real: `check_end_bands.py`'s five bands all agree to 0.0016%-0.0027%;
`check_regenerate.py`'s four `U` values all agree to 0.0005%-0.0065%. Both verified against
the missing-reference case too (a monkeypatched `out_path` hiding the references), confirming
the exit code goes nonzero rather than silently passing.

**New real coverage, all verified for real against the actual module rather than a synthetic
stand-in wherever one was available:**

- `check_geometry_branches.py` -- `_watching()`'s winner/tie bookkeeping and `attribute_at()`'s
  backward scan, exercised against `corner_common.Params.flat_offset`'s own real `max()` call
  (the module's own worked example) with two constructed parameter sets chosen so each argument
  wins once, plus a real end-to-end subprocess run of `geometry_branches.py` itself.
- `check_units.py` -- every conversion function, `bbox_m_matches_mm`'s pass/genuine-1000x-fail/
  malformed-input paths (the roadmap's own named "single easiest place to be silently wrong by
  1000x" check), and `describe_bbox_mismatch`'s two diagnostic branches. Written for the
  freecadcmd tier even though `units.py` itself has no FreeCAD dependency, deliberately matching
  this project's directory-scoped two-tier boundary (`tests/conftest.py`'s own stated rule)
  rather than exploiting a per-file exception nothing else in the project makes.
- `check_solid_measure.py` -- `mesh_volume`, `open_edges`, `converged_volume` (including a
  genuine `NotConverged` case, which needed a curved shape: a box's mesh volume is exact at
  every deflection and so trivially "converges" even at `tol=0.0`, a mistake this check's own
  first draft made and caught by rerunning it), `wire_area`, `surface_difference` and
  `converged_difference` (including a genuine `TopologyMismatch`), all against a 10 mm cube and
  small variations of it with closed-form answers.
- `pd_middle.py`/`pd_end.py` -- both already existed as PartDesign::-vs-Part:: comparison
  scripts (IP-FC-5) with real, substantive measurements, but neither had ever turned its own
  numbers into a verdict; fixed the same way as everywhere else in this pass. `pd_middle.py`
  also had a bare hardcoded literal (`"Part:: full section = 4041.580837"`) where a live call to
  `corner_common.section()` -- which computes exactly that, and already existed -- belonged;
  replaced it, and confirmed the live-computed reference still matches the hardcoded one it
  replaced. Both confirmed running for real: `pd_middle.py` correctly identifies
  `TransformMode = 'Whole shape'` (not `'Features'`) as the one that reproduces `mirror_xy()`'s
  semantics; `pd_end.py`'s `PartDesign::Boolean`-cutting-with-a-`Part::`-tool mechanism matches
  its reference to +0.0021%, while the full-revolution `Groove` it's deliberately compared
  against is off by -278 mm3 -- the expected, documented negative result the module's own
  docstring names as one of its three purposes, correctly NOT counted as a failure.

**Two modules judged not to need a `check_*.py` at all, and why.** `preview.py` and
`geometry_branches.py`'s own top-level purpose are not acceptance tests -- `preview.py` renders
PNGs for a human to look at ("that judgement needs eyes on the part"), matching the already-
excluded `draw_*.py` evidence generators from IP-TEST-4; confirmed it still runs cleanly for
real regardless. `mesh_to_brep.py` and `build_sheet.py` were audited and already fully correct
(real exit codes, proper flush) with no fix needed; both confirmed running for real too --
`mesh_to_brep.py` against a real corner B-rep and a matching freshly-rendered OpenSCAD mesh
(0.000355 mm max deviation), `build_sheet.py` already exercised earlier this pass building the
real sheet IP-TEST-8's `render_pages.py` test rendered.

**IP-TEST-11 is the item that directly answers "were the existing integration-level
verifications actually committed."** `check_*.py` and `check_derivation.py` themselves are
already tracked and were never the problem; the problem this item finds is every place a
change over this project's history was verified by a session-local script or a manual
measurement that never became one of them. `check_cowl_nose_parametric.py` (2026-09-22,
covering the `nose_plate`/`nose_tip` port under IP-FC-12) is the first entry closed this
way; IP-TEST-11 is the systematic pass that finds the rest.

**Started, not completed -- honestly scoped rather than rushed.** `freecad_migration.md` has
141 `IP-FC-*` rows, most of them multi-kilobyte narrative entries (one alone, IP-FC-137's, is
~39 KB of text); reading and cross-referencing all of them against current `check_*.py`/`tests/`
coverage is a genuinely large, standalone undertaking that this pass's remaining scope could
not respect the depth of without becoming shallow. A blanket keyword search across the whole
document for the obvious red flags ("scratchpad", "throwaway", "not committed", "session-local",
"manual measurement") returned almost nothing, which says the document does not consistently
flag this in vocabulary a grep can find -- each candidate genuinely needs reading, not
searching.

**One real, concrete finding made anyway, in the cluster this session's own `check_cowl_interior
.py` work already gave deep context on.** IP-FC-139/140/141's resolution (see IP-FC-137's own
entry, "Follow-up, 2026-09-21") claims the rib-cut construction fix was "verified... for all
eight swept `U` (0.5 through 4.0, `nose_size_variants.csv`)... both by calling
`cavity()`/`shell_solid()` directly and, for `U` = 0.5 and 0.75 specifically..., by the real
`cowl_tail_shell.emit()` -> `cowl_tree.emit()` -> `doc.recompute()` path." Checked what of that
is actually committed and re-runnable today: nothing sweeps `U`. `check_cowl_interior.py` and
the `cowl_*.py` wrapper `main()`s all build at one literal `U` (their own module defaults, not
`nose_size_variants.csv`'s eight rows); `soak_cowl_shell.py` builds one variant per invocation,
for a *different* purpose (pairwise reproducibility, OQ-ARCH-19), not a validity sweep. So the
specific claim "all eight swept `U` build cleanly for both cowls" has no standing, committed
regression -- only the narrative record of a one-time investigation.

**Run, 2026-09-22, on Alex's go-ahead.** Added `check_cowl_u_sweep.py`: builds `tail_shell` and
`nose_cowl_shell` at each of the eight rows in `nose_size_variants.csv` directly against
`cowl_tree`'s own `PARAMS_TAIL_SHELL`/`PARAMS_NOSE_COWL_SHELL` (only the `U` literal
substituted, via `soak_cowl_shell.with_u()`), checking exactly what each kind's own `main()`
checks -- `isValid()` and single-solid. All 16 builds passed: every one valid, single-solid,
and every rib cut left `0.000000 mm3` inside -- the exact IP-FC-137 defect signature, at zero
across the full range for both cowl kinds. 58.7 minutes total (`U=4` `tail_shell` alone took
969 s), confirming this really is a "full sweep" by the project's own standing definition --
committed as its own file rather than folded into the routine check pass, with that cost
documented at the top of the file so nobody runs it by accident. IP-FC-139/140/141's claim is
now backed by a real, re-runnable regression, not narrative record alone.

**Triage pass, 2026-09-22, and a genuine gap found and closed.** Delegated the module-grouping
sweep across the remaining ~140 rows to a research pass, restricted to reading and cross-
checking against files on disk (no fixing). Its report needed a real correction before acting
on it: it named `compare_backends.py`, `render_variant.py`, `oml_export.py`, `mesh_stats.py`,
`surface_distance.py`, `baseline_manifest.py`, `export_parameters.py` and `params_snapshot.py`
as having "zero regression coverage," which is wrong -- all twelve modules in that cluster
(including every one of those eight) already have real, committed pytest coverage from
**IP-TEST-5**, finished earlier this session and marked complete in this same document. Checked
directly (`tests/test_compare_backends.py` alone runs 40+ assertions against `bbox_tol`,
`u_of`, `kind_of`, `ensure_wiped`'s IP-FC-72 delete-pending refusal, and `compare()` end to end
against hand-built STL trees) before trusting the report further -- a reminder that a research
pass's claims about what exists need the same file-level verification as any other claim before
they're acted on, not just read and believed.

One claim did hold up: **`build_part.py`** (`src/Fuselage/freecad/` -- the report mislabeled it
as a `tools/` file, but it is the FreeCAD-tier CLI entry point IP-FC-10/11/14/45 describe) had
genuinely never been tested on its own. Every check script in this directory imports a kind's
geometry module directly and never `build_part.py` itself, so `parse()`'s hand-rolled `--pass`
argument handling, `load_seed()`'s two file shapes (a `tools/export_parameters.py` "variant"
vs. a sweep's flat "part" file), `export_deflection()`'s per-`U` cowl scaling, `fcstd_path()`'s
default derivation, and the "a `.FCStd` is always written, never skipped" promise (IP-FC-14)
had no committed regression -- only the narrative record of when each was written. Added
`check_build_part.py`: unit checks for all four pure functions plus a real end-to-end build of
`out/reference_bulkhead.params.json` (an existing, already-relied-on fixture) through `build()`,
`write_mesh()` and `doc.saveAs()`, confirming the mesh and `.FCStd` are both actually written to
disk and the shape is valid and single-solid. Verified load-bearing with a negative control
(forcing `export_deflection` to return a wrong constant, confirming the check's own assertions
catch it and the script exits 1, not just report OK unconditionally).

Remaining in this item: the systematic walk through the rest of the ~140 `IP-FC-*` rows. Given
how large this triage pass's own error was, further grouping-by-module passes should be
verified against `tests/*.py` and `src/Fuselage/freecad/check_*.py` file contents directly
before treating any claimed gap as real -- existence of a same-named test file must be checked
first, not inferred from a summary. Most efficiently continued by reading the rows whose
subject module has no `check_*.py`/`test_*.py` file of the same or related name at all (a
`find`/`ls` fact, checkable in one step) rather than re-deriving coverage claims narratively.
