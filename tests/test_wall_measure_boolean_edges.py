"""Does the rib cut's output lie on the two surfaces it is a boolean of?

`boolean_edges` checks the set identity the three-dimensional form of section 4.2 rests on --
`boundary(S - T)` is a subset of `boundary(S)` union `boundary(T)` -- which the build has never
checked. The parts of it that are arithmetic are held to closed-form truth here: a point at a
known distance from a known plane must read that distance, a point outside a face's box must be
rejected by the box filter, and the banding must put a sample in the band its magnitude belongs
to. The parts that need a kernel are exercised by `freecad/rib_edge_check.py` against a real
build.

**The box filter is tested for being optimistic in the documented direction, not for being
right.** A plane is not a face, and a point on the plane just outside the face reads zero. That is
a known property of the cheap measure and the reason `agrees_with_kernel` exists; a test that
asserted the cheap measure never does this would be asserting something false.

See doc/design/cowl_interior_surface.md section 4.2 and
doc/implementation/wall_thickness_measure.md.
"""
import contextlib
import os
import sys
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import boolean_edges as be                             # noqa: E402


class Plane(object):
    """Just enough of `Part.Plane` for `plane_set`: a position, an axis, and the type name."""

    def __init__(self, origin, normal):
        self.Position = Vec(*origin)
        n = np.asarray(normal, dtype=float)
        n = n / np.linalg.norm(n)
        self.Axis = Vec(*n)


class Cylinder(object):
    """A non-planar surface, so `plane_set`'s refusal can be exercised."""


class Vec(object):
    """Enough of `App.Vector` for the facet-area arithmetic in `interior_probes`."""

    def __init__(self, x, y, z):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def sub(self, other):
        return Vec(self.x - other.x, self.y - other.y, self.z - other.z)

    def cross(self, other):
        return Vec(self.y * other.z - self.z * other.y,
                   self.z * other.x - self.x * other.z,
                   self.x * other.y - self.y * other.x)

    @property
    def Length(self):                                                # noqa: N802 vendor name
        return float(np.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2))


class Box(object):
    def __init__(self, lo, hi):
        self.XMin, self.YMin, self.ZMin = [float(v) for v in lo]
        self.XMax, self.YMax, self.ZMax = [float(v) for v in hi]


class Vertex(object):
    def __init__(self, point):
        self.Point = Vec(*point)


class Edge(object):
    """Just enough of `Part.Edge` for `_edge_key`, `face_adjacency` and `edge_conformance`."""

    def __init__(self, a, b):
        self.a, self.b = tuple(float(v) for v in a), tuple(float(v) for v in b)
        self.Vertexes = [Vertex(self.a), Vertex(self.b)]
        self.FirstParameter, self.LastParameter = 0.0, 1.0
        self.Length = float(np.linalg.norm(np.array(self.b) - np.array(self.a)))

    def valueAt(self, u):                                            # noqa: N802 vendor name
        p = np.array(self.a) + float(u) * (np.array(self.b) - np.array(self.a))
        return Vec(*p)

    def reversed(self):
        return Edge(self.b, self.a)

    def discretize(self, Number):                                    # noqa: N803 vendor kwarg
        n = int(Number)
        return [self.valueAt(k / float(n - 1)) for k in range(n)]


class Face(object):
    def __init__(self, surface, lo, hi, edges=(), facets=()):
        self.Surface = surface
        self.BoundBox = Box(lo, hi)
        self.Edges = list(edges)
        self._facets = list(facets)

    def tessellate(self, _deflection):
        """`(vertices, index triples)`, the shape `Part.Face.tessellate` returns."""
        verts, tris = [], []
        for tri in self._facets:
            base = len(verts)
            verts.extend(Vec(*p) for p in tri)
            tris.append((base, base + 1, base + 2))
        return verts, tris


class Shape(object):
    def __init__(self, faces):
        self.Faces = list(faces)


def fake_part(on_face=None, raises=False, distance=0.0):
    """A stand-in for the `Part` module, to pass in as the `Part` argument.

    The real one arrives as an argument everywhere in this module (see `TestNoVendorImport`), so a
    substitute needs no `sys.modules` surgery -- which is the point of taking it as an argument.
    """
    class Vertex(object):
        def __init__(self, x, y, z):
            self.point = Vec(x, y, z)

        def distToShape(self, _other):                               # noqa: N802 vendor name
            if raises:
                raise RuntimeError('kernel refused')
            return (distance, [(self.point, on_face)], None)

    module = types.ModuleType('Part')
    module.Vertex = Vertex
    module.makeCompound = lambda faces: Shape(faces)
    return module


def unit_square_at(z, half=1.0):
    """A face on the plane `z = z`, spanning `+/-half` in x and y."""
    return Face(Plane((0.0, 0.0, z), (0.0, 0.0, 1.0)),
                (-half, -half, z), (half, half, z))


# ---------------------------------------------------------------------------- the plane set


class TestPlaneSet:

    def test_it_reads_origin_normal_and_box_off_each_face(self):
        shape = Shape([unit_square_at(0.0), unit_square_at(5.0)])
        faces, origins, normals, boxes = be.plane_set(shape)
        assert len(faces) == 2
        assert origins.shape == (2, 3) and normals.shape == (2, 3) and boxes.shape == (2, 6)
        assert origins[1].tolist() == [0.0, 0.0, 5.0]
        assert normals[0].tolist() == [0.0, 0.0, 1.0]
        assert boxes[0].tolist() == [-1.0, -1.0, 0.0, 1.0, 1.0, 0.0]

    def test_it_normalizes_nothing_it_was_not_given(self):
        """A `Part.Plane`'s `Axis` is already a unit vector; `plane_set` must not rescale it, or a
        signed distance computed against it would be wrong by that factor."""
        shape = Shape([Face(Plane((1.0, 2.0, 3.0), (0.0, 3.0, 4.0)), (0, 0, 0), (1, 1, 1))])
        _f, _o, normals, _b = be.plane_set(shape)
        assert np.allclose(normals[0], [0.0, 0.6, 0.8])

    def test_a_curved_face_is_refused_not_skipped(self):
        """Dropping it would make every distance an under-estimate -- the optimistic direction."""
        shape = Shape([unit_square_at(0.0), Face(Cylinder(), (0, 0, 0), (1, 1, 1))])
        with pytest.raises(ValueError) as exc:
            be.plane_set(shape)
        assert 'Cylinder' in str(exc.value)

    def test_a_shape_with_no_faces_is_refused(self):
        with pytest.raises(ValueError):
            be.plane_set(Shape([]))

    def test_only_the_tool_is_read_this_way(self):
        """The fitted interior solid's boundary is deliberately mixed -- one B-spline, planar lids
        and side caps, and `SurfaceOfExtrusion` end-overrun walls -- so it is measured with the
        kernel (`closure_faces`), never enumerated as planes. Reading it as a plane set is what
        discarded the extrusion walls and left two faces classified `neither`."""
        mixed = Shape([unit_square_at(0.0), Face(Cylinder(), (0, 0, 0), (1, 1, 1))])
        with pytest.raises(ValueError):
            be.plane_set(mixed)


