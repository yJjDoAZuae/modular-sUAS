"""Prove a change spanning Python *and* SCAD altered no geometry, end to end.

The third of the verification tools, for the case the other two cannot reach.

- `scad_snapshot.py` compares generated `.scad` text. Blind to `.scad` library files,
  and reports DIFF by construction whenever a module signature changes.
- `verify_scad_change.py` re-renders the `.stl.scad` files already in the output tree.
  Those pin the *old* call signature, so it stops working the moment a signature moves.
- **This tool** runs the real sweep -- Python, solid2, OpenSCAD -- for a sample of
  combinations and compares the resulting STLs against a reference tree by measured
  geometry. Signatures and generated text are free to change; the solid must not.

That makes it the only check that means anything for a parameter-grouping refactor,
where both languages change together.

It is slower than the other two by a wide margin: every sampled part is a full CGAL
render. Sample deliberately rather than raising --per-kind and waiting.

Usage, from the repository root:

    uv run python src/Fuselage/tools/verify_sweep_change.py <reference_dir> [options]

    --per-kind N   parts to check per part kind (default 2)
    --workers N    concurrent OpenSCAD renders
    --scratch DIR  where to build the sample (default: a temp directory)
    --tol FLOAT    volume tolerance, RELATIVE to each part's own volume (default 1e-6)
    --distance-samples N   also measure sampled surface distance (0 = off, ~30 s/part)
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fuselage_variants as fv  # noqa: E402
import mesh_stats  # noqa: E402
import surface_distance  # noqa: E402

# Sweep name -> (driver function, axis CSVs). Mirrors main(); a new sweep must be added
# here or it silently escapes verification.
SWEEPS = (
    ('corner', 'run_corner_parametric_sweep',
     ('panel_variants.csv', 'bulkhead_size_variants.csv', 'corner_size_variants.csv')),
    ('bulkhead', 'run_bulkhead_parametric_sweep',
     ('panel_variants.csv', 'bulkhead_type_variants.csv', 'bulkhead_size_variants.csv')),
    ('boom_bulkhead', 'run_boom_bulkhead_parametric_sweep',
     ('panel_variants.csv', 'bulkhead_size_variants.csv',
      'boom_bulkhead_type_variants.csv')),
    ('nose', 'run_nose_parametric_sweep',
     ('nose_size_variants.csv', 'nose_type_variants.csv')),
    ('tail', 'run_tail_parametric_sweep',
     ('nose_size_variants.csv', 'tail_type_variants.csv')),
)


def sample_names(reference: Path, per_kind: int) -> set[str]:
    """STL basenames to check, spread across each kind's range.

    Taken from the reference tree rather than from the sweep, so the set is stable
    across a refactor even as the code that produces them changes.
    """
    wanted: set[str] = set()
    for kind, _driver, _axes in SWEEPS:
        matches = sorted(
            p.name for p in reference.rglob('*.stl')
            if kind in p.name
            and not p.name.endswith('.partial.stl')
            and not (kind == 'bulkhead' and 'boom_bulkhead' in p.name)
        )
        if matches:
            step = max(1, len(matches) // per_kind)
            wanted.update(matches[::step][:per_kind])
    return wanted


def build_sample(scratch: Path, wanted: set[str], workers: int) -> None:
    """Run the real sweeps, rendering only the sampled parts.

    solid_render is wrapped rather than replaced: the wrapper decides whether a part is
    in the sample and defers to the real implementation when it is, so everything under
    test -- parameter derivation, the solid2 call, the generated .scad, the OpenSCAD
    invocation -- is the code that will actually run.
    """
    real_render = fv.solid_render
    rendered = {'count': 0}

    def sampling_render(scad_obj, output_dir, filename):
        stl_name = Path(filename).with_suffix('.stl').name
        if stl_name not in wanted:
            return (filename, filename, filename)
        rendered['count'] += 1
        return real_render(scad_obj, output_dir, filename)

    fv.solid_render = sampling_render
    try:
        with fv.sweep_session(workers=workers, resume=False, previews=False):
            for _kind, driver, axis_names in SWEEPS:
                getattr(fv, driver)(fv.axes(*axis_names), str(scratch))
    finally:
        fv.solid_render = real_render
    print(f'rendered {rendered["count"]} sampled part(s)\n')


def compare(reference: Path, scratch: Path, wanted: set[str], tol: float,
            samples: int = 0) -> int:
    """Compare the sample against the reference by measured geometry.

    Two tiers, per OQ-ARCH-16. The cheap criteria in `mesh_stats.same_geometry` screen;
    the sampled surface distance adjudicates when `samples` is non-zero. Volume and
    bounding box can both agree while a surface has moved, so a part that passes the
    cheap tier has been screened rather than cleared -- the distance is what turns that
    into a measurement in millimeters. It is off by default because it costs roughly half
    a minute per part at 4,000 samples, against well under a second for the cheap tier.
    """
    by_name = {p.name: p for p in reference.rglob('*.stl')}
    mismatches, missing = [], []

    for name in sorted(wanted):
        produced = next((p for p in scratch.rglob(name)), None)
        if produced is None:
            missing.append(name)
            print(f'  GONE  {name[:64]}')
            continue
        try:
            a = mesh_stats.mesh_stats(by_name[name])
            b = mesh_stats.mesh_stats(produced)
        except (mesh_stats.TruncatedMesh, ValueError, OSError) as exc:
            mismatches.append((name, f'unreadable: {exc}'))
            continue
        u = mesh_stats.u_of_name(name)
        cheap_ok = mesh_stats.same_geometry(a, b, tol, u)
        detail = '' if cheap_ok else mesh_stats.describe_difference(a, b)

        if samples:
            d = surface_distance.surface_distance(by_name[name], produced, samples)
            far = not surface_distance.within(d, u)
            note = f"surface max {d['max']:.6f} mm vs {surface_distance.surface_tol(u):.6f}"
            detail = f'{detail}; {note}' if detail else note
            if far and cheap_ok:
                # The case the cheap tier cannot see, and the reason this tier exists.
                detail += ' -- volume and bbox agree but the surface moved'
            cheap_ok = cheap_ok and not far

        if cheap_ok:
            print(f'  OK    {name[:64]}' + (f'   [{detail}]' if samples else ''))
        else:
            print(f'  DIFF  {name[:64]}')
            mismatches.append((name, detail))

    print('-' * 72)
    for name, why in mismatches:
        print(f'  DIFFERS  {name}\n           {why}')
    for name in missing:
        print(f'  NOT PRODUCED  {name}')

    if mismatches or missing:
        print('GEOMETRY CHANGED -- the refactor is not behaviour-preserving')
        return 1
    print(f'IDENTICAL GEOMETRY across {len(wanted)} sampled part(s)')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('reference', type=Path, help='tree of known-good rendered parts')
    parser.add_argument('--per-kind', type=int, default=2)
    parser.add_argument('--workers', type=int, default=None)
    parser.add_argument('--scratch', type=Path, default=None)
    parser.add_argument('--distance-samples', type=int, default=0,
                        help='surface-distance sample points per part; 0 (default) skips '
                             'the distance tier, which costs ~30 s per part at 4000')
    parser.add_argument('--tol', type=float, default=mesh_stats.VOLUME_TOL,
                        help="volume tolerance, relative to the part's own volume")
    args = parser.parse_args(argv)

    if not args.reference.is_dir():
        parser.error(f'not a directory: {args.reference}')

    wanted = sample_names(args.reference, args.per_kind)
    if not wanted:
        print(f'no parts found under {args.reference}')
        return 1
    workers = args.workers or fv.default_render_workers()
    print(f'sampling {len(wanted)} part(s), {workers} worker(s)\n')

    def run(scratch: Path) -> int:
        build_sample(scratch, wanted, workers)
        return compare(args.reference, scratch, wanted, args.tol, args.distance_samples)

    if args.scratch:
        args.scratch.mkdir(parents=True, exist_ok=True)
        return run(args.scratch)
    with tempfile.TemporaryDirectory(prefix='verify_sweep_') as tmp:
        return run(Path(tmp))


if __name__ == '__main__':
    raise SystemExit(main())
