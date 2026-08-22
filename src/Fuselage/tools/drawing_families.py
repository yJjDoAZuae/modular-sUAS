"""IP-FC-21: the topology partition, and the factored value table OQ-DES-D1 decided on.

`dimension_scheme.md` section 5.1 says two variants share a drawing when they have the same
*features*, and differ only in size. That rule produces the family sheets. OQ-DES-D1 then
decided what carries the size variation on one of those sheets: not one row per variant --
the corner would need hundreds -- but **one short table per size axis**, with each callout
labelled by the axis its dimension follows, and a small two-dimensional table for each field
that genuinely depends on two axes at once.

This module is both halves of that: it partitions the sweep into families, and it factors
each family's values into per-axis tables. It writes the result as JSON, which
`freecad/drawing.py` reads back -- the same boundary hop `export_parameters.py` makes, and
for the same reason: `derived_parameters()` needs `solid2` and lives in the project
virtualenv, and drawings are built under `freecadcmd`, whose Python cannot import it.

    python drawing_families.py                    # the report
    python drawing_families.py families.json      # ... and the data

**The axis label is derived, not authored, and that is the point.** OQ-DES-D1's one real
drawback was that a callout labelled with the wrong axis sends the reader to the wrong table
and yields a *plausible wrong number* -- a worse failure than a missing row. So no label is
written by hand. For each field this asks which axes it is actually a function of, over the
whole family, and takes the smallest such set. A field cannot be labelled with an axis its
value does not follow, because nothing here is capable of saying so.

**"Is a function of" is asked at the precision the sheet prints.** Two variants that differ
by 1e-13 do not differ on a drawing that writes two decimals, and calling that a dependence
would split a one-column table into a matrix to carry a difference no reader can see. The
precision is `drawing_standard.DECIMAL_PLACES`, so the table's shape and the annotation's
text are decided by one number. The exact comparison is run as well, and where the two
disagree the report says so -- a field that varies only below the printed precision is worth
knowing about even though it changes no cell.

**Scope: a field is tabulated only if it reaches the part's geometry as a named argument.**
That is section 1's membership test, applied by reading the parameter mapping each backend is
driven from (`fuselage_variants.corner_parameters` and its siblings) rather than the resolved
parameter object, most of whose 51 fields never reach the part in question -- a corner sheet
has no business tabulating a boom key's angle.

The nose and the tail are the exception and are marked as such: they are JSON-driven and have
no flat name mapping, so their fields are read from the resolved object. They are also not
ported to FreeCAD yet -- `part_kinds.KINDS` has three kinds, not five -- so their tables are
computed here and have nothing to draw on.

**What it found, since three of the numbers OQ-DES-D1 was decided on were estimates.**
**13 family sheets, not 18** -- the partition is taken from the features a resolved part has,
and two type axes turn out not to be topology: `end_bolt` and `end_anchor` differ in exactly
one number, and `offset_single` and `dual` in where the single boom sits. **Five coupled
fields, not two**, which is the same finding: demoting a type axis to a table column is what
makes three more fields follow two axes. **19 rows to a sheet, not about 25**, because the
sheet is now measured rather than guessed. Every family fits, and five fit exactly, with
nothing spare.

**What this does not decide, and what is blocked on it.** `drawing.py` does not exist yet and
cannot until [OQ-DES-D2] is answered: section 3 obliges a sheet to carry every dimension a
joint expression consumes, and 6 of 22 interface parameters exist as a distance anywhere on
their own part -- the rest are off by exactly a clearance, because the mating face already
contains it. Nothing in this module depends on that answer. It reports which dimensions are in
the interface set; it does not say where on the part they are measured.

**Unit regime: millimeters and degrees**, as the OpenSCAD path uses them.
"""
import dataclasses
import itertools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'freecad'))

import fuselage_variants as fv
import drawing_standard as ds

from render_variant import settings


# ----------------------------------------------------------------------------------------
# What makes two variants the same part
# ----------------------------------------------------------------------------------------

