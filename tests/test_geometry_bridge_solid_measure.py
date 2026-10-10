"""IP-GB-20: `solid_measure`'s checks as real tests -- the bridge's first production consumer.

`check_solid_measure.py` is the script this ports. It exists because `Shape.Volume`, `Face.Area`
and `Shape.BoundBox` are measurably wrong on this project's B-spline solids, so `solid_measure`
provides tessellation-based replacements -- and until now that library's own regression lived in a
script with no assertions, only printed lines and a failure count, runnable only by hand under
`freecadcmd`.

**What the port buys, concretely.** The script reports ``check_solid_measure: 0 failure(s)`` and
exits 0 -- but `freecadcmd` exits 0 on an unhandled exception too, so a crashed run and a clean run
look the same from outside. Every check below is an assertion a test runner can fail on, named
individually, and they run in the ordinary suite rather than on request.

**Where the port deliberately differs from the script.** The script skips its slanted-face check
when the cut produces no slanted face (``(no slanted face on this cut -- skipped, not a
failure)``). A test must not decide for itself that a missing precondition is acceptable, so here
the slanted face is asserted to exist: if the wedge cut stops producing one, that is a change in
behaviour worth hearing about, not something to pass over.

The script stays in place until this port is shown equivalent -- the plan's own condition for
IP-GB-20 -- and `test_the_ported_script_still_exists` is what keeps that honest.

See doc/architecture/geometry_bridge.md §6.1 and doc/implementation/geometry_bridge.md IP-GB-20.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from geometry_bridge.remote_errors import NotConverged, TopologyMismatch   # noqa: E402

from conftest import requires_freecad                                      # noqa: E402

pytestmark = requires_freecad

#: The script's own tolerance: a relative comparison with an absolute floor of 1.
TOL = 1e-6


@pytest.fixture
def sm(fc):
    """`solid_measure`, the library under test."""
    return fc.module('solid_measure')


@pytest.fixture
def cube(Part):
    """A 10 mm cube. **Every answer about it has a closed form**, which a real cowl never gives."""
    return Part.makeBox(10.0, 10.0, 10.0)


@pytest.fixture
def wedge(cube, Part, App):
    """The cube with a 45-degree corner removed, for the non-axis-aligned cases.

    A half-space — a large box whose top face is the z = 0 plane — rotated 45 degrees about Y
    through the cube's center, so the plane genuinely passes through the cube. The script this
    ports builds its cutter differently and, as measured, never intersects anything.
    """
    cutter = Part.makeBox(40.0, 40.0, 40.0, App.Vector(-20.0, -20.0, -40.0))
    cutter.rotate(App.Vector(5.0, 5.0, 5.0), App.Vector(0.0, 1.0, 0.0), 45.0)
    out = cube.cut(cutter)
    assert out.Volume < 999.0, 'the cutter must actually remove material'
    return out


class TestMeshVolume:
    """A box tessellates exactly -- six planar quads need no curvature approximation -- so its
    mesh volume is exactly 1000.0 at any deflection."""

    def test_the_mesh_volume_of_a_cube_is_exact(self, sm, cube):
        vol, facets = sm.mesh_volume(cube, 0.1)
        assert vol == pytest.approx(1000.0, rel=TOL)

    def test_a_box_tessellates_to_at_least_two_triangles_per_face(self, sm, cube):
        vol, facets = sm.mesh_volume(cube, 0.1)
        assert facets >= 12

    def test_the_deflection_does_not_change_a_planar_result(self, sm, cube):
        """The property that makes the cube the right instrument: planar faces are exact at any
        refinement, so this is the one case where a mesh volume has no discretisation error."""
        coarse, _ = sm.mesh_volume(cube, 0.1)
        fine, _ = sm.mesh_volume(cube, 0.001)
        assert coarse == pytest.approx(fine, rel=1e-12)

    def test_shape_volume_agrees_with_the_mesh_on_a_planar_solid(self, cube):
        """The converse that keeps `solid_measure`'s reason for existing honest.

        `Shape.Volume` is wrong on *B-spline* solids, not on everything. If it disagreed here, on
        a cube, the explanation would not be B-splines and the library's premise would be wrong.
        """
        assert cube.Volume == pytest.approx(1000.0, rel=1e-12)


class TestOpenEdges:

    def test_a_closed_box_has_no_unpaired_edges(self, sm, cube):
        points, facet_count, unpaired = sm.open_edges(cube, 0.1)
        assert unpaired == 0

    def test_the_facet_count_matches_mesh_volumes(self, sm, cube):
        """Two entry points tessellating the same shape the same way must agree, or one of them is
        meshing something other than what it reports on."""
        _vol, facets = sm.mesh_volume(cube, 0.1)
        _points, facet_count, _unpaired = sm.open_edges(cube, 0.1)
        assert facet_count == facets

    def test_an_open_shell_is_detected(self, sm, cube):
        """The converse. Without it, `unpaired == 0` would pass on an instrument stuck at zero."""
        one_face = cube.Faces[0]
        _points, _facets, unpaired = sm.open_edges(one_face, 0.1)
        assert unpaired > 0, 'a single face is an open shell and must report unpaired edges'


class TestConvergedVolume:

    def test_a_cube_converges_to_its_exact_volume(self, sm, cube):
        conv_vol, _deflection, _tri = sm.converged_volume(cube)
        assert conv_vol == pytest.approx(1000.0, rel=TOL)

    def test_a_cube_converges_on_the_second_deflection_tried(self, sm, cube):
        """Not the last: a planar mesh does not move, so the first comparison already succeeds.

        This is what distinguishes converging from running out of deflections.
        """
        _conv_vol, deflection, _tri = sm.converged_volume(cube)
        assert deflection == pytest.approx(sm.DEFLECTIONS[1], rel=1e-9)

    def test_a_curved_solid_cannot_converge_at_zero_tolerance(self, sm, Part):
        """**A cube cannot reach this path at all**, which is why the script uses a cylinder here.

        A planar mesh is exact at every deflection, so even ``tol=0.0`` converges on a box
        instantly. A cylinder's mesh volume genuinely keeps moving as the facets approximate the
        round wall better, so ``tol=0.0`` genuinely never converges.
        """
        cyl = Part.makeCylinder(5.0, 10.0)
        with pytest.raises(NotConverged):
            sm.converged_volume(cyl, tol=0.0)

    def test_a_curved_solid_does_converge_at_the_real_tolerance(self, sm, Part):
        """The converse of the refusal: the guard must not be firing on everything curved."""
        cyl = Part.makeCylinder(5.0, 10.0)
        vol, _deflection, _tri = sm.converged_volume(cyl)
        import math
        assert vol == pytest.approx(math.pi * 25.0 * 10.0, rel=1e-3)


class TestTessellationIsCachedOnTheShape:
    """**Found while porting, 2026-10-06: FreeCAD caches a shape's triangulation, so a second
    convergence run on the same shape object converges spuriously.**

    `tessellate(deflection)` does not re-mesh. Once a shape has been tessellated at a fine
    deflection, every later call on that same object returns the cached mesh whatever deflection is
    asked for. Measured on a cylinder: a fresh shape gives 500 / 1 672 / 5 024 facets at 0.02 /
    0.005 / 0.001, and the same shape asked again gives 5 024 at all three.

    `converged_volume` walks the deflections coarse to fine on one shape, so its *first* run is
    correct — each deflection really is finer than the cache. A second run compares identical
    volumes and stops at once, reporting the coarsest deflection as the converged one.

    These tests pin the behaviour rather than assert it is right. Whether `solid_measure` should
    defeat the cache, and at what cost on a real cowl, is [OQ-DES-CW27] in
    doc/design/cowl.md.
    """

    def test_a_fresh_shape_refines_with_the_deflection(self, sm, Part):
        """The baseline the cache is measured against: meshing really is deflection-driven."""
        facets = []
        for d in (0.02, 0.005, 0.001):
            cyl = Part.makeCylinder(5.0, 10.0)
            _vol, f = sm.mesh_volume(cyl, d)
            facets.append(f)
        assert facets[0] < facets[1] < facets[2], facets

    def test_the_same_shape_returns_its_cached_mesh(self, sm, Part):
        """The defect itself. A coarse request after a fine one gets the fine mesh back."""
        cyl = Part.makeCylinder(5.0, 10.0)
        _vol_fine, facets_fine = sm.mesh_volume(cyl, 0.001)
        _vol_coarse, facets_coarse = sm.mesh_volume(cyl, 0.02)
        assert facets_coarse == facets_fine, (
            'expected the cached %d-facet mesh, got %d -- if this now differs, FreeCAD has '
            'stopped caching and OQ-DES-CW27 can be closed' % (facets_fine, facets_coarse))

    def test_a_second_convergence_run_reports_a_different_deflection(self, sm, Part):
        """The consequence that matters: the reported deflection is wrong on a reused shape."""
        cyl = Part.makeCylinder(5.0, 10.0)
        _v1, first, _t1 = sm.converged_volume(cyl)
        _v2, second, _t2 = sm.converged_volume(cyl)
        assert first != second, (
            'both runs reported deflection %s; the cache effect may have been fixed' % first)
        assert second == pytest.approx(sm.DEFLECTIONS[1], rel=1e-9)

    def test_the_volume_itself_is_not_corrupted_only_the_reported_deflection(self, sm, Part):
        """Bounding the damage: the number is still the finest mesh's, which is the right answer.

        This is why the production path is unaffected -- `soak_cowl_shell.py` reads `mesh_volume`
        at one fixed deflection on a freshly built shape, so it never reuses a tessellated shape
        at a coarser setting.
        """
        import math
        cyl = Part.makeCylinder(5.0, 10.0)
        v1, _d1, _t1 = sm.converged_volume(cyl)
        v2, _d2, _t2 = sm.converged_volume(cyl)
        assert v1 == pytest.approx(v2, rel=1e-12)
        assert v1 == pytest.approx(math.pi * 25.0 * 10.0, rel=1e-3)

    def test_zero_tolerance_stops_refusing_on_a_reused_shape(self, sm, Part):
        """The sharpest form of it: the same call raises, then succeeds.

        A guard that depends on call history is the part worth knowing about, and it is why the
        error-identity tests below build a fresh cylinder each time.
        """
        cyl = Part.makeCylinder(5.0, 10.0)
        with pytest.raises(NotConverged):
            sm.converged_volume(cyl, tol=0.0)
        sm.converged_volume(cyl, tol=0.0)        # no raise: the cache makes every mesh identical


class TestWireArea:

    def test_the_area_of_the_cubes_top_face(self, sm, cube):
        """`discretize(Number=400)` does not land exactly on the square's four corners, so even a
        straight boundary picks up a polygon-vs-square shortfall -- 0.003% measured. `wire_area`'s
        own docstring names this, so the tolerance reflects the method rather than a looser
        standard for this check."""
        top_face = max(cube.Faces.items(), key=lambda f: f.CenterOfMass.z)
        assert sm.wire_area(top_face) == pytest.approx(100.0, rel=1e-3)

    def test_a_non_axis_aligned_face_measures_positive_and_bounded(self, sm, wedge):
        """Exercises the "project onto whichever plane it is most parallel to" branch.

        **Asserted to exist, not skipped — and the script's own cutter does not produce one.**
        `check_solid_measure.py` builds its cutter as a box at the origin rotated 45 degrees about
        Y and falls back to ``(no slanted face on this cut -- skipped, not a failure)`` when the
        filter finds nothing. Measured 2026-10-06: it finds nothing *every* time, because that
        cutter never intersects the cube — the cut returns a shape of volume 1000.0, the cube
        unchanged. So the script's slanted-face check has never executed. The fixture here uses a
        half-space positioned to actually cut, and the assertion is that the face exists.
        """
        slanted = [f for f in wedge.Faces.items()
                   if abs(f.Surface.Axis.normalize().z) < 0.9 and abs(f.Surface.Axis.z) > 1e-6]
        assert slanted, 'the 45-degree cut must produce a slanted face, or this check has no'\
                        ' subject'
        area = sm.wire_area(slanted[0])
        assert 0.0 < area < 200.0

    def test_the_slanted_faces_area_is_right_not_merely_positive(self, sm, wedge):
        """A bound of ``0 < area < 200`` would pass on almost any wrong answer.

        The cut plane is at 45 degrees through the cube's center, so the exposed face is a
        rectangle 10 mm wide by the plane's chord across the cube. `Face.Area` is trustworthy here
        because the face is planar — it is on B-spline faces that it reads 23% off — so the two
        instruments can be compared directly.
        """
        slanted = [f for f in wedge.Faces.items()
                   if abs(f.Surface.Axis.normalize().z) < 0.9 and abs(f.Surface.Axis.z) > 1e-6]
        assert len(slanted) == 1
        assert sm.wire_area(slanted[0]) == pytest.approx(slanted[0].Area, rel=1e-3)


class TestSurfaceDifference:

    def test_two_identical_boxes_show_no_gap(self, sm, Part):
        box_a = Part.makeBox(10.0, 10.0, 10.0)
        box_b = Part.makeBox(10.0, 10.0, 10.0)
        est, _err, _area, mean_gap, _max_gap = sm.surface_difference(box_a, box_b, samples=50)
        assert mean_gap == pytest.approx(0.0, abs=1e-9)
        assert est == pytest.approx(0.0, abs=1e-9)

    def test_the_reported_area_is_the_boxs_true_area(self, sm, Part):
        box_a = Part.makeBox(10.0, 10.0, 10.0)
        box_b = Part.makeBox(10.0, 10.0, 10.0)
        _est, _err, area, _mean, _max = sm.surface_difference(box_a, box_b, samples=50)
        assert area == pytest.approx(600.0, rel=TOL)

    def test_a_genuine_size_difference_is_detected(self, sm, Part):
        """The converse, and the one the script reports without asserting."""
        box_a = Part.makeBox(10.0, 10.0, 10.0)
        box_c = Part.makeBox(12.0, 10.0, 10.0)          # 2 mm longer in x
        _est, _err, _area, mean_gap, max_gap = sm.surface_difference(box_a, box_c, samples=200)
        assert mean_gap > 0.0
        assert max_gap > 0.0

    def test_the_measurement_is_a_distance_not_a_signed_integral(self, sm, Part):
        """Why `surface_difference` and not a volume difference: a surface that wanders out and
        back cancels itself in an integral. Measured on two tail builds, a signed volume read
        0.006 mm3 where the symmetric difference was 2.08 -- 260x larger.

        A box shrunk in one axis and grown in another has nearly the same volume; the gap must
        still be positive.
        """
        box_a = Part.makeBox(10.0, 10.0, 10.0)
        box_d = Part.makeBox(8.0, 12.5, 10.0)           # same volume, different surface
        assert box_d.Volume == pytest.approx(box_a.Volume, rel=1e-9)
        _est, _err, _area, mean_gap, _max = sm.surface_difference(box_a, box_d, samples=200)
        assert mean_gap > 0.0, 'equal volumes must not read as equal surfaces'


class TestConvergedDifference:

    def test_two_identical_boxes_differ_by_zero(self, sm, Part):
        box_a = Part.makeBox(10.0, 10.0, 10.0)
        box_b = Part.makeBox(10.0, 10.0, 10.0)
        diff, _deflection, _relative = sm.converged_difference(box_a, box_b)
        assert diff == pytest.approx(0.0, abs=1e-9)

    def test_unequal_face_counts_are_refused(self, sm, cube, Part, App):
        """The module's stated precondition, surfaced as its own exception through the bridge."""
        cutter = Part.makeBox(20.0, 20.0, 20.0, App.Vector(0, 0, 0), App.Vector(1, 0, 0))
        cutter.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), 45.0)
        wedge = cube.cut(cutter)
        assert len(wedge.Faces) != len(cube.Faces)
        with pytest.raises(TopologyMismatch):
            sm.converged_difference(cube, wedge)


