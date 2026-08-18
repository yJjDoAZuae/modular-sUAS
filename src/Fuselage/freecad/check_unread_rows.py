"""IP-FC-56: find parameter rows that no geometry reads.

    freecadcmd check_unread_rows.py params.json           # every ported kind
    freecadcmd check_unread_rows.py params.json corner    # just one

A row on a part's sheet is supposed to be something that part is built from. Some are not:
`bulkhead_section` merges `corner_tree.PARAMS` so it can reuse `corner_end`, and `FX`,
`unit_length`, `greeble_tolerance`, `mid_h` and `mid_z0` come along with it. Nothing the
bulkhead builds reads any of them. That is invisible from the outside -- the sheet is longer
than it should be and every number on it is right -- and it stops being harmless as soon as
someone reasons from it, or exports a value for it, or asserts that a variant must supply it.

**The method is perturbation, not analysis.** Set the row to a value it does not have,
recompute, and see whether the part moves. That answers the question the expression graph
cannot: a row can be *referenced* by another row that nothing reads, so following references
finds rows that are used, not rows that matter.

**Three measurements, because volume alone is not enough.** IP-FC-55 found an eps whose
removal left the volume identical to the last digit and added four faces: the cut stopped
flush with the face it should have passed through, leaving a coincident boundary. A checker
watching only volume would have called that row unread and invited its deletion. So volume,
face count and bounding box, and a row is unread only when none of the three moves.

**What "unread" does not mean.** It does not mean the row is safe to delete on its own --
other rows may reference it, and deleting it would leave them evaluating against nothing. It
means the row does not reach the geometry, which is the evidence needed before pruning, not
the pruning itself. See IP-FC-56 for the order that has to follow.

A perturbation that makes the part fail to build counts as read: the row plainly matters, and
the failure is the proof.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import parameters
import part_kinds
from corner_common import is_entry_point, script_args

# Two perturbations, up and down, and a row counts as unread only if NEITHER moves the part.
#
# **One direction is not enough, and the first run of this script proved it.** Perturbing only
# upward reported 13 unread rows on the corner, most of which were tool dimensions that are
# generous on purpose: `through_cut`, `mask_reach`, `cut_z0`, the diagonal mask's extents. A
# cut tool sized to pass clear through the material does not care about being made longer, so
# it looks unread from above and is plainly not. Shrinking finds them.
#
# Multiplied and shifted so a row cannot land back on its own value, and so a row that is
# zero still moves. Deterministic, so two runs agree.
def perturbations(value):
    return (value * 1.3125 + 0.4375, value * 0.6875 - 0.4375)


def measure(tip):
    s = tip.Shape
    if s.isNull() or not s.isValid():
        return None
    bb = s.BoundBox
    return (s.Volume, len(s.Faces),
            (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))


def differs(a, b, tol=1e-9):
    """Whether two measurements differ in volume, face count or bounding box."""
    if a is None or b is None:
        return True
    if b[1] != a[1]:
        return True
    if abs(b[0] - a[0]) > tol:
        return True
    return max(abs(x - y) for x, y in zip(a[2], b[2])) > tol


def check_kind(kind, params_path):
    module_name, table = part_kinds.KINDS[kind]
    seed = parameters.seed(params_path, getattr(parameters, table))
    module = __import__(module_name)

    doc = App.newDocument('unread_' + kind)
    tip = module.emit(doc, seed)
    sheet = doc.getObject('Params')
    base = measure(tip)
    if base is None:
        raise SystemExit('%s: the unperturbed part is not valid' % kind)

    # The alias comes from `getAlias`, which is the sheet's own record of it. Column A holds
    # the name as *text*, and `getContents` returns it with FreeCAD's literal-text apostrophe
    # attached -- "'unit_width", not "unit_width". Parsing that column was this script's first
    # bug and it is worth naming, because of how it failed: every alias lookup missed, every
    # row was skipped as "not a number", and the report said 183 rows and nothing unread. A
    # checker that tests nothing and passes is worse than no checker, which is why `skipped`
    # is counted and refused below rather than quietly tolerated.
    cells = []
    row = 1
    while sheet.getContents('A%d' % row).strip():
        alias = sheet.getAlias('B%d' % row)
        if alias:
            cells.append((alias, 'B%d' % row))
        row += 1

    # **A row at a time, announced before it is tried and flushed immediately.**
    # Perturbation drives the geometry into states no parameter set produces, and OCCT does
    # not always survive them as a Python exception -- some kill the process outright. That is
    # tolerable; what is not is losing the whole run's output when it happens, which is what
    # buffering did: on 2026-08-17 this exited non-zero twice on the bulkhead at
    # `1.5 end_anchor 0mm` after about forty minutes each time and printed nothing at all, so
    # forty minutes of work could not say even which row it was on. Printing the row first
    # costs one line per row and turns the next crash into a diagnosis. It goes to stderr so
    # the report on stdout stays exactly as it was, and so it survives the same buffering.
    unread, skipped = [], []
    for alias, cell in cells:
        sys.stderr.write('    ... %s\n' % alias)
        sys.stderr.flush()
        original = sheet.getContents(cell)
        try:
            current = float(sheet.get(alias))
        except Exception:
            skipped.append(alias)
            continue
        moved = False
        for value in perturbations(current):
            try:
                sheet.set(alias, repr(value))
                doc.recompute()
                after = measure(tip)
            except Exception:
                after = None
            finally:
                sheet.set(alias, original)
                doc.recompute()
            if differs(base, after):
                moved = True
                break
        if not moved:
            unread.append(alias)

    restored = measure(tip)
    App.closeDocument(doc.Name)
    if differs(base, restored):
        raise SystemExit('%s: the sheet did not restore -- results are not trustworthy' % kind)
    return cells, unread, skipped


def main():
    args = script_args()
    if not args:
        print(__doc__.strip().splitlines()[0])
        print('usage: freecadcmd check_unread_rows.py params.json [kind]')
        return 0
    path = args[0]
    doc = json.load(open(path))
    wanted = args[1:] if len(args) > 1 else sorted(part_kinds.KINDS)

    print('IP-FC-56 -- parameter rows no geometry reads')
    v = doc.get('variant', {})
    print('  variant = U=%s %s panel=%s' % (v.get('U'), v.get('bulkhead_type_name'),
                                            v.get('panel_name')))
    print('  source  = %s\n' % path)
    # Flushed here, not at the end of the first kind: a kind takes tens of minutes and can die
    # inside, and a report that only appears if the run survives is no report.
    sys.stdout.flush()

    total, checked_any, bad = 0, False, []
    for kind in wanted:
        table = getattr(parameters, part_kinds.KINDS[kind][1])
        if table not in doc:
            print('  %-14s not measured -- this file carries no %r table' % (kind, table))
            continue
        cells, unread, skipped = check_kind(kind, path)
        total += len(unread)
        tested = len(cells) - len(skipped)
        checked_any = checked_any or tested > 0
        print('  %-14s %3d rows, %d tested, %d read by nothing'
              % (kind, len(cells), tested, len(unread)))
        for alias in unread:
            print('      %s' % alias)
        if skipped:
            # Named, not swallowed. A row this script could not move is a row it has said
            # nothing about, and the difference between that and "read" is the whole result.
            bad.append('%s: %d row(s) could not be perturbed: %s'
                       % (kind, len(skipped), ', '.join(skipped[:8])))
        sys.stdout.flush()

    if not checked_any:
        bad.append('no row was tested at all -- this result means nothing')
    for line in bad:
        print('\n  UNTESTED  %s' % line)

    print('\n  %s' % ('every row reaches the geometry' if not total else
                      '%d row(s) do not -- see IP-FC-56 before deleting any of them, they '
                      'may still be referenced' % total))
    return 1 if bad else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