# The fields that decide *which features a part has*, as paths into the resolved parameter
# object. Two variants share a family when all of these agree; everything else is size.
#
# **`panel.is_metric` is deliberately not here, and it is the reason this list is declared
# rather than taken as "every boolean".** It is a boolean, and the mechanical rule would put
# it in -- doubling every panelled family for no difference in the part. It reaches only
# `generate_*_filename_from_params`; it never reaches geometry. `check_topology_fields`
# asserts that separation rather than trusting this comment.
#
# `bulkhead.type` is the encoded END/INTERCONNECT/COWLING/BOOM enum, so the five frame types
# and the three boom types are distinguished by what they *are* rather than by their names.
# Names are recorded alongside, because a reader looks up a family by name.
#
# **`bolt.is_anchor` is not here either, and the reason is a finding rather than a choice.**
# The field exists on `BoltParameters` and **nothing ever assigns it** -- `derived_parameters`
# reads `is_anchor` out of the variant row into a local, uses it on one line, and leaves the
# object's own field at its `False` default. So it could not distinguish a family even if it
# should. It also should not: the anchor and the bolt reach the *same* OpenSCAD module with
# the same arguments, differing in exactly one number, `bolt_hole_radius` -- 1.95 mm against
# 1.50 mm at U = 0.5. Under section 5.1's rule that is one part in two sizes, not two parts,
# so the fastener is a table axis below and not a sheet.
TOPOLOGY_FIELDS = ('bulkhead.type',
                   'boom_bulkhead.make_vert_web', 'boom_bulkhead.make_lower_web')

# A feature whose presence is carried by a dimension being zero rather than by a flag.
# `panel.thickness == 0` is the no-panel variant: `bulkhead_section` puts the whole corner
# cut-out behind a branch, and a callout pointing at a rebate a part does not have is exactly
# the failure section 5.1 exists to prevent.
PRESENCE_FIELDS = ('panel.thickness',)


# ----------------------------------------------------------------------------------------
# The sweeps
# ----------------------------------------------------------------------------------------

# One entry per sweep in `_run_all_sweeps`, giving the axes it varies and how a variant is
# resolved. The axis names are the keys a table is written on; the CSV column each reads is
# named because the axis value has to be recoverable from the combination row.
#
#   axes        (label, the CSV column carrying it), in the order a table sorts on
#   mapping     the flat parameter mapping, or None for a JSON-driven part
#   ported      whether `part_kinds.KINDS` can build it, and so whether a sheet can be drawn
#
# **The type axis is listed as an axis, not assumed to be a sheet.** Whether a type gets its
# own drawing is decided by `topology_of`, from the features the resolved part has -- so a
# type axis that changes a feature splits the family, and a type axis that only moves a
# number becomes a column like `U` does. Deciding it here instead would be authoring the
# partition rather than deriving it, and the two type axes in this sweep disagree: the frame
# bulkhead's five names cover three feature sets, and the boom bulkhead's three cover two.
SWEEPS = {
    'corner': {
        'axis_csvs': ('panel_variants.csv', 'bulkhead_size_variants.csv',
                      'corner_size_variants.csv'),
        'axes': (('U', 'U'), ('FX', 'FX'), ('panel', 'panel_name')),
        'mapping': 'corner_parameters',
        'is_bulkhead': False,
        'validity': 'corner_validity_check',
        'ported': True,
    },
    'bulkhead': {
        'axis_csvs': ('panel_variants.csv', 'bulkhead_type_variants.csv',
                      'bulkhead_size_variants.csv'),
        'axes': (('U', 'U'), ('panel', 'panel_name'), ('type', 'bulkhead_type_name')),
        'mapping': 'bulkhead_parameters',
        'is_bulkhead': True,
        'validity': 'bulkhead_validity_check',
        'ported': True,
    },
    'boom_bulkhead': {
        'axis_csvs': ('panel_variants.csv', 'bulkhead_size_variants.csv',
                      'boom_bulkhead_type_variants.csv'),
        'axes': (('U', 'U'), ('panel', 'panel_name'), ('type', 'bulkhead_type_name')),
        'mapping': 'boom_bulkhead_parameters',
        'is_bulkhead': True,
        'validity': None,                      # the family table declares two checks
        'family': 'boom_bulkhead',
        'ported': True,
    },
    'nose': {
        'axis_csvs': ('nose_size_variants.csv', 'nose_type_variants.csv'),
        'axes': (('U', 'U'),),
        'mapping': None,
        'cowl': True,
        'ported': False,
    },
    'tail': {
        'axis_csvs': ('nose_size_variants.csv', 'tail_type_variants.csv'),
        'axes': (('U', 'U'),),
        'mapping': None,
        'cowl': True,
        'ported': False,
    },
}


