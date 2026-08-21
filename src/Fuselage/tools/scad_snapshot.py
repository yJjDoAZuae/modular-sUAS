"""Prove a refactor of the Python sweep code changed no geometry, without rendering.

`solid2` emits *named* parameters into the generated `.scad`, so the text it produces
for a given variant is a complete statement of the geometry that variant will build.
Capture that text for every variant before a change and after it: if the two snapshots
are byte-identical, the geometry cannot have changed. No OpenSCAD, no CGAL, seconds
rather than hours.

This is the cheap half of the verification pair:

- **This tool** proves *Python-side* changes -- call-site refactors, parameter
  plumbing, derived-value cleanups. It is exact and near-instant.
- **`sweep_check.py`** proves *SCAD-side* changes, by rendering and comparing triangle
  count, volume, and bounding box. Necessary because a change to a `.scad` module
  alters the generated text by construction, so a text diff cannot speak to it.

Usage, from the repository root:

    uv run python src/Fuselage/tools/scad_snapshot.py capture before.json
    ...make the change...
    uv run python src/Fuselage/tools/scad_snapshot.py capture after.json
    uv run python src/Fuselage/tools/scad_snapshot.py compare before.json after.json

The snapshots themselves are disposable build artifacts -- regenerate them, do not
commit them. A full capture is roughly half a megabyte.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import solid2  # noqa: E402

import fuselage_variants as fv  # noqa: E402

# Every sweep and the axes main() drives it with. Kept beside the sweeps rather than
# inferred, so a new sweep is a visible one-line addition here rather than silently
# missing from the verification.
SWEEPS = (
    ('corner', 'run_corner_parametric_sweep',
     ('panel_variants.csv', 'bulkhead_size_variants.csv', 'corner_size_variants.csv')),
    ('bulkhead', 'run_bulkhead_parametric_sweep',
     ('panel_variants.csv', 'bulkhead_type_variants.csv', 'bulkhead_size_variants.csv')),
    ('boom', 'run_boom_bulkhead_parametric_sweep',
     ('panel_variants.csv', 'bulkhead_size_variants.csv',
      'boom_bulkhead_type_variants.csv')),
    ('nose', 'run_nose_parametric_sweep',
     ('nose_size_variants.csv', 'nose_type_variants.csv')),
    ('tail', 'run_tail_parametric_sweep',
     ('nose_size_variants.csv', 'tail_type_variants.csv')),
)


def capture(quiet=False):
    """Generate every variant's .scad text, keyed by part filename.

    Substitutes solid_render so nothing reaches OpenSCAD -- the sweep runs to
    completion in seconds and produces no geometry.

    A real temporary directory is still needed: each sweep mkdir's its output
    directory up front, before the first part is generated, so a placeholder path
    fails there rather than being harmlessly ignored. Nothing is ever written into
    it, and it is removed on the way out.
    """
    captured = {}

    def record(scad_obj, output_dir, filename):
        captured[filename] = solid2.scad_render(scad_obj)
        return (filename + '.scad', filename + '.stl', filename + '.png')

    previous, fv.solid_render = fv.solid_render, record
    try:
        with tempfile.TemporaryDirectory(prefix='scad_snapshot_') as scratch:
            for label, func_name, csv_names in SWEEPS:
                before = len(captured)
                getattr(fv, func_name)(fv.axes(*csv_names), scratch)
                if not quiet:
                    print('  %-10s %4d part(s)' % (label, len(captured) - before),
                          flush=True)
    finally:
        fv.solid_render = previous
    return captured


def compare(before, after):
    """Report differences between two snapshots. Returns the number of problems."""
    only_before = sorted(set(before) - set(after))
    only_after = sorted(set(after) - set(before))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])

    for name in only_before[:10]:
        print('  MISSING NOW   %s' % name)
    for name in only_after[:10]:
        print('  NEW           %s' % name)
    for name in changed[:5]:
        print('  CHANGED       %s' % name)
        a, b = before[name].splitlines(), after[name].splitlines()
        for i, (left, right) in enumerate(zip(a, b)):
            if left != right:
                print('      line %d\n        before: %s\n        after : %s'
                      % (i + 1, left.strip(), right.strip()))
                break
        else:
            print('      differing line count: %d -> %d' % (len(a), len(b)))
    if len(changed) > 5:
        print('  ... %d more changed part(s)' % (len(changed) - 5))

    return len(only_before) + len(only_after) + len(changed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)

    cap = sub.add_parser('capture', help='generate and save every variant\'s .scad text')
    cap.add_argument('path', type=Path)

    cmp_ = sub.add_parser('compare', help='diff two snapshots')
    cmp_.add_argument('before', type=Path)
    cmp_.add_argument('after', type=Path)

    args = parser.parse_args(argv)

    if args.command == 'capture':
        print('capturing .scad text for every variant (nothing is rendered)')
        snapshot = capture()
        args.path.write_text(json.dumps(snapshot, indent=0, sort_keys=True),
                             encoding='utf-8', newline='\n')
        print('captured %d part(s) -> %s' % (len(snapshot), args.path))
        return 0

    before = json.loads(args.before.read_text(encoding='utf-8'))
    after = json.loads(args.after.read_text(encoding='utf-8'))
    print('comparing %d part(s) against %d' % (len(before), len(after)))
    problems = compare(before, after)
    print('-' * 68)
    if problems:
        print('DIFFERENT: %d part(s) differ -- the change is NOT geometry-neutral'
              % problems)
    else:
        print('IDENTICAL: every part generates byte-identical .scad; '
              'the change cannot have altered geometry')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
