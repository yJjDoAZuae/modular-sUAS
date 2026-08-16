"""IP-FC-67: the octant's smallest features, measured across a list of variants.

IP-FC-67 records that the bulkhead octant carries sub-micron edges and near-coincident vertex
pairs "at every parameter set, clustered at the bolt boss", and that the variants which build
are not cleaner than the one that does not -- merely luckier. That was measured on two
variants. This measures the same three things on as many as it is handed, so the claim can be
confirmed, narrowed or retired against the geometry as it stands rather than as it stood.

Three numbers per variant, all on `SectionCut`, which is where IP-FC-58's defect appeared:

    min_edge    the shortest edge. 3e-4 mm is four orders below the 0.2 mm layer height and
                represents no design intent; 0.4 mm is a real feature.
    min_face    the smallest face area. A negative one is a fold-back, not a small face.
    pairs       distinct vertices closer together than `--tol`, which is the measure a short
                edge misses: two vertices can be near-coincident without an edge joining them.
    invalid     nodes of the built tree whose shape fails `isValid()`. IP-FC-66's claim that
                the refined cut tools are unorientable "on every variant" was also made on a
                handful, and it is the same tree and the same build, so it is measured here
                rather than in a second sweep of its own.
    refined     `BulkheadSection`'s volume, which is `Part::Refine(SectionCut)`. IP-FC-68:
                a topological cleanup must not change the volume, and this one did -- by
                0.006150 mm3, small enough to pass every tolerance in `compare_backends` and
                so only findable by looking on purpose.

Driven by `tools/scan_octant_micro.py`, which resolves the variants and writes the manifest.
One process for the whole list, because a FreeCAD start-up per variant dominates the run:

    freecadcmd src/Fuselage/freecad/measure_octant_micro.py --pass manifest.json out.json
"""
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import bulkhead_section
import corner_tree as C
import parameters
from corner_common import is_entry_point, script_args

DEFAULT_TOL = 1e-3


def close_pairs(shape, tol):
    """Distinct vertices closer than `tol`. Quadratic, but an octant has fewer than 100."""
    pts = [(v.Point.x, v.Point.y, v.Point.z) for v in shape.Vertexes]
    out = []
    for a, b in itertools.combinations(range(len(pts)), 2):
        d = sum((x - y) ** 2 for x, y in zip(pts[a], pts[b])) ** 0.5
        if d < tol:
            out.append((round(d, 9), pts[a]))
    out.sort()
    return out


def invalid_nodes(doc):
    """Names of built nodes whose shape fails `isValid()`, in build order."""
    out = []
    for obj in doc.Objects:
        shape = getattr(obj, 'Shape', None)
        if shape is None or shape.isNull() or shape.isValid():
            continue
        out.append(obj.Name)
    return out


def measure(entry, tol):
    doc = App.newDocument('micro')
    try:
        C._SEEN.clear()
        bulkhead_section.emit(doc, parameters.seed(entry['params']))
        doc.recompute()
        shape = doc.getObject('SectionCut').Shape
        refined = doc.getObject('BulkheadSection')
        edges = [e.Length for e in shape.Edges]
        areas = [f.Area for f in shape.Faces]
        pairs = close_pairs(shape, tol)
        return dict(name=entry['name'], ok=True, volume=round(shape.Volume, 6),
                    valid=shape.isValid(), solids=len(shape.Solids),
                    faces=len(shape.Faces), vertexes=len(shape.Vertexes),
                    min_edge=round(min(edges), 9) if edges else 0.0,
                    min_face=round(min(areas), 9) if areas else 0.0,
                    pairs=len(pairs),
                    closest_pair=pairs[0] if pairs else None,
                    invalid=invalid_nodes(doc),
                    # Full precision, not rounded: the difference this exists to catch is
                    # 0.006 mm3 against a 2000 mm3 part, and rounding either operand first
                    # would decide the answer before the subtraction does.
                    refined=refined.Shape.Volume if refined is not None else None,
                    section=shape.Volume)
    except Exception as exc:
        return dict(name=entry['name'], ok=False, error=str(exc)[:200])
    finally:
        App.closeDocument(doc.Name)


def main():
    args = script_args()
    if len(args) < 2:
        print('usage: freecadcmd measure_octant_micro.py --pass manifest.json out.json')
        return 0
    manifest, out = args[0], args[1]
    tol = float(args[2]) if len(args) > 2 else DEFAULT_TOL

    with open(manifest) as f:
        entries = json.load(f)
    print('measuring %d variant(s), pair tolerance %g mm' % (len(entries), tol))

    results = []
    for i, entry in enumerate(entries, start=1):
        r = measure(entry, tol)
        results.append(r)
        if r['ok']:
            print('  %3d/%d %-34s min_edge %11.8f  min_face %12.8f  pairs %d  invalid %s'
                  % (i, len(entries), r['name'], r['min_edge'], r['min_face'], r['pairs'],
                     ','.join(r['invalid']) or '-'))
        else:
            print('  %3d/%d %-34s FAILED: %s' % (i, len(entries), r['name'], r['error']))
        sys.stdout.flush()

    with open(out, 'w') as f:
        json.dump({'tol': tol, 'results': results}, f)
    print('wrote %s' % out)
    return 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
