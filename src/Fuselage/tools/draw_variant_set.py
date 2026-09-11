"""IP-FC-84: one variant's drawing set -- every part a build needs at one `U` and one panel,
collocated as a unit.

    python draw_variant_set.py U PANEL [--out DIR]

    python draw_variant_set.py 1.0 3/16in

**A set is a build kit, not a family sheet.** `draw_set.py` (IP-FC-114) draws one
representative variant per *family*, tabulated so one sheet covers many sizes. This draws
every part a builder installs to assemble one fuselage at one size and one panel stock --
single-variant sheets, numbers on the view rather than callout letters, since there is only
one size to look up (`drawing.build_sheets` has drawn those since 2026-09-10).

**Eleven parts are owed and nine can be drawn today.** 1 corner, 5 bulkhead types, 3 boom
bulkhead types, nose and tail. Nose and tail are always OWED: IP-FC-12/13's cowl port is
blocked on OQ-DES-CW16 and OQ-DES-CW18, and this backend does not build either kind at all
yet, not just at this variant.

**Some of the nine are also legitimately absent at particular `U`/panel pairs, and that is
reported, not silently skipped.** The cowling types have no panel joint of their own --
measured under IP-FC-135, "no panel interaction, one design for both cowls" -- so the sweep
marks every panel above 0mm invalid for them. Rather than report every panelled set as owing
two parts the design does not have at any panel, this draws the cowling types from their own
valid 0mm regardless of which panel the rest of the set is for, and says so on the sheet
(`DrawingTitle` already states the type; `sheet_annotations.coverage_rows` states 0mm). Every
other invalid combination -- most of the boom bulkhead's own grid past `U` = 1 -- is reported
as owed with the reason, from the same `export_parameters.py` refusal `render_variant.py`
lists, not a second guess at validity built here.

**The corner rides on a bulkhead type because it has none of its own** -- same convention
`draw_set.py` uses (`CORNER_THROUGH_TYPE`), and the same reason: a corner's own parameters do
not depend on which type supplies them, so any valid type would do, and end_bolt already is
one at every `U`/panel this sweep produces.

Reuses `export_parameters.py` for validity (a combination it cannot resolve is not drawn, the
same authority `render_variant.py` lists) and `build_sheet.py`'s single-variant mode
(IP-FC-84) for the sheet itself -- nothing here re-derives either.
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FREECAD_DIR = os.path.normpath(os.path.join(HERE, '..', 'freecad'))
sys.path.insert(0, HERE)
sys.path.insert(0, FREECAD_DIR)

import export_parameters
import freecad_render
import sheet_naming

BUILDER = os.path.join(FREECAD_DIR, 'build_sheet.py')
DEFAULT_OUT = os.path.join(FREECAD_DIR, 'out', 'sets')

CORNER_THROUGH_TYPE = 'end_bolt'

#: (label, export_type_name, draw_kind) for the nine parts this backend can draw today. Order
#: is the order a build kit lists them in: the corner first, then the five bulkhead types,
#: then the three boom bulkhead types.
#:
#: **`export_type_name` and `draw_kind` disagree for exactly one row, and that disagreement
#: is not optional.** `export_parameters.py` has no `kind=` argument -- it resolves the
#: family from the type name alone (`fv.family_of(want_type)`), and a corner has no type axis
#: of its own, so `CORNER_THROUGH_TYPE` supplies one purely to get a valid export. But the
#: export carries both halves of a frame variant (`parameters` for the bulkhead,
#: `corner_parameters` for the corner it mates with), and which half gets *drawn* is a
#: separate question `check_drawing.PARAMS_KEY` answers by `draw_kind`, not by
#: `export_type_name`. Collapsing the two to one field drew a bulkhead sheet under the
#: corner's own filename the first time this ran -- `corner.dxf` came out 89913 bytes with
#: `DimE`/`DimB`/`DimA`/`DetailViewLabel`, the bulkhead's own signature, not the corner's
#: single `DimF`/`DimA` SECTION view -- because `draw_variant` was handed `export_type_name`
#: ('bulkhead') where it needed `draw_kind` ('corner'). Found and fixed 2026-09-10.
PARTS = [
    ('corner', CORNER_THROUGH_TYPE, 'corner'),
    ('bulkhead_end_anchor', 'end_anchor', 'bulkhead'),
    ('bulkhead_end_bolt', 'end_bolt', 'bulkhead'),
    ('bulkhead_cowling_anchor', 'cowling_anchor', 'bulkhead'),
    ('bulkhead_cowling_bolt', 'cowling_bolt', 'bulkhead'),
    ('bulkhead_interconnect', 'interconnect', 'bulkhead'),
    ('boom_bulkhead_offset_single', 'offset_single', 'boom_bulkhead'),
    ('boom_bulkhead_center_single', 'center_single', 'boom_bulkhead'),
    ('boom_bulkhead_dual', 'dual', 'boom_bulkhead'),
]

#: A cowling bulkhead has no panel of its own -- IP-FC-135 -- so it is always drawn from its
#: own 0mm, whatever panel the rest of the set is for.
FIXED_PANEL = {
    'cowling_anchor': '0mm',
    'cowling_bolt': '0mm',
}

#: Owed regardless of `U` or panel: this backend does not build either kind at all.
ALWAYS_OWED = [('nose', 'IP-FC-12/13 blocked on OQ-DES-CW16 and OQ-DES-CW18'),
              ('tail', 'IP-FC-12/13 blocked on OQ-DES-CW16 and OQ-DES-CW18')]

#: What a sheet leaves behind, and what has to be gone before it is drawn again -- the same
#: set `draw_set.clear` uses, duplicated rather than imported because that module also drags
#: in `drawing_families`, which this script has no other reason to load.
SHEET_SUFFIXES = ('.FCStd', '.FCStd1', '.dxf', '.svg', '.pdf', '.png')


def clear(stem):
    gone = 0
    for suffix in SHEET_SUFFIXES:
        for pattern in sheet_naming.sheet_glob(stem):
            for path in glob.glob(pattern + suffix):
                os.remove(path)
                gone += 1
    return gone


def export_for(u, type_name, panel, path):
    """Resolve and write one part's parameters. `False` on a combination this backend does
    not sweep -- the same refusal `render_variant.py` would list, not a second check.

    Takes a type name and nothing else identifying which part: `export_parameters.py` has no
    `kind=` argument, because it resolves the family from `type_name` alone."""
    code = export_parameters.main([str(u), type_name, str(panel), path])
    return code == 0 and os.path.isfile(path)


def draw_variant(freecadcmd, params_path, kind, stem):
    """One single-variant sheet, in its own interpreter. Returns `(ok, output)`.

    No `families.json`, no `key` -- `build_sheet.py`'s single-variant mode (IP-FC-84), which
    draws the numbers a callout letter would otherwise point at, because there is nothing
    else in this set to tabulate against.
    """
    clear(stem)
    argv = [freecadcmd, BUILDER, '--pass', params_path,
            '--pass', 'kind=%s' % kind, '--pass', 'out=%s' % stem]
    done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = done.stdout.decode('utf-8', 'replace')
    # freecadcmd's exit code is not trusted -- the artefact is, same reasoning as
    # `draw_set.draw`.
    return os.path.isfile(stem + '.FCStd'), text


def build_set(u, panel, out_dir, freecadcmd, say=print):
    """Every part of one set. Returns `(drawn, owed)`, each a list of `(label, detail)`."""
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    drawn, owed = [], []
    for label, type_name, draw_kind in PARTS:
        actual_panel = FIXED_PANEL.get(type_name, panel)
        params_path = os.path.join(out_dir, label + '.params.json')
        if not export_for(u, type_name, actual_panel, params_path):
            owed.append((label, 'no such combination at U=%s panel=%s (see render_variant.py)'
                        % (u, actual_panel)))
            continue
        stem = os.path.join(out_dir, label)
        ok, text = draw_variant(freecadcmd, params_path, draw_kind, stem)
        if ok:
            drawn.append((label, actual_panel))
            say('  %-32s drawn (panel=%s)' % (label, actual_panel))
        else:
            headline = next((l for l in text.splitlines() if l.startswith('REFUSED')), None)
            owed.append((label, headline or 'build_sheet.py did not write a sheet'))
            say('  %-32s NOT DRAWN: %s' % (label, headline or '(no artefact; see log)'))

    for label, reason in ALWAYS_OWED:
        owed.append((label, reason))

    return drawn, owed


def main(argv):
    if len(argv) < 2:
        print('usage: draw_variant_set.py U PANEL [--out DIR]')
        print('run render_variant.py with no arguments to list valid U/panel combinations')
        return 2
    u, panel = argv[0], argv[1]
    out_dir = DEFAULT_OUT
    if '--out' in argv:
        out_dir = argv[argv.index('--out') + 1]
    out_dir = os.path.join(out_dir, 'U%s_%s' % (u, panel.replace('/', '-')))

    try:
        freecadcmd = freecad_render.freecadcmd_path()
    except Exception as exc:                                            # noqa: BLE001
        print('freecadcmd not found: %s' % exc)
        return 2

    print('DRAWING SET -- U=%s panel=%s' % (u, panel))
    print('  out                 %s' % out_dir)
    drawn, owed = build_set(u, panel, out_dir, freecadcmd)

    print('')
    print('  drawn %d of %d parts' % (len(drawn), len(PARTS)))
    for label, reason in owed:
        print('  OWED: %-32s %s' % (label, reason))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