# ----------------------------------------------------------------------------------------
# Which dimensions the sheet has to carry
# ----------------------------------------------------------------------------------------

# Section 3's completeness test: *the set is complete when, for every entry in
# `design_constants.json`'s `tolerances` group, the drawing carries every dimension that
# entry's expression consumes.* Each entry's expression is written into its `why`, so the
# consumed names are recovered by looking for known parameter names in that text -- matching
# against a fixed vocabulary rather than parsing prose, so the worst a badly worded entry can
# do is name too few dimensions, which the report shows.
#
# **This is the required floor, not the whole drawing.** A field outside the interface set
# still has a value and still gets factored; it is simply not what the completeness test
# obliges the sheet to carry. Keeping the two apart is what lets the sheet-fit question be
# asked about the dimensions a drawing *must* have rather than about every argument the
# module happens to take.
def vocabulary(dp):
    """Every parameter name a part can be driven by, across all three mappings."""
    names = set()
    for mapping in ('corner_parameters', 'bulkhead_parameters', 'boom_bulkhead_parameters'):
        names |= set(getattr(fv, mapping)(dp))
    return names


DIMENSION_SCHEME = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
    'doc', 'design', 'dimension_scheme.md')

# Which part's drawing carries each register row, mapped onto the sweeps. The register says
# "bulkhead" for both bulkhead families because it is describing a joint, not a sweep; which
# of the two actually carries it falls out of the mapping intersection, since a boom collet's
# names exist only in the boom mapping.
CARRIED_BY = {
    'corner': ('corner',),
    'bulkhead': ('bulkhead', 'boom_bulkhead'),
    'nose closure': ('nose', 'tail'),
}


def _identifiers(cell, aliases):
    """Parameter names out of one register cell, from its code spans only.

    Only what is written between backticks. The register's cells are prose with the
    expressions marked up in it, and reading the prose as well would pull in every English
    word -- harmless once intersected with a parameter mapping, and misleading in a report
    that is supposed to say what a joint consumes.
    """
    names = set()
    for span in re.findall('`([^`]*)`', cell):
        for word in re.findall('[A-Za-z_][A-Za-z_0-9]*', span):
            names.add(aliases.get(word, word))
    return names


def read_register(path=None):
    """Section 2's interface register, as rows of (number, consumed names, clearance, part).

    **Why the register and not only the constants file.** Section 3 says the completeness test
    rides on `design_constants.json`, on the argument that each tolerance entry's `why`
    carries the governing expression. Measured against the file on 2026-08-22, most of them do
    not: `panel_tolerance`'s `why` yields `corner_radius` and itself, where the register's row
    for the same joint consumes `panel_thickness`, `panel_overlap`, `panel_offset` and
    `corner_radius` as well. Read from the constants file alone the test would pass on a
    drawing missing most of the panel joint.

    So the two are read together and cross-checked: the constants file is the authority on
    *which joints exist*, because `load_constants` validates its membership on every sweep
    run, and the register is the authority on *what each joint consumes*. A tolerance in the
    group with no row here fails, which is what keeps the document from going stale silently.
    """
    with open(path or DIMENSION_SCHEME, encoding='utf-8') as f:
        text = f.read()

    body = text[text.index('## 2. The interface register'):text.index('## 3.')]

    # `w` and `n_p` are the register's own shorthands, defined in its preamble sentence
    # rather than assumed here, so renaming one in the document does not silently drop the
    # dimensions it stands for.
    aliases = dict(re.findall('`([A-Za-z_][A-Za-z_0-9]*)` is `([A-Za-z_][A-Za-z_0-9]*)`',
                              body))

    rows = []
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) != 5 or not cells[0].isdigit():
            continue
        number, _joint, expression, clearance, part = cells
        rows.append((int(number), _identifiers(expression + ' ' + clearance, aliases),
                     _identifiers(clearance, aliases), part))
    if not rows:
        raise RuntimeError('no register rows parsed out of %s -- the table in section 2 is '
                           'not in the five-column form this reads'
                           % (path or DIMENSION_SCHEME))
    return rows


