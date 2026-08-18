"""IP-FC-73: the fillet centers are solved by a sketch. Does that survive use?

Replacing arithmetic with a solver buys a relationship the model states and checks, and it
costs things that arithmetic never had to prove. This asserts them, for every rounded corner:

  1. **The delivered .FCStd stays editable.** A generated model is not only a mesh source --
     someone opens it and changes a parameter. A sketch that solved once at generation time
     and then went stale, or that only re-solves in the GUI, would be a regression that no
     volume check would notice.
  2. **The solver stays on the right branch.** A circle tangent to two things admits more than
     one solution. A wrong branch is geometry that builds happily in the wrong place, so the
     closed form is kept as a test of the solved position across a sweep of the parameter it
     is most sensitive to.
  3. **An unsatisfiable configuration is refused, by name.** This is the whole point of the
     change: the `max(...; 0)` these replace used to clamp and return a plausible wrong
     center. Since OQ-ARCH-14 all four corners share one sketch, and `solve()` and
     `FullyConstrained` are per sketch -- so a refusal that said only "the sketch failed"
     would be *weaker* than the four separate sketches it replaced. The message must name the
     sub-system, and this checks that it does.
  4. **Full constraint is checked by `solve()` and not by `FullyConstrained` alone.** The
     latter answers "are there enough constraints", never "were they satisfiable" -- past a
     degeneracy the solver returns -1 while it still reports True.
  5. **A corner the variant does not have is left out, not relocated** (OQ-ARCH-14). The
     greeble-to-web fillet is the only one of the four with an existence condition; where it
     fails, nothing must be built and the sketch must carry no circle for it.
  6. **Nothing is constrained to a modeling convenience.** Three of the sketch's four features
     are line *segments* whose endpoints mean nothing; stretching them must move no center.
  7. **Every topology case is reached on purpose.** The swept corpus visits one of the three
     switches that decide what gets built and stays a factor of 4.33 from another, so the
     configurations where a corner disappears or a tangency stops being satisfiable are walked
     from both sides here rather than left to a sweep that never arrives. This is what found
     the web-to-bolt fillet's second boundary -- see `fillets._wtb_seed()`.

    freecadcmd src/Fuselage/freecad/check_tangency.py --pass params.json

Adding a corner means adding a `Case` -- the checks are written against the case, not against
a particular fillet. The closed forms and the existence condition are restated here rather
than imported from `fillets`, deliberately: a test that asks the code under test what the
answer is proves only that it is self-consistent.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import bulkhead_section
import corner_tree as C
import fillets
import parameters
from corner_common import is_entry_point, out_path, script_args

# What a freshly generated sketch must hold, where the generator has solved it explicitly.
TOL = 1e-7

# What a sketch must hold after a bare recompute, which is the state a delivered file is in
# once someone edits a parameter. Since the four corners share one sketch the solver stops on
# a residual over the whole system, and where the geometry is ill-conditioned -- the
# bolt-flange fillet near its degeneracy -- that shows up as about 1e-7 mm rather than the
# 1e-11 mm the separate sketches reached (`fillets._fillet_tangency_sketch()` has the
# measurement). This is set two orders above that and is still four orders below any branch
# jump, which is what the sweep exists to catch and which moves a center by millimeters.
SWEEP_TOL = 1e-5

SQ2 = math.sqrt(2.0)
SKETCH = 'FilletTangency'


class Case:
    """One rounded corner: its builder, the closed form it must agree with, and the edits
    that put it into each state worth checking.

    `closed_form` returns (cx, cy, span). `span` is the discriminant the old arithmetic
    clamped -- at or below zero the two tangencies have no common solution, which is the state
    check 3 forces and the sketch must refuse by name. Two of the four corners are cut between
    two non-parallel planes and can never reach that state; they pass `impossible=None` and
    say so rather than being quietly skipped.

    `impossible` and `inactive` return a **list** of (alias, value) edits, not one. Under a
    single shared sketch an edit that breaks one sub-system easily breaks another -- thickening
    the flange wall past the bolt boss also pushes the flange face out of the bolt-flange
    fillet's reach -- and a check whose edit breaks two corners cannot tell which one the
    refusal was about. Each set of edits below is chosen to leave the other three satisfiable.

    `active` is separate from `span` and answers a different question: not "can this circle be
    placed" but "does this variant have this corner at all".

    `driver` is the parameter this corner's center is most sensitive to, and it differs: the
    two bolt fillets follow `bolt_offset`, and the two that are measured off the flange face
    do not move with it at all, so sweeping it would prove nothing about them.
    """

    def __init__(self, tag, fillet, body, build, closed_form,
                 impossible=None, active=None, inactive=None, driver='bolt_offset'):
        self.tag, self.fillet, self.fillet_body, self.build = tag, fillet, body, build
        self.closed_form, self.impossible = closed_form, impossible
        self.active, self.inactive, self.driver = active or (lambda _c: True), inactive, driver

    def center(self, doc):
        sk = doc.getObject(SKETCH)
        return (sk.getDatum(self.tag + '_cx').Value, sk.getDatum(self.tag + '_cy').Value)

    def has_center(self, doc):
        sk = doc.getObject(SKETCH)
        return sk is not None and any(c.Name == self.tag + '_cx' for c in sk.Constraints)


def _g(cells):
    return lambda a: float(cells.get(a))


def ocf_closed_form(cells):
    """The outer corner: one radius in from each of two perpendicular flange faces."""
    g = _g(cells)
    r = g('flange_fillet_radius')
    return g('flange_inner_x') - r, g('flange_y') - r, float('inf')


def gtw_closed_form(cells):
    """The greeble-to-web corner: one radius off the flange face, one off the 45 degree wall."""
    g = _g(cells)
    r, ft = g('flange_fillet_radius'), g('flange_thickness')
    cx = g('flange_inner_x') - r
    return cx, cx + r * SQ2 + ft / SQ2, float('inf')


def gtw_active(cells):
    """The web runs from the corner at the origin to the bolt center and stops there, so it
    crosses the flange's inner face only while that face is inboard of the bolt."""
    g = _g(cells)
    return g('flange_inner_x') >= g('bolt_c')


