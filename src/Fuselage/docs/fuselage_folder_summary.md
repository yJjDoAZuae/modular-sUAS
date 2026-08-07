# Modular sUAS — Fuselage

Parametric OpenSCAD design system for a modular, 3D-printed sUAS fuselage, plus a
Python driver that sweeps the parameter space and batch-renders every valid variant
to STL and preview PNG.

The airframe is a **unit-cube truss**: printed corner extrusions and bulkheads form
the skeleton, flat sheet panels slide into slots in the corners, and cowled
nose/tail caps close out the ends against an OML imported from OpenVSP.

> **Scope of this document.** It describes `src/Fuselage/` in *this* repository, verified
> against the filesystem on 2026-08-04. The other two documents in this folder
> (`reorganization_plan.md`, `migration_tools_plan.md`) came from the repository these
> scripts were copied from and describe **that** repo at an earlier time — do not read them
> as descriptions of this tree.

---

## Folder layout

The tree is organized by kind. Everything is under `src/Fuselage/`.

| Folder | Contents | Size |
| --- | --- | --- |
| [`scad/`](../scad) | 13 hand-authored OpenSCAD files — the geometry. **Source of truth.** | 0.1 MB |
| [`tools/`](../tools) | Python sweep drivers, shape-definition JSON, insert table | 108 MB |
| [`variant_param/`](../variant_param) | 9 CSV parameter axes — the sweep inputs | 0.03 MB |
| [`oml/`](../oml) | Outer-mold-line meshes exported from OpenVSP | 37 MB |
| [`cad/`](../cad) | The OpenVSP source model | 39 MB |
| [`blender/`](../blender) | Surfacing and exploded-assembly Blender files | 36 MB |
| [`parts/`](../parts) | Hand-modeled geometry and print-ready exports. **Irreplaceable.** | 118 MB |
| [`archive/`](../archive) | 8 `.bak` files — hand-rolled backups, read-only history | 0.1 MB |
| `docs/` | This document and the dimensioned OML drawings | 2.7 MB |
| `variant_output_baseline/` | Renamed from `variant_output` to protect it. Generated. | 2.44 GB |
| `variant_output_original/` | An earlier generated set. Generated. | 2.62 GB |

Two notes on the tree as it stands:

- `media/` still exists here but holds only a single locked `Thumbs.db`. The build
  photography moved to the repo-root [`media/`](../../../media) folder.
- `Thumbs.db` files are Explorer cruft. They are held open by the shell and block folder
  deletion; clearing their hidden/system attributes releases most of them.

### Git tracking

Everything the sweep needs to run is tracked. Note two traps:

- **`parts/` is silently ignored** by the stock Python `.gitignore` template's `parts/`
  rule (a distutils artifact rule). 122 files and 118 MB of hand-modeled and hardware
  geometry are invisible to git. Verify with `git check-ignore -v` before assuming a file
  is safe.
- The `*` inside `variant_output*/.gitignore` matches those files themselves, so neither is
  committed — the generated output is protected only in this working tree.

---

## The parametric standard

Two scalars drive everything:

| Symbol | Meaning |
| --- | --- |
| `U` | Unit scale. `unit_width = 100·U` mm — the fuselage cross-section is a `100·U` mm square with rounded corners. |
| `FX` | Length multiplier for one bay. `unit_length = 100·U·FX` mm. |

Everything else in the "standard" scales off `U` and is marked *don't change these*
in the source (`standard_values()` in `fuselage_variants.py`):

- `corner_radius = 10·U`
- `longeron_radius = 2·U`
- `bolt_offset = 8·U`

Swept `U` values are `0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0`. Bulkhead thickness and bolt
diameter track `U` via a lookup table (see
[bulkhead_size_variants.csv](../variant_param/bulkhead_size_variants.csv)).

**Units.** This whole path is **millimeters and degrees** — OpenSCAD source, the Python
that drives it, and the parameter CSVs alike. That diverges from the project's SI standard
by deliberate exemption, because this implementation is transitional; see
[doc/guidelines/openscad.md](../../../doc/guidelines/openscad.md). Exported STL must stay in
millimeters regardless — the format carries no unit metadata and a slicer reads it as mm.

### Panel stock

Panel material is not fixed — the design is parameterized on panel *thickness*, and the
sweep covers metric (0/1/3/6 mm) and imperial (1/32" … 1/4") stock. A thickness of `0`
is a valid case meaning no panel at all, used for the cowling bulkheads.

