"""IP-FC-41: seed parameter sheets from `derived_parameters()`, and check the ones that are
not seeded yet.

`derived_parameters()` is the authority on a variant's parameters, and it cannot be called
from FreeCAD's Python -- see `tools/export_parameters.py`, which resolves a variant in the
project virtualenv and writes the flat parameter set as JSON. This is the reading half.

    python tools/export_parameters.py 1.0 end_bolt 3/16in params.json
    freecadcmd parameters.py params.json          # check every module against it

`rows()` turns the JSON into spreadsheet rows for a generator to build on. `check_literals()`
does the other job: the ported modules each carry literal values, which was the right thing
while they were only compared against isolated references at matching inputs, and it becomes
wrong the moment a generator feeds the sweep. Rather than rewrite them all at once, this
compares each module's literals against the authority and reports the disagreements -- so a
module that has not been converted yet is still *verified* against the real parameter set
rather than merely assumed to agree with it.

`corner_tree.py` is expected to disagree: its aliases carry `fuselage_corner.scad`'s hand
driver values, which are one hand-written configuration and not design intent. That is the
disagreement IP-FC-41 exists to resolve, and the report names it rather than hiding it.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from corner_common import is_entry_point, script_args

# The tables the export can carry, by the key each occupies in the JSON.
#
# A frame bulkhead variant carries two of them. The corner and the bulkhead are separate
# variants in the sweep -- `derived_parameters()` branches on is_bulkhead -- and they differ
# on `greeble_tolerance` by design: the corner's bore carries the whole fit clearance and the
# bulkhead's post is nominal, because split across both halves the joint would take it twice.
#
# A boom bulkhead variant carries one, `boom_parameters`, and none of the others. It is a
# different sweep off a different type axis, and it has no corner: the corner is a frame part
# and does not vary with where the boom sits. Naming its table separately is what makes a
# mismatched parameter file fail rather than seed the wrong part -- see `part_kinds.KINDS`.
BULKHEAD, CORNER = 'parameters', 'corner_parameters'
BOOM_BULKHEAD = 'boom_parameters'

# Modules whose literals should already agree with the swept parameter set, as
# (module, table, the bulkhead type they are written at or None for any).
#
# A module is only checked when the parameter file actually carries its table, so this one
# list serves both families: a frame bulkhead variant exercises the first seven rows, a boom
# bulkhead variant the last six, and neither is reported as failing for the other's rows.
#
# **The type gate is the same one SWEPT_REFS needs, for the same reason.** A module's
# literals are one configuration. The frame bulkhead's five types do not move any number, so
# its modules agree with all of them; the boom bulkhead's three types move three numbers --
# `boom_z_position`, `boom_make_vert_web`, `boom_make_lower_web` -- so its modules can only
# be measured at the type they were written at, which is `offset_single`. Measured at
# `center_single` they report exactly those three, correctly, and no set of literals could
# make that report empty at both types. `boom_bulkhead.VARIANTS` is where the other type's
# values are stated and checked.
CHECKED = [('flange_base', BULKHEAD, None), ('simple_positives', BULKHEAD, None),
           ('web', BULKHEAD, None), ('greeble_web', BULKHEAD, None),
           ('fillets', BULKHEAD, None), ('flange_boss', BULKHEAD, None),
           ('bulkhead_cuts', BULKHEAD, None),
           ('boom_key', BOOM_BULKHEAD, 'offset_single'),
           ('boom_web', BOOM_BULKHEAD, 'offset_single'),
           ('boom_webs', BOOM_BULKHEAD, 'offset_single'),
           ('boom_oml', BOOM_BULKHEAD, 'offset_single'),
           ('bulkhead_web', BOOM_BULKHEAD, 'offset_single'),
           ('boom_bulkhead', BOOM_BULKHEAD, 'offset_single')]

# Modules known to carry a different configuration on purpose, reported but not failed.
EXPECTED_TO_DIFFER = {
    'corner_tree': (CORNER,
                    'hand driver values from fuselage_corner.scad, not the swept set'),
}


def load(path):
    with open(path) as f:
        doc = json.load(f)
    if not doc.get('valid'):
        raise RuntimeError('%s is a combination the sweep would not generate' % path)
    return doc


def table_of(doc, table, path='the parameter file'):
    """One table out of a loaded parameter document, or say which file has the wrong shape.

    A missing table is not a corrupt file, it is the wrong *kind* of file -- a boom bulkhead
    asked to build from a frame bulkhead's variant, or the reverse. Left as a bare KeyError
    it surfaces from `freecadcmd` as a traceback naming a dict key, which says nothing about
    which of the two the caller got wrong.

    Written to stderr and flushed before the exit, for the reason `build_part.build` states
    about `check_seed`: freecadcmd discards the message a `SystemExit` carries, so a refusal
    raised the obvious way produces no output at all -- just a part that never appears. The
    refusal is right either way; being able to read it is what makes it useful.
    """
    if table not in doc:
        sys.stderr.write(
            'parameters: %s carries %s, not %r.\nThis part is seeded from the %r table, so '
            'the parameter file has to be the one exported for its own variant -- the frame '
            'bulkhead and the boom bulkhead are separate sweeps off separate type axes.\n'
            % (path, ' and '.join(repr(k) for k in sorted(doc) if k.endswith('parameters'))
               or 'no parameter table', table, table))
        sys.stderr.flush()
        raise SystemExit(1)
    return doc[table]


def rows(path, table=BULKHEAD):
    """Spreadsheet rows for the variant's parameters, as (alias, value) pairs."""
    return [(k, repr(float(v)))
            for k, v in sorted(table_of(load(path), table, path).items())]


