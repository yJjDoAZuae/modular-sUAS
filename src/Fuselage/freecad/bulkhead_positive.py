"""IP-FC-9 / IP-FC-41: bulkhead_flange_positive assembled from its ported constituents.

Eight pieces, all positives, union'd:

    flange_base           the extruded base profile
    flange_chamfer        the chamfer along the flange at the plate
    flange_boss           the quadrant ring around the longeron bore
    outer_corner_fillet
    greeble_bolt_web
    greeble_to_web_fillet
    web_to_bolt_fillet
    bolt_flange_fillet

Each was checked on its own against an isolated OpenSCAD reference. This assembles them
against the real `bulkhead_flange_positive`, which is what makes `ref_flange_boss.scad`
trustworthy -- that file transcribes geometry the source builds inline, so on its own it
proves only that the port matches the transcription. Here the reference goes through the
module itself, and a transcription error would show up as a volume divergence.

IP-FC-41: the constituents each carried their own parameter sheet, which was fine in
isolation but would collide the moment two of them shared a document. This merges them into
one sheet and *asserts* that no alias is defined two different ways -- the check is kept
permanently rather than run once, because the failure mode is silent: FreeCAD would take
whichever definition landed in the row and the geometry would quietly follow the wrong one.

Derived parameters for U=1.0 end_bolt 3/16in, make_web = true, is_interconnect = false,
is_cowling = false.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
import fillets
import flange_base
import flange_boss
import greeble_web
from corner_common import build_sheet, is_entry_point, merge_params

REF = 982.5042986
EXPECT_BBOX = (-40.0, -9.5625, 0.0, 0.0, 5.1375, 6.0)

# Order is presentation only -- the sheet is a dependency graph, not a program, and FreeCAD
# resolves it after every cell is set.
SOURCES = [flange_base, greeble_web, fillets, flange_boss]


def sheet(doc, seed=None):
    return build_sheet(doc, merge_params(SOURCES, seed), seed)


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    return flange_positive(doc)


def flange_positive(doc):
    """Geometry only, against whatever sheet the document already has."""
    parts = [flange_base.flange_base(doc),
             fillets.flange_chamfer(doc),
             flange_boss.flange_boss(doc),
             fillets.outer_corner_fillet(doc),
             greeble_web.greeble_bolt_web(doc),
             fillets.greeble_to_web_fillet(doc),
             fillets.web_to_bolt_fillet(doc),
             fillets.bolt_flange_fillet(doc)]

    node = parts[0]
    for i, part in enumerate(parts[1:], start=1):
        node = C._fuse(doc, 'PositiveFuse%d' % i, node, part)

    tip = C._owned(doc, 'Part::Refine', 'FlangePositive')
    tip.Source = node
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('bulkhead_positive')
    tip = emit(doc)
    s = tip.Shape
    d = s.Volume - REF

    print('PART:: CSG tree -- bulkhead_flange_positive assembled')
    print('  constituents = %d, nodes = %d' % (8, len(doc.Objects)))
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD, through the real module)' % REF)
    print('  delta   = %+.7f  (%+.5f%%)' % (d, 100 * d / REF))
    bb = s.BoundBox
    got = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)
    print('  bbox    = [%s]' % ', '.join('%.4f' % v for v in got))
    print('  expect  = [%s]' % ', '.join('%.4f' % v for v in EXPECT_BBOX))
    print('  valid   = %s  solids=%d  faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    fail = []
    if not s.isValid():
        fail.append('invalid shape')
    if len(s.Solids) != 1:
        fail.append('%d solids -- the constituents should overlap into one' % len(s.Solids))
    if abs(d) / REF > 1e-3:
        fail.append('volume off by more than 0.1%')
    if max(abs(a - b) for a, b in zip(got, EXPECT_BBOX)) > 1e-3:
        fail.append('bounding box moved')
    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout, so a
    # bare sys.exit(main()) loses the whole report.
    sys.stdout.flush()
    sys.exit(_code)
