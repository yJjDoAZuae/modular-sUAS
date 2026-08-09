"""IP-FC-41: resolve a variant's parameters and hand them to FreeCAD as data.

`derived_parameters()` is the authority on what a variant's parameters are -- see
`render_variant.py` for why nothing else may be used to render one. But it lives here, in the
project virtualenv, and FreeCAD ships its own Python that cannot import `solid2`. So the
FreeCAD generators cannot call it directly, and up to now each of them carried literals
instead: fine while a module is only compared against an isolated reference at matching
inputs, wrong the moment the generator feeds the sweep.

This is the hop across that boundary. It resolves a variant exactly as `render_variant.py`
does and writes the flat parameter set as JSON; `freecad/parameters.py` reads it back and
seeds the spreadsheet from it. The parameter set crosses as *data*, so there is one authority
and no second copy of the design intent.

**The names are checked, not assumed.** The flat names below have to match what
`bulkhead_section_full` actually accepts, and that is asserted against the module's own
signature rather than trusted -- a renamed or dropped OpenSCAD parameter would otherwise
surface as a FreeCAD alias that silently no longer corresponds to anything.

    python export_parameters.py                          # list the variants
    python export_parameters.py 1.0 end_bolt 3/16in out.json

Values are millimetres and degrees, as the OpenSCAD path uses them.
"""
import re
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)                         # the CSV axes resolve relative to this directory

import fuselage_variants as fv

from render_variant import combinations, settings


def flat_parameters(dp):
    """The same mapping bulkhead_render() applies when it calls bulkhead_section_full."""
    return {
        'unit_width': dp.bulkhead.width,
        'bulkhead_thickness': dp.bulkhead.thickness,
        'corner_radius': dp.corner.radius,
        'panel_thickness': dp.panel.thickness,
        'panel_offset': dp.panel.offset,
        'panel_overlap': dp.panel.overlap,
        'panel_tolerance': dp.panel.tolerance,
        'longeron_radius': dp.longeron.radius,
        'longeron_tolerance': dp.longeron.tolerance,
        'bolt_hole_radius': dp.bolt.radius,
        'bolt_thickness': dp.bolt.thickness,
        'bolt_offset': dp.bolt.offset,
        'greeble_opening_angle': dp.greeble.opening_angle,
        'greeble_thickness': dp.greeble.thickness,
        'greeble_nub_thickness': dp.greeble.nub_thickness,
        'plate_thickness': dp.plate.thickness,
        'web_fillet_radius': dp.web.fillet_radius,
        'web_width': dp.web.width,
        'flange_fillet_radius': dp.bulkhead_flange.fillet_radius,
        'flange_thickness': dp.bulkhead_flange.thickness,
        'flange_chamfer': dp.bulkhead_flange.chamfer,
        'cowl_flange_height': dp.cowl_flange.height,
        'cowl_flange_tolerance': dp.cowl_flange.tolerance,
        'extrusion_width': dp.printer.extrusion_width,
    }


def scad_module_parameters(scad_name, module_name):
    """The parameter names of an OpenSCAD module, read from the source.

    Not from `inspect.signature` of the solid2 import: solid2 wraps every imported module
    behind a generic signature, so introspecting it reports nothing useful and -- worse --
    would report *every* name as unknown, which reads like a real failure.
    """
    path = os.path.join(fv.SCAD_DIR, scad_name)
    with open(path) as f:
        source = f.read()
    match = re.search(r'\bmodule\s+%s\s*\((.*?)\)\s*\{' % re.escape(module_name),
                      source, re.S)
    if not match:
        raise RuntimeError('no module %s in %s' % (module_name, scad_name))
    names = []
    for arg in match.group(1).split(','):
        arg = arg.split('=')[0].strip()
        if arg:
            names.append(arg)
    return set(names)


def check_names(flat):
    """Assert the flat names are exactly bulkhead_section_full's, minus the flags the
    generators carry themselves. A silent mismatch here would put a stale alias into every
    generated sheet."""
    accepted = scad_module_parameters('fuselage_bulkhead_geometry.scad',
                                      'bulkhead_section_full')
    ours = set(flat)
    unknown = ours - accepted
    if unknown:
        raise RuntimeError('not parameters of bulkhead_section_full: %s'
                           % ', '.join(sorted(unknown)))
    missing = accepted - ours - {'is_interconnect', 'is_cowling', 'make_web'}
    if missing:
        raise RuntimeError('bulkhead_section_full takes parameters this export does not '
                           'carry: %s' % ', '.join(sorted(missing)))


def resolve(want_u, want_type, want_panel):
    printer, FX = settings()
    for p in combinations():
        if (float(p['U']) != want_u or p['bulkhead_type_name'] != want_type
                or p['panel_name'] != want_panel):
            continue
        dp = fv.derived_parameters(p['U'], FX, p, printer, True)
        return p, dp, fv.bulkhead_validity_check(dp)
    return None, None, None


def main(argv):
    args = [a for a in argv if not a.endswith('.py')]

    if len(args) < 3:
        print('usage: export_parameters.py U TYPE PANEL [out.json]')
        print('run render_variant.py with no arguments to list the combinations')
        return 0

    want_u, want_type, want_panel = float(args[0]), args[1], args[2]
    out = args[3] if len(args) > 3 else None

    p, dp, valid = resolve(want_u, want_type, want_panel)
    if p is None:
        print('no such combination -- run render_variant.py to list them')
        return 1

    flat = flat_parameters(dp)
    check_names(flat)

    doc = {
        'variant': {'U': p['U'], 'bulkhead_type_name': p['bulkhead_type_name'],
                    'panel_name': p['panel_name']},
        'valid': bool(valid),
        'units': 'mm and degrees, as the OpenSCAD path uses them',
        'source': 'derived_parameters() via export_parameters.py -- do not hand-edit',
        'parameters': {k: float(v) for k, v in sorted(flat.items())},
    }

    text = json.dumps(doc, indent=2, sort_keys=False)
    if out:
        with open(out, 'w') as f:
            f.write(text + '\n')
        print('wrote %s' % os.path.normpath(os.path.abspath(out)))
    else:
        print(text)

    if not valid:
        print('NOTE: the sweep would not generate this combination', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
