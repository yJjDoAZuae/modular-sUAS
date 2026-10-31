"""What `wall_measure.refusals` promises, and the ways saving evidence can lose it.

Every test here runs without FreeCAD, because every trap is about an exception or a path and none
of them needs a solid -- which is the point of the exporter being an argument.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src', 'Fuselage', 'tools'))

from wall_measure import refusals                                   # noqa: E402


class _Refusal(Exception):
    """Stands in for `cowl_interior.Unconverged`, which cannot be imported without FreeCAD."""

    def __init__(self, message='refused', shape=None, z=None):
        Exception.__init__(self, message)
        self.shape = shape
        self.z = z


class _Bare(Exception):
    """An exception with no shape attribute at all, like `PreconditionFailed`."""


class _Recorder(object):
    """An exporter that records rather than writes."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __call__(self, shape, path):
        self.calls.append((shape, path))
        if self.fail is not None:
            raise self.fail


class TestWhatAnExceptionCarries(object):

    def test_a_refusal_with_a_shape_gives_it_up(self):
        assert refusals.shape_of(_Refusal(shape='solid')) == 'solid'

    def test_a_refusal_without_a_shape_is_none_and_not_an_error(self):
        assert refusals.shape_of(_Refusal()) is None

    def test_an_exception_with_no_such_attribute_is_none_and_not_an_error(self):
        # The whole reason `shape_of` uses `getattr`: an `AttributeError` raised from the
        # diagnosis path would replace the refusal with a failure to diagnose it.
        assert refusals.shape_of(_Bare('no shape here')) is None
        assert refusals.station_of(_Bare('no z here')) is None

    def test_a_station_comes_back_as_a_float(self):
        z = refusals.station_of(_Refusal(z='-73.1818'))
        assert isinstance(z, float)
        assert z == pytest.approx(-73.1818)

    def test_a_station_of_zero_is_a_station_and_not_an_absence(self):
        # `if z:` would drop it. A station at z = 0 is a legitimate height on these parts.
        assert refusals.station_of(_Refusal(z=0.0)) == 0.0


class TestTheName(object):

    def test_the_u_is_printed_the_way_every_other_artifact_prints_it(self):
        assert refusals.artifact_name('tail_shell', 3.0).startswith('tail_shell_U3.')

    def test_a_fractional_u_keeps_its_fraction(self):
        assert refusals.artifact_name('tail_shell', 0.5).startswith('tail_shell_U0.5.')

    def test_the_station_is_carried_at_four_decimals_so_it_matches_the_log(self):
        # The round note and the `Unconverged` message both print `%.4f`, and matching a file to
        # the line that produced it by eye is the whole reason the station is in the name.
        name = refusals.artifact_name('tail_shell', 3.0, z=-73.18185)
        assert '_z-73.1818' in name or '_z-73.1819' in name

    def test_a_dose_is_carried_when_there_is_one(self):
        assert '_d0.03' in refusals.artifact_name('tail_shell', 3.0, delta=0.03)

    def test_an_absent_part_is_left_out_rather_than_rendered(self):
        # `'%.4f' % None` raises, and a name containing "None" reads as a station called None.
        name = refusals.artifact_name('tail_shell', 3.0)
        assert 'None' not in name
        assert '_z' not in name
        assert '_d' not in name

    def test_a_dose_of_zero_is_a_dose_and_not_an_absence(self):
        assert '_d0' in refusals.artifact_name('tail_shell', 3.0, delta=0.0)

    def test_the_extension_is_the_kernels_own_format(self):
        assert refusals.artifact_name('tail_shell', 3.0).endswith('.brep')

    def test_a_separator_in_a_component_cannot_make_it_a_path(self):
        name = refusals.artifact_name('../../etc', 3.0, tag='a/b')
        assert os.sep not in name
        assert '/' not in name
        assert '\\' not in name