def interface_fields(kind, mapping_keys, register=None):
    """The dimensions section 3 obliges `kind`'s drawing to carry.

    Restricted to names the part is actually driven by, so a register row carried by "the
    bulkhead" contributes the boom collet's names to a boom bulkhead and nothing to a frame
    one.
    """
    wanted = set()
    for _number, names, _clearance, part in (register or read_register()):
        if kind in CARRIED_BY.get(part, ()):
            wanted |= names
    return sorted(wanted & set(mapping_keys))


def check_register(register=None):
    """Cross-check the register against the group `load_constants` validates.

    `load_constants` is called for its refusals rather than its return: it is what makes the
    tolerance group's membership trustworthy, refusing a missing name and an unrecognized
    one. What it hands back is a flat name -> value dict, with the `why` discarded.
    """
    fv.load_constants()
    register = register or read_register()
    covered = set()
    for _number, _names, clearance, _part in register:
        covered |= clearance

    problems = []
    for name in sorted(fv.CONSTANT_GROUPS['tolerances']):
        if name not in covered:
            problems.append(
                '%s is a clearance in design_constants.json with no row in the interface '
                'register, so no drawing is obliged to carry its joint' % name)
    for part in sorted({p for _n, _names, _c, p in register}):
        if part not in CARRIED_BY:
            problems.append(
                'the register says a joint is carried by %r, which is not a part this '
                'partitions -- CARRIED_BY has %s'
                % (part, ', '.join(sorted(CARRIED_BY))))
    return problems


def flatten(obj, prefix=''):
    """The resolved parameter object as flat dotted names."""
    out = {}
    if dataclasses.is_dataclass(obj):
        for field in dataclasses.fields(obj):
            out.update(flatten(getattr(obj, field.name), prefix + field.name + '.'))
    else:
        out[prefix[:-1]] = obj
    return out


def check_topology_fields():
    """Assert TOPOLOGY_FIELDS is what it claims to be, and complain about what it is not.

    Two claims, both checkable. Every declared topology field must be a field of the resolved
    object -- a typo would silently stop distinguishing a family. And every *other* boolean
    must be absent from all three parameter mappings, which is what "does not reach geometry"
    means here: a boolean that a module takes as an argument is a branch, and a branch is a
    feature, and a feature belongs in the partition.
    """
    printer, FX = settings()
    row = fv.family_combinations('bulkhead')[0]
    dp = fv.derived_parameters(row['U'], FX, dict(row, FX=FX), printer, True)
    flat = flatten(dp)

    problems = []
    for name in TOPOLOGY_FIELDS + PRESENCE_FIELDS:
        if name not in flat:
            problems.append('%s is declared as topology but is not a parameter' % name)

    reaches = set()
    for mapping in ('corner_parameters', 'bulkhead_parameters', 'boom_bulkhead_parameters'):
        reaches |= set(getattr(fv, mapping)(dp))

    for name, value in sorted(flat.items()):
        if not isinstance(value, bool) or name in TOPOLOGY_FIELDS:
            continue
        leaf = name.split('.')[-1]
        if leaf in reaches or name.replace('.', '_') in reaches:
            problems.append(
                '%s is a boolean that reaches geometry as an argument, so it selects a '
                'feature and belongs in TOPOLOGY_FIELDS' % name)
    return problems