def gtw_inactive(cells):
    """Pull the bolt inboard of the flange face, so the web no longer reaches it."""
    g = _g(cells)
    return [('bolt_offset', -g('flange_inner_x') * 0.9)]


def bff_closed_form(cells):
    """What the bolt-flange fillet's two tangencies require, as the sheet used to compute it."""
    g = _g(cells)
    cx = g('flange_inner_x') - g('flange_fillet_radius')
    span = (g('flange_fillet_radius') + g('bolt_boss_r')) ** 2 - (cx - g('bolt_c')) ** 2
    return cx, math.sqrt(max(span, 0.0)) + g('bolt_c'), span


def bff_impossible(cells):
    """Push the bolt inboard until no circle can touch both the flange face and the boss.

    Only this corner is affected: the outer corner and the greeble-to-web corner are measured
    off the flange face and do not see the bolt, and the web-to-bolt fillet's discriminant is
    the boss against the wall thickness, neither of which moves here.
    """
    g = _g(cells)
    cx = g('flange_inner_x') - g('flange_fillet_radius')
    reach = g('flange_fillet_radius') + g('bolt_boss_r')
    return [('bolt_offset', -(cx + reach * 1.1))]


def wtb_closed_form(cells):
    """What the web-to-bolt fillet's two tangencies require, as the sheet used to compute it."""
    g = _g(cells)
    a = g('flange_fillet_radius') + g('flange_thickness') / 2.0
    span = (g('flange_fillet_radius') + g('bolt_boss_r')) ** 2 - a ** 2
    tan = math.sqrt(max(span, 0.0))
    return (g('bolt_c') + (tan - a) / SQ2, g('bolt_c') + (tan + a) / SQ2, span)


def wtb_impossible(cells):
    """Shrink the boss below half the wall thickness, which is where this discriminant goes.

    The obvious edit is the other way round -- thicken the wall past twice the boss -- and it
    is wrong here. `flange_inner_x` includes `flange_thickness`, so thickening the wall also
    marches the flange face outboard until the **bolt-flange** fillet cannot be placed either,
    and the refusal then names that corner instead of this one. Shrinking the boss leaves the
    flange face where it is, and `bolt_offset` moves with it so the bolt-flange fillet stays
    exactly on its own discriminant's safe side: with the bolt directly below the fillet
    center its span is `(r + boss_r)^2`, which is positive for any boss at all.
    """
    g = _g(cells)
    r, ft = g('flange_fillet_radius'), g('flange_thickness')
    boss = ft / 2.0 * 0.9              # below ft/2, so no circle reaches both boss and wall
    return [('bolt_hole_radius', boss / 2.0), ('bolt_thickness', boss / 2.0),
            ('bolt_offset', r - g('flange_inner_x'))]


