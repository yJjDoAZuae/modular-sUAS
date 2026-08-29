"""IP-FC-87: the design relationships, written as a derivation and checked against the sweep.

`doc/design/dimension_scheme.md` section 2 is an *analysis* of the implementation -- decided in
OQ-DES-D9 on 2026-08-28 -- so a reading of it establishes that a drawing states what a part
measures, and not that the part is what anyone intended. This module is the other direction.
It states each design relationship as a **derivation from a chosen input**, and checks that the
sweep's parameters are what the derivation produces. Where a derivation cannot produce the
parameter, one of the two is wrong and the run says which field.

**The split that makes this a derivation rather than a restatement.** Every numeric field a
variant carries is either

  * a **given** -- a number somebody chose, listed in `GIVENS` with where it was chosen and
    why it could not be derived (a stock size, a standard, a tuned value, a clearance); or
  * a **derived** field -- produced by a `Relation` below from the givens and from values this
    module has already derived, never by reading the sweep's own answer.

`check_coverage` refuses a field that is neither. That is the property the arrangement lacked:
a parameter added to `fuselage_variants.py` fails here until somebody says whether it was
chosen or where it follows from, so the derivation cannot silently fall behind the geometry.

**A derived value never reads the implementation's value for anything.** The derivations chain
-- `panel.offset` needs the greeble wall, which is itself derived -- so an error in an early
relation surfaces in the later ones too. That is intended; the chain is the design's own order.

**What this cannot check.** These are the *parameters*. The relationships that live in the
geometry -- the corner's bore, its seating faces, the panel groove, the bulkhead's flange face,
the cowl flange's outer radius -- are checked against built solids elsewhere
(`freecad/check_drawing.py`, `tools/joint_analysis/`, `doc/design/corner_bulkhead_joint.md`)
and are derived in `doc/design/derivation.md` section 4 with the measurement beside each.

    python check_derivation.py                 # check every variant of every sweep
    python check_derivation.py corner          # one sweep
    python check_derivation.py --report        # print the derivation, one line per relation

Millimeters and degrees, as the OpenSCAD path uses them.
"""
import io
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import drawing_families as df
import fuselage_variants as fv


CONSTANTS_PATH = os.path.join(HERE, '..', 'design_constants.json')

#: Fields are compared this loosely. The derivations below are written in the shape of the
#: requirement rather than copied from `fuselage_variants.py`, so an equivalent expression can
#: associate its multiplications differently and land a bit or two away.
TOL = 1e-9


# ------------------------------------------------------------------------------------------
# What was chosen
# ------------------------------------------------------------------------------------------

# A field here is a number the design *picks*, and the note says where it is picked and why
# there is no rule to derive it from. Several of these notes are findings rather than
# explanations -- see doc/design/derivation.md section 6, which lists the ones nothing on
# record justifies.
GIVENS = {
    'bulkhead.U': 'the size axis itself (bulkhead_size_variants.csv)',
    'corner.FX': 'the bay-length axis (corner_size_variants.csv)',
    'printer.extrusion_width': 'a slicing setting (design_constants.json printer)',
    'printer.layer_height': 'a slicing setting (design_constants.json printer)',
    'bulkhead.thickness': 'tabulated per size step in bulkhead_size_variants.csv; no rule '
                          'relates it to U and none is on record',
    'bolt.diameter': 'tabulated per size step in bulkhead_size_variants.csv; a standard '
                     'fastener series, not a formula',
    'panel.thickness': 'stock: the panel is bought, so its thickness is a supplier size '
                       '(panel_variants.csv)',
    'greeble.opening_angle': 'tuned by experiment (design_constants.json geometry); the file '
                             'says explicitly not to replace it with a formula',
    'boom_bulkhead.key_angle': 'chosen at 0 so the key sits on the fuselage centerline',
    'cowl_flange.cowl_n_perimeters': 'a slicing setting: how many perimeters the COWL prints '
                                     'with, which is what its wall occupies',
    'longeron.tolerance': 'a clearance, chosen (design_constants.json tolerances)',
}


# ------------------------------------------------------------------------------------------
# Originating requirements
# ------------------------------------------------------------------------------------------

