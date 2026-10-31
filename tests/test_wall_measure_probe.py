"""The measurement seam: that it is inert, that it is always removed, and that it cannot nest.

`cowl_interior`'s production entry points take no measurement arguments. What a measurement may
change lives in `wall_measure.probe`, which installs a probe on the construction module for the
duration of a `with` block. That design has exactly three ways to go wrong, and each is a test here:

* the seam is **not** inert, so a build behaves differently from how it ships;
* the probe is **not** removed, so a later build in the same process is silently perturbed;
* two probes are installed at once, so one of them silently does nothing.

The third is the one this subsystem has already been burned by in another form: a hook on the wrong
rows and a target station that collapsed onto a pinned boundary row both read as clean null
results. A measurement that is quietly not happening is the failure mode to design against.

`installed` takes the module as an argument, so all of this is checked against a stub rather than
by building a cowl. See doc/design/cowl.md OQ-DES-CW34.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import probe as wm_probe                                  # noqa: E402


class FakeModule(object):
    """Stands in for `cowl_interior`: it only needs the attribute and a name for the error."""

    __name__ = 'fake_cowl_interior'

    def __init__(self, probe=None):
        self._probe = probe


def read_seam(module, default=None):
    """What the construction's accessors would see, written the way they are written."""
    p = getattr(module, wm_probe.PROBE_ATTR, None)
    return p


class TestTheProbeItself:

    def test_with_no_hook_the_contour_is_the_identity(self):
        """Inert means the **same object** back, not an equal copy: a build must be untouched."""
        p = wm_probe.Probe()
        pts = [(1.0, 2.0), (3.0, 4.0)]
        assert p.contour(-10.0, pts) is pts
        assert p.calls == 0 and p.moved is False

    def test_with_no_override_the_floor_is_the_default(self):
        p = wm_probe.Probe()
        assert p.station_floor(0.6) == 0.6

    def test_a_zero_floor_is_honored_and_not_treated_as_absent(self):
        """**The trap `0.0 or default` would set.** Zero is the whole point of the override."""
        p = wm_probe.Probe(station_floor_mm=0.0)
        assert p.station_floor(0.6) == 0.0

    def test_the_floor_override_is_coerced_to_a_float(self):
        p = wm_probe.Probe(station_floor_mm=0)
        assert isinstance(p.station_floor(0.6), float)

    def test_a_hook_that_changes_a_row_is_counted_and_its_station_recorded(self):
        def hook(z, pts):
            return [(x + 1.0, y) for x, y in pts] if z == -5.0 else pts
        p = wm_probe.Probe(contour=hook)
        pts = [(0.0, 0.0)]
        assert p.contour(-1.0, pts) is pts            # declined
        out = p.contour(-5.0, pts)
        assert out == [(1.0, 0.0)]
        assert p.calls == 1 and p.stations == [-5.0] and p.moved is True

    def test_a_hook_that_declines_every_row_is_not_counted_as_having_moved(self):
        """The `inputs.unmoved` discipline: a probe that fired on nothing must say so."""
        p = wm_probe.Probe(contour=lambda z, pts: pts)
        for z in (-1.0, -2.0, -3.0):
            p.contour(z, [(0.0, 0.0)])
        assert p.calls == 0 and p.moved is False

    def test_the_same_station_hit_twice_counts_twice(self):
        """Section 5 rebuilds its rows after the rib cut, so a station is legitimately revisited."""
        p = wm_probe.Probe(contour=lambda z, pts: list(pts) + [(9.0, 9.0)])
        p.contour(-5.0, [(0.0, 0.0)])
        p.contour(-5.0, [(0.0, 0.0)])
        assert p.calls == 2 and p.stations == [-5.0, -5.0]