The hand-driven `.scad` drivers default to `DTF_thickness = 4.77` mm, which is 3/16"
foamboard — "Adams board" or "Dollar Tree Foam", the low-cost R/C airframe material
popularized by [Flite Test](https://www.flitetest.com). It is a convenient and cheap
default, not a requirement; any 3/16" sheet drops into the same slot, and the
`3/16in` row of [panel_variants.csv](../variant_param/panel_variants.csv) carries the
exact 4.7625 mm value.

### Vocabulary used throughout the source

- **corner** — the extruded longeron/panel-slot profile that runs the length of a bay.
- **bulkhead** — the square frame that caps or joins bays. Five types: `end_bolt`,
  `end_anchor` (threaded insert instead of a through-bolt), `cowling_bolt`,
  `cowling_anchor`, `interconnect`.
- **greeble** — the interlocking detail where a corner registers onto a bulkhead. It is
  the **positive post on the bulkhead**, with a snap rib around it; the corner carries
  the matching bore and groove, and the longeron snaps into the post's centre through a
  70° mouth. Its wall is sized in extrusions (`2·√U·extrusion_width`, floored at two) so
  it prints crisply at any scale. See [bulkhead.md](../../../doc/design/bulkhead.md).
- **web / flange / plate** — the internal stiffening structure of a bulkhead.
- **OML** — outer mold line, imported as a mesh from OpenVSP for the nose and tail cowls.

---

## OpenSCAD source — [`scad/`](../scad)

All 13 files are siblings in one directory, so every `include`/`use` is a bare filename.
**That is why they resolve at all** — moving any of them into a subdirectory means editing
every include line that references it.

### Geometry libraries (the actual modeling code)

| File | Contents |
| --- | --- |
| [fuselage_bulkhead_geometry.scad](../scad/fuselage_bulkhead_geometry.scad) | The big one (42 KB). `bulkhead_section_full` and ~25 supporting modules: webs, bolt flanges, fillets, chamfers, greeble posts, OML profiles. |
| [fuselage_corner_geometry.scad](../scad/fuselage_corner_geometry.scad) | `fuselage_corner`, built from `corner_end` / `corner_transition` / `corner_middle`. |
| [fuselage_boom_bulkhead_geometry.scad](../scad/fuselage_boom_bulkhead_geometry.scad) | `boom_bulkhead` — tail-boom collet interface with a keyed anti-rotation feature. |
| [cowl_geometry.scad](../scad/cowl_geometry.scad) | Nose and tail cowls, nose plate, buttress ribs, body blanks, and an `assembly_tool`. Imports the OML mesh and cuts it to shape. |
| [shape_modifier_utils.scad](../scad/shape_modifier_utils.scad) | Symmetry helpers (`octant_to_full`, `mirror_x/y/xy`) and `fillet_inner` / `fillet_outer`. |
| [fuselage_geometry.scad](../scad/fuselage_geometry.scad) | Three-line aggregator that `include`s the corner, bulkhead, and boom-bulkhead libraries. |

Most parts are modeled as a single **octant** and mirrored out to full symmetry — that
is why so many modules have an `_octant` twin.

Dependency graph:

```text
fuselage_geometry.scad  →  fuselage_corner_geometry, fuselage_bulkhead_geometry,
                           fuselage_boom_bulkhead_geometry
fuselage_bulkhead_geometry.scad       →  shape_modifier_utils, fuselage_corner_geometry
fuselage_boom_bulkhead_geometry.scad  →  shape_modifier_utils, fuselage_bulkhead_geometry
cowl_geometry.scad                    →  shape_modifier_utils
```

### Driver files (open these in the OpenSCAD GUI)

These set concrete parameter values and call one module. They are the interactive
"knobs" version of what `fuselage_variants.py` does in bulk.

- [fuselage_corner.scad](../scad/fuselage_corner.scad) — one corner extrusion.
- [fuselage_bulkhead.scad](../scad/fuselage_bulkhead.scad) — end / interconnect bulkhead.
- [fuselage_cowling_bulkhead.scad](../scad/fuselage_cowling_bulkhead.scad) — cowling bulkhead (`FX = 0.5`, panel-less).
- [fuselage_boom_bulkhead.scad](../scad/fuselage_boom_bulkhead.scad) — boom-interface bulkhead.
- [nose_cowl.scad](../scad/nose_cowl.scad) — nose cowl against `vsp_nose.stl`.
- [tail_cowl.scad](../scad/tail_cowl.scad) — tail cowl against `vsp_tail.stl`.
- [fuselage_oml.scad](../scad/fuselage_oml.scad) — standalone reference block for the 100 mm OML cross-section.

Each driver carries a draft/publish pair at the top; `$fa = 15; $fs = 0.5` for working,
the commented `$fa = 1; $fs = 0.1` for final output.

---

## Python variant sweep — [`tools/`](../tools)

[fuselage_variants.py](../tools/fuselage_variants.py) (1413 lines) is the batch pipeline.

**How it works**

1. Each CSV in [variant_param/](../variant_param) is one independent axis of variation.
   `read_all_param_axes` loads them, `flatten_param_space` takes the full Cartesian product.
2. `derived_parameters(U, FX, params, printer_settings, is_bulkhead)` expands a flat CSV
   row into the `Parameters` dataclass tree the geometry modules need — deriving greeble
   thickness from nozzle diameter, panel overlap from panel thickness, anchor bore from
   bolt diameter via [threaded_insert_dimensions.csv](../tools/threaded_insert_dimensions.csv)
   (McMaster part numbers included).
3. `corner_validity_check` / `bulkhead_validity_check` reject combinations where the panel
   is thicker than the corner can accept (`corner_radius` minus the longeron, greeble, and
   nub stack-up) or thinner than the parametric minimum of `U`·1 mm. A `0` thickness always
   passes. Invalid combos are skipped rather than rendered.
4. `solid_render` uses **SolidPython2** (`solid2`) to emit a `.scad` file, calls
   `relativize_scad_references()` on it, then submits one `openscad` CLI invocation for
   the STL to the module's `RenderQueue`.
5. Output lands in `variant_output/U_<U>/<metric|imperial>/panel_<name>/<part>/` for
   corners and bulkheads, and `variant_output/U_<U>/<nose|tail>/<type_name>/` for cowls.

**Preview PNGs are no longer produced by the sweep.** OpenSCAD used to render them with a
second invocation carrying `--render`, which re-solved the entire CSG tree purely to take a
picture — the dominant cost of a run, for an image the STL already contains the information
for. Previews are now a separate pass; see *Preview rendering* below.

**Path anchoring.** Every input path is anchored to `__file__` via `_HERE`/`_ROOT`, not to
the working directory, and `relativize_scad_references()` rewrites absolute `use <...>`
lines in generated output to relative ones. This is load-bearing: an earlier sweep run from
a mapped drive baked a since-dead `R:\` path into all 1774 files it produced, none of which
can be re-rendered. Do not undo it.

One limit worth knowing: a relative path only exists when the output directory and `scad/`
are on the **same volume**. Across volumes the function deliberately leaves the path
absolute, so writing sweep output to a local disk while the geometry sits on the NAS bakes
absolute paths into every generated `.scad`. Keep output on the same share as the source.

**Entry point** — `main()` runs five sweeps: corner, bulkhead, boom bulkhead, nose, tail.
There is no way to run a subset; `main()` is all-or-nothing and writes into
`variant_output/`.

```text
uv run python src/Fuselage/tools/fuselage_variants.py        # default worker count
uv run python src/Fuselage/tools/fuselage_variants.py 8      # explicit
FUSELAGE_RENDER_WORKERS=1 uv run python src/Fuselage/tools/fuselage_variants.py
```

**Parallel rendering.** `RenderQueue` overlaps the OpenSCAD subprocess calls across a
thread pool, draining in chunks so a failing render surfaces early rather than after
thousands more have been queued behind it. Threads rather than processes, because each job
blocks in a child process and releases the GIL — and because generation stays on the main
thread, solid2's module-level facet state (`set_global_fn`/`fa`/`fs`) is never raced.

The default is `physical_cores - 1`, estimated as `logical // 2 - 1` (5 on a 12-logical
machine). `workers=1` restores the original strictly serial behavior exactly: the queue
runs each command inline instead of deferring it.

