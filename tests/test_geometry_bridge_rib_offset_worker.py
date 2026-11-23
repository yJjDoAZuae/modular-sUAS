"""OQ-DES-CW41: the rib tool's inner offset is built in a child process, with a time limit.

`freecad/rib_offset_worker.py` hands the tool to a child `freecadcmd` and refuses when the child runs
past its limit, fails or writes nothing. These cases have exact answers: a box's inner offset is a
box `2 eps` smaller each way, and a slab thinner than `2 eps` has none. Fixtures are kernel geometry
and so millimeters; the worker's interface is SI.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from conftest import requires_freecad  # noqa: E402
from geometry_bridge.errors import remote_class  # noqa: E402

pytestmark = requires_freecad

OffsetNotBuilt = remote_class('OffsetNotBuilt', ('OffsetNotBuilt', 'Exception'))


@pytest.fixture
def worker(fc):
    return fc.module('rib_offset_worker')


class TestBoundedInnerOffset(object):

    def test_a_box_comes_back_two_eps_smaller(self, worker, Part):
        cores, report = worker.bounded_inner_offset(Part.makeBox(10.0, 4.0, 3.0), 0.0005,
                                                    cell_m=0.003)
        assert len(cores) == 1
        assert cores[0].isValid()
        assert abs(cores[0].Volume - 9.0 * 3.0 * 2.0) < 1e-6
        assert report['error'] is None
        assert report['seconds'] < report['limit_s']

    def test_one_core_per_solid_in_the_tools_order(self, worker, Part, App):
        """The second solid is too thin to have an offset, so its place holds `None`: the caller
        judges a cavity solid by solid, and a shifted list would judge it against the wrong one."""
        tool = Part.Compound([Part.makeBox(10.0, 4.0, 3.0),
                              Part.makeBox(10.0, 0.5, 3.0, App.Vector(0.0, 10.0, 0.0))])
        cores, _report = worker.bounded_inner_offset(tool, 0.0003)
        assert len(cores) == 2
        assert abs(cores[0].Volume - 9.4 * 3.4 * 2.4) < 1e-6
        assert cores[1] is None

    def test_a_child_past_its_limit_is_refused_and_says_why(self, worker, Part):
        with pytest.raises(OffsetNotBuilt) as caught:
            worker.bounded_inner_offset(Part.makeBox(10.0, 4.0, 3.0), 0.0005, limit_s=0.01)
        assert 'time limit' in str(caught.value)

    def test_the_limit_grows_with_the_cells_cut(self, worker, Part):
        box = Part.makeBox(30.0, 10.0, 10.0)
        assert worker.cells(box, 0.02) == 2
        assert worker.time_limit_s(box, 0.02) == pytest.approx(
            worker.OFFSET_START_S + worker.OFFSET_MARGIN * worker.OFFSET_CELL_S * 2)
