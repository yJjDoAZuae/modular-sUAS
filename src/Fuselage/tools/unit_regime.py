"""IP-FC-161: inventory and enforce the unit regime of the FreeCAD port.

The project standard is SI (`doc/guidelines/general.md`): every internally stored value is in
meters, seconds, kilograms and radians, and non-SI appears only where something outside the
project demands it. The port did not meet that -- measured 2026-10-31, 46 of 79 modules held
173 module-level numeric constants in millimeters -- and the divergence survived three months
and 125 completed work items without anything noticing. A standard that only a reader enforces
drifts again the same way, so this module makes it mechanical.

**What this tool checks, and why it is a manifest rather than a pattern match.** A name cannot
be trusted to say what a number is: `TAU = 0.05` is a length in millimeters, `CHEEK_DOT = 0.9`
is a dot product, `RIB_FACETS = 48` is a count, and `UNITS_PER_EM = 2048` is a font design
unit. Guessing from the name is how an audit gets a number like "173 millimeter constants"
roughly right and individually wrong. So every module-level numeric constant in the port is
listed in `unit_regime.json` with the unit it carries, and this tool's first job is to fail when
a constant appears that nobody has classified. That makes classification a step in adding a
constant rather than an archaeology exercise later.

**The three places millimeters are legitimate**, which the manifest names per module:

    kernel        a value handed to OpenCASCADE, whose API is millimeters -- a boolean's fuzz,
                  a tessellation deflection. These live behind `freecad/si.py`, the one module
                  allowed to hold them, because a conversion called from geometry code means
                  the boundary is in the wrong place.
    presentation  a human-facing view of the geometry -- a drawing sheet, a text height, a line
                  weight. A drawing of a printed part is dimensioned in millimeters because
                  that is what the reader needs, which the guidelines place at their own
                  display boundary.
    external      a figure that belongs to something outside the project and is compared
                  against it unconverted -- an OpenSCAD reference volume in mm3.

Everything else is SI, and a dimensional SI constant must say so in its name (`_M`, `_M2`,
`_M3`, `_RAD`), because the one defect every other check in this project passes is a factor of
1000 and a reader needs to see the unit at the use site, not look it up.

**Inline literals are inventoried too, with a budget rather than a manifest entry.** A number
written inside a function has no name to classify, so `inline_literals` sorts each one by what it
*structurally cannot be* and reports what is left. Measured 2026-10-31: of **3089** numeric
literals in the port's function bodies, **2818 cannot be a length at all** -- an index, a
`/ 2.0`, a `range` bound, a format width -- and of the 271 that could, most are a fraction, an
epsilon, a named default argument or an angle. The residue is small enough to read.

Because a line number moves with every edit, the manifest records a **per-module ceiling** on
that residue instead of listing sites: a count that may not rise. Converting a module lowers its
ceiling; a new magic number raises the count past it and fails. The classifier being imperfect
only makes a ceiling slightly wrong, never the verdict.

**Limits on the instrument.** Two things remain outside what it can see:

1. **A value's unit at run time.** A parameter read from a sheet, a function argument, a return
   value: the manifest says what a *constant* carries, not what flows through a call. The check
   that covers that is `units.bbox_m_matches_mm` on a built part, which is a measurement rather
   than a lint.
2. **Whether a classification is right.** The manifest records a decision; it cannot verify one.
   Each entry here was made by reading the use site, and `FLAT_TOL` -- a dimensionless
   hypotenuse of a unit normal that reads like a length tolerance -- is why that was done by hand
   rather than from the names. The inline classifier is a heuristic for the same reason and says
   so: `abs(d) / ref > 1e-3` is a *relative* tolerance, and only the division tells you.

Saying so here matters because a passing check reads as "the port is SI", and what it actually
means is "every declared constant is classified, none of them stores millimeters in library
code, and no module has gained an unexplained inline dimension". That is a real property and it
is narrower than the sentence it invites.

Run:

    uv run python src/Fuselage/tools/unit_regime.py            # report
    uv run python src/Fuselage/tools/unit_regime.py --strict   # exit 1 on any finding
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
PORT = os.path.join(ROOT, 'src', 'Fuselage', 'freecad')
MANIFEST = os.path.join(HERE, 'unit_regime.json')

#: Units a constant may carry. `none` is dimensionless -- a count, a ratio, a dot product, an
#: enum member, a font design unit.
SI_UNITS = ('m', 'm2', 'm3', 'rad', 's', 'kg', 'none')
MM_UNITS = ('mm', 'mm2', 'mm3', 'deg')

#: A regime a module may declare. `si` is the default and is not listed in the manifest.
#:
#:     si            library code: every stored value is SI.
#:     boundary      the module's job is crossing a unit boundary -- `si.py` itself, the OML
#:                   import, the mesh readers, the export settings. It may hold a millimeter
#:                   value that belongs to whatever is on the other side.
#:     presentation  a human-facing view of the geometry: a drawing sheet, a figure, page
#:                   layout. Millimeters are what the reader of a printed part wants, and the
#:                   guidelines place display at its own boundary.
#:     external      a figure belonging to something outside the project, compared against it
#:                   unconverted.
REGIMES = ('si', 'boundary', 'presentation', 'external')

#: Suffix a dimensional SI constant's name must end with, per unit. `none` has no suffix rule.
SUFFIX = {'m': '_M', 'm2': '_M2', 'm3': '_M3', 'rad': '_RAD'}

#: Modules this tool does not read. The check scripts are entry points rather than library code,
#: and `si.py` is the boundary itself -- it is the one place a millimeter constant belongs.
SKIP_PREFIXES = ('check_', 'spike_')


class Finding(object):
    """One problem, with enough in it to fix without opening the file."""

    def __init__(self, module, name, line, kind, detail):
        self.module = module
        self.name = name
        self.line = line
        self.kind = kind
        self.detail = detail

    def __str__(self):
        where = '%s:%d' % (self.module, self.line) if self.line else self.module
        return '%-34s %-22s %s' % (where, self.name or '-', self.detail)


def _numeric(node):
    """The value of a numeric literal node, or `None` if it is not one.

    Handles the unary minus that `ast` keeps as its own node, and tuples of numbers, which the
    port uses for ladders like `CUT_FUZZ_LADDER`. A tuple reports its first element -- the unit
    is a property of the tuple, not of each member.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _numeric(node.operand)
        return None if inner is None else -inner
    if isinstance(node, (ast.Tuple, ast.List)) and node.elts:
        first = _numeric(node.elts[0])
        return first
    return None


