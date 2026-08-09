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


def bulkhead_parameters(dp):
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


def corner_parameters(dp):
    """The same mapping corner_render() applies when it calls fuselage_corner.

    Two of these are the corner's alone. `unit_length` is bay length, which the bulkhead
    genuinely does not have -- one bulkhead design serves every FX, see OQ-DES-C3. And
    `greeble_tolerance` is the fit clearance, which the corner carries in its bore and the
    bulkhead's post is built without, because split across both halves the joint would take
    it twice. Neither is a name the bulkhead export forgot; both are asymmetries of the
    design, so the corner needs its own mapping rather than a wider one.
    """
    return {
        'U': dp.bulkhead.U,
        'unit_length': dp.corner.length,
        'bulkhead_thickness': dp.bulkhead.thickness,
        'corner_radius': dp.corner.radius,
        'panel_thickness': dp.panel.thickness,
        'panel_offset': dp.panel.offset,
        'panel_overlap': dp.panel.overlap,
        'panel_tolerance': dp.panel.tolerance,
        'longeron_radius': dp.longeron.radius,
        'longeron_tolerance': dp.longeron.tolerance,
        'greeble_thickness': dp.greeble.thickness,
        'greeble_nub_thickness': dp.greeble.nub_thickness,
        'greeble_tolerance': dp.greeble.tolerance,
        'extrusion_width': dp.printer.extrusion_width,
    }


# Names both parts take. They describe the same joint from its two sides and must agree
# on every one of them -- except `greeble_tolerance`, which is the asymmetry the joint is
# built on: the corner carries the whole fit clearance in its bore and the bulkhead's post
# is nominal, because split across both halves the joint would take it twice.
ASYMMETRIC = {'greeble_tolerance'}


def check_agreement(bulkhead, corner):
    """Refuse a variant where the two halves disagree on a shared parameter.

    They are resolved separately -- `derived_parameters(..., is_bulkhead)` branches on that
    flag -- so this is a real check, not an identity. It is what caught the first attempt at
    this export reading the corner's parameters off a bulkhead variant, where
    `greeble.tolerance` is 0 and the corner's bore would have come out with no clearance at
    all.
    """
    for name in sorted(set(bulkhead) & set(corner) - ASYMMETRIC):
        if abs(float(bulkhead[name]) - float(corner[name])) > 1e-12:
            raise RuntimeError(
                '%s is %r for the bulkhead and %r for the corner -- the two halves of the '
                'joint disagree' % (name, bulkhead[name], corner[name]))


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


# module -> (file, its own mapping, the flags the generators carry themselves)
CHECKED_MODULES = [
    ('bulkhead_section_full', 'fuselage_bulkhead_geometry.scad', 'bulkhead_parameters',
     {'is_interconnect', 'is_cowling', 'make_web'}),
    ('fuselage_corner', 'fuselage_corner_geometry.scad', 'corner_parameters', set()),
]


def check_names(dp, dp_corner):
    """Assert each mapping is exactly its module's parameter list, minus the flags the
    generators carry themselves. A silent mismatch here would put a stale alias into every
    generated sheet."""
    for module, scad, mapping, flags in CHECKED_MODULES:
        accepted = scad_module_parameters(scad, module)
        ours = set(globals()[mapping](dp_corner if mapping == 'corner_parameters'
                                      else dp))
        unknown = ours - accepted
        if unknown:
            raise RuntimeError('not parameters of %s: %s'
                               % (module, ', '.join(sorted(unknown))))
        missing = accepted - ours - flags
        if missing:
            raise RuntimeError('%s takes parameters this export does not carry: %s'
                               % (module, ', '.join(sorted(missing))))


def resolve(want_u, want_type, want_panel):
    """The variant's bulkhead and corner parameter objects, from one combination.

    Both come from the same row of the parameter space, resolved twice -- exactly as the two
    sweeps do it, and as fuselage_splode.py does when it needs a matched pair.
    """
    printer, FX = settings()
    for p in combinations():
        if (float(p['U']) != want_u or p['bulkhead_type_name'] != want_type
                or p['panel_name'] != want_panel):
            continue
        p = dict(p, FX=FX)
        dp = fv.derived_parameters(p['U'], FX, p, printer, True)
        dp_corner = fv.derived_parameters(p['U'], FX, p, printer, False)
        return p, dp, dp_corner, fv.bulkhead_validity_check(dp)
    return None, None, None, None


def main(argv):
    args = [a for a in argv if not a.endswith('.py')]

    if len(args) < 3:
        print('usage: export_parameters.py U TYPE PANEL [out.json]')
        print('run render_variant.py with no arguments to list the combinations')
        return 0

    want_u, want_type, want_panel = float(args[0]), args[1], args[2]
    out = args[3] if len(args) > 3 else None

    p, dp, dp_corner, valid = resolve(want_u, want_type, want_panel)
    if p is None:
        print('no such combination -- run render_variant.py to list them')
        return 1

    check_names(dp, dp_corner)
    bulkhead = bulkhead_parameters(dp)
    corner = corner_parameters(dp_corner)
    check_agreement(bulkhead, corner)

    doc = {
        'variant': {'U': p['U'], 'bulkhead_type_name': p['bulkhead_type_name'],
                    'panel_name': p['panel_name']},
        'valid': bool(valid),
        'units': 'mm and degrees, as the OpenSCAD path uses them',
        'source': 'derived_parameters() via export_parameters.py -- do not hand-edit',
        'parameters': {k: float(v) for k, v in sorted(bulkhead.items())},
        'corner_parameters': {k: float(v) for k, v in sorted(corner.items())},
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
