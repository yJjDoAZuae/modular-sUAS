# FreeCAD geometry

The FreeCAD port of the fuselage geometry, mirroring [`../scad/`](../scad/). Everything
here today is the IP-FC-5 corner prototype — the corner built **both ways**, `Part::` and
`PartDesign::`, so the two paradigms could be compared on real geometry rather than in the
abstract. Findings are recorded in
[doc/implementation/freecad_migration.md](../../../doc/implementation/freecad_migration.md).

## Running

Scripts are run by `freecadcmd`, which takes the script as its first argument:

```
freecadcmd part_corner.py
```

Scripts that take arguments need `--pass` before **each** one, with the value joined by `=`:

```
freecadcmd build_part.py --pass --kind=bulkhead --pass --params=p.json --pass --out=p.stl
```

`freecadcmd` parses the command line before the script runs. An unrecognised `--flag` makes
it print its own usage and stop without ever calling the script; a bare positional it tries
to **open as a document**, which on a `.json` fails inside the FEM mesh importer with
`invalid literal for int() with base 10: 'U'` -- an error naming neither FreeCAD nor anything
actually wrong with the file.

**And its exit code cannot be trusted.** An uncaught exception prints `Exception while
processing file: ...` and exits **0**; an explicit `sys.exit(n)` is not stable between runs.
Anything driving these scripts must check that the output file appeared, not the status.

`freecadcmd` **imports** the script as a module named after the file, so `__name__` is
`part_corner`, never `__main__`. Use `corner_common.is_entry_point(__name__)` for the
entry-point guard — the usual idiom silently suppresses the whole script.

**Editing anything here invalidates the sweep's output, and `--resume` now knows that**
(IP-FC-11). `tools/geometry_version.py` hashes the transitive import closure of each kind's
builder — `build_part.py` plus `corner_tree.py` or `bulkhead_full.py`, followed through
their sibling imports — and stamps the digest into the definition file the sweep compares.
So a resumed run re-renders the parts an edit here affects, without needing `--force`. The
closure is followed automatically: adding an import extends it. Files outside it (`spike_*`,
`check_*`, `measure.py`, the superseded `part_*`/`pd_*` path) are correctly ignored.

One consequence worth knowing: the digest is over **file bytes**, so editing a comment
re-renders parts whose geometry did not move — the safe direction, chosen deliberately.

`part_kinds.py` is what lets the driver walk the right closure. It states which module
builds each kind, and **nothing in it may import FreeCAD, or anything that imports FreeCAD**
— that is the only reason it is a separate file. `build_part.py` imports it normally;
`tools/freecad_render.py`, which runs in the project virtualenv where `import FreeCAD` fails,
loads it by file path. A second copy of that table naming the wrong module would produce the
digest of the wrong closure: a staleness key that looks like it works and tracks the wrong
files.

**An expression row needs its inputs in the seed.** `seeded()` replaces *literal* rows only,
so a row stated as a relationship — `corner_radius` is `=U * 10`, `unit_length` is
`=U * FX * 100` — keeps its expression and evaluates from whatever the sheet holds. That is
the point of stating it as a relationship, and it is why `merge_params` prefers one over a
constant. But if the seed does not supply everything the expression reads, the row computes a
plausible number from the module's own literal while the correct value sits unused in the
parameter file. There is no geometric symptom: the part is valid, single-solid and the wrong
size. `U` and `FX` were both missing, so every swept corner was built at FX=1.0 and every
swept bulkhead at U=1.0 (IP-FC-48). `build_part.build()` now runs `check_seed` on every
build, which is what names it:

```text
build_part: bulkhead: the sheet disagrees with the parameter file on corner_radius
  corner_radius          sheet 10   authority 25
```

