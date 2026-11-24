"""Does any face of the rib tool enter the cavity? An exact test for a failed rib cut.

**Why** (`cowl_interior_surface.md` section 7.2, IP-FC-169). `cavity`'s residue check asks a boolean
whether rib material is left inside the cut cavity; measured 2026-11-15 it returned an empty shape
on a cavity holding at least 8641.5 mm3 of uncut rib. The requirement is a detector with no false
negatives and no false positives, so this one does not rest on a boolean's result.

**How**, with the argument in `wall_measure.rib_cut`: rib material is left in the cavity exactly
when some face of the tool's boundary passes through the cavity's interior. Every face of the fused
tool is planar (each rib is a union of translated copies of a polyhedral slab), so each face is
moved `eps + clearance` into the tool and shrunk until a distance certificate places the copy
strictly inside the tool. Where one copy of the whole face cannot be built, the face's exact
triangulation is used instead, one inset triangle at a time. A correct cavity is outside the tool and therefore clear of every such copy; a cavity
that runs through an uncut rib contains it. A face is cleared only by two certificates -- the copy
keeps `clearance` from the cavity's boundary, and one of its points is outside the cavity -- and
everything else is a flag, so a failed computation errs toward a flag.

**`eps` is the wall tolerance, and it is exactly the threshold.** The copy sits `eps + clearance`
deep, so residue reaching less than `eps` past a tool face leaves it more than `clearance` away and
clears, and residue reaching further flags. What is not seen is residue confined within the inset
margin of a face's edges or, on the triangulation path, of a triangle's edges; that unexamined area
is reported per face, never counted as passing.

**Distances are taken to the boundary shells, not to the solids.** `distToShape` against a solid
may report zero for a shape inside it; the containment is asked separately with `isInside`, so each
certificate is two independent facts rather than one call's semantics.

Run it as::

    freecadcmd rib_cut_detector.py --pass --brep=<cavity .brep> --pass --kind=tail_shell \\
        --pass --u=3.0

One `--pass` per argument; read the report and the JSON, not the exit code.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))

import FreeCAD as App                                                    # noqa: E402
import Part                                                              # noqa: E402

import cowl_interior as ci                                               # noqa: E402
import cowl_tree                                                         # noqa: E402
import si                                                                # noqa: E402
from corner_common import is_entry_point                                 # noqa: E402
from refused_wall import load_brep, say                                  # noqa: E402
from station_gaps import BUILDERS, PARAMS, notch_compound, with_u        # noqa: E402
from wall_measure.rib_cut import (CLEAR, FLAGGED, UNTESTABLE, inset_triangle,  # noqa: E402
                                  placed, verdict)

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'rib_cut_detector')

#: How far into the tool each face is tested: the wall tolerance, so residue that would remove
#: more than the tolerance from the finished wall reaches past the copy.
EPS_M = ci.WALL_TOL_M

#: Both certificates require this much separation, and the kernel's tolerances (1e-10 m) are far
#: below it.
CLEARANCE_M = 0.5 * EPS_M

#: How deep into the tool each copy sits: `EPS_M + CLEARANCE_M`, so the flag threshold is exactly
#: the wall tolerance. A residue reaching `d` past a tool face leaves the copy `DEPTH_M - d` away:
#: more than `CLEARANCE_M` -- clear -- when `d < EPS_M`, and within it -- flagged -- when `d > EPS_M`.
#: Found 2026-11-19 by working the threshold through: at depth `EPS_M` the flag fired from
#: `EPS_M - CLEARANCE_M` = 0.005 mm, flagging residue below the tolerance, which the requirement
#: counts as a false positive.
DEPTH_M = EPS_M + CLEARANCE_M

#: Floating-point allowance on the certificates, 1 nm: a copy is built exactly `DEPTH_M` from its own
#: face, and a distance computed back to that face must not fail the certificate on rounding.
SLACK_M = 1.0e-9

#: How far a copy must be from the **whole** tool boundary to be placed. Measured 2026-11-19 on a
#: synthetic 0.009 mm residue: certified only `CLEARANCE_M` clear, the copies of the faces next to the
#: residue's face flagged it, because their in-plane inset brought them within reach of residue
#: below the threshold. The general condition does not depend on the angle between faces: residue
#: below the threshold lies within `EPS_M` of the tool boundary, so a copy at least
#: `EPS_M + CLEARANCE_M` from all of that boundary is at least `CLEARANCE_M` from any such residue.
PLACE_MIN_M = DEPTH_M - SLACK_M

#: A face is cleared when its copy keeps at least this much from the cavity.
VERDICT_CLEARANCE_M = CLEARANCE_M - 2.0 * SLACK_M

#: Shrink margins tried in turn until a copy is placed, as multiples of `EPS_M`.
SHRINK_STEPS = (1.0, 1.5, 2.0, 4.0, 8.0)

#: Insets tried for a triangle, as multiples of `EPS_M`, largest first. Measured 2026-11-19: at
#: 1.0 alone, 516 faces had every triangle thinner than the inset and went unexamined. A smaller
#: inset is safe to try because the placement certificate, not the inset, decides whether a copy
#: sits inside the tool; it cannot go below the clearance the certificate demands.
TRIANGLE_INSETS = (1.0, 0.6)

#: Containment tolerance for `isInside`, 1e-7 mm. The point tested is certified to
#: be at least `CLEARANCE_M` from the boundary, so this only has to be smaller than that.
INSIDE_TOL_M = 1.0e-10


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def _shells(shape):
    return Part.Compound(list(shape.Shells))


def _outward_normal(face, b):
    """The outward unit normal of `face` at its point nearest `b` (`normalAt` honors orientation)."""
    u, v = face.Surface.parameter(b)
    n = face.normalAt(u, v)
    n.normalize()
    return n


def _leaving_direction(edge, vertex):
    """The unit tangent of `edge` at `vertex`, pointing away from it along the edge."""
    p = vertex.Point
    first, last = edge.FirstParameter, edge.LastParameter
    at_first = (edge.valueAt(first) - p).Length <= (edge.valueAt(last) - p).Length
    t = edge.tangentAt(first if at_first else last)
    t.normalize()
    return t if at_first else -t


def _vertex_side(shells, vertex, w, tol=1.0e-9):
    """`normal_side` when the nearest boundary point is `vertex` and `w` is the offset from it:
    decided at a convex or a concave vertex, `None` at a saddle (see `normal_side`)."""
    b = vertex.Point
    normals = [_outward_normal(f, b) for f in shells.ancestorsOfType(vertex, Part.Face)]
    directions = [_leaving_direction(e, vertex) for e in shells.ancestorsOfType(vertex, Part.Edge)]
    if len(normals) < 3 or len(directions) < 3:
        return None
    products = [dj.dot(ni) for dj in directions for ni in normals]
    projections = [w.dot(n) for n in normals]
    if all(x <= tol for x in products):
        return not any(x > 0.0 for x in projections)
    if all(x >= -tol for x in products):
        return any(x < 0.0 for x in projections)
    return None


def normal_side(shells, q):
    """`True` inside, `False` outside, `None` undecided: which side of a closed boundary `q` is on,
    read from the outward normals at its nearest boundary point rather than by casting a ray.

    `isInside` classifies by ray casting, and measured 2026-11-19 it put a copy's corner inside a
    cavity and its center outside while the whole copy was at least 0.015 mm from the cavity's
    boundary -- which cannot be, so one reading was wrong. This reading is pure geometry:

    - **Nearest point inside a face.** `q - b` lies along that face's normal; its sign against the
      outward normal is the side.
    - **Nearest point on an edge.** `q - b` lies in the edge's normal cone. With `n1`, `n2` the
      outward normals of the two faces meeting there, a point outside a convex edge has
      `q - b = a n1 + c n2` with `a, c >= 0`, and a point inside a concave edge has `a, c <= 0`;
      solving for `a` and `c` settles it. Mixed signs are undecided.
    - **Nearest point on a vertex.** With `n_i` the outward normals of the faces meeting there and
      `d_j` the directions the edges leave it along: if every `d_j . n_i <= 0` the vertex is convex
      -- locally the solid is the intersection of the faces' half-spaces -- so `q` is outside
      exactly when some `(q - b) . n_i > 0`. If every `d_j . n_i >= 0` it is concave, the mirror
      case, and `q` is inside exactly when some `(q - b) . n_i < 0`. A saddle vertex, neither, is
      undecided.
    - **A degenerate edge, or anything else.** Undecided, never a guess; `side` then tries another
      point of the copy.
    """
    d, pairs, info = Part.Vertex(q).distToShape(shells)
    if not info or d <= 0.0:
        return None
    topo, index = info[0][3], info[0][4]
    b = pairs[0][1]
    w = q - b
    if topo == 'Face':
        return w.dot(_outward_normal(shells.Faces[index], b)) < 0.0
    if topo == 'Vertex':
        return _vertex_side(shells, shells.Vertexes[index], w)
    if topo != 'Edge':
        return None
    edge = shells.Edges[index]
    faces = shells.ancestorsOfType(edge, Part.Face)
    normals = []
    for f in faces:
        n = _outward_normal(f, b)
        if not any(abs(n.dot(m) - 1.0) < 1.0e-12 for m in normals):
            normals.append(n)
    if len(normals) == 1:
        # A seam: the same face on both sides of the edge.
        return w.dot(normals[0]) < 0.0
    if len(normals) != 2:
        return None
    n1, n2 = normals
    k = n1.dot(n2)
    det = 1.0 - k * k
    if det < 1.0e-12:
        return None
    p1, p2 = w.dot(n1), w.dot(n2)
    a = (p1 - k * p2) / det
    c = (p2 - k * p1) / det
    if a >= 0.0 and c >= 0.0:
        return False
    if a <= 0.0 and c <= 0.0:
        return True
    return None


BALL_FRACTION = 0.9
"""How far into a point's empty ball `ball_side` probes, as a fraction of its distance to the
boundary. Anything below 1 is exact; 0.9 reaches well away from the point's own nearest feature."""


