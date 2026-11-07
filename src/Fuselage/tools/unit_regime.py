"""IP-FC-161: inventory and enforce the unit regime of the FreeCAD port.

The project standard is SI (`doc/guidelines/general.md`): every internally stored value is in
meters, seconds, kilograms and radians, and non-SI appears only where something outside the
project demands it. The port did not meet that -- measured 2026-10-31, 46 of 79 modules held
173 module-level numeric constants in millimeters -- and the divergence survived three months
and 125 completed work items without anything noticing. A standard that only a reader enforces
drifts again the same way, so this module makes it mechanical.

**What this tool checks, and why it is a manifest rather than a pattern match.** A name cannot
be trusted to say what a number is: `TAU = 0.05` is a length in millimeters, `CAP_COSINE = 0.9`
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
*structurally cannot be* and reports what is left. Measured 2026-11-01, and the breakdown is
given in full because it is the figure the ceilings are argued from -- of **3 044** numeric
literals in the port's function bodies:

    structural   2492   an index, a `/ 2.0`, a `range` bound, a format width -- cannot be a length
    epsilon       218   below 1e-5, so a construction epsilon rather than a dimension
    dimension     188   the residue: what this tool reports
    fraction       50   a proportion of something else
    default        48   a named default argument, so it has a name after all
    angle          18   on a line calling `radians()` or `degrees()`
    relative       16   a tolerance against a reference, not a length
    count          14   a whole number that is not in the structural set

Re-derive it with `sum(1 for ... in inline_literals(path))` grouped by kind; an earlier version
of this paragraph quoted 3 089 and 2 818, and the second figure reproduced from nothing.

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
import builtins
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
#:
#: `record` is a table whose rows hold several quantities at once -- `boom_oml.REFS` is an area,
#: a bounding box and a tolerance per label. One suffix on the table's name cannot say what
#: three different members carry, so the rule moves to the members: a `record` must be a
#: `namedtuple` whose field names carry the units (`area_m2`, `bbox_m`), which puts the unit at
#: every use site rather than on the declaration, and it must give a reason naming them. That
#: is a stronger guarantee than the suffix, not a way around it -- `REFS[label].area_m2` says
#: its unit on the line that reads it, where a suffixed table name would not.
SI_UNITS = ('m', 'm2', 'm3', 'rad', 's', 'kg', 'none', 'record')
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


def _first_number(node):
    """The first numeric literal anywhere inside an expression, or `None` if it holds none.

    The fallback for the two shapes `_numeric` cannot read, both of which the port really
    writes and both of which were invisible to this inventory until 2026-11-01:

        REFS = [('web_inner', 5700.1741175, (-40.9, ...)), ...]   a table keyed by label
        SQ2 = 2 ** 0.5                                            a computed constant

    A table carries one unit for the whole table, exactly as a ladder tuple does, so one entry
    classifies it and the reported value is the first figure in it -- enough for a reader to
    recognize which constant the finding is about. Missing these mattered: `cowl.REFERENCE`
    alone holds 51 numbers, and a blind inventory cannot support a claim that the port is SI.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, (int, float)) \
                and not isinstance(sub.value, bool):
            return sub.value
    return None


def constants(path):
    """Every module-level numeric constant in one file, as `(name, line, value)`.

    Module level means exactly that: a constant inside a function or a class is a local and is
    governed by the same rule but is not part of this inventory, which exists to make the
    *declared* surface classifiable. Only upper-case names are collected, which is the project's
    convention for a module constant and is what separates one from a module-level variable.

    `value` is the constant's value when it is a plain number, and otherwise the first number
    inside it -- a tuple's first member, a table's first figure, the first literal in a computed
    expression. A constant holding no number at all is not in the inventory, because there is
    nothing in it to carry a unit.
    """
    text = io.open(path, encoding='utf-8').read()
    found = []
    for node in ast.parse(text).body:
        if not isinstance(node, ast.Assign):
            continue
        value = _numeric(node.value)
        if value is None:
            value = _first_number(node.value)
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