# -------------------------------------------------------------------------- interior probes


def triangle(a, b, c):
    return (a, b, c)


class TestInteriorProbes:
    """`snap=False` throughout: the snap needs a kernel, and these hold the facet arithmetic that
    picks *which* point to snap. `TestProbeSnap` below covers the snap's own contract."""

    def test_a_centroid_is_returned_for_each_facet(self):
        face = Face(Plane((0, 0, 0), (0, 0, 1)), (0, 0, 0), (1, 1, 0),
                    facets=[triangle((0, 0, 0), (3, 0, 0), (0, 3, 0))])
        pts = be.interior_probes(face)
        assert len(pts) == 1
        assert pts[0] == pytest.approx((1.0, 1.0, 0.0))

    def test_the_largest_facets_come_first(self):
        """**The reason, documented in the function:** a sliver facet along a trim curve has a
        centroid within a tolerance of the boundary, which is the thing being avoided."""
        big = triangle((0, 0, 0), (10, 0, 0), (0, 10, 0))
        sliver = triangle((0, 0, 0), (10, 0, 0), (10, 1.0e-6, 0))
        face = Face(Plane((0, 0, 0), (0, 0, 1)), (0, 0, 0), (10, 10, 0), facets=[sliver, big])
        pts = be.interior_probes(face, count=1)
        assert pts[0] == pytest.approx((10.0 / 3.0, 10.0 / 3.0, 0.0))

    def test_it_returns_at_most_the_count_asked_for(self):
        facets = [triangle((0, 0, 0), (k + 1, 0, 0), (0, k + 1, 0)) for k in range(10)]
        face = Face(Plane((0, 0, 0), (0, 0, 1)), (0, 0, 0), (10, 10, 0), facets=facets)
        assert len(be.interior_probes(face, count=3)) == 3
        assert len(be.interior_probes(face, count=99)) == 10

    def test_a_face_that_tessellates_to_nothing_gives_no_probes(self):
        face = Face(Plane((0, 0, 0), (0, 0, 1)), (0, 0, 0), (1, 1, 0), facets=[])
        assert be.interior_probes(face) == []

    def test_a_degenerate_facet_is_ranked_last_not_dropped(self):
        """Zero area is still a point inside the face; it just has no claim to being far from the
        boundary, so it sorts behind anything with area."""
        zero = triangle((1, 1, 0), (1, 1, 0), (1, 1, 0))
        real = triangle((0, 0, 0), (3, 0, 0), (0, 3, 0))
        face = Face(Plane((0, 0, 0), (0, 0, 1)), (0, 0, 0), (3, 3, 0), facets=[zero, real])
        pts = be.interior_probes(face, count=2)
        assert len(pts) == 2
        assert pts[0] == pytest.approx((1.0, 1.0, 0.0))


class TestProbeSnap:

    def face(self):
        return Face(Plane((0, 0, 0), (0, 0, 1)), (0, 0, 0), (3, 3, 0),
                    facets=[triangle((0, 0, 0), (3, 0, 0), (0, 3, 0))])

    def test_a_centroid_is_moved_onto_the_face(self):
        """**The regression the third real run exposed.** A facet is a chord, so its centroid sits
        inside a curved face by up to the tessellation deflection -- exact for a plane, ~0.1 mm off
        the fitted B-spline. Against a 1e-5 mm tolerance that put zero of a nose cavity's 60 faces
        on the fitted surface, and showed the 45 real rib creases as `neither + tool`."""
        pts = be.interior_probes(self.face(), Part=fake_part(on_face=Vec(1.0, 1.0, 0.25)))
        assert pts[0] == pytest.approx((1.0, 1.0, 0.25))

    def test_the_unsnapped_point_is_the_chord_centroid(self):
        assert be.interior_probes(self.face())[0] == pytest.approx((1.0, 1.0, 0.0))

    def test_a_kernel_refusal_leaves_the_point_where_it_was(self):
        """A face the kernel cannot measure against must not lose its probe entirely -- an empty
        probe list classifies the face `neither`, which is the one answer that means a defect."""
        pts = be.interior_probes(self.face(), Part=fake_part(raises=True))
        assert pts[0] == pytest.approx((1.0, 1.0, 0.0))

    def test_with_no_part_the_points_come_back_unsnapped_rather_than_raising(self):
        """`Part` defaults to `None` so the facet arithmetic stays testable without a kernel; the
        module must not import one, see `TestNoVendorImport`."""
        assert be.interior_probes(self.face(), Part=None)[0] == pytest.approx((1.0, 1.0, 0.0))


# ------------------------------------------------------------------- distance to a face plane


