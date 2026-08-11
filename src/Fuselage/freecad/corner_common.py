"""IP-FC-5: shared parameters and the corner's 2D section, in Part:: primitives.

`corner_middle_shape` is the one profile every axial section of the corner extrudes -- the
middle run, the two ends and the two transitions all start from it. It is factored out here
for the same reason it is a separate module in the OpenSCAD source.

Everything is built as 3D prisms rather than 2D faces: each cut in the profile is a prism of
constant cross-section, so extruding first and differencing in 3D gives the same result with
fewer 2D-boolean edge cases.

Parameters are a value object rather than module constants, so a regenerate is a new
`Params(U=...)` and a re-run -- the Part:: paradigm has no stored feature tree to update.
"""
import os
import sys

import FreeCAD as App
import Part

# Everything these scripts write goes here, and nothing here is source. The scripts used to
# save beside themselves, which put `.FCStd` documents, their rotating `.FCStd1` backups,
# `.step` exports, check meshes and a whole `preview/` tree into the source directory --
# and two of them into git, where a 440 KB binary was rewritten on every check run.
#
# One directory rather than a system temp dir, because several of these are a producer and a
# consumer that have to agree: check_tree.py writes `regen_U*.stl` for check_regenerate.py,
# pd_end.py writes the document verify_pd_end.py reloads. A path that vanishes between runs
# would break those pairs, and being able to open the artifact after a failed check is most
# of what makes these scripts useful.
_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')


def out_path(*parts):
    """A path under `freecad/out/`, with the directory created. Never beside the source."""
    path = os.path.join(_OUT_DIR, *parts)
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    return path


# Only unit_width, unit_length, corner_radius and longeron_radius scale with U; the
# thicknesses, overlaps and tolerances are user parameters that do not. See
# scaled_standard_values() in fuselage_variants.py and the "1.0U parameters" block in
# fuselage_corner.scad.


class Params(object):
    def __init__(self, U=1.0, FX=1.0, bulkhead_thickness=6.0, panel_thickness=4.77,
                 panel_offset=0.0, panel_overlap=4.0, panel_tolerance=0.1,
                 longeron_tolerance=0.05, greeble_thickness=0.8, greeble_tolerance=0.05,
                 extrusion_width=0.4, greeble_nub_thickness=None):
        self.U, self.FX = U, FX
        self.unit_length = 100.0 * U * FX
        self.corner_radius = 10.0 * U
        self.longeron_radius = 2.0 * U

        self.bulkhead_thickness = bulkhead_thickness
        self.panel_thickness = panel_thickness
        self.panel_offset = panel_offset
        self.panel_overlap = panel_overlap
        self.panel_tolerance = panel_tolerance
        self.longeron_tolerance = longeron_tolerance
        self.greeble_thickness = greeble_thickness
        self.greeble_tolerance = greeble_tolerance
        self.extrusion_width = extrusion_width
        # greeble_nub_thickness_of() is the identity today; the driver sets them equal.
        self.greeble_nub_thickness = (greeble_thickness if greeble_nub_thickness is None
                                      else greeble_nub_thickness)

        self.eps = 0.01                              # geometry_eps()
        self.longeron_chamfer = extrusion_width
        self.far = 2.0 * self.corner_radius          # mask_reach()

        # greeble derived values (fuselage_corner_geometry.scad)
        self.greeble_radius = (self.longeron_radius + longeron_tolerance
                               + greeble_thickness + greeble_tolerance)
        self.greeble_nub_radius = self.greeble_radius + self.greeble_nub_thickness
        self.greeble_nub_height = bulkhead_thickness / 3.0

        # flat_offset uses longeron_chamfer as a floor, so the flat face clears the bore
        # and its chamfer *and* whatever the panel interface has been pushed out to.
        self.flat_offset = -max(
            self.longeron_radius + longeron_tolerance + self.longeron_chamfer,
            (panel_overlap + panel_offset)
            - (self.corner_radius - panel_thickness - panel_tolerance))
        self.flat_x = -(panel_overlap + panel_offset)
        self.flat_y = self.flat_offset - self.flat_x


