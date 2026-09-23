"""IP-TEST-6 (doc/implementation/test_coverage.md): unit tests for sweep_variant_sets.py.

A real run of this sweep takes about 2.5 hours (the module's own docstring) -- `run_pair`'s
`dvs.build_set` call and `main`'s loop over `run_pair` are always faked out here, the same
"fake the expensive step, keep the orchestration real" approach used for every batch-job
module in this plan. `all_pairs` runs for real against the real `panel_variants.csv`/
`bulkhead_size_variants.csv` axes, and `run_pair`'s manifest-skip/force logic and JSON
structure are checked against real files under `tmp_path`.
"""
import json
from pathlib import Path

import draw_variant_set as dvs
import freecad_render
import fuselage_variants as fv
import sweep_variant_sets as svs

# ------------------------------------------------------------
# all_pairs
# ------------------------------------------------------------

def test_all_pairs_matches_the_documented_8x9_grid():
    pairs = svs.all_pairs()
    assert len(pairs) == 72


def test_all_pairs_has_no_duplicate_u_panel_combinations():
    pairs = svs.all_pairs()
    assert len(pairs) == len(set(pairs))


def test_all_pairs_matches_the_real_shared_axes():
    expected = {(p['U'], p['panel_name']) for p in fv.family_combinations('bulkhead')}
    assert set(svs.all_pairs()) == expected


# ------------------------------------------------------------
# run_pair -- dvs.build_set faked, manifest I/O real
# ------------------------------------------------------------

def test_run_pair_skips_when_a_manifest_already_exists_and_force_is_false(tmp_path, monkeypatch):
    the_dir = Path(dvs.pair_dir(str(tmp_path), 1.0, '3/16in'))
    the_dir.mkdir(parents=True)
    (the_dir / svs.MANIFEST_NAME).write_text('{}')

    called = []
    monkeypatch.setattr(dvs, 'build_set', lambda *a, **k: called.append(1) or ([], []))
    result = svs.run_pair(1.0, '3/16in', str(tmp_path), 'freecadcmd.exe', force=False)
    assert result is None
    assert called == []


def test_run_pair_redoes_the_pair_when_force_is_true_even_with_a_manifest_present(
    tmp_path, monkeypatch
):
    the_dir = Path(dvs.pair_dir(str(tmp_path), 1.0, '3/16in'))
    the_dir.mkdir(parents=True)
    (the_dir / svs.MANIFEST_NAME).write_text('{"stale": true}')

    monkeypatch.setattr(dvs, 'build_set',
                        lambda *a, **k: ([('corner', '3/16in')], [('boom', 'not ported')]))
    result = svs.run_pair(1.0, '3/16in', str(tmp_path), 'freecadcmd.exe', force=True)
    assert result is not None
    assert result['drawn'] == [{'label': 'corner', 'panel': '3/16in'}]


def test_run_pair_writes_a_manifest_matching_build_sets_real_return_shape(tmp_path, monkeypatch):
    def fake_build_set(u, panel, out_dir, freecadcmd, say):
        Path(out_dir).mkdir(parents=True, exist_ok=True)   # the real build_set's own contract
        return ([('corner', '3/16in'), ('end_bolt', '3/16in')],
               [('offset_single', 'no FreeCAD generator')])

    monkeypatch.setattr(dvs, 'build_set', fake_build_set)
    manifest = svs.run_pair(2.0, '6mm', str(tmp_path), 'freecadcmd.exe', force=False)

    assert manifest['U'] == 2.0
    assert manifest['panel'] == '6mm'
    assert manifest['drawn'] == [{'label': 'corner', 'panel': '3/16in'},
                                 {'label': 'end_bolt', 'panel': '3/16in'}]
    assert manifest['owed'] == [{'label': 'offset_single', 'reason': 'no FreeCAD generator'}]
    assert isinstance(manifest['elapsed_s'], float)

    manifest_path = Path(dvs.pair_dir(str(tmp_path), 2.0, '6mm')) / svs.MANIFEST_NAME
    assert json.loads(manifest_path.read_text(encoding='utf-8')) == manifest


# ------------------------------------------------------------
# main
# ------------------------------------------------------------

def test_main_reports_when_freecadcmd_is_not_found(tmp_path, monkeypatch, capsys):
    def boom():
        raise freecad_render.FreeCADNotFound('not installed')

    monkeypatch.setattr(freecad_render, 'freecadcmd_path', boom)
    result = svs.main(['--out', str(tmp_path)])
    assert result == 2
    assert 'freecadcmd not found' in capsys.readouterr().out


def test_main_parses_out_and_force_flags_and_runs_every_pair(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(freecad_render, 'freecadcmd_path', lambda: 'fake_freecadcmd.exe')
    calls = []

    def fake_run_pair(u, panel, out_dir, freecadcmd, force):
        calls.append((u, panel, out_dir, freecadcmd, force))
        return {'drawn': [{'label': 'x', 'panel': panel}], 'owed': [], 'elapsed_s': 1.0}

    monkeypatch.setattr(svs, 'run_pair', fake_run_pair)
    result = svs.main(['--out', str(tmp_path), '--force'])

    assert result == 0
    assert len(calls) == 72
    assert all(c[2] == str(tmp_path) and c[3] == 'fake_freecadcmd.exe' and c[4] is True
              for c in calls)
    out = capsys.readouterr().out
    assert 'SWEEP -- 72 (U, panel) pairs' in out
    assert '--force' in out
    assert 'DONE -- 72 pairs run, 0 skipped, 72 sheets drawn, 0 owed' in out


def test_main_counts_skipped_pairs_separately_from_run_pairs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(freecad_render, 'freecadcmd_path', lambda: 'fake_freecadcmd.exe')
    monkeypatch.setattr(svs, 'run_pair', lambda *a, **k: None)   # every pair "already done"

    result = svs.main(['--out', str(tmp_path)])
    assert result == 0
    out = capsys.readouterr().out
    assert 'SKIPPED (manifest exists)' in out
    assert 'DONE -- 0 pairs run, 72 skipped, 0 sheets drawn, 0 owed' in out
