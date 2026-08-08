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

`freecadcmd` **imports** the script as a module named after the file, so `__name__` is
`part_corner`, never `__main__`. Use `corner_common.is_entry_point(__name__)` for the
entry-point guard — the usual idiom silently suppresses the whole script.

The OpenSCAD references are rendered with `openscad -o out.stl ref_*.scad`, with parameters
supplied by `-D`. `measure.py` reads an STL and reports triangle count, volume by the
divergence theorem, and bounding box; run it with a real Python, not `freecadcmd`.

## The `Part::` port

| File | Contents |
| --- | --- |
| `corner_common.py` | `Params`, and the shared 2D section every axial slice extrudes |
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

## Verification

| File | Checks |
| --- | --- |
| `check_end_bands.py` | `corner_end` band by band, at the heights the snap groove is defined by, so a discrepancy is localised in z rather than resting on a single total |
| `check_regenerate.py` | The whole corner rebuilt at U = 0.5, 1, 2, 4 against OpenSCAD, plus the invariants that must hold at every U |
| `verify_pd_end.py` | Reloads the saved `.FCStd` and forces a recompute — the only measurement worth trusting, since figures taken during construction can be of a stale shape |
| `variants.py` | The regenerate parameter table, from the real variant tables rather than the driver's 1.0U constants |

`ref_*.scad` isolate the matching OpenSCAD module at the same parameters. They are the
reference the ports are measured against, and they stop working when IP-FC-34 retires the
OpenSCAD path — by which point IP-FC-13 has already done the comparison across the sweep.
