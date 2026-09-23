"""IP-TEST-3 (doc/implementation/test_coverage.md): unit tests for geometry_version.py.

IP-FC-11's fingerprint mechanism, in full: `_digest`, `_resolved`, `_closure`,
`_scad_dependencies`, `_python_dependencies`, `scad_version`, `freecad_version`, and
`clear_cache`. The module is entirely file-I/O-driven with no FreeCAD/OpenSCAD dependency,
so every test builds a small real dependency chain under `tmp_path` rather than mocking.

Adoption-phase retrofit (general.md's TDD section): pins current, intended behavior. The
module's own docstrings already state several deliberate, easy-to-get-backwards properties
(over-sensitive to comment edits, keyed by basename not full path, cache keyed on resolved
paths) -- each gets a test precisely because a "fix" that quietly reversed one would look
like an improvement.
"""
import os
import tempfile
from pathlib import Path

import geometry_version as gv
import pytest


@pytest.fixture(autouse=True)
def clear_module_cache():
    """The module's cache is process-global (`_CACHE = {}` at import time), so a stale
    entry from one test would leak into the next -- every test starts and ends clean."""
    gv.clear_cache()
    yield
    gv.clear_cache()


# ------------------------------------------------------------
# _digest
# ------------------------------------------------------------

def test_digest_is_deterministic_and_16_hex_characters(tmp_path):
    f = tmp_path / 'a.scad'
    f.write_text('module x() {}\n', encoding='utf-8')
    d1 = gv._digest([str(f)])
    d2 = gv._digest([str(f)])
    assert d1 == d2
    assert len(d1) == 16
    int(d1, 16)  # must be valid hex


def test_digest_changes_when_file_content_changes(tmp_path):
    f = tmp_path / 'a.scad'
    f.write_text('module x() {}\n', encoding='utf-8')
    before = gv._digest([str(f)])
    f.write_text('module x() { cube(1); }\n', encoding='utf-8')
    after = gv._digest([str(f)])
    assert before != after


def test_digest_is_order_independent_across_the_input_list(tmp_path):
    a = tmp_path / 'a.scad'
    b = tmp_path / 'b.scad'
    a.write_text('a\n', encoding='utf-8')
    b.write_text('b\n', encoding='utf-8')
    assert gv._digest([str(a), str(b)]) == gv._digest([str(b), str(a)])


def test_digest_is_keyed_by_basename_not_full_path():
    """A rename changes the digest and a move does not -- see _digest's own docstring:
    the closure lives in one directory, and keying on the absolute path would make every
    checkout produce a different digest for identical sources."""
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        same_name_1 = Path(d1) / 'a.scad'
        same_name_2 = Path(d2) / 'a.scad'
        renamed = Path(d1) / 'b.scad'
        for p in (same_name_1, same_name_2, renamed):
            p.write_text('module x() {}\n', encoding='utf-8')

        assert (gv._digest([str(same_name_1)])
                == gv._digest([str(same_name_2)]))  # moved: same digest
        assert (gv._digest([str(same_name_1)])
                != gv._digest([str(renamed)]))       # renamed: differs


# ------------------------------------------------------------
# _resolved
# ------------------------------------------------------------

def test_resolved_returns_absolute_normcased_paths(tmp_path):
    f = tmp_path / 'sub' / 'a.scad'
    f.parent.mkdir()
    f.write_text('x', encoding='utf-8')
    [resolved] = gv._resolved([str(f)])
    assert resolved.lower() == str(f.resolve()).lower()
    assert Path(resolved).is_absolute()


# ------------------------------------------------------------
# _scad_dependencies -- use/include, with or without a trailing semicolon
# ------------------------------------------------------------