def seed(path, table=BULKHEAD):
    """The alias -> value mapping a generator seeds its sheet from.

    Pass to `corner_common.build_sheet`, which replaces the literal rows a module declares
    and leaves the '=' rows -- the port itself -- alone. Pass table=CORNER for the corner:
    seeding it from the bulkhead's table would give its bore no clearance at all.
    """
    return dict(table_of(load(path), table, path))


def applicable(entries, path):
    """The `(name, table, at_type)` entries this parameter file can actually speak to.

    Two filters, and both are the difference between a check and a claim. A table the file
    does not carry means the entry belongs to the other bulkhead family, and its literals are
    neither right nor wrong with respect to this variant. A stated type that is not this
    variant's type means the entry is written at a different point of the same family, where
    a disagreement is the other point's correct answer rather than an error.
    """
    doc = load(path)
    variant_type = doc.get('variant', {}).get('bulkhead_type_name')
    return [e for e in entries
            if e[1] in doc and (e[2] is None or e[2] == variant_type)]


def _literals(params):
    """The alias/value pairs of a module's PARAMS that are plain numbers, not expressions."""
    out = {}
    for alias, value in params:
        text = str(value).strip()
        if text.startswith('='):
            continue
        try:
            out[alias] = float(text)
        except ValueError:
            pass
    return out


def check_literals(modules, path):
    """Compare each module's literal parameters against the table it belongs to.

    Entries this parameter file cannot speak to are skipped rather than failed -- see
    `applicable` for the two ways that happens and why neither is a defect.
    """
    doc = load(path)
    report = []
    for name, table, _at_type in applicable(modules, path):
        truth = doc[table]
        mod = __import__(name)
        for alias, value in sorted(_literals(getattr(mod, 'PARAMS', [])).items()):
            if alias not in truth:
                continue
            want = float(truth[alias])
            if abs(value - want) > 1e-9:
                report.append((name, alias, value, want))
    return report


# Modules that state more than one configuration, as (module, table, the attribute holding
# them). The attribute is a list of `(type name, reference value, overriding rows)`, which is
# what `boom_bulkhead.VARIANTS` is.
#
# These exist because the boom bulkhead's three types move three numbers between them, so one
# set of module literals cannot describe them all. `CHECKED` measures the literals at the type
# they are written at; this measures the *other* types, which nothing else does -- those
# overriding rows are hand-typed, they are the only statement on the FreeCAD side of what a
# second boom type is, and an error in one produces a part built at a configuration no variant
# has.
VARIANT_MODULES = [('boom_bulkhead', BOOM_BULKHEAD, 'VARIANTS')]


def overlays_for(entries, path):
    """The names `check_variant_overlays` will actually measure, for the report."""
    doc = load(path)
    variant_type = doc.get('variant', {}).get('bulkhead_type_name')
    out = []
    for name, table, attr in entries:
        if table not in doc:
            continue
        for label, _ref, _overlay in getattr(__import__(name), attr, []):
            if label == variant_type:
                out.append('%s at %s' % (name, label))
    return out


def check_variant_overlays(entries, path):
    """Compare a module's overridden parameter set, at this variant's type, against the
    authority.

    The whole set after the override, not just the overriding rows. Checking only the rows
    the overlay names would confirm the values it states and say nothing about the ones it
    omits -- and a row that should have been overridden and was not is exactly the failure
    worth catching, because it leaves the part at the other type's value while everything
    stated is correct.
    """
    doc = load(path)
    variant_type = doc.get('variant', {}).get('bulkhead_type_name')
    report = []
    for name, table, attr in entries:
        if table not in doc:
            continue
        truth = doc[table]
        mod = __import__(name)
        for label, _ref, overlay in getattr(mod, attr, []):
            if label != variant_type:
                continue
            rows = [(a, overlay.get(a, v)) for a, v in mod.PARAMS]
            for alias, value in sorted(_literals(rows).items()):
                if alias not in truth:
                    continue
                want = float(truth[alias])
                if abs(value - want) > 1e-9:
                    report.append(('%s at %s' % (name, label), alias, value, want))
    return report


