"""IP-TEST-6 (doc/implementation/test_coverage.md): unit tests for render_variant.py.

`combinations`/`settings`/`take_backend`/`check` are pure and get direct coverage.
`main()`'s listing, unknown-type, no-such-combination and invalid-combination branches are
covered against the real corpus (`family_combinations`/`family_is_valid`) -- none of them
reach a render. The one branch that does (a genuinely valid combination, which constructs a
real `fv.RenderQueue` and calls through to `bulkhead_render`/`boom_bulkhead_render`) is
deliberately out of scope here, for the same reason IP-TEST-2 left `RenderQueue`'s own
thread-pool behavior uncovered: exercising it properly needs its own follow-up pass, not an
incidental one from this file.
"""
import fuselage_variants as fv
import pytest
import render_variant as rv

# ------------------------------------------------------------
# combinations / settings
# ------------------------------------------------------------

def test_combinations_matches_fuselage_variants_family_combinations():
    assert list(rv.combinations('bulkhead')) == list(fv.family_combinations('bulkhead'))


def test_settings_returns_the_plain_default_printer_and_fx_one():
    printer, fx = rv.settings()
    assert printer == fv.null_printer_settings()
    assert fx == 1.0


# ------------------------------------------------------------
# take_backend
# ------------------------------------------------------------

def test_take_backend_defaults_to_openscad_when_absent():
    args = ['1.0', 'end_bolt', '3/16in']
    assert rv.take_backend(args) == 'openscad'
    assert args == ['1.0', 'end_bolt', '3/16in']   # unmodified


def test_take_backend_reads_a_separate_flag_and_value_and_removes_both():
    args = ['--backend', 'freecad', '1.0', 'end_bolt']
    assert rv.take_backend(args) == 'freecad'
    assert args == ['1.0', 'end_bolt']


def test_take_backend_reads_an_equals_form_and_removes_only_that_token():
    args = ['--backend=freecad', '1.0', 'end_bolt']
    assert rv.take_backend(args) == 'freecad'
    assert args == ['1.0', 'end_bolt']


def test_take_backend_raises_when_the_flag_has_no_value():
    with pytest.raises(SystemExit, match='--backend needs a name'):
        rv.take_backend(['--backend'])


def test_take_backend_rejects_an_unknown_name():
    with pytest.raises(SystemExit, match='unknown backend'):
        rv.take_backend(['--backend', 'bogus'])


# ------------------------------------------------------------
# check
# ------------------------------------------------------------

def test_check_accepts_openscad_and_freecad():
    assert rv.check('openscad') == 'openscad'
    assert rv.check('freecad') == 'freecad'


def test_check_rejects_anything_else():
    with pytest.raises(SystemExit, match='unknown backend'):
        rv.check('vray')


# ------------------------------------------------------------
# main -- every branch that does not reach a render
# ------------------------------------------------------------

def test_main_with_no_arguments_lists_every_combination_and_its_validity(capsys):
    result = rv.main(['render_variant.py'])
    assert result == 0
    out = capsys.readouterr().out
    assert 'family' in out and 'valid' in out
    assert 'bulkhead' in out
    assert 'boom_bulkhead' in out


def test_main_reports_an_unknown_bulkhead_type(capsys):
    result = rv.main(['1.0', 'no_such_type', '3/16in'])
    assert result == 1
    assert 'no bulkhead type named' in capsys.readouterr().out


def test_main_reports_no_such_combination_for_an_unmatched_real_type(capsys):
    result = rv.main(['999.0', 'end_bolt', '3/16in'])
    assert result == 1
    assert 'no such combination' in capsys.readouterr().out


def test_main_reports_not_rendered_for_a_real_invalid_combination(capsys):
    """U=1.5, end_bolt, 1mm is a real combination the corpus rejects (confirmed against
    fv.family_is_valid directly) -- this exercises main()'s validity-refusal branch without
    ever reaching a render."""
    result = rv.main(['1.5', 'end_bolt', '1mm'])
    assert result == 1
    out = capsys.readouterr().out
    assert 'NOT RENDERED' in out
    assert 'would not generate' in out
