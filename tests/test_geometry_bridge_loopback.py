"""The whole bridge protocol, driven in-process against a stub vendor, with no FreeCAD present.

This file is why the library is testable at all. The codec, the handle watermark, the proxy
semantics, the lifetime rules, the cache policy, the error synthesis and the paging all run here in
the project's ordinary pytest tier in milliseconds. Testing them only against a real worker would
put the library that exists to enable the fast tier inside the slow one.

The stubs are not toys: each models a vendor behavior that was measured to break a naive proxy --
an object with no ``len``, a mapping-valued attribute, an object whose properties are added at run
time, a sequence worth projecting over, and an operator that returns ``NotImplemented``.
"""
import gc

import pytest

from geometry_bridge.errors import (
    BridgeError, ProtocolError, RemoteGeometryError, StaleHandle, remote_class)
from geometry_bridge.ops import Dispatcher
from geometry_bridge.proxy import Remote, RemoteMethod
from geometry_bridge.session import Session
from geometry_bridge.transport import LoopbackTransport


# ---------------------------------------------------------------- the stub vendor


class StubPrecondition(Exception):
    """Stands in for `cowl_interior.PreconditionFailed`: a project guard with its own class."""


class StubVector(object):
    def __init__(self, x, y, z):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __eq__(self, other):
        if not isinstance(other, StubVector):
            return NotImplemented
        return (self.x, self.y, self.z) == (other.x, other.y, other.z)

    def __add__(self, other):
        if not isinstance(other, StubVector):
            return NotImplemented
        return StubVector(self.x + other.x, self.y + other.y, self.z + other.z)

    def __mul__(self, k):
        if not isinstance(k, (int, float)):
            return NotImplemented
        return StubVector(self.x * k, self.y * k, self.z * k)

    def __neg__(self):
        return StubVector(-self.x, -self.y, -self.z)

    def length(self):
        return (self.x ** 2 + self.y ** 2 + self.z ** 2) ** 0.5


class StubShape(object):
    """A shape-like object: has attributes and methods, and deliberately has NO ``len``."""

    def __init__(self, volume=1.0, valid=True, n_vertexes=3):
        self.Volume = volume
        self._valid = valid
        self.Vertexes = [StubVector(i, i * 2, i * 3) for i in range(n_vertexes)]

    def isValid(self):
        return self._valid

    def cut(self, other):
        return StubShape(volume=self.Volume - other.Volume, n_vertexes=2)

    def check(self):
        raise StubPrecondition('section too shallow to erode')


class StubDynamic(object):
    """Models a FreeCAD document object: properties appear at run time.

    Two of these report the same type name and can carry different attributes, which is why a
    client-side cache keyed on the type name is unsound for them.
    """

    def __init__(self, **props):
        self.PropertiesList = sorted(props)
        for k, v in props.items():
            setattr(self, k, v)


class StubDocumentHost(object):
    """Holds a mapping-valued attribute, the case that crashed a prototype assuming an index."""

    def __init__(self):
        self.documents = {'alpha': StubShape(2.0), 'beta': StubShape(3.0)}
        self.Label = 'start'


class StubModule(object):
    Vector = StubVector
    Shape = StubShape
    Dynamic = StubDynamic
    PreconditionFailed = StubPrecondition

    @staticmethod
    def makeShape(volume=1.0, n_vertexes=3):
        return StubShape(volume=volume, n_vertexes=n_vertexes)

    @staticmethod
    def host():
        return StubDocumentHost()

    @staticmethod
    def boom():
        raise StubPrecondition('a deliberate vendor failure')

    @staticmethod
    def numbers(n=5):
        return [StubVector(i, i + 0.5, i + 0.25) for i in range(n)]


@pytest.fixture
def session():
    s = Session(LoopbackTransport({'stub': StubModule}))
    yield s
    s.close()


@pytest.fixture
def stub(session):
    return session.module('stub')


@pytest.fixture
def baseline(session):
    """Live handle count after everything the fixtures created has settled."""
    session.collect()
    return session.stats()['live']


# ---------------------------------------------------------------- the module allowlist


class TestModuleAccess:

    def test_an_allowlisted_module_is_reachable(self, stub):
        assert isinstance(stub, Remote)
        assert stub.remote_type == 'type'

    def test_a_module_outside_the_allowlist_is_refused_by_name(self, session):
        with pytest.raises(RemoteGeometryError) as caught:
            session.module('os')
        assert caught.value.remote_name == 'ProtocolError'
        assert 'not exposed' in caught.value.message


# ---------------------------------------------------------------- attributes and assignment


