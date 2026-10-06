# Geometry Bridge — Implementation Plan

**Scope:** Building the adaptation library designed in
[geometry_bridge.md](../architecture/geometry_bridge.md): a process boundary that lets `pytest`,
running under the project's own interpreter, drive FreeCAD and OpenVSP whose binary extensions are
built for different, vendor-chosen CPython versions. Both of the design's open questions are
resolved — OQ-GB-1 fixed the typed facade set from a survey, OQ-GB-2 made new geometry tests
bridge-first — so no item here is blocked on a design decision. The design's §7 verification table
is the source of this plan's test items; each one names the measured hazard it exists for.

**Design authority:** [geometry_bridge.md](../architecture/geometry_bridge.md),
[freecad_migration.md](../architecture/freecad_migration.md) (OQ-ARCH-22),
[general.md](../guidelines/general.md) (the three-tier test convention)

**Last updated:** 2026-10-06

**Progress.** The library is working end to end. 138 tests: 92 in the loopback tier with no vendor
present, 17 on the line protocol and liveness against a fake worker subprocess, and 29 against real
FreeCAD. The whole project suite is 1011 passing, up from 873, with nothing broken. Measured against
the real vendor: 29 bridge cases in 5.16 s, a warm method call at one round trip, a handle operation
under 5 ms, and a method call allocating no handle.

---

## Work Items

| ID | Status | Title | Depends on | Design refs |
| --- | --- | --- | --- | --- |
| IP-GB-1 | done | Create the `geometry_bridge` package under `src/Fuselage/tools/` with `codec`, `transport`, `proxy`, `lifetime`, `errors`, `api` modules and no vendor import at module scope | — | [geometry_bridge.md §3](../architecture/geometry_bridge.md) |
| IP-GB-2 | done | Implement the value/handle codec: scalar and container passthrough, handle encoding, the documented lossy mappings, and a bounded nesting depth | IP-GB-1 | [§4.3](../architecture/geometry_bridge.md), [§4.4](../architecture/geometry_bridge.md) |
| IP-GB-5 | done | Implement the handle registry with the monotonic-id watermark rule, so stale and unknown are distinguished with no per-id storage | IP-GB-2 | [§4.6](../architecture/geometry_bridge.md) |
| IP-GB-4 | done | Implement the vendor-free op dispatcher: `module`/`getattr`/`setattr`/`callattr`/`call`/`getitem`/`setitem`/`len`/`iterate`/`project`/`batch`/`release`/`reset`/`stats`, a module allowlist, and no code-evaluation op | IP-GB-5 | [§4.2](../architecture/geometry_bridge.md), [§4.3](../architecture/geometry_bridge.md) |
| IP-GB-3 | done | Implement `LoopbackTransport` — the full protocol in-process against a stub object graph, no vendor needed | IP-GB-4 | [§3](../architecture/geometry_bridge.md), [§7](../architecture/geometry_bridge.md) |
| IP-GB-8 | done | Implement remote exception synthesis: class chain rebuilding, builtin co-inheritance, a pre-registered `remote_errors` module, `__tracebackhide__`, and `BridgeError` as an unrelated class | IP-GB-2 | [§4.9](../architecture/geometry_bridge.md) |
| IP-GB-9 | done | Implement the `Remote` proxy: the dunder allowlist, explicit `__bool__`, `__eq__` without `__hash__`, passthrough `__getitem__`, and `__iter__` bound to `iterate` | IP-GB-5, IP-GB-8 | [§4.3](../architecture/geometry_bridge.md) |
| IP-GB-10 | done | Implement handle lifetime: `__del__` queueing only, releases piggybacked on the next request, threshold flush, and a bound method that holds its owner proxy | IP-GB-9 | [§4.6](../architecture/geometry_bridge.md) |
| IP-GB-11 | done | Implement the callable cache with the worker-supplied `cacheable` flag, never inferred client-side | IP-GB-9 | [§4.5](../architecture/geometry_bridge.md) |
| IP-GB-12 | done | Implement `project` and `batch` bulk ops, with cursor paging above the line-size limit | IP-GB-9 | [§4.8](../architecture/geometry_bridge.md), [§4.2](../architecture/geometry_bridge.md) |
| IP-GB-6 | done | Implement `WorkerTransport` and `wire`: subprocess launch via `freecad_render.freecadcmd_path()`, explicit UTF-8, sentinel framing, a reader thread, and a bounded ring buffer for the vendor's own output | IP-GB-4 | [§4.2](../architecture/geometry_bridge.md), [§4.7](../architecture/geometry_bridge.md) |
| IP-GB-7 | done | Implement the liveness deadline: a worker heartbeat thread, a client deadline on silence rather than duration, and a `BridgeTimeout` that terminates the worker before raising | IP-GB-6 | [§4.7](../architecture/geometry_bridge.md) |
| IP-GB-13 | done | Implement the worker lifecycle API: session worker, fresh worker, `reset` per vendor, and restart on a handle ceiling | IP-GB-7, IP-GB-10 | [§5.1](../architecture/geometry_bridge.md), [§5.2](../architecture/geometry_bridge.md), [§5.3](../architecture/geometry_bridge.md) |
| IP-GB-14 | done | Add the pytest fixtures and conftest wiring: `fc`, `fresh_fc`, module fixtures, autouse per-test vendor reset, and one bridge per xdist worker with no module-global state | IP-GB-13 | [§5.2](../architecture/geometry_bridge.md), [§5.4](../architecture/geometry_bridge.md) |
| IP-GB-15 | done | Implement `LocalTransport` and wire OpenVSP to it through `oml_export.import_vsp()`'s existing discovery | IP-GB-9 | [§3](../architecture/geometry_bridge.md), [§5.2](../architecture/geometry_bridge.md) |
| IP-GB-16 | todo | Write the typed facades in survey order — `DocumentObject`, `Vector`, `Document`, `BoundBox`, `Placement` — then one shared `Shape` with thin `Face`/`Edge`/`Vertex`/`Wire` extensions | IP-GB-11 | [§4.10](../architecture/geometry_bridge.md) |
| IP-GB-17 | todo | Add the facade drift test: every member a facade declares exists on the live vendor object, and a facade call reaches the same member the proxy would | IP-GB-16 | [§4.10](../architecture/geometry_bridge.md), [§5.6](../architecture/geometry_bridge.md) |
| IP-GB-18 | todo | Add the performance-budget tests: a warm method call is one round trip, a handle op stays under 5 ms, `project` over N elements is one trip, a method call allocates no handle | IP-GB-12, IP-GB-14 | [§7](../architecture/geometry_bridge.md), [§1](../architecture/geometry_bridge.md) |
| IP-GB-19 | todo | Measure the release delay for a proxy held in a reference cycle, the one residual limit the design records as unmeasured | IP-GB-10 | [§4.6](../architecture/geometry_bridge.md) |
| IP-GB-20 | todo | Port `check_solid_measure.py`'s four checks to bridge tests as the first real consumer, keeping the script until the port is shown equivalent | IP-GB-14, IP-GB-16 | [§6.1](../architecture/geometry_bridge.md), [general.md](../guidelines/general.md#two-test-tiers-because-two-python-interpreters-are-involved) |
| IP-GB-21 | todo | Give `cowl_interior.py`'s private helpers named bridge tests — `_check_slope`, `_Polyline`, `_thin_stations`, `station_floor`, `section_regions` — the assertions that today are printed lines inside `check_cowl_interior.py` | IP-GB-20 | [§6.1](../architecture/geometry_bridge.md), [cowl_interior_surface.md §6](../design/cowl_interior_surface.md) |
| IP-GB-22 | todo | Move the nine `check_*.py` scripts that import no FreeCAD into `tests/` as ordinary pytest tests | — | [§6.1](../architecture/geometry_bridge.md) |

