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


class TestTheInventorySeesATableAndAComputedConstant:
    """The blind spot that let 34 constants sit unclassified, and the `record` unit that
    followed from closing it.

    `_numeric` read a plain number or a tuple's first member and nothing else, so a table keyed
    by label and a constant whose value is an expression were both invisible to the whole
    inventory -- `cowl.REFERENCE` alone holds 51 numbers. A blind inventory cannot support a
    claim that the port is SI, which is why this is tested rather than left to the next audit.
    """

    def test_a_table_keyed_by_label_is_in_the_inventory(self, tmp_path):
        """A `(label, figure, ...)` table carries a unit and must be classifiable."""
        write(tmp_path, 'm.py',
              "REFS = [('web_inner', 5700.1741175, (-40.9, -40.9)),\n"
              "        ('other', 1265.7236228, (-33.8, -33.8))]\n")
        got = ur.constants(str(tmp_path / 'm.py'))
        assert got == [('REFS', 1, 5700.1741175)], 'the first figure identifies the table'

    def test_a_dict_table_is_in_the_inventory(self, tmp_path):
        write(tmp_path, 'm.py', "REFS = {'a': (8959.34, (-50.0, -50.0), 6.0e-5)}\n")
        assert [n for n, _l, _v in ur.constants(str(tmp_path / 'm.py'))] == ['REFS']

    def test_a_computed_constant_is_in_the_inventory(self, tmp_path):
        """`SQ2 = 2 ** 0.5` holds literals, so it has something to classify."""
        write(tmp_path, 'm.py', 'SQ2 = 2 ** 0.5\n')
        assert ur.constants(str(tmp_path / 'm.py')) == [('SQ2', 1, 2)]

    def test_a_constant_with_no_number_in_it_stays_out(self, tmp_path):
        """There is nothing in it to carry a unit."""
        write(tmp_path, 'm.py', "MODE = 'tail'\nNAMES = ['a', 'b']\n")
        assert ur.constants(str(tmp_path / 'm.py')) == []

    def test_a_record_needs_no_suffix(self, tmp_path):
        """Its members carry the units, so the table's own name cannot and need not."""
        write(tmp_path, 'm.py', "REFS = {'a': (1.0, (2.0, 3.0))}\n")
        manifest = {'regimes': {}, 'constants': {
            'm.REFS': {'unit': 'record', 'reason': 'rows are Ref2D(area_m2, bbox_m)'}}}
        findings, _summary = ur.audit(str(tmp_path), manifest)
        assert findings == []

    def test_a_record_with_no_reason_is_reported(self, tmp_path):
        """The reason is where the field units are stated, so it is the whole guarantee."""
        write(tmp_path, 'm.py', "REFS = {'a': (1.0, (2.0, 3.0))}\n")
        manifest = {'regimes': {}, 'constants': {'m.REFS': {'unit': 'record'}}}
        findings, _summary = ur.audit(str(tmp_path), manifest)
        assert [f.kind for f in findings] == ['no-reason']

    def test_a_constant_may_declare_its_own_regime(self, tmp_path):
        """A sheet alias table is millimeters inside an otherwise-SI module. Declaring the whole
        module `boundary` to excuse one table would exempt everything around it."""
        write(tmp_path, 'm.py', "PARAMS = [('cut_len', 6.0)]\nWALL_M = 0.0006\n")
        manifest = {'regimes': {}, 'constants': {
            'm.PARAMS': {'unit': 'mm', 'regime': 'boundary', 'reason': 'a parameter sheet'},
            'm.WALL_M': {'unit': 'm'}}}
        findings, summary = ur.audit(str(tmp_path), manifest)
        assert findings == []
        assert summary['pending'] == 0, 'a declared boundary is not pending work'

    def test_a_constant_regime_override_does_not_leak_to_its_neighbors(self, tmp_path):
        """The override is per constant. The module stays SI, so a *second* millimeter constant
        with no override of its own is still a finding."""
        write(tmp_path, 'm.py', "PARAMS = [('cut_len', 6.0)]\nSTRAY = 0.6\n")
        manifest = {'regimes': {}, 'constants': {
            'm.PARAMS': {'unit': 'mm', 'regime': 'boundary', 'reason': 'a parameter sheet'},
            'm.STRAY': {'unit': 'mm'}}}
        findings, summary = ur.audit(str(tmp_path), manifest)
        assert [(f.name, f.kind) for f in findings] == [('STRAY', 'stored-mm')]
        assert summary['pending'] == 1


