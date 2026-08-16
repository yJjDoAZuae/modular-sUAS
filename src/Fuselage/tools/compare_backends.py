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
    uv run python src/Fuselage/tools/compare_backends.py --all --kinds boom_bulkhead
    uv run python src/Fuselage/tools/compare_backends.py --all --build-only

**`--build-only` when the question is "what fails to build", not "do they agree".** Those are
different questions with wildly different costs, and running the expensive one to answer the
cheap one wastes hours. A full comparison renders the space twice; the OpenSCAD half measured
2.5 hours at ~38 s/part against the FreeCAD half's ~1.3 s/part, and it exists *only* to supply
reference volumes. It can produce no build failures of its own -- OpenSCAD is the authority, it
builds everything. So a run whose purpose is to enumerate unbuildable variants gets the whole
answer from the FreeCAD pass alone, in about a hundredth of the time.

**Sample first, then sweep the kind exhaustively.** A sample finds systematic errors, which is
most of them; it does not find the ones that need a particular corner of the space. IP-FC-50 was
a boom bulkhead wrong by +0.167% at exactly one of eight sampled variants and by 0.0006% at the
other seven -- had the sample missed it, nothing else in the toolchain would have.

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
import tempfile
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
    ('boom_bulkhead', 'run_boom_bulkhead_parametric_sweep',
     ('panel_variants.csv', 'boom_bulkhead_type_variants.csv',
      'bulkhead_size_variants.csv')),
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

# Ask `mesh_stats` for the box at full precision. Its default rounds to 4 decimal places --
# a 1e-4 grid, one fifth of BBOX_TOL -- and rounding two coordinates onto different grid
# points before subtracting them manufactures a difference that is not in either mesh. That
# is precisely what IP-FC-71 was: two bulkheads whose extents differ by 0.000497 mm, rounded
# to 0.000500 and then failed by 2e-15 mm on the comparison. Rounding is right for the
# `same_geometry` and display callers, which want a stable key; it is wrong under a subtraction.
BBOX_PLACES = 9

FILLETED_KINDS = {'bulkhead', 'boom_bulkhead'}


def kind_of(name: str) -> str:
    """Which sweep produced this part, from its filename.

    Longest kind name first, because the names nest: both sweeps write into a `bulkhead`
    directory and a boom bulkhead's file is `..._boom_bulkhead_offset_single.stl`, so a
    plain scan in table order would call every boom part a frame bulkhead -- and compare it
    at the frame bulkhead's tolerance against a part the frame sweep never produced.
    """
    for kind in sorted((k for k, _d, _a in SWEEPS), key=len, reverse=True):
        if kind in name:
            return kind
    return 'other'


def sweeps_for(kinds: set[str] | None):
    """The sweeps to run, optionally narrowed to some kinds.

    Exhaustive coverage of one kind is the useful thing to be able to ask for and `--all`
    could not express it: a newly ported kind wants every one of its variants compared, and
    paying for the two already covered at the same time is what makes that run unaffordable
    and so not run. IP-FC-12's boom bulkhead is 132 valid variants against the frame
    bulkhead's 148 and the corner's own space.
    """
    return tuple(s for s in SWEEPS if kinds is None or s[0] in kinds)


