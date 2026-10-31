"""The measurement interface to `cowl_interior`'s construction. Test and measurement only.

**Why this module exists.** Driving the booleans after the fit needs two things the construction
does not otherwise offer: a way to perturb the eroded contour every row is built from, and a way to
seed a station set the production floor would thin. Both were first built as **parameters on
`cavity` and `shell_solid`** -- `contour_probe` and `station_floor_mm`
([OQ-DES-CW34](../../../../doc/design/cowl.md#open-questions)) -- which put measurement-only
features in the signature of the subsystem's production entry point. That was judged unacceptable,
which the decision itself had recorded as reversible, and this module is the replacement.

**What the construction keeps.** One private module-level seam, `cowl_interior._probe`, inert when
`None`, read through two one-line accessors. Nothing in `cavity`'s or `shell_solid`'s signature
mentions measurement, and a reader of either sees the production interface only.

**What this module adds.** The whole measurement vocabulary: what a probe is, what it may change,
and a context manager that installs one and is guaranteed to remove it. A measurement harness
imports this; the construction never imports it.

**The module is an argument, not an import**, which is the standing rule for this package -- `Part`
and `App` arrive as arguments so nothing here needs a vendor interpreter. Here it buys the test that
matters: `installed` can be exercised against a stub module, so its install, restore and
refuse-to-nest behavior is checked without building anything.

**Two deliberate refusals.**

*Nesting is an error, not a stack.* Two probes installed at once would mean one of them is silently
ignored, and a measurement that is quietly not happening is the exact failure this subsystem has
already produced twice -- a hook on the wrong rows, and a target station that collapsed onto a
pinned boundary row, both of which read as clean null results (§4.4).

*Restoration is unconditional.* `__exit__` puts back whatever was there even when the body raises,
because a dose series that fails partway must not leave the next build perturbed.
"""

#: The attribute the seam lives under on the construction module.
PROBE_ATTR = '_probe'


class ProbeInUse(Exception):
    """Raised when a probe is installed while another is already active."""


class Probe(object):
    """What a measurement may change about the construction, and nothing else.

    `contour(z, pts)` is applied to the eroded contour of **every** row the construction builds,
    which is the only placement that works: section 5's second pass rebuilds its rows from
    `fit_at` after the rib cut, so a perturbation applied to `_refine`'s output is discarded on the
    first post-cut round.

    `station_floor(default)` replaces `station_floor(t)` for the per-patch union. `0.0` restores the
    unfiltered union the construction seeded before IP-FC-144 -- it declines to *drop* stations the
    construction derived for itself, and is not a way to force one in.

    `calls` counts how many rows the contour hook actually transformed, so a reading is never
    quoted without evidence that something moved.
    """

    __slots__ = ('contour_fn', 'station_floor_mm', 'calls', 'stations')

    def __init__(self, contour=None, station_floor_mm=None):
        self.contour_fn = contour
        self.station_floor_mm = None if station_floor_mm is None else float(station_floor_mm)
        self.calls = 0
        #: Every `z` the contour hook transformed, in order, so the station actually moved is on
        #: record rather than assumed from the request.
        self.stations = []

    def contour(self, z, pts):
        """The contour the construction should use at `z`. Identity when no hook is set."""
        if self.contour_fn is None:
            return pts
        out = self.contour_fn(z, pts)
        if out is not pts:
            self.calls += 1
            self.stations.append(float(z))
        return out

    def station_floor(self, default):
        """The floor to thin the per-patch union with. `default` when none is set."""
        return default if self.station_floor_mm is None else self.station_floor_mm

    @property
    def moved(self):
        """Did the contour hook change anything? The `inputs.unmoved` discipline, in one place."""
        return self.calls > 0

    def __repr__(self):
        return '<Probe contour=%s floor=%s calls=%d>' % (
            self.contour_fn is not None, self.station_floor_mm, self.calls)


class Installed(object):
    """Installs a `Probe` on a module for the duration of a `with` block.

    Refuses to nest, and restores the previous value whether the body returns or raises. See the
    module note for why both are deliberate.
    """

    __slots__ = ('module', 'probe', '_previous', '_active')

    def __init__(self, module, probe):
        self.module = module
        self.probe = probe
        self._previous = None
        self._active = False

    def __enter__(self):
        current = getattr(self.module, PROBE_ATTR, None)
        if current is not None:
            raise ProbeInUse(
                'a probe is already installed on %s; nesting would silently ignore one of them. '
                'Close the outer measurement first.' % getattr(self.module, '__name__', self.module))
        self._previous = current
        setattr(self.module, PROBE_ATTR, self.probe)
        self._active = True
        return self.probe

    def __exit__(self, exc_type, exc, tb):
        if self._active:
            setattr(self.module, PROBE_ATTR, self._previous)
            self._active = False
        return False                       # never swallow the body's exception


def installed(module, contour=None, station_floor_mm=None, probe=None):
    """A `with` block that installs a probe on `module`, as `Installed`.

    Pass `probe` to install one you already hold -- a dose series keeps its own so it can read
    `calls` afterwards -- or `contour` and `station_floor_mm` to have one built.
    """
    if probe is None:
        probe = Probe(contour, station_floor_mm)
    elif contour is not None or station_floor_mm is not None:
        raise ValueError('pass a probe or its parts, not both')
    return Installed(module, probe)


def active(module):
    """The probe installed on `module`, or `None`. For a harness checking its own state."""
    return getattr(module, PROBE_ATTR, None)
