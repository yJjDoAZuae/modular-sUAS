"""Measuring a wall's local thickness, and deciding which measure to trust.

The acceptance gate on the cowl wall compares a nearest-point minimum against `WALL_TOL` = 0.01 mm,
and that minimum does not converge: it was still falling at 3840 inner samples at 17 of 24 stations,
because a nearest-point distance at a concave corner crosses the corner rather than the wall. The
one measure that does converge is a mean and cannot see a local thin spot. So no figure this project
has recorded about wall thickness is a settled number.

This package exists to end that by measurement rather than by argument:

* `truth` builds shapes whose **true** local thickness is known in closed form, which is the thing
  every measure here has been missing. Convergence under refinement only shows a measure settles;
  it can settle on the wrong number, and the area-based mean reading 0.4753 mm where the wall is
  0.6 mm is this project's own example.
* `sections` extracts a station's section as plain coordinate arrays, so a candidate measure is
  numerical work in `numpy` rather than a vendor call per sample.
* The candidates and the five-gate screening harness follow in this package.
* `corpus` reaches the 28 saved soak walls, and `sweep` runs several measures over them on
  identical sections, which is the only comparison that holds without the cowl body.
* `prediction` reads `cavity()`'s own pass-2 prediction back out of a build log and sets it against
  those real readings. That measurement is what withdrew OQ-DES-CW23: the "small residual gap" it
  asked how to handle is zero below `U` = 3 and 0.11-0.17 mm above it.
* `normal_distance` is the only measure here that is **not** in-plane, and it exists because every
  other one is. A plane cutting a slab inclined at theta reads `thickness / cos theta`, always
  thicker than the slab; measured on a real `tail_shell` the interior surface is inclined 21.6-22.1
  degrees where the wall is thin, so every in-plane figure there is inflated by 1.079 and the real
  deficit is 0.0550 mm where the incumbent reads 0.0115.
* `inputs` is the one module here that cannot work from the saved corpus. Every wall the 2026-10-06
  soak left varies `U` alone, so a question about any other design input needs walls that do not
  exist yet; `inputs` holds the case list, the sheet-cell arithmetic and the verdict for building
  them, and `corpus.screen` reads them back as a population deliberately kept apart from the soak's.

**Nothing here imports a vendor module at module scope.** The builders take `Part` and `App` as
arguments -- bridge proxies in a test, real modules under `freecadcmd` -- so this package is
importable from the project's own interpreter and the measures run client-side.

The plan is doc/implementation/wall_thickness_measure.md and the design basis is
doc/design/cowl_interior_surface.md section 5, "The three convergences, and where the chain breaks".
"""
