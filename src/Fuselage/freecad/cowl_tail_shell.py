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

import cowl_interior
import cowl_tree
from corner_common import is_entry_point

PARAMS = cowl_tree.PARAMS_TAIL_SHELL

#: IP-FC-137, measured 2026-09-12: the lowest `U` this construction is known to build at, not a
#: theoretical bound and not a tolerance to widen -- no fix for the underlying rib cut is known
#: (steps 1-2 named the operand and confirmed the residue is real, not a `Shape.Volume`
#: artefact; step 4 is this floor). Every `U` tried below it failed, and not gracefully: `U` =
#: 0.5, 0.7 and 0.75 raised `ValueError: Null shape` on the rib-cut retry in every one of three
#: independent builds each (residue 5540.9-6006.8, 15982.45, and 5931.8-18333.3 mm3
#: respectively -- 0.7 is *worse* than 0.5, not partway to safe); `U` = 0.6 additionally varied
#: between builds of identical inputs (residue 0, 681.8 and 4082.6 mm3, one of the three failing
#: one step later instead, at the final wall cut). Every `U` tried at or above this floor built
#: cleanly. Nose is unaffected at any of these -- it is the tail's 22-tool cut, not the shared
#: path -- so this guard is here and not in `cowl_tree`.
MIN_U = 0.8

_DEFAULT_U = float(dict(PARAMS)['U'])


def emit(doc, seed=None, overlay=None):
    u = float(seed['U']) if seed and 'U' in seed else _DEFAULT_U
    if u < MIN_U:
        raise cowl_interior.PreconditionFailed(
            'tail_shell at U=%.4g is below %.4g, the lowest U this construction is known to '
            'build at (IP-FC-137). U=0.5, 0.6, 0.7 and 0.75 all fail cavity()\'s rib cut in '
            'direct testing; U=0.8 and above have not. Refusing now rather than spending the '
            'build only to hand back a null shape at the end.' % (u, MIN_U))
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
