"""IP-FC-9 / IP-FC-41: bulkhead_section assembled from every ported constituent.

This is the whole octant of an ordinary bulkhead -- make_web true, is_interconnect and
is_cowling false -- and it is the last check the port needs before tiling:

    positives   bulkhead_flange_positive     (eight pieces, see bulkhead_positive.py)
                bolt_flange_positive         \\
                bolt_flange_fillet            > simple_positives.py
                bolt_web                     /
                bulkhead_web                 web.py
    negatives   the greeble-forming tool     bulkhead_tree.py -- corner_end re-evaluated
                the opening wedge            \\
                the outer cleanup             \\
                the longeron bore              > bulkhead_cuts.py
                the bolt hole                 /
                the octant mask              /

Sixteen modules, and **not one sketch among them**. That was not the expected outcome: the
working assumption at IP-FC-38 was that arbitrary polygons would force sketches. Every
profile the bulkhead defines turned out to be a convex region -- a covering box minus the
half-planes of its non-axis-aligned edges -- and where an edge's angle moves with the
parameters, `Placement.Rotation.Angle` takes an expression just as `Placement.Base` does.

The assembled section does contain one sketch, and it is not the bulkhead's: the greeble
tool is corner_end, and corner_end's wedge is one of the corner's two genuinely non-convex
profiles. Reusing the corner's description brings the corner's sketch with it.

What this proves that the isolated checks could not: `ref_bulkhead_cuts.scad` transcribes
five cut tools the source builds inline, so comparing against it only shows the port matches
the transcription. Here the reference goes through the real `bulkhead_section`, so a
transcription error is a volume divergence. Same for `ref_flange_boss.scad`, one level down.

IP-FC-41 is what made this possible at all. The constituents each carried their own sheet of
literal values; sharing a document means one sheet, and `corner_tree` -- which the greeble
tool is built from -- carries `fuselage_corner.scad`'s hand driver values, not the swept set.
The two disagree on six parameters, including greeble_thickness 0.8 against 1.2, which is the
snap post's wall. Merging them by name would have silently built the post at two thirds
thickness. So the sheet is *seeded* from `derived_parameters()` instead: every literal comes
from the authority, and only the '=' rows -- the relationships, which are the port itself --
have to agree between modules.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import bulkhead_cuts
import bulkhead_positive
import bulkhead_tree
import corner_tree as C
import fillets
import flange_base
import flange_boss
import greeble_web
import parameters
import simple_positives
import web
from corner_common import build_sheet, check_seed, is_entry_point, merge_params

REF = 865.7690714
EXPECT_BBOX = (-40.0, -13.6618, 0.0, 0.0, 5.1375, 6.0)

# corner_tree last: its '=' rows restate relationships the bulkhead modules also define, and
# putting it first would make every conflict message point at it rather than at the module
# that actually introduced the second definition.
SOURCES = [flange_base, greeble_web, fillets, flange_boss, simple_positives, web,
           bulkhead_cuts, C]


def merged_rows(seed):
    """Every constituent's alias table as one, seeded from the exported parameter set.

    `seed` is not optional here. Without it the merge is a comparison of two different
    configurations and refuses -- correctly, because at the hand driver's values this
    assembly would not be a bulkhead the sweep produces.
    """
    return merge_params(SOURCES, seed) + list(bulkhead_tree.GREEBLE_TOOL_PARAMS)


def sheet(doc, seed, rows=None):
    """One sheet for every constituent. `rows` lets a part built on top of this one -- see
    bulkhead_full.py -- add its own without a second sheet."""
    return build_sheet(doc, merged_rows(seed) if rows is None else rows, seed)


def emit(doc, seed, rows=None):
    C._SEEN.clear()
    sheet(doc, seed, rows)

    # simple_positives builds six; only the bolt three belong to a bulkhead that is not a
    # cowling. See its docstring -- this is the distinction the assembly exists to catch.
    positive = bulkhead_positive.flange_positive(doc)
    for name, part in (('SectionSimple', simple_positives.bolt_positives(doc)),
                       ('SectionWeb', web.bulkhead_web(doc))):
        positive = C._fuse(doc, name, positive, part)

    negative = C._fuse(doc, 'SectionTools', bulkhead_tree.greeble_tool(doc),
                       bulkhead_cuts.cuts(doc))

    tip = C._owned(doc, 'Part::Refine', 'BulkheadSection')
    tip.Source = C._cut(doc, 'SectionCut', positive, negative)
    doc.recompute()
    return tip


def main():
    args = [a for a in sys.argv[1:] if not a.endswith('.py')]
    if not args:
        print('usage: freecadcmd bulkhead_section.py params.json')
        print('generate params.json with tools/export_parameters.py')
        return 0

    seed = parameters.seed(args[0])
    doc = App.newDocument('bulkhead_section')
    tip = emit(doc, seed)
    s = tip.Shape
    d = s.Volume - REF
    bb = s.BoundBox
    got = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)

    print('PART:: CSG tree -- bulkhead_section assembled')
    print('  nodes   = %d, sketches = %d'
          % (len(doc.Objects), len([o for o in doc.Objects if o.isDerivedFrom(
              'Sketcher::SketchObject')])))
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD, through the real module)' % REF)
    print('  delta   = %+.7f  (%+.5f%%)' % (d, 100 * d / REF))
    print('  bbox    = [%s]' % ', '.join('%.4f' % v for v in got))
    print('  expect  = [%s]' % ', '.join('%.4f' % v for v in EXPECT_BBOX))
    print('  valid   = %s  solids=%d  faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    drift = check_seed(doc.getObject('Params'), seed)
    if drift:
        print('  sheet   = DISAGREES with derived_parameters():')
        for alias, got, want in drift:
            print('            %-24s sheet %-14s derived %s' % (alias, got, want))
    else:
        print('  sheet   = every seeded alias reproduces derived_parameters()')

    fail = []
    if drift:
        fail.append('the sheet does not reproduce the derived parameter set')
    if not s.isValid():
        fail.append('invalid shape')
    if len(s.Solids) != 1:
        fail.append('%d solids -- the octant is one connected body' % len(s.Solids))
    if abs(d) / REF > 1e-3:
        fail.append('volume off by more than 0.1%')
    if max(abs(a - b) for a, b in zip(got, EXPECT_BBOX)) > 1e-3:
        fail.append('bounding box moved')
    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
