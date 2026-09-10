"""IP-FC-56: which sheet rows are structurally read, following the expression graph.

    freecadcmd check_reachable_rows.py --pass KIND params.json

`sweep_unread_rows.py` answers "did perturbing this row move the built geometry" -- a
numeric sample, real evidence, but blind to two things: a row that is read by a genuinely
oversized tool (the perturbation never reaches far enough to matter) reads exactly like a row
nothing touches, and a row read only by a variant the sweep never seeded (a cowling bulkhead,
say, when every seed passed was an end type) reads exactly like a row nothing anywhere reads.

This asks a different, structural question instead: starting from every geometry object's own
`ExpressionEngine` -- the properties that actually drive a solid, `Radius`, `LengthFwd`,
`Placement.Base.z` and the like -- which `Params.<alias>` cells are named, directly or through
another cell's own formula? An alias that is not reachable this way is not read by *this
document*, full stop, for any value that document's literals could hold; there is no
perturbation that would find it, because no expression ever names it.

**Two reference syntaxes, and missing the second one is a real trap.** An external object's
expression must qualify a cell as `Params.name` -- that is the only form `ExpressionEngine`
hands back. A formula written *inside* the sheet references a sibling cell by its bare alias,
with no prefix, because it is already in that object's own namespace: `slot_depth`'s own
formula is `=panel_thickness + panel_tolerance`, not `=Params.panel_thickness + ...`. A first
draft of this checker matched only the qualified form and called `panel_thickness` and `U`
themselves unreachable, which they obviously are not -- every geometry object on the sheet
depends on them through a chain of bare-name references this checker was blind to.

**One document is one variant, and a name absent from its geometry only means absent from
that build.** `is_cowling` and `is_interconnect` gate entire branches in Python
(`bulkhead_section.py` reads them with `P.get(...)` before any expression exists, to decide
which objects to construct at all) rather than through a live formula, so no run of this
checker will ever call them reachable -- that is not evidence they are unread, it is evidence
this checker cannot see a Python-level branch. Rows read only by a cowling or interconnect or
panelled build likewise need that specific kind of seed passed in to show up as reachable at
all; run this across every type and panel state a family has, the same way
`sweep_unread_rows.py` asks for several seeds, and only the intersection is a structural claim
about the family as a whole.

Run: `freecadcmd check_reachable_rows.py --pass KIND params.json [params.json ...]` -- one
run per seed, each a self-contained report; there is no seed-to-seed narrowing to do, because
unlike a perturbation this is exact per seed and the only combining step is a set intersection
left to the caller.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import build_part
import part_kinds
from corner_common import is_entry_point, script_args

QUALIFIED_RE = re.compile(r'\bParams\.([A-Za-z_][A-Za-z0-9_]*)\b')
IDENT_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')

# A function name that happens to collide with an alias would make every formula that calls
# it look like it also references that row. None of the three kinds' sheets hit this today --
# checked below rather than trusted, since a future row could.
FUNCTIONS = {'sqrt', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2', 'min', 'max',
            'abs', 'sign', 'round', 'trunc', 'exp', 'log', 'log10', 'pow', 'mod', 'pi',
            'hypot', 'radians', 'degrees'}


def aliased_cells(sheet):
    """(alias -> formula_or_None) for every aliased row, in sheet order."""
    out = {}
    row = 1
    while sheet.getContents('A%d' % row).strip():
        alias = sheet.getAlias('B%d' % row)
        if alias:
            content = sheet.getContents('B%d' % row)
            out[alias] = content if content.startswith('=') else None
        row += 1
    return out


def references(text, known):
    """Every alias `text` mentions, qualified (`Params.name`) or bare (a sibling cell)."""
    if text is None:
        return set()
    found = set(QUALIFIED_RE.findall(text))
    found |= {name for name in IDENT_RE.findall(text) if name in known}
    return found


def unreachable_rows(doc):
    """The aliases on `doc`'s `Params` sheet that no geometry object's expression reaches.

    Returns `(unreachable_sorted_list, cells_dict)`. `cells_dict` lets a caller print each
    row's own formula alongside its name.
    """
    sheet = doc.getObject('Params')
    cells = aliased_cells(sheet)
    known = set(cells)

    collisions = known & FUNCTIONS
    if collisions:
        print('WARNING: alias name(s) collide with a function name and may over-count '
             'references: %s' % ', '.join(sorted(collisions)))

    roots = set()
    for obj in doc.Objects:
        if obj.Name == 'Params':
            continue
        try:
            engine = obj.ExpressionEngine
        except Exception:
            continue
        for _prop, expr in engine:
            roots |= references(expr, known)

    reachable = set()
    frontier = list(roots)
    while frontier:
        name = frontier.pop()
        if name in reachable:
            continue
        reachable.add(name)
        for dep in references(cells.get(name), known):
            if dep not in reachable:
                frontier.append(dep)

    return sorted(set(cells) - reachable), cells


def main():
    args = script_args()
    if len(args) < 2:
        print('usage: freecadcmd check_reachable_rows.py --pass KIND params.json '
             '[params.json ...]')
        return 2
    kind, paths = args[0], args[1:]
    if kind not in part_kinds.KINDS:
        print('%r is not a kind; known kinds are %s' % (kind, ', '.join(sorted(part_kinds.KINDS))))
        return 2

    print('IP-FC-56 -- rows no geometry object\'s expression reaches (%s, %d seed(s))'
         % (kind, len(paths)))

    candidates = None
    for path in paths:
        doc = App.newDocument('reach_' + kind)
        build_part.build(doc, kind, path)
        doc.recompute()
        unreachable, cells = unreachable_rows(doc)
        print('  %-40s %3d of %3d rows unreachable'
             % (os.path.basename(path), len(unreachable), len(cells)))
        candidates = (set(unreachable) if candidates is None
                      else candidates & set(unreachable))
        App.closeDocument(doc.Name)

    print('\n  %d row(s) unreachable in every one of the %d seed(s):' %
         (len(candidates), len(paths)))
    for name in sorted(candidates):
        print('      %s' % name)
    print('\n  Structural, not statistical -- true for these seeds\' literals at any value. '
         'Still not permission to delete on its own: a row a Python branch reads with '
         '`.get()` rather than an expression (`is_cowling`, `is_interconnect`) will always '
         'land here too, and a row this list omits only because no cowling, interconnect or '
         'panelled seed was passed is not thereby proven read.')
    return 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