#: Name endings that say an operand carries a unit. The suffixes the standard already requires,
#: plus the millimeter ones the presentation and OpenSCAD layers keep.
#:
#: **Declared here rather than beside `_dimensional_operand`, because two separate checks read
#: it** -- that one, for a `//`, and `_carries_a_unit`, for the left operand of a `*`. Keeping one
#: list is what stops the two answering differently about the same name.
_DIMENSIONAL_SUFFIX = ('_m', '_mm', '_m2', '_m3', '_rad',
                       '_M', '_MM', '_M2', '_M3', '_RAD')


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

    **One exception on that last rule, added by IP-FC-163: the left operand of a `*` whose other
    side plainly carries a unit.**

        2.0 * r_outer_m       the NAME carries the unit, so the literal is a multiplier
        0.010 * U             `U` is dimensionless, so the literal is the dimension

    The distinction is the same one the `//` rule already uses -- `_dimensional_operand`, which
    reads the suffix the standard requires. Without it, converting a module *creates* findings:
    `arc / (2.0 * r_outer)` reported nothing and `arc_m / (2.0 * r_outer_m)` reported the `2.0`,
    so the SI conversion turned 37 correct lines in `wall_measure` into inline-dimension
    findings purely by renaming their operands. A sweep that fires on a conversion done right is
    one that gets ignored.
    """
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp):
            continue
        if isinstance(node.op, (ast.Pow, ast.Mod)):
            sides = (node.left, node.right)
        elif isinstance(node.op, (ast.Div, ast.FloorDiv)):
            sides = (node.right,)
        elif isinstance(node.op, ast.Mult):
            sides = [node.right]
            # A literal times something that names its own unit is a multiplier, not a dimension.
            if isinstance(node.left, ast.Constant) and _carries_a_unit(node.right):
                sides.append(node.left)
        else:
            continue
        for side in sides:
            if isinstance(side, ast.Constant):
                out.add((side.lineno, side.col_offset))
    return out


def _carries_a_unit(node):
    """Does this expression name a unit-suffixed value anywhere inside it?

    Deliberately the *same* suffix list `_dimensional_operand` uses, so the two places that ask
    this question cannot drift apart. A literal is not enough on its own -- `2.0 * 0.6` says
    nothing about which number is the dimension -- so only a name, attribute or call counts.
    """
    for child in ast.walk(node):
        name = None
        if isinstance(child, ast.Name):
            name = child.id
        elif isinstance(child, ast.Attribute):
            name = child.attr
        elif isinstance(child, ast.Call):
            name = child.func.id if isinstance(child.func, ast.Name) else (
                child.func.attr if isinstance(child.func, ast.Attribute) else None)
        if name and name.endswith(_DIMENSIONAL_SUFFIX):
            return True
    return False


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


#: Directories whose Python the constant audit covers. **`tools/` is here because the standard
#: covers it**: `doc/guidelines/general.md` says "every variable, field, parameter, function
#: argument, and return value in the project", and `tools/wall_measure` is 8 022 lines of library
#: code called directly from the port.
AUDIT_ROOTS = (PORT, HERE)

#: Directory names never descended into.
SKIP_DIRS = ('__pycache__', '.pytest_cache', 'variant_output', 'variant_output_original', 'out')


def modules(port=None, roots=None):
    """Every library module the audit covers, in sorted order, as `(name, path)`.

    **Walked, not listed.** Until 2026-11-02 this used `os.listdir` on one directory, so
    `tools/wall_measure/` -- 19 modules and 8 022 lines, the largest body of unconverted code in
    the project -- was never opened by this sweep or by `--undefined` or `--counts`. It was not
    reported clean; it was not reported, and every "0 still stored in millimeters" figure taken
    before the fix excluded it. A sweep that enumerates less than it claims to audit is worse than
    no sweep, because its clean reading gets quoted. IP-FC-167 carries the repair.

    **Names are package-qualified** relative to the root they were found under, so
    `wall_measure.truth.R_OUTER` and a top-level `R_OUTER` cannot share a manifest key and excuse
    each other. A module directly in a root keeps its bare name, so every existing manifest entry
    still resolves.

    `port` is accepted for the callers that passed one positionally and audits that directory
    alone; `roots` overrides the default set.
    """
    if roots is None:
        roots = (port,) if port is not None else AUDIT_ROOTS
    out = []
    for root in roots:
        for base, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                if not name.endswith('.py') or name.startswith(SKIP_PREFIXES):
                    continue
                rel = os.path.relpath(os.path.join(base, name), root)
                dotted = rel[:-3].replace(os.sep, '.')
                if dotted.endswith('.__init__'):
                    dotted = dotted[:-len('.__init__')]
                out.append((dotted, os.path.join(base, name)))
    return sorted(out)


def load_manifest(path=MANIFEST):
    """The classification manifest, or an empty one when it does not exist yet."""
    if not os.path.exists(path):
        return {'regimes': {}, 'constants': {}}
    with io.open(path, encoding='utf-8') as handle:
        return json.load(handle)


def audit(port=None, manifest=None):
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

            # A constant may declare its own regime, overriding the module's. This is what a
            # parameter-sheet alias table needs: `cowl.PARAMS_TAIL` is millimeters because a
            # `Spreadsheet::Sheet` evaluates in millimeters and the seed comes from
            # `derived_parameters()`, the exempt OpenSCAD path -- but the other 550 lines of
            # `cowl.py` are ordinary library code and must stay SI. Declaring the whole module
            # `boundary` to excuse one table would exempt everything around it, which is the
            # coarse version of the mistake this tool exists to catch.
            regime_here = entry.get('regime', regime)
            if regime_here not in REGIMES:
                findings.append(Finding(module, name, line, 'regime',
                                        'declares unknown regime %r, expected one of %s'
                                        % (regime_here, ', '.join(REGIMES))))
                regime_here = regime

            unit = entry.get('unit')
            if unit not in SI_UNITS and unit not in MM_UNITS:
                findings.append(Finding(module, name, line, 'bad-unit',
                                        'unit %r is not one of %s'
                                        % (unit, ', '.join(SI_UNITS + MM_UNITS))))
                continue

            by_unit[unit] = by_unit.get(unit, 0) + 1

            if unit in MM_UNITS:
                if regime_here == 'si':
                    pending += 1
                    findings.append(Finding(
                        module, name, line, 'stored-mm',
                        'stores %s in a module whose regime is SI -- convert it, or move it '
                        'behind si.py if the kernel requires it' % unit))
                elif not entry.get('reason'):
                    findings.append(Finding(module, name, line, 'no-reason',
                                            'is %s at a %s and gives no reason'
                                            % (unit, regime_here)))
                continue

            # A record carries no suffix, because its members carry their own; what it owes
            # instead is a stated reason naming them, so a reader can check the claim.
            if unit == 'record' and not entry.get('reason'):
                findings.append(Finding(module, name, line, 'no-reason',
                                        'is a record and does not name the units its fields '
                                        'carry -- give the reason, e.g. "rows are '
                                        'Ref2D(area_m2, bbox_m, tol)"'))
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
        # `rpartition`, not `partition`: a package-qualified key is `wall_measure.truth.R_OUTER`,
        # and splitting on the first dot would report the module as `wall_measure` and the
        # constant as `truth.R_OUTER`.
        module, _, name = key.rpartition('.')
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


# ---------------------------------------------------------------------------------------------
# The rename sweep. A unit conversion renames constants, parameters and locals in bulk, and the
# one error it keeps making is a reference the rename missed.
# ---------------------------------------------------------------------------------------------

#: Names a module may read without defining: the FreeCAD interpreter's own, and the two the port
#: imports under a short alias everywhere. `__file__` and friends are module attributes rather
#: than globals and are listed for the same reason.
AMBIENT = frozenset((
    'App', 'Part', 'Sketcher', 'Mesh', 'MeshPart', 'Draft', 'TechDraw', 'FreeCAD', 'FreeCADGui',
    '__file__', '__name__', '__doc__', '__package__', '__spec__', '__builtins__',
))


def _bound_in(node):
    """Every name a function binds: its parameters, its assignments, its imports, its `except`
    aliases, and the names of anything defined inside it."""
    out = set()
    args = getattr(node, 'args', None)
    if args is not None:
        for group in (getattr(args, 'posonlyargs', []), args.args, args.kwonlyargs):
            out.update(a.arg for a in group)
        if args.vararg:
            out.add(args.vararg.arg)
        if args.kwarg:
            out.add(args.kwarg.arg)
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
            out.add(sub.id)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and sub is not node:
            out.add(sub.name)
        elif isinstance(sub, ast.Lambda) and sub is not node:
            for group in (getattr(sub.args, 'posonlyargs', []), sub.args.args,
                          sub.args.kwonlyargs):
                out.update(a.arg for a in group)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            out.add(sub.name)
        elif isinstance(sub, (ast.Import, ast.ImportFrom)):
            for alias in sub.names:
                out.add((alias.asname or alias.name).split('.')[0])
        elif isinstance(sub, ast.Global) or isinstance(sub, ast.Nonlocal):
            out.update(sub.names)
    return out


def undefined_names(path):
    """Names a file reads that nothing in it defines, as `(line, name)` pairs.

    **This is the check a bulk rename needs and a test suite does not give you.** Renaming
    `t` to `t_m` across a 3600-line module leaves a reference behind somewhere, and the
    reference raises `NameError` only on the branch that reaches it -- which for a geometry
    refusal path can be never, in any check that passes. Found 7 such sites in
    `cowl_interior.py` alone on the day it was converted, including one in an `Unconverged`
    message that no passing build executes.

    Scoped rather than flat: a function sees the module's names plus its own, so a local that
    shadows nothing is not reported, and a name defined only inside a sibling function is.
    Imports inside a `try` are collected, because that is how the port guards `Mesh`.
    """
    text = io.open(path, encoding='utf-8').read()
    tree = ast.parse(text)

    top = set(dir(builtins)) | set(AMBIENT)
    # Module scope: every name bound at the top level, plus the names of the functions and
    # classes defined there. A function's own body is walked separately, with its own scope.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            top.add(node.name)
            continue
        top |= _bound_in(node)

    found = []

    def visit(node, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, scope | _bound_in(child))
            elif isinstance(child, ast.ClassDef):
                visit(child, scope | {child.name} | _bound_in(child))
            elif isinstance(child, ast.Lambda):
                visit(child, scope | _bound_in(child))
            else:
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) \
                        and child.id not in scope:
                    found.append((child.lineno, child.id))
                visit(child, scope)

    visit(tree, top)
    return sorted(set(found))


#: Where the rename sweep looks: the port, its sibling tool directory, and the pytest tier.
#: Wider than `modules()` deliberately -- the references a rename misses are most often in a
#: check script or a test, which are exactly the files `modules()` skips.
SWEEP_DIRS = (
    PORT,
    HERE,
    os.path.join(ROOT, 'tests'),
)


def _public_names(path):
    """Every name a module defines at its top level, which is its importable surface."""
    out = set()
    try:
        tree = ast.parse(io.open(path, encoding='utf-8').read())
    except (SyntaxError, OSError):
        return out
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        else:
            out |= _bound_in(node)
    return out


def _aliases(tree):
    """`local name -> module name` for every `import x` / `import x as y` in a file."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split('.')[0]
                out[alias.asname or base] = base
    return out