def _probe_directions(shells, q):
    """Unit directions to probe from `q`: the axes, the cube diagonals, and the normals and edge
    directions at its nearest boundary feature, both ways -- the last two lead off a vertex."""
    out = []
    for x in (-1.0, 0.0, 1.0):
        for y in (-1.0, 0.0, 1.0):
            for z in (-1.0, 0.0, 1.0):
                if x or y or z:
                    out.append(App.Vector(x, y, z))
    _d, pairs, info = Part.Vertex(q).distToShape(shells)
    if info and info[0][3] == 'Vertex':
        vertex = shells.Vertexes[info[0][4]]
        b = vertex.Point
        own = ([_outward_normal(f, b) for f in shells.ancestorsOfType(vertex, Part.Face)]
               + [_leaving_direction(e, vertex) for e in shells.ancestorsOfType(vertex, Part.Edge)])
        out += own + [-v for v in own]
    for v in out:
        v.normalize()
    return out


def ball_side(shells, q):
    """`normal_side` at points of `q`'s empty ball, when it is undecided at `q` itself.

    No boundary point is closer to `q` than its distance `d` to the boundary, so every point within
    `d` of `q` is on `q`'s side, and a decided reading at any of them is `q`'s. Probing at
    `BALL_FRACTION * d` moves the nearest boundary point off the vertex or the saddle that left `q`
    undecided -- measured 2026-11-19 on two copies of the dosed cavity whose every point was
    nearest a saddle vertex. `None` only if every probe is undecided too.
    """
    d = Part.Vertex(q).distToShape(shells)[0]
    if d <= 0.0:
        return None
    for u in _probe_directions(shells, q):
        got = normal_side(shells, q + u * (BALL_FRACTION * d))
        if got is not None:
            return got
    return None


