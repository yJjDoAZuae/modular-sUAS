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

**Every measurement is against one baseline, so restoring has to be exact.** A row is set,
recomputed, and set back, and the whole method assumes setting it back returns the part to the
state the baseline was taken from. That is checked after every perturbation rather than assumed
-- and where it fails the run stops there and says which row and by how much, because a row
that does not restore invalidates every row after it and nothing else this script prints would
mean anything.
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


# **The volume test is relative, and it has to be, because the kernel does not repeat itself
# exactly.** Rebuilding a part from the parameters it was built from, after having built a
# different part in between, does not return bit-identical volume: OCCT lands a few parts in
# 1e10 away. Face count and bounding box do come back exactly; only volume moves.
#
# Measured 2026-08-17 at `1.5 end_anchor 0mm`, perturbing all 154 rows both ways and setting
# each back: 142 of the 308 restores miss by more than 1e-9 mm^3 and the worst misses 2.602e-4
# mm^3 on a 17406 mm^3 part, which is 1.5e-8 of it. Most of them sit at a constant 4.128e-8
# mm^3 -- the document takes a small step early and then holds it, rather than accumulating
# without bound.
#
# It is the kernel and not the tangency sketch IP-FC-73 introduced. The solved centers do drift
# under the same perturbations, which makes the sketch look guilty; forcing it to re-solve to
# convergence after every restore drives all four centers to within 2e-15 mm of their build
# values and leaves the volume miss exactly as it was. The rows that move the sketch are simply
# the rows that move the fillet solids, so the two drift together without one causing the other.
#
# The tolerance was absolute at 1e-9 mm^3, which is 6e-14 of a bulkhead -- far finer than the
# kernel can repeat. That is why only the bulkhead failed: the corner is small enough that
# 1e-9 mm^3 still sits above the floor. An absolute tolerance applied to parts of very
# different sizes is the whole of the bug, and it cost two silent forty-minute runs.
#
# 1e-6 *relative* is 1.7e-2 mm^3 here, some 67 times the worst miss measured, and what that
# gives up is negligible on a part at this scale. A row whose entire contribution is under
# 0.017 mm^3 is a cube 0.26 mm on a side, or about 0.14 mm of a single extrusion bead at 0.6 mm
# wide and 0.2 mm tall -- smaller than the printer's own quantum, on a bulkhead 100*U mm across.
# No feature this port builds is that small, so no row that reaches the geometry hides under it.
#
# Two things back that up rather than resting on it. The volume test was never the sensitive one
# -- IP-FC-55 is precisely the case of a row that moved the volume by nothing at all and the
# face count by four, which is why there are three measurements and not one -- and face count
# and bounding box are both still exact. And the failure modes are not symmetric: too tight
# refuses loudly, as this did, while too loose reports a read row as unread and invites its
# deletion. 67x keeps the loud failure off kernel noise without making the quiet one reachable.
#
# **Being relative is how this one scales with `U`.** Every tolerance here has to, for the
# reason `compare_backends.bbox_tol()` states at length: a part's coordinates grow linearly
# with `U` -- `unit_width` is 100*U -- so its volume grows as U^3, and any floating-point noise
# floor grows with the magnitude of the numbers it comes out of. Expressing the volume test as
# a fraction of the part's own volume *is* the U^3 scaling, stated in the form that reads
# correctly for a volume; a threshold linear in U would be wrong for a cubic quantity.
#
# The zero-volume case keeps an absolute floor so the test cannot become vacuous.
VOLUME_TOL = 1e-6       # relative to the part's own volume, which is to say proportional to U^3

# **The bounding box is a length, so it scales linearly**, exactly as
# `compare_backends.BBOX_TOL_PER_U` does and for the same reason -- and floored at U = 1 for
# the same reason too, that scaling all the way down only *tightens* a threshold below U = 1,
# which is a change nobody asked for and which can only newly fail parts. Delete the `max` to
# make it purely proportional.
#
# Unlike the volume test this one has never fired: no refusal in any run has named the bounding
# box, at any U. It is scaled because leaving one absolute tolerance among scaled ones is how
# the bug this file just fixed got written in the first place, not because it is known to be
# too tight anywhere.
GEOMETRY_TOL_PER_U = 1e-9      # mm at U = 1
GEOMETRY_TOL_FLOOR_U = 1.0


def geometry_tol(u):
    """The bounding-box tolerance for a part built at size `u`, in mm."""
    return GEOMETRY_TOL_PER_U * max(u, GEOMETRY_TOL_FLOOR_U)


