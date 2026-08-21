"""OQ-ARCH-14: `measure_clamped_gtw.py` over every variant whose greeble-to-web corner is gone.

The decision omits that fillet wherever the bolt-to-corner web never reaches the flange's inner
face. OpenSCAD still builds a body there, so those variants are the only place the port can now
disagree with the reference, and this is the whole population of them -- there is no sampling
to argue about.

    uv run python src/Fuselage/tools/fillet_scope_analysis/sweep_clamped_gtw.py
    uv run python src/Fuselage/tools/fillet_scope_analysis/sweep_clamped_gtw.py --all

By default only the variants that lost the fillet are built, which is the question. `--all`
builds every valid variant instead, which also confirms the ones that kept it are unaffected;
it costs five times as long and finds nothing new unless something has moved.

Two FreeCAD builds per variant, since the difference is only visible at the stage where the
fillet is fused -- see `measure_clamped_gtw.py` for why fusing it into the finished octant
gives a badly wrong answer instead.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..')))

import export_parameters  # noqa: E402
import fillet_intent  # noqa: E402
from freecad_render import freecadcmd_path  # noqa: E402

MEASURE = os.path.join(HERE, 'measure_clamped_gtw.py')

# Below this a volume difference is the boolean kernel's noise, not geometry.
NIL = 1.0e-6


def loses_the_corner(params_path):
    with open(params_path) as f:
        p = json.load(f)['parameters']
    d = fillet_intent.derived(p)
    return d['flange_inner_x'] < d['bolt_c']


def run_one(params_path, out_path):
    """The measurement's own JSON, or None -- `freecadcmd` exits 0 even when the script
    raised, so the artifact is the only signal that the build actually happened."""
    if os.path.exists(out_path):
        os.remove(out_path)
    subprocess.run([freecadcmd_path(), MEASURE, '--pass', params_path, out_path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(out_path):
        return None
    with open(out_path) as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--all', action='store_true',
                    help='build every valid variant, not only the ones that lost the corner')
    ap.add_argument('--out', help='write the collected rows here as JSON')
    args = ap.parse_args(argv)

    scratch = tempfile.mkdtemp(prefix='clamped_gtw_')
    picked = []
    for U, type_name, panel in fillet_intent.variants('all'):
        name = 'U_%s_%s_%s' % (U, type_name, panel.replace('/', '_'))
        pp = os.path.join(scratch, name + '.params.json')
        export_parameters.main([str(U), type_name, panel, pp])
        if args.all or loses_the_corner(pp):
            picked.append((name, pp))

    print('%d variant(s), two FreeCAD builds each' % len(picked))
    rows, failed = [], []
    for i, (name, pp) in enumerate(picked, start=1):
        res = run_one(pp, os.path.join(scratch, name + '.clamped.json'))
        if res is None:
            failed.append(name)
            print('%3d/%d  %-34s FAILED TO BUILD' % (i, len(picked), name))
            continue
        res['name'] = name
        rows.append(res)
        print('%3d/%d  %-34s corner %-9s  clamped body %9.5f  part loses %9.5f mm3%s'
              % (i, len(picked), name, 'exists' if res['corner'] else 'gone',
                 res['own'], res['net'], '' if abs(res['net']) < NIL else '   <-- MOVED'))

    print()
    gone = [r for r in rows if not r['corner']]
    moved = [r for r in rows if abs(r['net']) >= NIL]
    if gone:
        worst = max(gone, key=lambda r: abs(r['net']))
        print('%d variant(s) lost the corner. The clamped bodies ranged %.5f to %.5f mm3, and '
              'the largest change to the finished octant was %.5f mm3 on %s.'
              % (len(gone), min(r['own'] for r in gone), max(r['own'] for r in gone),
                 abs(worst['net']), worst['name']))
    print('%d variant(s) where the finished octant moved at all (threshold %g mm3)'
          % (len(moved), NIL))
    for r in moved:
        print('  %-34s %+.6f mm3 on an octant of %.4f (%+.6f%%)'
              % (r['name'], r['net'], r['octant'], 100 * r['net'] / r['octant']))
    if failed:
        print('%d variant(s) failed to build: %s' % (len(failed), ', '.join(failed)))

    if args.out:
        with open(args.out, 'w', newline='\n') as f:
            json.dump(rows, f, indent=1)
        print('wrote %s' % args.out)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
