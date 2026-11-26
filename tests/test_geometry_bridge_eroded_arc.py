"""OQ-DES-CW37 / IP-FC-173: `eroded_arc` must erode the real nose sections its ladder ran out on.

Found 2026-11-26 by the IP-FC-152 survey. On a `nose_cowl_shell` at `U` = 3, the wall check's
rib-gap measurement raised P3 at z = -83.9998 mm: the refit was refused by `makeOffset2D` at all
three rungs of the shipped ladder (524, 1048 and 2096 points on a 131.097 mm arc). A scan of the
same cell found three more such stations within 0.1 mm of it. Those four are pinned here.

On the body this file builds, three of the four are refused under the shipped ladder (2026-11-26:
-83.9998, -83.9997 and -83.8998); -83.9995 happens to clear. That is the chaos below at work -- this
body comes by a shorter route than the shelled build's and is a different draw at the last bits --
and it is why all four stay pinned: a fix has to clear every one, not the ones that fail today.

**A real cowl, not a tube.** The failure is a property of these particular sections, and nothing
synthetic is known to reproduce it -- the refusal is deterministic but chaotic in the station's
position (a 1e-12 mm move of the slice flips it), so a stand-in section would be testing a different
draw. The cell body alone is built, not the shelled part: about 4 s, against minutes for the shell,
and the body is all `eroded_arc` is ever handed.

**Strict xfail until IP-FC-173 lands.** Which ladder fixes it is OQ-DES-CW37's open decision; this
file pins the stations any fix must clear. When the fix makes the test pass, strict mode fails the
run so the marker is removed rather than left to hide a later regression.

See doc/design/cowl.md OQ-DES-CW37 and doc/design/cowl_interior_surface.md §10.0.
"""

import contextlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "Fuselage" / "tools"))

from conftest import requires_freecad  # noqa: E402
from geometry_bridge.remote_errors import PreconditionFailed  # noqa: E402

pytestmark = requires_freecad

#: The swept size at which the ladder ran out.
U = 3.0

#: The nose's wall thickness at that `U`, in meters -- the `Inset` the shelled build reports
#: (0.6000 mm in the survey log), so the erosion here is the one the check performed.
WALL_M = 0.6e-3

#: The stations, in millimeters, at which every rung of the shipped ladder was refused. Millimeters
#: because they are kernel slice heights copied from the scan; converted at the call.
EXHAUSTED_Z_MM = (-83.9998, -83.9997, -83.9995, -83.8998)


def _literal_rows(params):
    """The plain-number rows of a `PARAMS` list -- `parameters._literals`, applied this side.

    `parameters` is not on the worker's module allow-list and does not need to be: the rows cross
    the bridge by value, and the filter is a pure one, so widening the worker for it would trade a
    production boundary for a test's convenience.
    """
    out = {}
    for alias, value in params:
        text = str(value).strip()
        if text.startswith("="):
            continue
        with contextlib.suppress(ValueError):
            out[alias] = float(text)
    return out


@pytest.fixture
def nose_body(fc):
    """The un-mirrored `nose_cowl` cell body at `U` = 3, as the build's own tree emits it.

    `cowl_tree.emit`'s three steps, written out, because `emit` takes the builder as a function
    and a function does not cross the bridge as an argument.
    """
    App = fc.module("FreeCAD")
    cowl_tree = fc.module("cowl_tree")
    corner_common = fc.module("corner_common")
    params = cowl_tree.PARAMS_NOSE_COWL_SHELL
    doc = App.newDocument("cw37_nose_u3")
    cowl_tree.C._SEEN.clear()
    corner_common.build_sheet(doc, params, dict(_literal_rows(params), U=U))
    cowl_tree.nose_cowl(doc)
    doc.recompute()
    return cowl_tree.pieces(doc)[0].Shape


@pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="OQ-DES-CW37 is open; IP-FC-173 changes the ladder"
)
def test_the_nose_at_u3_erodes_where_the_shipped_ladder_ran_out(nose_body, ci):
    planes = ci.cell_boundary_planes(nose_body)
    refused = []
    for z_mm in EXHAUSTED_Z_MM:
        z_m = z_mm / 1000.0
        wires = ci._slice_wires(nose_body, z_m)
        assert len(wires) == 1, f"z = {z_mm:.4f} mm sections into {len(wires)} loops"
        arc, p_start, p_end, flip = ci.open_arc(wires[0], planes)
        try:
            xy_m = ci.eroded_arc(arc, WALL_M, z_m, p_start, p_end, flip)
        except PreconditionFailed:
            refused.append(z_mm)
            continue
        assert len(xy_m) >= 2
    assert refused == [], f"eroded_arc raised P3 at z = {refused} mm"
