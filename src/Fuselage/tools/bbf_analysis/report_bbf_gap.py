"""OQ-DES-B14, Alternative 5: report where every variant's bolt-flange fillet center lands.

The fillet's center is the circle of radius `flange_fillet_radius` tangent to both the
flange's inner face and the bolt boss, so the fillet is fully determined. What is NOT
determined is how far that center ends up from the bolt axis -- `bbf_dx` -- which is a
difference of four independently chosen dimensions and can be anything, zero included.

Nothing rejects a value of it, by design (a minimum was Alternative 2 and was rejected). This
makes it visible instead, so that a change to `panel_offset`, `panel_overlap`,
`flange_thickness`, `flange_fillet_radius` or `bolt_offset` that moves variants around is
noticed rather than discovered later.

Costs nothing to run -- it resolves parameters and builds no geometry:

    uv run python src/Fuselage/tools/bbf_analysis/report_bbf_gap.py
    uv run python src/Fuselage/tools/bbf_analysis/report_bbf_gap.py --band 0.5 --quiet

Exit status is 1 only when a variant has **no** fillet solution at all, `abs(gap) >= reach`,
which is a real error: the FreeCAD generator refuses to build such a variant. Being inside
the band is reported, never failed.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..')))

import fuselage_variants as fv  # noqa: E402

AXES = ('panel_variants.csv', 'bulkhead_type_variants.csv', 'bulkhead_size_variants.csv')


def rows():
    """Every valid end-type variant, with its gap. Only end types carry this fillet."""
    printer = fv.null_printer_settings()
    out = []
    for params in fv.flatten_param_space(fv.read_all_param_axes(fv.axes(*AXES))):
        dp = fv.derived_parameters(params['U'], 1.0, params, printer, True)
        if not fv.family_is_valid('bulkhead', dp):
            continue
        if dp.bulkhead.type != fv.BulkheadType.END:
            continue
        gap, reach = fv.bolt_flange_fillet_gap(dp)
        out.append((gap, reach, params['U'], dp.bulkhead.type_name, dp.panel.type_name))
    out.sort()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--band', type=float, default=1.0,
                    help='report variants whose gap is inside +/- this, in mm (default 1.0)')
    ap.add_argument('--quiet', action='store_true', help='summary only')
    args = ap.parse_args(argv)

    data = rows()
    if not data:
        print('no valid end-type variants -- nothing carries this fillet')
        return 0

    unsolvable = [r for r in data if abs(r[0]) >= r[1]]
    inside = [r for r in data if abs(r[0]) < args.band]

    if not args.quiet:
        print('%-26s %10s %10s %8s' % ('variant', 'gap mm', 'reach mm', 'in band'))
        for gap, reach, U, type_name, panel in data:
            print('%-26s %10.4f %10.4f %8s'
                  % ('U=%s %s %s' % (U, type_name, panel), gap, reach,
                     'yes' if abs(gap) < args.band else ''))
        print()

    print('%d valid end-type variants' % len(data))
    print('gap spans %.4f .. %.4f mm; %d within %.2f mm of zero'
          % (data[0][0], data[-1][0], len(inside), args.band))
    tight = min(data, key=lambda r: r[1] - abs(r[0]))
    print('closest any variant comes to having no fillet at all: %.4f mm of margin '
          '(gap %.4f of reach %.4f) at U=%s %s %s'
          % (tight[1] - abs(tight[0]), tight[0], tight[1], tight[2], tight[3], tight[4]))

    if unsolvable:
        print()
        print('ERROR: %d variant(s) have no circle tangent to both the flange face and the '
              'bolt boss, so there is no fillet to build:' % len(unsolvable))
        for gap, reach, U, type_name, panel in unsolvable:
            print('  U=%s %s %s -- gap %.4f exceeds reach %.4f' % (U, type_name, panel, gap,
                                                                  reach))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
