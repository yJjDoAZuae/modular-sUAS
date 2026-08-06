"""Render every GUI driver `.scad` and report failures, warnings, and empty output.

The drivers -- `fuselage_corner.scad`, `fuselage_bulkhead.scad`, `nose_cowl.scad` and
the rest -- set concrete parameter values and call one geometry module each. They are
the interactive path: how a person opens a part in OpenSCAD to look at it and adjust it.

**No other verification tool touches them.** `scad_snapshot.py` and
`verify_sweep_change.py` drive the Python sweep; `verify_scad_change.py` re-renders
generated `.stl.scad` files. All three reach the geometry modules through the sweep's
call path only, so a change to a module signature can be certified geometry-preserving
while leaving every driver broken.

Warnings are treated as failures, and that is the point rather than strictness. A bare
identifier with no matching variable evaluates in OpenSCAD to `undef` with a *warning*,
not an error -- so a driver that was missed during a signature change still renders, and
still produces a shape, just the wrong one. "Did it exit zero" would pass it. The
warning is the only signal.

Usage, from the repository root:

    uv run python src/Fuselage/tools/verify_drivers.py [--scad-dir DIR] [--keep DIR]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesh_stats  # noqa: E402

# OpenSCAD prints these on stderr while still exiting zero. The undef case is the one
# this tool exists for; the others are worth surfacing for the same reason.
WARNING_RE = re.compile(r'^(WARNING|ERROR|TRACE):', re.MULTILINE)

DEFAULT_SCAD_DIR = Path(__file__).resolve().parent.parent / 'scad'


def find_drivers(scad_dir: Path) -> list[Path]:
    """Driver files: `.scad` with no module definitions of their own.

    Libraries define modules; drivers call one. `fuselage_geometry.scad` also matches --
    it is a pure aggregator of includes -- and is reported separately as producing no
    geometry rather than as a failure.
    """
    drivers = []
    for path in sorted(scad_dir.glob('*.scad')):
        text = path.read_text(encoding='utf-8', errors='replace')
        if not re.search(r'^\s*module\s+\w+\s*\(', text, re.MULTILINE):
            drivers.append(path)
    return drivers


def render(job):
    scad, out_stl, binary = job
    done = subprocess.run([binary, '-o', str(out_stl), str(scad)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr = done.stderr.decode('utf-8', 'replace')
    return scad, out_stl, done.returncode, stderr


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--scad-dir', type=Path, default=DEFAULT_SCAD_DIR)
    parser.add_argument('--keep', type=Path, default=None,
                        help='keep the rendered STLs here instead of a temp directory')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args(argv)

    root = os.environ.get('OPENSCADPATH')
    if not root:
        raise SystemExit('OPENSCADPATH is not set; it must point at the OpenSCAD '
                         'install directory')
    binary = os.path.join(root, 'openscad')

    drivers = find_drivers(args.scad_dir)
    if not drivers:
        print(f'no driver .scad files under {args.scad_dir}')
        return 1
    print(f'rendering {len(drivers)} driver(s) from {args.scad_dir}\n')

    def run(out_dir: Path) -> int:
        jobs = [(d, out_dir / (d.stem + '.stl'), binary) for d in drivers]
        failures, warned, empty = [], [], []

        with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
            results = list(pool.map(render, jobs))

        for scad, out_stl, code, stderr in sorted(results, key=lambda r: r[0].name):
            notes = WARNING_RE.findall(stderr)

            # An aggregator of includes has no top-level geometry, and OpenSCAD exits
            # non-zero on empty output rather than writing an empty file. That is not a
            # failure of the file; it is a file that was never a driver.
            #
            # The `not notes` guard is load-bearing. A *broken* driver also produces
            # empty output -- a failed import or an undef dimension leaves nothing to
            # render -- and without this check it would be waved through as an
            # aggregator. That is how nose_cowl.scad and tail_cowl.scad, which cannot
            # find their OML mesh, briefly reported clean.
            if code and not notes and 'top level object is empty' in stderr.lower():
                print(f'  no geom  {scad.name}  (aggregator, not a driver)')
                empty.append(scad.name)
                continue

            if code:
                print(f'  FAILED   {scad.name}  (exit {code})')
                first = next((ln for ln in stderr.splitlines() if ln.strip()), '')
                print(f'           {first[:100]}')
                failures.append(scad.name)
                continue

            triangles = 0
            if out_stl.is_file():
                try:
                    triangles = mesh_stats.mesh_stats(out_stl)['triangles']
                except (mesh_stats.TruncatedMesh, ValueError, OSError):
                    triangles = 0

            if notes:
                print(f'  WARNED   {scad.name}  ({triangles:,} tris)')
                flagged = [ln for ln in stderr.splitlines() if WARNING_RE.match(ln)]
                for line in flagged[:3]:
                    print(f'           {line.strip()[:100]}')
                if len(flagged) > 3:
                    print(f'           ... {len(flagged) - 3} more')
                warned.append(scad.name)
            elif triangles == 0:
                # An aggregator of includes legitimately produces nothing.
                print(f'  no geom  {scad.name}  (aggregator, not a driver)')
                empty.append(scad.name)
            else:
                print(f'  OK       {scad.name}  ({triangles:,} tris)')

        print('-' * 68)
        bad = len(failures) + len(warned)
        if bad:
            print(f'{len(failures)} failed, {len(warned)} rendered with warnings')
            print('A warning here usually means an identifier resolved to undef -- the '
                  'driver still produced a shape, but not the right one.')
        else:
            print(f'ALL DRIVERS OK  ({len(drivers) - len(empty)} rendered, '
                  f'{len(empty)} aggregator(s) skipped)')
        return 1 if bad else 0

    if args.keep:
        args.keep.mkdir(parents=True, exist_ok=True)
        return run(args.keep)
    with tempfile.TemporaryDirectory(prefix='verify_drivers_') as tmp:
        return run(Path(tmp))


if __name__ == '__main__':
    raise SystemExit(main())