# The reference .scad files rendered at the swept parameter set rather than at the hand
# driver's, as (file, table, the bulkhead type it is rendered at or None for any).
# ref_greeble_tool.scad and the corner's references are deliberately excluded: they are
# rendered at fuselage_corner.scad's values, which is the point of them.
#
# **The type matters for the boom references and for nothing else.** Every frame bulkhead
# reference holds only dimensions, and those are the same across the five frame types --
# `end_bolt` and `interconnect` differ in which branch consumes the numbers, not in the
# numbers. The boom's two references are the first pair where the type moves a value:
# `boom_z_position` is 25.0 at `offset_single` and 0.0 at `center_single`. Checked against
# the wrong one, each would report a disagreement that is really the other variant's
# correct answer.
SWEPT_REFS = [('ref_flange_base.scad', BULKHEAD, None),
              ('ref_simple_positives.scad', BULKHEAD, None),
              ('ref_web.scad', BULKHEAD, None),
              ('ref_greeble_web.scad', BULKHEAD, None),
              ('ref_fillets.scad', BULKHEAD, None),
              ('ref_flange_boss.scad', BULKHEAD, None),
              ('ref_flange_positive.scad', BULKHEAD, None),
              ('ref_bulkhead_cuts.scad', BULKHEAD, None),
              ('ref_bulkhead_section.scad', BULKHEAD, None),
              ('ref_bulkhead_full.scad', BULKHEAD, None),
              ('ref_greeble_tool_swept.scad', BULKHEAD, None),
              ('ref_corner_full.scad', CORNER, None),
              ('ref_boom_key.scad', BOOM_BULKHEAD, 'offset_single'),
              ('ref_boom_bulkhead.scad', BOOM_BULKHEAD, 'offset_single'),
              ('ref_boom_bulkhead_center.scad', BOOM_BULKHEAD, 'center_single')]

_ASSIGN = re.compile(r'^\s*([A-Za-z_]\w*)\s*=\s*([-+]?[0-9.]+)\s*;', re.M)


def check_refs(refs, path):
    """Compare the top-level assignments in each reference .scad against the exported set.

    The references are hand-typed, and a mistyped value there is the worst kind of error to
    have: the port is then compared against the wrong shape, so it either fails for no
    reason or -- if the same typo reached both sides -- agrees while both are wrong. The
    numbers exist in machine-readable form now, so nothing has to be taken on trust.
    """
    doc = load(path)
    here = os.path.dirname(os.path.abspath(__file__))
    report = []
    for name, table, _at_type in applicable(refs, path):
        truth = doc[table]
        with open(os.path.join(here, name)) as f:
            source = f.read()
        for alias, text in _ASSIGN.findall(source):
            if alias not in truth:
                continue
            if abs(float(text) - float(truth[alias])) > 1e-9:
                report.append((name, alias, float(text), float(truth[alias])))
    return report


def main():
    args = script_args()
    if not args:
        print('usage: freecadcmd parameters.py params.json')
        print('generate params.json with tools/export_parameters.py')
        return 0
    path = args[0]

    doc = load(path)
    v = doc['variant']
    print('IP-FC-41 -- module literals against derived_parameters()')
    print('  variant = U=%s %s panel=%s' % (v['U'], v['bulkhead_type_name'],
                                            v['panel_name']))
    print('  source  = %s' % path)

    # What this file can speak to, rather than the whole list. A frame bulkhead variant has
    # nothing to say about the boom modules and the reverse, and printing the names of
    # modules that were skipped would claim coverage the run does not have.
    checked = applicable(CHECKED, path)
    refs = applicable(SWEPT_REFS, path)

    bad = check_literals(CHECKED, path) + check_variant_overlays(VARIANT_MODULES, path)
    names = [n for n, _t, _a in checked] + overlays_for(VARIANT_MODULES, path)
    print('\n  checked: %s' % (', '.join(names) or 'nothing -- no module carries literals '
                               'for this variant'))
    if bad:
        print('  %-32s %-24s %14s %14s' % ('module', 'alias', 'literal', 'derived'))
        for name, alias, got, want in bad:
            print('  %-32s %-24s %14s %14s' % (name, alias, got, want))
    else:
        print('  every literal agrees with the derived parameter set')

    bad_refs = check_refs(SWEPT_REFS, path)
    print('\n  reference .scad files rendered at the swept set: %d of %d'
          % (len(refs), len(SWEPT_REFS)))
    if bad_refs:
        print('  %-28s %-24s %14s %14s' % ('reference', 'name', 'in file', 'derived'))
        for name, alias, got, want in bad_refs:
            print('  %-28s %-24s %14s %14s' % (name, alias, got, want))
    else:
        print('  every assignment agrees with the derived parameter set')

    print('\n  known to differ on purpose:')
    for name, (table, why) in sorted(EXPECTED_TO_DIFFER.items()):
        if table not in doc:
            # Said rather than skipped silently: zero disagreements against a table this
            # file does not carry is not agreement, and printing it as one would be a
            # clean line for a check that never ran.
            print('    %-16s not measured -- this variant carries no %r table'
                  % (name, table))
            continue
        diffs = check_literals([(name, table, None)], path)
        print('    %-16s %d disagreement(s) -- %s' % (name, len(diffs), why))
        for _, alias, got, want in diffs:
            print('      %-24s driver %-10s derived %s' % (alias, got, want))

    fail = []
    if bad:
        fail.append('a checked module disagrees with the authority')
    if bad_refs:
        fail.append('a reference .scad disagrees with the authority')
    print('\n  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
