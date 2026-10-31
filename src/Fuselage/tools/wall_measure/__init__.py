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
* `fit_response` is the interior fit's own response to a displaced row, in closed form and without
  a build. The fit is an interpolation, so a one-row nudge moves the surface by exactly that row's
  cardinal function -- zero at every other row, and amplified by 1 / the gap when a near-duplicate
  station pair sits beside the nudged one. Measured against the kernel at 0.997 to 0.999.
* `probe` is this package's **interface to the construction**, and the reason `cowl_interior`'s own
  entry points carry no measurement arguments. Driving the booleans after the fit needs a way to
  perturb the eroded contour and a way to seed a station set the production floor would thin; both
  were first parameters on `cavity` and `shell_solid`, which put test-only features in a production
  signature. They are now one inert module-level seam the construction reads, and everything about
  what a probe is, what it may change, and installing and removing one lives here.
* `ring_breaks` measures how far a break in the wall's section ring runs along the axis, which is
  the figure OQ-DES-CW26 has never had: the severance on record is quantified circumferentially, at
  93 mm of a 1600 mm ring at one station. It takes the classifier as an argument, so the run-finding
  and the end-bisection are testable against a synthetic break of **known** extent -- the one test
  real geometry cannot supply, since the extent is the unknown. It also prints what a scan would
  have missed, because a clean scan means "no break longer than the station spacing".
* `refusals` keeps the shape a refusal was measured on, which until 2026-10-29 was destroyed along
  with the exception: the post-cut pass refused a wall closed to 0.0001 mm at `z` = -73.1818 and the
  cavity that reading came from was gone, so asking what the geometry looks like there cost another
  1.94 hour build. `Unconverged` now carries `shape` and `z`, and this is the side that writes them
  down -- with the exporter as an argument, so none of it needs the kernel. Its one rule is that
  saving evidence must never fail the refusal: it runs inside a caller's `except` block, so it
  reports an export failure instead of raising and replacing the finding with a failure to find it.
* `station_sets` reads the station-gap screen's records back as a population, which is the only
  form in which OQ-DES-CW26's two-input question has an answer: 242 pair cases, each judged against
  its own station floor, because the two rows that set the wall thickness also move that floor.
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
