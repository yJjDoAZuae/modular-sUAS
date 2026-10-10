"""Operation dispatch, with no vendor import anywhere in it.

This is the worker's brain, separated from the worker's body on purpose. `worker.py` imports
FreeCAD and hands the modules to a :class:`Dispatcher`; `LoopbackTransport` hands it a stub object
graph instead. The protocol, the handle lifetime, the encoding and the error paths are therefore
exercised in the project's ordinary pytest tier, with no FreeCAD present and in milliseconds.

Without that separation the library that exists to enable a fast test tier would itself be testable
only in the slow one, which is the circularity the design calls out.

Two decisions here are not obvious and both come from measurement:

**A callable allocates no handle.** ``getattr`` on a callable returns a marker, not a handle, and
``callattr`` does the lookup and the call together. A handle per bound method would be one per call
site, which was the largest source of growth in the prototype.

**The worker decides what the client may cache.** Two ``App::FeaturePython`` objects both report
type ``FeaturePython`` and can carry different run-time properties, so a client-side cache keyed on
the type name is unsound for them. Each ``getattr`` reply carries ``cacheable``, computed here from
the object, and the client never infers it.

See doc/architecture/geometry_bridge.md sections 4.3, 4.5, 4.6 and 4.8.
"""
from . import codec
from .errors import ProtocolError
from .registry import Registry

#: Reply kinds. A `callable` reply deliberately carries no handle.
VALUE = 'value'
HANDLE = 'handle'
LIST = 'list'
CALLABLE = 'callable'


def default_is_dynamic(obj):
    """Does `obj` carry run-time properties, making a per-type attribute cache unsound?

    FreeCAD document objects do: properties are added at run time, so two objects reporting the
    same type name can disagree about which attributes exist. Detected by duck-typing rather than
    by importing FreeCAD, because this module must stay vendor-free.
    """
    return hasattr(obj, 'PropertiesList') or hasattr(obj, 'addProperty')


#: How many base-class names a handle reply carries. FreeCAD's deepest relevant chain is
#: `PrimitivePy, Feature, GeoFeature, DocumentObject, ExtensionContainer, PropertyContainer,
#: Persistence, BaseClass`, so eight is the real depth and twelve leaves headroom without letting
#: a pathological hierarchy bloat every reply.
MAX_BASES = 12


def base_names(obj):
    """The object's class chain, leaf first, as plain names -- **not** just its type name.

    **A leaf type name is not enough to identify what an object is, and assuming it was would have
    broken the most-used facade.** A `Part::Box` document object reports its type as `PrimitivePy`;
    `DocumentObject` is four classes up its MRO. Since `DocumentObject` carries 361 of the
    project's attribute uses -- more than any other type -- a client keying on the leaf name alone
    would have faceted everything *except* the case that matters most, and done so silently,
    falling back to the dynamic proxy with no error to notice.

    `object` is dropped because every chain ends there and it identifies nothing.
    """
    try:
        mro = type(obj).__mro__
    except AttributeError:                                               # noqa: PERF203
        return []
    out = [c.__name__ for c in mro if c is not object]
    return out[:MAX_BASES]