Every item above carries its own tests, per the TDD rule in
[general.md](../guidelines/general.md#test-driven-development-tdd). The test items listed
separately — IP-GB-17, IP-GB-18, IP-GB-19 — are there because each needs a fixture or a
measurement harness that is substantial standalone work, which is the stated exception.

---

## Notes

**Ordering rationale.** `LoopbackTransport` (IP-GB-3) comes before the real worker on purpose. It
is what lets the codec, lifetime, watermark, cache policy, error synthesis and paging be tested in
the venv `pytest` tier with no vendor present. Building the worker first would push the library's
own tests into the slow tier it exists to avoid, which is the circularity the design's §7 calls
out.

**IP-GB-5 before IP-GB-10.** The watermark rule is what makes a use-after-free report `StaleHandle`
instead of a bare `KeyError`. Reference counting without it produces confusing failures during
exactly the work that shakes out lifetime bugs.

**Ordering corrected during implementation, 2026-10-06.** The plan as first written had IP-GB-5
depending on IP-GB-4 and IP-GB-3 depending on IP-GB-1. Both edges were backwards: the dispatcher
needs the registry to resolve a handle at all, and the loopback transport needs the dispatcher to
have something to dispatch. The real order is codec, registry, dispatcher, loopback — now reflected
in the table, with the rows re-sorted so no item precedes something it depends on.

**Two findings from building it, recorded because neither was predicted.** `object` gained a real
`__getstate__` in Python 3.11, so it is found by ordinary attribute lookup and never reaches the
proxy's `__getattr__` — a test probing the dunder guard has to use something genuinely absent, such
as `__deepcopy__`. And closing a dead worker's pipe raised an unraisable `OSError` from the stream's
own destructor, surfacing as an ownerless pytest warning; the transport now closes both pipes
deliberately, because a warning with no owner will mask a real one later.

**IP-GB-9's two defects are known in advance and are why it is one item, not several.** The
prototype got both wrong: a blanket underscore guard made the whole private half of `cowl_interior`
unreachable, and a bound method that held its owner's handle *id* rather than the owner proxy freed
a live object mid-expression. Both are called out in the design; the item is not done until the
converse test — that a still-referenced object is never freed — passes.

**IP-GB-22 is independent of everything else** and is listed here only because the §6.1 survey is
what found it. Those nine scripts, 2,290 lines, import no FreeCAD at all and need no bridge; they
are in the `freecadcmd` tier for no reason the survey could identify.

**No item requires a full parametric sweep to verify.** The design's own measurements were taken on
primitives and on one slotted tube, both sub-second. IP-GB-20 and IP-GB-21 are the first items that
touch real project geometry, and both use existing committed shapes rather than regenerating
anything.

**What is deliberately not in this plan.** Converting the 19 document-driven `check_*.py` scripts.
OQ-GB-2 settled that they stay, and the bridge is for new tests plus the fine-grained assertions
that have no home today.
