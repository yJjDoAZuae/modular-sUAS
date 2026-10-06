"""Importable names for the vendor and project exceptions the bridge raises.

So a test can write::

    from geometry_bridge.remote_errors import PreconditionFailed

    def test_a_shallow_section_is_refused(fc):
        with pytest.raises(PreconditionFailed):
            ...

and get the *same* class object the bridge will raise, rather than calling
:func:`geometry_bridge.errors.remote_class` by hand with a base chain it should not have to know.

An unregistered remote exception is still synthesized on first use; this module exists so the
import works before the first failure has ever happened. Adding a name here is a one-line change
in :data:`geometry_bridge.errors.PRE_REGISTERED`.
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

#: `cowl_interior`'s precondition guard: a section too shallow to erode, a notch in the layer
#: plane, an erosion that annihilates the section.
PreconditionFailed = remote_class('PreconditionFailed', ('PreconditionFailed', 'Exception'))

#: `cowl_interior`'s convergence guard, raised when a mirror step produces disconnected shells.
Unconverged = remote_class('Unconverged', ('Unconverged', 'Exception'))

#: OCCT's own refusal, surfaced through FreeCAD -- an offset with no wires, a boolean that will not
#: close. Observed in this project from `makeOffset2D` eroded past a section's half-width.
CADKernelError = remote_class('CADKernelError', ('CADKernelError', 'Exception'))

#: The broader OCCT error class.
OCCError = remote_class('OCCError', ('OCCError', 'Exception'))

__all__ = [
    'BridgeError', 'BridgeTimeout', 'CADKernelError', 'OCCError', 'PreconditionFailed',
    'ProtocolError', 'RemoteGeometryError', 'StaleHandle', 'Unconverged', 'WorkerDied',
    'remote_class',
]