class Dispatcher(object):
    """Executes protocol operations against a module table and a handle registry."""

    def __init__(self, modules, is_dynamic=None, max_items=None):
        #: Allowlist: only these module names can be reached, by name, from the client.
        self.modules = dict(modules)
        self.registry = Registry()
        self.is_dynamic = is_dynamic or default_is_dynamic
        #: Cap on how many elements one `iterate` or `project` reply may carry before it pages.
        self.max_items = max_items
        self.calls = 0

    # -- encoding helpers

    def _encode(self, obj):
        if codec.is_value(obj):
            return {'kind': VALUE, 'value': codec.encode_value(obj)}
        hid = self.registry.hold(obj)
        try:
            text = repr(obj)[:120]
        except Exception:                                                # noqa: BLE001
            text = '<unreprable>'
        return {'kind': HANDLE, 'h': hid, 'type': type(obj).__name__, 'repr': text,
                'bases': base_names(obj)}

    def _decode(self, obj):
        return codec.decode_argument(obj, self.registry.resolve)

    def _args(self, req):
        args = [self._decode(a) for a in req.get('args', [])]
        kwargs = dict((k, self._decode(v)) for k, v in req.get('kwargs', {}).items())
        return args, kwargs

    # -- dispatch

    def handle(self, req):
        """Execute one request and return its reply payload.

        Releases carried on the request are processed first, so reclaiming never needs a round trip
        of its own.
        """
        if req.get('rel'):
            self.registry.release(req['rel'])
        op = req.get('op')
        fn = getattr(self, '_op_' + op, None) if isinstance(op, str) else None
        if fn is None:
            raise ProtocolError('unknown op %r' % (op,))
        return fn(req)

    def _op_module(self, req):
        name = req.get('name')
        if name not in self.modules:
            raise ProtocolError(
                'module %r is not exposed by this worker; allowed: %s'
                % (name, ', '.join(sorted(self.modules))))
        return self._encode(self.modules[name])

    def _op_getattr(self, req):
        obj = self.registry.resolve(req['h'])
        got = getattr(obj, req['name'])
        if callable(got):
            return {'kind': CALLABLE, 'type': type(got).__name__,
                    'cacheable': not self.is_dynamic(obj)}
        out = self._encode(got)
        out['cacheable'] = not self.is_dynamic(obj)
        return out

    def _op_setattr(self, req):
        obj = self.registry.resolve(req['h'])
        setattr(obj, req['name'], self._decode(req.get('value')))
        return {'kind': VALUE, 'value': True}

    def _op_callattr(self, req):
        obj = self.registry.resolve(req['h'])
        fn = getattr(obj, req['name'])
        args, kwargs = self._args(req)
        self.calls += 1
        return self._encode(fn(*args, **kwargs))

    def _op_call(self, req):
        fn = self.registry.resolve(req['h'])
        args, kwargs = self._args(req)
        self.calls += 1
        return self._encode(fn(*args, **kwargs))

    def _op_getitem(self, req):
        # The key is passed through unchanged. Sequence and mapping are not distinguished here --
        # a prototype assumed an integer index and raised KeyError on a dict-returning vendor call.
        return self._encode(self.registry.resolve(req['h'])[self._decode(req['key'])])

    def _op_setitem(self, req):
        self.registry.resolve(req['h'])[self._decode(req['key'])] = self._decode(req.get('value'))
        return {'kind': VALUE, 'value': True}

    def _op_len(self, req):
        return self._encode(len(self.registry.resolve(req['h'])))

    def _op_iterate(self, req):
        """`list(iter(obj))`, encoded in one reply.

        Bound to the client's ``__iter__`` so iteration is one round trip instead of one per
        element; it also gets mapping iteration right for free, by delegating to the object's own
        iterator.
        """
        obj = self.registry.resolve(req['h'])
        start = int(req.get('start', 0) or 0)
        items = list(iter(obj))
        total = len(items)
        window = items[start:] if self.max_items is None else items[start:start + self.max_items]
        nxt = start + len(window)
        return {'kind': LIST,
                'items': [self._encode(x) for x in window],
                'total': total,
                'next': nxt if nxt < total else None}

    def _op_project(self, req):
        """Read the same attribute path from every element of a sequence, in one reply.

        The op that makes a sample loop usable: reading three coordinates from each of eight
        vertices cost 33 round trips through per-element proxying, and costs one here.
        """
        obj = self.registry.resolve(req['h'])
        paths = req.get('paths') or []
        if not paths:
            raise ProtocolError('project needs at least one attribute path')
        start = int(req.get('start', 0) or 0)
        items = list(iter(obj))
        total = len(items)
        window = items[start:] if self.max_items is None else items[start:start + self.max_items]
        rows = []
        for element in window:
            row = []
            for path in paths:
                cur = element
                for part in path.split('.'):
                    cur = getattr(cur, part)
                row.append(self._encode(cur))
            rows.append(row)
        nxt = start + len(window)
        return {'kind': 'table', 'paths': list(paths), 'rows': rows, 'total': total,
                'next': nxt if nxt < total else None}

    def _op_batch(self, req):
        """Several unrelated ops in one round trip.

        Each sub-result is reported with its own ok/error status, so one failure does not discard
        the others -- the point of batching is to avoid round trips, not to couple outcomes.
        """
        out = []
        for sub in req.get('ops', []):
            try:
                out.append({'ok': True, 'result': self.handle(sub)})
            except BaseException as exc:                                 # noqa: BLE001
                out.append({'ok': False, 'error': type(exc).__name__, 'message': str(exc)[:400]})
        return {'kind': 'batch', 'results': out}

    def _op_release(self, req):
        return {'kind': VALUE, 'value': self.registry.release(req.get('hs', []))}

    def _op_stats(self, req):
        stats = self.registry.stats()
        stats['calls'] = self.calls
        return {'kind': VALUE, 'value': stats}

    def _op_reset(self, req):
        """Drop every handle. Vendor-specific state hygiene is layered on top by the worker."""
        return {'kind': VALUE, 'value': self.registry.clear()}
