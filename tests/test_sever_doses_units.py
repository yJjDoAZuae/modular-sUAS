"""The dose harness's `--target` option, and the unit boundary it sits on.

**Why this file is structural rather than behavioral.** `sever_doses` imports FreeCAD at module
scope, so it cannot be imported here at all; the same constraint `test_wall_measure_refusals.py`
works under. These read the source, which is enough for the defect they exist to catch: a value
crossing a unit boundary without being converted is visible in the text of the call.

**The defect, recorded 2026-11-13.** IP-FC-163 converted the construction to SI. `--floor` was
converted at the CLI and `--target` was not, so `target_station` compared a millimeter target
against a station set in meters. It missed by a factor of a thousand, and the refusal it produced
blamed the station floor -- advice that is wrong in exactly this case and sent a reader to
re-pass a flag they had already passed. The module's own usage example still gave millimeters,
so the documented command could not work.
"""
import io
import os

SEVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'src', 'Fuselage', 'freecad', 'sever_doses.py')


def _source():
    with io.open(SEVER, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


class TestTheTargetCrossesTheUnitBoundary(object):

    def test_the_cli_converts_the_target_to_meters(self):
        """`--floor` has always done this; `--target` did not."""
        assert 'want_z_m=None if target is None else si.m(float(target))' in _source()

    def test_the_floor_is_still_converted_too(self):
        """Guards the fix from being 'applied' by making both wrong in the same way."""
        assert 'si.m(float(floor_mm))' in _source()

    def test_the_comparison_names_its_units(self):
        src = _source()
        assert 'def target_station(kept, z_lo, z_hi, notch_edges, want_m=None, tol_m=1.0e-6):' \
            in src

    def test_no_unitless_target_name_survives(self):
        """`want_z` and `want=` are the pre-conversion names. Either one present means a call
        site was missed, which is how this defect existed in the first place."""
        src = _source()
        assert 'want_z=' not in src
        assert 'want=' not in src


class TestTheRefusalDiagnosesTheRightThing(object):

    def test_the_distance_is_reported_in_the_unit_it_claims(self):
        """It printed a meters difference labeled 'mm', so '283.6951365 mm away' was really
        283.7 m -- the one number that would have named the cause, stating the opposite."""
        src = _source()
        assert 'si.mm(want_m), len(kept), si.mm(near_m), si.mm(off_m), why' in src

    def test_the_floor_advice_is_conditional(self):
        """Offering it unconditionally is what made the refusal misleading: the floor cannot
        explain a target outside the patch, and saying it can costs the reader a run."""
        src = _source()
        # Matched in fragments: the literal is wrapped across two source lines, and this
        # test reads source rather than running the branch.
        assert 'outside the patch' in src
        assert 'setting can produce it' in src
        assert '`--target` is millimeters' in src


class TestTheUsageExampleIsRunnable(object):

    def test_the_documented_target_is_the_millimeter_value(self):
        """The example is the first thing anyone runs, and it was unrunnable: it gave the
        millimeter station while the code wanted meters."""
        assert '--pass --target=-283.9951339' in _source()


class TestTheProbeRecordReadsAnAttributeThatExists(object):
    """`_moved` runs on every outcome the harness records, so a wrong attribute name here is
    not a degraded record -- it is no record at all, raised after the build has already been
    paid for. `Probe.__slots__` makes it raise rather than read as empty, which is the one
    mercy: the failure is loud, it just arrives 70 minutes late.

    Found 2026-11-13: it read `probe.stations`, renamed to `stations_m` by IP-FC-163.
    """

    def test_it_reads_the_attribute_probe_declares(self):
        src = _source()
        assert 'probe.stations_m' in src
        assert 'probe.stations[' not in src
        assert 'set(probe.stations)' not in src

    def test_probe_still_declares_that_attribute(self):
        """Ties this to the real class rather than to the assertion above, so a second rename
        fails here instead of in a build."""
        probe_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools', 'wall_measure', 'probe.py')
        with io.open(probe_py, 'r', encoding='utf-8', newline='') as fh:
            assert "'stations_m'" in fh.read()

    def test_the_record_keys_name_their_unit(self):
        """The record mixes `delta_mm` with these, and an unsuffixed `station` holding meters
        beside a `delta_mm` holding millimeters is the same defect one layer down."""
        src = _source()
        assert "'station_mm'" in src
        assert "'distinct_stations_mm'" in src

    def test_the_record_converts_rather_than_storing_si(self):
        assert 'si.mm(z_m) for z_m in probe.stations_m' in _source()


class TestTheOverhangAngleReachesTheConstructionInRadians(object):
    """`shell_solid` takes `overhang_rad`; the parameter sheet states degrees. The harness
    builds its own parameters rather than going through `cowl.from_flat`, so it owns the
    conversion -- and it was not doing it.

    Found 2026-11-13, and it had stopped the harness working entirely: P1 compared real radians
    against 35 of them, so every dose refused before any geometry was built. The tell was in the
    refusal itself, which printed `overhang_angle_from_bed = 2005.35` -- 35 radians rendered as
    degrees. A guard whose threshold is 57.3 times too large rejects everything, which reads as
    a part that cannot be built rather than as a broken check.
    """

    def test_the_harness_converts_degrees_to_radians(self):
        assert "si.deg_to_rad(float(params.get('overhang_angle_from_bed')))" in _source()

    def test_what_reaches_shell_solid_is_named_for_its_unit(self):
        src = _source()
        assert 't_m, overhang_rad, mirrors' in src
        assert 't_m, overhang, mirrors' not in src

    def test_the_sheet_value_is_degrees(self):
        """Stated here so the conversion's direction is pinned by something other than itself."""
        cowl_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'src', 'Fuselage', 'freecad', 'cowl.py')
        with io.open(cowl_py, 'r', encoding='utf-8', newline='') as fh:
            cowl = fh.read()
        assert "ANGLE_ROWS = ('overhang_angle_from_bed',)" in cowl

    def test_thirty_five_radians_is_the_number_that_was_printed(self):
        """Keeps the diagnostic arithmetic on record: a limit reported as 2005.35 deg is 35 rad,
        so this exact symptom identifies this exact defect if it reappears anywhere else."""
        import math
        assert round(math.degrees(35.0), 2) == 2005.35