CASES = [
    Case('ocf', 'outer_corner_fillet', 'OuterCornerFillet',
         fillets.outer_corner_fillet, ocf_closed_form, driver='panel_offset'),
    Case('gtw', 'greeble_to_web_fillet', 'GreebleToWebFillet',
         fillets.greeble_to_web_fillet, gtw_closed_form,
         active=gtw_active, inactive=gtw_inactive, driver='panel_offset'),
    Case('bbf', 'bolt_flange_fillet', 'BoltFlangeFillet',
         fillets.bolt_flange_fillet, bff_closed_form, impossible=bff_impossible),
    Case('wtb', 'web_to_bolt_fillet', 'WebToBoltFillet',
         fillets.web_to_bolt_fillet, wtb_closed_form, impossible=wtb_impossible),
]


class Topology:
    """One point on a topology boundary, and what has to happen there.

    **These are not variants anybody builds, and that is the point.** The swept corpus
    exercises exactly one of the three switches below: `flange_inner_x` crosses `bolt_c` in 27
    of 148 variants, and gets within 0.05 mm of it. The other two it never approaches -- the
    boss stays above **4.33** times the wall half-thickness where the boundary is 1.0, and the
    bolt-flange fillet's reach comes within 0.45 mm of failing and never crosses. So every
    refusal path in the module was, until 2026-08-17, reachable only through one synthetic
    edit made from whichever seed happened to be passed.

    That mattered: walking these deliberately found a band where the web-to-bolt tangency is
    perfectly satisfiable and the body still cannot be built, which failed with OCCT's "shape
    is invalid" from several features downstream and named nothing. See `fillets._wtb_seed()`.

    `edits` are applied to the seeded sheet in order, each a function of the sheet. Boundaries
    are computed from the parameters rather than written down, so these stay meaningful at any
    seed. `builds` is the set of corners that must be built; `refuses` is the list of fillet
    names the refusal must mention -- more than one where a configuration defeats more than
    one corner at once, which is the case a single shared sketch has to keep straight.

    `unpinned=True` says the outcome is not asserted, only the invariant that whatever happens
    is *attributable*: either every corner that builds is one valid solid, or the refusal names a
    fillet. That is for the cases where one parameter crosses several boundaries at once and
    which one it reaches first genuinely depends on the seed -- asserting a fixed answer there
    would be writing down one variant's arithmetic and calling it a rule, which is the habit
    this whole item exists to break.
    """

    def __init__(self, name, why, edits, builds=None, refuses=(), unpinned=False):
        self.name, self.why, self.edits = name, why, edits
        self.builds, self.refuses, self.unpinned = builds, tuple(refuses), unpinned


def _face_at(offset):
    """Put the flange's inner face `offset` mm inboard of the bolt center, via panel_offset."""
    return [('panel_offset',
             lambda g: g('panel_offset') + (g('flange_inner_x') - g('bolt_c')) - offset)]


def _wtb_body_boss(g):
    """The smallest boss whose web-to-bolt covering block still has any extent.

    The block runs from the bolt center out to where the fillet meets the wall, and that point
    marches back past the bolt center as the boss thins. Setting the two to be equal and
    solving for the boss gives this, which sits *above* the boss at which the circle itself
    becomes unplaceable -- the two boundaries are not the same one.
    """
    r, ft = g('flange_fillet_radius'), g('flange_thickness')
    return math.sqrt((r + ft / 2.0) ** 2 + (ft / 2.0) ** 2) - r


def _boss(size):
    """Set the boss to `size(sheet)`, with the bolt where the bolt-flange fillet stays safe.

    Directly below the fillet center its discriminant is `(r + boss_r)^2`, positive for any
    boss at all, so this isolates the web-to-bolt fillet -- which is the whole difficulty with
    a shared sketch, and what `wtb_impossible` got wrong before.
    """
    return [('bolt_hole_radius', lambda g: size(g) / 2.0),
            ('bolt_thickness', lambda g: size(g) / 2.0),
            ('bolt_offset', lambda g: g('flange_fillet_radius') - g('flange_inner_x'))]


