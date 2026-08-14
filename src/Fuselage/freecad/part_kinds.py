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


def geometry_roots(kind):
    """The modules the IP-FC-11 digest walks from, for `kind`.

    `build_part.py` is a root for every kind, not just a convenience: LINEAR_DEFLECTION
    lives in it, and the tessellation setting changes the exported mesh as surely as a
    sketch does. Everything below these is reached by following imports, so adding one
    extends the closure without touching this.
    """
    return ('build_part.py', KINDS[kind][0] + '.py')