def side(shells, shape):
    """`True` inside, `False` outside, `None` undecided, for a copy certified not to cross the
    boundary of `shells`: the normal-side reading at the first of its points where it is defined.

    Every point of such a copy is on the same side, so one decided point settles it. The points
    tried are the copy's vertices and its center of mass, and then, if all of those are undecided,
    points of each one's empty ball (`ball_side`).
    """
    points = [v.Point for v in shape.Vertexes] + [shape.CenterOfMass]
    for q in points:
        got = normal_side(shells, q)
        if got is not None:
            return got
    for q in points:
        got = ball_side(shells, q)
        if got is not None:
            return got
    return None


def face_point(face, grid=9):
    """A point on `face`, strictly inside it, or `None`.

    The center of mass first, then a parameter grid. Measured 2026-11-19: taking the center of mass
    unconditionally left 957 of 2740 tool faces untestable, because a non-convex face's center of
    mass need not lie on the face.
    """
    c = face.CenterOfMass
    if face.isInside(c, 1.0e-6, True):
        return c
    u0, u1, v0, v1 = face.ParameterRange
    for i in range(1, grid):
        for j in range(1, grid):
            p = face.valueAt(u0 + (u1 - u0) * i / grid, v0 + (v1 - v0) * j / grid)
            if face.isInside(p, 1.0e-6, True):
                return p
    return None


