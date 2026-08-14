"""IP-FC-10: build one part from one parameter file, and write its mesh.

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


def write_mesh(shape, out_path):
    """Mesh a shape at the stated deflection and write it as binary STL.

    `Shape.exportStl` is not used: it meshes at whatever deviation the document carries,
    which is a preference rather than a decision, so two machines could produce different
    STLs from the same model. MeshPart takes the deflection as an argument.
    """
    import MeshPart

    mesh = MeshPart.meshFromShape(Shape=shape,
                                  LinearDeflection=LINEAR_DEFLECTION,
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

    facets = write_mesh(shape, opt['out'])
    print('%s  %.6f mm3  %d facets  -> %s'
          % (opt['kind'], shape.Volume, facets, os.path.basename(opt['out'])))

    if opt.get('fcstd'):
        # UC-2 wants the parametric document, not just its mesh. Written here when asked so
        # the sweep can produce both in one build; IP-FC-14 is what turns it on by default.
        doc.saveAs(opt['fcstd'])

    return 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
