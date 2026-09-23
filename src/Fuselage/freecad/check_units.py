"""IP-TEST-10 (doc/implementation/test_coverage.md): unit-level regression for units.py.

`units.py` has no FreeCAD dependency of its own -- it is pure Python (`math` only) -- but the
two-tier boundary this project has kept throughout is directory-scoped, not per-file
(tests/conftest.py: "this tier covers src/Fuselage/tools/... FreeCAD-dependent code under
src/Fuselage/freecad/... is tested separately with freecadcmd check_*.py scripts"), so this
stays a freecadcmd check rather than a pytest test, consistent with every other module in this
directory regardless of what it happens to import today.

Exercises every conversion function, `bbox_m_matches_mm`'s pass/fail/malformed-input paths
(the roadmap's own "single easiest place to be silently wrong by 1000x" check), and
`describe_bbox_mismatch`'s two diagnostic branches (mm-read-as-m, m-written-as-mm).

Run: freecadcmd check_units.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import units as u
from corner_common import is_entry_point

TOL = 1e-9


def main():
    failures = []

    def check(label, got, want, tol=TOL):
        if isinstance(got, float) or isinstance(want, float):
            ok = abs(got - want) <= tol * max(1.0, abs(want))
        else:
            ok = got == want
        print('  %-52s %-20s %-20s  %s' % (label, got, want, 'ok' if ok else 'FAIL'))
        if not ok:
            failures.append(label)

    # ------------------------------------------------------------
    # The four named conversions, and that each pair is a genuine round trip -- not merely
    # that the constant is right, but that going out and back returns the original value.
    # ------------------------------------------------------------
    check('m_to_mm(1.5)', u.m_to_mm(1.5), 1500.0)
    check('mm_to_m(1500.0)', u.mm_to_m(1500.0), 1.5)
    check('m_to_mm/mm_to_m round trip', u.mm_to_m(u.m_to_mm(0.12345)), 0.12345)
    check('mpa_to_pa(1.0)', u.mpa_to_pa(1.0), 1.0e6)
    check('pa_to_mpa(2.5e6)', u.pa_to_mpa(2.5e6), 2.5)
    check('mpa_to_pa/pa_to_mpa round trip', u.pa_to_mpa(u.mpa_to_pa(7.3)), 7.3)
    check('MM_PER_M and M_PER_MM are genuine reciprocals', u.MM_PER_M * u.M_PER_MM, 1.0)

    # Angles delegate to math.degrees/radians directly -- confirm the re-export is the same
    # function, not a copy that could drift, and that it behaves correctly either way.
    import math
    check('rad_to_deg is math.degrees', u.rad_to_deg is math.degrees, True)
    check('deg_to_rad is math.radians', u.deg_to_rad is math.radians, True)
    check('rad_to_deg(pi)', u.rad_to_deg(math.pi), 180.0)

    # ------------------------------------------------------------
    # bbox_m_matches_mm -- the roadmap's named check for a 1000x scale error. A clean pass
    # (every component agrees), a genuine failure (one axis off by exactly 1000x, the error
    # this whole module exists to catch), and the malformed-input guard.
    # ------------------------------------------------------------
    bbox_mm = (-40.0, -8.0, 0.0, 0.0, 5.1375, 6.0)
    bbox_m_correct = tuple(u.mm_to_m(v) for v in bbox_mm)
    ok, report = u.bbox_m_matches_mm(bbox_m_correct, bbox_mm)
    check('bbox_m_matches_mm agrees on a correctly converted box', ok, True)
    check('bbox_m_matches_mm reports nothing when it agrees', report, [])

    # zmax read in millimeters where meters were wanted -- exactly the 1000x defect.
    bbox_m_wrong = bbox_m_correct[:5] + (bbox_mm[5],)
    ok2, report2 = u.bbox_m_matches_mm(bbox_m_wrong, bbox_mm)
    check('bbox_m_matches_mm catches a genuine 1000x miss', ok2, False)
    wrong_axis_ok = len(report2) == 1 and report2[0][0] == 'zmax'
    print('  %-52s %-20s %-20s  %s' % ('bbox_m_matches_mm isolates the wrong axis',
                                       str(report2), '1 entry, zmax',
                                       'ok' if wrong_axis_ok else 'FAIL'))
    if not wrong_axis_ok:
        failures.append('bbox_m_matches_mm did not isolate zmax as the sole mismatch')

    raised = False
    try:
        u.bbox_m_matches_mm((1.0, 2.0, 3.0), bbox_mm)
    except ValueError:
        raised = True
    check('bbox_m_matches_mm refuses a malformed (short) box', raised, True)

    # ------------------------------------------------------------
    # describe_bbox_mismatch -- the diagnostic text, including its two "this looks like a
    # 1000x error in this specific direction" branches.
    # ------------------------------------------------------------
    clean_msg = u.describe_bbox_mismatch([])
    check('describe_bbox_mismatch on a clean report', clean_msg, 'bounding boxes agree')

    msg_over = u.describe_bbox_mismatch(report2)
    over_ok = 'measured is about 1000x expected' in msg_over
    print('  %-52s %-20s %-20s  %s' % ('describe_bbox_mismatch names mm-read-as-m',
                                       repr(msg_over[:40]), 'contains the 1000x phrase',
                                       'ok' if over_ok else 'FAIL'))
    if not over_ok:
        failures.append('describe_bbox_mismatch did not name the mm-read-as-m direction')

    # The opposite direction: a value in meters written where millimeters belong (1/1000).
    under_report = [('zmax', bbox_m_correct[5], bbox_m_correct[5] * u.M_PER_MM, 0.999)]
    msg_under = u.describe_bbox_mismatch(under_report)
    under_ok = 'measured is about 1/1000 of expected' in msg_under
    print('  %-52s %-20s %-20s  %s' % ('describe_bbox_mismatch names m-written-as-mm',
                                       repr(msg_under[:40]), 'contains the 1/1000 phrase',
                                       'ok' if under_ok else 'FAIL'))
    if not under_ok:
        failures.append('describe_bbox_mismatch did not name the m-written-as-mm direction')

    print('')
    print('check_units: %d failure(s)' % len(failures))
    for f in failures:
        print('  FAILED: %s' % f)
    return 1 if failures else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