def inward_normal(face, tool):
    """`(normal, reason)`: the unit normal pointing into `tool`, asked of the tool rather than
    trusted from the face's orientation flag; `reason` names why there is none."""
    p0 = face_point(face)
    if p0 is None:
        return None, 'no point on the face'
    u, v = face.Surface.parameter(p0)
    n = face.normalAt(u, v)
    step = si.mm(EPS_M)
    for sign in (-1.0, 1.0):
        if tool.isInside(p0 + n * (sign * step), si.mm(INSIDE_TOL_M), False):
            return n * sign, None
    return None, 'neither side is inside the tool at depth eps'


def inner_copy(face, tool, tool_shells):
    """`(copy, margin_m, dist_to_tool_m, reason)`; `copy` is `None` when no copy could be placed,
    and `reason` says which step failed, so untestable faces can be accounted for."""
    n, why = inward_normal(face, tool)
    if n is None:
        return None, None, None, why
    shifted = face.translated(n * si.mm(DEPTH_M))
    best = None
    reason = 'every shrink margin failed to offset'
    for k in SHRINK_STEPS:
        margin_m = k * DEPTH_M
        try:
            shrunk = shifted.makeOffset2D(-si.mm(margin_m), 0, False, False, False)
        except Exception:                                                 # noqa: BLE001
            continue
        faces = shrunk.Faces
        if len(faces) != 1:
            reason = 'shrinking split or erased the face'
            continue
        copy = faces[0]
        d_m = si.m(copy.distToShape(tool_shells)[0])
        # Normal side, not ray casting: measured 2026-11-19, `isInside` misclassified points well
        # clear of a boundary, and a copy wrongly placed outside the tool would test nothing.
        inside = side(tool_shells, copy) if d_m >= PLACE_MIN_M else None
        if placed(d_m, inside, PLACE_MIN_M):
            return copy, margin_m, d_m, None
        best = d_m if best is None else max(best, d_m)
        reason = ('copy not certified inside the tool (best clearance %.6f mm)'
                  % si.mm(best))
    return None, None, None, reason