class TestPlaneDeviations:

    def setup_method(self):
        self.planes = be.plane_set(Shape([unit_square_at(0.0), unit_square_at(5.0)]))

    def dev(self, points, **kw):
        _f, o, n, b = self.planes
        return be.plane_deviations(points, o, n, b, **kw)

    def test_a_point_on_a_face_reads_zero(self):
        d, i = self.dev([(0.0, 0.0, 0.0)])
        assert d[0] == pytest.approx(0.0, abs=1e-15)
        assert i[0] == 0

    def test_distance_is_the_perpendicular_one_and_exact(self):
        d, i = self.dev([(0.3, -0.4, 0.25)])
        assert d[0] == pytest.approx(0.25, abs=1e-15)
        assert i[0] == 0

    def test_it_picks_the_nearer_of_two_candidate_planes(self):
        """A point between the two faces, inside both boxes once they are padded, must report the
        nearer plane -- not the first one, and not the one with the smaller index."""
        tall = be.plane_set(Shape([
            Face(Plane((0, 0, 0), (0, 0, 1)), (-1, -1, -1), (1, 1, 9)),
            Face(Plane((0, 0, 5), (0, 0, 1)), (-1, -1, -1), (1, 1, 9)),
        ]))
        _f, o, n, b = tall
        d, i = be.plane_deviations([(0.0, 0.0, 3.5)], o, n, b)
        assert i[0] == 1
        assert d[0] == pytest.approx(1.5)

    def test_a_point_outside_every_padded_box_has_no_candidate(self):
        d, i = self.dev([(50.0, 50.0, 50.0)])
        assert not np.isfinite(d[0])
        assert i[0] == -1

    def test_the_box_test_is_on_the_projection_not_the_point(self):
        """**The regression this module was built wrong on first.** A planar face's bounding box
        is flat, so padding the raw point against it rejects every point further off the plane
        than the pad -- precisely the points worth finding. Here the point is 0.25 mm off a face
        whose box has zero thickness, and must read 0.25 mm, not `inf`."""
        d, i = self.dev([(0.0, 0.0, 0.25)])
        assert i[0] == 0
        assert d[0] == pytest.approx(0.25)

    def test_the_off_plane_distance_is_never_filtered_however_large(self):
        """One face, so the nearest candidate cannot change with the offset."""
        _f, o, n, b = be.plane_set(Shape([unit_square_at(0.0)]))
        for off in (1.0e-6, 1.0e-3, 0.25, 7.0, 1000.0):
            d, i = be.plane_deviations([(0.0, 0.0, off)], o, n, b)
            assert i[0] == 0, off
            assert d[0] == pytest.approx(off), off

    def test_the_pad_is_what_decides_the_in_plane_box_test(self):
        """0.0004 mm beyond the face in x is a candidate at the default pad, not at a tighter
        one. In plane, unlike off plane, the box does constrain."""
        just_outside = [(1.0004, 0.0, 0.0)]
        d_default, i_default = self.dev(just_outside)
        assert i_default[0] == 0 and d_default[0] == pytest.approx(0.0, abs=1e-12)
        d_tight, i_tight = self.dev(just_outside, pad=1.0e-6)
        assert i_tight[0] == -1 and not np.isfinite(d_tight[0])

    def test_the_box_filter_is_optimistic_just_outside_a_face(self):
        """Documented, not a defect: a plane is not a trim. The point is 0.0005 mm beyond the face
        in x, so its true distance to the *face* is 0.0005 mm, and the cheap measure says 0.0.
        `agrees_with_kernel` is what catches this; a test claiming otherwise would be false."""
        d, i = self.dev([(1.0005, 0.0, 0.0)])
        assert i[0] == 0
        assert d[0] == pytest.approx(0.0, abs=1e-12)

    def test_it_is_vectorized_over_points(self):
        pts = [(0, 0, 0.0), (0, 0, 0.001), (0, 0, 5.0), (40, 40, 40)]
        d, i = self.dev(pts)
        assert len(d) == 4 and len(i) == 4
        assert d[1] == pytest.approx(0.001)
        assert i[2] == 1
        assert i[3] == -1

    def test_chunking_is_exact_at_every_block_size(self):
        """**Bounded before the tail was ever run.** The intermediate is points x faces x 3
        floats, so a tail's thousands of samples against eleven tools' thousands of faces would
        be hundreds of megabytes in one allocation; `candidates._segment_distances` was caught by
        the identical arithmetic asking for 37 TB. Chunking must not change a single answer."""
        _f, o, n, b = self.planes
        pts = [(0.3 * k, -0.2 * k, 0.01 * k) for k in range(37)]
        ref_d, ref_i = be.plane_deviations(pts, o, n, b, max_block=be.MAX_BLOCK)
        for block in (6, 7, 12, 60, 300, 1000):
            d, i = be.plane_deviations(pts, o, n, b, max_block=block)
            assert np.array_equal(i, ref_i), block
            assert np.array_equal(np.isfinite(d), np.isfinite(ref_d)), block
            finite = np.isfinite(ref_d)
            assert np.allclose(d[finite], ref_d[finite], rtol=0.0, atol=0.0), block

    def test_a_block_too_small_for_one_row_still_runs(self):
        """`rows` is floored at 1, so an absurd budget degrades to one point at a time rather
        than dividing by zero or looping forever."""
        _f, o, n, b = self.planes
        d, i = be.plane_deviations([(0, 0, 0.1), (0, 0, 5.1)], o, n, b, max_block=1)
        assert i.tolist() == [0, 1]
        assert d == pytest.approx([0.1, 0.1])

    def test_a_tilted_plane_is_measured_along_its_own_normal(self):
        """Not along z. A 45-degree plane through the origin puts (1, 0, 0) at 1/sqrt(2)."""
        tilted = be.plane_set(Shape([
            Face(Plane((0, 0, 0), (1.0, 0.0, 1.0)), (-2, -2, -2), (2, 2, 2))]))
        _f, o, n, b = tilted
        d, _i = be.plane_deviations([(1.0, 0.0, 0.0)], o, n, b)
        assert d[0] == pytest.approx(1.0 / np.sqrt(2.0))


# ------------------------------------------------------------------------------ banding


class TestClassifyFace:

    def test_each_boundary_on_its_own(self):
        far = 1.0
        assert be.classify_face(0.0, far, far) == be.ON_SURFACE
        assert be.classify_face(far, 0.0, far) == be.ON_LID
        assert be.classify_face(far, far, 0.0) == be.ON_TOOL

    def test_a_lid_is_not_the_fitted_surface(self):
        """**The regression the first real run exposed.** Folding the lids and side caps in with
        the fitted surface made every edge the nose cavity reported a rib crease a `tool`/`lid`
        edge instead -- 2.411 mm from the fitted surface, exactly on a side cap at `x` = 0."""
        assert be.classify_face(2.411, 0.0, 1.0) == be.ON_LID
        assert be.classify_face(2.411, 0.0, 1.0) != be.ON_SURFACE

    def test_near_more_than_one_is_ambiguous_not_a_pick(self):
        assert be.classify_face(0.0, 0.0, 1.0) == be.ON_AMBIGUOUS
        assert be.classify_face(0.0, 1.0, 0.0) == be.ON_AMBIGUOUS
        assert be.classify_face(1.0, 0.0, 0.0) == be.ON_AMBIGUOUS
        assert be.classify_face(0.0, 0.0, 0.0) == be.ON_AMBIGUOUS

    def test_near_none_is_geometry_the_boolean_invented(self):
        assert be.classify_face(1.0, 1.0, 1.0) == be.ON_NEITHER

    def test_the_tolerance_is_a_parameter(self):
        assert be.classify_face(1.0e-3, 1.0, 1.0, tol=1.0e-2) == be.ON_SURFACE
        assert be.classify_face(1.0e-3, 1.0, 1.0, tol=1.0e-4) == be.ON_NEITHER


class TestClassify:

    def test_on_both_is_the_rib_edge_case(self):
        assert be.classify(0.0, 0.0) == be.ON_BOTH

    def test_each_single_surface_case(self):
        assert be.classify(0.0, 1.0) == be.ON_SMOOTH
        assert be.classify(1.0, 0.0) == be.ON_TOOL

    def test_on_neither_is_geometry_the_boolean_invented(self):
        assert be.classify(1.0, 1.0) == be.ON_NEITHER

    def test_the_boundary_is_inclusive_at_the_tolerance(self):
        tol = be.FUZZ_TOL
        assert be.classify(tol, 10.0) == be.ON_SMOOTH
        assert be.classify(tol * 1.000001, 10.0) == be.ON_NEITHER

    def test_the_tolerance_is_a_parameter(self):
        assert be.classify(1.0e-3, 10.0, tol=1.0e-2) == be.ON_SMOOTH
        assert be.classify(1.0e-3, 10.0, tol=1.0e-4) == be.ON_NEITHER


# ----------------------------------------------------------------- adjacency and rib edges


def square_face(z, edges, cls_hint=None):
    """A planar face at height `z` carrying `edges`."""
    return Face(Plane((0.0, 0.0, z), (0.0, 0.0, 1.0)), (-9, -9, z), (9, 9, z), edges=edges)


class TestEdgeKey:

    def test_the_same_edge_from_either_direction_keys_the_same(self):
        """Two faces sharing an edge see it with opposite orientation; the key must not care."""
        forward = Edge((0, 0, 0), (1, 2, 3))
        assert be._edge_key(forward) == be._edge_key(forward.reversed())

    def test_two_different_edges_key_differently(self):
        assert be._edge_key(Edge((0, 0, 0), (1, 0, 0))) != \
            be._edge_key(Edge((0, 0, 0), (0, 1, 0)))

    def test_two_edges_with_the_same_endpoints_but_different_length_key_differently(self):
        """A straight chord and an arc between the same two points are different edges."""
        straight = Edge((0, 0, 0), (2, 0, 0))
        bowed = Edge((0, 0, 0), (2, 0, 0))
        bowed.Length = 2.5
        bowed.valueAt = lambda u: Vec(2.0 * u, 0.3, 0.0)
        assert be._edge_key(straight) != be._edge_key(bowed)