def constants(path):
    """Every module-level numeric constant in one file, as `(name, line, value)`.

    Module level means exactly that: a constant inside a function or a class is a local and is
    governed by the same rule but is not part of this inventory, which exists to make the
    *declared* surface classifiable. Only upper-case names are collected, which is the project's
    convention for a module constant and is what separates one from a module-level variable.
    """
    text = io.open(path, encoding='utf-8').read()
    found = []
    for node in ast.parse(text).body:
        if not isinstance(node, ast.Assign):
            continue
        value = _numeric(node.value)
        if value is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                found.append((target.id, node.lineno, value))
    return found


#: Integers that cannot be a dimension whatever the context: a count, an index, a full turn,
#: a right angle, the millimeter factor itself.
STRUCTURAL = frozenset((0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100, 360, 180, 90, 45, 1000))

#: Values that are a proportion of something else wherever they appear -- a midpoint, a third,
#: a fraction of a span. A dimension of 0.5 mm exists, but it is written as a named constant;
#: a bare 0.5 in an expression is a ratio in every instance measured in this port.
FRACTIONS = frozenset((0.5, 0.25, 0.75, 1.5, 2.5, 0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9))

#: Text on the same line that makes a literal structural rather than dimensional.
STRUCTURAL_MARKERS = ('[', 'range(', 'round(', '%', 'start=', 'Number=', 'enumerate(')

#: Text that marks a comparison as *relative* -- a tolerance against a reference rather than a
#: length. A heuristic, and the one place this classifier is most likely to be wrong, which is
#: why the manifest holds a ceiling rather than a verdict per site.
RELATIVE_MARKERS = ('/ ref', '/ REF', '/ reference', 'rel ', 'rel)', 'rel,', '/ ref)',
                    'relative', 'fraction', '/ span', '/ total', '.Volume', '/ nominal')

#: The kind an inline literal is given. Only `dimension` counts against a module's ceiling.
INLINE_KINDS = ('structural', 'count', 'fraction', 'epsilon', 'default', 'angle', 'relative',
                'dimension')


