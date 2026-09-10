"""IP-FC-21: does a generated sheet hold together, on a real part?

`check_dimension_placement.py` checks the solver on 2D coordinates and
`check_sheet_standard.py` checks the sheet pin. Neither builds a part, and everything between
them -- projecting the
model, binding a dimension to points computed from parameters, getting a note and its leader
onto the page, choosing a scale -- only exists once a real solid is on a real page.

So this builds one, and then asks the questions that can only be asked of the finished page:

    1. does the drawn view get the share OQ-DES-D5 requires
    2. does every dimension report the value the parameters say, rather than the view's
       scaled distance -- a dimension bound to the wrong thing still prints a number
    3. is every annotation inside the frame
    4. does the page export, and does the export carry the dimensions and the notes
    5. do two builds of the same variant export the same bytes
    6. does the value table fit its band, land where the layout says, and survive the export

**Question 4 was asked too weakly until 2026-08-27 and passed a broken sheet.** It looked for
`BORE`, which is the first line of the first note, and `writeDXFPage` writes exactly one TEXT
entity per annotation however many lines the annotation holds. Every sheet was exporting one
line of each note and dropping the rest, and this check reported the export carried the
callout. It now looks for *every* line of *every* note, which is the only form of the question
that could have failed.

Run:

    freecadcmd check_drawing.py --pass params.json families.json kind=bulkhead

`kind=` rather than `--kind`, because `freecadcmd` claims any argument starting with `--`
for its own option parser even after `--pass`, and answers with its usage text instead of
running the script. `--pass --kind=bulkhead` is accepted too -- that is the form the rest of
this project passes arguments in, and a checker that only took one of the two spellings would
be a small trap for whoever runs it next.

**Every kind with an annotation set, not just the corner.** It was corner-only until
2026-08-27, which is how the corner's unpanelled family went unbuilt long enough for its
sheet to become undrawable -- a check that only ever builds one variant of one kind is a check
that reports on one variant of one kind.

**Unit regime: millimeters.**
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import dimension_placement as dp
import drawing
import drawing_standard as std
import part_kinds
import sheet_annotations
import sheet_table

from corner_common import is_entry_point

NEWLINE = chr(10)
TOLERANCE = 1e-6


def out_dir():
    path = os.environ.get('CHECK_DRAWING_OUT') or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'out')
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def export(page, path):
    import TechDraw

    TechDraw.writeDXFPage(page, path)
    with open(path, 'rb') as handle:
        return handle.read()


# Which key in an exported parameter file a kind's sheet is drawn from. One export carries a
# whole frame variant -- the bulkhead and the corner it mates with -- so the kind chooses. The
# boom bulkhead's own export carries no corner (IP-FC-12: "a boom bulkhead has no corner of its
# own"), so it is the only key in its file rather than one of two.
PARAMS_KEY = {'corner': 'corner_parameters', 'bulkhead': 'parameters',
             'boom_bulkhead': 'boom_parameters'}


def is_panelled(params):
    return abs(params.get('panel_thickness', 0.0)) > 1e-9


def check_view(entry, doc, placement, fail, note_text):
    """One view's dimensions, containment and note objects, appended to `fail`/`note_text`."""
    layout = entry.layout
    view = entry.view
    label = entry.spec.name

    # The dimensions have to report what the parameters say. A dimension bound to the wrong
    # vertices still prints a confident number, and the view scale leaking into the value is
    # the specific failure `spike_techdraw` measured this against.
    for placed in layout:
        name = 'Dim' + placed.letter
        obj = doc.getObject(name)
        if obj is None:
            fail.append('%s was placed on %s but no dimension object was made'
                        % (name, label))
            continue
        got = obj.getRawValue()
        want = abs(placed.dimension.value)
        mark = 'ok' if abs(got - want) <= TOLERANCE else 'WRONG'
        print('  %-19s %s = %.4f mm, parameters say %.4f  %s  [%s]'
              % (name, obj.Type, got, want, mark, label))
        if mark == 'WRONG':
            fail.append('%s reports %.6f mm where the parameters say %.6f -- it is bound to '
                        'the wrong points, or the view scale is leaking into the value'
                        % (name, got, want))

    # H1 over the finished layout, re-derived rather than trusted: `place` already refuses a
    # layout that leaves the frame, so this failing would mean the frame it was given is not
    # the frame the page has. Each view is checked against **its own region**, which is what
    # it was placed in -- checking a detail against the whole view region would pass a layout
    # that runs across the sheet into the plan.
    complaints = dp.check_placement(
        layout, [],
        drawing.frame_in_view(view, entry.region, drawing.origin_offset(view)),
        notes=layout.notes)
    print('  independent check   %s  [%s]' % (complaints or 'clean', label))
    for complaint in complaints:
        fail.append('the finished page, %s: %s' % (label, complaint))

    missing = []
    for placed in layout.notes:
        name = 'Note' + str(placed.key).title()
        for index, line in enumerate(placed.note.lines):
            obj = doc.getObject(name + ('L%d' % index))
            if obj is None:
                missing.append('%s line %d' % (placed.key, index))
            else:
                note_text.append(line)
    if missing:
        fail.append('no annotation object for note %s' % ', '.join(missing))
    print('  note text           %d notes  [%s]' % (len(layout.notes), label))


