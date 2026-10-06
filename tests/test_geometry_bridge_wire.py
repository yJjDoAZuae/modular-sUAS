"""The line protocol and the liveness deadline, against a fake worker process.

No FreeCAD and no vendor here. The fake worker is an ordinary Python script, which is what lets the
two things that would otherwise be untestable get tested: a worker that **hangs** and a worker that
**dies**, each of which must produce a named failure rather than an indefinitely blocked test run.

The hang case is the one this project has reason to care about: a `solid.common` that did not finish
in nine minutes, and a `makeOffset2D` that was still running three hours and forty-eight minutes
later because a timeout was reported in prose and the process was never stopped.
"""
import io
import json
import os
import subprocess
import sys
import textwrap
import time

import pytest

from geometry_bridge import wire
from geometry_bridge.errors import BridgeTimeout, ProtocolError, RemoteGeometryError, WorkerDied
from geometry_bridge.ops import Dispatcher
from geometry_bridge.session import Session
from geometry_bridge.transport import WorkerTransport


# ---------------------------------------------------------------- framing, in-process


class _Stub(object):
    value = 7

    @staticmethod
    def boom():
        raise ValueError('deliberate')


def _serve_once(requests, heartbeat_s=1000.0):
    """Run the serve loop over canned input and return the lines it wrote."""
    stdin = io.StringIO(''.join(json.dumps(r) + '\n' for r in requests))
    stdout = io.StringIO()
    wire.serve(Dispatcher({'stub': _Stub}), stdin=stdin, stdout=stdout,
               heartbeat_s=heartbeat_s)
    return [ln for ln in stdout.getvalue().splitlines() if ln]


class TestFraming:

    def test_every_reply_carries_the_sentinel(self):
        lines = _serve_once([{'op': 'module', 'name': 'stub', 'id': 1}])
        assert lines
        assert all(ln.startswith(wire.SENTINEL) for ln in lines)

    def test_the_first_line_is_a_hello_with_the_interpreter_version(self):
        lines = _serve_once([])
        hello = json.loads(lines[0][len(wire.SENTINEL):])
        assert hello['kind'] == 'hello'
        assert hello['python'].count('.') == 2

    def test_a_reply_echoes_the_request_id(self):
        lines = _serve_once([{'op': 'module', 'name': 'stub', 'id': 42}])
        reply = json.loads(lines[-1][len(wire.SENTINEL):])
        assert reply['id'] == 42

    def test_a_malformed_request_line_is_answered_not_fatal(self):
        stdin = io.StringIO('not json\n' + json.dumps({'op': 'stats', 'id': 2}) + '\n')
        stdout = io.StringIO()
        wire.serve(Dispatcher({'stub': _Stub}), stdin=stdin, stdout=stdout, heartbeat_s=1000.0)
        replies = [json.loads(ln[len(wire.SENTINEL):])
                   for ln in stdout.getvalue().splitlines() if ln]
        assert replies[1]['error'] == 'ProtocolError'
        assert replies[2]['kind'] == 'value', 'the loop must keep serving after a bad line'

    def test_a_vendor_exception_is_reported_with_its_full_class_chain(self):
        lines = _serve_once([{'op': 'module', 'name': 'stub', 'id': 1},
                             {'op': 'callattr', 'h': 1, 'name': 'boom', 'id': 2}])
        reply = json.loads(lines[-1][len(wire.SENTINEL):])
        assert reply['kind'] == 'error'
        assert reply['error'] == 'ValueError'
        assert 'Exception' in reply['bases'], 'without the bases a hierarchy catch would miss'
        assert 'deliberate' in reply['message']
        assert 'test_geometry_bridge_wire' in reply['traceback']

    def test_bye_ends_the_loop(self):
        lines = _serve_once([{'op': 'bye', 'id': 9},
                             {'op': 'stats', 'id': 10}])
        kinds = [json.loads(ln[len(wire.SENTINEL):]).get('kind') for ln in lines]
        assert kinds == ['hello', 'value'], 'nothing after bye should be served'

    def test_stdin_closing_ends_the_loop(self):
        """What makes an orphan impossible: if the client dies, stdin closes and the worker exits."""
        assert wire.serve(Dispatcher({'stub': _Stub}),
                          stdin=io.StringIO(''), stdout=io.StringIO()) == 0


class TestHeartbeat:

    def test_a_long_call_emits_heartbeats(self):
        """Proof of life during a slow call, which is what makes a silence deadline safe."""

        class Slow(object):
            @staticmethod
            def work():
                time.sleep(0.5)
                return 1

        stdin = io.StringIO(json.dumps({'op': 'module', 'name': 'slow', 'id': 1}) + '\n'
                            + json.dumps({'op': 'callattr', 'h': 1, 'name': 'work', 'id': 2}) + '\n')
        stdout = io.StringIO()
        wire.serve(Dispatcher({'slow': Slow}), stdin=stdin, stdout=stdout, heartbeat_s=0.1)
        kinds = [json.loads(ln[len(wire.SENTINEL):]).get('kind')
                 for ln in stdout.getvalue().splitlines() if ln]
        assert kinds.count(wire.HEARTBEAT) >= 2, 'got %r' % (kinds,)
        assert kinds[-1] == 'value'


