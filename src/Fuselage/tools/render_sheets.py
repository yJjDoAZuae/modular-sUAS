"""IP-FC-129: render drawn sheets to SVG and PDF using TechDraw's own page renderer.

    python render_sheets.py                  # every .FCStd under freecad/out/sheets
    python render_sheets.py --out DIR        # somewhere else
    python render_sheets.py --key corner-corner-7faa02

`draw_set.py` calls this as its last step, so a normal run of the set needs neither this
module's name nor its flags. It stands alone as well, because re-rendering is not re-drawing:
the sheets take minutes to build and seconds to render, and a question about how a sheet looks
should not cost a rebuild of the geometry it looks at.

**Why the drawing is rendered by a second process, and a different executable.** The sheets
are built under `freecadcmd`, which has no Qt and therefore no TechDraw page renderer -- see
`freecad/render_pages.py` for the mistake that fact led me into. `freecad.exe`, the GUI binary
of the same install, renders pages with no display attached under `QT_QPA_PLATFORM=offscreen`.
So the build stays where it is and the rendering moves to the binary that can do it.

**One process for the whole set, not one per sheet.** The rest of this project spawns a
FreeCAD per part, because a build can crash the kernel and one part should not take the sweep
with it. Rendering is not that: it reads finished documents and writes pictures of them, and
the GUI binary costs about ten seconds to start against `freecadcmd`'s 0.24 s. `render_pages`
catches per-sheet exceptions itself so one bad sheet still does not stop the others.

**Neither exit code is read.** `freecadcmd`'s is unreliable in this project already, and
`render_pages` ends with `os._exit` besides. What is read is the log it writes and the files
themselves, which is the same rule the part sweep follows.
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import freecad_render

FREECAD_DIR = os.path.normpath(os.path.join(HERE, '..', 'freecad'))
RENDERER = os.path.join(FREECAD_DIR, 'render_pages.py')
DEFAULT_OUT = os.path.join(FREECAD_DIR, 'out', 'sheets')

#: Generous, and bounded on purpose: this runs on a working machine, and a GUI process that
#: hangs with no window to close is a bad thing to leave behind. Measured about 12 s of
#: startup plus roughly 2 s per sheet, so six sheets land near 25 s.
TIMEOUT_BASE = 120.0
TIMEOUT_PER_SHEET = 30.0


def jobs_for(out_dir, only=None):
    """Every `.FCStd` in `out_dir` as a render job, sorted so a run is reproducible."""
    jobs = []
    for path in sorted(glob.glob(os.path.join(out_dir, '*.FCStd'))):
        stem = path[:-len('.FCStd')]
        if only and os.path.basename(stem) != only:
            continue
        jobs.append({'fcstd': path, 'stem': stem})
    return jobs


def render(jobs, out_dir, echo=print):
    """Render every job in one GUI process. Returns the list of stems that produced files."""
    if not jobs:
        echo('  nothing to render')
        return []

    try:
        binary = freecad_render.freecad_gui_path()
    except Exception as exc:                                            # noqa: BLE001
        echo('  FreeCAD GUI not found: %s' % exc)
        return []

    job_path = os.path.join(out_dir, 'render.job.json')
    log_path = os.path.join(out_dir, 'render.log')
    with open(job_path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(jobs, handle, indent=1, sort_keys=True)

    environment = dict(os.environ)
    environment['RENDER_JOB'] = job_path
    environment['RENDER_LOG'] = log_path
    # **This is what keeps a window off the screen.** Qt's offscreen platform plugin gives the
    # scene somewhere to rasterise into without a display; TechDraw's renderer is
    # `QGraphicsScene`, so it needs no GPU and nothing to show. Without it the GUI opens on
    # the working machine and steals focus.
    environment['QT_QPA_PLATFORM'] = 'offscreen'

    timeout = TIMEOUT_BASE + TIMEOUT_PER_SHEET * len(jobs)
    try:
        subprocess.run([binary, RENDERER], env=environment, timeout=timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        echo('  the renderer did not finish within %.0f s and was stopped' % timeout)

    if os.path.isfile(log_path):
        with open(log_path, encoding='utf-8') as handle:
            for line in handle.read().splitlines():
                if line.strip():
                    echo('  ' + line)

    return [job['stem'] for job in jobs
            if os.path.isfile(job['stem'] + '.svg') or os.path.isfile(job['stem'] + '.pdf')]


def main(argv):
    out_dir = DEFAULT_OUT
    only = None
    for i, arg in enumerate(argv):
        if arg == '--out' and i + 1 < len(argv):
            out_dir = argv[i + 1]
        if arg == '--key' and i + 1 < len(argv):
            only = argv[i + 1]

    if not os.path.isdir(out_dir):
        print('no such directory: %s' % out_dir)
        return 2

    jobs = jobs_for(out_dir, only)
    print('RENDERING %d sheet(s) with TechDraw' % len(jobs))
    done = render(jobs, out_dir)
    print('')
    print('  rendered %d of %d' % (len(done), len(jobs)))
    return 0 if len(done) == len(jobs) and jobs else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
