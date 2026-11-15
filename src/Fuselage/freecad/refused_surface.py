"""Read the wall a pre-cut refusal's fitted surface would have produced, station by station.

**Why this exists.** On 2026-11-13 a `tail_shell` at `U` = 3.0, dosed at 0.03 mm, refused at
section 5's *pre-cut* station budget with "worst measured wall error 18.4928 mm against 0.050".
The figure was tested first as a unit error, because 18.4928 is exactly 0.0184928 x 1000 and a
true 0.0185 mm would pass -- and refuted by measurement: at five stations the wall read 0.576 to
0.605 mm against t = 0.600. So the figure is real, and it is not at any station that was sampled.

**What the refusal does and does not measure.** `_refine` sections the fitted surface at every
interval midpoint. A section that is not exactly one open arc is counted as "unsliceable" and
*skipped* -- it is not measured at all, which corrects an earlier reading of this defect that
assumed the first arc of a folded section was being compared. Every gap in the reported worst
therefore comes from a station that *does* section into one arc. This scans the saved surface
the same way and finds that station.

**The refusal carries the fitted surface** (`cowl_interior.Unconverged.shape`, a single
`BSplineSurface` face, written by `wall_measure.refusals` through `sever_doses._export_brep`), so
this needs the cowl tree for the exterior and nothing else. The tree builds in seconds; the fit
that produced the surface took 22 minutes and is not repeated.

**Nothing in the measurement is reimplemented.** The exterior is `cavity`'s own `body_arc` and
`outer_at`, recomposed from the same module-level functions in the same order --
`cell_boundary_planes`, `_slice_wires`, `open_arc`, `open_contour` -- with `n_check` from
`check_samples` over the widest of the same three stations. The interior is `_refine`'s: the open
wires of `_slice_wires` on the face, `open_contour(cut[0], n_check)` when there is exactly one, and
`max |d - t|`. A comparison that rebuilt any of those is how four earlier attempts at a reading
like this produced plausible wrong numbers (`cowl_interior_surface.md` section 6.1).

**One approximation, stated.** `_refine` measures at the midpoints of the rows it fitted, and
those rows are not in the artifact -- only the surface is. So this scans at a uniform spacing
and then refines around the worst readings. A gap peaked more narrowly than the refined spacing
could be under-read; the refined spacing is printed so that limit is visible.

    freecadcmd refused_surface.py --pass --brep=out/rounds_probe/refusals/tail_shell_U3_d0.03mm.brep \\
        --pass --kind=tail_shell --pass --u=3.0

`freecadcmd`'s exit code is unreliable: read the printed table and the JSON.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App                                                    # noqa: E402
import numpy as np                                                       # noqa: E402

import cowl_interior as ci                                               # noqa: E402
import cowl_tree                                                         # noqa: E402
import si                                                                # noqa: E402
from corner_common import is_entry_point                                 # noqa: E402
from refused_wall import load_brep, say                                  # noqa: E402
from station_gaps import BUILDERS, PARAMS, with_u                        # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'refused_surface')

#: The part-wide pass. 2 mm over a 300 mm part is 150 stations, which places at least one sample
#: inside any defect wider than that -- the refined pass below is what resolves its peak.
COARSE_STEP_M = 2.0e-3

#: How many of the worst coarse readings get a refined pass, and how finely. 0.1 mm either side
#: of each over +/- one coarse step resolves a peak twenty times narrower than the coarse pass.
REFINE_COUNT = 3
REFINE_STEP_M = 1.0e-4


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


class Exterior(object):
    """`cavity`'s `body_arc` and `outer_at`, recomposed from the same module-level functions.

    Cached per station on the same `round(z / Z_TOL_M)` key `cavity` uses, so a refined pass
    that revisits a coarse station gets the identical polyline rather than a re-section.
    """

    def __init__(self, body):
        self.body = body
        self.planes = ci.cell_boundary_planes(body)
        lo_m, hi_m = ci.z_extent(body)
        self.z_lo_m = lo_m + ci.END_INSET_M
        self.z_hi_m = hi_m - ci.END_INSET_M
        self._arcs = {}
        self._outers = {}
        widest_m = max(si.length_m(self.arc(z_m)[0])
                       for z_m in (self.z_lo_m, 0.5 * (self.z_lo_m + self.z_hi_m),
                                   self.z_hi_m))
        self.n_check = ci.check_samples(widest_m)

    @staticmethod
    def _key(z_m):
        return round(z_m / ci.Z_TOL_M)

    def arc(self, z_m):
        k = self._key(z_m)
        if k not in self._arcs:
            wires = ci._slice_wires(self.body, z_m)
            if len(wires) != 1:
                raise ci.PreconditionFailed(
                    'P2: the cell body sections into %d loops at z = %.4f mm, not one'
                    % (len(wires), si.mm(z_m)))
            self._arcs[k] = ci.open_arc(wires[0], self.planes)
        return self._arcs[k]

    def outer_at(self, z_m):
        k = self._key(z_m)
        if k not in self._outers:
            arc, _p0, _p1, flip = self.arc(z_m)
            self._outers[k] = ci.open_contour(arc, self.n_check, flip)[1]
        return self._outers[k]


def reading(face, exterior, z_m, t_m):
    """`_refine`'s measurement at one station, or the reason it would have skipped it.

    Returns a dict. `gap_mm` is present only for a station `_refine` would actually measure --
    exactly one open arc -- because that is the only kind its reported worst can come from.
    """
    sliced = ci._slice_wires(face, z_m)
    cut = [w for w in sliced if not w.isClosed()]
    out = {'z_mm': si.mm(z_m), 'wires': len(sliced), 'open': len(cut)}
    if len(cut) != 1:
        out['skipped'] = '%d wire(s), %d open' % (len(sliced), len(cut))
        return out
    here, _dense = ci.open_contour(cut[0], exterior.n_check)
    d = exterior.outer_at(z_m).distances(here)
    dev = np.abs(d - t_m)
    worst = int(np.argmax(dev))
    out.update(gap_mm=si.mm(float(dev[worst])),
               d_min_mm=si.mm(float(d.min())), d_max_mm=si.mm(float(d.max())),
               worst_point_mm=[si.mm(float(here[worst][0])), si.mm(float(here[worst][1]))])
    return out


def run(brep, kind, u, out_dir):
    started = time.time()
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    stem = os.path.join(out_dir, '%s_U%g' % (kind, u))
    rec = {'brep': brep, 'kind': kind, 'u': float(u),
           'coarse_step_mm': si.mm(COARSE_STEP_M), 'refine_step_mm': si.mm(REFINE_STEP_M)}

    def keep():
        rec['seconds'] = time.time() - started
        with io.open(stem + '.json', 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(rec, indent=1, sort_keys=True, default=float))

    say('')
    say('the wall a pre-cut refusal surface would produce: %s' % os.path.basename(brep))
    doc = App.newDocument('refused_surface')
    try:
        cowl_tree.emit(doc, None, with_u(PARAMS[kind], u), BUILDERS[kind])
        doc.recompute()
        body_node, _tools, _mirrors, _cell_cut = cowl_tree.pieces(doc)
        params = doc.getObject('Params')
        t_m = si.m(float(params.get('cowl_n_perimeters')) * float(params.get('extrusion_width')))
        exterior = Exterior(body_node.Shape)
        face = load_brep(brep)
        rec.update(t_mm=si.mm(t_m), n_check=exterior.n_check,
                   z_lo_mm=si.mm(exterior.z_lo_m), z_hi_mm=si.mm(exterior.z_hi_m))
        say('  tree built in %.0f s; t = %.3f mm, n_check = %d, z %.4f..%.4f mm'
            % (time.time() - started, si.mm(t_m), exterior.n_check,
               si.mm(exterior.z_lo_m), si.mm(exterior.z_hi_m)))
        keep()

        span_m = exterior.z_hi_m - exterior.z_lo_m
        n = max(2, int(round(span_m / COARSE_STEP_M)))
        coarse = []
        say('  coarse pass: %d stations at %.2f mm' % (n + 1, si.mm(COARSE_STEP_M)))
        for k in range(n + 1):
            z_m = exterior.z_lo_m + span_m * k / float(n)
            coarse.append(reading(face, exterior, z_m, t_m))
            if k % 25 == 0:
                say('    %3d/%d  z = %9.4f  %.0f s' % (k, n, si.mm(z_m), time.time() - started))
        rec['coarse'] = coarse
        keep()

        measured = sorted((r for r in coarse if 'gap_mm' in r),
                          key=lambda r: -r['gap_mm'])
        refined = []
        for top in measured[:REFINE_COUNT]:
            center_m = si.m(top['z_mm'])
            lo_m = max(exterior.z_lo_m, center_m - COARSE_STEP_M)
            hi_m = min(exterior.z_hi_m, center_m + COARSE_STEP_M)
            steps = max(2, int(round((hi_m - lo_m) / REFINE_STEP_M)))
            say('  refining around z = %.4f mm (%.4f mm coarse): %d stations'
                % (top['z_mm'], top['gap_mm'], steps + 1))
            for k in range(steps + 1):
                refined.append(reading(face, exterior, lo_m + (hi_m - lo_m) * k / float(steps),
                                       t_m))
        rec['refined'] = refined
        keep()

        allm = [r for r in coarse + refined if 'gap_mm' in r]
        skipped = [r for r in coarse if 'skipped' in r]
        worst = max(allm, key=lambda r: r['gap_mm']) if allm else None
        rec['worst'] = worst
        rec['skipped_coarse'] = len(skipped)
        keep()

        say('')
        say('  stations measured: %d; coarse stations skipped as unsliceable: %d of %d'
            % (len(allm), len(skipped), len(coarse)))
        for r in skipped:
            say('    skipped z = %9.4f  %s' % (r['z_mm'], r['skipped']))
        if worst is not None:
            say('  worst gap %.4f mm at z = %.4f, wall read %.4f..%.4f mm, worst point (%.3f, %.3f)'
                % (worst['gap_mm'], worst['z_mm'], worst['d_min_mm'], worst['d_max_mm'],
                   worst['worst_point_mm'][0], worst['worst_point_mm'][1]))
        say('  the refusal reported 18.4928 mm; written %s.json in %.0f s'
            % (stem, time.time() - started))
    finally:
        App.closeDocument(doc.Name)
    return rec


def main():
    brep = _opt('brep')
    if not brep:
        raise SystemExit('--brep=<path to a pre-cut refusal surface> is required')
    run(os.path.normpath(brep), _opt('kind', 'tail_shell'), float(_opt('u', '3.0')),
        os.path.normpath(_opt('out-dir', OUT_DIR)))


if is_entry_point(__name__):
    main()
