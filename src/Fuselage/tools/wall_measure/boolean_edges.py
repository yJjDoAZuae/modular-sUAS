"""Does the rib cut's output lie on the two surfaces it is a boolean of?

**The question this answers.** Section 4.2 of `cowl_interior_surface.md` evaluates

    erode(A - B, t) == erode(A, t) - dilate(B, t)

in three dimensions precisely so that a rib's crease is **not** fitted into the interior
surface. The surface is fitted through the un-notched blank's erosion alone, and the dilated rib
tool is subtracted afterwards as a solid, so "the creases then arrive as the edges of a boolean
between two well-formed solids, which is where a crease belongs" (`dilated_notches`).

That argument is about where a crease *comes from*. It says nothing about whether the crease the
kernel actually produced is in the right place. The set identity

    boundary(S - T)  is a subset of  boundary(S) union boundary(T)

is what makes the construction correct, and nothing in the build has ever checked it. Three
things in the cut are entitled to move geometry and none of them is bounded by anything the wall
is measured against:

* `Shape.cut(..., RIB_CUT_FUZZ)` is a **fuzzy** boolean. `RIB_CUT_FUZZ` = 1e-5 mm is an explicit
  license for the kernel to snap near-coincident geometry together, and its own note records
  doing exactly that -- "a snap of the near-tangent geometry together, not a bulk change".
* `removeSplitter()` (`ShapeUpgrade_UnifySameDomain`) merges faces it judges to share a surface
  and **refits** the merged boundary. On a B-spline face that is a genuine change of geometry,
  and it runs on both operands as well as on the result.
* a near-tangency between the dilated tool and the interior surface is already documented here
  (`RIB_CUT_FUZZ`, the `Diag12Safe` sliver at `U` = 0.75), and a tangency is the condition under
  which a trimming curve is worst determined.

So the check is: sample the cut cavity's own rib edges, and measure each sample against **both**
references it must satisfy at once -- the fitted interior surface and the dilated tool's face
plane. A rib edge is the intersection of those two surfaces, so a sample on it is on both, and
any sample that is on neither, or on only one, is geometry the boolean invented.

**The two references are measured in the cheap way each one allows, and both are exact for it.**

* The dilated tool is a **union of translated polyhedra** (`dilated_notches`: "every piece is the
  original polyhedron"), so every face of it is planar and the distance from a point to a face's
  surface is one dot product. `plane_deviations` does that in `numpy` over all faces at once,
  after a bounding-box filter picks the faces that could plausibly carry the point. This is the
  "offset rib plane" in the literal sense: each face of `dilate(B, t)` is a face of `B` pushed
  out by `t`, or part of the rounding between two of them.
* The fitted interior is a **single** B-spline surface in every configuration built so far
  (`feature_stations`: all twelve soak walls report `patch 1/1`), so the distance from a point to
  it is one projection, not a search over faces.

**A plane is not a face, and the bounding-box filter is what stands in for the trim.** A point
far outside a face's trimmed region but on its plane reads zero deviation from that plane. The
box filter rejects those, but a box is not a trim either, so `plane_deviations` can be optimistic
by admitting a point that lies on the plane just outside the face. That is why `agrees_with_kernel`
exists: it re-measures the worst samples with `distToShape` against the real trimmed faces, which
is authoritative and which no caller should skip.

**Nothing here imports a vendor module anywhere, not even inside a function.** The whole
`wall_measure` package has to import on a sweep worker that has no FreeCAD, and
`test_wall_measure_sweep.TestThePackageIsPortableToTheWorker` walks every module's entire AST to
enforce it -- not just the module-level imports. A first version of this module put `import Part`
inside the four functions that need a kernel distance, which is the convention elsewhere in the
project for a vendor-side script and is the wrong one here; that test caught all four. So `Part`
and `App` arrive as arguments, the way `locate` and `corpus` already take them.
"""
import numpy as np

#: The kernel's own coincidence tolerance (`Precision::Confusion`), in mm. A point genuinely on a
#: surface reads below this; anything above it the kernel considers a real separation.
KERNEL_TOL = 1.0e-7

#: `cowl_interior.RIB_CUT_FUZZ`, in mm: what the fuzzy rib cut is explicitly allowed to move.
#: Restated rather than imported because this module must stay free of the vendor-side module.
FUZZ_TOL = 1.0e-5

#: `cowl_interior.WALL_TOL`, in mm: the scale at which a deviation stops being bookkeeping and
#: starts being a wall that is the wrong thickness.
WALL_TOL = 0.01

#: Arc length, in mm, between samples along an edge. `cowl_interior.CHECK_ARC`'s value, for the
#: same reason: a third of the wall, so a chord's sag is well inside the quantity being measured.
SAMPLE_ARC = 0.20

#: How far outside a face's bounding box a point's **in-plane projection** may sit and still be
#: considered a candidate for lying on that face, in mm. Two orders above `FUZZ_TOL` so the filter
#: never rejects a face the fuzzy cut legitimately snapped a point to, and an order below
#: `WALL_TOL` so it cannot admit a face a wall-sized distance away in plane.
#:
#: **It pads the projection, not the point, and the distinction is the whole filter.** A planar
#: face's bounding box is flat -- zero thickness along its own normal -- so padding the raw point
#: against it rejects any point further off the plane than `pad`, which is exactly the set of
#: points this module exists to find. The first version did that and a test caught it: a sample
#: 0.25 mm off a face read `inf` (no candidate) instead of 0.25 mm. Projecting first asks the
#: right question -- is the point *over* the face -- and leaves the distance being measured
#: unfiltered.
BOX_PAD = 1.0e-3

#: Face classifications `classify_face` returns.
#:
#: **`lid` is separate from `surface`, and conflating them measured the wrong edges.** Both are
#: part of the smooth operand's boundary, so for the question "did the boolean invent this face"
#: they are the same thing. But a rib crease is where a tool plane cuts the **fitted surface**,
#: and an edge where a tool plane meets a *closing plane* is something else entirely -- it is
#: where the rib cut runs out to the cell boundary. A first version called both `smooth`, and on a
#: real `nose_cowl_shell` cavity at `U` = 0.5 every edge it reported as a rib crease was of the
#: second kind: 2.411 mm from the fitted surface, exactly on a side cap, at `x` = 0 on the cell's
#: own symmetry plane.
ON_SURFACE = 'surface'      #: On the fitted interior surface.
ON_LID = 'lid'              #: On one of the lids or side caps that close the fitted patch.
ON_TOOL = 'tool'            #: On the dilated rib tool's boundary.
ON_AMBIGUOUS = 'ambiguous'  #: Within tolerance of more than one -- a tangency, or a coincidence.
ON_NEITHER = 'neither'      #: On none of them: geometry the boolean invented.

#: Sample classifications `classify` returns. A sample on a rib edge is asked only about the two
#: surfaces that edge is the intersection of, so this set is the two-way one.
ON_BOTH = 'both'            #: On the fitted surface and on a tool face: what a rib edge is.
ON_SMOOTH = 'smooth'        #: On the fitted surface only.