def differs(a, b, u):
    """Whether two measurements differ in volume, face count or bounding box."""
    return why(a, b, u) is not None


def why(a, b, u):
    """The same test, saying which of the three moved and by how much, or None if none did.

    `differs` answers the question this script asks of every row and needs nothing more. The
    *refusals* need more: both of them end a run that has already cost the better part of an
    hour, and "the sheet did not restore" on its own sends the next person back to spend that
    hour again just to learn which measurement it was.
    """
    if a is None or b is None:
        return 'one of the two measurements is a null or invalid shape'
    if b[1] != a[1]:
        return 'face count %d -> %d' % (a[1], b[1])
    if abs(b[0] - a[0]) > VOLUME_TOL * max(abs(a[0]), 1.0):
        return ('volume %.9f -> %.9f (%+.3e, %.1e of the part)'
                % (a[0], b[0], b[0] - a[0], abs(b[0] - a[0]) / max(abs(a[0]), 1.0)))
    box = max(abs(x - y) for x, y in zip(a[2], b[2]))
    btol = geometry_tol(u)
    return (None if box <= btol else
            'bounding box moved %.3e mm, over %.3e mm at U = %s' % (box, btol, u))


# freecadcmd discards the message a `SystemExit` carries -- measured 2026-08-17: a script that
# raises `SystemExit('...')` prints everything before it, exits 1, and shows nothing of the
# message. So a refusal raised the obvious way is a non-zero exit with no explanation, which is
# the worst possible ending for a check that runs for an hour first. `parameters.table_of`
# documents the same finding and the same workaround: say it on stderr, flush, then exit.
def refuse(message):
    sys.stderr.write('\ncheck_unread_rows: %s\n' % message)
    sys.stderr.flush()
    sys.stdout.flush()
    raise SystemExit(1)


def check_kind(kind, params_path, u):
    module_name, table = part_kinds.KINDS[kind]
    seed = parameters.seed(params_path, getattr(parameters, table))
    module = __import__(module_name)

    doc = App.newDocument('unread_' + kind)
    tip = module.emit(doc, seed)
    sheet = doc.getObject('Params')
    base = measure(tip)
    if base is None:
        refuse('%s: the unperturbed part is not valid, so there is nothing to compare '
               'perturbations against. Nothing was tested.' % kind)

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
            # **Restoration is checked here, per row, and not only once at the end.** Which row
            # failed to restore is the one thing an end-of-run check cannot say: by the time it
            # runs, every row has been perturbed and put back, and the refusal can name none of
            # them. Checked inside the loop it costs one measurement per perturbation and names
            # the row while the run is still standing on it -- and it stops immediately, rather
            # than spending another half hour measuring rows against a baseline that has moved.
            back = why(base, measure(tip), u)
            if back:
                refuse('%s: setting %s to %r and then back did not restore the part -- %s.\n'
                       'Every row before this one was measured against the original part and '
                       'stands. Nothing after it would mean anything, because the baseline the '
                       'comparison rests on has moved.' % (kind, alias, value, back))
            if differs(base, after, u):
                moved = True
                break
        if not moved:
            unread.append(alias)

    # Kept as a backstop even though the per-row check above makes it unreachable by
    # construction: it is the assertion that the whole run rests on, and an assertion that
    # cannot fail costs nothing to state.
    restored = measure(tip)
    App.closeDocument(doc.Name)
    moved_at_end = why(base, restored, u)
    if moved_at_end:
        refuse('%s: the sheet did not restore -- %s. Results are not trustworthy.'
               % (kind, moved_at_end))
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
    # Read rather than defaulted, and refused rather than assumed, for the reason
    # `compare_backends.u_of()` gives: a part whose size is unknown cannot be checked at
    # the right tolerance, and quietly taking U = 1 would apply a threshold too tight on
    # the large parts and report failures that are not real -- which is the whole of what
    # the scaling fixes.
    if v.get('U') is None:
        refuse('%s carries no variant U, so no tolerance can be scaled to this part'
               % path)
    u = float(v['U'])
    # Flushed here, not at the end of the first kind: a kind takes tens of minutes and can die
    # inside, and a report that only appears if the run survives is no report.
    sys.stdout.flush()

    total, checked_any, bad = 0, False, []
    for kind in wanted:
        table = getattr(parameters, part_kinds.KINDS[kind][1])
        if table not in doc:
            print('  %-14s not measured -- this file carries no %r table' % (kind, table))
            continue
        cells, unread, skipped = check_kind(kind, path, u)
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
