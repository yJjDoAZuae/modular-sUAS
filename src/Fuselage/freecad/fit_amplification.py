"""Does a one-row nudge attenuate across the interior fit, or amplify? Measured on the real fit.

**The question.** `cowl.md` OQ-DES-CW26 alternative 1 asks what the switch is that a 0.03 mm row
displacement flips when 0.01 mm is benign. `freecad_migration.md` IP-FC-146 records the sharpest
open thread in that investigation as a contradiction between two numbers:

- `cowl_interior_surface.md` section 4.4 says the fit attenuates about **3.7x per station**, which
  over the 7.5 station intervals between the nudged row and the target station is a factor of
  about 1.3e-4.
- The construction's measured gain at that same target station is **0.408 mm of wall reading per
  mm of nudge**, three orders of magnitude larger.

IP-FC-146 ends "Why the measured gain so far exceeds the per-station decay is unexplained".

**What this measures.** `cowl_interior._fit` is an interpolation, so its response to displacing one
row by `delta` is exactly `delta` times a fixed shape and nothing else -- the interpolating
spline's cardinal function. `wall_measure.fit_response.cardinal` computes that shape in pure
Python, and a pure-Python search over station meshes says the 3.7x figure describes a *uniform*
mesh only: put a near-duplicate station pair immediately beside the nudged row and the same fit
*amplifies*, with a gain proportional to 1 / (pair tightness).

That prediction is about a natural cubic spline in `numpy`. This script puts it to the real kernel.
It builds synthetic rows, fits them with `cowl_interior._fit` itself, nudges one row, re-fits, and
measures how far the surface actually moved -- then prints the prediction beside it. Two unrelated
instruments through one claim is the point: a `numpy` tridiagonal solve and OCC's own
`BSplineCurve.interpolate` should agree, and if they do not, the prediction is what is wrong.

**The synthetic rows have real corners.** A rounded rectangle with fixed-radius corners, per the
requirement recorded under IP-FC-137 that synthetic geometry reproduce the real cowl's curvature
discontinuities rather than stand in for them smoothly.

**No booleans and no build.** This is the fit alone, which is what makes it seconds rather than
hours, and it is also the limit of what it can conclude: it measures how far a nudge travels
through the *surface*, not what the rib cut then does with it.

Run it as::

    freecadcmd fit_amplification.py
    freecadcmd fit_amplification.py --pass --knots=21 --pass --offset=7.5

`freecadcmd`'s exit code is unreliable, so read the printed table and the JSON.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App                                                    # noqa: E402,F401
import Part                                                              # noqa: E402,F401

import cowl_interior as ci                                               # noqa: E402
from corner_common import is_entry_point                                 # noqa: E402
from wall_measure import fit_response as fr                              # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'fit_amplification')

#: The section the synthetic rows carry, in mm: a tail-sized rounded rectangle.
HALF_X, HALF_Y, CORNER = 60.0, 40.0, 8.0

#: Points per row. `cowl_interior`'s own fit resolution is this order, and the response is measured
#: at matched surface parameters rather than at row points, so it is not a sampling knob.
N_FIT = 96

#: How tight to squeeze the station pair beside the nudged row, as a fraction of the interval it
#: replaces. 1.0 is the uniform mesh -- the control.
TIGHTNESS = (1.0, 1.0e-1, 1.0e-2, 1.0e-3, 1.0e-4)

#: The nudge, in mm. Small enough to stay in the regime OQ-DES-CW26 measured its gain in.
DELTA = 0.001

#: The cowl wall at the parameter sheet's current values, `cowl_n_perimeters * extrusion_width`.
#: `cavity` is handed this as `t` and derives its station floor from it, so the floor this script
#: reports is the floor a real build at these values gets.
WALL_MM = 0.6


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


#: Near-duplicate station pairs this subsystem is recorded as actually containing, in mm. The
#: first is the pair IP-FC-144 exists to remove and reaches a real build because `MIN_INTERVAL` is
#: enforced against subdivision and not against the seed-set union; the second is the artifact an
#: earlier harness manufactured by unioning a four-decimal printing of a real notch edge into the
#: seed set; the third is the real neighbor gap at the perturbed row once nothing is forced.
REAL_PAIRS = ((0.0009433, 'the pair IP-FC-144 removes'),
              (0.0000338812, "an earlier harness's forced pair"),
              (0.4310898, 'the real notch-edge neighbor gap'))


def mesh(knots, i_row, tightness, z_lo, z_hi, at=None):
    """Station heights: uniform, with one interval squeezed by `tightness`.

    `at` is which interval to squeeze, defaulting to the one immediately after `i_row`. Being able
    to put the crowding somewhere else is the whole converse: if crowding anywhere amplified, the
    finding would be about the mesh, and if only crowding *beside the nudged row* amplifies, it is
    about the pair and the nudge together.
    """
    span = z_hi - z_lo
    zs = [z_lo + span * i / float(knots - 1) for i in range(knots)]
    if tightness < 1.0:
        k = i_row if at is None else at
        zs[k + 1] = zs[k] + tightness * (zs[k + 1] - zs[k])
    return sorted(zs)


def _gain(zs, i_row, offset):
    """The measured gain of the real fit at `offset` knots along, and its prediction."""
    rows = fr.rounded_rows(zs, N_FIT, HALF_X, HALF_Y, CORNER, taper=0.0005)
    target = fr._at([z for z, _p in rows], i_row, offset)
    return fr.response(ci._fit, rows, i_row, DELTA, [target])[0]


def run(knots, offset, out_dir):
    started = time.time()
    i_row = int(knots // 2)
    z_lo, z_hi = -300.0, 0.0
    print('')
    print('The fit alone: how far a %.4f mm one-row nudge travels, %s knots along.'
          % (DELTA, offset))
    print('  rows %d, nudged row %d, section %.0f x %.0f mm, corner r = %.0f mm'
          % (knots, i_row, 2 * HALF_X, 2 * HALF_Y, CORNER))
    print('')
    print('  pair gap, mm   measured gain   predicted gain      ratio')
    print('  ' + '-' * 60)

    records = []
    for tightness in TIGHTNESS:
        zs = mesh(knots, i_row, tightness, z_lo, z_hi)
        gap = zs[i_row + 1] - zs[i_row]
        got = _gain(zs, i_row, offset)
        ratio = (got['gain'] / got['predicted_gain']
                 if got['predicted_gain'] else float('nan'))
        print('  %12.6g   %13.6e   %13.6e   %8.3f'
              % (gap, got['gain'], got['predicted_gain'], ratio))
        records.append(dict(got, tightness=tightness, pair_gap_mm=gap, arm='tightness',
                            knots=knots, offset=offset, i_row=i_row))

    print('')
    base = records[0]['gain']
    print('  Against the uniform mesh, which is the control:')
    for rec in records[1:]:
        print('    pair %10.3e mm  amplifies by %12.1fx'
              % (rec['pair_gap_mm'], rec['gain'] / base if base else float('nan')))

    # The converse. A pair crowded somewhere other than beside the nudged row has to *not*
    # amplify, or the finding is about the mesh rather than about the pair and the nudge together.
    print('')
    print('  Converse: the same 1.5e-3 mm pair, moved away from the nudged row.')
    print('    pair beside interval   measured gain    against uniform')
    tight = 1.0e-4
    for at in (0, 3, i_row - 1, i_row, i_row + 1, i_row + 4, knots - 2):
        zs = mesh(knots, i_row, tight, z_lo, z_hi, at=at)
        got = _gain(zs, i_row, offset)
        flag = '   <- beside the nudge' if at in (i_row - 1, i_row) else ''
        print('    %18d   %13.6e   %12.1fx%s'
              % (at, got['gain'], got['gain'] / base if base else float('nan'), flag))
        records.append(dict(got, tightness=tight, pair_at=at, arm='converse',
                            knots=knots, offset=offset, i_row=i_row))

    # What the pairs this subsystem really contains would do, at the same offset.
    print('')
    print('  The near-duplicate pairs actually on record:')
    print('    pair gap, mm    measured gain   what it is')
    span_interval = (z_hi - z_lo) / float(knots - 1)
    for gap, what in REAL_PAIRS:
        zs = mesh(knots, i_row, gap / span_interval, z_lo, z_hi)
        got = _gain(zs, i_row, offset)
        print('    %12.7f   %13.6e   %s' % (gap, got['gain'], what))
        records.append(dict(got, pair_gap_mm=gap, arm='real', what=what,
                            knots=knots, offset=offset, i_row=i_row))

    # The bound. IP-FC-144 put a floor under the station gap, and since the gain goes as
    # 1 / gap, a floor on the gap is a ceiling on the gain. This is the number that says whether
    # the condition behind the 0.408 reading is still reachable.
    floor = ci.station_floor(WALL_MM)
    zs = mesh(knots, i_row, floor / span_interval, z_lo, z_hi)
    got = _gain(zs, i_row, offset)
    print('')
    print('  The bound IP-FC-144 puts on this, at t = %.3f mm:' % WALL_MM)
    print('    station_floor(t)          %.4f mm' % floor)
    print('    gain at the floor         %13.6e mm per mm' % got['gain'])
    print('    against the 0.408 on record     %.1fx smaller'
          % (0.408 / got['gain'] if got['gain'] else float('nan')))
    records.append(dict(got, pair_gap_mm=floor, arm='floor', what='station_floor(t)',
                        knots=knots, offset=offset, i_row=i_row))

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    stem = os.path.join(out_dir, 'fit_amplification')
    with io.open(stem + '.json', 'w', encoding='utf-8') as fh:
        fh.write(json.dumps({'delta_mm': DELTA, 'records': records,
                             'section': {'half_x': HALF_X, 'half_y': HALF_Y,
                                         'corner': CORNER, 'n_fit': N_FIT}},
                            indent=1, sort_keys=True, default=float))
    print('')
    print('  wrote %s.json in %.1f s' % (stem, time.time() - started))
    return records


def main():
    knots = int(_opt('knots', '21'))
    offset = float(_opt('offset', '7.5'))
    run(knots, offset, os.path.normpath(_opt('out-dir', OUT_DIR)))


if is_entry_point(__name__):
    main()