def plane_set(shape):
    """Every planar face of `shape`, as `(origins, normals, boxes)` arrays plus the face list.

    Raises `ValueError` on a non-planar face rather than skipping it. The dilated tool is a union
    of polyhedra and has no curved face; one appearing would mean the tool is not what
    `dilated_notches` says it is, and silently dropping it would make every distance below an
    over-estimate of how well the cut conforms -- the optimistic direction.

    **Only the tool is read this way.** The smooth operand's boundary is a deliberate mix, and
    `smooth_reference` measures it with the kernel instead; see `closure_faces`.
    """
    faces, origins, normals, boxes = [], [], [], []
    for index, face in enumerate(shape.Faces):
        surf = face.Surface
        if type(surf).__name__ != 'Plane':
            raise ValueError('face %d is a %s, not a Plane; `plane_deviations` is only exact '
                             'for a polyhedron' % (index, type(surf).__name__))
        pos, axis = surf.Position, surf.Axis
        bb = face.BoundBox
        faces.append(face)
        origins.append((pos.x, pos.y, pos.z))
        normals.append((axis.x, axis.y, axis.z))
        boxes.append((bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    if not faces:
        raise ValueError('the shape has no planar faces')
    return (faces, np.asarray(origins, dtype=float), np.asarray(normals, dtype=float),
            np.asarray(boxes, dtype=float))


#: The largest intermediate `plane_deviations` will allocate, in array elements. Matches
#: `candidates.MAX_BLOCK`: the same arithmetic there, unbounded, once asked for 37 TB.
MAX_BLOCK = 25000000

#: Chord tolerance, in mm, for the tessellation `interior_probes` takes its probe points from.
#: Only has to be fine enough that a facet centroid is near the face; `interior_probes` snaps it
#: on exactly afterwards, so this trades facet count against nothing else.
PROBE_DEFLECTION = 0.01


def interior_probes(face, count=4, deflection=PROBE_DEFLECTION, Part=None):
    """Points strictly inside `face` and exactly on it, from its own tessellation's largest facets.

    **Vertices are not probe points, and using them is what broke the first version of this
    module.** A face's vertices are shared with its neighbors, so a vertex between a smooth face
    and a tool face is on *both* operands by construction. Probing there classified 35 of a nose
    cavity's 60 faces as near more than one boundary, which then made every edge touching one of
    them look like a rib edge: an end-lid edge 22.5 mm from the nearest tool was reported as a rib
    crease. The parametric center is no good either -- on a trimmed face it can fall outside the
    trim.

    A triangle's centroid is interior to the face, and taking the largest facets first keeps the
    probe away from the boundary; a sliver facet along a trim curve has a centroid within a
    tolerance of it.

    **But a centroid is on the tessellation, not on the face, and that broke the second version.**
    A facet is a chord, so its centroid sits inside a curved face by up to the deflection -- exact
    for a plane, which is why the tool and lid faces classified correctly all along, and about
    0.1 mm off for the fitted B-spline at the deflection first used. Against a 1e-5 mm tolerance
    that put **zero** of a nose cavity's 60 faces on the fitted surface and 3 on nothing at all,
    with the 45 real rib creases showing up as `neither + tool`. Given `Part`, each centroid is
    moved to the nearest point *on the face* with the kernel, which is exact and stays inside the
    trim; without it the unsnapped centroids come back, which is only useful for testing the facet
    arithmetic itself.
    """
    verts, facets = face.tessellate(float(deflection))
    ranked = []
    for tri in facets:
        if len(tri) != 3:
            continue
        a, b, c = (verts[i] for i in tri)
        area = 0.5 * float(b.sub(a).cross(c.sub(a)).Length)
        mid = ((a.x + b.x + c.x) / 3.0, (a.y + b.y + c.y) / 3.0, (a.z + b.z + c.z) / 3.0)
        ranked.append((area, mid))
    ranked.sort(key=lambda row: -row[0])
    picked = [mid for _area, mid in ranked[:int(count)]]
    return [_snap_to(Part, face, p) for p in picked] if Part is not None else picked


def _snap_to(Part, face, point, strict=False):
    """`point` moved to the nearest point on `face`, by the kernel.

    **The two callers want opposite things on a refusal, and conflating them was a bug a test
    caught.** `interior_probes` wants the point kept: an empty probe list classifies its face
    `neither`, the one answer that means the boolean invented something, so losing a probe would
    manufacture the very finding this module reports. `face_normal` must have it dropped: an
    unsnapped offset is not on the face, and fitting a plane through six of them returns a
    confident normal computed from nothing but the offset directions -- which is what it did, as
    a unit vector, with no indication anything had failed.

    So `strict` returns `None` instead of falling back, and `face_normal` passes it.
    """
    try:
        pairs = Part.Vertex(float(point[0]), float(point[1]), float(point[2])).distToShape(face)[1]
        on_face = pairs[0][1]
        return (float(on_face.x), float(on_face.y), float(on_face.z))
    except Exception:                                               # noqa: BLE001 kernel refusal
        return None if strict else point


def plane_deviations(points, origins, normals, boxes, pad=BOX_PAD, max_block=MAX_BLOCK):
    """Per point, the distance to the nearest candidate face's plane, and which face that was.

    A face is a candidate for a point when the point's **projection onto that face's plane** is
    inside the face's bounding box grown by `pad` -- the point is over the face. See `BOX_PAD` on
    why the projection and not the point, and the module note on why a box stands in for the trim
    here and why the result has to be checked against the kernel.

    Returns `(distance, index)`, both length-`len(points)`. A point with no candidate face gets
    `inf` and `-1`.

    **Chunked over points, because the intermediate is the product of both counts.** The
    projection array is `points x faces x 3` floats, so a nose cavity's 187 samples against one
    tool's 152 faces is nothing while a tail's thousands against eleven tools' thousands would be
    hundreds of megabytes. `candidates._segment_distances` was already caught by the same
    arithmetic -- it asked for 37 TB -- and `MAX_BLOCK` is the same bound restated here.
    """
    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    n_faces = max(len(origins), 1)
    rows = max(int(max_block // (3 * n_faces)), 1)
    if len(pts) > rows:
        best = np.empty(len(pts), dtype=float)
        index = np.empty(len(pts), dtype=int)
        for start in range(0, len(pts), rows):
            stop = min(start + rows, len(pts))
            b, i = plane_deviations(pts[start:stop], origins, normals, boxes, pad=pad,
                                    max_block=max_block)
            best[start:stop], index[start:stop] = b, i
        return best, index
    # (n_points, n_faces): signed distance along each plane's normal, then its magnitude.
    delta = pts[:, None, :] - origins[None, :, :]
    signed = np.einsum('pfk,fk->pf', delta, normals)
    dist = np.abs(signed)
    # Drop each point onto each plane before the box test, so the box only ever constrains the
    # in-plane position and never the distance being measured.
    projected = pts[:, None, :] - signed[:, :, None] * normals[None, :, :]
    inside = np.ones(dist.shape, dtype=bool)
    for k in range(3):
        inside &= (projected[:, :, k] >= boxes[None, :, k] - pad)
        inside &= (projected[:, :, k] <= boxes[None, :, 3 + k] + pad)
    masked = np.where(inside, dist, np.inf)
    index = np.argmin(masked, axis=1)
    best = masked[np.arange(len(pts)), index]
    index = np.where(np.isfinite(best), index, -1)
    return best, index


def fitted_faces(Part, smooth):
    """The **pre-cut** solid's own B-spline face(s), as the reference `surface_deviations` uses.

    **Which copy of the surface is the reference, and it took two wrong answers to settle.** The
    question is whether a rib edge lies on the fitted interior surface, so the reference must be
    that surface without the tool's trim on it -- measuring against the *cut* cavity's own B-spline
    face would compare the edge to its own trim boundary and read zero wherever it had gone. Two
    ways of getting an untrimmed copy were tried against a real `nose_cowl_shell` cavity at
    `U` = 0.5, and both reported the rib edges **2.411 mm** off a surface the kernel put them
    6.9e-18 mm from:

    1. `surface.projectPoint(Point=v, Method='LowerDistance')`, and `parameter()` plus `value()`
       behind it. The interior surface is periodic in `u`, so a parameter solve settling on a
       local rather than a global minimum looks exactly like this.
    2. `surface.toShape()`, which rebuilds the surface over its own natural parameter range rather
       than the range the fit actually used.

    `smooth`'s own face is neither reconstruction. It is the operand the boolean was handed, it is
    not trimmed by the tool because the cut has not happened to it, and `distToShape` against it
    is the measure `agrees_with_kernel` had been quietly getting right all along -- which is what
    identified both failures above. Returned as a compound so a caller pays for building it once.
    """
    faces = [f for f in smooth.Faces if type(f.Surface).__name__ == 'BSplineSurface']
    if not faces:
        raise ValueError('the pre-cut solid has no B-spline face: this is not a fitted interior')
    return Part.makeCompound(faces)


def surface_deviations(Part, points, shape):
    """Per point, the kernel distance to `shape`.

    `shape` is `fitted_faces(Part, smooth)` for the conformance question, or
    `closure_faces(Part, smooth)` for the classification one; see `fitted_faces` for why no
    reconstruction of the surface is an acceptable substitute for either.
    """
    out = np.empty(len(points), dtype=float)
    for i, p in enumerate(points):
        vertex = Part.Vertex(float(p[0]), float(p[1]), float(p[2]))
        out[i] = float(vertex.distToShape(shape)[0])
    return out


def closure_faces(Part, smooth):
    """Everything on the fitted solid's boundary that is **not** the fitted surface.

    **Three kinds of face, not two, and the third was found by elimination.** `assemble_patch`
    closes each patch with planar lids and side caps, and then extrudes the two end lids outward
    past the part (`END_OVERRUN`) so the cavity does not leave the cowl's openings skinned over.
    Those extrusions contribute `SurfaceOfExtrusion` side walls -- neither the B-spline nor a
    plane. A version that read this side as a plane set discarded them, and the two faces
    concerned came back `neither`, the one classification that means the boolean invented
    something. Measured on a nose cavity at `U` = 0.5: 1.96e-2 and 1.01e-1 mm from the fitted
    surface, 1.68e-2 and 3.64e-2 mm from the nearest lid plane, and over no tool face at all.

    Taken as a compound and measured with the kernel rather than enumerated by surface type, so a
    fourth kind appearing later is handled rather than silently dropped. Classification is a few
    probes a face, so the kernel's cost does not matter here; the tool side, which every edge
    sample is measured against, keeps the exact plane arithmetic.
    """
    faces = [f for f in smooth.Faces if type(f.Surface).__name__ != 'BSplineSurface']
    if not faces:
        raise ValueError('the pre-cut solid has no closing faces: it cannot be a closed patch')
    return Part.makeCompound(faces)


def smooth_reference(Part, smooth):
    """The fitted interior solid's boundary, split into the things it is made of.

    Returns `(surface, fitted, closure)`: the single fitted B-spline, that solid's own B-spline
    face(s) to measure against (`fitted_faces`), and everything else on its boundary
    (`closure_faces`). **Classification needs both parts** -- a lid is on this operand's boundary
    just as much as the B-spline is, and a version that measured only against the B-spline called
    every lid `neither`.

    Conformance, unlike classification, is measured against the fitted surface alone: a rib edge
    is where a tool plane cuts *that*, and that is the thing the question is about.
    """
    return smooth_surface_of(smooth), fitted_faces(Part, smooth), closure_faces(Part, smooth)


def classify_faces(Part, cut, smooth_reference_pair, tool_planes, tol=FUZZ_TOL, probes=4):
    """Which operand each face of `cut` lies on, as a list of dicts, one per face.

    **Classified by measurement, not by surface type.** Asking whether a face is a B-spline or a
    plane would be cheaper and would be wrong twice over: the smooth solid contributes planar lids
    and side caps as well as its B-spline, so a plane is not evidence of a tool; and
    `removeSplitter` is entitled to refit either operand's faces, which is the very thing being
    checked.

    Probed at `interior_probes` points -- strictly inside the face, never on its boundary; see
    that function for what probing vertices did instead. This is not a sampling of the face:
    `edge_conformance` does the sampling, on the edges, which is where the question is.
    """
    _surface, surface_faces, closure = smooth_reference_pair
    _tf, t_origins, t_normals, t_boxes = tool_planes
    rows = []
    for index, face in enumerate(cut.Faces):
        pts = interior_probes(face, probes, Part=Part)
        if not pts:
            rows.append({'face': index, 'surface': type(face.Surface).__name__,
                         'd_smooth_mm': float('nan'), 'd_tool_mm': float('nan'),
                         'on': ON_NEITHER, 'probes': 0})
            continue
        d_tool, _which = plane_deviations(pts, t_origins, t_normals, t_boxes)
        d_surface = surface_deviations(Part, pts, surface_faces)
        d_lid = surface_deviations(Part, pts, closure)
        near_surface = float(np.min(d_surface))
        near_lid = float(np.min(d_lid))
        near_tool = float(np.min(d_tool))
        rows.append({'face': index,
                     'surface': type(face.Surface).__name__,
                     # The smooth operand's boundary is the fitted surface *or* a closing plane.
                     'd_smooth_mm': min(near_surface, near_lid),
                     'd_surface_mm': near_surface,
                     'd_lid_mm': near_lid,
                     'd_tool_mm': near_tool,
                     'on': classify_face(near_surface, near_lid, near_tool, tol),
                     'probes': len(pts)})
    return rows


def classify_face(d_surface, d_lid, d_tool, tol=FUZZ_TOL):
    """Which boundary a face at these three distances lies on.

    Three separate things, not two: see the `ON_SURFACE` block above for why a lid cannot be
    folded into the fitted surface, and what folding them measured instead.
    """
    hits = [name for name, d in ((ON_SURFACE, d_surface), (ON_LID, d_lid), (ON_TOOL, d_tool))
            if d <= tol]
    if len(hits) > 1:
        return ON_AMBIGUOUS
    return hits[0] if hits else ON_NEITHER


def classify(d_smooth, d_tool, tol=FUZZ_TOL):
    """Which of the two surfaces a rib-edge sample at these distances lies on.

    `d_smooth` here is the distance to the **fitted surface**, not to the smooth operand's whole
    boundary: a rib edge is the intersection of that surface with a tool face, so those are the
    two things a sample on it has to satisfy, and `ON_BOTH` is the answer a conformant one gives.
    """
    s, t = d_smooth <= tol, d_tool <= tol
    if s and t:
        return ON_BOTH
    if s:
        return ON_SMOOTH
    if t:
        return ON_TOOL
    return ON_NEITHER


def _edge_key(edge, quantum=KERNEL_TOL):
    """A key two faces sharing an edge agree on. Endpoints sorted, so orientation does not matter.

    Two faces of one solid share the *same* underlying edge, so their coordinates are identical
    rather than merely close, and any quantum separates distinct edges. Keyed geometrically rather
    than through `ancestorsOfType` because that is a search over every face per edge, and a tail
    cavity has thousands of each.
    """
    def q(v):
        return (int(round(v.x / quantum)), int(round(v.y / quantum)), int(round(v.z / quantum)))
    ends = tuple(sorted(q(v.Point) for v in edge.Vertexes))
    mid = edge.valueAt(0.5 * (edge.FirstParameter + edge.LastParameter))
    return (ends, q(mid), int(round(edge.Length / quantum)))


def face_adjacency(cut, face_rows):
    """Group `cut`'s edges by the faces that share them. Returns `(groups, nonmanifold)`.

    `groups` maps an edge key to `{'edge': shape, 'faces': [index, ...]}`. `nonmanifold` counts
    the keys whose face count is not two, which on a closed solid should be none -- reported
    rather than ignored, because a key that failed to match is a rib edge this check would then
    silently never look at.
    """
    groups = {}
    for row in face_rows:
        index = row['face']
        for edge in cut.Faces[index].Edges:
            key = _edge_key(edge)
            slot = groups.setdefault(key, {'edge': edge, 'faces': []})
            if index not in slot['faces']:
                slot['faces'].append(index)
    nonmanifold = sum(1 for slot in groups.values() if len(slot['faces']) != 2)
    return groups, nonmanifold


def rib_edges(cut, face_rows, groups=None):
    """The edges of `cut` where a `surface` face meets a `tool` face: the rib creases themselves.

    Three kinds of edge are deliberately not here, and each would be a different question:

    * two faces of the same class -- a seam within one boundary, which the boolean did not create;
    * `tool` against `lid` -- where the rib cut runs out to the cell boundary, not a crease in the
      interior surface. On a real nose cavity at `U` = 0.5 **all four** edges a first version
      reported were of this kind, 2.411 mm from the fitted surface and exactly on a side cap;
    * anything touching an `ambiguous` or `neither` face. `ambiguous` means within tolerance of
      more than one boundary -- a tangency, or a coincidence -- and treating it as supplying every
      side it is near is what let an end-lid edge 22.5 mm from the nearest tool be called a rib
      crease. Both stay visible in the classification tally instead of manufacturing edges here.
    """
    by_index = {row['face']: row['on'] for row in face_rows}
    if groups is None:
        groups, _nm = face_adjacency(cut, face_rows)
    out = []
    for key, slot in groups.items():
        classes = [by_index.get(i) for i in slot['faces']]
        if ON_SURFACE in classes and ON_TOOL in classes:
            out.append({'edge': slot['edge'], 'faces': list(slot['faces']),
                        'classes': sorted(c for c in classes if c),
                        'length_mm': float(slot['edge'].Length)})
    out.sort(key=lambda row: -row['length_mm'])
    return out


def edge_kinds(cut, face_rows, groups=None):
    """Every edge group tallied by the pair of face classes that share it.

    Reported beside `rib_edges` so the set it selected can be seen against the set it did not --
    an unexpected pairing, or a `surface`/`tool` count of zero, is then visible rather than
    looking like a clean result.
    """
    by_index = {row['face']: row['on'] for row in face_rows}
    if groups is None:
        groups, _nm = face_adjacency(cut, face_rows)
    tally = {}
    for slot in groups.values():
        key = ' + '.join(sorted(str(by_index.get(i)) for i in slot['faces']))
        tally[key] = tally.get(key, 0) + 1
    return tally


def edge_conformance(Part, edge_rows, tool_planes, smooth_faces, arc=SAMPLE_ARC,
                     max_points=200000):
    """Sample every rib edge by arc length and measure each sample against both references.

    **Measured against the fitted surface, not against the smooth solid's boundary.** A rib edge
    is where a tool plane cuts that surface, so the surface is what it must lie on; a lid plane
    happening to pass nearby is not a reason to call the edge conformant.

    Returns `(samples, truncated)`. Each sample carries the two distances, the classification, and
    where it is, so a worst point can be looked at rather than only counted. `truncated` is the
    number of edges dropped on the `max_points` budget, so a partial answer is never mistaken for
    a complete one. Edges are taken longest-first (`rib_edges` sorts them), so a truncated run
    drops the shortest rather than whatever came last.
    """
    _faces, origins, normals, boxes = tool_planes
    samples, budget, truncated = [], int(max_points), 0
    for ei, row in enumerate(edge_rows):
        edge = row['edge']
        n = max(int(edge.Length / float(arc)) + 1, 2)
        if n > budget:
            truncated += 1
            continue
        budget -= n
        pts = [(p.x, p.y, p.z) for p in edge.discretize(Number=n)]
        d_tool, which = plane_deviations(pts, origins, normals, boxes)
        d_smooth = surface_deviations(Part, pts, smooth_faces)
        for k, p in enumerate(pts):
            samples.append({'edge': ei, 'faces': row['faces'], 'i': k,
                            'x': p[0], 'y': p[1], 'z': p[2],
                            'd_smooth_mm': float(d_smooth[k]),
                            'd_tool_mm': float(d_tool[k]),
                            'tool_face': int(which[k]),
                            'on': classify(float(d_smooth[k]), float(d_tool[k]))})
    return samples, truncated


# ----------------------------------------------------------------------------------------------
# Is the surface the boolean handed back the surface it was given? Position alone cannot say.
#
# A rib edge sitting exactly on both surfaces (`edge_conformance`) is necessary and not
# sufficient. It constrains the *trim curve*, not the surface the curve is drawn on, and the two
# are independent: `removeSplitter` (`ShapeUpgrade_UnifySameDomain`) refits what it merges, and a
# refit that reproduces the trim boundary to the kernel's tolerance can still differ from the
# original in the patch interior, where nothing pins it. That is a boundary-value problem, and the
# interior is exactly where a B-spline has freedom -- so an error imposed at a patch edge shows up
# as a displacement in the middle of the patch, not at the edge where it was introduced.
#
# Three tests, strongest first:
#
# 1. `surface_identity` compares the control nets. If they match, the boolean trimmed and did not
#    refit, and no interior displacement is possible -- a trim cannot move the surface it trims.
#    Exact, parameter-free, and it settles the question outright when it holds.
# 2. `patch_deviation` samples the cut surface's interior densely and measures position against
#    the pre-cut face, tabulated by distance to the nearest rib edge. Independent of (1), so it
#    catches a comparison made against the wrong pair of faces, and the distance tabulation is
#    what would show propagation inward from an edge.
# 3. the same probes' **normals**. A normal difference is first order in a surface perturbation
#    where a position difference is second order, so this is the sensitive one: two surfaces can
#    agree to 1e-9 mm in position and still disagree visibly in slope.
# ----------------------------------------------------------------------------------------------

#: Step, in mm, for the parameter-free normal. Small enough that the chord error over it is a
#: fraction of a degree on these radii, large enough that the snapped offsets are not dominated by
#: the kernel's own 1e-7 mm resolution.
#:
#: **The resolution that buys is measured, not predicted.** `face_normal` returns the
#: non-coplanarity of its snapped neighbours as a residual, and over 187 rib-edge samples on a
#: `nose_cowl_shell` cavity at `U` = 0.5 that residual ran 4e-20 to 7.7e-05 mm, median
#: 1.9e-05 mm -- which over `h` = 0.05 mm is a **median 0.022 deg and a worst 0.088 deg**. So this
#: resolves a normal difference of about a tenth of a degree and no better, which is ample for
#: telling a refit from a trim and far too coarse to quote a crease angle to three decimals.
NORMAL_STEP = 0.05

#: Directions offset before snapping, for `face_normal`. Six, because an offset along the local
#: normal snaps straight back to the point it came from and carries no tangent information; with
#: all six axes at least four always survive, whatever the surface's orientation.
NORMAL_DIRECTIONS = ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                     (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0))


def bspline_surfaces(shape):
    """Every distinct B-spline surface on `shape`, as `[(face_index, surface), ...]`.

    Distinct by control net, not by face: a cut can leave one surface carrying several faces, and
    the tail's cavity does exactly that -- three `surface` faces over one fitted patch.
    """
    out = []
    for index, face in enumerate(shape.Faces):
        surf = face.Surface
        if type(surf).__name__ != 'BSplineSurface':
            continue
        if not any(_same_surface(surf, known) for _i, known in out):
            out.append((index, surf))
    return out


def surface_identity(a, b, atol=KERNEL_TOL):
    """Do two B-spline surfaces have the same control net? The exact form of the question.

    **This is the test that settles whether a boundary-value error is even possible.** A boolean
    that only trims leaves the surface untouched, so its poles, knots and weights are those of the
    operand it was given, and no interior displacement can exist. A `removeSplitter` refit changes
    them, and then the interior is unpinned and has to be measured.

    Compared field by field rather than by a single verdict, so a near-match reports *which* part
    differs -- a changed knot vector and a nudged pole are different failures.
    """
    out = {'same_degrees': None, 'same_pole_counts': None, 'same_knots': None,
           'same_weights': None, 'same_periodicity': None, 'worst_pole_mm': None,
           'identical': False, 'comparable': False}
    try:
        out['same_degrees'] = (a.UDegree, a.VDegree) == (b.UDegree, b.VDegree)
        out['same_pole_counts'] = (a.NbUPoles, a.NbVPoles) == (b.NbUPoles, b.NbVPoles)
        out['same_periodicity'] = (bool(a.isUPeriodic()), bool(a.isVPeriodic())) == \
                                  (bool(b.isUPeriodic()), bool(b.isVPeriodic()))
        out['same_knots'] = (_close(a.getUKnots(), b.getUKnots(), atol)
                             and _close(a.getVKnots(), b.getVKnots(), atol)
                             and list(a.getUMultiplicities()) == list(b.getUMultiplicities())
                             and list(a.getVMultiplicities()) == list(b.getVMultiplicities()))
        out['comparable'] = True
        if not out['same_pole_counts']:
            return out
        pa = _pole_array(a)
        pb = _pole_array(b)
        out['worst_pole_mm'] = float(np.max(np.linalg.norm(pa - pb, axis=-1)))
        out['same_weights'] = _close(np.ravel(_weight_array(a)), np.ravel(_weight_array(b)), atol)
        out['identical'] = bool(out['same_degrees'] and out['same_pole_counts']
                                and out['same_knots'] and out['same_weights']
                                and out['same_periodicity']
                                and out['worst_pole_mm'] <= atol)
    except Exception:                                               # noqa: BLE001 kernel/API
        pass
    return out


def congruent_identity(a, b, atol=KERNEL_TOL):
    """Are two B-spline surfaces the same surface **up to a rigid motion**? For the mirror steps.

    `surface_identity` compares poles where they stand, which is the right question for a boolean
    that is supposed to leave its operand alone. It is the wrong question after
    `mirror_across_cell`: a mirrored copy's poles are *reflected*, so identical coordinates would
    mean the mirror had not moved anything. What must hold instead is that the copy is the original
    carried rigidly -- same parameterization, same shape, a different place.

    **A mirror is an isometry, so the control net's own internal distances are preserved exactly.**
    This compares the step lengths along each parameter direction, pole by pole:
    `|P[i+1][j] - P[i][j]|` and `|P[i][j+1] - P[i][j]|`. A refit moves poles relative to each other
    and changes these; a reflection, rotation or translation cannot touch them. No plane of
    reflection has to be known or guessed, which matters because a finished wall carries several
    copies composed through several cell planes and the composition is not recoverable from the
    saved shape.

    The lattice may also be indexed the other way round in either direction, because a reflection
    reverses orientation and the kernel may renumber, so the four flip combinations are tried and
    the closest reported. Transposition is **not** tried: swapping `u` for `v` is a
    reparameterization rather than a rigid motion, and accepting it would hide the kind of change
    this exists to find.

    Returns the same shape of dict as `surface_identity` with `worst_step_mm` in place of
    `worst_pole_mm`, so one formatter prints either.
    """
    out = {'same_degrees': None, 'same_pole_counts': None, 'same_knots': None,
           'same_weights': None, 'same_periodicity': None, 'worst_step_mm': None,
           'identical': False, 'comparable': False}
    try:
        out['same_degrees'] = (a.UDegree, a.VDegree) == (b.UDegree, b.VDegree)
        out['same_pole_counts'] = (a.NbUPoles, a.NbVPoles) == (b.NbUPoles, b.NbVPoles)
        out['same_periodicity'] = (bool(a.isUPeriodic()), bool(a.isVPeriodic())) == \
                                  (bool(b.isUPeriodic()), bool(b.isVPeriodic()))
        out['same_knots'] = (_close(a.getUKnots(), b.getUKnots(), atol)
                             and _close(a.getVKnots(), b.getVKnots(), atol)
                             and list(a.getUMultiplicities()) == list(b.getUMultiplicities())
                             and list(a.getVMultiplicities()) == list(b.getVMultiplicities()))
        out['comparable'] = True
        if not out['same_pole_counts']:
            return out
        out['worst_step_mm'] = _worst_step_difference(_pole_array(a), _pole_array(b))
        out['same_weights'] = _close(np.ravel(_weight_array(a)), np.ravel(_weight_array(b)), atol)
        out['identical'] = bool(out['same_degrees'] and out['same_pole_counts']
                                and out['same_knots'] and out['same_weights']
                                and out['same_periodicity']
                                and out['worst_step_mm'] is not None
                                and out['worst_step_mm'] <= atol)
    except Exception:                                               # noqa: BLE001 kernel/API
        pass
    return out


#: Classifications `anomalous_edges` separates an edge group into.
#: One face, and that face's surface is **periodic**: the closing seam signature.
#:
#: **Periodicity is the discriminator, and an earlier version used the occurrence count instead --
#: wrongly.** It classified a seam as "one face carrying the edge twice", on the assumption that
#: `Face.Edges` lists a seam once per orientation. Measured on a cylinder through the test bridge,
#: it does **not**: the lateral face lists its seam edge exactly once, the same as any other edge.
#: So the count cannot separate a seam from an open boundary, and neither can the kernel's
#: `ancestorsOfType`, which returns *distinct* ancestors and so answers "one face" for both. A seam
#: exists only on a periodic surface, which is what is left to decide it on.
EDGE_SEAM = 'seam'
#: One face, and that face's surface is not periodic: an open boundary. On a closed solid, a defect.
EDGE_FREE = 'free_boundary'
EDGE_DEGENERATE = 'degenerate'        #: Zero length: a pole of the parameterization.
EDGE_NONMANIFOLD = 'nonmanifold'      #: Three or more faces share it.
#: The kernel would not say how long it is or where its ends are. **Counted a finding, not a pass.**
#: An earlier version let the read fail into the ordinary branches, which turned a zero-length edge
#: into a confident `free_boundary` -- a broad `except` producing a diagnosis instead of an error.
EDGE_UNREADABLE = 'unreadable'
#: The kernel says two faces share it and the geometric keying did not. **A finding about this
#: instrument, not about the part**, and it has to be a category of its own: `_edge_key` includes
#: the edge's midpoint at `valueAt(0.5 * (First + Last))`, which is *parameter*-dependent, so two
#: representations of one curve that are parameterized differently key apart and each present as a
#: one-face group. Reporting that as an open boundary on a shape the kernel calls a closed solid
#: would be the proxy overruling the authority.
EDGE_KEYED_APART = 'keyed_apart'


def kernel_face_count(Part, shape, edge):
    """How many faces the **kernel** says share `edge`, or `None` if it will not say.

    `ancestorsOfType` is a search over the shape per edge, which is why `face_adjacency` keys
    edges geometrically instead -- a tail cavity has thousands of each. Asked here for the handful
    of edges the keying already called anomalous, where the cost is nothing and the keying is
    exactly what is in doubt.
    """
    try:
        return len(shape.ancestorsOfType(edge, Part.Face))
    except Exception:                                               # noqa: BLE001 kernel/API
        return None


def loose_faces(shape):
    """Faces of `shape` that belong to no solid. A compound can carry one, and it is a finding.

    A stray face left beside a solid by a boolean has free edges by definition, so it would show
    up as an open boundary without the solid being open at all. Returns `(total, in_solids)`;
    unequal counts mean the shape is not just its solids.
    """
    try:
        total = len(shape.Faces)
        in_solids = sum(len(s.Faces) for s in shape.Solids)
        return total, in_solids
    except Exception:                                               # noqa: BLE001 kernel/API
        return None, None


def anomalous_edges(shape, quantum=KERNEL_TOL, length_tol=1.0e-6, Part=None):
    """Every edge group of `shape` not shared by exactly two faces, each one classified.

    **On a closed solid every edge has exactly two faces, so a group that does not is one of four
    different things and they are not equally serious** (IP-WTM-35). `face_adjacency` counts them
    and stops there, which is right for its own purpose -- an unmatched key is a rib edge that
    would otherwise go unexamined -- but it leaves "one of the tail's 3 164 edge groups is not
    shared by exactly two faces" as a fact with no diagnosis. The four cases:

    * `EDGE_DEGENERATE` -- zero length. A pole of the parameterization, where a surface collapses
      to a point. Entirely normal on a revolved or lofted patch and not a defect.
    * `EDGE_SEAM` -- one face, whose surface is **periodic**: the closing seam, equally normal.
    * `EDGE_FREE` -- one face, whose surface is not periodic, so it has no seam to be: an open
      boundary. On a shape that should be a closed solid this is a real defect, and it is the one of
      the four worth raising.

    **Periodicity is what separates those two, because nothing else can.** `face_adjacency` records
    a face index once per group, so a seam presents as a one-face group; the kernel's own
    `ancestorsOfType` returns *distinct* ancestors and so also answers "one face"; and
    `Face.Edges` was measured **not** to list a seam twice (a cylinder's lateral face lists its
    seam once, like any other edge), so the occurrence count cannot carry the distinction either.
    `occurrences` is reported because it is cheap and would matter if that vendor behaviour ever
    changed, but no classification depends on it.

    A genuine open boundary on a *periodic* face is therefore indistinguishable from a seam by this
    test and would be reported as a seam. That limit is real and is the price of the only sound
    discriminator available.
    * `EDGE_NONMANIFOLD` -- three or more faces. Also a real defect.

    Returns one row a group, with the face indices, how many times each face carries the edge, the
    edge's length, whether its endpoints coincide, and the surface type and periodicity of the
    faces involved -- enough to tell a seam from a free boundary without going back to the shape.

    **Pass `Part` and every anomaly is cross-checked against the kernel's own adjacency, which is
    the authority this grouping is a proxy for.** `_edge_key` includes the edge's midpoint at
    `valueAt(0.5 * (First + Last))`, and that is a *parameter*, not a position: two
    differently-parameterized representations of one shared curve key apart, and each half then
    presents as a one-face group indistinguishable from a real open boundary. Where the kernel says
    two faces share the edge, the row becomes `EDGE_KEYED_APART` -- a defect in this measurement
    rather than in the part. Without `Part` the rows are the proxy's unchecked opinion, which on a
    shape the kernel calls a closed valid solid is not enough to report an open boundary.
    """
    groups, unkeyed = {}, []
    for index, face in enumerate(shape.Faces):
        for edge in face.Edges:
            try:
                key = _edge_key(edge, quantum)
            except Exception:                                       # noqa: BLE001 kernel/API
                # **Reported, not skipped.** `_edge_key` reads the edge's length and midpoint, so
                # an edge the kernel will not describe cannot be grouped -- and dropping it here
                # would remove it from the count as well, which is the one outcome that looks like
                # a clean wall. It becomes a finding of its own below.
                unkeyed.append(index)
                continue
            slot = groups.setdefault(key, {'edge': edge, 'faces': {}})
            slot['faces'][index] = slot['faces'].get(index, 0) + 1
    out = [{'kind': EDGE_UNREADABLE, 'faces': [i], 'occurrences': 1,
            'length_mm': float('nan'), 'closed': False,
            'surfaces': sorted({type(shape.Faces[i].Surface).__name__}),
            'periodic': _is_periodic(shape.Faces[i].Surface),
            'kernel_faces': None, 'key': None}
           for i in unkeyed]
    for key, slot in groups.items():
        faces = slot['faces']
        if sum(faces.values()) == 2 and len(faces) == 2:
            continue
        edge = slot['edge']
        try:
            length = float(edge.Length)
            verts = [v.Point for v in edge.Vertexes]
            if len(verts) < 2:
                closed = True
            else:
                a, b = verts[0], verts[-1]
                # Read by attribute, not by index. A vendor vector happens to support `v[0]`, and
                # relying on that is what made this branch raise and then mis-label the edge.
                closed = bool(abs(a.x - b.x) <= length_tol and abs(a.y - b.y) <= length_tol
                              and abs(a.z - b.z) <= length_tol)
            readable = True
        except Exception:                                           # noqa: BLE001 kernel/API
            length, closed, readable = float('nan'), False, False
        occurrences = sum(faces.values())
        surfaces = sorted({type(shape.Faces[i].Surface).__name__ for i in faces})
        periodic = any(_is_periodic(shape.Faces[i].Surface) for i in faces)
        if not readable:
            kind = EDGE_UNREADABLE
        elif length <= length_tol:
            kind = EDGE_DEGENERATE
        elif len(faces) >= 3:
            kind = EDGE_NONMANIFOLD
        elif len(faces) == 1:
            # Periodic, not the occurrence count: see `EDGE_SEAM`. A non-periodic surface has no
            # seam for this to be, so the edge really is a boundary of the shell.
            kind = EDGE_SEAM if periodic else EDGE_FREE
        else:
            # Two faces, but one of them carries the edge twice -- a seam on a face that also abuts
            # a neighbour there. Named rather than lumped in with the ordinary two-faced edges.
            kind = EDGE_SEAM
        kernel_faces = kernel_face_count(Part, shape, edge) if Part is not None else None
        if kernel_faces == 2 and kind in (EDGE_FREE, EDGE_NONMANIFOLD):
            # The authority says this edge is shared normally, so the anomaly is the keying's.
            kind = EDGE_KEYED_APART
        out.append({'kind': kind, 'faces': sorted(faces), 'occurrences': occurrences,
                    'length_mm': length, 'closed': closed, 'surfaces': surfaces,
                    'periodic': periodic, 'kernel_faces': kernel_faces, 'key': key})
    order = {EDGE_FREE: 0, EDGE_NONMANIFOLD: 1, EDGE_UNREADABLE: 2, EDGE_KEYED_APART: 3,
             EDGE_SEAM: 4, EDGE_DEGENERATE: 5}
    # `-length_mm` would put a NaN anywhere, so the kind alone orders the unreadable ones.
    return sorted(out, key=lambda r: (order.get(r['kind'], 9),
                                      0.0 if r['length_mm'] != r['length_mm']
                                      else -r['length_mm']))


def _is_periodic(surface):
    try:
        return bool(surface.isUPeriodic() or surface.isVPeriodic())
    except Exception:                                               # noqa: BLE001 non-spline
        return False


def edge_anomaly_verdict(rows):
    """Fold `anomalous_edges`' rows into one answer. A seam and a pole are not findings.

    `unchecked` counts the rows that would be findings but were never put to the kernel. They are
    still reported as serious -- an unchecked suspicion is not a clean bill -- but the count says
    whether the verdict rests on the proxy alone, which on a shape the kernel calls a closed solid
    is the difference between a finding and an artifact.
    """
    serious = [r for r in rows if r['kind'] in (EDGE_FREE, EDGE_NONMANIFOLD, EDGE_UNREADABLE)]
    counts = {}
    for r in rows:
        counts[r['kind']] = counts.get(r['kind'], 0) + 1
    return {'groups': len(rows), 'kinds': counts, 'serious': serious,
            'unchecked': [r for r in serious if r.get('kernel_faces') is None],
            'keyed_apart': counts.get(EDGE_KEYED_APART, 0),
            'clean': not serious}


def table_anomalous(rows, limit=12):
    """`anomalous_edges` as text, worst kind first."""
    head = '%-14s %10s %7s %8s %-22s %8s %s' % ('kind', 'length mm', 'faces', 'times', 'surfaces',
                                                'periodic', 'kernel faces')
    out = [head, '-' * len(head)]
    for r in rows[:limit]:
        out.append('%-14s %10s %7d %8d %-22s %8s %s'
                   % (r['kind'],
                      '?' if r['length_mm'] != r['length_mm'] else '%.5f' % r['length_mm'],
                      len(r['faces']), r['occurrences'],
                      ','.join(s[:20] for s in r['surfaces']), 'yes' if r['periodic'] else 'no',
                      'not asked' if r.get('kernel_faces') is None else r['kernel_faces']))
    if len(rows) > limit:
        out.append('... %d more' % (len(rows) - limit))
    return '\n'.join(out)


def parameterization_key(surface, quantum=KERNEL_TOL):
    """Everything about a B-spline surface except where its poles are: degrees, pole counts, knots,
    multiplicities and periodicity, quantized so two copies of one fit hash together."""
    def q(values):
        return tuple(int(round(float(v) / quantum)) for v in values)
    return (surface.UDegree, surface.VDegree, surface.NbUPoles, surface.NbVPoles,
            q(surface.getUKnots()), q(surface.getVKnots()),
            tuple(surface.getUMultiplicities()), tuple(surface.getVMultiplicities()),
            bool(surface.isUPeriodic()), bool(surface.isVPeriodic()))


def mirror_families(shape, atol=KERNEL_TOL):
    """Group a finished wall's B-spline surfaces by parameterization, and test each group for
    congruence. **The build-free half of the after-`cavity` question.**

    `shell_solid` finishes a wall by mirroring one cell across its cell planes, so a saved wall
    already carries several copies of the fitted interior patch. Each mirror step runs its own
    boolean and its own `removeSplitter`, either of which could refit the surface -- and a refit is
    what `surface_identity` was built to detect, except that it cannot be asked here, because a
    mirrored copy's poles are *supposed* to differ.

    **The test is non-circular because it predicts one property from another.** Two B-spline
    surfaces on one finished wall that agree in degrees, pole counts, knots, multiplicities and
    periodicity are copies of the same fit -- nothing else in the construction produces that
    structure twice. If they are copies, they must also be **congruent**, since a mirror is an
    isometry. So within each parameterization group, congruence is a prediction that can fail:
    grouping is by `parameterization_key`, which never looks at a pole, and the verdict is
    `congruent_identity` on the poles, which never looks at the key.

    Returns one row a group: `size`, how many members are *exactly* equal to the representative,
    the worst congruence mismatch in millimetres, and the pole counts. The `exact` count is what
    says the test is not vacuous -- a group where every member is pole-identical has not been
    mirrored at all, and congruence there is trivially true.
    """
    rows = {}
    for index, face in enumerate(shape.Faces):
        surf = face.Surface
        if type(surf).__name__ != 'BSplineSurface':
            continue
        try:
            key = parameterization_key(surf, atol)
        except Exception:                                           # noqa: BLE001 kernel/API
            continue
        rows.setdefault(key, []).append((index, surf))
    out = []
    for key, members in rows.items():
        _i0, first = members[0]
        worst, exact, comparable = 0.0, 0, True
        for _i, surf in members[1:]:
            verdict = congruent_identity(first, surf, atol)
            if not verdict['comparable'] or verdict['worst_step_mm'] is None:
                comparable = False
                continue
            worst = max(worst, verdict['worst_step_mm'])
            if _same_surface(first, surf):
                exact += 1
        out.append({'poles': (key[2], key[3]), 'degrees': (key[0], key[1]),
                    'size': len(members), 'exact': exact + 1, 'mirrored': len(members) - exact - 1,
                    'worst_step_mm': worst, 'comparable': comparable,
                    'congruent': bool(comparable and worst <= atol),
                    'faces': [i for i, _s in members]})
    return sorted(out, key=lambda r: (-r['size'], r['poles']))


def mirror_verdict(rows):
    """Fold `mirror_families`' rows into one answer, and say whether it was vacuous.

    `tested` counts only the groups that actually contain a mirrored copy: a wall whose every
    B-spline group is pole-identical throughout has told us nothing about the mirror steps, and
    reporting that as a pass would be the same error as cross-checking two measures of an empty
    input.
    """
    tested = [r for r in rows if r['mirrored'] > 0]
    return {'groups': len(rows), 'surfaces': sum(r['size'] for r in rows),
            'groups_with_a_mirrored_copy': len(tested),
            'mirrored_copies': sum(r['mirrored'] for r in tested),
            'worst_step_mm': (max(r['worst_step_mm'] for r in tested) if tested else None),
            'failed': [r for r in rows if not r['congruent']],
            'vacuous': not tested,
            'clean': bool(tested and all(r['congruent'] for r in rows))}


def table_mirror(rows):
    """`mirror_families` as text, one line a parameterization group."""
    head = '%6s %10s %6s %6s %9s %14s' % ('faces', 'poles', 'exact', 'mirror', 'degrees',
                                          'worst step mm')
    out = [head, '-' * len(head)]
    for r in rows:
        out.append('%6d %10s %6d %6d %9s %14s%s'
                   % (r['size'], '%dx%d' % r['poles'], r['exact'], r['mirrored'],
                      '%dx%d' % r['degrees'],
                      'n/a' if r['worst_step_mm'] is None else '%.3e' % r['worst_step_mm'],
                      '' if r['congruent'] else '   <-- NOT CONGRUENT'))
    return '\n'.join(out)


def _lattice_steps(poles):
    """Distances between adjacent poles, along `u` then along `v`. Invariant under a rigid motion."""
    du = np.linalg.norm(poles[1:, :, :] - poles[:-1, :, :], axis=-1)
    dv = np.linalg.norm(poles[:, 1:, :] - poles[:, :-1, :], axis=-1)
    return du, dv


def _worst_step_difference(pa, pb):
    """The smallest worst-case step mismatch over the four index-flip combinations."""
    ua, va = _lattice_steps(pa)
    best = None
    for flip_u in (False, True):
        for flip_v in (False, True):
            q = pb[::-1, :, :] if flip_u else pb
            q = q[:, ::-1, :] if flip_v else q
            ub, vb = _lattice_steps(q)
            if ua.shape != ub.shape or va.shape != vb.shape:
                continue
            worst = max(float(np.max(np.abs(ua - ub))) if ua.size else 0.0,
                        float(np.max(np.abs(va - vb))) if va.size else 0.0)
            best = worst if best is None else min(best, worst)
    return best


def _close(a, b, atol):
    a, b = np.asarray(list(a), dtype=float), np.asarray(list(b), dtype=float)
    return bool(a.shape == b.shape and np.allclose(a, b, rtol=0.0, atol=atol))


def _pole_array(surface):
    return np.array([[(p.x, p.y, p.z) for p in row] for row in surface.getPoles()], dtype=float)


def _weight_array(surface):
    try:
        return np.array(surface.getWeights(), dtype=float)
    except Exception:                                               # noqa: BLE001 non-rational
        return np.ones((surface.NbUPoles, surface.NbVPoles), dtype=float)


def face_normal(Part, face, point, h=NORMAL_STEP, directions=NORMAL_DIRECTIONS):
    """The unit normal of `face` at `point`, without ever asking for a surface parameter.

    **Parameter-free on purpose.** `Surface.parameter` and `projectPoint` have both been measured
    wrong by 2.411 mm on this very surface (`fitted_faces`), and a normal taken at a wrong
    parameter is wrong without being implausible. This instead offsets `point` along each of
    `directions`, snaps every offset back onto the face with `distToShape`, and takes the normal of
    the plane those on-face neighbours span -- the smallest singular vector of their offsets.

    Returns `(normal, residual, used)`: the unit normal, the singular value it came from (how far
    the neighbours are from coplanar, in mm -- large means the step is too big for the local
    curvature), and how many offsets survived. `(None, nan, n)` when fewer than three survive,
    which happens at a point pinched between trim boundaries.
    """
    p = np.asarray(point, dtype=float)
    offsets = []
    for d in directions:
        moved = p + h * np.asarray(d, dtype=float)
        back = _snap_to(Part, face, moved, strict=True)
        if back is None:                                   # not on the face; see `_snap_to`
            continue
        delta = np.asarray(back, dtype=float) - p
        # An offset along the local normal snaps straight back; one that barely moved carries no
        # tangent information and would only add noise to the fit.
        if np.linalg.norm(delta) > 0.1 * h:
            offsets.append(delta)
    if len(offsets) < 3:
        return None, float('nan'), len(offsets)
    matrix = np.asarray(offsets, dtype=float)
    _u, singular, vt = np.linalg.svd(matrix - matrix.mean(axis=0), full_matrices=True)
    normal = vt[-1]
    norm = np.linalg.norm(normal)
    if norm == 0.0:
        return None, float('nan'), len(offsets)
    return normal / norm, float(singular[-1]), len(offsets)


def angle_between(a, b):
    """The unsigned angle in degrees between two directions, folded into [0, 90].

    **Folded because a normal's sign is a convention, not a measurement.** Two faces of the same
    surface can be oriented oppositely and are still the same surface, so 180 deg apart has to
    read as 0. The cost is that this cannot distinguish a convex crease from a concave one; where
    that matters it has to come from the solid, not from a pair of normals.
    """
    if a is None or b is None:
        return float('nan')
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0.0 or nb == 0.0:
        return float('nan')
    cos = float(np.clip(abs(np.dot(a, b) / (na * nb)), 0.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def patch_deviation(Part, cut, fitted, rib_edge_shapes, probes=400,
                    deflection=PROBE_DEFLECTION, h=NORMAL_STEP, normal_limit=150):
    """Sample the cut cavity's fitted-surface faces inside, and compare to the pre-cut face.

    Per probe: the distance to `fitted` (the pre-cut B-spline face compound), the angle between the
    two surfaces' normals there, and the distance to the nearest rib edge. **The last is the point
    of the whole measurement**: a boundary-value error introduced at a patch edge appears as a
    displacement in the patch *interior*, so a deviation that grows away from the edges is the
    signature, and one that is flat at the kernel's noise floor is the refutation.

    Only faces lying on the pre-cut fitted surface are probed -- the lids, the caps and the tool
    faces are not that surface and are not what this question is about.

    **`normal_limit` is there because a normal costs twelve kernel calls and a position costs
    one.** `face_normal` snaps six offsets per surface and there are two surfaces, so normals on
    every probe would dominate the run. Position is measured on all `probes`; normals on the first
    `normal_limit` of them, in the order the tessellation ranks facets, which is largest-first and
    therefore spread over the face rather than clustered.
    """
    rows = []
    for index, face in _surface_faces(Part, cut, fitted):
        pts = interior_probes(face, probes, deflection=deflection, Part=Part)
        if not pts:
            continue
        d_surface = surface_deviations(Part, pts, fitted)
        for k, p in enumerate(pts):
            row = {'face': index, 'i': k, 'x': p[0], 'y': p[1], 'z': p[2],
                   'd_fitted_mm': float(d_surface[k]),
                   'edge_mm': _nearest_edge_distance(Part, p, rib_edge_shapes),
                   'normal_deg': float('nan'), 'normal_residual_mm': float('nan'),
                   'offsets_used': 0}
            if k < int(normal_limit):
                n_cut, res, used = face_normal(Part, face, p, h=h)
                n_pre, _r2, _u2 = face_normal(Part, fitted, p, h=h)
                row['normal_deg'] = angle_between(n_cut, n_pre)
                row['normal_residual_mm'] = res
                row['offsets_used'] = used
            rows.append(row)
    return rows


def _surface_faces(Part, cut, fitted):
    """`cut`'s faces that lie on the pre-cut fitted surface, as `(index, face)`.

    Selected by the same measurement `classify_faces` uses, on a handful of interior probes, so
    this cannot drift from that classification; it is not re-derived from the surface type, for
    the reasons in `classify_faces`.
    """
    out = []
    for index, face in enumerate(cut.Faces):
        if type(face.Surface).__name__ != 'BSplineSurface':
            continue
        pts = interior_probes(face, 3, Part=Part)
        if not pts:
            continue
        if float(np.min(surface_deviations(Part, pts, fitted))) <= FUZZ_TOL:
            out.append((index, face))
    return out


def _nearest_edge_distance(Part, point, edge_shapes):
    """How far `point` is from the nearest rib edge, in mm. `inf` when there are none."""
    if not edge_shapes:
        return float('inf')
    vertex = Part.Vertex(float(point[0]), float(point[1]), float(point[2]))
    best = float('inf')
    for shape in edge_shapes:
        try:
            best = min(best, float(vertex.distToShape(shape)[0]))
        except Exception:                                           # noqa: BLE001 kernel refusal
            continue
    return best


def crease_angles(Part, samples, cut, fitted, tool_planes, h=NORMAL_STEP, worst=200):
    """At each rib-edge sample, the angle between the fitted surface and the tool's cutting plane.

    **This is a design quantity, not a conformance one, and it is the degeneracy that matters.**
    90 degrees is two surfaces meeting squarely; 0 degrees is a *tangency*, which is the condition
    `RIB_CUT_FUZZ` exists for -- its own note records a dilated diagonal grazing the interior
    surface at a shallow near-tangent angle and pinching off a zero-volume sliver. So the minimum
    over every rib edge is a direct reading of how close any build comes to that.

    The surface normal is taken from the pre-cut face, where a rib-edge point is in the interior;
    on the cut face the same point sits on a trim boundary, where `face_normal` has fewer than
    three usable offsets and declines.
    """
    _faces, origins, normals, _boxes = tool_planes
    ranked = sorted(samples, key=lambda s: -max(s['d_smooth_mm'], s['d_tool_mm']))[:int(worst)]
    rows = []
    for s in ranked:
        point = (s['x'], s['y'], s['z'])
        n_surface, residual, used = face_normal(Part, fitted, point, h=h)
        face_index = s.get('tool_face', -1)
        n_tool = normals[face_index] if 0 <= face_index < len(normals) else None
        rows.append({'edge': s['edge'], 'i': s['i'], 'z': s['z'],
                     'crease_deg': angle_between(n_surface, n_tool),
                     'normal_residual_mm': residual, 'offsets_used': used,
                     'tool_face': face_index})
    return rows


def summarize_patch(rows, kernel_tol=KERNEL_TOL, fuzz_tol=FUZZ_TOL, bands=(0.1, 0.5, 2.0)):
    """`patch_deviation`'s verdict, including the deviation banded by distance to a rib edge.

    The banding is what answers the question. If the boolean imposes something at a patch edge
    that the interior has to absorb, the near-edge band and the far band differ; if every band sits
    at the same figure, there is nothing propagating.
    """
    if not rows:
        return {'probes': 0}
    d = np.array([r['d_fitted_mm'] for r in rows], dtype=float)
    e = np.array([r['edge_mm'] for r in rows], dtype=float)
    ang = np.array([r['normal_deg'] for r in rows], dtype=float)
    finite_ang = ang[np.isfinite(ang)]
    order = int(np.argmax(d))
    out = {
        'probes': len(rows),
        'faces': len({r['face'] for r in rows}),
        'worst_mm': float(np.max(d)),
        'mean_mm': float(np.mean(d)),
        'worst_at': rows[order],
        'within_kernel': int(np.count_nonzero(d <= kernel_tol)),
        'within_fuzz': int(np.count_nonzero(d <= fuzz_tol)),
        'over_fuzz': int(np.count_nonzero(d > fuzz_tol)),
        'worst_normal_deg': float(np.max(finite_ang)) if len(finite_ang) else float('nan'),
        'mean_normal_deg': float(np.mean(finite_ang)) if len(finite_ang) else float('nan'),
        'normals_measured': int(len(finite_ang)),
        'bands': [],
    }
    edges = [0.0] + list(bands) + [float('inf')]
    for lo, hi in zip(edges[:-1], edges[1:]):
        pick = (e >= lo) & (e < hi)
        if not np.any(pick):
            continue
        band_ang = ang[pick]
        band_ang = band_ang[np.isfinite(band_ang)]
        out['bands'].append({
            'lo_mm': lo, 'hi_mm': hi, 'probes': int(np.count_nonzero(pick)),
            'worst_mm': float(np.max(d[pick])), 'mean_mm': float(np.mean(d[pick])),
            'worst_normal_deg': float(np.max(band_ang)) if len(band_ang) else float('nan'),
        })
    return out


def table_patch(summary, identity=None, creases=None):
    """`summarize_patch` and its two companions as text, for a log."""
    lines = []
    if identity is not None:
        lines.append('surface identity, cut against pre-cut:')
        for row in identity:
            lines.append('  cut face %-4d  %s  degrees %s  poles %s  knots %s  weights %s  '
                         'periodic %s  worst pole %s'
                         % (row['face'], 'IDENTICAL' if row['identical'] else 'DIFFERS',
                            row['same_degrees'], row['same_pole_counts'], row['same_knots'],
                            row['same_weights'], row['same_periodicity'],
                            'n/a' if row['worst_pole_mm'] is None
                            else '%.3e mm' % row['worst_pole_mm']))
    if summary.get('probes'):
        lines.append('patch interior: %d probe(s) on %d fitted face(s)'
                     % (summary['probes'], summary['faces']))
        lines.append('  worst position deviation from the pre-cut face  %12.3e mm'
                     % summary['worst_mm'])
        lines.append('  worst normal angle between the two surfaces     %12.4f deg'
                     % summary['worst_normal_deg'])
        lines.append('  mean normal angle (%d measured)                 %12.4f deg'
                     % (summary['normals_measured'], summary['mean_normal_deg']))
        lines.append('  at kernel tolerance %d, within fuzz %d, over fuzz %d, of %d'
                     % (summary['within_kernel'], summary['within_fuzz'],
                        summary['over_fuzz'], summary['probes']))
        lines.append('  by distance to the nearest rib edge:')
        lines.append('    %-18s %7s %12s %12s %12s' % ('band', 'probes', 'worst mm',
                                                       'mean mm', 'worst deg'))
        for b in summary['bands']:
            label = '%.2f .. %s mm' % (b['lo_mm'],
                                       'inf' if b['hi_mm'] == float('inf') else '%.2f' % b['hi_mm'])
            lines.append('    %-18s %7d %12.3e %12.3e %12.4f'
                         % (label, b['probes'], b['worst_mm'], b['mean_mm'],
                            b['worst_normal_deg']))
    if creases:
        angles = np.array([r['crease_deg'] for r in creases], dtype=float)
        angles = angles[np.isfinite(angles)]
        if len(angles):
            lines.append('crease angle, fitted surface against the tool plane, over %d rib-edge '
                         'sample(s):' % len(angles))
            lines.append('  min %.3f deg, median %.3f deg, max %.3f deg  (0 would be a tangency)'
                         % (float(np.min(angles)), float(np.median(angles)),
                            float(np.max(angles))))
    return '\n'.join(lines) + '\n' if lines else 'nothing measured\n'


def summarize(samples, kernel_tol=KERNEL_TOL, fuzz_tol=FUZZ_TOL, wall_tol=WALL_TOL):
    """The banded verdict over a set of samples.

    The bands are the three scales a deviation can be at, and they mean different things: under
    `kernel_tol` the point is on the surface as far as the kernel is concerned; between that and
    `fuzz_tol` it moved by no more than the fuzzy cut was licensed to move it; above `fuzz_tol`
    nothing in the construction accounts for it; above `wall_tol` it is a wall of the wrong
    thickness, not a bookkeeping difference.
    """
    if not samples:
        return {'samples': 0}
    ds = np.array([s['d_smooth_mm'] for s in samples], dtype=float)
    dt = np.array([s['d_tool_mm'] for s in samples], dtype=float)
    worst = np.maximum(ds, dt)
    order = int(np.argmax(worst))
    # **An `inf` is a finding, not a number to average.** `plane_deviations` returns it for a
    # point whose projection falls over no tool face at all, which on a rib edge should never
    # happen -- the edge is on a tool face by definition. Counted separately, and kept out of the
    # means, so one of them cannot turn the whole summary into `inf` and hide the rest.
    no_tool = int(np.count_nonzero(~np.isfinite(dt)))
    finite_t = dt[np.isfinite(dt)]
    return {
        'samples': len(samples),
        'edges': len({s['edge'] for s in samples}),
        'worst_smooth_mm': float(np.max(ds)),
        'worst_tool_mm': float(np.max(finite_t)) if len(finite_t) else float('nan'),
        'worst_either_mm': float(worst[order]),
        'worst_sample': samples[order],
        'no_tool_candidate': no_tool,
        'mean_smooth_mm': float(np.mean(ds)),
        'mean_tool_mm': float(np.mean(finite_t)) if len(finite_t) else float('nan'),
        'within_kernel': int(np.count_nonzero(worst <= kernel_tol)),
        'within_fuzz': int(np.count_nonzero(worst <= fuzz_tol)),
        'over_fuzz': int(np.count_nonzero(worst > fuzz_tol)),
        'over_wall_tol': int(np.count_nonzero(worst > wall_tol)),
        'on': _tally(samples),
    }


def _tally(samples):
    out = {}
    for s in samples:
        out[s['on']] = out.get(s['on'], 0) + 1
    return out


def agrees_with_kernel(Part, App, samples, smooth, tool, worst=12):
    """Re-measure the worst samples with `distToShape` against the real trimmed faces.

    **The cheap measures above are both optimistic in a known direction and this is the check on
    them.** `plane_deviations` compares a point to an untrimmed plane behind a bounding-box
    filter, and `surface_deviations` to an untrimmed surface, so each can read zero for a point
    that is on the right surface but outside the face that was supposed to carry it.
    `distToShape` against a compound of the operand's own faces has no such license.

    **The smooth side is re-measured against the fitted faces, and against the whole boundary
    separately.** A first version compared only against the whole boundary and read 6.9e-18 mm
    where the fitted surface was 2.411 mm away -- reassuring, and about a different question. The
    two columns together say which of the smooth operand's surfaces the sample is actually on.

    Returns one row per re-measured sample with the figures side by side.
    """
    fitted = fitted_faces(Part, smooth)
    smooth_boundary = Part.makeCompound(smooth.Faces)
    tool_boundary = Part.makeCompound(tool.Faces)
    ranked = sorted(samples, key=lambda s: -max(s['d_smooth_mm'], s['d_tool_mm']))[:worst]
    rows = []
    for s in ranked:
        v = Part.Vertex(App.Vector(s['x'], s['y'], s['z']))
        rows.append({
            'edge': s['edge'], 'i': s['i'], 'z': s['z'],
            'cheap_smooth_mm': s['d_smooth_mm'],
            'cheap_tool_mm': s['d_tool_mm'],
            'kernel_smooth_mm': float(v.distToShape(fitted)[0]),
            'kernel_boundary_mm': float(v.distToShape(smooth_boundary)[0]),
            'kernel_tool_mm': float(v.distToShape(tool_boundary)[0]),
        })
    return rows


def smooth_surface_of(cut_or_smooth):
    """The single fitted B-spline surface of a smooth-interior solid.

    Raises `ValueError` on anything but exactly one, because the caller's whole cost model depends
    on there being one surface to project onto rather than a set to search. `feature_stations`
    records that all twelve soak walls report `patch 1/1`; a cell with a genuine axial crease in
    its blank would have more, and would need a different, slower measure rather than a quiet
    choice of one of them.
    """
    found = [f.Surface for f in cut_or_smooth.Faces
             if type(f.Surface).__name__ == 'BSplineSurface']
    if not found:
        raise ValueError('no B-spline face: this is not a fitted interior solid')
    first = found[0]
    for other in found[1:]:
        if not _same_surface(first, other):
            raise ValueError('%d distinct B-spline surfaces, not one; this measure assumes a '
                             'single fitted patch' % len(found))
    return first


def _same_surface(a, b):
    """Do two B-spline surfaces have identical control nets? Faces of one fitted patch do."""
    try:
        if (a.NbUPoles, a.NbVPoles) != (b.NbUPoles, b.NbVPoles):
            return False
        pa = np.array([[(p.x, p.y, p.z) for p in row] for row in a.getPoles()], dtype=float)
        pb = np.array([[(p.x, p.y, p.z) for p in row] for row in b.getPoles()], dtype=float)
        return bool(np.allclose(pa, pb, atol=KERNEL_TOL, rtol=0.0))
    except Exception:                                               # noqa: BLE001 kernel/API
        return False


def table(summary, agreement=None):
    """The summary as text, for a log."""
    if not summary.get('samples'):
        return 'no rib edge samples\n'
    lines = ['%d samples on %d rib edge(s)' % (summary['samples'], summary['edges']),
             '  worst distance to the fitted interior surface  %12.3e mm'
             % summary['worst_smooth_mm'],
             '  worst distance to a dilated tool face plane    %12.3e mm'
             % summary['worst_tool_mm'],
             '  worst of the two, per sample                   %12.3e mm'
             % summary['worst_either_mm'],
             '  at kernel tolerance (%.0e)   %d of %d'
             % (KERNEL_TOL, summary['within_kernel'], summary['samples']),
             '  within the cut fuzz  (%.0e)   %d of %d'
             % (FUZZ_TOL, summary['within_fuzz'], summary['samples']),
             '  over the cut fuzz                %d of %d'
             % (summary['over_fuzz'], summary['samples']),
             '  over WALL_TOL (%.3f mm)         %d of %d'
             % (WALL_TOL, summary['over_wall_tol'], summary['samples']),
             '  over no tool face at all         %d of %d'
             % (summary.get('no_tool_candidate', 0), summary['samples']),
             '  classification: %s' % summary['on']]
    w = summary['worst_sample']
    lines.append('  worst at edge %d point %d, (%.4f, %.4f, %.4f)'
                 % (w['edge'], w['i'], w['x'], w['y'], w['z']))
    if agreement:
        lines.append('  cheap measure against the kernel, worst %d samples:' % len(agreement))
        lines.append('    %-9s %11s %11s %11s %11s %11s'
                     % ('z', 'cheap surf', 'kern surf', 'kern bndry', 'cheap tool', 'kern tool'))
        for r in agreement:
            lines.append('    %-9.3f %11.3e %11.3e %11.3e %11.3e %11.3e'
                         % (r['z'], r['cheap_smooth_mm'], r['kernel_smooth_mm'],
                            r.get('kernel_boundary_mm', float('nan')),
                            r['cheap_tool_mm'], r['kernel_tool_mm']))
    return '\n'.join(lines) + '\n'


#: Stage names that move the geometry **rigidly**, so pole-for-pole identity is the wrong test
#: across them and congruence is the right one.
#:
#: **This constant exists because the first run of `stage_identity` got it wrong.** On a
#: `nose_cowl_shell` at `U` = 1.0, which mirrors three times, the two mirror-to-mirror transitions
#: reported a worst pole displacement of exactly **1.000e+02 mm** and were labelled a refit. That
#: is a reflection distance, not a refit: after a mirror the shape carries the original copy *and*
#: its image, both with the same parameterization key and different pole coordinates, so matching
#: by key and comparing poles can compare a copy against its own reflection. `congruent_identity`'s
#: docstring says precisely this about `surface_identity`; the mistake was applying the identity
#: test to the one step already known to need the congruence test.
ISOMETRY_STAGES = ('mirror_across_cell',)


def stage_identity(stages, atol=KERNEL_TOL, isometries=ISOMETRY_STAGES):
    """IP-WTM-38: does the fitted interior surface survive each boolean *after* `cavity`?

    `stages` is the list `cowl_interior.shell_solid` fills when given one: `(name, shape)` a step,
    in order, starting with `cavity`'s own output. For each consecutive pair this asks whether the
    B-spline surface the earlier stage carried is still there, pole for pole, in the later one.

    **Why a finished wall cannot answer this and a staged build can.** `mirror_families` tests that
    a finished wall's mirrored copies are congruent to one another, which catches a refit applied
    to one copy and not the others. It cannot catch a refit applied *before* the mirror: every copy
    is then equally refit, every copy is congruent, and the test passes. `_extend_across_cell` and
    `notched.cut(inside)` both run before any mirror, and `_strip_seam` runs inside the first one,
    so all three are invisible from the finished article. That is the gap this closes.

    **Matched by parameterization, not by face index.** A boolean renumbers faces freely and can
    leave one surface carrying several faces -- the tail's cavity carries three faces over one
    fitted patch -- so the surfaces are grouped by `parameterization_key` and a stage's group is
    compared against the same key in the next stage. A key that **disappears** between stages is
    the interesting outcome and is reported as `lost`, since that is what a refit looks like: the
    old parameterization is gone and a new one has taken its place.

    Returns one row a transition, each with:

    * `from_stage`, `to_stage` -- the two step names.
    * `keys_before`, `keys_after` -- how many distinct parameterizations each side carried.
    * `matched` -- keys present on both sides.
    * `lost` -- keys present before and gone after: a refit, or a surface the step removed.
    * `worst_mm` -- over matched keys, the largest discrepancy the applied test found.
    * `test` -- `'identity'` (poles where they stand) or `'congruence'` (internal step lengths).
    * `identical` -- every matched key passed the applied test, and nothing was lost.
    * `vacuous` -- the earlier stage carried no B-spline surface at all, so nothing was tested.

    **Which test is applied depends on the step**, and getting that wrong is how this function's
    first run produced a false positive -- see `ISOMETRY_STAGES`. A step that moves the geometry
    rigidly is checked with `congruent_identity`, which compares the control net's own internal
    step lengths and is invariant under reflection; every other step is checked with
    `surface_identity`, which compares poles where they stand and is the right question for a
    boolean that is supposed to leave its operand alone.
    """
    rows = []
    for (name_a, shape_a), (name_b, shape_b) in zip(stages, stages[1:]):
        before, after = {}, {}
        for store, shape in ((before, shape_a), (after, shape_b)):
            for _index, surf in bspline_surfaces(shape):
                try:
                    store.setdefault(parameterization_key(surf, atol), surf)
                except Exception:                                   # noqa: BLE001 kernel/API
                    continue
        matched = sorted(set(before) & set(after), key=repr)
        lost = sorted(set(before) - set(after), key=repr)
        rigid = name_b in isometries
        worst, all_same = None, True
        for key in matched:
            if rigid:
                ident = congruent_identity(before[key], after[key], atol)
                found = ident['worst_step_mm']
            else:
                ident = surface_identity(before[key], after[key], atol)
                found = ident['worst_pole_mm']
            if found is not None:
                worst = found if worst is None else max(worst, found)
            all_same = all_same and bool(ident['identical'])
        rows.append({
            'from_stage': name_a, 'to_stage': name_b,
            'keys_before': len(before), 'keys_after': len(after),
            'matched': len(matched), 'lost': len(lost),
            'worst_mm': worst, 'test': 'congruence' if rigid else 'identity',
            'identical': bool(all_same and not lost and matched),
            'vacuous': not before,
        })
    return rows


def stage_verdict(rows):
    """Fold `stage_identity`'s transitions into one answer.

    `clean` requires every transition to be identical **and** at least one transition to have
    tested something. A run where no stage carried a B-spline surface would otherwise report a pass
    from having measured nothing, which is the error this subsystem has now made seven times
    (cowl_interior_surface.md section 6.1).
    """
    tested = [r for r in rows if not r['vacuous']]
    bad = [r for r in rows if not r['vacuous'] and not r['identical']]
    worst = max((r['worst_mm'] for r in rows if r['worst_mm'] is not None), default=None)
    return {
        'transitions': len(rows),
        'tested': len(tested),
        'refitting': bad,
        'lost_total': sum(r['lost'] for r in rows),
        'worst_pole_mm': worst,
        'vacuous': not tested,
        'clean': bool(tested and not bad),
    }


def table_stages(rows):
    """`stage_identity` as text, one line a transition."""
    v = stage_verdict(rows)
    head = '%-22s %-22s %7s %7s %7s %6s %11s %12s %s' % (
        'from', 'to', 'before', 'after', 'matched', 'lost', 'test', 'worst', 'verdict')
    out = [head, '-' * len(head)]
    for r in rows:
        out.append('%-22s %-22s %7d %7d %7d %6d %11s %12s %s'
                   % (r['from_stage'], r['to_stage'], r['keys_before'], r['keys_after'],
                      r['matched'], r['lost'], r['test'],
                      '-' if r['worst_mm'] is None else '%.3e' % r['worst_mm'],
                      'NOTHING TESTED' if r['vacuous'] else
                      ('passes' if r['identical'] else 'REFIT OR LOST')))
    out.append('-' * len(head))
    if v['vacuous']:
        out.append('NOTHING TESTED: no stage carried a B-spline surface, so no step was checked')
    elif v['clean']:
        out.append('CLEAN: the fitted surface survives all %d tested transition(s) pole for '
                   'pole, worst displacement %s mm'
                   % (v['tested'],
                      '-' if v['worst_pole_mm'] is None else '%.3e' % v['worst_pole_mm']))
    else:
        out.append('%d of %d tested transition(s) refit or lost the surface: %s'
                   % (len(v['refitting']), v['tested'],
                      ', '.join('%s->%s' % (r['from_stage'], r['to_stage'])
                                for r in v['refitting'])))
    return '\n'.join(out)