class TestTheRefusalEvidenceIsActuallyWritten(object):
    """Two ways a refusal's evidence was being lost after the build had paid for it."""

    def test_the_exporter_handles_geometry_not_only_topology(self):
        """`Unconverged` carries the fitted surface for the pre-cut budget refusal, and a
        `Part.BSplineSurface` has no `exportBrep`. That is the refusal this harness actually
        produces, so the unhandled case was the common one."""
        src = _source()
        assert 'def _export_brep(shape, path):' in src
        assert "hasattr(shape, 'toShape')" in src
        assert 'lambda shape, path: shape.exportBrep(path)' not in src

    def test_the_rounds_data_is_written_to_the_record(self):
        """The exception grew the field and nothing persisted it, so a refusal carrying the
        per-interval list still produced a record without it."""
        src = _source()
        assert "rec['rounds'] = _rounds(exc)" in src
        assert 'def _rounds(exc):' in src

    def test_the_rounds_record_is_in_millimeters(self):
        src = _source()
        for key in ("'worst_mm'", "'worst_z_mm'", "'z_lo_mm'", "'z_hi_mm'", "'gap_mm'"):
            assert key in src, key

    def test_an_exception_without_rounds_records_an_empty_list(self):
        """Most refusals are not the post-cut pass's, so this is the ordinary case and must not
        raise on its way to being empty."""
        assert "getattr(exc, 'rounds', ()) or ()" in _source()


