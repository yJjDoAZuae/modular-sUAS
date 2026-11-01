"""IP-FC-158: confirm the kernel fuzz moved without leaving a dangling reference.

`RIB_CUT_FUZZ` and `CUT_FUZZ_LADDER` were module constants of `cowl_interior` and are now
`si.RIB_CUT_FUZZ_MM` and `si.CUT_FUZZ_LADDER_MM`. A missed use site is a `NameError` raised deep
inside a build that takes minutes to reach, so this fails in a second instead.

Run: freecadcmd check_fuzz_move.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cowl_interior
import si
from corner_common import is_entry_point


def main():
    failures = []

    def check(label, ok):
        print('  %-62s %s' % (label, 'ok' if ok else 'FAIL'))
        sys.stdout.flush()
        if not ok:
            failures.append(label)

    print('the kernel fuzz moved to the unit boundary')
    print('')

    check('cowl_interior imports with si on its path', cowl_interior is not None)
    check('si.RIB_CUT_FUZZ_MM is 1.0e-5 mm', si.RIB_CUT_FUZZ_MM == 1.0e-5)
    check('si.CUT_FUZZ_LADDER_MM is the four-rung ladder',
          tuple(si.CUT_FUZZ_LADDER_MM) == (1.0e-5, 1.0e-4, 1.0e-3, 1.0e-2))
    check('cowl_interior no longer defines RIB_CUT_FUZZ',
          not hasattr(cowl_interior, 'RIB_CUT_FUZZ'))
    check('cowl_interior no longer defines CUT_FUZZ_LADDER',
          not hasattr(cowl_interior, 'CUT_FUZZ_LADDER'))

    # The real risk is a use site the move missed. Compiling the module resolves nothing, so
    # the names are checked against the code objects instead: a global that is read somewhere
    # and defined nowhere is what a NameError at build time looks like, found statically.
    missing = _undefined_globals(cowl_interior)
    check('no name in cowl_interior is read but never defined (%s)'
          % (', '.join(sorted(missing)) if missing else 'none'), not missing)

    print('')
    if failures:
        print('%d check(s) FAILED:' % len(failures))
        for label in failures:
            print('  %s' % label)
    else:
        print('all checks passed')
    sys.stdout.flush()
    return len(failures)


def _undefined_globals(module):
    """Global names a module's own functions load that nothing defines or imports.

    Walks every code object reachable from the module, collecting `LOAD_GLOBAL` names, and
    subtracts what the module actually has plus the builtins. It will not catch a name reached
    only through `getattr`, which is the usual limit of a static check like this.
    """
    import builtins
    import types

    seen = set()
    todo = []
    for value in vars(module).values():
        if isinstance(value, types.FunctionType):
            todo.append(value.__code__)
        elif isinstance(value, type):
            for attr in vars(value).values():
                if isinstance(attr, types.FunctionType):
                    todo.append(attr.__code__)

    names = set()
    while todo:
        code = todo.pop()
        if id(code) in seen:
            continue
        seen.add(id(code))
        for instruction in _global_loads(code):
            names.add(instruction)
        for const in code.co_consts:
            if isinstance(const, types.CodeType):
                todo.append(const)

    known = set(vars(module)) | set(dir(builtins))
    return {name for name in names if name not in known}


def _global_loads(code):
    import dis
    for instruction in dis.get_instructions(code):
        if instruction.opname in ('LOAD_GLOBAL', 'LOAD_NAME') and instruction.argval:
            yield instruction.argval


if is_entry_point(__name__):
    sys.exit(main())
