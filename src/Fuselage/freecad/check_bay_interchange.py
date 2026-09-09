"""IP-FC-100: DES-15 -- a bay end's mating features are identical across every bay of the same
size, and the interior aperture is deliberately excluded.

    freecadcmd check_bay_interchange.py --pass out/ref_end_anchor.params.json \\
        out/ref_end_bolt.params.json out/ref_cowling_anchor.params.json \\
        out/ref_cowling_bolt.params.json out/ref_interconnect.params.json
    freecadcmd check_bay_interchange.py --pass ... controls

**What DES-15 says**, corrected from an earlier draft under OQ-DES-SR3 on 2026-08-30: sameness
holds for the mating features only -- the OML perimeter, the longeron positions and sizes, and
the fastener positions and sizes -- across every bulkhead type of one size, **not** for the
bulkhead's interior aperture, which the requirement says outright must be free to vary (a boom
bulkhead's is neither a standard dimension nor a standard shape). Nothing checked any of this
before this: `check_derived_geometry.py` predicts and checks planar faces only, and has no
notion of comparing two builds against each other rather than against a derivation.

**Extracting "the fastener" is the one real design decision here, and it was settled by
measuring five real builds rather than by reading the register alone.** Every frame bulkhead
type carries, on the same diagonal axis as the longeron, a stack of concentric cylindrical
faces at the bolt/insert position -- a bore, then one or two wider relief or boss steps around
it, since a flange needs clearance for a fastener head or a printed boss around an insert. Only
the *innermost* one is the fastener itself: `end_bolt` and `cowling_bolt` both read exactly
2.0000 mm there (`bolt_hole_radius`), `end_anchor` and `cowling_anchor` both read exactly
2.7500 mm, and in both pairs the outer steps differ between the two types (cowling's flange
needs a different boss than end's web) while the innermost bore does not. So "the fastener's
size" is the smallest-radius cylinder centred on that axis, and the boss around it is
implementation the requirement was never about.

**The longeron is unambiguous by contrast** -- one radius, `longeron_radius +
longeron_tolerance`, at each of the four `(corner_offset, corner_offset)` positions, on every
type including `interconnect`, which is why it needs no innermost-of-a-stack rule.

**Interconnect has no fastener at all**, decided and verified under IP-FC-133 -- `bolt_offset`
is not a feature that type has -- so it is checked for the longeron and the OML perimeter and
excluded from the fastener comparison, the same exclusion `dimension_scheme.md`'s register now
carries for the same reason.

**The OML perimeter** is the bulkhead's own outer X/Y extent -- the mold line or, where a panel
sets it back, the panel pocket's inner face, per `bulkhead_faces` in `check_derived_geometry.py`
-- and it is compared as the built solid's own bounding box in X and Y, which is exact for this
part: every face at the true outer boundary is planar and axis-normal, so nothing is lost to
the B-spline inflation `check_overhang_angle.py` had to work around for the cowls.

**How to know it worked.** `controls` perturbs one built document directly rather than
re-deriving a broken variant: `bolt_offset` is a `=` row (`8 * U`, section 2), not
configuration, so the seed cannot move it -- the negative control instead sets the sheet cell
after the document is built and recomputes, which is a legitimate way to ask "does the checker
notice" without inventing a new variant the sweep would never produce. It must fail. A second
control edits the sheet's `mask_reach` -- an interior-only quantity no mating feature reads --
and confirms the checker does **not** fail, which is the exclusion DES-15 itself demands, tested
rather than assumed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

import build_part
from corner_common import is_entry_point

#: How closely a position or radius has to land to count as the same feature. A kernel-
#: agreement tolerance, matching `check_derived_geometry.py`'s `POSITION_TOL` -- these are
#: modelling disagreements to catch, not manufacturing tolerances to allow.
POSITION_TOL = 1e-6
RADIUS_TOL = 1e-6

#: The four frame bulkhead types with a fastener, and which kind of fastener each carries.
#: `interconnect` is deliberately absent -- see the module docstring.
FASTENER_KIND = {'end_anchor': 'anchor', 'end_bolt': 'bolt',
                 'cowling_anchor': 'anchor', 'cowling_bolt': 'bolt'}

ALL_TYPES = tuple(FASTENER_KIND) + ('interconnect',)


def build(type_name, params_path):
    doc = App.newDocument('bay_%s' % type_name)
    tip = build_part.build(doc, 'bulkhead', params_path)
    return doc, tip


def vertical_cylinders(shape):
    """Every cylindrical face whose axis is the bulkhead's own z axis, as (radius, x, y)."""
    out = []
    for face in shape.Faces:
        if not isinstance(face.Surface, Part.Cylinder):
            continue
        axis = face.Surface.Axis
        if abs(abs(axis.z) - 1.0) > 1e-6:
            continue
        center = face.Surface.Center
        out.append((face.Surface.Radius, center.x, center.y))
    return out


