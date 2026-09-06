"""IP-FC-98: DES-12, the requirement with a live silent failure mode.

    freecadcmd check_vase_printable.py --pass --kind=tail
    freecadcmd check_vase_printable.py --pass --kind=tail --controls

**What DES-12 says.** A cowl stays printable in spiral vase mode: the solid exported for
printing carries one closed contour per layer and no interior geometry whatsoever. Vase mode
spirals a single continuous contour up the part, so the wall comes from the slicer and not
from the model ([cowl.md](../../../doc/design/cowl.md) OQ-DES-CW6).

**Why it needs a check at all, when every other requirement here is about a number.** The
failure is silent in the strongest sense: a cowl given a modelled wall still builds, still
exports, still has one solid, still passes every acceptance test in
`check_cowl_interior.py`, and produces an STL that looks *better*. Nothing in the geometry
says the print capability is gone. The port has both representations in it already --
`tail_shell` is exactly the walled cowl this forbids -- so the mistake to guard against is not
hypothetical carelessness, it is one `emit()` pointed at the wrong module.

**Scope is a rule, not a list, and the direction it fails in is the point.** "A cowl" means
the vase-printed piece of an assembly, not the pieces that cap it. The nose tip and nose plate
are **cap pieces**: a single-contour shell cannot close the nose without carrying the wall
round the tip, where it would lean shallower than `overhang_angle_from_bed`, so those two parts
exist precisely so the cowl never has to violate the overhang limit to close the shape
([cowl.md](../../../doc/design/cowl.md)). The geometry agrees, measured 2026-09-06: the plate
sections into two closed loops at 143 of 200 stations and the tip into two at **all** 200,
being a 7 mm ring.

So the scope is computed rather than written down: **every cowl kind, less the shelled
representations, less an explicit register of cap pieces each carrying its reason.** The tail
is one cowl today because its aft end is the OML's own closure, and a future tail design may
add an end piece on the same footing as the nose's. Under this rule that new kind is **in
scope by default and fails until somebody records why it is a cap**. Naming the two parts to
check instead would let a newly added vase-printed cowl go unchecked in silence -- which is
the shape of the failure DES-12 exists to prevent, arriving through the check meant to catch
it.

**The two criteria, and why the cheap one is not enough on its own.**

- *Every sampled section is exactly one closed contour.* This is DES-12 restated. It catches a
  modelled wall, a hollowed interior, a through hole -- anything that puts a second loop in a
  layer -- and it catches it at every z the offending feature spans.
- *The solid has exactly one shell.* A shell is a closed connected boundary, so a second one
  is an **enclosed void**: interior geometry that touches no exterior face. That is the case
  sectioning can miss, because a void thinner than the station pitch can fall between two
  stations. This criterion is topological, costs nothing, and has no sampling in it. The
  controls below include a void deliberately sized to slip through the sections, so the claim
  that this criterion earns its place is demonstrated rather than asserted.

Between them the coverage argument is stateable: interior geometry that reaches the outside
spans a z range and is caught by sections wherever it spans; interior geometry that does not
reach the outside is a void and is caught by the shell count. What is left uncovered is a
*through* feature -- open to the outside at both ends -- whose z extent is shorter than the
station pitch, which is why the pitch is a stated fraction of the part rather than a constant,
and why the stations are drawn from the part's own features rather than spread evenly.

**Where the stations come from.** Uniform sampling for its own sake would spend the budget in
the middle of long featureless spans. A second contour appears where a feature does, so every
distinct z at which the solid has a *vertex* becomes a station -- that is every buttress ramp
start and end, every cut plane, the flange, and the ends -- and each is sampled just above and
just below rather than on it, because a section taken exactly in the plane of a horizontal
edge is degenerate. That is the same reason P4 exists
([cowl_interior_surface.md](../../../doc/design/cowl_interior_surface.md) §2). A uniform
background at `PITCH_FRACTION` of the part fills the spans between features.

**The z range comes from `cowl_interior.z_extent`, not from the bounding box.** `Shape.BoundBox`
is computed from B-spline geometry rather than from the trimmed result, so on these parts it
is an outer bound and nothing more: measured 2026-09-06 the nose cowl's box is **139 %** of
the part's height and the nose tip's is **874 %**. Sampling over a box would put stations
outside the solid, where the section is legitimately empty -- which this check would then have
to call either a failure on a good part or a pass on nothing at all.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

import build_part
import cowl_interior as ci
from corner_common import is_entry_point

#: Kinds that must FAIL, as themselves rather than as a mock. These are the real walled cowls
#: the design keeps for the other use cases, so the negative control is the actual mistake
#: DES-12 forbids and not an imitation of it. They are also excluded from the scope below, for
#: the obvious reason: a shelled cowl is the *other* representation and is not exported to
#: print.
CONTROL_KINDS = ('nose_cowl_shell', 'tail_shell')

#: The cap pieces, with why each one is a cap. **Membership here is the only way a cowl kind
#: leaves DES-12's scope**, so adding an entry is a design statement and reads as one. A part
#: is a cap when the cowl cannot close the shape itself without leaning shallower than
#: `overhang_angle_from_bed` -- which is a property of the assembly, not of the part's name.
CAP_PIECES = {
    'nose_nose': 'the tip: the shell would have to turn over the nose to close it',
    'nose_plate': 'the removable plate closing the tip, printed flat and flipped',
}


def kinds_in_scope():
    """Every cowl kind DES-12 governs, by subtraction rather than by enumeration.

    A kind added to `build_part.COWL_KINDS` arrives here **in scope**, and stays in scope until
    someone puts it in `CAP_PIECES` with a reason. That is the safe direction: the cost of
    getting it wrong is a check that fails and has to be answered, rather than a part that is
    silently never checked.
    """
    return tuple(kind for kind in build_part.COWL_KINDS
                 if kind not in CONTROL_KINDS and kind not in CAP_PIECES)

#: Uniform background stations, as a fraction of the part's own height. A fraction rather than
#: a constant so the sampling stays the same *relative* to the part at every `U`, which is what
#: the coverage statement above is in terms of.
PITCH_FRACTION = 1.0 / 200.0

#: How far above and below a feature's z each pair of stations sits, in millimetres. Far enough
#: off the plane of a horizontal edge that the section is not degenerate, and near enough that
#: a feature is bracketed rather than straddled. Absolute, because it answers to the kernel's
#: tolerance rather than to the size of the part -- the same argument `cowl_interior.END_INSET`
#: makes for itself.
BRACKET = 1.0e-2

#: Two feature z closer than this are one feature. Set to twice `BRACKET` because that is when
#: their brackets would overlap and the second pair would be re-sampling the first. Without it
#: the tail's 306 faces contribute over a thousand stations, nearly all of them duplicates of
#: each other -- vertices are plentiful and distinct feature heights are not.
MIN_FEATURE_GAP = 2.0 * BRACKET


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    if default is None:
        raise SystemExit('missing --%s=' % name)
    return default


def _flag(name):
    return ('--%s' % name) in sys.argv


def stations(shape, lo, hi, features=True):
    """Every z the part is sectioned at: its own features, bracketed, plus a background.

    Returned sorted and de-duplicated at `cowl_interior.Z_TOL`, and clipped to `(lo, hi)` --
    a bracket that falls off the end of the part would section empty and mean nothing.

    `features=False` gives the uniform background alone. Nothing in the check runs that way;
    it exists so the controls can measure what the feature stations are worth, rather than
    leaving it as a claim in this docstring.
    """
    pitch = (hi - lo) * PITCH_FRACTION
    found = []
    if features:
        for z in sorted(v.Point.z for v in shape.Vertexes):
            if not found or z - found[-1] > MIN_FEATURE_GAP:
                found.append(z)
    out = []
    for feature in found:
        for z in (feature - BRACKET, feature + BRACKET):
            if lo < z < hi:
                out.append(z)
    n = max(int(round((hi - lo) / pitch)), 2)
    for i in range(1, n):
        out.append(lo + (hi - lo) * i / float(n))
    out.sort()
    kept = []
    for z in out:
        if not kept or z - kept[-1] > ci.Z_TOL:
            kept.append(z)
    return kept


def section_faults(shape, zs):
    """Stations whose section is not exactly one closed contour.

    Returns `(faults, sampled)`. A station that raises is a fault too, and is reported as one
    rather than skipped: a section that cannot be taken is not evidence that the layer is
    clean.
    """
    faults = []
    for z in zs:
        try:
            wires = shape.slice(App.Vector(0, 0, 1), z)
        except Exception as exc:                                        # noqa: BLE001
            faults.append((z, None, None, '%s: %s' % (type(exc).__name__, exc)))
            continue
        closed = [w for w in wires if w.isClosed()]
        if len(closed) != 1 or len(wires) != len(closed):
            faults.append((z, len(closed), len(wires) - len(closed), ''))
    return faults, len(zs)


def report(label, shape, expect_pass):
    """Both criteria on one solid. Returns True when the solid met DES-12."""
    try:
        lo, hi = ci.z_extent(shape)
    except ci.PreconditionFailed as exc:
        print('  %-22s could not be located: %s' % (label, exc))
        return False
    lo, hi = lo + BRACKET, hi - BRACKET

    shells = len(shape.Shells)
    zs = stations(shape, lo, hi)
    faults, sampled = section_faults(shape, zs)

    ok = (shells == 1) and not faults
    caught = []
    if shells != 1:
        caught.append('%d shells' % shells)
    if faults:
        caught.append('%d of %d sections' % (len(faults), sampled))
    print('  %-22s z %9.4f .. %9.4f  %4d stations  %d solid(s) %d shell(s)  %s'
          % (label, lo, hi, sampled, len(shape.Solids), shells,
             'one contour everywhere' if ok else 'FAILED on ' + ' and '.join(caught)))
    for z, closed, opened, err in faults[:6]:
        if err:
            print('      z %9.4f  section raised %s' % (z, err))
        else:
            print('      z %9.4f  %d closed contour(s), %d open' % (z, closed, opened))
    if len(faults) > 6:
        print('      ... and %d more' % (len(faults) - 6))
    if ok is not expect_pass:
        print('      <-- this is the wrong answer: expected %s'
              % ('a pass' if expect_pass else 'a failure'))
    # Flushed per solid rather than at the end: a `--controls` run builds the two real shelled
    # cowls, which is about ten minutes on the tail, and a run that says nothing until it
    # finishes cannot be distinguished from one that has hung.
    sys.stdout.flush()
    return ok


def build(kind):
    """The kind's own reference build, which is what `build_part` exports for printing."""
    doc = App.newDocument(kind)
    module = __import__(build_part.KINDS[kind][0])
    tip = module.emit(doc)
    doc.recompute()
    return tip.Shape