def installed_attributes(path):
    """`module.NAME` for every attribute this file assigns on an imported module.

    A module attribute that something installs at run time is defined, even though no
    top-level statement writes it: `geometry_branches` swaps `corner_common.max` for a tracing
    wrapper and restores it in a `finally`, and `test_branching_dimensions` then asserts the
    restore happened. Collected across the whole sweep rather than per file, because the file
    that installs one and the file that reads it are usually not the same.
    """
    try:
        tree = ast.parse(io.open(path, encoding='utf-8').read())
    except (SyntaxError, OSError):
        return set()
    alias_map = _aliases(tree)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)) \
                and isinstance(node.value, ast.Name):
            module = alias_map.get(node.value.id)
            if module is not None:
                out.add('%s.%s' % (module, node.attr))
    return out


def missing_attributes(path, surface, installed=()):
    """References to `module.NAME` where `module` is in `surface` and `NAME` is not in it.

    **The half of a rename sweep that `undefined_names` cannot see.** `ci.WALL_TOL` is an
    attribute access, not a name, so a renamed module constant read through an import alias is
    invisible to a scope check and raises `AttributeError` only when that line runs. The
    `cowl_interior` conversion left 20-odd of these across the check scripts and the pytest
    tier, in modules whose own tests pass.

    `surface` is `{module: set of its top-level names}`. A module not in it is skipped, so this
    says nothing about FreeCAD's own API or the standard library.
    """
    try:
        text = io.open(path, encoding='utf-8').read()
        tree = ast.parse(text)
    except (SyntaxError, OSError):
        return []
    alias_map = _aliases(tree)
    installed = set(installed) | installed_attributes(path)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
            continue
        if not isinstance(node.ctx, ast.Load):
            continue
        module = alias_map.get(node.value.id)
        if module is None or module not in surface:
            continue
        # Every module has these whether or not it writes them.
        if node.attr.startswith('__') and node.attr.endswith('__'):
            continue
        reference = '%s.%s' % (module, node.attr)
        if node.attr not in surface[module] and reference not in installed:
            out.append((node.lineno, reference))
    return sorted(set(out))


