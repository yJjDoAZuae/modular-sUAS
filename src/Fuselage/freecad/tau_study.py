"""Build one cowl wall at several values of section 5's criterion and measure each one.

**This answers a question that was briefly mis-filed as a design decision.** Measured 2026-10-10,
every fully measured `tail_shell` wall reads 0.013 to 0.047 mm thinner than nominal -- three to five
times `WALL_TOL` = 0.01 mm -- while `cavity()`'s two refinement passes both stop at `TAU` = 0.05 mm,
so the walls come out just inside the criterion they were converged to. The obvious reading is that
`TAU` is the binding constraint. Whether that is true, and what tightening it costs, is a
measurement: build the same part at several `TAU` and see what the wall does.

Three outcomes are all informative and the experiment is written not to prefer any of them:

1. **The wall gets thinner in proportion.** `TAU` is the lever, and the cost in build time is the
   only remaining question.
2. **The build raises `Unconverged`.** Pass 2 cannot reach the tighter criterion inside
   `POST_CUT_ROUNDS` = 6, and the next question is whether a larger round budget helps. The
   `tail_shell` at `U` = 3.0 already spends 5 of its 6 rounds at `TAU` = 0.05, so this is a live
   possibility.
3. **The wall does not improve.** `TAU` is *not* the lever, which refutes the reading above and
   sends the search back to the mechanism (IP-WTM-26).

**`TAU` is not reachable from the document.** `cowl_tree`'s `_CowlShell.execute` calls
`shell_solid` without a `tau` argument, so a build always uses the module default. This builds the
tree once to get the cell shapes -- `Base`, `Body`, the notches, the inset, the overhang and the
mirrors, exactly what `execute` passes -- and then calls `shell_solid` directly per `TAU`. Nothing
here mutates `cowl_interior.TAU`, so a failure cannot leak into a later build in the same process.

**Cost, measured from the 2026-10-06 soak, because this has to be bounded before it is run.** A
`nose_cowl_shell` builds in 38 to 117 s and a `tail_shell` in 727 to 4 525 s. Start on the nose: it
is forty times cheaper, and at `U` = 4 its wall reads 0.0115 mm, just over tolerance, so it has room
to show an effect. Only then pay for a tail.

Usage, under `freecadcmd`. **Every argument needs its own `--pass`**, as `soak_cowl_shell.py`'s own
docstring shows: `--pass` takes a single token, so one `--pass` followed by several flags leaves
`freecadcmd` parsing the rest as its own options and printing its usage instead of running anything.
Its exit code is unreliable either way -- read the printed artifact, not the status::

    freecadcmd tau_study.py --pass --kind=nose_cowl_shell --pass --u=4.0 \\
        --pass --taus=0.05,0.02,0.01
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

import check_cowl_interior as cci                                  # noqa: E402
import cowl_interior as ci                                         # noqa: E402
import cowl_tree                                                   # noqa: E402
import soak_cowl_shell as soak                                     # noqa: E402
from corner_common import is_entry_point                           # noqa: E402

from wall_measure import candidates, density, locate               # noqa: E402

#: **Taken from `soak_cowl_shell`, not restated.** The kind-to-builder map, the parameter sheets and
#: the `U`-row substitution are exactly what the 28-build soak used, so a wall built here is the same
#: wall that corpus holds and the two sets of figures are comparable. A second copy of `with_u` would
#: be a second thing to keep in step with `cowl_tree`'s sheets.
BUILDERS = soak.BUILDERS
BASE_PARAMS = soak.BASE_PARAMS
with_u = soak.with_u

#: Circumferential spacing the wall is measured at, in mm. Fixed as a spacing and not as a sample
#: count: a cowl's perimeter scales with `U` while its wall does not, and a fixed count is what made
#: this subsystem's first corpus figures wrong by a factor of six
#: (cowl_interior_surface.md section 6.6).
SPACING = 0.125

#: The criterion values to try, coarsest first so the baseline is reproduced before anything is
#: tightened. The first should be `cowl_interior.TAU` itself.
DEFAULT_TAUS = (0.05, 0.02, 0.01)


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def build_cell(kind, u):
    """Build the tree once and return the shell object, whose inputs `shell_solid` needs.

    The recompute pays one wall at the module default `TAU`; that is unavoidable, because the cell
    shapes are produced by the same recompute, and it doubles as the baseline build.
    """
    doc = App.newDocument('tau_study')
    tip = cowl_tree.emit(doc, None, with_u(BASE_PARAMS[kind], u), BUILDERS[kind])
    doc.recompute()
    if not tip.Shape.Solids:
        raise ValueError(
            'the wall has no solids -- the construction failed inside execute() and recompute() '
            'swallowed it. Read the freecadcmd log above for the real traceback.')
    return doc, tip


def wall_at_tau(shell, tau):
    """`shell_solid` on the same cell inputs at one `tau`. Returns a row, never raises.

    An `Unconverged` is a result here, not an error: outcome 2 in this module's docstring. It is
    recorded with the message, because the message carries the worst gap pass 2 reached and how
    many intervals it still wanted.
    """
    notches = Part.makeCompound([n.Shape for n in shell.Notches])
    mirrors = [App.Vector(*[float(v) for v in text.split(',')]) for text in shell.Mirrors]
    report = {}
    started = time.time()
    row = {'tau': float(tau), 'converged': False, 'error': None, 'elapsed_s': None,
           'rows': None, 'predicted': None, 'solids': None, 'volume': None}
    try:
        solid = ci.shell_solid(shell.Base.Shape, shell.Body.Shape, notches, shell.Inset,
                               shell.Overhang, mirrors, tau=float(tau), report=report)
    except ci.Unconverged as exc:
        row['elapsed_s'] = time.time() - started
        row['error'] = str(exc)
        row['rows'] = report.get('stations')
        row['predicted'] = report.get('worst_wall')
        return row, None
    row.update(converged=True, elapsed_s=time.time() - started,
               rows=report.get('stations'), predicted=report.get('worst_wall'),
               solids=len(solid.Solids), volume=solid.Volume)
    return row, solid


def measure(solid, t, spacing=SPACING, stations=cci.STATIONS):
    """The finished wall's worst thinness, on a grid placed the way the acceptance gate places its.

    **`ci.z_extent` on the finished wall, not `Shape.BoundBox`.** `z_extent` finds the real axial
    extent by sectioning and bisecting, because a bounding box on these solids is an outer bound
    and nothing more -- its own docstring records a nose whose box was 139 % of the part. That is
    why this reaches all 12 stations where `wall_measure.corpus.station_grid`, which does use the
    bounding box, loses 3 to 7 of them on a nose wall.

    It is still not *identical* to the gate's grid: `check_cowl_interior.main` takes
    `ci.z_extent(body)`, the full cowl solid, while this takes the finished wall's. Both are real
    extents rather than boxes, so they differ by however much the shell's own closure differs from
    the body's -- small, but unmeasured. A figure from here is comparable across `TAU`, which is
    what this study needs; comparing one against a gate figure needs that difference measured first.
    """
    lo, hi = ci.z_extent(solid)
    lo, hi = lo + 1.0, hi - 1.0
    zs = [lo + (hi - lo) * i / float(stations - 1) for i in range(stations)]
    rows = locate.profile(solid, zs, measure=candidates.corner_excluded_min, nominal=t,
                          App=App, spacing=spacing)
    worst = locate.worst(rows)
    readable = [r for r in rows if r['worst_thin'] is not None]
    return {
        'stations': len(zs),
        'stations_measured': len(readable),
        'worst_thin': worst['worst_thin'] if worst else None,
        'worst_z': worst['z'] if worst else None,
        'worst_angle_deg': worst['angle_deg'] if worst else None,
        'over_tolerance': sum(1 for r in readable if r['worst_thin'] > ci.WALL_TOL),
        'states': locate.states(rows),
        'gate_spacing_mm': density.gate_spacing(
            density.section_perimeter(solid, zs[len(zs) // 2], App=App) or 0.0)[0],
    }


def study(kind, u, taus=DEFAULT_TAUS, spacing=SPACING, out=None):
    """Build `kind` at `u` once, then re-cut and measure the wall at each `tau`."""
    out = out if out is not None else sys.stdout
    doc, shell = build_cell(kind, u)
    t = float(shell.Inset)
    out.write('tau_study %s U=%s, wall t = %.4f mm, WALL_TOL = %.3f, module TAU = %.3f\n'
              % (kind, u, t, ci.WALL_TOL, ci.TAU))
    out.flush()
    rows = []
    for tau in taus:
        row, solid = wall_at_tau(shell, tau)
        if solid is not None:
            row['measured'] = measure(solid, t, spacing)
        else:
            row['measured'] = None
        rows.append(row)
        m = row['measured']
        if row['converged']:
            out.write('  TAU %.4f  converged  rows %3s  predicted %8.5f  real %8.5f  '
                      'over_tol %2d of %2d  %5.0f s\n'
                      % (tau, row['rows'], row['predicted'] or float('nan'),
                         m['worst_thin'] if m['worst_thin'] is not None else float('nan'),
                         m['over_tolerance'], m['stations_measured'], row['elapsed_s']))
        else:
            out.write('  TAU %.4f  UNCONVERGED  rows %3s  predicted %8.5f  %5.0f s\n    %s\n'
                      % (tau, row['rows'], row['predicted'] or float('nan'), row['elapsed_s'],
                         row['error'][:160]))
        out.flush()
    App.closeDocument(doc.Name)
    return rows


def main():
    kind = _opt('kind', 'nose_cowl_shell')
    u = float(_opt('u', '4.0'))
    taus = tuple(float(v) for v in _opt('taus', ','.join(str(x) for x in DEFAULT_TAUS)).split(','))
    rows = study(kind, u, taus, float(_opt('spacing', SPACING)))
    print('TAU_STUDY ' + json.dumps({'kind': kind, 'u': u, 'rows': rows}, default=str))
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    sys.exit(main())
