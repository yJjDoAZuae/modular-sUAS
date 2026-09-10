"""IP-FC-9 / IP-FC-41: bulkhead_section assembled from every ported constituent.

This is the whole octant of an ordinary bulkhead -- make_web true, is_interconnect and
is_cowling false -- and it is the last check the port needs before tiling:

    positives   bulkhead_flange_positive     (eight pieces, see bulkhead_positive.py)
                bolt_flange_positive         \\
                bolt_flange_fillet            > simple_positives.py
                bolt_web                     /
                bulkhead_web                 web.py
    negatives   the greeble-forming tool     bulkhead_tree.py -- corner_end re-evaluated
                the opening wedge            \\
                the outer cleanup             \\
                the longeron bore              > bulkhead_cuts.py
                the bolt hole                 /
                the octant mask              /

Sixteen modules, and **not one sketched profile among them**. That was not the expected
outcome: the working assumption at IP-FC-38 was that arbitrary polygons would force
sketches. Every profile the bulkhead defines turned out to be a convex region -- a covering
box minus the half-planes of its non-axis-aligned edges -- and where an edge's angle moves
with the parameters, `Placement.Rotation.Angle` takes an expression just as `Placement.Base`
does.

The assembled section contains two sketches and neither is a profile. One is the corner's:
the greeble tool is corner_end, and corner_end's wedge is one of the corner's two genuinely
non-convex profiles, so reusing the corner's description brings the corner's sketch with it.
The other is the bulkhead's own `FilletTangency` -- construction geometry whose `Tangent`
constraints solve all four rounded corners' centers at once, replacing subtractions and two
clamped square roots with relationships the solver checks and a reader can see. It began as
`BffTangency`, one sketch for the bolt-flange fillet (OQ-DES-B14, 2026-08-16); OQ-ARCH-14
merged the four into one on 2026-08-17, so the count here stayed at two sketches while the
number of solved corners went from one to four. **It carries only the corners this variant
has**, which is why the section is 142 nodes at some parameter sets and 153 at others.

Those fillets' *profiles* are still half-planes, which is scope and not capability: the
bolt-flange profile does change topology across the parameter space, from a quad to a triangle
on 18 of the 88 valid end-type variants, but a document is generated per parameter set so the
generator can simply emit the topology those parameters call for.
`fillets._fillet_tangency_sketch()` carries the measurement.

What this proves that the isolated checks could not: `ref_bulkhead_cuts.scad` transcribes
five cut tools the source builds inline, so comparing against it only shows the port matches
the transcription. Here the reference goes through the real `bulkhead_section`, so a
transcription error is a volume divergence. Same for `ref_flange_boss.scad`, one level down.

IP-FC-41 is what made this possible at all. The constituents each carried their own sheet of
literal values; sharing a document means one sheet, and `corner_tree` -- which the greeble
tool is built from -- carries `fuselage_corner.scad`'s hand driver values, not the swept set.
The two disagree on six parameters, including greeble_thickness 0.8 against 1.2, which is the
snap post's wall. Merging them by name would have silently built the post at two thirds
thickness. So the sheet is *seeded* from `derived_parameters()` instead: every literal comes
from the authority, and only the '=' rows -- the relationships, which are the port itself --
have to agree between modules.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import bulkhead_cuts
import bulkhead_positive
import bulkhead_tree
import corner_tree as C
import cowl_rim
import fillets
import flange_base
import flange_boss
import greeble_web
import parameters
import simple_positives
import web
from corner_common import build_sheet, check_seed, is_entry_point, merge_params, script_args

# The octant, at mask_eps = 0. **Deliberately not the OpenSCAD number**, which is 865.7400435
# with the bounding box reaching y = -13.6618. OpenSCAD's octant is oversized by the mask
# overlap its union wants; OCCT does not want it (IP-FC-49), so this one is exactly an eighth
# and stops a hair short across the diagonal. The offset between the two is the mask overlap
# and nothing else, -0.4549745, and this constant is OpenSCAD's number less that.
#
# That makes this constant more useful than it was, not less: 8 x REF is now the full part's
# volume exactly, so bulkhead_full's tiling check reads as "the eight pieces tile with neither
# gap nor overlap" rather than "matches a number 3.6 mm3 short of eight octants".
#
# Regenerated 2026-08-11 for the OQ-DES-B12 fix, which takes 0.029 mm3 out of the octant by
# making the greeble tool's snap rib nominal. OpenSCAD moved by -0.0290279 and FreeCAD by
# -0.0290299: the two kernels agreeing on the SIZE OF THE CHANGE to 2e-6 mm3 is what says the
# fix did the same thing on both sides, and it is a stronger check than either number alone.
REF = 865.2850690
EXPECT_BBOX = (-40.0, -13.6569, 0.0, 0.0, 5.1375, 6.0)

# **The one variant REF and EXPECT_BBOX actually describe -- checked, not assumed.** Found
# 2026-09-10: `main()` took whatever `params.json` a caller passed on faith, and `out/` is
# gitignored, so a file named `ref_end_bolt.params.json` is whatever the last regeneration
# left there -- 0mm panel one day, 3/16in the next. Comparing the unpanelled octant against
# these numbers reads as a 2.88% volume miss and a bounding box that moved, which is neither:
# the panelled octant reproduces REF to 2e-6 mm3, so the constants were always right and the
# file passed in was the wrong variant, silently. `main()` now checks the seed's own `variant`
# before trusting it, rather than reporting a geometry regression that was really a file mixup.
REF_VARIANT = {'U': 1.0, 'bulkhead_type_name': 'end_bolt', 'panel_name': '3/16in'}

# IP-FC-56: rows `corner_tree.PARAMS` carries for the corner's *other* two sections and for
# its own (unprefixed) greeble socket, read by nothing a bulkhead builds. The bulkhead's
# greeble tool is `corner_tree.end_section` called with `pfx='gt_'`
# (`bulkhead_tree.greeble_tool()`), so every row that call addresses resolves to
# `Params.gt_name` -- and `bulkhead_tree.GREEBLE_TOOL_PARAMS` supplies a complete `gt_`-
# prefixed replacement for each one of these. They arrive on the bulkhead's sheet only as a
# side effect of merging `corner_tree.PARAMS` wholesale to also pick up `_section()`'s bare-
# named calls (`slot_w`, `mask_reach`, `corner_radius`, ...), which have no prefix and so are
# not in this list. Proved dead, not assumed: `check_reachable_rows.py`, run across all seven
# type/panel combinations a bulkhead has, found every one of these unreachable from any
# geometry object in every single one, and `sweep_unread_rows.py`'s independent perturbation
# sweep agrees. `corner_tree.py` itself is untouched -- the corner's own three sections still
# read every one of these in full; only what reaches the *bulkhead's* sheet is trimmed.
_CORNER_TREE_DEAD_ON_BULKHEAD = frozenset([
    'FX', 'cut_z0', 'end_h', 'end_z0', 'greeble_nub_height', 'greeble_nub_radius',
    'greeble_radius', 'greeble_tolerance', 'mid_h', 'mid_z0', 'mouth_w', 'mouth_x',
    'mouth_y', 'nub_span', 'nub_z1', 'nub_z2', 'nub_z3', 'nub_z4', 'relief_depth',
    'relief_diag', 'relief_mid', 'relief_top', 'through_cut', 'trans_h', 'trans_z0',
    'unit_length',
])


class _CornerTreeOnBulkhead(object):
    """`corner_tree.PARAMS`, minus the rows proved dead on a bulkhead's own sheet.

    A view, not a copy of the module: `merge_params` only ever reads `.PARAMS`, so this is
    the whole of what stands in for `corner_tree` in `SOURCES` below, and `C` itself -- used
    elsewhere in this file for `_fuse`/`_owned`/`_cut`/`_SEEN`, none of them parameter-related
    -- is unaffected.
    """
    __name__ = C.__name__
    PARAMS = [row for row in C.PARAMS if row[0] not in _CORNER_TREE_DEAD_ON_BULKHEAD]


# corner_tree last: its '=' rows restate relationships the bulkhead modules also define, and
# putting it first would make every conflict message point at it rather than at the module
# that actually introduced the second definition.
SOURCES = [flange_base, greeble_web, fillets, flange_boss, simple_positives, web,
           bulkhead_cuts, cowl_rim, _CornerTreeOnBulkhead]

# IP-FC-132: which of the two type flags this section is built at. Neither is a dimension,
# both are structural zeros on the sheets that do not need them (IP-FC-56's argument for
# corner_tree's rows applies here too). Both `is_cowling` and `is_interconnect` are acted on
# in `emit()` below.
TYPE_PARAMS = [
    ('is_cowling', '0.0'),
    ('is_interconnect', '0.0'),
]


def merged_rows(seed):
    """Every constituent's alias table as one, seeded from the exported parameter set.

    `seed` is not optional here. Without it the merge is a comparison of two different
    configurations and refuses -- correctly, because at the hand driver's values this
    assembly would not be a bulkhead the sweep produces.
    """
    return (merge_params(SOURCES, seed) + list(bulkhead_tree.GREEBLE_TOOL_PARAMS)
           + TYPE_PARAMS)


def sheet(doc, seed, rows=None):
    """One sheet for every constituent. `rows` lets a part built on top of this one -- see
    bulkhead_full.py -- add its own without a second sheet."""
    return build_sheet(doc, merged_rows(seed) if rows is None else rows, seed)


def emit(doc, seed, rows=None, make_web=True):
    """`make_web` is which of an interconnect's two mirrored halves this is (IP-FC-132) --
    the end and cowling types never vary it, since `bulkhead_section_octant`'s
    non-interconnect branch always builds a single call at `make_web=True`.
    """
    C._SEEN.clear()
    sheet(doc, seed, rows)
    P = doc.getObject('Params')
    is_cowling = float(P.get('is_cowling')) >= 0.5
    is_interconnect = float(P.get('is_interconnect')) >= 0.5

    positive = bulkhead_positive.flange_positive(
        doc, is_cowling=is_cowling, is_interconnect=is_interconnect, make_web=make_web)

    # `simple_positives.bolt_positives` is the source's `if (!is_interconnect)` group --
    # an interconnect bolts to its neighbour rather than carrying a bolt of its own.
    if not is_interconnect:
        positive = C._fuse(doc, 'SectionSimple', positive,
                           simple_positives.bolt_positives(doc))
    # `bulkhead_web` is the source's `if (make_web)` -- an interconnect's mirrored top half
    # has none, and which shape it builds where it does have one follows `is_interconnect`.
    if make_web:
        web_part = (web.bulkhead_web_interconnect(doc) if is_interconnect
                   else web.bulkhead_web(doc))
        positive = C._fuse(doc, 'SectionWeb', positive, web_part)

    if is_cowling:
        # IP-FC-132: the other three of the six is_cowling positives (simple_positives'
        # docstring), plus the two the assembled reference caught were missing from it --
        # see cowl_rim.py. No greeble socket to cut on a cowling bulkhead: it does not mate
        # with a corner, so `bulkhead_tree.greeble_tool` never runs.
        positive = simple_positives.cowl_positives(doc, positive)
        positive = cowl_rim.add(doc, positive)
        negative = bulkhead_cuts.cuts(doc, is_cowling=True)
    else:
        # An interconnect keeps the greeble socket -- only is_cowling gates that away --
        # and keeps the opening wedge and outer cleanup with it; only the bolt hole is
        # additionally excluded, inside bulkhead_cuts.cuts() itself.
        negative = C._fuse(doc, 'SectionTools', bulkhead_tree.greeble_tool(doc),
                           bulkhead_cuts.cuts(doc, is_interconnect=is_interconnect))

    tip = C._owned(doc, 'Part::Refine', 'BulkheadSection')
    tip.Source = C._cut(doc, 'SectionCut', positive, negative)
    doc.recompute()
    return tip


def main():
    # `--pass` is freecadcmd's escape for arguments meant for the script rather than for
    # freecadcmd, and it forwards the token itself as well as the value -- so it has to be
    # filtered here, exactly as build_part.py does. Without the filter the seed path is read
    # as the literal string '--pass' and the run dies on a file-not-found that names a flag.
    args = script_args()
    if not args:
        print('usage: freecadcmd bulkhead_section.py --pass params.json')
        print('generate params.json with '
             '`export_parameters.py %s %s %s`'
             % (REF_VARIANT['U'], REF_VARIANT['bulkhead_type_name'], REF_VARIANT['panel_name']))
        return 0

    file_variant = parameters.load(args[0]).get('variant') or {}
    got_variant = {k: file_variant.get(k) for k in REF_VARIANT}

    seed = parameters.seed(args[0])
    doc = App.newDocument('bulkhead_section')
    tip = emit(doc, seed)
    is_cowling = float(doc.getObject('Params').get('is_cowling')) >= 0.5
    is_interconnect = float(doc.getObject('Params').get('is_interconnect')) >= 0.5
    s = tip.Shape
    bb = s.BoundBox
    got = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)

    label = (' (is_cowling)' if is_cowling
             else ' (is_interconnect)' if is_interconnect else '')
    print('PART:: CSG tree -- bulkhead_section assembled%s' % label)
    print('  nodes   = %d, sketches = %d'
          % (len(doc.Objects), len([o for o in doc.Objects if o.isDerivedFrom(
              'Sketcher::SketchObject')])))
    print('  volume  = %.7f' % s.Volume)

    mismatch = False
    if is_cowling:
        # REF and EXPECT_BBOX are the end type's octant, at mask_eps = 0 -- not a shape an
        # is_cowling octant is. IP-FC-132 has no isolated octant reference for this branch;
        # the binding check is bulkhead_full's, against the real OpenSCAD full-part render.
        print('  ref     = -- (no octant-only reference for is_cowling; see bulkhead_full.py)')
        d = None
    elif is_interconnect:
        # Same reasoning: an interconnect's octant is two mirrored halves (bulkhead_full.py),
        # a different shape REF/EXPECT_BBOX were never computed against.
        print('  ref     = -- (no octant-only reference for is_interconnect; '
             'see bulkhead_full.py)')
        d = None
    elif got_variant != REF_VARIANT:
        # Told which variant REF describes and worked out which variant this file is --
        # `build_sheet.py`'s own rule for a family key, applied here to a hand check.
        # Comparing anyway reports a volume/bbox "regression" that is really a file mismatch,
        # which is exactly the failure IP-FC-56 found by hand on 2026-09-10: `out/` is
        # gitignored, so a file named `ref_end_bolt.params.json` is whatever the last
        # regeneration left there, and the panelled octant this constant describes reproduces
        # it to 2e-6 mm3.
        mismatch = True
        print('  ref     = -- REFUSED: REF/EXPECT_BBOX are U=%s %s panel=%s; this file is '
             'U=%s %s panel=%s. Regenerate with `export_parameters.py %s %s %s`'
             % (REF_VARIANT['U'], REF_VARIANT['bulkhead_type_name'], REF_VARIANT['panel_name'],
                got_variant['U'], got_variant['bulkhead_type_name'], got_variant['panel_name'],
                REF_VARIANT['U'], REF_VARIANT['bulkhead_type_name'], REF_VARIANT['panel_name']))
        d = None
    else:
        d = s.Volume - REF
        print('  ref     = %.7f  (OpenSCAD, through the real module)' % REF)
        print('  delta   = %+.7f  (%+.5f%%)' % (d, 100 * d / REF))
        print('  bbox    = [%s]' % ', '.join('%.4f' % v for v in got))
        print('  expect  = [%s]' % ', '.join('%.4f' % v for v in EXPECT_BBOX))
    print('  valid   = %s  solids=%d  faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    drift = check_seed(doc.getObject('Params'), seed)
    if drift:
        print('  sheet   = DISAGREES with derived_parameters():')
        for alias, got, want in drift:
            print('            %-24s sheet %-14s derived %s' % (alias, got, want))
    else:
        print('  sheet   = every seeded alias reproduces derived_parameters()')

    fail = []
    if drift:
        fail.append('the sheet does not reproduce the derived parameter set')
    if not s.isValid():
        fail.append('invalid shape')
    if len(s.Solids) != 1:
        fail.append('%d solids -- the octant is one connected body' % len(s.Solids))
    if mismatch:
        fail.append('wrong variant passed -- see the REFUSED line above')
    elif d is not None:
        if abs(d) / REF > 1e-3:
            fail.append('volume off by more than 0.1%')
        if max(abs(a - b) for a, b in zip(got, EXPECT_BBOX)) > 1e-3:
            fail.append('bounding box moved')
    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