def sweep_undefined(dirs=SWEEP_DIRS):
    """Both rename sweeps over every Python file in `dirs`, as `(relative path, line, what)`.

    `undefined_names` catches a bare reference a rename missed; `missing_attributes` catches one
    read through an import alias. Together they are what makes a bulk rename checkable without
    executing every branch.
    """
    surface = {}
    for directory in (PORT, HERE):
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if name.endswith('.py'):
                surface[name[:-3]] = _public_names(os.path.join(directory, name))

    paths = []
    for directory in dirs:
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if name.endswith('.py'):
                paths.append(os.path.join(directory, name))

    installed = set()
    for path in paths:
        installed |= installed_attributes(path)

    out = []
    for path in paths:
        rel = os.path.relpath(path, ROOT)
        try:
            rows = undefined_names(path)
        except SyntaxError as exc:
            out.append((rel, exc.lineno or 0, 'SYNTAX ERROR: %s' % exc.msg))
            continue
        for line, symbol in rows:
            out.append((rel, line, symbol))
        for line, symbol in missing_attributes(path, surface, installed):
            out.append((rel, line, symbol))
    return out


#: Calls that turn a real-valued expression into a whole number.
_TRUNCATING = frozenset(('int', 'round', 'floor', 'ceil', 'trunc'))