class TestSaving(object):

    def test_a_refusal_with_no_shape_saves_nothing_and_says_so(self, tmp_path):
        export = _Recorder()
        assert refusals.save(_Refusal(), str(tmp_path), 'tail_shell', 3.0, export) is None
        assert export.calls == []

    def test_a_bare_exception_saves_nothing_rather_than_raising(self, tmp_path):
        export = _Recorder()
        assert refusals.save(_Bare(), str(tmp_path), 'tail_shell', 3.0, export) is None
        assert export.calls == []

    def test_the_shape_is_handed_to_the_exporter_with_its_path(self, tmp_path):
        export = _Recorder()
        rec = refusals.save(_Refusal(shape='the-cavity', z=-73.1818), str(tmp_path),
                            'tail_shell', 3.0, export, delta=0.03)
        assert len(export.calls) == 1
        shape, path = export.calls[0]
        assert shape == 'the-cavity'
        assert path == rec['path']
        assert rec['z'] == pytest.approx(-73.1818)

    def test_the_artifact_goes_in_its_own_subdirectory(self, tmp_path):
        # A reader should not have to parse a filename to tell a diagnosis from a result.
        rec = refusals.save(_Refusal(shape='s'), str(tmp_path), 'tail_shell', 3.0, _Recorder())
        assert os.path.basename(os.path.dirname(rec['path'])) == refusals.DIRNAME

    def test_the_directory_is_created_before_the_export_is_called(self, tmp_path):
        seen = {}

        def export(shape, path):
            seen['dir_exists'] = os.path.isdir(os.path.dirname(path))

        refusals.save(_Refusal(shape='s'), str(tmp_path / 'not-yet'),
                      'tail_shell', 3.0, export)
        assert seen['dir_exists'] is True

    def test_an_export_that_raises_is_recorded_and_never_re_raised(self, tmp_path):
        # The sharpest trap in this module. This runs inside a caller's `except` block, so a
        # raise here would replace the refusal being diagnosed with a failure to diagnose it.
        export = _Recorder(fail=IOError('the network share went away'))
        rec = refusals.save(_Refusal(shape='s', z=-1.0), str(tmp_path),
                            'tail_shell', 3.0, export)
        assert rec is not None
        assert 'IOError' in rec['error'] or 'OSError' in rec['error']
        assert 'network share' in rec['error']
        assert 'bytes' not in rec

    def test_a_size_is_reported_when_the_file_is_really_written(self, tmp_path):
        def export(shape, path):
            with open(path, 'w') as fh:
                fh.write(shape)

        rec = refusals.save(_Refusal(shape='x' * 17), str(tmp_path),
                            'tail_shell', 3.0, export)
        assert rec['bytes'] == 17
        assert 'error' not in rec

    def test_a_stub_exporter_that_writes_nothing_is_not_reported_as_a_failure(self, tmp_path):
        # The export reported success; an unreadable size is not evidence against it.
        rec = refusals.save(_Refusal(shape='s'), str(tmp_path), 'tail_shell', 3.0, _Recorder())
        assert 'error' not in rec
        assert 'bytes' not in rec


class TestDidTheCavityLeaveTheBlank(object):
    """`escape`, whose whole reason for existing is that volume alone is the wrong test."""

    def test_no_residue_is_a_contained_cavity(self):
        verdict, why = refusals.escape(0.0, 0, True)
        assert verdict == refusals.CONTAINED
        assert 'no topology' in why

    def test_a_face_only_residue_counts_as_pieces(self):
        # The same IP-FC-137 finding read a second way, and a trap I walked into writing the
        # caller: that sliver was five *faces* and not a valid solid, so a caller passing
        # `len(shape.Solids)` hands this function a zero and gets told `contained`. The
        # parameter is pieces of any topology, and the caller counts faces where there are no
        # solids.
        verdict, why = refusals.escape(0.0, 5, True, span_mm=0.010)
        assert verdict == refusals.SLIVER
        assert '5 piece(s)' in why

    def test_real_volume_outside_the_blank_is_an_escape(self):
        verdict, why = refusals.escape(12.5, 2, True)
        assert verdict == refusals.ESCAPED
        assert '12.5' in why

    def test_the_ip_fc_137_sliver_is_not_reported_as_contained(self):
        # The trap this function exists for, with that finding's own numbers: a residue whose
        # volume reads 0.000000 and which is nonetheless a real invalid five-face shape in a
        # ten-micron bounding box. A volume-only check called this empty and passed it.
        verdict, _why = refusals.escape(0.0, 1, False, span_mm=0.010)
        assert verdict == refusals.INVALID
        verdict, why = refusals.escape(0.0, 1, True, span_mm=0.010)
        assert verdict == refusals.SLIVER
        assert 'near-tangency' in why
        assert 'sliver scale' in why

    def test_invalid_topology_is_reported_ahead_of_any_volume(self):
        # A volume measured on an invalid shape is not a figure. This must not read as an escape
        # just because the number happens to be large.
        verdict, why = refusals.escape(4349.27, 3, False)
        assert verdict == refusals.INVALID
        assert 'not a valid shape' in why

    def test_a_sliver_wider_than_sliver_scale_is_still_a_sliver_but_says_so(self):
        verdict, why = refusals.escape(0.0, 1, True, span_mm=5.0)
        assert verdict == refusals.SLIVER
        assert 'sliver scale' not in why
        assert '5.0' in why

    def test_the_volume_floor_is_a_floor_on_volume_and_not_on_existence(self):
        # Just above the floor with one piece is material; just below it with one piece is a
        # sliver. Neither is `contained`, because a piece exists either way.
        assert refusals.escape(2.0e-6, 1, True)[0] == refusals.ESCAPED
        assert refusals.escape(5.0e-7, 1, True)[0] == refusals.SLIVER


