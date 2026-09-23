"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for sweep_check.py.

`scaling_family`/`part_id`/`find_stls` are pure path logic. `check_families` operates only
on the `rel` half of its `entries` (the path is never read), so its fixtures are synthetic
relative-path strings rather than real files -- exercising the same logic without the I/O
cost. `check_integrity`/`check_reference` do read real STL files, so those use hand-built
binary STL fixtures. `main()` (argparse wiring) is not covered, consistent with the other
CLI-entry-point modules in this plan.
"""
import struct
from pathlib import Path

import mesh_stats
import sweep_check as sc


def _rel(*parts):
    """An os.sep-joined relative path, exactly what `Path.rglob`/`relative_to` would hand
    `scaling_family`/`part_id` on this platform -- sweep_check's own `.replace(os.sep, '/')`
    is what these tests exist to check, so the fixture must use the real separator."""
    return str(Path(*parts))


# ------------------------------------------------------------
# scaling_family
# ------------------------------------------------------------

def test_scaling_family_of_a_panelled_part_is_u_plus_unit_plus_panel():
    rel = _rel('U_1.0', 'imperial', 'panel_1_8in', 'corner_FX_1.0.stl')
    assert sc.scaling_family(rel) == 'U_1.0/imperial/panel_1_8in'


def test_scaling_family_of_a_metric_panelled_part():
    rel = _rel('U_2.0', 'metric', 'panel_6mm', 'bulkhead.stl')
    assert sc.scaling_family(rel) == 'U_2.0/metric/panel_6mm'


def test_scaling_family_of_a_cowl_part_with_no_panel_level_is_just_the_scale():
    rel = _rel('U_1.0', 'nose_cowl.stl')
    assert sc.scaling_family(rel) == 'U_1.0'


def test_scaling_family_normalizes_os_sep_to_forward_slash():
    rel = _rel('U_1.0', 'imperial', 'panel_1_8in', 'corner.stl')
    assert '\\' not in sc.scaling_family(rel)


# ------------------------------------------------------------
# part_id
# ------------------------------------------------------------

def test_part_id_strips_the_scale_and_panel_prefix():
    name = 'U_2.0__imperial_panel_1_8in__corner_FX_3.0.stl'
    assert sc.part_id(name) == 'corner_FX_3.0.stl'


def test_part_id_takes_only_the_final_path_component():
    rel = _rel('U_2.0', 'imperial', 'panel_1_8in',
              'U_2.0__imperial_panel_1_8in__corner_FX_3.0.stl')
    assert sc.part_id(rel) == 'corner_FX_3.0.stl'


def test_part_id_of_a_name_with_no_double_underscore_is_unchanged():
    assert sc.part_id('nose_cowl.stl') == 'nose_cowl.stl'


# ------------------------------------------------------------
# find_stls
# ------------------------------------------------------------

def _touch(root, *names):
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b'')


def test_find_stls_finds_files_recursively_and_pairs_them_with_a_relative_path(tmp_path):
    _touch(tmp_path, _rel('a', 'part1.stl'), 'part2.stl')
    found = sc.find_stls(tmp_path)
    rels = sorted(rel for _p, rel in found)
    assert rels == sorted([_rel('a', 'part1.stl'), 'part2.stl'])


def test_find_stls_excludes_partial_stl_files(tmp_path):
    _touch(tmp_path, 'done.stl', 'in_progress.partial.stl')
    found = [rel for _p, rel in sc.find_stls(tmp_path)]
    assert found == ['done.stl']


def test_find_stls_returns_real_paths_pointing_at_the_actual_file(tmp_path):
    _touch(tmp_path, 'part.stl')
    [(path, rel)] = sc.find_stls(tmp_path)
    assert path.is_file()
    assert rel == 'part.stl'


# ------------------------------------------------------------
# check_families -- synthetic rel strings only; the path half of `entries` is never read
# ------------------------------------------------------------

def _entries(*rels):
    return [(None, rel) for rel in rels]


def test_check_families_reports_no_shorts_when_every_family_matches(capsys):
    common = ['corner_FX_1.0.stl', 'corner_FX_2.0.stl', 'bulkhead.stl']
    entries = _entries(
        *[_rel('U_1.0', 'metric', 'panel_A', p) for p in common],
        *[_rel('U_1.0', 'imperial', 'panel_B', p) for p in common],
    )
    short = sc.check_families(entries, quiet=False)
    assert short == []
    assert 'every family carries all 3 common parts' in capsys.readouterr().out


def test_check_families_flags_a_family_missing_a_part(capsys):
    common = ['corner_FX_1.0.stl', 'corner_FX_2.0.stl', 'bulkhead.stl']
    full_families = (
        [_rel('U_1.0', 'metric', 'panel_A', p) for p in common]
        + [_rel('U_1.0', 'imperial', 'panel_B', p) for p in common]
        + [_rel('U_2.0', 'metric', 'panel_C', p) for p in common]
    )
    short_family = [_rel('U_2.0', 'imperial', 'panel_D', p)
                    for p in common[:-1]]   # missing bulkhead.stl
    short = sc.check_families(_entries(*full_families, *short_family), quiet=False)
    assert short == ['U_2.0/imperial/panel_D']
    out = capsys.readouterr().out
    assert 'SHORT  U_2.0/imperial/panel_D' in out
    assert 'missing bulkhead.stl' in out


def test_check_families_reports_families_with_extra_parts_as_extra_not_short(capsys):
    common = ['corner_FX_1.0.stl', 'bulkhead.stl']
    families = (
        [_rel('U_1.0', 'metric', 'panel_A', p) for p in common]
        + [_rel('U_1.0', 'imperial', 'panel_B', p) for p in common]
        + [_rel('U_1.0', 'metric', 'panel_0mm', p)
           for p in common + ['cowling_bulkhead.stl']]
    )
    short = sc.check_families(_entries(*families), quiet=False)
    assert short == []
    out = capsys.readouterr().out
    assert 'carry parts beyond the common set of 2' in out


def test_check_families_returns_empty_when_no_family_has_a_panel_level(capsys):
    entries = _entries(_rel('U_1.0', 'nose_cowl.stl'), _rel('U_2.0', 'tail_cowl.stl'))
    assert sc.check_families(entries, quiet=False) == []


def test_check_families_counts_cowl_sets_separately_from_panelled_families(capsys):
    common = ['corner_FX_1.0.stl']
    entries = _entries(
        *[_rel('U_1.0', 'metric', 'panel_A', p) for p in common],
        _rel('U_1.0', 'nose_cowl.stl'),
    )
    sc.check_families(entries, quiet=False)
    out = capsys.readouterr().out
    assert '1 (one U scale + one panel stock each), 1 cowl set(s)' in out


def test_check_families_truncates_short_list_after_twelve(capsys):
    # The "expected" set is the most COMMON set among families, so the full-set families
    # must outnumber the short ones (14 vs. 13) for {a, b} to win as expected rather than
    # the majority collapsing to the short families' own {a} set.
    common = ['a.stl', 'b.stl']
    full = []
    for i in range(14):
        full += [_rel('U_1.0', 'metric', f'panel_full_{i}', p) for p in common]
    shorts = [_rel('U_1.0', 'imperial', f'panel_{i}', 'a.stl') for i in range(13)]
    short = sc.check_families(_entries(*full, *shorts), quiet=False)
    assert len(short) == 13
    out = capsys.readouterr().out
    assert '... 1 more short families' in out


def test_check_families_quiet_suppresses_the_summary_but_not_the_short_lines(capsys):
    common = ['a.stl', 'b.stl']
    full = [_rel('U_1.0', 'metric', 'panel_full', p) for p in common]
    short_fam = [_rel('U_1.0', 'imperial', 'panel_short', 'a.stl')]
    sc.check_families(_entries(*full, *short_fam), quiet=True)
    out = capsys.readouterr().out
    assert 'families  :' not in out
    assert 'SHORT' in out


# ------------------------------------------------------------
# check_integrity / check_reference -- real STL fixtures
# ------------------------------------------------------------

_CUBE_VERTS = {
    0: (0, 0, 0), 1: (1, 0, 0), 2: (1, 1, 0), 3: (0, 1, 0),
    4: (0, 0, 1), 5: (1, 0, 1), 6: (1, 1, 1), 7: (0, 1, 1),
}
_CUBE_TRI_IDX = [
    (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
    (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
]


def _cube_points(scale=1.0):
    return [[(_CUBE_VERTS[i][0] * scale, _CUBE_VERTS[i][1] * scale,
             _CUBE_VERTS[i][2] * scale) for i in tri] for tri in _CUBE_TRI_IDX]


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


def test_check_integrity_reports_a_whole_mesh_as_parsed(tmp_path, capsys):
    path = tmp_path / 'part.stl'
    _write_binary_stl(path, _cube_points())
    stats, failures = sc.check_integrity([(path, 'part.stl')], quiet=False)
    assert failures == []
    assert stats['part.stl']['triangles'] == 12
    assert '1/1 meshes parse as complete' in capsys.readouterr().out


def test_check_integrity_reports_a_truncated_mesh_as_a_failure(tmp_path, capsys):
    path = tmp_path / 'broken.stl'
    _write_binary_stl(path, _cube_points())
    data = path.read_bytes()
    path.write_bytes(data[:-40])
    stats, failures = sc.check_integrity([(path, 'broken.stl')], quiet=False)
    assert stats['broken.stl'] is None
    assert failures[0][0] == 'broken.stl'
    assert 'TRUNCATED  broken.stl' in capsys.readouterr().out


def test_check_integrity_quiet_suppresses_the_summary_but_not_failures(tmp_path, capsys):
    path = tmp_path / 'broken.stl'
    _write_binary_stl(path, _cube_points())
    path.write_bytes(path.read_bytes()[:-40])
    sc.check_integrity([(path, 'broken.stl')], quiet=True)
    out = capsys.readouterr().out
    assert 'meshes parse as complete' not in out
    assert 'TRUNCATED' in out


def test_check_reference_matches_identical_geometry(tmp_path, capsys):
    ref_dir = tmp_path / 'ref'
    out_path = tmp_path / 'out' / 'U_1.0__part.stl'
    ref_path = ref_dir / 'U_1.0__part.stl'
    _write_binary_stl(out_path, _cube_points())
    _write_binary_stl(ref_path, _cube_points())
    stats = {'U_1.0__part.stl': mesh_stats.mesh_stats(out_path)}

    mismatches, missing, only_in_ref = sc.check_reference(
        stats, ref_dir, mesh_stats.VOLUME_TOL, quiet=False)
    assert (mismatches, missing, only_in_ref) == ([], [], [])
    assert '1/1 parts match ref' in capsys.readouterr().out


def test_check_reference_reports_a_part_missing_from_the_reference(tmp_path, capsys):
    ref_dir = tmp_path / 'ref'
    ref_dir.mkdir()
    out_path = tmp_path / 'out' / 'U_1.0__part.stl'
    _write_binary_stl(out_path, _cube_points())
    stats = {'U_1.0__part.stl': mesh_stats.mesh_stats(out_path)}

    mismatches, missing, only_in_ref = sc.check_reference(
        stats, ref_dir, mesh_stats.VOLUME_TOL, quiet=False)
    assert missing == ['U_1.0__part.stl']
    assert 'NOT IN REFERENCE  U_1.0__part.stl' in capsys.readouterr().out


def test_check_reference_reports_a_part_only_in_the_reference(tmp_path, capsys):
    ref_dir = tmp_path / 'ref'
    ref_path = ref_dir / 'U_1.0__extra.stl'
    _write_binary_stl(ref_path, _cube_points())

    mismatches, missing, only_in_ref = sc.check_reference(
        {}, ref_dir, mesh_stats.VOLUME_TOL, quiet=False)
    assert only_in_ref == ['U_1.0__extra.stl']
    assert 'MISSING FROM OUTPUT  U_1.0__extra.stl' in capsys.readouterr().out


def test_check_reference_reports_a_geometry_mismatch(tmp_path, capsys):
    ref_dir = tmp_path / 'ref'
    out_path = tmp_path / 'out' / 'U_1.0__part.stl'
    ref_path = ref_dir / 'U_1.0__part.stl'
    _write_binary_stl(out_path, _cube_points(scale=2.0))
    _write_binary_stl(ref_path, _cube_points(scale=1.0))
    stats = {'U_1.0__part.stl': mesh_stats.mesh_stats(out_path)}

    mismatches, _missing, _only = sc.check_reference(
        stats, ref_dir, mesh_stats.VOLUME_TOL, quiet=False)
    assert mismatches[0][0] == 'U_1.0__part.stl'
    assert 'DIFFERS  U_1.0__part.stl' in capsys.readouterr().out


def test_check_reference_reports_an_unreadable_reference_without_crashing(tmp_path, capsys):
    ref_dir = tmp_path / 'ref'
    out_path = tmp_path / 'out' / 'U_1.0__part.stl'
    ref_path = ref_dir / 'U_1.0__part.stl'
    _write_binary_stl(out_path, _cube_points())
    _write_binary_stl(ref_path, _cube_points())
    ref_path.write_bytes(ref_path.read_bytes()[:-40])
    stats = {'U_1.0__part.stl': mesh_stats.mesh_stats(out_path)}

    mismatches, _missing, _only = sc.check_reference(
        stats, ref_dir, mesh_stats.VOLUME_TOL, quiet=False)
    assert 'reference unreadable' in mismatches[0][1]


def test_check_reference_truncates_mismatch_list_after_ten(tmp_path, capsys):
    ref_dir = tmp_path / 'ref'
    stats = {}
    for i in range(11):
        name = f'U_1.0__part{i}.stl'
        _write_binary_stl(tmp_path / 'out' / name, _cube_points(scale=2.0))
        _write_binary_stl(ref_dir / name, _cube_points(scale=1.0))
        stats[name] = mesh_stats.mesh_stats(tmp_path / 'out' / name)

    mismatches, _missing, _only = sc.check_reference(
        stats, ref_dir, mesh_stats.VOLUME_TOL, quiet=False)
    assert len(mismatches) == 11
    out = capsys.readouterr().out
    assert out.count('DIFFERS') == 10
    assert '... 1 more differing parts' in out
