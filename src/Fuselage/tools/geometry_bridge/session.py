"""The client session: proxies, lifetime, and the callable cache.

A `Session` wraps a transport and is what a test actually holds. It owns three things the test
author must never have to think about:

**Handle lifetime.** A proxy's ``__del__`` queues its handle here; the queue rides along on the
next request, so reclaiming costs no round trip of its own, and a threshold flush covers a session
that has gone quiet. Measured on the prototype: 200 temporaries in a loop leave nothing behind, and
a chain of three booleans leaves exactly one live handle -- the result -- freed in turn when
dropped.

**The callable cache.** A method call would otherwise cost two round trips, one to discover the
attribute is callable and one to call it. The cache makes a warm call a single trip. **The worker
decides what may be cached**, reporting a ``cacheable`` flag, because two FreeCAD document objects
can report the same type name and carry different run-time properties; the client never infers it.

**Leak observability.** ``stats()`` reports live, high-water and released counts, and
``assert_no_leak`` pins the invariant so a regression is caught by the suite rather than noticed as
slow memory growth.

See doc/architecture/geometry_bridge.md sections 4.5, 4.6 and 4.8.
"""
import gc

from .errors import BridgeError
from .ops import CALLABLE, HANDLE, LIST, VALUE
from .proxy import Remote, RemoteMethod, _NOT_IMPLEMENTED_TYPE

#: Flush queued releases once this many have built up, even if no other request is due. Chosen so an
#: idle session cannot accumulate unboundedly while staying far above the per-expression churn that
#: piggybacking already covers.
RELEASE_BATCH = 64