def triangle_copies(face, tool, tool_shells, margin_m=None):
    """`(copies, unplaced_mm2, reason)`: the face's exact triangulation, each triangle inset by
    `margin_m` toward its incenter and moved `EPS_M` into the tool.

    The fallback where `inner_copy` cannot build one copy of the whole face. Every tool face is a
    planar polygon, so its triangulation has its vertices on the true boundary and is exact, and a
    triangle's centroid is always on the face -- the two things the whole-face path failed on
    (measured 2026-11-19: 397 faces with no grid point found, 447 where `makeOffset2D` failed).
    What it gives up: residue lying only within `margin_m` of a triangle edge is not seen, the
    same kind of band the whole-face path leaves along the face's own edges. `unplaced_mm2` is the
    area of triangles that could not be placed, and it is reported, never treated as passing.
    """
    margin_m = DEPTH_M if margin_m is None else margin_m
    try:
        pts, tris = face.tessellate(1.0e-3)
    except Exception:                                                     # noqa: BLE001
        return [], face.Area, 'the face would not triangulate'
    if not tris:
        return [], face.Area, 'the face triangulated to nothing'
    n = None
    for t in tris:
        a, b, c = pts[t[0]], pts[t[1]], pts[t[2]]
        nn = (b - a).cross(c - a)
        if nn.Length <= 0.0:
            continue
        nn.normalize()
        centroid = (a + b + c) * (1.0 / 3.0)
        for sign in (-1.0, 1.0):
            if tool.isInside(centroid + nn * (sign * si.mm(EPS_M)), si.mm(INSIDE_TOL_M), False):
                n = nn * sign
                break
        if n is not None:
            break
    if n is None:
        return [], face.Area, 'neither side of any triangle is inside the tool'
    shift = n * si.mm(DEPTH_M)
    copies, unplaced = [], 0.0
    def one(a, b, c, inset_m):
        """A placed copy of one triangle at `inset_m`, or `None`."""
        got = inset_triangle(tuple(a), tuple(b), tuple(c), si.mm(inset_m))
        if got is None:
            return None
        corners = [App.Vector(*q) + shift for q in got]
        try:
            tri = Part.Face(Part.makePolygon(corners + [corners[0]]))
        except Exception:                                                 # noqa: BLE001
            return None
        if si.m(tri.distToShape(tool_shells)[0]) < PLACE_MIN_M:
            return None
        if side(tool_shells, tri) is not True:
            return None
        return tri

    placed_copies, any_inset = [], False
    for t in tris:
        a, b, c = pts[t[0]], pts[t[1]], pts[t[2]]
        area = 0.5 * (b - a).cross(c - a).Length
        tri = None
        for k in TRIANGLE_INSETS:
            if inset_triangle(tuple(a), tuple(b), tuple(c), si.mm(k * margin_m)) is not None:
                any_inset = True
            tri = one(a, b, c, k * margin_m)
            if tri is not None:
                break
        if tri is None:
            unplaced += area
        else:
            placed_copies.append(tri)
    if not placed_copies:
        return [], face.Area, ('nothing could be placed' if any_inset
                               else 'every triangle was smaller than the smallest inset')
    return placed_copies, unplaced, None


