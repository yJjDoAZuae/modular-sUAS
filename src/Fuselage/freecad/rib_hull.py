"""Rib tools dilated as exact Minkowski sums, and their exact inner offsets. Measurement only.

**What this is for.** OQ-DES-CW40 (`doc/design/cowl.md`) asks how to get an exact rib-cut detector.
The detector needs the rib tool's inner offset by `WALL_TOL_M`, and the kernel cannot build that for
the tool `cowl_interior.dilated_notches` makes: a union of 48 translated copies of each slab,
whose surface is a zigzag of 2,740 faces. The recommended alternative builds each rib differently,
and this module is the harness that measures it before anything in production changes.

**The construction.** A convex slab `S` dilated by the 48-gon `Q` of copies is the Minkowski sum
`S + Q`, which is the convex hull of the translated copies. That is one convex polyhedron, with no
zigzag, and its inner offset is exact: every face plane moves in by `eps`. A non-convex slab is
split into convex parts first, at its concave edges, and each part is dilated on its own. Ribs that
follow an inward-then-outward tail profile are non-convex by design, so the split is not optional.

**Units.** Kernel geometry is millimeters, as everywhere `Part` is called; `t_m` crosses in from the
construction in meters and is converted once, at the top of `dilate`.

**scipy** comes from FreeCAD's own interpreter, which is the only one that runs this module.
"""
import math

import numpy as np
from scipy.spatial import ConvexHull, HalfspaceIntersection

import FreeCAD as App
import Part

import cowl_interior as ci
import si

CONVEX_TOL_MM = 1.0e-7
"""How far a vertex may sit on the outer side of a face plane and the solid still count as convex.
Far below any feature here (the smallest slab face is 0.002 mm2), far above double-precision noise
on coordinates of a few hundred millimeters."""

TOUCH_TOL_MM = 1.0e-7

#: How many points of an inner offset `reaches` tests for lying inside the shape before it asks
#: the kernel for the distance. Each test costs about 0.2 s against a 547-face cavity, so this
#: bounds the shortcut at about 13 s when nothing is found.
REACH_PROBES = 64
"""A shape within this of a tool's inner offset touches it. The kernel's own confusion distance;
a residue 1% past `WALL_TOL_M` overlaps the offset by 1e-4 mm, a thousand times more."""

COPLANAR_TOL = 1.0e-9
"""Hull facets whose unit normals and offsets agree to this are one face. Tighter merging is always
safe: an unmerged pair stays two coplanar faces, which `removeSplitter` joins."""


def _plane(face):
    """`(n, d)`: the outward unit normal of a planar `face` and its offset, so `n . x = d` on it."""
    n = face.normalAt(*face.Surface.parameter(face.CenterOfMass))
    n.normalize()
    return n, n.dot(face.Vertexes[0].Point)


def bends_out(edge, face_a, face_b):
    """Whether `face_b` leaves `edge` on the outer side of `face_a`'s plane: the solid is concave
    there. Both faces are planar.

    The test is local to the edge. It steps from the edge's midpoint into `face_b`, along `face_b`
    and square to the edge, and asks which side of `face_a`'s plane that step goes. Testing all of
    `face_b`'s vertices instead calls convex edges concave whenever `face_b` is not convex and
    reaches round past `face_a`'s plane somewhere else, as fused rib faces do.
    """
    na = _plane(face_a)[0]
    nb = _plane(face_b)[0]
    mid = 0.5 * (edge.FirstParameter + edge.LastParameter)
    at = edge.valueAt(mid)
    step = nb.cross(edge.tangentAt(mid))
    step.normalize()
    for h in (1.0e-3, 1.0e-5, 1.0e-7):
        for sign in (1.0, -1.0):
            p = at + step * (sign * h)
            if face_b.isPartOfDomain(*face_b.Surface.parameter(p)):
                return na.dot(step) * sign > COPLANAR_TOL
    raise ValueError('no point of the face found beside the edge at %s' % at)


def concave_edges(solid):
    """The edges of a planar-faced `solid` where it is not locally convex: each as
    `(edge, face_a, face_b)`, with `face_b` bending out past `face_a`'s plane at the edge."""
    out = []
    for e in solid.Edges:
        faces = solid.ancestorsOfType(e, Part.Face)
        if len(faces) == 2 and bends_out(e, faces[0], faces[1]):
            out.append((e, faces[0], faces[1]))
    return out


