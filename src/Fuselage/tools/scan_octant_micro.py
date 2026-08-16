"""IP-FC-67: is the bulkhead octant's sub-micron geometry still there, and where?

IP-FC-67 was opened on two variants and claims the octant carries degenerate micro-geometry
"at every parameter set". Whether that is still true is a question about the geometry as it
stands, and the geometry has moved twice since -- IP-FC-58 changed where the bolt-flange
fillet's block starts, and IP-FC-76 replaced its centre with a solved one. So this resolves
the variants, hands them to FreeCAD in one process, and reports the distribution.

Cheap by the standards of this project: it builds octants only, never the full part, and
never renders OpenSCAD. Roughly ten seconds a variant.

    uv run python src/Fuselage/tools/scan_octant_micro.py                    # end types
    uv run python src/Fuselage/tools/scan_octant_micro.py --types all
    uv run python src/Fuselage/tools/scan_octant_micro.py --limit 6 --keep

A feature under `--flag` mm is reported, never failed: this is a measurement of where the
geometry sits relative to what a boolean can resolve, not a pass/fail gate. The exit status
is non-zero only when a variant fails to build at all.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import export_parameters  # noqa: E402
import fuselage_variants as fv  # noqa: E402

FREECAD = os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'), 'FreeCAD 1.1',
                       'bin', 'freecadcmd.exe')
FALLBACK = os.path.expandvars(r'%LOCALAPPDATA%\Programs\FreeCAD 1.1\bin\freecadcmd.exe')
WORKER = os.path.normpath(os.path.join(HERE, '..', 'freecad', 'measure_octant_micro.py'))
AXES = ('panel_variants.csv', 'bulkhead_type_variants.csv', 'bulkhead_size_variants.csv')

# 0.2 mm is the layer height; a feature four orders under it is not a design feature. These
# are the bands the report groups by, not thresholds anything is judged against.
BANDS = [(1e-4, 'under 0.0001'), (1e-3, '0.0001 to 0.001'), (1e-2, '0.001 to 0.01'),
         (2e-1, '0.01 to 0.2'), (float('inf'), 'over 0.2 (a real feature)')]


def freecadcmd():
    for path in (FREECAD, FALLBACK):
        if os.path.exists(path):
            return path
    raise SystemExit('freecadcmd not found; looked in %s and %s' % (FREECAD, FALLBACK))


def variants(types):
    """Valid bulkhead variants of the requested types, as (U, type_name, panel_name)."""
    printer = fv.null_printer_settings()
    out = []
    for params in fv.flatten_param_space(fv.read_all_param_axes(fv.axes(*AXES))):
        dp = fv.derived_parameters(params['U'], 1.0, params, printer, True)
        if not fv.family_is_valid('bulkhead', dp):
            continue
        if types == 'end' and dp.bulkhead.type != fv.BulkheadType.END:
            continue
        out.append((params['U'], dp.bulkhead.type_name, dp.panel.type_name))
    return out


def band(value):
    for limit, label in BANDS:
        if value < limit:
            return label
    return BANDS[-1][1]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--types', choices=('end', 'all'), default='end',
                    help='which bulkhead types to measure (default end, where IP-FC-67 looked)')
    ap.add_argument('--limit', type=int, help='measure only the first N, for a quick look')
    ap.add_argument('--tol', type=float, default=1e-3,
                    help='vertex pairs closer than this are counted (default 0.001 mm)')
    ap.add_argument('--scratch', help='where to put the parameter files (default: a temp dir)')
    ap.add_argument('--keep', action='store_true', help='keep the scratch tree')
    args = ap.parse_args(argv)

    picked = variants(args.types)
    if args.limit:
        picked = picked[:args.limit]
    if not picked:
        print('no variants matched')
        return 0

    scratch = args.scratch or tempfile.mkdtemp(prefix='octant_micro_')
    os.makedirs(scratch, exist_ok=True)
    try:
        manifest = []
        for U, type_name, panel in picked:
            name = 'U_%s_%s_%s' % (U, type_name, panel.replace('/', '_'))
            path = os.path.join(scratch, name + '.json')
            export_parameters.main([str(U), type_name, panel, path])
            manifest.append({'name': name, 'params': path})
        manifest_path = os.path.join(scratch, 'manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        out_path = os.path.join(scratch, 'results.json')
        proc = subprocess.run([freecadcmd(), WORKER, '--pass', manifest_path, '--pass',
                               out_path, '--pass', repr(args.tol)],
                              capture_output=True, text=True)
        for line in proc.stdout.splitlines():
            if line.startswith('  ') or line.startswith('measuring'):
                print(line)
        if not os.path.exists(out_path):
            # freecadcmd exits 0 on a script exception, so the artifact is the only signal
            print(proc.stdout[-2000:])
            print(proc.stderr[-2000:])
            raise SystemExit('the worker wrote no results')
        with open(out_path) as f:
            results = json.load(f)['results']
    finally:
        if not args.keep and not args.scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    good = [r for r in results if r['ok']]
    bad = [r for r in results if not r['ok']]

    print()
    print('%d variant(s) measured, %d failed to build' % (len(good), len(bad)))
    if good:
        counts = {}
        for r in good:
            counts.setdefault(band(r['min_edge']), []).append(r)
        print()
        print('shortest edge in SectionCut, by band:')
        for _limit, label in BANDS:
            rows = counts.get(label, [])
            if rows:
                print('  %-28s %3d variant(s)   e.g. %s at %.8f mm'
                      % (label, len(rows), rows[0]['name'], rows[0]['min_edge']))
        worst = min(good, key=lambda r: r['min_edge'])
        print()
        print('smallest edge anywhere : %.8f mm on %s' % (worst['min_edge'], worst['name']))
        neg = [r for r in good if r['min_face'] < 0]
        tiny = [r for r in good if 0 <= r['min_face'] < 1e-4]
        print('faces with negative area: %d   faces under 0.0001 mm2: %d'
              % (len(neg), len(tiny)))
        withp = [r for r in good if r['pairs']]
        print('variants with vertex pairs under %g mm: %d' % (args.tol, len(withp)))
        for r in withp[:5]:
            print('    %-34s %d pair(s), closest %.9f mm'
                  % (r['name'], r['pairs'], r['closest_pair'][0]))
        notsolid = [r for r in good if r['solids'] != 1 or not r['valid']]
        if notsolid:
            print('variants whose octant is not one valid solid: %d -- %s'
                  % (len(notsolid), ', '.join(r['name'] for r in notsolid[:5])))
    for r in bad:
        print('  FAILED %-34s %s' % (r['name'], r['error']))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