Requires the environment defined by `pyproject.toml` / `uv.lock` (`pandas` pinned `<2.x`
compatible, `solidpython2`) and the **`OPENSCADPATH`** environment variable pointing at the
OpenSCAD install directory — it is joined onto the CLI invocation directly, so an unset
value fails with a `TypeError` from `os.path.join(None, ...)`. Note this is a non-standard
use of `OPENSCADPATH`, which is normally OpenSCAD's *library* search path.

**Parameter axes** — 9 CSVs in [variant_param/](../variant_param):

| File | Axis | Rows |
| --- | --- | --- |
| [bulkhead_size_variants.csv](../variant_param/bulkhead_size_variants.csv) | `U` + matched thickness/bolt size | 8 |
| [corner_size_variants.csv](../variant_param/corner_size_variants.csv) | `FX` | 6 |
| [panel_variants.csv](../variant_param/panel_variants.csv) | panel stock, metric + imperial | 9 |
| [panel_variants_all.csv](../variant_param/panel_variants_all.csv) | extended panel list — not used by `main()` | 31 |
| [bulkhead_type_variants.csv](../variant_param/bulkhead_type_variants.csv) | end/cowling/interconnect × bolt/anchor | 5 |
| [boom_bulkhead_type_variants.csv](../variant_param/boom_bulkhead_type_variants.csv) | offset single / center single / dual boom | 3 |
| [nose_size_variants.csv](../variant_param/nose_size_variants.csv) | `U` **plus** print-driven nose dimensions | 8 |
| [nose_type_variants.csv](../variant_param/nose_type_variants.csv) | points at the nose JSON | 1 |
| [tail_type_variants.csv](../variant_param/tail_type_variants.csv) | points at the tail JSON | 1 |