def family_of(document, kind, params, type_name=None):
    """The family record this variant belongs to, or None.

    **Not "whichever family of this kind comes first".** A kind's families are a topology
    partition, and handing a sheet the wrong one gives it a table of columns the part has no
    dimensions for -- every number in it plausible and none of them about this part. Two
    things separate them and both are readable from the variant: the type name, where the kind
    has a type axis, and whether the part has a panel.

    The panel test is asked of the *table* rather than of the topology signature, because the
    signature is computed in the virtualenv from a resolved parameter object this side cannot
    build. A family whose table carries `panel_thickness` is the panelled one.
    """
    wanted = is_panelled(params)
    span = sheet_annotations.corner_seat_span(params)
    seated = span is not None and span > 0.0
    for candidate in document['families']:
        if candidate['kind'] != kind or not candidate.get('quantity_blocks'):
            continue
        # A kind with no type axis has one type name, its own; anything else has to match.
        if candidate['type_names'] != [kind] and type_name not in candidate['type_names']:
            continue
        carries = any(c['field'] == 'panel_thickness'
                      for b in candidate['quantity_blocks'] for c in b['columns'])
        if carries != wanted:
            continue
        # **The seating flat, since OQ-DES-D6 made it part of the partition.** Read off the
        # family's own topology signature rather than inferred from its table, because two
        # families can tabulate the same quantities and differ in whether the face is there --
        # which is exactly the pair the split created.
        flag = dict((str(name), value) for name, value in candidate.get('topology', []))
        if 'corner seating flat' in flag and flag['corner seating flat'] is not True \
                and flag['corner seating flat'] is not False:
            return candidate                      # 'absent': this kind has no such face
        if 'corner seating flat' in flag and flag['corner seating flat'] != seated:
            continue
        return candidate
    return None


def dxf_lines(text):
    """Every LINE entity in a DXF, as a rounded (x_min, y_min, x_max, y_max).

    A minimal reader on purpose: the question is where a handful of rules landed, and pulling
    in a DXF library to answer it would make the check depend on a second interpretation of
    the file the export writes. Group codes 10/20 are the start point and 11/21 the end.

    Rounded to two decimals, and compared as an unordered box rather than as an ordered pair
    of endpoints, because which end of a rule the exporter writes first is not something the
    layout decides or should be asserting.
    """
    rows = text.replace(chr(13), '').split(chr(10))
    out = set()
    index = 0
    while index < len(rows):
        if rows[index].strip() == 'LINE':
            values = {}
            scan = index + 1
            while scan + 1 < len(rows) and rows[scan].strip() not in ('0',):
                code = rows[scan].strip()
                if code in ('10', '20', '11', '21'):
                    try:
                        values[code] = float(rows[scan + 1])
                    except ValueError:
                        pass
                scan += 2
            if len(values) == 4:
                xs = (values['10'], values['11'])
                ys = (values['20'], values['21'])
                out.add((round(min(xs), 2), round(min(ys), 2),
                         round(max(xs), 2), round(max(ys), 2)))
            index = scan
            continue
        index += 1
    return out


