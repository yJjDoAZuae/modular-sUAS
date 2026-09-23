"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for compare_backends.py.

The pure name/kind-parsing functions (`u_of`, `kind_of`, `bbox_tol`, `sweeps_for`,
`_drivers_for`, `split_failures`, `used_freecad`) get direct unit tests. `wanted_parts` is
exercised against the real sweep machinery restricted to one fast kind, exactly as
`capture()` is in test_scad_snapshot.py/test_params_snapshot.py. `compare`/`report_builds`
are tested against hand-built STL/`.stl.json`/`.stl.scad` trees covering every kind category
(exact, filleted, freeform, shelled) and every skip/failure branch. `unusable_dirs`/
`ensure_wiped` are tested against real filesystem state, with the delete-pending case
simulated by faking `shutil.rmtree` rather than actually holding a Windows handle open.
`render()`/`main()` (real OpenSCAD/FreeCAD subprocess orchestration) are not covered,
consistent with the other CLI-entry-point/render modules in this plan.
"""
import struct
from pathlib import Path

import compare_backends as cb
import fuselage_variants as fv
import pytest

# ------------------------------------------------------------
# sweeps_for / _drivers_for
# ------------------------------------------------------------

def test_sweeps_for_none_returns_every_row_unchanged():
    assert cb.sweeps_for(None) == cb.SWEEPS


def test_sweeps_for_narrows_to_the_given_kinds_in_table_order():
    result = cb.sweeps_for({'bulkhead', 'tail'})
    assert [k for k, _d, _a in result] == ['bulkhead', 'tail']


def test_sweeps_for_unknown_kind_returns_nothing():
    assert cb.sweeps_for({'no_such_kind'}) == ()


def test_drivers_for_dedupes_the_three_nose_kinds_into_one_driver_call():
    all_drivers = cb._drivers_for(None)
    nose_drivers = [d for d in all_drivers if d[0] == 'run_nose_parametric_sweep']
    assert len(nose_drivers) == 1


def test_drivers_for_dedupes_the_two_tail_kinds_into_one_driver_call():
    all_drivers = cb._drivers_for(None)
    tail_drivers = [d for d in all_drivers if d[0] == 'run_tail_parametric_sweep']
    assert len(tail_drivers) == 1


def test_drivers_for_returns_five_distinct_drivers_for_every_kind():
    assert len(cb._drivers_for(None)) == 5


def test_drivers_for_narrowed_to_one_kind_returns_one_driver():
    assert len(cb._drivers_for({'corner'})) == 1


def test_drivers_for_unknown_kind_returns_nothing():
    assert cb._drivers_for({'no_such_kind'}) == []


# ------------------------------------------------------------
# bbox_tol / u_of / kind_of
# ------------------------------------------------------------

def test_bbox_tol_below_the_floor_is_clamped():
    assert cb.bbox_tol(0.5) == pytest.approx(cb.BBOX_TOL_PER_U)


def test_bbox_tol_scales_above_the_floor():
    assert cb.bbox_tol(2.5) == pytest.approx(cb.BBOX_TOL_PER_U * 2.5)


def test_u_of_reads_the_scale_from_the_filename():
    assert cb.u_of('U_1.5__imperial_panel_1_8in__corner_FX_1.0.stl') == 1.5


def test_u_of_accepts_an_integer_scale_with_no_decimal():
    assert cb.u_of('U_2__metric_panel_6mm__bulkhead.stl') == 2.0


def test_u_of_raises_when_the_name_carries_no_u():
    with pytest.raises(ValueError, match='cannot read U from part name'):
        cb.u_of('bulkhead_no_scale_prefix.stl')


def test_kind_of_prefers_boom_bulkhead_over_the_shorter_bulkhead_substring():
    assert cb.kind_of('U_1.0__panel_A__boom_bulkhead_offset_single.stl') == 'boom_bulkhead'


def test_kind_of_matches_plain_bulkhead_when_boom_bulkhead_is_absent():
    assert cb.kind_of('U_1.0__panel_A__bulkhead_type_end.stl') == 'bulkhead'


def test_kind_of_prefers_nose_cowl_shell_over_nose_cowl():
    assert cb.kind_of('U_1.0__nose_cowl_shell.stl') == 'nose_cowl_shell'


def test_kind_of_prefers_tail_shell_over_tail():
    assert cb.kind_of('U_1.0__tail_shell.stl') == 'tail_shell'


def test_kind_of_matches_plain_tail_when_tail_shell_is_absent():
    assert cb.kind_of('U_1.0__tail_plate.stl') == 'tail'


def test_kind_of_returns_other_for_an_unrecognized_name():
    assert cb.kind_of('U_1.0__something_unrelated.stl') == 'other'


# ------------------------------------------------------------
# used_freecad
# ------------------------------------------------------------

def test_used_freecad_true_when_the_stl_json_sidecar_exists(tmp_path):
    stl = tmp_path / 'part.stl'
    stl.write_bytes(b'')
    (tmp_path / 'part.stl.json').write_text('{}')
    assert cb.used_freecad(stl) is True


def test_used_freecad_false_when_there_is_no_sidecar(tmp_path):
    stl = tmp_path / 'part.stl'
    stl.write_bytes(b'')
    assert cb.used_freecad(stl) is False


# ------------------------------------------------------------
# split_failures
# ------------------------------------------------------------

def test_split_failures_separates_unported_refusals_from_genuine_breaks():
    unported_exc = fv.UnportedPart('no generator for this kind')
    broken_exc = RuntimeError('CGAL kernel error')
    failures = [
        (('some/dir/part_a.scad',), unported_exc),
        (('some/dir/part_b.scad',), broken_exc),
    ]
    unported, broken = cb.split_failures(failures)
    assert unported == {'part_a.stl'}
    assert broken == [(('some/dir/part_b.scad',), broken_exc)]


def test_split_failures_with_no_failures_returns_empty_results():
    assert cb.split_failures([]) == (set(), [])


# ------------------------------------------------------------
# wanted_parts -- real sweep machinery, restricted to one fast kind
# ------------------------------------------------------------

def test_wanted_parts_restores_solid_render_and_freecad_render(monkeypatch):
    original_solid = fv.solid_render
    original_freecad = fv.freecad_render
    cb.wanted_parts(None, {'corner'})
    assert fv.solid_render is original_solid
    assert fv.freecad_render is original_freecad


def test_wanted_parts_collects_real_corner_variants_keyed_by_kind():
    collected = cb.wanted_parts(None, {'corner'})
    assert len(collected) > 0
    assert all(kind == 'corner' for kind in collected.values())


def test_wanted_parts_per_kind_caps_the_sample_and_spreads_across_the_range():
    full = cb.wanted_parts(None, {'corner'})
    sampled = cb.wanted_parts(2, {'corner'})
    assert len(sampled) <= 2
    assert set(sampled).issubset(set(full))


# ------------------------------------------------------------
# unusable_dirs / ensure_wiped -- real filesystem state
# ------------------------------------------------------------

def test_unusable_dirs_reports_nothing_for_an_ordinary_readable_tree(tmp_path):
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'file.txt').write_text('x')
    assert cb.unusable_dirs(tmp_path) == []


def test_unusable_dirs_reports_a_nonexistent_root_as_unusable(tmp_path):
    missing = tmp_path / 'does_not_exist'
    assert cb.unusable_dirs(missing) == [missing]


def test_ensure_wiped_removes_an_ordinary_directory_without_raising(tmp_path):
    target = tmp_path / 'scratch'
    target.mkdir()
    (target / 'file.txt').write_text('x')
    cb.ensure_wiped(target, 'test tree')
    assert not target.exists()


def test_ensure_wiped_raises_when_the_tree_survives_the_wipe(tmp_path, monkeypatch):
    target = tmp_path / 'stuck'
    target.mkdir()
    (target / 'file.txt').write_text('x')
    monkeypatch.setattr(cb.shutil, 'rmtree', lambda *a, **k: None)   # simulate a stuck wipe

    with pytest.raises(SystemExit) as exc_info:
        cb.ensure_wiped(target, 'freecad output')
    message = str(exc_info.value)
    assert 'refusing to render' in message
    assert 'freecad output' in message
    # An ordinary readable directory that merely failed to delete is not the delete-pending
    # case -- the message must say so rather than claim a Windows handle is held.
    assert 'not the' in message and 'delete-pending' in message


# ------------------------------------------------------------
# report_builds -- real filesystem sidecar layout
# ------------------------------------------------------------

def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'')


def test_report_builds_classifies_built_fell_back_missing_and_refused(tmp_path, capsys):
    b_dir = tmp_path / 'freecad'
    _touch(b_dir / 'built1.stl')
    (b_dir / 'built1.stl.json').write_text('{}')
    _touch(b_dir / 'fellback1.stl')
    (b_dir / 'fellback1.stl.scad').write_text('// scad')
    # missing2.stl deliberately not created
    # refused1.stl deliberately not created either, and is named in `unported`

    wanted = {
        'built1.stl': 'corner',
        'fellback1.stl': 'bulkhead',
        'missing1.stl': 'corner',
        'refused1.stl': 'tail',
    }
    code = cb.report_builds(b_dir, wanted, unported={'refused1.stl'})
    out = capsys.readouterr().out

    assert code == 1
    assert 'built by FreeCAD' in out and 'corner=1' in out
    assert 'not ported (refused)' in out and 'tail=1' in out
    assert 'fell back to OpenSCAD' in out and 'bulkhead=1' in out
    assert 'DID NOT BUILD' in out
    assert '1 of 2 PORTED PART(S) DO NOT BUILD' in out
    assert 'UNEXPECTED' in out   # fell_back warning block
    assert 'UNBUILDABLE' in out


def test_report_builds_reports_success_when_nothing_is_missing(tmp_path, capsys):
    b_dir = tmp_path / 'freecad'
    _touch(b_dir / 'built1.stl')
    (b_dir / 'built1.stl.json').write_text('{}')

    code = cb.report_builds(b_dir, {'built1.stl': 'corner'}, unported=set())
    out = capsys.readouterr().out

    assert code == 0
    assert 'EVERY PORTED PART BUILDS' in out


# ------------------------------------------------------------
# compare -- hand-built STL/.stl.json trees across every kind category
# ------------------------------------------------------------

_VERTS = {
    0: (0, 0, 0), 1: (1, 0, 0), 2: (1, 1, 0), 3: (0, 1, 0),
    4: (0, 0, 1), 5: (1, 0, 1), 6: (1, 1, 1), 7: (0, 1, 1),
}
_TRI_IDX = [
    (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
    (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
]


def _points(verts):
    return [[verts[i] for i in tri] for tri in _TRI_IDX]


def _write_binary_stl(path, triangles):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('wb') as f:
        f.write(b'test'.ljust(80, b'\0'))
        f.write(struct.pack('<I', len(triangles)))
        for tri in triangles:
            f.write(struct.pack('<3f', 0.0, 0.0, 0.0))
            for point in tri:
                f.write(struct.pack('<3f', *point))
            f.write(struct.pack('<H', 0))


def _cube(offset=(0.0, 0.0, 0.0)):
    ox, oy, oz = offset
    shifted = {i: (x + ox, y + oy, z + oz) for i, (x, y, z) in _VERTS.items()}
    return _points(shifted)


def _dented_cube(delta):
    """The unit cube with corner 6 pulled inward along z by `delta`.

    Every other vertex at z = 1 (indices 4, 5, 7) is untouched, so the bounding box is
    exactly unchanged (verified numerically before use) while the enclosed volume shrinks --
    an isolated, bbox-free volume difference to test the volume criteria against, at any
    chosen magnitude, without also perturbing the bbox check.
    """
    verts = dict(_VERTS)
    verts[6] = (1, 1, 1 - delta)
    return _points(verts)


def _mark_freecad_built(stl_path):
    Path(str(stl_path) + '.json').write_text('{}')


def _setup(tmp_path, kind, a_tris, b_tris, mark_built=True, name='U_1.0__part.stl'):
    a_dir, b_dir = tmp_path / 'openscad', tmp_path / 'freecad'
    a_path, b_path = a_dir / name, b_dir / name
    _write_binary_stl(a_path, a_tris)
    _write_binary_stl(b_path, b_tris)
    if mark_built:
        _mark_freecad_built(b_path)
    return a_dir, b_dir, {name: kind}, name


def test_compare_agrees_on_identical_geometry_for_an_exact_kind(tmp_path, capsys):
    a_dir, b_dir, wanted, name = _setup(tmp_path, 'corner', _cube(), _cube())
    code = cb.compare(a_dir, b_dir, wanted, cb.TOL_EXACT, cb.TOL_FILLETED)
    out = capsys.readouterr().out
    assert code == 0
    assert 'BACKENDS AGREE' in out
    assert 'compared 1 part(s)' in out


def test_compare_fails_an_exact_kind_outside_a_tight_tolerance(tmp_path, capsys):
    a_dir, b_dir, wanted, name = _setup(
        tmp_path, 'corner', _cube(), _dented_cube(0.01))
    code = cb.compare(a_dir, b_dir, wanted, tol_exact=1e-6, tol_filleted=cb.TOL_FILLETED)
    out = capsys.readouterr().out
    assert code == 1
    assert 'BACKENDS DISAGREE' in out
    assert 'volume' in out


def test_compare_admits_the_same_delta_under_a_looser_filleted_tolerance(tmp_path, capsys):
    """The same volume delta that fails the exact-kind test above must pass once the kind
    is judged as filleted, because compare() selects tol_filleted for FILLETED_KINDS -- the
    whole reason the two-tier tolerance exists (OQ-DES-B9)."""
    a_dir, b_dir, wanted, name = _setup(
        tmp_path, 'bulkhead', _cube(), _dented_cube(0.01))
    code = cb.compare(a_dir, b_dir, wanted, tol_exact=1e-6, tol_filleted=0.5)
    out = capsys.readouterr().out
    assert code == 0
    assert 'BACKENDS AGREE' in out


def test_compare_fails_on_a_bbox_shift_alone_even_with_identical_volume(tmp_path, capsys):
    """A rigid translation leaves volume exactly unchanged but moves every bbox corner by
    the same amount -- isolating the bounding-box criterion from the volume criterion."""
    a_dir, b_dir, wanted, name = _setup(
        tmp_path, 'corner', _cube(), _cube(offset=(0.01, 0.0, 0.0)))
    code = cb.compare(a_dir, b_dir, wanted, cb.TOL_EXACT, cb.TOL_FILLETED)
    out = capsys.readouterr().out
    assert code == 1
    assert 'bounding box moved' in out


def test_compare_freeform_kind_uses_the_module_freeform_tolerance(tmp_path, capsys):
    a_dir, b_dir, wanted, name = _setup(
        tmp_path, 'nose_cowl', _cube(), _dented_cube(0.1))   # -3.3% >> TOL_FREEFORM
    code = cb.compare(a_dir, b_dir, wanted, cb.TOL_EXACT, cb.TOL_FILLETED)
    out = capsys.readouterr().out
    assert code == 1
    assert 'volume' in out


def test_compare_shelled_kind_uses_the_offset_criterion_not_relative_volume(tmp_path, capsys):
    a_dir, b_dir, wanted, name = _setup(
        tmp_path, 'nose_cowl_shell', _cube(), _dented_cube(0.2))   # offset 1.1e-4 > TOL_OFFSET
    code = cb.compare(a_dir, b_dir, wanted, cb.TOL_EXACT, cb.TOL_FILLETED)
    out = capsys.readouterr().out
    assert code == 1
    assert 'volume offset' in out


def test_compare_shelled_kind_passes_when_offset_is_within_tolerance(tmp_path, capsys):
    a_dir, b_dir, wanted, name = _setup(
        tmp_path, 'nose_cowl_shell', _cube(), _cube())   # identical: offset 0
    code = cb.compare(a_dir, b_dir, wanted, cb.TOL_EXACT, cb.TOL_FILLETED)
    assert code == 0


def test_compare_treats_missing_area_for_a_shelled_kind_as_a_failure_not_a_pass(
    tmp_path, capsys, monkeypatch
):
    """`offset is None` (a measurement predating the `area` key, per volume_offset's own
    docstring) must not fall back to assuming agreement -- compare() explicitly refuses to
    substitute a rule this kind was moved off. Forced via monkeypatch: constructing a real
    STL pair that computes an area-less mesh_stats() result is not possible through the
    module's own logic (a fresh mesh_stats() call always includes the key today), so this
    isolates the one branch that exists for older, differently-shaped data."""
    a_dir, b_dir, wanted, name = _setup(
        tmp_path, 'nose_cowl_shell', _cube(), _cube())
    import mesh_stats
    monkeypatch.setattr(mesh_stats, 'volume_offset', lambda *a, **k: None)
    code = cb.compare(a_dir, b_dir, wanted, cb.TOL_EXACT, cb.TOL_FILLETED)
    out = capsys.readouterr().out
    assert code == 1
    assert 'no surface area recorded' in out


def test_compare_reports_a_part_not_produced_by_one_side(tmp_path, capsys):
    a_dir, b_dir = tmp_path / 'openscad', tmp_path / 'freecad'
    name = 'U_1.0__part.stl'
    _write_binary_stl(b_dir / name, _cube())
    _mark_freecad_built(b_dir / name)
    # a_dir/name deliberately not created

    code = cb.compare(a_dir, b_dir, {name: 'corner'}, cb.TOL_EXACT, cb.TOL_FILLETED)
    out = capsys.readouterr().out
    assert code == 1
    assert 'not produced by openscad' in out


def test_compare_reports_an_unreadable_mesh_without_crashing(tmp_path, capsys):
    a_dir, b_dir, wanted, name = _setup(tmp_path, 'corner', _cube(), _cube())
    data = (a_dir / name).read_bytes()
    (a_dir / name).write_bytes(data[:-40])   # truncate the openscad side

    code = cb.compare(a_dir, b_dir, wanted, cb.TOL_EXACT, cb.TOL_FILLETED)
    out = capsys.readouterr().out
    assert code == 1
    assert 'unreadable' in out


def test_compare_skips_a_part_that_fell_back_to_openscad_without_failing_it(tmp_path, capsys):
    a_dir, b_dir, wanted, name = _setup(
        tmp_path, 'corner', _cube(), _cube(), mark_built=False)   # no .stl.json sidecar

    code = cb.compare(a_dir, b_dir, wanted, cb.TOL_EXACT, cb.TOL_FILLETED)
    out = capsys.readouterr().out
    assert code == 1   # nothing was actually compared
    assert 'NOTHING COMPARED' in out
    assert 'FAIL' not in out


def test_compare_skips_an_unported_part_without_failing_it(tmp_path, capsys):
    a_dir, b_dir = tmp_path / 'openscad', tmp_path / 'freecad'
    name = 'U_1.0__part.stl'
    # Neither side has a mesh for it -- unported means FreeCAD was never asked to build it.
    code = cb.compare(a_dir, b_dir, {name: 'corner'}, cb.TOL_EXACT, cb.TOL_FILLETED,
                      unported={name})
    out = capsys.readouterr().out
    assert code == 1   # nothing compared, but not a disagreement
    assert 'NOTHING COMPARED' in out
    assert 'no FreeCAD generator' in out


def test_compare_reports_agreement_alongside_a_skipped_unported_part(tmp_path, capsys):
    a_dir, b_dir, wanted, name = _setup(tmp_path, 'corner', _cube(), _cube())
    unported_name = 'U_1.0__other_part.stl'
    wanted[unported_name] = 'tail'

    code = cb.compare(a_dir, b_dir, wanted, cb.TOL_EXACT, cb.TOL_FILLETED,
                      unported={unported_name})
    out = capsys.readouterr().out
    assert code == 0
    assert 'BACKENDS AGREE' in out
    assert 'no FreeCAD generator' in out
