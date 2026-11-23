"""The 48-gon rib constructions OQ-DES-CW40 measured planar ribs against. Measurement only.

**What this is for.** OQ-DES-CW40 (`doc/design/cowl.md`) asked how to get an exact rib-cut detector.
The ribs were then a union of 48 translated copies of each slab, whose surface is a zigzag of 2,740
faces the kernel could not offset. This harness measured two replacements: each convex part dilated
as the exact Minkowski sum with the 48-gon (`dilate`, `hull_ribs`), and with flat faces and square or
beveled corners (`planar_tools`). Planar ribs were adopted, and IP-FC-170 moved their construction
and the exact inner offset into the production module `rib_geometry.py`. What is left here is the
48-gon side of that comparison, and the probe hooks `sever_doses.py` and `rib_examples.py` use.

**The construction.** A convex slab `S` dilated by the 48-gon `Q` of copies is the Minkowski sum
`S + Q`, which is the convex hull of the translated copies. That is one convex polyhedron, with no
zigzag, and its inner offset is exact: every face plane moves in by `eps` (`shrink`).

**Units.** Kernel geometry is millimeters, as everywhere `Part` is called; `t_m` crosses in from the
construction in meters and is converted once, at the top of `dilate`.

**scipy** comes from FreeCAD's own interpreter, which is the only one that runs this module.
"""
import math

import numpy as np
from scipy.spatial import HalfspaceIntersection

import cowl_interior as ci
import si
from rib_geometry import _plane, _solid_from_hull, convex_parts, dilate_planar, planar_ribs

#: The facet count of the retired 48-gon dilation, which `cowl_interior` no longer has. Kept here so
#: the measurements made against it can be repeated.
HULL_FACETS = 48


def dilate(part, t_m, facets):
    """The convex `part` dilated by the `facets`-gon of radius `t_m` in the layer plane: the hull of
    its copies at exactly the offsets the retired 48-gon union used."""
    t = si.mm(t_m)
    base = np.array([[v.X, v.Y, v.Z] for v in part.Vertexes])
    offsets = [(t * math.cos(2.0 * math.pi * i / facets),
                t * math.sin(2.0 * math.pi * i / facets), 0.0) for i in range(facets)]
    points = np.vstack([base + np.array(o) for o in offsets])
    return _solid_from_hull(points)


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
    center = convex.CenterOfMass
    inside = np.array([center.x, center.y, center.z])
    if np.max(halfspaces[:, :3].dot(inside) + halfspaces[:, 3]) >= 0.0:
        return None
    hs = HalfspaceIntersection(halfspaces, inside)
    solid, _volume = _solid_from_hull(hs.intersections)
    return solid


def tools(notches, t_m, report=None):
    """The rib tools as `cowl_interior.dilated_notches` returns them -- a list of solids -- but
    each built as `hull_ribs` does, at the retired construction's `HULL_FACETS`. This is the hook
    `wall_measure.probe.Probe(dilate=...)` installs."""
    ribs = hull_ribs(notches, t_m, HULL_FACETS)
    if report is not None:
        report.update(dilated_tools=len(ribs),
                      dilated_volume_m3=sum(si.volume_m3(r) for _i, r in ribs),
                      dilation='hull')
    ci.note('ribs: %d notches dilated as %d convex hull parts by %.4f mm, %d-gon'
            % (len(notches.Solids), len(ribs), si.mm(t_m), HULL_FACETS))
    return [r for _i, r in ribs]


def planar_tools(notches, t_m, report=None):
    """As `tools`, but each rib built as `rib_geometry.planar_ribs` does: flat faces, square or
    beveled corners. Since IP-FC-170 this is the production construction too; the hook is kept so
    `sever_doses.py --dilate=planar` still names it."""
    ribs = planar_ribs(notches, t_m)
    if report is not None:
        report.update(dilated_tools=len(ribs),
                      dilated_volume_m3=sum(si.volume_m3(r) for _i, r in ribs),
                      dilation='planar')
    ci.note('ribs: %d notches dilated as %d planar parts by %.4f mm'
            % (len(notches.Solids), len(ribs), si.mm(t_m)))
    return [r for _i, r in ribs]


def failed_planar_tools(omit=(), thinner_m=None):
    """A `Probe(dilate=...)` hook that cuts with the planar tool made smaller on purpose: the notches
    in `omit` left out, and each notch `i` in `thinner_m` grown by `t - thinner_m[i]` instead of `t`.

    **IP-FC-169's failure made on purpose** (OQ-DES-CW42, algorithm document section 7.2). The cavity
    this cuts is judged against the inner offset of the *full* planar tool, so the answer is known
    before the detector runs: a left-out rib is flagged, and a thinner rib leaves a residue
    `delta * |n_xy|` deep on each face, flagged exactly when that reaches `WALL_TOL_M` on a face that
    bounds the cavity. On an inclined face the residue is thinner than `delta`.
    """
    omit = frozenset(omit)
    thinner_m = dict(thinner_m or {})

    def hook(notches, t_m, report=None):
        ribs = []
        for i, slab in enumerate(notches.Solids):
            if i in omit:
                continue
            for part in convex_parts(slab):
                rib, _v = dilate_planar(part, t_m - thinner_m.get(i, 0.0))
                ribs.append(rib)
        if report is not None:
            report.update(dilated_tools=len(ribs),
                          dilated_volume_m3=sum(si.volume_m3(r) for r in ribs),
                          dilation='planar, failed on purpose')
        ci.note('ribs: %d notches dilated as %d planar parts by %.4f mm, FAILED ON PURPOSE: '
                'left out %s, thinner %s'
                % (len(notches.Solids), len(ribs), si.mm(t_m), sorted(omit) or 'none',
                   ', '.join('%d by %.6f mm' % (i, si.mm(d)) for i, d in sorted(thinner_m.items()))
                   or 'none'))
        return ribs

    return hook


def hull_ribs(notches, t_m, facets):
    """Every notch dilated as `dilate` does, part by part: a list of `(notch_index, rib_part)`."""
    out = []
    for i, slab in enumerate(notches.Solids):
        for part in convex_parts(slab):
            rib, _v = dilate(part, t_m, facets)
            out.append((i, rib))
    return out
