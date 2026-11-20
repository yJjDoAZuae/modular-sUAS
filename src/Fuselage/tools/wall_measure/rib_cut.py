"""The decision rule for a failed rib cut: certificates, so the errors run one way only.

**Why this exists** (`cowl_interior_surface.md` section 7.2, IP-FC-169). The rib cut's own check
asks a boolean whether any rib is left in the cavity, and measured 2026-11-15 that boolean returned
an empty shape on a cavity holding at least 8641.5 mm3 of uncut rib. The requirement is a check
with no false negatives and no false positives, so the method may not rest on a boolean's result.

**The equivalence the detector rests on.** Let `R` be the rib tool's material left inside the
cavity. If the cavity is one connected solid not contained in the tool, then `R` has volume
**exactly when** some point of the tool's boundary lies in the cavity's interior: a path inside the
cavity from a point of `R` to a point outside the tool must cross the tool's boundary there, and
conversely a boundary point inside the cavity has tool material on one side of it, inside the
cavity. So "is any rib left?" becomes "does any tool face enter the cavity?"

**Why each face is tested at depth, not on itself.** In a correct cut the tool's faces lie *on* the
cavity boundary, and coincident geometry is where sectioning and booleans break. So each face is
moved `eps` into the tool and shrunk until it is certified to lie strictly inside the tool. A
correct cavity, being disjoint from the tool, keeps a positive distance from that copy; a cavity
that runs through an uncut rib contains it.

**A face passes only on two certificates, so an error can only produce a flag.**

- *Placed:* the inner copy is a positive distance from the tool's boundary and one of its points is
  inside the tool, so the whole connected copy is inside the tool. Without this certificate the face
  is reported as untestable, never as passing.
- *Clear:* the inner copy is a positive distance from the cavity's boundary and one of its points is
  outside the cavity, so the whole copy is outside the cavity.

A correct cut always earns *clear* for a placed copy, because the copy is inside the tool and the
cavity is outside it; nothing about a correct cut can produce a flag except a failed distance or
containment computation, and those fail toward the flag. A residue reaching more than `eps` past a
tool face puts cavity in contact with the copy, and that face cannot be certified clear. What can be
missed is residue shallower than `eps`, or confined to the margin the shrink leaves along a face's
edges -- both bounded by `eps`, which is set from the wall tolerance.

Kernel-free by the package rule: the caller measures the distances and containments under
`freecadcmd`; this module only decides.
"""

#: The verdicts a face can receive.
CLEAR, FLAGGED, UNTESTABLE = 'clear', 'flagged', 'untestable'


def placed(dist_to_tool_boundary_m, point_inside_tool, clearance_m):
    """Is a face's inner copy certified to lie strictly inside the tool?

    `dist_to_tool_boundary_m` is the copy's minimum distance to the tool's boundary, and
    `point_inside_tool` whether one point of the copy is inside the tool. `None` for either means
    the measurement failed, which never certifies.
    """
    if dist_to_tool_boundary_m is None or point_inside_tool is None:
        return False
    return bool(point_inside_tool) and dist_to_tool_boundary_m >= clearance_m


def verdict(is_placed, dist_to_cavity_boundary_m, point_inside_cavity, clearance_m):
    """`CLEAR`, `FLAGGED` or `UNTESTABLE` for one tool face.

    Clear only when the copy is placed and certified outside the cavity: at least `clearance_m`
    from its boundary, with a point outside it. Any failed measurement (`None`) or any contact is
    a flag. A copy that could not be placed is untestable, which a caller must count against the
    check and never as a pass.
    """
    if not is_placed:
        return UNTESTABLE
    if dist_to_cavity_boundary_m is None or point_inside_cavity is None:
        return FLAGGED
    if point_inside_cavity:
        return FLAGGED
    if dist_to_cavity_boundary_m < clearance_m:
        return FLAGGED
    return CLEAR


def inset_triangle(a, b, c, margin):
    """Triangle `abc` shrunk uniformly by `margin` toward its incenter, or `None` if it vanishes.

    Points are 3-tuples. Scaling about the incenter by `(r - margin) / r`, with `r` the inradius,
    moves every edge inward by exactly `margin`, because each edge is `r` from the incenter. This is
    the exact inset the detector uses where `makeOffset2D` fails on a tool face: every tool face is
    a planar polygon, so its triangulation is exact and each triangle can be inset without the
    kernel. A triangle whose inradius does not exceed `margin` has no interior left and returns
    `None`.
    """
    def sub(p, q):
        return (p[0] - q[0], p[1] - q[1], p[2] - q[2])

    def norm(p):
        return (p[0] ** 2 + p[1] ** 2 + p[2] ** 2) ** 0.5

    def cross(p, q):
        return (p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0])

    la, lb, lc = norm(sub(b, c)), norm(sub(c, a)), norm(sub(a, b))
    perimeter = la + lb + lc
    area = 0.5 * norm(cross(sub(b, a), sub(c, a)))
    if perimeter <= 0.0 or area <= 0.0:
        return None
    r = 2.0 * area / perimeter
    if r <= margin:
        return None
    center = tuple((la * a[i] + lb * b[i] + lc * c[i]) / perimeter for i in range(3))
    k = (r - margin) / r
    return tuple(tuple(center[i] + k * (p[i] - center[i]) for i in range(3)) for p in (a, b, c))
