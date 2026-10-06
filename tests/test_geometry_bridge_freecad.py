"""The bridge against the real vendor: named pytest cases for FreeCAD geometry.

Every assertion here is one the project could not previously make in this tier. They are also the
first real consumers of the library, so they double as its integration test: if the loopback suite
passes and this one does not, the gap is in the worker or the transport, not in the protocol.

The private helpers of `cowl_interior` are deliberately prominent. They are the functions a unit test
most wants and the ones that have never had one -- today their only coverage is a printed line inside
a 551-line `check_*.py` script.
"""
import math

import pytest

from conftest import requires_freecad
from geometry_bridge.proxy import Remote
from geometry_bridge.remote_errors import PreconditionFailed, RemoteGeometryError

pytestmark = requires_freecad


class TestTheBoundaryItself:

    def test_the_client_and_the_worker_are_different_interpreters(self, fc):
        """The whole point of the design, asserted rather than assumed."""
        import sys
        client = '.'.join(str(v) for v in sys.version_info[:3])
        assert fc.transport.python != client
        assert fc.transport.python.startswith('3.11'), 'FreeCAD 1.1 embeds 3.11'
        assert client.startswith('3.13'), 'the project chooses its own version'

    def test_freecad_is_not_importable_here_which_is_why_the_bridge_exists(self):
        with pytest.raises(ImportError):
            import Part                                                  # noqa: F401


class TestKernelGeometry:

    def test_a_boolean_gives_the_arithmetic_volume(self, Part):
        cut = Part.makeBox(10.0, 10.0, 10.0).cut(Part.makeBox(10.0, 10.0, 2.0))
        assert cut.isValid() is True
        assert cut.Volume == pytest.approx(800.0, abs=1e-9)

    def test_a_vector_behaves_like_a_vector(self, App):
        a = App.Vector(1.0, 2.0, 3.0)
        b = App.Vector(4.0, 5.0, 6.0)
        assert (a + b).x == 5.0
        assert a.dot(b) == pytest.approx(32.0)

    def test_a_bound_box_reads_through_two_hops(self, Part):
        assert Part.makeBox(3.0, 4.0, 5.0).BoundBox.ZLength == pytest.approx(5.0)

    def test_faces_iterate_in_one_round_trip(self, fc, Part):
        faces = Part.makeBox(1.0, 1.0, 1.0).Faces
        before = fc.round_trips
        n = sum(1 for _f in faces)
        assert n == 6
        assert fc.round_trips - before == 1

    def test_project_reads_every_vertex_coordinate_in_one_round_trip(self, fc, Part):
        """Per-element proxying measured 4.1 round trips per vertex; this is the fix."""
        verts = Part.makeBox(2.0, 2.0, 2.0).Vertexes
        before = fc.round_trips
        rows = verts.project('X', 'Y', 'Z')
        assert len(rows) == 8
        assert fc.round_trips - before == 1
        assert sorted(rows)[0] == (0.0, 0.0, 0.0)


class TestDocumentDrivenWork:
    """The case §4.3's `setattr` exists for, and the reason document tests belong in this tier."""

    def test_a_document_property_can_be_assigned(self, App):
        doc = App.newDocument('bridge_setattr')
        try:
            box = doc.addObject('Part::Box', 'B')
            box.Length = 12.0
            doc.recompute()
            assert box.Length.Value == pytest.approx(12.0)
            assert box.Shape.Volume == pytest.approx(12.0 * 10.0 * 10.0, rel=1e-9)
        finally:
            App.closeDocument('bridge_setattr')

    def test_a_document_object_is_never_cached_by_type(self, fc, App):
        """Two document objects report one type name and carry different run-time properties."""
        doc = App.newDocument('bridge_dynamic')
        try:
            box = doc.addObject('Part::Box', 'B')
            assert box.Length.Value > 0
            assert box.remote_type in fc.uncacheable_types, \
                'a document object must not be cached by type; got %r' % (fc.uncacheable_types,)
        finally:
            App.closeDocument('bridge_dynamic')

    def test_the_document_list_is_a_mapping_and_subscripts_as_one(self, App):
        """A prototype assumed an integer index here and raised KeyError."""
        doc = App.newDocument('bridge_mapping')
        try:
            docs = App.listDocuments()
            assert 'bridge_mapping' in docs
            assert docs['bridge_mapping'].Name == 'bridge_mapping'
        finally:
            App.closeDocument('bridge_mapping')


