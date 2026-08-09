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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from corner_common import is_entry_point

# Modules whose literals should already agree with the swept parameter set.
CHECKED = ['flange_base', 'simple_positives', 'web', 'greeble_web', 'fillets',
           'flange_boss', 'bulkhead_cuts']

# Modules known to carry a different configuration on purpose, reported but not failed.
EXPECTED_TO_DIFFER = {
    'corner_tree': 'hand driver values from fuselage_corner.scad, not the swept set',
}


def load(path):
    with open(path) as f:
        doc = json.load(f)
    if not doc.get('valid'):
        raise RuntimeError('%s is a combination the sweep would not generate' % path)
    return doc


def rows(path):
    """Spreadsheet rows for the variant's parameters, as (alias, value) pairs."""
    doc = load(path)
    return [(k, repr(float(v))) for k, v in sorted(doc['parameters'].items())]


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


def check_literals(module_names, path):
    """Compare each module's literal parameters against the exported set."""
    truth = load(path)['parameters']
    report = []
    for name in module_names:
        mod = __import__(name)
        for alias, value in sorted(_literals(getattr(mod, 'PARAMS', [])).items()):
            if alias not in truth:
                continue
            want = float(truth[alias])
            if abs(value - want) > 1e-9:
                report.append((name, alias, value, want))
    return report


def main():
    args = [a for a in sys.argv[1:] if not a.endswith('.py')]
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
    print('\n  checked: %s' % ', '.join(CHECKED))
    if bad:
        print('  %-18s %-24s %14s %14s' % ('module', 'alias', 'literal', 'derived'))
        for name, alias, got, want in bad:
            print('  %-18s %-24s %14s %14s' % (name, alias, got, want))
    else:
        print('  every literal agrees with the derived parameter set')

    print('\n  known to differ on purpose:')
    for name, why in sorted(EXPECTED_TO_DIFFER.items()):
        diffs = check_literals([name], path)
        print('    %-16s %d disagreement(s) -- %s' % (name, len(diffs), why))
        for _, alias, got, want in diffs:
            print('      %-24s driver %-10s derived %s' % (alias, got, want))

    print('\n  %s' % ('FAIL: a checked module disagrees with the authority'
                      if bad else 'ok'))
    return 1 if bad else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
