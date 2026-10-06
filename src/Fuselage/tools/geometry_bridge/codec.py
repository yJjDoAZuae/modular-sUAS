"""What crosses the boundary as a value, and what stays behind a handle.

The rule: anything JSON-representable crosses as itself; anything else stays in the worker and
crosses as a handle reference. A ``Shape`` is never serialized -- it does not have to be, and that
is what lets one expensive build serve any number of assertions.

**Float fidelity is a requirement, not a hope.** This project asserts a construction identity at
about 1e-13 mm and a wall tolerance at 0.01 mm, so a transport that rounded in the twelfth digit
would manufacture error indistinguishable from a geometry defect. Measured 2026-10-05: every probe
value round-tripped bit-exactly through this encoding, including 1e-13, ``1.0 + 1e-15``, a
subnormal at 2.2250738585072014e-308 and the largest finite double. CPython's ``repr`` is
round-trip exact and ``json`` uses it.

**The wire format is Python JSON, not interoperable JSON.** ``inf``, ``-inf`` and ``nan`` cross
intact, which the JSON standard does not permit. Both ends are CPython so this is safe, and it is
recorded because it constrains any future change of transport.

**Two mappings are deliberately lossy**, and tests that care use handles instead:
a ``tuple`` of scalars arrives as a ``list``, and a structure nested deeper than
:data:`MAX_VALUE_DEPTH` becomes a handle rather than a value.

See doc/architecture/geometry_bridge.md sections 4.3 and 4.4.
"""

#: Beyond this nesting depth a container is not inspected further and becomes a handle. Bounded
#: because the check is recursive and runs on every return value; an unbounded walk would let a
#: deeply nested vendor structure cost more to classify than to use.
MAX_VALUE_DEPTH = 3

#: Types that cross as themselves, unconditionally.
SCALARS = (type(None), bool, int, float, str)

#: Marker key for a handle reference travelling as a call argument.
HANDLE_KEY = '__h__'


def is_value(obj, depth=0):
    """Can `obj` cross as a JSON value, or must it stay behind a handle?

    `bytes` is deliberately excluded: it is not JSON-representable and silently encoding it as a
    string would be a lossy conversion of exactly the kind this project's measurement history warns
    about.
    """
    if isinstance(obj, SCALARS):
        return True
    if depth >= MAX_VALUE_DEPTH:
        return False
    if isinstance(obj, (list, tuple)):
        return all(is_value(x, depth + 1) for x in obj)
    if isinstance(obj, dict):
        return all(isinstance(k, str) and is_value(v, depth + 1) for k, v in obj.items())
    return False


def encode_value(obj):
    """Normalize a value for the wire. Tuples become lists; this is the documented lossy mapping."""
    if isinstance(obj, (list, tuple)):
        return [encode_value(x) for x in obj]
    if isinstance(obj, dict):
        return dict((k, encode_value(v)) for k, v in obj.items())
    return obj


def encode_argument(obj, handle_of):
    """Encode a call argument, turning any proxy into a handle reference.

    `handle_of` returns the handle id for a client-side proxy, or ``None`` if the object is not one.
    Passing a proxy by reference is what keeps a chain like ``a.cut(b)`` entirely worker-side.
    """
    h = handle_of(obj)
    if h is not None:
        return {HANDLE_KEY: h}
    if isinstance(obj, (list, tuple)):
        return [encode_argument(x, handle_of) for x in obj]
    if isinstance(obj, dict):
        return dict((k, encode_argument(v, handle_of)) for k, v in obj.items())
    return obj


def decode_argument(obj, resolve):
    """Turn handle references in an incoming argument back into live objects.

    `resolve` maps a handle id to the object, and is expected to raise for a released or unknown
    id rather than returning ``None`` -- a silent ``None`` here would reach vendor code and fail
    somewhere unrelated.
    """
    if isinstance(obj, dict) and HANDLE_KEY in obj and len(obj) == 1:
        return resolve(obj[HANDLE_KEY])
    if isinstance(obj, list):
        return [decode_argument(x, resolve) for x in obj]
    if isinstance(obj, dict):
        return dict((k, decode_argument(v, resolve)) for k, v in obj.items())
    return obj
