"""IP-WTM-1: walls whose true local thickness is known in closed form.

**Why this module is first in its plan.** Every wall-thickness measure this project has tried was
judged by whether it agreed with *itself* under refinement, and none by whether it agreed with a
known answer. That is how a measure which converges on the wrong number survived as a candidate:
the area-based mean settles to 1e-6 mm and reads 0.4753 mm where the wall is 0.6 mm. Convergence is
necessary and not sufficient, so the screening needs geometry where the right answer is arithmetic.

**All three fixtures are concentric cylinders, which is what makes the truth exact.** Between two
coaxial cylinders of radii `r_in` and `r_out`, the radial distance, the nearest-point distance and
the inscribed-circle diameter are all exactly `r_out - r_in`. Every candidate measure's own
definition therefore agrees on the answer, so a disagreement is the measure's error and nothing
else. A flat-bottomed pocket milled into a curved wall would not have that property -- its depth
varies across the pocket by the cylinder's sag, 0.0045 mm over a 0.6 mm chord at `R` = 10, which is
the same order as the defects being measured.

Three shapes, each with one thing wrong with it:

* `uniform_tube` -- nothing wrong. Fixes accuracy (gate G3): a measure that cannot read a constant
  wall has no business reading a cowl.
* `thin_patch_tube` -- a sector where the outer radius is reduced, so the wall is **thinner** by a
  known amount over a known arc. Fixes discrimination (gates G1 and G4): this is the defect the
  slicer responds to, and the measure must both see it and say how deep it is.
* `ribbed_tube` -- a sector where the inner radius is reduced, so the wall is **thicker** by a known
  amount, and the inner boundary gains two re-entrant corners. This reproduces the real cowl's rib:
  "the wall follows the notch in and back out again and the inner contour dips with it". It is the
  shape that exposes the incumbent's own failure cause, since a nearest-point distance taken at one
  of those concave corners crosses the corner instead of the wall.

Every builder takes the `Part` and `App` modules as arguments and returns a :class:`WallTruth`,
whose `true_thickness_at` answers for any point on any section. See
doc/implementation/wall_thickness_measure.md.
"""
import math

from . import kern

#: Default tube geometry. `WALL_M` is the cowl's own wall -- `cowl_n_perimeters` *
#: `extrusion_width` = 1 * 0.6 mm -- so readings here are on the same scale as the real part's.
#: Converted from 10.0 / 0.6 / 20.0 mm by IP-FC-163; the fixtures are the same size they were.
R_OUTER_M = 0.010
WALL_M = 6.0e-4
HEIGHT_M = 0.020

#: How far a cutting or adding ring reaches past the tube's outer surface, so it cuts cleanly
#: rather than meeting it tangentially. Named rather than written inline at each of the three
#: `makeCylinder` calls that use it: a bare `1.0e-3` beside a `kern.mm()` reads as a conversion
#: artifact, and `tools/unit_regime.py` reports it as an unexplained inline dimension -- which it
#: was, in the one module where the fixtures' exactness is the whole point.
RING_PAD_M = 1.0e-3

#: The same thing for `_sector_limiter`'s pie wedge, which has to clear the outer surface by more
#: because it is cut against a ring that has already been padded.
SECTOR_PAD_M = 2.0e-3

#: How close to a feature's own edge a sample has to be before its true thickness is ambiguous.
#: At a patch or rib boundary the wall steps discontinuously, so a sample there has two defensible
#: answers and scoring it would measure the fixture rather than the candidate. Samples inside this
#: margin are reported as `None` by `true_thickness_at` and excluded from accuracy scoring.
EDGE_MARGIN_M = 5.0e-5


