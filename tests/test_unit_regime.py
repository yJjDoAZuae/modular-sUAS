"""IP-FC-158/161: regression for `tools/unit_regime.py` and the manifest it enforces.

The tool exists because a documented unit standard that only a reader enforces drifted for
three months and 125 completed work items without anything noticing. A check meant to stop that
has to be trusted, which means two separate things get tested here: that the classifier reports
what it should on geometry it is handed (the parser and the rules), and that the manifest
actually describes the tree as it stands (the inventory).

The second is the one that rots. A manifest is only as good as its agreement with the code, so
the test that matters most is simply that running the tool over the real port produces no
unclassified constant -- which is the condition that makes adding a constant a decision about
its unit rather than an omission.
"""
import io
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
TOOLS = os.path.join(ROOT, 'src', 'Fuselage', 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import unit_regime as ur


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return str(path)


class TestTheParserFindsWhatAConstantIs:
    """`constants` has to see every form the port actually writes, and no more."""

    def test_a_plain_float_is_a_constant(self, tmp_path):
        write(tmp_path, 'm.py', 'WALL_TOL_M = 1.0e-5\n')
        assert ur.constants(str(tmp_path / 'm.py')) == [('WALL_TOL_M', 1, 1.0e-5)]

    def test_a_negative_number_is_a_constant(self, tmp_path):
        """`ast` keeps the minus as its own node, so a station at a negative z is easy to miss."""
        write(tmp_path, 'm.py', 'HISTORIC_Z_M = -0.2839951339\n')
        assert ur.constants(str(tmp_path / 'm.py')) == [('HISTORIC_Z_M', 1, -0.2839951339)]

    def test_a_tuple_reports_its_first_member(self, tmp_path):
        """A ladder carries one unit for the whole tuple, so one entry classifies it."""
        write(tmp_path, 'm.py', 'LADDER_MM = (1.0e-5, 1.0e-4, 1.0e-3)\n')
        assert ur.constants(str(tmp_path / 'm.py')) == [('LADDER_MM', 1, 1.0e-5)]

    def test_a_lower_case_name_is_not_a_module_constant(self, tmp_path):
        write(tmp_path, 'm.py', 'wall_tol = 1.0e-5\n')
        assert ur.constants(str(tmp_path / 'm.py')) == []

    def test_a_constant_inside_a_function_is_not_in_the_inventory(self, tmp_path):
        """The inventory is the declared surface; a local is governed but not listed."""
        write(tmp_path, 'm.py', 'def f():\n    LOCAL_M = 1.0\n    return LOCAL_M\n')
        assert ur.constants(str(tmp_path / 'm.py')) == []

    def test_a_derived_value_is_not_a_literal(self, tmp_path):
        """`MM2_PER_M2 = MM_PER_M * MM_PER_M` carries no literal to classify."""
        write(tmp_path, 'm.py', 'A = 2.0\nB = A * A\n')
        assert [name for name, _l, _v in ur.constants(str(tmp_path / 'm.py'))] == ['A']

    def test_a_boolean_is_not_a_number(self, tmp_path):
        """`True` is an int subclass, which would otherwise arrive as a dimensionless 1."""
        write(tmp_path, 'm.py', 'KEEP = True\n')
        assert ur.constants(str(tmp_path / 'm.py')) == []


class TestTheAuditReportsTheRightProblem:
    """Each rule gets a case that fires it and the manifest entry that silences it."""

    def manifest(self, constants, regimes=None):
        return {'regimes': regimes or {}, 'constants': constants}

    def test_an_unclassified_constant_is_reported(self, tmp_path):
        write(tmp_path, 'geo.py', 'WALL_TOL_M = 1.0e-5\n')
        findings, summary = ur.audit(str(tmp_path), self.manifest({}))
        assert [f.kind for f in findings] == ['unclassified']
        assert summary['constants'] == 1

    def test_a_classified_constant_is_not_reported(self, tmp_path):
        write(tmp_path, 'geo.py', 'WALL_TOL_M = 1.0e-5\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo.WALL_TOL_M': {'unit': 'm'}}))
        assert findings == []

    def test_a_millimeter_value_in_a_library_module_is_pending(self, tmp_path):
        """The finding the whole repair drives to zero."""
        write(tmp_path, 'geo.py', 'WALL_TOL = 0.01\n')
        findings, summary = ur.audit(str(tmp_path),
                                     self.manifest({'geo.WALL_TOL': {'unit': 'mm'}}))
        assert [f.kind for f in findings] == ['stored-mm']
        assert summary['pending'] == 1

    def test_the_same_value_at_a_declared_boundary_is_allowed(self, tmp_path):
        write(tmp_path, 'geo.py', 'FUZZ_MM = 1.0e-5\n')
        findings, summary = ur.audit(
            str(tmp_path),
            self.manifest({'geo.FUZZ_MM': {'unit': 'mm', 'reason': 'an OCC fuzz argument'}},
                          regimes={'geo': 'boundary'}))
        assert findings == []
        assert summary['pending'] == 0

    def test_a_boundary_value_with_no_reason_is_reported(self, tmp_path):
        """An exemption without a reason is drift with a manifest entry on top of it."""
        write(tmp_path, 'geo.py', 'FUZZ_MM = 1.0e-5\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo.FUZZ_MM': {'unit': 'mm'}},
                                              regimes={'geo': 'boundary'}))
        assert [f.kind for f in findings] == ['no-reason']

    def test_an_si_length_must_say_so_in_its_name(self, tmp_path):
        write(tmp_path, 'geo.py', 'WALL_TOL = 1.0e-5\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo.WALL_TOL': {'unit': 'm'}}))
        assert [f.kind for f in findings] == ['unnamed-unit']

    @pytest.mark.parametrize('unit,suffix', [('m', '_M'), ('m2', '_M2'),
                                             ('m3', '_M3'), ('rad', '_RAD')])
    def test_each_dimensional_unit_has_its_own_suffix(self, tmp_path, unit, suffix):
        write(tmp_path, 'geo.py', 'VALUE%s = 1.0\n' % suffix)
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo.VALUE%s' % suffix: {'unit': unit}}))
        assert findings == []

    def test_a_dimensionless_constant_needs_no_suffix(self, tmp_path):
        write(tmp_path, 'geo.py', 'RIB_FACETS = 48\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo.RIB_FACETS': {'unit': 'none'}}))
        assert findings == []

    def test_an_unknown_unit_is_reported(self, tmp_path):
        write(tmp_path, 'geo.py', 'VALUE = 1.0\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo.VALUE': {'unit': 'furlong'}}))
        assert [f.kind for f in findings] == ['bad-unit']

    def test_an_unknown_regime_is_reported(self, tmp_path):
        """A typo in a regime must not silently grant an exemption."""
        write(tmp_path, 'geo.py', 'VALUE_M = 1.0\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo.VALUE_M': {'unit': 'm'}},
                                              regimes={'geo': 'kernel'}))
        assert [f.kind for f in findings] == ['regime']

    def test_a_manifest_entry_with_no_constant_is_reported(self, tmp_path):
        """A deleted constant leaves an entry that would otherwise excuse a new one."""
        write(tmp_path, 'geo.py', '\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo.GONE_M': {'unit': 'm'}}))
        assert [f.kind for f in findings] == ['stale']

    def test_check_scripts_are_not_inventoried(self, tmp_path):
        """`check_*` are entry points, not library code."""
        write(tmp_path, 'check_geo.py', 'TOL = 1e-9\n')
        findings, summary = ur.audit(str(tmp_path), self.manifest({}))
        assert findings == []
        assert summary['constants'] == 0