ALL = ('ocf', 'gtw', 'bbf', 'wtb')
NO_GTW = ('ocf', 'bbf', 'wtb')

def _web_both_fail(g):
    """A wall thick enough to defeat the bolt-flange fillet *and* the web-to-bolt fillet.

    Thickening the wall moves three things at once, which is what makes it worth a case of its
    own: it is half the wall the web-to-bolt fillet is measured off, and it is a term in
    `flange_inner_x`, so it also marches the flange face outboard and shortens the bolt-flange
    fillet's reach. The bolt-flange fillet gives out once the face passes `bolt_c - boss_r`,
    and the web-to-bolt circle once the wall half-thickness reaches the boss. Take whichever
    needs more and pass it.
    """
    boss, margin = g('bolt_boss_r'), g('flange_inner_x') - g('bolt_c')
    return 1.05 * max(2.0 * boss, g('flange_thickness') + margin + boss)


TOPOLOGY = [
    Topology('flange face 0.5 inboard of the bolt', 'the web crosses it; bolt-flange quad',
             _face_at(0.5), builds=ALL),
    Topology('flange face a hair inboard of the bolt', 'the boundary, from the inboard side',
             _face_at(1e-6), builds=ALL),
    Topology('flange face a hair outboard of the bolt', 'the boundary, from the other side',
             _face_at(-1e-6), builds=NO_GTW),
    Topology('flange face 0.5 outboard of the bolt', 'the web stops short; no such corner',
             _face_at(-0.5), builds=NO_GTW),

    Topology('boss 1.05x the block boundary', 'thin boss, thick web -- last that builds',
             _boss(lambda g: 1.05 * _wtb_body_boss(g)), builds=ALL),
    Topology('boss 0.99x the block boundary', 'circle still placeable, block has no extent',
             _boss(lambda g: 0.99 * _wtb_body_boss(g)), refuses=['web_to_bolt_fillet']),
    Topology('boss 0.99x half the web', 'no circle touches both boss and wall',
             _boss(lambda g: 0.99 * g('flange_thickness') / 2.0),
             refuses=['web_to_bolt_fillet']),

    Topology('web thick enough to defeat two corners', 'both must be named, not just the first',
             [('flange_thickness', _web_both_fail)],
             refuses=['bolt_flange_fillet', 'web_to_bolt_fillet']),
    Topology('web 2x thicker', 'one parameter, three boundaries -- whichever it reaches first',
             [('flange_thickness', lambda g: 2.0 * g('flange_thickness'))], unpinned=True),
    Topology('web 4x thicker', 'same, further along', unpinned=True,
             edits=[('flange_thickness', lambda g: 4.0 * g('flange_thickness'))]),
    Topology('web 8x thicker', 'same, further still', unpinned=True,
             edits=[('flange_thickness', lambda g: 8.0 * g('flange_thickness'))]),

    Topology('bolt at 0.999x the fillet reach', 'bolt-flange fillet at the edge of possible',
             [('bolt_offset',
               lambda g: -((g('flange_inner_x') - g('flange_fillet_radius'))
                           + 0.999 * (g('flange_fillet_radius') + g('bolt_boss_r'))))],
             builds=NO_GTW),
    Topology('bolt at exactly the fillet reach', 'the boundary itself',
             [('bolt_offset',
               lambda g: -((g('flange_inner_x') - g('flange_fillet_radius'))
                           + (g('flange_fillet_radius') + g('bolt_boss_r'))))],
             refuses=['bolt_flange_fillet']),
    Topology('bolt past the fillet reach', 'no circle touches both face and boss',
             [('bolt_offset',
               lambda g: -((g('flange_inner_x') - g('flange_fillet_radius'))
                           + 1.05 * (g('flange_fillet_radius') + g('bolt_boss_r'))))],
             refuses=['bolt_flange_fillet']),
]


