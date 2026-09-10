"""IP-FC-10: build one part from one parameter file, and write its parametric document.

This is the FreeCAD counterpart of a single `openscad -o part.stl part.scad` invocation, and
it is deliberately shaped like one: one process, one part, one file in, one file out, an exit
code that means what it says. IP-FC-1 measured `freecadcmd` startup at 0.24 s against a
~0.5 s part, so subprocess-per-part is affordable and the sweep's existing queue -- which
submits *commands* and moves the result into place on success -- carries over unchanged.
Nothing about atomic writes, the worker budget, previews or the retry-serially recovery had
to be rewritten to accept a second backend; they never knew which binary they were running.

    freecadcmd build_part.py --kind bulkhead --params p.json --out part.stl

`--params` is what `tools/export_parameters.py` writes. It carries both tables, and the kind
selects which: seeding the corner from the bulkhead's table would build its bore with no fit
clearance at all (see `parameters.py`). That is why the kind is passed explicitly rather than
inferred from the file -- the file describes a *variant*, and a variant is two parts.

**The `.FCStd` is written by default, beside the mesh.** It is the reason this backend exists:
an editable, parametric document is the one thing the OpenSCAD path cannot produce, and every
downstream use case -- UC-2, the modelled non-printed components in IP-FC-18, the family
drawings in IP-FC-21 -- consumes the document, not the triangles. Saving it used to require an
explicit `--fcstd`, which nothing passed, so every invocation built the document in memory and
threw it away. `--fcstd=<path>` now only *relocates* it; there is no way to suppress it, and
none is wanted. (An empty `--fcstd=` cannot be the off switch even if one were: freecadcmd
parses it as an option of its own, prints its usage, and exits 0 without running the script.)

**The mesh is a setting, not a property of the model.** A B-rep has no triangles; the numbers
below decide how many. They are stated here, once, rather than left to whatever the FreeCAD
document happens to default to -- a default that varies with the GUI's preferences file would
make the sweep's output depend on the machine that ran it.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import FreeCAD as App

import corner_common
import parameters
import part_kinds
from corner_common import is_entry_point

# kind -> (module, which of the export's two tables it is seeded from). The pairing lives in
# part_kinds, which the driver side can also read -- see IP-FC-45. The table is named there
# and resolved here, because part_kinds must not import anything that imports FreeCAD.
KINDS = {kind: (module, getattr(parameters, table))
         for kind, (module, table) in part_kinds.KINDS.items()}

# Tessellation for the exported mesh. Chosen by measurement, not by taking the finest
# available: on `bulkhead_section_full` at U=1, against a B-rep volume of 6922.5127750 mm3,
#
#     linear   facets     STL volume      delta        (OpenSCAD, for scale:
#     1e-2      7 264   6922.7192046   +0.00298%         29 000 facets, -0.00011%)
#     3e-3     13 392   6922.5711638   +0.00084%
#     1e-3     26 304   6922.5291739   +0.00024%   <- here
#     1e-4     65 264   6922.4862676   -0.00038%
#     1e-5    173 408   6922.4794155   -0.00048%
#
# **Refining past 1e-3 makes agreement worse and then stops improving.** That floor is not
# the mesher: binary STL stores coordinates as float32, so a 45 mm part carries about 3e-6 mm
# of quantisation per vertex no matter how many vertices there are. Past ~26k facets the
# error is dominated by the file format, and the extra facets buy five times the meshing time
# and six times the file for a worse number. 1e-3 also lands within a facet count of the
# OpenSCAD reference, which keeps IP-FC-13 comparing geometry rather than mesh density.
#
# ANGULAR_DEFLECTION barely binds on these parts -- 0.5 and 5.0 produce identical meshes, and
# only at 0.05 does it start adding facets -- so the linear term is what is being set here.
LINEAR_DEFLECTION = 1.0e-3
ANGULAR_DEFLECTION = 0.5

# The cowls are the exception, and they need one. The table above was measured on a bulkhead,
# whose surfaces are planes, cylinders and cones -- shapes a mesher covers with few facets
# however tight the deflection. A cowl's surface is freeform over its whole area, so the same
# 1.0e-3 produced a 94 MB tail of 1 879 224 facets, against the OpenSCAD path's 18 MB and
# 89 910 for the same part. Multiplied across the sweep that is tens of gigabytes of
# tessellation for a part whose *definition* is a few dozen control points, which is the
# opposite of what IP-FC-4 set out to achieve.
#
# 0.02 mm is chosen to land near the OpenSCAD tessellation rather than to match it exactly:
# the two meshers do not agree facet for facet, and pretending otherwise would be a false
# precision. It is far finer than any printer resolves and, being only the *exported mesh*,
# it does not touch the B-rep the `.FCStd` carries -- which is the artifact that matters and
# is exact at any deflection.
#
# **This is not the acceptance measure.** That is `oml_blank.VOLUME_DEFLECTION`, which is
# 0.002 and is chosen by a different criterion entirely -- see OQ-DES-CW12.
#
# **It scales with `U`, decided 2026-09-06.** The figure below is the deflection at `U` = 1 and
# `export_deflection` multiplies it by the part's own `U`. A fixed 0.02 mm is a *shrinking*
# fraction of a growing part: at `U` = 4 the same part is four times the size and meshed four
# times as finely relative to itself, which costs facets nobody asked for and makes every
# comparison across `U` measure the export setting as much as the geometry. `compare_backends`
# records exactly that drift -- the tail's volume error falls 2.1e-04 to 1.5e-05 from `U` = 0.5
# to 4 -- and its own comment already called it worth removing. Scaling here is what makes a
# nondimensional comparison criterion `U`-invariant rather than merely dimensionless; see
# OQ-ARCH-20.
#
# **What this is not.** It is not scaled to make a comparison tolerance pass -- the export is
# chosen for printing and preview, and analysis of the B-rep is a separate concern that must
# never reach back into it. It is scaled because a part four times the size deserves the same
# fidelity *relative to itself*, which is the same rule OQ-ARCH-12 sets for every other
# tolerance in this project. At `U` = 1 nothing changes.
#
# **Scaled by `U`, not by the shape's bounding box.** `MeshPart` offers `Relative=True`, which
# divides the deflection by the shape's own bounding box -- and a nose and a tail at one `U`
# have different bounding boxes, so that would export two parts of the same family at two
# different absolute deflections. `U` is the family's scale and is carried in the parameter
# file, so it is the honest hook.
#
# **Deliberately not applied to `LINEAR_DEFLECTION` above.** That constant has a floor this
# argument does not reach: binary STL stores float32, so past about 26k facets the error is the
# file format rather than the mesher, and 1e-3 was also chosen to land within a facet count of
# the OpenSCAD reference so IP-FC-13 compares geometry and not mesh density. Scaling it would
# move both of those. The prismatic parts pass today; extending this to them is a separate
# question and needs its own measurement.
COWL_LINEAR_DEFLECTION = 0.02
COWL_KINDS = ('nose_cowl', 'nose_nose', 'tail', 'nose_cowl_shell', 'tail_shell')

# **`nose_plate` was here and it was a miscategorization, not a design choice -- IP-FC-136.**
# It reads like a cowl kind because `nose_render` builds it, but `cowl.nose_plate()` is three
# `Part.makeCylinder`/`Part.makeCone` calls fused and cut -- exactly the "planes, cylinders and
# cones" shape the comment above says a mesher covers cheaply at any deflection, not the
# freeform OpenVSP surface `COWL_LINEAR_DEFLECTION` exists for. Carrying it here anyway cost
# real accuracy: at `U` = 1 `COWL_LINEAR_DEFLECTION * U` = 0.02 mm gave a mesh 0.0148% off the
# part's own exact B-rep volume (2883.546217 mm3, read from the FCStd `compare_backends`
# `--keep` preserved), nearly three times `LINEAR_DEFLECTION`'s 0.001mm mesh (0.0007% off the
# same shape) -- and it was the reason `nose_plate` failed its own `TOL_EXACT` cross-backend
# check at `U` = 1, 2 and 3 while passing at `U` = 0.5, where the coarser deflection happened
# to still be fine enough. Re-meshed at `LINEAR_DEFLECTION` and re-measured against the same
# OpenSCAD reference: 0.00395%, 0.00452%, 0.00487%, 0.00496% at `U` = 0.5, 1, 2, 3 -- comfortably
# inside 0.006% at every one, where OpenSCAD's own fixed-resolution mesh was the entire
# remaining gap. Not a tolerance loosened to pass a check: the same tolerance, a part correctly
# excused from a coarsening it never needed.

# Do NOT reach for `Mesh.Volume` to check any of this. It accumulates in single precision and
# gets *worse* as the mesh gets finer: on the 173 408-facet mesh above it reports
# 6921.9243164, which is 0.55 mm3 -- twenty times the real tessellation error -- below what
# the same file measures at. That artefact reads exactly like a mesh too coarse to trust, and
# inverts the conclusion. Measure the written STL instead, which `measure.py` does in float64.


def load_seed(params_path, kind):
    """The alias -> value mapping for `kind`, from either shape of parameter file.

    Two things write these, and they are not the same document:

    - `tools/export_parameters.py` writes a **variant**, which is one or more parts under
      their own table names: a frame bulkhead variant carries `parameters` for the bulkhead
      and `corner_parameters` for the corner, a boom bulkhead variant carries
      `boom_parameters` and nothing else. Used interactively, and by every check script in
      this directory.
    - the sweep writes a **part**, which is one: a single flat `parameters` table with the
      `kind` stated alongside it, because at that point the choice has already been made.

    Reading both from here is what lets the same builder serve the sweep and a hand check of
    one variant, and lets a definition file the sweep produced be replayed by hand later --
    which is the first thing anyone will want when a swept part looks wrong.

    The two are told apart by `kind`, which only the sweep's document carries -- not by
    looking for `corner_parameters`, which the boom bulkhead's variant has no reason to
    contain. A variant then picks this part's table by name, and a name the file does not
    carry is refused rather than silently substituted; see `parameters.table_of`.
    """
    module_name, table = KINDS[kind]
    with open(params_path) as f:
        doc = json.load(f)
    if 'kind' not in doc:
        return parameters.seed(params_path, table)      # a variant: pick this part's table
    if doc['kind'] != kind:
        raise SystemExit('%s defines a %r, not a %r'
                         % (params_path, doc['kind'], kind))
    return dict(doc['parameters'])


def build(doc, kind, params_path):
    """The part's tip node, seeded from the exported parameter set.

    The finished sheet is checked against the seed, which is not a formality. Seeding
    replaces *literal* rows only: a row the port states as a relationship -- `unit_length` is
    `=U * FX * 100` in `corner_tree`, on purpose, so a generated document still follows a
    changed U -- keeps its expression and evaluates from whatever the sheet holds. If the
    seed does not supply everything that expression reads, the row quietly computes the
    wrong number from the module's own literals while the *correct* value sits unused in the
    parameter file two lines away.

    That is not hypothetical. `FX` was missing from the corner's seed, so `unit_length`
    evaluated at FX=1.0 and every corner in the sweep was built one bay length long,
    matching OpenSCAD exactly at FX=1.0 and by up to 115% elsewhere (IP-FC-48). `check_seed`
    is what makes the difference between a port that agrees with the authority and one that
    merely reads the same file, so it runs on every build rather than in a check script.
    """
    seed = load_seed(params_path, kind)
    module = __import__(KINDS[kind][0])
    tip = module.emit(doc, seed)

    bad = corner_common.check_seed(doc.getObject('Params'), seed)
    if bad:
        # Written to stderr and flushed, not raised as SystemExit(message). freecadcmd
        # discards the message either way -- a SystemExit carrying this text produced no
        # output at all, just a missing mesh -- and a refusal nobody can read is only
        # marginally better than the wrong part it prevented.
        sys.stderr.write(
            'build_part: %s: the sheet disagrees with the parameter file on %s\n%s\n'
            'An expression row is computing from values the seed did not supply. The part '
            'would be built to the wrong dimensions with nothing else to show for it.\n'
            % (kind, ', '.join(alias for alias, _, _ in bad),
               '\n'.join('  %-22s sheet %.9g   authority %.9g' % (a, got, want)
                         for a, got, want in bad)))
        sys.stderr.flush()
        raise SystemExit(1)
    return tip


def export_deflection(kind, seed):
    """The linear deflection this part is exported at, in millimetres.

    One place for the rule, because it is no longer a constant lookup: a cowl's figure scales
    with the part's `U` and every other kind's does not. See `COWL_LINEAR_DEFLECTION` above for
    why, and for why this is not applied to `LINEAR_DEFLECTION`.

    `U` comes from the parameter file, which carries it beside `unit_width` for every swept
    part. A seed without it -- a hand-written variant, say -- falls back to the `U` = 1 figure
    rather than guessing a scale, which is the same choice `mesh_stats.u_of_name` makes when a
    filename carries no `U`.
    """
    if kind not in COWL_KINDS:
        return LINEAR_DEFLECTION
    u = seed.get('U')
    return COWL_LINEAR_DEFLECTION * (float(u) if u is not None else 1.0)


def write_mesh(shape, out_path, deflection):
    """Mesh a shape at the stated deflection and write it as binary STL.

    `Shape.exportStl` is not used: it meshes at whatever deviation the document carries,
    which is a preference rather than a decision, so two machines could produce different
    STLs from the same model. MeshPart takes the deflection as an argument.

    **The deflection arrives already decided.** It used to be chosen in here from the kind,
    which hid a rule inside a mesher call; `export_deflection` states it instead, and this
    function does what its name says.

    `Relative=False` is deliberate: `Relative=True` would divide the deflection by the shape's
    own bounding box, which differs between a nose and a tail at the same `U`.
    """
    import MeshPart

    mesh = MeshPart.meshFromShape(Shape=shape,
                                  LinearDeflection=deflection,
                                  AngularDeflection=ANGULAR_DEFLECTION,
                                  Relative=False)
    mesh.write(out_path)
    return mesh.CountFacets


def parse(argv):
    """`--name=value` arguments, without argparse.

    **Each one has to arrive behind freecadcmd's `--pass`**, and that is not a style choice.
    freecadcmd parses the command line itself before the script ever runs: an unrecognised
    `--flag` makes it print its own usage and stop, and a bare positional it does not
    recognise it tries to *open as a document* -- which for a `.json` fails inside the FEM
    mesh importer with "invalid literal for int() with base 10", an error that reads like a
    corrupt parameter file and has nothing to do with one. `--pass` is the documented escape,
    it takes exactly one argument, and it survives into `sys.argv` verbatim:

        freecadcmd build_part.py --pass --kind=bulkhead --pass --params=p.json ...

    So the value must be joined to the name with `=`. The `--pass` tokens themselves come
    through too and are skipped here. Kept free of argparse so it imports under FreeCAD's
    Python, which is not the project virtualenv.
    """
    out = {}
    for arg in argv:
        if arg == '--pass' or arg.endswith('.py'):
            continue
        if not arg.startswith('--') or '=' not in arg:
            raise SystemExit('unexpected argument %r -- expected --name=value' % arg)
        name, _, value = arg[2:].partition('=')
        out[name] = value
    missing = {'kind', 'params', 'out'} - set(out)
    if missing:
        raise SystemExit('missing %s' % ', '.join(sorted('--' + m for m in missing)))
    if out['kind'] not in KINDS:
        raise SystemExit('unknown kind %r -- one of %s'
                         % (out['kind'], ', '.join(sorted(KINDS))))
    return out


def fcstd_path(opt):
    """Where the parametric document goes. Always somewhere -- it is never skipped.

    Defaults to the mesh's own path with the extension swapped, so the document lands beside
    the part it describes without every caller having to name it twice. `--out=x.partial.stl`
    gives `x.partial.FCStd`, which is what the sweep's partial-then-rename write wants -- it
    renames both on success, so a killed render leaves neither.
    """
    return opt.get('fcstd') or os.path.splitext(opt['out'])[0] + '.FCStd'


def main():
    opt = parse(sys.argv[1:])

    doc = App.newDocument('build')
    tip = build(doc, opt['kind'], opt['params'])
    doc.recompute()

    shape = tip.Shape
    problems = []
    if not shape.isValid():
        problems.append('invalid shape')
    if len(shape.Solids) != 1:
        problems.append('%d solids' % len(shape.Solids))
    if problems:
        # Loud, and non-zero. The sweep's atomic write means a failure here leaves no file
        # at the real path rather than a convincing broken one, so this must actually fail
        # rather than write a part nobody would look at twice.
        sys.stderr.write('build_part: %s: %s\n'
                         % (opt['kind'], '; '.join(problems)))
        sys.stdout.flush()
        return 1

    deflection = export_deflection(opt['kind'], load_seed(opt['params'], opt['kind']))
    facets = write_mesh(shape, opt['out'], deflection)

    # UC-2 wants the parametric document, not just its mesh -- and it is the *primary* output
    # of this backend, so it is written every time rather than only when asked (IP-FC-14). The
    # document is already built and recomputed by this point; saving it is the cheap part.
    fcstd = fcstd_path(opt)
    doc.saveAs(fcstd)

    # The deflection is printed because it is no longer a constant: a reader comparing two
    # runs at different `U` needs to see what each was meshed at without inferring it.
    print('%s  %.6f mm3  %d facets at %.5f mm  -> %s + %s'
          % (opt['kind'], shape.Volume, facets, deflection,
             os.path.basename(opt['out']), os.path.basename(fcstd)))

    return 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
