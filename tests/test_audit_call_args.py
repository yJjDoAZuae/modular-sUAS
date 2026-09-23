"""IP-TEST-6 (doc/implementation/test_coverage.md): unit tests for audit_call_args.py.

This module is a bare top-level script with no functions and no `main()` -- everything runs
as module-level code reading `sys.argv[1]` at import time, so there is no function API to
call directly. It is invoked as a real subprocess instead (`sys.executable
audit_call_args.py <scad_dir>`), which is cheap and instant here since the script itself is
pure Python with no FreeCAD/OpenSCAD dependency -- unlike every other subprocess call
deferred elsewhere in this plan, this *is* the lightweight thing under test, not a stand-in
for an expensive one.

Wired into pytest as a real self-check against the committed `.scad` corpus (currently
clean), the same "run the pre-existing checker for real" approach IP-TEST-3 used for
`check_derivation.check()`/`requirements.check_register()`, plus a synthetic fixture that
reproduces the real historical bug this tool was built to catch (OQ-DES-B10:
`greeble_bolt_web`'s rotated call-site arguments).
"""
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / 'src' / 'Fuselage' / 'tools' / 'audit_call_args.py'
_REAL_SCAD_DIR = Path(__file__).resolve().parents[1] / 'src' / 'Fuselage' / 'scad'


def _run(scad_dir):
    return subprocess.run([sys.executable, str(_SCRIPT), str(scad_dir)],
                          capture_output=True, text=True, check=False)


def test_the_real_committed_scad_corpus_has_no_positional_mismatches():
    """A regression pin: OQ-DES-B10's bug class, re-checked against the real corpus."""
    result = _run(_REAL_SCAD_DIR)
    assert result.returncode == 0
    assert '0 call site(s) with a positional mismatch' in result.stdout


def test_detects_a_rotated_call_site_matching_the_real_oq_des_b10_bug_shape(tmp_path):
    (tmp_path / 'lib.scad').write_text(
        'module inner(a, b, c) {\n'
        '  cube([a, b, c]);\n'
        '}\n'
        'module outer(a, b, c) {\n'
        '  inner(b, a, c);\n'   # a and b swapped -- the exact defect shape
        '}\n', encoding='utf-8')

    result = _run(tmp_path)
    assert 'lib.scad' in result.stdout
    assert 'inner() called from outer()' in result.stdout
    assert 'arg 1: passes b' in result.stdout
    assert 'arg 2: passes a' in result.stdout
    assert '1 call site(s) with a positional mismatch' in result.stdout


def test_does_not_flag_a_call_site_that_passes_arguments_in_the_declared_order(tmp_path):
    (tmp_path / 'lib.scad').write_text(
        'module inner(a, b, c) {\n'
        '  cube([a, b, c]);\n'
        '}\n'
        'module outer(a, b, c) {\n'
        '  inner(a, b, c);\n'
        '}\n', encoding='utf-8')

    result = _run(tmp_path)
    assert '0 call site(s) with a positional mismatch' in result.stdout


def test_does_not_flag_an_identifier_that_is_not_a_parameter_of_the_callee(tmp_path):
    """The docstring's own scope: a caller using a more specific local name for a generic
    parameter is normal, not a defect -- only a name that is ALSO one of the callee's own
    parameter names (so could plausibly be a rotated argument) counts."""
    (tmp_path / 'lib.scad').write_text(
        'module inner(a, b, c) {\n'
        '  cube([a, b, c]);\n'
        '}\n'
        'module outer(width, height, depth) {\n'
        '  inner(height, width, depth);\n'   # rotated, but names are not inner's own params
        '}\n', encoding='utf-8')

    result = _run(tmp_path)
    assert '0 call site(s) with a positional mismatch' in result.stdout


def test_does_not_flag_calls_with_a_mismatched_argument_count(tmp_path):
    (tmp_path / 'lib.scad').write_text(
        'module inner(a, b, c) {\n'
        '  cube([a, b, c]);\n'
        '}\n'
        'module outer(a, b, c) {\n'
        '  inner(a, b);\n'   # fewer arguments than inner declares -- a caller error of a
        '}\n', encoding='utf-8')   # different kind, out of scope for this checker

    result = _run(tmp_path)
    assert '0 call site(s) with a positional mismatch' in result.stdout


def test_does_not_flag_a_module_definition_line_as_a_call_to_itself(tmp_path):
    """`module inner(a, b, c) {` itself matches the call-site regex for `inner(`; the
    'ends with module' guard exists specifically to exclude the definition line."""
    (tmp_path / 'lib.scad').write_text(
        'module inner(a, b, c) {\n'
        '  cube([a, b, c]);\n'
        '}\n', encoding='utf-8')

    result = _run(tmp_path)
    assert '0 call site(s) with a positional mismatch' in result.stdout