def topology_of(flat):
    """A variant's family signature: its features, and nothing about its size.

    A field the part does not have at all reads as `absent` rather than as a missing key. The
    nose and the tail are resolved through `derived_cowl_parameters` into a different object
    and have none of these fields; that is a true statement about a cowl, and it is a
    different statement from having the field and it being false.
    """
    key = []
    for name in TOPOLOGY_FIELDS:
        if name not in flat:
            key.append((name, 'absent'))
            continue
        value = flat[name]
        key.append((name, value.name if hasattr(value, 'name') else bool(value)))
    for name in PRESENCE_FIELDS:
        key.append((name + ' != 0',
                    'absent' if name not in flat else float(flat[name]) != 0.0))
    return tuple(key)


def resolve(kind):
    """Every variant of one sweep that the sweep would actually generate.

    Returns (axis_values, flat_parameters, mapped_parameters, type_name) per variant, with
    the invalid combinations dropped -- a family whose row count included combinations the
    sweep refuses would describe a drawing set that cannot be built.
    """
    spec = SWEEPS[kind]
    printer, default_fx = settings()
    combinations = fv.flatten_param_space(
        fv.read_all_param_axes(fv.axes(*spec['axis_csvs'])))

    out = []
    for row in combinations:
        U = float(row['U'])
        FX = float(row.get('FX', default_fx))

        if spec.get('cowl'):
            dp = fv.derived_cowl_parameters(U, FX, row, printer)
            valid = True
        else:
            params = dict(row, FX=FX)
            dp = fv.derived_parameters(U, FX, params, printer, spec['is_bulkhead'])
            if 'family' in spec:
                valid = fv.family_is_valid(spec['family'], dp)
            else:
                valid = getattr(fv, spec['validity'])(dp)
        if not valid:
            continue

        flat = flatten(dp)
        if spec['mapping']:
            mapped = {k: v for k, v in getattr(fv, spec['mapping'])(dp).items()}
        else:
            mapped = {k: v for k, v in flat.items()
                      if isinstance(v, (int, float)) and not isinstance(v, bool)}

        axis_values = {}
        for label, column in spec['axes']:
            value = row[column]
            axis_values[label] = float(value) if label in ('U', 'FX') else str(value)
        out.append((axis_values, flat, mapped, row.get('bulkhead_type_name', kind)))
    return out


# ----------------------------------------------------------------------------------------
# Factoring
# ----------------------------------------------------------------------------------------

