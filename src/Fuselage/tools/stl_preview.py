"""Render a verification preview PNG directly from an STL mesh.

Replaces the second OpenSCAD invocation in `solid_render`, which passed
`--render` and so re-solved the entire CSG tree a second time purely to take a
picture. The STL produced by the first invocation already *is* the evaluated
geometry, so imaging it is a mesh load plus a rasterization rather than a repeat
of the expensive part.

Dependencies are numpy and the standard library only -- deliberately. A GL-based
renderer (trimesh/pyglet, VTK, Open3D) needs a graphics context, which on Windows
means a hidden window per process and makes the batch fragile and awkward to
parallelize. A software rasterizer has no context to lose, is deterministic, and
parallelizes across processes without further thought.

Projection is orthographic. These images exist to verify geometry, and perspective
actively hurts that -- it makes a feature's size depend on where it sits in the
part, so nothing in the image can be compared to anything else.

Flat shading alone hides two of the three kinds of edge. A step -- one face
parallel to and in front of another -- has identical normals on both sides and
vanishes completely; a shallow crease differs too little in tone to read. Both are
recovered here by post-processing the depth and normal buffers, with ambient
occlusion darkening concave junctions on top. See `_edge_mask` and `_occlusion`.

Units are irrelevant: the camera fits the part's projected extent, so the render is
scale-invariant. Feeding it millimeters or meters produces the same image.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

# The part is chromatic and the background is not, so the two separate by hue as
# well as by value. A grey part on a grey ground has only value to work with, and
# the shading range runs straight through the background tone: any face turned
# away from the light lands on roughly the background's grey and its silhouette
# stops reading there.
BACKGROUND = (0x26, 0x28, 0x2C)     # neutral dark; no hue to compete with the part
FACE_FRONT = (0xA6, 0xC6, 0xE6)     # light blue

# Back faces mark a defect (see `render`), so this must stay unmistakable against
# FACE_FRONT. It used to be blue, which was fine against a grey part and useless
# against a blue one. Red-orange is the widest hue separation available here, and
# reads as a fault besides.
FACE_BACK = (0xD2, 0x4B, 0x38)

EDGE_COLOR = (0x14, 0x18, 0x1F)     # near-black, faintly cool so it sits in the blue

# Floor of the diffuse term: a face pointing fully away still renders at this
# fraction of its base colour. High enough that the darkest face stays clearly
# above the background, which is what keeps a silhouette readable where the part
# curves away. Face-to-face separation is carried by the edge lines and the
# occlusion rather than by driving the shading down towards black.
AMBIENT = 0.42

# Camera rotation as rot_x, rot_y, rot_z in degrees, originally the `--camera`
# argument in solid_render. Translation and distance are not carried over because
# `--viewall --autocenter` overrode them anyway.
#
# rot_z was swung 45 degrees clockwise (as seen from above) from OpenSCAD's 305.20:
# the eye azimuth is -rot_z - 90, so adding to rot_z rotates the camera clockwise.
# That puts square parts square to the frame instead of on the diagonal.
CAMERA_ROTATION_DEG = (64.10, 0.00, 350.20)

# Fraction of the frame left as margin around the fitted part.
DEFAULT_MARGIN = 1.06

# The comment above the old render_opts line read "# 2048,1080" against an active
# 4096x2160. The smaller size is what the images actually needed.
DEFAULT_SIZE = (2048, 1080)

# Crease sharper than this reads as an edge. Tessellated cylinders at the sweep's
# $fa=1 have facet angles near 1 degree, so this is far clear of them.
CREASE_ANGLE_DEG = 28.0

# Render this many times larger in each axis, then box-filter down. 2x is the knee:
# it removes the stair-stepping on silhouettes and edge lines, while 3x costs more
# than it visibly returns at this output size.
DEFAULT_SUPERSAMPLE = 2


def load_stl(path: str | Path) -> np.ndarray:
    """Load a binary or ASCII STL as an (n, 3, 3) array of triangle vertices.

    Binary is detected by checking the header's triangle count against the file
    length, rather than by sniffing for the word "solid" -- binary STLs written by
    some tools begin with it too.
    """
    data = Path(path).read_bytes()
    if len(data) < 84:
        raise ValueError(f"{path}: too short to be an STL ({len(data)} bytes)")

    count = struct.unpack("<I", data[80:84])[0]
    if len(data) == 84 + count * 50:
        # 50 bytes per facet: 3 normal floats, 9 vertex floats, 2 attribute bytes.
        rec = np.dtype([("n", "<3f4"), ("v", "<9f4"), ("attr", "<u2")])
        facets = np.frombuffer(data, dtype=rec, count=count, offset=84)
        return facets["v"].reshape(-1, 3, 3).astype(np.float64)

    return _load_ascii_stl(data, path)


def _load_ascii_stl(data: bytes, path: str | Path) -> np.ndarray:
    verts = [
        [float(p) for p in line.split()[1:4]]
        for line in data.decode("utf-8", "replace").splitlines()
        if line.strip().startswith("vertex")
    ]
    if not verts or len(verts) % 3:
        raise ValueError(f"{path}: not a readable STL ({len(verts)} vertices)")
    return np.asarray(verts, dtype=np.float64).reshape(-1, 3, 3)


def _rotation(rot_deg: tuple[float, float, float]) -> np.ndarray:
    """Build OpenSCAD's gimbal camera rotation as applied to the object.

    OpenSCAD issues gluLookAt and then glRotated(x), glRotated(y), glRotated(z),
    which post-multiply onto the modelview stack. A vertex therefore reaches eye
    space as `V @ Rx @ Ry @ Rz @ p`, so the object takes the rotation with the
    angles *as given* -- they are not inverted.

    Checked by putting the eye back into the part's own frame: `R.T @ (0, -1, 0)`
    gives (+0.357, -0.252, +0.900) for these angles, so the camera looks down at
    the part. Negating the angles flips that z to -0.900 and views it from
    underneath, which is what an earlier version of this function did. Comparing
    renders by eye is what let that through -- a corner post looks plausible
    upside down, and only a part with an unmistakable top, like the nose cowl with
    its flat circular face, makes the error obvious.
    """
    rx, ry, rz = np.radians(rot_deg)
    cx, sx, cy, sy, cz, sz = (
        np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz),
    )
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return mx @ my @ mz


def _shift(arr: np.ndarray, dy: int, dx: int, fill: float) -> np.ndarray:
    """Translate an image by (dy, dx), padding exposed rows/columns with `fill`."""
    out = np.full_like(arr, fill)
    ys_dst = slice(max(dy, 0), arr.shape[0] + min(dy, 0))
    ys_src = slice(max(-dy, 0), arr.shape[0] + min(-dy, 0))
    xs_dst = slice(max(dx, 0), arr.shape[1] + min(dx, 0))
    xs_src = slice(max(-dx, 0), arr.shape[1] + min(-dx, 0))
    out[ys_dst, xs_dst] = arr[ys_src, xs_src]
    return out


def _occlusion(
    zbuf: np.ndarray, nbuf: np.ndarray, unit: float, strength: float = 0.42
) -> np.ndarray:
    """Normal-oriented screen-space ambient occlusion.

    A neighbour occludes this pixel only if it sits nearer than the pixel's own
    tangent plane predicts. Comparing raw depth instead -- the naive form -- counts
    every sloped surface as self-occluding, because a neighbour 16 px away on an
    inclined face is genuinely nearer; the result is a part uniformly darkened
    rather than shaded at its concavities. Using the normal removes that entirely,
    which is worth the extra buffer.

    Orthographic projection makes this unusually well behaved: depth is linear in
    model units, so one threshold works everywhere in the image regardless of how
    far the feature sits from the camera.

    Samples are also bounded above. Without that, a silhouette -- where the
    neighbour is a different surface far closer -- reads as maximum occlusion and
    paints a dark halo around the whole part.
    """
    solid = np.isfinite(zbuf)
    z = np.where(solid, zbuf, 0.0).astype(np.float32)

    # Depth gradient implied by the surface normal. Screen +x is camera +x and
    # screen +y is camera -z, so a step of (dx_px, dy_px) moves along the tangent
    # plane by this much in depth. ny is clamped away from zero: at a silhouette
    # the plane is edge-on and the prediction is meaningless.
    nx, ny, nz = nbuf[:, :, 0], nbuf[:, :, 1], nbuf[:, :, 2]
    ny_safe = np.where(np.abs(ny) < 0.15, np.sign(ny) * 0.15 + 1e-6, ny)

    bias, far = 0.6 * unit, 40.0 * unit
    total = np.zeros(zbuf.shape, dtype=np.float32)
    count = 0
    for radius in (2, 4, 8, 16):
        for dy, dx in ((radius, 0), (-radius, 0), (0, radius), (0, -radius),
                       (radius, radius), (-radius, -radius),
                       (radius, -radius), (-radius, radius)):
            predicted = z - (nx * (dx * unit) + nz * (-dy * unit)) / ny_safe
            zn = _shift(z, dy, dx, 0.0)
            valid = _shift(solid, dy, dx, False) & solid
            gap = predicted - zn
            total += (valid & (gap > bias) & (gap < far)).astype(np.float32)
            count += 1

    ao = 1.0 - strength * (total / count)
    return np.where(solid, ao, 1.0).astype(np.float32)


def _smoothstep(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Ramp from 0 at `lo` to 1 at `hi`, with zero slope at both ends."""
    t = np.clip((x - lo) / max(hi - lo, 1e-12), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _edge_strength(
    zbuf: np.ndarray, nbuf: np.ndarray, unit: float, crease_deg: float
) -> np.ndarray:
    """Per-pixel edge coverage in 0..1 for silhouette, step, and crease edges.

    Continuous rather than a boolean mask. A hard threshold makes a line whose
    measure sits near the cutoff flicker on and off from pixel to pixel, so a
    weak edge renders as a dotted line rather than a faint one. Ramping between a
    lower and upper bound turns that into partial coverage, which reads as a
    continuous line of reduced intensity -- which is what a weak edge should look
    like.

    Depth uses a Laplacian rather than a gradient on purpose. A first difference is
    large anywhere the surface is steeply slanted, which paints false edges across
    every inclined face; the Laplacian cancels constant slope and responds only to
    an actual discontinuity.
    """
    solid = np.isfinite(zbuf)
    z = np.where(solid, zbuf, 0.0)

    up, down = _shift(z, 1, 0, 0.0), _shift(z, -1, 0, 0.0)
    left, right = _shift(z, 0, 1, 0.0), _shift(z, 0, -1, 0.0)
    neighbours_solid = (
        _shift(solid, 1, 0, False) & _shift(solid, -1, 0, False)
        & _shift(solid, 0, 1, False) & _shift(solid, 0, -1, False)
    )

    laplacian = np.abs(4.0 * z - (up + down + left + right))
    step = np.where(solid & neighbours_solid,
                    _smoothstep(laplacian, 0.6 * unit, 2.6 * unit), 0.0)

    # Silhouette: solid abutting background. A genuine discontinuity, so it takes
    # full strength -- its softening comes from supersampling, not from ramping.
    silhouette = (solid & ~neighbours_solid).astype(np.float32)

    # Crease strength ramps in angle rather than in the dot product: the cosine
    # compresses near zero degrees, so equal steps in dot are not equal steps in
    # the quantity being judged, and the ramp would be lopsided.
    crease = np.zeros(zbuf.shape, dtype=np.float32)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        dot = np.clip(np.sum(nbuf * _shift(nbuf, dy, dx, 0.0), axis=2), -1.0, 1.0)
        angle = np.degrees(np.arccos(dot))
        pair = solid & _shift(solid, dy, dx, False)
        ramp = _smoothstep(angle, crease_deg * 0.55, crease_deg * 1.30)
        crease = np.maximum(crease, np.where(pair, ramp, 0.0))

    return np.clip(np.maximum(np.maximum(step, silhouette), crease), 0.0, 1.0)


def render(
    tris: np.ndarray,
    size: tuple[int, int] = DEFAULT_SIZE,
    rot_deg: tuple[float, float, float] = CAMERA_ROTATION_DEG,
    margin: float = DEFAULT_MARGIN,
    background: tuple[int, int, int] = BACKGROUND,
    front: tuple[int, int, int] = FACE_FRONT,
    back: tuple[int, int, int] = FACE_BACK,
    edges: bool = True,
    occlusion: bool = True,
    crease_deg: float = CREASE_ANGLE_DEG,
    supersample: int = DEFAULT_SUPERSAMPLE,
) -> np.ndarray:
    """Render at `supersample`x and box-filter down, then delegate to _render_at.

    Supersampling is what antialiases the silhouette and the edge lines. Edge
    coverage alone cannot: a silhouette is a genuine discontinuity in the depth
    buffer, so at 1x it is exactly one pixel wide and hard, however it is shaded.

    The cost is well under the naive 4x. The rasterizer loops in Python over
    triangles and vectorizes each triangle's pixel span, so quadrupling the pixels
    grows the vectorized part while the per-triangle overhead -- which dominates at
    these mesh sizes -- stays fixed.
    """
    factor = max(1, int(supersample))
    if factor == 1:
        return _render_at(tris, size, rot_deg, margin, background, front, back,
                          edges, occlusion, crease_deg)

    width, height = size
    big = _render_at(tris, (width * factor, height * factor), rot_deg, margin,
                     background, front, back, edges, occlusion, crease_deg)
    return (big.reshape(height, factor, width, factor, 3)
               .mean(axis=(1, 3))
               .round()
               .astype(np.uint8))


def _render_at(
    tris: np.ndarray,
    size: tuple[int, int],
    rot_deg: tuple[float, float, float],
    margin: float,
    background: tuple[int, int, int],
    front: tuple[int, int, int],
    back: tuple[int, int, int],
    edges: bool,
    occlusion: bool,
    crease_deg: float,
) -> np.ndarray:
    """Rasterize triangles to an (h, w, 3) uint8 image.

    Back-facing triangles are shaded in `back`, which acts as a **defect
    indicator**: on a closed, consistently wound solid the z-buffer never shows a
    back face, so a well-formed part renders entirely in `front`. Any blue means
    the mesh is open, inverted, or self-intersecting there -- worth seeing, since a
    parametric sweep will eventually reach a corner of the parameter space that
    produces bad geometry.

    This deliberately does not reproduce the blue in the pre-existing OpenSCAD
    previews. That came from OpenSCAD's CGAL viewer coloring its own internal
    representation and is not information the exported STL carries; the meshes
    themselves are cleanly wound.
    """
    width, height = size
    image = np.empty((height, width, 3), dtype=np.float32)
    image[:] = background
    if len(tris) == 0:
        return image.astype(np.uint8)

    verts = tris.reshape(-1, 3)
    center = (verts.min(axis=0) + verts.max(axis=0)) / 2.0
    if not np.any(verts.max(axis=0) - verts.min(axis=0)):
        return image.astype(np.uint8)

    cam = (tris - center) @ _rotation(rot_deg).T

    # OpenSCAD's gimbal camera looks along +Y with +Z up -- not the Z-forward/Y-up
    # basis most renderers default to. Getting this wrong yields a plausible image
    # from entirely the wrong angle.
    flat = cam.reshape(-1, 3)
    x_lo, x_hi = float(flat[:, 0].min()), float(flat[:, 0].max())
    z_lo, z_hi = float(flat[:, 2].min()), float(flat[:, 2].max())
    span_x = max(x_hi - x_lo, 1e-9)
    span_z = max(z_hi - z_lo, 1e-9)

    # Fit the projected bounding box, not the bounding sphere. OpenSCAD's --viewall
    # uses the sphere, which for a long thin part is mostly empty space.
    scale = min(width / (span_x * margin), height / (span_z * margin))
    sx = width / 2.0 + scale * (cam[:, :, 0] - (x_lo + x_hi) / 2.0)
    sy = height / 2.0 - scale * (cam[:, :, 2] - (z_lo + z_hi) / 2.0)

    # The eye is on the -Y side, so smaller y is nearer and depth ordering is just y.
    depth = cam[:, :, 1]

    # Screen-space winding decides front vs back after projection -- not the STL's
    # stored normal, which some exporters get wrong.
    area = (sx[:, 1] - sx[:, 0]) * (sy[:, 2] - sy[:, 0]) - (sx[:, 2] - sx[:, 0]) * (
        sy[:, 1] - sy[:, 0]
    )
    facing_front = area < 0

    normals = np.cross(cam[:, 1] - cam[:, 0], cam[:, 2] - cam[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    good = (lengths > 1e-12) & (np.abs(area) > 1e-9)
    normals[good] /= lengths[good, None]

    # Headlight from the eye side (-Y), lifted in +Z so faces at different angles
    # separate instead of flattening into one tone.
    light = np.array([-0.35, -0.82, 0.45])
    light /= np.linalg.norm(light)
    shade = AMBIENT + (1.0 - AMBIENT) * np.abs(normals @ light)

    base = np.where(facing_front[:, None], np.array(front), np.array(back))
    colors = (base * shade[:, None]).astype(np.float32)

    xmin = np.floor(sx.min(axis=1)).astype(np.int64)
    xmax = np.ceil(sx.max(axis=1)).astype(np.int64)
    ymin = np.floor(sy.min(axis=1)).astype(np.int64)
    ymax = np.ceil(sy.max(axis=1)).astype(np.int64)
    visible = good & (xmax >= 0) & (xmin < width) & (ymax >= 0) & (ymin < height)

    zbuf = np.full((height, width), np.inf)
    nbuf = np.zeros((height, width, 3), dtype=np.float32)
    _rasterize(
        image, zbuf, nbuf, sx, sy, depth, colors, normals.astype(np.float32),
        np.clip(xmin, 0, width - 1), np.clip(xmax, 0, width - 1),
        np.clip(ymin, 0, height - 1), np.clip(ymax, 0, height - 1),
        np.flatnonzero(visible),
    )

    # One pixel expressed in model units -- the natural threshold unit for both the
    # occlusion window and the depth-step test, and what makes them resolution- and
    # scale-independent.
    unit = 1.0 / scale

    if occlusion:
        image *= _occlusion(zbuf, nbuf, unit)[:, :, None]
    if edges:
        # Blend by coverage rather than overwriting. A partially-covered pixel keeps
        # some of the shading underneath, which is what makes a faint edge read as a
        # faint line instead of a broken one.
        alpha = _edge_strength(zbuf, nbuf, unit, crease_deg)[:, :, None]
        image = image * (1.0 - alpha) + np.asarray(EDGE_COLOR, dtype=np.float32) * alpha

    return np.clip(image, 0, 255).astype(np.uint8)


def _rasterize(
    image, zbuf, nbuf, sx, sy, depth, colors, normals, x0, x1, y0, y1, order
) -> None:
    """Scatter triangles into the colour, depth, and normal buffers.

    Loops in Python over triangles but vectorizes each triangle's pixel span, which
    is the right split here: parts average a few thousand covered pixels spread over
    tens of thousands of small triangles, so per-triangle numpy overhead dominates
    and a fully vectorized scatter would cost more memory than it saves time.
    """
    for i in order:
        ax, bx, cx = sx[i]
        ay, by, cy = sy[i]
        denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(denom) < 1e-12:
            continue

        xs = np.arange(x0[i], x1[i] + 1)
        ys = np.arange(y0[i], y1[i] + 1)
        if xs.size == 0 or ys.size == 0:
            continue
        px = xs[None, :] + 0.5
        py = ys[:, None] + 0.5

        w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denom
        w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denom
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue

        da, db, dc = depth[i]
        z = w0 * da + w1 * db + w2 * dc
        ysl, xsl = slice(ys[0], ys[-1] + 1), slice(xs[0], xs[-1] + 1)
        tile_z = zbuf[ysl, xsl]
        hit = inside & (z < tile_z)
        if not hit.any():
            continue
        tile_z[hit] = z[hit]
        image[ysl, xsl][hit] = colors[i]
        nbuf[ysl, xsl][hit] = normals[i]


def write_png(path: str | Path, rgb: np.ndarray) -> None:
    """Write an 8-bit RGB PNG using only zlib and struct.

    Avoids pulling in Pillow for what is, for a non-interlaced truecolor image, a
    header, one zlib stream of filter-0 scanlines, and a trailer.
    """
    height, width, _ = rgb.shape
    raw = np.concatenate(
        [np.zeros((height, 1), dtype=np.uint8), rgb.reshape(height, -1)], axis=1
    ).tobytes()

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def render_stl_to_png(
    stl_path: str | Path,
    png_path: str | Path,
    size: tuple[int, int] = DEFAULT_SIZE,
    **kwargs,
) -> Path:
    """Load an STL, render it, and write the PNG. Returns the PNG path."""
    write_png(png_path, render(load_stl(stl_path), size=size, **kwargs))
    return Path(png_path)


def render_one(job: tuple) -> tuple[str, str | None]:
    """Render one STL to the PNG beside it. Returns (path, error-or-None).

    The entry point for a process pool, so it lives here rather than in the sweep:
    a spawned worker imports the module this is defined in, and importing a numpy
    renderer is far cheaper than importing the whole generator toolchain with
    pandas and solid2 behind it.

    Returns the error rather than raising so one bad mesh names itself instead of
    taking down the batch.
    """
    stl_path, size, edges, occlusion, supersample = job
    try:
        render_stl_to_png(
            stl_path,
            Path(stl_path).with_suffix(".png"),
            size=size,
            edges=edges,
            occlusion=occlusion,
            supersample=supersample,
        )
        return stl_path, None
    except Exception as exc:  # noqa: BLE001 - reported per file, never swallowed
        return stl_path, f"{type(exc).__name__}: {exc}"


if __name__ == "__main__":
    import sys

    if not 3 <= len(sys.argv) <= 5:
        sys.exit(f"usage: {sys.argv[0]} <in.stl> <out.png> [width] [height]")
    dims = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) == 5 else DEFAULT_SIZE
    out = render_stl_to_png(sys.argv[1], sys.argv[2], dims)
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
