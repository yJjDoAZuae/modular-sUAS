"""IP-WTM-26: is the residual only in the gap between the construction's two exteriors?

**Where this question comes from.** `cowl_interior` necessarily has two exteriors. `_refine`, the
first refinement pass, measures the wall out to `outer_at` -- `body`'s **un-notched OML** -- because
no buttress cut exists at the moment the interior surface is fitted. The post-cut loop measures it
out to `finished_outer_at`, the **notched** exterior, which is the real finished part. Those two
diverge wherever a buttress tool removed exterior material, and `finished_outer_at`'s own note
records them 26.5 mm apart at one real thin station's worst point.

IP-WTM-44 made that difference the leading explanation for a result nothing else accounted for: on
`tail_shell` at `U` = 2.0, pass 1 converges to **0.0073 mm**, inside `WALL_TOL`, while the finished
wall it hands over still reads **0.0481 mm**, and tightening `TAU` fivefold moves the second not at
all. If the residual lives in the reference surface, that is exactly what it would look like.

**What this script is for is refuting that, not confirming it.** The attractive version of the
claim is weak -- of course two different reference surfaces give two different numbers. The version
worth testing is that the residual is **only** there, and it has a converse: at a station where the
two exteriors coincide, no buttress tool is within reach, so the two readings are the same number
and there should be no residual either. **A station that reads thin against both exteriors refutes
it**, because no choice of reference surface explains that station. `locate.exterior_verdict` sorts
the stations into `coincident`, `explained` and `unexplained` and reports a record with no
coincident station as **vacuous** rather than clean -- a record that never exercised the converse
has not tested anything (section 6.1).

**The two readings come from one `_finished_wall_gap` call with the exterior swapped**, inside
`cavity` where both closures live, never from a contour rebuilt here. Rebuilding one is how four
earlier attempts at measuring against an operand each produced a plausible wrong number.

**Cost.** A `nose_cowl_shell` builds in 38 to 117 s and a `tail_shell` in 727 to 4 525 s, so start
on the nose: it is forty times cheaper and it has notches, which is all this measurement needs. The
split itself adds one distance field per round-0 station, which is seconds.

Usage, one `--pass` per argument, and `freecadcmd`'s exit code is unreliable -- read the table::

    freecadcmd exterior_split.py --pass --kind=nose_cowl_shell --pass --u=1.0
    freecadcmd exterior_split.py --pass --kind=tail_shell --pass --u=0.5

`--rows` runs IP-WTM-30's measurement instead: the finished wall's thin spots against the **fit row
spacing** of the same build, which is the refined form of §6.7.1's diagonal hypothesis -- that the
diagonals act on the wall through the fit's row placement rather than through the cut::

    freecadcmd exterior_split.py --pass --kind=tail_shell --pass --u=0.5 --pass --rows
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

from wall_measure import corpus, locate                            # noqa: E402

BUILDERS = soak.BUILDERS
BASE_PARAMS = soak.BASE_PARAMS
with_u = soak.with_u


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def build_cell(kind, u):
    """Build the tree once and return the shell object, whose inputs `shell_solid` needs.

    Taken from `tau_study.build_cell` rather than re-derived: the kind-to-builder map, the
    parameter sheets and the `U`-row substitution are what the 28-build soak used, so a wall built
    here is the same wall the corpus holds.
    """
    doc = App.newDocument('exterior_split')
    tip = cowl_tree.emit(doc, None, with_u(BASE_PARAMS[kind], u), BUILDERS[kind])
    doc.recompute()
    if not tip.Shape.Solids:
        raise ValueError(
            'the wall has no solids -- the construction failed inside execute() and recompute() '
            'swallowed it. Read the freecadcmd log above for the real traceback.')
    return doc, tip


def measure(shell, tau=None, out=None):
    """One build: `shell_solid` with the split recorded, then the verdict.

    `tau` defaults to the module constant, which is what production uses. A tighter `tau` is
    interesting here for a different reason than in `tau_study`: it is the setting under which
    pass 1 reaches 0.0073 mm, so the gap between the two exteriors should be at its most visible.
    But it also raises `Unconverged` on a tail, and an exception means no record at all -- so the
    default run is at the production value, where the build is known to finish.
    """
    out = out if out is not None else sys.stdout
    rows = []
    report = {}
    notches = Part.makeCompound([n.Shape for n in shell.Notches])
    mirrors = [App.Vector(*[float(v) for v in text.split(',')]) for text in shell.Mirrors]
    t = float(shell.Inset)
    started = time.time()
    try:
        ci.shell_solid(shell.Base.Shape, shell.Body.Shape, notches, t, shell.Overhang, mirrors,
                       tau=float(tau) if tau is not None else ci.TAU, report=report,
                       exterior_split=rows)
        error = None
    except ci.Unconverged as exc:
        # **A record is still a record.** The split is appended during round 0, which runs before
        # any insertion, so an `Unconverged` raised later does not invalidate the rows already
        # collected -- and on a tail at a tightened `tau` that is the only way to get them.
        error = str(exc)
    out.write('wall t = %.4f mm, TAU = %.3f, WALL_TOL = %.3f, %d round-0 station(s), %.0f s\n'
              % (t, float(tau) if tau is not None else ci.TAU, ci.WALL_TOL, len(rows),
                 time.time() - started))
    if error:
        out.write('  Unconverged (the round-0 record below still stands): %s\n' % error[:160])
    out.write('\n'.join('  ' + line for line in
                        locate.exterior_table(rows, wall_tol=ci.WALL_TOL).splitlines()) + '\n')
    out.flush()
    return rows, locate.exterior_verdict(rows, wall_tol=ci.WALL_TOL), error


def measure_rows(shell, tau=None, out=None):
    """IP-WTM-30: the finished wall's thin spots against the **fit row spacing** of its own build.

    `cavity`'s `station_positions` and the wall `shell_solid` returns come out of one call here, so
    the two sides of the comparison are the same build. Taking rows from one build and a wall from
    another would lean on a reproducibility this subsystem only has away from degenerate
    configurations, and nothing about this question needs that.
    """
    out = out if out is not None else sys.stdout
    report = {}
    notches = Part.makeCompound([n.Shape for n in shell.Notches])
    mirrors = [App.Vector(*[float(v) for v in text.split(',')]) for text in shell.Mirrors]
    t = float(shell.Inset)
    started = time.time()
    wall = ci.shell_solid(shell.Base.Shape, shell.Body.Shape, notches, t, shell.Overhang,
                          mirrors, tau=float(tau) if tau is not None else ci.TAU, report=report)
    row_zs = report.get('station_positions') or []
    out.write('built in %.0f s; %d fit row(s), wall %.3f mm3 in %d solid(s)\n'
              % (time.time() - started, len(row_zs), wall.Volume, len(wall.Solids)))
    if not row_zs:
        out.write('  NO ROW POSITIONS in the report -- nothing to compare against\n')
        out.flush()
        return [], None
    zs = corpus.measurable_station_grid(wall, App=App)
    out.flush()
    rows = locate.row_spacing_split(wall, row_zs, zs, nominal=t, App=App)
    out.write('\n'.join('  ' + line
                        for line in locate.row_spacing_table(rows).splitlines()) + '\n')
    out.flush()
    return rows, locate.row_spacing_verdict(rows)


def main():
    kind = _opt('kind', 'nose_cowl_shell')
    u = float(_opt('u', '1.0'))
    tau = _opt('tau')
    if any(a == '--rows' for a in sys.argv):
        print('row_spacing %s U=%s' % (kind, u), flush=True)
        doc, shell = build_cell(kind, u)
        rows, verdict = measure_rows(shell, tau)
        App.closeDocument(doc.Name)
        print('ROW_SPACING ' + json.dumps({'kind': kind, 'u': u, 'verdict': verdict,
                                           'rows': rows}, default=str), flush=True)
        return 0
    print('exterior_split %s U=%s' % (kind, u), flush=True)
    doc, shell = build_cell(kind, u)
    rows, verdict, error = measure(shell, tau)
    App.closeDocument(doc.Name)
    print('EXTERIOR_SPLIT ' + json.dumps({
        'kind': kind, 'u': u, 'tau': tau, 'error': error,
        'stations': verdict['stations'], 'coincident': len(verdict['coincident']),
        'explained': len(verdict['explained']), 'unexplained': len(verdict['unexplained']),
        'worst_notched': verdict['worst_notched'], 'worst_oml': verdict['worst_oml'],
        'worst_unexplained_oml': verdict['worst_unexplained_oml'],
        'vacuous': verdict['vacuous'], 'clean': verdict['clean'],
        'rows': rows,
    }, default=str), flush=True)
    return 0


if is_entry_point(__name__):
    sys.exit(main())