class TestTheRenameSweepFindsWhatATestRunDoesNot:
    """`--undefined`. A rename leaves a reference that raises only on the branch reaching it,
    and an attribute read through an import alias is invisible to any scope check.

    Measured 2026-11-01 on the real conversion: 7 bare names in `cowl_interior`, one inside a
    refusal message no passing build executes, and 58 `module.NAME` references across the check
    scripts and this tier.
    """

    def test_a_name_nothing_defines_is_reported(self, tmp_path):
        write(tmp_path, 'm.py', 'A_M = 1.0\n\n\ndef f():\n    return A\n')
        assert ur.undefined_names(str(tmp_path / 'm.py')) == [(5, 'A')]

    def test_a_local_shadowing_nothing_is_not_reported(self, tmp_path):
        write(tmp_path, 'm.py', 'def f():\n    x = 1.0\n    return x\n')
        assert ur.undefined_names(str(tmp_path / 'm.py')) == []

    def test_a_comprehension_variable_is_bound(self, tmp_path):
        write(tmp_path, 'm.py', 'def f(rows):\n    return [z for z, _p in rows]\n')
        assert ur.undefined_names(str(tmp_path / 'm.py')) == []

    def test_an_except_alias_is_bound(self, tmp_path):
        write(tmp_path, 'm.py',
              'def f():\n    try:\n        pass\n'
              '    except ValueError as exc:\n        return exc\n')
        assert ur.undefined_names(str(tmp_path / 'm.py')) == []

    def test_a_name_defined_only_in_a_sibling_function_is_reported(self, tmp_path):
        """The scope walk is the point: a flat check would call this defined."""
        write(tmp_path, 'm.py',
              'def a():\n    helper = 1\n    return helper\n\n\n'
              'def b():\n    return helper\n')
        assert ur.undefined_names(str(tmp_path / 'm.py')) == [(7, 'helper')]

    def test_an_ambient_vendor_name_is_not_reported(self, tmp_path):
        """`App` and `Part` arrive from FreeCAD's own interpreter in the check scripts."""
        write(tmp_path, 'm.py', 'def f():\n    return App.Vector(0, 0, 1)\n')
        assert ur.undefined_names(str(tmp_path / 'm.py')) == []

    def test_an_attribute_a_module_does_not_define_is_reported(self, tmp_path):
        """`ci.WALL_TOL` after the rename: an `ast.Attribute`, invisible to a scope check."""
        write(tmp_path, 'other.py', 'WALL_TOL_M = 1.0e-5\n')
        write(tmp_path, 'm.py', 'import other\n\n\ndef f():\n    return other.WALL_TOL\n')
        surface = {'other': ur._public_names(str(tmp_path / 'other.py'))}
        assert ur.missing_attributes(str(tmp_path / 'm.py'), surface) == [(5, 'other.WALL_TOL')]

    def test_the_renamed_attribute_is_accepted(self, tmp_path):
        write(tmp_path, 'other.py', 'WALL_TOL_M = 1.0e-5\n')
        write(tmp_path, 'm.py',
              'import other\n\n\ndef f():\n    return other.WALL_TOL_M\n')
        surface = {'other': ur._public_names(str(tmp_path / 'other.py'))}
        assert ur.missing_attributes(str(tmp_path / 'm.py'), surface) == []

    def test_an_import_alias_is_followed(self, tmp_path):
        """`import cowl_interior as ci` is how the port spells it everywhere."""
        write(tmp_path, 'other.py', 'WALL_TOL_M = 1.0e-5\n')
        write(tmp_path, 'm.py', 'import other as o\n\n\ndef f():\n    return o.WALL_TOL\n')
        surface = {'other': ur._public_names(str(tmp_path / 'other.py'))}
        assert ur.missing_attributes(str(tmp_path / 'm.py'), surface) == [(5, 'other.WALL_TOL')]

    def test_a_module_dunder_is_not_a_missing_attribute(self, tmp_path):
        """Every module has `__file__` whether or not a statement writes it."""
        write(tmp_path, 'other.py', 'A_M = 1.0\n')
        write(tmp_path, 'm.py', 'import other\n\n\ndef f():\n    return other.__file__\n')
        surface = {'other': ur._public_names(str(tmp_path / 'other.py'))}
        assert ur.missing_attributes(str(tmp_path / 'm.py'), surface) == []

    def test_an_attribute_installed_at_run_time_is_defined(self, tmp_path):
        """`geometry_branches` swaps `corner_common.max` for a tracing wrapper and restores it;
        `test_branching_dimensions` then asserts the restore happened. Neither is a defect."""
        write(tmp_path, 'other.py', 'A_M = 1.0\n')
        write(tmp_path, 'm.py',
              'import other\n\n\ndef f():\n    other.max = max\n    return other.max\n')
        surface = {'other': ur._public_names(str(tmp_path / 'other.py'))}
        assert ur.missing_attributes(str(tmp_path / 'm.py'), surface) == []

    def test_an_installed_attribute_is_shared_across_the_sweep(self, tmp_path):
        """The file that installs one and the file that reads it are usually not the same."""
        write(tmp_path, 'other.py', 'A_M = 1.0\n')
        write(tmp_path, 'm.py', 'import other\n\n\ndef f():\n    return other.max\n')
        surface = {'other': ur._public_names(str(tmp_path / 'other.py'))}
        assert ur.missing_attributes(str(tmp_path / 'm.py'), surface) == [(5, 'other.max')]
        got = ur.missing_attributes(str(tmp_path / 'm.py'), surface, installed={'other.max'})
        assert got == []

    def test_the_real_tree_has_no_dangling_reference(self):
        """The condition the conversion drove to zero, and the one a later rename breaks."""
        rows = ur.sweep_undefined()
        assert rows == [], 'dangling reference(s): %s' % rows[:8]