def main(argv):
    fail = []
    paths = [a for a in argv if a.endswith('.json')]
    if not paths:
        print('usage: freecadcmd check_drawing.py --pass params.json [families.json] '
              '[kind=KIND]')
        return 2
    params_path = paths[0]

    kind = 'corner'
    for argument in argv:
        # Both spellings, because `freecadcmd`'s own option parser claims a bare `--kind`
        # even after `--pass` and answers with its usage text instead of running the script.
        # `--pass --kind=KIND` is the form that survives it; `kind=KIND` is the shorter one
        # that also does.
        for prefix in ('--kind=', 'kind='):
            if argument.startswith(prefix):
                kind = argument.split('=', 1)[1]
    if kind not in sheet_annotations.ANNOTATIONS:
        print('no annotation set for %r -- have %s'
              % (kind, ', '.join(sorted(sheet_annotations.ANNOTATIONS))))
        return 2

    with open(params_path, encoding='utf-8') as handle:
        exported = json.load(handle)
    # One export carries both halves of a frame variant: the bulkhead under `parameters` and
    # its matching corner under `corner_parameters`. Which one a sheet is drawn from is the
    # kind, so it is read here rather than assumed.
    params = exported[PARAMS_KEY[kind]]

    # The family this variant belongs to, which is what carries the value table. Optional so
    # the check still runs on a machine that has not regenerated the families file, and
    # reported as absent rather than skipped silently -- a sheet drawn without its table is a
    # sheet whose callout letters point at nothing, and that must not look like a pass.
    family = None
    # **The other families of this kind, because the sheet's own statement of what it is
    # depends on them.** `branch_phrase` names the topology conditions that *differ* between
    # the families of a kind; given none to compare against it names them all, which is a
    # longer string, which is a wider sheet-coverage block, which is a refusal on a sheet the
    # set draws without complaint. A checker that draws a different sheet from the one under
    # test is not checking it.
    siblings = ()
    if len(paths) > 1:
        with open(paths[1], encoding='utf-8') as handle:
            document = json.load(handle)
        family = family_of(document, kind, params,
                           (exported.get('variant') or {}).get('bulkhead_type_name'))
        siblings = [f for f in document['families'] if f.get('kind') == kind]

    print('CHECK:: a generated sheet')
    print('  kind                %s' % kind)
    print('  variant             %s' % exported.get('variant', '?'))
    print('  family              %s' % (family['key'] if family else
                                        'NONE -- pass families.json to draw the table'))

    # A family whose types this backend does not build must be *refused*, and the check is
    # that it refuses rather than that it draws. Reporting the refusal as a failure would make
    # a correctly-behaving tool look broken, and reporting nothing would let the day the
    # refusal stops working pass unnoticed.
    expect_refusal = bool(family is not None
                          and part_kinds.unbuilt_types(kind, family.get('type_names', ())))
    if expect_refusal:
        print('  builder             does not build %s -- a refusal is the pass'
              % ', '.join(part_kinds.unbuilt_types(kind, family['type_names'])))

    bodies = []
    note_text = []
    table_drawn = None
    for run in ('a', 'b'):
        doc = App.newDocument('check_drawing_' + kind + '_' + run)
        try:
            # IP-FC-134: `build_sheets` (plural), not the single-page `build_sheet` this
            # called until 2026-09-09. `build_sheet` hands back only `sheets[0]` -- correct
            # for a corner or a boom bulkhead, which are one page, but a frame bulkhead's
            # DETAIL A is `sheets[1]`, and every note this kind writes lives there. The
            # checker was exporting page 1 and asking it for notes that were always on page
            # 2: not a TechDraw DXF defect, a wrong artifact. `build_sheet.py`, the tool that
            # writes the real deliverable, was never affected -- it already calls this and
            # writes one DXF per sheet.
            sheets = drawing.build_sheets(
                doc, kind, params_path, params, family,
                variant=exported.get('variant'), siblings=siblings)
        except dp.PlacementError as exc:
            # A refusal is a result, not a crash. Section 5.6 says an unplaceable sheet is a
            # drafting decision to be made deliberately, and a traceback is a worse way to
            # say so than a failure with the refusal's own words in it.
            print('  REFUSED             %s' % str(exc).split(NEWLINE)[0])
            if not expect_refusal:
                fail.append('the sheet could not be drawn: ' + str(exc))
            App.closeDocument(doc.Name)
            break

        built = [sheet.view for sheet in sheets]
        scale = built[0].scale

        if run == 'a':
            # The same fixed region `build_sheet` used to construct for the lead page alone --
            # every sheet gets the whole band (`build_sheets`' own docstring), so one is enough.
            left, bottom, frame_w, frame_h = drawing.frame_page_box()
            band_depth = std.TEMPLATE_TITLE_BLOCK_MM[3]
            placement = drawing.Placement(
                std.PLACEMENT_BAND,
                (left, bottom + band_depth, frame_w, frame_h - band_depth))
            frame = std.frame_region_mm()
            region = placement.view_region
            share = (region[2] * region[3]) / (frame[2] * frame[3])
            print('  scale               %g:1' % scale if scale >= 1.0
                  else '  scale               1:%g' % (1.0 / scale))
            print('  view region         %.1f x %.1f mm, %.1f%% of the frame'
                  % (region[2], region[3], 100.0 * share))
            # Compared with a tolerance, and the tolerance is not slack: the band's depth is
            # *defined* as one minus the share, so the region is the share by construction and
            # this is a number being compared with itself through two floating-point
            # operations. It came back 0.7499999999999999 the first time it ran.
            print('  layout              %s' % placement.name)
            # **The share requirement is about the band, and only the band can meet it.**
            # OQ-DES-D5's 75% is one minus the band's depth, so in that placement this is a
            # number compared with itself and the check is a guard against the arithmetic
            # drifting. A sheet in the column placement is there precisely because its table
            # does not fit the band; holding it to the band's share would fail every such
            # sheet for the reason it exists, and would say nothing about whether it was
            # drawn correctly. It is reported instead, because a reader should see that this
            # sheet gives its view less room than the requirement asks for.
            if placement.name == std.PLACEMENT_BAND:
                if share < std.VIEW_SHARE - 1e-9:
                    fail.append('the view region is %.4f%% of the frame, under the %.0f%% '
                                'OQ-DES-D5 requires'
                                % (100.0 * share, 100.0 * std.VIEW_SHARE))
            elif share < std.VIEW_SHARE - 1e-9:
                print('  NOTE                this sheet is in the %s placement and its view '
                      'has %.1f%% of the frame, under the %.0f%% OQ-DES-D5 asks for -- see '
                      'OQ-DES-D15' % (placement.name, 100.0 * share, 100.0 * std.VIEW_SHARE))

            # **Every view, not only the leading one.** A sheet with a plan and a corner
            # detail carries most of its dimensions and all of its notes on the detail, and
            # a checker that inspects `layout` alone inspects the plan's two dimensions and
            # reports "0 of 0 note lines" on a sheet with five notes -- a pass that means
            # nothing, which is worse than a failure. Measured 2026-09-07, on the run that
            # first split a bulkhead in two.
            print('  views               %s'
                  % ', '.join('%s at %s (%d dim, %d note)'
                              % (b.spec.name, drawing.format_scale(b.scale),
                                 len(b.layout), len(b.layout.notes)) for b in built))

            note_text = []
            for entry in built:
                check_view(entry, doc, placement, fail, note_text)


            # The table. Laid out again here rather than read off the page, because the point
            # is whether the page agrees with the layout: comparing the page with itself would
            # pass whatever it drew.
            table = None
            if family is not None and family.get('quantity_blocks'):
                table = sheet_table.layout(family['quantity_blocks'], family['letters'])
                band = std.table_region_mm()
                print('  value table         %.1f x %.1f mm into a %.1f x %.1f band, '
                      '%d cells, %d rules'
                      % (table.width, table.height, band[2], band[3],
                         len(table.cells), len(table.rules)))
                for problem in table.fits(band):
                    fail.append('the value table: ' + problem)
                table_drawn = table

                # H1 and H2 over the table itself, the same two questions
                # `dp.check_placement` asks of the view's annotations. A table is where they
                # are easiest to get wrong, because a column is sized once against strings it
                # is assumed to hold.
                complaints = sheet_table.check_layout(table)
                print('  table layout        %s'
                      % (complaints[0] if complaints else 'clean'))
                for complaint in complaints:
                    fail.append('the value table: ' + complaint)

                # Every column has to be addressable from the view -- OQ-DES-D5's whole
                # point. The letters the table prints as headings are checked against the
                # letters the annotations carry, which are issued by `sheet_annotations` on
                # this variant's parameters rather than read from the family record.
                issued = {q.name: q.letter
                          for q in sheet_annotations.quantities_for(kind, params)
                          if q.letter}
                disagree = sorted(k for k in set(issued) | set(family['letters'])
                                  if issued.get(k) != family['letters'].get(k))
                print('  callout letters     %d issued, table agrees: %s'
                      % (len(issued), not disagree))
                if disagree:
                    fail.append(
                        'the table heads %s with a different letter than the view puts on it, '
                        'so a reader following the callout lands in the wrong column'
                        % ', '.join(disagree))

        # One DXF per page -- TechDraw's own limitation, and `build_sheet.py` writes the
        # deliverable the same way -- concatenated here because this check only ever asks
        # the combined bytes a substring question (a DIMENSION count, a note line's text),
        # never anything that depends on one page's DXF being well-formed on its own.
        page_bodies = []
        for sheet in sheets:
            suffix = '' if sheet.number == 1 else str(sheet.number)
            page_bodies.append(export(sheet.page, os.path.join(
                out_dir(), 'check_drawing_%s_%s%s.dxf' % (kind, run, suffix))))
        bodies.append(b''.join(page_bodies))
        App.closeDocument(doc.Name)

    if expect_refusal and bodies:
        fail.append('the sheet was drawn for a family whose types this backend does not '
                    'build, so the drawing set contains a plausible wrong part')

    if not bodies:
        if expect_refusal and not fail:
            print('  ok -- refused, which is what a family this backend cannot build must do')
            return 0
        print('  %s' % ('FAIL:' + NEWLINE + '    ' + (NEWLINE + '    ').join(fail)))
        return 1

    body = bodies[0]
    text = body.decode('utf-8', 'replace')
    dimensions = body.count(b'DIMENSION')
    lines_in = [line for line in note_text if line in text]
    print('  DXF                 %d bytes, %d DIMENSION entities' % (len(body), dimensions))
    print('  note lines exported %d of %d' % (len(lines_in), len(note_text)))
    print('  two runs identical  %s' % (bodies[0] == bodies[1]))

    if dimensions == 0:
        fail.append('the exported page carries no DIMENSION entities, so the export drops '
                    'the only thing UC-7a is for')
    dropped = [line for line in note_text if line not in text]
    if dropped:
        fail.append('the export drops %d of %d note lines -- %s. The hardware the feature is '
                    'for is on those lines, so the deliverable states the feature and not '
                    'what it is for.'
                    % (len(dropped), len(note_text), '; '.join(repr(d) for d in dropped[:3])))

    # The table, in the export. Its cells are text and its rules are geometry, and the two
    # fail differently: a missing cell is a value the sheet does not state, a missing rule is
    # a 1.0 mm gutter with nothing in it, which is section 5.2's H2 failure.
    if table_drawn is not None:
        cells_in = [c for c in table_drawn.cells if c.text in text]
        print('  table cells exported %d of %d'
              % (len(cells_in), len(table_drawn.cells)))
        if len(cells_in) < len(table_drawn.cells):
            absent = [c.text for c in table_drawn.cells if c.text not in text]
            fail.append('the export drops %d table cells -- %s'
                        % (len(absent), ', '.join(repr(a) for a in absent[:5])))

        # Where the rules landed, read back rather than assumed. A `DrawViewPart` centers its
        # projection on the shape's own center, and this is the only thing that says the
        # centering did what the arithmetic expected -- a table drawn 20 mm from where the
        # layout put it renders perfectly well and sits on the title block.
        placed = dxf_lines(text)
        want = set()
        for (x1, y1), (x2, y2) in table_drawn.rules:
            a = drawing.page_point((x1, y1))
            b = drawing.page_point((x2, y2))
            want.add((round(min(a[0], b[0]), 2), round(min(a[1], b[1]), 2),
                      round(max(a[0], b[0]), 2), round(max(a[1], b[1]), 2)))
        found = want & placed
        print('  table rules placed   %d of %d at the laid-out coordinates'
              % (len(found), len(want)))
        if len(found) < len(want):
            missed = sorted(want - found)[:3]
            fail.append(
                'the export carries %d of %d table rules at the coordinates the layout gives '
                '-- first missing %s. The rules are what pays for the 1.0 mm column gutter, '
                'so a table without them is section 5.2\'s H2 failure in the deliverable.'
                % (len(found), len(want), missed))
    if bodies[0] != bodies[1]:
        fail.append('two builds of the same variant exported different bytes, so a drawing '
                    'set cannot be reviewed by diff')

    print('  %s' % ('FAIL:' + NEWLINE + '    ' + (NEWLINE + '    ').join(fail) if fail
                    else 'ok -- the sheet builds, binds, places and exports'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main(sys.argv)
    sys.stdout.flush()
    sys.exit(_code)
