"""IP-TEST-11: build_part.py had no dedicated test of its own -- every other check script in
this directory imports a kind's geometry module directly, never `build_part.py` itself, so its
own logic (`parse`'s hand-rolled `--pass` argument handling, `load_seed`'s two file shapes,
`export_deflection`'s per-U cowl scaling, `fcstd_path`'s default derivation, and the real
"always writes a `.FCStd`" promise the module's own docstring makes) had no committed
regression at all -- only the narrative record of when each was written (IP-FC-10, 11, 14, 45).

Uses the real `out/reference_bulkhead.params.json` fixture (the "variant" file shape
`tools/export_parameters.py` writes) for the file-shape and end-to-end tests, since it is
already relied on elsewhere in this directory and building a real bulkhead is cheap.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import build_part as bp
from corner_common import is_entry_point

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE_BULKHEAD = os.path.join(HERE, 'out', 'reference_bulkhead.params.json')
SCRATCH = os.path.join(HERE, 'out', 'check_build_part_scratch')


def _check_parse():
    ok = True

    got = bp.parse(['build_part.py', '--pass', '--kind=bulkhead', '--pass',
                    '--params=p.json', '--pass', '--out=o.stl'])
    want = {'kind': 'bulkhead', 'params': 'p.json', 'out': 'o.stl'}
    if got != want:
        print('  FAIL parse: normal args -> %r, want %r' % (got, want))
        ok = False

    try:
        bp.parse(['--kind=bulkhead', '--params=p.json'])   # --out missing
        print('  FAIL parse: missing --out did not raise')
        ok = False
    except SystemExit as exc:
        if 'out' not in str(exc):
            print('  FAIL parse: missing-arg message %r does not name the missing flag'
                  % str(exc))
            ok = False

    try:
        bp.parse(['--kind=not_a_real_kind', '--params=p.json', '--out=o.stl'])
        print('  FAIL parse: unknown kind did not raise')
        ok = False
    except SystemExit as exc:
        if 'unknown kind' not in str(exc):
            print('  FAIL parse: unknown-kind message %r' % str(exc))
            ok = False

    try:
        bp.parse(['--kind=bulkhead', '--params=p.json', '--out=o.stl', 'positional'])
        print('  FAIL parse: bare positional (not a --pass, not a .py) did not raise')
        ok = False
    except SystemExit:
        pass

    if ok:
        print('  parse: OK (5/5)')
    return ok


def _check_fcstd_path():
    ok = True
    cases = [
        ({'out': 'part.stl'}, 'part.FCStd'),
        ({'out': os.path.join('x', 'part.partial.stl')},
         os.path.join('x', 'part.partial.FCStd')),
        ({'out': 'part.stl', 'fcstd': 'explicit.FCStd'}, 'explicit.FCStd'),
    ]
    for opt, want in cases:
        got = bp.fcstd_path(opt)
        if got != want:
            print('  FAIL fcstd_path(%r) -> %r, want %r' % (opt, got, want))
            ok = False
    if ok:
        print('  fcstd_path: OK (%d/%d)' % (len(cases), len(cases)))
    return ok


def _check_load_seed():
    ok = True

    seed = bp.load_seed(REFERENCE_BULKHEAD, 'bulkhead')
    if not isinstance(seed, dict) or 'U' not in seed or seed.get('U') != 1.0:
        print('  FAIL load_seed: variant-shape file did not load the bulkhead table, got %r'
              % (seed,))
        ok = False

    os.makedirs(SCRATCH, exist_ok=True)
    swept_ok_path = os.path.join(SCRATCH, 'swept_ok.json')
    with open(swept_ok_path, 'w') as f:
        json.dump({'kind': 'bulkhead', 'parameters': {'U': 2.0, 'FX': 1.0}}, f)
    seed2 = bp.load_seed(swept_ok_path, 'bulkhead')
    if seed2 != {'U': 2.0, 'FX': 1.0}:
        print('  FAIL load_seed: sweep-shape file (kind matches) -> %r' % (seed2,))
        ok = False

    swept_bad_path = os.path.join(SCRATCH, 'swept_bad.json')
    with open(swept_bad_path, 'w') as f:
        json.dump({'kind': 'corner', 'parameters': {'U': 2.0}}, f)
    try:
        bp.load_seed(swept_bad_path, 'bulkhead')
        print('  FAIL load_seed: mismatched kind did not raise')
        ok = False
    except SystemExit as exc:
        if 'corner' not in str(exc) or 'bulkhead' not in str(exc):
            print('  FAIL load_seed: mismatch message %r missing both kind names' % str(exc))
            ok = False

    if ok:
        print('  load_seed: OK (3/3)')
    return ok


def _check_export_deflection():
    ok = True
    cases = [
        ('bulkhead', {}, bp.LINEAR_DEFLECTION),
        ('bulkhead', {'U': 4.0}, bp.LINEAR_DEFLECTION),   # non-cowl: U must not matter
        ('tail', {'U': 2.0}, bp.COWL_LINEAR_DEFLECTION * 2.0),
        ('tail', {}, bp.COWL_LINEAR_DEFLECTION * 1.0),    # no U in seed -> falls back to 1.0
        ('nose_cowl_shell', {'U': 0.5}, bp.COWL_LINEAR_DEFLECTION * 0.5),
    ]
    for kind, seed, want in cases:
        got = bp.export_deflection(kind, seed)
        if abs(got - want) > 1e-12:
            print('  FAIL export_deflection(%r, %r) -> %.6f, want %.6f'
                  % (kind, seed, got, want))
            ok = False
    if ok:
        print('  export_deflection: OK (%d/%d)' % (len(cases), len(cases)))
    return ok


def _check_end_to_end_build():
    """The real promise: a real build always writes a `.FCStd` beside the mesh, exits 0, and
    the shape it wrote is valid and single-solid -- `main()`'s own logic, exercised directly
    rather than via a subprocess so this can report a real Python exception if one occurs."""
    ok = True
    os.makedirs(SCRATCH, exist_ok=True)
    out_stl = os.path.join(SCRATCH, 'e2e_bulkhead.stl')
    out_fcstd = os.path.join(SCRATCH, 'e2e_bulkhead.FCStd')
    for p in (out_stl, out_fcstd):
        if os.path.exists(p):
            os.remove(p)

    doc = App.newDocument('check_build_part_e2e')
    tip = bp.build(doc, 'bulkhead', REFERENCE_BULKHEAD)
    doc.recompute()
    shape = tip.Shape
    if not shape.isValid() or len(shape.Solids) != 1:
        print('  FAIL end-to-end: built shape invalid=%s solids=%d'
              % (not shape.isValid(), len(shape.Solids)))
        ok = False

    deflection = bp.export_deflection('bulkhead', bp.load_seed(REFERENCE_BULKHEAD, 'bulkhead'))
    facets = bp.write_mesh(shape, out_stl, deflection)
    doc.saveAs(out_fcstd)

    if not os.path.exists(out_stl) or os.path.getsize(out_stl) == 0:
        print('  FAIL end-to-end: mesh was not written to %s' % out_stl)
        ok = False
    if not os.path.exists(out_fcstd):
        print('  FAIL end-to-end: .FCStd was not written to %s -- the "always written, never '
              'skipped" promise (IP-FC-14) does not hold' % out_fcstd)
        ok = False
    if facets <= 0:
        print('  FAIL end-to-end: write_mesh reported %d facets' % facets)
        ok = False

    if ok:
        print('  end-to-end build (bulkhead, real fixture): OK  volume=%.4f  facets=%d'
              % (shape.Volume, facets))
    return ok


def main():
    checks = [_check_parse, _check_fcstd_path, _check_load_seed,
              _check_export_deflection, _check_end_to_end_build]
    ok = True
    for check in checks:
        ok = check() and ok
    sys.stdout.flush()
    return 0 if ok else 1


if is_entry_point(__name__):
    raise SystemExit(main())