`nose_size_variants.csv` carries `U` itself, so it *replaces* `bulkhead_size_variants.csv`
as the size axis for the nose and tail sweeps — crossing both would multiply two `U`
columns into a nonsense product.

Resulting combination counts: corner 9×8×6 = **432**, bulkhead 9×5×8 = **360**,
boom bulkhead 9×8×3 = **216**, nose 8×1 = **8**, tail 8×1 = **8**. **1024 parts**, each
rendered twice.

**Shape-definition JSON** lives beside the scripts in [`tools/`](../tools), not in
`variant_param/` — a `*_type_variants.csv` row names one by filename in its
`parameter_filename` column. [nose_round_plate.json](../tools/nose_round_plate.json) and
[tail_high_open.json](../tools/tail_high_open.json) each specify the OML source mesh, its
scale, cone angle, cut length, and per-buttress (`top`, `side`, `bottom`, two `top_diag`)
activation and geometry.

That makes a two-hop, data-level file reference — CSV names a JSON, JSON names a mesh —
which no static analysis can see and which breaks silently if either end moves:

```text
nose_type_variants.csv  --parameter_filename-->  tools/nose_round_plate.json
nose_round_plate.json   --oml.filename-------->  oml/vsp_nose.stl   (via ../oml/)
```

**Preview rendering**

- [stl_preview.py](../tools/stl_preview.py) — renders a PNG directly from an STL. Software
  rasterizer, numpy and stdlib only (zlib writes the PNG; no Pillow, no OpenGL context to
  lose). Orthographic, because these are verification images and perspective makes a
  feature's apparent size depend on where it sits in the part. Edge detection covers all
  three edge classes — silhouette, step (depth Laplacian, which unlike a gradient does not
  fire on merely-slanted faces), and crease (normal-buffer dot product) — with
  normal-oriented ambient occlusion darkening concavities. Back faces render blue as a
  **defect indicator**: a closed, consistently wound solid never shows one, so any blue
  means an open, inverted, or self-intersecting mesh.
Previews are produced by the sweep itself, from each finished STL, on the worker thread
that rendered it. There is no separate preview command: `fuselage_variants.py` is the only
user-facing entry point.

To regenerate previews across an existing tree without re-rendering geometry — after a
camera or shading change, where the meshes are already correct and only the images are
stale — use `--previews-only`:

```text
uv run python src/Fuselage/tools/fuselage_variants.py --previews-only --force
```

That batch runs across a **process** pool, not the sweep's thread pool: rasterizing is
numpy-bound and would serialize on the GIL, which is the opposite of the OpenSCAD renders,
where threads are right precisely because each job blocks in a child process.

**Verification**

Four tools, each covering a case the others cannot. Which one applies depends on *what
changed*, and using the wrong one gives a false pass.

