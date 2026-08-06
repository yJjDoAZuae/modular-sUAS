# modular-sUAS roadmap

The Python sweep drivers and OpenSCAD geometry under `src/Fuselage/` were **copied in from
another repository** to be adopted into modular-sUAS. They have not been committed here yet
(`git status` reports the whole of `src/` as untracked), and their original commit history
did not come with them. Anything in those files that refers to a past commit refers to the
*source* repo's history, not this one.

Three phases, in order. Each depends on the one before it.

---

## Phase 0 — Adopt what was copied in

Prerequisite for everything else. Nothing under `src/` is under version control here, so
today there is no rollback for any of it.

- [ ] Decide what actually gets adopted. `src/Fuselage/` currently mixes hand-authored
      source, ~2.6 GB of regenerable sweep output (`variant_output/`,
      `variant_output_original/`), `.bak` files in `archive/`, and scratch (`tools/tmp.py`).
      Only the first belongs in git.
- [ ] Extend `.gitignore` to cover `variant_output/`, `variant_output_original/`,
      `tools/test_fuse_output/`, and `Thumbs.db`. Note the stock Python `.gitignore`
      already ignores `parts/` and `lib/` — `src/Fuselage/parts/` holds **hand-modeled,
      irreplaceable** geometry and must be un-ignored deliberately.
- [ ] Commit the adopted source in one clearly-labeled commit, so the "as copied in"
      state is a recoverable baseline before any refactoring starts.
- [ ] Record where it was copied from and at what revision, so the two can be diffed later.

**Environment** is defined but **not yet committed**: `pyproject.toml`, `uv.lock`, and
`.python-version` (3.13) exist at the repo root and `uv sync` reproduces the environment,
but all three are still untracked. Until they are committed the code is reproducible and
the environment that runs it is not.

`OPENSCADPATH` is a second, undeclared requirement: `solid_render()` does
`os.path.join(os.environ.get('OPENSCADPATH'), cmd)`, so an unset value fails with
`TypeError: ... not NoneType` at the first render. It is currently a User environment
variable on this machine only, and uv cannot capture it — it needs an `.env` (untracked)
plus a committed `.env.example`. See [CLAUDE.md](../../CLAUDE.md).

---

## Phase 1 — Get the parameter variation sweep working here

The goal is a sweep that runs correctly *from this repo, on this machine*, and whose output
is reproducible. Do not refactor geometry in this phase — only make it run.

- [ ] **Establish a baseline.** Run one single parameter combination end to end before
      attempting the full factorial. Capture what fails; the sweep is a full-factorial
      product and a failure deep in the loop is expensive to discover.
