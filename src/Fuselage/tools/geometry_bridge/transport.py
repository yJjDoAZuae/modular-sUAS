"""Transports. Three of them, behind one interface, and the third is why the library is testable.

``LoopbackTransport``
    Runs the dispatcher in this process against whatever object graph it is given. No vendor, no
    subprocess, no pipe. This is what puts the codec, the lifetime rules, the watermark, the cache
    policy, the paging and the error synthesis in the project's ordinary pytest tier.

``WorkerTransport``
    A subprocess under the vendor's interpreter, spoken to in JSON lines. Added in IP-GB-6.

``LocalTransport``
    Plain in-process imports, for a vendor whose build matches this interpreter -- OpenVSP today.
    Added in IP-GB-15.

A transport's only job is ``request(payload) -> reply`` plus teardown. Everything about proxies,
handles and errors lives above it, so a new transport cannot change semantics.
"""
from .errors import ProtocolError, raise_remote
from .ops import Dispatcher


class Transport(object):
    """The interface every transport satisfies."""

    #: Round trips performed, for the performance-budget tests.
    round_trips = 0

    def request(self, payload):
        raise NotImplementedError

    def close(self):
        pass

    @property
    def vendor_output(self):
        """Whatever the vendor printed on its own account, most recent last. Empty if none."""
        return ''


class LoopbackTransport(Transport):
    """The dispatcher, in this process, with no vendor and no pipe.

    Takes the same `modules` mapping the real worker would, so a test can supply stubs that model
    the shapes of vendor behavior that matter -- a dynamic-property object, a mapping-valued
    attribute, an object with no ``len`` -- without needing FreeCAD to produce them.
    """

    def __init__(self, modules, is_dynamic=None, max_items=None):
        self.dispatcher = Dispatcher(modules, is_dynamic=is_dynamic, max_items=max_items)
        self.round_trips = 0
        self.python = 'in-process'

    def request(self, payload):
        __tracebackhide__ = True
        self.round_trips += 1
        try:
            return self.dispatcher.handle(payload)
        except BaseException as exc:                                     # noqa: BLE001
            # Re-raised through the same synthesis path the pipe transport uses, so a test cannot
            # pass under loopback and fail against a real worker because the error arrived as a
            # different class.
            raise_remote(type(exc).__name__, str(exc),
                         [c.__name__ for c in type(exc).__mro__], '')

    def stats(self):
        return self.dispatcher.handle({'op': 'stats'})['value']


class LocalTransport(LoopbackTransport):
    """The same protocol over real in-process imports, for a vendor built for this interpreter.

    OpenVSP is this case today -- its extension is built for the project's 3.13, so no subprocess is
    needed. It is deliberately the *same* code path as the worker, proxies and all, rather than a
    shortcut that hands back raw objects: a test written against the bridge must behave identically
    whichever side of a boundary its library is on, and the day a vendor changes its build the switch
    is one line with no test changes.

    `modules` maps the name a test will ask for to the importable module name.
    """

    def __init__(self, modules, is_dynamic=None, max_items=None):
        import importlib
        resolved = {}
        missing = []
        for exposed, module_name in dict(modules).items():
            try:
                resolved[exposed] = importlib.import_module(module_name)
            except ImportError:
                missing.append(module_name)
        super().__init__(resolved, is_dynamic=is_dynamic, max_items=max_items)
        #: Names that could not be imported. Reported rather than raised, so one absent vendor does
        #: not stop every unrelated test, the same reasoning the worker uses.
        self.missing = missing
        self.python = 'in-process'


def check_reply(reply):
    """A reply must be a dict with a known `kind`. Guards against a truncated or stray line."""
    if not isinstance(reply, dict) or 'kind' not in reply:
        raise ProtocolError('malformed reply: %r' % (reply,))
    return reply