def is_convex(solid, tol=CONVEX_TOL_MM):
    """Every vertex on the inner side of every face plane, to `tol`."""
    for f in solid.Faces:
        if f.Surface.__class__.__name__ != 'Plane':
            return False
        n, d = _plane(f)
        if any(n.dot(v.Point) - d > tol for v in solid.Vertexes):
            return False
    return True


def _half_space(n, d, near, reach):
    """A box standing for the half-space `n . x <= d`: `reach` mm across, centered on the foot of
    `near` on the plane, so it covers everything within `reach / 2` of that point."""
    foot = near + n * (d - n.dot(near))
    rot = App.Rotation(App.Vector(0, 0, 1), n)
    box = Part.makeBox(reach, reach, reach, App.Vector(-reach / 2.0, -reach / 2.0, -reach))
    box.Placement = App.Placement(foot, rot)
    return box


def convex_parts(solid, depth=0, limit=16):
    """`solid` split into convex parts, at the plane of a face beside each concave edge.

    Each split is a boolean between a small polyhedron and a box, the kernel's easiest case, and is
    checked: the two pieces' volumes must add up to the whole to 1e-9 relative. Recursion stops at
    `limit` levels, which a slab with fewer bends than that never reaches.
    """
    if is_convex(solid):
        return [solid]
    if depth >= limit:
        raise RuntimeError('convex_parts: still non-convex after %d splits' % limit)
    _edge, face_a, _face_b = concave_edges(solid)[0]
    n, d = _plane(face_a)
    reach = 4.0 * solid.BoundBox.DiagonalLength + 1.0
    near = solid.BoundBox.Center
    inner = solid.common(_half_space(n, d, near, reach)).Solids
    outer = solid.cut(_half_space(n, d, near, reach)).Solids
    total = sum(s.Volume for s in inner + outer)
    if abs(total - solid.Volume) > 1.0e-9 * solid.Volume:
        raise RuntimeError('convex_parts: split lost volume, %.12g of %.12g'
                           % (total, solid.Volume))
    parts = []
    for piece in inner + outer:
        parts += convex_parts(piece, depth + 1, limit)
    return parts


def _solid_from_hull(points):
    """The convex hull of `points` (an `(n, 3)` array, mm) as a valid `Part` solid."""
    hull = ConvexHull(points)
    groups = []
    for simplex, eq in zip(hull.simplices, hull.equations):
        for g in groups:
            if np.allclose(g['eq'], eq, rtol=0.0, atol=COPLANAR_TOL):
                g['idx'].update(simplex.tolist())
                break
        else:
            groups.append({'eq': eq, 'idx': set(simplex.tolist())})
    faces = []
    for g in groups:
        n = g['eq'][:3]
        pts = points[sorted(g['idx'])]
        c = pts.mean(axis=0)
        u = pts[0] - c
        u = u / np.linalg.norm(u)
        v = np.cross(n, u)
        order = np.argsort([math.atan2(np.dot(p - c, v), np.dot(p - c, u)) for p in pts])
        ring = [App.Vector(*pts[k]) for k in order]
        faces.append(Part.Face(Part.makePolygon(ring + [ring[0]])))
    solid = Part.Solid(Part.Shell(faces)).removeSplitter()
    if solid.Volume < 0:
        solid.reverse()
    return solid, hull.volume


def dilate(part, t_m, facets):
    """The convex `part` dilated by the `facets`-gon of radius `t_m` in the layer plane: the hull of
    its copies at exactly the offsets `cowl_interior.dilated_notches` uses."""
    t = si.mm(t_m)
    base = np.array([[v.X, v.Y, v.Z] for v in part.Vertexes])
    offsets = [(t * math.cos(2.0 * math.pi * i / facets),
                t * math.sin(2.0 * math.pi * i / facets), 0.0) for i in range(facets)]
    points = np.vstack([base + np.array(o) for o in offsets])
    return _solid_from_hull(points)


BEVEL_DEG = 90.0
"""A convex edge whose two face normals differ by more than this is beveled by `dilate_planar`.
Unbeveled, a mitre there would reach more than `t / cos(45 degrees)`, 1.41 `t`, past the part;
beveled, each of the two corners it leaves turns by half as much."""