class TestAttributes:

    def test_a_scalar_attribute_comes_back_as_a_plain_value(self, stub):
        shape = stub.makeShape(volume=7.5)
        assert shape.Volume == 7.5
        assert isinstance(shape.Volume, float)

    def test_a_method_is_callable_and_returns_a_value(self, stub):
        assert stub.makeShape().isValid() is True

    def test_an_object_valued_attribute_stays_remote(self, stub):
        verts = stub.makeShape().Vertexes
        assert isinstance(verts, Remote)
        assert verts.remote_type == 'list'

    def test_assignment_reaches_the_vendor_object(self, stub):
        """Required, not optional: the project's real FreeCAD code drives documents by assigning."""
        host = stub.host()
        host.Label = 'changed'
        assert host.Label == 'changed'

    def test_assignment_of_a_proxy_passes_by_reference(self, stub):
        host = stub.host()
        shape = stub.makeShape(volume=42.0)
        host.Label = shape
        assert host.Label.Volume == 42.0

    def test_a_private_name_is_reachable(self, stub):
        """The regression that mattered: a blanket underscore guard hid the whole private API."""
        shape = stub.makeShape()
        assert shape._valid is True

    def test_a_dunder_is_not_forwarded_blindly(self, stub):
        """copy, pickle and pytest all probe for dunders; a round trip each is slow and wrong.

        ``__deepcopy__`` is the probe used rather than ``__getstate__``: Python 3.11 gave ``object``
        a real ``__getstate__``, so that one is found by ordinary lookup and never reaches
        ``__getattr__`` at all.
        """
        shape = stub.makeShape()
        before = shape._session.round_trips
        with pytest.raises(AttributeError):
            shape.__deepcopy__
        assert shape._session.round_trips == before, 'a dunder probe must cost no round trip'

    def test_deleting_an_attribute_is_refused_clearly(self, stub):
        with pytest.raises(AttributeError) as caught:
            del stub.makeShape().Volume
        assert 'not supported' in str(caught.value)


# ---------------------------------------------------------------- object semantics


class TestObjectSemantics:

    def test_truthiness_works_on_an_object_with_no_len(self, stub):
        """`__len__` fallback raised TypeError on a Solid. `__bool__` must be explicit."""
        shape = stub.makeShape()
        assert bool(shape) is True
        if shape:
            pass
        else:
            pytest.fail('a proxy must be truthy')

    def test_a_proxy_is_unhashable_on_purpose(self, stub):
        shape = stub.makeShape()
        with pytest.raises(TypeError):
            {shape: 1}

    def test_equality_forwards_to_the_vendor(self, stub):
        a = stub.Vector(1.0, 2.0, 3.0)
        b = stub.Vector(1.0, 2.0, 3.0)
        c = stub.Vector(9.0, 9.0, 9.0)
        assert (a == b) is True
        assert (a == c) is False
        assert (a != c) is True

    def test_arithmetic_forwards(self, stub):
        a = stub.Vector(1.0, 2.0, 3.0)
        b = stub.Vector(4.0, 5.0, 6.0)
        assert (a + b).x == 5.0
        assert (a * 2.0).z == 6.0
        assert (-a).y == -2.0

    def test_an_unsupported_operand_returns_not_implemented_so_python_can_fall_back(self, stub):
        """The vendor's NotImplemented cannot cross as a value; it must still behave as one."""
        a = stub.Vector(1.0, 2.0, 3.0)
        with pytest.raises(TypeError):
            a + 5          # StubVector returns NotImplemented, so Python raises TypeError

    def test_subscript_passes_the_key_through_for_a_mapping(self, stub):
        """A prototype assumed an integer index and raised KeyError on a dict-valued attribute."""
        docs = stub.host().documents
        assert docs['alpha'].Volume == 2.0
        assert docs['beta'].Volume == 3.0

    def test_subscript_works_for_a_sequence_too(self, stub):
        assert stub.makeShape().Vertexes[1].y == 2.0

    def test_len_forwards(self, stub):
        assert len(stub.makeShape(n_vertexes=4).Vertexes) == 4

    def test_len_on_an_object_without_one_raises_type_error(self, stub):
        with pytest.raises(RemoteGeometryError) as caught:
            len(stub.makeShape())
        assert caught.value.remote_name == 'TypeError'

    def test_iteration_is_one_round_trip(self, stub):
        verts = stub.makeShape(n_vertexes=6).Vertexes
        before = stub._session.round_trips
        got = [v for v in verts]
        cost = stub._session.round_trips - before
        assert len(got) == 6
        assert cost == 1, 'iteration must use the bulk op, got %d trips' % cost

    def test_iterating_a_mapping_yields_its_keys(self, stub):
        """Delegating to the object's own iterator gets mapping semantics for free."""
        assert sorted(k for k in stub.host().documents) == ['alpha', 'beta']

    def test_contains_forwards(self, stub):
        assert ('alpha' in stub.host().documents) is True


