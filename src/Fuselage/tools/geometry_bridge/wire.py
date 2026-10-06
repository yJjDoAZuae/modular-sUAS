"""The line protocol, and the heartbeat that distinguishes a slow call from a dead one.

Vendor-free on purpose: the framing, the heartbeat and the serve loop are exercised in the project's
ordinary pytest tier against ordinary file objects, with no FreeCAD and no subprocess.

**Framing.** One JSON object per line. Every reply carries :data:`SENTINEL` as a prefix, because the
vendor writes freely to the same stream -- a cowl build prints progress for a quarter of an hour --
so the client cannot assume a clean channel. A non-sentinel line is the vendor's own output and is
kept for diagnostics rather than discarded.

**Encoding is explicit UTF-8.** Left to the environment it became the locale codec on Windows, which
turned a probe's ``naïve`` into ``na?ve``.

**Heartbeat.** A fixed per-call timeout cannot work here: a legitimate cowl build takes about 990 s
and must not be mistaken for a hang, while a wedged kernel call -- this project has measured a
``solid.common`` that did not finish in nine minutes -- must be caught. So the worker emits a
heartbeat while a call is in flight and the client's deadline is on *silence*, not on duration. A
990 s build needs no per-call configuration, and a wedged call is caught within one interval.

Writes are serialized under a lock: the heartbeat thread and the reply both emit whole lines, and
without the lock they could interleave inside one line.
"""
import json
import sys
import threading
import traceback

#: Prefix marking a line as ours rather than the vendor's.
SENTINEL = '##GBW##'

#: Emitted while a call is in flight, so silence means death rather than slowness.
HEARTBEAT = 'heartbeat'

#: Seconds between heartbeats. Short enough that a wedged call is caught promptly, long enough that
#: a long build does not fill the pipe with them.
HEARTBEAT_S = 5.0

#: How long the client waits for *any* line before declaring the worker dead. A multiple of the
#: heartbeat interval, so an ordinarily-scheduled heartbeat that is merely late is not fatal.
LIVENESS_S = 30.0

#: Largest line the client will accept. Far above ordinary use -- a 20 000-float bulk payload
#: measured 349 KB -- so this turns a runaway reply into a named error rather than an allocation
#: failure.
MAX_LINE_BYTES = 8 * 1024 * 1024


class LineWriter(object):
    """Serializes whole lines to a stream from more than one thread."""

    def __init__(self, stream):
        self._stream = stream
        self._lock = threading.Lock()

    def send(self, payload):
        text = SENTINEL + json.dumps(payload) + '\n'
        with self._lock:
            self._stream.write(text)
            self._stream.flush()


class _Heartbeat(object):
    """Emits a heartbeat line while a call is in flight."""

    def __init__(self, writer, interval=HEARTBEAT_S):
        self.writer = writer
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 1.0)
        return False

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.writer.send({'kind': HEARTBEAT})
            except Exception:                                            # noqa: BLE001
                return


def serve(dispatcher, stdin=None, stdout=None, heartbeat_s=HEARTBEAT_S, label='geometry'):
    """Read requests, execute them, write replies. Returns when stdin closes or `bye` arrives.

    Reading from stdin is also what makes an orphan impossible: if the client goes away, including
    by being killed, stdin closes and this returns.
    """
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    writer = LineWriter(stdout)
    writer.send({'kind': 'hello', 'label': label,
                 'python': '%d.%d.%d' % sys.version_info[:3]})
    while True:
        line = stdin.readline()
        if not line:
            return 0
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError as exc:
            writer.send({'kind': 'error', 'error': 'ProtocolError',
                         'bases': ['ProtocolError', 'Exception'],
                         'message': 'malformed request line: %s' % exc})
            continue
        if req.get('rel'):
            dispatcher.registry.release(req['rel'])
        if req.get('op') == 'bye':
            writer.send({'kind': 'value', 'value': True, 'id': req.get('id')})
            return 0
        try:
            with _Heartbeat(writer, heartbeat_s):
                reply = dispatcher.handle(req)
            reply['id'] = req.get('id')
            writer.send(reply)
        except BaseException as exc:                                     # noqa: BLE001
            # The class chain, not just the name: the client cannot import these classes -- that
            # import is what the boundary exists to avoid -- so it rebuilds them from these names,
            # and without the bases a hierarchy catch in a test would silently miss.
            writer.send({'kind': 'error', 'id': req.get('id'),
                         'error': type(exc).__name__,
                         'bases': [c.__name__ for c in type(exc).__mro__],
                         'message': str(exc)[:4000],
                         'traceback': traceback.format_exc()})
