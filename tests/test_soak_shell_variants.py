"""IP-TEST-6 (doc/implementation/test_coverage.md): unit tests for soak_shell_variants.py.

A real run of this soak takes on the order of five hours (the module's own docstring) --
`run_one`'s `subprocess.run` call and `main`'s loop over `run_one` are always faked out here,
the same "fake the expensive step, keep the orchestration real" approach used for
sweep_variant_sets.py. `plan`/`load_done` are pure and tested directly; `run_one`'s
SOAK_RESULT/SOAK_ERROR/neither-line parsing is tested with `subprocess.run` faked.
"""
import json

import freecad_render
import soak_shell_variants as ssv

# ------------------------------------------------------------
# plan
# ------------------------------------------------------------

def test_plan_matches_the_documented_28_build_total():
    assert len(ssv.plan()) == 28


def test_plan_repeats_five_times_at_u_1_and_u_4_and_once_elsewhere():
    triples = ssv.plan()
    for kind in ssv.KINDS:
        for u in ssv.U_VALUES:
            count = sum(1 for k, uu, _r in triples if k == kind and uu == u)
            assert count == (5 if u in (1.0, 4.0) else 1)


def test_plan_covers_both_shell_kinds():
    kinds_seen = {k for k, _u, _r in ssv.plan()}
    assert kinds_seen == set(ssv.KINDS)


def test_plan_has_no_duplicate_triples():
    triples = ssv.plan()
    assert len(triples) == len(set(triples))


# ------------------------------------------------------------
# load_done
# ------------------------------------------------------------

def test_load_done_is_empty_when_the_file_does_not_exist(tmp_path):
    assert ssv.load_done(str(tmp_path / 'missing.jsonl')) == set()


def test_load_done_reads_every_recorded_triple_and_skips_blank_lines(tmp_path):
    path = tmp_path / 'results.jsonl'
    path.write_text(
        json.dumps({'kind': 'tail_shell', 'u': 1.0, 'repeat': 0}) + '\n'
        + '\n'
        + json.dumps({'kind': 'nose_cowl_shell', 'u': 4.0, 'repeat': 2}) + '\n',
        encoding='utf-8')
    done = ssv.load_done(str(path))
    assert done == {('tail_shell', 1.0, 0), ('nose_cowl_shell', 4.0, 2)}