def written(value):
    """A value as the sheet writes it, or None for something a dimension cannot be."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return ds.format_length(float(value))


def minimal_axes(members, field, axes, exact=False):
    """The smallest set of axes `field` is a function of, or None if it is not a function.

    Tried smallest-first, so a field that follows one axis is labelled with one axis. The
    empty set means the field is the same on every variant of the family, which is not a
    table row at all -- it is a value printed on the view.

    `exact` compares the resolved float rather than the written string. The written form is
    what decides a table's shape; the exact form is run alongside to report fields that vary
    only below the printed precision.
    """
    for size in range(len(axes) + 1):
        for subset in itertools.combinations(axes, size):
            seen = {}
            consistent = True
            for axis_values, values in members:
                key = tuple(axis_values[a] for a in subset)
                value = values[field] if exact else written(values[field])
                if key in seen and seen[key] != value:
                    consistent = False
                    break
                seen[key] = value
            if consistent:
                return subset
    return None


def factor(members, axes, interface):
    """One family's fields, grouped into the tables they belong in.

    Returns a dict with four parts:

      `constants`         fields that do not vary across the family. Not a table row at all
                          -- a value printed on the view.
      `structural_zeros`  fields that are zero across the whole family. Section 2 is explicit
                          that these are **the absence of the joint** rather than a setting at
                          its minimum, and that a drawing must omit the dimension rather than
                          print `0.0`, because a dimensioned zero asserts a coincident fit
                          somebody designed and an inspector can check. They are separated
                          here rather than dropped, so the report can name what was left off.
      `tables`            one per distinct axis set, with the axis values as key columns.
      `precision_only`    fields whose exact values follow more axes than their written ones.

    `interface` is the set section 3 obliges the sheet to carry; every field is marked with
    whether it is in it, so the required floor and the rest stay distinguishable downstream.
    """
    fields = sorted(set(members[0][1]))
    result = {'constants': {}, 'structural_zeros': {}, 'tables': [],
              'precision_only': [], 'interface': sorted(interface)}
    groups = {}

    for field in fields:
        first = written(members[0][1][field])
        if first is None:
            continue                        # a name or a flag, not a dimension
        subset = minimal_axes(members, field, axes)
        if subset is None:
            raise RuntimeError(
                '%s is not a function of the size axes %s -- either the family is not one '
                'family, or an axis is missing from SWEEPS' % (field, ', '.join(axes)))
        exact = minimal_axes(members, field, axes, exact=True)
        if exact is not None and len(exact) > len(subset):
            result['precision_only'].append((field, subset, exact))

        if not subset:
            target = 'structural_zeros' if float(first) == 0.0 else 'constants'
            result[target][field] = first
        else:
            groups.setdefault(subset, []).append(field)

    for subset in sorted(groups, key=lambda s: (len(s), s)):
        columns = sorted(groups[subset])
        rows = {}
        for axis_values, values in members:
            key = tuple(axis_values[a] for a in subset)
            rows[key] = [written(values[c]) for c in columns]
        ordered = [list(k) + v for k, v in sorted(rows.items(), key=_sort_key)]
        result['tables'].append({
            'axes': list(subset),
            'columns': columns,
            'interface': [c for c in columns if c in interface],
            'rows': ordered,
            'shape': [len({r[i] for r in ordered}) for i in range(len(subset))],
            'sheet_rows': sheet_rows(subset, ordered),
        })
    return result


def sheet_rows(axes, rows):
    """How many printed rows a table costs, which is not how many entries it has.

    A one-axis table is a list and costs one row per value. A two-axis table is a **matrix** --
    that is the whole of OQ-DES-D1's alternative 2 -- so it costs one row per value of its
    first axis and spends the second across the page as columns. Counting cells instead would
    say the corner needs 48 rows for `unit_length` where a reader sees eight.
    """
    return len({row[0] for row in rows})


def _sort_key(item):
    """Sort a table's rows by its axis values, numbers before names."""
    return tuple((0, v, '') if isinstance(v, float) else (1, 0.0, str(v)) for v in item[0])


def sheet_blocks(tables):
    """The tables grouped into what the sheet actually prints, and what each block costs.

    **Tables that share a leading axis are one block, not several.** A one-axis `U` table and
    a `U` x `panel` matrix both put the same eight values of `U` down the left, so printing
    them separately prints that column twice and costs eight rows for nothing. Merged, the
    single-axis fields are ordinary columns and each coupled field is a band of columns across
    the page -- which is what OQ-DES-D1's alternative 2 describes, read carefully: one table
    per axis, with a matrix *inside* it, rather than a matrix beside it.

    A block costs one heading row, plus a second when it carries a coupled field, because a
    band of columns needs the field named above the values of the axis it spans. A block with
    no coupled field needs only the one row, since the key column's own heading names the axis
    it is read on.

    Returns a list of (leading axis, tables, printed rows).
    """
    blocks = {}
    for table in tables:
        blocks.setdefault(table['axes'][0], []).append(table)

    out = []
    for axis in sorted(blocks, key=lambda a: (len(blocks[a]) == 1, a)):
        group = blocks[axis]
        keys = [{row[0] for row in t['rows']} for t in group]
        if any(k != keys[0] for k in keys):
            raise RuntimeError(
                'the tables led by %r do not share their key column, so they cannot be '
                'printed as one block' % axis)
        headings = 2 if any(len(t['axes']) > 1 for t in group) else 1
        out.append((axis, group, len(keys[0]) + headings))
    return out


