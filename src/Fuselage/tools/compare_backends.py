"""IP-FC-13: render the same variants with both engines and compare the solids.

The other three verification tools all answer "did *this* change alter the geometry" within
one toolchain. This one answers the migration's actual question: **does the FreeCAD port
produce the same part as the OpenSCAD original, across the swept space rather than at one
point.**

That distinction is not academic. IP-FC-10 verified the port on one part per kind, at
U=1, FX=1, and four defects survived it -- every one found later by widening coverage:

    IP-FC-46  a zero-extent tool nulled the whole cut chain on the no-panel variant
    IP-FC-47  three of five bulkhead types were built as a fourth, silently
    IP-FC-48  U and FX never reached the sheet, so every corner was built at FX=1
    IP-FC-49  the tiling fuse failed above U=2.5

Three of those produce a valid, single-solid, plausible-looking part. Only a comparison
against the authority catches them, and only if it covers more than one combination.

    uv run python src/Fuselage/tools/compare_backends.py --per-kind 4
    uv run python src/Fuselage/tools/compare_backends.py --all --workers 6

**Two tiers, per OQ-DES-B9.** The corner is exactly reproducible and held to `--tol`. Parts
carrying real fillets are allowed a stated deviation, because a FreeCAD fillet is a true
surface where OpenSCAD's is a tessellated approximation -- so agreement is bounded by mesh
resolution rather than by modelling error. Interface dimensions are strict in both tiers,
which is what the bounding-box check stands in for until IP-FC-36 enumerates them.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import freecad_render  # noqa: E402
import fuselage_variants as fv  # noqa: E402
import mesh_stats  # noqa: E402

# Only the kinds with a FreeCAD generator. Anything else falls back to OpenSCAD inside the
# sweep, and comparing OpenSCAD against OpenSCAD passes while proving nothing -- see
# `verify_used_freecad` below, which refuses to let that count.
SWEEPS = (
    ('corner', 'run_corner_parametric_sweep',
     ('panel_variants.csv', 'bulkhead_size_variants.csv', 'corner_size_variants.csv')),
    ('bulkhead', 'run_bulkhead_parametric_sweep',
     ('panel_variants.csv', 'bulkhead_type_variants.csv', 'bulkhead_size_variants.csv')),
)

# Volume agreement, as a fraction.
#
# **The floor is tessellation, not modelling, and it is computable.** Both sides are meshes.
# OpenSCAD renders with $fa=1, which caps a circle at 360 segments, and an inscribed regular
# n-gon under-measures its circle by 1 - (n/2pi)*sin(2pi/n):
#
#     n = 360   +0.005077%      <- the cap, and so the floor
#     n = 720   +0.001269%
#     n = 1440  +0.000317%
#
# So on a part with circular features the two engines *cannot* agree closer than about
# 0.005%, FreeCAD always reading larger because its mesh is the more accurate one -- the
# B-rep is exact and MeshPart's 1e-3 linear deviation puts the STL within +0.00024% of it
# (IP-FC-10). The measured corner deltas sit under that bound and scale with how much of the
# part is round: +0.00121% at U=1, +0.00222% at U=2.
#
# A tolerance tighter than the faceting floor does not detect modelling error, it detects
# OpenSCAD's circle approximation -- which is what the first run of this tool did, failing a
# corner at +0.00222%.
TOL_EXACT = 6.0e-5          # 0.006% -- the 360-segment floor, with margin
TOL_FILLETED = 1.0e-4       # 0.010% -- fillets add real surface-vs-facet error on top
BBOX_TOL = 5.0e-4           # mm, absolute -- interfaces must not move

FILLETED_KINDS = {'bulkhead'}


def kind_of(name: str) -> str:
    """Which sweep produced this part, from its filename."""
    if 'boom_bulkhead' in name:
        return 'boom_bulkhead'
    for kind, _driver, _axes in SWEEPS:
        if kind in name:
            return kind
    return 'other'


def wanted_parts(per_kind: int | None) -> dict[str, str]:
    """Part filename -> kind, for the variants to compare.

    Collected by running the sweeps with rendering stubbed out, so the selection comes from
    the real parameter derivation and validity checks rather than from a guess about what
    the space contains.
    """
    collected: dict[str, str] = {}

    def note(filename):
        stl = Path(filename).with_suffix('.stl').name
        collected[stl] = kind_of(stl)

    real_solid, real_freecad = fv.solid_render, fv.freecad_render
    fv.solid_render = lambda obj, d, f: (note(f), (f, f, f))[1]
    fv.freecad_render = lambda k, p, d, f, v=None: note(f)
    try:
        for _kind, driver, axis_names in SWEEPS:
            getattr(fv, driver)(fv.axes(*axis_names), '/nonexistent')
    finally:
        fv.solid_render, fv.freecad_render = real_solid, real_freecad

    if per_kind is None:
        return collected

    out: dict[str, str] = {}
    for kind, _driver, _axes in SWEEPS:
        names = sorted(n for n, k in collected.items() if k == kind)
        step = max(1, len(names) // per_kind)
        for n in names[::step][:per_kind]:
            out[n] = kind
    return out


def render(backend: str, out_dir: Path, wanted: set[str], workers: int) -> None:
    """Render exactly the wanted parts with `backend`, through the real sweep."""
    real_solid, real_freecad = fv.solid_render, fv.freecad_render
    count = {'n': 0}

    def gate(filename):
        if Path(filename).with_suffix('.stl').name not in wanted:
            return False
        count['n'] += 1
        return True

    def solid(obj, d, f):
        return real_solid(obj, d, f) if gate(f) else (f, f, f)

    def freecad(k, p, d, f, v=None):
        return real_freecad(k, p, d, f, v) if gate(f) else None

    fv.solid_render, fv.freecad_render = solid, freecad
    previous = fv.set_backend(backend)
    try:
        with fv.sweep_session(workers=workers, resume=False, previews=False):
            for _kind, driver, axis_names in SWEEPS:
                getattr(fv, driver)(fv.axes(*axis_names), str(out_dir))
    finally:
        fv.solid_render, fv.freecad_render = real_solid, real_freecad
        fv.set_backend(previous)
    print(f'  {backend}: rendered {count["n"]} part(s)', flush=True)


def used_freecad(stl: Path) -> bool:
    """Did the FreeCAD backend actually build this, or did it fall back?

    The backend writes its parameter table as `<part>.stl.json` beside the mesh; the
    OpenSCAD path writes `<part>.stl.scad`. Checked because a fallback is silent by design
    -- an unported kind, or an unported *variant* of a ported kind such as an interconnect
    bulkhead (IP-FC-47) -- and comparing OpenSCAD against OpenSCAD would otherwise report a
    clean pass for a part FreeCAD has never built.
    """
    return stl.with_suffix('.stl.json').exists()


def compare(a_dir: Path, b_dir: Path, wanted: dict[str, str], tol_exact: float,
            tol_filleted: float) -> int:
    a_by_name = {p.name: p for p in a_dir.rglob('*.stl') if not p.name.endswith('.partial.stl')}
    b_by_name = {p.name: p for p in b_dir.rglob('*.stl') if not p.name.endswith('.partial.stl')}

    rows, failures, skipped = [], [], []
    for name in sorted(wanted):
        kind = wanted[name]
        a, b = a_by_name.get(name), b_by_name.get(name)
        if a is None or b is None:
            failures.append((name, 'not produced by ' + ('openscad' if a is None else 'freecad')))
            continue
        if not used_freecad(b):
            skipped.append((name, kind))
            continue
        try:
            sa, sb = mesh_stats.mesh_stats(a), mesh_stats.mesh_stats(b)
        except (mesh_stats.TruncatedMesh, ValueError, OSError) as exc:
            failures.append((name, f'unreadable: {exc}'))
            continue

        rel = (sb['volume'] - sa['volume']) / sa['volume']
        bbox_off = max(abs(x - y) for x, y in zip(sa['bbox'], sb['bbox']))
        tol = tol_filleted if kind in FILLETED_KINDS else tol_exact
        ok = abs(rel) <= tol and bbox_off <= BBOX_TOL
        rows.append((name, kind, sa['volume'], sb['volume'], rel, bbox_off, ok))
        if not ok:
            why = []
            if abs(rel) > tol:
                why.append(f'volume {rel * 100:+.5f}% exceeds {tol * 100:.5f}%')
            if bbox_off > BBOX_TOL:
                why.append(f'bounding box moved {bbox_off:.6f} mm')
            failures.append((name, '; '.join(why)))

    print()
    print(f'  {"part":<52} {"openscad":>14} {"freecad":>14} {"delta":>11}  bbox')
    for name, _kind, va, vb, rel, bbox_off, ok in rows:
        print(f'  {name[:52]:<52} {va:>14.6f} {vb:>14.6f} {rel * 100:>+10.5f}% '
              f'{"ok" if bbox_off <= BBOX_TOL else f"{bbox_off:.6f}mm"}'
              f'{"" if ok else "   <-- FAIL"}')

    print('-' * 100)
    if skipped:
        print(f'  {len(skipped)} part(s) fell back to OpenSCAD and were NOT compared '
              f'(no FreeCAD generator for that variant):')
        for name, kind in skipped[:6]:
            print(f'      {name[:70]}')
        if len(skipped) > 6:
            print(f'      ... and {len(skipped) - 6} more')
    if rows:
        worst = max(rows, key=lambda r: abs(r[4]))
        print(f'  compared {len(rows)} part(s); worst |delta| {abs(worst[4]) * 100:.5f}% '
              f'on {worst[0][:52]}')
    for name, why in failures:
        print(f'  FAIL  {name}\n        {why}')

    if failures:
        print('\nBACKENDS DISAGREE')
        return 1
    if not rows:
        print('\nNOTHING COMPARED -- every sampled part fell back to OpenSCAD')
        return 1
    print('\nBACKENDS AGREE within tolerance')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--per-kind', type=int, default=3,
                       help='parts to compare per kind, spread across the range (default 3)')
    group.add_argument('--all', action='store_true',
                       help='compare every valid combination -- slow, the OpenSCAD half '
                            'dominates')
    parser.add_argument('--workers', type=int, default=None)
    parser.add_argument('--scratch', type=Path, default=None)
    parser.add_argument('--tol', type=float, default=TOL_EXACT,
                        help=f'volume tolerance for exactly-reproducible kinds '
                             f'(default {TOL_EXACT})')
    parser.add_argument('--tol-filleted', type=float, default=TOL_FILLETED,
                        help=f'volume tolerance for kinds carrying real fillets '
                             f'(default {TOL_FILLETED})')
    parser.add_argument('--keep', action='store_true', help='keep the rendered trees')
    args = parser.parse_args(argv)

    wanted = wanted_parts(None if args.all else args.per_kind)
    print(f'comparing {len(wanted)} part(s): '
          + ', '.join(f'{k}={sum(1 for v in wanted.values() if v == k)}'
                      for k, _d, _a in SWEEPS))

    scratch = args.scratch or Path(fv.OUTPUT_DIR).parent / 'compare_backends'
    scratch.mkdir(parents=True, exist_ok=True)
    a_dir, b_dir = scratch / 'openscad', scratch / 'freecad'
    for d in (a_dir, b_dir):
        shutil.rmtree(d, ignore_errors=True)

    names = set(wanted)
    render('openscad', a_dir, names, args.workers)
    render('freecad', b_dir, names, args.workers)

    code = compare(a_dir, b_dir, wanted, args.tol, args.tol_filleted)
    if not args.keep:
        shutil.rmtree(scratch, ignore_errors=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
