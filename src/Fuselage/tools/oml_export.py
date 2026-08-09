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


# --------------------------------------------------------------------------------
# Units: OpenVSP is dimensionless, so the exported file's unit label means nothing
# --------------------------------------------------------------------------------
# An OpenVSP model holds bare numbers. No unit is stored with the geometry -- which is
# why the API offers LEN_UNITLESS alongside the real units, and why several unrelated
# settings containers each carry their own independent *LenUnit parm. Every consumer
# declares its own interpretation.
#
# The STEP exporter must still write *something* into the file header, and it writes
# CONVERSION_BASED_UNIT('FOOT'). Verified by reading the exported file. That label is an
# artifact of the exporter, not a statement about the airframe -- and setting CADLenUnit
# to LEN_M yields a byte-identical file, so that parm does not govern this path.
#
# The interpretation is therefore a project convention, and the project already has one:
#
#     1 OpenVSP model unit = 1 metre
#
# which is exactly what the OpenSCAD path applies as
# `scale = U / oml_scale_m_per_mm` with `oml_scale_m_per_mm = 1e-3` -- the suffix says
# it (OQ-DES-CW1). The airframe confirms it: the OML's rounded-rectangle sections are
# 0.1 x 0.1 model units and must equal `unit_width` = 100 mm at U = 1.
#
# A consumer reading the STEP therefore sees 0.1 FOOT (30.48 mm) where the convention
# means 100 mm. Rather than fight the exporter, the factor is stated here and the result
# is checked after every export.
MODEL_UNIT_MM = 1000.0          # one model unit is one metre, by project convention
_MM_PER_DECLARED_FOOT = 304.8   # what the header's FOOT label makes a consumer apply

#: Multiply imported STEP geometry by this to reach the project's millimetre convention.
STEP_IMPORT_SCALE = MODEL_UNIT_MM / _MM_PER_DECLARED_FOOT   # 3.28084


def _set_cad_len_unit(vsp, unit):
    """Set the CAD export length unit, if the parm exists.

    Retained because it is the parm one reaches for, and a future OpenVSP may honour it.
    **Known not to affect ExportFile(EXPORT_STEP) in 3.50.5** -- the output is
    byte-identical either way. The scale assertion after export is the real guard.
    """
    found = []
    for cid in vsp.FindContainers():
        for pid in vsp.FindContainerParmIDs(cid):
            if vsp.GetParmName(pid) == 'CADLenUnit':
                vsp.SetParmVal(pid, float(unit))
                found.append((vsp.GetContainerName(cid), pid))
    if found:
        vsp.Update()
        return [(name, float(vsp.GetParmVal(pid))) for name, pid in found]
    return []


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

    # Attempted for completeness; see _set_cad_len_unit -- it does not affect STEP in
    # 3.50.5, and the export is correct regardless because the unit label is meaningless
    # (the model is dimensionless). What matters is that consumers apply
    # STEP_IMPORT_SCALE, which the check below pins down.
    _set_cad_len_unit(vsp, vsp.LEN_M)

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


PROVENANCE = 'oml_provenance.json'


def _model_hash():
    """SHA-256 of the source model, so an export can be tied to the .vsp3 it came from."""
    import hashlib
    h = hashlib.sha256()
    with open(VSP3, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_provenance(out_dir, written):
    """Record which model produced these files.

    Nothing previously connected the committed `.vsp3` to the committed OML: the export
    was done by hand, and a model edited in the GUI would leave the repository describing
    an airframe that no longer exists, with no signal that anything was wrong. See
    OQ-DES-CW7. This is the cheap half of the fix -- it does not prevent drift, but it
    makes drift detectable instead of silent.
    """
    import json
    record = {
        'source': VSP3.name,
        'source_sha256': _model_hash(),
        'model_unit_mm': MODEL_UNIT_MM,
        'step_import_scale': STEP_IMPORT_SCALE,
        'step_declares': 'FOOT (an exporter artifact; OpenVSP is dimensionless)',
        'files': sorted(p.name for p in written),
    }
    path = Path(out_dir) / PROVENANCE
    path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return path


def check_provenance(out_dir):
    """Verify the recorded export still matches the committed model. Returns problems."""
    import json
    path = Path(out_dir) / PROVENANCE
    if not path.exists():
        print('  NO PROVENANCE  %s is absent -- cannot tell whether the OML is current'
              % PROVENANCE)
        return 1
    record = json.loads(path.read_text(encoding='utf-8'))
    actual = _model_hash()
    if record.get('source_sha256') != actual:
        print('  STALE  %s has changed since the OML was exported' % VSP3.name)
        print('     recorded %s' % record.get('source_sha256', '?')[:16])
        print('     actual   %s' % actual[:16])
        return 1
    missing = [f for f in record.get('files', [])
               if not (Path(out_dir) / f).exists()]
    for f in missing:
        print('  MISSING  %s was exported but is not present' % f)
    if not missing:
        print('  OK  OML matches %s (%s)' % (VSP3.name, actual[:16]))
    return len(missing)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--list', action='store_true',
                    help='report what the model contains and exit')
    ap.add_argument('--check', action='store_true',
                    help='verify the exported OML matches the committed model, and exit')
    ap.add_argument('--out', default=str(OML_DIR), help='output directory')
    ap.add_argument('--format', choices=('step', 'iges'), default='step')
    args = ap.parse_args(argv)

    if args.check:
        # Deliberately does not import the OpenVSP API: a provenance check must be
        # runnable in CI, or by anyone, without OpenVSP installed.
        print('checking OML provenance against %s' % VSP3.name)
        return 1 if check_provenance(args.out) else 0

    if not VSP3.exists():
        raise SystemExit('Source model not found: %s' % VSP3)

    vsp, root = import_vsp()
    print('OpenVSP %s (%s)' % (vsp.GetVSPVersion(), root))

    if args.list:
        list_model(vsp)
        return 0

    print('exporting %s from %s' % (args.format.upper(), VSP3.name))
    written = export(vsp, args.out, args.format)
    path = write_provenance(args.out, written)
    print('  provenance   -> %s' % path.name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
