"""Which of `cowl_interior`'s constants a driver can override, and which are frozen at import.

**This file exists because of a null experiment that was nearly run.** IP-WTM-26 needed to sweep
`TAU` on a real build, and `freecad/seed_density.py` already sweeps `SEED_MAX`, `FIT_ARC`,
`CHECK_ARC` and their clamps by setting the module attribute and restoring it in a `finally`. Adding
`--tau` the same way would have produced a table of four `TAU` values and four identical builds, all
at 0.05, with the driver printing the value it believed it was testing: `cavity` and `shell_solid`
both declare `tau=TAU` as a **default argument**, which Python binds once when the module is
imported and never re-reads.

That failure mode has no symptom. It does not raise, the build succeeds, the numbers look plausible,
and the conclusion drawn from them is confidently wrong. The four constants the driver does sweep are
safe for the opposite reason -- each is read inside a function body at call time, `check_samples`
reading `CHECK_ARC`/`CHECK_MIN`/`CHECK_MAX` and `_seed` reading `SEED_MAX` -- and that was confirmed
empirically as well, by the achieved spacings in those sweeps moving with the override.

So the hazard is not `TAU` specifically, it is **the shape of the binding**, and the set of constants
with that shape is what this file pins. A new one appearing is not a defect; it is a constant that
has silently become un-overridable, and whoever added it should know that a driver cannot sweep it by
`setattr`.

`cowl_interior` imports FreeCAD at module scope and cannot be imported here, so this reads the source
and parses it -- the same approach `test_wall_measure_sweep.py` takes to enforce that package's
no-vendor-at-module-scope rule.

See doc/implementation/wall_thickness_measure.md and
doc/design/cowl_interior_surface.md section 6.8.3.
"""
import ast
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(_HERE, '..', 'src', 'Fuselage', 'freecad', 'cowl_interior.py')

#: Every `(function, parameter, constant)` whose default is a module-level constant, and therefore
#: **frozen when `cowl_interior` is imported**. A driver cannot sweep any of these by setting the
#: module attribute; it has to pass the value as an argument, the way `seed_density.one` passes
#: `tau`. Recorded as of 2026-10-14.
FROZEN_DEFAULTS = {
    ('smoothed', 'tol', 'REFIT_TOL'),
    ('eroded_body', 'tol', 'REFIT_TOL'),
    ('_smoothed_open', 'tol', 'REFIT_TOL'),
    ('eroded_arc', 'tol', 'REFIT_TOL'),
    ('_outward_normal', 'step', 'OUTWARD_STEP_MM'),
    ('z_extent', 'tol', 'END_INSET'),
    ('_finished_wall_gap', 'plane_tol', 'FINISHED_PLANE_TOL'),
    ('cavity', 'tau', 'TAU'),
    ('shell_solid', 'tau', 'TAU'),
}

#: The constants `freecad/seed_density.py` sweeps by `setattr`. **None of these may appear in
#: `FROZEN_DEFAULTS`**, which is the assertion that makes this file worth having: if one ever does,
#: that driver's table silently becomes a column of identical builds.
SWEPT_BY_SETATTR = ('SEED_MAX', 'FIT_ARC', 'FIT_MIN', 'FIT_MAX', 'CHECK_ARC', 'CHECK_MIN')


def _tree():
    with open(SOURCE, encoding='utf-8') as handle:
        return ast.parse(handle.read())


def _module_constants(tree):
    """Module-level `UPPER_CASE` assignments -- the things `cowl_interior` calls constants."""
    out = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    out.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper():
                out.add(node.target.id)
    return out


def _frozen_defaults(tree):
    """Every `(function, parameter, constant)` whose default is one of those constants."""
    constants = _module_constants(tree)
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        pairs = []
        if args.defaults:
            # Defaults align with the *last* n positional parameters.
            positional = args.posonlyargs + args.args if hasattr(args, 'posonlyargs') else args.args
            pairs += list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
        pairs += list(zip(args.kwonlyargs, args.kw_defaults or []))
        for arg, default in pairs:
            if isinstance(default, ast.Name) and default.id in constants:
                out.add((node.name, arg.arg, default.id))
    return out