class TestFaceAdjacency:

    def shared(self):
        """Two faces sharing one edge, each with one edge of its own."""
        common = Edge((0, 0, 0), (1, 0, 0))
        a = square_face(0.0, [common, Edge((0, 0, 0), (0, 1, 0))])
        b = square_face(0.0, [common.reversed(), Edge((1, 0, 0), (1, 1, 0))])
        return Shape([a, b])

    def rows(self, shape, classes):
        return [{'face': i, 'on': c} for i, c in enumerate(classes)]

    def test_a_shared_edge_groups_the_two_faces_together(self):
        shape = self.shared()
        groups, _nm = be.face_adjacency(shape, self.rows(shape, [be.ON_SMOOTH, be.ON_TOOL]))
        shared = [slot for slot in groups.values() if len(slot['faces']) == 2]
        assert len(shared) == 1
        assert sorted(shared[0]['faces']) == [0, 1]

    def test_an_unshared_edge_is_reported_as_non_manifold(self):
        """On a closed solid every edge has exactly two faces, so a count that is not two means a
        key failed to match -- a rib edge this check would then silently never look at."""
        shape = self.shared()
        groups, nonmanifold = be.face_adjacency(shape, self.rows(shape, [be.ON_SMOOTH,
                                                                        be.ON_TOOL]))
        assert len(groups) == 3
        assert nonmanifold == 2

    def test_a_face_listed_twice_for_one_edge_is_counted_once(self):
        e = Edge((0, 0, 0), (1, 0, 0))
        shape = Shape([square_face(0.0, [e, e])])
        groups, _nm = be.face_adjacency(shape, self.rows(shape, [be.ON_SMOOTH]))
        assert list(groups.values())[0]['faces'] == [0]


class TestRibEdges:

    def pair(self, class_a, class_b):
        common = Edge((0, 0, 0), (4, 0, 0))
        a = square_face(0.0, [common])
        b = square_face(0.0, [common.reversed()])
        shape = Shape([a, b])
        rows = [{'face': 0, 'on': class_a}, {'face': 1, 'on': class_b}]
        return be.rib_edges(shape, rows)

    def test_the_fitted_surface_meeting_a_tool_face_is_a_rib_edge(self):
        out = self.pair(be.ON_SURFACE, be.ON_TOOL)
        assert len(out) == 1
        assert out[0]['length_mm'] == pytest.approx(4.0)
        assert out[0]['classes'] == [be.ON_SURFACE, be.ON_TOOL]

    def test_order_of_the_two_faces_does_not_matter(self):
        assert len(self.pair(be.ON_TOOL, be.ON_SURFACE)) == 1

    def test_two_faces_of_the_same_class_are_a_seam_not_a_rib_edge(self):
        assert self.pair(be.ON_SURFACE, be.ON_SURFACE) == []
        assert self.pair(be.ON_TOOL, be.ON_TOOL) == []

    def test_a_tool_against_a_lid_is_not_a_rib_crease(self):
        """**The regression the first real run exposed, and the one that mattered.** All four
        edges the nose cavity reported were `tool`/`lid`: where the rib cut runs out to the cell
        boundary, 2.411 mm from the fitted surface. A rib crease is a cut into the *interior
        surface*, and nothing else counts as one."""
        assert self.pair(be.ON_TOOL, be.ON_LID) == []
        assert self.pair(be.ON_LID, be.ON_LID) == []
        assert self.pair(be.ON_SURFACE, be.ON_LID) == []

    def test_an_ambiguous_face_supplies_no_side(self):
        """Probing face vertices had classified 35 of a nose cavity's 60 faces as near more than
        one boundary, and letting such a face supply every side it is near reported an end-lid
        edge 22.5 mm from the nearest tool as a rib crease."""
        assert self.pair(be.ON_AMBIGUOUS, be.ON_AMBIGUOUS) == []
        assert self.pair(be.ON_AMBIGUOUS, be.ON_SURFACE) == []
        assert self.pair(be.ON_AMBIGUOUS, be.ON_TOOL) == []

    def test_a_neither_face_supplies_no_side_either(self):
        assert self.pair(be.ON_NEITHER, be.ON_SURFACE) == []
        assert self.pair(be.ON_NEITHER, be.ON_TOOL) == []

    def test_longest_first_so_a_truncated_run_drops_the_shortest(self):
        short, long_ = Edge((0, 0, 0), (1, 0, 0)), Edge((0, 5, 0), (0, 12, 0))
        a = square_face(0.0, [short, long_])
        b = square_face(0.0, [short.reversed(), long_.reversed()])
        out = be.rib_edges(Shape([a, b]), [{'face': 0, 'on': be.ON_SURFACE},
                                           {'face': 1, 'on': be.ON_TOOL}])
        assert [round(r['length_mm']) for r in out] == [7, 1]


class TestEdgeKinds:

    def test_every_group_is_tallied_by_its_pair_of_classes(self):
        shared = Edge((0, 0, 0), (1, 0, 0))
        own_a, own_b = Edge((0, 0, 0), (0, 1, 0)), Edge((1, 0, 0), (1, 1, 0))
        a = square_face(0.0, [shared, own_a])
        b = square_face(0.0, [shared.reversed(), own_b])
        shape = Shape([a, b])
        rows = [{'face': 0, 'on': be.ON_SURFACE}, {'face': 1, 'on': be.ON_TOOL}]
        kinds = be.edge_kinds(shape, rows)
        assert kinds['surface + tool'] == 1
        assert sum(kinds.values()) == 3                 # one shared, two unshared

    def test_the_pair_label_is_order_independent(self):
        shared = Edge((0, 0, 0), (1, 0, 0))
        shape = Shape([square_face(0.0, [shared]), square_face(0.0, [shared.reversed()])])
        one = be.edge_kinds(shape, [{'face': 0, 'on': be.ON_TOOL},
                                    {'face': 1, 'on': be.ON_SURFACE}])
        other = be.edge_kinds(shape, [{'face': 0, 'on': be.ON_SURFACE},
                                      {'face': 1, 'on': be.ON_TOOL}])
        assert one == other == {'surface + tool': 1}

    def test_it_accounts_for_the_edges_rib_edges_rejected(self):
        """The point of the tally: a `surface`/`tool` count of zero has to be visible rather than
        looking like a clean result."""
        shared = Edge((0, 0, 0), (1, 0, 0))
        shape = Shape([square_face(0.0, [shared]), square_face(0.0, [shared.reversed()])])
        rows = [{'face': 0, 'on': be.ON_TOOL}, {'face': 1, 'on': be.ON_LID}]
        assert be.rib_edges(shape, rows) == []
        assert be.edge_kinds(shape, rows) == {'lid + tool': 1}


