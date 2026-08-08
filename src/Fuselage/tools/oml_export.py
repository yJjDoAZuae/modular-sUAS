"""Export the OML from the committed OpenVSP model, as surfaces rather than a mesh.

**Why this exists.** The cowls are built by importing a tessellated OML and cutting it,
which means a cowl can never be a true solid model: a mesh has no cylindrical face to
write into a STEP file, no surface for an assembly constraint to attach to, and no arc
for a drawing to dimension. UC-2, UC-3, UC-4 and UC-7 are all blocked for cowls until the
OML arrives as a surface. See doc/design/cowl.md and IP-FC-4.

It also replaces 36 MB of committed tessellation -- `vsp_nose.stl` is 12 MB and
`vsp_tail.stl` 24 MB -- with a serialization of a definition that is a few dozen control
points (doc/design/cowl.md section 1).

**Provenance.** The export is driven from the committed `.vsp3`, so the OML and the model
it came from cannot drift. Previously the export was performed by hand in the GUI and
nothing connected the two files -- see OQ-DES-CW7.

**Licensing.** OpenVSP is under the NASA Open Source Agreement v1.3, whose obligations
attach to *distribution* of the covered software rather than to linkage, so importing the
API imposes nothing on this project. See doc/guidelines/general.md.

Usage, from the repository root:

    uv run python src/Fuselage/tools/oml_export.py --list
    uv run python src/Fuselage/tools/oml_export.py --out src/Fuselage/oml
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

# The committed source model. This, not the exported geometry, is the definition.
VSP3 = _ROOT / 'cad' / 'modular_sUAS_nose_tail.vsp3'
OML_DIR = _ROOT / 'oml'

# OpenVSP ships its Python packages beside the application rather than on sys.path, and
# `openvsp` imports siblings (`degen_geom`, `openvsp_config`) that must be importable
# too. Located rather than hardcoded to one version so a FreeCAD/OpenVSP upgrade does
# not silently break the export.
_VSP_SIBLINGS = ('openvsp', 'degen_geom', 'openvsp_config', 'utilities')


def _vsp_python_roots():
    """Candidate OpenVSP python/ directories, newest version first."""
    bases = [Path(os.environ.get('OPENVSP_HOME', '')),
             Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs',
             Path(os.environ.get('ProgramFiles', 'C:/Program Files')),
             Path('C:/Program Files')]
    found = []
    for b in bases:
        if not b or not b.exists():
            continue
        if (b / 'python' / 'openvsp').exists():          # OPENVSP_HOME points at the install
            found.append(b / 'python')
        for child in b.glob('OpenVSP*'):
            if (child / 'python' / 'openvsp').exists():
                found.append(child / 'python')
    # newest by directory name, which embeds the version
    return sorted(set(found), key=lambda p: p.parent.name, reverse=True)


def import_vsp():
    """Import the OpenVSP API, or fail with a message that says what to do."""
    for root in _vsp_python_roots():
        for sib in _VSP_SIBLINGS:
            p = str(root / sib)
            if (root / sib).exists() and p not in sys.path:
                sys.path.insert(0, p)
        try:
            import openvsp as vsp
            return vsp, root
        except ImportError:
            continue
    raise SystemExit(
        'Could not import the OpenVSP Python API.\n'
        'Looked for an OpenVSP install under %%LOCALAPPDATA%%\\Programs and '
        '%%ProgramFiles%%.\n'
        'Set OPENVSP_HOME to the install directory if it is elsewhere.')


# Which geometry each exported file should contain. The Vehicle holds four parametric
# FuselageGeoms plus two MeshGeoms; the cowl generator consumes the nose and the tail.
# Named here rather than inferred so that a rename in the model is a loud failure.
EXPORTS = (
    ('vsp_nose', ('Nose',)),
    ('vsp_tail', ('Tail',)),
)

# The first user-definable set. Sets 0-2 are the built-in Shown/Highlighted/All, so
# writing to them would disturb the model's own display state.
USER_SET = 3


def _set_cad_len_unit(vsp, unit):
    """Set the CAD export length unit, failing loudly if the parm is not found.

    A silent miss here produces geometry that is wrong by a constant factor and valid in
    every other respect, so the absence of the parameter must not be tolerated.
    """
    # There is more than one CADLenUnit — the CFD-mesh and surface-intersect settings
    # each carry their own, and only one of them governs a given exporter. Set every
    # occurrence rather than guessing which; setting the first alone is a silent no-op.
    found = []
    for cid in vsp.FindContainers():
        for pid in vsp.FindContainerParmIDs(cid):
            if vsp.GetParmName(pid) == 'CADLenUnit':
                vsp.SetParmVal(pid, float(unit))
                found.append((vsp.GetContainerName(cid), pid))
    if found:
        vsp.Update()
        return [(name, float(vsp.GetParmVal(pid))) for name, pid in found]
    raise SystemExit(
        'CADLenUnit parameter not found. The export unit cannot be verified, and an '
        'unverified unit silently rescales every surface -- refusing to export.')


def list_model(vsp):
    """Report what the committed model contains, without exporting."""
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(VSP3))
    print('model: %s' % VSP3.name)
    for gid in vsp.FindGeoms():
        name = vsp.GetGeomName(gid)
        gtype = vsp.GetGeomTypeName(gid)
        n_xsec = ''
        try:
            surf = vsp.GetXSecSurf(gid, 0)
            n_xsec = '  stations=%d' % vsp.GetNumXSec(surf)
        except Exception:
            pass
        print('  %-14s %-14s%s' % (name, gtype, n_xsec))


def export(vsp, out_dir, fmt='step'):
    """Export each named geometry set as surfaces."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(VSP3))
    by_name = {vsp.GetGeomName(g): g for g in vsp.FindGeoms()}

    # The model stores CADLenUnit = LEN_FT, which is wrong for this airframe and scales
    # every exported surface by 1/3.28084. Nothing in the .vsp3 records the intended
    # unit; the airframe does. The OML's rounded-rectangle sections are 0.1 x 0.1 model
    # units and must equal `unit_width` = 100 mm at U = 1, so one model unit is one
    # metre -- which is also how the OpenSCAD path has always read it
    # (`scale = U/oml_scale` with `oml_scale = 1e-3`).
    #
    # Set on every export rather than corrected once in the .vsp3, so the result cannot
    # depend on a setting a GUI session might change back. Getting it wrong is silent:
    # the STEP still loads, still carries valid surfaces, and is simply 3.28x too small.
    for _c, _v in _set_cad_len_unit(vsp, vsp.LEN_M):
        print("  CADLenUnit[%s] = %g (LEN_M=%g)" % (_c, _v, vsp.LEN_M))

    ext = {'step': '.step', 'iges': '.igs'}[fmt]
    code = {'step': vsp.EXPORT_STEP, 'iges': vsp.EXPORT_IGES}[fmt]

    written = []
    for stem, wanted in EXPORTS:
        missing = [w for w in wanted if w not in by_name]
        if missing:
            raise SystemExit(
                'Geometry %s not found in %s. Present: %s\n'
                'The export names geometry explicitly so a rename in the model fails '
                'loudly rather than silently exporting the wrong thing.'
                % (missing, VSP3.name, sorted(by_name)))

        # Export one geometry set at a time by marking membership of a user set. Every
        # geom is set explicitly, True or False, so no separate clearing pass is needed
        # -- and SetSetFlag takes a geom ID, not a set constant.
        for g in vsp.FindGeoms():
            vsp.SetSetFlag(g, USER_SET, vsp.GetGeomName(g) in wanted)

        target = out_dir / (stem + ext)
        vsp.ExportFile(str(target), USER_SET, code)
        err = vsp.ErrorMgr.PopErrorAndPrint(False) if hasattr(vsp, 'ErrorMgr') else None
        if not target.exists():
            raise SystemExit('Export produced no file: %s (%s)' % (target, err))
        written.append(target)
        print('  %-12s -> %-22s %10d bytes' % (','.join(wanted), target.name,
                                               target.stat().st_size))
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--list', action='store_true',
                    help='report what the model contains and exit')
    ap.add_argument('--out', default=str(OML_DIR), help='output directory')
    ap.add_argument('--format', choices=('step', 'iges'), default='step')
    args = ap.parse_args(argv)

    if not VSP3.exists():
        raise SystemExit('Source model not found: %s' % VSP3)

    vsp, root = import_vsp()
    print('OpenVSP %s (%s)' % (vsp.GetVSPVersion(), root))

    if args.list:
        list_model(vsp)
        return 0

    print('exporting %s from %s' % (args.format.upper(), VSP3.name))
    export(vsp, args.out, args.format)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
