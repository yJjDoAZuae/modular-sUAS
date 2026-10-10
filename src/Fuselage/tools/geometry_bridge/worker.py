"""The FreeCAD-side worker. **The only file in this package that imports a vendor module.**

Run by `WorkerTransport` under FreeCAD's own interpreter::

    freecadcmd .../geometry_bridge/worker.py

It builds the module allowlist and hands it to a vendor-free dispatcher; the protocol, the handle
lifetime and the error paths all live in modules that need no FreeCAD, which is what lets them be
tested in the project's ordinary pytest tier.

**There is no code-evaluation operation.** An earlier prototype had one, and it is deliberately
absent: it is an arbitrary-code-execution surface, and it is what forced geometry into strings where
no editor or type checker could see it.

**Document hygiene is the worker's job, not each test's.** `reset` closes every open document as
well as dropping every handle, because FreeCAD keeps an open-document list that otherwise outlives a
test and contaminates the next one.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
_FREECAD_DIR = os.path.normpath(os.path.join(_TOOLS, '..', 'freecad'))

for _p in (_TOOLS, _FREECAD_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from geometry_bridge import wire                                         # noqa: E402
from geometry_bridge.ops import Dispatcher                               # noqa: E402

import FreeCAD                                                          # noqa: E402
import Part                                                             # noqa: E402

#: Modules the client may reach by name. An allowlist, not an open door: the client names a module
#: and gets a proxy, so anything not here is unreachable.
#:
#: The project's own geometry modules are included because the whole point is to give their private
#: helpers named tests -- `_check_slope`, `_Polyline`, `_thin_stations`, `section_regions` are
#: exactly what has no test today.
MODULE_NAMES = (
    ('FreeCAD', 'FreeCAD'),
    ('App', 'FreeCAD'),
    ('Part', 'Part'),
    ('cowl_interior', 'cowl_interior'),
    ('check_cowl_interior', 'check_cowl_interior'),
    ('cowl_tree', 'cowl_tree'),
    ('corner_common', 'corner_common'),
    ('solid_measure', 'solid_measure'),
    ('mesh_stats', 'mesh_stats'),
)


def build_modules():
    """Import the allowlisted modules, skipping any that is not present in this checkout.

    Skipping rather than failing: a module that has been renamed should make the tests that use it
    fail by name, not make the worker refuse to start and take every unrelated test with it.
    """
    out = {}
    missing = []
    for exposed, module_name in MODULE_NAMES:
        try:
            out[exposed] = __import__(module_name)
        except ImportError:
            missing.append(module_name)
    return out, missing


def is_dynamic(obj):
    """Does `obj` carry run-time properties, making a per-type attribute cache unsound?

    FreeCAD document objects do -- properties are added at run time, and two of them report the same
    type name while carrying different attributes. Checked against FreeCAD's own base classes here,
    with the duck-typed fallback for anything that behaves the same way.
    """
    for attr in ('DocumentObject', 'Document', 'DocumentObjectGroup'):
        base = getattr(FreeCAD, attr, None)
        if base is not None and isinstance(base, type) and isinstance(obj, base):
            return True
    return hasattr(obj, 'PropertiesList') or hasattr(obj, 'addProperty')


class FreeCADDispatcher(Dispatcher):
    """Adds FreeCAD's own state hygiene to the vendor-free dispatcher."""

    def _op_reset(self, req):
        dropped = self.registry.clear()
        closed = []
        for name in list(FreeCAD.listDocuments()):
            try:
                FreeCAD.closeDocument(name)
                closed.append(name)
            except Exception:                                            # noqa: BLE001
                pass
        return {'kind': 'value', 'value': {'handles_dropped': dropped,
                                           'documents_closed': closed}}

    def _op_vendor_info(self, req):
        return {'kind': 'value', 'value': {
            'freecad': '.'.join(FreeCAD.Version()[:3]),
            'python': '%d.%d.%d' % sys.version_info[:3],
            'modules': sorted(self.modules),
        }}


def main():
    modules, missing = build_modules()
    dispatcher = FreeCADDispatcher(modules, is_dynamic=is_dynamic,
                                   max_items=int(os.environ.get('GB_MAX_ITEMS', '2000')))
    if missing:
        sys.stderr.write('geometry_bridge worker: could not import %s\n' % ', '.join(missing))
        sys.stderr.flush()
    return wire.serve(dispatcher, label='FreeCAD')


# `freecadcmd` never triggers a bare `if __name__ == '__main__':` guard, and this file is also
# imported by its own tests, so the entry point is gated the way the project's check scripts are.
try:
    from corner_common import is_entry_point
except ImportError:                                                      # pragma: no cover
    def is_entry_point(name):
        return name == '__main__'

if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