# ------------------------------------------------------------------------ edge conformance


class TestEdgeConformance:

    def setup_method(self):
        self.planes = be.plane_set(Shape([unit_square_at(0.0, half=9.0)]))

    def rows(self, *edges):
        return [{'edge': e, 'faces': [0, 1], 'length_mm': e.Length} for e in edges]

    def part(self):
        """A `Part` whose every distance to the fitted faces reads 0.002 mm."""
        return fake_part(distance=0.002)

    def test_sample_count_follows_arc_length_not_a_fixed_number(self):
        part = self.part()
        samples, truncated = be.edge_conformance(part, self.rows(Edge((0, 0, 0), (2, 0, 0))),
                                                 self.planes, None, arc=0.2)
        assert truncated == 0
        assert len(samples) == 11                       # 2.0 mm / 0.2 mm + 1
        samples, _t = be.edge_conformance(part, self.rows(Edge((0, 0, 0), (4, 0, 0))),
                                          self.planes, None, arc=0.2)
        assert len(samples) == 21

    def test_both_distances_are_carried_per_sample(self):
        samples, _t = be.edge_conformance(self.part(),
                                          self.rows(Edge((0, 0, 0.5), (2, 0, 0.5))),
                                          self.planes, None, arc=1.0)
        assert all(s['d_smooth_mm'] == pytest.approx(0.002) for s in samples)
        assert all(s['d_tool_mm'] == pytest.approx(0.5) for s in samples)
        assert all(s['on'] == be.ON_NEITHER for s in samples)

    def test_an_edge_over_the_point_budget_is_dropped_and_counted(self):
        samples, truncated = be.edge_conformance(self.part(),
                                                 self.rows(Edge((0, 0, 0), (9, 0, 0))),
                                                 self.planes, None, arc=0.2, max_points=5)
        assert samples == [] and truncated == 1

    def test_a_short_edge_still_gets_two_samples(self):
        samples, _t = be.edge_conformance(self.part(),
                                          self.rows(Edge((0, 0, 0), (0.001, 0, 0))),
                                          self.planes, None, arc=0.2)
        assert len(samples) == 2

    def test_the_edge_index_is_the_position_in_the_row_list(self):
        samples, _t = be.edge_conformance(self.part(),
                                          self.rows(Edge((0, 0, 0), (1, 0, 0)),
                                                    Edge((0, 1, 0), (1, 1, 0))),
                                          self.planes, None, arc=1.0)
        assert sorted({s['edge'] for s in samples}) == [0, 1]


# ------------------------------------------------- the surface, not the edge: normals and nets


class BSplineSurface(object):
    """Enough of `Part.BSplineSurface` for `surface_identity` and `bspline_surfaces`."""

    def __init__(self, poles, u_deg=3, v_deg=3, u_knots=(0.0, 1.0), v_knots=(0.0, 1.0),
                 u_mult=(4, 4), v_mult=(4, 4), weights=None, u_per=False, v_per=False):
        self._poles = [[Vec(*p) for p in row] for row in poles]
        self.UDegree, self.VDegree = u_deg, v_deg
        self.NbUPoles, self.NbVPoles = len(poles), len(poles[0])
        self._u_knots, self._v_knots = tuple(u_knots), tuple(v_knots)
        self._u_mult, self._v_mult = tuple(u_mult), tuple(v_mult)
        self._weights = weights
        self._u_per, self._v_per = bool(u_per), bool(v_per)

    def getPoles(self):                                              # noqa: N802 vendor name
        return self._poles

    def getUKnots(self):                                             # noqa: N802 vendor name
        return self._u_knots

    def getVKnots(self):                                             # noqa: N802 vendor name
        return self._v_knots

    def getUMultiplicities(self):                                    # noqa: N802 vendor name
        return self._u_mult

    def getVMultiplicities(self):                                    # noqa: N802 vendor name
        return self._v_mult

    def getWeights(self):                                            # noqa: N802 vendor name
        if self._weights is None:
            raise RuntimeError('non-rational')
        return self._weights

    def isUPeriodic(self):                                           # noqa: N802 vendor name
        return self._u_per

    def isVPeriodic(self):                                           # noqa: N802 vendor name
        return self._v_per


