"""IP-FC-85: the panel OML becomes a part, decided in OQ-DES-D4 on 2026-08-22.

A panel is cut sheet, not a printed part, and the sweep's assumptions are about prints -- so
this is deliberately not wired into `fuselage_variants.py`'s sweep or `part_kinds.BUILT_TYPES`.
What a panel *is* stays a design left to whoever cuts one; what this builds is the **envelope**
it must fit inside, so a candidate design can be checked against it by containment rather than
by someone comparing it against transcribed numbers -- which is what interchange actually
needs.

Every boundary here is an expression over parameters that IP-FC-87 already verified against
built faces, not a new measurement:

    width, corner to corner        unit_width - 2*(corner_radius + panel_offset)
    exposed span between corners   width - 2*panel_overlap
    pocket it seats in             panel_thickness + panel_tolerance
    inner face, from the axis      unit_width/2 - panel_thickness - panel_tolerance
    outer face                     the mold line, unit_width/2
    length along the bay           unit_length, the full bay

**One box, not four.** "One envelope serves all four faces of a bay" was established while
OQ-DES-D4 was open and is not re-derived here: a cowling station never touches a side face, and
the boom runs parallel to the fuselage axis with 12.94 mm to clear even at its worst case. What
differs between the four faces of a bay is the panel *design* fitted into the envelope, not the
envelope, so this builds one canonical instance -- the +X face, inner face at
`unit_width/2 - panel_thickness - panel_tolerance` and outer face at the mold line -- and the
other three are the same box at 90, 180 and 270 degrees, left to whatever assembles a bay rather
than baked in here.

There is no cross-engine reference: a panel is not part of the OpenSCAD sweep, so there is
nothing to render and compare. What `main()` checks instead is that the built box's own faces
land on the closed-form expressions above -- the same role `check_derived_geometry.py` plays
for the printed parts, run here directly against the one solid this module builds.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import build_sheet, is_entry_point

# U = 1.0, 3/16 in panel -- the same reference configuration bulkhead_cuts.py and corner_tree.py
# check against, so a number quoted here is comparable to a number quoted there.
PARAMS = [
    ('U', '1.0'),
    ('FX', '1.0'),
    ('panel_thickness', '4.7625'),
    ('panel_offset', '2.5'),
    ('panel_overlap', '4.7625'),
    ('panel_tolerance', '0.1'),

    ('unit_width', '=U * 100'),
    ('corner_radius', '=U * 10'),
    ('unit_length', '=U * FX * 100'),

    # The envelope's own dimensions, named rather than inlined so a placement expression
    # reads as what it is instead of as arithmetic to re-derive.
    ('width', '=unit_width - 2 * (corner_radius + panel_offset)'),
    ('half_width', '=width / 2'),
    ('exposed_span', '=width - 2 * panel_overlap'),
    ('pocket_depth', '=panel_thickness + panel_tolerance'),
    ('inner_face', '=unit_width / 2 - panel_thickness - panel_tolerance'),
    ('outer_face', '=unit_width / 2'),
]

REF_WIDTH = 75.000
REF_EXPOSED_SPAN = 65.475
REF_POCKET_DEPTH = 4.8625
REF_INNER_FACE = 45.1375
REF_OUTER_FACE = 50.000
REF_LENGTH = 100.000


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def envelope(doc):
    """The +X face's envelope: a box from the inner (pocket) face to the mold line."""
    P = 'Params.'
    box = C._box(doc, 'PanelEnvelope', P + 'pocket_depth', P + 'width', P + 'unit_length',
                 P + 'inner_face', '-' + P + 'half_width', '0')
    doc.recompute()
    return box


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    return envelope(doc)


def main():
    doc = App.newDocument('panel_oml')
    tip = emit(doc)
    s = tip.Shape
    bb = s.BoundBox

    print('PART:: panel OML envelope (+X face)')
    print('  bbox    = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
          % (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    print('  valid   = %s   solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    width = bb.YMax - bb.YMin
    depth = bb.XMax - bb.XMin
    length = bb.ZMax - bb.ZMin
    exposed_span = doc.Params.get('exposed_span')
    print('  width          = %.4f  (expect %.4f)' % (width, REF_WIDTH))
    print('  exposed span   = %.4f  (expect %.4f, not a box dimension -- printed for the '
          'record)' % (exposed_span, REF_EXPOSED_SPAN))
    print('  pocket depth   = %.4f  (expect %.4f)' % (depth, REF_POCKET_DEPTH))
    print('  inner face x   = %.4f  (expect %.4f)' % (bb.XMin, REF_INNER_FACE))
    print('  outer face x   = %.4f  (expect %.4f)' % (bb.XMax, REF_OUTER_FACE))
    print('  length         = %.4f  (expect %.4f)' % (length, REF_LENGTH))

    fail = []
    if not s.isValid():
        fail.append('invalid shape')
    if len(s.Solids) != 1:
        fail.append('%d solids -- expected one box' % len(s.Solids))
    for label, got, expect in (
            ('width', width, REF_WIDTH), ('exposed span', exposed_span, REF_EXPOSED_SPAN),
            ('pocket depth', depth, REF_POCKET_DEPTH), ('inner face', bb.XMin, REF_INNER_FACE),
            ('outer face', bb.XMax, REF_OUTER_FACE), ('length', length, REF_LENGTH)):
        if abs(got - expect) > 1e-9:
            fail.append('%s off: got %.6f, expected %.6f' % (label, got, expect))
    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