class TestTheManifestDescribesTheRealTree:
    """The inventory half: these run against the port itself."""

    def test_every_constant_in_the_port_is_classified(self):
        findings, _s = ur.audit()
        unclassified = [str(f) for f in findings if f.kind == 'unclassified']
        assert unclassified == []

    def test_no_manifest_entry_names_a_constant_that_is_gone(self):
        findings, _s = ur.audit()
        assert [str(f) for f in findings if f.kind == 'stale'] == []

    def test_every_declared_regime_is_a_known_one(self):
        findings, _s = ur.audit()
        assert [str(f) for f in findings if f.kind == 'regime'] == []

    def test_every_millimeter_exemption_gives_a_reason(self):
        findings, _s = ur.audit()
        assert [str(f) for f in findings if f.kind == 'no-reason'] == []

    def test_no_library_module_stores_a_millimeter_value(self):
        """The repair's own acceptance criterion, and it holds as of IP-FC-158."""
        findings, summary = ur.audit()
        stored = [str(f) for f in findings if f.kind == 'stored-mm']
        assert stored == []
        assert summary['pending'] == 0

    def test_the_manifest_is_valid_json_with_the_two_sections(self):
        manifest = ur.load_manifest()
        assert set(manifest) >= {'regimes', 'constants'}
        assert manifest['constants'], 'the manifest is empty'

    def test_the_exit_code_is_zero_only_when_nothing_is_unclassified(self):
        """`main` is what a hook or a CI step would call, so its contract is tested too."""
        assert ur.main([]) == 0