class TestTheDetectorItself:
    """**The converse, on synthetic sources.** The assertions below pass because `_frozen_defaults`
    returns exactly the recorded set; a detector that returned nothing would be caught by the
    `gone` half of that comparison, and an empty parse by the constants check. What neither covers
    is whether a *newly added* binding would be seen at all, which is the thing the guard is for.
    """

    def _find(self, source):
        return _frozen_defaults(ast.parse(source))

    def test_a_default_bound_to_a_constant_is_found(self):
        assert self._find('TAU = 0.05\ndef f(a, tau=TAU):\n    pass\n') == {('f', 'tau', 'TAU')}

    def test_a_keyword_only_default_is_found_too(self):
        """`def f(a, *, tol=REFIT_TOL)` freezes exactly as a positional default does."""
        got = self._find('REFIT_TOL = 1e-4\ndef f(a, *, tol=REFIT_TOL):\n    pass\n')
        assert got == {('f', 'tol', 'REFIT_TOL')}

    def test_a_nested_function_is_found(self):
        """`_finished_wall_gap` and friends are module-level, but `cavity` defines closures, and a
        frozen default inside one is frozen the same way."""
        got = self._find('TAU = 0.05\ndef outer():\n    def inner(tau=TAU):\n        pass\n')
        assert got == {('inner', 'tau', 'TAU')}

    def test_a_literal_default_is_not_a_finding(self):
        """`budget=64` in `cavity` is a literal, so a caller can pass it and nothing is frozen."""
        assert self._find('def f(a, budget=64):\n    pass\n') == set()

    def test_a_constant_read_in_the_body_is_not_a_finding(self):
        """This is the safe shape, and the one `check_samples` and `_seed` use: the constant is read
        at call time, so `setattr` on the module reaches it."""
        assert self._find('CHECK_ARC = 0.2\ndef f(p):\n    return p / CHECK_ARC\n') == set()

    def test_a_lower_case_module_global_is_not_treated_as_a_constant(self):
        """Only `UPPER_CASE` names are the module's constants; a lower-case global default is not
        what this guard is about and would be noise."""
        assert self._find('scale = 2.0\ndef f(a, s=scale):\n    pass\n') == set()

    def test_defaults_align_with_the_last_parameters_not_the_first(self):
        """The alignment is the one place this detector could silently mis-attribute: `defaults`
        covers the *trailing* parameters, so a function with leading required arguments must not
        report the wrong parameter name."""
        got = self._find('TAU = 0.05\ndef f(body, notched, t, tau=TAU):\n    pass\n')
        assert got == {('f', 'tau', 'TAU')}


class TestFrozenDefaults:

    def test_the_source_parses_and_declares_constants(self):
        """A guard on the guard: if this file silently found nothing, every assertion below would
        pass for the wrong reason."""
        tree = _tree()
        constants = _module_constants(tree)
        assert 'TAU' in constants
        assert 'SEED_MAX' in constants
        assert len(constants) > 20, 'only %d constants found; the parse is wrong' % len(constants)

    def test_tau_is_a_default_argument_in_both_entry_points(self):
        """The specific fact `seed_density.NOT_OVERRIDABLE` and its `tau` parameter exist for. If
        this ever fails, `TAU` has become overridable and that note is stale."""
        found = _frozen_defaults(_tree())
        assert ('cavity', 'tau', 'TAU') in found
        assert ('shell_solid', 'tau', 'TAU') in found

    def test_no_new_constant_has_quietly_become_un_overridable(self):
        """**A new entry here is not a bug, it is a notification.** A constant bound as a default
        argument cannot be swept by setting the module attribute, and that failure is silent: the
        build succeeds, the numbers look plausible, and the sweep was a column of identical runs.
        Whoever adds one should know; update `FROZEN_DEFAULTS` and say so in the driver that cares.
        """
        found = _frozen_defaults(_tree())
        new = found - FROZEN_DEFAULTS
        gone = FROZEN_DEFAULTS - found
        assert not new, (
            'these defaults are frozen at import and cannot be overridden by setattr: %s'
            % ', '.join('%s(%s=%s)' % t for t in sorted(new)))
        assert not gone, (
            'these are no longer frozen defaults, so a note somewhere is stale: %s'
            % ', '.join('%s(%s=%s)' % t for t in sorted(gone)))

    @pytest.mark.parametrize('constant', SWEPT_BY_SETATTR)
    def test_a_constant_a_driver_sweeps_is_never_a_frozen_default(self, constant):
        """**The assertion this file is for.** `seed_density.py` sweeps these by `setattr`, so if one
        becomes a default argument its sweep stops doing anything and reports success."""
        offenders = [t for t in _frozen_defaults(_tree()) if t[2] == constant]
        assert not offenders, (
            '%s is swept by seed_density.py via setattr but is now a default argument in %s, so '
            'that sweep silently tests one value'
            % (constant, ', '.join('%s(%s=)' % (f, p) for f, p, _ in offenders)))
