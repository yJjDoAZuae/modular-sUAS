"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for baseline_manifest.py.

OQ-ARCH-15's frozen-baseline capture/verify pair, exercised against real STL files under
`tmp_path` -- the same reasoning as test_baseline_ledger.py: this module's whole job is
measuring real geometry, so a mock would test nothing this module actually does.

Adoption-phase retrofit (general.md's TDD section).
"""
import json
import struct
from pathlib import Path

import baseline_manifest as bm


def _write_binary_stl(path, triangles):
    with Path(path).open('wb') as f:
        f.write(b'test'.ljust(80, b'\0'))
        f.write(struct.pack('<I', len(triangles)))
        for tri in triangles:
            f.write(struct.pack('<3f', 0.0, 0.0, 0.0))
            for point in tri:
                f.write(struct.pack('<3f', *point))
            f.write(struct.pack('<H', 0))


_UNIT_TRIANGLE = [[(0, 0, 0), (1, 0, 0), (0, 1, 0)]]
_OTHER_TRIANGLE = [[(0, 0, 0), (2, 0, 0), (0, 2, 0)]]


# ------------------------------------------------------------
# git_head -- a real call against this actual repository
# ------------------------------------------------------------

def test_git_head_returns_a_commit_hash_string_in_this_repo():
    head = bm.git_head()
    assert head is None or (isinstance(head, str) and len(head) == 40)


# ------------------------------------------------------------
# measure_tree -- real STL discovery, skipping partials, collecting unreadable ones
# ------------------------------------------------------------

def test_measure_tree_finds_every_stl_and_skips_partial_files(tmp_path):
    (tmp_path / 'sub').mkdir()
    _write_binary_stl(tmp_path / 'sub' / 'a.stl', _UNIT_TRIANGLE)
    _write_binary_stl(tmp_path / 'b.partial.stl', _UNIT_TRIANGLE)

    parts, bad = bm.measure_tree(tmp_path)

    assert list(parts) == ['sub/a.stl']  # posix-style relative path, per the module
    assert bad == []


def test_measure_tree_collects_unreadable_files_rather_than_raising(tmp_path):
    _write_binary_stl(tmp_path / 'broken.stl', _UNIT_TRIANGLE)
    (tmp_path / 'broken.stl').write_bytes((tmp_path / 'broken.stl').read_bytes()[:-10])

    parts, bad = bm.measure_tree(tmp_path)

    assert parts == {}
    assert len(bad) == 1 and 'broken.stl' in bad[0]


# ------------------------------------------------------------
# capture
# ------------------------------------------------------------

def test_capture_writes_a_manifest_with_the_documented_shape(tmp_path):
    tree = tmp_path / 'tree'
    tree.mkdir()
    _write_binary_stl(tree / 'part.stl', _UNIT_TRIANGLE)
    out = tmp_path / 'manifest.json'

    code = bm.capture(tree, out)

    assert code == 0
    manifest = json.loads(out.read_text(encoding='utf-8'))
    assert manifest['manifest_version'] == bm.MANIFEST_VERSION
    assert manifest['part_count'] == 1
    assert 'part.stl' in manifest['parts']
    assert manifest['unreadable'] == []
    assert manifest['note'] == bm.PROVENANCE_NOTE


def test_capture_returns_1_and_writes_nothing_when_the_tree_has_no_stl(tmp_path):
    tree = tmp_path / 'empty_tree'
    tree.mkdir()
    out = tmp_path / 'manifest.json'

    code = bm.capture(tree, out)

    assert code == 1
    assert not out.exists()


# ------------------------------------------------------------
# verify -- moved / missing / added / unreadable
# ------------------------------------------------------------

def _captured_manifest(tmp_path, triangles, part_name='part.stl'):
    tree = tmp_path / 'capture_source'
    tree.mkdir()
    _write_binary_stl(tree / part_name, triangles)
    manifest_path = tmp_path / 'manifest.json'
    bm.capture(tree, manifest_path)
    return manifest_path


def test_verify_intact_when_the_tree_matches_the_manifest_exactly(tmp_path, capsys):
    manifest_path = _captured_manifest(tmp_path, _UNIT_TRIANGLE)
    tree = tmp_path / 'tree'
    tree.mkdir()
    _write_binary_stl(tree / 'part.stl', _UNIT_TRIANGLE)

    assert bm.verify(tree, manifest_path) == 0
    assert 'baseline intact' in capsys.readouterr().out


def test_verify_reports_a_moved_part(tmp_path, capsys):
    manifest_path = _captured_manifest(tmp_path, _UNIT_TRIANGLE)
    tree = tmp_path / 'tree'
    tree.mkdir()
    _write_binary_stl(tree / 'part.stl', _OTHER_TRIANGLE)

    assert bm.verify(tree, manifest_path) == 1
    out = capsys.readouterr().out
    assert 'MOVED' in out and 'part.stl' in out


def test_verify_reports_a_missing_part(tmp_path, capsys):
    manifest_path = _captured_manifest(tmp_path, _UNIT_TRIANGLE)
    tree = tmp_path / 'tree'
    tree.mkdir()  # part.stl never written here

    assert bm.verify(tree, manifest_path) == 1
    out = capsys.readouterr().out
    assert 'MISSING' in out and 'part.stl' in out


def test_verify_reports_an_added_part_not_in_the_manifest(tmp_path, capsys):
    manifest_path = _captured_manifest(tmp_path, _UNIT_TRIANGLE)
    tree = tmp_path / 'tree'
    tree.mkdir()
    _write_binary_stl(tree / 'part.stl', _UNIT_TRIANGLE)
    _write_binary_stl(tree / 'new_part.stl', _UNIT_TRIANGLE)

    assert bm.verify(tree, manifest_path) == 1
    out = capsys.readouterr().out
    assert 'ADDED' in out and 'new_part.stl' in out
