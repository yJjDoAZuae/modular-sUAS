"""Did the real station set carry a near-duplicate pair, and does the floor remove it? Measured.

**The question this closes.** `cowl_interior_surface.md` §4.4 measures that the interior fit
*amplifies* a one-row displacement when a near-duplicate station pair sits beside the displaced
row, by 1 / the pair's gap, and that a 0.0015 mm pair reproduces OQ-DES-CW26's 0.408 mm per mm to
2 %. What that measurement could not say is whether a real build's station set ever contains such a
pair, because it was taken on a synthetic uniform mesh and no saved artifact holds a real build's
converged station list.

**It does not need the converged list.** The pair gets in at the *seed*, not during refinement:
`cavity` unions the uniform seed with the notch edges, and §4.1 records that `MIN_INTERVAL` is
enforced against subdivision and never against that union, which is how two individually legitimate
stations land arbitrarily close. `_refine` only ever inserts the exact midpoint of two adjacent
rows, so it cannot create a pair tighter than half the tightest one it starts with. So the seed
union bounds the whole question, and the seed union costs a cowl tree -- no cavity, no fit, no
boolean.

**What this prints.** For one kind at one `U`, the seed stations, the notch edges, their union, the
tightest gaps in it, and what `_thin_stations(zs, station_floor(t))` keeps. The last is the fix
IP-FC-144 landed, so the before-and-after is the same run rather than two.

Run it as::

    freecadcmd station_gaps.py --pass --kind=tail_shell --pass --u=3.0
    freecadcmd station_gaps.py --pass --kind=nose_cowl_shell --pass --u=1.0

`freecadcmd`'s exit code is unreliable, so read the printed table and the JSON. One `--pass` per
argument.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App                                                    # noqa: E402

import cowl_interior as ci                                               # noqa: E402
import cowl_tree                                                        # noqa: E402
from corner_common import is_entry_point                                 # noqa: E402
from wall_measure.fit_response import gaps, sub_floor                    # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'station_gaps')

#: The un-shelled builders. Building the *shell* would run `cavity` and cost the hour this script
#: exists to avoid; the tree up to `pieces()` carries the body and the notch tools, which is
#: everything the station set is derived from.
BUILDERS = {'tail_shell': cowl_tree.tail_cowl,
            'nose_cowl_shell': cowl_tree.nose_cowl}

PARAMS = {'tail_shell': cowl_tree.PARAMS_TAIL_SHELL,
          'nose_cowl_shell': cowl_tree.PARAMS_NOSE_COWL_SHELL}

#: How many of the tightest gaps to print.
SHOW = 8


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def with_u(params, u):
    """`params` with its `U` row set, the way `soak_cowl_shell.with_u` does it."""
    out, found = [], False
    for alias, value in params:
        if alias == 'U':
            out.append((alias, repr(float(u))))
            found = True
        else:
            out.append((alias, value))
    if not found:
        raise ValueError('%r has no U row' % (params,))
    return out


def with_case(params, case):
    """`params` with a design-input `case`'s `U` and row moves applied.

    **This is what makes the pair population affordable to screen at all.** The two-input
    interaction axis of `cowl.md` OQ-DES-CW26 alternative 1 is 242 pairs on the tail, and screening
    it by building and densely scanning each wall was priced at 114 to 175 hours -- five to seven
    days -- of which the scan is the larger part and searches for a signature nobody can yet
    define. The station set is derived from the cowl tree alone, so screening every pair for its
    station configuration costs the tree.

    **Measured, now that it has been run rather than estimated: 48.5 s a case and 3.27 hours for
    all 243**, min 30.2 and max 77.1 (2026-10-26, `tail_shell` at `U` = 3.0). The 34 s this
    docstring quoted was not wrong about a case -- it is what a case costs on a fresh process, and
    what the 24-case single-row family averaged. The gap was a leaked document per case, now fixed
    in `run`; see the note there for the measurement that found it. On the fix the whole 243 should
    cost about **2.2 hours**, and that figure is a prediction until someone re-runs it.

    What it covers and what it does not, stated rather than implied: it measures each pair's
    station spacing, which is the precondition §4.4's amplification needs, and it does **not**
    measure whether the wall severs. The fit is now known not to produce the severance on its own,
    so a clean station set is not proof of a sound wall. This is a coverage screen for one axis,
    and it is the cheap half of the question.
    """
    from wall_measure import inputs
    return inputs.apply_case(with_u(params, case.u), case)


def run(kind, u, out_dir, case=None):
    doc = App.newDocument('station_gaps')
    try:
        return _run(doc, kind, u, out_dir, case)
    finally:
        # **One document a case, closed whether the case worked or not.** Measured on the
        # 2026-10-26 pair screen, which did not close them: the per-case time drifted 32.6 s to
        # 72.3 s over 243 cases, correlating with position in the run at r = 0.980, and the
        # converse holds -- a row appearing only in the slow late pairs cost 31.4 s when run early
        # in the 24-case family. So it is the accumulated documents and not the configuration. The
        # run cost 3.27 hours instead of about 2.2, and a longer family would be worse than
        # linear. The family loop reports a failure and continues, so an abandoned case would leak
        # one too.
        App.closeDocument(doc.Name)


def _run(doc, kind, u, out_dir, case=None):
    started = time.time()
    rows = with_u(PARAMS[kind], u) if case is None else with_case(PARAMS[kind], case)
    cowl_tree.emit(doc, None, rows, BUILDERS[kind])
    doc.recompute()
    body, tools, _mirrors, _cell_cut = cowl_tree.pieces(doc)
    body_shape = body.Shape
    notches = notch_compound(tools)
    built_s = time.time() - started

    # `Inset` is what `_shell` sets from the sheet, and `cavity` is handed it as `t`.
    t = float(doc.getObject('Params').get('cowl_n_perimeters')) * \
        float(doc.getObject('Params').get('extrusion_width'))

    z_lo, z_hi = ci.z_extent(body_shape)
    notch_edges = ci.feature_stations(notches, z_lo, z_hi)
    body_features = ci.feature_stations(body_shape, z_lo, z_hi)
    patches = ci._patches(z_lo, z_hi, body_features)

    print('')
    print('%s at U = %g: the station set the fit is seeded with.' % (kind, u))
    print('  tree built in %.1f s, no cavity' % built_s)
    print('  z extent %.4f to %.4f mm, t = %.3f mm, station floor %.3f mm'
          % (z_lo, z_hi, t, ci.station_floor(t)))
    print('  %d notch edge(s), %d body crease(s), %d patch(es)'
          % (len(notch_edges), len(body_features), len(patches)))

    records = []
    for index, (p_lo, p_hi) in enumerate(patches):
        seed = ci._seed(p_lo, p_hi, p_lo <= z_lo, p_hi >= z_hi)
        edges = [e for e in notch_edges if p_lo < e < p_hi]
        union = sorted(set(seed) | set(edges))
        kept = ci._thin_stations(union, ci.station_floor(t))
        tight = gaps(union)
        print('')
        print('  patch %d, z %.4f to %.4f' % (index, p_lo, p_hi))
        print('    %d seed + %d notch edge(s) -> %d in the union -> %d on the floor'
              % (len(seed), len(edges), len(union), len(kept)))
        print('    tightest gaps in the union:')
        for gap, lo, hi in tight[:SHOW]:
            flag = '  UNDER THE FLOOR' if gap < ci.station_floor(t) else ''
            print('      %12.7f mm   between %.7f and %.7f%s' % (gap, lo, hi, flag))
        under = sub_floor(union, ci.station_floor(t))
        print('    %d gap(s) under the %.3f mm floor; tightest surviving gap %.7f mm'
              % (len(under), ci.station_floor(t), gaps(kept)[0][0] if len(kept) > 1 else 0.0))
        records.append({
            'patch': index, 'z_lo': p_lo, 'z_hi': p_hi,
            'seed': len(seed), 'notch_edges': len(edges),
            'union': len(union), 'kept': len(kept),
            'tightest_union_mm': tight[0][0] if tight else None,
            'under_floor': len(under),
            'tightest_kept_mm': gaps(kept)[0][0] if len(kept) > 1 else None,
            'union_stations': list(union),
            'kept_stations': list(kept),
        })

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    # A case's own name in the file, so a pair screen cannot overwrite the baseline's record --
    # the same separation `inputs._SCREEN_NAME` keeps between the screen and the `U` corpus.
    stem = os.path.join(out_dir, '%s_U%g%s'
                        % (kind, u, '' if case is None else '_' + case.name))
    with io.open(stem + '.json', 'w', encoding='utf-8') as fh:
        fh.write(json.dumps({'kind': kind, 'u': float(u), 't_mm': t,
                             'case': None if case is None else case.name,
                             'moves': None if case is None else [list(m) for m in case.moves],
                             'station_floor_mm': ci.station_floor(t),
                             'z_lo': z_lo, 'z_hi': z_hi,
                             'notch_edges': list(notch_edges),
                             'body_creases': list(body_features),
                             'patches': records},
                            indent=1, sort_keys=True, default=float))
    print('')
    print('  wrote %s.json in %.1f s total' % (stem, time.time() - started))
    return records


def notch_compound(tools):
    """The notch tools as one shape, since `pieces` hands back a list of objects.

    `cowl_interior` only sections these and reads their vertices, so a compound is what it wants
    and a fuse would be wasted work -- the same reasoning `cowl_tree._shell`'s docstring gives for
    handing them over unfused.
    """
    if hasattr(tools, 'Vertexes'):
        return tools
    import Part
    return Part.makeCompound([obj.Shape for obj in tools])


def main():
    kind = _opt('kind', 'tail_shell')
    u = float(_opt('u', '3.0'))
    out_dir = os.path.normpath(_opt('out-dir', OUT_DIR))
    family = _opt('family')
    if family is None:
        run(kind, u, out_dir)
        return

    # **The whole population, one tree a case.** `--family=pairs` screens the two-input axis and
    # `--family=single` the one-input axis. Each case is independent, so a failure is reported and
    # the run continues: an interrupted screen leaves real coverage behind rather than nothing,
    # which is the same reason `inputs.cases` orders its excursions by what the mechanism
    # implicates.
    from wall_measure import inputs
    cases = (inputs.pair_cases(kind, u) if family == 'pairs'
             else inputs.cases(kind, u))
    print('%s at U = %g: %d %s case(s), one cowl tree each and no cavity'
          % (kind, u, len(cases), family))
    worst = []
    for n, case in enumerate(cases, 1):
        print('')
        print('[%d/%d] %s' % (n, len(cases), case.name))
        try:
            records = run(kind, u, out_dir, None if case.is_baseline else case)
            under = sum(r['under_floor'] for r in records)
            tight = min(r['tightest_union_mm'] for r in records)
            worst.append((tight, under, case.name))
        except Exception as exc:                                  # noqa: BLE001
            print('    FAILED %s: %s' % (type(exc).__name__, str(exc)[:120]))
            worst.append((None, None, case.name + ' (failed)'))

    print('')
    print('tightest seeded gap per case, tightest first:')
    for tight, under, name in sorted(w for w in worst if w[0] is not None):
        print('  %12.7f mm   %2d under the floor   %s' % (tight, under, name))
    bad = [w for w in worst if w[0] is None]
    if bad:
        print('  %d case(s) failed: %s' % (len(bad), ', '.join(w[2] for w in bad)))


if is_entry_point(__name__):
    main()
