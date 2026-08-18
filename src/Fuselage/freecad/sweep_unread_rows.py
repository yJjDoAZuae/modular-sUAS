"""IP-FC-56: which sheet rows reach no geometry at *any* variant, not just at one.

    freecadcmd sweep_unread_rows.py --pass bulkhead a.json b.json c.json

`check_unread_rows.py` answers the question for the variant it is handed, and that is not the
question pruning asks. Measured 2026-08-18: the bulkhead has 68 rows reaching no geometry at
`1.5 end_anchor 0mm` and 67 at `1.0 end_bolt 3/16in`, and **the two lists are not nested** --
`clean_r` and `slot_y` are unread only at the first, `rect_w` only at the second. A row deleted
on the evidence of a single run is a row that may be load-bearing at a variant nobody ran.

**Narrowing, not repeating.** The first seed tests every row; each seed after it tests only the
rows still standing. The expensive pass happens once and every later one shrinks, which is what
makes a multi-seed answer affordable at roughly forty minutes for the first bulkhead pass and a
fraction of that for each seed after.

**A row surviving every seed here is still not a row that may be deleted.** It means no variant
in this set is sensitive to it, which is the necessary evidence and not the sufficient
condition: other rows may reference it, and the expression graph decides the order things can
come out in. See IP-FC-56 for what has to follow.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import parameters
import part_kinds
from check_unread_rows import measure, perturbations, refuse, why
from corner_common import is_entry_point, script_args


def sheet_rows(sheet):
    """(alias, cell) for every aliased row, in sheet order."""
    cells, row = [], 1
    while sheet.getContents('A%d' % row).strip():
        alias = sheet.getAlias('B%d' % row)
        if alias:
            cells.append((alias, 'B%d' % row))
        row += 1
    return cells


def unread_at(kind, path, u, only=None):
    """The rows of `kind` that reach no geometry at this seed.

    `only` restricts the test to a set of aliases -- the narrowing that makes the sweep
    affordable. A row outside it is not reported either way, because it has already been shown
    to be read somewhere and nothing here can change that.
    """
    module_name, table = part_kinds.KINDS[kind]
    seed = parameters.seed(path, getattr(parameters, table))
    module = __import__(module_name)

    doc = App.newDocument('sweep_' + kind)
    tip = module.emit(doc, seed)
    sheet = doc.getObject('Params')
    base = measure(tip)
    if base is None:
        refuse('%s at %s: the unperturbed part is not valid' % (kind, path))

    unread, tested = [], 0
    for alias, cell in sheet_rows(sheet):
        if only is not None and alias not in only:
            continue
        sys.stderr.write('    ... %s\n' % alias)
        sys.stderr.flush()
        original = sheet.getContents(cell)
        try:
            current = float(sheet.get(alias))
        except Exception:
            continue
        tested += 1
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
            back = why(base, measure(tip), u)
            if back:
                refuse('%s at %s: setting %s to %r and back did not restore the part -- %s'
                       % (kind, path, alias, value, back))
            if why(base, after, u):
                moved = True
                break
        if not moved:
            unread.append(alias)

    App.closeDocument(doc.Name)
    return unread, tested


def main():
    args = script_args()
    if len(args) < 2:
        print(__doc__.strip().splitlines()[0])
        print('usage: freecadcmd sweep_unread_rows.py --pass KIND params.json [params.json ...]')
        return 0
    kind, paths = args[0], args[1:]
    if kind not in part_kinds.KINDS:
        refuse('%r is not a kind; known kinds are %s'
               % (kind, ', '.join(sorted(part_kinds.KINDS))))

    print('IP-FC-56 -- rows reaching no geometry at EVERY seed (%s, %d seed(s))'
          % (kind, len(paths)))
    sys.stdout.flush()

    table = getattr(parameters, part_kinds.KINDS[kind][1])
    candidates, first = None, True
    for path in paths:
        doc = parameters.load(path)
        if table not in doc:
            print('  %-44s skipped -- carries no %r table' % (os.path.basename(path), table))
            sys.stdout.flush()
            continue
        v = doc.get('variant', {})
        if v.get('U') is None:
            refuse('%s carries no variant U, so no tolerance can be scaled to this part' % path)
        u = float(v['U'])
        label = 'U=%s %s panel=%s' % (v.get('U'), v.get('bulkhead_type_name'),
                                      v.get('panel_name'))

        unread, tested = unread_at(kind, path, u, None if first else set(candidates))
        if first:
            candidates, first = list(unread), False
            print('  %-30s %3d tested, %3d unread   (the full pass)' % (label, tested, len(unread)))
        else:
            dropped = [a for a in candidates if a not in unread]
            candidates = [a for a in candidates if a in unread]
            print('  %-30s %3d retested, %3d still unread, %d dropped%s'
                  % (label, tested, len(candidates), len(dropped),
                     '' if not dropped else ': ' + ', '.join(dropped)))
        sys.stdout.flush()

    if candidates is None:
        refuse('no seed carried a %r table, so nothing was measured' % table)

    print('\n  %d row(s) reach no geometry at any of the %d seed(s):' % (len(candidates),
                                                                        len(paths)))
    for alias in candidates:
        print('      %s' % alias)
    print('\n  This is necessary evidence for pruning, not permission: see IP-FC-56 for the '
          'expression-graph order deletion has to follow.')
    return 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