class WallTruth(object):
    """A wall with a closed-form local thickness, and the shape that realizes it."""

    __slots__ = ('shape', 'label', 'nominal', 'r_outer', 'features')

    def __init__(self, shape, label, nominal, r_outer, features=()):
        #: The solid, as whatever the caller's `Part` produced -- a bridge proxy or a real shape.
        self.shape = shape
        self.label = label
        #: The wall thickness away from every feature.
        self.nominal = nominal
        self.r_outer = r_outer
        #: Each feature is a dict with `kind`, `thickness`, `z_lo`, `z_hi`, `half_angle` and
        #: `arc`. Kept as plain data so a test can assert against it without reaching into
        #: geometry.
        self.features = tuple(features)

    def __repr__(self):
        return '<WallTruth %s nominal=%.4f features=%d>' % (
            self.label, self.nominal, len(self.features))

    def covering(self, x, y, z):
        """`(outer_features, inner_features)` covering this point, or `'ambiguous'` near an edge.

        **Every feature is counted, not the first one found.** An earlier version returned a single
        feature, which silently gave the wrong answer wherever two overlap -- and the one fixture
        that matters most, a thin patch spanning a concave corner, is exactly an overlap of a patch
        on the outer surface with a rib on the inner. Thickness is the difference of two radii, so
        features are summed per surface rather than selected between.
        """
        angle = math.atan2(y, x)
        radius = math.hypot(x, y) or 1.0
        outer, inner = [], []
        for f in self.features:
            # Angular margin expressed as an arc length, so it means the same thing at any radius.
            ang_margin = EDGE_MARGIN_M / radius
            d_ang = abs(_wrap(angle - f['angle_rad']))
            near_ang = abs(d_ang - f['half_angle_rad']) < ang_margin
            near_z = (abs(z - f['z_lo_m']) < EDGE_MARGIN_M
                      or abs(z - f['z_hi_m']) < EDGE_MARGIN_M)
            inside_ang = d_ang <= f['half_angle_rad'] - ang_margin
            inside_z = f['z_lo_m'] + EDGE_MARGIN_M <= z <= f['z_hi_m'] - EDGE_MARGIN_M
            spans_z = f['z_lo_m'] <= z <= f['z_hi_m']
            spans_ang = d_ang <= f['half_angle_rad']
            # Only a point near an edge *of a feature it is otherwise in line with* is ambiguous:
            # a sample far round the section from a patch is not made ambiguous by its z.
            if (near_ang and spans_z) or (near_z and spans_ang):
                return 'ambiguous'
            if inside_ang and inside_z:
                (outer if f['surface'] == 'outer' else inner).append(f)
        return outer, inner

    def feature_at(self, x, y, z):
        """The first feature covering this point, or `None`; `'ambiguous'` near an edge.

        Kept for readability where a fixture has one feature. Use `covering` where features may
        overlap.
        """
        got = self.covering(x, y, z)
        if got == 'ambiguous':
            return 'ambiguous'
        outer, inner = got
        both = list(outer) + list(inner)
        return both[0] if both else None

    def true_thickness_at(self, x, y, z):
        """The exact local wall thickness at a point, or `None` where it is ambiguous.

        Computed as the difference of the two radii -- `r_outer` reduced by every outer-surface
        feature covering the point, `r_outer - nominal` reduced by every inner-surface one -- so
        overlapping features compose correctly instead of one shadowing the other.

        `None` means the point sits within `EDGE_MARGIN_M` of a feature boundary, where the wall steps
        and two answers are defensible. Scoring such a point would measure the fixture.
        """
        got = self.covering(x, y, z)
        if got == 'ambiguous':
            return None
        outer, inner = got
        r_out = self.r_outer + sum(f['delta_m'] for f in outer)
        r_in = (self.r_outer - self.nominal) + sum(f['delta_m'] for f in inner)
        return r_out - r_in


def _wrap(a):
    """An angle difference folded into (-pi, pi]."""
    while a <= -math.pi:
        a += 2.0 * math.pi
    while a > math.pi:
        a -= 2.0 * math.pi
    return a