def through_cut(extent):
    """Length for a *centred* cutting solid that must pass entirely through `extent`."""
    return 3.0 * extent


def is_entry_point(name):
    """True when `name` is the module freecadcmd was handed on the command line.

    `if __name__ == '__main__'` does not work under freecadcmd: it *imports* the script as
    a module named after the file's basename, so __name__ is 'part_end', never '__main__',
    and the guard silently suppresses the whole script. Compare against argv instead.
    """
    if name == '__main__':
        return True
    for arg in sys.argv:
        if arg.endswith('.py') and os.path.splitext(os.path.basename(arg))[0] == name:
            return True
    return False


def script_args():
    """The arguments meant for the script, with freecadcmd's own tokens removed.

    Two things have to come out of `sys.argv`. The script paths, because freecadcmd puts the
    file it is running there. And `--pass`, which is freecadcmd's escape for arguments meant
    for the script rather than for itself -- it forwards the token *as well as* the value, so
    a script that filters only `.py` reads the flag as its first argument.

    That failure is quiet in the worst way: the run dies on a file-not-found naming `--pass`,
    which reads like a malformed command line rather than like the script ignoring a flag it
    was handed. Six scripts had their own copy of this filter and five of them had this bug,
    so it is stated once here.
    """
    return [a for a in sys.argv[1:] if a != '--pass' and not a.endswith('.py')]


def is_literal(value):
    """True when a PARAMS row carries a plain number rather than an expression.

    The distinction is the whole of IP-FC-41: literal rows are *configuration* -- one
    variant's parameter values -- and belong to `derived_parameters()`. '=' rows are the
    *port*: the relationships the OpenSCAD source defines between those values, which no
    parameter set can supply and which have to agree between modules.
    """
    text = str(value).strip()
    if text.startswith('='):
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def seeded(params, seed=None):
    """`params` with its literal rows replaced by the exported parameter set.

    A row is only replaced when the authority actually defines it. `eps`, `U` and `FX` are
    literals no variant carries -- geometry_eps() is a constant of the source, not a
    parameter -- so they stay as written rather than silently becoming zero.
    """
    if not seed:
        return list(params)
    out = []
    for alias, value in params:
        if is_literal(value) and alias in seed:
            out.append((alias, repr(float(seed[alias]))))
        else:
            out.append((alias, value))
    return out


def build_sheet(doc, params, seed=None, extra=()):
    """The parameter sheet, seeded from `derived_parameters()` when `seed` is given.

    Left alone if the document already has one: the assembly builds a single merged sheet
    and then calls each constituent's geometry against it.
    """
    sheet = doc.getObject('Params')
    if sheet is not None:
        return sheet
    sheet = doc.addObject('Spreadsheet::Sheet', 'Params')
    for row, (alias, value) in enumerate(seeded(list(params) + list(extra), seed), start=1):
        sheet.set('A%d' % row, alias)
        sheet.setAlias('B%d' % row, alias)
        sheet.set('B%d' % row, value)
    doc.recompute()
    return sheet


def merge_params(sources, seed=None):
    """The union of several modules' alias tables, with conflicting definitions refused.

    Kept as a permanent assertion rather than a one-off audit, because the failure is
    silent: FreeCAD would take whichever definition landed in the row and the geometry
    would quietly follow the wrong one.

    A seed exempts the rows it supplies. Two modules disagreeing on what `panel_offset` is
    stops meaning anything once both take it from the same authority -- but disagreeing on
    a '=' row still does, and so does disagreeing on a literal the authority never defines.

    Where one module states a relationship and another states this variant's value --
    `corner_radius` is `=U * 10` in corner_tree and 10.0 in the bulkhead modules -- the
    RELATIONSHIP wins. Both are true, but only one of them survives the user changing U,
    and a sheet whose corner_radius stops tracking U is a worse deliverable than one whose
    rows are redundant. `check_seed` then confirms the expression reproduces the authority's
    number, which is a stronger check than either row on its own: it tests the port's
    derivations against `derived_parameters()`, not just its constants.
    """
    merged, at, owner = [], {}, {}
    for mod in sources:
        for alias, value in mod.PARAMS:
            if alias not in owner:
                owner[alias], at[alias] = (mod, value), len(merged)
                merged.append((alias, value))
                continue
            prev_mod, prev_value = owner[alias]
            if prev_value == value:
                continue
            if seed and alias in seed:
                if is_literal(prev_value) and not is_literal(value):
                    owner[alias] = (mod, value)
                    merged[at[alias]] = (alias, value)
                if is_literal(prev_value) != is_literal(value) or is_literal(value):
                    continue
            raise RuntimeError(
                'alias %r means two different things: %r in %s, %r in %s -- rename one '
                'before they share a sheet'
                % (alias, prev_value, prev_mod.__name__, value, mod.__name__))
    return merged


