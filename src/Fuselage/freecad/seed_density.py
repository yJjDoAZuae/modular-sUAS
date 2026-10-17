"""IP-WTM-36: is the nose's `U`-linear thinning the fit's axial seed being a fixed *count*?

**The observation this starts from.** The nose's finished wall thins strictly monotonically in `U` --
0.00115, 0.00310, 0.00376, 0.00504, 0.00829, 0.01403 mm over `U` = 0.5 to 4.0, a factor of 12.2
across a factor of 8 -- while the wall is an absolute 0.6 mm at every scale, so nothing in the
construction is supposed to scale that way (section 6.7). IP-WTM-44 then measured that the nose's
thinning is **not** a reference-surface effect: at `U` = 4.0 all 20 of its over-tolerance stations
read thin against both exteriors, the two worst readings agreeing to 0.00003 mm (section 6.8.2). So
the cause is in the fit or the cut, not in which exterior is measured.

**The candidate, and it is this project's recurring error.** `_seed` takes `SEED_MAX` = 6 stations
for *any* patch at least `SEED_LONG_MM` = 3 mm long, and that is a **count, not a spacing**. A nose
patch is 44 mm at `U` = 1 and 176 mm at `U` = 4, so the same six seeds are 8.8 mm apart and then
35 mm apart. `_refine` bisects from there and stops at the first subdivision inside `TAU`, so a
coarser start is accepted at a coarser resolution: pass 1's own worst wall is **0.0129 mm at
`U` = 1 and 0.0308 mm at `U` = 4**, both inside `TAU` = 0.05 and therefore both accepted. That is a
mechanism which would produce exactly a `U` trend in a quantity that should have none.

`FIT_ARC` and `CHECK_ARC` are **not** candidates, and the same logs rule them out: both are already
spacings with a count floor, so their resolution saturates once the floor stops binding -- the nose's
fit spacing is 0.399 mm at `U` = 1 and 1.002 mm at `U` = 3 and 4 alike -- while the thinning keeps
growing by 1.69x from `U` = 3 to 4. A cause that saturates cannot explain a trend that does not.

**Two measurements, and the second is the one that could refute it.**

1. **The trend.** Build the nose across `U` and report, per build, the patch length, the seeded and
   final station counts, the axial station spacing, pass 1's own worst wall and the finished wall's.
   If the seed is the mechanism, pass 1's worst should track the station spacing rather than `U`
   directly.
2. **The converse, at fixed `U`.** Re-build one `U` with `SEED_MAX` raised, so the seed spacing is
   restored without anything else changing. If the thinning is the seed, it should fall; if it does
   not move, the seed is not the mechanism however well it correlates. A correlate that explains the
   symptom is not the cause until the converse is tested.

`--seed-max` monkeypatches the module constant for the duration of one run and restores it after,
which is deliberate: nothing here should leave a changed constant behind for a later build in the
same process to inherit.

**Cost.** A `nose_cowl_shell` builds in 38 to 117 s, so the whole `U` sweep is minutes -- which is
why the nose is the right place to chase this and the tail (727 to 4 525 s) is not.

---

**IP-WTM-26's continuation: the floor underneath, and the other axis of the same question.** The
measurements above landed: `SEED_MAX` is the mechanism and raising it at fixed `U` = 4 takes the nose
from 0.01530 to 0.00733 mm -- passing -- then **saturates at about 0.00710 mm** at `SEED_MAX` = 24.
Seeding does not reach that floor, and what sets it is the question this driver was extended for.

**The candidate is the fit's resolution in the other direction**, and the exclusion recorded above
does not cover it. `FIT_ARC` was ruled out as a cause of the `U` *trend* because it saturates once
its count floor stops binding -- a cause that saturates cannot explain a trend that does not. **A
quantity that saturates is exactly the right shape for a floor**, which is the opposite claim, and
the arithmetic is suggestive: at `U` = 4 the nose fits at **1.002 mm around the section against a
0.6 mm wall**, so the surface's control rows are further apart than the wall is thick. A residual of
a few thousandths from that discretization would not be surprising.

So: hold `U` = 4 and `SEED_MAX` = 24, where the axial seed is measured to be no longer binding, and
move `FIT_ARC` alone. If the floor falls, the floor is circumferential fit resolution. If it does not
move, it is not -- and the converse matters as much, so a *coarser* `FIT_ARC` is run too: a mechanism
that is real should make the wall worse when the sampling is loosened, and one that is not will leave
it where it is in both directions.

`--fit-arc`, `--fit-min` and `--fit-max` override their constants the same way `--seed-max` does,
with the same `finally` restore. `FIT_MIN` and `FIT_MAX` are exposed because `FIT_ARC` alone does not
control the spacing: the count is clamped to `[FIT_MIN, FIT_MAX]`, which is why the nose's spacing is
0.399 mm at `U` = 1 (the floor binding, finer than asked) and 1.002 mm at `U` = 3 and 4 (the arc
binding). A run that asks for a spacing the clamp will not give is a run that measured nothing, so
the achieved spacing is now read back out of the build's own report rather than assumed.

Usage, one `--pass` per argument; `freecadcmd`'s exit code is unreliable, read the table::

    freecadcmd seed_density.py --pass --us=0.5,1.0,2.0,3.0,4.0
    freecadcmd seed_density.py --pass --us=4.0 --pass --seed-max=24
    freecadcmd seed_density.py --pass --us=4.0 --pass --seed-max=24 --pass --fit-arc=0.25
    freecadcmd seed_density.py --pass --us=4.0 --pass --seed-max=24 \
                               --pass --arcs=2.0,1.0,0.5,0.25
    freecadcmd seed_density.py --pass --us=4.0 --pass --seeds=6,24 --pass --taus=0.05,0.02
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))

import FreeCAD as App                                              # noqa: E402,N813
import Part                                                        # noqa: E402

import cowl_interior as ci                                         # noqa: E402
import cowl_tree                                                   # noqa: E402
import soak_cowl_shell as soak                                     # noqa: E402
from corner_common import is_entry_point                           # noqa: E402

BUILDERS = soak.BUILDERS
BASE_PARAMS = soak.BASE_PARAMS
with_u = soak.with_u


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


#: The constants this driver may override, by option name. Each is restored in a `finally`.
#:
#: **An explicit list, not a general `--const=NAME=VALUE`.** A driver that can set any module
#: constant can set one the measurement was not about, and the result would look like a
#: measurement either way. These four are the fit's resolution in its two directions -- `SEED_MAX`
#: axially, `FIT_ARC` with its two clamps circumferentially -- which is one question asked twice.
OVERRIDABLE = {'seed-max': ('SEED_MAX', int), 'fit-arc': ('FIT_ARC', float),
               'fit-min': ('FIT_MIN', int), 'fit-max': ('FIT_MAX', int),
               # **`CHECK_ARC` is the instrument, not the construction**, which is why it is here
               # last and matters most. `report['worst_wall']` -- the finished-wall figure every
               # row of this driver prints -- is `_finished_wall_gap` sampled at `n_check`, so a
               # floor in that figure could be the construction's or could be the resolution it is
               # read at. The acceptance gate was moved to 0.125 mm by IP-WTM-25 while this stayed
               # at 0.20, so the two are already known to be different samplings of the same wall.
               'check-arc': ('CHECK_ARC', float), 'check-min': ('CHECK_MIN', int)}

#: **`TAU` is deliberately not in `OVERRIDABLE`, and the reason is a trap worth naming.**
#: Setting `ci.TAU` does nothing, because both `cavity` and `shell_solid` declare `tau=TAU` as a
#: **default argument** -- bound once when the module is imported, never re-read. A `--tau` option
#: implemented the same way as the four above would print the value it meant to test and build at
#: 0.05 regardless: a silent null experiment that produces a confident wrong result rather than an
#: error. The four constants above are safe because each is read inside a function body at call
#: time (`check_samples` reads `CHECK_ARC`/`CHECK_MIN`/`CHECK_MAX`; `_seed` reads `SEED_MAX`), which
#: is also confirmed empirically -- the achieved spacings in those sweeps moved with the override.
#: `TAU` is therefore passed to `shell_solid` as an argument instead; see `one`'s `tau` parameter.
NOT_OVERRIDABLE = ('TAU',)


def one(kind, u, seed_max=None, overrides=None, out=None, save_dir=None, tau=None):
    """Build `kind` at `u`, optionally with a denser fit, and report what pass 1 did.

    `seed_max` is kept as its own argument for continuity with IP-WTM-36's recorded runs;
    `overrides` carries anything else from `OVERRIDABLE`, keyed by the constant's real name.

    **`save_dir` exists because `CHECK_ARC` is both the instrument and part of the control loop.**
    `n_check` is handed to `_refine`, where it is the resolution of pass 1's own convergence
    criterion and therefore decides where stations are inserted, *and* to `_finished_wall_gap`,
    where it is the resolution the finished wall is read at. Sweeping it moves the wall and the
    ruler together, so such a sweep cannot say whether a floor is in the construction or in the
    measurement. Separating them needs **one** wall, saved, and re-measured off disk at several
    spacings -- which is what this writes the BREP for, and it needs no further build.

    **Measured 2026-10-14, the confound is real in general and was inactive in the run that
    prompted this**: at `SEED_MAX` = 24 on a nose at `U` = 4, all four `CHECK_ARC` values reported
    26 seeded to 26 stations with pass 1's worst identical to five decimals, so bisection never
    subdivided and `n_check` reached `_refine` without changing anything. The sweep therefore moved
    only the ruler *there*. It would not be true of a configuration where pass 1 does subdivide, and
    nothing makes it true in general, so the save stays.

    **`tau` is an argument and not an override**, for the reason `NOT_OVERRIDABLE` records: the
    constant is captured in two default-argument bindings at import and setting it has no effect.
    `None` leaves `shell_solid`'s own default in place.
    """
    out = out if out is not None else sys.stdout
    overrides = dict(overrides or {})
    if seed_max is not None:
        overrides['SEED_MAX'] = int(seed_max)
    # **Every name checked against the module before anything is set.** A typo would otherwise
    # raise `AttributeError` from the capture below -- harmlessly, since nothing has changed yet,
    # but as a traceback rather than a sentence, and after `freecadcmd` has started. This is the
    # same lesson as `input_screen.py --check`: anything that can waste a run is checked before the
    # run, and the check costs nothing.
    unknown = sorted(n for n in overrides if not hasattr(ci, n))
    if unknown:
        raise SystemExit('cowl_interior has no constant(s) %s; overridable: %s'
                         % (', '.join(unknown),
                            ', '.join(sorted(c for c, _ in OVERRIDABLE.values()))))
    # **Captured before anything is set and restored in the `finally` below**, for the reason the
    # `--seed-max` note gives: a changed constant left behind would be inherited by any later build
    # in the same process, and the next run's figures would silently not be the run it printed.
    was = {name: getattr(ci, name) for name in overrides}
    for name, value in overrides.items():
        setattr(ci, name, value)
    started = time.time()
    report = {}
    row = {'kind': kind, 'u': float(u), 'seed_max': ci.SEED_MAX,
           'fit_arc': ci.FIT_ARC, 'fit_min': ci.FIT_MIN, 'fit_max': ci.FIT_MAX,
           'check_arc': ci.CHECK_ARC, 'check_min': ci.CHECK_MIN,
           'tau': float(tau) if tau is not None else ci.TAU,
           'overrides': {k: v for k, v in overrides.items()},
           'error': None, 'seconds': None, 'patches': None, 'worst_smooth': None,
           'worst_finished': None, 'stations': None}
    doc = None
    try:
        doc = App.newDocument('seed_density')
        tip = cowl_tree.emit(doc, None, with_u(BASE_PARAMS[kind], u), BUILDERS[kind])
        doc.recompute()
        if not tip.Shape.Solids:
            raise ValueError('the wall has no solids -- read the log for execute()\'s traceback')
        notches = Part.makeCompound([n.Shape for n in tip.Notches])
        mirrors = [App.Vector(*[float(v) for v in t.split(',')]) for t in tip.Mirrors]
        kwargs = {} if tau is None else {'tau': float(tau)}
        # **Timed separately, because this function builds the wall twice and the total is not a
        # build's cost.** `cowl_tree.emit` plus `doc.recompute()` runs the shell node's own
        # `execute()`, which calls `shell_solid` itself; this second call is here only because the
        # node does not expose a `report`, and `report` is the whole point of this driver. Found
        # 2026-10-14 when a `tail_shell` at `U` = 0.5 reported 1 464 s against the 2026-10-06
        # soak's 727 s for the identical configuration -- a factor of 2.01, and the nose at `U` = 4
        # reported 226 s against 117 s, a factor of 1.93. **Every `seconds` figure this driver
        # printed before that date is two builds**, so IP-WTM-36's recorded build times are too;
        # its conclusions are ratios and wall figures and are unaffected.
        row['emit_s'] = time.time() - started
        shell_at = time.time()
        wall = ci.shell_solid(tip.Base.Shape, tip.Body.Shape, notches, float(tip.Inset),
                              tip.Overhang, mirrors, report=report, **kwargs)
        row['shell_s'] = time.time() - shell_at
        if save_dir:
            if not os.path.isdir(save_dir):
                os.makedirs(save_dir)
            # Named by every constant that was overridden, so two walls from different runs cannot
            # be confused for each other on disk -- the whole point of saving one is to re-measure
            # it, and re-measuring the wrong one would answer a question nobody asked.
            stem = '%s_U%g_seed%d_arc%g_chk%g' % (kind, float(u), ci.SEED_MAX, ci.FIT_ARC,
                                                  ci.CHECK_ARC)
            row['brep'] = os.path.join(save_dir, stem + '.brep')
            wall.exportBrep(row['brep'])
            out.write('    saved %s\n' % row['brep'])
            out.flush()
    except Exception as exc:                                       # noqa: BLE001 - a result
        row['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
    finally:
        for name, value in was.items():
            setattr(ci, name, value)
        if doc is not None:
            App.closeDocument(doc.Name)
    patches = report.get('smooth_patches') or []
    row.update(seconds=time.time() - started, patches=patches,
               stations=report.get('stations'),
               worst_finished=report.get('worst_wall'),
               worst_smooth=max((p['worst'] for p in patches), default=None),
               # **The spacing the build achieved, not the one asked for.** The point count is
               # clamped to `[FIT_MIN, FIT_MAX]`, so a `FIT_ARC` finer than the clamp allows gives
               # the clamp's spacing instead and a run that assumed otherwise measured nothing.
               fit_points=report.get('fit_points'),
               fit_spacing_mm=report.get('fit_spacing_mm'),
               check_spacing_mm=report.get('check_spacing_mm'))
    if patches:
        longest = max(patches, key=lambda p: p['p_hi'] - p['p_lo'])
        length = longest['p_hi'] - longest['p_lo']
        spacing = length / float(max(1, longest['stations'] - 1))
        row.update(patch_mm=length, seeded=longest['seeded'],
                   patch_stations=longest['stations'], station_mm=spacing)
    out.write('  %-16s U=%-5s seed=%-3s arc=%-5s chk=%-5s tau=%-5s %s\n'
              % (kind, u, row['seed_max'], row['fit_arc'], row['check_arc'], row['tau'],
                 'ERROR ' + row['error'] if row['error'] else
                 'patch %7.2f mm  %2d seeded -> %2d stations  %6.2f mm apart  '
                 'fit %4s pts %6.3f mm  pass1 %7.5f  finished %7.5f  %4.0f s (2 builds)'
                 % (row.get('patch_mm', float('nan')), row.get('seeded', 0),
                    row.get('patch_stations', 0), row.get('station_mm', float('nan')),
                    row['fit_points'] if row['fit_points'] is not None else '?',
                    row['fit_spacing_mm'] if row['fit_spacing_mm'] is not None
                    else float('nan'),
                    row['worst_smooth'] or float('nan'),
                    row['worst_finished'] or float('nan'), row['seconds'])))
    out.flush()
    return row


def main():
    kind = _opt('kind', 'nose_cowl_shell')
    us = [float(v) for v in _opt('us', '0.5,1.0,2.0,3.0,4.0').split(',')]
    seed_max = _opt('seed-max')
    # **`--arcs` sweeps `FIT_ARC` at a fixed `U`**, which is IP-WTM-26's question: the axial seed is
    # held where IP-WTM-36 measured it to stop binding, and the circumferential sampling is the only
    # thing that moves. Both directions, because a mechanism that is real should also make the wall
    # worse when the sampling is loosened.
    arcs = [float(v) for v in _opt('arcs', '').split(',') if v] or [None]
    # **`--checks` sweeps the instrument's own resolution**, which is a different question from
    # `--arcs` and has to be asked separately: if the finished-wall figure moves with `CHECK_ARC`
    # then the floor is in how the wall is read, not in how it is built.
    checks = [float(v) for v in _opt('checks', '').split(',') if v] or [None]
    # **`--taus` composes with `--seed-max`**, which is the question IP-WTM-26 needs: the seeding
    # lever saturates near 0.0070 mm on a nose at `U` = 4, and IP-WTM-27 measured `TAU` = 0.02
    # reaching 0.00378 mm at *default* seeding -- below that saturation point. Two levers whose
    # saturations differ are not hitting one floor, so whether they compose has to be built.
    taus = [float(v) for v in _opt('taus', '').split(',') if v] or [None]
    overrides = {}
    for opt_name, (const, cast) in OVERRIDABLE.items():
        if opt_name == 'seed-max':
            continue
        raw = _opt(opt_name)
        if raw is not None:
            overrides[const] = cast(raw)
    print('seed_density %s, SEED_MAX=%s (module default %d), SEED_LONG_MM=%.1f, TAU=%.3f, '
          'FIT_ARC=%.3f clamped to [%d, %d], CHECK_ARC=%.3f'
          % (kind, seed_max or 'default', ci.SEED_MAX, ci.SEED_LONG_MM, ci.TAU,
             ci.FIT_ARC, ci.FIT_MIN, ci.FIT_MAX, ci.CHECK_ARC), flush=True)
    seeds = [int(v) for v in _opt('seeds', '').split(',') if v] or [seed_max]
    rows = []
    for u in us:
        for seed in seeds:
            for arc in arcs:
                for check in checks:
                    for tau in taus:
                        per_run = dict(overrides)
                        if arc is not None:
                            per_run['FIT_ARC'] = arc
                        if check is not None:
                            per_run['CHECK_ARC'] = check
                        rows.append(one(kind, u, seed, per_run, save_dir=_opt('save'), tau=tau))
    print('SEED_DENSITY ' + json.dumps({'kind': kind, 'seeds': seeds, 'arcs': arcs,
                                        'checks': checks, 'taus': taus,
                                        'overrides': overrides, 'rows': rows},
                                       default=str), flush=True)
    return 0


if is_entry_point(__name__):
    sys.exit(main())