# **These come from outside the design and are traceable to nothing below them.** They are the
# axiomatic source the rest of the structure hangs from -- once they are reviewed and accepted.
# Until then they are PROPOSED, and this table is a reading of what the project has recorded
# rather than a statement anybody has ratified. `doc/design/derivation.md` section 2 gives each
# one its source and its argument.
#
# Nothing here is checkable by this module or by any other. An originating requirement is
# accepted by review; what the checkers verify is that the implementation satisfies the
# level-1 requirements, and that each of those either traces to one of these or is flagged as
# derived.
ORIGINATING = {
    'OR-1': 'one parametric standard produces the whole family of sizes',
    'OR-2': 'the airframe is modular: bays of four corners and two bulkheads, joined end '
            'to end',
    'OR-3': 'the outer surface is an aerodynamic mold line, continuous across every part '
            'that reaches it',
    'OR-4': 'panels are designed by others inside an allocated envelope, and interchange',
    'OR-5': 'structural parts are FDM printed; longerons, booms, panels, fasteners and '
            'inserts are bought',
    'OR-6': 'joints are bonded or fastened, and must accommodate print variation and bond '
            'thickness',
    'OR-7': 'the airframe assembles by hand, without jigs',
    'OR-8': 'the volume the airframe encloses is usable -- payload, wiring, and a hand',
    'OR-9': 'the drawing user is integrating with the structure, not inspecting a part',
}


# ------------------------------------------------------------------------------------------
# Level-1 system requirements
# ------------------------------------------------------------------------------------------

# **A level below the originating requirements. Most of these are DECOMPOSED from a parent;
# three are DERIVED, and the two words are not interchangeable.**
#
# A decomposed requirement is obtained by allocating a parent requirement to the system, and it
# traces to that parent. A **derived** requirement, in the sense INCOSE and ARP4754A/DO-178C
# both use, is one that is **not traceable to any higher-level requirement** -- it arises from
# the design solution itself, from a technology or implementation choice. That is a narrower
# narrower thing than "obtained by decomposition", and it matters: a derived requirement has no
# parent to validate it against, so it has to be reviewed and accepted on its own, exactly like
# an originating requirement. This table said "derived" of all ten and then checked that every
# one traced upward -- which, in the standard sense of the word, is a contradiction.
#
# `parents` is empty exactly when `derived` is True, and `check_traceability` enforces that in
# both directions: a requirement with no parent that is not flagged is an untraced requirement,
# and a flagged one with a parent is not derived. `rationale` is required on a derived
# requirement, because with nothing above it that sentence is the whole of its justification.
#
# Argued in `doc/design/derivation.md` section 4.


class Requirement(object):
    def __init__(self, statement, parents=(), derived=False, rationale=None):
        self.statement = statement
        self.parents = parents
        self.derived = derived
        self.rationale = rationale


SYSTEM = {
    'SR-1': Requirement(
        'airframe dimensions are proportional to U, and scale freely with it -- including '
        'below their 1U value on a sub-unit airframe',
        parents=('OR-1',)),
    'SR-2': Requirement(
        'a feature whose size the print process governs is sized in whole extrusions or whole '
        'layers',
        parents=('OR-5',)),
    'SR-3': Requirement(
        'every part reaching the outer surface lands on the mold line, and a joint\'s '
        'clearance is taken inboard of it',
        parents=('OR-3', 'OR-6')),
    'SR-4': Requirement(
        'a JOINT\'s clearance appears once, on one named side; the other side is nominal -- '
        'which is not the same as a clearance PARAMETER appearing on one part',
        derived=True,
        rationale='OR-6 requires that a joint accommodate print variation and bond thickness. '
                  'It does not say the accommodation is single-sided -- splitting it across '
                  'both halves would satisfy OR-6 equally. Putting it on one side is a design '
                  'decision, and its reason IS recorded (the joint would otherwise take '
                  'the clearance twice), which is what makes this a clean example of the two '
                  'axes being independent: recorded, and still derived. **The unit is the '
                  'joint, not the parameter.** `panel_tolerance` is carried by BOTH the corner '
                  '(register row 4) and the bulkhead (row 5), and that is not a violation: '
                  'those are two different joints with the same bought panel, and each takes '
                  'its own clearance once on its own printed side. SR-3 in fact requires it -- '
                  'the panel lies across both seats, so both must be set back by the same '
                  'pocket or it cannot sit flat on the mold line. Measured at 1U with a 3/16 '
                  'in panel: the corner seats at 5.1375 corner-local and the bulkhead at '
                  '45.1375 airframe, both mold line less 4.8625.'),
    'SR-5': Requirement(
        'the bought part is nominal and the printed part carries the fit',
        derived=True,
        rationale='follows from no parent. OR-5 says which parts are bought and OR-6 says the '
                  'joint needs clearance; neither implies the clearance goes on the printed '
                  'side. It is an allocation decision, and no reason for it is on record.'),
    'SR-6': Requirement(
        'at the corner/bulkhead interface the corner carries the clearance, so that the '
        'bulkhead\'s dimensions stay consistent across variants',
        derived=True,
        rationale='**Rationale stated 2026-08-29, so this is no longer inferred:** the corner '
                  'is less likely to have integrated components interfacing it than the '
                  'bulkhead, so the bulkhead is the part whose dimensions should stay '
                  'consistent, and the variation is allocated to the corner. **Both of this '
                  'module\'s earlier reconstructions were wrong** -- neither "four corners to '
                  'one bulkhead" nor "the corner is the part that is pressed in" is the '
                  'reason, and both read plausibly. It stays flagged derived pending '
                  'OQ-DES-DV5: a parent very likely exists in the project wiki, whose '
                  'Modularity4 says interchange must not affect fuselage structure and whose '
                  'objectives include facilitating system integration.'),
    'SR-7': Requirement(
        'where a joint does not exist its clearance is zero, and that zero is the absence of '
        'the joint rather than a fit set to nothing',
        parents=('OR-6', 'OR-9')),
    'SR-8': Requirement(
        'no part may intrude on the volume swept by another part\'s assembly motion',
        parents=('OR-7',)),
    'SR-9': Requirement(
        'a drawing states which of several competing requirements produced a dimension',
        parents=('OR-9',)),
    'SR-10': Requirement(
        'the panel envelope is fixed by the frame and stated without reference to any panel '
        'design',
        parents=('OR-4',)),
    'SR-11': Requirement(
        'where a feature\'s function is set by something that does not scale with the '
        'airframe, its size is floored at what that function requires',
        parents=('OR-5', 'OR-6')),
}