def longeron_bores(cyls, longeron_r):
    """The four longeron bore centres, at the one radius the design derives for them."""
    return sorted((round(x, 6), round(y, 6)) for r, x, y in cyls
                  if abs(r - longeron_r) <= RADIUS_TOL)


def fastener_axes(doc):
    """The four positions section 2's register puts a fastener at: `bolt_offset` in from each
    longeron axis, on the diagonal -- `(corner_offset - bolt_offset, corner_offset -
    bolt_offset)` and its three sign-mirrors, `corner_offset` being the octant translation
    `bulkhead_full.PARAMS` already names (`unit_width / 2 - corner_radius`).

    **Computed from the sheet rather than found by elimination.** A first version treated any
    cylinder that was not the longeron's own radius as a fastener candidate, and it caught the
    greeble post and its nub too -- both real cylindrical features near the same corner, on
    `end_anchor`, `end_bolt` and `interconnect`, that `cowling_anchor` and `cowling_bolt` do not
    have at all because a cowling bulkhead mates through a flange rather than a greeble. Asking
    at the one position the register actually predicts is what tells the two kinds of feature
    apart without needing to name the greeble to exclude it.
    """
    # `corner_offset` is `bulkhead_full.PARAMS`'s own name for this -- the octant translation,
    # `unit_width / 2 - corner_radius` -- read back rather than re-derived, so a change to that
    # expression cannot silently disagree with this one.
    d = doc.Params.get('corner_offset') - doc.Params.get('bolt_offset')
    return [(d, d), (d, -d), (-d, d), (-d, -d)]


def fastener_positions(cyls, doc):
    """Each of the four fastener axes with any cylinder there, and its innermost bore radius."""
    by_xy = {}
    for x, y in fastener_axes(doc):
        radii = [r for r, cx, cy in cyls
                 if abs(cx - x) <= POSITION_TOL and abs(cy - y) <= POSITION_TOL]
        if radii:
            by_xy[(round(x, 6), round(y, 6))] = min(radii)
    return by_xy


def oml_perimeter(shape):
    bb = shape.BoundBox
    return (round(bb.XMin, 6), round(bb.YMin, 6), round(bb.XMax, 6), round(bb.YMax, 6))


def features(type_name, params_path):
    doc, tip = build(type_name, params_path)
    shape = tip.Shape
    longeron_r = doc.Params.get('longeron_radius') + doc.Params.get('longeron_tolerance')
    cyls = vertical_cylinders(shape)
    return {
        'doc': doc,
        'tip': tip,
        'oml': oml_perimeter(shape),
        'longeron': longeron_bores(cyls, longeron_r),
        'fastener': fastener_positions(cyls, doc),
        'longeron_r': longeron_r,
    }


def refresh(entry):
    """Re-derive an entry's feature sets after its document has been mutated and recomputed."""
    shape = entry['tip'].Shape
    longeron_r = entry['doc'].Params.get('longeron_radius') + entry['doc'].Params.get(
        'longeron_tolerance')
    cyls = vertical_cylinders(shape)
    entry['oml'] = oml_perimeter(shape)
    entry['longeron'] = longeron_bores(cyls, longeron_r)
    entry['fastener'] = fastener_positions(cyls, entry['doc'])
    entry['longeron_r'] = longeron_r
    return entry


