"""OQ-DES-B14: the bolt-flange fillet's center is solved by a sketch. Does that survive use?

Replacing arithmetic with a solver buys a relationship the model states and checks, and it
costs three things that arithmetic never had to prove. This asserts all three:

  1. **The delivered .FCStd stays editable.** A generated model is not only a mesh source --
     someone opens it and changes a parameter. A sketch that solved once at generation time
     and then went stale, or that only re-solves in the GUI, would be a regression that no
     volume check would notice.
  2. **The solver stays on the right branch.** Two circles admit more than one common tangent
     circle. A wrong branch is geometry that builds happily in the wrong place, so the closed
     form is kept as a test of the solved position across a sweep of the parameter it is most
     sensitive to.
  3. **An unsatisfiable configuration is refused.** This is the whole point of the change:
     `max(...; 0)` used to clamp and return a plausible wrong center.

    freecadcmd src/Fuselage/freecad/check_bff_tangency.py --pass params.json
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


def center(doc):
    sk = doc.getObject('BffTangency')
    return sk.getDatum('bbf_cx').Value, sk.getDatum('bbf_cy').Value


def closed_form(cells):
    """What the two tangencies require, computed the way the sheet used to."""
    g = lambda a: float(cells.get(a))                                    # noqa: E731
    cx = g('flange_inner_x') - g('flange_fillet_radius')
    span = (g('flange_fillet_radius') + g('bolt_boss_r')) ** 2 - (cx - g('bolt_c')) ** 2
    return cx, math.sqrt(max(span, 0.0)) + g('bolt_c'), span


def fillet_only(seed):
    doc = App.newDocument('bfftan')
    C._SEEN.clear()
    fillets.sheet(doc, seed)
    tip = fillets.bolt_flange_fillet(doc)
    doc.recompute()
    return doc, doc.getObject('Params'), tip


def check_solves(seed, fail):
    doc, cells, tip = fillet_only(seed)
    sk = doc.getObject('BffTangency')
    got, want = center(doc), closed_form(cells)
    print('  fully constrained = %s, solve() = %d' % (sk.FullyConstrained, sk.solve()))
    print('  center solved (%.9f, %.9f)' % got)
    print('  two tangencies require (%.9f, %.9f)' % want[:2])
    if not sk.FullyConstrained or sk.solve() != 0:
        fail.append('BffTangency is not fully constrained')
    if max(abs(got[0] - want[0]), abs(got[1] - want[1])) > TOL:
        fail.append('solved center disagrees with the tangencies it states')
    if not tip.Shape.isValid() or len(tip.Shape.Solids) != 1:
        fail.append('the fillet is not one valid solid')
    App.closeDocument(doc.Name)


def check_branch(seed, fail):
    """Sweep the parameter the center is most sensitive to and watch for a branch jump."""
    doc, cells, _tip = fillet_only(seed)
    base = float(cells.get('bolt_offset'))
    worst, worst_at = 0.0, None
    for step in range(-14, 15):
        cells.set('bolt_offset', repr(base + step * 0.25))
        doc.recompute()
        want = closed_form(cells)
        if want[2] <= 0:
            continue
        got = center(doc)
        err = max(abs(got[0] - want[0]), abs(got[1] - want[1]))
        if err > worst:
            worst, worst_at = err, base + step * 0.25
    print('  swept bolt_offset %.3f .. %.3f: worst |solved - tangency| = %.3e mm at %s'
          % (base - 3.5, base + 3.5, worst, worst_at))
    if worst > TOL:
        fail.append('the solver left the correct branch during the sweep')
    App.closeDocument(doc.Name)


def check_refuses(seed, fail):
    """A flange too far out for any fillet circle to reach the boss must be refused."""
    doc = App.newDocument('bffbad')
    C._SEEN.clear()
    fillets.sheet(doc, seed)
    cells = doc.getObject('Params')
    # push the bolt inboard until the two tangencies cannot both be met
    cx = float(cells.get('flange_inner_x')) - float(cells.get('flange_fillet_radius'))
    reach = float(cells.get('flange_fillet_radius')) + float(cells.get('bolt_boss_r'))
    cells.set('bolt_offset', repr(-(cx + reach * 1.1)))
    doc.recompute()
    try:
        fillets.bolt_flange_fillet(doc)
    except RuntimeError as exc:
        print('  refused, as it should: %s' % str(exc).split('.')[0][:96])
    else:
        fail.append('an unsatisfiable tangency was accepted instead of refused')
    App.closeDocument(doc.Name)


def check_editable(seed, fail):
    """Save the octant, reload it, move a parameter, and confirm the solver follows."""
    doc = App.newDocument('bffedit')
    tip = bulkhead_section.emit(doc, seed)
    path = out_path('bff_tangency_roundtrip.FCStd')
    doc.saveAs(path)
    App.closeDocument(doc.Name)

    doc = App.openDocument(path)
    cells, tip = doc.getObject('Params'), doc.getObject('BulkheadSection')
    before_c, before_v = center(doc), tip.Shape.Volume
    print('  reloaded: center (%.9f, %.9f), octant %.5f mm3' % (before_c + (before_v,)))
    if max(abs(a - b) for a, b in zip(before_c, closed_form(cells)[:2])) > TOL:
        fail.append('the reloaded sketch does not agree with its own constraints')

    moved = float(cells.get('bolt_offset')) + 0.75
    cells.set('bolt_offset', repr(moved))
    doc.recompute()
    after_c, after_v = center(doc), tip.Shape.Volume
    want = closed_form(cells)
    print('  bolt_offset +0.75 after reload: center (%.9f, %.9f), octant %.5f mm3'
          % (after_c + (after_v,)))
    print('  tangencies require (%.9f, %.9f)' % want[:2])
    if max(abs(a - b) for a, b in zip(after_c, want[:2])) > TOL:
        fail.append('the sketch did not re-solve after a parameter edit on the reloaded file')
    if abs(after_c[1] - before_c[1]) < 1e-6:
        fail.append('the fillet center did not move, so nothing was actually driven by it')
    if not tip.Shape.isValid() or len(tip.Shape.Solids) != 1:
        fail.append('the edited octant is not one valid solid')
    App.closeDocument(doc.Name)
    os.remove(path)


def main():
    args = script_args()
    if not args:
        print('usage: freecadcmd check_bff_tangency.py --pass params.json')
        return 0
    seed = parameters.seed(args[0])
    fail = []
    for name, fn in (('the sketch solves the stated tangencies', check_solves),
                     ('it stays on the same branch across a sweep', check_branch),
                     ('an impossible configuration is refused', check_refuses),
                     ('the saved file re-solves after an edit', check_editable)):
        print('CHECK:: %s' % name)
        fn(seed, fail)
    print()
    if fail:
        for f in fail:
            print('  FAIL: %s' % f)
    else:
        print('  ok -- solved, single-branch, refusing, and still editable')
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