def check_traceability():
    """Every level-1 requirement either traces to a parent or is flagged derived, never both.

    A requirement with no parent that is not flagged is an *untraced* requirement: a design
    decision justified by nothing, and indistinguishable at a glance from one that follows from
    something. A requirement flagged derived that has a parent is mislabeled the other way, and
    that matters: a derived requirement carries a review obligation a decomposed one does
    not. Both are structural defects rather than wording problems, and both are invisible to a
    reader.

    Returns (complaints, notes). A note is not a failure: a requirement governing the drawing
    or the panel envelope reaches no parameter, so it is stated here and checked elsewhere.
    Reporting it keeps that gap visible instead of letting an unenforced requirement sit in the
    table looking enforced.
    """
    complaints = []
    for name in sorted(SYSTEM):
        req = SYSTEM[name]
        if req.derived:
            if req.parents:
                complaints.append('%s is flagged derived but has parents %s -- a derived '
                                  'requirement is one that traces to NO higher-level '
                                  'requirement' % (name, ', '.join(req.parents)))
            if not req.rationale:
                complaints.append('%s is derived and carries no rationale; with no parent '
                                  'above it, that sentence is its whole justification' % name)
        elif not req.parents:
            complaints.append('%s traces to no originating requirement and is not flagged '
                              'derived' % name)
        for origin in req.parents:
            if origin not in ORIGINATING:
                complaints.append('%s traces to %s, which is not an originating requirement'
                                  % (name, origin))

    used = set()
    for relation in RELATIONS + COWL_RELATIONS:
        for name in relation.serves:
            used.add(name)
            if name not in SYSTEM:
                complaints.append('%s names %s, which is not a level-1 requirement'
                                  % (relation.field, name))
    notes = ['%s reaches no parameter relation; it is checked elsewhere or not at all' % name
             for name in sorted(set(SYSTEM) - used)]
    return complaints, notes


class Relation(object):
    """One design relationship: what it produces, which requirements it serves, and how.

    `serves` is a tuple of level-1 requirement ids, not prose. That is what makes the trace a
    structure rather than a habit of wording: each id either resolves or the run says so. A
    tuple rather than one id because a feature commonly answers to more than one -- a printed
    wall is sized in whole extrusions (SR-2) *and* floored where its function does not scale
    (SR-11), and naming only the first would hide half of why it is what it is.
    """

    def __init__(self, field, serves, requirement, derive):
        self.field = field
        self.serves = (serves,) if isinstance(serves, str) else tuple(serves)
        self.requirement = requirement
        self.derive = derive

    def __repr__(self):
        return 'Relation(%r)' % (self.field,)


def _floored(coefficient, U):
    """`SR-11`: a feature that must not shrink with the airframe, held at its 1U size below 1U.

    **This is the exception, not the rule.** Most airframe dimensions are SR-1 and scale
    freely: at U=0.5 the corner radius is 5 against 10, the web 1.5 against 3, the flange
    fillet 1 against 2, the plate 0.4 against 0.8. Only four derived quantities floor --
    `bolt.thickness`, `bulkhead_flange.thickness`, `greeble.thickness` and its nub -- plus the
    boom key's three, which the sweep leaves at zero on every non-boom variant.

    Written as a helper because `max(n*U, n)` read as a bare expression looks like a
    coincidence of two literals, and because the floor's *reason* differs per feature: recorded
    for the greeble wall (a one-extrusion wall has no interior), unrecorded for the bolt boss
    and the boom key. See derivation.md section 8.
    """
    return max(coefficient * U, coefficient)