def test_load_done_counts_an_error_record_as_done_too():
    """A failed build must not be silently missing from `done`: 'kind'/'u'/'repeat' are the
    only keys load_done reads, and an error record carries all three."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'results.jsonl'
        path.write_text(json.dumps({'kind': 'tail_shell', 'u': 0.5, 'repeat': 0,
                                    'error': 'build failed'}) + '\n', encoding='utf-8')
        assert ssv.load_done(str(path)) == {('tail_shell', 0.5, 0)}


# ------------------------------------------------------------
# run_one -- subprocess.run faked
# ------------------------------------------------------------

def _fake_run(stdout_text):
    class _Done:
        stdout = stdout_text.encode('utf-8')
    return lambda argv, stdout=None, stderr=None: _Done()


def test_run_one_builds_the_expected_freecadcmd_argv(tmp_path, monkeypatch):
    calls = []

    def fake_run(argv, stdout=None, stderr=None):
        calls.append(argv)
        class _Done:
            stdout = b'SOAK_RESULT {"kind": "tail_shell", "u": 1.0}\n'
        return _Done()

    monkeypatch.setattr(ssv.subprocess, 'run', fake_run)
    ssv.run_one('freecadcmd.exe', 'tail_shell', 1.0, 2, str(tmp_path))
    assert calls[0] == ['freecadcmd.exe', ssv.WORKER,
                        '--pass', '--kind=tail_shell', '--pass', '--u=1.0',
                        '--pass', '--repeat=2', '--pass', f'--out={tmp_path}']


def test_run_one_parses_a_soak_result_line(monkeypatch, tmp_path):
    monkeypatch.setattr(ssv.subprocess, 'run', _fake_run(
        'some preamble\nSOAK_RESULT {"kind": "tail_shell", "u": 1.0, "wall_volume": 5.0}\n'))
    record, raw = ssv.run_one('freecadcmd.exe', 'tail_shell', 1.0, 0, str(tmp_path))
    assert record == {'kind': 'tail_shell', 'u': 1.0, 'wall_volume': 5.0}
    assert 'preamble' in raw


def test_run_one_parses_a_soak_error_line(monkeypatch, tmp_path):
    monkeypatch.setattr(ssv.subprocess, 'run', _fake_run(
        'SOAK_ERROR {"kind": "tail_shell", "u": 0.5, "error": "no solid produced"}\n'))
    record, _raw = ssv.run_one('freecadcmd.exe', 'tail_shell', 0.5, 0, str(tmp_path))
    assert record == {'kind': 'tail_shell', 'u': 0.5, 'error': 'no solid produced'}


def test_run_one_records_a_synthetic_error_when_neither_line_appears(monkeypatch, tmp_path):
    monkeypatch.setattr(ssv.subprocess, 'run', _fake_run('freecadcmd crashed with no output\n'))
    record, raw = ssv.run_one('freecadcmd.exe', 'nose_cowl_shell', 2.0, 0, str(tmp_path))
    assert record['kind'] == 'nose_cowl_shell'
    assert record['u'] == 2.0
    assert 'no SOAK_RESULT/SOAK_ERROR line' in record['error']
    assert 'crashed' in raw


# ------------------------------------------------------------
# main
# ------------------------------------------------------------

def test_main_reports_when_freecadcmd_is_not_found(tmp_path, monkeypatch, capsys):
    def boom():
        raise freecad_render.FreeCADNotFound('not installed')

    monkeypatch.setattr(freecad_render, 'freecadcmd_path', boom)
    result = ssv.main(['--out', str(tmp_path)])
    assert result == 2
    assert 'freecadcmd not found' in capsys.readouterr().out


def _success_record(kind, u):
    return {'kind': kind, 'u': u, 'wall_volume': 12.3456, 'solids': 1,
            'worst_wall_error': 0.001, 'worst_rib_error': 0.002, 'partition_slip': 1e-6}


def test_main_runs_every_planned_build_and_writes_results_and_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(freecad_render, 'freecadcmd_path', lambda: 'fake_freecadcmd.exe')

    def fake_run_one(freecadcmd, kind, u, repeat, shapes_dir):
        return _success_record(kind, u), f'raw output for {kind} {u} {repeat}'

    monkeypatch.setattr(ssv, 'run_one', fake_run_one)
    result = ssv.main(['--out', str(tmp_path)])
    assert result == 0

    results_path = tmp_path / 'soak_results.jsonl'
    lines = results_path.read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) == 28
    first = json.loads(lines[0])
    assert 'repeat' in first and 'elapsed_s' in first

    log_text = (tmp_path / 'soak_log.txt').read_text(encoding='utf-8')
    assert 'raw output for' in log_text

    out = capsys.readouterr().out
    assert 'SOAK -- 28 builds (0 already done)' in out
    assert 'DONE -- 28 builds run' in out
    assert 'vol=12.3456' in out


def test_main_skips_builds_already_present_unless_forced(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(freecad_render, 'freecadcmd_path', lambda: 'fake_freecadcmd.exe')
    tmp_path.mkdir(exist_ok=True)
    results_path = tmp_path / 'soak_results.jsonl'
    first_triple = ssv.plan()[0]
    results_path.write_text(json.dumps(
        {'kind': first_triple[0], 'u': first_triple[1], 'repeat': first_triple[2]}) + '\n',
        encoding='utf-8')

    calls = []

    def fake_run_one(freecadcmd, kind, u, repeat, shapes_dir):
        calls.append((kind, u, repeat))
        return _success_record(kind, u), 'raw'

    monkeypatch.setattr(ssv, 'run_one', fake_run_one)
    result = ssv.main(['--out', str(tmp_path)])
    assert result == 0
    assert len(calls) == 27   # every planned build except the one already recorded
    assert first_triple not in calls
    assert 'SKIPPED (already done)' in capsys.readouterr().out


def test_main_force_reruns_a_build_that_was_already_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(freecad_render, 'freecadcmd_path', lambda: 'fake_freecadcmd.exe')
    tmp_path.mkdir(exist_ok=True)
    results_path = tmp_path / 'soak_results.jsonl'
    first_triple = ssv.plan()[0]
    results_path.write_text(json.dumps(
        {'kind': first_triple[0], 'u': first_triple[1], 'repeat': first_triple[2]}) + '\n',
        encoding='utf-8')

    calls = []
    monkeypatch.setattr(
        ssv, 'run_one',
        lambda freecadcmd, kind, u, repeat, shapes_dir: (
            calls.append((kind, u, repeat)) or (_success_record(kind, u), 'raw')))
    ssv.main(['--out', str(tmp_path), '--force'])
    assert len(calls) == 28
    assert first_triple in calls


def test_main_prints_an_error_line_for_a_failed_build(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(freecad_render, 'freecadcmd_path', lambda: 'fake_freecadcmd.exe')

    def fake_run_one(freecadcmd, kind, u, repeat, shapes_dir):
        return {'kind': kind, 'u': u, 'error': 'the kernel refused'}, 'raw'

    monkeypatch.setattr(ssv, 'run_one', fake_run_one)
    ssv.main(['--out', str(tmp_path)])
    out = capsys.readouterr().out
    assert 'ERROR: the kernel refused' in out


def test_main_marks_an_unreliable_volume_on_the_summary_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(freecad_render, 'freecadcmd_path', lambda: 'fake_freecadcmd.exe')

    def fake_run_one(freecadcmd, kind, u, repeat, shapes_dir):
        record = _success_record(kind, u)
        record['volume_reliable'] = False
        record['open_edge_count'] = 3
        return record, 'raw'

    monkeypatch.setattr(ssv, 'run_one', fake_run_one)
    ssv.main(['--out', str(tmp_path)])
    assert 'UNRELIABLE(3 open edges)' in capsys.readouterr().out
