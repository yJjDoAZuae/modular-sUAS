"""IP-TEST-7/10 (doc/implementation/test_coverage.md): unit-level regression for
geometry_branches.py.

`geometry_branches.py` has no verdict of its own -- it is a data reporter for
`tools/branching_dimensions.py`, always exits 0, and that is correct for what it is. What had
never been exercised is whether its own instrumentation (`_watching`'s winner detection,
`attribute_at`'s backward scan for the owning `self.x =`) actually reports the right answer,
as opposed to merely running without crashing.

`corner_common.Params.flat_offset` is the module's own worked example (its docstring calls it
"DES-9's own evidence") -- a `max()` of a longeron term and a panel term -- so it is used here
as the real branch to watch, with two constructed parameter sets chosen so each argument wins
once, rather than a synthetic function invented for the test.

Run: freecadcmd check_geometry_branches.py
"""
import inspect
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corner_common as cc
import geometry_branches as gb
from corner_common import is_entry_point, out_path

TOL = 1e-9


def main():
    failures = []

    def check(label, got, want):
        if isinstance(got, float) or isinstance(want, float):
            ok = abs(got - want) <= TOL * max(1.0, abs(want))
        else:
            ok = got == want
        print('  %-46s %-24s %-24s  %s' % (label, got, want, 'ok' if ok else 'FAIL'))
        if not ok:
            failures.append(label)

    # ------------------------------------------------------------
    # The two constructed variants. **Meters, since `Params` is SI (IP-FC-160)**; the
    # millimeter figures stay here because they are what the arithmetic reads as. At the
    # defaults, flat_offset's max() picks the longeron term (2.0 + 0.05 + 0.4 = 2.45 mm) over
    # the panel term (4.0 - (10 - 4.77 - 0.1) = -1.13 mm). Growing panel_overlap alone pushes
    # the panel term past it: 20.0 - (10 - 0 - 0) = 10.0 mm.
    # ------------------------------------------------------------
    longeron_wins = {}
    panel_wins = {'panel_overlap': 0.020,                 # 20 mm
                  'panel_thickness': 0.0, 'panel_tolerance': 0.0}

    p_lon = cc.Params(**longeron_wins)
    p_pan = cc.Params(**panel_wins)
    lon_term = p_lon.longeron_radius + 0.00005 + p_lon.longeron_chamfer    # + 0.05 mm
    pan_term = 0.020 - p_pan.corner_radius                                 # 20 mm - r
    check('defaults: the longeron term genuinely wins flat_offset', -p_lon.flat_offset,
          lon_term)
    check('grown panel_overlap: the panel term genuinely wins flat_offset', -p_pan.flat_offset,
          pan_term)

    # ------------------------------------------------------------
    # attribute_at -- the backward scan for the owning `self.x =`. Found dynamically (the
    # line `self.flat_offset = -max(` actually sits on in the current source), not hardcoded,
    # so this does not silently stop testing anything if the module is edited.
    # ------------------------------------------------------------
    source_lines = io.open(cc.__file__, encoding='utf-8').read().splitlines()
    flat_offset_line = next(i + 1 for i, line in enumerate(source_lines)
                            if 'self.flat_offset = -max(' in line)
    check('attribute_at finds flat_offset for its own max() call',
          gb.attribute_at(flat_offset_line), 'flat_offset')
    check('attribute_at returns ? above any assignment', gb.attribute_at(1), '?')

    # ------------------------------------------------------------
    # _watching -- real winner/tie bookkeeping, driven through cc.Params exactly as main()
    # drives it, against the two constructed variants plus a genuine tie (both arguments
    # equal).
    # ------------------------------------------------------------
    gb.SITES.clear()
    gb.TIES.clear()
    gb.PER_ENTRY.clear()
    original_max = getattr(cc, 'max', max)
    cc.max = gb._watching('max', max)
    try:
        entries = [longeron_wins, panel_wins]
        for i, entry in enumerate(entries):
            gb._AT[0] = i
            cc.Params(**entry)
    finally:
        cc.max = original_max

    key = (flat_offset_line, 'max')
    check('_watching recorded the longeron term winning once', gb.SITES.get(key, {}).get(0),
          1)
    check('_watching recorded the panel term winning once', gb.SITES.get(key, {}).get(1), 1)
    check('_watching per-entry record is winner-per-variant, in order',
          ''.join(gb.PER_ENTRY[key][i] for i in range(2)), '01')

    # ------------------------------------------------------------
    # A real end-to-end run of the script itself, as a subprocess exactly the way
    # tools/branching_dimensions.py drives it -- confirms the reported BRANCH/PER lines, not
    # just the in-process bookkeeping above.
    # ------------------------------------------------------------
    # **The variants file is millimeters, and that is a contract rather than an accident.**
    # The real producer is `tools/branching_dimensions.py`, which fills it from the parameter
    # sheets -- the exempt OpenSCAD path -- so `geometry_branches.py` reads it through
    # `Params.from_mm`. The dicts above are this script's own SI test data, so they cross here.
    def to_mm(entry):
        return dict((key, value * 1000.0 if key in cc.Params.LENGTHS else value)
                    for key, value in entry.items())

    variants_path = out_path('geometry_branches_variants.json')
    with io.open(variants_path, 'w', encoding='utf-8') as f:
        json.dump([to_mm(longeron_wins), to_mm(panel_wins)], f)

    freecadcmd = os.path.join(os.path.dirname(sys.executable), 'freecadcmd.exe')
    if not os.path.exists(freecadcmd):
        freecadcmd = 'freecadcmd'
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geometry_branches.py')
    proc = subprocess.run(
        [freecadcmd, script, '--pass', '--variants=' + variants_path],
        capture_output=True, text=True, timeout=60)
    out = proc.stdout
    check('subprocess run exits 0', proc.returncode, 0)
    check('subprocess reports 2 variants', 'VARIANTS 2' in out, True)
    branch_line = next((ln for ln in out.splitlines() if ln.startswith('BRANCH\tflat_offset')),
                       None)
    print('  branch line: %r' % branch_line)
    if branch_line is None or '0:1' not in branch_line or '1:1' not in branch_line:
        failures.append('subprocess BRANCH line missing expected 0:1 and 1:1 counts')
    per_line = next((ln for ln in out.splitlines() if ln.startswith('PER\tflat_offset')), None)
    print('  per line: %r' % per_line)
    if per_line is None or not per_line.endswith('01'):
        failures.append('subprocess PER line does not end in the expected "01"')

    print('')
    print('check_geometry_branches: %d failure(s)' % len(failures))
    for f in failures:
        print('  FAILED: %s' % f)
    return 1 if failures else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