def net(dx=0.0):
    return [[(0.0 + dx, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [(1.0, 0.0, 0.0), (1.0, 1.0, 0.5)]]


class TestSurfaceIdentity:

    def test_the_same_net_is_identical(self):
        out = be.surface_identity(BSplineSurface(net()), BSplineSurface(net()))
        assert out['comparable'] is True
        assert out['identical'] is True
        assert out['worst_pole_mm'] == pytest.approx(0.0)

    def test_a_moved_pole_is_reported_with_its_magnitude(self):
        """**The signature of a `removeSplitter` refit**, which is the whole reason this test
        exists: a refit reproduces the trim boundary and moves the net."""
        out = be.surface_identity(BSplineSurface(net()), BSplineSurface(net(dx=0.004)))
        assert out['identical'] is False
        assert out['same_pole_counts'] is True
        assert out['worst_pole_mm'] == pytest.approx(0.004)

    def test_a_pole_moved_under_the_tolerance_is_still_identical(self):
        out = be.surface_identity(BSplineSurface(net()), BSplineSurface(net(dx=1.0e-9)))
        assert out['identical'] is True

    def test_different_degrees_are_not_identical(self):
        out = be.surface_identity(BSplineSurface(net()), BSplineSurface(net(), u_deg=2))
        assert out['same_degrees'] is False and out['identical'] is False

    def test_different_knots_are_not_identical(self):
        out = be.surface_identity(BSplineSurface(net()), BSplineSurface(net(), u_knots=(0.0, 0.5)))
        assert out['same_knots'] is False and out['identical'] is False

    def test_different_multiplicities_are_not_identical(self):
        out = be.surface_identity(BSplineSurface(net()), BSplineSurface(net(), u_mult=(4, 3)))
        assert out['same_knots'] is False and out['identical'] is False

    def test_different_periodicity_is_not_identical(self):
        """The cowl interior is periodic in `u`; a surface that lost that is a different one."""
        out = be.surface_identity(BSplineSurface(net()), BSplineSurface(net(), u_per=True))
        assert out['same_periodicity'] is False and out['identical'] is False

    def test_a_different_pole_count_stops_before_comparing_poles(self):
        """Subtracting mismatched arrays would raise; the function reports and returns instead."""
        bigger = [[(0.0, 0.0, 0.0)] * 3] * 2
        out = be.surface_identity(BSplineSurface(net()), BSplineSurface(bigger))
        assert out['same_pole_counts'] is False
        assert out['worst_pole_mm'] is None
        assert out['identical'] is False

    def test_a_non_rational_surface_is_treated_as_unit_weights(self):
        """`getWeights` raises on a non-rational B-spline in FreeCAD; two non-rational surfaces
        must still compare equal rather than both falling into the exception path."""
        out = be.surface_identity(BSplineSurface(net()), BSplineSurface(net()))
        assert out['same_weights'] is True

    def test_differing_weights_are_not_identical(self):
        a = BSplineSurface(net(), weights=[[1.0, 1.0], [1.0, 1.0]])
        b = BSplineSurface(net(), weights=[[1.0, 1.0], [1.0, 0.5]])
        out = be.surface_identity(a, b)
        assert out['same_weights'] is False and out['identical'] is False

    def test_an_unreadable_surface_reports_not_comparable_rather_than_raising(self):
        out = be.surface_identity(object(), BSplineSurface(net()))
        assert out['comparable'] is False and out['identical'] is False


class TestBsplineSurfaces:

    def test_only_bspline_faces_are_returned(self):
        shape = Shape([unit_square_at(0.0),
                       Face(BSplineSurface(net()), (0, 0, 0), (1, 1, 1)),
                       Face(Cylinder(), (0, 0, 0), (1, 1, 1))])
        out = be.bspline_surfaces(shape)
        assert [i for i, _s in out] == [1]

    def test_several_faces_on_one_surface_collapse_to_one(self):
        """**Measured, not hypothetical**: the tail's cavity carries three `surface` faces over a
        single fitted patch, so counting faces would report three surfaces where there is one."""
        same = net()
        shape = Shape([Face(BSplineSurface(same), (0, 0, 0), (1, 1, 1)),
                       Face(BSplineSurface(same), (0, 0, 0), (1, 1, 1)),
                       Face(BSplineSurface(same), (0, 0, 0), (1, 1, 1))])
        assert len(be.bspline_surfaces(shape)) == 1

    def test_two_genuinely_different_surfaces_are_both_returned(self):
        shape = Shape([Face(BSplineSurface(net()), (0, 0, 0), (1, 1, 1)),
                       Face(BSplineSurface(net(dx=3.0)), (0, 0, 0), (1, 1, 1))])
        assert len(be.bspline_surfaces(shape)) == 2


class TestAngleBetween:

    def test_identical_directions_are_zero(self):
        assert be.angle_between((0, 0, 1), (0, 0, 1)) == pytest.approx(0.0)

    def test_opposite_directions_are_also_zero(self):
        """**Folded on purpose.** A normal's sign is an orientation convention, so two faces of
        one surface oriented oppositely must read as the same surface."""
        assert be.angle_between((0, 0, 1), (0, 0, -1)) == pytest.approx(0.0)

    def test_perpendicular_is_ninety(self):
        assert be.angle_between((1, 0, 0), (0, 0, 1)) == pytest.approx(90.0)

    def test_a_known_oblique_angle(self):
        assert be.angle_between((1, 0, 0), (1, 1, 0)) == pytest.approx(45.0)
        assert be.angle_between((1, 0, 0), (-1, 1, 0)) == pytest.approx(45.0)

    def test_it_does_not_require_unit_vectors(self):
        assert be.angle_between((0, 0, 7), (0, 3, 0)) == pytest.approx(90.0)

    def test_a_missing_or_zero_direction_is_not_a_number(self):
        assert np.isnan(be.angle_between(None, (0, 0, 1)))
        assert np.isnan(be.angle_between((0, 0, 1), None))
        assert np.isnan(be.angle_between((0, 0, 0), (0, 0, 1)))


class TestFaceNormal:

    def plane_part(self, z=0.0):
        """A `Part` that snaps every point onto the plane `z = z` -- so the recovered normal must
        come out along z whatever offsets were tried."""
        class Vertex(object):
            def __init__(self, x, y, zz):
                self.p = Vec(x, y, zz)

            def distToShape(self, _face):                            # noqa: N802 vendor name
                return (0.0, [(self.p, Vec(self.p.x, self.p.y, z))], None)

        module = types.ModuleType('Part')
        module.Vertex = Vertex
        return module

    def test_a_plane_gives_its_own_normal(self):
        n, residual, used = be.face_normal(self.plane_part(), object(), (0.3, -0.7, 0.0))
        assert used >= 3
        assert be.angle_between(n, (0, 0, 1)) == pytest.approx(0.0, abs=1e-9)
        assert residual == pytest.approx(0.0, abs=1e-12)

    def test_the_normal_offset_is_discarded_rather_than_fitted(self):
        """An offset along the local normal snaps straight back to the point it came from, so it
        carries no tangent information; keeping it would bias the plane fit."""
        n, _r, used = be.face_normal(self.plane_part(), object(), (0.0, 0.0, 0.0))
        assert used == 4, 'the two z offsets should have collapsed and been dropped'
        assert be.angle_between(n, (0, 0, 1)) == pytest.approx(0.0, abs=1e-9)

    def test_too_few_usable_offsets_declines_rather_than_guessing(self):
        """A point pinched between trim boundaries is where this happens, and a wrong normal there
        would be worse than none -- which is why rib-edge creases are taken on the pre-cut face."""
        class Vertex(object):
            def __init__(self, x, y, z):
                self.p = Vec(x, y, z)

            def distToShape(self, _face):                            # noqa: N802 vendor name
                return (0.0, [(self.p, Vec(0.0, 0.0, 0.0))], None)

        module = types.ModuleType('Part')
        module.Vertex = Vertex
        n, residual, used = be.face_normal(module, object(), (0.0, 0.0, 0.0))
        assert n is None and used == 0 and np.isnan(residual)

    def test_a_kernel_refusal_declines_rather_than_fitting_the_offsets(self):
        """**A real bug this test caught.** `_snap_to` fell back to returning the point it was
        given, which for `interior_probes` is right -- losing a probe manufactures a `neither`
        classification -- and for this is wrong: the six unsnapped offsets are not on the face,
        and the plane through them is a unit normal derived from the offset directions alone. It
        came back as `[-0, -0, -1]` with nothing to say it was meaningless. `face_normal` now
        passes `strict`, and a point that could not be snapped is dropped."""
        n, _r, used = be.face_normal(fake_part(raises=True), object(), (0.0, 0.0, 0.0))
        assert n is None and used == 0

    def test_a_probe_still_survives_a_refusal_in_the_non_strict_caller(self):
        """The other half of the same contract: `interior_probes` must keep its point."""
        face = Face(Plane((0, 0, 0), (0, 0, 1)), (0, 0, 0), (3, 3, 0),
                    facets=[triangle((0, 0, 0), (3, 0, 0), (0, 3, 0))])
        assert be.interior_probes(face, Part=fake_part(raises=True)) == [
            pytest.approx((1.0, 1.0, 0.0))]

    def test_the_step_is_a_parameter(self):
        for h in (0.01, 0.05, 0.5):
            n, _r, _u = be.face_normal(self.plane_part(), object(), (0.0, 0.0, 0.0), h=h)
            assert be.angle_between(n, (0, 0, 1)) == pytest.approx(0.0, abs=1e-9), h


def probe_row(d, edge, deg=0.0, face=0, i=0):
    return {'face': face, 'i': i, 'x': 0.0, 'y': 0.0, 'z': 0.0, 'd_fitted_mm': d,
            'edge_mm': edge, 'normal_deg': deg, 'normal_residual_mm': 0.0, 'offsets_used': 6}


class TestSummarizePatch:

    def test_no_probes_reports_so(self):
        assert be.summarize_patch([]) == {'probes': 0}

    def test_the_bands_split_by_distance_to_the_nearest_rib_edge(self):
        """**The measurement that answers the question.** A boundary-value error imposed at a
        patch edge shows up in the patch interior, so the near and far bands differing is the
        signature and every band reading alike is the refutation."""
        rows = [probe_row(1.0e-9, 0.05), probe_row(2.0e-9, 0.2),
                probe_row(3.0e-9, 1.0), probe_row(9.0e-9, 50.0)]
        s = be.summarize_patch(rows, bands=(0.1, 0.5, 2.0))
        labels = [(b['lo_mm'], b['hi_mm'], b['probes']) for b in s['bands']]
        assert labels == [(0.0, 0.1, 1), (0.1, 0.5, 1), (0.5, 2.0, 1), (2.0, float('inf'), 1)]
        assert s['bands'][-1]['worst_mm'] == pytest.approx(9.0e-9)

    def test_an_empty_band_is_omitted_rather_than_reported_as_zero(self):
        s = be.summarize_patch([probe_row(1.0e-9, 50.0)], bands=(0.1, 0.5, 2.0))
        assert [b['probes'] for b in s['bands']] == [1]
        assert s['bands'][0]['lo_mm'] == 2.0

    def test_the_normal_angle_is_summarized_over_the_probes_that_have_one(self):
        """Only `normal_limit` probes carry a normal, so the rest are `nan` and must not drag the
        mean to `nan` or be counted as measured."""
        rows = [probe_row(0.0, 1.0, deg=0.4), probe_row(0.0, 1.0, deg=float('nan')),
                probe_row(0.0, 1.0, deg=0.2)]
        s = be.summarize_patch(rows)
        assert s['normals_measured'] == 2
        assert s['worst_normal_deg'] == pytest.approx(0.4)
        assert s['mean_normal_deg'] == pytest.approx(0.3)

    def test_the_worst_probe_is_handed_back_so_it_can_be_looked_at(self):
        rows = [probe_row(1.0e-9, 1.0, face=2, i=3), probe_row(5.0e-4, 1.0, face=7, i=9)]
        s = be.summarize_patch(rows)
        assert s['worst_at']['face'] == 7 and s['worst_at']['i'] == 9
        assert s['worst_mm'] == pytest.approx(5.0e-4)

    def test_the_bands_are_disjoint_and_cover_every_probe(self):
        rows = [probe_row(0.0, d) for d in (0.0, 0.09, 0.1, 0.49, 0.5, 1.9, 2.0, 1e9)]
        s = be.summarize_patch(rows, bands=(0.1, 0.5, 2.0))
        assert sum(b['probes'] for b in s['bands']) == len(rows)


class TestTablePatch:

    def test_nothing_measured_says_so(self):
        assert 'nothing measured' in be.table_patch({'probes': 0})

    def test_the_identity_verdict_is_printed_per_face(self):
        identity = [{'face': 3, 'identical': True, 'same_degrees': True, 'same_pole_counts': True,
                     'same_knots': True, 'same_weights': True, 'same_periodicity': True,
                     'worst_pole_mm': 0.0}]
        text = be.table_patch({'probes': 0}, identity=identity)
        assert 'cut face 3' in text and 'IDENTICAL' in text

    def test_a_missing_pole_figure_prints_as_not_applicable(self):
        identity = [{'face': 0, 'identical': False, 'same_degrees': True,
                     'same_pole_counts': False, 'same_knots': True, 'same_weights': None,
                     'same_periodicity': True, 'worst_pole_mm': None}]
        text = be.table_patch({'probes': 0}, identity=identity)
        assert 'DIFFERS' in text and 'n/a' in text

    def test_the_bands_and_the_creases_are_printed(self):
        s = be.summarize_patch([probe_row(1.0e-9, 0.05, deg=0.1),
                                probe_row(2.0e-9, 9.0, deg=0.2)])
        creases = [{'edge': 0, 'i': 0, 'z': -1.0, 'crease_deg': 62.5,
                    'normal_residual_mm': 0.0, 'offsets_used': 6},
                   {'edge': 1, 'i': 0, 'z': -2.0, 'crease_deg': 88.0,
                    'normal_residual_mm': 0.0, 'offsets_used': 6}]
        text = be.table_patch(s, creases=creases)
        assert 'distance to the nearest rib edge' in text
        assert 'crease angle' in text and 'tangency' in text
        assert 'min 62.500 deg' in text and 'max 88.000 deg' in text

    def test_creases_that_are_all_unmeasurable_print_nothing_rather_than_nan(self):
        creases = [{'edge': 0, 'i': 0, 'z': -1.0, 'crease_deg': float('nan'),
                    'normal_residual_mm': float('nan'), 'offsets_used': 2}]
        text = be.table_patch(be.summarize_patch([probe_row(0.0, 1.0)]), creases=creases)
        assert 'crease angle' not in text


# ------------------------------------------------------------------------------ summary


def sample(ds, dt, edge=0, i=0, z=0.0):
    return {'edge': edge, 'i': i, 'x': 0.0, 'y': 0.0, 'z': z,
            'd_smooth_mm': ds, 'd_tool_mm': dt, 'tool_face': 0,
            'on': be.classify(ds, dt)}


class TestSummarize:

    def test_an_empty_set_reports_no_samples_rather_than_a_verdict(self):
        assert be.summarize([]) == {'samples': 0}

    def test_the_three_bands_are_disjoint_and_nested_where_they_should_be(self):
        """`within_kernel` is a subset of `within_fuzz`, and `over_fuzz` is its complement."""
        samples = [sample(0.0, 0.0),                        # at kernel tolerance
                   sample(1.0e-6, 0.0),                     # inside the fuzz, over the kernel
                   sample(1.0e-4, 0.0),                     # over the fuzz, under WALL_TOL
                   sample(0.05, 0.0)]                       # over WALL_TOL
        s = be.summarize(samples)
        assert s['samples'] == 4
        assert s['within_kernel'] == 1
        assert s['within_fuzz'] == 2
        assert s['over_fuzz'] == 2
        assert s['within_fuzz'] + s['over_fuzz'] == s['samples']
        assert s['within_kernel'] <= s['within_fuzz']
        assert s['over_wall_tol'] == 1

    def test_the_worst_is_the_worst_of_the_two_distances_per_sample(self):
        """A sample 0.01 mm off the tool and on the surface is as bad as one 0.01 mm off the
        surface and on the tool; taking the max per sample is what makes that true."""
        s = be.summarize([sample(0.009, 0.0), sample(0.0, 0.011)])
        assert s['worst_smooth_mm'] == pytest.approx(0.009)
        assert s['worst_tool_mm'] == pytest.approx(0.011)
        assert s['worst_either_mm'] == pytest.approx(0.011)

    def test_the_worst_sample_is_handed_back_so_it_can_be_looked_at(self):
        s = be.summarize([sample(0.0, 0.0, edge=1, i=2, z=-7.5),
                          sample(0.02, 0.0, edge=3, i=4, z=-9.5)])
        assert s['worst_sample']['edge'] == 3
        assert s['worst_sample']['i'] == 4
        assert s['worst_sample']['z'] == -9.5

    def test_it_counts_distinct_edges_not_samples(self):
        s = be.summarize([sample(0.0, 0.0, edge=5, i=0), sample(0.0, 0.0, edge=5, i=1),
                          sample(0.0, 0.0, edge=6, i=0)])
        assert s['samples'] == 3 and s['edges'] == 2

    def test_the_classification_tally_adds_up(self):
        samples = [sample(0.0, 0.0), sample(0.0, 1.0), sample(1.0, 0.0), sample(1.0, 1.0)]
        s = be.summarize(samples)
        assert s['on'] == {be.ON_BOTH: 1, be.ON_SMOOTH: 1, be.ON_TOOL: 1, be.ON_NEITHER: 1}
        assert sum(s['on'].values()) == s['samples']

    def test_the_bands_are_parameters_so_a_caller_can_re_band_without_re_measuring(self):
        samples = [sample(1.0e-6, 0.0), sample(1.0e-4, 0.0)]
        assert be.summarize(samples, fuzz_tol=1.0e-3)['over_fuzz'] == 0
        assert be.summarize(samples, fuzz_tol=1.0e-7)['over_fuzz'] == 2

    def test_a_sample_over_no_tool_face_is_counted_not_averaged(self):
        """**The regression the first real run exposed.** One `inf` turned every aggregate in the
        summary into `inf` and hid the other 3 173 samples behind it. An `inf` means the point's
        projection fell over no tool face at all -- a finding in its own right on a rib edge,
        which is on a tool face by definition -- so it is counted and kept out of the means."""
        s = be.summarize([sample(0.0, float('inf')), sample(0.0, 0.004)])
        assert s['no_tool_candidate'] == 1
        assert s['worst_tool_mm'] == pytest.approx(0.004)
        assert s['mean_tool_mm'] == pytest.approx(0.004)
        assert np.isinf(s['worst_either_mm'])
        assert 'over no tool face' in be.table(s)

    def test_every_sample_over_no_tool_face_leaves_the_tool_figures_undefined(self):
        s = be.summarize([sample(0.0, float('inf'))])
        assert s['no_tool_candidate'] == 1
        assert np.isnan(s['worst_tool_mm']) and np.isnan(s['mean_tool_mm'])


# ------------------------------------------------------------------------------ the table


class TestTable:

    def test_an_empty_summary_says_so_rather_than_printing_zeros(self):
        assert 'no rib edge samples' in be.table({'samples': 0})

    def test_it_carries_every_band_and_the_worst_location(self):
        s = be.summarize([sample(0.0, 0.0, edge=2, i=3, z=-4.5), sample(0.02, 0.0, edge=1, i=7)])
        text = be.table(s)
        assert 'rib edge' in text
        assert 'fitted interior surface' in text
        assert 'dilated tool face plane' in text
        assert 'WALL_TOL' in text
        assert 'edge 1 point 7' in text

    def test_the_kernel_cross_check_is_printed_when_given(self):
        s = be.summarize([sample(1.0e-3, 0.0)])
        rows = [{'edge': 0, 'i': 0, 'z': -1.0, 'cheap_smooth_mm': 1.0e-3,
                 'kernel_smooth_mm': 1.1e-3, 'kernel_boundary_mm': 1.0e-9,
                 'cheap_tool_mm': 0.0, 'kernel_tool_mm': 2.0e-3}]
        text = be.table(s, agreement=rows)
        assert 'against the kernel' in text
        assert 'kern tool' in text
        assert 'kern bndry' in text

    def test_a_missing_boundary_column_prints_rather_than_raising(self):
        """The column was added after the first real run; a row from before it must still print."""
        s = be.summarize([sample(1.0e-3, 0.0)])
        rows = [{'edge': 0, 'i': 0, 'z': -1.0, 'cheap_smooth_mm': 1.0e-3,
                 'kernel_smooth_mm': 1.1e-3, 'cheap_tool_mm': 0.0, 'kernel_tool_mm': 2.0e-3}]
        assert 'nan' in be.table(s, agreement=rows)


# ------------------------------------------------------------------------- stated constants


class TestConstants:

    def test_the_bands_are_ordered_by_magnitude(self):
        assert be.KERNEL_TOL < be.FUZZ_TOL < be.WALL_TOL

    def test_the_fuzz_band_matches_the_builders_own_rib_cut_fuzz(self):
        """Restated here rather than imported, so it is checked against the source of truth."""
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'src', 'Fuselage', 'freecad', 'cowl_interior.py')
        with open(path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        for name, here in (('RIB_CUT_FUZZ', be.FUZZ_TOL),
                           ('WALL_TOL', be.WALL_TOL),
                           ('CHECK_ARC', be.SAMPLE_ARC)):
            marker = '\n%s = ' % name
            assert marker in text, '%s is no longer a module constant in cowl_interior' % name
            value = float(text.split(marker, 1)[1].split('\n', 1)[0].split('#')[0].strip())
            assert value == pytest.approx(here), '%s drifted: builder %s, here %s' % (
                name, value, here)

    def test_the_box_pad_sits_between_the_fuzz_and_the_wall_tolerance(self):
        """Wide enough never to reject a face the fuzzy cut legitimately snapped a point to, and
        far enough below `WALL_TOL` that it cannot hide a deviation that matters."""
        assert be.FUZZ_TOL < be.BOX_PAD < be.WALL_TOL


# -------------------------------------------------------------------- no vendor import


class TestNoVendorImport:

    def test_the_module_imports_no_vendor_module_anywhere(self):
        """**Anywhere, not just at module level, and the first version of this test was too weak
        to catch it.** The whole package has to import on a sweep worker with no FreeCAD, which
        `test_wall_measure_sweep.TestThePackageIsPortableToTheWorker` enforces by walking every
        module's entire AST. A local `import Part` inside the four functions that need a kernel
        distance passed this test when it looked at `tree.body` alone and failed that one. `Part`
        and `App` now arrive as arguments, the way `locate` and `corpus` already take them."""
        import ast
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'src', 'Fuselage', 'tools', 'wall_measure', 'boolean_edges.py')
        with open(path, 'r', encoding='utf-8') as handle:
            tree = ast.parse(handle.read())
        vendor = {'FreeCAD', 'Part', 'App', 'MeshPart', 'Mesh'}
        found = []
        for node in ast.walk(tree):                          # every scope, not just the top
            if isinstance(node, ast.Import):
                found += [a.name for a in node.names if a.name.split('.')[0] in vendor]
            if isinstance(node, ast.ImportFrom) and not node.level:
                if (node.module or '').split('.')[0] in vendor:
                    found.append(node.module)
        assert found == [], 'vendor import inside the package: %s' % found

    def test_every_function_that_needs_a_kernel_takes_part_as_an_argument(self):
        """The other half of the same rule: having no import is only portable if the kernel is
        reachable some other way, and an argument named `Part` is that way."""
        import inspect
        for name in ('fitted_faces', 'closure_faces', 'surface_deviations', 'smooth_reference',
                     'classify_faces', 'edge_conformance', 'agrees_with_kernel'):
            args = inspect.getfullargspec(getattr(be, name)).args
            assert 'Part' in args, '%s cannot reach a kernel' % name