def _has_division(node):
    """Does this expression divide anywhere inside itself, in a way a unit could reach?

    A true division counts wherever it appears. A `//` counts only when an operand plainly
    carries a length, because `len(x) // 2` and `available // (per_worker * 1024 * 1024)` are
    integer arithmetic on counts and bytes and no unit can reach them.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.BinOp):
            if isinstance(child.op, ast.Div):
                return True
            if isinstance(child.op, ast.FloorDiv) and _dimensional_operand(child):
                return True
    return False


def _rounds(node):
    """Is this truncation a `round`, or does it wrap one?

    **`round` is materially safer than `int` here and the report says so rather than treating
    them alike.** `int(a / b)` has a boundary at every integer and approaches it from one side,
    so a last-bit change in either operand flips it whenever the ratio is just above a whole
    number -- which is the common case for a span that is a whole number of steps.  `round`'s
    boundaries are the half-integers, and a ratio of two lengths sits within an ulp of one of
    those only by coincidence. Both are reported; only the truncating form is a finding.
    """
    name = node.func.id if isinstance(node.func, ast.Name) else (
        node.func.attr if isinstance(node.func, ast.Attribute) else None)
    if name == 'round':
        return True
    for child in ast.walk(node.args[0]) if node.args else ():
        if isinstance(child, ast.Call):
            inner = child.func.id if isinstance(child.func, ast.Name) else (
                child.func.attr if isinstance(child.func, ast.Attribute) else None)
            if inner == 'round':
                return True
    return False


#: Calls whose result is a count whatever their argument is, so a unit suffix inside one says
#: nothing about the division it feeds.
_COUNTING_CALLS = frozenset(('len',))


def _dimensional_operand(node):
    """Does either side of this division plainly carry a length?

    Used only for `//`, which is integer arithmetic on counts far more often than it is one
    length over another. A float literal or a unit-suffixed name is the signal; a `len()` call,
    an index or an integer literal is not. The test is the name, so it stays readable and cannot
    depend on this tool knowing any module's figures -- and it errs toward reporting, since a
    name with no suffix at all is exactly what the standard forbids for a dimension.

    **The inside of a `len(...)` is not read, and the conversion is what exposed that it had to
    be skipped** (IP-FC-163). This function's own docstring named `len(x) // 2` as the case it
    must not flag, and that held only while `x` had no unit suffix: once `tau_study`'s station
    list became `zs_m`, `len(zs_m) // 2` walked down to a `_m` name and was reported as a
    dimensional count. It is the midpoint of a list -- as unit-invariant as an expression gets --
    so the finding was the instrument's, not the code's. A sweep that cries wolf on a correct site
    is how a real one gets dismissed, which is the whole reason this tool reports a ceiling rather
    than a verdict.

    The skip is computed as a set of nodes and not by breaking out of the walk, because
    `ast.walk` is breadth-first: breaking at the `len` call would also abandon the rest of that
    side, so `len(x) + y_m` would stop before reaching `y_m`.
    """
    for side in (node.left, node.right):
        skip = set()
        for child in ast.walk(side):
            if not isinstance(child, ast.Call):
                continue
            called = child.func.id if isinstance(child.func, ast.Name) else (
                child.func.attr if isinstance(child.func, ast.Attribute) else None)
            if called in _COUNTING_CALLS:
                skip.update(id(inner) for inner in ast.walk(child))
        for child in ast.walk(side):
            if id(child) in skip:
                continue
            if isinstance(child, ast.Constant) and isinstance(child.value, float):
                return True
            name = None
            if isinstance(child, ast.Name):
                name = child.id
            elif isinstance(child, ast.Attribute):
                name = child.attr
            elif isinstance(child, ast.Call):
                name = child.func.id if isinstance(child.func, ast.Name) else (
                    child.func.attr if isinstance(child.func, ast.Attribute) else None)
            if name and name.endswith(_DIMENSIONAL_SUFFIX):
                return True
    return False


def _has_slack(node):
    """Does this expression add a named slack term, the way `_steps` does?

    The marker is a name ending in `SLACK`, which is what makes the count land on the same side
    of the boundary whichever unit its operands are written in. Matching the name rather than a
    magnitude keeps this checkable without the tool knowing any module's figures.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Add, ast.Sub)):
            for side in (child.left, child.right):
                if isinstance(side, ast.Name) and side.id.endswith('SLACK'):
                    return True
    return False


