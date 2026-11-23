"""The rib tool's inner offset, built in a separate process with a time limit.

**Why a separate process** ([OQ-DES-CW41](../../../doc/design/cowl.md), decided 2026-11-23). The
exact rib-cut check needs the tool's inner offset by `WALL_TOL_M`, and `rib_geometry.inner_offset`
builds it from thousands of kernel cuts. A kernel cut can fail to return, and nothing inside the
process that called it can interrupt it: on the 48-gon tool four cells of 3,584 were still running
after 30 minutes or more. So the build hands the tool to a child `freecadcmd`, which builds the
offset and writes it back, and the build refuses the part if the child runs past its time limit.
Algorithm document section 7.2.1, "How it is cut".

Both sides are here. `bounded_inner_offset` is the parent's call; the module run as a script is
the child:

    freecadcmd rib_offset_worker.py --pass --tool=tool.brep --pass --eps=1e-05
        --pass --cell=0.02 --pass --out=dir

`--eps` and `--cell` are meters. The child writes `core.brep`, a compound with one child shape
per tool solid in the tool's own order (an empty compound where a solid is too thin to have an
offset), and `report.json`, which says whether it finished. Its exit code is not read:
`freecadcmd` exits 0 on a script exception, so the files are what say it worked.
"""
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402
import rib_geometry  # noqa: E402
import si  # noqa: E402
from corner_common import is_entry_point  # noqa: E402

#: The edge of the cubes the offset is cut in, as surveyed on the `U` = 3.0 tail: 6,824 cells of
#: the planar tool, every one trusted (algorithm document section 7.2.1).
CELL_M = 0.02

#: The time limit's terms, measured on the planar tool of the `U` = 3.0 tail, the largest measured:
#: 6,824 cells cut in 327 s, 0.048 s a cell. The limit is `START_S + MARGIN * CELL_S * cells`, so
#: it grows with the part, and ten times the measured cost leaves a slow healthy build room while
#: still ending a cut that never returns: 3,472 s on that tail. `START_S` covers starting
#: `freecadcmd` and reading the tool back.
OFFSET_START_S = 60.0
OFFSET_CELL_S = 0.05
OFFSET_MARGIN = 10.0


class OffsetNotBuilt(Exception):
    """The inner offset did not come back: the child ran past its limit, or failed, or wrote
    nothing. Carries the reason; the caller refuses the part with it."""


def cells(tool, cell_m=CELL_M):
    """How many cubes `inner_offset` will cut, over every solid of `tool`."""
    edge = si.mm(cell_m)
    n = 0
    for s in tool.Solids:
        bb = s.BoundBox
        n += (max(1, int(math.ceil(bb.XLength / edge))) * max(1, int(math.ceil(bb.YLength / edge)))
              * max(1, int(math.ceil(bb.ZLength / edge))))
    return n


def time_limit_s(tool, cell_m=CELL_M):
    """The child's time limit for `tool`, in seconds. See `OFFSET_START_S`."""
    return OFFSET_START_S + OFFSET_MARGIN * OFFSET_CELL_S * cells(tool, cell_m)


def _freecadcmd():
    """The console executable beside the running FreeCAD. Not `sys.executable`, which is the GUI's
    `freecad.exe` when a document is recomputed in the GUI."""
    bindir = Path(App.getHomePath()) / 'bin'
    for name in ('freecadcmd.exe', 'FreeCADCmd.exe', 'freecadcmd', 'FreeCADCmd'):
        path = bindir / name
        if path.is_file():
            return str(path)
    raise OffsetNotBuilt('no freecadcmd beside this FreeCAD, in %s' % bindir)


def bounded_inner_offset(tool, eps_m, cell_m=CELL_M, limit_s=None):
    """The inner offset of each solid of `tool` by `eps_m`, built in a child process.

    Returns `(cores, report)`: `cores[k]` is solid `k`'s inner offset, or `None` where it has
    none, and `report` is the child's record plus the limit and the time taken. Raises
    `OffsetNotBuilt`, naming the cause, if the child runs past `limit_s` (by default
    `time_limit_s(tool, cell_m)`), fails, or writes nothing usable.
    """
    limit = time_limit_s(tool, cell_m) if limit_s is None else limit_s
    # A local directory, not one beside the part: the share is UNC, and a child writing there has
    # been the source of more than one path failure in this project.
    work = Path(tempfile.mkdtemp(prefix='rib_offset_'))
    started = time.time()
    try:
        tool.exportBrep(str(work / 'tool.brep'))
        argv = [_freecadcmd(), str(_HERE / 'rib_offset_worker.py'),
                '--pass', '--tool=%s' % (work / 'tool.brep'),
                '--pass', '--eps=%r' % eps_m, '--pass', '--cell=%r' % cell_m,
                '--pass', '--out=%s' % work]
        try:
            done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  timeout=limit)
        except subprocess.TimeoutExpired as exc:
            raise OffsetNotBuilt(
                'the inner offset did not finish within its time limit of %.0f s (%d cells at '
                '%.2f s a cell, %gx margin): a kernel cut in it most likely never returned, and '
                'the cut cannot be checked without it'
                % (limit, cells(tool, cell_m), OFFSET_CELL_S, OFFSET_MARGIN)) from exc
        log = done.stdout.decode('utf-8', 'replace')
        report_path = work / 'report.json'
        if not report_path.is_file():
            raise OffsetNotBuilt('the inner-offset process wrote no report; its output ends: %s'
                                 % log[-600:])
        report = json.loads(report_path.read_text())
        if report.get('error'):
            raise OffsetNotBuilt('the inner offset could not be built: %s' % report['error'])
        compound = Part.read(str(work / 'core.brep'))
        children = compound.childShapes()
        if len(children) != len(tool.Solids):
            raise OffsetNotBuilt('the inner offset came back with %d parts for a tool of %d solids'
                                 % (len(children), len(tool.Solids)))
        cores = [c if c.Solids else None for c in children]
        report.update(limit_s=limit, seconds=time.time() - started)
        return cores, report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _child(opt):
    """Build every solid's inner offset and write `core.brep` and `report.json` to `opt['out']`."""
    out = Path(opt['out'])
    report = {'solids': [], 'error': None}
    try:
        tool = Part.read(opt['tool'])
        eps_m, cell_m = float(opt['eps']), float(opt['cell'])
        cores = []
        for k, solid in enumerate(tool.Solids):
            at = time.time()
            rec = {}
            core = rib_geometry.inner_offset(solid, eps_m, report=rec, cell_m=cell_m)
            cores.append(core if core is not None else Part.Compound([]))
            report['solids'].append({
                'solid': k, 'faces': len(solid.Faces),
                'retries': len(rec.get('retries', [])),
                'cells_mm3': rec.get('cells_mm3'), 'solid_mm3': solid.Volume,
                'core_mm3': 0.0 if core is None else core.Volume,
                'seconds': time.time() - at})
        Part.Compound(cores).exportBrep(str(out / 'core.brep'))
    except Exception as exc:                                             # noqa: BLE001
        # Recorded and handed back, not swallowed: the parent refuses the part with this text.
        report['error'] = '%s: %s' % (type(exc).__name__, exc)
    (out / 'report.json').write_text(json.dumps(report, indent=1))


def main():
    opt = {}
    for arg in sys.argv[1:]:
        if arg.startswith('--') and '=' in arg:
            name, _, value = arg[2:].partition('=')
            opt[name] = value
    _child(opt)


if is_entry_point(__name__):
    main()