def check_seed(sheet, seed):
    """Every seeded alias the sheet carries, against the value the authority gave.

    Rows the seed replaced are trivially equal. The ones that matter are the expression
    rows kept in preference to a literal: this is where a derivation the port transcribed
    from the OpenSCAD source is measured against what `derived_parameters()` computes.
    """
    bad = []
    for alias in sorted(seed):
        try:
            got = float(sheet.get(alias))
        except Exception:
            continue                      # not an alias any module on this sheet declares
        if abs(got - float(seed[alias])) > 1e-9:
            bad.append((alias, got, float(seed[alias])))
    return bad


def prism(points, z0, h):
    """A polygon extruded through `h` starting at `z0`."""
    pts = [App.Vector(x, y, z0) for x, y in points]
    pts.append(pts[0])
    return Part.Face(Part.makePolygon(pts)).extrude(App.Vector(0, 0, h))


def half_shape(p, z0, h):
    """One half of the profile, before the diagonal mirror."""
    far = p.far
    solid = Part.makeCylinder(p.corner_radius, h, App.Vector(0, 0, z0))

    # rectangular extension carrying the panel interface outboard
    w = p.panel_overlap + p.panel_offset - p.panel_tolerance
    solid = solid.fuse(Part.makeBox(w, p.corner_radius, h, App.Vector(-w, 0, z0)))

    # longeron bore
    solid = solid.cut(Part.makeCylinder(p.longeron_radius + p.longeron_tolerance, h,
                                        App.Vector(0, 0, z0)))

    # panel slot
    solid = solid.cut(Part.makeBox(
        2 * p.panel_overlap, 2 * p.panel_thickness + 2 * p.panel_tolerance, h,
        App.Vector(-2 * p.panel_overlap - p.panel_offset + p.panel_tolerance,
                   p.corner_radius - p.panel_thickness - p.panel_tolerance, z0)))

    # bulkhead boundary
    solid = solid.cut(prism([
        (p.flat_x, p.corner_radius), (p.flat_x, p.flat_y), (p.flat_offset, 0),
        (0, p.flat_offset), (p.flat_y, p.flat_x), (0, -far), (-far, -far), (-far, far)],
        z0, h))

    # diagonal mirror-line mask
    solid = solid.cut(prism([(-far, -far), (far, far), (far, -far)], z0, h))

    # longeron chamfer
    solid = solid.cut(prism([(0, 0), (-far, 0), (-far, -far), (0, -far)], z0, h))
    return solid


def section(p, z0, h):
    """The full profile -- mirror_xy() of the half -- extruded from `z0` through `h`."""
    half = half_shape(p, z0, h)
    # mirror_xy(): mirror([1,-1,0]), i.e. reflect across the plane normal to (1,-1,0)
    full = half.fuse(half.mirror(App.Vector(0, 0, 0), App.Vector(1, -1, 0)))
    return full.removeSplitter()


def report(name, shape, ref_volume):
    """Print the comparison IP-FC-5 is built to make."""
    bb = shape.BoundBox
    print('PART:: %s' % name)
    print('  volume  = %.6f' % shape.Volume)
    print('  bbox    = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
          % (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    print('  valid   = %s   solids=%d faces=%d'
          % (shape.isValid(), len(shape.Solids), len(shape.Faces)))
    print('  ref     = %.6f  (OpenSCAD, faceted)' % ref_volume)
    d = shape.Volume - ref_volume
    print('  delta   = %+.6f  (%+.4f%%)' % (d, 100 * d / ref_volume))