class TestCowlInteriorHelpers:
    """Named assertions for functions whose only coverage today is a printed line."""

    def test_check_slope_refuses_a_section_shallower_than_the_overhang_limit(self, ci):
        with pytest.raises(PreconditionFailed) as caught:
            ci._check_slope([(10.0, 0.0)], [(10.5, 0.0)], 0.0, 0.1, 35.0)
        assert caught.value.message

    def test_polyline_closest_agrees_with_distances(self, ci):
        square = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
        probes = [(2.0, 1.0), (-1.5, 1.5), (4.0, 3.0), (2.0, 7.0)]
        line = ci._Polyline(square)
        want = min(line.distances(probes))
        got = line.closest(probes)
        assert got[0] == pytest.approx(want, abs=1e-12)

    def test_thin_stations_removes_a_crowded_pair_and_keeps_both_ends(self, ci):
        floor = ci.station_floor(0.6)
        near = ci._thin_stations([-300.0, -60.0009, -60.0, -30.0, 0.0], floor)
        assert near[0] == -300.0 and near[-1] == 0.0, 'both ends must survive'
        assert all(b - a >= floor - 1e-12 for a, b in zip(near, near[1:]))

    def test_thin_stations_keeps_the_last_station_displacing_its_neighbour(self, ci):
        floor = ci.station_floor(0.6)
        ends = ci._thin_stations([0.0, 1.0, 1.0 + 0.5 * floor], floor)
        assert ends[-1] == 1.0 + 0.5 * floor
        assert all(b - a >= floor - 1e-12 for a, b in zip(ends, ends[1:]))

    def test_the_station_floor_is_the_wall_thickness(self, ci):
        assert ci.station_floor(0.6) >= 0.6 - 1e-12

    def test_wall_tol_is_five_times_tighter_than_the_fit_criterion(self, ci):
        """Pinned so a future edit cannot quietly merge the two figures again."""
        assert ci.WALL_TOL == 0.01
        assert ci.TAU == 0.05
        assert ci.WALL_TOL < ci.TAU


class TestRingContinuity:
    """`section_regions` is the ring-continuity classifier that caught the silent hole."""

    def test_a_tube_section_is_an_annulus(self, Part, App, cci):
        tube = Part.makeCylinder(10.0, 20.0).cut(Part.makeCylinder(9.4, 20.0))
        wires = [w for w in tube.slice(App.Vector(0, 0, 1), 10.0) if w.isClosed()]
        assert len(wires) == 2
        faces, counts, area = cci.section_regions(wires)
        assert faces == 1, 'one region'
        assert counts == [2], 'with exactly one hole'
        assert area == pytest.approx(math.pi * (100.0 - 9.4 ** 2), rel=1e-6)

    def test_two_separate_tubes_are_not_one_annulus(self, Part, App, cci):
        """The converse, which is the half that matters: a classifier that said annulus to
        everything would have passed the test above."""
        a = Part.makeCylinder(10.0, 20.0).cut(Part.makeCylinder(9.4, 20.0))
        b = a.copy()
        b.translate(App.Vector(40.0, 0.0, 0.0))
        pair = Part.makeCompound([a, b])
        wires = [w for w in pair.slice(App.Vector(0, 0, 1), 10.0) if w.isClosed()]
        faces, counts, _area = cci.section_regions(wires)
        assert faces == 2
        assert counts == [2, 2]

    def test_a_broken_ring_is_reported_as_arcs_not_as_an_annulus(self, Part, App, cci):
        """The actual defect shape: a slot through the wall opens the ring."""
        tube = Part.makeCylinder(10.0, 40.0).cut(Part.makeCylinder(9.4, 40.0))
        slot = Part.makeBox(4.0, 4.0, 4.0, App.Vector(7.0, -2.0, 18.0))
        part = tube.cut(slot)
        wires = [w for w in part.slice(App.Vector(0, 0, 1), 20.0) if w.isClosed()]
        faces, counts, _area = cci.section_regions(wires)
        assert counts == [1], 'a broken ring is one-wire arcs, not a face with a hole'


