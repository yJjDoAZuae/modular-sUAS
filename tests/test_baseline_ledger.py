"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for baseline_ledger.py.

OQ-ARCH-15's departure-tracking mechanism, exercised against real STL files and real
manifest/ledger JSON under `tmp_path` -- not mocked, since `check()`'s whole job is
comparing real measured geometry (via `mesh_stats`) against a recorded expectation.

Adoption-phase retrofit (general.md's TDD section).
"""
import json
import struct
from pathlib import Path

import baseline_ledger as bl
import mesh_stats


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
# load / accepted_parts
# ------------------------------------------------------------

def test_load_reads_json(tmp_path):
    path = tmp_path / 'x.json'
    path.write_text(json.dumps({'a': 1}), encoding='utf-8')
    assert bl.load(path) == {'a': 1}


def test_accepted_parts_maps_each_part_to_its_groups_id():
    ledger = {'accepted': [
        {'id': 'grp-1', 'commit': 'abc', 'parts': ['a.stl', 'b.stl']},
        {'id': 'grp-2', 'commit': 'def', 'parts': ['c.stl']},
    ]}
    assert bl.accepted_parts(ledger) == {'a.stl': 'grp-1', 'b.stl': 'grp-1', 'c.stl': 'grp-2'}


def test_accepted_parts_empty_ledger_is_empty():
    assert bl.accepted_parts({}) == {}


# ------------------------------------------------------------
# check -- against real STL files and real manifest/ledger JSON
# ------------------------------------------------------------

def _setup(tmp_path, tree_triangles, manifest_triangles, accepted_groups=()):
    tree = tmp_path / 'tree'
    tree.mkdir()
    rel = 'U_1.0/part.stl'
    (tree / 'U_1.0').mkdir()
    _write_binary_stl(tree / rel, tree_triangles)

    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(json.dumps(
        {'parts': {rel: _measure(tmp_path, manifest_triangles)}}),
        encoding='utf-8')

    ledger_path = tmp_path / 'ledger.json'
    ledger_path.write_text(json.dumps({'accepted': list(accepted_groups)}), encoding='utf-8')

    return tree, manifest_path, ledger_path, rel


def _measure(tmp_path, triangles):
    ref = tmp_path / '_ref.stl'
    _write_binary_stl(ref, triangles)
    return mesh_stats.mesh_stats(str(ref))


def test_check_returns_0_when_every_part_matches_the_manifest(tmp_path, capsys):
    tree, manifest_path, ledger_path, _rel = _setup(
        tmp_path, _UNIT_TRIANGLE, _UNIT_TRIANGLE)
    assert bl.check(tree, manifest_path, ledger_path) == 0
    assert 'accounted for' in capsys.readouterr().out


def test_check_returns_1_for_an_unexplained_departure(tmp_path, capsys):
    tree, manifest_path, ledger_path, rel = _setup(
        tmp_path, _OTHER_TRIANGLE, _UNIT_TRIANGLE)
    assert bl.check(tree, manifest_path, ledger_path) == 1
    out = capsys.readouterr().out
    assert 'UNEXPLAINED' in out and rel in out


def test_check_returns_0_when_the_departure_is_in_the_ledger(tmp_path, capsys):
    known_rel = 'U_1.0/part.stl'  # matches the fixed `rel` _setup always writes at
    tree, manifest_path, ledger_path, rel = _setup(
        tmp_path, _OTHER_TRIANGLE, _UNIT_TRIANGLE,
        accepted_groups=[{'id': 'grp-1', 'commit': 'abc', 'parts': [known_rel]}])
    assert rel == known_rel
    assert bl.check(tree, manifest_path, ledger_path) == 0
    out = capsys.readouterr().out
    assert '1 accepted departure' in out


def test_check_reports_a_missing_part_and_returns_1(tmp_path, capsys):
    tree = tmp_path / 'tree'
    tree.mkdir()
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(json.dumps(
        {'parts': {'never_written.stl': _measure(tmp_path, _UNIT_TRIANGLE)}}),
        encoding='utf-8')
    ledger_path = tmp_path / 'ledger.json'
    ledger_path.write_text(json.dumps({'accepted': []}), encoding='utf-8')

    assert bl.check(tree, manifest_path, ledger_path) == 1
    out = capsys.readouterr().out
    assert 'MISSING' in out and 'never_written.stl' in out


def test_check_reports_a_truncated_file_as_unreadable_not_a_crash(tmp_path, capsys):
    tree = tmp_path / 'tree'
    tree.mkdir()
    rel = 'broken.stl'
    _write_binary_stl(tree / rel, _UNIT_TRIANGLE)
    (tree / rel).write_bytes((tree / rel).read_bytes()[:-10])  # truncate mid-facet

    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(json.dumps(
        {'parts': {rel: _measure(tmp_path, _UNIT_TRIANGLE)}}), encoding='utf-8')
    ledger_path = tmp_path / 'ledger.json'
    ledger_path.write_text(json.dumps({'accepted': []}), encoding='utf-8')

    assert bl.check(tree, manifest_path, ledger_path) == 1
    out = capsys.readouterr().out
    assert 'UNEXPLAINED' in out and 'unreadable' in out