class TestTheErrorsCrossAsThemselves:
    """§4.9's claim, exercised by a real library rather than by a stub.

    This is the question the design was challenged on -- whether a boundary degrades a geometry
    failure into a confusing test error. It does not: the class, the message and the worker-side
    traceback all arrive.
    """

    def test_not_converged_is_not_catchable_as_a_bridge_fault(self, sm, Part):
        """The separation that makes the distinction useful: a measurement refusing to converge is
        not the bridge failing."""
        from geometry_bridge.errors import BridgeError
        cyl = Part.makeCylinder(5.0, 10.0)
        with pytest.raises(NotConverged) as caught:
            sm.converged_volume(cyl, tol=0.0)
        assert not isinstance(caught.value, BridgeError)

    def test_the_remote_traceback_names_the_library(self, sm, Part):
        cyl = Part.makeCylinder(5.0, 10.0)
        with pytest.raises(NotConverged) as caught:
            sm.converged_volume(cyl, tol=0.0)
        assert 'solid_measure' in caught.value.remote_traceback
        assert 'converged_volume' in caught.value.remote_traceback

    def test_the_same_remote_class_twice_is_the_same_class(self, sm, Part):
        """A **fresh cylinder each time**, because a reused one stops raising -- see
        `TestTessellationIsCachedOnTheShape`. This test is about class identity, so it must not
        depend on that."""
        seen = []
        for _ in range(2):
            cyl = Part.makeCylinder(5.0, 10.0)
            try:
                sm.converged_volume(cyl, tol=0.0)
            except Exception as exc:                                     # noqa: BLE001
                seen.append(type(exc))
        assert len(seen) == 2, 'both calls should have raised'
        assert seen[0] is seen[1] is NotConverged


