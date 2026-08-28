"""IP-FC-45: which module builds which kind of part, stated once.

Two places need this and they cannot import each other. `build_part.py` runs under
`freecadcmd` and imports `FreeCAD` at module scope, so the project virtualenv cannot read
it; `tools/freecad_render.py` runs in the virtualenv and drives `freecadcmd` as a
subprocess, so FreeCAD's Python never sees it. Without somewhere neutral to put the table,
each keeps its own copy -- and a copy that says a kind is built by a module it is not built
by produces the IP-FC-11 digest of the wrong closure, which is worse than no digest: it
looks like a working staleness key and silently tracks the wrong files.

**Nothing here may import FreeCAD, or anything that imports FreeCAD.** That is the whole
reason the file exists. `parameters.py` is out for that reason, which is why the seed tables
are named rather than referenced -- `build_part.py` resolves the name against `parameters`
once it has one.
"""

# kind -> (top geometry module, the name of its seed table in parameters.py)
#
# The boom bulkhead reads its own table rather than sharing the frame bulkhead's. They are
# different parts of different sweeps and their parameter lists only partly overlap -- the
# boom takes eleven names the frame bulkhead has never heard of and does without eight of
# its. Sharing the name would mean a frame bulkhead's parameter file seeded a boom bulkhead
# without complaint, leaving every boom row at its module literal: a part built at the
# reference configuration under the swept variant's filename. A separate name makes that a
# missing key instead.
KINDS = {
    'corner': ('corner_tree', 'CORNER'),
    'bulkhead': ('bulkhead_full', 'BULKHEAD'),
    'boom_bulkhead': ('boom_bulkhead', 'BOOM_BULKHEAD'),
}


# **Which type names each kind's builder actually implements.** A kind absent from this has
# no type axis, so every variant of it is buildable.
#
# It lives here for the reason the table above does: both sides of the FreeCAD boundary need
# it and neither can import the other. `drawing.py` needs it to refuse a family sheet it
# cannot draw; `tools/drawing_families.py` needs it to say which of the thirteen family sheets
# the port can actually produce, and that runs in the virtualenv.
#
# **What it prevents is a plausible wrong drawing.** `bulkhead_full.emit()` implements the
# plain end type and nothing else (IP-FC-9), and it takes no type flag -- so handing it an
# interconnect variant does not fail, it returns an end bulkhead. Measured 2026-08-27: at 1U
# with the 0 mm panel the interconnect and `end_bolt` variants have **identical parameter
# values**, differing only in the `is_interconnect` boolean, which is not a parameter and never
# reaches this backend. That boolean is not cosmetic -- in `fuselage_bulkhead_geometry.scad` it
# removes the bolt flange, its fillet, its web and the bolt hole. A drawing made without it
# shows four bolt bosses and four bolt holes the part does not have, dimensioned, under the
# interconnect's title and beside a table of the interconnect's own values.
#
# `fuselage_variants.bulkhead_render` already routes these types to OpenSCAD rather than to a
# builder that would ignore the distinction. This is that judgement applied to the drawing.
BUILT_TYPES = {'bulkhead': ('end_anchor', 'end_bolt')}


def unbuilt_types(kind, type_names):
    """Which of a family's type names this backend cannot build. Empty means it can."""
    built = BUILT_TYPES.get(kind)
    if built is None:
        return []
    return sorted(name for name in type_names if name not in built)


def geometry_roots(kind):
    """The modules the IP-FC-11 digest walks from, for `kind`.

    `build_part.py` is a root for every kind, not just a convenience: LINEAR_DEFLECTION
    lives in it, and the tessellation setting changes the exported mesh as surely as a
    sketch does. Everything below these is reached by following imports, so adding one
    extends the closure without touching this.
    """
    return ('build_part.py', KINDS[kind][0] + '.py')
