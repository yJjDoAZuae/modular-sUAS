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

# The export carries two tables. The corner and the bulkhead are separate variants in the
# sweep -- `derived_parameters()` branches on is_bulkhead -- and they differ on
# `greeble_tolerance` by design: the corner's bore carries the whole fit clearance and the
# bulkhead's post is nominal, because split across both halves the joint would take it twice.
BULKHEAD, CORNER = 'parameters', 'corner_parameters'

# Modules whose literals should already agree with the swept parameter set, and which table
# each is measured against.
CHECKED = [('flange_base', BULKHEAD), ('simple_positives', BULKHEAD), ('web', BULKHEAD),
           ('greeble_web', BULKHEAD), ('fillets', BULKHEAD), ('flange_boss', BULKHEAD),
           ('bulkhead_cuts', BULKHEAD)]

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


def rows(path, table=BULKHEAD):
    """Spreadsheet rows for the variant's parameters, as (alias, value) pairs."""
    return [(k, repr(float(v))) for k, v in sorted(load(path)[table].items())]


def seed(path, table=BULKHEAD):
    """The alias -> value mapping a generator seeds its sheet from.

    Pass to `corner_common.build_sheet`, which replaces the literal rows a module declares
    and leaves the '=' rows -- the port itself -- alone. Pass table=CORNER for the corner:
    seeding it from the bulkhead's table would give its bore no clearance at all.
    """
    return dict(load(path)[table])


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
    """Compare each module's literal parameters against the table it belongs to."""
    doc = load(path)
    report = []
    for name, table in modules:
        truth = doc[table]
        mod = __import__(name)
        for alias, value in sorted(_literals(getattr(mod, 'PARAMS', [])).items()):
            if alias not in truth:
                continue
            want = float(truth[alias])
            if abs(value - want) > 1e-9:
                report.append((name, alias, value, want))
    return report


# The reference .scad files rendered at the swept parameter set rather than at the hand
# driver's. ref_greeble_tool.scad and the corner's references are deliberately excluded:
# they are rendered at fuselage_corner.scad's values, which is the point of them.
SWEPT_REFS = [('ref_flange_base.scad', BULKHEAD), ('ref_simple_positives.scad', BULKHEAD),
              ('ref_web.scad', BULKHEAD), ('ref_greeble_web.scad', BULKHEAD),
              ('ref_fillets.scad', BULKHEAD), ('ref_flange_boss.scad', BULKHEAD),
              ('ref_flange_positive.scad', BULKHEAD),
              ('ref_bulkhead_cuts.scad', BULKHEAD),
              ('ref_bulkhead_section.scad', BULKHEAD),
              ('ref_bulkhead_full.scad', BULKHEAD),
              ('ref_greeble_tool_swept.scad', BULKHEAD),
              ('ref_corner_full.scad', CORNER)]

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
    for name, table in refs:
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

    bad = check_literals(CHECKED, path)
    print('\n  checked: %s' % ', '.join(n for n, _ in CHECKED))
    if bad:
        print('  %-18s %-24s %14s %14s' % ('module', 'alias', 'literal', 'derived'))
        for name, alias, got, want in bad:
            print('  %-18s %-24s %14s %14s' % (name, alias, got, want))
    else:
        print('  every literal agrees with the derived parameter set')

    bad_refs = check_refs(SWEPT_REFS, path)
    print('\n  reference .scad files rendered at the swept set: %d' % len(SWEPT_REFS))
    if bad_refs:
        print('  %-28s %-24s %14s %14s' % ('reference', 'name', 'in file', 'derived'))
        for name, alias, got, want in bad_refs:
            print('  %-28s %-24s %14s %14s' % (name, alias, got, want))
    else:
        print('  every assignment agrees with the derived parameter set')

    print('\n  known to differ on purpose:')
    for name, (table, why) in sorted(EXPECTED_TO_DIFFER.items()):
        diffs = check_literals([(name, table)], path)
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
