"""IP-FC-12: the nose tip, as one kind `build_part.py` can build.

`build_part.build()` imports one module per part kind and calls its `emit()`, so each cowl
part needs its own module even though all four share `cowl.py`'s geometry. The alternative --
one module branching on the kind -- would mean `part_kinds.geometry_roots` could not tell the
four apart, and the IP-FC-11 staleness digest would rebuild every cowl whenever any one of
them changed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cowl
from corner_common import is_entry_point

PARAMS = cowl.PARAMS_NOSE_TIP


def emit(doc, seed=None, overlay=None):
    return cowl.emit_part(doc, seed, PARAMS, cowl.nose_tip, 'NoseTip')


if is_entry_point(__name__):
    raise SystemExit(cowl.main())
