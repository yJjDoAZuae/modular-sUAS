"""IP-TEST-6 (doc/implementation/test_coverage.md): unit tests for render_sheets.py.

`jobs_for` is pure filesystem logic. `render` invokes a real GUI FreeCAD process (~12s
startup alone, per the module's own docstring) and is tested with `subprocess.run` faked
out, real job/log files under `tmp_path`, and pre-created `.svg`/`.pdf` files standing in for
what a real render would produce -- the same "fake the subprocess, keep everything else real"
approach used throughout this plan for render-orchestration code. `main()`'s argument
parsing and return-code logic is tested with the module-level `render` faked.
"""
import json
import subprocess

import freecad_render
import render_sheets as rs

# ------------------------------------------------------------
# jobs_for
# ------------------------------------------------------------

def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'')


def test_jobs_for_finds_every_fcstd_sorted(tmp_path):
    _touch(tmp_path / 'b.FCStd')
    _touch(tmp_path / 'a.FCStd')
    _touch(tmp_path / 'notes.txt')
    jobs = rs.jobs_for(str(tmp_path))
    assert [j['fcstd'] for j in jobs] == sorted(j['fcstd'] for j in jobs)
    assert len(jobs) == 2


def test_jobs_for_builds_the_stem_by_stripping_the_fcstd_suffix(tmp_path):
    _touch(tmp_path / 'corner-corner-7faa02.FCStd')
    [job] = rs.jobs_for(str(tmp_path))
    assert job['stem'] == str(tmp_path / 'corner-corner-7faa02')
    assert job['fcstd'] == str(tmp_path / 'corner-corner-7faa02.FCStd')


def test_jobs_for_filters_to_the_given_key(tmp_path):
    _touch(tmp_path / 'wanted.FCStd')
    _touch(tmp_path / 'other.FCStd')
    jobs = rs.jobs_for(str(tmp_path), only='wanted')
    assert len(jobs) == 1
    assert jobs[0]['stem'].endswith('wanted')


def test_jobs_for_returns_nothing_when_the_key_matches_no_stem(tmp_path):
    _touch(tmp_path / 'a.FCStd')
    assert rs.jobs_for(str(tmp_path), only='no_such_key') == []


# ------------------------------------------------------------
# render -- subprocess.run faked, everything else real
# ------------------------------------------------------------

def _echo_collector():
    lines = []
    return lines, lines.append


def test_render_with_no_jobs_reports_nothing_to_render_and_returns_empty():
    lines, echo = _echo_collector()
    result = rs.render([], 'out_dir', echo=echo)
    assert result == []
    assert any('nothing to render' in line for line in lines)


def test_render_reports_when_the_gui_binary_is_not_found(tmp_path, monkeypatch):
    def boom():
        raise freecad_render.FreeCADNotFound('not installed')

    monkeypatch.setattr(freecad_render, 'freecad_gui_path', boom)
    lines, echo = _echo_collector()
    jobs = [{'fcstd': str(tmp_path / 'a.FCStd'), 'stem': str(tmp_path / 'a')}]
    result = rs.render(jobs, str(tmp_path), echo=echo)
    assert result == []
    assert any('FreeCAD GUI not found' in line for line in lines)


def test_render_writes_the_job_file_and_sets_the_offscreen_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(freecad_render, 'freecad_gui_path', lambda: 'fake_freecad.exe')
    captured = {}

    def fake_run(cmd, env=None, timeout=None, stdout=None, stderr=None):
        captured['cmd'] = cmd
        captured['env'] = env
        captured['timeout'] = timeout

    monkeypatch.setattr(rs.subprocess, 'run', fake_run)

    jobs = [{'fcstd': str(tmp_path / 'a.FCStd'), 'stem': str(tmp_path / 'a')},
            {'fcstd': str(tmp_path / 'b.FCStd'), 'stem': str(tmp_path / 'b')}]
    rs.render(jobs, str(tmp_path), echo=lambda _l: None)

    job_path = tmp_path / 'render.job.json'
    assert json.loads(job_path.read_text(encoding='utf-8')) == jobs
    assert captured['cmd'] == ['fake_freecad.exe', rs.RENDERER]
    assert captured['env']['RENDER_JOB'] == str(job_path)
    assert captured['env']['RENDER_LOG'] == str(tmp_path / 'render.log')
    assert captured['env']['QT_QPA_PLATFORM'] == 'offscreen'
    assert captured['timeout'] == rs.TIMEOUT_BASE + rs.TIMEOUT_PER_SHEET * 2


