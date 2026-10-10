"""Exceptions, and the rule that keeps a geometry failure distinguishable from a plumbing one.

Two families, deliberately unrelated:

``BridgeError``
    The bridge itself failed -- the worker died, a call went silent, the protocol broke. **Never a
    geometry finding.** It does not inherit from ``RemoteGeometryError``, so a test that catches
    geometry failures cannot swallow a dead worker and report a defect that is not there.

``RemoteGeometryError``
    The worker ran and the vendor's own code raised. A real finding.

The client cannot import the vendor's exception classes -- that import is exactly what the process
boundary exists to avoid -- so it rebuilds them. The worker sends the class name, its full base
chain, the message and the traceback; :func:`remote_class` synthesizes a matching class once and
caches it, so the same remote type is the same client class on every raise and
``pytest.raises(PreconditionFailed)`` behaves as it would in-process.

The base chain is sent rather than just the name because without it a hierarchy catch would
silently miss: a remote ``PreconditionFailed`` has to be catchable as an ``Exception`` too.

See doc/architecture/geometry_bridge.md section 4.9.
"""


class BridgeError(AssertionError):
    """The bridge failed, not the geometry.

    Subclasses ``AssertionError`` so an unexpected one reads as a test failure rather than as an
    error escaping the harness, and deliberately does **not** subclass
    :class:`RemoteGeometryError`.
    """


class WorkerDied(BridgeError):
    """The worker process ended mid-call."""


class BridgeTimeout(BridgeError):
    """No sign of life from the worker within the liveness interval.

    The deadline is on silence, not on duration: a legitimate build takes minutes and emits
    heartbeats throughout, while a wedged kernel call emits nothing. The worker is terminated
    before this is raised, so a timeout never leaves an orphan process holding a core.
    """


class ProtocolError(BridgeError):
    """A malformed or unexpected message."""


class RemoteGeometryError(Exception):
    """Base of every synthesized remote exception: the worker ran and its code raised."""

    #: The vendor-side class name this stands for. Overridden on each synthesized subclass.
    remote_name = 'RemoteGeometryError'

    def __init__(self, message, remote_traceback='', remote_bases=(), vendor_output=''):
        super().__init__(message)
        self.message = message
        self.remote_traceback = remote_traceback
        self.remote_bases = tuple(remote_bases)
        #: Whatever the vendor printed on its own before failing. A cowl build prints progress for
        #: a quarter of an hour, and it is the first thing wanted when a geometry test fails.
        self.vendor_output = vendor_output

    def __str__(self):
        """pytest prints this, so the worker's traceback belongs in it.

        Without this the failure report shows only client frames, which say nothing about which
        geometry call failed -- the usual complaint about a process boundary. With it the report
        names the remote file, function and line.
        """
        parts = [self.message]
        if self.remote_traceback:
            parts.append('--- traceback from the %s worker ---\n%s'
                         % (VENDOR_LABEL, self.remote_traceback.rstrip()))
        if self.vendor_output:
            parts.append('--- last output from the worker ---\n%s' % self.vendor_output.rstrip())
        return '\n\n'.join(parts)


#: Named in the error text so a reader knows which side of the boundary failed.
VENDOR_LABEL = 'geometry'


class StaleHandle(RemoteGeometryError):
    """A handle used after its proxy was collected.

    A lifetime bug, and named as one. The alternative -- a bare ``KeyError`` surfacing from inside
    unrelated work -- reads as a geometry fault and sends someone hunting a defect that does not
    exist.
    """

    remote_name = 'StaleHandle'


#: Remote names that must map onto the real builtins, so ``except ValueError`` and
#: ``except Exception`` keep working across the boundary. A synthesized class for one of these
#: co-inherits from the genuine builtin as well as from :class:`RemoteGeometryError`.
_BUILTINS = {
    'BaseException': BaseException, 'Exception': Exception, 'ValueError': ValueError,
    'TypeError': TypeError, 'KeyError': KeyError, 'IndexError': IndexError,
    'LookupError': LookupError, 'AttributeError': AttributeError, 'RuntimeError': RuntimeError,
    'OSError': OSError, 'IOError': OSError, 'ArithmeticError': ArithmeticError,
    'ZeroDivisionError': ZeroDivisionError, 'OverflowError': OverflowError,
    'FloatingPointError': FloatingPointError, 'NotImplementedError': NotImplementedError,
    'SyntaxError': SyntaxError, 'IndentationError': IndentationError, 'NameError': NameError,
    'MemoryError': MemoryError, 'StopIteration': StopIteration,
}

#: Vendor and project exception names worth exposing as importable attributes, so a test can write
#: ``from geometry_bridge.remote_errors import PreconditionFailed`` and get the same class the
#: bridge raises. Registering a name here is not required -- an unregistered one is synthesized on
#: first use -- it only makes the import available before the first failure.
PRE_REGISTERED = (
    # cowl_interior's own guards
    ('PreconditionFailed', ('PreconditionFailed', 'Exception')),
    ('Unconverged', ('Unconverged', 'Exception')),
    # OCCT, surfaced through FreeCAD
    ('CADKernelError', ('CADKernelError', 'Exception')),
    ('OCCError', ('OCCError', 'Exception')),
    # solid_measure's guards. Both are preconditions of a *measurement* rather than geometry
    # faults, and a test asserting one must be able to import it before it has ever fired.
    ('NotConverged', ('NotConverged', 'Exception')),
    ('TopologyMismatch', ('TopologyMismatch', 'Exception')),
)

_CACHE = {'StaleHandle': StaleHandle}


def remote_class(name, bases=()):
    """The synthesized class for a remote exception name, created once and reused.

    `bases` is the worker's MRO as names, nearest first. Identity is stable across calls, which
    matters because ``pytest.raises`` is given the class: a fresh class per raise would make the
    same remote failure uncatchable the second time.
    """
    if name in _CACHE:
        return _CACHE[name]

    if name in _BUILTINS and _BUILTINS[name] is not BaseException:
        # Co-inherit, so both `except AttributeError` and `except RemoteGeometryError` catch it.
        # BaseException is excluded because co-inheriting from it gains nothing and risks a
        # layout conflict.
        cls = type(name, (RemoteGeometryError, _BUILTINS[name]), {'remote_name': name})
        _CACHE[name] = cls
        return cls

    parent = RemoteGeometryError
    bases = list(bases)
    for i, base_name in enumerate(bases):
        if base_name in (name, 'object'):
            continue
        parent = remote_class(base_name, bases[i:])
        break
    cls = type(name, (parent,), {'remote_name': name})
    _CACHE[name] = cls
    return cls


def raise_remote(name, message, bases=(), traceback_text='', vendor_output=''):
    """Raise the synthesized equivalent of the worker's exception.

    ``__tracebackhide__`` keeps pytest's report pointing at the test's own line instead of at the
    bridge's frames; the worker's traceback travels on the exception and is printed by its
    ``__str__``.
    """
    __tracebackhide__ = True
    cls = remote_class(name or 'RemoteGeometryError', bases)
    raise cls(message, traceback_text, bases, vendor_output)


def known_names():
    """Every synthesized class name so far. For tests and diagnostics."""
    return sorted(_CACHE)


for _name, _bases in PRE_REGISTERED:
    remote_class(_name, _bases)
