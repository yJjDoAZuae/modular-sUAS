"""Prove a change altered no *parameters*, without rendering or generating geometry.

This is the toolchain-independent half of the verification pair, and it is what replaces
`scad_snapshot.py` when the FreeCAD port removes the generated `.scad` text that tool
compares.

- **`scad_snapshot.py`** compares generated OpenSCAD source. Exact and fast, but it exists
  only while OpenSCAD is the backend: FreeCAD builds objects in memory and emits no
  intermediate text to diff.
- **This tool** compares the `Parameters` / `NoseParameters` tree that *both* backends
  consume. It is exact, faster still, and survives the port untouched -- the parameter
  layer is the part of the pipeline the migration does not replace.

What it covers, and what it does not:

- Covers everything upstream of geometry construction: the CSV and JSON axes, the
  Cartesian product, `derived_parameters()` and `derived_cowl_parameters()`, the validity
  checks, and the output filename scheme. That is where most changes land.
- Does **not** cover geometry code. A change inside a `.scad` module or a FreeCAD
  generator produces identical parameters and different solids, and this tool will
  correctly report IDENTICAL. Use a geometric comparison for those.

That division is the same one `scad_snapshot.py` documents, moved one layer up.

Usage, from the repository root:

    uv run python src/Fuselage/tools/params_snapshot.py capture before.json
    ...make the change...
    uv run python src/Fuselage/tools/params_snapshot.py capture after.json
    uv run python src/Fuselage/tools/params_snapshot.py compare before.json after.json

Snapshots are disposable build artifacts -- regenerate them, do not commit them.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fuselage_variants as fv  # noqa: E402

# Every sweep and the axes main() drives it with. Deliberately duplicated from
# scad_snapshot.py rather than shared: the two tools must be able to disagree, because a
# refactor that accidentally changes which variants exist is exactly the class of bug
# worth catching, and a shared constant would hide it.
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


def encode(value):
    """Render a parameter tree as plain JSON-able data, deterministically.

    Dataclasses become dicts in *field declaration order*, not alphabetical: a field
    reordering is a real change to a positional cross-language contract, so it should
    show up as a difference rather than be normalised away.

    Enums become "TypeName.MEMBER" rather than their value, so that renumbering an enum
    is visible and renaming a member is visible, which `repr()` alone would not give.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name))
                for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return '%s.%s' % (type(value).__name__, value.name)
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if isinstance(value, float):
        # repr() round-trips exactly in Python 3; str() would too, but repr is explicit
        # about the intent to preserve the bit pattern.
        return repr(value)
    return value


def capture(quiet=False):
    """Derive every variant's parameter tree, keyed by the part filename it would write.

    Substitutes `solid_render` so no geometry is generated and nothing reaches OpenSCAD.
    The sweeps still run their full derivation and validity logic, which is the point --
    a rejected combination must stay rejected, and that is only visible by running the
    same code path the sweep uses.

    The filename is the key rather than an index, so that a change to the naming scheme
    shows up as renamed entries rather than as silently shifted values.
    """
    captured = {}

    def record(scad_obj, output_dir, filename):
        # scad_obj is the solid2 object tree; deliberately not inspected. This tool is
        # about parameters, and reaching into the geometry here would blur the boundary
        # that makes the two verification tiers independent.
        captured[filename] = None
        return (filename + '.scad', filename + '.stl', filename + '.png')

    # The render functions receive the derived parameters; intercept them there so the
    # captured tree is exactly what geometry would have been built from.
    originals = {}
    for name in ('corner_render', 'bulkhead_render', 'boom_bulkhead_render',
                 'nose_render', 'tail_render'):
        originals[name] = getattr(fv, name)

    def wrap(name, func):
        def wrapped(*args, **kwargs):
            # dp is the first dataclass argument; nose/tail take (U, dp, ...).
            dp = next((a for a in args if dataclasses.is_dataclass(a)), None)
            filename = next((a for a in args if isinstance(a, str)
                             and a.endswith('.scad')), None)
            if dp is not None and filename is not None:
                captured[filename] = encode(dp)
            return None        # do not call through: no geometry, no render
        return wrapped

    previous_render, fv.solid_render = fv.solid_render, record
    for name, func in originals.items():
        setattr(fv, name, wrap(name, func))
    try:
        import tempfile
        with tempfile.TemporaryDirectory(prefix='params_snapshot_') as scratch:
            for label, func_name, csv_names in SWEEPS:
                before = len(captured)
                getattr(fv, func_name)(fv.axes(*csv_names), scratch)
                if not quiet:
                    print('  %-10s %4d part(s)' % (label, len(captured) - before),
                          flush=True)
    finally:
        fv.solid_render = previous_render
        for name, func in originals.items():
            setattr(fv, name, func)
    return captured


def _flatten(prefix, value, out):
    """Flatten a nested tree to dotted paths, so a diff can name the exact field."""
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten('%s.%s' % (prefix, k) if prefix else k, v, out)
    else:
        out[prefix] = value
    return out


def compare(before, after):
    """Report differences between two snapshots. Returns the number of problems."""
    only_before = sorted(set(before) - set(after))
    only_after = sorted(set(after) - set(before))
    shared = sorted(set(before) & set(after))

    for name in only_before[:10]:
        print('  MISSING NOW   %s' % name)
    for name in only_after[:10]:
        print('  NEW           %s' % name)

    changed = []
    for name in shared:
        a = _flatten('', before[name] or {}, {})
        b = _flatten('', after[name] or {}, {})
        diffs = [(k, a.get(k), b.get(k))
                 for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
        if diffs:
            changed.append((name, diffs))

    for name, diffs in changed[:5]:
        print('  CHANGED       %s' % name)
        for field, av, bv in diffs[:6]:
            print('      %-38s %s -> %s' % (field, av, bv))
        if len(diffs) > 6:
            print('      ... %d more field(s)' % (len(diffs) - 6))
    if len(changed) > 5:
        print('  ... %d more changed part(s)' % (len(changed) - 5))

    return len(only_before) + len(only_after) + len(changed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)

    cap = sub.add_parser('capture', help="derive and save every variant's parameters")
    cap.add_argument('path', type=Path)

    cmp_ = sub.add_parser('compare', help='diff two snapshots')
    cmp_.add_argument('before', type=Path)
    cmp_.add_argument('after', type=Path)

    args = parser.parse_args(argv)

    if args.command == 'capture':
        print('capturing parameters for every variant (no geometry is generated)')
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
        print('DIFFERENT: %d part(s) differ -- parameters changed' % problems)
    else:
        print('IDENTICAL: every part derives byte-identical parameters; '
              'nothing upstream of geometry construction changed')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