**A constant inherited from the OpenSCAD source is a claim about CGAL, not about OCCT.**
`eps` (0.01 mm) has two jobs there: making cuts overshoot the material they pass through, and
making the octant overlap its own mirror so the tiling union resolves. The first is real on
both kernels. **The second is not** — OCCT fuses a solid with its own mirror about the exact
touching plane cleanly at 10, 100, 250 and 400 mm, and the 0.01 mm sliver is small enough at
U ≥ 2.5 to make the fuse *invalid* while the octant and mirror are each fine (IP-FC-49). The
mask shift is now its own row, `mask_eps = 0`, leaving cut overshoot alone. The 2D port
carries the same row in `boom_oml.py`, where the shift cannot move the answer either way —
each octant's overhang past the mirror line lies inside its own mirror image, so the tiled
union covers the same region at 0 as at 0.01. Zero is still the honest value there. Before
adjusting any such constant, measure whether the target kernel wants it at all.

**Zero is a real parameter value here.** The `0mm` panel row is the no-panel variant, so
`panel_thickness`, `panel_tolerance` and `panel_overlap` are all zero and the panel slot has
no extent. OpenSCAD treats a zero-size `cube()` as the empty set and the `difference()`
becomes a no-op; `Part::Box` yields a **null shape** that nulls everything downstream, and
the error surfaces several features away as `BRepCheck_Analyzer::Init() - NULL shape`.
`corner_tree._degenerate()` omits such a feature. New geometry built from a parameter that
can reach zero needs the same treatment — see IP-FC-46.

The OpenSCAD references are rendered with `openscad -o out.stl ref_*.scad`, with parameters
supplied by `-D`. `measure.py` reads an STL and reports triangle count, volume by the
divergence theorem, and bounding box; run it with a real Python, not `freecadcmd`.

## The `Part::` port

| File | Contents |
| --- | --- |
| `build_part.py` | **The sweep's entry point** (IP-FC-10). One process, one part, one parameter file in, one STL out -- shaped like a single `openscad -o` call so the sweep's queue could take it unchanged. Reads either definition shape: the two-table *variant* `export_parameters.py` writes, or the flat one-kind *part* the sweep writes. Every argument must go behind freecadcmd's `--pass` |
| `part_kinds.py` | Which module builds which kind, and the roots the IP-FC-11 digest walks from. **Imports nothing that imports FreeCAD** — that is the point of it: `tools/freecad_render.py` has to read it from the project virtualenv, where `import FreeCAD` fails |
| `corner_common.py` | `Params`, the shared 2D section every axial slice extrudes, and the sheet machinery — `build_sheet` (seeded from the authority), `merge_params` (refuses an alias defined two ways) and `check_seed` (the finished sheet must reproduce `derived_parameters()`) |

| `part_middle.py` | `corner_middle` — the constant-section run |
| `part_end.py` | `corner_end` — the greeble socket, with the interrupted snap groove |
| `part_transition.py` | `corner_transition` — socket bore down to longeron bore |
| `part_corner.py` | `fuselage_corner`, assembled from the three and mirrored in z |

## The `PartDesign::` port

