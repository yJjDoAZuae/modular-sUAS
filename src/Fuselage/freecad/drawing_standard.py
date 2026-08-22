"""IP-FC-21: the drawing's appearance, pinned as project data.

**Why this file exists.** `dimension_scheme.md` section 5 makes five hard constraints on where
a generated drawing puts its dimensions, and a build that violates one fails rather than
emitting the drawing. Three of them -- containment, text against text, text against geometry --
test the *rectangle an annotation occupies*, and nothing in a headless FreeCAD reports that
rectangle: `getArrowPositions()` returns the origin for both arrowheads, and no call reports
the text's rendered width. Both are computed by the GUI-side view provider, which does not
exist in a console application.

So the extent has to be known from the font. That is entirely tractable -- but only if the
font is known, and today it is not. Measured 2026-08-21 under `freecadcmd`: TechDraw's
`Labels`, `Dimensions` and `General` preference groups are **empty**, so the text is drawn with
a compiled-in default that a user preference can silently change, and the sheet template
resolves through `App.getResourceDir()` into the FreeCAD installation rather than into this
repository. **A placement bound taken from a font the reader's machine does not use is not a
bound.** This module pins both and checks the pin.

**Why the pin is checked rather than trusted.** The failure mode is the one this project keeps
meeting: a drawing built against the wrong metrics does not fail. It renders, it exports
byte-identically, it diffs cleanly, and it prints with two dimensions touching. There is no
symptom until someone reads a digit wrong. `verify_font` below recomputes the recorded numbers
from the font file actually found and refuses to proceed if they disagree -- the same shape as
`units.bbox_m_matches_mm`, and for the same reason.

**What is NOT in here, deliberately.** Nothing in this file reaches geometry, so none of it
belongs in `design_constants.json` -- that file's own membership test is "if a number reaches
an OpenSCAD module as a named argument", and a font does not. These are presentation
standards, and the sheet is where they end.

**Unit regime: millimeters**, per `units.py` -- everything here is a page dimension, and a page
is a FreeCAD-side object.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------------------
# The sheet
# --------------------------------------------------------------------------------------

# ANSI A landscape, 279.4 x 215.9 mm. Chosen because it is the smallest stock sheet that
# holds a family drawing's view plus its value table, and because the whole point of
# OQ-ARCH-7's family drawing is that one readable sheet replaces 576 crowded ones -- a
# larger sheet would be solving a problem the family drawing already solved.
TEMPLATE_RELPATH = ('Mod', 'TechDraw', 'Templates', 'ASME', 'ANSIA_Landscape.svg')
TEMPLATE_WIDTH_MM = 279.4
TEMPLATE_HEIGHT_MM = 215.9

# The sheet's own geometry, read out of that SVG on 2026-08-22 and re-asserted by
# `verify_template`. Pinned for the same reason as the font metrics, and with the same
# consequence if it is wrong: a table sized against a frame the template does not have runs
# off the sheet or wastes half of it, and nothing complains either way.
#
# Recorded by element id rather than by ordinal, because a template edit that adds a
# rectangle would renumber the ordinals and silently move the frame.
#
#   frame        `rect3675`, the inner border everything is drawn inside
#   title block  `rect2985`, which occupies the bottom right of that frame
#
# Each is (x, y, width, height) in millimeters, in the template's own coordinates -- y
# downward from the top edge, as SVG counts it.
TEMPLATE_FRAME_ID = 'rect3675'
TEMPLATE_FRAME_MM = (20.107, 14.473, 239.52, 187.2)
TEMPLATE_TITLE_BLOCK_ID = 'rect2985'
TEMPLATE_TITLE_BLOCK_MM = (112.63, 153.5, 146.66, 48.074)

# A value table's row pitch, as a multiple of the text height -- the same 2 h that
# `dimension_placement.LANE_PITCH_HEIGHTS` puts between dimension lines, so the sheet has one
# vertical rhythm rather than two. 7.0 mm at the pinned 3.5 mm text.
TABLE_ROW_PITCH_HEIGHTS = 2.0


# --------------------------------------------------------------------------------------
# The font
# --------------------------------------------------------------------------------------

# osifont is the ISO 3098 drawing face TechDraw ships in its own resources. It is pinned by
# name here rather than left to the empty preference group, and `verify_font` asserts that
# what is installed is what was measured.
#
# It is NOT vendored into this repository. Vendoring raises a licensing question -- osifont
# is LGPL-3 with a font exception -- which belongs to IP-FC-6's survey and not to a drawing
# module. Referencing the installed copy and *checking its metrics* closes the same hole
# without taking that decision: a substituted or updated font fails the build loudly instead
# of quietly changing every annotation's width.
FONT_NAME = 'osifont'
FONT_RELPATH = ('Mod', 'TechDraw', 'Resources', 'fonts', 'osifont-lgpl3fe.ttf')

# ISO 3098 preferred text heights are 2.5, 3.5, 5, 7, 10, 14 and 20 mm. 3.5 mm is the
# smallest of those that stays legible in a reduced print, which is how a shop drawing is
# usually read.
TEXT_HEIGHT_MM = 3.5

# Recorded from the pinned font on 2026-08-21 and re-asserted on every build by
# `verify_font`. Advances are in font design units; divide by UNITS_PER_EM and multiply by
# the text height to get millimeters.
UNITS_PER_EM = 2048


# ----------------------------------------------------------------------------------------
# Precision
# ----------------------------------------------------------------------------------------

# How many decimal places a length carries, and it is pinned here for the same reason the
# font is: it is not in the document either. TechDraw's `FormatSpec` defaults to two places
# from a compiled-in default -- `spike_techdraw.py` measured a 20 mm distance coming back as
# `20.00 mm` with nothing in the project asking for that -- so the number of digits a shop
# reads is currently inherited from a preference group that is empty on this machine.
#
# Two places is also the right number rather than merely the observed one. The tightest fit
# in the design is `longeron_tolerance` at 0.05 mm and `panel_tolerance` at 0.1 mm, so a
# hundredth resolves every clearance the parts are built to; a third place would print
# floating-point residue as though it were intent.
#
# **This is a drawing property with a measurement consequence.** `drawing_families.py` asks
# whether a dimension is a function of one size axis, and the honest form of that question is
# *at the precision the sheet prints*: a field that varies by 1e-13 with panel thickness is
# not a panel-dependent dimension on a sheet that writes two decimals. So the same constant
# decides the table's shape and the annotation's text, and it must not be two answers.
DECIMAL_PLACES = 2


def format_length(value_mm, decimals=DECIMAL_PLACES):
    """A length as it is written on the sheet.

    One function so the table cell, the annotation text and the separability test cannot
    disagree about what number a variant shows. `-0.00` is normalized to `0.00`: the sign of
    a value that rounds to zero is floating-point residue, and a drawing that prints it is
    stating a direction it does not mean.
    """
    text = '%.*f' % (decimals, value_mm)
    if float(text) == 0.0:
        text = '%.*f' % (decimals, 0.0)
    return text


# --------------------------------------------------------------------------------------
# Callouts
# --------------------------------------------------------------------------------------

# OQ-ARCH-7's family drawing puts a lettered callout on the view and the values in a table,
# so the text on a view is one capital and the set of strings a drawing can contain is known
# before any variant is built. That is what makes the extent a bound rather than a
# measurement, and it is the whole reason the placement problem is tractable.
#
# I, O and Q are omitted, which is drafting convention rather than preference: I reads as 1,
# and O and Q read as 0. A callout the reader mistakes for a digit is worse than one letter
# less of alphabet.
CALLOUT_ALPHABET = 'ABCDEFGHJKLMNPRSTUVWXYZ'

# The widest glyph in that alphabet, W, at 1559 units. Every callout is bounded by this one
# number, and -- because every callout is the same length -- the bound is *uniform*. A
# uniform over-estimate shifts a layout; it does not distort it. That distinction is why the
# family drawing makes a conservative bound nearly free, where on variable-length value text
# it would reject layouts that would have placed cleanly.
WIDEST_CALLOUT_UNITS = 1559
WIDEST_CALLOUT_CHAR = 'W'


# --------------------------------------------------------------------------------------
# The value table
# --------------------------------------------------------------------------------------

# The table is the one place on the sheet where variable-length value text survives, so it
# does not get the callout bound. It does not need the collision machinery either: sizing a
# column is a grid problem, each column as wide as its widest cell.
#
# **osifont's digits are not tabular**, which is worth stating because it is the natural
# assumption for a drawing face and it is false here: '1' is 700 units and '8' is 1056, a
# 50 % spread. So a column cannot be sized by counting characters. Bounding each digit
# position by the widest digit is correct and cheap.
WIDEST_DIGIT_UNITS = 1056
WIDEST_DIGIT_CHAR = '8'
DECIMAL_POINT_UNITS = 412
MINUS_UNITS = 952


def resource_dir():
    """FreeCAD's installed data directory. Imported lazily so this module reads anywhere.

    `units.py` makes the same choice for the same reason: a module that states the project's
    conventions should be readable by any interpreter, not only by one with FreeCAD in it.
    """
    import FreeCAD as App
    return App.getResourceDir()


def template_path(resource=None):
    """Absolute path to the pinned sheet template."""
    return os.path.join(resource or resource_dir(), *TEMPLATE_RELPATH)


def font_path(resource=None):
    """Absolute path to the pinned drawing font."""
    return os.path.join(resource or resource_dir(), *FONT_RELPATH)


def table_column_height_mm():
    """How much column height a value table has, in millimeters.

    The table's place on the sheet is the column beside the view and above the title block,
    which is where a reader expects it and which is the only region of the frame that is both
    tall and free. So the height is the frame's top edge down to the title block's top edge --
    139.0 mm on the pinned ANSI A landscape template.
    """
    _frame_x, frame_y, _frame_w, _frame_h = TEMPLATE_FRAME_MM
    _block_x, block_y, _block_w, _block_h = TEMPLATE_TITLE_BLOCK_MM
    return block_y - frame_y


def table_rows_available(text_height_mm=TEXT_HEIGHT_MM):
    """How many printed rows fit in that column, which is what decides whether a family fits.

    This is the number OQ-DES-D1's question turns on, and it is derived here rather than
    estimated: the frame and the title block come from the template, and the row pitch is the
    drawing standard's own. At 3.5 mm text on ANSI A landscape it is 19 -- appreciably fewer
    than the "about 25" the question was filed with, which was a guess at a sheet nobody had
    measured.
    """
    return int(table_column_height_mm() // (TABLE_ROW_PITCH_HEIGHTS * text_height_mm))


def read_template_rect(text, element_id):
    """One rectangle out of a template SVG, as (x, y, width, height) in millimeters.

    The template's `viewBox` is in millimeters and its `width` is stated in millimeters, so
    the user unit is the millimeter and no scaling applies. `verify_template` checks that
    rather than assuming it -- a template authored at another scale would report a frame of
    plausible numbers in the wrong unit.
    """
    import re

    match = re.search('<rect[^>]*id="%s"[^>]*>' % re.escape(element_id), text)
    if match is None:
        return None
    attributes = dict(re.findall('([a-zA-Z-]+)="([^"]*)"', match.group(0)))
    try:
        return tuple(float(attributes[k]) for k in ('x', 'y', 'width', 'height'))
    except (KeyError, ValueError):
        return None


def verify_template(path=None):
    """Assert the installed sheet template is the one these constants were measured from.

    Returns a list of complaints, empty when the pin holds -- the same contract as
    `verify_font`, and called from the same place.
    """
    import re

    path = path or template_path()
    problems = []

    if not os.path.isfile(path):
        return ['the pinned sheet template is not at %s' % path]

    with open(path, encoding='utf-8') as handle:
        text = handle.read()

    header = re.search('<svg[^>]*>', text)
    attributes = dict(re.findall('([a-zA-Z:-]+)="([^"]*)"',
                                 header.group(0) if header else ''))
    if attributes.get('width') != '%gmm' % TEMPLATE_WIDTH_MM:
        problems.append('the template is %r wide, not %g mm -- every figure below is in the '
                        'template user unit, and that is the millimeter only if this says so'
                        % (attributes.get('width'), TEMPLATE_WIDTH_MM))
    if attributes.get('viewBox') != '0 0 %g %g' % (TEMPLATE_WIDTH_MM, TEMPLATE_HEIGHT_MM):
        problems.append('the template viewBox is %r, not the %g x %g the recorded rectangles '
                        'were read in' % (attributes.get('viewBox'), TEMPLATE_WIDTH_MM,
                                          TEMPLATE_HEIGHT_MM))

    for element_id, recorded, what in (
            (TEMPLATE_FRAME_ID, TEMPLATE_FRAME_MM, 'drawing frame'),
            (TEMPLATE_TITLE_BLOCK_ID, TEMPLATE_TITLE_BLOCK_MM, 'title block')):
        found = read_template_rect(text, element_id)
        if found is None:
            problems.append('the template has no rectangle %r, which is where the %s was '
                            'measured' % (element_id, what))
        elif any(abs(a - b) > 5e-3 for a, b in zip(found, recorded)):
            problems.append('the %s %r is at %s, not the recorded %s -- a table sized against '
                            'it would not fit the sheet' % (what, element_id, found, recorded))
    return problems


def mm_from_units(units, text_height_mm=TEXT_HEIGHT_MM):
    """Convert a font advance in design units to millimeters at a given text height."""
    return units / float(UNITS_PER_EM) * text_height_mm


def callout_width_mm(text_height_mm=TEXT_HEIGHT_MM):
    """The bound on a lettered callout's width. The same for every callout on the sheet."""
    return mm_from_units(WIDEST_CALLOUT_UNITS, text_height_mm)


