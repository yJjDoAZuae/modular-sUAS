"""IP-FC-114: produce the drawing set — every family sheet the project owes, in one run.

    python draw_set.py                       # write the set under freecad/out/sheets
    python draw_set.py --out DIR             # somewhere else
    python draw_set.py --key corner-corner-7faa02      # one sheet

**What was missing.** `drawing_families.py` says which family sheets the set needs;
`freecad/drawing.py` can build one; nothing joined them. The only end-to-end path was
`check_drawing.py`, which draws one sheet for one kind from one variant and exports it under a
checker's filename as evidence for its own assertions — so the artefact a reader would ask for
existed only as a by-product, one at a time. This walks the families and writes the set.

**Two interpreters, for the usual reason.** The families and the parameter resolution live in
the virtualenv and need `solid2`; `drawing.py` needs FreeCAD. So this side chooses the sheets
and exports each one's parameters, and `freecad/build_sheet.py` draws them, one `freecadcmd`
per sheet — the same shape as `freecad_render.py`'s subprocess-per-part.

**Three interpreters, in fact, because drawing a sheet and rendering one are different
jobs.** `freecadcmd` builds the documents and cannot draw a picture of them: it has no Qt,
so TechDraw's page renderer is not in it. The last step therefore hands the finished
`.FCStd` files to `render_sheets.py`, which runs the *GUI* binary of the same FreeCAD
offscreen and lets TechDraw render its own pages to SVG and PDF. Those two files are what a
person reviews; everything before them is machinery.

**Which sheets are in the set, and why some are not.** A family gets a sheet when its kind has
an annotation set to draw callouts from — `corner` and `bulkhead` — and when this backend can
build every type in it. Measured 2026-09-07: **10 of 16 families have an annotation set, and 4
of those name types `build_part` does not build** (`cowling_anchor`, `cowling_bolt`,
`interconnect`), which `drawing.build_sheet` refuses rather than drawing a different part under
the family's title. **Those four are reported as owed, not skipped in silence**, because a
drawing set that quietly omits a quarter of itself is worse than one that says what is missing.

**Picking the variant a family is drawn from.** A family sheet stands for many variants, so one
of them supplies the geometry and the table supplies the rest. The representative is chosen by
bucketing the sweep exactly as `drawing_families.families()` does — same `resolve`, same
`topology_of`, same `family_key` — rather than by a rule of its own, so the variant drawn and
the family tabulated cannot come apart. `build_sheet.py` re-derives the family from the
parameters it is handed and refuses if it disagrees with the key it was given.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FREECAD_DIR = os.path.normpath(os.path.join(HERE, '..', 'freecad'))
sys.path.insert(0, HERE)
sys.path.insert(0, FREECAD_DIR)

import drawing_families as df
import export_parameters
import freecad_render
import render_sheets
import sheet_naming
BUILDER = os.path.join(FREECAD_DIR, 'build_sheet.py')
DEFAULT_OUT = os.path.join(FREECAD_DIR, 'out', 'sheets')

#: The bulkhead type a corner sheet's parameters are exported through. A corner has no type
#: axis -- one export carries a bulkhead under `parameters` and its matching corner under
#: `corner_parameters` -- so a type has to be named to get at the corner, and it must be one
#: this backend builds. The corner's own parameters do not depend on it, and `build_sheet.py`
#: re-derives the family from what it loads, so a wrong choice here fails loudly rather than
#: drawing the wrong sheet.
CORNER_THROUGH_TYPE = 'end_bolt'


def representatives():
    """One variant per family, bucketed the way `drawing_families.families()` buckets.

    Returns `{family key: (kind, axis_values, type_name)}`. Re-derived rather than read out of
    the families document because that document does not record which variant it was built
    from -- and inventing a rule here for picking one would be a second authority on what a
    family *is*.
    """
    out = {}
    for kind in sorted(df.SWEEPS):
        buckets = {}
        for axis_values, flat, mapped, type_name in df.resolve(kind):
            buckets.setdefault(df.topology_of(flat, mapped), []).append(
                (axis_values, type_name))
        for signature, rows in buckets.items():
            names = sorted({t for _, t in rows})
            _none, axis_values, type_name = representative(rows)
            out[df.family_key(kind, names, signature)] = (
                kind, axis_values, type_name)
    return out


#: The size a family sheet's geometry is drawn at. **One unit, because that is what the
#: airframe's sizes are multiples of** -- a reader looking at a family sheet is looking at the
#: shape, and the shape they have in their head is the unit one. A family that does not cover
#: it is drawn at whichever of its sizes is nearest, which keeps the choice a rule rather than
#: an accident of dictionary order: before 2026-09-07 this took `rows[0]`, so the panelled
#: bulkhead family was drawn at U = 0.5 and the reader had no way to know it was the smallest
#: variant of eight.
REPRESENTATIVE_U = 1.0


def representative(rows):
    """The variant a family is drawn from: U = 1.0, or the nearest size it has."""
    def distance(row):
        axis_values, type_name = row
        return (abs(float(axis_values['U']) - REPRESENTATIVE_U),
                float(axis_values['U']), str(type_name))

    axis_values, type_name = min(rows, key=distance)
    return (None, axis_values, type_name)


def export_for(kind, axis_values, type_name, path):
    """Resolve and write one variant's parameters, as `export_parameters.py` does by hand."""
    want_type = type_name if kind != 'corner' else CORNER_THROUGH_TYPE
    code = export_parameters.main([str(axis_values['U']), want_type,
                                   str(axis_values['panel']), path])
    return code == 0 and os.path.isfile(path)


