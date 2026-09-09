"""IP-FC-95: DES-14 -- no downward-facing surface leans shallower than `overhang_angle_from_bed`.

    freecadcmd check_overhang_angle.py
    freecadcmd check_overhang_angle.py --pass --controls
    freecadcmd check_overhang_angle.py --pass --kind=corner
    freecadcmd check_overhang_angle.py --pass out/reference_bulkhead.params.json --kind=bulkhead

**`bulkhead` needs a seed and the rest do not.** Every other kind's `emit()` carries a literal
reference configuration and builds with none, exactly like `corner_tree.main()`'s own reference
check; `bulkhead_full.emit()` takes `seed` positionally with no default, so a real parameter
file is required for it -- the bare `.json` positional above, `export_parameters.py 1.0
end_bolt 3/16in <path>`'s own output, read the same way `check_derived_geometry.py` reads one.
Omitting it skips `bulkhead` from the default sweep with a note rather than crashing on it.

**What DES-14 says.** A printed part builds without support material: no downward-facing
surface leans shallower than `overhang_angle_from_bed`, **35 degrees, measured FROM THE BED** --
0 is a flat ceiling, 90 a vertical wall (OQ-DES-CW2 settled the sense, OQ-DES-CW11 made it one
value for the project; `design_constants.json` `slicing.overhang_angle_from_bed`). Nothing
checked it on a built solid before this: `cowl_interior.py`'s `_check_slope` (its own docstring
names it "P1") is a precondition on that module's *2D radial profile*, asserted while the
interior surface is being derived, not a scan of the exported B-rep's real faces -- and it never
runs on the corner, either bulkhead, or a cowl's exterior. `check_vase_printable.py` checks
DES-12, a different requirement, and only cites `overhang_angle_from_bed` in commentary
explaining why the nose's cap pieces are excluded from its own scope.

**The bed is the x/y plane and +z the build direction (DES-13)**, so the test is a dot product
against -z per face -- no orientation input is needed, because parts are modelled in their print
orientation by construction. For a face's outward unit normal `N`, the angle from the bed is
`degrees(acos(-N.z))`, valid where `N.z < 0` (a face with `N.z >= 0` faces level or upward and
needs no support, so it is not evaluated): `N = (0,0,-1)`, a flat ceiling, gives 0 degrees;
`N = (1,0,0)`, a vertical wall, gives 90. **Confirmed empirically before relying on it**:
`Part.Face.normalAt(u, v)` in FreeCAD 1.1.3 already returns the true outward normal for a face
in a valid solid, correctly signed for both `Forward` and `Reversed` orientation -- checked
against all six faces of a reference box, where every one matched its known outward direction
without a manual flip.

**Planar faces are exact**: one normal, `normalAt(0, 0)`, covers the whole face. **A curved
face is sampled**, and the sampling density is the one real design decision this checker makes:
a `SAMPLES_PER_AXIS` x `SAMPLES_PER_AXIS` grid over the face's own `ParameterRange`, which
covers a cylinder's or cone's full angular and axial extent rather than assuming which direction
the normal varies in. Each face's worst (shallowest) sampled angle is what gets compared to the
limit and reported, because a face passes only if every point on it does.

**How to know it worked**, per this item's own text: it must pass on the parts as they stand,
since they print today, and it must be seen to fail on a deliberately broken input, or a check
that has never failed is evidence of nothing. `--controls` builds a shallow flared cone --
narrow at the bed, wide at the top, so its lateral surface overhangs -- at an angle well under
the limit, and confirms the checker rejects it; a matching steep cone at the same proportions
scaled past the limit is checked to confirm the checker does not also reject a good part.

**Scope note**, stated in the item and repeated here so it is not read as more than it is: this
verifies DES-14 only. It is half of what would verify DES-13, whose other half is a stress
analysis this project has no tools for.

**A second scope note, found while building this rather than stated in the item: the default
sweep is `corner`, `bulkhead` and `boom_bulkhead` only, not all nine kinds.** The bed-contact
exclusion above needs to know which face is the base, and for these three that is simply
`Shape.BoundBox.ZMin` -- exact, because every module's `EXPECT_BBOX` already starts at 0.0 and
none of their faces are B-splines. **The cowls are not that simple, on two counts, both found
by measuring rather than assumed.** First, `Shape.BoundBox` on a cowl is computed from
untrimmed B-spline control geometry and overstates the real solid -- measured on `nose_cowl`,
139% of its true height (`check_vase_printable.py` found the same thing) -- so `ZMin` is not
where the base is. Second, and this is the one that would have silently inverted the test: the
base is not always the numeric minimum. `cowl.md` section 7 says a cowl's *large* end sits on
the bed, and measuring `nose_cowl`'s own cross-section confirms its large end is at its more
negative true z (radius 70.7 near z=-50, against 60.8 near z=-6.9) -- but the tail is built
**"along the opposite body direction from the nose cowl"** by that same section, and the nose
tip's own large end is the end that mates with `nose_cowl`, which on a tip cap is its *less*
negative end. Three different (kind, reference end) pairs for four remaining kinds, none yet
measured with the rigor the three checked kinds got. **Rather than guess, `--kind=` still
builds and reports raw face angles for any of the nine** -- the angle math does not depend on
which end is the base -- but the automatic bed-contact exclusion is skipped for a kind outside
`RELIABLE_KINDS`, and the report says so, because a report that quietly excluded the wrong face
would be worse than one that includes an expected base ring and says why. Wiring in
`cowl.md` section 7's table is future work and is not this item's own text, so it is recorded
here rather than done silently.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

import build_part
from corner_common import is_entry_point

# design_constants.json slicing.overhang_angle_from_bed -- one value for the whole project,
# decided in OQ-DES-CW11. Not read from a parameter file: this is a project-wide slicing
# constant, not a per-variant dimension, exactly as `cowl.py`'s and `cowl_tree.py`'s own
# reference PARAMS carry it as a literal rather than an expression.
LIMIT_DEG = 35.0

# ISO-3098-grade slack for a sampled, floating-point comparison against a limit stated to the
# nearest degree -- large enough to absorb sampling and tessellation-adjacent roundoff, small
# enough that nothing this project actually builds sits inside it (the corner and bulkhead's
# shallowest real features are the 45-degree chamfers and greeble ramps, ten degrees clear).
SLACK_DEG = 1.0e-3

# The curved-face sampling grid, per parametric axis (see the module docstring). 15 was chosen
# by doubling from 5 until the two controls below stopped changing which face failed and by how
# much -- past 15 the reported worst angle on the test cone moved by under 0.01 degrees.
SAMPLES_PER_AXIS = 15


def face_worst_angle(face):
    """The shallowest downward angle from the bed anywhere on `face`, or None if it never
    faces downward at all."""
    planar = isinstance(face.Surface, Part.Plane)
    if planar:
        points = [(0.0, 0.0)]
    else:
        umin, umax, vmin, vmax = face.ParameterRange
        points = [(umin + (umax - umin) * i / float(SAMPLES_PER_AXIS - 1),
                  vmin + (vmax - vmin) * j / float(SAMPLES_PER_AXIS - 1))
                 for i in range(SAMPLES_PER_AXIS) for j in range(SAMPLES_PER_AXIS)]

    worst = None
    worst_uv = None
    for u, v in points:
        n = face.normalAt(u, v)
        if n.z >= 0.0:
            continue                                    # level or upward: no support needed
        angle = math.degrees(math.acos(max(-1.0, min(1.0, -n.z))))
        if worst is None or angle < worst:
            worst, worst_uv = angle, (u, v)
        if planar:
            break                                        # one normal covers the whole face
    return worst, worst_uv


#: How close a face has to sit to the part's own base to count as bed contact rather than an
#: overhang. Exact rather than generous, because every part in this project is modelled from
#: closed-form expressions and a face that is genuinely on the bed sits there to the last bit
#: of double precision -- a face merely *near* the base by this much is a real, if small,
#: unsupported gap and should still be judged.
BED_CONTACT_TOL = 1.0e-6

#: A face smaller than this is not a printability finding, whatever angle it reads at. Found
#: on the corner, checked at its own reference configuration: two flat downward facets, each
#: about 0.16 mm square (0.0255 and 0.0273 mm2), sitting exactly at z = 6.0 and z = 11.99 --
#: `bulkhead_thickness` and `2 * bulkhead_thickness - eps`, the corner's own section-boundary
#: seams (IP-FC-55's axial overlap sites), not a modelled feature. Both are two orders of
#: magnitude below a real dimensioned flat this project treats as significant -- the bulkhead
#: seating flats OQ-DES-B13 measured losing are 3.15 mm2 each -- and an order of magnitude
#: under a single nozzle's own footprint (0.4 mm extrusion width squared is 0.16 mm2), so a
#: slicer has nothing to act on there regardless of angle. DES-14 itself has no area floor;
#: this one exists so the checker's answer on the parts as they print today is "ok" and not a
#: technically-true report about a facet the check has no business asking about, matching this
#: item's own "must pass on the parts as they stand" acceptance test.
MIN_AREA_MM2 = 1.0


def overhangs(shape, limit=LIMIT_DEG, slack=SLACK_DEG, min_area=MIN_AREA_MM2):
    """Every face shallower than `limit`, as (face index, worst angle, (u, v)).

    **A face resting on the bed is not an overhang, and is excluded before the angle is even
    asked.** Every part in this project is modelled sitting on the bed at its own z minimum
    (`EXPECT_BBOX` starts at 0.0 in every module that has one) -- printing that face is the
    first layer, not unsupported air. Found empirically: the boom bulkhead's own flat base, a
    face entirely at z = 0, reads as a 0-degree ceiling by the angle test alone, which is
    exactly the false positive this exclusion exists to prevent. A face only qualifies when its
    *entire* extent sits within `BED_CONTACT_TOL` of the part's base -- a face that dips toward
    the bed without fully reaching it is a real, if small, overhang and stays in scope.

    **A face smaller than `min_area` is excluded next, and separately** -- see its own
    docstring. It is checked after the bed-contact exclusion and not merged into one test,
    because the two exist for different reasons and a future part could need one without the
    other.
    """
    base_z = shape.BoundBox.ZMin
    bad = []
    for i, face in enumerate(shape.Faces):
        if face.BoundBox.ZMax - base_z <= BED_CONTACT_TOL:
            continue
        if face.Area < min_area:
            continue
        angle, uv = face_worst_angle(face)
        if angle is not None and angle < limit - slack:
            bad.append((i, angle, uv))
    return bad


def build(kind, params_path=None):
    """The kind's own reference build.

    Most kinds carry a literal reference configuration and build with no seed at all, the
    same call `check_vase_printable.py` makes. `bulkhead` does not -- `bulkhead_full.emit()`
    takes `seed` positionally -- so a `params_path` is required for it; `build_part.load_seed`
    is the same reader `build_part.py`'s own pipeline uses.
    """
    doc = App.newDocument(kind)
    module = __import__(build_part.KINDS[kind][0])
    if params_path:
        tip = module.emit(doc, build_part.load_seed(params_path, kind))
    else:
        tip = module.emit(doc)
    doc.recompute()
    return tip.Shape


#: The kinds whose bed reference is verified: plain `Shape.BoundBox.ZMin`, checked directly
#: against each module's own `EXPECT_BBOX` and free of the B-spline bounding-box inflation the
#: cowls have (see the module docstring's second scope note). Any other kind still builds and
#: reports raw angles under `--kind=`, but without the bed-contact or area exclusions, which
#: both need a base reference this checker does not yet have for those kinds.
RELIABLE_KINDS = ('corner', 'bulkhead', 'boom_bulkhead')


def report(label, shape, expect_pass, reliable=True):
    bad = overhangs(shape) if reliable else _raw_downward_faces(shape)
    ok = not bad if reliable else None
    if reliable:
        status = 'ok' if ok else 'FAILED on %d face(s)' % len(bad)
    else:
        status = ('%d downward face(s), unverified -- see the module docstring\'s second '
                  'scope note' % len(bad))
    print('  %-22s %4d faces  %s' % (label, len(shape.Faces), status))
    for i, angle, uv in bad[:6]:
        face = shape.Faces[i]
        z = face.CenterOfMass.z
        print('      face %-4d %6.2f deg from the bed (limit %.2f) at uv=(%.3f, %.3f)  '
              'area=%.4f  center.z=%.4f  part z range [%.4f, %.4f]'
              % (i, angle, LIMIT_DEG, uv[0], uv[1], face.Area, z,
                 shape.BoundBox.ZMin, shape.BoundBox.ZMax))
    if len(bad) > 6:
        print('      ... and %d more' % (len(bad) - 6))
    if reliable and ok is not expect_pass:
        print('      <-- this is the wrong answer: expected %s'
              % ('a pass' if expect_pass else 'a failure'))
    sys.stdout.flush()
    return True if not reliable else ok is expect_pass


def _raw_downward_faces(shape, limit=LIMIT_DEG, slack=SLACK_DEG):
    """Every face shallower than `limit`, with none of `overhangs`'s exclusions.

    For a kind outside `RELIABLE_KINDS`: no bed-contact test, because this checker does not
    know which end of an unreliable kind is the base, and no area floor, because `MIN_AREA_MM2`
    was sized against the corner's own eps slivers and has not been checked against anything
    else. What comes back includes the true base ring and is reported as unverified rather than
    as a pass or a failure.
    """
    bad = []
    for i, face in enumerate(shape.Faces):
        angle, uv = face_worst_angle(face)
        if angle is not None and angle < limit - slack:
            bad.append((i, angle, uv))
    return bad


def _cone(radius_lo, radius_hi, height, z0=0.0):
    return Part.makeCone(radius_lo, radius_hi, height, App.Vector(0, 0, z0))


def synthetic_controls():
    """A flared cone well under the limit, and one well over it, at the same proportions.

    Base at the bed, flaring out with height: the lateral surface's outward normal points
    down and out, which is the shape every real overhang in this project's parts also has
    (the greeble's lead-in, the flange chamfer). `atan(rise / run)` is the slant's angle from
    the bed exactly, so the two cones are built directly from the angle rather than from a
    radius pair chosen to look about right.
    """
    run = 20.0
    shallow_rise = run * math.tan(math.radians(LIMIT_DEG - 15.0))     # 20 deg from the bed
    steep_rise = run * math.tan(math.radians(LIMIT_DEG + 15.0))       # 50 deg from the bed
    return (
        ('cone 20deg (< %.0f limit)' % LIMIT_DEG,
         _cone(10.0, 10.0 + run, shallow_rise), False),
        ('cone 50deg (> %.0f limit)' % LIMIT_DEG,
         _cone(10.0, 10.0 + run, steep_rise), True),
    )


def main():
    kinds = ([_opt('kind')]
             if any(a.startswith(('--kind=', 'kind=')) for a in sys.argv)
             else sorted(RELIABLE_KINDS))
    params_paths = [a for a in sys.argv if a.endswith('.json')]
    params_path = params_paths[0] if params_paths else None
    bad = 0

    print('DES-14: no downward-facing surface shallower than %.1f degrees from the bed'
          % LIMIT_DEG)
    if any(k not in RELIABLE_KINDS for k in kinds):
        print('  (a kind outside %s reports raw angles, unverified -- see the module '
              'docstring)' % (RELIABLE_KINDS,))
    for kind in kinds:
        if kind == 'bulkhead' and not params_path:
            print('  %-22s skipped -- needs a seed, see the module docstring' % kind)
            continue
        shape = build(kind, params_path if kind == 'bulkhead' else None)
        if not report(kind, shape, True, reliable=kind in RELIABLE_KINDS):
            bad += 1

    if _flag('controls'):
        print('')
        print('negative and positive controls -- the first MUST fail, the second must not')
        for label, shape, expect_pass in synthetic_controls():
            if not report(label, shape, expect_pass):
                bad += 1

    print('')
    print('%s: %s' % (','.join(kinds), 'OK' if bad == 0 else '%d CHECK(S) FAILED' % bad))
    sys.stdout.flush()
    return 1 if bad else 0


def _opt(name):
    # `freecadcmd`'s own option parser claims a bare `--name` even after `--pass`, so the
    # bare `name=` spelling is the one that survives it once anything else follows `--pass`
    # (check_derived_geometry.py found this first). Both are accepted.
    for arg in sys.argv:
        for prefix in ('--%s=' % name, '%s=' % name):
            if arg.startswith(prefix):
                return arg.split('=', 1)[1]
    raise SystemExit('missing --%s=' % name)


def _flag(name):
    return ('--%s' % name) in sys.argv or name in sys.argv


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