#: Truncating divisions that are allowed to stand, by module, with the reason each is safe.
#: Keyed on the unparsed expression rather than a line number, because a line moves with every
#: edit above it. A site not listed here and carrying no slack term is reported.
#:
#: **The reason has to be that no unit crosses, not that the count looks harmless.** This tool
#: asks one question -- can this count change because its operands were converted -- so a ratio
#: of two millimeter figures inside a declared millimeter module is genuinely out of scope,
#: while an SI ratio in geometry code is not, however small the consequence looks.
COUNT_ALLOWED = {
    'check_cowl_interior': {
        'int((edge_mm + margin_mm - (edge_mm - margin_mm)) / step_mm_)':
            'the millimeter half of the `_steps` unit-invariance case, written out on purpose '
            'so the two units can be compared; converting it would delete the test',
        'int(span / step)':
            'the expression `_steps` replaced, written out so the clamp-commutation case can '
            'compare the two; routing it through the helper would compare the helper with '
            'itself',
    },
    'cowl_interior': {
        'int(math.ceil(math.pi / math.asin(min(1.0, in_plane_m / (2.0 * t_m)))))':
            'inside a `PreconditionFailed` message, computing the facet count it suggests; no '
            'geometry reads it',
    },
    'check_table_width': {
        'int((block_b[1] - frame_b[1]) // (ds.TABLE_ROW_PITCH_HEIGHTS * ds.TEXT_HEIGHT_MM))':
            'page geometry, millimeters on both sides, in a declared presentation module',
        'int((block[1] - frame[1]) // (ds.TABLE_ROW_PITCH_HEIGHTS * ds.TEXT_HEIGHT_MM))':
            'page geometry, millimeters on both sides, in a declared presentation module',
    },
    'drawing_standard': {
        'int(table_band_depth_mm() // table_row_pitch_mm(height))':
            'page geometry, millimeters on both sides, in a declared presentation module',
    },
    'clearance_sheet': {
        'int((bb.ZMax - bb.ZMin) / step)':
            'the drawing\'s own model-space window, millimeters on both sides off a kernel '
            'bounding box, in a declared presentation module',
    },
    'check_derivation': {
        'math.ceil(offset / quantum)':
            'the OpenSCAD path, which is millimeters throughout by the exemption in '
            'doc/guidelines/general.md and is never converted',
    },
    'fuselage_variants': {
        'math.ceil(panel_offset / PANEL_OFFSET_QUANTUM_MM)':
            'the OpenSCAD path, which is millimeters throughout by the exemption in '
            'doc/guidelines/general.md and is never converted',
    },
    'test_drawing_standard': {
        'int(ds.table_band_depth_mm() // real_pitch)':
            'mirrors the presentation module it tests, millimeters on both sides',
    },
}


