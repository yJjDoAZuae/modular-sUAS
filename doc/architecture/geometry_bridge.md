# Geometry Bridge — Architecture

**Scope.** The design of an adaptation library that lets `pytest`, running under the project's own
Python interpreter, drive FreeCAD and OpenVSP — libraries whose binary extensions are built for
different, vendor-chosen CPython versions. It covers the process boundary, the object model that
crosses it, handle lifetime, error propagation, the hazards each of those creates, and how the
library itself is verified. It does not cover which geometry tests get written; that is the
business of the design documents those tests check.

**Status.** Written 2026-10-06, resolving
[OQ-ARCH-22](freecad_migration.md#oq-arch-22-how-does-the-pytest-tier-reach-freecad-decided-2026-10-06-alternative-7)
in favor of its alternative 7. A throwaway prototype of every mechanism below was built and measured first;
every number in this document was taken on this machine, and the measurements that contradicted
the first draft of the design are called out where they did.

**Why this exists.** The project selects its own Python version on its own merits. FreeCAD 1.1.3
embeds CPython 3.11 and OpenVSP's extension is built for 3.13; both are vendor build choices,
each revisable at any release, and the two already disagree. Matching either breaks the other and
hands the project's interpreter choice to a CAD vendor. A process boundary is what makes the
choice the project's own. The full measurement of the version lock, and the five alternatives
rejected, are in OQ-ARCH-22 and are not repeated here.

---

## 1. What was measured before designing

A prototype carried every mechanism in this document. It is scratch and is not the proposed
implementation, but it is the evidence base.

| Measurement | Result |
| --- | --- |
| Geometry cases driven from the 3.13 venv against FreeCAD's 3.11 | 34 passed |
| Worker startup, once per session | 0.55–0.94 s |
| Round trip, handle operation | **0.4–0.9 ms** |
| Round trip, evaluating a source snippet | 8.8 ms |
| One build reused across 19 assertions | build ran exactly once, asserted before and after |
| Reuse against rebuilding, on a 5 ms shape | **16.2× cheaper** |
| 200 temporaries in a loop | nothing left behind |
| A chain of three booleans | exactly one live handle, freed when dropped |
| 100 bool-returning method calls | zero handles allocated |
| 20 warm method calls | 20 round trips — one each |
| A 45 s single call, client blocked on the read | survived |
| A worker killed mid-call | reported in **0.01 s**, not a hang |
| A real kernel refusal | arrived as `CADKernelError: makeOffset2D: offset result has no wires.` |
| A remote traceback | named the remote file, function and line |

Two findings from that work are load-bearing for the whole design:

**A handle operation is an order of magnitude cheaper than evaluating source.** 0.9 ms against
8.8 ms, because a handle operation compiles nothing. The variant that reads as ordinary Python is
also the faster one, so there is no trade to make between expressiveness and speed.

**The expensive thing is a build, and a build is paid once.** The whole efficiency question turns
on whether an object can be reused across assertions, not on per-call latency. It can: a `Shape`
cannot be *serialized* across the boundary, but it does not have to be, and nothing rebuilds it.
A 990 s cowl build amortizes over an entire session.

---

## 2. Hazards found by probing, and the rule each one sets

Twelve probes were run against the prototype specifically to find problems the open question had
not raised. Five were real gaps, two crashed the prototype outright, and three confirmed
behaviors the design can now rely on. **The design rules in this document come from these
results, not from expectation.**

| # | Probe | Result | Rule it sets |
| --- | --- | --- | --- |
| 1 | Float round trip at project tolerances | **Exact**, including `1e-13`, `2.225e-308` and `1+1e-15` | §4.4 may encode floats as JSON numbers; §7 pins it with a test |
| 2 | Non-finite floats | `inf`, `-inf`, `nan` all survive | §4.3: the wire is *Python* JSON, not interoperable JSON |
| 3 | `box.Length = 12.0` | **AttributeError. Assignment is impossible** | §4.3 requires a `setattr` op |
| 4 | `v1 + v2`, `v * 2` | **TypeError. Operators do not forward** | §4.3 requires an explicit dunder allowlist |
| 5 | `for f in shape.Faces` | Worked, but **7 round trips for 6 faces** | §4.3 binds `__iter__` to a bulk op |
| 6 | Two `App::FeaturePython` objects | **Both report type `FeaturePython`** | §4.5: the callable cache is unsafe for dynamic types; the worker decides what may be cached |
| 7 | Released-handle bookkeeping | **Grew 30 → 336 for 300 temporaries, unbounded** | §4.6 replaces the set with a watermark |
| 8 | The blocking read | **No deadline at all** | §4.7 requires a liveness deadline and a worker heartbeat |
| 9 | `bool(shape)` | **TypeError** — `__bool__` fell through to `__len__`, and a `Solid` has no `len` | §4.3 defines `__bool__` explicitly |
| 10 | Non-ASCII through an error message | `naïve` came back as `na?ve` | §4.2 sets the transport encoding explicitly |
| 11 | Reading 8 vertices' coordinates | **33 round trips, 4.1 per vertex** | §4.8 requires a projection op |
| 12 | A realistic bulk payload | 349 KB for 20 000 floats | §4.2 sets a maximum line size and a paging rule |

Probe 9 deserves naming, because it is the kind of defect that only appears in use. Defining
`__len__` on a proxy silently hijacks truthiness for every object: Python falls back to `__len__`
when `__bool__` is absent, so `if shape:` became `len(shape)` and raised `TypeError` on a `Solid`.
A proxy must define `__bool__` itself.

Probe 11 is the one that would have embarrassed the library in use. Reading three coordinates from
each of eight vertices cost 33 round trips. At 0.9 ms each that is invisible for eight vertices
and ruinous for the 3840-sample convergence sweeps this project actually runs
([cowl_interior_surface.md](../design/cowl_interior_surface.md) §6.1). Per-element proxying is
correct and unusably slow; §4.8 exists because of this number.

---

## 3. Components

```text
      project interpreter (the project's own choice)        vendor interpreter
      ----------------------------------------------        ------------------
  pytest
    |
    +-- geometry_bridge.api          typed facades, fixtures
    +-- geometry_bridge.proxy        Remote, RemoteMethod, operators
    +-- geometry_bridge.lifetime     reference counting, release batching
    +-- geometry_bridge.errors       synthesized remote exception classes
    +-- geometry_bridge.codec        value/handle encoding, type mapping
    +-- geometry_bridge.transport ------------ pipe ----------->  worker.serve
            |                                                      |
            +-- WorkerTransport   (subprocess + reader thread)      +-- registry
            +-- LoopbackTransport (in-process, for the library's     +-- codec
            |                      own tests -- no vendor needed)    +-- ops
            +-- LocalTransport    (plain imports, when the vendor
                                   build matches our interpreter)
```

Three transports behind one interface, and the third is not a nicety:

- **`WorkerTransport`** — FreeCAD today. A subprocess under the vendor's interpreter.
- **`LocalTransport`** — OpenVSP today, whose extension already matches the project's 3.13. The
  same API over plain imports, so **a test is written once and does not know which side of a
  boundary its library is on.** The day either vendor moves is a one-line change.
- **`LoopbackTransport`** — the library's own tests. See §7: without it, the library that exists
  to enable the fast test tier would itself be testable only in the slow one.

---

## 4. The design

### 4.1 One principle

**A reference crosses the boundary; an object never does.** Every rule below follows from it.
`a.cut(b)` sends two handles and receives a third; the solids stay in the worker for the whole
chain and only the final measurement is serialized.

### 4.2 Transport

One JSON object per line, each direction, over the worker's stdin and stdout.

- **Encoding is explicit: `utf-8`, errors strict.** Probe 10 returned `na?ve` for `naïve` because
  the prototype used `universal_newlines=True` and inherited the locale codec, cp1252 on this
  machine. The encoding is never left to the environment. A separate caution: a vendor's own
  error text may already be lossy before the bridge sees it, so round-trip fidelity is asserted on
  the bridge's own payloads, not on FreeCAD's message strings.
- **Responses carry a sentinel prefix.** The vendor writes freely to the same stream — a cowl
  build prints progress for a quarter of an hour — so the client cannot assume a clean channel.
  Non-sentinel lines are **drained into a bounded ring buffer and attached to the next error**,
  rather than discarded; a build's own progress output is the first thing wanted when a geometry
  test fails.
- **Maximum line size is bounded** (proposed 8 MiB). Probe 12 put a realistic bulk payload at
  349 KB for 20 000 floats, so the limit is far above ordinary use and exists to turn a runaway
  response into a named error rather than an allocation failure. Bulk ops that would exceed it
  page with a cursor (§4.8).
- **The wire format is Python JSON, not interoperable JSON.** Probe 2 confirmed `inf` and `nan`
  cross intact, which standard JSON does not permit. This is acceptable because both ends are
  CPython, and is recorded because it constrains any future change of transport.
- **No code-evaluation op.** The prototype had one, and it is deliberately absent here: it is an
  arbitrary-code-execution surface, and it is what forced geometry into strings where no editor
  or type checker could see it. A debug-only variant may exist behind an explicitly-enabled flag,
  off by default, and never used by a committed test.

### 4.3 The object model

| Op | Purpose |
| --- | --- |
| `module` | a handle to a named, allowlisted module |
| `getattr` | an attribute: a value, or a handle, or "callable" |
| `setattr` | **assignment** — required, probe 3 |
| `callattr` | attribute lookup and call in one step; allocates no handle for the method |
| `call` | call a handle that is itself callable |
| `getitem` / `setitem` | subscript, key passed through unchanged |
| `len` | `len()` |
| `iterate` | `list(iter(obj))`, encoded in one response |
| `project` | the bulk read of §4.8 |
| `batch` | several ops in one round trip |
| `release` | drop handles |
| `reset` | vendor state hygiene (§5.2) |
| `stats` | counters, for leak observability |

**Assignment is a first-class operation.** Probe 3 found the prototype could not do it at all, and
`__slots__` on the proxy turned every assignment into a client-side `AttributeError` that looked
like a missing attribute rather than a missing feature. This is not an edge case: the project's
FreeCAD code is parametric-document driven, and
[check_cowl_interior.py](../../src/Fuselage/freecad/check_cowl_interior.py) sets
`tip.ClearanceCheck = True` to drive a build. Without `setattr` the library cannot run the
project's existing checks.

**Operators forward from an explicit allowlist**, not from a catch-all. Probe 4 found `v1 + v2`
and `v * 2` both raise `TypeError`, because the proxy's dunder guard blocks them. The allowlist is
arithmetic (`add`, `radd`, `sub`, `rsub`, `mul`, `rmul`, `truediv`, `neg`, `abs`), comparison
(`eq`, `ne`, `lt`, `le`, `gt`, `ge`), and container protocol (`getitem`, `setitem`, `contains`,
`len`, `iter`). It is an allowlist rather than a general forward because the probes showed `copy`,
`pickle` and pytest itself all speculatively look for dunders, and a round trip per probe is both
slow and wrong.

**Three semantics are decided explicitly rather than inherited:**

- **`__bool__` returns `True` unconditionally.** A proxy references a real object, so the useful
  reading of `if shape:` is "is not None". Probe 9 showed the alternative — falling through to
  `__len__` — raises `TypeError` on any object without a length. Remote truthiness, when actually
  wanted, is an explicit call.
- **`__eq__` forwards to the remote comparison, and `__hash__` is therefore undefined.** Python
  makes a type with `__eq__` and no `__hash__` unhashable, which is the correct default here: two
  proxies for the same remote object hold different handle ids, so hashing by id would be wrong,
  and hashing by remote identity would cost a round trip inside `dict.__setitem__`. A proxy is not
  a dict key; an explicit remote identity accessor exists for code that needs one.
- **`__getitem__` passes the key through unchanged.** The prototype assumed an integer index and
  crashed on `App.listDocuments()`, which returns a *mapping*: the client sent index `0` and the
  worker raised `KeyError: 0`. Sequence and mapping are not distinguished by the bridge at all;
  the subscript is forwarded and the vendor object decides.
- **`__iter__` uses `iterate`, not repeated `__getitem__`.** Probe 5 measured 7 round trips for 6
  faces under the fallback. `iterate` also gets mapping iteration right for free, since it
  delegates to the object's own iterator.

**The type mapping is documented and partly lossy.** Scalars, and lists and dicts of scalars,
cross as values; everything else becomes a handle. Two consequences are recorded rather than
fixed: a `tuple` of scalars arrives as a `list`, and a deeply nested structure beyond a bounded
depth becomes a handle instead of a value. Tests that care about either use handles explicitly.

### 4.4 Numeric fidelity

Probe 1 is the reason this is a section rather than an assumption. This project asserts a
construction identity at **~1e-13 mm** ([freecad_migration.md](freecad_migration.md), IP-FC-143)
and a wall tolerance at 0.01 mm. A transport that rounded in the twelfth digit would manufacture
error indistinguishable from a geometry defect.

Measured: every probe value round-tripped **bit-exactly**, including `1e-13`, `1.0 + 1e-15`, a
subnormal at `2.2250738585072014e-308`, and `1.7976931348623157e308`. CPython's `repr` is
round-trip exact and `json` uses it. §7 pins this with a test rather than leaving it to a comment,
because it is a property of the transport that a future change could silently break.

### 4.5 The callable cache, and why the worker decides

A method call would otherwise cost two round trips: one to discover the attribute is callable,
one to call it. The client caches callability so a warm call is a single trip — measured 20 trips
for 20 calls.

Probe 6 found the obvious cache key is unsound. Two `App::FeaturePython` objects **both report
remote type `FeaturePython`**, and FreeCAD document objects gain properties at run time, so two
objects sharing a reported type can disagree about whether a name is even present. A per-type
cache is therefore shared between objects whose attribute sets differ.

**The worker decides what may be cached.** Each `getattr` response carries a `cacheable` flag,
set from the object's own type: static vendor types (shapes, vectors, modules) may be cached;
anything carrying dynamic properties may not. The client never infers cacheability itself. This
keeps the fast path for the types that dominate geometry code and is simply correct for the
document objects where it would have been wrong.

### 4.6 Handle lifetime

Lifetime is the library's responsibility. A test author writes ordinary geometry code, releases
nothing, and the worker's memory does not grow.

1. **Distributed reference counting.** The proxy's `__del__` queues its handle for release, which
   CPython's reference counting makes prompt in the ordinary non-cyclic case. Measured: 200
   temporaries leave nothing behind; a chain of three booleans leaves exactly one live handle, the
   result, freed in turn when dropped.
2. **Releases ride along.** The pending list is attached to the next request, so reclaiming costs
   no round trip of its own. A threshold flush covers a session that has gone quiet.
3. **A method call allocates nothing.** `callattr` does the lookup and the call worker-side, so no
   handle is created for a bound method — otherwise one per call site, the largest source of
   growth. Measured: 100 bool-returning calls allocated zero handles.
4. **`__del__` only appends.** It never performs I/O, which during interpreter teardown would
   deadlock or raise against half-finalized modules.
5. **Stale is distinguished from unknown by a watermark, not by a set.** The prototype remembered
   every released id forever so it could tell the two apart — probe 7 measured that set growing
   to 336 entries for 300 temporaries, unbounded, which is the same leak one level down. Handle
   ids are monotonic, so the rule needs no per-id storage: an id in the registry is **live**; an
   id not in the registry and not greater than the highest ever issued is **released**; anything
   greater is **unknown**.
6. **Use-after-free is named.** A released handle raises `StaleHandle` identifying the handle,
   never a bare `KeyError` from inside unrelated work — which would read as a geometry fault and
   send someone hunting a defect that does not exist.
7. **Leaks are observable.** The worker reports live, high-water and released counts, and the
   library offers an explicit no-leak assertion so the invariant is pinned in CI rather than
   trusted.

**The defect this design invites, recorded because it was found the hard way.** The prototype's
bound-method object held the owner's handle *id* rather than a reference to the owner proxy. In
`a.cut(b).cut(c)` the first result is never named, so once `.cut` had produced a method object the
only thing referring to that shape was an integer: the proxy was collected, its release was
queued, and the very request carrying that release used the handle. A **live object was freed** —
worse than a leak, because a leak wastes memory while this corrupts a result. The rule is *alive
while reachable*, not *alive while named*: anything holding a handle holds a reference to the
proxy that owns it. It was caught only by the test written for the converse, that a
still-referenced object must not be freed, which is the test this kind of library most needs and
is easiest to omit.

**The residual limit, measured 2026-10-06 (IP-GB-19).** Promptness relies on reference counting,
and reference counting does not see a cycle. A proxy reachable only through one is still held
after the last name for it is gone — confirmed, and **a single `gc.collect()` is the whole
remedy**: 40 cycles built in a loop stay held as a group and all 40 release together on the first
pass, with nothing lost. So the limit is a bounded delay, not growth, and bounding it needs no
tracking of its own. The converse is pinned too: a proxy *not* in a cycle needs no collector pass,
and neither does a chain intermediate — which matters because the bound-method defect this design
already fixed lived exactly there, and if an intermediate's lifetime depended on the collector,
every chain would hold handles until one happened to run. Tested in the loopback tier, since a
cycle is a property of the client's own object graph and involves no vendor.

### 4.7 Liveness: a hang is not a failure mode the prototype had

Probe 8 found the blocking read has **no deadline**. A dead worker is detected in 0.01 s because
the pipe closes, but a worker *stuck* in a long kernel call is not detected at all — and this
project has measured a `solid.common` that did not finish in **nine minutes** and a `makeOffset2D`
that did not finish in six. One of those was still running three hours and 48 minutes later,
holding a core, because a timeout was reported in prose and the process was never stopped. In CI
that is a hung job, not a failed test.

A fixed per-call timeout cannot work, because a legitimate cowl build takes about 990 s and must
not be mistaken for a hang. So the design separates slowness from death:

- **The worker runs a heartbeat.** A watchdog thread emits a heartbeat line at a fixed interval
  while a call is in flight.
- **The client's deadline is on liveness, not on duration.** It waits for *any* line — heartbeat
  or response — and fails only when nothing arrives for the interval. A 990 s build needs no
  per-call configuration; a wedged kernel call is caught within one interval.
- **A reader thread, not `select`.** Windows pipes do not support `select`, so the transport runs
  a reader thread feeding a queue the client reads with a timeout. This is also what makes the
  drained vendor output of §4.2 available without blocking.
- **A timeout stops the worker.** The named `BridgeTimeout` error is raised *after* the worker
  process is terminated, so a timeout can never leave an orphan holding a core. This is a
  requirement, not a nicety: the prose-timeout-and-walk-away failure above is precisely what it
  prevents.

### 4.8 Bulk reads

Probe 11 measured 33 round trips to read 8 vertices' coordinates — 4.1 per vertex. Correct, and
unusable at the sample counts this project works at.

- **`project`** takes a handle to a sequence and a list of attribute paths, and returns a table of
  values in one round trip: 8 vertices × 3 coordinates becomes one trip rather than 33.
- **`batch`** takes a list of unrelated ops and returns their results together, for the case where
  the reads are not a uniform projection.
- **Paging.** A projection whose response would exceed the §4.2 line limit returns a cursor, so a
  large result is bounded by request rather than by hope.

The guidance that follows from this is explicit in the library's documentation: a loop over
thousands of samples uses `project`, and a loop that reads attributes one at a time is a
performance defect, not a style preference.

### 4.9 Errors

The worker sends the exception's class **name, full base chain, message and traceback**; the
client rebuilds a matching class once and caches it, so the same remote type is the same client
class on every raise. Measured: a project precondition arrives as `PreconditionFailed` and
satisfies `pytest.raises(PreconditionFailed)`; the same failure is still caught by a hierarchy
catch; a kernel refusal arrives as the kernel's own `CADKernelError` with its own message; and a
remote `AttributeError` is catchable as a real `AttributeError`, because a remote builtin inherits
from the genuine builtin as well as from the remote base.

The base chain is sent, not just the name, because without it a hierarchy catch in a test would
silently miss. The known project exception names are pre-registered in an importable module, so a
test writes `from geometry_bridge.remote_errors import PreconditionFailed` and gets the same class
the bridge raises.

`__tracebackhide__` on the bridge frames keeps a failure report pointing at the test's own line,
with the worker's traceback carried on the exception and emitted in its string form.

**A bridge fault is a deliberately unrelated class.** A dead worker, a timeout or a protocol error
is never catchable as a geometry error, so a crashed worker cannot be mistaken for a geometry
finding. A synthesized class is not the worker's class object and cannot be, so a test takes its
identity from the library rather than by importing the vendor's.

### 4.10 The typed facade set

A proxy forwards attributes dynamically, so an editor cannot complete `shape.` and a type checker
cannot catch `shape.Volum`. Facades — hand-written classes with real signatures, delegating to the
proxy — recover that where it is used most, and are worth writing only if the set of types is
small. **Surveyed 2026-10-06** rather than assumed: FreeCAD was asked for the public member names
of each candidate class, every attribute access in the 101 modules under
`src/Fuselage/freecad` was counted, and the two were intersected. A member name belonging to
exactly one candidate type attributes a use unambiguously; the shared names are counted separately
so the ambiguity is visible.

| Type | Members | Used | Unambiguous uses | Most-used unambiguous members |
| --- | --- | --- | --- | --- |
| `DocumentObject` | 98 | 22 | **361** | `Shape` (193), `setExpression` (93), `Height` (19) |
| `Vector` | 23 | 13 | **317** | `x` (104), `y` (100), `z` (70), `normalize` (19) |
| `Document` | 109 | 15 | **241** | `addObject` (94), `getObject` (76), `Objects` (35) |
| `BoundBox` | 27 | 14 | **184** | `ZMin` (36), `ZMax` (31), `XMin` (27) |
| `Placement` | 16 | 6 | **139** | `Base` (103), `Rotation` (36) |
| `Vertex` | 142 | 51 | 51 | `Point` (25), `X` (13), `Y` (13) |
| `Face` | 163 | 55 | 42 | `Surface` (26), `Wire` (12), `OuterWire` (4) |
| `Edge` | 168 | 57 | 36 | `split` (29), `Curve` (3) |
| `Wire` | 153 | 53 | 2 | `approximate` (1), `OrderedEdges` (1) |
| `Shape`, `Solid` | 146 | 49 | **0** | — every member is shared |
| `Matrix` | 45 | 3 | 0 | — |

**The head is short: five types cover 90.5% of unambiguous uses, eight cover 99.9%.** That is the
condition the facade recommendation required, so facades are worth writing.

Two results changed which facades to write, and both contradict what this document's first draft
assumed.

**`Shape` and `Solid` have zero unambiguous uses.** Every member they expose is shared with
`Face`, `Edge`, `Wire` and `Vertex`, because all of them are `Part.Shape` subclasses over a common
API. A facade per shape subclass is therefore the wrong decomposition: there is **one `Shape`
facade** carrying the shared surface, plus the few genuinely distinct members —
`Face.Surface`/`OuterWire`, `Edge.split`/`Curve`, `Vertex.Point`/`X`/`Y`, `Wire.OrderedEdges`.

**The document side dominates, not the shape side.** The top three by unambiguous use are
`DocumentObject`, `Vector` and `Document`, and `setExpression` alone accounts for 93 uses. This
project's FreeCAD code is parametric-document driven, so the facades that earn their keep are the
document ones. That is the same conclusion probe 3 reached from the other direction when it found
assignment impossible, and it is why §4.3 makes `setattr` a first-class operation.

**The facade set, in build order:** `DocumentObject`, `Vector`, `Document`, `BoundBox`,
`Placement`, then one shared `Shape` with thin `Face`/`Edge`/`Vertex`/`Wire` extensions. Anything
outside the set falls back to the dynamic proxy, which is a deliberate unevenness: the fallback
always works, so an unfaceted type costs completion and nothing else.

**Limits of the method, stated because they bound the numbers.** It is static text scanning, so a
name reached through `getattr` or held in a variable is missed, and a name that is also an
ordinary local or a dict key inflates its type's count. No attempt is made to resolve which object
a given `.Volume` belongs to — that is exactly the shared-name ambiguity the unambiguous column
isolates. The ranking is robust to all three; the absolute counts are approximate.

#### What writing the facades changed, 2026-10-06

Three things only showed up once the facades were built against the live vendor, and each changed
the design rather than the implementation.

**A leaf type name does not identify a vendor object, so the protocol now carries the class
chain.** A `Part::Box` document object reports its type as `PrimitivePy`; `DocumentObject` is four
classes up its MRO (`PrimitivePy → Feature → GeoFeature → DocumentObject`). A facade lookup keyed
on the leaf name — which is what a handle reply carried until now — would have faceted every type
in the set **except `DocumentObject`**, the most-used of all at 361 uses, and would have done it
silently, because an unmatched type falls back to the working proxy and raises nothing. Each
handle reply now carries `bases`, the MRO names with `object` dropped and capped at twelve
(`ops.base_names`), and `facade_for` walks it leaf first. This is the same mechanism §4.9 already
uses to rebuild a remote exception's class, so the protocol gained no new idea, only a second
user. `Remote.remote_isinstance(*names)` is the client-side `isinstance` it also makes possible.

**`Vertex` has no `CenterOfMass`, and it is the only such member, so the facade hierarchy
branches.** Of every member the facades declare, exactly one is present on `Shape`, `Solid`,
`Face`, `Edge` and `Wire` but absent from `Vertex`. 137 members are common to all six. So
`ShapeCommon` carries what all six have, `Shape` adds `CenterOfMass` and `CenterOfGravity`, and
`Vertex` extends `ShapeCommon` directly rather than `Shape`. Found by checking all six type by
type; a flat hierarchy would have had `Vertex` advertising a member the vendor does not provide,
which is exactly the failure §5.6 calls worse than no facade — it type-checks, then raises.

**A member that returns a list arrives as a handle to the list, not as a list of handles.**
`shape.Faces` is a Python list of vendor objects, which cannot cross as a value, so the obvious
facade implementation — read the list and wrap each element — allocates a handle per face the
moment the attribute is touched. On a tail shell that is thousands of handles for a caller who
wanted `len()`. `wrap` therefore returns a `RemoteSequence`: `len`, indexing and iteration each
forward to the vendor and face what comes out, so nothing is read until it is asked for, and
`project` stays available on it for the bulk case.

**Measured while writing them: FreeCAD's docstrings carry real signatures for 31% of the methods
in the facade set, and for none of `Part.Shape`'s.** `Base.Vector`, `Base.BoundBox` and
`Base.Placement` document every method with a signature line (17 of 17); `Part.Shape`'s 35 methods
have none in the first line, though most carry one on the second. This is the measurement
[OQ-GB-1](#oq-gb-1--typed-facades-generated-stubs-or-neither--decided-2026-10-06-alternative-2)
named as the prerequisite for alternative 3 and recorded as unmeasured. It does not change the
decision — the signatures are in prose, not in a form a stub generator could trust, and the shape
side where the geometry work happens is the side with none — but it is no longer an expectation.

---

## 5. Hazards that are not about the protocol

### 5.1 A long-lived worker and the project's reproducibility criterion

The project requires that two builds of the same part be the same part, with thresholds fixed by
[OQ-ARCH-19](freecad_migration.md) and a sampling protocol still open under OQ-ARCH-21. Separately
recorded: a fresh build is bit-identical **except** near a degenerate configuration, where even
rankings and failure modes can differ between processes.

A session-scoped worker accumulates kernel and allocator state across every test that ran before.
That is exactly the condition under which the reproducibility floor says results may differ.

**Rule: a measurement that feeds a reproducibility claim runs in a fresh worker.** The library
provides both — a session worker for ordinary assertions, and a per-test fresh worker for
measurements whose value depends on process cleanliness. A test that compares two builds uses two
fresh workers, not one worker twice. This is a correctness rule about *what the number means*, not
a performance tuning knob, and it is the reason the worker lifecycle is part of the public API
rather than an implementation detail.

### 5.2 Vendor global state between tests

Both vendors keep process-global state that outlives a test:

- FreeCAD keeps an open-document list. A probe confirmed a document created in one call is still
  open in the next, which is cross-test contamination.
- OpenVSP keeps a single global model, cleared by its own `ClearVSPModel`.

**Rule: a `reset` op per vendor, run by an autouse fixture between tests.** The bridge owns this
rather than each test remembering, for the same reason it owns handle lifetime.

### 5.3 Worker memory, and when to restart

A worker holds every shape its handles reference, and this project has produced a single
measurement that reached **5 GB of RAM** on a degenerate configuration. A worker that only ever
grows is a hazard on a machine the user is working on.

**Rule: the worker reports its own resident size with `stats`, and the library restarts it when a
configurable ceiling or handle count is exceeded, between tests and never inside one.** A restart
invalidates every outstanding handle, so it is only safe at a test boundary, and a handle used
across a restart must raise `StaleHandle` rather than silently address a different object. Batch
work runs on the user's own machine; bounding it is a standing project rule, not a preference.

### 5.4 Parallel test execution

Under `pytest-xdist` each worker process gets its own bridge and its own vendor subprocess. The
library holds no module-global bridge, starts the subprocess lazily, and names nothing in a shared
location — no fixed port, no fixed temporary path — so N parallel pytest workers mean N
independent vendor workers. The cost is N startups and N vendor processes, which is a real
resource consideration on this machine and is why the ceiling in §5.3 is configurable.

### 5.5 Orphan processes

A worker must exit when its client goes away, including when the client is killed outright. It
reads from stdin, so a closed stdin ends its loop; that covers both a clean exit and a killed
parent. The library also terminates the worker on timeout (§4.7) and at session teardown. This
hazard is listed explicitly because an orphaned vendor process holding a core for hours has
already happened once in this project's history.

### 5.6 Editor and type-checker support

A proxy is dynamic, so an editor cannot complete `shape.` and a type checker cannot verify it.
This is a genuine regression against in-process imports and it is not fully solvable.

**Resolved by typed facades (OQ-GB-1, decided 2026-10-06).** The set is named in
[§4.10](#410-the-typed-facade-set), chosen from a survey rather than assumed, and is short because
five types carry 90.5% of unambiguous member use. Coverage is deliberately uneven: a type outside
the set keeps the dynamic proxy, which works but offers no completion. **The facades carry their
own hazard** — each is a second surface that can drift from the vendor API as FreeCAD changes, and
a facade that silently disagrees with the real object is worse than no facade, because it type-
checks and then fails at run time. §7 requires a test that every facade member actually exists on
the live vendor object, so drift is caught by the suite rather than by a confused reader.
**Written, 2026-10-06:** `tests/test_geometry_bridge_facades.py` checks every declared member of
all eleven facade classes against a live object of that type, and asserts the converse for the one
member the hierarchy branches on — that `Vertex` really does lack `CenterOfMass` on the vendor
object, not merely in the source.

---

## 6. What this design deliberately does not do

- **It does not let a client-side callable cross into the vendor.** Passing a Python function to a
  vendor API that would call back is unsupported; a test that needs it runs in the slow
  `check_*.py` tier.
- **It does not replace the `check_*.py` scripts.** A quarter-hour build whose job is to print a
  report is well served by a standalone script. The bridge is for the fast, named, asserted cases
  that have no home today. Both tiers stay — and where a *new* test goes is settled by OQ-GB-2:
  bridge-first, with a script only when the output is a report a person reads.
- **It does not make the vendor's own output structured.** Progress text is captured for
  diagnostics, not parsed.
- **It does not provide transactions or rollback.** A failed call may leave vendor state modified;
  §5.2's reset is what bounds the consequence.

### 6.1 What the existing check-script tier actually contains

Surveyed 2026-10-06, because the claim above — that both tiers stay — should rest on what the
scripts are rather than on an impression of them. There are **29 `check_*.py` scripts, 7,395
lines, and 45 explicit assertion sites** between them. They fall into three groups, and the groups
are not what a reader would guess:

| Group | Scripts | Lines | What it means |
| --- | --- | --- | --- |
| No FreeCAD import at all | **9** | 2,290 | Pure Python. Belongs in the venv `pytest` tier today, independent of this design |
| FreeCAD, but no document build | **1** | 146 | `check_solid_measure.py` — constructs shapes and measures them |
| Document-driven parametric build | **19** | 4,959 | Builds a document and recomputes it; reachable from the bridge only because §4.3 adds `setattr` |

**Three consequences.**

**The assertion density is about one per 164 lines.** 45 assertion sites across 7,395 lines, where
a failure is a printed line and an increment of a counter rather than a named case. This is the
bridge's actual value: granularity and names in the report, not speed.

**Startup amortization is not an argument, and this document's first draft implied it was.**
Measured: `freecadcmd` fixed startup is **0.27–0.37 s**, and `check_solid_measure.py` runs end to
end in **1.05 s**. Across all 29 scripts the per-process overhead the bridge would save is on the
order of nine seconds, which is nothing. The run time of this tier is dominated entirely by the
document-driven builds — `check_cowl_interior.py` is about 17 minutes, of which 990 s is one
cavity construction — and the bridge does not make a build faster. What it does is let one build
serve many assertions, which is a different claim and only applies to the 19.

**Only one existing script is cleanly shape-only.** That matters for any rule that would route
tests by whether they construct a shape or drive a document: such a rule moves exactly one script
of 29, which is near-vacuous as a policy. See OQ-GB-2.

**A finding independent of this design, recorded so it is not lost.** The nine scripts that import
no FreeCAD are `check_dimension_placement`, `check_drawing_standard`, `check_geometry_branches`,
`check_measure`, `check_placement_determinism`, `check_sheet_standard`, `check_sheet_table`,
`check_table_width` and `check_units`. They are pure Python checks living in the `freecadcmd`
tier for no reason this survey can see, where a failure is a printed line rather than an
assertion, and where the project's own guidelines would put them in `tests/`. Moving them needs no
bridge and no decision from this document; it is noted here because the survey is what found it.

---

## 7. Verification of the library itself

The library exists to enable a fast test tier, so testing it only in the slow tier would be
circular. **`LoopbackTransport` runs the full protocol in-process against a stub object graph with
no vendor present**, which puts the codec, the lifetime rules, the error synthesis, the watermark,
the cache policy and the paging logic in the project's existing venv `pytest` tier, where they run
in milliseconds and need no FreeCAD at all. Only the cases that genuinely exercise a vendor need a
vendor.

Required coverage, each item traceable to a measured hazard above:

| Area | Must assert | From |
| --- | --- | --- |
| Numeric fidelity | floats round trip bit-exactly, including `1e-13` and subnormals | §4.4, probe 1 |
| Non-finite | `inf`, `-inf`, `nan` survive, and the format's non-standardness is pinned | §4.2, probe 2 |
| Assignment | `setattr` works, and a failed assignment is distinguishable from a missing attribute | §4.3, probe 3 |
| Operators | every allowlisted dunder forwards; a non-allowlisted one raises cleanly rather than round-tripping | §4.3, probe 4 |
| Iteration | sequence and mapping both iterate correctly, in one round trip | §4.3, probes 5 and 9 |
| Truthiness | `bool(proxy)` is `True` for an object with no `len` | §4.3, probe 9 |
| Hashability | a proxy is unhashable, and says why | §4.3 |
| Cache policy | a dynamic-property object is never cached by type | §4.5, probe 6 |
| Lifetime, forward | temporaries and chain intermediates are freed | §4.6 |
| **Lifetime, converse** | **a still-referenced object is never freed** | §4.6 — this is the test that caught the live-object-freed defect |
| Lifetime, cycles | the delay for a proxy in a reference cycle is measured, not assumed | §4.6 residual limit |
| Watermark | stale, unknown and live are distinguished with no per-id storage | §4.6, probe 7 |
| Errors, identity | a remote exception is catchable by name, by hierarchy, and is the same class twice | §4.9 |
| Errors, separation | a bridge fault is **not** catchable as a geometry error | §4.9 |
| Errors, diagnostics | the remote traceback names file, function and line, and reaches the report | §4.9 |
| Liveness | a hung call fails within one interval; a long call does not; a timeout leaves no orphan process | §4.7, probe 8 |
| Bulk | `project` reads N×M attributes in one trip; an oversized response pages | §4.8, probes 11 and 12 |
| Encoding | non-ASCII round trips through the bridge's own payloads | §4.2, probe 10 |
| Freshness | a fresh worker is actually fresh — no document, handle or state inherited | §5.1 |
| Reset | vendor state does not leak between tests | §5.2 |
| Restart | a handle used across a restart raises rather than addressing a different object | §5.3 |
| Parallel | two bridges in one process do not interfere | §5.4 |
| Orphans | closing the client's stdin ends the worker | §5.5 |
| **Facade fidelity** | **every member a facade declares exists on the live vendor object, and every facade call reaches the same member the proxy would** | §4.10, §5.6 — the drift hazard, and the one test a facade cannot do without |
| Facade fallback | a type outside the facade set still works through the dynamic proxy | §4.10 |
| **Facade lookup** | **a document object, whose leaf type is `PrimitivePy`, resolves to the `DocumentObject` facade** | §4.10 — keying on the leaf name silently unfacets the most-used type |
| Facade hierarchy | `Vertex` lacks `CenterOfMass` on the live object, not only in the source | §4.10 — the converse of the one branch in the hierarchy |
| Facade containers | a member returning a list reads lazily and faces its elements | §4.10 — the alternative allocates a handle per element on attribute access |
| Facade cost | a faceted read is the same one round trip the proxy costs | §4.10 — a facade is a spelling, not a layer |

**A performance budget is part of the contract, not an aspiration**, because the measurements
above are what justify the design over the alternatives, and a regression would silently remove
that justification. Asserted with generous margins so the suite is not flaky: a warm method call
is one round trip; a handle operation stays under 5 ms; `project` over N elements is one round
trip; a method call allocates no handle.

## 8. Open questions

| ID | Status | Question |
| --- | --- | --- |
| GB-1 | decided 2026-10-06 | Typed facades, scoped by a survey of which vendor types the project actually uses. The survey is §4.10 and names the set |
| GB-2 | decided 2026-10-06 | Bridge-first: a new geometry test is a bridge test unless its purpose is a whole-build report for a person to read. Needs writing into the guidelines' two-tier section |

### OQ-GB-1 — Typed facades, generated stubs, or neither? — DECIDED 2026-10-06: alternative 2

**Decision.** Alternative 2, typed facades, with the prerequisite survey carried out before
anything was written. **The survey and the resulting facade set are [§4.10](#410-the-typed-facade-set)**,
which is the authority; it is design content and does not belong in an open question.

**The survey confirmed the decision and changed its content.** Five types cover 90.5% of
unambiguous member uses and eight cover 99.9%, so the head is short enough for facades to be worth
writing — the condition the recommendation set. But `Shape` and `Solid` turned out to have **zero**
unambiguous uses, every member being shared across the `Part.Shape` subclasses, so the one-facade-
per-shape-type decomposition this document first assumed is wrong; there is one shared `Shape`
facade instead. And the types that dominate are the document ones, not the geometry ones, led by
`DocumentObject` at 361 uses with `setExpression` alone at 93.

**Caveat attached to the choice.** Coverage is deliberately uneven: a type outside the facade set
falls back to the dynamic proxy, which always works but offers no completion. The fallback is what
keeps the facade set small.

**The measurement alternative 3's rejection was waiting on has since been taken, and it supports
the decision.** Alternative 3 was set aside on the *expectation* that introspecting a C extension
yields `(*args, **kwargs)`, with the prerequisite that this be measured. Measured while writing
the facades (§4.10): FreeCAD's docstrings carry a signature line for 31% of the methods in the
facade set — all 17 of `Base.Vector`, `Base.BoundBox` and `Base.Placement`, and **none** of
`Part.Shape`'s 35. So the signature information exists, but as prose on a second docstring line
rather than anything a generator could rely on, and it is absent exactly on the shape side where
the geometry work happens. Alternative 3 stays rejected, now on a measurement instead of an
expectation. Revisit it only if the facades prove inadequate.

A proxy forwards attributes dynamically, so an editor cannot offer completions on `shape.` and a
type checker cannot verify that `shape.Volum` is a typo. In-process imports do not have this
problem, so this is a real regression introduced by the boundary, and it affects every geometry
test written from here on. It is not fully solvable, because the vendor API is itself only
partly typed.

**Alternatives**

1. **Neither.** Document that geometry proxies are dynamic. *Benefits:* no work, nothing to keep
   in sync. *Drawbacks:* a misspelled attribute is a run-time failure found by running the suite,
   and the completion loss is felt on every test written. *Prerequisites:* none.
2. **Typed facades for the types the project actually uses.** Hand-written classes wrapping the
   small set — `Shape`, `Solid`, `Face`, `Wire`, `Edge`, `Vertex`, `Vector`, `BoundBox`, the
   document object — with real signatures, delegating to the proxy. *Benefits:* full completion
   and checking where it is used most; the facade is also the natural place for project-level
   convenience; a facade's own surface is small enough to test. *Drawbacks:* every facade is a
   second surface to maintain and can drift from the vendor API; anything outside the facade set
   falls back to the dynamic proxy, so coverage is uneven in a way a reader must learn.
   *Prerequisites:* a survey of which vendor types the project's tests actually touch.
3. **Generated stub files for the vendor API.** Produce `.pyi` stubs by introspecting the vendor
   modules in the worker. *Benefits:* broad coverage without hand-maintenance; regenerated when
   the vendor version changes. *Drawbacks:* introspection of a C extension yields poor signatures
   — most FreeCAD methods would come out as `(*args, **kwargs)` — so the completion is shallow
   and the type checking close to worthless; a generated artifact must be committed and kept
   current. *Prerequisites:* measuring how much real signature information FreeCAD's extension
   modules actually expose, which is unknown.

**Recommendation**

**Alternative 2, scoped by a measurement.** The dynamic fallback is adequate for breadth and the
value of typing is concentrated in a handful of types, so hand-writing those few is the best
return. It should not be started before the survey its prerequisite names: if the project's tests
turn out to touch a wide spread of vendor types, 2 degrades into 3's maintenance problem without
3's breadth, and alternative 1 becomes the honest choice. Alternative 3 cannot be recommended
without first measuring the signature quality available, and the expectation is that it is poor.

### OQ-GB-2 — Where does a new geometry test go? — DECIDED 2026-10-06: alternative 1

**Decision. Bridge-first, with one exception stated in terms of purpose:** a new geometry test is a
bridge test unless its purpose is a whole-build report for a person to read, which stays a
`check_*.py` script. No existing file changes, and the rule binds only tests written from here on.

**The rule, as it should appear in the guidelines.** A new geometry check is a `pytest` function in
the bridge tier. It becomes a `check_*.py` script only when what it produces is a report a person
reads rather than a set of assertions — in practice, the whole-part parametric builds that take
minutes and print a table. The test being document-driven is **not** a reason to make it a script;
§4.3 makes `setattr` a first-class operation precisely so document-driven tests can be bridge
tests.

**Rationale.** Alternative 1 is the only option that points new work at the tier this design
exists to create while leaving the 19 expensive builds where they are well served. The three
rejected options each failed on a measurement rather than on taste: alternative 2 would route one
script of 29 and would forbid exactly the document-driven tests `setattr` was built for;
alternative 3 pays 4,959 lines of rewriting for a nine-second saving, startup being the only thing
the bridge saves; alternative 4's real outcome is the status quo, since the script tier has 29
examples to copy and the bridge tier none, which would make this whole design a waste.

**Caveat attached to the choice.** "Purpose" is a judgment, so the boundary case — a test needing
most of a build to assert one number — is decided per test rather than by rule. That was accepted
deliberately: the alternative is a mechanical rule, and the mechanical rule available here was
measured to be near-vacuous.

**Outstanding.** This decision is a convention and does nothing until it is written into
[general.md](../guidelines/general.md)'s two-tier section — the same section whose stated
justification OQ-ARCH-22 found to be false. Both corrections belong in one edit.

**What is being decided.** After this library exists there are two places a geometry test can
live, and they are not interchangeable. The question is which one a *new* test goes in by default.
It is a convention, not a capability: both will work, and the cost of getting it wrong is paid
slowly, in a test suite that is harder to run than it needed to be.

**The two destinations, concretely.**

A **bridge test** is an ordinary `pytest` function in the project's own interpreter. It is
collected by name, reports as a named case, can use fixtures and `@pytest.mark.parametrize`, and
asserts with `assert` and `pytest.raises`. It holds vendor objects by reference and measures them,
and an expensive build held in a fixture is paid once for the whole session. It runs under a
liveness deadline (§4.7) and inside the handle-lifetime machinery (§4.6).

A **`check_*.py` script** is a standalone program run by `freecadcmd`. It builds what it needs,
prints a line per check, counts failures in a `bad` counter and returns it as an exit code — an
exit code the project does not trust, because `freecadcmd` exits 0 on an uncaught exception. Its
output is a report a person reads. It has no collection, no fixtures, no parametrization, and one
uncaught exception ends the whole report.

**What the existing corpus looks like**, surveyed in [§6.1](#61-what-the-existing-check-script-tier-actually-contains):
29 scripts, 7,395 lines, **45 assertion sites** — about one per 164 lines. Nine of the 29 import no
FreeCAD at all; **exactly one** is FreeCAD-but-shape-only; **19 are document-driven parametric
builds**.

**Two quantities that bound the argument, both measured and both inconvenient.**

*Startup amortization is worth almost nothing.* `freecadcmd` starts in 0.27–0.37 s and a shape-only
check runs end to end in 1.05 s, so running 29 scripts as 29 processes costs about nine seconds of
overhead in total. Any claim that the bridge is faster because it starts the vendor once is false
at this corpus size. The tier's run time is dominated by the document builds, and the bridge does
not make a build faster.

*What the bridge does buy is granularity and build reuse.* A named case instead of a printed line,
at a density far above one per 164 lines; and one build serving many assertions, which applies
only to the 19 document-driven scripts and is worth a great deal there — `check_cowl_interior.py`
spends 990 s on a single cavity construction and then makes roughly a dozen checks against it.

**Why this is not already settled by §6.** §6 says both tiers stay, which disposes of the existing
scripts. It does not say where a new test goes. Left unstated, the default is whichever a person
already knows, and the realistic outcome is that the slow tier keeps growing: it is the one with 29
examples to copy from.

**Who is affected and when it binds.** Only tests written from here on. The decision is a
convention in the guidelines, reversible at any time, and no existing file changes under any
alternative below.

**Alternatives**

1. **Bridge-first, with one stated exception.** A new geometry test is a bridge test unless its
   purpose is a whole-build report for a person to read, which stays a `check_*.py`.
   *Benefits:* a clear default that points new work at the tier with names, fixtures and
   assertions; the exception is stated in terms of the test's purpose, which is the thing that
   actually differs. *Drawbacks:* purpose is a judgment, so the boundary case — a test needing
   most of a build to assert one number — is decided per test rather than by rule; a reader must
   understand both tiers to apply it. *Prerequisites:* none.
2. **Split by what is built: constructed shape to the bridge, document build to a script.**
   *Benefits:* mechanical, no judgment required. *Drawbacks:* **measurably near-vacuous** — the
   survey found exactly one of 29 existing scripts is shape-only, so this rule routes almost
   everything to the script tier and the bridge would accumulate only the narrow class of tests
   that build geometry from primitives. It also forbids document-driven tests from the bridge
   although §4.3 makes `setattr` a first-class operation specifically to enable them, so the rule
   would prohibit what the design deliberately built. *Prerequisites:* none.
3. **Bridge only; convert the 19 document-driven scripts over time.** *Benefits:* one place, one
   idiom, and every check becomes a named case. *Drawbacks:* 4,959 lines rewritten for no run-time
   gain, since startup is the only thing the bridge saves and that is nine seconds; it puts every
   quarter-hour build behind a liveness deadline and the handle-lifetime machinery, which is
   additional failure surface for a job whose output is a human-read report; and the reports
   themselves would need replacing, since `pytest` output is not a report.
   *Prerequisites:* a replacement for the printed reports.
4. **No rule; each test goes where its author prefers.** *Benefits:* no convention to write,
   enforce or argue about; the person writing the test knows most about it. *Drawbacks:* with 29
   examples in one tier and none in the other, "no rule" resolves in practice to "keep using
   scripts", so the library gets built and then goes unused — the failure mode worth naming
   explicitly, because it is what happens by default rather than by decision.
   *Prerequisites:* none.

**Recommendation**

**Alternative 1.** It is the only option that routes new work to the tier this design exists to
create while leaving the 19 expensive builds where they are well served. Alternative 2 is rejected
on its own measurement: one script in 29, and it forbids precisely the document-driven tests
§4.3 was built for. Alternative 3 pays 4,959 lines for a nine-second saving. Alternative 4 is
rejected because its real outcome is the status quo, which is the one result that would make this
whole design a waste.

The exception should be written in terms of purpose — *a report a person reads* stays a script —
rather than in terms of mechanism, because mechanism is exactly what §4.3 stopped being a
distinction.

---

## 9. References

- [freecad_migration.md](freecad_migration.md) — OQ-ARCH-22, which this document resolves, with
  the version-lock measurements and the five rejected alternatives; OQ-ARCH-19 and OQ-ARCH-21 on
  the reproducibility criterion that §5.1 serves
- [general.md](../guidelines/general.md) — the two-tier test convention, whose stated
  justification OQ-ARCH-22 corrects
- [python.md](../guidelines/python.md) — the same correction, and the dataclass conventions the
  library follows
- [cowl_interior_surface.md](../design/cowl_interior_surface.md) — the measurement cautions that
  set §4.4's fidelity requirement and §4.8's sample counts
- [roadmap.md](../roadmap.md) — Phase 3, which this tooling serves