class TestErrorsAcrossTheRealBoundary:

    def test_a_kernel_refusal_arrives_as_the_kernels_own_class(self, Part, App):
        """Eroding a face past its own half-width is a real OCC failure, seen in this project."""
        ribbon = Part.makePolygon([App.Vector(0, 0, 0), App.Vector(100, 0, 0),
                                   App.Vector(100, 0.6, 0), App.Vector(0, 0.6, 0),
                                   App.Vector(0, 0, 0)])
        face = Part.Face(ribbon)
        with pytest.raises(RemoteGeometryError) as caught:
            face.makeOffset2D(-0.31, 0, False, False, False)
        assert caught.value.remote_name in ('CADKernelError', 'OCCError', 'RuntimeError'), \
            'got %r' % caught.value.remote_name

    def test_a_remote_traceback_names_the_failing_vendor_line(self, ci):
        try:
            ci._check_slope([(10.0, 0.0)], [(10.5, 0.0)], 0.0, 0.1, 35.0)
        except RemoteGeometryError as exc:
            assert 'cowl_interior.py' in exc.remote_traceback
            assert '_check_slope' in exc.remote_traceback
            assert 'traceback from the' in str(exc)
        else:
            pytest.fail('expected a remote failure')


class TestLifetimeAgainstTheRealVendor:

    def test_two_hundred_shapes_leave_nothing_behind(self, fc, Part):
        fc.collect()
        baseline = fc.stats()['live']
        for _ in range(200):
            shape = Part.makeCylinder(5.0, 10.0)
            assert shape.Volume > 0.0
            del shape
        fc.assert_no_leak(baseline, '200 real shapes')

    def test_a_still_referenced_shape_is_never_freed(self, fc, Part):
        """The converse test. A live object being freed corrupts a result; a leak only wastes
        memory."""
        fc.collect()
        baseline = fc.stats()['live']
        kept = Part.makeBox(2.0, 2.0, 2.0)
        for _ in range(50):
            tmp = Part.makeBox(1.0, 1.0, 1.0)
            assert tmp.Volume == pytest.approx(1.0)
            del tmp
        fc.collect()
        assert fc.stats()['live'] == baseline + 1
        assert kept.Volume == pytest.approx(8.0)

    def test_one_shape_serves_many_assertions_without_rebuilding(self, fc, Part, App, cci):
        """The access pattern that makes a 990 s cowl build testable at all."""
        tube = Part.makeCylinder(10.0, 40.0).cut(Part.makeCylinder(9.4, 40.0))
        expect = math.pi * (100.0 - 9.4 ** 2)
        for z in (5.0, 12.0, 20.0, 28.0, 35.0):
            wires = [w for w in tube.slice(App.Vector(0, 0, 1), z) if w.isClosed()]
            faces, counts, area = cci.section_regions(wires)
            assert faces == 1 and counts == [2]
            assert area == pytest.approx(expect, rel=1e-6)


class TestPerformanceBudget:
    """The measurements that justify this design over the alternatives, asserted with margin."""

    def test_a_warm_method_call_is_one_round_trip(self, fc, Part):
        box = Part.makeBox(1.0, 1.0, 1.0)
        box.isValid()
        before = fc.round_trips
        for _ in range(20):
            box.isValid()
        assert fc.round_trips - before == 20

    def test_a_method_call_allocates_no_handle(self, fc, Part):
        box = Part.makeBox(1.0, 1.0, 1.0)
        fc.collect()
        before = fc.stats()['live']
        for _ in range(50):
            box.isValid()
        fc.collect()
        assert fc.stats()['live'] == before

    def test_a_handle_operation_stays_well_under_five_milliseconds(self, fc, Part):
        """Measured at 0.4-0.9 ms on the prototype; the budget is generous so the suite is not
        flaky."""
        import time
        box = Part.makeBox(1.0, 1.0, 1.0)
        box.Volume
        started = time.time()
        for _ in range(50):
            box.Volume
        per_call = (time.time() - started) / 50.0
        assert per_call < 5.0e-3, '%.2f ms per handle operation' % (per_call * 1000.0)


class TestFreshWorker:

    def test_a_fresh_session_inherits_nothing(self, fresh_fc):
        """What §5.1 requires of a reproducibility measurement."""
        assert fresh_fc.stats()['live'] == 0
        assert fresh_fc.stats()['issued'] == 0
        docs = fresh_fc.module('FreeCAD').listDocuments()
        assert len(docs) == 0, 'a fresh worker must hold no document'

    def test_a_proxy_is_not_shared_between_sessions(self, fresh_fc, Part):
        """Two sessions are two processes; a handle from one is meaningless in the other."""
        mine = fresh_fc.module('Part').makeBox(1.0, 1.0, 1.0)
        assert isinstance(mine, Remote)
        assert mine._session is fresh_fc