class TestInstalling:

    def test_the_seam_is_none_before_and_after(self):
        mod = FakeModule()
        assert read_seam(mod) is None
        with wm_probe.installed(mod, station_floor_mm=0.0) as p:
            assert read_seam(mod) is p
        assert read_seam(mod) is None

    def test_it_is_removed_even_when_the_body_raises(self):
        """A dose that fails partway must not leave the next build perturbed."""
        mod = FakeModule()
        with pytest.raises(ValueError):
            with wm_probe.installed(mod, station_floor_mm=0.0):
                assert read_seam(mod) is not None
                raise ValueError('the build failed')
        assert read_seam(mod) is None

    def test_it_does_not_swallow_the_body_s_exception(self):
        mod = FakeModule()
        with pytest.raises(ci_error()):
            with wm_probe.installed(mod):
                raise ci_error()('boom')

    def test_a_probe_passed_in_is_the_one_installed_and_is_readable_after(self):
        """A dose series keeps its own probe so it can read `calls` once the build is over."""
        mod = FakeModule()
        mine = wm_probe.Probe(contour=lambda z, pts: list(pts) + [(1.0, 1.0)])
        with wm_probe.installed(mod, probe=mine) as got:
            assert got is mine
            read_seam(mod).contour(-5.0, [(0.0, 0.0)])
        assert mine.calls == 1

    def test_nesting_is_refused_rather_than_stacked(self):
        """Two probes would mean one is silently ignored, which is the failure to design against."""
        mod = FakeModule()
        with wm_probe.installed(mod, station_floor_mm=0.0) as outer:
            with pytest.raises(wm_probe.ProbeInUse):
                with wm_probe.installed(mod, station_floor_mm=0.1):
                    pass
            assert read_seam(mod) is outer
        assert read_seam(mod) is None

    def test_a_refused_nesting_does_not_disturb_the_installed_probe(self):
        mod = FakeModule()
        with wm_probe.installed(mod, station_floor_mm=0.0) as outer:
            try:
                with wm_probe.installed(mod, station_floor_mm=0.1):
                    pass
            except wm_probe.ProbeInUse:
                pass
            assert read_seam(mod) is outer
            assert outer.station_floor(0.6) == 0.0

    def test_passing_a_probe_and_its_parts_is_an_error(self):
        mod = FakeModule()
        with pytest.raises(ValueError):
            wm_probe.installed(mod, station_floor_mm=0.0, probe=wm_probe.Probe())

    def test_active_reports_what_is_installed(self):
        mod = FakeModule()
        assert wm_probe.active(mod) is None
        with wm_probe.installed(mod) as p:
            assert wm_probe.active(mod) is p
        assert wm_probe.active(mod) is None

    def test_a_module_with_no_seam_attribute_at_all_still_works(self):
        """`getattr(..., None)` rather than an attribute that must pre-exist."""
        class Bare(object):
            __name__ = 'bare'
        mod = Bare()
        with wm_probe.installed(mod) as p:
            assert getattr(mod, wm_probe.PROBE_ATTR) is p
        assert getattr(mod, wm_probe.PROBE_ATTR, 'gone') is None


def ci_error():
    """A distinct exception type, so the no-swallow test cannot pass by accident."""
    class HarnessError(Exception):
        pass
    if not hasattr(ci_error, '_cls'):
        ci_error._cls = HarnessError
    return ci_error._cls


class TestTheConstructionHasNoMeasurementInItsInterface:
    """The point of the whole module, asserted against the source rather than argued.

    `cowl_interior` cannot be imported without FreeCAD, so this reads its text -- the same
    technique `test_fit_response` uses to pin the station-floor formula.
    """

    def source(self):
        import io
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'src', 'Fuselage', 'freecad', 'cowl_interior.py')
        return io.open(path, encoding='utf-8').read()

    def signature(self, name):
        """The text of one `def`'s parameter list, which is what this class is about.

        Matched against the signature and not the whole file on purpose: the comments in
        `cowl_interior` name both retired parameters deliberately, to record why they are gone, and
        a test that forbade the *words* would forbid explaining the history.
        """
        import re
        src = self.source()
        m = re.search(r'\ndef %s\((.*?)\):\n' % re.escape(name), src, re.DOTALL)
        assert m, 'no def %s found' % name
        return m.group(1)

    def test_neither_entry_point_takes_a_measurement_argument(self):
        for name in ('cavity', 'shell_solid'):
            params = self.signature(name)
            for gone in ('contour_probe', 'station_floor_mm', 'probe'):
                assert gone not in params, \
                    '%r is back in %s\'s signature: %s' % (gone, name, params)

    def test_the_signatures_still_carry_their_production_arguments(self):
        """So the test above cannot pass by the signature having been emptied or renamed."""
        assert 'tau=TAU' in self.signature('cavity')
        assert 'report=None' in self.signature('cavity')
        assert 'mirrors' in self.signature('shell_solid')
        assert 'stages=None' in self.signature('shell_solid')

    def test_the_seam_defaults_to_inert(self):
        src = self.source()
        assert '\n_probe = None\n' in src

    def test_the_construction_reads_the_seam_through_its_two_accessors(self):
        src = self.source()
        assert 'def _probe_contour(z, pts):' in src
        assert 'def _probe_floor(default):' in src
        assert 'fits[k] = _probe_contour(z, pts)' in src
        assert 'floor = _probe_floor(default_floor)' in src

    def test_the_construction_does_not_import_the_measurement_module(self):
        """The dependency runs one way: a harness imports the construction, never the reverse.

        Checked as import *statements* rather than as the words, since the comments name the module
        so a reader can find it -- which is the point of having it named there.
        """
        import ast
        tree = ast.parse(self.source())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or '')
        offenders = [m for m in imported if 'wall_measure' in m or m.endswith('probe')]
        assert not offenders, 'the construction imports its own measurement interface: %s' % offenders