def test_scad_dependencies_finds_use_and_include_resolved_relative_to_the_file(tmp_path):
    sub = tmp_path / 'sub'
    sub.mkdir()
    scad = sub / 'main.scad'
    scad.write_text(
        'use <helper.scad>;\n'
        'include <../shared.scad>\n'  # no trailing semicolon -- must still be found
        '// use <commented_out.scad>;  -- not a real reference at line start\n',
        encoding='utf-8')

    deps = gv._scad_dependencies(str(scad))

    # os.path.join, not the pathlib `/` operator: _scad_dependencies joins with os.path.join,
    # which -- unlike pathlib -- preserves a literal ".." inside the joined-in argument rather
    # than normalizing the separator, so only this reproduces its exact output string.
    assert os.path.join(str(sub), 'helper.scad') in deps
    assert os.path.join(str(sub), '../shared.scad') in deps


def test_scad_dependencies_does_not_match_a_use_inside_a_comment_line():
    """The regex is anchored to (?m)^\\s*(?:use|include), so a `//` prefix on the same
    line as the keyword is not a reference -- pinned because a looser regex would also
    match commented-out lines like the third one in the fixture above."""
    assert not gv._SCAD_REF.match('// use <x.scad>;')


# ------------------------------------------------------------
# _python_dependencies -- only siblings that exist
# ------------------------------------------------------------

def test_python_dependencies_finds_import_and_from_import_as_sibling_files(tmp_path):
    real_sibling = tmp_path / 'helper.py'
    real_sibling.write_text('x = 1\n', encoding='utf-8')
    main = tmp_path / 'main.py'
    main.write_text(
        'import helper\n'
        'from helper import x\n'
        'import os\n'          # stdlib -- not a sibling file, dropped by _closure
        'import not_a_real_module\n',
        encoding='utf-8')

    deps = gv._python_dependencies(str(main), str(tmp_path))

    assert str(tmp_path / 'helper.py') in deps
    # _python_dependencies itself does not filter -- every import name becomes a candidate
    # path, real or not. Filtering to files that actually exist is _closure's job.
    assert str(tmp_path / 'os.py') in deps
    assert str(tmp_path / 'not_a_real_module.py') in deps


def test_python_dependencies_finds_a_deferred_import_inside_a_function(tmp_path):
    """Unanchored to indentation on purpose -- corner_tree.py has a deferred import inside
    a function, per the module's own comment."""
    sibling = tmp_path / 'lazy.py'
    sibling.write_text('y = 1\n', encoding='utf-8')
    main = tmp_path / 'main.py'
    main.write_text('def f():\n    import lazy\n    return lazy.y\n', encoding='utf-8')

    deps = gv._python_dependencies(str(main), str(tmp_path))

    assert str(tmp_path / 'lazy.py') in deps


# ------------------------------------------------------------
# _closure -- reachability, including cycle termination and non-existent files
# ------------------------------------------------------------

def test_closure_walks_the_full_dependency_chain(tmp_path):
    a = tmp_path / 'a.scad'
    b = tmp_path / 'b.scad'
    c = tmp_path / 'c.scad'
    a.write_text('use <b.scad>;\n', encoding='utf-8')
    b.write_text('use <c.scad>;\n', encoding='utf-8')
    c.write_text('cube(1);\n', encoding='utf-8')

    files = gv._closure([str(a)], gv._scad_dependencies)

    names = {Path(f).name for f in files}
    assert names == {'a.scad', 'b.scad', 'c.scad'}


def test_closure_terminates_on_a_self_referential_cycle(tmp_path):
    """OpenSCAD's `include <>` is textual, and a self-include is legal -- the docstring's
    own justification for why the visited set is not optional here."""
    a = tmp_path / 'a.scad'
    b = tmp_path / 'b.scad'
    a.write_text('use <b.scad>;\n', encoding='utf-8')
    b.write_text('use <a.scad>;\n', encoding='utf-8')  # cycle back to a

    files = gv._closure([str(a)], gv._scad_dependencies)  # must return, not loop forever

    assert {Path(f).name for f in files} == {'a.scad', 'b.scad'}


def test_closure_silently_drops_a_reference_to_a_file_that_does_not_exist(tmp_path):
    a = tmp_path / 'a.scad'
    a.write_text('use <does_not_exist.scad>;\n', encoding='utf-8')

    files = gv._closure([str(a)], gv._scad_dependencies)

    assert [Path(f).name for f in files] == ['a.scad']


