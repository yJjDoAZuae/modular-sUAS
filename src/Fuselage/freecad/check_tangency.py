"""IP-FC-73: the fillet centers that are solved by a sketch. Does that survive use?

Replacing arithmetic with a solver buys a relationship the model states and checks, and it
costs four things that arithmetic never had to prove. This asserts all four, for every fillet
converted so far:

  1. **The delivered .FCStd stays editable.** A generated model is not only a mesh source --
     someone opens it and changes a parameter. A sketch that solved once at generation time
     and then went stale, or that only re-solves in the GUI, would be a regression that no
     volume check would notice.
  2. **The solver stays on the right branch.** A circle tangent to two things admits more than
     one solution. A wrong branch is geometry that builds happily in the wrong place, so the
     closed form is kept as a test of the solved position across a sweep of the parameter it
     is most sensitive to.
  3. **An unsatisfiable configuration is refused.** This is the whole point of the change: the
     `max(...; 0)` these replace used to clamp and return a plausible wrong center.
  4. **Full constraint is checked by `solve()` and not by `FullyConstrained` alone.** The
     latter answers "are there enough constraints", never "were they satisfiable" -- past a
     degeneracy the solver returns -1 while it still reports True.

    freecadcmd src/Fuselage/freecad/check_tangency.py --pass params.json

Named for the property rather than for one fillet: this was `check_bff_tangency.py` while the
bolt-flange fillet was the only conversion, and the remaining two of IP-FC-73 belong here too
rather than in copies of it. Adding one means adding a `Case` -- the four checks are written
against the case, not against a particular sketch.
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

TOL = 1e-7
SQ2 = math.sqrt(2.0)


class Case:
    """One converted fillet: its sketch, its builder, and the closed form it must agree with.

    `closed_form` returns (cx, cy, span). `span` is the discriminant the old arithmetic
    clamped: at or below zero the two tangencies have no common solution, which is the state
    check 3 forces and the sketch must refuse.

    `impossible` returns a parameter edit -- (alias, value) -- that puts the case past that
    point, since what makes a configuration unsatisfiable differs per fillet.
    """

    def __init__(self, tag, sketch, build, closed_form, impossible, driver='bolt_offset'):
        self.tag, self.sketch, self.build = tag, sketch, build
        self.closed_form, self.impossible, self.driver = closed_form, impossible, driver

    def center(self, doc):
        sk = doc.getObject(self.sketch)
        return (sk.getDatum(self.tag + '_cx').Value, sk.getDatum(self.tag + '_cy').Value)


def _g(cells):
    return lambda a: float(cells.get(a))


def bff_closed_form(cells):
    """What the bolt-flange fillet's two tangencies require, as the sheet used to compute it."""
    g = _g(cells)
    cx = g('flange_inner_x') - g('flange_fillet_radius')
    span = (g('flange_fillet_radius') + g('bolt_boss_r')) ** 2 - (cx - g('bolt_c')) ** 2
    return cx, math.sqrt(max(span, 0.0)) + g('bolt_c'), span


def bff_impossible(cells):
    """Push the bolt inboard until no circle can touch both the flange face and the boss."""
    g = _g(cells)
    cx = g('flange_inner_x') - g('flange_fillet_radius')
    reach = g('flange_fillet_radius') + g('bolt_boss_r')
    return 'bolt_offset', -(cx + reach * 1.1)


def wtb_closed_form(cells):
    """What the web-to-bolt fillet's two tangencies require, as the sheet used to compute it."""
    g = _g(cells)
    a = g('flange_fillet_radius') + g('flange_thickness') / 2.0
    span = (g('flange_fillet_radius') + g('bolt_boss_r')) ** 2 - a ** 2
    tan = math.sqrt(max(span, 0.0))
    return (g('bolt_c') + (tan - a) / SQ2, g('bolt_c') + (tan + a) / SQ2, span)


def wtb_impossible(cells):
    """Thicken the wall past twice the boss radius, which is where its discriminant goes."""
    g = _g(cells)
    return 'flange_thickness', 2.0 * g('bolt_boss_r') * 1.1


CASES = [
    Case('bbf', 'BffTangency', fillets.bolt_flange_fillet, bff_closed_form, bff_impossible),
    Case('wtb', 'WtbTangency', fillets.web_to_bolt_fillet, wtb_closed_form, wtb_impossible),
]


def fillet_only(case, seed):
    doc = App.newDocument('tan' + case.tag)
    C._SEEN.clear()
    fillets.sheet(doc, seed)
    tip = case.build(doc)
    doc.recompute()
    return doc, doc.getObject('Params'), tip


