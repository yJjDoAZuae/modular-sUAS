"""IP-FC-17: the tail cowl's solid representation, as one kind `build_part.py` can build.

**Not a better tail cowl -- a different one.** `tail` is the print representation and stays
what UC-1 exports, because cowls print in spiral vase mode and a modelled inner surface makes
that mode unavailable (OQ-DES-CW6, cowl.md section 6.4). This kind is the shelled solid that
UC-2, UC-3, UC-4, UC-7 and UC-8 need and that the blank cannot serve. Two kinds rather than a
flag on one, so that nothing downstream can take the wrong one for the right one.

`build_part.build()` imports one module per part kind and calls its `emit()`, so this needs its
own module even though the geometry is `cowl_tree`'s -- the same reason `cowl_tail` has one,
and it also keeps the IP-FC-11 staleness digest able to tell the two apart.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cowl_tree
from corner_common import is_entry_point

PARAMS = cowl_tree.PARAMS_TAIL_SHELL


def emit(doc, seed=None, overlay=None):
    return cowl_tree.emit(doc, seed, PARAMS, cowl_tree.tail_shell)


def main():
    """Build at the module's own rows and report, the reference check."""
    import FreeCAD as App
    doc = App.newDocument('tail_shell')
    tip = emit(doc)
    shape = tip.Shape
    bound = sum(len(list(getattr(o, "ExpressionEngine", []) or []))
                for o in doc.Objects)
    print("PART:: %s  solids=%d valid=%s  objects=%d bindings=%d  volume=%.4f"
          % ('tail_shell', len(shape.Solids), shape.isValid(), len(doc.Objects), bound,
             shape.Volume))
    sys.stdout.flush()
    return 0 if shape.isValid() and len(shape.Solids) == 1 else 1


if is_entry_point(__name__):
    raise SystemExit(main())