def synthetic_controls(shape):
    """Two ways to break a good solid, aimed at one criterion each.

    *Hollowed* is DES-12's failure in its simplest form -- a bore up the middle turns every
    layer into two contours -- and it must be caught by the sections. It is still a single
    shell, so it exercises that criterion alone.

    *Void* is a disc of material removed from the middle of the solid, touching no exterior
    face, and it is **a fifth of the station pitch thick**. It was built expecting the sections
    to miss it and the shell count to be the only thing that caught it.

    **They did not miss it, and the reason is worth more than the expectation was.** Measured
    2026-09-06 on the nose cowl: caught by *both* criteria, on 3 of 211 sections. Cutting a
    void into a solid **creates vertices at the void's own boundary**, and the stations are
    drawn from vertices -- so a modelled void generates the very stations that find it, at any
    thickness, however far it falls below the background pitch. The run now reports the
    background-only outcome alongside, which is the number that separates the two effects.

    So the shell count is not covering a demonstrated gap in the sections; it is a free
    topological backstop for the cases sampling cannot reach at all -- a void whose vertices
    fall outside the clipped range, or a section that raises rather than returning loops.
    That is a smaller claim than the one this control was built to support, and it is the one
    the measurement actually carries.

    Both are cut from the real part, so the operands are the geometry actually shipped rather
    than a stand-in with a friendlier shape.
    """
    lo, hi = ci.z_extent(shape)
    mid = 0.5 * (lo + hi)
    section = shape.slice(App.Vector(0, 0, 1), mid)
    seed = section[0].BoundBox.Center if section else shape.BoundBox.Center
    radius = 0.1 * (hi - lo)

    bore = Part.makeCylinder(radius, (hi - lo) + 2.0,
                             App.Vector(seed.x, seed.y, lo - 1.0))
    thin = 0.2 * (hi - lo) * PITCH_FRACTION
    disc = Part.makeCylinder(radius, thin,
                             App.Vector(seed.x, seed.y, mid - 0.5 * thin))
    return (('hollowed r=%.2f' % radius, shape.cut(bore)),
            ('void %.4f mm thick' % thin, shape.cut(disc)))