def check_topology(spot, seed, fail):
    """Build every corner at one topology spot and confirm it does what it must."""
    doc = App.newDocument('top')
    C._SEEN.clear()
    fillets.sheet(doc, seed)
    cells = doc.getObject('Params')
    for alias, value_of in spot.edits:
        cells.set(alias, repr(value_of(lambda a: float(cells.get(a)))))
        doc.recompute()

    built, refusal, broke = [], None, None
    try:
        tips = [(c.tag, c.build(doc)) for c in CASES]
        doc.recompute()
        for tag, tip in tips:
            if tip is None:
                continue
            built.append(tag)
            if not tip.Shape.isValid() or len(tip.Shape.Solids) != 1:
                fail.append('%s: %s built but is not one valid solid' % (spot.name, tag))
    except RuntimeError as exc:
        refusal = str(exc)
    except Exception as exc:                                            # noqa: BLE001
        broke = '%s: %s' % (type(exc).__name__, str(exc)[:80])

    print('  %-38s %s' % (spot.name, spot.why))
    if broke is not None:
        print('      FAILED WITHOUT A NAME: %s' % broke)
        fail.append('%s: failed with an error that names no fillet -- %s'
                    % (spot.name, broke))
    elif refusal is not None:
        named = [c.fillet for c in CASES if c.fillet in refusal]
        print('      refused, naming %s: %s'
              % (' and '.join(named) or 'nothing', refusal.split('.')[0][:70]))
        missing = [n for n in spot.refuses if n not in refusal]
        if not named:
            fail.append('%s: refused without naming any fillet -- %s'
                        % (spot.name, refusal[:88]))
        elif spot.unpinned:
            pass
        elif not spot.refuses:
            fail.append('%s: expected to build %s, was refused -- %s'
                        % (spot.name, ', '.join(spot.builds or ()), refusal[:88]))
        elif missing:
            fail.append('%s: the refusal does not name %s' % (spot.name, ', '.join(missing)))
    elif spot.unpinned:
        print('      built: %s' % (', '.join(built) or 'nothing'))
    else:
        print('      built: %s' % (', '.join(built) or 'nothing'))
        if spot.refuses:
            fail.append('%s: expected a refusal naming %s, but it built %s'
                        % (spot.name, ', '.join(spot.refuses), ', '.join(built)))
        elif spot.builds is not None and tuple(built) != tuple(spot.builds):
            fail.append('%s: built %s, expected %s'
                        % (spot.name, ', '.join(built) or 'nothing', ', '.join(spot.builds)))
    App.closeDocument(doc.Name)


def fillet_only(case, seed):
    doc = App.newDocument('tan' + case.tag)
    C._SEEN.clear()
    fillets.sheet(doc, seed)
    tip = case.build(doc)
    doc.recompute()
    return doc, doc.getObject('Params'), tip


def check_solves(case, seed, fail):
    doc, cells, tip = fillet_only(case, seed)
    sk = doc.getObject(SKETCH)
    if tip is None:
        print('  omitted at these parameters -- this variant has no %s corner' % case.tag)
        if case.has_center(doc):
            fail.append('%s: omitted, but the sketch still carries a circle for it' % case.tag)
        App.closeDocument(doc.Name)
        return
    got, want = case.center(doc), case.closed_form(cells)
    print('  fully constrained = %s, solve() = %d' % (sk.FullyConstrained, sk.solve()))
    print('  center solved (%.9f, %.9f)' % got)
    print('  two tangencies require (%.9f, %.9f)' % want[:2])
    if not sk.FullyConstrained or sk.solve() != 0:
        fail.append('%s is not fully constrained' % SKETCH)
    if max(abs(got[0] - want[0]), abs(got[1] - want[1])) > TOL:
        fail.append('%s/%s: solved center disagrees with the tangencies it states'
                    % (SKETCH, case.tag))
    if not tip.Shape.isValid() or len(tip.Shape.Solids) != 1:
        fail.append('%s: the fillet is not one valid solid' % case.tag)
    App.closeDocument(doc.Name)


