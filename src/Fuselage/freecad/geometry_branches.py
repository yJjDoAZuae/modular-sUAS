"""IP-FC-99 step one, the half that does not run in the virtualenv.

    freecadcmd geometry_branches.py --pass --variants=<path to the json>

**Why this is a second process rather than a second function.** The branching sweep has to
cover two layers, and they cannot be imported together. The *parameter* layer is
`check_derivation.RELATIONS`, which reaches it through `fuselage_variants` and therefore needs
`solid2` from the virtualenv. The *geometry* layer is `corner_common.Params`, whose module
imports FreeCAD. Neither interpreter has both, which is the same boundary `part_kinds` exists
to respect. So `tools/branching_dimensions.py` owns the first layer and drives this for the
second, handing over the variants as JSON.

**Why the second layer is not optional.** DES-9's own evidence is `flat_offset` -- register
row 3, a `max()` of a longeron term and a panel term where the branch decides whether a face
exists at all. It is **not** a `check_derivation` relation, not a declared given, and not a
field of the swept parameters: it is computed here, at `corner_common.Params.__init__`. A
count taken from the parameter layer alone would have missed the dimension the requirement was
written about, and would have looked complete.

**What this does and does not cover.** `Params` is pure arithmetic over the swept inputs, so
every variant can be evaluated without building anything. Dimensions computed *during a build*
-- inside a cowl or bulkhead geometry module -- are not reached, because exercising those means
building the parts. That is stated in the report rather than left to be assumed.

The method is `branching_dimensions.py`'s: replace `max` and `min` in the module's own
namespace and record which argument won at each call site, then attribute the site to the
attribute being assigned by reading back through the source. Nothing about the geometry
changes and no expression is restated.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corner_common as cc
from corner_common import is_entry_point

#: (line, which) -> {winning argument index: variants}
SITES = {}

#: Both branches gave the same value, so neither governed and there is nothing for a note to
#: say. Counted apart from wins rather than credited to the first argument.
TIES = {}

#: (line, which) -> [winner per entry], in the order the entries arrived. Aggregate counts say
#: how often a branch wins; only a per-variant record says *which* variants, and that is what
#: decides whether the note can be factored onto the same axes the value is
#: (`drawing_families.minimal_axes`). A tie is recorded as `t`, because "neither governed" is
#: a third outcome and folding it into the first argument would invent a branch.
PER_ENTRY = {}

#: Index of the variant being evaluated, so a recorded call can be placed.
_AT = [0]

ASSIGNMENT = re.compile(r'^\s*self\.([A-Za-z_][A-Za-z_0-9]*)\s*=')


def _watching(name, chooser):
    def watched(*args, **kwargs):
        value = chooser(*args, **kwargs)
        if kwargs or len(args) < 2:
            return value
        line = sys._getframe(1).f_lineno
        winners = [i for i, a in enumerate(args) if a == value]
        key = (line, name)
        if len(winners) > 1:
            TIES[key] = TIES.get(key, 0) + 1
            PER_ENTRY.setdefault(key, {})[_AT[0]] = 't'
        else:
            counts = SITES.setdefault(key, {})
            counts[winners[0]] = counts.get(winners[0], 0) + 1
            PER_ENTRY.setdefault(key, {})[_AT[0]] = str(winners[0])
        return value
    return watched


def attribute_at(line):
    """The `self.<name>` a call site belongs to, by reading back from its line.

    A multi-line expression reports the line the call starts on, which is at or below the
    assignment, so the nearest assignment above it is the one being computed.
    """
    source = io.open(cc.__file__, encoding='utf-8').read().splitlines()
    for i in range(min(line, len(source)) - 1, -1, -1):
        found = ASSIGNMENT.match(source[i])
        if found:
            return found.group(1)
    return '?'


def main():
    path = None
    for arg in sys.argv:
        if arg.startswith('--variants='):
            path = arg.split('=', 1)[1]
    if not path:
        raise SystemExit('missing --variants=<json>')

    entries = json.load(io.open(path, encoding='utf-8'))
    original = (getattr(cc, 'max', max), getattr(cc, 'min', min))
    cc.max = _watching('max', max)
    cc.min = _watching('min', min)
    try:
        for index, entry in enumerate(entries):
            _AT[0] = index
            cc.Params(**entry)
    finally:
        cc.max, cc.min = original

    print('VARIANTS %d' % len(entries))
    for (line, which), counts in sorted(SITES.items()):
        print('BRANCH\t%s\t%s:%d\t%s'
              % (attribute_at(line), which, line,
                 ' '.join('%d:%d' % (i, n) for i, n in sorted(counts.items()))))
    for (line, which), n in sorted(TIES.items()):
        print('TIE\t%s\t%s:%d\t%d' % (attribute_at(line), which, line, n))
    # One character per variant, in the order they were handed over, so the caller can line
    # them up against the axis values it already holds without trusting two enumerations to
    # agree. A variant whose call never happened reads `-`.
    for (line, which), seen in sorted(PER_ENTRY.items()):
        run = ''.join(seen.get(i, '-') for i in range(len(entries)))
        print('PER\t%s\t%s:%d\t%s' % (attribute_at(line), which, line, run))
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