COWL_INTERIOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                             'src', 'Fuselage', 'freecad', 'cowl_interior.py')


def _unconverged_raises():
    """Every `raise Unconverged(...)` in the construction, as `(line, keyword names)`.

    Parsed rather than matched: a regex over a message that spans six lines and contains its own
    parentheses and percent formatting cannot tell a keyword from prose, and this assertion is
    only worth having if it is exact.
    """
    import ast
    tree = ast.parse(open(COWL_INTERIOR, encoding='utf-8').read())
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        func = node.exc.func
        name = getattr(func, 'id', None) or getattr(func, 'attr', None)
        if name == 'Unconverged':
            out.append((node.lineno, set(kw.arg for kw in node.exc.keywords)))
    return out


class TestTheConstructionHandsOverItsShape(object):
    """The half of this feature that lives in `cowl_interior`, pinned from outside it.

    `cowl_interior` cannot be imported without FreeCAD, so these read its source. That is the
    same technique `test_fit_response.py` uses on the station floor, and for the same reason: the
    thing worth asserting is a property of the construction, and a test that skips without a
    kernel would assert it nowhere.
    """

    def test_the_exception_accepts_a_shape_and_a_station(self):
        src = open(COWL_INTERIOR, encoding='utf-8').read()
        assert 'def __init__(self, message, shape=None, z=None):' in src

    def test_there_are_refusal_sites_to_check(self):
        # Guards the two tests below from passing because the parse found nothing.
        assert len(_unconverged_raises()) >= 10

    def test_every_refusal_hands_over_the_shape_it_was_measured_on(self):
        # The trap this file exists for. A new refusal site that does not pass its shape
        # reintroduces exactly the loss that cost a 1.94 hour rebuild on 2026-10-29 -- and it
        # does so silently, because a refusal without evidence still reads as a working check.
        # A site that genuinely has no single shape in scope should say so here rather than be
        # exempted by nobody noticing.
        missing = [line for line, kwargs in _unconverged_raises() if 'shape' not in kwargs]
        assert missing == [], ('cowl_interior.py raises Unconverged without a shape at line(s) '
                              '%s' % ', '.join(str(n) for n in missing))

    def test_the_post_cut_refusals_also_hand_over_the_station(self):
        # `shape` alone would make the artifact findable but not interpretable: the whole reason
        # the post-cut pass is instrumented is that a 0.5999 mm reading means nothing without the
        # `z` it was taken at. These are the only two sites that have one.
        with_z = [line for line, kwargs in _unconverged_raises() if 'z' in kwargs]
        assert len(with_z) == 2


class TestThisModuleDoesNotNeedTheKernel(object):

    def test_it_imports_nothing_the_worker_may_not_have(self):
        # The package-wide allowlist is pinned by `test_wall_measure_sweep.py`; this is the
        # narrower statement that matters here, since the whole design is that the exporter is
        # an argument precisely so no kernel import is needed.
        src = open(refusals.__file__.replace('.pyc', '.py'), encoding='utf-8').read()
        for forbidden in ('import FreeCAD', 'import Part', 'from FreeCAD', 'from Part'):
            assert forbidden not in src
