"""Run `measure_fillet_share.py` across the corpus and group the answer by branch.

OQ-ARCH-14 turns on the greeble-to-web fillet's conditional reference,

    gtw_start = max(flange_inner_x; -bolt_offset)

which picks the flange's inner face in 121 of the 148 valid variants and a plane through the
bolt center in the other 27. One variant of each was measured by hand: neither contributed
anything to the finished part, because the fillet sits inside the bolt hole and is cut away
again. One variant is an anecdote, so this runs the measurement over every geometry the
conditional can produce and reports the range.

**One bulkhead type is enough, and the default.** Both sides of the conditional are functions
of `U` and the panel only, so `end_bolt` alone visits every distinct case; the other four types
would re-measure the same corner geometry and triple the runtime. `--types all` overrides that
if the assumption ever needs re-checking.

Each variant is a separate `freecadcmd` build of `bulkhead_positive`, so this is minutes, not
seconds -- it is a sweep, and priced like one.

    uv run python src/Fuselage/tools/fillet_scope_analysis/sweep_fillet_share.py
    uv run python src/Fuselage/tools/fillet_scope_analysis/sweep_fillet_share.py --out s.json

Volumes are mm^3, as the OpenSCAD path uses them.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, '..'))
sys.path.insert(0, TOOLS)

import export_parameters  # noqa: E402
import fillet_intent  # noqa: E402
from freecad_render import freecadcmd_path  # noqa: E402

MEASURE = os.path.join(HERE, 'measure_fillet_share.py')

# Matches `measure_fillet_share.NIL` -- below this a volume is the boolean kernel's noise.
NIL = 1.0e-6


def branch_of(params_path):
    with open(params_path) as f:
        p = json.load(f)['parameters']
    d = fillet_intent.derived(p)
    inner, bolt = d['flange_inner_x'], -p['bolt_offset']
    return ('flange face' if inner >= bolt else 'bolt center', inner, bolt)


def run_one(params_path, out_path):
    """The measurement's own JSON, or None -- freecadcmd's exit code cannot be trusted.

    `freecadcmd` returns 0 even when the script raised, so the artifact is the only signal
    that the build happened. A missing file is reported as a failed variant rather than
    silently dropping out of the population being described.
    """
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
    ap.add_argument('--types', choices=('end', 'all'), default='end',
                    help="'end' measures the end_bolt type only, which visits every distinct "
                         'corner geometry (default)')
    ap.add_argument('--out', help='write the collected rows here as JSON')
    args = ap.parse_args(argv)

    picked = [v for v in fillet_intent.variants(args.types)
              if args.types == 'all' or v[1] == 'end_bolt']
    scratch = tempfile.mkdtemp(prefix='fillet_share_')
    print('%d variant(s), each a separate FreeCAD build' % len(picked))

    rows, failed = [], []
    for i, (U, type_name, panel) in enumerate(picked, start=1):
        name = 'U_%s_%s_%s' % (U, type_name, panel.replace('/', '_'))
        pp = os.path.join(scratch, name + '.params.json')
        export_parameters.main([str(U), type_name, panel, pp])
        branch, inner, bolt = branch_of(pp)

        res = run_one(pp, os.path.join(scratch, name + '.share.json'))
        if res is None:
            failed.append(name)
            print('%3d/%d  %-34s FAILED TO BUILD' % (i, len(picked), name))
            continue
        gtw = res['fillets']['GreebleToWebFillet']
        ocf = res['fillets']['OuterCornerFillet']
        exposed = res['params'].get('web_exposed')
        rows.append({'name': name, 'U': U, 'panel': panel, 'branch': branch,
                     'flange_inner_x': inner, 'minus_bolt_offset': bolt,
                     'web_exposed': exposed, 'fillets': res['fillets'],
                     'gtw': gtw, 'ocf': ocf})
        print('%3d/%d  %-34s %-11s  web exposed %10.5f%s   gtw net %9.5f in_part %9.5f'
              % (i, len(picked), name, branch, exposed if exposed is not None else -1,
                 ' NONE' if exposed is not None and exposed < NIL else '     ',
                 gtw['net'], gtw['in_part']))

    print()
    for who in ('GreebleToWebFillet', 'OuterCornerFillet', 'WebToBoltFillet',
                'BoltFlangeFillet'):
        sub = [r['fillets'][who] for r in rows]
        if not sub:
            continue
        nets = [f['net'] for f in sub]
        parts = [f['in_part'] for f in sub]
        omitted = sum(1 for f in sub if f.get('omitted'))
        print('%-19s %2d variants:  net %8.5f to %9.5f (%d inert)   '
              'in_part %8.5f to %9.5f (%d absent)%s'
              % (who, len(sub), min(nets), max(nets),
                 sum(1 for f in sub if f['inert']), min(parts), max(parts),
                 sum(1 for f in sub if f['absent']),
                 '   %d not built at all' % omitted if omitted else ''))
    for branch in ('flange face', 'bolt center'):
        sub = [r for r in rows if r['branch'] == branch]
        if not sub:
            continue
        ex = [r['web_exposed'] for r in sub if r['web_exposed'] is not None]
        print('  %-11s branch: %2d variant(s), %d absent from the part; web outside the '
              'flange base %.5f to %.5f mm^3, %d with none'
              % (branch, len(sub), sum(1 for r in sub if r['gtw']['absent']),
                 min(ex), max(ex), sum(1 for v in ex if v < NIL)))
    if failed:
        print('\n%d variant(s) did not build: %s' % (len(failed), ', '.join(failed)))

    if args.out:
        with open(args.out, 'w') as f:
            json.dump({'rows': rows, 'failed': failed}, f, indent=1)
        print('wrote %s' % args.out)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