# ---------------------------------------------------------------- handle lifetime


class TestLifetime:

    def test_an_unnamed_temporary_is_freed(self, session, stub, baseline):
        def measure():
            return stub.makeShape(volume=3.0).Volume
        assert measure() == 3.0
        session.assert_no_leak(baseline, 'an unnamed temporary')

    def test_two_hundred_temporaries_leave_nothing_behind(self, session, stub, baseline):
        for _ in range(200):
            shape = stub.makeShape()
            assert shape.Volume == 1.0
            del shape
        session.assert_no_leak(baseline, '200 temporaries')

    def test_a_chain_leaves_exactly_one_handle_then_none(self, session, stub, baseline):
        out = stub.makeShape(volume=10.0).cut(stub.makeShape(volume=4.0))
        assert out.Volume == 6.0
        session.collect()
        assert session.stats()['live'] == baseline + 1, 'only the result should survive'
        del out
        session.assert_no_leak(baseline, 'after dropping the result')

    def test_a_still_referenced_object_is_never_freed(self, session, stub, baseline):
        """**The converse, and the test that caught a live object being freed.**

        A bound method that held its owner's handle id rather than the owner proxy let the owner be
        collected mid-expression, so the request carrying the release then used the handle. Freeing
        a live object is worse than leaking: a leak wastes memory, this corrupts a result.
        """
        kept = stub.makeShape(volume=8.0)
        for _ in range(50):
            tmp = stub.makeShape()
            assert tmp.Volume == 1.0
            del tmp
        session.collect()
        assert session.stats()['live'] == baseline + 1
        assert kept.Volume == 8.0, 'the kept object must still be usable'

    def test_a_bound_method_keeps_its_owner_alive(self, session, stub):
        """The precise mechanism, isolated: a method object alone must hold the shape."""
        method = stub.makeShape(volume=5.0).isValid
        assert isinstance(method, RemoteMethod)
        gc.collect()
        session.flush_releases()
        assert method() is True, 'the owner was collected while its method was still held'

    def test_a_method_call_allocates_no_handle(self, session, stub, baseline):
        shape = stub.makeShape()
        session.collect()
        before = session.stats()['live']
        for _ in range(50):
            assert shape.isValid() is True
        session.collect()
        assert session.stats()['live'] == before

    def test_releases_ride_along_rather_than_costing_a_trip(self, session, stub, baseline):
        for _ in range(5):
            del_me = stub.makeShape()
            del del_me
        gc.collect()
        queued = set(session._pending_release)
        assert queued, 'collected proxies should have queued releases'
        before = session.round_trips
        stub.makeShape()                      # ordinary work, whose result is itself discarded
        assert session.round_trips - before == 1, 'the releases must not add a round trip'
        # The new temporary's own handle queues on the way out, so the invariant is that the
        # EARLIER ids were carried -- not that the queue is empty.
        assert not (queued & set(session._pending_release)), \
            'the queued releases must have ridden along with that request'