#: What a sheet leaves behind, and what has to be gone before it is drawn again.
SHEET_SUFFIXES = ('.FCStd', '.FCStd1', '.dxf', '.svg', '.pdf', '.png')


def clear(stem):
    """Remove a sheet's artefacts. Returns how many were there.

    **Because the artefact is the evidence, a stale one is a false pass.** This module reads
    files rather than exit codes, `freecadcmd`'s being unreliable -- but a file only says a
    sheet was drawn if it could not have been drawn by an earlier run. Measured 2026-09-07:
    four sheets refused, their `.FCStd` from the previous run was still on disk, and the run
    reported "wrote 6 sheet(s)" with four of the six untouched and out of date. Clearing
    first makes the test mean what it says.

    **Globbed for sheet 2 and up, because this side does not know how many pages a drawing
    has until it is drawn.** The `.FCStd` is one file for every page (`build_sheet.export`),
    but the `.dxf`/`.svg`/`.pdf`/`.png` are one per page, named `stem-sheetN` by
    `sheet_naming`. A family that grows a second sheet on this run and had one on the last
    would otherwise leave that run's `stem-sheet2.pdf` on disk forever, since nothing later
    ever asks to remove it by name.
    """
    gone = 0
    for suffix in SHEET_SUFFIXES:
        for pattern in sheet_naming.sheet_glob(stem):
            for path in glob.glob(pattern + suffix):
                os.remove(path)
                gone += 1
    return gone


def draw(freecadcmd, params_path, families_path, kind, key, stem):
    """One sheet, in its own interpreter. Returns (ok, output)."""
    clear(stem)
    argv = [freecadcmd, BUILDER,
            '--pass', params_path, '--pass', families_path,
            '--pass', 'kind=%s' % kind, '--pass', 'key=%s' % key,
            '--pass', 'out=%s' % stem]
    done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = done.stdout.decode('utf-8', 'replace')
    # `freecadcmd`'s exit code is not a reliable signal -- it has been observed exiting 0 on a
    # script that raised -- so the artefact is what says the sheet was drawn. `clear` above is
    # what makes that true: without it the artefact only says a sheet was drawn *at some
    # point*, which is a different claim and a much weaker one.
    return os.path.isfile(stem + '.FCStd'), text


def main(argv):
    out_dir = DEFAULT_OUT
    only = None
    for i, arg in enumerate(argv):
        if arg == '--out' and i + 1 < len(argv):
            out_dir = argv[i + 1]
        if arg == '--key' and i + 1 < len(argv):
            only = argv[i + 1]

    try:
        freecadcmd = freecad_render.freecadcmd_path()
    except Exception as exc:                                            # noqa: BLE001
        print('freecadcmd not found: %s' % exc)
        return 2

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    families_path = os.path.join(out_dir, 'families.json')

    print('DRAWING SET')
    data = df.families()
    document = {'decimals': df.ds.DECIMAL_PLACES,
                'rows_per_sheet': df.ROWS_PER_SHEET,
                'register': [[n, sorted(names), sorted(c), p]
                             for n, names, c, p in df.read_register()],
                'families': data}
    with open(families_path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(document, handle, indent=1, sort_keys=True)
    print('  families            %s' % families_path)

    reps = representatives()
    drawable, owed = [], []
    for family in data:
        if not family.get('quantity_blocks'):
            continue                       # no annotation set: not a sheet this set owes yet
        (owed if family['unbuilt_types'] else drawable).append(family)

    print('  sheets to draw      %d' % len(drawable))
    print('  owed but unbuildable %d' % len(owed))
    print('')

    written, failed = [], []
    for family in drawable:
        key = family['key']
        if only and key != only:
            continue
        kind, axis_values, type_name = reps[key]
        params_path = os.path.join(out_dir, key + '.params.json')
        if not export_for(kind, axis_values, type_name, params_path):
            print('  %-42s parameters could not be exported' % key)
            failed.append(key)
            continue
        ok, text = draw(freecadcmd, params_path, families_path, kind, key,
                        os.path.join(out_dir, key))
        for line in text.splitlines():
            if line.startswith('  ') or line.startswith('REFUSED'):
                print(line if line.startswith('  ') else '  ' + line)
        (written if ok else failed).append(key)

    print('')
    print('  wrote %d sheet(s)' % len(written))
    for key in failed:
        print('  NOT DRAWN: %s' % key)
    for family in owed:
        print('  OWED: %-38s this backend does not build %s'
              % (family['key'], ', '.join(family['unbuilt_types'])))

    # The pictures, drawn by TechDraw itself in the GUI binary. Only the sheets
    # this run actually wrote are rendered, so a partial run cannot refresh a
    # stale sheet from an earlier one and present it as current.
    if written:
        print('')
        jobs = [{'fcstd': os.path.join(out_dir, key + '.FCStd'),
                 'stem': os.path.join(out_dir, key)} for key in written]
        print('RENDERING %d sheet(s) with TechDraw' % len(jobs))
        rendered = render_sheets.render(jobs, out_dir)
        print('')
        print('  rendered %d of %d' % (len(rendered), len(jobs)))
        failed = failed + [
            '%s (drawn, not rendered)' % os.path.basename(job['stem'])
            for job in jobs if job['stem'] not in rendered]

    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