def digits_width_mm(digit_positions, decimals=0, negative=False,
                    text_height_mm=TEXT_HEIGHT_MM):
    """A bound on the width of a numeric value-table cell.

    Bounds each digit position by the widest digit rather than rendering the actual number,
    so a column sized with this holds every value that will ever appear in it -- which is
    what a column needs, since the column is sized once and the rows are the variants.
    """
    units = digit_positions * WIDEST_DIGIT_UNITS
    if decimals:
        units += DECIMAL_POINT_UNITS
    if negative:
        units += MINUS_UNITS
    return mm_from_units(units, text_height_mm)


_ADVANCE_CACHE = {}


def text_width_mm(text, text_height_mm=TEXT_HEIGHT_MM, path=None):
    """The exact rendered width of a string in the pinned font.

    **This is for the single-variant sheets, not the family sheets.** A family sheet's view
    carries one lettered callout per dimension, so `callout_width_mm` bounds every annotation
    with one number and the bound is uniform. A single-variant sheet carries the *value* --
    `112.50` is about five times the width of `W` -- so its annotations differ from each other,
    and a uniform bound would either be useless or reject layouts that fit. Measuring each
    string exactly is what the second product needs, and it costs a dictionary lookup.

    Kerning is not applied. For digits, a decimal point and a space -- which is all a dimension
    value contains -- osifont defines no kern pairs, so the sum of advances is the rendered
    width rather than an approximation of it.
    """
    path = path or font_path()
    cache = _ADVANCE_CACHE.get(path)
    if cache is None:
        cache = {}
        _ADVANCE_CACHE[path] = cache
    unknown = [c for c in text if c not in cache]
    if unknown:
        advances, _ = measure_advances(path, ''.join(sorted(set(unknown))))
        cache.update(advances)
    return mm_from_units(sum(cache[c] for c in text), text_height_mm)