def dilate_planar(part, t_m, bevel_deg=BEVEL_DEG):
    """The convex `part` dilated by `t_m` in the layer plane, with flat faces and square or beveled
    corners instead of round ones.

    Each face plane moves out by the layer-plane disc's support in its normal direction,
    `t * |n_xy|`, exactly as far as `dilate` moves it with a round disc. A convex edge sharper than
    `bevel_deg` also gets a plane along its bisector, at the same support distance. The result is
    the intersection of those half-spaces. Every plane touches the disc dilation, so the result
    contains it: no wall is thinner than `t`, only some corners are thicker. That is the design
    intent the user stated for OQ-DES-CW40 (doc/design/cowl.md): a rib corner may be square or
    chamfered, provided the wall is never thinner than the extrusion width.

    The result has the part's own faces plus one per beveled edge, against the hull of `dilate`'s
    copies, which has a facet fan at every edge.
    """
    t = si.mm(t_m)
    verts = np.array([[v.X, v.Y, v.Z] for v in part.Vertexes])

    def row(n):
        n = np.asarray(n, dtype=float)
        n = n / np.linalg.norm(n)
        return list(n) + [-(float(np.max(verts.dot(n))) + t * math.hypot(n[0], n[1]))]

    rows = []
    for f in part.Faces:
        n, _d = _plane(f)
        rows.append(row([n.x, n.y, n.z]))
    limit = math.cos(math.radians(bevel_deg)) - COPLANAR_TOL  # a right angle stays square
    for e in part.Edges:
        faces = part.ancestorsOfType(e, Part.Face)
        if len(faces) != 2:
            continue
        na, nb = _plane(faces[0])[0], _plane(faces[1])[0]
        if na.dot(nb) < limit:
            rows.append(row([na.x + nb.x, na.y + nb.y, na.z + nb.z]))
    centre = part.CenterOfMass
    hs = HalfspaceIntersection(np.array(rows), np.array([centre.x, centre.y, centre.z]))
    return _solid_from_hull(hs.intersections)


def shrink(convex, eps_mm):
    """The inner offset of a convex polyhedron by `eps_mm`: every face plane moved in by `eps_mm`.

    Exact for a convex solid, because the set of points at least `eps_mm` from its boundary is the
    intersection of its half-spaces each moved in by `eps_mm`. `None` when nothing is left.
    """
    rows = []
    for f in convex.Faces:
        n, d = _plane(f)
        rows.append([n.x, n.y, n.z, -(d - eps_mm)])
    halfspaces = np.array(rows)
    centre = convex.CenterOfMass
    inside = np.array([centre.x, centre.y, centre.z])
    if np.max(halfspaces[:, :3].dot(inside) + halfspaces[:, 3]) >= 0.0:
        return None
    hs = HalfspaceIntersection(halfspaces, inside)
    solid, _volume = _solid_from_hull(hs.intersections)
    return solid


BATCH_GAP_MM = 1.0e-4
"""Operands cut together in one call have bounding boxes at least this far apart."""

ARTIFACT_TOL_MM = 1.0e-6
"""A piece of an inner offset closer than `eps - ARTIFACT_TOL_MM` to the solid's boundary is not
part of it: every true piece is `eps` away by definition. Measured faces of true pieces sit at
`eps` to 1e-9 mm."""


def _disjoint_batches(operands, gap=BATCH_GAP_MM):
    """`operands` grouped so no two in a group have bounding boxes within `gap` of each other."""
    boxes = []
    for o in operands:
        b = o.BoundBox
        b.enlarge(gap)
        boxes.append(b)
    groups = []
    for k in range(len(operands)):
        for g in groups:
            if all(not boxes[k].intersect(boxes[j]) for j in g):
                g.append(k)
                break
        else:
            groups.append([k])
    return [[operands[k] for k in g] for g in groups]


#: A cell's cut that comes back with more solids than this is treated as suspect and redone, one
#: operand at a time and then in smaller cells. It never accepts or drops geometry by itself: a
#: clean cell of the tail's largest tool solid gave 1 to 3 solids, while the bad ones shattered
#: into 1,756 to 307,211, and one of those took 1,877 s, measured 2026-11-20.
SHATTER_SOLIDS = 20

#: The smallest cell a suspect cell is split into. Below it, the cell is retried once in a box
#: grown by half on every side; if that fails too, `inner_offset` raises.
MIN_CELL_MM = 1.25