| File | Contents |
| --- | --- |
| `spike_csg_tree.py` | `Part::` **document objects** — a parametric CSG tree driven by spreadsheet expressions, which survives save/reload still editable. This is the path IP-FC-38 takes; the `part_*.py` above build static shapes and are the verified reference |
| `spike_hand_edit.py` | How a hand edit interacts with a generated tree: writing an expression-bound property is silently discarded, clearing an expression decouples that dimension permanently and invisibly, and a user node added downstream survives but keeps whatever dimensions it was given |
| `spike_derived_part.py` | The derived-part workflow — the user's document owns the parameter sheet, the generated nodes and its own geometry. Shows the two properties that make repeated generation safe: a `Generator` tag so a regenerate touches only its own nodes, and a stable `Tip` so user features keep a valid reference when the generated internals restructure |
| `spike_link.py` | What `App::Link` to a generated file does (geometry reuse, follows the source live, accepts user geometry) and does not (no way to drive the source's parameters from the referencing document) |
| `spike_partdesign.py` | Body, sketch, Pad, Pocket, Groove, datum plane all work headless |
| `pd_middle.py` | The octant as sketches and features, then the `mirror_xy` question |
| `pd_end.py` | The socket, including what a native `Groove` cannot express |

## The CSG document tree (IP-FC-38)

This is what the generator will emit — document objects with live properties, every
dimension an expression over a `Spreadsheet::Sheet`, ending in a stable `Tip`.

| File | Contents |
| --- | --- |
| `corner_tree.py` | The whole corner as a live CSG tree — 82 nodes, 2 sketches. Every polygon mask in the section profile is a union of half-planes and the snap groove is a stack of cylinders and cones, so only two polygons in the part need sketches. Its tip *is* `fuselage_corner`: the half-length run and its mirror about mid-span, which is all `corner_render()` calls. Run it with a `params.json` for the swept parameters, without one for `fuselage_corner.scad`'s |
| `check_tree.py` | The tree against OpenSCAD at four sizes, by editing the parameter sheet rather than re-running; then reload, a tolerance edit, and a parameter-bound user feature. Also re-asserts every sketch is fully constrained *at each size* |
| `spike_eps.py` | Whether OCCT needs `eps` at all, and where. Cut overshoot buys nothing — a tool cap coplanar with the face it exits through is exact at every scale and yields *fewer* faces. An abutting fuse is likewise clean. The exception is tangency: safe when incidental, but where a boolean *depends* on a tangent face OCCT under-removes (0.0199 mm³ in the greeble wedge), so that one `eps` stays (IP-FC-50) |
| `spike_offset2d.py` | Whether `Part::Offset2D` reproduces OpenSCAD's `offset(r=)` and `fillet_inner()`. A single offset matches to 0.01%; the chained morphological fillet diverges by 19% once the intermediate shape fragments. Settled by OQ-DES-B9 — the port uses real fillets, and keeps `Offset2D` for the erosion |
| `spike_fillet.py` | Whether `Part::Fillet` survives a parameter change. It does for dimension-only changes, and fails *visibly* when the topology shifts — but its `Shape` goes stale rather than null, so `State` must be checked, not `isValid()` |
| `flange_base.py` | `bulkhead_flange_positive`'s base profile. Two boxes minus the half-plane `x > y` — the only non-axis-aligned edge in the polygon is its closing one, so no sketch is needed. Matches **exactly**, being entirely planar |
| `simple_positives.py` | The six plain positives of `bulkhead_section` — bolt boss, its web and chamfer, the plate, the longeron flange and its chamfer. All cylinders, cones and boxes. **Only the bolt three are unconditional**: the other three are inside `if (is_cowling)`, forty lines below the brace that opens it, so an ordinary bulkhead has no longeron flange at all. Built in two groups for that reason — the assembly takes only what it is entitled to |

| `fillets.py` | All five true fillets and chamfers — `outer_corner_fillet`, `bulkhead_flange_chamfer`, `greeble_to_web_fillet`, `bulkhead_bolt_flange_fillet`, `web_to_bolt_fillet`. Each is a block minus a stepped cylinder/cone/cylinder stack, where the step *is* the chamfer. The last two clip their block with a half-plane whose **rotation comes from an expression**, `atan2(dy; dx)`, because the bolt-centre-to-fillet-centre edge lies at no fixed angle |
| `flange_boss.py` | The quadrant ring around the longeron bore, flared into the plate by a chamfer cone. The source builds this inline rather than as a module, so its isolated reference is a transcription — see the note in `ref_flange_boss.scad` |
| `bulkhead_positive.py` | `bulkhead_flange_positive` assembled from all eight positives, checked against the **real module** — which is what makes the `flange_boss` transcription trustworthy. Also merges the per-module parameter sheets into one and asserts no alias is defined two different ways (IP-FC-41) |
| `parameters.py` | Reads the JSON [`tools/export_parameters.py`](../tools/export_parameters.py) writes from `derived_parameters()`. The parameter set crosses from the project virtualenv as **data**, because FreeCAD's Python has no `solid2` and cannot call the authority directly. `seed()` feeds `corner_common.build_sheet`; `check_literals` and `check_refs` verify the modules and the hand-typed reference `.scad` files against the same authority (IP-FC-41) |

| `bulkhead_cuts.py` | The five cut tools — opening wedge, outer-face cleanup, longeron and bolt holes, octant mask. The octant mask turns out to be the `x > y` half-plane shifted by `mask_eps`; the wedge is the one shape with arbitrary angles, and is a covering box clipped by three half-planes rather than a sketch |
| `greeble_web.py` | `greeble_bolt_web`. Its plan view is a parallelogram — a strip laid along the corner-to-bolt diagonal — so one rotated box, plus a rib prism placed by composed rotation |
| `web.py` | `bulkhead_web`. Three stacked boxes minus the `x > y` half-plane, then a cylinder subtracted at the re-entrant corner — which is already a **true** fillet, not the morphological `fillet_inner` that OQ-DES-B9 concerns |
| `bulkhead_tree.py` | The bulkhead's greeble-forming tool: `corner_end` re-evaluated at greeble tolerance **0** and `bulkhead_thickness + 2*eps`. Shows what "reuse the corner's end section" actually means — a second evaluation of the same builders against a second set of spreadsheet rows, never a reference to the corner's built shape, which carries the fit clearance. It is also the one sketch in the assembled section, inherited from `corner_end`'s wedge |
| `bulkhead_section.py` | The whole octant, assembled from every ported constituent and checked against the **real module** — the binding check for the `bulkhead_cuts` transcription, and what caught the `is_cowling` misreading above. Needs a seed: without one the merge is comparing two configurations and refuses |
| `bulkhead_full.py` | `bulkhead_section_full` — the octant translated to its corner and tiled eight ways, as seven `Part::Mirroring` objects and seven fuses. `bulkhead_render()` calls this and nothing else, so it is the whole part. Now exactly eight times the octant, and it did not used to be — `octant_mask`'s `eps` made neighbours overlap by a sliver the union reclaimed, until IP-FC-49 measured that OCCT is harmed rather than helped by it |

### The boom bulkhead (IP-FC-12)

Unlike every other part here, this one is **flat**: the whole shape is worked out in the plane
and a single `Part::Extrusion` at the top gives it thickness. That is forced rather than
chosen — most of its geometry comes from morphological offsets, and `Part::Offset2D` operates
on faces. Every module below builds 2D, and each is checked against its own mode of
[`ref_boom_bulkhead.scad`](ref_boom_bulkhead.scad).

| module | what it is |
| --- | --- |
| `plane2d.py` | The 2D primitives and the one union rule. **Never fuse coplanar faces**: `Part::Fuse` returns a compound of abutting patches, and `Part::Offset2D` then offsets each patch separately, interior shared edges included — measured at +329% on the boom key. The union here is `R − ((R − a) − b)` instead, and `fragmented()` is the standing check that no two faces share an edge |
| `boom_key.py` | `boom_key_shape` — the keyed collet. The one site in this part that gets **real fillets**: a named corner round with a fixed count of four, which is what OQ-DES-B11 settled it on |
| `boom_web.py` | The seven-vertex spine the boom's web is strokes of, and the mirror that doubles it |
| `boom_webs.py` | `boom_web_outer_shape` and `boom_web_inner_shape` — the two region-wide roundings. `boom_make_vert_web` swaps an erode with a mirror, and **the two do not commute**: eroding each half first leaves the vertical web the flag is named for. Two of the three boom types set it |
| `boom_oml.py` | The bulkhead outline, in three forms from one octant — before the bores, the bores alone, and the difference. Shared with the frame bulkhead, which reaches the same shapes as 3D octants through `bulkhead_cuts.py` |
| `bulkhead_web.py` | `bulkhead_web_inner_shape` — the lightening pocket inside the frame. **Built region-wide although the source builds it as an octant**, because this is the one `*_octant` module whose two translates cancel: its contents are whole-region shapes evaluated in world coordinates, and the eight wedges only reassemble what a region-wide intersection already gives. Computing it locally and tiling would give a closed, plausible, wrong region |
| `boom_bulkhead.py` | The part. `OML − fillet_inner(OML − MATERIAL) − KEY`, where the double negation is what rounds the lightening pockets and drops slivers instead of cutting them as knife edges. Checked at **both** boom types that reach it, because `boom_make_lower_web` is a second *evaluation* of the web builders at `−boom_z_position` and `180 − boom_key_angle` — not a mirror of the upper web, which would be wrong by the key and still land within a percent |

| `spike_sketch_expr.py` | Expression-driven sketch constraints, for the polygons that do not decompose. **A generated sketch must be fully constrained** — an under-constrained one deforms silently and still yields a valid solid |

## Rendering a variant — never by `-D` on a driver

To render a part the sweep would actually produce, use
[`tools/render_variant.py`](../tools/render_variant.py), which drives
`derived_parameters()`:

```
.venv/Scripts/python render_variant.py                     # list combinations + validity
.venv/Scripts/python render_variant.py 1.0 end_bolt 3/16in
```

**`panel.offset` is derived, not free.** It comes from `panel.overlap`, `panel.thickness`,
the greeble clearance and the extrusion width — 0 mm panel gives 5.5, 3/16 in gives 2.5, and
`fuselage_bulkhead.scad` hard-codes 0. The sweep also uses `extrusion_width = 0.6` where the
driver uses 0.4. Overriding some of these on the command line and leaving the rest produces a
combination the sweep would never generate: it renders without complaint and the geometry is
wrong. A 0 mm panel rendered with the driver's `panel_offset = 0` **loses the greeble posts
entirely**, because that offset is exactly the clearance holding the panel's inner corner off
the greeble perimeter.

The `ref_*.scad` files here are module *isolators*, for comparing one module against its
FreeCAD port at identical inputs. They are deliberately not variants and must not be read as
one. The corner's references (`ref_end.scad`, `ref_middle.scad`, `ref_transition.scad`,
`ref_greeble_tool.scad`, `ref_regenerate.scad`) are at the hand driver's values; the bulkhead's
are at the swept set, and `parameters.py` checks every one of their assignments against
`derived_parameters()` — they are hand-typed, and a mistyped value there compares the port
against the wrong shape.

