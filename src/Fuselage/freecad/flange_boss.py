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
import math
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


def flange_boss(doc, make_web=True):
    """IP-FC-132: `make_web` selects which of `bulkhead_flange_positive`'s two branches
    built this -- both intersect the same quadrant, but only the `make_web` one flares the
    foot into a chamfer cone. The `make_web=False` branch is what an interconnect's
    mirrored top half builds (it has no web and no chamfer either), so the ring there is a
    plain cylinder with nothing fused to it.
    """
    P = 'Params.'
    r, rc = P + 'flange_boss_r', P + 'flange_boss_rc'
    ring = C._cyl(doc, 'BossBody', r, P + 'bulkhead_thickness', '0')
    if make_web:
        ring = C._fuse(doc, 'BossFuse', ring,
                       C._cone(doc, 'BossChamfer', rc, r, P + 'flange_chamfer',
                               P + 'plate_thickness'))
    # The quadrant square reaches flange_boss_rc on both axes, so it contains the flared
    # foot outright (where there is one); the intersection is a clean quarter either way.
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
    """Found while auditing IP-TEST-7 (doc/implementation/test_coverage.md): the per-part
    `checks` list below was printed but never aggregated into an exit code, so the script
    always exited 0 even when it had just printed INVALID/VOLUME/SIGN -- the same gap fixed
    in corner_common.report() for the part_*.py cluster.
    """
    doc = App.newDocument('flange_boss')
    tips = emit(doc)

    all_ok = True
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
        if checks:
            all_ok = False
        print('  %-20s %14.6f %14.6f %+12.6f %+8.4f%%  %s'
              % (tip.Name, s.Volume, ref, d, 100 * d / ref,
                 ' '.join(checks) if checks else 'ok'))
        bb = s.BoundBox
        print('  %-20s bbox [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
              % ('', bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    print('  result  = %s' % ('PASS' if all_ok else 'FAIL'))

    # make_web=False had no coverage at all before this -- bulkhead_positive.py calls it for
    # an interconnect's mirrored top half, which has no chamfer, so REFS (which only measures
    # the make_web=True build against ref_flange_boss.scad) never exercised it. There is no
    # ref_*.scad for this branch either, so it is checked against the closed form for a
    # quarter cylinder: pi * r^2 * bulkhead_thickness / 4.
    doc2 = App.newDocument('flange_boss_noweb')
    C._SEEN.clear()
    sheet(doc2)
    P = doc2.getObject('Params')
    r = float(P.get('flange_boss_r'))
    thickness = float(P.get('bulkhead_thickness'))
    plain_ref = math.pi * r * r * thickness / 4.0
    boss2 = flange_boss(doc2, make_web=False)
    doc2.recompute()
    s2 = boss2.Shape
    d2 = s2.Volume - plain_ref
    rel2 = d2 / plain_ref
    ok2 = s2.isValid() and len(s2.Solids) == 1 and abs(rel2) <= 1e-6

    print('PART:: CSG tree -- bulkhead_flange_positive quadrant boss (make_web=False)')
    print('  volume  = %.7f' % s2.Volume)
    print('  ref     = %.7f  (hand-derived closed form)' % plain_ref)
    print('  delta   = %+.7f  (%+.5f%%)' % (d2, 100 * rel2))
    print('  valid   = %s  solids=%d faces=%d'
          % (s2.isValid(), len(s2.Solids), len(s2.Faces)))
    print('  result  = %s' % ('PASS' if ok2 else 'FAIL'))

    return 0 if (all_ok and ok2) else 1


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
