"""`Remote` -- a reference to an object that lives on the other side of the boundary.

A `Remote` makes a vendor object usable as if it were local: ``wall.Volume`` returns a float,
``wall.isValid()`` returns a bool, ``wall.BoundBox.ZLength`` returns a further proxy and then a
float, and ``a.cut(b).cut(c)`` passes handles so the whole chain happens vendor-side with only the
final number crossing.

Four decisions here are deliberate and each exists because the obvious alternative was measured to
be wrong.

**Only dunders are blocked from forwarding, not every underscore name.** An earlier version refused
anything starting with ``_``, which silently made the entire private half of the project's own API
unreachable -- ``_check_slope``, ``_Polyline``, ``_fit``, ``_thin_stations`` are exactly the
functions a unit test wants. The proxy's own attributes are in ``__slots__`` and are found by
descriptor before ``__getattr__`` runs, so they never needed that guard. Dunders do need it: copy,
pickle and pytest all speculatively probe for them, and a round trip per probe is both slow and
wrong.

**A bound method holds the owning proxy, not the owner's handle id.** Holding the bare id let the
owner be collected while the bound method was still on the expression stack: in
``a.cut(b).cut(c)`` the first result is never named, so after ``.cut`` produced a method object the
only reference to that shape was an integer, the proxy was collected, its release was queued, and
the very request carrying that release used the handle. A **live object was freed** -- worse than a
leak, because a leak wastes memory while this corrupts a result. The rule is *alive while
reachable*, not *alive while named*.

**``__bool__`` is defined explicitly and always true.** Python falls back to ``__len__`` when
``__bool__`` is absent, so ``if shape:`` became ``len(shape)`` and raised ``TypeError`` on any
object without a length. A proxy references a real object, so the useful reading of ``if shape:``
is "is not None".

**``__eq__`` forwards and ``__hash__`` is therefore undefined.** Python makes a type with ``__eq__``
and no ``__hash__`` unhashable, which is the right default: two proxies for the same vendor object
hold different handle ids, so hashing by id would be wrong, and hashing by vendor identity would
cost a round trip inside ``dict.__setitem__``.

See doc/architecture/geometry_bridge.md section 4.3.
"""

#: The proxy's own attributes. Assignments to these are local; everything else is forwarded.
_INTERNAL = frozenset(('_session', '_h', '_type', '_repr', '_bases'))

#: Arithmetic and comparison dunders forwarded to the vendor object, as an allowlist rather than a
#: catch-all. `__eq__` and `__ne__` are included so a comparison means what the vendor means.
_BINARY_OPS = (
    '__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__',
    '__add__', '__radd__', '__sub__', '__rsub__', '__mul__', '__rmul__',
    '__truediv__', '__rtruediv__', '__mod__', '__pow__',
)

_UNARY_OPS = ('__neg__', '__pos__', '__abs__')

#: The vendor's `NotImplemented` cannot cross as a value, so it arrives as a handle of this type.
#: Recognising it is what lets Python's own operator fallback still work.
_NOT_IMPLEMENTED_TYPE = 'NotImplementedType'