def examine(cavity, tool, ribs=None):
    """A verdict for every face of `tool` against `cavity`, plus the preconditions."""
    rec = {'eps_mm': si.mm(EPS_M), 'clearance_mm': si.mm(CLEARANCE_M),
           'depth_mm': si.mm(DEPTH_M), 'place_min_mm': si.mm(PLACE_MIN_M),
           'cavity_solids': len(cavity.Solids), 'cavity_valid': bool(cavity.isValid()),
           'tool_solids': len(tool.Solids), 'tool_faces': len(tool.Faces),
           'tool_valid': bool(tool.isValid()),
           'non_planar_tool_faces': sum(1 for f in tool.Faces
                                        if 'Plane' not in type(f.Surface).__name__)}
    tool_shells = _shells(tool)
    cav_shells = _shells(cavity)
    faces = []
    started = time.time()
    for i, face in enumerate(tool.Faces):
        copy, margin_m, d_tool_m, why = inner_copy(face, tool, tool_shells)
        item = {'face': i, 'area_mm2': face.Area}
        bb = face.BoundBox
        item['z_mm'] = [bb.ZMin, bb.ZMax]
        if copy is not None:
            copies, unplaced, item['path'] = [copy], 0.0, 'whole face'
            item.update(margin_mm=si.mm(margin_m), to_tool_mm=si.mm(d_tool_m))
        else:
            item['whole_face_reason'] = why
            copies, unplaced, tri_why = triangle_copies(face, tool, tool_shells)
            item['path'] = 'triangles'
            item['triangles_placed'] = len(copies)
            if tri_why is not None:
                item['reason'] = tri_why
        item['unplaced_mm2'] = unplaced
        verdicts, hit = [], None
        if copies:
            batch = copies[0] if len(copies) == 1 else Part.Compound(copies)
            try:
                d_cav_m = si.m(batch.distToShape(cav_shells)[0])
            except Exception:                                             # noqa: BLE001
                d_cav_m = None
            item['to_cavity_mm'] = None if d_cav_m is None else si.mm(d_cav_m)
            for c in copies:
                p = c.Vertexes[0].Point
                # Containment by normal side, which is exact where it is defined; the ray-cast
                # reading is recorded beside it only as a cross-check. A copy closer to the cavity
                # than the clearance flags on distance alone, so the side is only read when the
                # copy is certified not to cross the boundary.
                in_cav = (side(cav_shells, c) if d_cav_m is not None
                          and d_cav_m >= VERDICT_CLEARANCE_M else None)
                try:
                    ray = bool(cavity.isInside(p, si.mm(INSIDE_TOL_M), False))
                except Exception:                                         # noqa: BLE001
                    ray = None
                # Only a decided reading can be contradicted; undecided ones are counted apart.
                if in_cav is not None and ray is not None and ray != in_cav:
                    item['raycast_disagrees'] = item.get('raycast_disagrees', 0) + 1
                if in_cav is None and d_cav_m is not None and d_cav_m >= VERDICT_CLEARANCE_M:
                    item['side_undecided'] = item.get('side_undecided', 0) + 1
                v = verdict(True, d_cav_m, in_cav, VERDICT_CLEARANCE_M)
                verdicts.append(v)
                if v == FLAGGED and hit is None:
                    hit = p
                    item['point_in_cavity'] = in_cav
        if FLAGGED in verdicts:
            item['verdict'] = FLAGGED
            if ribs is not None and hit is not None:
                item['ribs'] = [k for k, r in enumerate(ribs)
                                if r.isInside(hit, si.mm(INSIDE_TOL_M), True)]
        elif verdicts and unplaced == 0.0:
            item['verdict'] = CLEAR
        else:
            item['verdict'] = UNTESTABLE
            item.setdefault('reason', 'part of the face could not be placed'
                            if verdicts else 'nothing could be placed')
        faces.append(item)
        if (i + 1) % 100 == 0:
            say('    %d/%d faces, %d flagged, %d untestable, %.0f s'
                % (i + 1, len(tool.Faces), sum(1 for f in faces if f['verdict'] == FLAGGED),
                   sum(1 for f in faces if f['verdict'] == UNTESTABLE), time.time() - started))
    rec['faces'] = faces
    rec['counts'] = dict((v, sum(1 for f in faces if f['verdict'] == v))
                         for v in (CLEAR, FLAGGED, UNTESTABLE))
    flagged_ribs = sorted(set(k for f in faces for k in f.get('ribs', ())))
    rec['flagged_ribs'] = flagged_ribs
    rec['untestable_area_mm2'] = sum(f['area_mm2'] for f in faces if f['verdict'] == UNTESTABLE)
    # Area actually left unexamined: an untestable face counts only what was not placed.
    rec['unplaced_area_mm2'] = sum(f.get('unplaced_mm2') or 0.0 for f in faces)
    rec['by_path'] = dict((path, sum(1 for f in faces if f.get('path') == path))
                          for path in ('whole face', 'triangles'))
    reasons = {}
    for f in faces:
        if f['verdict'] == UNTESTABLE:
            key = f['reason'].split(' (')[0]
            reasons.setdefault(key, [0, 0.0])
            reasons[key][0] += 1
            reasons[key][1] += f['area_mm2']
    rec['untestable_reasons'] = reasons
    rec['raycast_disagreements'] = sum(f.get('raycast_disagrees', 0) for f in faces)
    rec['side_undecided'] = sum(f.get('side_undecided', 0) for f in faces)
    rec['seconds'] = time.time() - started
    return rec