def _extrusions(count, U, w):
    """A wall of `count` extrusions at 1U, widened in whole extrusions as the airframe grows.

    `ceil` because a wall is printed in whole passes (SR-2): two and a half extrusion widths is
    not a thing a slicer can lay down, so the count rounds up and the wall takes the width that
    produces. Floored at the 1U wall under SR-11 -- a wall thin enough to stop printing has
    stopped being a wall, whatever the airframe is doing.
    """
    return max(math.ceil(count * U) * w, count * w)


# ------------------------------------------------------------------------------------------
# The derivations
# ------------------------------------------------------------------------------------------

def _panel_offset(g, d):
    """How far the panel's inboard edge stands off the longeron axis.

    Two requirements bear on it and the binding one wins.

    **R1 -- the panel must not run into the greeble.** The greeble is the C-shaped seat that
    grips the longeron; its outer perimeter is a circle about the longeron axis of radius
    `longeron_radius + longeron_tolerance + greeble_thickness + greeble_nub_thickness`, and
    `greeble_margin_extrusions` of clearance is kept outside that. The panel's inboard corner
    is the point (offset, seat_y) where `seat_y` is the groove bottom, so the corner is
    outside the clearance circle exactly when `offset**2 + seat_y**2 >= radius**2`.

    **R2 -- the corner has to be able to snap on.** The greeble's mouth faces the 45 degree
    diagonal and the corner presses onto the longeron sideways, so the corner's mating plane
    at `panel_overlap + panel_offset` must clear the greeble's extremity *measured along that
    diagonal*, plus the margin, plus `greeble_snap_clearance_per_u` of room to move. The
    margin is taken out of the radius before the projection and added back after, because it
    is a clearance normal to the plane and not a radial one: projecting it would shrink it by
    a factor of root 2 and the clearance would no longer be the clearance.

    The result is rounded UP to a whole `panel_offset_quantum_mm`, which is what puts the
    panel width on a readable grid.
    """
    if g['is_cowling']:
        return 0.0                               # SR-7: no panel, so no edge to stand off

    greeble_outer = (d['longeron.radius'] + g['longeron_tolerance']
                     + d['greeble.thickness'] + d['greeble.nub_thickness'])
    margin = g['greeble_margin_extrusions'] * g['w']
    clearance_radius = greeble_outer + margin

    seat_y = max(d['corner.radius'] - g['panel_thickness'] - d['panel.tolerance'], 0)
    if clearance_radius > seat_y:
        r1 = math.sqrt(clearance_radius * clearance_radius - seat_y * seat_y)
    else:
        r1 = 0.0

    snap = g['greeble_snap_clearance_per_u'] * g['U']
    r2 = greeble_outer / math.sqrt(2) + margin + snap - d['panel.overlap']

    offset = max(r1, r2, 0.0)

    # The corner's extension cannot reach past the diagonal that mirrors the quarter section.
    # NOTE: the clamp is applied before the rounding, so the rounding can carry the result
    # back over it -- see doc/design/derivation.md section 6.
    offset = min(offset, math.sqrt(2) * d['corner.radius'])

    quantum = g['panel_offset_quantum_mm']
    return quantum * math.ceil(offset / quantum)


def _bolt_radius(g, d):
    """The hole the fastener goes in.

    `P3`: the bolt and the threaded insert are both bought, so the hole is sized to them.
    A bolt gets a clearance hole at its own nominal; an anchor gets the insert's bore from
    `threaded_insert_dimensions.csv`, which is supplier data and so a given in its own right.
    """
    if g['is_anchor']:
        return fv.lookup_anchor_diameter(g['bolt_diameter']) / 2
    return g['bolt_diameter'] / 2


