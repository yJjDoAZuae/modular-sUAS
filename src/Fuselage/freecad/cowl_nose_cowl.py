"""IP-FC-12: the nose cowl, as one kind `build_part.py` can build.

`build_part.build()` imports one module per part kind and calls its `emit()`, so each cowl
part needs its own module even though all four share `cowl.py`'s geometry. The alternative --
one module branching on the kind -- would mean `part_kinds.geometry_roots` could not tell the
four apart, and the IP-FC-11 staleness digest would rebuild every cowl whenever any one of
them changed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cowl_tree
from corner_common import is_entry_point

PARAMS = cowl_tree.PARAMS_NOSE_COWL


def emit(doc, seed=None, overlay=None):
    return cowl_tree.emit(doc, seed, PARAMS, cowl_tree.nose_cowl)


def main():
    """Build at the module's own rows and report, the reference check."""
    import FreeCAD as App
    doc = App.newDocument('nose_cowl')
    tip = emit(doc)
    shape = tip.Shape
    bound = sum(len(list(getattr(o, "ExpressionEngine", []) or []))
                for o in doc.Objects)
    print("PART:: %s  solids=%d valid=%s  objects=%d bindings=%d"
          % ('nose_cowl', len(shape.Solids), shape.isValid(), len(doc.Objects), bound))
    sys.stdout.flush()
    return 0 if shape.isValid() and len(shape.Solids) == 1 else 1


if is_entry_point(__name__):
    raise SystemExit(main())