class TestEquivalenceWithTheScript:

    def test_the_ported_script_still_exists(self):
        """IP-GB-20 keeps the script until the port is shown equivalent, so its removal should be
        a deliberate act with this test in hand, not a silent one."""
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(here, 'src', 'Fuselage', 'freecad', 'check_solid_measure.py')
        assert os.path.isfile(script)

    def test_every_library_entry_point_the_script_touches_is_covered_here(self):
        """Guards the port's completeness against the script drifting ahead of it.

        A set built only from this file would prove nothing -- it would just copy itself. So the
        names come from the script's own text.
        """
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(here, 'src', 'Fuselage', 'freecad', 'check_solid_measure.py')
        text = open(script, encoding='utf-8').read()
        mine = open(os.path.abspath(__file__), encoding='utf-8').read()
        missing = []
        for name in ('mesh_volume', 'open_edges', 'converged_volume', 'wire_area',
                     'surface_difference', 'converged_difference', 'DEFLECTIONS'):
            if 'sm.' + name in text and 'sm.' + name not in mine:
                missing.append(name)
        # The exceptions are reached through `remote_errors`, not through the module proxy, so the
        # bare name is what to look for here.
        for name in ('NotConverged', 'TopologyMismatch'):
            if 'sm.' + name in text and name not in mine:
                missing.append(name)
        assert not missing, 'the script exercises %s and this port does not' % ', '.join(missing)
