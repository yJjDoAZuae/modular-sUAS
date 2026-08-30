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
and are derived in `doc/design/design_basis.md` section 4 with the measurement beside each.

    python check_derivation.py                 # check every variant of every sweep
    python check_derivation.py corner          # one sweep
    python check_derivation.py --report        # print the derivation, one line per relation
    python check_derivation.py --requirements  # delegates to requirements.py, the register

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
# explanations -- see doc/design/design_basis.md section 6, which lists the ones nothing on
# record justifies.
GIVENS = {
    'bulkhead.U': 'the size axis itself (bulkhead_size_variants.csv)',
    'corner.FX': 'the bay-length axis (corner_size_variants.csv)',
    'printer.extrusion_width': 'a slicing setting (design_constants.json printer)',
    'printer.layer_height': 'a slicing setting (design_constants.json printer)',
    'bulkhead.thickness': 'tabulated per size step in bulkhead_size_variants.csv. OQ-DES-DB2, '
                          '2026-08-29: a design choice made on a tradeoff of several factors '
                          'and objectives, tracing to no formula and to no higher requirement. '
                          'Airframe size is a DISCRETE SERIES OF EIGHT and a ninth step means '
                          'choosing again. 4*U fits six of the eight rows and must not be '
                          'adopted -- the small sizes are thicker than proportion because they '
                          'were chosen to be',
    'bolt.diameter': 'tabulated per size step in bulkhead_size_variants.csv; a standard '
                     'fastener series, not a formula. OQ-DES-DB2, 2026-08-29: chosen per step '
                     'on the same tradeoff as bulkhead.thickness',
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
# The requirements
# ------------------------------------------------------------------------------------------

# **The register lives in `requirements.py`, not here.** It used to be three tables in this
# file, which made this module two things -- a derivation of the parameters and a register of
# the requirements they serve -- and put a second copy of every statement beside the one in
# `doc/design/system_requirements.md`. Two copies of a requirement is the failure the register
# exists to prevent, so keeping one here would have been the register contradicting itself.
#
# What stays here is the half of the trace that is about *relations*: every relation names a
# design requirement, and that id has to resolve. `requirements.py` owns the other half -- do
# citations resolve to a tier above, does anything skip a tier, does the document state the
# same set -- and running it is a separate check with its own exit code.

import requirements as rq

ARCHITECTURE = rq.ARCHITECTURE
DESIGN = rq.DESIGN
INTERFACE = rq.INTERFACE          # re-exported for readers that had it from here


def check_traceability():
    """Every relation names a design requirement that exists.

    The requirement register's own structure -- citations resolving to a tier above, level
    skips, sources, verifiers, and agreement with `doc/design/system_requirements.md` -- is
    checked by `requirements.py`. This is the part only this module can check: a relation is
    justified by naming a `DES-` id rather than by describing its reason in prose, and an id
    that resolves to nothing means a number is justified by something that is not a
    requirement.

    Returns (complaints, notes). A note is not a failure: it reports a design requirement that
    reaches no parameter relation, so a rule nothing enforces cannot sit in the table looking
    enforced.
    """
    complaints = []
    used = set()
    for relation in RELATIONS + COWL_RELATIONS:
        for name in relation.serves:
            used.add(name)
            if name not in DESIGN:
                complaints.append('%s names %s, which is not a design requirement'
                                  % (relation.field, name))
    notes = ['%s reaches no parameter relation; it is checked elsewhere or not at all' % name
             for name in sorted(set(DESIGN) - used)]
    return complaints, notes

class Relation(object):
    """One design relationship: what it produces, which requirements it serves, and how.

    `serves` is a tuple of level-1 requirement ids, not prose. That is what makes the trace a
    structure rather than a habit of wording: each id either resolves or the run says so. A
    tuple rather than one id because a feature commonly answers to more than one -- a printed
    wall is sized in whole extrusions (DES-2) *and* floored where its function does not scale
    (DES-11), and naming only the first would hide half of why it is what it is.
    """

    def __init__(self, field, serves, requirement, derive):
        self.field = field
        self.serves = (serves,) if isinstance(serves, str) else tuple(serves)
        self.requirement = requirement
        self.derive = derive

    def __repr__(self):
        return 'Relation(%r)' % (self.field,)


def _floored(coefficient, U):
    """`DES-11`: a feature that must not shrink with the airframe, held at its 1U size below 1U.

    **This is the exception, not the rule.** Most airframe dimensions are DES-1 and scale
    freely: at U=0.5 the corner radius is 5 against 10, the web 1.5 against 3, the flange
    fillet 1 against 2, the plate 0.4 against 0.8. Only four derived quantities floor --
    `bolt.thickness`, `bulkhead_flange.thickness`, `greeble.thickness` and its nub -- plus the
    boom key's three, which the sweep leaves at zero on every non-boom variant.

    Written as a helper because `max(n*U, n)` read as a bare expression looks like a
    coincidence of two literals, and because the floor's *reason* differs per feature: recorded
    for the greeble wall (a one-extrusion wall has no interior), unrecorded for the bolt boss
    and the boom key. See design_basis.md section 8.
    """
    return max(coefficient * U, coefficient)


def _extrusions(count, U, w):
    """A wall of `count` extrusions at 1U, widened in whole extrusions as the airframe grows.

    `ceil` because a wall is printed in whole passes (DES-2): two and a half extrusion widths is
    not a thing a slicer can lay down, so the count rounds up and the wall takes the width that
    produces. Floored at the 1U wall under DES-11 -- a wall thin enough to stop printing has
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
        return 0.0                               # DES-7: no panel, so no edge to stand off

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

    # A GUARD against an excessively large panel offset, recorded 2026-08-29 under OQ-DES-DB1.
    # It has never fired: zero of the 528 non-cowling variants reach it, and at 1U the
    # requirements produce 2.5 against a clamp at 14.14. **The ordering is deliberate** -- the
    # guard bounds the requirement-driven value and the quantum is applied last, so whatever
    # leaves this expression sits on the 0.25 mm grid. Clamping after the rounding would return
    # an off-grid offset in exactly the case the guard fires.
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
    Relation('bulkhead.width', 'DES-1',
             'the fuselage is unit_width across flats at 1U',
             lambda g, d: g['unit_width'] * g['U']),
    Relation('corner.length', 'DES-1',
             'a bay is unit_length long at 1U, and FX is the bay-length axis',
             lambda g, d: g['unit_length'] * g['U'] * g['FX']),
    Relation('corner.radius', 'DES-1',
             'the mold line turns each corner on an arc of corner_radius at 1U',
             lambda g, d: g['corner_radius'] * g['U']),
    Relation('longeron.radius', 'DES-1',
             'the longeron tube is longeron_radius at 1U',
             lambda g, d: g['longeron_radius'] * g['U']),
    Relation('bolt.offset', 'DES-1',
             'the bolt axis sits bolt_offset from the corner arc center at 1U',
             lambda g, d: g['bolt_offset'] * g['U']),

    # -- printed features -----------------------------------------------------------------
    Relation('greeble.thickness', ('DES-2', 'DES-11'),
             'the greeble wall is a printed feature sized to survive a snap fit, so it '
             'scales in extrusions and as sqrt(U) rather than as a fraction of the airframe; '
             'a one-extrusion wall has no interior, which is the floor',
             lambda g, d: max(g['greeble_wall_extrusions'] * math.sqrt(g['U']) * g['w'],
                              g['greeble_wall_extrusions'] * g['w'])),
    Relation('greeble.nub_thickness', 'DES-2',
             'the snap rib and the seat wall it stands on are one wall thickness, related by '
             'a formula rather than two independent parameters -- identity today',
             lambda g, d: fv.greeble_nub_thickness_of(d['greeble.thickness'])),
    Relation('bulkhead_flange.thickness', ('DES-2', 'DES-11'),
             'the flange wall is printed in whole perimeters; a cowling bulkhead gets one '
             'more than the rest because it carries the cowl',
             lambda g, d: _extrusions(g['cowl_bulkhead_flange_extrusions'] if g['is_cowling']
                                      else g['bulkhead_flange_extrusions'], g['U'], g['w'])),
    Relation('bolt.thickness', 'DES-11',
             'the boss around the bolt scales with the airframe but never below its 1U value',
             lambda g, d: _floored(g['bolt_thickness_per_u'], g['U'])),
    Relation('plate.thickness', 'DES-2',
             'the plate is a printed skin and wants to come out an exact number of passes, '
             'so it is a count of layer heights and not a length',
             lambda g, d: math.ceil(g['plate_layers'] * g['U']) * g['h']),
    Relation('web.width', 'DES-1',
             'a boom bulkhead\'s web is twice a frame bulkhead\'s: it carries the boom',
             lambda g, d: (g['boom_web_width_per_u'] if g['is_boom']
                           else g['frame_web_width_per_u']) * g['U']),
    Relation('web.fillet_radius', 'DES-1',
             'the fillet where the web meets the ring scales with the airframe',
             lambda g, d: g['web_fillet_radius_per_u'] * g['U']),
    Relation('bulkhead_flange.fillet_radius', 'DES-1',
             'the fillet at the flange root scales with the airframe',
             lambda g, d: g['bulkhead_flange_fillet_per_u'] * g['U']),
    Relation('bulkhead_flange.chamfer', 'DES-1',
             'the chamfer on the flange\'s leading edge scales with the airframe',
             lambda g, d: g['bulkhead_flange_chamfer_per_u'] * g['U']),

    # -- the panel ------------------------------------------------------------------------
    Relation('panel.tolerance', 'DES-7',
             'the gap the panel stands off the flange face by. A cowling bulkhead and a 0 mm '
             'panel take 0, and that zero is the absence of the joint rather than a fit set '
             'to nothing',
             lambda g, d: (0.0 if (g['is_cowling'] or g['panel_thickness'] == 0)
                           else g['panel_tolerance'])),
    Relation('panel.overlap', 'DES-11',
             'the length of panel captured in the corner\'s groove: at least one panel '
             'thickness, and never less than panel_overlap_min_mm of bond area, which is an '
             'absolute minimum and so does not scale',
             lambda g, d: (0.0 if (g['is_cowling'] or g['panel_thickness'] == 0)
                           else max(g['panel_thickness'], g['panel_overlap_min_mm']))),
    Relation('panel.offset', 'DES-8',
             'how far the panel\'s inboard edge stands off the longeron axis: far enough that '
             'it clears the greeble, and that the corner can still snap onto the longeron',
             _panel_offset),

    # -- who carries the clearance --------------------------------------------------------
    Relation('greeble.tolerance', 'DES-4',
             'the snap fit\'s clearance is carried entirely on the corner: its socket is '
             'opened out and the bulkhead\'s post stays nominal, so the joint takes the '
             'clearance once',
             lambda g, d: 0.0 if g['is_bulkhead'] else g['greeble_tolerance']),
    Relation('corner.tolerance', 'DES-6',
             'the two corner faces that seat against the bulkhead carry their clearance on '
             'the corner too -- the bulkhead cuts its socket from the same shape at 0',
             lambda g, d: g['corner_tolerance']),
    Relation('bolt.radius', 'DES-5',
             'the hole is sized to the bought fastener: a bolt to its own nominal, an anchor '
             'to the insert bore from the supplier table',
             _bolt_radius),

    # -- the cowl mount -------------------------------------------------------------------
    Relation('cowl_flange.height', 'DES-7',
             'the flange stands cowl_flange_height_per_u off the bulkhead face per U; a '
             'bulkhead that mounts no cowl has no flange, and that zero is structural',
             lambda g, d: g['cowl_flange_height_per_u'] * g['U'] if g['is_cowling'] else 0.0),
    Relation('cowl_flange.tolerance', 'DES-7',
             'the fit between the flange and the cowl that slides over it, on a cowling '
             'bulkhead only',
             lambda g, d: g['cowl_flange_tolerance'] if g['is_cowling'] else 0.0),

    # -- the boom -------------------------------------------------------------------------
    Relation('boom_bulkhead.diameter', 'DES-1',
             'the boom tube is bought; the sweep states its size as a fraction of unit_width '
             'so a whole airframe scales together',
             lambda g, d: d['bulkhead.width'] * g['boom_diameter'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.y_position', 'DES-1',
             'the boom\'s position across the fuselage, as a fraction of unit_width',
             lambda g, d: d['bulkhead.width'] * g['y_position'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.z_position', 'DES-1',
             'the boom\'s position up the fuselage, as a fraction of unit_width',
             lambda g, d: d['bulkhead.width'] * g['z_position'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.thickness', 'DES-1',
             'the boom bulkhead\'s own wall scales with the airframe',
             lambda g, d: g['boom_wall_per_u'] * g['U'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.collet_thickness', 'DES-1',
             'the collet wall that grips the boom scales with the airframe',
             lambda g, d: g['boom_collet_thickness_per_u'] * g['U'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.key_width', 'DES-11',
             'the anti-rotation key never shrinks below its 1U size',
             lambda g, d: (_floored(g['boom_key_width_per_u'], g['U'])
                           if g['is_boom'] else 0)),
    Relation('boom_bulkhead.key_height', 'DES-11',
             'the key\'s height is an independent dimension that happens to equal its width',
             lambda g, d: (_floored(g['boom_key_height_per_u'], g['U'])
                           if g['is_boom'] else 0)),
    Relation('boom_bulkhead.key_radius', 'DES-11',
             'the radius on the key never shrinks below its 1U size either',
             lambda g, d: (_floored(g['boom_key_radius_per_u'], g['U'])
                           if g['is_boom'] else 0)),
    Relation('boom_bulkhead.key_web_width', 'DES-1',
             'the web that carries the key scales with the airframe',
             lambda g, d: g['boom_key_web_width_per_u'] * g['U'] if g['is_boom'] else 0),
    Relation('boom_bulkhead.tolerance', 'DES-7',
             'the boom tube\'s clearance in the collet, on a boom bulkhead only',
             lambda g, d: g['boom_tolerance'] if g['is_boom'] else 0),
)


# The cowl sweeps are not covered field by field -- their parameters come from JSON files that
# are largely shape control points rather than interfaces. One relation is derived here because
# it is a joint: the nose closure's seat on the cowl shell, register row 8.
COWL_RELATIONS = (
    Relation('nose.flange_inset', 'DES-3',
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
    """The requirement tree: architecture, design, and the relations under each."""
    print('ARCHITECTURAL REQUIREMENTS -- doc/architecture/requirements.md is the authority')
    for name in sorted(ARCHITECTURE):
        print('  %-10s %s' % (name, ARCHITECTURE[name]))
    print('')
    print('DESIGN REQUIREMENTS -- citing architecture is optional; a requirement that cites')
    print('nothing carries its own rationale instead')
    under = {}
    for relation in RELATIONS + COWL_RELATIONS:
        for name in relation.serves:
            under.setdefault(name, []).append(relation)
    for name in sorted(DESIGN, key=lambda k: int(k.split('-')[1])):
        req = DESIGN[name]
        print('  %-7s %s' % (name, req.statement))
        if req.cites:
            print('  %-7s cites %s' % ('', ', '.join(req.cites)))
        else:
            print('  %-7s cites nothing -- design-level, and derived in the INCOSE sense'
                  % '')
        if req.rationale:
            print('  %-7s %s' % ('', req.rationale))
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

    if '--requirements' in argv:
        # Delegated rather than removed: the flag was here first, and a flag that quietly
        # stops doing anything is worse than one that says where the work went.
        print('requirements -- delegated to requirements.py, which owns the register')
        return rq.main([])

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
        derived = sorted((n for n in DESIGN if DESIGN[n].derived),
                         key=lambda k: int(k.split('-')[1]))
        print('traceability -- every relation names one of the %d design requirements; %d of '
              'them cite architecture, %d carry their own rationale (%s)'
              % (len(DESIGN), len(DESIGN) - len(derived), len(derived), ', '.join(derived)))
        print('             the register itself is checked by requirements.py')
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