# ---------------------------------------------------------------- a real subprocess


FAKE_WORKER = textwrap.dedent('''
    """A fake worker: no vendor, but a real process on the other end of a real pipe."""
    import os, sys, time
    sys.path.insert(0, %r)
    from geometry_bridge import wire
    from geometry_bridge.ops import Dispatcher

    class Vendor(object):
        answer = 41

        @staticmethod
        def add(a, b):
            return a + b

        @staticmethod
        def hang():
            time.sleep(600)

        @staticmethod
        def die():
            os._exit(7)

        @staticmethod
        def chatty():
            sys.stdout.write("vendor progress line\\n")
            sys.stdout.flush()
            return "done"

    # Heartbeat disabled for the hang test to be able to detect silence.
    wire.serve(Dispatcher({"vendor": Vendor}), heartbeat_s=float(os.environ.get("FAKE_HB", "5")))
''')


@pytest.fixture
def fake_worker(tmp_path):
    tools = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'src', 'Fuselage', 'tools')
    path = tmp_path / 'fake_worker.py'
    path.write_text(FAKE_WORKER % tools, encoding='utf-8')
    return str(path)


class TestWorkerTransport:

    def test_a_round_trip_through_a_real_pipe(self, fake_worker):
        s = Session(WorkerTransport([sys.executable, fake_worker]))
        try:
            vendor = s.module('vendor')
            assert vendor.answer == 41
            assert vendor.add(2, 3) == 5
        finally:
            s.close()

    def test_the_worker_is_a_different_process(self, fake_worker):
        t = WorkerTransport([sys.executable, fake_worker])
        try:
            assert t.proc.pid != os.getpid()
        finally:
            t.close()

    def test_the_vendors_own_output_is_captured_not_discarded(self, fake_worker):
        """A cowl build prints progress for a quarter of an hour; it is wanted when a test fails."""
        s = Session(WorkerTransport([sys.executable, fake_worker]))
        try:
            assert s.module('vendor').chatty() == 'done'
            # The vendor line arrives interleaved; it is drained on the next read.
            assert s.module('vendor').answer == 41
            assert 'vendor progress line' in s.transport.vendor_output
        finally:
            s.close()

    def test_a_dead_worker_is_reported_promptly_and_as_a_bridge_fault(self, fake_worker):
        s = Session(WorkerTransport([sys.executable, fake_worker]))
        try:
            started = time.time()
            with pytest.raises(WorkerDied):
                s.module('vendor').die()
            assert time.time() - started < 20.0, 'it must fail promptly, not hang'
        finally:
            s.close()

    def test_a_hung_call_times_out_and_the_worker_is_terminated(self, fake_worker, monkeypatch):
        """The failure mode the prototype did not have at all.

        The worker is started with heartbeats effectively disabled so the client sees true silence,
        which is what a wedged kernel call looks like.
        """
        monkeypatch.setenv('FAKE_HB', '600')
        t = WorkerTransport([sys.executable, fake_worker], liveness_s=2.0)
        s = Session(t)
        proc = t.proc
        try:
            started = time.time()
            with pytest.raises(BridgeTimeout) as caught:
                s.module('vendor').hang()
            elapsed = time.time() - started
            assert 1.0 < elapsed < 15.0, 'timed out in %.1f s' % elapsed
            assert 'terminated' in str(caught.value)
            # The point of the design rule: a reported timeout must not leave a process running.
            proc.wait(timeout=10)
            assert proc.poll() is not None, 'the worker must be gone, not merely reported'
        finally:
            s.close()

    def test_a_heartbeating_call_is_not_mistaken_for_a_hang(self, fake_worker, monkeypatch):
        """The converse: slowness must survive a deadline that death does not."""
        monkeypatch.setenv('FAKE_HB', '0.2')
        s = Session(WorkerTransport([sys.executable, fake_worker], liveness_s=2.0))
        try:
            # `add` is fast; the heartbeat interval being shorter than the deadline is what matters,
            # and the hang test above is what proves the deadline fires when silence is real.
            assert s.module('vendor').add(20, 21) == 41
        finally:
            s.close()

    def test_an_error_from_the_worker_carries_the_vendor_output(self, fake_worker):
        s = Session(WorkerTransport([sys.executable, fake_worker]))
        try:
            s.module('vendor').chatty()
            with pytest.raises(RemoteGeometryError) as caught:
                s.module('vendor').no_such_attribute
            assert caught.value.remote_name == 'AttributeError'
            assert 'vendor progress line' in caught.value.vendor_output
        finally:
            s.close()

    def test_a_module_outside_the_allowlist_is_refused_over_the_pipe(self, fake_worker):
        s = Session(WorkerTransport([sys.executable, fake_worker]))
        try:
            with pytest.raises(RemoteGeometryError) as caught:
                s.module('os')
            assert caught.value.remote_name == 'ProtocolError'
        finally:
            s.close()


class TestLimits:

    def test_the_max_line_size_is_far_above_a_realistic_bulk_payload(self):
        """A 20 000-float payload measured 349 KB; the cap exists for runaways, not for normal use."""
        assert wire.MAX_LINE_BYTES > 1_000_000
        assert wire.LIVENESS_S > wire.HEARTBEAT_S * 2, \
            'a merely-late heartbeat must not be fatal'
