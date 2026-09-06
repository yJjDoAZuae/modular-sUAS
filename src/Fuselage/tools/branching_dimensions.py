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

#: Ties, kept apart from wins. Two branches agreeing on a value is not one of them governing --
#: it is the case where the note has nothing to choose between, and counting it as a win for
#: the first argument would overstate how often that branch decides anything.
TIES = {}


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
        else:
            counts = SITES.setdefault(key, {})
            counts[winners[0]] = counts.get(winners[0], 0) + 1
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
            for row, U, FX, _flat in rows:
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
        elif line.startswith('BRANCH\t') or line.startswith('TIE\t'):
            rows.append(line.split('\t'))
    if total is None:
        return None, ('geometry_branches.py produced no result%s%s'
                      % (chr(10), done.stderr.decode('utf-8', 'replace')[-1500:]))
    return (total, rows), None


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

    print('  %d fields where both branches actually win somewhere in the sweep -- these are '
          'the ones' % len(split))
    print('  DES-9 is about, and the ones whose note text has to vary:')
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