def check_branch(case, seed, fail):
    """Sweep the parameter the center is most sensitive to and watch for a branch jump.

    **The whole sketch has to be solvable, not just this corner.** Since OQ-ARCH-14 the four
    share one sketch, so a step that leaves *any* sub-system unsatisfiable fails the sketch and
    leaves every center holding whatever last worked -- including this one, which would then
    read as a branch jump it had no part in. Sweeping `panel_offset` for the two corners
    measured off the flange face does exactly that at small U, by marching the flange face out
    of the bolt-flange fillet's reach. Those steps are skipped and counted, and the sheet is
    recomputed on its own first so the document is never driven into the failing state at all.
    """
    doc, cells, tip = fillet_only(case, seed)
    if tip is None:
        print('  omitted at these parameters -- nothing to sweep')
        App.closeDocument(doc.Name)
        return
    base = float(cells.get(case.driver))
    worst, worst_at, seen, blocked = 0.0, None, 0, {}
    for step in range(-14, 15):
        cells.set(case.driver, repr(base + step * 0.25))
        cells.recompute()
        stuck = [c.tag for c in CASES if c.closed_form(cells)[2] <= 0]
        if stuck:
            for tag in stuck:
                blocked[tag] = blocked.get(tag, 0) + 1
            continue
        doc.recompute()
        want = case.closed_form(cells)
        seen += 1
        got = case.center(doc)
        err = max(abs(got[0] - want[0]), abs(got[1] - want[1]))
        if err > worst:
            worst, worst_at = err, base + step * 0.25
    print('  swept %s %.3f .. %.3f (%d solvable): worst |solved - tangency| = %.3e mm at %s '
          '(read after a bare recompute, tolerance %.0e)'
          % (case.driver, base - 3.5, base + 3.5, seen, worst, worst_at, SWEEP_TOL))
    if blocked:
        print('  %s step(s) skipped: the sketch as a whole is unsolvable there'
              % ', '.join('%d for %s' % (n, tag) for tag, n in sorted(blocked.items())))
    if seen == 0:
        fail.append('%s/%s: the sweep never reached a solvable configuration'
                    % (SKETCH, case.tag))
    if worst > SWEEP_TOL:
        fail.append('%s/%s: the solver left the correct branch during the sweep'
                    % (SKETCH, case.tag))
    App.closeDocument(doc.Name)


def check_refuses(case, seed, fail):
    """A configuration where the two tangencies cannot both be met must be refused, and the
    refusal must say which corner could not be built -- one sketch, four sub-systems."""
    if case.impossible is None:
        print('  no such configuration: this corner is cut between two non-parallel planes, '
              'which always admits a tangent circle')
        return
    doc = App.newDocument('bad' + case.tag)
    C._SEEN.clear()
    fillets.sheet(doc, seed)
    cells = doc.getObject('Params')
    for alias, value in case.impossible(cells):
        cells.set(alias, repr(value))
    doc.recompute()
    if case.closed_form(cells)[2] > 0:
        fail.append('%s: the "impossible" edit is still satisfiable, so this proves nothing'
                    % case.tag)
    # The edit has to break this corner and no other, or the refusal cannot be attributed.
    others = [c.tag for c in CASES if c is not case and c.closed_form(cells)[2] <= 0]
    if others:
        fail.append('%s: the "impossible" edit also breaks %s, so a refusal naming one of them '
                    'proves nothing about this corner' % (case.tag, ', '.join(others)))
    try:
        case.build(doc)
    except RuntimeError as exc:
        message = str(exc)
        print('  refused, as it should: %s' % message.split('.')[0][:96])
        if case.fillet not in message:
            fail.append('%s: refused without naming the sub-system that failed -- the message '
                        'was %r' % (case.tag, message.split('.')[0][:96]))
    else:
        fail.append('%s: an unsatisfiable tangency was accepted instead of refused' % case.tag)
    App.closeDocument(doc.Name)


def check_omits(case, seed, fail):
    """A corner the variant does not have must be absent, not moved somewhere it fits."""
    if case.inactive is None:
        print('  no such configuration: this corner exists at every parameter set')
        return
    doc = App.newDocument('off' + case.tag)
    C._SEEN.clear()
    fillets.sheet(doc, seed)
    cells = doc.getObject('Params')
    edits = case.inactive(cells)
    for alias, value in edits:
        cells.set(alias, repr(value))
    doc.recompute()
    if case.active(cells):
        fail.append('%s: the "inactive" edit leaves the corner in place, so this proves '
                    'nothing' % case.tag)
    tip = case.build(doc)
    doc.recompute()
    print('  %s: flange face %.4f, bolt center %.4f -> built %s'
          % (', '.join('%s = %.4f' % e for e in edits),
             float(cells.get('flange_inner_x')), float(cells.get('bolt_c')),
             'nothing' if tip is None else tip.Name))
    if tip is not None:
        fail.append('%s: the corner does not exist here but a body was built anyway' % case.tag)
    if case.has_center(doc):
        fail.append('%s: the corner does not exist here but %s still carries a circle for it'
                    % (case.tag, SKETCH))
    App.closeDocument(doc.Name)