def main():
    kinds = ([_opt('kind')] if any(a.startswith('--kind=') for a in sys.argv)
             else list(kinds_in_scope()))
    bad = 0

    print('DES-12: one closed contour per layer, no interior geometry')
    print('  in scope: %s' % ', '.join(kinds_in_scope()))
    for kind, why in sorted(CAP_PIECES.items()):
        print('  not a cowl: %-12s %s' % (kind, why))
    for kind in kinds:
        shape = build(kind)
        if not report(kind, shape, True):
            bad += 1

    if _flag('controls'):
        print('')
        print('negative controls -- each of these MUST fail, or the check proves nothing')
        for kind in kinds:
            shape = build(kind)
            for label, broken in synthetic_controls(shape):
                if report('%s + %s' % (kind, label), broken, False):
                    print('      <-- the check passed a part it must reject')
                    bad += 1
                # **What the feature stations are worth, measured on the same solid.** The
                # background alone is uniform sampling for its own sake, which is the thing
                # the sampling section of this module's docstring argues against.
                lo, hi = ci.z_extent(broken)
                bare = stations(broken, lo + BRACKET, hi - BRACKET, features=False)
                missed, sampled = section_faults(broken, bare)
                print('      background stations alone: %d of %d sections see it%s'
                      % (len(missed), sampled,
                         '' if missed else '   <-- only the features and the shell count find'
                                           ' this'))
        print('')
        print('the real walled cowls, which are what the port actually risks exporting:')
        for kind in CONTROL_KINDS:
            try:
                shape = build(kind)
            except Exception as exc:                                    # noqa: BLE001
                print('  %-22s did not build: %s: %s' % (kind, type(exc).__name__, exc))
                bad += 1
                continue
            if report(kind, shape, False):
                print('      <-- the check passed a walled cowl')
                bad += 1

    print('')
    print('%s: %s' % (','.join(kinds), 'OK' if bad == 0 else '%d CHECK(S) FAILED' % bad))
    sys.stdout.flush()
    return 1 if bad else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