class TestTheCountSweepFindsAUnitDependentCount:
    r"""`int(span / step)` is not unit-invariant, and a regex cannot be trusted to find it.

    The sweep that first looked for this class was written as `int\([^)]*/[^)]*` and missed two
    of the four sites in `cowl_interior`, because `int(si.length_m(arc) / SAMPLE_SPACING_M)` has
    a closing parenthesis before the divide. Both were found by reading. These cases pin the
    expression-tree version against that blind spot and against the distinctions that keep its
    report honest.
    """

    def test_a_bare_truncating_division_is_a_finding(self, tmp_path):
        write(tmp_path, 'm.py', 'def f(span_m, step_m):\n    return int(span_m / step_m)\n')
        rows = ur.truncating_counts(str(tmp_path / 'm.py'))
        assert [(line, verdict) for line, _t, verdict in rows] == [(2, 'bare')]

    def test_a_call_before_the_divide_does_not_hide_it(self, tmp_path):
        """The exact shape the regex could not see."""
        write(tmp_path, 'm.py',
              'def f(wire, step_m):\n    return int(length_m(wire) / step_m)\n')
        rows = ur.truncating_counts(str(tmp_path / 'm.py'))
        assert [verdict for _l, _t, verdict in rows] == ['bare']

    def test_a_slack_term_clears_it(self, tmp_path):
        write(tmp_path, 'm.py',
              'STEP_SLACK = 1e-09\n\n\ndef f(span, step):\n'
              '    return int(span / step + STEP_SLACK)\n')
        rows = ur.truncating_counts(str(tmp_path / 'm.py'))
        assert [verdict for _l, _t, verdict in rows] == ['slack']

    def test_rounding_is_reported_but_is_not_a_finding(self, tmp_path):
        """`round`'s boundaries are the half-integers, which a ratio of lengths does not sit on."""
        write(tmp_path, 'm.py', 'def f(a_m, b_m):\n    return round(a_m / b_m)\n')
        rows = ur.truncating_counts(str(tmp_path / 'm.py'))
        assert [verdict for _l, _t, verdict in rows] == ['round']

    def test_an_int_around_a_round_is_classified_by_the_round(self, tmp_path):
        """`int(round(x))` is one site and its fragility is `round`'s, not `int`'s."""
        write(tmp_path, 'm.py', 'def f(a_m, b_m):\n    return int(round(a_m / b_m))\n')
        rows = ur.truncating_counts(str(tmp_path / 'm.py'))
        assert len(rows) == 1, 'the inner call is not a second site: %s' % (rows,)
        assert rows[0][2] == 'round'

    def test_integer_arithmetic_on_counts_is_not_a_unit_question(self, tmp_path):
        """`//` is ordinary integer division far more often than it is a length over a length."""
        write(tmp_path, 'm.py',
              'def f(pts, n, available, per_worker):\n'
              '    a = len(pts) // 2\n'
              '    b = n // 8\n'
              '    c = available // (per_worker * 1024 * 1024)\n'
              '    return a, b, c\n')
        assert ur.truncating_counts(str(tmp_path / 'm.py')) == []

    def test_a_floor_division_of_two_lengths_is_a_finding(self, tmp_path):
        write(tmp_path, 'm.py',
              'def f(height):\n    return int(band_depth_mm() // row_pitch_mm(height))\n')
        rows = ur.truncating_counts(str(tmp_path / 'm.py'))
        assert [verdict for _l, _t, verdict in rows] == ['bare']

    def test_the_allowlist_needs_the_expression_not_the_line(self, tmp_path, monkeypatch):
        """A line number moves with every edit above it; the expression does not."""
        write(tmp_path, 'm.py',
              '# a comment that moves the line\ndef f(a_m, b_m):\n    return int(a_m / b_m)\n')
        monkeypatch.setitem(ur.COUNT_ALLOWED, 'm', {'int(a_m / b_m)': 'a stated reason'})
        rows = ur.truncating_counts(str(tmp_path / 'm.py'))
        assert [verdict for _l, _t, verdict in rows] == ['allowed']

    def test_every_allowlist_entry_states_a_reason(self):
        """An allowlist whose entries carry no reason is a suppression list."""
        for module, entries in ur.COUNT_ALLOWED.items():
            for expression, reason in entries.items():
                assert isinstance(reason, str) and len(reason) > 20, \
                    '%s: %s has no stated reason' % (module, expression)

    def test_the_real_tree_has_no_bare_unit_dependent_count(self):
        """The condition this was driven to, and the one a later edit breaks."""
        bare = [r for r in ur.sweep_counts() if r[3] == 'bare']
        assert bare == [], 'bare truncating division(s): %s' % (bare[:6],)