#: Depths along a face's inward normal at which `profile` reads the cavity, in multiples of
#: `EPS_M`. Negative is outside the tool, on the cavity's side of a correct cut.
PROFILE_STEPS = (-3.0, -1.5, -0.5, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0)


def profile(cavity, tool, face):
    """Settle one flagged face: which side of it the cavity is on, read along its normal.

    A flag is adjudicated by an exact reading, not argued away (the OQ-ARCH-19 pattern). For a
    correct cut the cavity lies on the outside of the tool face and not behind it; for residue it
    lies behind it. Each row is `(depth_mm, inside_cavity, to_cavity_boundary_mm,
    to_tool_boundary_mm)` at a point on the face moved along its inward normal; a negative depth
    is outside the tool.
    """
    n, why = inward_normal(face, tool)
    if n is None:
        return {'error': why}
    p0 = face_point(face)
    cav_shells, tool_shells = _shells(cavity), _shells(tool)
    rows = []
    for k in PROFILE_STEPS:
        q = p0 + n * si.mm(k * EPS_M)
        v = Part.Vertex(q)
        rows.append((si.mm(k * EPS_M), bool(cavity.isInside(q, si.mm(INSIDE_TOL_M), True)),
                     v.distToShape(cav_shells)[0], v.distToShape(tool_shells)[0]))
    return {'point_mm': [p0.x, p0.y, p0.z], 'rows': rows}


def explain(cavity, tool, face):
    """Rebuild exactly the copies `examine` tested for `face` and report each one's readings.

    For a copy `D` at least `d` from the cavity's boundary, every point of `D` is on the same side
    of that boundary, so containment read at its tested corner and at its center must agree. A
    disagreement means one of the two kernel readings -- the distance or the containment -- is
    wrong there, and that is what this exists to find. Each row: `(corner_inside, center_inside,
    corner_to_cavity_mm, copy_to_cavity_mm)`.
    """
    tool_shells, cav_shells = _shells(tool), _shells(cavity)
    copy, _m, _d, why = inner_copy(face, tool, tool_shells)
    copies = [copy] if copy is not None else triangle_copies(face, tool, tool_shells)[0]
    rows = []
    for c in copies:
        corner = c.Vertexes[0].Point
        center = c.CenterOfMass
        rows.append((bool(cavity.isInside(corner, si.mm(INSIDE_TOL_M), False)),
                     bool(cavity.isInside(center, si.mm(INSIDE_TOL_M), False)),
                     Part.Vertex(corner).distToShape(cav_shells)[0],
                     c.distToShape(cav_shells)[0],
                     normal_side(cav_shells, corner), normal_side(cav_shells, center)))
    return {'path': 'whole face' if copy is not None else 'triangles', 'rows': rows}


def run_profiles(breps, kind, u, faces):
    """`profile` for each face index in `faces`, against each cavity in `breps`."""
    doc = App.newDocument('rib_cut_profile')
    try:
        cowl_tree.emit(doc, None, with_u(PARAMS[kind], u), BUILDERS[kind])
        doc.recompute()
        _body, tools, _mirrors, _cell = cowl_tree.pieces(doc)
        params = doc.getObject('Params')
        t_m = si.m(float(params.get('cowl_n_perimeters')) * float(params.get('extrusion_width')))
        ribs = ci.dilated_notches(notch_compound(tools), t_m)
        tool = ribs[0] if len(ribs) == 1 else ribs[0].fuse(ribs[1:]).removeSplitter()
    finally:
        App.closeDocument(doc.Name)
    cavities = [(os.path.basename(b), load_brep(b)) for b in breps]
    out = {}
    for i in faces:
        face = tool.Faces[i]
        out[i] = {}
        for name, cav in cavities:
            got = profile(cav, tool, face)
            got['explain'] = explain(cav, tool, face)
            out[i][name] = got
            for corner_in, center_in, d_corner, d_copy, n_corner, n_center in \
                    got['explain']['rows']:
                if corner_in != center_in or corner_in:
                    say('    copy (%s): ray-cast corner %s center %s; normal-side corner %s '
                        'center %s; corner to cavity %.5f mm, copy to cavity %.5f mm'
                        % (got['explain']['path'], corner_in, center_in, n_corner, n_center,
                           d_corner, d_copy))
            say('    %d copies tested' % len(got['explain']['rows']))
            say('')
            say('  face %d in %s at %s' % (i, name, got.get('point_mm', got.get('error'))))
            for depth, inside, d_cav, d_tool in got.get('rows', ()):
                say('    depth %+8.4f mm  inside cavity %-5s  to cavity %.5f mm  to tool %.5f mm'
                    % (depth, inside, d_cav, d_tool))
    return out


