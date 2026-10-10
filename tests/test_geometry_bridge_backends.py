"""Two vendors, one interface -- and the lifecycle rules that are correctness, not tuning.

The claim being tested is that a test written against the bridge does not know which side of a
process boundary its library is on. OpenVSP is the in-process case today, because its extension is
built for the same CPython the project uses -- the opposite pin to FreeCAD's. If that symmetry holds
here, the day either vendor changes its build is a one-line change with no test changes, which is the
reason both sit behind one interface rather than only FreeCAD being bridged.
"""
import os
import sys

import pytest

from geometry_bridge.api import HANDLE_CEILING, loopback_session, maybe_restart
from geometry_bridge.errors import StaleHandle
from geometry_bridge.transport import LocalTransport


class _Module(object):
    """Stands in for a vendor module in the local-backend tests."""

    answer = 41

    @staticmethod
    def make(n):
        return [float(i) for i in range(n)]


class TestTheLocalBackend:

    def test_a_real_module_is_reachable_by_name(self):
        from geometry_bridge.session import Session
        s = Session(LocalTransport({'math': 'math'}))
        try:
            m = s.module('math')
            assert m.sqrt(9.0) == 3.0
            assert m.pi == pytest.approx(3.141592653589793)
        finally:
            s.close()

    def test_an_absent_module_is_reported_not_raised(self):
        """One missing vendor must not stop every unrelated test, the same rule the worker uses."""
        t = LocalTransport({'nope': 'definitely_not_a_module_xyz'})
        assert 'definitely_not_a_module_xyz' in t.missing

    def test_the_local_backend_uses_the_same_proxy_path_as_a_worker(self):
        """Not a shortcut handing back raw objects: a test must behave identically either way."""
        from geometry_bridge.proxy import Remote
        from geometry_bridge.session import Session
        s = Session(LocalTransport({'json': 'json'}))
        try:
            decoder = s.module('json').JSONDecoder()
            assert isinstance(decoder, Remote), 'a non-value must still arrive as a proxy'
            assert decoder.decode('[1, 2]') == [1, 2]
        finally:
            s.close()


class TestOpenVSP:
    """OpenVSP is the in-process case. Skipped where it is not installed."""

    @pytest.fixture
    def vsp_session(self):
        try:
            from geometry_bridge.api import openvsp_session
            s = openvsp_session()
        except BaseException as exc:                                     # noqa: BLE001
            pytest.skip('OpenVSP not available: %s' % str(exc)[:80])
        yield s
        s.close()

    def test_openvsp_is_reachable_through_the_same_session_interface(self, vsp_session):
        vsp = vsp_session.module('vsp')
        version = vsp.GetVSPVersion()
        assert isinstance(version, str) and version
        assert vsp_session.label == 'OpenVSP'

    def test_the_vendor_runs_in_this_interpreter_not_a_worker(self, vsp_session):
        """The asymmetry worth asserting: OpenVSP matches our ABI, FreeCAD does not."""
        assert vsp_session.transport.python == 'in-process'

    def test_clearing_the_model_is_reachable_for_per_test_hygiene(self, vsp_session):
        """OpenVSP keeps one global model, so a reset hook needs this to exist."""
        vsp = vsp_session.module('vsp')
        vsp.ClearVSPModel()
        assert vsp.FindGeoms() is not None


class TestLifecycle:

    def test_a_session_is_a_context_manager(self):
        """A session owns a subprocess, so `with` has to work -- an un-closed one is the orphan
        hazard §5.5 exists for, and every caller was otherwise writing the same try/finally."""
        with loopback_session({'m': _Module}) as s:
            assert s.module('m') is not None
            assert not s._closed
        assert s._closed

    def test_the_context_manager_closes_on_an_exception(self):
        """The case the try/finally was there for in the first place."""
        s = loopback_session({'m': _Module})
        with pytest.raises(ValueError):
            with s:
                raise ValueError('boom')
        assert s._closed

    def test_the_context_manager_does_not_swallow(self):
        """`__exit__` returning anything truthy would silently pass failing tests."""
        s = loopback_session({'m': _Module})
        assert s.__exit__(None, None, None) is False

    def test_a_session_under_the_ceiling_is_not_restarted(self):
        s = loopback_session({'m': _Module})
        try:
            same = maybe_restart(s, lambda: loopback_session({'m': _Module}))
            assert same is s
        finally:
            s.close()

    def test_a_session_over_the_ceiling_is_replaced(self):
        s = loopback_session({'m': _Module})
        held = [s.module('m') for _ in range(5)]
        try:
            fresh = maybe_restart(s, lambda: loopback_session({'m': _Module}),
                                  handle_ceiling=2)
            assert fresh is not s
            assert fresh.stats()['live'] == 0, 'a replacement must start clean'
            fresh.close()
        finally:
            del held
            s.close()

    def test_a_proxy_used_across_a_reset_raises_rather_than_addressing_something_else(self):
        """What makes an automatic between-tests reset safe at all."""
        s = loopback_session({'m': _Module})
        try:
            kept = s.module('m')
            assert kept.answer == 41
            s.reset()
            with pytest.raises(StaleHandle):
                kept.answer
        finally:
            s.close()

    def test_a_reset_clears_the_callable_cache_too(self):
        """A cached entry naming a dropped handle's type would survive into a different object."""
        s = loopback_session({'m': _Module})
        try:
            s.module('m').make(2)
            assert s._callable_cache
            s.reset()
            assert not s._callable_cache
            assert not s._uncacheable_types
        finally:
            s.close()

    def test_the_default_ceiling_is_high_enough_not_to_fire_in_ordinary_use(self):
        assert HANDLE_CEILING >= 1000


class TestNoGlobalState:
    """What makes a parallel run under xdist safe: nothing is shared between sessions."""

    def test_two_sessions_in_one_process_do_not_interfere(self):
        a = loopback_session({'m': _Module})
        b = loopback_session({'m': _Module})
        try:
            pa = a.module('m')
            pb = b.module('m')
            assert pa.answer == 41 and pb.answer == 41
            a.reset()
            assert pb.answer == 41, 'resetting one session must not disturb the other'
            with pytest.raises(StaleHandle):
                pa.answer
        finally:
            a.close()
            b.close()

    def test_the_package_holds_no_module_level_session(self):
        """A module-global would be shared across xdist workers and silently serialize them."""
        import geometry_bridge
        import geometry_bridge.api as api
        from geometry_bridge.session import Session
        for module in (geometry_bridge, api):
            for name in dir(module):
                if name.startswith('_'):
                    continue
                assert not isinstance(getattr(module, name), Session), \
                    '%s.%s is a module-level Session' % (module.__name__, name)

    def test_the_worker_path_exists_and_is_inside_the_package(self):
        from geometry_bridge.api import WORKER
        assert os.path.isfile(WORKER)
        assert 'geometry_bridge' in WORKER

    def test_no_bridge_module_imports_a_vendor_at_module_scope(self):
        """The property that makes this package importable from any interpreter.

        `worker.py` is excluded: it is the one file that does import FreeCAD, and it is executed by
        the vendor's interpreter rather than imported by ours.
        """
        import importlib
        import pkgutil

        import geometry_bridge
        for info in pkgutil.iter_modules(geometry_bridge.__path__):
            if info.name == 'worker':
                continue
            module = importlib.import_module('geometry_bridge.%s' % info.name)
            assert module is not None
        assert 'FreeCAD' not in sys.modules, 'importing the package must not pull in FreeCAD'