- [ ] **Fix path anchoring.** `solid2.import_scad()` resolves bare filenames against the
      process CWD and then calls `.absolute()`, and that absolute path is what gets written
      into generated `.scad` as `use <...>`. A previous sweep baked a since-dead `R:\` drive
      mapping into its entire output this way. `fuselage_variants.py` already anchors to
      `__file__` via `_HERE`/`_ROOT`; confirm every input path does, and confirm generated
      files contain only **relative** references.
- [ ] **Confirm the sweep is CWD-independent.** Run it from `tools/`, from the repo root,
      and from an unrelated directory, and verify the three outputs are identical.
- [ ] **Confirm all five sweeps run**, including nose and tail. There is no known defect
      here — an earlier draft of this roadmap claimed the nose/tail sweeps were broken, but
      that claim was lifted from `src/Fuselage/docs/reorganization_plan.md`, which describes
      a **different repository at an earlier point in time** and says nothing about the code
      here. Checked against this code on 2026-08-04: every symbol it named as missing is
      present and consistent, and `ruff --select F821` (undefined names — the exact failure
      class alleged) passes clean. Verify by running, not by assuming either way.
- [ ] **Pin down `OPENSCADPATH`.** On this machine it holds the OpenSCAD *binary* directory
      rather than a library search path, and `solid_render` depends on that. It works;
      leave it working, but document it so it does not get "corrected" later.
- [ ] **Fix the OpenSCAD MCP temp directory.** Its render/analyze/export tools all fail on
      this machine because the temp directory resolves to a UNC path, and `validate_scad`
      silently reports everything as invalid. Until this is fixed there is no cheap way to
      check generated geometry, which makes the tests below much harder to write. See
      [CLAUDE.md](../../CLAUDE.md) for the specifics.
- [ ] **Add regression tests.** `tools/test_fuse.py` is a three-line scratch file, not a
      test suite. Stand up `tests/` with pytest, and assert on model properties — bounding
      box, dimensions, feature presence via `analyze_model` — rather than on
      byte-identical `.scad`/`.stl` output, which is not stable.
- [ ] **Regenerate output from scratch** and confirm it matches the committed reference
      geometry. `variant_output_original/` may be usable as that reference — establish
      whether it is trustworthy before relying on it.

**Exit criteria:** a full sweep runs clean from any working directory, writes no absolute
paths, covers nose and tail, and is reproducible run-to-run.

---

## Phase 2 — Refactor and improve the OpenSCAD implementation

Only start once Phase 1's tests exist. Without them there is no way to tell a refactor
from a regression.

**Tracked in detail:** [doc/implementation/geometry_refactor.md](implementation/geometry_refactor.md)
carries the specific work items from the 2026-08-06 review of the geometry modules, each
with the check that proves it changed no geometry.

**Progress as of 2026-08-06.** Nine items complete and verified — keyword arguments at
the seven Python→SCAD call sites, a formula duplicated across the language boundary
resolved, and five library extractions the code was already asking for. Four verification
tools built along the way, each covering a case the others cannot; they are documented in
[src/Fuselage/docs/fuselage_folder_summary.md](../src/Fuselage/docs/fuselage_folder_summary.md).

**Scope corrected.** The largest planned item — regrouping the 28-parameter SCAD
signatures — was **dropped** after assessing it against Phase 3. The parameter groups
already exist in Python; the refactor would only have built an encoding of them in
OpenSCAD vectors, which the FreeCAD port discards entirely. The equivalent work on the
Python side, typed parameter objects, survives and replaced it. See OQ-GEO-1.

That assessment is now a standing guideline — see *Weigh a refactor against what replaces
the code* in [doc/guidelines/general.md](guidelines/general.md) — because the same
question applies to every remaining item in this phase.

**Open and blocking:** nothing in the verification tooling renders the seven GUI driver
`.scad` files, so a change can be certified geometry-preserving while leaving every
interactive driver broken. See OQ-GEO-2.

- [ ] **Map the current geometry.** 13 hand-written `.scad` modules in `scad/`, currently
      all siblings, so every `include`/`use` is a bare filename. That is why they resolve
      at all — any restructuring into subdirectories means editing every include line.
- [ ] **Separate library modules from drivers.** Geometry primitives and shared utilities
      (`shape_modifier_utils.scad`, `*_geometry.scad`) are a different kind of thing from
      the top-level part definitions that produce printable output.
- [x] **Make the parameter interface explicit.** Done as IP-GEO-16: parameters are
      dataclasses (`Parameters`, `NoseParameters`), not dicts, so a misspelled field is
      an `AttributeError` where it is written rather than a silently added key. What
      remains open is *validation* at the boundary where CSV/JSON is read — the types are
      declared but nothing checks a row's values before geometry consumes them.
- [ ] **Leave the OpenSCAD path in millimeters.** The project standard is SI internally
      (see [general.md](guidelines/general.md#units--si-is-the-project-standard)), but the
      OpenSCAD implementation is transitional — Phase 3 replaces it. Converting code that is
      scheduled for replacement buys nothing and risks geometry that is wrong by 1000× in
      one dimension while still rendering and exporting cleanly. SI arrives with the FreeCAD
      port, which is new code. Recorded here so the divergence is a decision, not an
      oversight.
- [ ] **Resolve the OML mesh coupling.** `import()` inside `cowl_geometry.scad` resolves
      relative to that file, *and* the same mesh filenames appear as data in
      `variant_param/*.json`. Code and data must move in lockstep. A stale duplicate mesh
      anywhere will silently shadow the real one.
- [ ] **Improve the geometry itself** — the MAUS unit standard (panel types, interstitial
      and boom bulkheads, corners, cowls) is only partly specified in the wiki. Close the
      gap between what the wiki claims and what `scad/` actually builds.
- [ ] **Revisit the folder reorganization proposal.** A detailed reorganization plan and a
      migration-tooling plan existed in `src/Fuselage/` — see the note at the bottom of
      this document about their disappearance. Their conclusions about path resolution
      were verified by testing and are worth recovering rather than re-deriving.

**Exit criteria:** geometry is modular and documented, the Python↔OpenSCAD parameter
contract is explicit and validated, and Phase 1's tests still pass.

---

## Phase 3 — Port the generators to FreeCAD Python scripting

The end state: parts are generated through FreeCAD's Python API rather than by emitting
OpenSCAD source. This buys real solid modeling, assemblies, technical drawings, and FEM —
none of which OpenSCAD offers. FreeCAD 1.1.1 is installed and driveable from the MCP.

- [ ] **Prototype one part first.** Port a single well-understood component — a corner or a
      bulkhead — before committing to the approach. Confirm it can express the same
      parametric intent.
- [ ] **Choose the modeling paradigm.** `Part::` primitives with booleans map most
      directly onto the existing CSG-style OpenSCAD code; `PartDesign::` bodies with
      sketches are more idiomatic FreeCAD and support proper fillets and drafts, but are a
      bigger rewrite. This decision shapes the whole phase.
- [ ] **Adopt SI internally in the ported code.** This is where the project's unit standard
      actually lands: the port is new code, so it is written in meters, seconds, kilograms,
      and radians from the start, with conversion confined to the file interface. FreeCAD's
      own API is millimeters and its FEM stack is N/mm², so the boundary is real and needs a
      single named conversion layer rather than scattered factors.

      Hard constraint that does not change: **exported STL and 3MF stay in millimeters.**
      Those formats carry no unit metadata and a slicer reads them as mm regardless.

      Verify the conversion by measurement — a ported part's bounding box in meters must
      equal the OpenSCAD part's bounding box in millimeters divided by 1000. This is the
      single easiest place in the project to be silently wrong by 1000×.
- [ ] **Validate equivalence, not appearance.** Compare ported parts against OpenSCAD
      output by measured properties — bounding box, volume, hole positions — not by eye.
      Phase 1's property-based tests should be reusable here almost unchanged.
- [ ] **Run the sweep headless.** The FreeCAD MCP drives a live GUI session, which is fine
      for interactive work but wrong for a batch of thousands of parts. Sweeps need
      `freecadcmd`. Note that a document edited headlessly must be reloaded before the GUI
      shows current geometry.
- [ ] **Then, and only then, exploit what FreeCAD adds:** FEM on the load-bearing
      structure, TechDraw for dimensioned drawings, assemblies for fit checks between
      modules.
- [ ] **Decide the fate of the OpenSCAD implementation.** Retire it, or keep it as a
      cross-check. Do not delete it before the FreeCAD path is proven across the full
      parameter range.

**Exit criteria:** the full parameter sweep runs headless through FreeCAD and produces
geometry that is verifiably equivalent to the OpenSCAD output it replaces.

---

## Reference documents — from another repository, not this one

Three planning documents from the source repo sit in `src/Fuselage/docs/`. **They are not
this repository's documents.** They were written about a different repo at an earlier point
in time, against code that has since changed, and their commit references point at a history
that did not come across with the files.

| Document | What it is |
| --- | --- |
| `reorganization_plan.md` | Proposal to separate generated output from hand-authored files. |
| `migration_tools_plan.md` | Implementation plan for tooling that would perform that move. |
| `fuselage_folder_summary.md` | Inventory of that repo's folder at that time. |

**How to use them:**

- **Never cite them as evidence about this code.** Statements about what is broken, what a
  function does, or what a directory contains describe the *source* repo. This has already
  produced one wrong roadmap item — see the nose/tail entry in Phase 1.
- The **mechanism** findings in `reorganization_plan.md` §1 are still worth reading: how
  `include`/`use`/`import()` and `solid2.import_scad()` resolve paths and shadow each other.
  Those are facts about OpenSCAD and `solid2`, not about any repository, so they carry over —
  but re-verify before relying on one.
- Both plans are **proposals — nothing in them has been executed**, and the `migrate`
  commands they describe are a specified interface, not a working tool.
- Read the filesystem for the actual layout. Always.