class Session(object):
    """Client-side façade over a transport: proxies in, measurements out."""

    def __init__(self, transport, label='geometry'):
        self.transport = transport
        self.label = label
        self._pending_release = []
        self._callable_cache = {}
        self._uncacheable_types = set()
        self.released_total = 0
        self._closed = False

    # -- lifetime

    def _queue_release(self, h):
        self._pending_release.append(h)

    def _take_pending(self):
        hs = self._pending_release
        self._pending_release = []
        self.released_total += len(hs)
        return hs

    def flush_releases(self):
        """Send queued releases now. Returns how many were sent."""
        if self._closed or not self._pending_release:
            return 0
        hs = self._take_pending()
        self.transport.request({'op': 'release', 'hs': hs})
        return len(hs)

    def collect(self):
        """Force a collection pass and push the releases it produces.

        Needed because promptness relies on reference counting: a proxy caught in a reference cycle
        waits for the collector, so a test that pins a lifetime invariant calls this first rather
        than assuming.
        """
        gc.collect()
        return self.flush_releases()

    def assert_no_leak(self, expected_live, note=''):
        """Assert the worker holds exactly `expected_live` handles after a collection."""
        __tracebackhide__ = True
        self.collect()
        live = self.stats()['live']
        if live != expected_live:
            raise AssertionError(
                'handle leak%s: %d live, expected %d'
                % ((' (%s)' % note) if note else '', live, expected_live))
        return live

    # -- transport

    def _request(self, payload):
        __tracebackhide__ = True
        if self._closed:
            raise BridgeError('this %s session is closed' % self.label)
        if self._pending_release:
            payload['rel'] = self._take_pending()
        return self.transport.request(payload)

    def _wrap(self, reply, allow_not_implemented=False):
        kind = reply.get('kind')
        if kind == VALUE:
            return reply.get('value')
        if kind == HANDLE:
            if reply.get('type') == _NOT_IMPLEMENTED_TYPE and allow_not_implemented:
                # Drop the handle rather than holding a proxy to NotImplemented.
                self._queue_release(reply['h'])
                return NotImplemented
            return Remote(self, reply['h'], reply.get('type', '?'), reply.get('repr', ''),
                          reply.get('bases') or ())
        if kind == LIST:
            return [self._wrap(x) for x in reply.get('items', [])]
        if kind == CALLABLE:
            raise BridgeError('a callable arrived where a value was expected')
        raise BridgeError('unexpected reply kind %r' % (kind,))

    def _maybe_flush(self):
        if len(self._pending_release) >= RELEASE_BATCH:
            self.flush_releases()

    # -- attribute access

    def _get(self, proxy, name):
        __tracebackhide__ = True
        self._maybe_flush()
        key = (proxy.remote_type, name)
        if self._callable_cache.get(key) is True:
            return RemoteMethod(proxy, name)          # no round trip, no handle
        reply = self._request({'op': 'getattr', 'h': proxy.remote_handle, 'name': name})
        cacheable = reply.get('cacheable', False)
        # Recorded for both outcomes, not just the callable one: whether a type may be cached is a
        # property of the type, and a test that asserts "this type is never cached" has to be able
        # to see it after reading an ordinary value attribute.
        if not cacheable:
            self._uncacheable_types.add(proxy.remote_type)
        if reply.get('kind') == CALLABLE:
            if cacheable:
                self._callable_cache[key] = True
            return RemoteMethod(proxy, name)
        if cacheable:
            self._callable_cache[key] = False
        return self._wrap(reply)

    def _set(self, proxy, name, value):
        __tracebackhide__ = True
        self._request({'op': 'setattr', 'h': proxy.remote_handle, 'name': name,
                       'value': self._encode_arg(value)})

    def _callattr(self, proxy, name, args, kwargs, allow_not_implemented=False):
        __tracebackhide__ = True
        self._maybe_flush()
        reply = self._request({
            'op': 'callattr', 'h': proxy.remote_handle, 'name': name,
            'args': [self._encode_arg(a) for a in args],
            'kwargs': dict((k, self._encode_arg(v)) for k, v in kwargs.items())})
        return self._wrap(reply, allow_not_implemented=allow_not_implemented)

    # -- containers

    def _len(self, proxy):
        __tracebackhide__ = True
        return self._wrap(self._request({'op': 'len', 'h': proxy.remote_handle}))

    def _getitem(self, proxy, key):
        __tracebackhide__ = True
        return self._wrap(self._request({'op': 'getitem', 'h': proxy.remote_handle,
                                         'key': self._encode_arg(key)}))

    def _setitem(self, proxy, key, value):
        __tracebackhide__ = True
        self._request({'op': 'setitem', 'h': proxy.remote_handle,
                       'key': self._encode_arg(key), 'value': self._encode_arg(value)})

    def _iterate(self, proxy):
        """Every element, paging if the worker caps a reply."""
        __tracebackhide__ = True
        out = []
        start = 0
        while True:
            reply = self._request({'op': 'iterate', 'h': proxy.remote_handle, 'start': start})
            out.extend(self._wrap(x) for x in reply.get('items', []))
            nxt = reply.get('next')
            if nxt is None:
                return out
            start = nxt

    def _project(self, proxy, paths):
        """A table of attribute values over a sequence, paging if the worker caps a reply."""
        __tracebackhide__ = True
        rows = []
        start = 0
        while True:
            reply = self._request({'op': 'project', 'h': proxy.remote_handle,
                                   'paths': list(paths), 'start': start})
            for row in reply.get('rows', []):
                rows.append(tuple(self._wrap(cell) for cell in row))
            nxt = reply.get('next')
            if nxt is None:
                return rows
            start = nxt

    # -- encoding

    def _encode_arg(self, value):
        from . import codec
        return codec.encode_argument(
            value, lambda v: v.remote_handle if isinstance(v, Remote) else None)

    # -- api

    def module(self, name):
        """A proxy to an allowlisted vendor module."""
        return self._wrap(self._request({'op': 'module', 'name': name}))

    def stats(self):
        return self._wrap(self._request({'op': 'stats'}))

    def batch(self, calls):
        """Several independent reads in one round trip.

        `calls` is a sequence of ``(proxy, attribute_name)`` pairs. Each result is returned
        separately as ``(ok, value_or_message)``: one failure does not discard the others, because
        the purpose of batching is to avoid round trips rather than to couple outcomes.
        """
        __tracebackhide__ = True
        ops = [{'op': 'getattr', 'h': p.remote_handle, 'name': n} for p, n in calls]
        reply = self._request({'op': 'batch', 'ops': ops})
        out = []
        for sub in reply.get('results', []):
            if sub.get('ok'):
                out.append((True, self._wrap(sub['result'])))
            else:
                out.append((False, '%s: %s' % (sub.get('error'), sub.get('message'))))
        return out

    def reset(self):
        """Drop every handle and the vendor's own global state.

        Invalidates every outstanding proxy, so it is only safe at a test boundary. A proxy used
        afterwards raises `StaleHandle` rather than addressing a different object, which is the
        property that makes this safe to do automatically between tests.
        """
        self._pending_release = []
        self._callable_cache.clear()
        self._uncacheable_types.clear()
        return self._wrap(self._request({'op': 'reset'}))

    def needs_restart(self, handle_ceiling):
        """Is this worker holding more than it should?

        A worker holds every object its handles reference, and this project has produced a single
        measurement that reached 5 GB of RAM on a degenerate configuration. Checked rather than
        assumed, and acted on only between tests: a restart invalidates every outstanding handle.
        """
        if self._closed:
            return False
        return self.stats()['live'] > handle_ceiling

    @property
    def round_trips(self):
        return self.transport.round_trips

    @property
    def uncacheable_types(self):
        """Types the worker refused to let the client cache. For diagnostics and tests."""
        return sorted(self._uncacheable_types)

    def close(self):
        if self._closed:
            return
        try:
            self.transport.close()
        finally:
            self._closed = True

    def __enter__(self):
        """A session owns a subprocess, so `with` is the right way to hold one.

        Added because every caller outside the pytest fixtures was writing the same try/finally,
        and a worker left running is the orphan hazard §5.5 exists for.
        """
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