def families():
    """Every family sheet the drawing set needs, with its factored tables."""
    register = read_register()
    out = []
    for kind, spec in SWEEPS.items():
        axes = [label for label, _ in spec['axes']]
        buckets = {}
        for axis_values, flat, mapped, type_name in resolve(kind):
            buckets.setdefault(topology_of(flat), []).append(
                (axis_values, mapped, type_name))

        for signature, rows in sorted(buckets.items(), key=lambda kv: str(kv[0])):
            members = [(a, m) for a, m, _ in rows]
            names = sorted({t for _, _, t in rows})
            interface = set(interface_fields(kind, members[0][1], register))
            factored = factor(members, axes, interface)

            tables = factored['tables']
            required = [t for t in tables if t['interface']]
            out.append({
                'kind': kind,
                'ported': spec['ported'],
                'topology': [list(pair) for pair in signature],
                'type_names': names,
                'axes': axes,
                'variants': len(members),
                'constants': factored['constants'],
                'structural_zeros': factored['structural_zeros'],
                'interface': factored['interface'],
                'tables': tables,
                'precision_only': [[f, list(w), list(e)]
                                   for f, w, e in factored['precision_only']],
                'cells': sum(len(t['rows']) for t in tables),
                'blocks': [[axis, [t['axes'] for t in group], rows]
                           for axis, group, rows in sheet_blocks(tables)],
                'sheet_rows': sum(r for _a, _g, r in sheet_blocks(tables)),
                'interface_sheet_rows': sum(r for _a, _g, r in sheet_blocks(required)),
            })
    return out


# ----------------------------------------------------------------------------------------
# The report
# ----------------------------------------------------------------------------------------

# How many printed rows the sheet actually holds, derived rather than estimated -- the frame
# and the title block are read off the pinned template and the row pitch is the drawing
# standard's own. **19, not the "about 25" OQ-DES-D1 was filed with**, which was a guess at a
# sheet nobody had measured. The question that decided the whole table's shape was asked
# against a budget a quarter too generous, so it is worth having the number come from
# somewhere.
ROWS_PER_SHEET = ds.table_rows_available()

# How much spare column a family should have before it is called comfortable. One row
# for a title over the table and one for a note under it is the least a real sheet
# spends, so a family with less than that fits only in the arithmetic.
MARGIN_ROWS = 2