def ball_centers(solid):
    """The distinct ends of `solid`'s concave edges, where `inner_offset` puts its balls."""
    centers = []
    for e, _fa, _fb in concave_edges(solid):
        for p in (e.Vertexes[0].Point, e.Vertexes[-1].Point):
            if all((p - q).Length >= ARTIFACT_TOL_MM for q in centers):
                centers.append(p)
    return centers


def _deep_points(piece, boundary, eps_mm):
    """Points of `piece` at least `eps_mm` from `boundary`: its vertices and its solids' centers.

    A cell's piece has vertices on the cell's walls, which can lie deep inside the solid, so these
    are real samples of the inner offset that a correct cut must keep."""
    probes = [v.Point for v in piece.Vertexes] + [s.CenterOfMass for s in piece.Solids]
    return [p for p in probes
            if piece.isInside(p, ARTIFACT_TOL_MM, True)
            and boundary.distToShape(Part.Vertex(p))[0] >= eps_mm + ARTIFACT_TOL_MM]


def _cut(piece, operands, batched):
    core = piece
    for batch in (_disjoint_batches(operands) if batched else operands):
        core = core.cut(batch)
        if not core.Solids or len(core.Solids) > SHATTER_SOLIDS:
            break
    return core


def _classify(piece, boundary, eps_mm):
    """`('keep', 0)`, `('drop', 0)` for a cut artifact, or `('incomplete', depth)`.

    Every point of the inner offset is at least `eps_mm` from the boundary, so a piece that comes
    nearer is either an artifact lying on the boundary or material a cut failed to remove. It is an
    artifact only if none of its vertices and not its center lies `eps_mm` deep."""
    if boundary.distToShape(piece)[0] >= eps_mm - ARTIFACT_TOL_MM:
        return 'keep', 0.0
    probes = [v.Point for v in piece.Vertexes] + [piece.CenterOfMass]
    deep = max(boundary.distToShape(Part.Vertex(p))[0] for p in probes)
    if deep >= eps_mm - ARTIFACT_TOL_MM:
        return 'incomplete', deep
    return 'drop', 0.0


def _suspect(core, deep, boundary=None, eps_mm=None):
    """Why a cell's cut is not to be trusted, or `None`."""
    if len(core.Solids) > SHATTER_SOLIDS:
        return 'shattered into %d solids' % len(core.Solids)
    if not all(s.isValid() for s in core.Solids):
        return 'invalid'
    lost = [p for p in deep
            if not any(s.isInside(p, ARTIFACT_TOL_MM, True) for s in core.Solids)]
    if lost:
        return 'lost %d of %d points at least eps deep' % (len(lost), len(deep))
    if boundary is not None:
        for s in core.Solids:
            kind, depth = _classify(s, boundary, eps_mm)
            if kind == 'incomplete':
                return ('a piece of %.6g mm3 comes nearer the boundary than eps but reaches '
                        '%.6g mm deep' % (s.Volume, depth))
    return None


def _cut_cell(solid, tools, boundary, eps_mm, origin, size, report, grown=False):
    """The solids of `solid`'s inner offset in the cube at `origin`, retried until trusted."""
    pad = size / 2.0 if grown else 0.0
    box = Part.makeBox(size + 2 * pad, size + 2 * pad, size + 2 * pad,
                       origin - App.Vector(pad, pad, pad))
    piece = solid.common(box)
    if not piece.Solids:
        return [], 0.0
    reach = box.BoundBox
    reach.enlarge(BATCH_GAP_MM)
    mine = [t for t in tools if t.BoundBox.intersect(reach)]
    deep = _deep_points(piece, boundary, eps_mm)
    why = None
    for batched in (True, False):
        core = None
        try:
            core = _cut(piece, mine, batched)
            why = _suspect(core, deep, boundary, eps_mm)
        except Exception as e:  # the kernel's failures arrive as bare exceptions
            why = 'failed: %r' % e
        if why is None:
            return core.Solids, piece.Volume
        report['retries'].append((tuple(origin), size, grown, batched, why))
        if core is None or not core.Solids:
            continue
        # Cut the same operands again from what is left. In exact arithmetic that removes
        # nothing more, so the result is still exact; it only completes a cut the kernel left
        # short, such as a needle along a concave edge that its cylinder silently missed.
        try:
            again = _cut(core, mine, False)
            why = _suspect(again, deep, boundary, eps_mm)
        except Exception as e:
            why = 'failed: %r' % e
        if why is None:
            return again.Solids, piece.Volume
        report['retries'].append((tuple(origin), size, grown, 'again', why))
    if size / 2.0 >= MIN_CELL_MM:
        out, vol = [], 0.0
        h = size / 2.0
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    s, v = _cut_cell(solid, tools, boundary, eps_mm,
                                     origin + App.Vector(dx, dy, dz) * h, h, report)
                    out += s
                    vol += v
        return out, vol
    if not grown:
        s, _v = _cut_cell(solid, tools, boundary, eps_mm, origin, size, report, grown=True)
        # the grown box overlaps its neighbors; this cell's own share of the solid is still `piece`
        return s, piece.Volume
    if report.get('unresolved') is not None:
        report['unresolved'].append((tuple(origin), size, why))
        return [], piece.Volume
    raise RuntimeError('inner_offset: the %.3g mm cell at (%.6g, %.6g, %.6g) could not be cut: %s'
                       % (size, origin.x, origin.y, origin.z, why))


