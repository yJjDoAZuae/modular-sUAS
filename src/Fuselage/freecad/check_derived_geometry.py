"""IP-FC-87: the derivation predicts where a face lands, and the built solid is asked.

`tools/check_derivation.py` derives the *parameters* and checks them against the sweep. That
leaves the half of the design that lives in the geometry -- the panel's seat, the corner's end
stop, the faces the bulkhead mates against -- where an expression and the solid it is supposed
to produce can disagree without any parameter being wrong. This is that half.

**The direction matters.** Nothing here measures the part and writes down what it finds. Each
entry states, from `doc/design/design_basis.md`, a face the design *requires*: its normal, where
it must sit, how big it must be, and whether it exists at all on this variant. Then the solid
is built and asked. A face that is missing, mispositioned or the wrong size is a disagreement
between the derivation and the implementation, and the run says which.

**Structural absence is part of the prediction, not an exemption.** A 0 mm panel variant has no
panel seat because there is no panel -- so the derivation predicts the face is *absent*, and a
face found there would be as much a failure as a missing one. That is DES-7 tested rather than
asserted: on a variant with no panel the seat merges into the mold line, and on the 24 corner
variants where the longeron branch stops governing the seating flat vanishes entirely.

    freecadcmd check_derived_geometry.py --pass variant.params.json
    freecadcmd check_derived_geometry.py --pass variant.params.json kind=bulkhead

Millimeters, in each part's own frame: the corner's arc center at the origin, the bulkhead's
frame centered on the airframe axis.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import FreeCAD as App

import build_part
from corner_common import is_entry_point

#: How closely a face has to land. This is a kernel-agreement tolerance, not a fit -- the
#: printed clearances in this design are 0.1 mm and up, and a face out by 1e-6 is a modeling
#: disagreement rather than a manufacturing one.
POSITION_TOL = 1e-6

#: Areas come out of a boolean history, so they are compared relatively.
AREA_TOL = 1e-7


class Face(object):
    """A face the derivation says the part must have.

    `present` is a prediction in its own right: False means the derivation says this feature
    does not exist on this variant, and finding it would be a failure.
    """

    def __init__(self, name, axis, position, area, present, requirement):
        self.name = name
        self.axis = axis
        self.position = position
        self.area = area
        self.present = present
        self.requirement = requirement


def corner_faces(p):
    """The corner's interface faces, derived. See design_basis.md section 5, INT-1 and INT-4.

    Corner-local: the arc center at the origin, the mold line at `corner_radius`, the arm
    running out along -x toward the panel. The part is mirrored about x = y, so every face
    here has a twin with its axes swapped; the check accepts either.
    """
    radius = p['corner_radius']
    thickness = p['panel_thickness']
    fit = p['panel_tolerance']
    overlap = p['panel_overlap']
    offset = p['panel_offset']
    length = p['unit_length'] * p['FX']

    # DES-3: the panel's outer surface IS the mold line, so its seat is set back from the mold
    # line by the panel and its fit, and no material stands outboard of the panel at all.
    seat_y = radius - thickness - fit

    # The end stop the panel butts against, one fit short of the panel's own edge so the panel
    # lands on clearance rather than on the stop.
    stop_x = -(offset - fit)

    # DES-9 on the seating flat: the diagonal is placed one longeron_chamfer outside the bore
    # where it crosses the axis, unless the panel interface has been pushed further out, in
    # which case the flat closes up entirely and the diagonal meets the seat.
    bore_branch = p['longeron_radius'] + p['longeron_tolerance'] + p['extrusion_width']
    panel_branch = (overlap + offset) - seat_y
    seat_span = max(bore_branch, panel_branch) - panel_branch

    panelled = (thickness + fit) > 0

    return [
        Face('mold line', 'Y', radius, (offset - fit) * length, True,
             'DES-3: the corner meets the panel at the mold line and stops there'),
        Face('panel seat', 'Y', seat_y, (overlap + fit) * length, panelled,
             'DES-3: the seat is set back by the panel and its fit, so the panel lands flush'),
        Face('panel end stop', 'X', stop_x, (thickness + fit) * length, panelled,
             'DES-5: the panel bottoms out on clearance, not on the stop'),
        Face('bulkhead seating flat', 'X', -(overlap + offset) + p['corner_tolerance'],
             seat_span * length, seat_span > 0,
             'DES-9: what the bore branch has left above the panel interface, and nothing '
             'when the panel branch governs'),
    ]


def bulkhead_faces(p):
    """The bulkhead's panel seat, derived. See design_basis.md section 5, INT-5.

    The bulkhead's outer flat face *is* the panel's seating surface: set back from the mold
    line by the panel pocket, and running exactly the panel's exposed span. That is why a
    panel is not interrupted at a station -- the bulkhead gives way to it.

    **The face does not vanish when the panel does; the setback does.** On a 0 mm panel
    variant the pocket is zero and this face lands *on* the mold line, still running the full
    span between the corners. That is the difference between this face and the corner's seat,
    which vanishes outright because its width is the overlap and the overlap goes to zero.
    The first form of this prediction had them behaving alike and the 0 mm bulkhead is what
    said otherwise.
    """
    half = p['unit_width'] / 2.0
    pocket = p['panel_thickness'] + p['panel_tolerance']
    width = p['unit_width'] - 2 * (p['corner_radius'] + p['panel_offset'])
    exposed = width - 2 * p['panel_overlap']

    return [
        Face('outer face', 'Y', half - pocket, exposed * p['bulkhead_thickness'], True,
             'DES-3: the mold line less the panel pocket, running the panel\'s exposed span'),
    ]


DERIVED = {'corner': corner_faces, 'bulkhead': bulkhead_faces}


def planar_faces(shape):
    """Axis-normal planar faces as (axis, position, area), the only ones predicted here."""
    out = []
    for face in shape.Faces:
        if face.Surface.TypeId != 'Part::GeomPlane':
            continue
        normal = face.normalAt(0, 0)
        center = face.CenterOfMass
        for axis, component, position in (('X', normal.x, center.x),
                                          ('Y', normal.y, center.y),
                                          ('Z', normal.z, center.z)):
            if abs(abs(component) - 1.0) < 1e-7:
                out.append((axis, position, face.Area))
    return out


def matches(found, predicted):
    """Faces sitting where this one is predicted, on either of the mirrored axes.

    The corner is mirrored about x = y, so a face predicted normal to Y at some position has a
    twin normal to X at the same position. Accepting either is what lets one prediction cover
    both arms without stating the symmetry twice.
    """
    if predicted.axis in ('X', 'Y'):
        axes = ('X', 'Y')
    else:
        axes = (predicted.axis,)
    return [f for f in found
            if f[0] in axes and abs(f[1] - predicted.position) <= POSITION_TOL]


def check(kind, params, shape):
    found = planar_faces(shape)
    predictions = DERIVED[kind](params)
    complaints = []
    for predicted in predictions:
        hits = matches(found, predicted)
        if not predicted.present:
            # **Absence is not the same as nothing being there.** Where a feature vanishes it
            # usually vanishes by *merging*: with no panel the seat collapses onto the mold
            # line and the end stop onto the seating flat, so a face is still found at the
            # derived coordinate and it belongs to the other feature. What the derivation
            # forbids is an EXTRA face -- one at that coordinate that no other prediction
            # accounts for -- so that is what is checked.
            others = [q for q in predictions
                      if q is not predicted and q.present
                      and abs(q.position - predicted.position) <= POSITION_TOL]
            stray = [a for _, _, a in hits
                     if not any(abs(a - q.area) <= AREA_TOL * max(1.0, q.area)
                                for q in others)]
            if stray:
                complaints.append(
                    '%s: derived as absent on this variant, but the part has a face at %.4f '
                    'of %s mm2 that no other feature accounts for (%s)'
                    % (predicted.name, predicted.position,
                       ', '.join('%.4f' % a for a in stray), predicted.requirement))
            elif others:
                print('  %-22s absent, merged into %s, as derived'
                      % (predicted.name, others[0].name))
            else:
                print('  %-22s absent, as derived   (%s)'
                      % (predicted.name, predicted.requirement))
            continue
        if not hits:
            complaints.append('%s: derived at %.4f, and the part has no face there (%s)'
                              % (predicted.name, predicted.position, predicted.requirement))
            continue
        areas = [a for _, _, a in hits]
        if not any(abs(a - predicted.area) <= AREA_TOL * max(1.0, predicted.area)
                   for a in areas):
            complaints.append(
                '%s: at %.4f as derived, but %.4f mm2 was derived and the part has %s'
                % (predicted.name, predicted.position, predicted.area,
                   ', '.join('%.4f' % a for a in areas)))
            continue
        print('  %-22s %10.4f   %10.4f mm2   as derived'
              % (predicted.name, predicted.position, predicted.area))
    return complaints


PARAMS_KEY = {'corner': 'corner_parameters', 'bulkhead': 'parameters'}


def main(argv):
    paths = [a for a in argv if a.endswith('.json')]
    if not paths:
        print('usage: freecadcmd check_derived_geometry.py --pass params.json [kind=KIND]')
        return 2

    kind = 'corner'
    for argument in argv:
        # `freecadcmd`'s own option parser claims a bare `--kind` even after `--pass`, so the
        # bare `kind=` spelling is the one that survives it. Both are accepted.
        for prefix in ('--kind=', 'kind='):
            if argument.startswith(prefix):
                kind = argument.split('=', 1)[1]
    if kind not in DERIVED:
        print('nothing derived for %r -- have %s' % (kind, ', '.join(sorted(DERIVED))))
        return 2

    with open(paths[0], encoding='utf-8') as handle:
        exported = json.load(handle)
    params = exported[PARAMS_KEY[kind]]

    print('CHECK:: the derivation against the built solid')
    print('  kind                %s' % kind)
    print('  variant             %s' % exported.get('variant', '?'))

    doc = App.newDocument('check_derived_geometry')
    shape = build_part.build(doc, kind, paths[0])
    if hasattr(shape, 'Shape'):
        shape = shape.Shape
    print('  solid               %.4f mm3, %d faces' % (shape.Volume, len(shape.Faces)))

    complaints = check(kind, params, shape)
    print('')
    if complaints:
        for line in complaints:
            print('  FAIL  ' + line)
        print('')
        print('FAIL -- the derivation and the part disagree; one of them is wrong')
        return 1
    print('ok -- every face the derivation requires is where it says, and the ones it says '
          'are absent are absent')
    return 0


if is_entry_point(__name__):
    # The flush is not decoration: under `freecadcmd` a `sys.exit` with buffered stdout loses
    # the whole report, so the run looks like it printed nothing rather than like it failed.
    _code = main(sys.argv)
    sys.stdout.flush()
    sys.exit(_code)
