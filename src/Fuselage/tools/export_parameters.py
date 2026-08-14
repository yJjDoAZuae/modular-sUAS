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
    python export_parameters.py 1.0 center_single 3mm out.json

**A variant belongs to a bulkhead family, and the type name says which.** The frame bulkhead
and the boom bulkhead are separate sweeps off separate type axes, sharing the panel and size
axes and nothing else, so what a variant *is* differs between them: a frame variant is a
bulkhead and its matching corner, a boom variant is one part with eleven parameters the frame
bulkhead has never heard of. The families are described in `fuselage_variants.BULKHEAD_
FAMILIES` and looked up here rather than restated -- see `render_variant.py` for the same
lookup on the rendering side.

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

from render_variant import settings


# The mappings live in `fuselage_variants`, beside the render functions that use them, and
# are re-exported here rather than restated. They were duplicated when this file was
# written, which is exactly the divergence a port is most likely to introduce and least
# likely to notice: both copies keep producing a part, and only the *values* drift.
# IP-FC-10 made the sweep drive FreeCAD from these same mappings, so there is now one
# definition feeding the OpenSCAD call, the FreeCAD build and this export.
bulkhead_parameters = fv.bulkhead_parameters
corner_parameters = fv.corner_parameters
boom_bulkhead_parameters = fv.boom_bulkhead_parameters


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


# The tables one variant of each family exports, as
# (JSON key, OpenSCAD module, its file, the mapping, the flags the generators carry
#  themselves, whether the corner's parameter object is the source).
#
# The JSON key is what `freecad/parameters.py` and `build_part.py` read the table back by,
# and each part kind names exactly one of them in `part_kinds.KINDS`. `boom_parameters` is
# separate from `parameters` rather than reusing it because the two describe different parts:
# a boom bulkhead seeded from a frame bulkhead's table would take every boom row from its
# module literals and build the reference configuration under the swept part's name.
TABLES = {
    'bulkhead': [
        ('parameters', 'bulkhead_section_full', 'fuselage_bulkhead_geometry.scad',
         'bulkhead_parameters', {'is_interconnect', 'is_cowling', 'make_web'}, False),
        ('corner_parameters', 'fuselage_corner', 'fuselage_corner_geometry.scad',
         'corner_parameters', set(), True),
    ],
    'boom_bulkhead': [
        # No flags exempted: `boom_bulkhead` takes all 25 of its parameters from the
        # mapping, the two boolean ones included, because the FreeCAD port reads them as
        # sheet rows rather than as a branch chosen at the call site.
        ('boom_parameters', 'boom_bulkhead', 'fuselage_boom_bulkhead_geometry.scad',
         'boom_bulkhead_parameters', set(), False),
    ],
}


def check_names(family, dp, dp_corner):
    """Assert each mapping is exactly its module's parameter list, minus the flags the
    generators carry themselves. A silent mismatch here would put a stale alias into every
    generated sheet."""
    for _key, module, scad, mapping, flags, from_corner in TABLES[family]:
        accepted = scad_module_parameters(scad, module)
        ours = set(globals()[mapping](dp_corner if from_corner else dp))
        unknown = ours - accepted
        if unknown:
            raise RuntimeError('not parameters of %s: %s'
                               % (module, ', '.join(sorted(unknown))))
        missing = accepted - ours - flags
        if missing:
            raise RuntimeError('%s takes parameters this export does not carry: %s'
                               % (module, ', '.join(sorted(missing))))


def resolve(family, want_u, want_type, want_panel):
    """The variant's parameter objects, from one combination of its family's axes.

    The corner is resolved alongside the frame bulkhead -- the same row of the parameter
    space, resolved twice, exactly as the two sweeps do it and as fuselage_splode.py does
    when it needs a matched pair. It is resolved for the boom family too and simply not
    exported: a boom bulkhead has no corner of its own, because the corner is a frame part
    and does not vary with where the boom sits.

    Validity is whatever the family declares, which for the boom bulkhead is two checks
    rather than one.
    """
    printer, FX = settings()
    for p in fv.family_combinations(family):
        if (float(p['U']) != want_u or p['bulkhead_type_name'] != want_type
                or p['panel_name'] != want_panel):
            continue
        p = dict(p, FX=FX)
        dp = fv.derived_parameters(p['U'], FX, p, printer, True)
        dp_corner = fv.derived_parameters(p['U'], FX, p, printer, False)
        return p, dp, dp_corner, fv.family_is_valid(family, dp)
    return None, None, None, None