def operands(solid, eps_mm):
    """The solids `inner_offset` removes from `solid`: one prism per plane of its faces, one
    cylinder per concave edge and one ball per distinct end of one. See `inner_offset`."""
    planes = []
    for f in solid.Faces:
        if f.Surface.__class__.__name__ != 'Plane':
            raise ValueError('inner_offset: a %s face; only planar solids are handled'
                             % f.Surface.__class__.__name__)
        n, d = _plane(f)
        for entry in planes:
            if (entry[0] - n).Length < COPLANAR_TOL and abs(entry[1] - d) < ARTIFACT_TOL_MM:
                entry[2].append(f.extrude(n * -eps_mm))
                break
        else:
            planes.append((n, d, [f.extrude(n * -eps_mm)]))
    tools = [p[0] if len(p) == 1 else Part.Compound(p) for _n, _d, p in planes]
    for e, _fa, _fb in concave_edges(solid):
        p0, p1 = e.Vertexes[0].Point, e.Vertexes[-1].Point
        axis = p1.sub(p0)
        tools.append(Part.makeCylinder(eps_mm, axis.Length, p0, axis.normalize()))
    tools += [Part.makeSphere(eps_mm, p) for p in ball_centers(solid)]
    return tools


def inner_offset(solid, eps_mm, report=None, cell_mm=None, keep_going=False):
    """The points of a planar-faced `solid` at least `eps_mm` from its boundary, or `None`.

    `shrink` is exact only for a convex solid. A union of convex parts is not convex, and the union
    of its parts' shrinks is not its inner offset: where two parts abut, it misses a slab `2 eps`
    thick along the whole shared face. This works on the solid's own boundary instead, so it does
    not depend on how the solid was split.

    A point inside the solid is within `eps_mm` of the boundary exactly when its nearest boundary
    point is within `eps_mm`. That nearest point lies inside a face, on an edge or at a vertex. Each
    case is covered by a solid that is removed:

    - inside a face: the face pushed inward by `eps_mm`, a prism;
    - on an edge: only a concave edge can be nearest, since at a convex edge the foot on one of the
      two faces is always nearer. Each gets a cylinder of radius `eps_mm`;
    - at a vertex: only one on a concave edge can be nearest, by the same argument on the faces and
      edges around it. Each gets a ball of radius `eps_mm`.

    Every operand is exact geometry, a plane, a cylinder or a sphere, so the result has no
    approximation in it beyond the kernel's own tolerance.

    **The operands are cut in batches that do not touch.** Handing the kernel all of them in one
    cut, or fusing them first, is wrong on the real ribs. On a convex hull rib of 154 faces, where
    `shrink` gives the exact answer, both left 1,673 mm3 or more uncut, measured 2026-11-20. One cut
    per operand, and one cut per batch of operands whose bounding boxes are apart, both matched
    `shrink` to 0 mm3 of symmetric difference; the batches took 3 s where single cuts took 8.

    **Coplanar faces are cut together.** Where ribs overlap, faces of different ribs share a plane:
    737 of the 1,240 faces of the largest tool solid on this tail, on 254 planes. Cut in different
    calls, the second prism's inner face lands exactly on the face the first one left, and the cut
    returned a null shape. Each plane's prisms are one operand, so its offset face is made once.

    **One ball per vertex.** A vertex shared by several concave edges is the end of each of them.
    One ball per edge end put identical spheres on it, in different batches since they overlap, and
    the coincident surfaces broke the cut the way coplanar prisms did. On the tail's largest tool
    solid the 1,714 edge ends are 845 distinct points.

    **Large solids are cut cell by cell.** With `cell_mm`, the solid's bounding box is divided into
    cubes and each cube's share of the solid is cut only by the operands that reach it. The
    operands still come from `solid`'s own boundary and not from the cube's walls, so each cube's
    result is exactly the inner offset's share of that cube, and the compound of them is the inner
    offset. On the tail's largest tool solid (1,240 faces), cutting the whole solid batch after
    batch degraded it: 2 solids after three batches, 231 after four and 51,743 after five. Cutting
    it rib by rib still failed, at about 1,300 operands per rib. In 20 mm cubes, 1,672 of 1,680 cut
    cleanly in about a second each.

    **Each cell's cut is checked, and redone if suspect.** The kernel also failed silently: on one
    20 mm cube it returned nothing, where a point of the solid 0.49 mm deep had to survive. So each
    cell's result must still contain every vertex and center of its piece that lies `eps` deep,
    must be valid, must not have shattered (`SHATTER_SOLIDS`), and must not hold a piece that comes
    nearer the boundary than `eps` while reaching `eps` deep, which is material a cut failed to
    remove: one such piece of 303 mm3 reached 0.35 mm deep. A suspect result is first cut again by
    the same operands, which removes nothing more in exact arithmetic and so stays exact: it cleared
    a needle of 7e-6 mm3 that a cylinder left along a 0.19 mm concave edge. A suspect cell is then
    cut again one operand at a time, which cleared a cell that failed in batches, then split into
    eight, down to
    `MIN_CELL_MM`; at that size it is tried once more in a grown box, because a sliver of 0.0004 mm3
    clipped off by the cube's own walls broke one cut. A cell that never passes raises: dropping it
    could hide residue. With `keep_going`, it is instead listed under `report['unresolved']` as
    `(origin, size_mm, why)` and left out of the result, so a whole solid can be surveyed in one
    run; a result with any unresolved cell is not the inner offset and must not be used as one.
    The retries are reported under `report['retries']`, and the shares of the
    solid the cells cut must add up to its volume.

    **Cut artifacts are dropped, and checked first.** On a non-convex rib the cuts also left pieces
    lying on the boundary: a sliver 300 mm long and 0.0009 mm thick, a whole ball, a speck. Each
    would make any flush cut look as if it reached `eps` deep. A piece closer to the boundary than
    `eps - ARTIFACT_TOL_MM` cannot be part of the result, so it is dropped, but only after
    checking that none of its vertices and not its center lies `eps` deep: a piece that did would
    mean real volume was about to be discarded, and that raises instead. The dropped volumes are
    reported under `report['artifacts_mm3']`.
    """
    tools = operands(solid, eps_mm)
    boundary = Part.Compound(solid.Faces)
    if report is None:
        report = {}
    report['retries'] = []
    report['unresolved'] = [] if keep_going else None
    if cell_mm is None:
        core = _cut(solid, tools, batched=True)
        why = _suspect(core, _deep_points(solid, boundary, eps_mm), boundary, eps_mm)
        if why is not None:
            raise RuntimeError('inner_offset: the cut is not to be trusted: %s; try cell_mm' % why)
        cut = core.Solids
    else:
        bb = solid.BoundBox
        cut, shares = [], 0.0
        n = [max(1, int(math.ceil(length / cell_mm)))
             for length in (bb.XLength, bb.YLength, bb.ZLength)]
        for i in range(n[0]):
            for j in range(n[1]):
                for k in range(n[2]):
                    origin = App.Vector(bb.XMin + i * cell_mm, bb.YMin + j * cell_mm,
                                        bb.ZMin + k * cell_mm)
                    s, v = _cut_cell(solid, tools, boundary, eps_mm, origin, cell_mm, report)
                    cut += s
                    shares += v
        report['cells_mm3'] = shares
        if abs(shares - solid.Volume) > 1.0e-6 * max(1.0, solid.Volume):
            raise RuntimeError('inner_offset: the cells hold %.9g mm3 of a %.9g mm3 solid'
                               % (shares, solid.Volume))
    kept, dropped = [], []
    for piece in cut:
        kind, deep = _classify(piece, boundary, eps_mm)
        if kind == 'incomplete':
            raise RuntimeError('inner_offset: a piece of %.6g mm3 touches the boundary but reaches '
                               '%.6g mm deep' % (piece.Volume, deep))
        (kept if kind == 'keep' else dropped).append(piece if kind == 'keep' else piece.Volume)
    if report is not None:
        report['artifacts_mm3'] = dropped
    if not kept:
        return None
    if len(kept) == 1:
        return kept[0].removeSplitter()
    return Part.Compound([k.removeSplitter() for k in kept])


