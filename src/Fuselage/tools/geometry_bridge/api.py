"""How a test gets a session. The only part of this package a test normally touches.

Two worker shapes, and the difference is a correctness rule rather than a performance knob:

``session()``
    A long-lived worker, reused across a whole test session. Right for ordinary assertions.

``fresh_session()``
    A worker that has built nothing yet. **Required for any measurement that feeds a reproducibility
    claim.** This project's criterion is that two builds of the same part are the same part, and it
    is separately recorded that a fresh build is bit-identical *except* near a degenerate
    configuration, where even rankings and failure modes differ between processes. A session worker
    has accumulated kernel and allocator state from every test that ran before it, which is exactly
    the condition under which results may differ. A test that compares two builds uses two fresh
    workers, not one worker twice.

The FreeCAD binary is found with `freecad_render.freecadcmd_path`, the same discovery the
`check_*.py` tier already uses, rather than a path written down here.
"""
import os
import sys

from .errors import BridgeError
from .session import Session
from .transport import LocalTransport, LoopbackTransport, WorkerTransport

_HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(_HERE, 'worker.py')

#: A worker is restarted once it holds more than this many handles, at a test boundary and never
#: inside one. A restart invalidates every outstanding handle, so it is only safe between tests.
HANDLE_CEILING = 20000


def freecadcmd_path():
    """The FreeCAD console binary, via the project's existing discovery."""
    tools = os.path.dirname(_HERE)
    if tools not in sys.path:
        sys.path.insert(0, tools)
    try:
        import freecad_render
    except ImportError as exc:                                           # pragma: no cover
        raise BridgeError('cannot locate freecad_render to find freecadcmd: %s' % exc)
    return freecad_render.freecadcmd_path()


def freecad_session(liveness_s=None):
    """A `Session` driving FreeCAD in its own interpreter."""
    return Session(WorkerTransport([freecadcmd_path(), WORKER], liveness_s=liveness_s),
                   label='FreeCAD')


def loopback_session(modules, **kwargs):
    """A `Session` over a stub object graph, for testing the bridge itself with no vendor."""
    return Session(LoopbackTransport(modules, **kwargs), label='loopback')


def local_session(modules):
    """A `Session` over plain in-process imports, for a vendor built for this interpreter.

    OpenVSP is this case today: its extension matches the project's 3.13, so it needs no subprocess.
    Keeping it behind the same interface means a test is written once and does not know which side of
    a boundary its library is on, and the day either vendor moves its build is a one-line change.
    """
    return Session(LocalTransport(modules), label='local')


def openvsp_session():
    """A `Session` over OpenVSP, using the project's existing on-disk discovery.

    OpenVSP needs no worker today -- its `_vsp.pyd` is built for the same 3.13 the project uses, the
    opposite pin to FreeCAD's. `oml_export.import_vsp` already finds it and puts its siblings on
    `sys.path`, so that is reused rather than reimplemented. Should OpenVSP ever move to a different
    CPython, this function changes to `freecad_session`'s shape and **no test changes**, which is the
    whole reason both vendors sit behind one interface.
    """
    tools = os.path.dirname(_HERE)
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import oml_export
    vsp, _root = oml_export.import_vsp()        # raises with instructions if absent
    return Session(LocalTransport({'vsp': vsp.__name__}), label='OpenVSP')


def maybe_restart(session, factory, handle_ceiling=HANDLE_CEILING):
    """Replace `session` with a fresh one if it is holding too much. Returns the session to use.

    Called between tests and never inside one: a restart invalidates every outstanding handle, and a
    proxy used across it raises `StaleHandle` rather than silently addressing a different object.
    """
    if not session.needs_restart(handle_ceiling):
        return session
    session.close()
    return factory()