RELATIONS = (
    # -- the standard, scaled -------------------------------------------------------------
    Relation('bulkhead.width', 'SR-1',
             'the fuselage is unit_width across flats at 1U',
             lambda g, d: g['unit_width'] * g['U']),
    Relation('corner.length', 'SR-1',
             'a bay is unit_length long at 1U, and FX is the bay-length axis',
             lambda g, d: g['unit_length'] * g['U'] * g['FX']),
    Relation('corner.radius', 'SR-1',
             'the mold line turns each corner on an arc of corner_radius at 1U',
             lambda g, d: g['corner_radius'] * g['U']),
    Relation('longeron.radius', 'SR-1',
             'the longeron tube is longeron_radius at 1U',
             lambda g, d: g['longeron_radius'] * g['U']),
    Relation('bolt.offset', 'SR-1',
             'the bolt axis sits bolt_offset from the corner arc center at 1U',
             lambda g, d: g['bolt_offset'] * g['U']),

    # -- printed features -----------------------------------------------------------------
    Relation('greeble.thickness', ('SR-2', 'SR-11'),
             'the greeble wall is a printed feature sized to survive a snap fit, so it '
             'scales in extrusions and as sqrt(U) rather than as a fraction of the airframe; '
             'a one-extrusion wall has no interior, which is the floor',
             lambda g, d: max(g['greeble_wall_extrusions'] * math.sqrt(g['U']) * g['w'],
                              g['greeble_wall_extrusions'] * g['w'])),
    Relation('greeble.nub_thickness', 'SR-2',
             'the snap rib and the seat wall it stands on are one wall thickness, related by '
             'a formula rather than two independent parameters -- identity today',
             lambda g, d: fv.greeble_nub_thickness_of(d['greeble.thickness'])),
    Relation('bulkhead_flange.thickness', ('SR-2', 'SR-11'),
             'the flange wall is printed in whole perimeters; a cowling bulkhead gets one '
             'more than the rest because it carries the cowl',
             lambda g, d: _extrusions(g['cowl_bulkhead_flange_extrusions'] if g['is_cowling']
                                      else g['bulkhead_flange_extrusions'], g['U'], g['w'])),
    Relation('bolt.thickness', 'SR-11',
             'the boss around the bolt scales with the airframe but never below its 1U value',
             lambda g, d: _floored(g['bolt_thickness_per_u'], g['U'])),
    Relation('plate.thickness', 'SR-2',
             'the plate is a printed skin and wants to come out an exact number of passes, '
             'so it is a count of layer heights and not a length',
             lambda g, d: math.ceil(g['plate_layers'] * g['U']) * g['h']),
    Relation('web.width', 'SR-1',
             'a boom bulkhead\'s web is twice a frame bulkhead\'s: it carries the boom',
             lambda g, d: (g['boom_web_width_per_u'] if g['is_boom']
                           else g['frame_web_width_per_u']) * g['U']),
    Relation('web.fillet_radius', 'SR-1',
             'the fillet where the web meets the ring scales with the airframe',
             lambda g, d: g['web_fillet_radius_per_u'] * g['U']),
    Relation('bulkhead_flange.fillet_radius', 'SR-1',
             'the fillet at the flange root scales with the airframe',
             lambda g, d: g['bulkhead_flange_fillet_per_u'] * g['U']),
    Relation('bulkhead_flange.chamfer', 'SR-1',
             'the chamfer on the flange\'s leading edge scales with the airframe',
             lambda g, d: g['bulkhead_flange_chamfer_per_u'] * g['U']),

    # -- the panel ------------------------------------------------------------------------
    Relation('panel.tolerance', 'SR-7',
             'the gap the panel stands off the flange face by. A cowling bulkhead and a 0 mm '
             'panel take 0, and that zero is the absence of the joint rather than a fit set '
             'to nothing',
             lambda g, d: (0.0 if (g['is_cowling'] or g['panel_thickness'] == 0)
                           else g['panel_tolerance'])),
    Relation('panel.overlap', 'SR-11',
             'the length of panel captured in the corner\'s groove: at least one panel '
             'thickness, and never less than panel_overlap_min_mm of bond area, which is an '
             'absolute minimum and so does not scale',
             lambda g, d: (0.0 if (g['is_cowling'] or g['panel_thickness'] == 0)
                           else max(g['panel_thickness'], g['panel_overlap_min_mm']))),
    Relation('panel.offset', 'SR-8',
             'how far the panel\'s inboard edge stands off the longeron axis: far enough that '
             'it clears the greeble, and that the corner can still snap onto the longeron',
             _panel_offset),

    # -- who carries the clearance --------------------------------------------------------
    Relation('greeble.tolerance', 'SR-4',
             'the snap fit\'s clearance is carried entirely on the corner: its socket is '
             'opened out and the bulkhead\'s post stays nominal, so the joint takes the '
             'clearance once',
             lambda g, d: 0.0 if g['is_bulkhead'] else g['greeble_tolerance']),
    Relation('corner.tolerance', 'SR-6',
             'the two corner faces that seat against the bulkhead carry their clearance on '
             'the corner too -- the bulkhead cuts its socket from the same shape at 0',
             lambda g, d: g['corner_tolerance']),
    Relation('bolt.radius', 'SR-5',
             'the hole is sized to the bought fastener: a bolt to its own nominal, an anchor '
             'to the insert bore from the supplier table',
             _bolt_radius),

    # -- the cowl mount -------------------------------------------------------------------
    Relation('cowl_flange.height', 'SR-7',
             'the flange stands cowl_flange_height_per_u off the bulkhead face per U; a '
             'bulkhead that mounts no cowl has no flange, and that zero is structural',
             lambda g, d: g['cowl_flange_height_per_u'] * g['U'] if g['is_cowling'] else 0.0),
    Relation('cowl_flange.tolerance', 'SR-7',
             'the fit between the flange and the cowl that slides over it, on a cowling '
             'bulkhead only',
             lambda g, d: g['cowl_flange_tolerance'] if g['is_cowling'] else 0.0),

    # -- the boom -------------------------------------------------------------------------
    Relation('boom_bulkhead.diameter', 'SR-1',
             'the boom tube is bought; the sweep states its size as a fraction of unit_width '
             'so a whole airframe scales together',
             lambda g, d: d['bulkhead.width'] * g['boom_diameter'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.y_position', 'SR-1',
             'the boom\'s position across the fuselage, as a fraction of unit_width',
             lambda g, d: d['bulkhead.width'] * g['y_position'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.z_position', 'SR-1',
             'the boom\'s position up the fuselage, as a fraction of unit_width',
             lambda g, d: d['bulkhead.width'] * g['z_position'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.thickness', 'SR-1',
             'the boom bulkhead\'s own wall scales with the airframe',
             lambda g, d: g['boom_wall_per_u'] * g['U'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.collet_thickness', 'SR-1',
             'the collet wall that grips the boom scales with the airframe',
             lambda g, d: g['boom_collet_thickness_per_u'] * g['U'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.key_width', 'SR-11',
             'the anti-rotation key never shrinks below its 1U size',
             lambda g, d: (_floored(g['boom_key_width_per_u'], g['U'])
                           if g['is_boom'] else 0)),
    Relation('boom_bulkhead.key_height', 'SR-11',
             'the key\'s height is an independent dimension that happens to equal its width',
             lambda g, d: (_floored(g['boom_key_height_per_u'], g['U'])
                           if g['is_boom'] else 0)),
    Relation('boom_bulkhead.key_radius', 'SR-11',
             'the radius on the key never shrinks below its 1U size either',
             lambda g, d: (_floored(g['boom_key_radius_per_u'], g['U'])
                           if g['is_boom'] else 0)),
    Relation('boom_bulkhead.key_web_width', 'SR-1',
             'the web that carries the key scales with the airframe',
             lambda g, d: g['boom_key_web_width_per_u'] * g['U'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.tolerance', 'SR-7',
             'the boom tube\'s clearance in the collet, on a boom bulkhead only',
             lambda g, d: g['boom_tolerance'] if g['is_boom'] else 0),
)


# The cowl sweeps are not covered field by field -- their parameters come from JSON files that
# are largely shape control points rather than interfaces. One relation is derived here because
# it is a joint: the nose closure's seat on the cowl shell, register row 8.
COWL_RELATIONS = (
    Relation('nose.flange_inset', 'SR-3',
             'the nose seats on top of the cowl\'s perimeter shell, so the inset is the '
             'cowl\'s own wall -- cowl_n_perimeters extrusions -- plus the fit against it, '
             'which is negative because the joint is bonded and grips',
             lambda g, d: (g['cowl_n_perimeters'] * g['w'] + g['nose_flange_tolerance'])),
)


# ------------------------------------------------------------------------------------------
# Reading the chosen values
# ------------------------------------------------------------------------------------------

def constants():
    """The chosen numbers, read from the file that holds them rather than from `fv`'s globals.

    Reading the JSON directly is the point: relations like `corner.radius = corner_radius * U`
    are only worth checking if the standard's own value comes from the design file and not
    from the same module that produced the parameter.
    """
    raw = json.load(io.open(CONSTANTS_PATH, encoding='utf-8'))
    out = {}
    for group in ('tolerances', 'geometry', 'standard', 'scaling', 'printer', 'slicing'):
        for name, entry in raw[group].items():
            if name.startswith('_'):
                continue
            out[name] = entry['value'] if isinstance(entry, dict) else entry
    return out


def givens(kind, row, U, FX, const):
    """Everything a derivation is allowed to consume, and nothing the sweep derived."""
    g = dict(const)
    g['U'] = U
    g['FX'] = FX
    g['w'] = const['extrusion_width']
    g['h'] = const['layer_height']
    g['is_bulkhead'] = df.SWEEPS[kind].get('is_bulkhead', False)
    g['panel_thickness'] = float(row.get('panel_thickness_mm', 0))
    g['bolt_diameter'] = row.get('bulkhead_bolt_diameter', 0)
    for flag in ('is_end', 'is_interconnect', 'is_cowling', 'is_boom', 'is_anchor'):
        g[flag] = bool(row.get(flag, False))
    for name in ('boom_diameter', 'y_position', 'z_position'):
        g[name] = float(row.get(name, 0))
    return g


def variants(kind):
    """Every variant of one sweep, with the axis row it came from.

    `drawing_families.resolve` drops the raw row and a derivation needs it -- the chosen
    inputs live there -- so the enumeration is repeated here off the same axis CSVs and the
    same validity checks.
    """
    spec = df.SWEEPS[kind]
    printer, default_fx = df.settings()
    combinations = fv.flatten_param_space(
        fv.read_all_param_axes(fv.axes(*spec['axis_csvs'])))

    out = []
    for row in combinations:
        U = float(row['U'])
        FX = float(row.get('FX', default_fx))
        if spec.get('cowl'):
            dp = fv.derived_cowl_parameters(U, FX, row, printer)
            valid = True
        else:
            dp = fv.derived_parameters(U, FX, dict(row, FX=FX), printer, spec['is_bulkhead'])
            if 'family' in spec:
                valid = fv.family_is_valid(spec['family'], dp)
            else:
                valid = getattr(fv, spec['validity'])(dp)
        if not valid:
            continue
        out.append((row, U, FX, df.flatten(dp)))
    return out


def label(kind, row, U, FX):
    parts = ['%s U=%g' % (kind, U)]
    if 'FX' in row:
        parts.append('FX=%g' % FX)
    if row.get('panel_name'):
        parts.append(str(row['panel_name']))
    if row.get('bulkhead_type_name'):
        parts.append(str(row['bulkhead_type_name']))
    if row.get('nose_type_name') or row.get('tail_type_name'):
        parts.append(str(row.get('nose_type_name') or row.get('tail_type_name')))
    return ' '.join(parts)


# ------------------------------------------------------------------------------------------
# The check
# ------------------------------------------------------------------------------------------

def agrees(derived, built):
    if derived is None or built is None:
        return derived is built
    return abs(float(derived) - float(built)) <= TOL * max(1.0, abs(float(built)))


def derive_all(g, relations=RELATIONS):
    """Run the derivations in order, each seeing only givens and what came before it."""
    d = {}
    for relation in relations:
        d[relation.field] = relation.derive(g, d)
    return d


# ------------------------------------------------------------------------------------------
# The requirements, tested on the built value rather than recomputed
# ------------------------------------------------------------------------------------------

# A `Relation` writes the design's expression and compares it with the sweep's. For an
# expression as involved as `panel.offset` that is a restatement in the shape of the
# requirement, and a restatement can be wrong in the same way twice. So the requirements
# themselves are tested a second way, on the number the sweep produced: does the built offset
# actually satisfy them, and is it the smallest step of the grid that does?
#
# This never evaluates the offset formula, so it cannot fail in sympathy with it.

def panel_offset_requirements(g, flat):
    """R1, R2 and minimality, evaluated against the offset the sweep actually built."""
    if g['is_cowling']:
        return []

    offset = flat['panel.offset']
    overlap = flat['panel.overlap']
    greeble_outer = (flat['longeron.radius'] + g['longeron_tolerance']
                     + flat['greeble.thickness'] + flat['greeble.nub_thickness'])
    margin = g['greeble_margin_extrusions'] * g['w']
    clearance_radius = greeble_outer + margin
    seat_y = max(flat['corner.radius'] - g['panel_thickness'] - flat['panel.tolerance'], 0)
    reach = greeble_outer / math.sqrt(2) + margin + g['greeble_snap_clearance_per_u'] * g['U']
    quantum = g['panel_offset_quantum_mm']

    def holds(x):
        """R1: the panel's inboard corner is outside the greeble's clearance circle.
           R2: the corner's mating plane clears the greeble's diagonal extremity."""
        r1 = math.hypot(x, seat_y) >= clearance_radius - TOL
        r2 = x + overlap >= reach - TOL
        return r1 and r2

    complaints = []
    if not holds(offset):
        complaints.append('panel.offset %.4f satisfies neither requirement it exists for'
                          % offset)
    elif offset > 0 and holds(offset - quantum) and offset - quantum >= 0:
        complaints.append('panel.offset %.4f is a whole quantum larger than it needs to be'
                          % offset)
    return complaints


REQUIREMENTS = (panel_offset_requirements,)


def check_variant(kind, row, U, FX, flat, const, relations=RELATIONS):
    """Every relation, on one variant. Returns a list of complaints."""
    g = givens(kind, row, U, FX, const)
    d = derive_all(g, relations)
    where = label(kind, row, U, FX)

    complaints = []
    if relations is RELATIONS:
        for requirement in REQUIREMENTS:
            complaints.extend('%s -- %s' % (where, c) for c in requirement(g, flat))
    for relation in relations:
        if relation.field not in flat:
            complaints.append('%s -- %s is not a field this variant has'
                              % (where, relation.field))
            continue
        if not agrees(d[relation.field], flat[relation.field]):
            complaints.append('%s -- %s: derived %.6f, built %.6f'
                              % (where, relation.field, d[relation.field],
                                 flat[relation.field]))
    return complaints


def check_coverage(flat, relations=RELATIONS):
    """Every numeric field is either a declared given or a derived relation.

    This is what stops the derivation falling behind the geometry: a number added to
    `fuselage_variants.py` arrives here unclassified and fails, so somebody has to say whether
    it was chosen or say what it follows from.
    """
    derived = set(r.field for r in relations)
    unclassified = []
    for name, value in sorted(flat.items()):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if name in GIVENS or name in derived:
            continue
        unclassified.append(name)
    return unclassified


def check(kind):
    """One sweep. Returns (variant count, complaints)."""
    const = constants()
    relations = COWL_RELATIONS if df.SWEEPS[kind].get('cowl') else RELATIONS
    rows = variants(kind)
    complaints = []
    for row, U, FX, flat in rows:
        complaints.extend(check_variant(kind, row, U, FX, flat, const, relations))
    if not df.SWEEPS[kind].get('cowl') and rows:
        for name in check_coverage(rows[0][3], relations):
            complaints.append('%s -- %s is neither a declared given nor a derived relation'
                              % (kind, name))
    return len(rows), complaints


def report():
    """The requirement tree: L0, L1, and the relations under each."""
    print('L0 ORIGINATING -- proposed; accepted by review, checkable by nothing')
    for name in sorted(ORIGINATING):
        print('  %-6s %s' % (name, ORIGINATING[name]))
    print('')
    print('L1 SYSTEM -- decomposed from a parent, or DERIVED with its own justification')
    under = {}
    for relation in RELATIONS + COWL_RELATIONS:
        for name in relation.serves:
            under.setdefault(name, []).append(relation)
    for name in sorted(SYSTEM, key=lambda k: int(k.split('-')[1])):
        req = SYSTEM[name]
        print('  %-6s %s' % (name, req.statement))
        if req.derived:
            print('  %-6s DERIVED -- traces to no higher-level requirement' % '')
            print('  %-6s %s' % ('', req.rationale))
        else:
            print('  %-6s decomposed from %s' % ('', ', '.join(req.parents)))
        for relation in under.get(name, ()):
            print('           %-30s %s' % (relation.field, relation.requirement))
        if name not in under:
            print('           (no parameter relation -- checked elsewhere or not at all)')
        print('')
    print('given (chosen, not derived):')
    for name in sorted(GIVENS):
        print('    %-34s %s' % (name, GIVENS[name]))


def main(argv):
    if '--report' in argv:
        report()
        return 0

    kinds = [a for a in argv if a in df.SWEEPS] or list(df.SWEEPS)
    failed = 0

    # The trace first, because a relation checked against a requirement that is justified by
    # nothing is a number agreeing with a number.
    broken, notes = check_traceability()
    if broken:
        failed += 1
        print('traceability -- %d defects' % len(broken))
        for line in broken:
            print('    ' + line)
    else:
        derived = sorted(n for n in SYSTEM if SYSTEM[n].derived)
        print('traceability -- %d L1 requirements: %d decomposed from %d L0, %d DERIVED (%s), '
              'each carrying its own justification'
              % (len(SYSTEM), len(SYSTEM) - len(derived), len(ORIGINATING), len(derived),
                 ', '.join(derived)))
    for line in notes:
        print('    note: ' + line)

    for kind in kinds:
        count, complaints = check(kind)
        if complaints:
            failed += 1
            print('%s -- %d variants, %d disagreements' % (kind, count, len(complaints)))
            for line in complaints[:40]:
                print('    ' + line)
            if len(complaints) > 40:
                print('    ... and %d more' % (len(complaints) - 40))
        else:
            print('%s -- %d variants, every relation derives the built value' % (kind, count))
    if failed:
        print('')
        print('FAIL -- the derivation and the implementation disagree; one of them is wrong')
        return 1
    print('')
    print('ok -- every parameter is a stated choice or follows from one')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