def reaches(shape, core, probes=REACH_PROBES):
    """How far `shape` stays from `core`, a tool's `inner_offset` by `eps`: 0 when they overlap.

    The exact rib-cut test. Material left inside a tool reaches `eps` or deeper exactly when it
    meets the tool's inner offset, so a cavity failed the cut to depth `eps` exactly when this is
    within `TOUCH_TOL_MM`. There is no clearance and no sampling in it. The kernel reports 0 when
    one solid lies wholly inside the other, which is the case of a rib not cut at all.

    `core` must be the inner offset of the tool that cut `shape`. A larger tool's offset reaches
    where a correct cut by a smaller tool leaves the shape, and flags it.

    The kernel's distance stalls when the two overlap widely: on a cavity with uncut ribs it gave
    no answer in 90 minutes. So up to `probes` vertices of the core, one from each of its largest
    pieces, are first tested for lying strictly inside `shape`. A point of the core strictly inside
    the shape is an overlap, so a hit returns 0 and cannot be a false positive. When there is no
    hit, the kernel's distance decides, as before.
    """
    pieces = sorted(core.Solids, key=lambda p: -p.Volume)[:probes]
    for piece in pieces:
        point = piece.Vertexes[0].Point
        for solid in shape.Solids:
            if solid.BoundBox.isInside(point) and solid.isInside(point, TOUCH_TOL_MM, False):
                return 0.0
    return shape.distToShape(core)[0]