def truncating_counts(path):
    """Every `int(a / b)`-shaped expression in `path`, as `(line, text, verdict)`.

    **This is the fourth instrument, and it exists because a regex missed the site that
    mattered.** `int(span / step)` is not unit-invariant -- a window of exactly two margins is
    `2.0 / 0.5 = 4` in millimeters and 3.9999999999999964 in meters, which truncates to 3 -- so
    every count of that shape has to be found, not most of them. The grep first used for it was
    `int\\([^)]*/[^)]*`, which cannot match `int(si.length_m(arc) / SAMPLE_SPACING_M)`: there is a
    closing parenthesis before the divide. Two of the four sites in `cowl_interior` were invisible
    to it and were found by reading. An expression tree has no such blind spot.

    `verdict` is `'slack'` when the expression adds a named slack term, `'allowed'` when
    `COUNT_ALLOWED` lists it with a reason, and `'bare'` otherwise. Only `'bare'` is a finding:
    a bare truncating division is a count whose value can depend on the unit its operands are
    written in, which is a defect on its own terms whether or not it currently bites.
    """
    with io.open(path, encoding='utf-8', newline='') as handle:
        tree = ast.parse(handle.read(), path)
    module = os.path.basename(path)[:-3]
    allowed = COUNT_ALLOWED.get(module, {})

    out = []
    for node in ast.walk(tree):
        argument = None
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else None)
            if name in _TRUNCATING and node.args and _has_division(node.args[0]):
                argument = node.args[0]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.FloorDiv):
            # `//` is ordinary integer arithmetic far more often than it is a length over a
            # length, so it counts only when an operand is plainly dimensional. `len(x) // 2`
            # and `flat // d2.shape[1]` are counts and cannot depend on a unit; `depth_mm() //
            # pitch_mm(h)` can.
            if _dimensional_operand(node):
                argument = node
        if argument is None:
            continue
        text = ast.unparse(node) if hasattr(ast, 'unparse') else '<expression>'
        if _has_slack(argument):
            verdict = 'slack'
        elif text in allowed:
            verdict = 'allowed'
        elif isinstance(node, ast.Call) and _rounds(node):
            verdict = 'round'
        else:
            verdict = 'bare'
        out.append((node.lineno, text, verdict))

    # A second pass is cheaper than tracking parents: drop any row whose text is a strict
    # substring of another row's on the same line, which is exactly the nested case.
    keep = []
    for line, text, verdict in sorted(out):
        if any(line == other_line and text != other and text in other
               for other_line, other, _v in out):
            continue
        keep.append((line, text, verdict))
    return keep


def sweep_counts(dirs=SWEEP_DIRS):
    """`truncating_counts` over every Python file in `dirs`, as `(path, line, text, verdict)`."""
    out = []
    for directory in dirs:
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.endswith('.py'):
                continue
            path = os.path.join(directory, name)
            rel = os.path.relpath(path, ROOT)
            try:
                rows = truncating_counts(path)
            except SyntaxError as exc:
                out.append((rel, exc.lineno or 0, 'SYNTAX ERROR: %s' % exc.msg, 'bare'))
                continue
            for line, text, verdict in rows:
                out.append((rel, line, text, verdict))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--strict', action='store_true',
                        help='exit 1 when there is any finding, not only an unclassified one')
    parser.add_argument('--kind', default=None,
                        help='report only findings of this kind')
    parser.add_argument('--undefined', action='store_true',
                        help='sweep for names a rename left behind, instead of auditing units')
    parser.add_argument('--counts', action='store_true',
                        help='sweep for truncating divisions, whose value can depend on the '
                             'unit their operands are written in')
    args = parser.parse_args(argv)

    if args.counts:
        rows = sweep_counts()
        bare = [r for r in rows if r[3] == 'bare']
        for path, line, text, verdict in rows:
            if verdict == 'bare' or args.strict:
                print('%-44s:%-5d %-8s %s' % (path, line, verdict, text))
        print('')
        print('%d division(s) turned into a whole number: %d bare, %d rounded, %d with slack, '
              '%d allowed'
              % (len(rows), len(bare),
                 sum(1 for r in rows if r[3] == 'round'),
                 sum(1 for r in rows if r[3] == 'slack'),
                 sum(1 for r in rows if r[3] == 'allowed')))
        return 1 if bare else 0

    if args.undefined:
        rows = sweep_undefined()
        for path, line, symbol in rows:
            print('%-52s:%-5d %s' % (path, line, symbol))
        print('')
        print('%d undefined reference(s) across %d directory(ies)'
              % (len(rows), len(SWEEP_DIRS)))
        return 1 if rows else 0

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