| Tool | Proves | Use when |
| --- | --- | --- |
| [mesh_stats.py](../tools/mesh_stats.py) | Triangle count, enclosed volume, bounding box of one STL; detects truncation | Underpins the other three; also a CLI for comparing two STLs |
| [scad_snapshot.py](../tools/scad_snapshot.py) | Generated `.scad` text is byte-identical across 576 parts, in seconds, without rendering | **Python-side changes only** |
| [verify_scad_change.py](../tools/verify_scad_change.py) | Re-renders existing `.stl.scad` files and compares geometry | **`.scad` library changes**, where the signature is unchanged |
| [verify_sweep_change.py](../tools/verify_sweep_change.py) | Runs the real sweep end to end for a sample and compares STLs | **Changes spanning Python and SCAD together**, where signatures move |

Two traps worth knowing:

- `scad_snapshot.py` is **blind to `.scad` library files**. A generated `.scad` names its
  library by path and contains none of its text, so editing a geometry module leaves every
  generated file byte-identical. It will report IDENTICAL however badly such an edit broke
  the geometry — a false negative, not an absence of evidence.
- `verify_scad_change.py` **stops working** once a module signature changes, because the
  `.stl.scad` files it re-renders pin the old signature. That is what
  `verify_sweep_change.py` exists for.

[sweep_check.py](../tools/sweep_check.py) is separate again: it audits a finished output
tree for integrity, scaling-family completeness, and agreement with a reference.

```text
uv run python src/Fuselage/tools/sweep_check.py src/Fuselage/variant_output --reference src/Fuselage/variant_output_baseline
```

None of those four render the GUI driver files — they all reach the geometry through the
sweep's call path. [verify_drivers.py](../tools/verify_drivers.py) covers that gap:

```text
uv run python src/Fuselage/tools/verify_drivers.py
```

It renders every driver and **treats a warning as a failure**. That is the point rather
than strictness: OpenSCAD reports an unknown identifier as a warning and carries on with
`undef`, so a driver broken by a signature change still renders, still produces a shape,
and still exits zero. Checking the exit code alone passes exactly the cases worth
catching.

Two drivers currently fail: `nose_cowl.scad` and `tail_cowl.scad` name their OML mesh as
`vsp_nose.stl` rather than `../oml/vsp_nose.stl`, so neither has rendered since the
meshes moved into `oml/`. The sweep is unaffected — `oml_ref()` adds the prefix. See
IP-GEO-18.

**Other Python**

- [fuselage_splode.py](../tools/fuselage_splode.py) — picks four specific bulkhead variants
  plus a corner out of the flattened space by index, for building the exploded assembly view.
- [test_fuse.py](../tools/test_fuse.py) — three-line scratch file that imports one SCAD
  module. **Not a test suite**; do not treat it as coverage.
- [test_fuse.ipynb](../tools/test_fuse.ipynb) — interactive scratch notebook (1.5 MB with
  outputs; clear them before committing).
- `tmp.py` — scratch, an older partial copy of `fuselage_variants.py`.
- `test_fuse_output/` — 38 one-off render artifacts, ~106 MB. Disposable.

---

## OML source geometry — [`oml/`](../oml) and [`cad/`](../cad)

- [modular_sUAS_nose_tail.vsp3](../cad/modular_sUAS_nose_tail.vsp3) — the OpenVSP model
  (39 MB), origin of the OML.
- [vsp_nose.stl](../oml/vsp_nose.stl) (12 MB), [vsp_tail.stl](../oml/vsp_tail.stl) (24 MB) —
  the meshes the cowl sweeps actually import. The `.obj` siblings and `fuselage_oml.csg` /
  `fuselage_oml.stl` are reference exports.
- Scale is **data-driven, not hardcoded**: `oml.scale = 0.001` in each shape JSON converts
  the meter-based export to millimeters. `oml_scale` is a module parameter throughout
  `cowl_geometry.scad`.
- `import()` inside `cowl_geometry.scad` resolves relative to **that file**, so the meshes
  are referenced as `../oml/<name>`. A stale duplicate anywhere on the search path will
  silently shadow the real one.
- [MAUS-FOS_OML.blend](../blender/MAUS-FOS_OML.blend), [splode.blend](../blender/splode.blend) —
  Blender files for surfacing and the exploded-assembly render.

## Documentation and reference imagery

- [fuselage_oml_dimensioned.svg](fuselage_oml_dimensioned.svg) /
  [fuselage_OML_dimensioned.png](fuselage_OML_dimensioned.png) — dimensioned OML drawings.