def _sector_limiter(Part, App, r_outer_m, half_angle_rad, z_lo_m, z_hi_m,
                    angle_rad=0.0):
    """An exact pie wedge spanning `angle +/- half_angle`, generous in radius.

    **A true sector, not a box, because the truth function decides a point's feature by angle.**
    A box of constant width subtends a *larger* angle the closer it gets to the axis -- a 0.72 mm
    wide box reaches 0.036 rad at `r` = 10 where 0.03 rad was asked for, 20% too wide -- so the
    geometry and the truth function would disagree about where the feature ends, and every accuracy
    figure measured against it would inherit that. `Part.makeCylinder`'s own sweep-angle argument
    gives the sector exactly: checked against the closed form at 130.899694 mm3 to six decimals.
    """
    # SI in, millimeters only inside the kernel calls (IP-FC-163). `SECTOR_PAD_M` is the 2.0 mm
    # it always was: enough to clear the outer surface so the sector cuts cleanly.
    wedge = Part.makeCylinder(kern.mm(r_outer_m + SECTOR_PAD_M), kern.mm(z_hi_m - z_lo_m),
                              App.Vector(0.0, 0.0, kern.mm(z_lo_m)), App.Vector(0.0, 0.0, 1.0),
                              math.degrees(2.0 * half_angle_rad))
    # `makeCylinder` sweeps from 0, so rotate the wedge's bisector onto `angle_rad`.
    wedge.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1),
                 math.degrees(angle_rad - half_angle_rad))
    return wedge


def uniform_tube(Part, App, r_outer_m=R_OUTER_M, wall_m=WALL_M, height_m=HEIGHT_M):
    """A straight tube of constant wall. True thickness is `wall` everywhere.

    Gate G3's fixture. All three candidate definitions of local thickness coincide on an annulus,
    so any deviation a measure reports here is its own error.
    """
    outer = Part.makeCylinder(kern.mm(r_outer_m), kern.mm(height_m))
    inner = Part.makeCylinder(kern.mm(r_outer_m - wall_m), kern.mm(height_m))
    shape = outer.cut(inner)
    return WallTruth(shape, 'uniform_tube', wall_m, r_outer_m)


def thin_patch_tube(Part, App, r_outer_m=R_OUTER_M, wall_m=WALL_M, height_m=HEIGHT_M,
                    depth_m=1.5e-4, arc_m=6.0e-4, band_m=4.0e-3, angle_rad=0.0):
    """A tube with one sector whose outer radius is reduced by `depth`.

    True thickness is `wall - depth` inside the patch and `wall` outside it, both exactly, because
    the patch's outer surface is a cylinder of radius `r_outer - depth` concentric with the bore.

    `arc` is the patch's extent **along the section**, in millimeters, and defaults to one extrusion
    width (0.6 mm) -- the shortest thin spot the slicer can act on, and therefore the shortest one
    gate G1 requires a measure to see. `depth` defaults to 0.15 mm, 15x `WALL_TOL`, so a measure
    that reports the patch at all reports it unambiguously.
    """
    tube = uniform_tube(Part, App, r_outer_m, wall_m, height_m).shape
    z_lo_m = (height_m - band_m) / 2.0
    z_hi_m = z_lo_m + band_m
    # A ratio of two lengths, so unit-invariant and unchanged by the conversion.
    half_angle_rad = arc_m / (2.0 * r_outer_m)

    # An annular ring from `r_outer_m - depth_m` outward: cutting it away leaves the patch's outer
    # surface **on a cylinder**, which is what makes the thickness exact rather than approximate.
    ring = (Part.makeCylinder(kern.mm(r_outer_m + RING_PAD_M), kern.mm(band_m),
                              App.Vector(0.0, 0.0, kern.mm(z_lo_m)))
            .cut(Part.makeCylinder(kern.mm(r_outer_m - depth_m), kern.mm(band_m),
                                   App.Vector(0.0, 0.0, kern.mm(z_lo_m)))))
    cutter = ring.common(_sector_limiter(Part, App, r_outer_m, half_angle_rad,
                                         z_lo_m, z_hi_m, angle_rad))
    shape = tube.cut(cutter)

    feature = {'kind': 'thin', 'thickness_m': wall_m - depth_m, 'depth_m': depth_m,
               'surface': 'outer', 'delta_m': -float(depth_m),
               'z_lo_m': z_lo_m, 'z_hi_m': z_hi_m, 'half_angle_rad': half_angle_rad,
               'arc_m': arc_m, 'angle_rad': angle_rad, 'z_mid_m': (z_lo_m + z_hi_m) / 2.0}
    return WallTruth(shape, 'thin_patch_tube', wall_m, r_outer_m, [feature])