def tools(notches, t_m, report=None):
    """The rib tools as `cowl_interior.dilated_notches` returns them -- a list of solids -- but
    each built as `hull_ribs` does, at the construction's own `RIB_FACETS`. This is the hook
    `wall_measure.probe.Probe(dilate=...)` installs."""
    ribs = hull_ribs(notches, t_m, ci.RIB_FACETS)
    if report is not None:
        report.update(dilated_tools=len(ribs),
                      dilated_volume_m3=sum(si.volume_m3(r) for _i, r in ribs),
                      dilation='hull')
    ci.note('ribs: %d notches dilated as %d convex hull parts by %.4f mm, %d-gon'
            % (len(notches.Solids), len(ribs), si.mm(t_m), ci.RIB_FACETS))
    return [r for _i, r in ribs]


def planar_ribs(notches, t_m):
    """Every notch dilated as `dilate_planar` does, part by part: a list of
    `(notch_index, rib_part)`."""
    out = []
    for i, slab in enumerate(notches.Solids):
        for part in convex_parts(slab):
            rib, _v = dilate_planar(part, t_m)
            out.append((i, rib))
    return out


def planar_tools(notches, t_m, report=None):
    """As `tools`, but each rib built as `planar_ribs` does: flat faces, square or beveled corners.
    The `Probe(dilate=...)` hook for `sever_doses.py --dilate=planar`."""
    ribs = planar_ribs(notches, t_m)
    if report is not None:
        report.update(dilated_tools=len(ribs),
                      dilated_volume_m3=sum(si.volume_m3(r) for _i, r in ribs),
                      dilation='planar')
    ci.note('ribs: %d notches dilated as %d planar parts by %.4f mm'
            % (len(notches.Solids), len(ribs), si.mm(t_m)))
    return [r for _i, r in ribs]


def hull_ribs(notches, t_m, facets):
    """Every notch dilated as `dilate` does, part by part: a list of `(notch_index, rib_part)`."""
    out = []
    for i, slab in enumerate(notches.Solids):
        for part in convex_parts(slab):
            rib, _v = dilate(part, t_m, facets)
            out.append((i, rib))
    return out
