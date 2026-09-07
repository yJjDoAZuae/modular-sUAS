"""IP-FC-99 step one: which dimensions have more than one requirement that can govern them.

    python branching_dimensions.py
    python branching_dimensions.py --sites

**Why the count matters before the layout does.** DES-9 says that where more than one
requirement can govern a dimension, the drawing states which one produced the value shown. The
evidence is `corner.flat_offset`, a `max()` of a longeron term and a panel term where the two
branches split the family and one of them removes a face entirely -- a drawing showing the
number without the note is right about the number and silent about the geometry. But nothing
has ever asked **how many such dimensions there are**, and that number is what sizes the note
budget on a sheet whose drawn view is already at 75.4 % against a 75 % requirement. A layout
decision taken before the count is a guess.

**Two layers, and the second one is where DES-9's own example lives.** The count has to cover
both, and they cannot be imported into one interpreter. The *parameter* layer is
`check_derivation.RELATIONS`, reached through `fuselage_variants`, which needs `solid2` from
the virtualenv. The *geometry* layer is `corner_common.Params`, whose module imports FreeCAD.
This tool owns the first and drives `freecad/geometry_branches.py` for the second, handing the
variants over as JSON.

**That second layer is not a refinement, it is a correction.** `flat_offset` -- register row 3,
the `max()` of a longeron term against a panel term, the dimension whose branch decides whether
a face exists at all -- is **not** a `check_derivation` relation, not a declared given, and not
a field of the swept parameters. Measured 2026-09-06: no relation or sweep field of any name
containing `flat_offset` exists. It is computed in `Params.__init__`. So the premise this step
was filed under -- that `check_derivation` already evaluates both branches for every variant --
is false for the one dimension the requirement was written about, and a count taken from the
parameter layer alone would have looked complete while missing it.

**How the branches are found: by watching, not by reading.** Every derivation lives in
`check_derivation.RELATIONS` as a Python callable, so this replaces `max` and `min` *in that
module's namespace* for the duration of a sweep and records, at each call site, which argument
won on each variant. Nothing about the derivations changes and nothing is restated here -- a
second copy of the relations would drift from the first, and the copy that moved would win
silently.

That gets `max` and `min`, which is what DES-9's own evidence is made of. **What it does not
get is a plain conditional**, an `if`/`else` that returns different expressions, because no
call is made to intercept. Those are found by reading the source of each relation and listed
separately as *branching, not instrumented* rather than quietly omitted -- a report that
silently covers only what its instrument happens to see is worse than one that names the gap.

**A call site that always resolves the same way is reported, not filtered out.** DES-9 is
about which requirement *can* govern, so a dimension whose second branch never wins on today's
axes is still a dimension with two requirements behind it -- and the branch that never wins
today is the one that starts winning when a constant changes. What the split *does* decide is
how expensive the note is: a field that resolves the same way for every variant of a family
can carry one note on the family sheet, and a field that splits within a family needs a note
whose text varies by variant, which is a much larger demand on the layout.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_derivation as cd
import drawing_families as df
import freecad_render

#: The geometry-layer half, run under `freecadcmd` because its module imports FreeCAD.
GEOMETRY_BRANCHES = os.path.normpath(
    os.path.join(HERE, '..', 'freecad', 'geometry_branches.py'))

#: Set while a relation is being evaluated, so a recorded call can be attributed to the field
#: it was computing. A module global rather than an argument because the call sites being
#: watched are `max` and `min` inside expressions nobody is going to thread a parameter through.
_FIELD = [None]

#: (field, function, line, name) -> {winning argument index: variants}
SITES = {}

#: A tie, as a branch label. Numeric like the others because `minimal_axes` compares through
#: `written()`, which answers `None` for anything that is not a number -- so a string label
#: would compare equal to every other string label and every branch would be reported constant.
#: Negative so it cannot collide with an argument index.
TIE = -1.0

#: (field, function, line, name) -> {variant index: winner}. Aggregate counts say how often a
#: branch wins; only this says *which* variants, and that is what decides whether the note can
#: be factored onto the same axes as the value it explains.
PER_VARIANT = {}

#: Index of the variant being evaluated, within its own kind.
_AT = [0]

#: kind -> [axis_values per variant], parallel to `_AT`, built the way `drawing_families.resolve`
#: builds them so the two describe the same axes.
AXIS_VALUES = {}

#: Ties, kept apart from wins. Two branches agreeing on a value is not one of them governing --
#: it is the case where the note has nothing to choose between, and counting it as a win for
#: the first argument would overstate how often that branch decides anything.
TIES = {}


def axis_values(kind, row):
    """One variant's axis values, built exactly as `drawing_families.resolve` builds them.

    Copied in shape rather than imported because `resolve` runs its own enumeration and
    returning to it here would mean trusting two enumerations to agree on order. The axes
    themselves come from the one `SWEEPS` entry, so there is still a single authority on what
    the axes *are*.
    """
    out = {}
    for label, column in df.SWEEPS[kind]['axes']:
        value = row[column]
        out[label] = float(value) if label in ('U', 'FX') else str(value)
    return out


def _tally(counts):
    return '  '.join('arg %d wins %d' % (i, n) for i, n in sorted(counts.items()))


def _watching(name, chooser):
    """`max` or `min`, recording which argument won and where."""
    def watched(*args, **kwargs):
        value = chooser(*args, **kwargs)
        # The single-iterable form is a fold over a collection, not a choice between named
        # alternatives, so there is no requirement on either side of it to report.
        if kwargs or len(args) < 2:
            return value
        frame = sys._getframe(1)
        key = (_FIELD[0], frame.f_code.co_name, frame.f_lineno, name)
        winners = [i for i, a in enumerate(args) if a == value]
        if len(winners) > 1:
            TIES[key] = TIES.get(key, 0) + 1
            PER_VARIANT.setdefault(key, {})[_AT[0]] = TIE
        else:
            counts = SITES.setdefault(key, {})
            counts[winners[0]] = counts.get(winners[0], 0) + 1
            PER_VARIANT.setdefault(key, {})[_AT[0]] = float(winners[0])
        return value
    return watched


def sweep():
    """Every relation on every variant of every sweep, with `max` and `min` under watch.

    Returns `{kind: variant count}`. The recorded sites accumulate in `SITES` and `TIES`.
    """
    const = cd.constants()
    original = (getattr(cd, 'max', max), getattr(cd, 'min', min))
    cd.max = _watching('max', max)
    cd.min = _watching('min', min)
    counted = {}
    try:
        for kind in df.SWEEPS:
            relations = cd.COWL_RELATIONS if df.SWEEPS[kind].get('cowl') else cd.RELATIONS
            rows = cd.variants(kind)
            counted[kind] = len(rows)
            AXIS_VALUES[kind] = [axis_values(kind, row) for row, _U, _FX, _f in rows]
            for index, (row, U, FX, _flat) in enumerate(rows):
                _AT[0] = index
                g = cd.givens(kind, row, U, FX, const)
                d = {}
                for relation in relations:
                    _FIELD[0] = (kind, relation.field)
                    d[relation.field] = relation.derive(g, d)
    finally:
        cd.max, cd.min = original
        _FIELD[0] = None
    return counted


#: A relation whose body contains one of these branches without calling `max` or `min`, so the
#: watcher above cannot see it. Matched on source text, which is a weak instrument and is
#: labelled as one in the output.
CONDITIONAL = re.compile(r'\bif\b.*\belse\b|^\s*if\b', re.M)


def uninstrumented():
    """Relations that branch on a conditional, which no call interception can catch."""
    import inspect
    out = []
    for relation in cd.RELATIONS + cd.COWL_RELATIONS:
        try:
            source = inspect.getsource(relation.derive)
        except (OSError, TypeError):
            continue
        if CONDITIONAL.search(source) is None:
            continue
        if 'max(' in source or 'min(' in source:
            note = 'conditional as well as a max/min'
        else:
            note = 'conditional only -- nothing above sees this'
        out.append((relation.field, note))
    return out


def params_inputs(kind):
    """Exactly what `corner_common.Params` takes, per variant, read off the sweep.

    Every name here is a key the sweep actually carries -- checked 2026-09-06 rather than
    assumed, because reconstructing a constructor's arguments from a neighbouring vocabulary
    is the kind of guess that produces a plausible wrong number.
    """
    const = cd.constants()
    out = []
    for row, U, FX, flat in cd.variants(kind):
        out.append({'U': U, 'FX': FX,
                    'bulkhead_thickness': float(flat['bulkhead.thickness']),
                    'panel_thickness': float(row.get('panel_thickness_mm', 0)),
                    'panel_offset': float(flat['panel.offset']),
                    'panel_overlap': float(flat['panel.overlap']),
                    'panel_tolerance': float(flat['panel.tolerance']),
                    'longeron_tolerance': float(flat['longeron.tolerance']),
                    'greeble_thickness': float(flat['greeble.thickness']),
                    'greeble_tolerance': float(flat['greeble.tolerance']),
                    'extrusion_width': float(const['extrusion_width'])})
    return out


def geometry_layer(kinds=('corner', 'bulkhead', 'boom_bulkhead')):
    """Run `geometry_branches.py` under freecadcmd. Returns its parsed lines, or a reason."""
    import json
    import subprocess
    import tempfile

    try:
        freecadcmd = freecad_render.freecadcmd_path()
    except Exception as exc:                                            # noqa: BLE001
        return None, 'freecadcmd not found: %s' % exc

    entries = []
    for kind in kinds:
        entries.extend(params_inputs(kind))
    handle, path = tempfile.mkstemp(suffix='.json', prefix='branching_')
    os.close(handle)
    try:
        with io.open(path, 'w', encoding='utf-8') as out:
            out.write(json.dumps(entries))
        done = subprocess.run([freecadcmd, GEOMETRY_BRANCHES, '--pass',
                               '--variants=%s' % path],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        os.remove(path)

    rows, total = [], None
    for line in done.stdout.decode('utf-8', 'replace').splitlines():
        if line.startswith('VARIANTS '):
            total = int(line.split()[1])
        elif line.split('\t')[0] in ('BRANCH', 'TIE', 'PER'):
            rows.append(line.split('\t'))
    if total is None:
        return None, ('geometry_branches.py produced no result%s%s'
                      % (chr(10), done.stderr.decode('utf-8', 'replace')[-1500:]))
    return (total, rows), None


def factor_report(kinds=('corner', 'bulkhead', 'boom_bulkhead')):
    """Does a branch follow the same axes as the value it explains?

    **This is the question OQ-DES-D13's implementation turns on, and it is not the one that
    was asked first.** The family table is *factored by axis* -- one short table per size axis,
    a field in each column, one row per value of that axis -- rather than one row per variant.
    So a `GOVERNED BY` annotation is only a paired column in an existing block if the branch is
    a function of **the same axes the value is**. If it follows more axes, it does not fit
    beside the value at all: it needs a block of its own, which costs rows and columns rather
    than the 6.92 mm of width the decision was measured against.

    `drawing_families.minimal_axes` is what decides a table's shape, so it is what decides
    this too -- the same function on the branch label instead of on the value. Anything else
    would be a second authority on the same question.

    Returns a list of `(kind, field, value_axes, branch_axes, verdict)`.
    """
    rows = []
    for kind in kinds:
        axes = [label for label, _column in df.SWEEPS[kind]['axes']]
        variants = cd.variants(kind)
        values = AXIS_VALUES.get(kind)
        if not values:
            continue

        # **DES-9 is about the value *shown*, so a branching quantity the sheet never prints
        # needs no note.** The obligation is `interface_fields`, which is what section 3 holds
        # the sheet to, and the two vocabularies differ -- the derivation writes `panel.offset`
        # and the sheet writes `panel_offset` -- so the correspondence is made explicit here
        # rather than assumed, and a field that maps to nothing is reported as not shown.
        resolved = df.resolve(kind)
        shown = df.interface_fields(kind, set(resolved[0][2])) if resolved else set()

        found = {}
        # The parameter layer.
        for (field_key, _func, _line, _name), seen in sorted(PER_VARIANT.items()):
            at_kind, field = field_key
            if at_kind == kind and len(set(seen.values())) > 1:
                found[field] = dict(seen)

        # The geometry layer, whose winners come back one character per variant in the order
        # the entries were handed over -- which is `cd.variants(kind)`'s order, the same order
        # `values` is in, so they line up without trusting two enumerations to agree.
        result, _why = geometry_layer((kind,))
        if result is not None:
            for row in result[1]:
                if row[0] != 'PER':
                    continue
                seen = {}
                for i, mark in enumerate(row[3]):
                    if mark == '-':
                        continue
                    seen[i] = TIE if mark == 't' else float(mark)
                if len(set(seen.values())) > 1:
                    found[row[1]] = seen

        for field in sorted(found):
            seen = found[field]
            branch = [(values[i], {field: seen[i]}) for i in sorted(seen)]
            value = [(values[i], {field: variants[i][3][field]})
                     for i in sorted(seen) if field in variants[i][3]]
            branch_axes = df.minimal_axes(branch, field, axes)
            value_axes = df.minimal_axes(value, field, axes) if value else None
            on_sheet = field.replace('.', '_') in shown
            rows.append((kind, field, value_axes, branch_axes, on_sheet,
                         _verdict(value_axes, branch_axes, on_sheet)))
    return rows


def _verdict(value_axes, branch_axes, on_sheet):
    if not on_sheet:
        return 'not shown on the sheet -- DES-9 asks about the value shown, so no note'
    if branch_axes is None:
        return 'NOT A FUNCTION OF THE AXES -- cannot be tabled at all'
    if branch_axes == ():
        return 'one branch governs the whole family -- one note, not a column'
    if value_axes is None:
        return 'shown, but not tabled -- nothing to ride beside'
    if set(branch_axes) <= set(value_axes):
        return 'rides beside the value'
    return 'follows MORE axes than the value -- needs a block of its own'


def main(argv):
    counted = sweep()
    total = sum(counted.values())
    print('BRANCHING DIMENSIONS -- IP-FC-99 step one')
    print('  %d variants over %d sweeps: %s'
          % (total, len(counted),
             ', '.join('%s %d' % (k, n) for k, n in sorted(counted.items()))))
    print('')

    # Collapse the per-kind records into one row per field, since a field is what carries a
    # note. The per-kind split is kept alongside, because a field that resolves one way for a
    # whole family costs one note and a field that splits inside one costs a note per variant.
    by_field = {}
    for (field_key, func, line, name), counts in SITES.items():
        kind, field = field_key
        entry = by_field.setdefault(field, {'sites': {}, 'kinds': {}})
        site = entry['sites'].setdefault((func, line, name), {})
        for index, n in counts.items():
            site[index] = site.get(index, 0) + n
        per_kind = entry['kinds'].setdefault(kind, set())
        per_kind.update(counts.keys())

    split, single = [], []
    for field in sorted(by_field):
        decided = set()
        for site in by_field[field]['sites'].values():
            decided.update(site.keys())
        multi = any(len(site) > 1 for site in by_field[field]['sites'].values())
        (split if multi else single).append(field)

    print('  %d fields where both branches actually win somewhere in the sweep. **Not all of '
          'these' % len(split))
    print('  need a note**: DES-9 is about the value *shown*, and only some of them are printed')
    print('  on a sheet -- see the budget below, which is the number that governs:')
    for field in split:
        entry = by_field[field]
        within = sorted(k for k, seen in entry['kinds'].items() if len(seen) > 1)
        print('    %-34s %s' % (field, 'splits inside %s' % ', '.join(within) if within
                                else 'splits only between sweeps, never inside one'))
        if '--sites' in argv:
            for site, counts in sorted(entry['sites'].items()):
                if len(counts) < 2:
                    continue
                func, line, name = site
                print('        %s:%d %s  %s' % (func, line, name, _tally(counts)))
                # Per sweep as well as in total, because a family sheet is per sweep -- and
                # because it is the only form in which this can be checked against a split
                # the project has already measured by another route.
                for kind in sorted(entry['kinds']):
                    per = SITES.get(((kind, field),) + site)
                    if per and len(per) > 1:
                        print('            in %-14s %s' % (kind, _tally(per)))


    print('')
    print('  %d fields whose every max/min resolved the same way on every variant. More than '
          'one' % len(single))
    print('  requirement still stands behind each, so DES-9 reaches them, but one note per '
          'family')
    print('  covers it:')
    print('    %s' % ', '.join(single) if single else '    (none)')

    print('')
    print('  --- the geometry layer, which the sweep above cannot reach ---')
    # Per sweep, not merely in total: a family sheet is per sweep, and this is also the only
    # form in which the instrument can be checked against a split the project already
    # measured -- the corner's 240 against 24, recorded under IP-FC-99 before this existed.
    for kind in ('corner', 'bulkhead', 'boom_bulkhead'):
        result, why = geometry_layer((kind,))
        if result is None:
            print('  %-14s NOT MEASURED: %s' % (kind, why))
            continue
        total, rows = result
        for row in rows:
            if row[0] == 'BRANCH':
                pairs = [p.split(':') for p in row[3].split()]
                tally = '  '.join('arg %s wins %s' % (i, n) for i, n in pairs)
                print('  %-14s %3d variants   %-14s %-22s %s   %s'
                      % (kind, total, row[1], row[2], tally,
                         'BOTH BRANCHES WIN' if len(pairs) > 1 else 'one branch only'))
            else:
                print('  %-14s %3d variants   %-14s %-22s tied on %s (neither governed)'
                      % (kind, total, row[1], row[2], row[3]))
    print('  Dimensions computed during a *build* are not reached by this -- exercising those')
    print('  means building the parts -- so the geometry layer is covered only as far as')
    print('  corner_common.Params goes.')

    if '--factor' in argv:
        print('')
        print('  --- can the DES-9 note ride in the table the value is already in? ---')
        print('  The family table is factored by axis (OQ-DES-D1), not one row per variant, so')
        print('  a GOVERNED BY column only sits beside a value if the branch follows the same')
        print('  axes the value does. Decided by drawing_families.minimal_axes, which is what')
        print('  decides the table\'s shape.')
        report_rows = factor_report()
        for kind, field, value_axes, branch_axes, on_sheet, verdict in report_rows:
            print('    %-14s %-26s %-9s value %-22s branch %-22s %s'
                  % (kind, field, 'SHOWN' if on_sheet else 'not shown',
                     '(constant)' if value_axes == () else str(value_axes or '-'),
                     '(constant)' if branch_axes == () else str(branch_axes or '-'),
                     verdict))
        print('')
        print('  the note budget is the SHOWN rows only, per sheet:')
        for kind in ('corner', 'bulkhead', 'boom_bulkhead'):
            need = [(f, v) for k, f, v, _b, sh, _x in report_rows if k == kind and sh]
            print('    %-14s %d branching dimension(s) the sheet prints: %s'
                  % (kind, len(need), ', '.join(f for f, _v in need) or 'none'))
            # **A block per distinct axis set is what the factoring produces, so what matters
            # is how many branching dimensions land in the same block.** One per block means
            # the GOVERNED BY column is unambiguous without naming its dimension; two would
            # mean the cell has to say which, and that is what widens it.
            blocks = {}
            for field, value_axes in need:
                blocks.setdefault(value_axes, []).append(field)
            for value_axes, fields in sorted(blocks.items(), key=lambda kv: str(kv[0])):
                print('        block %-22s %d: %s%s'
                      % (str(value_axes), len(fields), ', '.join(fields),
                         '' if len(fields) < 2
                         else '   <-- shares a block, so the column must name the dimension'))

    conditionals = uninstrumented()
    print('')
    print('  %d relations branch on a conditional, which watching max and min cannot see:'
          % len(conditionals))
    for field, note in conditionals:
        print('    %-34s %s' % (field, note))

    if TIES:
        print('')
        print('  ties, where both branches gave the same value and neither governed:')
        for (field_key, func, line, name), n in sorted(TIES.items(), key=lambda kv: -kv[1])[:8]:
            print('    %-34s %s:%d %s  %d variants' % (field_key[1], func, line, name, n))

    sys.stdout.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