- [oml_cross_section_dimensioned.png](oml_cross_section_dimensioned.png) — dimensioned cross-section.
- [`media/`](../../../media) at the repo root — build photographs and annotated dimension
  diagrams, grouped by subsystem: `bulkhead_corner/` (incl. `greeble.png` /
  `greeble_negative.png` explaining the interlock), `nose_tail/`, `boom_clamp/`,
  `16mm_collet/`.
- Narrative design rationale lives in the **wiki**, a separate repository
  (`modular-sUAS.wiki`).

---

## Hand-modeled and legacy content — [`parts/`](../parts)

Sorted into five subfolders. **None of this is regenerable by any script here.**

| Folder | Contents | Size |
| --- | --- | --- |
| `legacy_100mm/` | Fusion-modeled fixed 100 mm geometry (2024) that **predates the OpenSCAD implementation of this structural system entirely** — `corner*_100mm`, `fuse_bulkhead*100mm`, `fuse_panel*100mm`, `nosecone100mm*`, `tailcone100mm*`, and title-case one-offs (`Latch*`, `Battery Tray`, `Bulkhead Insert`, `Hatch Tab`, `Test Shell`). | 43 MB |
| `hardware/` | Boom clamp and 16 mm collet hardware (Jan 2026) — `Bushing`, `Single Clamp`, `collet_nut`, `collet_collet`, `collet_backer_nut`, with matching photo sets in the repo-root `media/`. | 19 MB |
| `scad_exports/` | `*_SCAD.stl` / `*_SCAD.3mf` exports from the parametric system. | 29 MB |
| `print/` | Print-ready and slicer project files. | 10 MB |
| `unsorted/` | Not yet classified. | 16 MB |

### [`archive/`](../archive) — `.bak` files

Hand-rolled backups, not a version-control scheme. Read for history; do not edit or revive
without being asked. Note that [fuselage_geometry.scad](../scad/fuselage_geometry.scad) is
now a 132-byte aggregator while `fuselage_geometry.scad.bak` is the 70 KB monolith it was
split out of — the `.bak` is the *older* design, not a newer variant.

---

## Fixed defect — `fillet_inner` clamp

`fillet_inner` in [shape_modifier_utils.scad](../scad/shape_modifier_utils.scad) called
`childresn()`, a typo for `children()`. OpenSCAD warns on the unknown module and drops
the node, which reduced the `intersection()` to a single child — so the clamp that is
supposed to guarantee the filleted result stays inside the input boundary silently did
nothing.

**Verified fixed in this repository** (2026-08-04): every call site in that file reads
`children()`.

### ⚠ The defect may have been masking the correct result — verify before reprinting

The fix is *not* confirmed to be an improvement in practice. The measurements below were
**carried over from the source repository and have not been reproduced here** — treat them
as a lead, not as evidence about this tree.

| Check | Result |
| --- | --- |
| Call sites reached, boom bulkhead | 5 |
| Call sites reached, main bulkhead (`end` / `interconnect` / `cowling`) | **0** — never fires |
| Bounding box, fixed vs. buggy | identical to 3 decimals |
| Volume, fixed vs. buggy | 7010.2 vs 7009.9 mm³ (**0.004 %**) |
| Boolean *buggy − fixed* | 0.005 mm³ (sliver artifacts) |
| Triangle count | 2364 fixed vs 3452 buggy |

So for the parameter values measured, the two versions were geometrically equivalent and
the fixed version merely tessellates more cleanly. **Any part already printed and
flight-validated was made with the unclamped version, and nothing yet proves the clamped
version is dimensionally identical at other points in the sweep.**

Why it can matter: the chain `offset(-r) → offset(+2r) → offset(-r)` is a
morphological open-then-close. The closing step *fills concave notches narrower than
`2r`*, and that fill can lie outside the input shape — which is precisely what the
intersection was written to clamp. Whether it fires depends on whether the input has
notches narrower than `2·web_fillet_radius`. It did not at `U = 1`; the sweep runs
`U` from 0.5 to 4.0, where feature sizes shift relative to the fillet radius.

**Before trusting the fix:** re-run the boom-bulkhead sweep across all `U` and both
boom types and diff against `variant_output_baseline/`. If any variant shows more than
tessellation-level change, decide deliberately which behavior is wanted — the unclamped
notch-filling may be load-bearing for the boom collet fit.