def main(argv):
    args = [a for a in argv if not a.endswith('.py')]

    if len(args) < 3:
        print('usage: export_parameters.py U TYPE PANEL [out.json]')
        print('run render_variant.py with no arguments to list the combinations')
        return 0

    want_u, want_type, want_panel = float(args[0]), args[1], args[2]
    out = args[3] if len(args) > 3 else None

    family = fv.family_of(want_type)
    if family is None:
        print('no bulkhead type named %r -- run render_variant.py to list them'
              % want_type)
        return 1

    p, dp, dp_corner, valid = resolve(family, want_u, want_type, want_panel)
    if p is None:
        print('no such combination -- run render_variant.py to list them')
        return 1

    check_names(family, dp, dp_corner)

    doc = {
        'family': family,
        'variant': {'U': p['U'], 'bulkhead_type_name': p['bulkhead_type_name'],
                    'panel_name': p['panel_name']},
        'valid': bool(valid),
        'units': 'mm and degrees, as the OpenSCAD path uses them',
        'source': 'derived_parameters() via export_parameters.py -- do not hand-edit',
    }

    if family == 'bulkhead':
        bulkhead = bulkhead_parameters(dp)
        corner = corner_parameters(dp_corner)
        check_agreement(bulkhead, corner)

        # U and FX on top, exactly as the sweep's FreeCAD branches add them, and after
        # check_names -- neither is a parameter of the OpenSCAD modules, which take the
        # finished dimensions, so check_names would rightly refuse them.
        #
        # The FreeCAD sheets need them because the port states `corner_radius`,
        # `longeron_radius` and `unit_length` as relationships in U and FX rather than as
        # numbers. Without them those rows evaluate at U=1, FX=1 and the part is built to
        # the wrong size with the right parameter file sitting beside it (IP-FC-48).
        # `check_seed` in build_part.py refuses that now, so an export missing these does not
        # silently produce a wrong part -- it produces no part, which is why this belongs
        # here and not only in the sweep.
        #
        # The boom bulkhead below adds none of these, and that is not an oversight: its
        # modules state `corner_radius` and `longeron_radius` as literals seeded from this
        # export, so nothing on its sheet reads U, and it has no `unit_length`, no greeble
        # and no bay length at all.
        #
        # **`FX` is deliberately NOT here, and neither is `greeble_tolerance`.** Both were
        # added earlier on 2026-08-14, on the reasoning that a design parameter is still a
        # design parameter where one backend's function signature omits it. That was the
        # wrong diagnosis. A bulkhead is independent of bay length (OQ-DES-C3), so FX is not
        # a parameter *of a bulkhead* at all -- there is no `dp.bulkhead.FX` field, which is
        # that decision written into the data model. It reaches the FreeCAD bulkhead's sheet
        # only because `bulkhead_section` merges `corner_tree.PARAMS` to reuse `corner_end`,
        # and it arrives with `unit_length` and `mid_h` in tow.
        #
        # Measured rather than argued: set FX to 7.0 on a built bulkhead's sheet, recompute,
        # and the volume is unchanged to the last digit -- as it is for `unit_length`,
        # `greeble_tolerance`, `mid_h` and `mid_z0`. No bulkhead geometry reads any of them.
        # The post is formed by the greeble *tool*, whose clearance is the separate
        # `gt_tolerance` row and is always 0.
        #
        # Exporting a value for a row nothing reads would assert that a bulkhead has an FX,
        # which is the claim OQ-DES-C3 settled the other way. The fix is to stop those rows
        # reaching the sheet (IP-FC-56), not to feed them.
        bulkhead = dict(bulkhead, U=dp.bulkhead.U)
        corner = dict(corner, FX=dp_corner.corner.FX)
        doc['parameters'] = {k: float(v) for k, v in sorted(bulkhead.items())}
        doc['corner_parameters'] = {k: float(v) for k, v in sorted(corner.items())}
    else:
        boom = boom_bulkhead_parameters(dp)
        doc['boom_parameters'] = {k: float(v) for k, v in sorted(boom.items())}

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