def check_lines_are_arbitrary(seed, fail):
    """The solved centers must not care how long the reference lines are.

    `FilletTangency` stands three of its four features up as line *segments*, and their
    endpoints carry no geometric meaning -- they are pinned at `Params.far` either side purely
    so the sketch can reach full constraint. A `Tangent` against a segment constrains the
    circle to its infinite line, so stretching the segments must move nothing.

    Worth asserting rather than assuming, because the failure would be quiet and the fix
    tempting: constrain a fillet to a line's *endpoint* instead of the line -- a `Coincident`
    or a `PointOnObject` where a `Tangent` belongs -- and the sketch still reaches full
    constraint, still solves, still builds a plausible solid, and now has an arbitrary
    modeling convenience wired into the geometry. `check_unread_rows.py` reports `far` as
    reaching no geometry, which is the same fact arrived at from the other side; this states it
    where the sketch is, so it fails loudly instead of turning up in a survey.
    """
    doc = App.newDocument('reach')
    C._SEEN.clear()
    fillets.sheet(doc, seed)
    for case in CASES:
        case.build(doc)
    doc.recompute()
    live = [c for c in CASES if c.has_center(doc)]
    cells = doc.getObject('Params')
    before = {c.tag: c.center(doc) for c in live}

    was = float(cells.get('far'))
    worst, worst_at = 0.0, None
    for factor in (0.25, 4.0):
        cells.set('far', repr(was * factor))
        doc.recompute()
        for c in live:
            moved = max(abs(a - b) for a, b in zip(c.center(doc), before[c.tag]))
            if moved > worst:
                worst, worst_at = moved, '%s at far x%.2f' % (c.tag, factor)
    cells.set('far', repr(was))
    doc.recompute()
    print('  reference lines stretched x0.25 and x4: worst center movement %.3e mm%s'
          % (worst, '' if worst_at is None else ' (%s)' % worst_at))
    if worst > TOL:
        fail.append('%s: a solved center moved when the reference lines were stretched -- '
                    'something is constrained to an endpoint rather than to the line (%s)'
                    % (SKETCH, worst_at))
    App.closeDocument(doc.Name)


def check_editable(cases, seed, fail):
    """Save the octant, reload it, move a parameter, and confirm every solver follows."""
    doc = App.newDocument('tanedit')
    bulkhead_section.emit(doc, seed)
    path = out_path('tangency_roundtrip.FCStd')
    doc.saveAs(path)
    App.closeDocument(doc.Name)

    doc = App.openDocument(path)
    cells, tip = doc.getObject('Params'), doc.getObject('BulkheadSection')
    live = [c for c in cases if c.has_center(doc)]
    before = {c.tag: c.center(doc) for c in live}
    print('  reloaded: octant %.5f mm3, %d of %d corners present'
          % (tip.Shape.Volume, len(live), len(cases)))
    for c in live:
        print('    %s center (%.9f, %.9f)' % ((c.tag,) + before[c.tag]))
        if max(abs(a - b) for a, b in zip(before[c.tag], c.closed_form(cells)[:2])) > TOL:
            fail.append('%s/%s: the reloaded sketch does not agree with its own constraints'
                        % (SKETCH, c.tag))

    # One edit per distinct driver. "The center followed the edit" can only be asserted for
    # the corners that parameter actually moves -- the two measured off the flange face do not
    # see `bolt_offset` at all, and demanding that they move would be demanding a defect.
    for driver in sorted({c.driver for c in live}):
        moved = float(cells.get(driver)) + 0.75
        cells.set(driver, repr(moved))
        doc.recompute()
        follows = [c for c in live if c.driver == driver]
        print('  %s +0.75 after reload: octant %.5f mm3, %s must follow'
              % (driver, tip.Shape.Volume, ' and '.join(c.tag for c in follows)))
        for c in live:
            after, want = c.center(doc), c.closed_form(cells)
            print('    %s center (%.9f, %.9f), tangencies require (%.9f, %.9f)'
                  % ((c.tag,) + after + want[:2]))
            if max(abs(a - b) for a, b in zip(after, want[:2])) > SWEEP_TOL:
                fail.append('%s/%s: did not re-solve after a parameter edit on the reloaded '
                            'file' % (SKETCH, c.tag))
        for c in follows:
            if max(abs(a - b) for a, b in zip(c.center(doc), before[c.tag])) < 1e-6:
                fail.append('%s/%s: the center did not move when %s did, so nothing is '
                            'actually driven by it' % (SKETCH, c.tag, driver))
        if not tip.Shape.isValid() or len(tip.Shape.Solids) != 1:
            fail.append('the octant is not one valid solid after editing %s' % driver)
    App.closeDocument(doc.Name)
    os.remove(path)