def run(brep, kind, u, out_dir):
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    stem = os.path.join(out_dir, '%s_U%g_%s' % (kind, u,
                                               os.path.splitext(os.path.basename(brep))[0]))
    say('')
    say('rib cut detector: %s' % os.path.basename(brep))
    doc = App.newDocument('rib_cut_detector')
    try:
        cowl_tree.emit(doc, None, with_u(PARAMS[kind], u), BUILDERS[kind])
        doc.recompute()
        _body, tools, _mirrors, _cell = cowl_tree.pieces(doc)
        params = doc.getObject('Params')
        t_m = si.m(float(params.get('cowl_n_perimeters')) * float(params.get('extrusion_width')))
        ribs = ci.dilated_notches(notch_compound(tools), t_m)
        # Exactly `cavity`'s line, so the tool is the one the build cut with.
        tool = ribs[0] if len(ribs) == 1 else ribs[0].fuse(ribs[1:]).removeSplitter()
    finally:
        App.closeDocument(doc.Name)
    cavity = load_brep(brep)
    say('  cavity: %d solid(s), valid=%s; tool: %d solid(s), %d faces, valid=%s'
        % (len(cavity.Solids), cavity.isValid(), len(tool.Solids), len(tool.Faces),
           tool.isValid()))
    rec = examine(cavity, tool, ribs)
    rec.update(brep=brep, kind=kind, u=float(u))
    with io.open(stem + '.json', 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(rec, indent=1, sort_keys=True, default=float))
    say('  %s; flagged ribs %s; untestable faces %.4f mm2, of which unplaced %.4f mm2; '
        'paths %s; non-planar tool faces %d; %.0f s'
        % (rec['counts'], rec['flagged_ribs'], rec['untestable_area_mm2'],
           rec['unplaced_area_mm2'], rec['by_path'], rec['non_planar_tool_faces'],
           rec['seconds']))
    say('  ray casting disagreed with the normal side on %d copies; side undecided on %d'
        % (rec['raycast_disagreements'], rec['side_undecided']))
    for key, (n, area) in sorted(rec['untestable_reasons'].items()):
        say('    untestable: %4d faces, %10.4f mm2 -- %s' % (n, area, key))
    return rec


def main():
    brep = _opt('brep')
    if not brep:
        raise SystemExit('--brep=<cavity .brep> is required')
    if _opt('profile'):
        breps = [os.path.normpath(b) for b in brep.split(',')]
        faces = [int(f) for f in _opt('profile').split(',')]
        got = run_profiles(breps, _opt('kind', 'tail_shell'), float(_opt('u', '3.0')), faces)
        out_dir = os.path.normpath(_opt('out-dir', OUT_DIR))
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        with io.open(os.path.join(out_dir, 'profiles.json'), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(got, indent=1, sort_keys=True, default=float))
        return
    run(os.path.normpath(brep), _opt('kind', 'tail_shell'), float(_opt('u', '3.0')),
        os.path.normpath(_opt('out-dir', OUT_DIR)))


if is_entry_point(__name__):
    main()
