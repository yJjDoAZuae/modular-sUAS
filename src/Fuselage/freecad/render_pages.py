"""IP-FC-129: render finished sheets with TechDraw's own page renderer.

Run by `tools/render_sheets.py`, never by hand, and **not under `freecadcmd`**:

    QT_QPA_PLATFORM=offscreen freecad.exe render_pages.py     # job in $RENDER_JOB

**Why this exists, and the mistake it corrects.** `freecadcmd` has no Qt in it, so TechDraw's
page renderer is not merely unavailable there but absent: `TechDraw` offers `writeDXFPage` and
`writeDXFView` and nothing that draws a page. Asking for the renderer under `freecadcmd` raises
*"Cannot load Gui module in console application"*, which reads like a fact about FreeCAD 1.1
and is a fact about `freecadcmd`. I read it the first way and wrote a page compositor of my
own -- template SVG plus `viewPartAsSvg` plus hand-placed annotations -- which drew the
geometry and the annotation positions and silently dropped everything else TechDraw puts on a
sheet: arrowheads, dimension text, line weights, the value table's contents, hatching, the
symbols. A drawing missing all of that is not a drawing, and no amount of work on the
compositor would have made it one, because the compositor was re-implementing a renderer that
already existed.

The same FreeCAD 1.1, run as `freecad.exe` with `QT_QPA_PLATFORM=offscreen`, renders pages
with no display attached and no window on screen. Measured on the corner sheet: 986 items in
the page scene, against the 83 paths and handful of letters the compositor emitted. So the
renderer was reachable the whole time, one executable away.

**Three formats, and the PDF is the one to review.** `exportPageAsSvg` writes the scene as
SVG, which is convenient to look at in a browser but renders text in whatever face the viewer
substitutes for the drawing font. `exportPageAsPdf` embeds it. Where the two disagree about a
sheet, the PDF is right.

The `.png` is the scene painted by Qt into an image at `RASTER_DPI`, and it exists because a
drawing has to be *looked at* to be reviewed. A PDF cannot be shown in a web page and an SVG
shown in one is not what the drawing says -- the font is substituted, so exactly the text a
reviewer is checking is the part that is not faithful. The raster is neither: it is the same
`QGraphicsScene` the other two come from, drawn by the same painter, with the drawing's own
font already resolved. It is the format to put in front of a person on a screen; the PDF is
the one to print from.

**The sheet's appearance is applied here, because here is where it can be.** Line weights,
dimension text size and hole centre marks are properties of TechDraw's *view providers*, which
are Gui objects that `freecadcmd` does not have -- so an `.FCStd` from this project carries no
appearance and whatever opens it supplies all of it from compiled-in defaults. Those defaults
are not the drawing standard: measured 2026-09-07, every view came out at 0.7 mm including the
value table's rules, dimension text at 5.0 mm against the 3.5 the standard sets, and centre
marks off, so no hole on any sheet had one. `drawing_standard.view_appearance` and its
neighbours say what those should be; this applies them, before the scene is built, for the same
reason the visibility below has to happen first.

**Everything has to be made visible first, and that is not a detail.** The sheets are built
by `freecadcmd`, which has no view providers at all, so an `.FCStd` from it carries no record
of what is shown. Opening it in the GUI creates those view providers fresh with `Visibility`
defaulted *off* -- 222 of them on a corner sheet -- and TechDraw honours that when it builds
the page scene. The result is not an empty page, which would be obvious: the views and the
dimensions come through and **the template does not**, so the sheet renders complete except for
its frame and title block, which reads as a drawing that was never given a border rather than
as a rendering fault. It cost me a round of chasing the template through Qt's SVG renderer,
which reads the file perfectly well, before looking at the one flag that was off.

The order matters as much as the flag. Setting `Visibility` after the scene exists does not
attach the template; the scene is built once, from whatever is visible at the time. So this
happens before anything asks for a scene.

**The scene has to be waited for, because the projection is not synchronous.** TechDraw
computes a `DrawViewPart`'s hidden-line projection off the main thread and adds the resulting
edges to the page scene when it finishes. Asking for the scene and exporting it in the next
statement therefore exports whatever happens to have arrived, which is the frame, the table
rules, the notes and the dimensions -- everything cheap -- and, often, none of the part. The
symptom is a sheet that looks deliberately drawn and is missing only its geometry, and it is
not deterministic: of six sheets exported without waiting, one came out with its part on it and
five did not, which reads as five broken sheets rather than as one race.

So `settle` spins the event loop until the scene stops growing. It is a poll rather than a
signal because the projection finishing is not exposed to Python here, and it stops on a
deadline so a view that never completes costs a bounded wait and a note in the log rather than
a hang.

**What must not happen is a recompute.** I added one after making things visible, on the
reasoning that a changed document should be brought up to date, and it silently emptied the
bulkhead sheets: their part view fell from 277 drawn paths to 26 -- the 26 being the table
rules, so the sheet kept its notes, its table and its frame and lost the part. The corner
sheets survived the same recompute, which is what made it look like a bulkhead problem rather
than a self-inflicted one. A recompute re-projects every `DrawViewPart` from its source, and a
re-projection that fails leaves an empty view rather than an error. The documents arrive here
finished and saved; there is nothing to bring up to date, and this module opens them to read.

**It has to be killed rather than asked to leave.** This is the real GUI with a real event
loop; `getMainWindow().close()` returns to that loop rather than ending the process, and the
first run of this script sat until its 180 s timeout with every artefact already correctly on
disk. So the log is flushed and closed and then `os._exit` is called, deliberately. Nothing
here needs an orderly shutdown -- the documents are read-only inputs and the artefacts are
already written and verified by the time it happens.

**The exit code says nothing** -- see the log instead. That is not a quirk of the hard exit:
`freecadcmd`'s exit code is unreliable in this project already, and the driver has always read
artefacts rather than codes. `render_sheets.py` reads `$RENDER_LOG` and the files themselves.
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawing_standard as std

#: A page that rendered has hundreds of scene items; one that failed to build its scene has a
#: handful or none. Used only to report a suspicious sheet, never to refuse one -- the file on
#: disk is the evidence, and a sparse sheet is still a sheet worth looking at.
THIN_SCENE = 50

#: Below this, an SVG is the header and an empty scene rather than a drawing. The smallest
#: real sheet measured here is 21 KB and the largest 142 KB.
MIN_BYTES = 4096

#: Dots per inch for the raster. An ANSI B sheet is 11 inches wide, so 200 dpi is 2200 px --
#: enough that the smallest text on these sheets, the 2.5 mm table digits, lands around 20 px
#: tall and stays legible when the page is scaled to fit a screen.
RASTER_DPI = 200.0
MM_PER_INCH = 25.4

#: How long to wait for a page's projections to arrive, and how often to look. A corner
#: settles in well under a second and the largest bulkhead here in about two; the ceiling is
#: for a sheet that never finishes, which should cost a bounded wait and a note rather than a
#: hung process on somebody's working machine.
SETTLE_TIMEOUT_S = 60.0
SETTLE_POLL_S = 0.05

#: How many consecutive unchanged polls mean the scene is done growing. One is not enough:
#: the item count pauses between views as each projection lands.
SETTLE_STABLE_POLLS = 12

#: How far past the paper something may reach before it is worth reporting, in millimetres.
#: Not zero: the template draws the sheet border *on* the paper edge, and half of that
#: stroke's width therefore falls outside it -- measured at 0.1 mm each side on every sheet
#: here, which as a bare `contains` test made every render cry off-paper about its own frame.
SPILL_TOLERANCE_MM = 0.5

#: Millimetres per unit of TechDraw's page scene. **Not one.** The scene is in tenths of a
#: millimetre: an ANSI B page, 279.4 mm wide, has a `sceneRect` 2794 units across, which is
#: also the `viewBox` the SVG export writes. Assuming millimetres here produced a raster ten
#: times too large in each direction before anything else was wrong with it.
MM_PER_SCENE_UNIT = 0.1


def _log_handle():
    path = os.environ.get('RENDER_LOG')
    if not path:
        return sys.stdout
    return open(path, 'w', encoding='utf-8', newline='\n')


def raster(page, scene, path, say):
    """Paint the page scene into a PNG. Returns True if a file came out.

    **The white fill is not cosmetic.** A `QImage` starts transparent and TechDraw draws a
    drawing in black on nothing; saved as a PNG with an alpha channel, that is black-on-black
    in any viewer with a dark background -- an apparently blank sheet whose content is
    entirely present. Filling white first makes the raster say what the paper says.

    **The paper is what gets painted, and neither rectangle in the scene is the paper.**
    `itemsBoundingRect` is the drawing plus every construction and off-sheet object a page
    scene carries, and `sceneRect` is the scrolling area, which TechDraw makes three times the
    page in each direction so a view can be dragged past the edge. Both were tried and both
    gave a raster nine times the area with the sheet as a patch in one corner. The template is
    the only object that states the sheet size, so the paper is taken from it.

    **Where the paper sits was measured, not inferred from the SVG.** The export writes a
    `viewBox` of `0 0 2794 2159` for this 279.4 x 215.9 mm page, which reads as the paper
    lying at the origin; painting that rectangle produced a blank sheet. The scene runs y
    *upward* while the exporter's viewBox runs it downward, so the page actually occupies
    `x 0..2794, y -2159..0` -- it hangs below the origin. Measured on this page: every drawn
    item falls in `x 67..1910, y -1967..-183`, inside that rectangle and nowhere near the one
    the viewBox suggests.

    Anything drawn beyond that is reported rather than painted. A number saying a mark is off
    the sheet is more use to a reviewer than a mark in a margin they are expected to notice.
    """
    from PySide6 import QtCore, QtGui

    template = getattr(page, 'Template', None)
    if template is None:
        say('    .png  the page has no template, so nothing states the sheet size')
        return False
    paper_mm = (float(template.Width), float(template.Height))
    wide = paper_mm[0] / MM_PER_SCENE_UNIT
    tall = paper_mm[1] / MM_PER_SCENE_UNIT
    box = QtCore.QRectF(0.0, -tall, wide, tall)
    if box.isEmpty():
        say('    .png  the template reports a %g x %g mm sheet' % paper_mm)
        return False

    slack = SPILL_TOLERANCE_MM / MM_PER_SCENE_UNIT
    spill = scene.itemsBoundingRect()
    if not box.adjusted(-slack, -slack, slack, slack).contains(spill):
        say('    .png  NOTE: something is drawn off the paper (items span %.1f x %.1f mm '
            'against a %.1f x %.1f mm sheet)'
            % (spill.width() * MM_PER_SCENE_UNIT, spill.height() * MM_PER_SCENE_UNIT,
               box.width() * MM_PER_SCENE_UNIT, box.height() * MM_PER_SCENE_UNIT))

    pixels_per_unit = MM_PER_SCENE_UNIT * RASTER_DPI / MM_PER_INCH
    width = int(round(box.width() * pixels_per_unit))
    height = int(round(box.height() * pixels_per_unit))
    image = QtGui.QImage(width, height, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor('white'))

    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
    try:
        scene.render(painter, QtCore.QRectF(image.rect()), box,
                     QtCore.Qt.KeepAspectRatio)
    finally:
        painter.end()

    if not image.save(path, 'PNG'):
        say('    .png  Qt refused to save the image')
        return False
    say('    .png  %d bytes, %d x %d px' % (os.path.getsize(path), width, height))
    return True


def render(page, stem, say):
    """Write `stem.svg` and `stem.pdf` from one page. Returns the paths that came out right.

    A format that fails is reported and skipped rather than aborting the sheet, matching
    `build_sheet.export`: they are all for reading and losing one should not lose the others.
    """
    import TechDrawGui

    written = []
    for suffix, export in (('.svg', TechDrawGui.exportPageAsSvg),
                           ('.pdf', TechDrawGui.exportPageAsPdf)):
        path = stem + suffix
        if os.path.isfile(path):
            os.remove(path)                 # so a stale file cannot be reported as this run's
        try:
            export(page, path)
        except Exception as exc:                                        # noqa: BLE001
            say('    %s  not written: %s: %s' % (suffix, type(exc).__name__, exc))
            continue
        if not os.path.isfile(path):
            say('    %s  export returned but wrote no file' % suffix)
            continue
        size = os.path.getsize(path)
        if size < MIN_BYTES:
            say('    %s  suspiciously small: %d bytes' % (suffix, size))
        written.append(path)
        say('    %s  %d bytes' % (suffix, size))
    return written


def apply_appearance(obj, view_object, say):
    """Put the sheet standard's line weights and text sizes on one view provider.

    Returns how many properties were set. A property this build of TechDraw does not have is
    skipped rather than raised: the appearance is worth having and no single setting of it is
    worth losing a sheet over, but a silent skip would leave a sheet looking wrong with
    nothing said, so it is counted and reported.
    """
    kind = obj.TypeId
    if kind == 'TechDraw::DrawViewPart':
        wanted = std.view_appearance(obj.Name)
    elif kind == 'TechDraw::DrawViewDimension':
        wanted = std.dimension_appearance()
    elif kind == 'TechDraw::DrawLeaderLine':
        wanted = std.leader_appearance()
    else:
        return 0, 0

    applied = missing = 0
    for name, value in sorted(wanted.items()):
        if not hasattr(view_object, name):
            missing += 1
            continue
        try:
            setattr(view_object, name, value)
            applied += 1
        except Exception as exc:                                        # noqa: BLE001
            missing += 1
            say('    %s.%s would not take %r: %s' % (obj.Name, name, value, exc))
    return applied, missing


def show_everything(doc, say):
    """Turn on every view provider in the document, and give it the sheet's appearance.

    See the module docstring: a document written by `freecadcmd` has no view provider state,
    the GUI defaults them to hidden, and a hidden template is a sheet with no frame or title
    block. Called before the page scene is built, because the scene is built once from what
    is visible then.

    A view provider that refuses is counted and ignored rather than raised: not every object
    in a page document is something with a meaningful visibility, and one that will not be
    shown is not a reason to lose the sheet.

    Note that this deliberately does **not** recompute afterwards. See the module docstring:
    a recompute re-projects the part views and empties some of them.
    """
    shown = refused = styled = missing = 0
    for obj in doc.Objects:
        view_object = getattr(obj, 'ViewObject', None)
        if view_object is None:
            continue
        try:
            view_object.Visibility = True
            shown += 1
        except Exception:                                               # noqa: BLE001
            refused += 1
        applied, absent = apply_appearance(obj, view_object, say)
        styled += applied
        missing += absent
    if refused:
        say('    %d view provider(s) would not be shown' % refused)
    if missing:
        say('    %d appearance setting(s) this build does not have' % missing)
    say('    %d appearance setting(s) applied' % styled)
    return shown


def settle(scene, say):
    """Spin the event loop until the page scene stops growing. Returns the seconds waited.

    See the module docstring: the part projection arrives on a worker thread, so a scene that
    has just been asked for is not a scene that is finished. Polling the item count is crude
    but it is the thing that actually changes, and it needs no signal TechDraw does not
    expose.
    """
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        return 0.0

    started = time.time()
    last = -1
    stable = 0
    while time.time() - started < SETTLE_TIMEOUT_S:
        app.processEvents()
        count = len(scene.items())
        if count == last:
            stable += 1
            if stable >= SETTLE_STABLE_POLLS:
                break
        else:
            stable = 0
            last = count
        time.sleep(SETTLE_POLL_S)
    else:
        say('    the scene was still changing after %.0f s; exporting it as it stands'
            % SETTLE_TIMEOUT_S)
    return time.time() - started


def render_one(source, stem, say):
    """Open one `.FCStd`, render its page, close it. Returns True if anything was written."""
    import FreeCAD

    doc = FreeCAD.openDocument(source)
    try:
        say('    %d view provider(s) shown' % show_everything(doc, say))
        pages = [o for o in doc.Objects if o.isDerivedFrom('TechDraw::DrawPage')]
        if not pages:
            say('    no DrawPage in this document')
            return False
        if len(pages) > 1:
            say('    %d pages; rendering %s only' % (len(pages), pages[0].Name))
        page = pages[0]

        # **The scene has to be asked for.** A page's `QGSPage` is built by its view provider
        # on demand, and a document merely opened has not needed one yet. `getSceneForPage`
        # is what forces it; without the scene, an export writes a page-sized empty file
        # rather than raising. Reporting the item count makes an empty one visible here
        # rather than in the artefact.
        import TechDrawGui
        try:
            scene = TechDrawGui.getSceneForPage(page)
            items = len(scene.items()) if scene is not None else 0
        except Exception as exc:                                        # noqa: BLE001
            say('    scene not available: %s: %s' % (type(exc).__name__, exc))
            scene, items = None, 0
        if scene is not None:
            waited = settle(scene, say)
            items = len(scene.items())
            say('    settled in %.1f s' % waited)
        say('    %d scene item(s)%s'
            % (items, '  THIN' if items < THIN_SCENE else ''))

        made = render(page, stem, say)
        if scene is not None:
            png = stem + '.png'
            if os.path.isfile(png):
                os.remove(png)
            try:
                if raster(page, scene, png, say):
                    made.append(png)
            except Exception as exc:                                    # noqa: BLE001
                say('    .png  not written: %s: %s' % (type(exc).__name__, exc))
        return bool(made)
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    log = _log_handle()

    def say(text):
        log.write(text + '\n')
        log.flush()

    job_path = os.environ.get('RENDER_JOB')
    if not job_path or not os.path.isfile(job_path):
        say('RENDER_JOB is not set to a readable file (%r)' % job_path)
        return 2
    with open(job_path, encoding='utf-8') as handle:
        jobs = json.load(handle)

    ok = 0
    for job in jobs:
        source, stem = job['fcstd'], job['stem']
        say('  %s' % os.path.basename(stem))
        if not os.path.isfile(source):
            say('    no such document: %s' % source)
            continue
        try:
            if render_one(source, stem, say):
                ok += 1
        except Exception:                                               # noqa: BLE001
            say('    EXCEPTION')
            for line in traceback.format_exc().splitlines():
                say('      ' + line)

    say('')
    say('rendered %d of %d' % (ok, len(jobs)))
    if log is not sys.stdout:
        log.close()
    return 0 if ok == len(jobs) else 1


# No `is_entry_point` guard: the GUI runs this file as a startup script, not as `__main__`,
# so a guard keyed on `__name__` would make it do nothing at all.
_CODE = main()
sys.stdout.flush()
sys.stderr.flush()
# See the module docstring: closing the main window returns to the event loop, it does not
# end the process. Everything is written and verified above.
os._exit(_CODE)