# ------------------------------------------------------------
# scad_version -- the full, cached, public entry point
# ------------------------------------------------------------

def _write_scad_chain(tmp_path):
    """generated.scad -> geometry.scad -> shared.scad, mimicking a real sweep output:
    the generated file's own `use <>` line is the closure's only root."""
    generated = tmp_path / 'generated.scad'
    geometry = tmp_path / 'geometry.scad'
    shared = tmp_path / 'shared.scad'
    generated.write_text(
        'use <geometry.scad>;\n'
        'fuselage_bulkhead(unit_width=100);\n', encoding='utf-8')
    geometry.write_text('use <shared.scad>;\nmodule fuselage_bulkhead() {}\n',
                        encoding='utf-8')
    shared.write_text('module helper() {}\n', encoding='utf-8')
    return generated, geometry, shared


def test_scad_version_excludes_the_generated_file_itself(tmp_path):
    generated, _geometry, _shared = _write_scad_chain(tmp_path)
    _version, modules = gv.scad_version(str(generated))
    assert modules == ['geometry.scad', 'shared.scad']
    assert 'generated.scad' not in modules


def test_scad_version_changes_when_a_dependency_changes_but_is_stable_when_it_does_not(
        tmp_path):
    generated, _geometry, shared = _write_scad_chain(tmp_path)
    version_before, _modules = gv.scad_version(str(generated))

    gv.clear_cache()  # otherwise the cached answer would hide the edit -- see the test below
    shared.write_text('module helper() { cube(1); }\n', encoding='utf-8')
    version_after, _modules = gv.scad_version(str(generated))

    assert version_before != version_after


def test_scad_version_is_cached_and_does_not_see_an_edit_without_clear_cache(tmp_path):
    """Documents the module's own stated tradeoff: 'a sweep does not need this [clearing]
    because the sources cannot change while it runs.' A caller that edits a source file
    mid-process without calling clear_cache() gets the stale answer -- that is deliberate
    inside one sweep, and would be a real bug in a long-lived process that does not follow
    the module's contract."""
    generated, _geometry, shared = _write_scad_chain(tmp_path)
    version_before, _modules = gv.scad_version(str(generated))

    shared.write_text('module helper() { cube(1); }\n', encoding='utf-8')  # no clear_cache()
    version_after, _modules = gv.scad_version(str(generated))

    assert version_before == version_after


# ------------------------------------------------------------
# freecad_version
# ------------------------------------------------------------

def test_freecad_version_walks_python_imports_from_the_entry_modules(tmp_path):
    builder = tmp_path / 'build_part.py'
    top = tmp_path / 'bulkhead_full.py'
    shared = tmp_path / 'corner_common.py'
    builder.write_text('import corner_common\n', encoding='utf-8')
    top.write_text('import corner_common\n', encoding='utf-8')
    shared.write_text('x = 1\n', encoding='utf-8')

    _version, modules = gv.freecad_version(['build_part', 'bulkhead_full'], str(tmp_path))

    assert modules == ['build_part.py', 'bulkhead_full.py', 'corner_common.py']


def test_freecad_version_accepts_entry_module_names_with_or_without_py_suffix(tmp_path):
    top = tmp_path / 'bulkhead_full.py'
    top.write_text('x = 1\n', encoding='utf-8')

    with_suffix = gv.freecad_version(['bulkhead_full.py'], str(tmp_path))
    gv.clear_cache()
    without_suffix = gv.freecad_version(['bulkhead_full'], str(tmp_path))

    assert with_suffix == without_suffix


# ------------------------------------------------------------
# clear_cache
# ------------------------------------------------------------

def test_clear_cache_empties_the_module_level_cache(tmp_path):
    generated, _geometry, _shared = _write_scad_chain(tmp_path)
    gv.scad_version(str(generated))
    assert gv._CACHE

    gv.clear_cache()

    assert gv._CACHE == {}
