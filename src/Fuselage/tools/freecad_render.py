"""IP-FC-10: render a sweep part with FreeCAD instead of OpenSCAD.

The swap is smaller than it sounds, and that is the point of how the sweep was built. The
render queue submits a *command* plus a callback that runs on success, and it never knew
which binary it was running: the worker budget, the atomic write, the serial-retry recovery
and the preview pass all carry over untouched. What is genuinely backend-specific is only two
things -- what file *defines* a part, and what command turns that file into an STL.

    OpenSCAD   definition = the generated .stl.scad     command = openscad -o
    FreeCAD    definition = the exported .params.json   command = freecadcmd build_part.py

Keeping the definition on disk in both cases is what keeps `--resume` honest. A resume that
skipped on "the STL exists" would bake in stale parts after a parameter change; comparing the
definition it *would* write now against the one sitting there catches exactly the changes that
matter. The JSON plays the role the generated `.scad` played -- including, since IP-FC-11, a
digest of the geometry code, which neither file contains: the generated `.scad` turned out to
be a `use <>` line and a call, so the OpenSCAD path had the same blind spot all along and
both are stamped by the same module now.

FreeCAD is invoked per part, not per sweep. IP-FC-1 measured `freecadcmd` startup at 0.24 s
against a part that builds in about 0.5 s, so a process per part costs a few minutes across
the whole sweep and buys the same crash isolation the OpenSCAD path has: a part that brings
down its interpreter takes nothing else with it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil

import geometry_version

HERE = os.path.dirname(os.path.abspath(__file__))
FREECAD_DIR = os.path.normpath(os.path.join(HERE, '..', 'freecad'))
BUILDER = os.path.join(FREECAD_DIR, 'build_part.py')

# Where freecadcmd lives. Environment first so a machine with it elsewhere needs no edit.
ENV_VAR = 'FREECADCMD'
_DEFAULT_PATHS = [
    r'C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe',
    os.path.expandvars(r'%LOCALAPPDATA%\Programs\FreeCAD 1.1\bin\freecadcmd.exe'),
    '/usr/bin/freecadcmd',
    '/usr/local/bin/freecadcmd',
]

def _load_part_kinds():
    """`freecad/part_kinds.py`, loaded by path rather than by import.

    It sits in the FreeCAD directory because that is what it describes, and it is
    deliberately free of any FreeCAD import so this side can read it (IP-FC-45). Loaded by
    file location rather than by putting `freecad/` on `sys.path`: the sweep imports this
    module, and a path entry added here would let `freecad/parameters.py` shadow anything of
    the same name elsewhere in the project for the rest of the process.
    """
    spec = importlib.util.spec_from_file_location(
        'part_kinds', os.path.join(FREECAD_DIR, 'part_kinds.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PART_KINDS = _load_part_kinds()

# Sweep part kind -> the kind build_part.py knows. Only the ported parts appear here; a kind
# absent from this table has no FreeCAD generator yet and must keep using OpenSCAD.
# Note this is per *kind*: the frame bulkhead is here, but only its end type is ported, which
# `bulkhead_render` handles through `_backend_for(kind, supported=)` -- see IP-FC-47. The
# boom bulkhead needs no such gate, all three of its types being ported.
KINDS = tuple(sorted(_PART_KINDS.KINDS))


class FreeCADNotFound(RuntimeError):
    pass


def freecadcmd_path():
    """The freecadcmd executable, or raise saying how to point at it."""
    explicit = os.environ.get(ENV_VAR)
    if explicit:
        if not os.path.isfile(explicit):
            raise FreeCADNotFound('%s is set to %r, which does not exist'
                                  % (ENV_VAR, explicit))
        return explicit
    found = shutil.which('freecadcmd')
    if found:
        return found
    for path in _DEFAULT_PATHS:
        if os.path.isfile(path):
            return path
    raise FreeCADNotFound(
        'freecadcmd not found. Set %s to its full path, or put it on PATH. '
        'Looked in: %s' % (ENV_VAR, ', '.join(_DEFAULT_PATHS)))


def definition_text(kind, params, variant=None):
    """The JSON that defines this part, as text.

    Deterministic on purpose -- sorted keys, fixed indent, `repr` of a float. `--resume`
    compares this byte for byte against what is on disk, so any instability here, a dict
    iterating in a different order or a float formatted differently, would re-render parts
    that did not change and quietly make resume worthless.

    `kind` is inside the document rather than only in the filename: the corner and the
    bulkhead of one variant are two parts of the same parameter set, and a definition that
    did not say which would compare equal between them.

    `geometry` is IP-FC-11, and it is what makes the parameters sufficient. Parameters alone
    describe the *input* to a build; without a fingerprint of the code that consumes them, a
    resumed sweep after an edit to bulkhead_full.py finds every definition unchanged and
    skips every part that edit invalidated. The module list is written out beside the digest
    so a sweep that suddenly re-renders everything says why.
    """
    version, modules = geometry_version.freecad_version(
        _PART_KINDS.geometry_roots(kind), FREECAD_DIR)
    doc = {
        'kind': kind,
        'variant': variant or {},
        'units': 'mm and degrees, as the OpenSCAD path uses them',
        'source': 'derived_parameters() via fuselage_variants.py -- do not hand-edit',
        'geometry': {'version': version, 'modules': modules},
        'parameters': {k: float(v) for k, v in sorted(params.items())},
    }
    return json.dumps(doc, indent=2, sort_keys=False) + '\n'


def build_command(kind, params_path, stl_path, fcstd_path=None):
    """The argv that builds one part.

    Every argument goes behind freecadcmd's `--pass`. freecadcmd parses the command line
    before the script runs: an unrecognised `--flag` makes it print its own usage and exit
    without ever calling the script, and a bare positional it tries to open as a document --
    which on a `.json` fails inside the FEM mesh importer with "invalid literal for int() with
    base 10", an error naming neither FreeCAD nor the file's real problem, of which it has
    none. `--pass` takes exactly one argument, so the value has to be joined with `=`.
    """
    cmd = [freecadcmd_path(), BUILDER,
           '--pass', '--kind=%s' % kind,
           '--pass', '--params=%s' % params_path,
           '--pass', '--out=%s' % stl_path]
    if fcstd_path:
        cmd += ['--pass', '--fcstd=%s' % fcstd_path]
    return cmd
