"""The worker-side handle registry, and the watermark rule that needs no per-id storage.

A handle is an integer naming an object the worker holds. Three states have to be told apart, and
telling them apart is what makes a lifetime bug report itself instead of surfacing as a confusing
geometry error:

    live        in the registry
    released    its client proxy was collected and the handle was returned
    unknown     never issued at all -- a protocol fault, not a lifetime one

The obvious implementation keeps a set of released ids. A prototype did, and it grew to 336 entries
for 300 temporaries, unbounded: the same leak the reference counting exists to prevent, one level
down. **Ids are issued monotonically, so no per-id storage is needed.** An id not in the registry
is released if it has ever been issued, and unknown otherwise -- one integer of state for the whole
process.

This module imports no vendor library and is exercised in the project's ordinary pytest tier.

See doc/architecture/geometry_bridge.md section 4.6.
"""
from .errors import ProtocolError, StaleHandle


class Registry(object):
    """Objects the worker holds on the client's behalf, addressed by monotonic integer id."""

    __slots__ = ('_held', '_issued', '_high_water', '_released')

    def __init__(self):
        self._held = {}
        self._issued = 0          # the watermark: every id <= this has been issued
        self._high_water = 0      # the most objects ever held at once
        self._released = 0        # count only, for observability -- never a set of ids

    def __len__(self):
        return len(self._held)

    def hold(self, obj):
        """Register `obj` and return its new handle id."""
        self._issued += 1
        self._held[self._issued] = obj
        if len(self._held) > self._high_water:
            self._high_water = len(self._held)
        return self._issued

    def resolve(self, hid):
        """The live object for `hid`, or a named failure saying which kind of mistake this is."""
        try:
            return self._held[hid]
        except KeyError:
            pass
        except TypeError:
            raise ProtocolError('handle must be an integer, got %r' % (hid,))
        if isinstance(hid, int) and 0 < hid <= self._issued:
            raise StaleHandle(
                'handle %d was released: the client proxy for it was garbage collected' % hid)
        raise ProtocolError('handle %r was never issued by this worker' % (hid,))

    def release(self, hids):
        """Drop handles. Releasing an already-released or unknown id is not an error.

        Deliberately forgiving: releases are driven by garbage collection and batched, so a
        duplicate is an ordinary consequence of a proxy being collected twice over a restart
        boundary, not a fault worth failing a test for.
        """
        n = 0
        for hid in hids:
            if self._held.pop(hid, None) is not None:
                self._released += 1
                n += 1
        return n

    def clear(self):
        """Drop everything. Used by a worker reset; invalidates every outstanding handle."""
        n = len(self._held)
        self._released += n
        self._held.clear()
        return n

    def stats(self):
        return {
            'live': len(self._held),
            'issued': self._issued,
            'high_water': self._high_water,
            'released': self._released,
        }