def report(data):
    lines = []
    say = lines.append
    nl = chr(10)

    say('%d families, %d variants' % (len(data), sum(f['variants'] for f in data)))
    say('')
    say('%-14s %-26s %6s %5s %5s %6s %6s %6s  %s'
        % ('kind', 'types', 'vars', 'const', 'zero', 'tables', 'floor', 'rows',
           'axis sets'))
    for f in data:
        sets = ' '.join('[%s: %s]' % (axis, ' '.join('+'.join(a) for a in group))
                        for axis, group, _rows in [(b[0], b[1], b[2]) for b in f['blocks']])
        say('%-14s %-26s %6d %5d %5d %6d %6d %6d  %s'
            % (f['kind'], ','.join(f['type_names'])[:26], f['variants'],
               len(f['constants']), len(f['structural_zeros']), len(f['tables']),
               f['interface_sheet_rows'], f['sheet_rows'], sets))
    say('')
    say('  floor  printed rows for the interface dimensions section 3 obliges the sheet')
    say('         to carry; rows  the same for every dimension the part is driven by.')
    say('         Tables sharing a leading axis print as one block with the key column')
    say('         written once, and a coupled field is a band of columns inside it.')
    say('  The sheet holds %d rows: %.1f mm of column between the frame and the title'
        % (ROWS_PER_SHEET, ds.table_column_height_mm()))
    say('  block on the pinned template, at a %.1f mm row pitch.'
        % (ds.TABLE_ROW_PITCH_HEIGHTS * ds.TEXT_HEIGHT_MM))

    for label, key in (('every dimension', 'sheet_rows'),
                       ('the interface dimensions alone', 'interface_sheet_rows')):
        over = [f for f in data if f[key] > ROWS_PER_SHEET]
        say('')
        say('carrying %s, %d of %d families exceed %d rows'
            % (label, len(over), len(data), ROWS_PER_SHEET))
        for f in over:
            say('  %-14s %-26s %d rows'
                % (f['kind'], ','.join(f['type_names']), f[key]))

    # A family that exactly fills the column has answered OQ-DES-D1's question and left
    # nothing over, which is a different situation from fitting and is worth saying plainly:
    # one more dimension, one more panel stock or a title row above the table puts it on a
    # second sheet.
    tight = [f for f in data if ROWS_PER_SHEET - f['sheet_rows'] < MARGIN_ROWS]
    say('')
    say('families with fewer than %d spare rows: %d of %d'
        % (MARGIN_ROWS, len(tight), len(data)))
    for f in tight:
        say('  %-14s %-26s %d of %d rows, %d spare'
            % (f['kind'], ','.join(f['type_names']), f['sheet_rows'], ROWS_PER_SHEET,
               ROWS_PER_SHEET - f['sheet_rows']))

    coupled = sorted({(c, tuple(t['axes'])) for f in data for t in f['tables']
                      if len(t['axes']) > 1 for c in t['columns']})
    say('')
    say('fields needing more than one axis: %d' % len(coupled))
    for name, axes in coupled:
        say('  %-22s %s' % (name, '+'.join(axes)))

    zeros = sorted({(name, f['kind']) for f in data
                    for name in f['structural_zeros'] if name in f['interface']})
    say('')
    say('interface dimensions omitted as structural zeros: %d' % len(zeros))
    for name, kind in zeros:
        say('  %-22s %s' % (name, kind))

    residue = sorted({(f['kind'], p[0], tuple(p[1]), tuple(p[2]))
                      for f in data for p in f['precision_only']})
    say('')
    say('fields that vary only below the printed precision: %d' % len(residue))
    for kind, name, wrote, exact in residue:
        say('  %-14s %-22s written %-10s exact %s'
            % (kind, name, '+'.join(wrote) or 'constant', '+'.join(exact) or 'constant'))

    unresolved = unresolved_register_names()
    say('')
    say('register names that reach no parameter mapping: %d' % len(unresolved))
    for name in unresolved:
        say('  %s' % name)
    return nl.join(lines)


def unresolved_register_names(register=None):
    """Names the register's expressions consume that no part is driven by.

    Not a failure. Some are OpenSCAD-side locals that never appear as a module argument --
    `flat_x`, `collet_radius` -- and naming them is what makes the register readable. But the
    list also holds the ones that matter: `bolt_radius` is the register's name for what every
    mapping calls `bolt_hole_radius`, so joint 10's bore is silently dropped from the
    completeness test by a name that does not match. A test that cannot say which names it
    failed to resolve cannot be trusted to have resolved the rest.
    """
    printer, FX = settings()
    row = fv.family_combinations('bulkhead')[0]
    dp = fv.derived_parameters(row['U'], FX, dict(row, FX=FX), printer, True)
    known = vocabulary(dp)

    out = set()
    for _number, names, _clearance, _part in (register or read_register()):
        out |= names - known
    return sorted(out)


def main(argv):
    nl = chr(10)

    problems = check_topology_fields()
    if problems:
        raise SystemExit('the topology partition does not hold:' + nl
                         + nl.join('  - ' + p for p in problems))

    problems = check_register()
    if problems:
        raise SystemExit('the interface register and the constants file disagree:' + nl
                         + nl.join('  - ' + p for p in problems))

    data = families()
    print(report(data))

    out = [a for a in argv[1:] if a.endswith('.json')]
    if out:
        document = {'decimals': ds.DECIMAL_PLACES,
                    'rows_per_sheet': ROWS_PER_SHEET,
                    'register': [[n, sorted(names), sorted(c), p]
                                 for n, names, c, p in read_register()],
                    'families': data}
        with open(out[0], 'w', encoding='utf-8', newline='\n') as f:
            json.dump(document, f, indent=1, sort_keys=True)
            f.write('\n')
        print('\nwrote %s' % out[0])
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