def wanted_parts(per_kind: int | None, kinds: set[str] | None = None) -> dict[str, str]:
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
        for _kind, driver, axis_names in sweeps_for(kinds):
            getattr(fv, driver)(fv.axes(*axis_names), '/nonexistent')
    finally:
        fv.solid_render, fv.freecad_render = real_solid, real_freecad

    if per_kind is None:
        return collected

    out: dict[str, str] = {}
    for kind, _driver, _axes in sweeps_for(kinds):
        names = sorted(n for n, k in collected.items() if k == kind)
        step = max(1, len(names) // per_kind)
        for n in names[::step][:per_kind]:
            out[n] = kind
    return out


def render(backend: str, out_dir: Path, wanted: set[str], workers: int,
           kinds: set[str] | None = None, resume: bool = False) -> list:
    """Render exactly the wanted parts with `backend`, through the real sweep.

    **A part that will not build is a result, not the end of the run.** This used to inherit
    the sweep's `fail_fast`, so the first unbuildable variant raised `RenderFailed` out of the
    driver and the comparison never ran -- 287 of 288 parts rendered and nothing was compared,
    because one of them was IP-FC-58. A check whose first failure hides every other failure
    behind it is worse than no check: it reports the defect you already knew about and stays
    silent about the ones you did not.

    So failures are collected and returned. The parts that did not build have no mesh, and
    `compare()` already reports a missing mesh as that part's own failure, which is where it
    belongs -- against the part, in the table, with everything else still measured.
    """
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
    failed = []
    try:
        with fv.sweep_session(workers=workers, resume=resume, previews=False,
                              fail_fast=False) as queue:
            for _kind, driver, axis_names in sweeps_for(kinds):
                getattr(fv, driver)(fv.axes(*axis_names), str(out_dir))
        failed = list(queue.failures)
    finally:
        fv.solid_render, fv.freecad_render = real_solid, real_freecad
        fv.set_backend(previous)
    # count['n'] counts parts *asked for*, which includes the ones refused for having no
    # FreeCAD generator -- they pass the gate and are turned away after it. Subtract both so
    # "rendered" means rendered.
    refused, broken = split_failures(failed)
    notes = ([f'{len(broken)} failed to build'] if broken else []) + \
            ([f'{len(refused)} not ported'] if refused else [])
    suffix = (', ' + ', '.join(notes)) if notes else ''
    print(f'  {backend}: rendered {count["n"] - len(broken) - len(refused)} part(s){suffix}',
          flush=True)
    return failed


def used_freecad(stl: Path) -> bool:
    """Did the FreeCAD backend actually build this, or did it fall back?

    The backend writes its parameter table as `<part>.stl.json` beside the mesh; the
    OpenSCAD path writes `<part>.stl.scad`. Checked because a fallback is silent by design
    -- an unported kind, or an unported *variant* of a ported kind such as an interconnect
    bulkhead (IP-FC-47) -- and comparing OpenSCAD against OpenSCAD would otherwise report a
    clean pass for a part FreeCAD has never built.
    """
    return stl.with_suffix('.stl.json').exists()


def split_failures(failures) -> tuple[set[str], list]:
    """Refusals (no FreeCAD generator) apart from renders that were tried and failed.

    `RenderQueue.failures` holds both, as `(job, exception)`. They must not be reported
    together: the first names porting work that is known to be outstanding, the second names a
    defect. Returns the refused part names as `.stl` names, and the genuine failures.
    """
    unported, broken = set(), []
    for job, exc in failures:
        if isinstance(exc, fv.UnportedPart):
            unported.add(Path(job[0]).with_suffix('.stl').name)
        else:
            broken.append((job, exc))
    return unported, broken


def report_builds(b_dir: Path, wanted: dict[str, str], unported: set[str]) -> int:
    """Which variants FreeCAD actually built, with no reference render and no comparison.

    The build question and the agreement question are separable, and only the second one needs
    the OpenSCAD side. Read off the tree rather than off the render queue's failure list: the
    queue records a command line and an exception, which names the part only incidentally, and
    it cannot see a part that FreeCAD "built" by silently falling back to OpenSCAD. Both of
    those are answered by what is on disk beside the mesh -- a `.stl.json` means FreeCAD built
    it, a `.stl.scad` means the fallback did, and no mesh at all means nothing did.
    """
    by_name = {p.name: p for p in b_dir.rglob('*.stl')
               if not p.name.endswith('.partial.stl')}

    missing, fell_back, built, refused = [], [], [], []
    for name in sorted(wanted):
        mesh = by_name.get(name)
        if name in unported:
            refused.append((name, wanted[name]))
        elif mesh is None:
            missing.append((name, wanted[name]))
        elif not used_freecad(mesh):
            fell_back.append((name, wanted[name]))
        else:
            built.append((name, wanted[name]))

    def by_kind(rows):
        return ', '.join('%s=%d' % (k, sum(1 for _n, rk in rows if rk == k))
                         for k, _d, _a in SWEEPS if any(rk == k for _n, rk in rows))

    print()
    print('  %-28s %4d   %s' % ('built by FreeCAD', len(built), by_kind(built)))
    print('  %-28s %4d   %s' % ('not ported (refused)', len(refused), by_kind(refused)))
    print('  %-28s %4d   %s' % ('fell back to OpenSCAD', len(fell_back), by_kind(fell_back)))
    print('  %-28s %4d   %s' % ('DID NOT BUILD', len(missing), by_kind(missing)))
    print('-' * 100)

    if refused:
        print('  %d variant(s) have no FreeCAD generator. They were NOT rendered with '
              'OpenSCAD under\n  the FreeCAD name -- nothing was written for them at all. '
              'This is outstanding porting\n  work, not a defect:' % len(refused))
        for name, _kind in refused[:6]:
            print('      %s' % name[:88])
        if len(refused) > 6:
            print('      ... and %d more' % (len(refused) - 6))
        print()

    if fell_back:
        print('  UNEXPECTED: these have an OpenSCAD definition in the FreeCAD tree, which the '
              'refusal\n  in solid_render should have made impossible:')
        for name, _kind in fell_back[:6]:
            print('      %s' % name[:88])
        print()

    if missing:
        print('  UNBUILDABLE -- FreeCAD has a generator for these and produced no mesh:')
        for name, _kind in missing:
            print('      %s' % name[:88])
        print('\n%d of %d PORTED PART(S) DO NOT BUILD'
              % (len(missing), len(built) + len(missing)))
        return 1

    print('EVERY PORTED PART BUILDS  (%d of %d variants; %d not ported yet. Agreement not '
          'checked -- this was a --build-only run)'
          % (len(built), len(wanted), len(refused)))
    return 0


def compare(a_dir: Path, b_dir: Path, wanted: dict[str, str], tol_exact: float,
            tol_filleted: float, unported: set[str] = frozenset()) -> int:
    a_by_name = {p.name: p for p in a_dir.rglob('*.stl') if not p.name.endswith('.partial.stl')}
    b_by_name = {p.name: p for p in b_dir.rglob('*.stl') if not p.name.endswith('.partial.stl')}

    rows, failures, skipped = [], [], []
    for name in sorted(wanted):
        kind = wanted[name]
        a, b = a_by_name.get(name), b_by_name.get(name)
        # Not ported is not a disagreement. FreeCAD was never asked to build these -- it has
        # no generator for them -- so there is nothing to compare and nothing is wrong. They
        # used to appear here as a fallback mesh that silently compared OpenSCAD against
        # itself and passed; now they are simply absent, which must not read as a failure.
        if name in unported:
            skipped.append((name, kind))
            continue
        if a is None or b is None:
            failures.append((name, 'not produced by ' + ('openscad' if a is None else 'freecad')))
            continue
        if not used_freecad(b):
            skipped.append((name, kind))
            continue
        try:
            sa = mesh_stats.mesh_stats(a, bbox_places=BBOX_PLACES)
            sb = mesh_stats.mesh_stats(b, bbox_places=BBOX_PLACES)
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
        print(f'  {len(skipped)} part(s) have no FreeCAD generator, were not produced, and so '
              f'were NOT compared (outstanding porting work, not a failure):')
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
    parser.add_argument('--scratch', type=Path, default=None,
                        help='where the two rendered trees go (default: a fixed directory '
                             'under the system temp dir, outside the repo)')
    parser.add_argument('--tol', type=float, default=TOL_EXACT,
                        help=f'volume tolerance for exactly-reproducible kinds '
                             f'(default {TOL_EXACT})')
    parser.add_argument('--tol-filleted', type=float, default=TOL_FILLETED,
                        help=f'volume tolerance for kinds carrying real fillets '
                             f'(default {TOL_FILLETED})')
    parser.add_argument('--reference', type=Path, default=None,
                        help='reuse an existing OpenSCAD tree as the reference instead of '
                             'rendering one. Rendered with --resume, so parts whose '
                             'definition still matches cost nothing and only stale or '
                             'missing ones are rebuilt')
    parser.add_argument('--build-only', action='store_true',
                        help='render only the FreeCAD side and report which variants fail to '
                             'build; skips the OpenSCAD reference render, which is the '
                             'expensive half and cannot fail')
    parser.add_argument('--keep', action='store_true', help='keep the rendered trees')
    parser.add_argument('--kinds', default=None,
                        help='comma-separated kinds to compare (default all): '
                             + ', '.join(k for k, _d, _a in SWEEPS))
    args = parser.parse_args(argv)

    kinds = None
    if args.kinds:
        kinds = {k.strip() for k in args.kinds.split(',') if k.strip()}
        unknown = kinds - {k for k, _d, _a in SWEEPS}
        if unknown:
            parser.error('no such kind: %s' % ', '.join(sorted(unknown)))

    wanted = wanted_parts(None if args.all else args.per_kind, kinds)
    print(f'{"building" if args.build_only else "comparing"} {len(wanted)} part(s): '
          + ', '.join(f'{k}={sum(1 for v in wanted.values() if v == k)}'
                      for k, _d, _a in sweeps_for(kinds)))

    # Outside the repo by default. This used to be `src/Fuselage/compare_backends`, which is
    # gitignored and so looked harmless -- until a crashed run left 2.6 GB of meshes in the
    # source tree, and until IP-FC-72, where an Explorer window left open on that tree put two
    # directories into Windows' delete-pending state and silently dropped 22 parts from a
    # comparison that still printed a verdict. Both are far less likely somewhere nobody
    # browses. A fixed name, not `mkdtemp`: `--resume` and `--reference` want to find the
    # previous run's tree, and the `freecad` half is wiped on the way in regardless.
    scratch = args.scratch or Path(tempfile.gettempdir()) / 'modular_suas_compare_backends'
    scratch.mkdir(parents=True, exist_ok=True)
    b_dir = scratch / 'freecad'
    shutil.rmtree(b_dir, ignore_errors=True)

    # A supplied reference is the caller's tree, not ours: never wiped going in, never deleted
    # coming out, and rendered with --resume so a part whose definition still matches byte for
    # byte costs nothing. That check is the same one --resume already trusts, which is what
    # makes reuse safe rather than merely fast -- a reference rendered before a geometry or
    # parameter change re-renders exactly the parts the change invalidated, and no others.
    a_dir = args.reference if args.reference else scratch / 'openscad'
    if args.reference is None:
        shutil.rmtree(a_dir, ignore_errors=True)
    elif not a_dir.is_dir():
        parser.error('--reference %s is not a directory' % a_dir)

    names = set(wanted)
    failures = []
    if not args.build_only:
        if args.reference:
            print(f'  reusing reference tree at {a_dir}', flush=True)
        failures += render('openscad', a_dir, names, args.workers, kinds,
                           resume=args.reference is not None)
    failures += render('freecad', b_dir, names, args.workers, kinds)

    unported, broken = split_failures(failures)
    if broken:
        print(f'\n  {len(broken)} part(s) could not be built and are reported as '
              f'failures below rather than ending the run', flush=True)
    if unported:
        print(f'  {len(unported)} part(s) have no FreeCAD generator and were refused rather '
              f'than rendered with OpenSCAD', flush=True)

    if args.build_only:
        code = report_builds(b_dir, wanted, unported)
    else:
        code = compare(a_dir, b_dir, wanted, args.tol, args.tol_filleted, unported)
    if not args.keep:
        # A supplied reference is never deleted. It usually sits *inside* the scratch tree --
        # that is the natural place for it, since it is what a previous run left there -- so
        # the ordinary "remove the scratch" cleanup would take hours of rendering with it.
        # Only what this run produced is removed in that case.
        if args.reference and args.reference.resolve() != scratch.resolve() \
                and args.reference.resolve().is_relative_to(scratch.resolve()):
            shutil.rmtree(b_dir, ignore_errors=True)
        elif not args.reference:
            shutil.rmtree(scratch, ignore_errors=True)
        else:
            shutil.rmtree(b_dir, ignore_errors=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