def ribbed_tube(Part, App, r_outer_m=R_OUTER_M, wall_m=WALL_M, height_m=HEIGHT_M,
                rise_m=4.0e-4, arc_m=3.0e-3, band_m=6.0e-3, angle_rad=0.0):
    """A tube with one sector whose inner radius is reduced by `rise`: a rib, with two creases.

    True thickness is `wall + rise` inside the rib and `wall` outside it. The point of this fixture
    is not the thickness but the **two re-entrant corners** where the rib meets the bore: that is
    the concave corner a nearest-point distance crosses instead of measuring the wall, which is the
    established cause of the incumbent measure's non-convergence. A measure that reads `wall`
    correctly on the flank right beside a crease has survived the thing that defeats the incumbent.

    Reproduces the real part's behavior, where the wall legitimately reads *more* than nominal over
    a rib because the inner contour dips with the notch.
    """
    tube = uniform_tube(Part, App, r_outer_m, wall_m, height_m).shape
    z_lo_m = (height_m - band_m) / 2.0
    z_hi_m = z_lo_m + band_m
    half_angle_rad = arc_m / (2.0 * r_outer_m)

    # Material added inward, from `r_outer_m - wall_m - rise_m` out to the bore, so the rib's own
    # inner surface is again a cylinder and its thickness is exact.
    ring = (Part.makeCylinder(kern.mm(r_outer_m - wall_m), kern.mm(band_m),
                              App.Vector(0.0, 0.0, kern.mm(z_lo_m)))
            .cut(Part.makeCylinder(kern.mm(r_outer_m - wall_m - rise_m), kern.mm(band_m),
                                   App.Vector(0.0, 0.0, kern.mm(z_lo_m)))))
    rib = ring.common(_sector_limiter(Part, App, r_outer_m, half_angle_rad,
                                      z_lo_m, z_hi_m, angle_rad))
    shape = tube.fuse(rib).removeSplitter()

    feature = {'kind': 'rib', 'thickness_m': wall_m + rise_m, 'rise_m': rise_m,
               'surface': 'inner', 'delta_m': -float(rise_m),
               'z_lo_m': z_lo_m, 'z_hi_m': z_hi_m, 'half_angle_rad': half_angle_rad,
               'arc_m': arc_m, 'angle_rad': angle_rad, 'z_mid_m': (z_lo_m + z_hi_m) / 2.0}
    return WallTruth(shape, 'ribbed_tube', wall_m, r_outer_m, [feature])


