"""IP-TEST-7 (doc/implementation/test_coverage.md): unit-level regression for corner_common.py's
sheet-building safety net.

`half_shape`/`section`/`prism`/`report` are already exercised for real by `part_end.py`,
`part_middle.py`, `part_transition.py` and `pd_middle.py`. What had never been exercised is the
FAILURE path of the functions whose own docstrings say the failure they guard against is
silent -- `is_literal` (IP-FC-41's whole distinction between configuration and port),
`check_unseeded` (IP-FC-53: a parameter file missing a row silently built the module's own
reference value under the variant's name), `merge_params` (its conflicting-alias RuntimeError,
never actually triggered in any committed run since every real parameter set is internally
consistent), and `check_seed` (its drift-detection branch, likewise never actually hit for
real). Every real invocation of these functions in this codebase has only ever exercised their
success path; this exercises both.

Run: freecadcmd check_corner_common.py
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import (build_sheet, check_seed, check_unseeded, is_entry_point,
                           is_literal, merge_params, script_args, seeded)

TOL = 1e-9


def main():
    doc = App.newDocument('check_corner_common')
    failures = []

    def check(label, got, want):
        ok = got == want
        print('  %-46s %-24s %-24s  %s' % (label, got, want, 'ok' if ok else 'FAIL'))
        if not ok:
            failures.append(label)

    # ------------------------------------------------------------
    # is_literal -- IP-FC-41's whole distinction. A plain number is literal (configuration);
    # an '=' expression is the port itself and never is.
    # ------------------------------------------------------------
    check('is_literal("10.0")', is_literal('10.0'), True)
    check('is_literal("-2.5")', is_literal('-2.5'), True)
    check('is_literal("  3.0  ")', is_literal('  3.0  '), True)
    check('is_literal("=U * 10")', is_literal('=U * 10'), False)
    check('is_literal(numeric 10.0)', is_literal(10.0), True)
    check('is_literal("not a number")', is_literal('not a number'), False)
    check('is_literal("")', is_literal(''), False)

    # ------------------------------------------------------------
    # check_unseeded -- the half of IP-FC-53 that was missing. A literal row absent from the
    # seed and not in UNSEEDED must be reported; one the seed supplies, or an '=' row, or a
    # genuinely-exempt row (eps, in the real UNSEEDED table), must not.
    # ------------------------------------------------------------
    params = [('a', '10.0'), ('b', '=a * 2'), ('c', '5.0'), ('eps', '0.01')]
    missing = check_unseeded(params, seed={'a': 1.0})
    check('check_unseeded finds the one truly-missing literal', missing, ['c'])
    missing_full = check_unseeded(params, seed={'a': 1.0, 'c': 5.0})
    check('check_unseeded finds nothing once every literal is seeded', missing_full, [])
    missing_empty_seed = check_unseeded(params, seed={})
    check('check_unseeded with an empty seed still exempts eps', missing_empty_seed,
          ['a', 'c'])

    # ------------------------------------------------------------
    # seeded -- literal rows replaced by the seed's value; '=' rows and unseeded rows pass
    # through unchanged.
    # ------------------------------------------------------------
    out = seeded(params, seed={'a': 7.0, 'c': 9.0})
    check('seeded replaces literal a', dict(out)['a'], repr(7.0))
    check('seeded replaces literal c', dict(out)['c'], repr(9.0))
    check('seeded leaves the "=" row alone', dict(out)['b'], '=a * 2')
    check('seeded leaves an unseeded literal alone', dict(out)['eps'], '0.01')
    out_noseed = seeded(params, seed=None)
    check('seeded with no seed is an identity', out_noseed, params)

    # ------------------------------------------------------------
    # merge_params -- IP-FC-41's permanent assertion. Two modules agreeing, or disagreeing
    # only where a seed resolves it, merge cleanly; a genuine conflict on an unseeded alias
    # raises, and this has never actually been exercised for real before -- every committed
    # parameter set is internally consistent by construction, so the raise itself was
    # unverified.
    # ------------------------------------------------------------
    # SimpleNamespace, not a class: `__name__` assigned in a class BODY does not shadow
    # `type.__name__` (a data descriptor on the metaclass always wins over the class's own
    # dict), so a plain `class _ModA: __name__ = 'mod_a'` silently reads back the real class
    # name instead -- caught by this check itself failing on its first draft. A real PARAMS
    # source is always an imported module, whose `__name__` is an ordinary instance attribute
    # with no such shadowing, which SimpleNamespace matches faithfully.
    _mod_a = SimpleNamespace(__name__='mod_a', PARAMS=[('x', '1.0'), ('shared', '=a * 2')])
    _mod_b = SimpleNamespace(__name__='mod_b',
                             PARAMS=[('y', '2.0'), ('shared', '=a * 2')])   # agrees

    merged = merge_params([_mod_a, _mod_b])
    check('merge_params of two modules agreeing on "shared"', dict(merged)['shared'],
          '=a * 2')
    check('merge_params keeps both modules'' own rows', sorted(dict(merged)),
          ['shared', 'x', 'y'])

    _mod_c = SimpleNamespace(__name__='mod_c',
                             PARAMS=[('shared', '=a * 3')])    # genuinely disagrees, unseeded

    raised, has_names = False, False
    try:
        merge_params([_mod_a, _mod_c])
    except RuntimeError as exc:
        raised = True
        has_names = 'mod_a' in str(exc) and 'mod_c' in str(exc)
    print('  %-46s %-24s %-24s  %s'
          % ('merge_params raises on a genuine conflict', raised, True,
             'ok' if raised else 'FAIL'))
    if not raised:
        failures.append('merge_params should have raised RuntimeError')
    elif not has_names:
        failures.append('merge_params raised, but its message omits the conflicting modules')

    _mod_d = SimpleNamespace(__name__='mod_d', PARAMS=[('corner_radius', '10.0')])  # literal
    _mod_e = SimpleNamespace(__name__='mod_e', PARAMS=[('corner_radius', '=U * 10')])  # port

    # a seeded literal loses to an unseeded '=' row -- the relationship wins, per the
    # function's own docstring ("Where one module states a relationship and another states
    # this variant's value ... the RELATIONSHIP wins")
    merged_de = merge_params([_mod_d, _mod_e], seed={'corner_radius': 10.0})
    check('merge_params: the "=" relationship wins over a seeded literal',
          dict(merged_de)['corner_radius'], '=U * 10')

    # ------------------------------------------------------------
    # check_seed -- the mirror direction: every seeded alias the sheet carries must reproduce
    # what the authority gave. Its drift branch has likewise never actually fired for real.
    # ------------------------------------------------------------
    sheet = build_sheet(doc, [('corner_radius', '=U * 10'), ('U', '1.0')],
                        seed={'U': 1.0})
    doc.recompute()
    clean = check_seed(sheet, {'U': 1.0})
    check('check_seed finds no drift when the sheet matches the seed', clean, [])

    drift = check_seed(sheet, {'U': 1.0, 'corner_radius': 99.0})
    drift_ok = len(drift) == 1 and drift[0][0] == 'corner_radius'
    print('  %-46s %-24s %-24s  %s'
          % ('check_seed catches a genuine drift', str(drift), '1 mismatch on corner_radius',
             'ok' if drift_ok else 'FAIL'))
    if not drift_ok:
        failures.append('check_seed did not report the injected drift')

    # ------------------------------------------------------------
    # is_entry_point -- freecadcmd imports the script as a module named after its basename,
    # so __name__ is never '__main__'; this compares against argv instead. Exercised here
    # against a controlled argv rather than the real one, so both the match and no-match
    # cases are actually tested (the real argv only ever demonstrates one of them per run).
    # ------------------------------------------------------------
    saved_argv = sys.argv[:]
    try:
        sys.argv = ['freecadcmd', 'check_corner_common.py']
        check('is_entry_point matches its own script name', is_entry_point('check_corner_common'),
              True)
        check('is_entry_point does not match an unrelated name', is_entry_point('other_module'),
              False)
        check('is_entry_point always matches "__main__"', is_entry_point('__main__'), True)

        # ------------------------------------------------------------
        # script_args -- freecadcmd's own tokens (the .py path, and '--pass' itself, which it
        # forwards alongside the value) must be filtered; the actual arguments must not be.
        # ------------------------------------------------------------
        sys.argv = ['freecadcmd', 'check_corner_common.py', '--pass', 'params.json', '--pass',
                   'extra']
        check('script_args strips the script path and every --pass token',
              script_args(), ['params.json', 'extra'])
    finally:
        sys.argv = saved_argv

    print('')
    print('check_corner_common: %d failure(s)' % len(failures))
    for f in failures:
        print('  FAILED: %s' % f)

    App.closeDocument(doc.Name)
    return 1 if failures else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
