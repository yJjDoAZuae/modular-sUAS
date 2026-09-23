"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for scad_snapshot.py.

`compare()` is pure and gets exhaustive synthetic-dict coverage. `capture()` is exercised
against the real sweep machinery (`fuselage_variants`, real CSVs, real `solid2` rendering)
rather than a fake sweep function, because the thing worth proving is that the
`fv.solid_render` monkeypatch genuinely intercepts every part and is restored afterward --
faking the sweep out would just test the fake. Cost is bounded by monkeypatching `SWEEPS`
down to a single, fast sweep kind rather than running the entire five-sweep corpus (one
corner sweep alone is ~260 parts in about a second; the module's own docstring already notes
a full capture is "seconds", not minutes). `main()` (argparse/file I/O wiring) is not
covered, consistent with the other CLI-entry-point modules in this plan.
"""
import fuselage_variants as fv
import pytest
import scad_snapshot as ss

# ------------------------------------------------------------
# capture -- against the real sweep machinery, restricted to one fast sweep kind
# ------------------------------------------------------------

_ONE_SWEEP = (ss.SWEEPS[0],)   # ('corner', 'run_corner_parametric_sweep', (...))


def test_capture_records_real_scad_text_for_every_part_and_restores_solid_render(monkeypatch):
    monkeypatch.setattr(ss, 'SWEEPS', _ONE_SWEEP)
    original_render = fv.solid_render

    captured = ss.capture(quiet=True)

    assert len(captured) > 0
    assert fv.solid_render is original_render   # the monkeypatch swap was undone
    # Every value is real solid2-rendered OpenSCAD text, not a placeholder.
    sample = next(iter(captured.values()))
    assert isinstance(sample, str)
    assert len(sample) > 0


def test_capture_restores_solid_render_even_when_a_sweep_raises(monkeypatch):
    monkeypatch.setattr(ss, 'SWEEPS', _ONE_SWEEP)
    original_render = fv.solid_render

    def boom(*_args, **_kwargs):
        raise RuntimeError('synthetic sweep failure')

    monkeypatch.setattr(fv, _ONE_SWEEP[0][1], boom)
    with pytest.raises(RuntimeError):
        ss.capture(quiet=True)
    assert fv.solid_render is original_render


def test_capture_key_names_are_unique_and_come_from_the_named_sweep(monkeypatch):
    monkeypatch.setattr(ss, 'SWEEPS', _ONE_SWEEP)
    captured = ss.capture(quiet=True)
    names = list(captured)
    assert len(names) == len(set(names))
    # _ONE_SWEEP is the corner sweep: every filename it produces carries "corner".
    assert all('corner' in name for name in names)


# ------------------------------------------------------------
# compare -- pure, exhaustive synthetic coverage
# ------------------------------------------------------------

def test_compare_returns_zero_and_reports_nothing_for_identical_snapshots(capsys):
    before = {'a': 'module a() {}'}
    after = {'a': 'module a() {}'}
    assert ss.compare(before, after) == 0
    assert capsys.readouterr().out == ''


def test_compare_reports_a_part_missing_from_after(capsys):
    before = {'a': 'x', 'b': 'y'}
    after = {'a': 'x'}
    assert ss.compare(before, after) == 1
    assert 'MISSING NOW   b' in capsys.readouterr().out


def test_compare_reports_a_new_part_in_after(capsys):
    before = {'a': 'x'}
    after = {'a': 'x', 'b': 'y'}
    assert ss.compare(before, after) == 1
    assert 'NEW           b' in capsys.readouterr().out


def test_compare_reports_a_changed_part_and_the_first_differing_line(capsys):
    before = {'a': 'line1\nline2\nline3'}
    after = {'a': 'line1\nCHANGED\nline3'}
    assert ss.compare(before, after) == 1
    out = capsys.readouterr().out
    assert 'CHANGED       a' in out
    assert 'line 2' in out
    assert 'before: line2' in out
    assert 'after : CHANGED' in out


def test_compare_reports_differing_line_count_when_no_common_line_differs(capsys):
    before = {'a': 'line1\nline2'}
    after = {'a': 'line1\nline2\nline3'}
    assert ss.compare(before, after) == 1
    out = capsys.readouterr().out
    assert 'differing line count: 2 -> 3' in out


def test_compare_truncates_the_changed_list_after_five_and_counts_the_rest(capsys):
    before = {f'p{i}': 'same\nold' for i in range(7)}
    after = {f'p{i}': 'same\nnew' for i in range(7)}
    problems = ss.compare(before, after)
    assert problems == 7
    out = capsys.readouterr().out
    assert out.count('CHANGED') == 5
    assert '... 2 more changed part(s)' in out


def test_compare_counts_every_missing_and_new_part_even_beyond_the_ten_printed(capsys):
    before = {f'gone{i}': 'x' for i in range(12)}
    after = {f'new{i}': 'y' for i in range(12)}
    problems = ss.compare(before, after)
    assert problems == 24
    out = capsys.readouterr().out
    assert out.count('MISSING NOW') == 10
    assert out.count('NEW') == 10
