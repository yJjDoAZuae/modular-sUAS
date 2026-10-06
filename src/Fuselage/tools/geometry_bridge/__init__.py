"""Drive FreeCAD and OpenVSP from the project's own Python interpreter.

FreeCAD 1.1.3 embeds CPython 3.11 and OpenVSP's extension is built for 3.13; both are vendor
build choices and the two disagree, so no single interpreter can import both. This package puts a
process boundary where the version lock is, so the project's Python version stays the project's
own choice. The design is doc/architecture/geometry_bridge.md and the plan is
doc/implementation/geometry_bridge.md.

**Nothing here imports a vendor module at module scope.** That is the whole point: this package is
importable from any interpreter, and only a worker subprocess ever imports FreeCAD.

One principle runs through all of it: **a reference crosses the boundary, an object never does.**
`a.cut(b)` sends two handles and receives a third; the solids stay in the worker for the whole
chain and only the final measurement is serialized.
"""
from .errors import (                                                    # noqa: F401
    BridgeError,
    BridgeTimeout,
    ProtocolError,
    RemoteGeometryError,
    StaleHandle,
    WorkerDied,
    remote_class,
)

__all__ = [
    'BridgeError',
    'BridgeTimeout',
    'ProtocolError',
    'RemoteGeometryError',
    'StaleHandle',
    'WorkerDied',
    'remote_class',
]