def _factor_positions(tree):
    """Literals used as a scale factor rather than as a dimension.

    The rule is syntactic and it is the one that separates the two readings of `2.0`:

        abs(a) / 2.0          the literal divides -- a factor
        unit_width * 0.30     the literal is the right operand -- a proportion of something
        0.010 * U             the literal is the LEFT operand -- a dimension scaled by U
        ic_big_r ** 2         an exponent

    A dimension is assigned, added, or passed; it is not what you divide or scale *by*. So a
    literal on the right of `/` or `*`, or anywhere in `**` or `%`, is a factor, and a literal
    on the left of `*` is not excused -- which is what keeps `0.010 * U` visible.
    """
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp):
            continue
        if isinstance(node.op, (ast.Pow, ast.Mod)):
            sides = (node.left, node.right)
        elif isinstance(node.op, (ast.Div, ast.Mult, ast.FloorDiv)):
            sides = (node.right,)
        else:
            continue
        for side in sides:
            if isinstance(side, ast.Constant):
                out.add((side.lineno, side.col_offset))
    return out


class _InlineWalk(ast.NodeVisitor):
    """Collect numeric literals that appear inside a function body."""

    def __init__(self, lines):
        self.lines = lines
        self.rows = []
        self.depth = 0
        self.defaults = set()
        self.factors = set()

    def visit_FunctionDef(self, node):
        for default in list(node.args.defaults) + list(node.args.kw_defaults):
            if default is None:
                continue
            for sub in ast.walk(default):
                if isinstance(sub, ast.Constant):
                    self.defaults.add((sub.lineno, sub.col_offset))
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Constant(self, node):
        if self.depth == 0:
            return
        value = node.value
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        line = self.lines[node.lineno - 1] if node.lineno <= len(self.lines) else ''
        self.rows.append((node.lineno, node.col_offset, value, line.strip()))


def classify_inline(value, line, is_default, is_factor=False):
    """What an inline literal is, from its value, its syntactic role and the line it sits on.

    Deliberately ordered cheapest-and-surest first. Everything that reaches the end is reported
    as a `dimension`, so the classifier errs toward reporting rather than excusing.
    """
    if is_factor:
        return 'structural'
    if isinstance(value, int) and value in STRUCTURAL:
        return 'structural'
    for marker in STRUCTURAL_MARKERS:
        if marker in line:
            return 'structural'
    if isinstance(value, int):
        return 'count'
    if is_default:
        return 'default'
    if 'radians(' in line or 'degrees(' in line:
        return 'angle'
    for marker in RELATIVE_MARKERS:
        if marker in line:
            return 'relative'
    if value in FRACTIONS:
        return 'fraction'
    if abs(value) < 1.0e-5:
        return 'epsilon'
    return 'dimension'


def inline_literals(path):
    """Every numeric literal inside a function in one file, as `(line, value, text, kind)`."""
    text = io.open(path, encoding='utf-8').read()
    tree = ast.parse(text)
    walk = _InlineWalk(text.splitlines())
    walk.factors = _factor_positions(tree)
    walk.visit(tree)
    out = []
    for lineno, col, value, line in walk.rows:
        kind = classify_inline(value, line, (lineno, col) in walk.defaults,
                               (lineno, col) in walk.factors)
        out.append((lineno, value, line, kind))
    return out


def modules(port=PORT):
    """The port's library modules, in sorted order, as `(name, path)`."""
    out = []
    for name in sorted(os.listdir(port)):
        if not name.endswith('.py') or name.startswith(SKIP_PREFIXES):
            continue
        out.append((name[:-3], os.path.join(port, name)))
    return out


def load_manifest(path=MANIFEST):
    """The classification manifest, or an empty one when it does not exist yet."""
    if not os.path.exists(path):
        return {'regimes': {}, 'constants': {}}
    with io.open(path, encoding='utf-8') as handle:
        return json.load(handle)