def measure_advances(path, chars):
    """Advance widths in design units for `chars`, read from the font file.

    Requires `fontTools`, which is present in FreeCAD's own Python (4.61.1 as of 1.1.1) and
    is not a project dependency -- drawings are built under `freecadcmd`, so that is where
    this runs. A missing glyph is an error rather than a zero: a zero-width character would
    silently shrink every bound that used it.
    """
    from fontTools.ttLib import TTFont

    font = TTFont(path, fontNumber=0)
    cmap = font.getBestCmap()
    hmtx = font['hmtx']
    units_per_em = font['head'].unitsPerEm

    advances = {}
    missing = []
    for char in chars:
        glyph = cmap.get(ord(char))
        if glyph is None:
            missing.append(char)
            continue
        advances[char] = hmtx[glyph][0]
    if missing:
        # Named by codepoint, not by the character. A build log is not guaranteed to be
        # UTF-8 -- FreeCAD's console on Windows is cp1252 -- and an error message that
        # cannot be printed is an error message that does not exist.
        raise ValueError(
            '%s has no glyph for %s. A missing glyph measures as zero width, which would '
            'silently shrink every placement bound derived from it.'
            % (os.path.basename(path),
               ', '.join('U+%04X' % ord(c) for c in missing)))
    return advances, units_per_em