class TestReferenceCycles:
    """IP-GB-19: what a reference cycle costs, measured rather than assumed.

    §4.6 records this as the design's one unmeasured residual limit. The release policy rests on
    `__del__` firing when the last reference goes, which is refcounting -- and refcounting does not
    see a cycle. **The loopback tier is the right place for it**, because a cycle is a property of
    the client's own object graph and nothing about it involves a vendor.

    The answer: a cycle delays a release until a collector pass, and one pass is the whole remedy.
    A delay, not a leak, and nothing needs to be tracked to bound it.
    """

    def test_a_proxy_in_a_cycle_is_not_released_when_its_name_goes(self, session, stub):
        """The limit itself, written as a test so it cannot quietly become false."""
        gc.collect()
        holder = {}
        holder['self'] = holder
        holder['shape'] = stub.makeShape()
        h = holder['shape'].remote_handle
        session.collect()
        assert session.transport.dispatcher.registry.is_live(h)

        del holder                            # the only name for the cycle
        session.flush_releases()
        assert session.transport.dispatcher.registry.is_live(h), \
            'a cycle is invisible to refcounting, so the handle must still be held here'

    def test_one_gc_pass_is_the_whole_remedy(self, session, stub):
        """What bounds the delay: a single `gc.collect()` releases it."""
        gc.collect()
        holder = {}
        holder['self'] = holder
        holder['shape'] = stub.makeShape()
        h = holder['shape'].remote_handle
        del holder

        gc.collect()
        session.flush_releases()
        assert not session.transport.dispatcher.registry.is_live(h)

    def test_many_cycles_accumulate_and_then_all_release_together(self, session, stub):
        """Bounded, not leaked: the handles are delayed as a group, then all reclaimed."""
        gc.collect()
        session.collect()
        before = session.stats()['live']
        handles = []
        for _ in range(40):
            node = {}
            node['self'] = node
            node['shape'] = stub.makeShape()
            handles.append(node['shape'].remote_handle)
            del node
        session.flush_releases()
        held = session.stats()['live'] - before
        assert held == 40, 'all 40 should still be held, got %d' % held

        gc.collect()
        session.flush_releases()
        assert session.stats()['live'] == before
        reg = session.transport.dispatcher.registry
        for h in handles:
            assert not reg.is_live(h)

    def test_a_proxy_not_in_a_cycle_needs_no_gc_pass(self, session, stub):
        """The converse. Without it the tests above would pass even if nothing were refcounted."""
        gc.collect()
        session.collect()
        before = session.stats()['live']
        tmp = stub.makeShape()
        h = tmp.remote_handle
        del tmp                               # refcount hits zero here; no collector involved
        session.flush_releases()
        assert session.stats()['live'] == before
        assert not session.transport.dispatcher.registry.is_live(h)

    def test_a_chain_intermediate_is_not_a_cycle(self, session, stub):
        """`a.cut(b).cut(c)`'s unnamed middle result is freed by refcounting, not by a gc pass.

        Pinned because the bound-method defect this design already fixed lived exactly here. If
        anything about an intermediate's lifetime needed the collector, every chain would hold
        handles until one happened to run.
        """
        gc.collect()
        session.collect()
        before = session.stats()['live']
        a, b, c = stub.makeShape(2.0), stub.makeShape(0.5), stub.makeShape(0.25)
        result = a.cut(b).cut(c)
        assert result.Volume == pytest.approx(1.25)
        del result
        session.flush_releases()
        # a, b and c are still named; the intermediate and the result should both have gone.
        assert session.stats()['live'] - before == 3


class TestWatermark:

    def test_a_released_handle_is_reported_as_stale(self, session, stub):
        shape = stub.makeShape()
        h = shape.remote_handle
        del shape
        session.collect()
        revived = Remote(session, h, 'StubShape', '<freed>')
        with pytest.raises(StaleHandle) as caught:
            revived.Volume
        assert 'released' in str(caught.value)

    def test_a_never_issued_handle_is_reported_as_a_protocol_fault(self, session):
        bogus = Remote(session, 999999, 'StubShape', '<invented>')
        with pytest.raises(RemoteGeometryError) as caught:
            bogus.Volume
        assert caught.value.remote_name == 'ProtocolError'
        assert 'never issued' in caught.value.message

    def test_the_registry_keeps_no_per_id_released_set(self, session, stub):
        """The prototype grew a set to 336 entries for 300 temporaries. One integer is enough."""
        reg = session.transport.dispatcher.registry
        for _ in range(300):
            tmp = stub.makeShape()
            del tmp
        session.collect()
        assert isinstance(reg._released, int)
        assert reg.stats()['released'] >= 300
        assert not hasattr(reg, '_released_ids')


# ---------------------------------------------------------------- the callable cache


class TestCallableCache:

    def test_a_warm_method_call_costs_one_round_trip(self, session, stub):
        shape = stub.makeShape()
        shape.isValid()                      # warms (StubShape, 'isValid')
        before = session.round_trips
        for _ in range(10):
            shape.isValid()
        assert session.round_trips - before == 10

    def test_a_dynamic_property_object_is_never_cached_by_type(self, session, stub):
        """Two FreeCAD document objects report one type name and can carry different attributes."""
        a = stub.Dynamic(Alpha=1)
        b = stub.Dynamic(Beta=2)
        assert a.Alpha == 1
        assert 'StubDynamic' in session.uncacheable_types
        assert ('StubDynamic', 'Alpha') not in session._callable_cache
        # b genuinely lacks Alpha; a stale per-type cache would have hidden that.
        with pytest.raises(RemoteGeometryError) as caught:
            b.Alpha
        assert caught.value.remote_name == 'AttributeError'

    def test_a_static_type_is_cached(self, session, stub):
        shape = stub.makeShape()
        shape.isValid()
        assert session._callable_cache.get(('StubShape', 'isValid')) is True


# ---------------------------------------------------------------- errors