**An isolator can only check the port against a reading of the source.** Where a module builds
geometry inline rather than calling a named module, the reference has to transcribe it, and
port and reference then share whatever the transcription got wrong.
`ref_flange_positive.scad` and `ref_bulkhead_section.scad` go through the real modules and are
what make the transcriptions trustworthy — `ref_bulkhead_section.scad` is what caught the
`is_cowling` misreading in `simple_positives`. `ref_greeble_tool_swept.scad` is the same
isolator as `ref_greeble_tool.scad` at the sweep's values, because a port that agrees at one
configuration and not another is exactly what seeding from the authority is meant to expose.

## Looking at the parts

`preview.py` exports a generated shape to a mesh and renders it through
[`stl_preview`](../tools/stl_preview.py) — the same software rasterizer the OpenSCAD sweep
uses, at the same camera. So a FreeCAD part and its OpenSCAD reference are drawn identically
and can be compared directly rather than impressionistically.

```
freecadcmd preview.py            # corner, three views, plus the OpenSCAD reference
```

Volume agreement says two solids enclose the same space; it does not say the shape is right.
That judgement needs eyes on the part, and this is how to get them without a GUI.

Output lands in `preview/` and is regenerable — delete it freely. `ref_corner.stl` beside
this script is the OpenSCAD comparison mesh; it is a build artifact too, kept only so the
side-by-side works without a re-render.

## Verification

| File | Checks |
| --- | --- |
| `check_end_bands.py` | `corner_end` band by band, at the heights the snap groove is defined by, so a discrepancy is localised in z rather than resting on a single total |
| `check_regenerate.py` | The whole corner rebuilt at U = 0.5, 1, 2, 4 against OpenSCAD, plus the invariants that must hold at every U |
| `verify_pd_end.py` | Reloads the saved `.FCStd` and forces a recompute — the only measurement worth trusting, since figures taken during construction can be of a stale shape |
| `variants.py` | The regenerate parameter table, from the real variant tables rather than the driver's 1.0U constants |

`check_tree.py` and `check_regenerate.py` need reference meshes rendered first; they skip any
size whose reference is missing rather than reporting a false pass:

```
openscad -o regen_U1.stl -D U=1 -D bulkhead_thickness=6 \
         -D panel_thickness=4.77 -D panel_overlap=4.77 ref_regenerate.scad
```

`ref_*.scad` isolate the matching OpenSCAD module at the same parameters. They are the
reference the ports are measured against, and they stop working when IP-FC-34 retires the
OpenSCAD path — by which point IP-FC-13 has already done the comparison across the sweep.