def test_render_returns_only_the_stems_that_produced_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr(freecad_render, 'freecad_gui_path', lambda: 'fake_freecad.exe')
    monkeypatch.setattr(rs.subprocess, 'run', lambda *a, **k: None)

    stem_ok_svg = tmp_path / 'ok_svg'
    stem_ok_pdf = tmp_path / 'ok_pdf'
    stem_missing = tmp_path / 'missing'
    (tmp_path / 'ok_svg.svg').write_bytes(b'')
    (tmp_path / 'ok_pdf.pdf').write_bytes(b'')

    jobs = [{'fcstd': str(stem_ok_svg) + '.FCStd', 'stem': str(stem_ok_svg)},
            {'fcstd': str(stem_ok_pdf) + '.FCStd', 'stem': str(stem_ok_pdf)},
            {'fcstd': str(stem_missing) + '.FCStd', 'stem': str(stem_missing)}]
    result = rs.render(jobs, str(tmp_path), echo=lambda _l: None)
    assert sorted(result) == sorted([str(stem_ok_svg), str(stem_ok_pdf)])


def test_render_echoes_nonblank_log_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(freecad_render, 'freecad_gui_path', lambda: 'fake_freecad.exe')
    monkeypatch.setattr(rs.subprocess, 'run', lambda *a, **k: None)
    (tmp_path / 'render.log').write_text('sheet 1 ok\n\n  \nsheet 2 ok\n', encoding='utf-8')

    lines, echo = _echo_collector()
    jobs = [{'fcstd': str(tmp_path / 'a.FCStd'), 'stem': str(tmp_path / 'a')}]
    rs.render(jobs, str(tmp_path), echo=echo)
    assert any('sheet 1 ok' in line for line in lines)
    assert any('sheet 2 ok' in line for line in lines)


def test_render_reports_a_timeout_without_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(freecad_render, 'freecad_gui_path', lambda: 'fake_freecad.exe')

    def raises_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd='freecad', timeout=1.0)

    monkeypatch.setattr(rs.subprocess, 'run', raises_timeout)
    lines, echo = _echo_collector()
    jobs = [{'fcstd': str(tmp_path / 'a.FCStd'), 'stem': str(tmp_path / 'a')}]
    result = rs.render(jobs, str(tmp_path), echo=echo)
    assert result == []
    assert any('did not finish within' in line for line in lines)


# ------------------------------------------------------------
# main
# ------------------------------------------------------------

def test_main_reports_a_nonexistent_output_directory(tmp_path, capsys):
    missing = tmp_path / 'does_not_exist'
    result = rs.main(['--out', str(missing)])
    assert result == 2
    assert 'no such directory' in capsys.readouterr().out


def test_main_parses_out_and_key_flags_and_reports_success(tmp_path, monkeypatch, capsys):
    (tmp_path / 'wanted.FCStd').write_bytes(b'')
    (tmp_path / 'other.FCStd').write_bytes(b'')

    def fake_render(jobs, out_dir, echo=print):
        return [j['stem'] for j in jobs]   # everything "rendered"

    monkeypatch.setattr(rs, 'render', fake_render)
    result = rs.main(['--out', str(tmp_path), '--key', 'wanted'])
    out = capsys.readouterr().out
    assert result == 0
    assert 'RENDERING 1 sheet(s)' in out
    assert 'rendered 1 of 1' in out


def test_main_returns_one_when_some_jobs_do_not_produce_a_file(tmp_path, monkeypatch, capsys):
    (tmp_path / 'a.FCStd').write_bytes(b'')
    (tmp_path / 'b.FCStd').write_bytes(b'')
    monkeypatch.setattr(rs, 'render', lambda jobs, out_dir, echo=print: jobs[:1])

    result = rs.main(['--out', str(tmp_path)])
    assert result == 1
    assert 'rendered 1 of 2' in capsys.readouterr().out


def test_main_returns_one_when_there_are_no_jobs_at_all(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rs, 'render', lambda jobs, out_dir, echo=print: [])
    result = rs.main(['--out', str(tmp_path)])
    assert result == 1
    assert 'rendered 0 of 0' in capsys.readouterr().out