class WorkerTransport(Transport):
    """A vendor in its own interpreter, spoken to over a pipe.

    Three things here are not incidental:

    **A reader thread, not ``select``.** Windows pipes do not support ``select``, so lines are read
    on a thread into a queue the client polls with a timeout. That is also what makes the vendor's
    own output available for diagnostics without ever blocking on it.

    **The deadline is on silence, not duration.** The worker heartbeats while a call is in flight, so
    a 990 s build needs no configuration and a wedged kernel call is caught within one interval.

    **A timeout terminates the worker before raising.** A reported timeout that leaves the process
    running is how this project once left a `freecadcmd` holding a core for three hours and
    forty-eight minutes. The error is raised only after the process is gone.
    """

    def __init__(self, argv, liveness_s=None, vendor_log_lines=200):
        import collections
        import queue
        import subprocess
        import threading

        from . import wire

        self._wire = wire
        self._queue = queue.Queue()
        self._liveness_s = liveness_s if liveness_s is not None else wire.LIVENESS_S
        self._vendor_log = collections.deque(maxlen=vendor_log_lines)
        self.round_trips = 0
        self.wall = 0.0
        self._id = 0
        self._closed = False

        self.proc = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            # Explicit, never the environment's: the locale codec turned a probe's "naive" with a
            # diaeresis into "na?ve" on this machine.
            encoding='utf-8', errors='replace', bufsize=1)
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        hello = self._await_reply(None)
        self.label = hello.get('label', 'geometry')
        self.python = hello.get('python')

    # -- the reader thread

    def _pump(self):
        try:
            for line in self.proc.stdout:
                if line.startswith(self._wire.SENTINEL):
                    self._queue.put(('reply', line[len(self._wire.SENTINEL):]))
                else:
                    self._queue.put(('vendor', line.rstrip('\n')))
        except Exception:                                                # noqa: BLE001
            pass
        finally:
            self._queue.put(('eof', None))

    def _await_reply(self, want_id):
        """Wait for the next reply, treating a heartbeat as proof of life and resetting the clock."""
        import json
        import queue as _queue

        from .errors import BridgeTimeout, ProtocolError, WorkerDied

        while True:
            try:
                kind, payload = self._queue.get(timeout=self._liveness_s)
            except _queue.Empty:
                self._terminate()
                raise BridgeTimeout(
                    'no sign of life from the %s worker for %.0f s; it was terminated'
                    % (getattr(self, 'label', 'geometry'), self._liveness_s))
            if kind == 'eof':
                raise WorkerDied('the %s worker closed its output; it died mid-call'
                                 % getattr(self, 'label', 'geometry'))
            if kind == 'vendor':
                self._vendor_log.append(payload)
                continue
            if len(payload) > self._wire.MAX_LINE_BYTES:
                raise ProtocolError('reply exceeded %d bytes' % self._wire.MAX_LINE_BYTES)
            reply = json.loads(payload)
            if reply.get('kind') == self._wire.HEARTBEAT:
                continue                         # alive but still working; the clock restarts
            if want_id is not None and reply.get('id') not in (None, want_id):
                continue                         # a stale reply from an abandoned call
            return reply

    # -- the interface

    def request(self, payload):
        __tracebackhide__ = True
        import json
        import time

        from .errors import BridgeError, raise_remote

        if self._closed:
            raise BridgeError('the %s worker is closed' % getattr(self, 'label', 'geometry'))
        self._id += 1
        payload['id'] = self._id
        started = time.time()
        try:
            self.proc.stdin.write(json.dumps(payload) + '\n')
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            from .errors import WorkerDied
            raise WorkerDied('could not reach the worker: %s' % exc)
        reply = self._await_reply(self._id)
        self.wall += time.time() - started
        self.round_trips += 1
        if reply.get('kind') == 'error':
            raise_remote(reply.get('error'), reply.get('message'), reply.get('bases', []),
                         reply.get('traceback', ''), self.vendor_output)
        return check_reply(reply)

    @property
    def vendor_output(self):
        return '\n'.join(self._vendor_log)

    def _shut_pipes(self):
        """Close both pipes, ignoring failures.

        Needed explicitly: after the worker dies, the stdin wrapper's own destructor tries to flush
        into a broken pipe and raises an unraisable ``OSError``, which surfaces as a test warning
        with no owner. Closing deliberately here keeps that out of the suite.
        """
        for stream in (self.proc.stdin, self.proc.stdout):
            try:
                if stream is not None:
                    stream.close()
            except Exception:                                            # noqa: BLE001
                pass

    def _terminate(self):
        try:
            self.proc.kill()
        except Exception:                                                # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:                                                # noqa: BLE001
            pass
        self._shut_pipes()
        self._closed = True

    def close(self):
        if self._closed:
            self._shut_pipes()
            return
        try:
            self.proc.stdin.write('{"op": "bye"}\n')
            self.proc.stdin.flush()
            self.proc.wait(timeout=20)
            self._shut_pipes()
        except Exception:                                                # noqa: BLE001
            self._terminate()
        finally:
            self._closed = True