def compare(by_type):
    """Every disagreement DES-15 forbids, as report lines. Empty means it holds."""
    problems = []

    oml = {t: f['oml'] for t, f in by_type.items()}
    reference = next(iter(oml.values()))
    for t, value in oml.items():
        if value != reference:
            problems.append('OML perimeter: %s is %s, not %s' % (t, value, reference))

    longeron = {t: f['longeron'] for t, f in by_type.items()}
    ref_longeron = next(iter(longeron.values()))
    for t, value in longeron.items():
        if value != ref_longeron:
            problems.append('longeron positions: %s is %s, not %s' % (t, value, ref_longeron))
    radii = {t: f['longeron_r'] for t, f in by_type.items()}
    ref_radius = next(iter(radii.values()))
    for t, value in radii.items():
        if abs(value - ref_radius) > RADIUS_TOL:
            problems.append('longeron radius: %s is %.6f, not %.6f' % (t, value, ref_radius))

    fastener_types = [t for t in by_type if t in FASTENER_KIND]
    if fastener_types:
        positions = {t: sorted(by_type[t]['fastener']) for t in fastener_types}
        ref_positions = next(iter(positions.values()))
        for t, value in positions.items():
            if value != ref_positions:
                problems.append('fastener positions: %s is %s, not %s'
                                % (t, value, ref_positions))
        for kind in ('anchor', 'bolt'):
            same_kind = [t for t in fastener_types if FASTENER_KIND[t] == kind]
            if len(same_kind) < 2:
                continue
            sizes = {t: sorted(by_type[t]['fastener'].values()) for t in same_kind}
            ref_size = next(iter(sizes.values()))
            for t, value in sizes.items():
                if value != ref_size:
                    problems.append('fastener size (%s): %s is %s, not %s'
                                    % (kind, t, value, ref_size))
    return problems


def report(label, by_type):
    problems = compare(by_type)
    print('%s: %s' % (label, 'ok' if not problems else '%d problem(s)' % len(problems)))
    for p in problems:
        print('  FAIL  %s' % p)
    sys.stdout.flush()
    return not problems


def _declared_type(path):
    """The type a parameter file was exported for, read from its own contents.

    Matched by filename first, since `export_parameters.py ref_<type>.params.json` is the
    normal way to make one and it is cheap to read off the path -- but the file's own
    `bulkhead_type_name` is the authority, so a differently-named copy still resolves.
    """
    base = os.path.basename(path)
    for t in ALL_TYPES:
        if t in base:
            return t
    try:
        import json
        with open(path, encoding='utf-8') as f:
            doc = json.load(f)
        return doc.get('parameters', {}).get('bulkhead_type_name')
    except Exception:                                                # noqa: BLE001
        return None


def main(argv):
    paths = {}
    for arg in argv:
        if not arg.endswith('.json'):
            continue
        t = _declared_type(arg)
        if t in ALL_TYPES:
            paths[t] = arg

    missing = [t for t in ALL_TYPES if t not in paths]
    if missing:
        print('usage: freecadcmd check_bay_interchange.py --pass '
              'out/ref_<type>.params.json (x5) [controls]')
        print('missing a parameter file for: %s' % ', '.join(missing))
        return 2

    print('DES-15: mating features identical across bay ends, aperture excluded')
    by_type = {t: features(t, paths[t]) for t in ALL_TYPES}
    ok = report('reference builds', by_type)
    bad = 0 if ok else 1

    if 'controls' in argv:
        print('')
        print('negative and positive controls -- the first MUST fail, the second must not')

        mutant = features('end_bolt', paths['end_bolt'])
        mutant['doc'].Params.set('bolt_offset', '9.5')
        mutant['doc'].recompute()
        refresh(mutant)
        shifted = dict(by_type, end_bolt=mutant)
        if report('shifted bolt_offset on end_bolt (must fail)', shifted):
            print('      <-- the check passed a shifted fastener')
            bad += 1

        aperture = features('end_bolt', paths['end_bolt'])
        aperture['doc'].Params.set('mask_reach', '999.0')
        aperture['doc'].recompute()
        refresh(aperture)
        untouched = dict(by_type, end_bolt=aperture)
        if not report('altered aperture-only quantity on end_bolt (must not fail)', untouched):
            print('      <-- the check failed on an interior-only change')
            bad += 1

    print('')
    print('%s' % ('OK' if bad == 0 else '%d CHECK(S) FAILED' % bad))
    sys.stdout.flush()
    return 1 if bad else 0


if is_entry_point(__name__):
    _code = main(sys.argv)
    sys.stdout.flush()
    sys.exit(_code)
