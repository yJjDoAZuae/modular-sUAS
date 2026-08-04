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
- [ ] Commit the adopted source in one clearly-labelled commit, so the "as copied in"
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
- [ ] **Repair the nose/tail sweeps.** These are reported broken by a change made in the
      source repo — undefined symbols introduced when nose output was added to the sweep.
      The surviving nose/tail artifacts in `variant_output/` predate the break, so they are
      *not* evidence the current code works. Treat this as the phase's main known defect
      and reproduce it before fixing it.
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

- [ ] **Map the current geometry.** 13 hand-written `.scad` modules in `scad/`, currently
      all siblings, so every `include`/`use` is a bare filename. That is why they resolve
      at all — any restructuring into subdirectories means editing every include line.
- [ ] **Separate library modules from drivers.** Geometry primitives and shared utilities
      (`shape_modifier_utils.scad`, `*_geometry.scad`) are a different kind of thing from
      the top-level part definitions that produce printable output.
- [ ] **Make the parameter interface explicit.** Parameters currently arrive as loosely
      structured dicts assembled in Python (`null_parameters()` and friends). Decide what
      the contract between Python and OpenSCAD is, and validate it at the boundary where
      CSV/JSON is read — not deep in geometry code where the error loses the row that
      caused it.
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
OpenSCAD source. This buys real solid modelling, assemblies, technical drawings, and FEM —
none of which OpenSCAD offers. FreeCAD 1.1.1 is installed and driveable from the MCP.

- [ ] **Prototype one part first.** Port a single well-understood component — a corner or a
      bulkhead — before committing to the approach. Confirm it can express the same
      parametric intent.
- [ ] **Choose the modelling paradigm.** `Part::` primitives with booleans map most
      directly onto the existing CSG-style OpenSCAD code; `PartDesign::` bodies with
      sketches are more idiomatic FreeCAD and support proper fillets and drafts, but are a
      bigger rewrite. This decision shapes the whole phase.
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

## Reference documents

Three planning documents from the source repo now live in `src/Fuselage/docs/`:

| Document | What it is |
| --- | --- |
| `reorganization_plan.md` | Proposal to separate generated output from hand-authored files. Section 1 is the valuable part: a table of **tested** conclusions about how `include`/`use`/`import()` and `solid2.import_scad()` resolve paths, and how they shadow each other. Phases 1 and 2 depend on these. |
| `migration_tools_plan.md` | Implementation plan for the tooling that would perform that move. |
| `fuselage_folder_summary.md` | Inventory of the folder as copied in. |

Both plans are **proposals — nothing in them has been executed**, and the `migrate`
commands they describe are a specified interface, not a working tool. Read the filesystem
for the actual layout. Their references to past commits point at the *source* repo's
history, which did not come across with the files.