class TestErrors:

    def test_a_vendor_exception_keeps_its_class_name(self, session, stub):
        cls = remote_class('StubPrecondition', ('StubPrecondition', 'Exception'))
        with pytest.raises(cls) as caught:
            stub.boom()
        assert caught.value.remote_name == 'StubPrecondition'
        assert 'deliberate vendor failure' in caught.value.message

    def test_the_same_failure_is_catchable_by_hierarchy(self, stub):
        with pytest.raises(RemoteGeometryError):
            stub.boom()

    def test_the_synthesized_class_identity_is_stable(self, stub):
        seen = []
        for _ in range(2):
            try:
                stub.boom()
            except RemoteGeometryError as exc:
                seen.append(type(exc))
        assert seen[0] is seen[1], 'a fresh class per raise would break pytest.raises reuse'

    def test_a_remote_builtin_is_catchable_as_the_real_builtin(self, stub):
        with pytest.raises(AttributeError):
            stub.makeShape().NoSuchAttribute

    def test_a_remote_builtin_is_also_a_remote_geometry_error(self, stub):
        with pytest.raises(RemoteGeometryError):
            stub.makeShape().NoSuchAttribute

    def test_a_bridge_fault_is_not_catchable_as_a_geometry_error(self, session):
        """The separation that matters: a broken bridge must not read as a geometry bug."""
        session.close()
        with pytest.raises(BridgeError) as caught:
            session.module('stub')
        assert not isinstance(caught.value, RemoteGeometryError)

    def test_bridge_error_and_remote_error_share_no_ancestry(self):
        assert not issubclass(BridgeError, RemoteGeometryError)
        assert not issubclass(RemoteGeometryError, BridgeError)
        assert issubclass(ProtocolError, BridgeError)

    def test_stale_handle_is_a_geometry_error_not_a_bridge_error(self):
        """It is a lifetime bug in the test's own code, reported where the test can catch it."""
        assert issubclass(StaleHandle, RemoteGeometryError)


# ---------------------------------------------------------------- bulk reads


class TestBulkReads:

    def test_project_reads_a_table_in_one_round_trip(self, session, stub):
        """Per-element proxying cost 4.1 round trips per vertex. This is the fix."""
        verts = stub.numbers(8)
        before = session.round_trips
        rows = verts.project('x', 'y', 'z')
        cost = session.round_trips - before
        assert len(rows) == 8
        assert rows[2] == (2.0, 2.5, 2.25)
        assert cost == 1, 'project must be one round trip, got %d' % cost

    def test_project_refuses_an_empty_path_list(self, stub):
        with pytest.raises(RemoteGeometryError) as caught:
            stub.numbers(2).project()
        assert caught.value.remote_name == 'ProtocolError'

    def test_project_follows_a_dotted_path(self, stub):
        shape = stub.makeShape(n_vertexes=3)
        rows = shape.Vertexes.project('x')
        assert [r[0] for r in rows] == [0.0, 1.0, 2.0]

    def test_a_capped_reply_pages_rather_than_truncating(self):
        """A reply too large for one line must page, not silently lose elements."""
        s = Session(LoopbackTransport({'stub': StubModule}, max_items=3))
        try:
            verts = s.module('stub').numbers(10)
            rows = verts.project('x')
            assert len(rows) == 10, 'paging must return every element'
            assert [r[0] for r in rows] == [float(i) for i in range(10)]
        finally:
            s.close()

    def test_iteration_pages_too(self):
        s = Session(LoopbackTransport({'stub': StubModule}, max_items=4))
        try:
            got = list(s.module('stub').numbers(10))
            assert len(got) == 10
        finally:
            s.close()

    def test_batch_returns_each_result_independently(self, session, stub):
        a = stub.makeShape(volume=1.0)
        b = stub.makeShape(volume=2.0)
        before = session.round_trips
        got = session.batch([(a, 'Volume'), (b, 'Volume'), (a, 'NoSuchThing')])
        assert session.round_trips - before == 1
        assert got[0] == (True, 1.0)
        assert got[1] == (True, 2.0)
        assert got[2][0] is False and 'AttributeError' in got[2][1], \
            'one failure must not discard the others'


# ---------------------------------------------------------------- reset


class TestReset:

    def test_reset_drops_every_handle(self, session, stub):
        kept = stub.makeShape()
        assert kept.Volume == 1.0
        session.reset()
        assert session.stats()['live'] == 0

    def test_a_handle_used_after_a_reset_reports_staleness(self, session, stub):
        kept = stub.makeShape()
        session.reset()
        with pytest.raises(StaleHandle):
            kept.Volume
