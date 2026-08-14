"""Render one variant through the sweep's own parameter pipeline.

**Do not render a variant by passing -D overrides to the .scad drivers.** The drivers carry
hard-coded values that are self-consistent only for their own single configuration, and
several parameters are *derived*, not free:

  * `panel.offset` is computed by `derived_parameters()` from `panel.overlap`,
    `panel.thickness`, the greeble clearance and the extrusion width. It is not independent
    and it is not zero in general -- 0 mm panel gives 5.5, 3/16 in gives 2.5, and the
    driver hard-codes 0.
  * `panel.overlap` is `max(panel.thickness, 4)`, or 0 when the panel is 0 mm.
  * the sweep uses `extrusion_width = 0.6`; `fuselage_bulkhead.scad` uses 0.4.

Overriding some of these and leaving the rest produces a combination the sweep would never
generate. It renders without complaint and the geometry is wrong -- a 0 mm panel rendered
with the driver's `panel_offset = 0` loses the greeble posts entirely, because that offset
is exactly the clearance keeping the panel's inner corner off the greeble perimeter.

The relationships are defined in `fuselage_variants.py`. This calls them.

    python render_variant.py                          # list every combination and its validity
    python render_variant.py 1.0 end_bolt 3/16in      # derive, check, render
    python render_variant.py 1.0 center_single 3mm    # ... a boom bulkhead

**Both bulkhead families are listed and rendered here.** The frame bulkhead and the boom
bulkhead are separate sweeps off separate type axes, and until IP-FC-12 this tool knew only
the first -- so the boom bulkhead had no way to be rendered one at a time at all, and
`export_parameters.py`, which enumerates through this file, answered "no such combination"
for every boom variant. The type name says which family a variant belongs to; the families
themselves are described in `fuselage_variants.BULKHEAD_FAMILIES`.

Needs the project venv -- `fuselage_variants` imports solid2, which FreeCAD's bundled
Python does not have.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)                         # the CSV axes resolve relative to this directory

import fuselage_variants as fv

# Generated renders, so `freecad/out/`, not the source directory beside the scripts. This
# used to be `freecad/preview/`, which put a 14 MB tree of meshes and PNGs in among the
# geometry modules. `freecad/out/` is ignored as a whole, and it is the same directory
# `corner_common.out_path()` hands the FreeCAD-side scripts, so both toolchains still write
# their comparable renders to one place.
DEFAULT_OUT = os.path.join(HERE, '..', 'freecad', 'out', 'preview')


def combinations(family='bulkhead'):
    """One family's parameter space. Kept for `export_parameters.py`, which imports it."""
    return fv.family_combinations(family)


def settings():
    """Exactly what run_bulkhead_parametric_sweep() uses."""
    printer = fv.null_printer_settings()
    printer.extrusion_width = 0.6
    return printer, 1.0                # printer_settings, FX


def main(argv):
    args = [a for a in argv if not a.endswith('.py')]
    printer, FX = settings()

    if len(args) < 3:
        print('%-14s %-6s %-14s %-10s %s'
              % ('family', 'U', 'type', 'panel', 'valid'))
        for family in sorted(fv.BULKHEAD_FAMILIES):
            for p in fv.family_combinations(family):
                dp = fv.derived_parameters(p['U'], FX, p, printer, True)
                print('%-14s %-6s %-14s %-10s %s'
                      % (family, p['U'], p['bulkhead_type_name'], p['panel_name'],
                         fv.family_is_valid(family, dp)))
        return 0

    want_u, want_type, want_panel = float(args[0]), args[1], args[2]
    out = args[3] if len(args) > 3 else DEFAULT_OUT

    family = fv.family_of(want_type)
    if family is None:
        print('no bulkhead type named %r -- run with no arguments to list them'
              % want_type)
        return 1
    spec = fv.BULKHEAD_FAMILIES[family]

    for p in fv.family_combinations(family):
        if (float(p['U']) != want_u or p['bulkhead_type_name'] != want_type
                or p['panel_name'] != want_panel):
            continue

        dp = fv.derived_parameters(p['U'], FX, p, printer, True)
        valid = fv.family_is_valid(family, dp)

        print('variant: %s U=%s %s panel=%s'
              % (family, p['U'], p['bulkhead_type_name'], p['panel_name']))
        print('  panel.thickness    = %s' % dp.panel.thickness)
        print('  panel.overlap      = %s' % dp.panel.overlap)
        print('  panel.offset       = %s   (derived, not chosen)' % dp.panel.offset)
        print('  bulkhead.thickness = %s' % dp.bulkhead.thickness)
        print('  corner.radius      = %s' % dp.corner.radius)
        print('  extrusion_width    = %s' % dp.printer.extrusion_width)
        if family == 'boom_bulkhead':
            b = dp.boom_bulkhead
            print('  boom.y_position    = %s' % b.y_position)
            print('  boom.z_position    = %s' % b.z_position)
            print('  boom.make_vert_web = %s' % b.make_vert_web)
            print('  boom.make_lower_web= %s' % b.make_lower_web)
        print('  validity check     = %s' % valid)

        if not valid:
            print('  NOT RENDERED -- the sweep would not generate this combination')
            return 1

        name = getattr(fv, spec['filename'])(dp)
        getattr(fv, spec['render'])(dp, out, name)
        print('  rendered -> %s' % os.path.normpath(os.path.join(out, name)))
        return 0

    print('no such combination -- run with no arguments to list them')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