def check_boundary_edit(case, seed):
    """What does a delivered file do when a parameter is edited past an existence boundary?

    **Reported, not asserted.** Which corners exist is decided when the document is generated,
    so a hand edit across that boundary cannot add or remove a circle -- the sketch has the
    geometry it was emitted with. That is true of every topology switch in this port. What is
    worth knowing, and was not before OQ-ARCH-14, is what the surviving body then does: it
    stays tangent to the flange face and the wall, both of which still exist, so it sits past
    the end of a web that no longer reaches it. This measures how much material that is.
    """
    if case.inactive is None:
        return
    doc = App.newDocument('bnd' + case.tag)
    bulkhead_section.emit(doc, seed)
    cells, tip = doc.getObject('Params'), doc.getObject('BulkheadSection')
    if not case.has_center(doc):
        print('  the generated file has no %s corner to begin with -- nothing to edit past'
              % case.tag)
        App.closeDocument(doc.Name)
        return
    edits = case.inactive(cells)
    was = ', '.join('%s %.4f -> %.4f' % (a, float(cells.get(a)), v) for a, v in edits)
    for alias, value in edits:
        cells.set(alias, repr(value))
    doc.recompute()
    body = doc.getObject(case.fillet_body)
    if body is None:
        print('  %s: the body is gone, so the file did follow the edit' % was)
        App.closeDocument(doc.Name)
        return
    # The octant's own volume is no use here -- the same edit moves the bolt, which moves far
    # more geometry than the fillet is. What the edit actually keeps is the part of the
    # surviving body that lies inside the finished octant, which is an upper bound on the
    # material a regenerated document would not have had.
    local = tip.Shape.copy()
    local.translate(tip.Placement.Base.negative())
    inside = body.Shape.common(local).Volume
    print('  %s' % was)
    print('  the %s body survives at %.5f mm3, of which %.5f mm3 is inside the octant'
          % (case.tag, body.Shape.Volume, inside))
    print('  a regenerated document at these parameters would leave it out; the delivered '
          'file cannot, and reports nothing')
    App.closeDocument(doc.Name)


def main():
    args = script_args()
    if not args:
        print('usage: freecadcmd check_tangency.py --pass params.json')
        return 0
    seed = parameters.seed(args[0])
    fail = []
    for case in CASES:
        for name, fn in (('the sketch solves the stated tangencies', check_solves),
                         ('it stays on the same branch across a sweep', check_branch),
                         ('an impossible configuration is refused, by name', check_refuses),
                         ('a corner this variant lacks is omitted', check_omits)):
            print('CHECK:: %s/%s -- %s' % (SKETCH, case.tag, name))
            fn(case, seed, fail)
    print('CHECK:: the reference lines\' length reaches no geometry -- %s' % SKETCH)
    check_lines_are_arbitrary(seed, fail)
    print('CHECK:: every topology case is reachable and does what it must -- %d spot(s)'
          % len(TOPOLOGY))
    for spot in TOPOLOGY:
        check_topology(spot, seed, fail)
    print('CHECK:: the saved file re-solves after an edit -- %s' % SKETCH)
    check_editable(CASES, seed, fail)
    for case in CASES:
        if case.inactive is not None:
            print('REPORT:: editing a delivered file past the %s existence boundary' % case.tag)
            check_boundary_edit(case, seed)
    print()
    if fail:
        for f in fail:
            print('  FAIL: %s' % f)
    else:
        print('  ok -- %d sub-system(s) solved, single-branch, refusing by name, omitting '
              'what is absent, and still editable' % len(CASES))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
