"""IP-FC-86: does the sheet pin hold, and can it fail?

`drawing_standard.require_standard()` asserts that the installed font and the project's sheet
template are the ones its constants were measured from, and every drawing build calls it. A
check that has never been seen to fail is not evidence of anything -- the failure mode this
project keeps meeting is the one with no symptom, and a sheet built against the wrong template
does not crash: it renders, it exports, it diffs cleanly, and it prints with the value table
over the title block.

So this runs `verify_template` over the real template and over four broken ones, and requires
that it passes the first and names the fault in each of the others.

Run:

    freecadcmd check_sheet_standard.py

**Unit regime: millimeters.**
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawing_standard as std

from corner_common import is_entry_point

NEWLINE = chr(10)


def broken(source, replace, with_):
    """A copy of the template with one thing wrong, as a path in a temporary directory."""
    directory = tempfile.mkdtemp(prefix='sheet_pin_')
    path = os.path.join(directory, 'broken.svg')
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    if replace is not None:
        if replace not in text:
            raise ValueError('%r is not in the template, so this test breaks nothing'
                             % replace[:40])
        text = text.replace(replace, with_, 1)
    with open(path, 'w', encoding='utf-8', newline=NEWLINE) as handle:
        handle.write(text)
    return directory, path


def cases(template):
    """Four ways a template can be wrong, each of which prints rather than crashes.

    The last is the one worth having and the one a stock template cannot even express: a title
    block outside OQ-DES-D5's envelope produces a sheet whose drawn view is under the share the
    decision requires, and nothing about that sheet looks wrong.
    """
    return (
        ('the units statement removed',
         std.TEMPLATE_UNITS_TEXT, 'DIMENSIONS'),
        ('an editable field lost',
         'freecad:editable="Scale"', 'data-was="Scale"'),
        ('the frame moved',
         'id="%s" x="20.1070"' % std.TEMPLATE_FRAME_ID,
         'id="%s" x="24.1070"' % std.TEMPLATE_FRAME_ID),
        ('authored at another scale',
         'width="279.4mm"', 'width="1100px"'),
    )


def main():
    fail = []
    print('CHECK:: the sheet standard')

    template = std.template_path()
    print('  template            %s' % os.path.basename(template))
    print('  on disk             %s' % os.path.isfile(template))
    if not os.path.isfile(template):
        print('  FAIL: the template is not there. Run tools/make_sheet_template.py.')
        return 1

    problems = std.verify_template()
    print('  pin                 %s' % (problems or 'holds'))
    for problem in problems:
        fail.append('the pin does not hold: ' + problem)

    print('  font pin            %s' % (std.verify_font() or 'holds'))
    for problem in std.verify_font():
        fail.append('font pin: ' + problem)

    frame = std.frame_region_mm()
    view = std.best_view(95.1, std.table_height_mm(10),
                         std.TEMPLATE_TITLE_BLOCK_MM[2], std.TEMPLATE_TITLE_BLOCK_MM[3])
    share = view[3] / (frame[2] * frame[3])
    print('  the drawn view      %.1f%% of the frame, placed as a %s'
          % (100.0 * share, view[0]))
    if share < std.VIEW_SHARE:
        fail.append('the view gets %.1f%% of the frame, under the %.0f%% OQ-DES-D5 requires'
                    % (100.0 * share, 100.0 * std.VIEW_SHARE))

    print('  --- refusals, which must happen ---')
    for label, replace, with_ in cases(template):
        directory, path = broken(template, replace, with_)
        try:
            complaints = std.verify_template(path)
            if complaints:
                print('  %-28s refused: %s' % (label, complaints[0].split('.')[0][:70]))
            else:
                print('  %-28s NOT REFUSED' % label)
                fail.append('%s was accepted, so the pin does not cover it' % label)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    # A template that is simply absent, which is the case a fresh clone hits before
    # `make_sheet_template.py` has been run.
    missing = std.verify_template(os.path.join(tempfile.gettempdir(), 'no_such_template.svg'))
    print('  %-28s %s' % ('a missing template',
                          'refused' if missing else 'NOT REFUSED'))
    if not missing:
        fail.append('a missing template was accepted')

    print('  %s' % ('FAIL:' + NEWLINE + '    ' + (NEWLINE + '    ').join(fail) if fail
                    else 'ok -- the pin holds and every refusal refuses'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
