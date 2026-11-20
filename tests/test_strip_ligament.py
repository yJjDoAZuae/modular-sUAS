"""`strip_ligament` measures the operands the build used, never a rebuild that differs from them.

The tool runs only under `freecadcmd`, so these tests read its source. Each pins one way it could
quietly measure the wrong thing: a fused rib tool assembled differently from `cavity`'s, a
containment test at a region's center of mass (which can lie outside the region), or a section
comparison whose booleans fail silently with nothing to show it.
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREECAD = os.path.join(ROOT, 'src', 'Fuselage', 'freecad')


def _read(name):
    with io.open(os.path.join(FREECAD, name), 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


FUSE_LINE = "ribs[0] if len(ribs) == 1 else ribs[0].fuse(ribs[1:]).removeSplitter()"


class TestTheRibToolIsTheBuildsOwn(object):

    def test_cavity_still_fuses_this_way(self):
        assert 'tool = ' + FUSE_LINE in _read('cowl_interior.py')

    def test_the_tool_is_fused_the_same_way(self):
        assert 'fused = ' + FUSE_LINE in _read('strip_ligament.py')

    def test_the_ribs_come_from_the_production_dilation(self):
        src = _read('strip_ligament.py')
        assert 'ci.dilated_notches(notch_compound(tools), t_m)' in src


class TestContainmentIsTestedInsideTheRegion(object):

    def test_the_point_tested_is_an_interior_point_not_the_center(self):
        src = _read('strip_ligament.py')
        assert "p = App.Vector(reg['inside_mm'][0], reg['inside_mm'][1], row['z_mm'])" in src
        assert "p = App.Vector(reg['center_mm']" not in src


class TestASilentBooleanIsSeen(object):

    def test_every_station_reports_its_accounting_residue(self):
        src = _read('strip_ligament.py')
        assert "unaccounted = (h_cell.Area - d.Area) - (removed_mm2 - added_mm2)" in src
        assert "'unaccounted_mm2': unaccounted" in src


class TestUnits(object):

    def test_the_slicer_is_handed_meters(self):
        src = _read('strip_ligament.py')
        assert 'ci._slice_wires(' in src
        assert 'si.mm(z_m))' not in src.split('def _section_face')[1].split('def ')[0]
