"""IP-TEST-11: a committed, re-runnable regression for IP-FC-139/140/141's own claim that the
rib-cut construction fix "build[s] cleanly for both cowls" across all eight swept `U` values in
`nose_size_variants.csv` (0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4). Before this file existed, that claim
had only the narrative record of a one-time 2026-09-21 investigation -- nothing re-ran it.

**Expensive -- not part of routine verification.** All 16 builds (2 kinds x 8 `U` values) take
close to an hour (58.7 min measured 2026-09-22, `U` = 4 `tail_shell` alone costs ~16 min). This
is a "full sweep" by this project's own standing guidance (ask before running one); run it
deliberately, not as part of a normal check pass:

    freecadcmd check_cowl_u_sweep.py

Builds directly against `cowl_tree`'s own parameter rows (`PARAMS_TAIL_SHELL` /
`PARAMS_NOSE_COWL_SHELL`), with only the `U` row's literal replaced via
`soak_cowl_shell.with_u()` -- the same construction `check_cowl_interior.py` and
`soak_cowl_shell.py` already use, not the real sweep's seeded overlay path (see
`soak_cowl_shell.py`'s own docstring for why that substitution is equivalent here). Checks
exactly what each kind module's own `main()` checks: `shape.isValid()` and
`len(shape.Solids) == 1`. Prints one flushed line per build so partial results survive if a
later build hangs or crashes, and continues past any single build's exception rather than
aborting the whole sweep.

**Result, 2026-09-22 (first real run of this file): 16/16 OK.** Every combination valid,
single-solid, and every rib cut left `0.000000 mm3` inside -- the exact IP-FC-137 defect
signature, at zero across the full range for both cowl kinds. IP-FC-139/140/141's claim is
confirmed by a real, committed regression, not narrative record alone.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import cowl_tree
import soak_cowl_shell as soak
from corner_common import is_entry_point

U_VALUES = [0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4]
KINDS = {
    'tail_shell': cowl_tree.tail_shell,
    'nose_cowl_shell': cowl_tree.nose_cowl_shell,
}
BASE_PARAMS = {
    'tail_shell': cowl_tree.PARAMS_TAIL_SHELL,
    'nose_cowl_shell': cowl_tree.PARAMS_NOSE_COWL_SHELL,
}


def main():
    results = []
    t_all = time.time()

    for kind, builder in KINDS.items():
        for u in U_VALUES:
            t0 = time.time()
            try:
                params = soak.with_u(BASE_PARAMS[kind], u)
                doc = App.newDocument('sweep')
                tip = cowl_tree.emit(doc, None, params, builder)
                shape = tip.Shape
                ok = bool(shape.isValid()) and len(shape.Solids) == 1
                row = (kind, u, ok, shape.isValid(), len(shape.Solids), shape.Volume,
                       time.time() - t0, None)
                App.closeDocument(doc.Name)
            except Exception as exc:
                row = (kind, u, False, None, None, None, time.time() - t0, repr(exc))
            results.append(row)
            kind_s, u_s, ok_s, valid_s, solids_s, vol_s, dt_s, err_s = row
            print("SWEEP kind=%-16s U=%-5s ok=%-5s valid=%s solids=%s volume=%s t=%.1fs%s"
                  % (kind_s, u_s, ok_s, valid_s, solids_s,
                     ("%.4f" % vol_s) if vol_s is not None else "n/a", dt_s,
                     ("  ERROR=%s" % err_s) if err_s else ""))
            sys.stdout.flush()

    failures = [r for r in results if not r[2]]
    print("=== SWEEP DONE: %d/%d builds OK, %.1f min total ==="
          % (len(results) - len(failures), len(results), (time.time() - t_all) / 60.0))
    if failures:
        print("=== FAILURES ===")
        for r in failures:
            print(r)
    sys.stdout.flush()
    return 0 if not failures else 1


if is_entry_point(__name__):
    raise SystemExit(main())