def corner_patch_tube(Part, App, r_outer_m=R_OUTER_M, wall_m=WALL_M, height_m=HEIGHT_M,
                      depth_m=1.5e-4, arc_m=6.0e-4, rise_m=4.0e-4, rib_arc_m=3.0e-3,
                      band_m=4.0e-3):
    """**The decisive fixture: a thin patch sitting exactly on a concave corner.**

    IP-WTM-17. Candidate C4 passes every other gate by *excluding* samples within 0.3 mm of a
    concave corner, and on a real wall that makes the section read exactly nominal. There are two
    readings of that and no gate so far can tell them apart: either the corners were the whole
    artifact and the wall is compliant, or **the exclusion is blind precisely where a wall is
    thinnest**, in which case C4 passes the screening and ships a part with a hole.

    This fixture separates them. A rib on the bore puts a re-entrant corner at a known angle; a
    thin patch on the outer surface is then centered on that same angle, one extrusion width wide,
    so the defect lies inside any plausible corner-exclusion zone. A measure that drops
    corner-adjacent samples cannot see it; a measure that sees it has shown the exclusion is not
    hiding real thinness.

    The two features overlap, which is why `WallTruth` composes radius modifiers instead of
    selecting one feature: across the patch the true wall steps from `wall + rise - depth` on the
    rib side of the corner to `wall - depth` on the other, and both are exact.
    """
    z_lo_m = (height_m - band_m) / 2.0
    z_hi_m = z_lo_m + band_m
    rib_half = rib_arc_m / (2.0 * r_outer_m)
    patch_half = arc_m / (2.0 * r_outer_m)
    # The rib spans [-rib_half, +rib_half]; its corner is at +rib_half, and the patch is centered
    # there, so half the patch lies over the rib and half over plain wall.
    corner = rib_half

    tube = uniform_tube(Part, App, r_outer_m, wall_m, height_m).shape
    rib_ring = (Part.makeCylinder(kern.mm(r_outer_m - wall_m), kern.mm(band_m),
                                  App.Vector(0.0, 0.0, kern.mm(z_lo_m)))
                .cut(Part.makeCylinder(kern.mm(r_outer_m - wall_m - rise_m), kern.mm(band_m),
                                       App.Vector(0.0, 0.0, kern.mm(z_lo_m)))))
    rib = rib_ring.common(_sector_limiter(Part, App, r_outer_m, rib_half,
                                          z_lo_m, z_hi_m, 0.0))
    with_rib = tube.fuse(rib).removeSplitter()

    patch_ring = (Part.makeCylinder(kern.mm(r_outer_m + RING_PAD_M), kern.mm(band_m),
                                    App.Vector(0.0, 0.0, kern.mm(z_lo_m)))
                  .cut(Part.makeCylinder(kern.mm(r_outer_m - depth_m), kern.mm(band_m),
                                         App.Vector(0.0, 0.0, kern.mm(z_lo_m)))))
    cutter = patch_ring.common(
        _sector_limiter(Part, App, r_outer_m, patch_half, z_lo_m, z_hi_m, corner))
    shape = with_rib.cut(cutter)

    rib_feature = {'kind': 'rib', 'thickness_m': wall_m + rise_m, 'rise_m': rise_m,
                   'surface': 'inner', 'delta_m': -float(rise_m),
                   'z_lo_m': z_lo_m, 'z_hi_m': z_hi_m, 'half_angle_rad': rib_half,
                   'arc_m': rib_arc_m, 'angle_rad': 0.0,
                   'z_mid_m': (z_lo_m + z_hi_m) / 2.0}
    patch_feature = {'kind': 'thin', 'thickness_m': wall_m - depth_m, 'depth_m': depth_m,
                     'surface': 'outer', 'delta_m': -float(depth_m),
                     'z_lo_m': z_lo_m, 'z_hi_m': z_hi_m, 'half_angle_rad': patch_half,
                     'arc_m': arc_m, 'angle_rad': corner,
                     'z_mid_m': (z_lo_m + z_hi_m) / 2.0, 'on_corner': True}
    return WallTruth(shape, 'corner_patch_tube', wall_m, r_outer_m,
                     [rib_feature, patch_feature])


#: The fixtures, by name, for a harness that wants to iterate them.
BUILDERS = {
    'uniform_tube': uniform_tube,
    'thin_patch_tube': thin_patch_tube,
    'ribbed_tube': ribbed_tube,
    'corner_patch_tube': corner_patch_tube,
}
