"""The two refusal-reading tools, and the unit boundaries they sit on.

**Structural, because neither imports without FreeCAD** -- the constraint the other refusal tests
work under. A value crossing a unit boundary unconverted is visible in the text of the call, which
is what these read.

**What they guard, found 2026-11-13.** `refused_wall` could not be imported at all: IP-FC-163
renamed `BREAK_Z`, `HEALTHY_MM` and `SILENT_MM` in `sever_doses` and the import was not moved, so
nothing in it had run since. Behind that import were three more defects that its failure had been
hiding -- the wall thickness `t` computed in millimeters and handed to `thickness_at` as `t_m`,
the command-line station in millimeters handed over as `z_m`, and the incumbent's meters printed
under a "mm" label. `refused_surface` is new and composes `cavity`'s own exterior rather than
rebuilding it, which is the property the second class checks.
"""
import io
import os

_PORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'src', 'Fuselage', 'freecad')


def _source(name):
    with io.open(os.path.join(_PORT, name), 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


class TestRefusedWallImportsNamesThatExist(object):

    def test_every_name_it_imports_from_sever_doses_is_defined_there(self):
        """The defect that hid the others. Checked against the definitions, not a list, so the
        next rename fails here instead of at the first run of the tool."""
        import re
        wall = _source('refused_wall.py')
        block = re.search(r'from sever_doses import \((.*?)\)', wall, re.S)
        assert block is not None, 'the import moved; this test must move with it'
        names = [n.strip() for n in re.sub(r'#.*', '', block.group(1)).split(',') if n.strip()]
        doses = _source('sever_doses.py')
        for name in names:
            defined = (re.search(r'^%s\s*=' % re.escape(name), doses, re.M)
                       or re.search(r'^def %s\(' % re.escape(name), doses, re.M))
            assert defined, '%s is imported from sever_doses but not defined there' % name

    def test_the_old_unit_less_names_are_gone(self):
        wall = _source('refused_wall.py')
        for old in ('BREAK_Z,', 'HEALTHY_MM', 'SILENT_MM'):
            assert old not in wall, old


class TestRefusedWallHandsSiToThicknessAt(object):

    def test_the_wall_thickness_is_converted_to_meters(self):
        wall = _source('refused_wall.py')
        assert "t_m = si.m(float(params.get('cowl_n_perimeters'))" in wall
        assert ', t)' not in wall, 'a bare millimeter t is still being passed somewhere'

    def test_the_command_line_station_is_converted_before_thickness_at(self):
        """`local_scan` already converted the same value four lines up; this call did not."""
        assert 'thickness_at(wall, si.m(z_of_interest), t_m)' in _source('refused_wall.py')

    def test_the_break_station_is_the_meter_constant(self):
        assert 'thickness_at(wall, BREAK_Z_M, t_m)' in _source('refused_wall.py')

    def test_the_incumbent_is_printed_in_the_unit_its_label_claims(self):
        wall = _source('refused_wall.py')
        assert "si.mm(inc.get('worst_low', float('nan')))" in wall


class TestSeverDosesPrintsTheIncumbentInMillimeters(object):

    def test_the_at_break_column_matches_its_banner(self):
        """The banner states the healthy reading in millimeters; the column printed meters."""
        assert "at_break = '%.6f' % si.mm(inc.get('worst_low', float('nan')))" \
            in _source('sever_doses.py')


class TestRefusedSurfaceComposesTheConstructionsOwnExterior(object):
    """Four earlier comparisons each produced a plausible wrong number by rebuilding an operand
    instead of using the construction's (`cowl_interior_surface.md` section 6.1). This tool is
    only worth running if it does not do that."""

    def test_it_uses_the_production_slicer_and_arc_functions(self):
        src = _source('refused_surface.py')
        for call in ('ci.cell_boundary_planes(body)', 'ci._slice_wires(self.body, z_m)',
                     'ci.open_arc(wires[0], self.planes)',
                     'ci.open_contour(arc, self.n_check, flip)[1]',
                     'ci.check_samples(widest_m)', 'ci._slice_wires(face, z_m)',
                     'ci.open_contour(cut[0], exterior.n_check)'):
            assert call in src, call

    def test_it_never_sections_with_the_generic_slicer(self):
        """`Shape.slice` is what the first, wrong version of this measurement used."""
        assert '.slice(' not in _source('refused_surface.py')

    def test_it_skips_exactly_what_refine_skips(self):
        """`_refine` does not measure a section that is not one open arc. Measuring those here
        would report a worst the refusal could never have seen."""
        src = _source('refused_surface.py')
        assert 'cut = [w for w in sliced if not w.isClosed()]' in src
        assert 'if len(cut) != 1:' in src
        refine = _source('cowl_interior.py')
        assert 'cut = [w for w in sliced if not w.isClosed()]' in refine
        assert 'if len(cut) != 1:' in refine

    def test_the_thickness_it_compares_against_is_meters(self):
        assert "t_m = si.m(float(params.get('cowl_n_perimeters'))" in _source('refused_surface.py')