def verify_font(path=None):
    """Assert that the installed font is the one these constants were measured from.

    Returns a list of complaints, empty when the pin holds. Equality is required rather than
    a mere upper bound: a font that got *narrower* would not break a layout, but it would
    mean the recorded numbers no longer describe the file, and the next person to widen
    something would be reasoning from stale measurements.
    """
    path = path or font_path()
    problems = []

    if not os.path.isfile(path):
        return ['the pinned font is not at %s -- TechDraw would fall back to a face whose '
                'metrics nothing here describes' % path]

    advances, units_per_em = measure_advances(path, CALLOUT_ALPHABET)

    if units_per_em != UNITS_PER_EM:
        problems.append('unitsPerEm is %d, not the recorded %d, so every millimeter figure '
                        'in this module is scaled wrong' % (units_per_em, UNITS_PER_EM))

    widest = max(advances, key=lambda c: advances[c])
    if advances[widest] != WIDEST_CALLOUT_UNITS or widest != WIDEST_CALLOUT_CHAR:
        problems.append(
            'the widest callout is %r at %d units, not the recorded %r at %d -- the '
            'placement bound no longer covers every letter'
            % (widest, advances[widest], WIDEST_CALLOUT_CHAR, WIDEST_CALLOUT_UNITS))

    digits, _ = measure_advances(path, '0123456789')
    widest_digit = max(digits, key=lambda c: digits[c])
    if digits[widest_digit] != WIDEST_DIGIT_UNITS or widest_digit != WIDEST_DIGIT_CHAR:
        problems.append(
            'the widest digit is %r at %d units, not the recorded %r at %d -- value-table '
            'columns would be sized too narrow'
            % (widest_digit, digits[widest_digit], WIDEST_DIGIT_CHAR, WIDEST_DIGIT_UNITS))

    return problems


def require_font(path=None):
    """`verify_font`, but raising. Call this before building a drawing, not after."""
    _require(verify_font(path), 'the pinned drawing font does not match its recorded metrics')


def require_template(path=None):
    """`verify_template`, but raising."""
    _require(verify_template(path),
             'the pinned sheet template does not match its recorded geometry')


def require_standard():
    """Everything the sheet is pinned to, checked in one call before a drawing is built."""
    require_font()
    require_template()


def _require(problems, headline):
    if problems:
        raise ValueError(headline + ':' + chr(10)
                         + chr(10).join('  - ' + p for p in problems))