class TestTheInlineClassifierSeparatesAFactorFromADimension:
    """The rule that makes `2.0` readable: a dimension is assigned, added or passed; a factor
    is what you divide or scale *by*. Both spellings occur in this port and only the syntax
    tells them apart."""

    def kinds(self, tmp_path, body):
        write(tmp_path, 'm.py', 'def f(a, b):\n' + body + '\n')
        return [(row[1], row[3]) for row in ur.inline_literals(str(tmp_path / 'm.py'))]

    def test_a_divisor_is_a_factor(self, tmp_path):
        assert self.kinds(tmp_path, '    return abs(a) / 2.0') == [(2.0, 'structural')]

    def test_an_exponent_is_a_factor(self, tmp_path):
        assert self.kinds(tmp_path, '    return a ** 2') == [(2, 'structural')]

    def test_a_right_hand_scale_is_a_factor(self, tmp_path):
        assert self.kinds(tmp_path, '    return a * 0.30') == [(0.30, 'structural')]

    def test_a_left_hand_dimension_scaled_by_a_multiplier_is_a_dimension(self, tmp_path):
        """`0.010 * U` is 10 mm scaled by U. Excusing this is the failure mode to avoid."""
        assert self.kinds(tmp_path, '    return 0.010 * a') == [(0.010, 'dimension')]

    def test_a_bare_coordinate_is_a_dimension(self, tmp_path):
        got = self.kinds(tmp_path, '    return (-13.4, 0.9375)')
        assert got == [(13.4, 'dimension'), (0.9375, 'dimension')]

    def test_a_default_argument_is_named_and_not_bare(self, tmp_path):
        write(tmp_path, 'm.py', 'def f(tol=1.0e-6):\n    return tol\n')
        rows = ur.inline_literals(str(tmp_path / 'm.py'))
        assert [row[3] for row in rows] == ['default']

    def test_an_index_is_structural(self, tmp_path):
        assert self.kinds(tmp_path, '    return a[11]') == [(11, 'structural')]

    def test_an_angle_in_degrees_is_its_own_kind(self, tmp_path):
        got = self.kinds(tmp_path, '    return math.radians(52.0)')
        assert got == [(52.0, 'angle')]

    def test_a_relative_tolerance_is_not_a_dimension(self, tmp_path):
        """`abs(d) / ref > 1e-3` is dimensionless, and only the division says so."""
        got = self.kinds(tmp_path, '    return abs(a) / ref > 1e-3')
        assert ('relative' in [kind for _v, kind in got]
                or 'structural' in [kind for _v, kind in got])

    def test_a_module_level_constant_is_not_an_inline_literal(self, tmp_path):
        """The two inventories must not double-count the same number."""
        write(tmp_path, 'm.py', 'WALL_TOL_M = 1.0e-5\n')
        assert ur.inline_literals(str(tmp_path / 'm.py')) == []


class TestTheInlineCeilingRatchets:
    """A count that may fall and may not rise. It is the guarantee the classifier cannot give."""

    def manifest(self, inline):
        return {'regimes': {}, 'constants': {}, 'inline': inline}

    def test_a_module_over_its_ceiling_is_reported(self, tmp_path):
        write(tmp_path, 'geo.py', 'def f():\n    return (13.4, 11.4)\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo': {'allowed': 1, 'reason': 'legacy'}}))
        assert [f.kind for f in findings] == ['inline-dimension']

    def test_a_module_at_its_ceiling_is_quiet(self, tmp_path):
        write(tmp_path, 'geo.py', 'def f():\n    return (13.4, 11.4)\n')
        findings, summary = ur.audit(
            str(tmp_path), self.manifest({'geo': {'allowed': 2, 'reason': 'legacy'}}))
        assert findings == []
        assert summary['inline_dimensions'] == 2

    def test_a_module_under_its_ceiling_is_reported_so_the_ceiling_drops(self, tmp_path):
        """Otherwise a converted module keeps headroom for a new magic number."""
        write(tmp_path, 'geo.py', 'def f():\n    return 13.4\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'geo': {'allowed': 5, 'reason': 'legacy'}}))
        assert [f.kind for f in findings] == ['inline-ceiling-stale']

    def test_a_module_with_no_entry_has_a_ceiling_of_zero(self, tmp_path):
        """A new module carrying a bare dimension is reported without anyone adding a rule."""
        write(tmp_path, 'geo.py', 'def f():\n    return 13.4\n')
        findings, _s = ur.audit(str(tmp_path), self.manifest({}))
        assert [f.kind for f in findings] == ['inline-dimension']

    def test_a_ceiling_for_a_module_that_is_gone_is_reported(self, tmp_path):
        write(tmp_path, 'geo.py', '\n')
        findings, _s = ur.audit(str(tmp_path),
                                self.manifest({'other': {'allowed': 1, 'reason': 'x'}}))
        assert [f.kind for f in findings] == ['inline-ceiling-stale']

    def test_the_real_tree_is_within_its_ceilings(self):
        findings, _s = ur.audit()
        over = [str(f) for f in findings if f.kind == 'inline-dimension']
        assert over == []

    def test_no_ceiling_in_the_real_tree_is_stale(self):
        findings, _s = ur.audit()
        assert [str(f) for f in findings if f.kind == 'inline-ceiling-stale'] == []

    def test_every_ceiling_gives_a_reason(self):
        manifest = ur.load_manifest()
        missing = [module for module, entry in manifest.get('inline', {}).items()
                   if not entry.get('reason')]
        assert missing == []


class TestTheToolSaysWhatItCannotSee:
    """An instrument's limits belong in its own documentation, not in a reader's memory."""

    def test_the_docstring_records_the_two_remaining_blind_spots(self):
        text = io.open(os.path.join(TOOLS, 'unit_regime.py'), encoding='utf-8').read()
        head = text.split('"""')[1].lower()
        assert 'run time' in head, 'it cannot see a value\'s unit at run time'
        assert 'heuristic' in head, 'the inline classifier is a heuristic and must say so'