def audit(port=PORT, manifest=None):
    """Check the port against the manifest. Returns `(findings, summary)`.

    `summary` counts what is left to do, so a caller can report progress without re-deriving it:
    `pending` is the number of constants still carrying a millimeter unit in a module whose
    regime is `si`, which is the quantity the conversion drives to zero.
    """
    manifest = load_manifest() if manifest is None else manifest
    regimes = manifest.get('regimes', {})
    declared = manifest.get('constants', {})

    findings = []
    seen = 0
    pending = 0
    by_unit = {}
    present = set()

    for module, path in modules(port):
        regime = regimes.get(module, 'si')
        if regime not in REGIMES:
            findings.append(Finding(module, None, 0, 'regime',
                                    'unknown regime %r, expected one of %s'
                                    % (regime, ', '.join(REGIMES))))
            regime = 'si'

        for name, line, value in constants(path):
            seen += 1
            key = '%s.%s' % (module, name)
            present.add(key)
            entry = declared.get(key)

            if entry is None:
                findings.append(Finding(module, name, line, 'unclassified',
                                        'not in the manifest -- classify it with its unit '
                                        '(value %r)' % (value,)))
                continue

            unit = entry.get('unit')
            if unit not in SI_UNITS and unit not in MM_UNITS:
                findings.append(Finding(module, name, line, 'bad-unit',
                                        'unit %r is not one of %s'
                                        % (unit, ', '.join(SI_UNITS + MM_UNITS))))
                continue

            by_unit[unit] = by_unit.get(unit, 0) + 1

            if unit in MM_UNITS:
                if regime == 'si':
                    pending += 1
                    findings.append(Finding(
                        module, name, line, 'stored-mm',
                        'stores %s in a module whose regime is SI -- convert it, or move it '
                        'behind si.py if the kernel requires it' % unit))
                elif not entry.get('reason'):
                    findings.append(Finding(module, name, line, 'no-reason',
                                            'is %s in a %s module and gives no reason'
                                            % (unit, regime)))
                continue

            suffix = SUFFIX.get(unit)
            if suffix and not name.endswith(suffix):
                findings.append(Finding(module, name, line, 'unnamed-unit',
                                        'is in %s and its name does not end %s'
                                        % (unit, suffix)))

    # An entry whose constant is gone is not merely untidy: it would silently excuse a future
    # constant of the same name carrying a different unit, which is the one way this manifest
    # could license the error it exists to catch.
    for key in sorted(set(declared) - present):
        module, _, name = key.partition('.')
        findings.append(Finding(module, name, 0, 'stale',
                                'is in the manifest and not in the tree -- delete the entry, '
                                'so it cannot excuse a future constant of the same name'))

    # Inline literals, against each module's ceiling. A module with no entry has a ceiling of
    # zero, so a new module carrying a bare dimension is reported without anyone adding a rule.
    ceilings = manifest.get('inline', {})
    inline_total = 0
    for module, path in modules(port):
        rows = [row for row in inline_literals(path) if row[3] == 'dimension']
        inline_total += len(rows)
        entry = ceilings.get(module, {})
        allowed = entry.get('allowed', 0)
        if len(rows) > allowed:
            # Report only the excess, so a module at its ceiling is quiet and a module one
            # over names one site rather than all of them.
            for lineno, value, line, _kind in rows[allowed:]:
                findings.append(Finding(
                    module, repr(value), lineno, 'inline-dimension',
                    'a bare dimensional literal over this module\'s ceiling of %d: %s'
                    % (allowed, line[:70])))
        elif len(rows) < allowed:
            findings.append(Finding(
                module, None, 0, 'inline-ceiling-stale',
                'has %d bare inline dimension(s) and a ceiling of %d -- lower the ceiling so '
                'it cannot drift back up' % (len(rows), allowed)))

    for module in sorted(set(ceilings) - dict((m, p) for m, p in modules(port)).keys()):
        findings.append(Finding(module, None, 0, 'inline-ceiling-stale',
                                'has an inline ceiling and is not in the tree'))

    summary = {'constants': seen, 'pending': pending, 'by_unit': by_unit,
               'modules': len(modules(port)), 'inline_dimensions': inline_total}
    return findings, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--strict', action='store_true',
                        help='exit 1 when there is any finding, not only an unclassified one')
    parser.add_argument('--kind', default=None,
                        help='report only findings of this kind')
    args = parser.parse_args(argv)

    findings, summary = audit()
    if args.kind:
        findings = [f for f in findings if f.kind == args.kind]

    by_kind = {}
    for finding in findings:
        by_kind.setdefault(finding.kind, []).append(finding)

    for kind in sorted(by_kind):
        print('')
        print('%s -- %d' % (kind, len(by_kind[kind])))
        print('=' * 78)
        for finding in by_kind[kind]:
            print('  %s' % finding)

    print('')
    print('%d module(s), %d constant(s), %d still stored in millimeters, '
          '%d bare inline dimension(s)'
          % (summary['modules'], summary['constants'], summary['pending'],
             summary['inline_dimensions']))
    if summary['by_unit']:
        print('by unit: %s' % ', '.join('%s=%d' % (u, n)
                                        for u, n in sorted(summary['by_unit'].items())))

    if findings and (args.strict or any(f.kind == 'unclassified' for f in findings)):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