class Remote(object):
    """A handle to an object living on the other side of the transport."""

    __slots__ = ('_session', '_h', '_type', '_repr', '_bases')

    def __init__(self, session, h, type_name, text='', bases=()):
        object.__setattr__(self, '_session', session)
        object.__setattr__(self, '_h', h)
        object.__setattr__(self, '_type', type_name)
        object.__setattr__(self, '_repr', text)
        object.__setattr__(self, '_bases', tuple(bases))

    # -- identity and display

    def __repr__(self):
        return '<Remote %s #%s %s>' % (self._type, self._h, self._repr)

    @property
    def remote_type(self):
        """The vendor-side type name, as the worker reported it."""
        return self._type

    @property
    def remote_handle(self):
        """The handle id. Exposed for diagnostics and lifetime tests, not for ordinary use."""
        return self._h

    @property
    def remote_bases(self):
        """The vendor-side class chain, leaf first, `object` dropped.

        Needed because a leaf type name does not identify what an object is: a `Part::Box`
        document object reports `PrimitivePy`, and `DocumentObject` is four classes up. See
        `ops.base_names`.
        """
        return self._bases

    def remote_isinstance(self, *names):
        """Is any of `names` in this object's class chain? The client-side `isinstance`."""
        return any(n in self._bases for n in names)

    def __bool__(self):
        """Always true: a proxy references a real object. See the module docstring."""
        return True

    #: Unhashable on purpose. See the module docstring.
    __hash__ = None

    # -- lifetime

    def __del__(self):
        """Queue this handle for release. **Only ever appends; never does I/O.**

        ``__del__`` can run while the interpreter is tearing down, where touching a pipe either
        deadlocks or raises against half-finalized modules.
        """
        try:
            self._session._queue_release(self._h)
        except BaseException:                                            # noqa: BLE001
            pass

    # -- attributes

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        return self._session._get(self, name)

    def __setattr__(self, name, value):
        """Forward assignment to the vendor object.

        Required, not optional: this project's FreeCAD code is parametric-document driven, and
        driving a document means assigning to properties. Without this every assignment became a
        client-side ``AttributeError`` that looked like a missing attribute rather than a missing
        feature.
        """
        if name in _INTERNAL:
            object.__setattr__(self, name, value)
            return
        self._session._set(self, name, value)

    def __delattr__(self, name):
        raise AttributeError(
            'deleting a vendor attribute through the bridge is not supported (%r)' % name)

    # -- containers

    def __len__(self):
        return self._session._len(self)

    def __getitem__(self, key):
        """The key is passed through unchanged, so a mapping subscripts as a mapping."""
        return self._session._getitem(self, key)

    def __setitem__(self, key, value):
        return self._session._setitem(self, key, value)

    def __iter__(self):
        """One round trip for the whole sequence, not one per element."""
        return iter(self._session._iterate(self))

    def __contains__(self, item):
        return self._session._callattr(self, '__contains__', (item,), {})

    # -- bulk

    def project(self, *paths):
        """Read the same attribute paths from every element, in one round trip.

        ``[(v.X, v.Y, v.Z) for v in shape.Vertexes]`` costs a round trip per coordinate;
        ``shape.Vertexes.project('X', 'Y', 'Z')`` costs one. A loop that reads attributes one at a
        time is a performance defect, not a style preference.
        """
        return self._session._project(self, paths)

    def items(self):
        """Every element as a value or proxy, in one round trip. The explicit form of ``__iter__``."""
        return self._session._iterate(self)


def _make_binary(op):
    def method(self, other):
        got = self._session._callattr(self, op, (other,), {}, allow_not_implemented=True)
        if got is NotImplemented:
            return NotImplemented
        return got
    method.__name__ = op
    method.__doc__ = 'Forwarded to the vendor object\'s %s.' % op
    return method


def _make_unary(op):
    def method(self):
        return self._session._callattr(self, op, (), {})
    method.__name__ = op
    method.__doc__ = 'Forwarded to the vendor object\'s %s.' % op
    return method


# Generated rather than hand-written: fifteen methods with identical bodies invite a copy-paste
# error in one of them, and the allowlists above are the part worth reading.
for _op in _BINARY_OPS:
    setattr(Remote, _op, _make_binary(_op))
for _op in _UNARY_OPS:
    setattr(Remote, _op, _make_unary(_op))


class RemoteMethod(object):
    """A bound vendor-side method. Allocates no handle, and keeps its owner alive.

    See the module docstring for why holding `owner` rather than ``owner._h`` is load-bearing.
    """

    __slots__ = ('_owner', '_name')

    def __init__(self, owner, name):
        self._owner = owner
        self._name = name

    def __repr__(self):
        return '<RemoteMethod %s of %r>' % (self._name, self._owner)

    def __call__(self, *args, **kwargs):
        return self._owner._session._callattr(self._owner, self._name, args, kwargs)


def is_not_implemented(obj):
    """Did the vendor return ``NotImplemented``? It cannot cross as a value, so it arrives typed."""
    return isinstance(obj, Remote) and obj.remote_type == _NOT_IMPLEMENTED_TYPE
