"""IP-FC-9: the quadrant boss block of bulkhead_flange_positive.

The ring of flange material standing around the longeron bore, flared out into the plate by
a chamfer cone, kept only in the corner quadrant. The source builds this inline rather than
as a named module, so `ref_flange_boss.scad` transcribes it -- see the note there about what
that does and does not prove.

This is the first ported piece whose *positive* is bounded by a curved surface over its full
height, so the tessellation bias runs the other way from the fillets: FreeCAD's true cylinder
holds more material than OpenSCAD's inscribed prism, and the delta must come out positive. A
negative delta here would mean an error, exactly as a positive one would in `fillets.py`.

Derived parameters for U=1.0 end_bolt 3/16in, make_web = true.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import build_sheet, is_entry_point

REFS = {'FlangeBoss': 352.4642526}

PARAMS = [
    ('bulkhead_thickness', '6'),
    ('panel_offset', '2.5'),
    ('panel_overlap', '4.7625'),
    ('panel_tolerance', '0.1'),
    ('plate_thickness', '0.8'),
    ('flange_thickness', '1.2'),
    ('flange_chamfer', '1.0'),

    # the flange's outer face, and the wider foot the chamfer flares out to at the plate
    ('flange_boss_r', '=panel_tolerance + panel_offset + panel_overlap + flange_thickness'),
    ('flange_boss_rc', '=flange_boss_r + flange_chamfer'),
]


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def _common(doc, name, base, tool):
    node = C._owned(doc, 'Part::Common', name)
    node.Base, node.Tool = base, tool
    return node


def flange_boss(doc):
    P = 'Params.'
    r, rc = P + 'flange_boss_r', P + 'flange_boss_rc'
    ring = C._fuse(doc, 'BossFuse',
                   C._cyl(doc, 'BossBody', r, P + 'bulkhead_thickness', '0'),
                   C._cone(doc, 'BossChamfer', rc, r, P + 'flange_chamfer',
                           P + 'plate_thickness'))
    # The quadrant square reaches flange_boss_rc on both axes, so it contains the flared
    # foot outright; the intersection is a clean quarter for any parameters.
    quad = C._box(doc, 'BossQuadrant', rc, rc, P + 'bulkhead_thickness',
                  '-' + rc, '-' + rc, '0')
    tip = C._owned(doc, 'Part::Refine', 'FlangeBoss')
    tip.Source = _common(doc, 'BossCommon', ring, quad)
    return tip


def emit(doc):
    C._SEEN.clear()
    sheet(doc)
    tips = [flange_boss(doc)]
    doc.recompute()
    return tips


def main():
    doc = App.newDocument('flange_boss')
    tips = emit(doc)

    print('PART:: CSG tree -- bulkhead_flange_positive quadrant boss')
    print('  %-20s %14s %14s %12s %9s  %s'
          % ('module', 'tree', 'OpenSCAD', 'delta', 'rel', 'checks'))
    for tip in tips:
        ref = REFS[tip.Name]
        s = tip.Shape
        d = s.Volume - ref
        checks = []
        if not s.isValid():
            checks.append('INVALID')
        if len(s.Solids) != 1:
            checks.append('solids=%d' % len(s.Solids))
        if abs(d) / ref > 1e-3:
            checks.append('VOLUME')
        if d < 0:
            checks.append('SIGN -- curved positive must exceed the inscribed prism')
        print('  %-20s %14.6f %14.6f %+12.6f %+8.4f%%  %s'
              % (tip.Name, s.Volume, ref, d, 100 * d / ref,
                 ' '.join(checks) if checks else 'ok'))
        bb = s.BoundBox
        print('  %-20s bbox [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
              % ('', bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))


if is_entry_point(__name__):
    main()