def check_solves(case, seed, fail):
    doc, cells, tip = fillet_only(case, seed)
    sk = doc.getObject(case.sketch)
    got, want = case.center(doc), case.closed_form(cells)
    print('  fully constrained = %s, solve() = %d' % (sk.FullyConstrained, sk.solve()))
    print('  center solved (%.9f, %.9f)' % got)
    print('  two tangencies require (%.9f, %.9f)' % want[:2])
    if not sk.FullyConstrained or sk.solve() != 0:
        fail.append('%s is not fully constrained' % case.sketch)
    if max(abs(got[0] - want[0]), abs(got[1] - want[1])) > TOL:
        fail.append('%s: solved center disagrees with the tangencies it states' % case.sketch)
    if not tip.Shape.isValid() or len(tip.Shape.Solids) != 1:
        fail.append('%s: the fillet is not one valid solid' % case.sketch)
    App.closeDocument(doc.Name)


def check_branch(case, seed, fail):
    """Sweep the parameter the center is most sensitive to and watch for a branch jump."""
    doc, cells, _tip = fillet_only(case, seed)
    base = float(cells.get(case.driver))
    worst, worst_at, seen = 0.0, None, 0
    for step in range(-14, 15):
        cells.set(case.driver, repr(base + step * 0.25))
        doc.recompute()
        want = case.closed_form(cells)
        if want[2] <= 0:
            continue
        seen += 1
        got = case.center(doc)
        err = max(abs(got[0] - want[0]), abs(got[1] - want[1]))
        if err > worst:
            worst, worst_at = err, base + step * 0.25
    print('  swept %s %.3f .. %.3f (%d solvable): worst |solved - tangency| = %.3e mm at %s'
          % (case.driver, base - 3.5, base + 3.5, seen, worst, worst_at))
    if seen == 0:
        fail.append('%s: the sweep never reached a solvable configuration' % case.sketch)
    if worst > TOL:
        fail.append('%s: the solver left the correct branch during the sweep' % case.sketch)
    App.closeDocument(doc.Name)


def check_refuses(case, seed, fail):
    """A configuration where the two tangencies cannot both be met must be refused."""
    doc = App.newDocument('bad' + case.tag)
    C._SEEN.clear()
    fillets.sheet(doc, seed)
    cells = doc.getObject('Params')
    alias, value = case.impossible(cells)
    cells.set(alias, repr(value))
    doc.recompute()
    if case.closed_form(cells)[2] > 0:
        fail.append('%s: the "impossible" edit is still satisfiable, so this proves nothing'
                    % case.sketch)
    try:
        case.build(doc)
    except RuntimeError as exc:
        print('  refused, as it should: %s' % str(exc).split('.')[0][:96])
    else:
        fail.append('%s: an unsatisfiable tangency was accepted instead of refused'
                    % case.sketch)
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
    before = {c.tag: c.center(doc) for c in cases}
    print('  reloaded: octant %.5f mm3' % tip.Shape.Volume)
    for c in cases:
        print('    %s center (%.9f, %.9f)' % ((c.tag,) + before[c.tag]))
        if max(abs(a - b) for a, b in zip(before[c.tag], c.closed_form(cells)[:2])) > TOL:
            fail.append('%s: the reloaded sketch does not agree with its own constraints'
                        % c.sketch)

    moved = float(cells.get('bolt_offset')) + 0.75
    cells.set('bolt_offset', repr(moved))
    doc.recompute()
    print('  bolt_offset +0.75 after reload: octant %.5f mm3' % tip.Shape.Volume)
    for c in cases:
        after, want = c.center(doc), c.closed_form(cells)
        print('    %s center (%.9f, %.9f), tangencies require (%.9f, %.9f)'
              % ((c.tag,) + after + want[:2]))
        if max(abs(a - b) for a, b in zip(after, want[:2])) > TOL:
            fail.append('%s: did not re-solve after a parameter edit on the reloaded file'
                        % c.sketch)
        if max(abs(a - b) for a, b in zip(after, before[c.tag])) < 1e-6:
            fail.append('%s: the center did not move, so nothing is actually driven by it'
                        % c.sketch)
    if not tip.Shape.isValid() or len(tip.Shape.Solids) != 1:
        fail.append('the edited octant is not one valid solid')
    App.closeDocument(doc.Name)
    os.remove(path)


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
                         ('an impossible configuration is refused', check_refuses)):
            print('CHECK:: %s -- %s' % (case.sketch, name))
            fn(case, seed, fail)
    print('CHECK:: the saved file re-solves after an edit -- %s'
          % ', '.join(c.sketch for c in CASES))
    check_editable(CASES, seed, fail)
    print()
    if fail:
        for f in fail:
            print('  FAIL: %s' % f)
    else:
        print('  ok -- %d sketch(es) solved, single-branch, refusing, and still editable'
              % len(CASES))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