class TestTheDoseReachesTheContourInMeters(object):
    """The defect behind the 18.49 mm refusal. `fit_response.nudge` takes `delta_m`; the dose is
    quoted in millimeters; the hook passed one as the other, so a 0.03 mm dose moved the row
    30 mm and the construction responded correctly to a perturbation a thousand times larger
    than the one being studied.

    The tell, for next time: the excursion sat exactly on the displaced station, and its size
    over the dose was close to 1000.
    """

    def test_the_hook_converts_the_dose_once_outside_the_row_loop(self):
        src = _source()
        assert 'def probe_for(delta_mm, target_z_m, normals, tol_m=1.0e-6):' in src
        assert 'delta_m = si.m(delta_mm)' in src

    def test_nudge_is_handed_the_meter_value(self):
        src = _source()
        assert 'fr.nudge(pts, delta_m, center=(0.0, 0.0))' in src
        assert 'fr.nudge(pts, delta,' not in src

    def test_nudge_really_takes_meters(self):
        """Pins the other side of the boundary, so a future change to `nudge` that made it take
        millimeters would fail here rather than silently undo this fix."""
        fr_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'src', 'Fuselage', 'tools', 'wall_measure', 'fit_response.py')
        with io.open(fr_py, 'r', encoding='utf-8', newline='') as fh:
            assert 'def nudge(pts, delta_m, center=None):' in fh.read()

    def test_a_millimeter_dose_moves_a_point_by_that_many_millimeters(self):
        """Behavioral, through the real `nudge`, which is kernel-free: 0.03 mm at radius 0.1 m
        must move the point 3e-5 m, not 0.03 m."""
        import sys
        tools = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'src', 'Fuselage', 'tools')
        if tools not in sys.path:
            sys.path.insert(0, tools)
        from wall_measure import fit_response as fr
        moved = fr.nudge([(0.1, 0.0)], 0.03 * 1.0e-3, center=(0.0, 0.0))
        assert abs(moved[0][0] - 0.10003) < 1e-12


class TestTheRingScanSlicesInMeters(object):
    """`ring_state_at` handed millimeters to `_slice_wires`, which takes meters since IP-FC-163.

    Every scan station was sliced a thousand times outside the part and came back with no wires,
    so the control build of 2026-11-13 read 150 of 151 stations `unreadable`. The one it read as
    an annulus was z = -0.0016 mm, which the double conversion moved to -1.6 mm -- still inside.
    """

    def test_the_station_is_meters_end_to_end(self):
        src = _source()
        assert 'def ring_state_at(wall, z_m):' in src
        assert 'ci._slice_wires(wall, z_m)' in src
        assert 'ring_state_at(wall, z_m)' in src
        assert 'ring_state_at(wall, si.mm(' not in src

    def test_slice_wires_really_takes_meters(self):
        ci_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'src', 'Fuselage', 'freecad', 'cowl_interior.py')
        with io.open(ci_py, 'r', encoding='utf-8', newline='') as fh:
            src = fh.read()
        assert 'def _slice_wires(shape, z_m):' in src
        assert 'si.mm(z_m))' in src


class TestTheRibResidueIsReadUnderItsRealKey(object):
    """`cavity` writes `rib_residue_m3`; the harness read `rib_residue`, which no longer exists,
    so every record carried `rib_residue: null` and the table printed `--`."""

    def _ci(self):
        ci_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'src', 'Fuselage', 'freecad', 'cowl_interior.py')
        with io.open(ci_py, 'r', encoding='utf-8', newline='') as fh:
            return fh.read()

    def test_cavity_writes_the_m3_key(self):
        assert 'report.update(rib_residue_m3=rib_residue_m3,' in self._ci()

    def test_the_harness_reads_it_and_converts_once(self):
        src = _source()
        assert "report.get('rib_residue')" not in src
        assert "report['rib_residue']" not in src
        assert "report['rib_residue_m3'] * si.MM3_PER_M3" in src


class TestTheControlKeepsItsCavity(object):
    """IP-FC-169 qualifies a rib-cut detector against a known-good cavity, and the control's
    finished wall cannot be turned back into one."""

    def test_cavity_hands_the_cut_cavity_out(self):
        ci_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'src', 'Fuselage', 'freecad', 'cowl_interior.py')
        with io.open(ci_py, 'r', encoding='utf-8', newline='') as fh:
            assert 'rib_tool=tool, cavity_shape=solid)' in fh.read()

    def test_the_harness_saves_it_for_the_control(self):
        src = _source()
        assert "rec['cavity_path'] = _save_wall(report['cavity_shape']" in src
