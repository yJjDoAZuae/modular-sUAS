"""IP-FC-12: `nose_plate` and `nose_tip`, ported from `cowl.py`'s baked `Part::Feature` path
to `cowl_tree.py`'s sheet-bound mechanism, 2026-09-21. Pins the regression that port was
verified against, so a future change cannot silently reintroduce a baked or mismatched shape.

    freecadcmd check_cowl_nose_parametric.py

Each part is checked at two configurations, not just the reference row -- a port that only
matches where it was written to match is not proven to scale correctly. For each:

* the new `cowl_tree` geometry matches `cowl.py`'s baked reference at zero symmetric
  difference and the same face count;
* the *same already-built* document, with its sheet edited in place to the other
  configuration and recomputed, matches a fresh build at that configuration -- the actual
  capability a baked `Part::Feature` does not have and this port exists to deliver. A port
  that merely agreed with the reference twice, independently, would not catch a broken
  expression or a node that silently cached its first shape.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import cowl
import cowl_tree
from corner_common import is_entry_point

# Pinned literals, not read from the sweep: nothing under `freecadcmd` can import
# `fuselage_variants` (it needs `solid2`, which lives only in the project virtualenv). These
# are the exact seeds `cowl_parameters()` produced for `U` = 1 and `U` = 1.5, and the
# `nose_size_variants.csv` rows for `U` = 1 and `U` = 4, on 2026-09-21 when the port was
# verified -- see `freecad_migration.md`'s IP-FC-12 entry for that date.
NOSE_TIP_SEEDS = {
    1.0: dict(U=1.0, unit_width=100.0, overhang_angle_from_bed=35.0, cut_len=0.06,
              nose_flange_height=1.0, nose_flange_inset=0.5, plate_diam=0.6,
              plate_thickness=0.8, plate_tol=0.1, oml_scale_m_per_mm=0.001,
              oml_length_m=0.05, oml_offset_x_m=0.0, oml_reversed=0.0),
    1.5: dict(U=1.5, unit_width=150.0, overhang_angle_from_bed=35.0, cut_len=0.06,
              nose_flange_height=1.6, nose_flange_inset=0.5, plate_diam=0.6,
              plate_thickness=1.2, plate_tol=0.1, oml_scale_m_per_mm=0.001,
              oml_length_m=0.05, oml_offset_x_m=0.0, oml_reversed=0.0),
}

NOSE_PLATE_SEEDS = {
    1.0: dict(U=1.0, overhang_angle_from_bed=35.0, plate_diam=60.0, plate_thickness=0.8,
              plate_flange_height=1.0, plate_flange_width=2.0),
    4.0: dict(U=4.0, overhang_angle_from_bed=35.0, plate_diam=240.0, plate_thickness=3.2,
              plate_flange_height=4.0, plate_flange_width=8.0),
}


def _old_nose_tip_shape(seed):
    """`cowl.nose_tip()` wants `cut_len`/`plate_diam` as absolute millimetres, not the
    fractions `cowl_tree`'s sheet holds -- see `cowl_tree.nose_tip`'s own docstring for why
    the two builders disagree about that."""
    p = dict(seed)
    p['cut_len'] = seed['cut_len'] * seed['unit_width']
    p['plate_diam'] = seed['plate_diam'] * seed['unit_width']
    p['oml'] = {'scale_m_per_mm': seed['oml_scale_m_per_mm'],
               'length_m': seed['oml_length_m'],
               'offset_x_m': seed['oml_offset_x_m'],
               'reversed': bool(seed['oml_reversed'])}
    solid, _repairs = cowl.nose_tip(p)
    return solid


def _symdiff(a, b):
    return a.cut(b).Volume + b.cut(a).Volume


def _check_one(label, old, doc, tip):
    new = tip.Shape
    d = _symdiff(old, new)
    ok = new.isValid() and len(new.Faces) == len(old.Faces) and d < 1.0e-6
    print('%-28s faces=%-3d valid=%-5s vol=%14.6f  symdiff=%.9f  %s'
          % (label, len(new.Faces), new.isValid(), new.Volume, d, 'OK' if ok else 'FAIL'))
    return 0 if ok else 1


def _check_resolve(label, doc_lo, tip_lo, seed_hi, fresh_vol):
    sheet = doc_lo.getObject('Params')
    for alias, value in seed_hi.items():
        sheet.set(alias, repr(float(value)))
    doc_lo.recompute()
    edited_vol = tip_lo.Shape.Volume
    ok = abs(edited_vol - fresh_vol) < 1.0e-6
    print('%-28s edited-in-place=%14.6f  fresh=%14.6f  %s'
          % (label, edited_vol, fresh_vol, 'OK' if ok else 'FAIL'))
    return 0 if ok else 1


def check_nose_plate():
    bad = 0
    docs = {}
    for U, seed in sorted(NOSE_PLATE_SEEDS.items()):
        old, _repairs = cowl.nose_plate(seed)
        doc = App.newDocument('check_plate_%g' % U)
        tip = cowl_tree.emit(doc, seed, cowl_tree.PARAMS_NOSE_PLATE, cowl_tree.nose_plate)
        bad += _check_one('nose_plate U=%g' % U, old, doc, tip)
        docs[U] = (doc, tip)
    lo, hi = sorted(NOSE_PLATE_SEEDS)
    bad += _check_resolve('nose_plate resolve %g->%g' % (lo, hi),
                          docs[lo][0], docs[lo][1], NOSE_PLATE_SEEDS[hi],
                          docs[hi][1].Shape.Volume)
    return bad


def check_nose_tip():
    bad = 0
    docs = {}
    for U, seed in sorted(NOSE_TIP_SEEDS.items()):
        old = _old_nose_tip_shape(seed)
        doc = App.newDocument('check_tip_%g' % U)
        tip = cowl_tree.emit(doc, seed, cowl_tree.PARAMS_NOSE_TIP, cowl_tree.nose_tip)
        bad += _check_one('nose_tip U=%g' % U, old, doc, tip)
        docs[U] = (doc, tip)
    lo, hi = sorted(NOSE_TIP_SEEDS)
    bad += _check_resolve('nose_tip resolve %g->%g' % (lo, hi),
                          docs[lo][0], docs[lo][1], NOSE_TIP_SEEDS[hi],
                          docs[hi][1].Shape.Volume)
    return bad


def main():
    bad = check_nose_plate() + check_nose_tip()
    print('check_cowl_nose_parametric: %s' % ('OK' if bad == 0 else '%d CHECK(S) FAILED' % bad))
    sys.stdout.flush()
    return 1 if bad else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
