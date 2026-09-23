"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for brep_snapshot.py.

`.FCStd` files are real zip archives, so the fixtures here are real zip archives built with
`zipfile`, not stand-ins for one -- `brep_members`/`digest`/`capture` read the container
format directly and a mock would hide any bug in that reading. `main()` (argparse wiring) is
not covered, consistent with the other CLI-entry-point modules in this plan.
"""
import hashlib
import json
import zipfile

import brep_snapshot as bs


def _make_fcstd(path, members: dict[str, bytes]):
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in members.items():
            z.writestr(name, data)


# ------------------------------------------------------------
# brep_members
# ------------------------------------------------------------

def test_brep_members_includes_only_dot_brp_members(tmp_path):
    path = tmp_path / 'part.FCStd'
    _make_fcstd(path, {
        'Document.xml': b'<xml/>',
        'Face1.brp': b'geometry-a',
        'Face2.BRP': b'geometry-b',   # case-insensitive suffix match
        'StringHasher.Table.txt': b'H1=abc',
    })
    members = bs.brep_members(path)
    assert set(members) == {'Face1.brp', 'Face2.BRP'}


def test_brep_members_hashes_are_sha256_of_the_member_bytes(tmp_path):
    path = tmp_path / 'part.FCStd'
    data = b'some-brep-bytes'
    _make_fcstd(path, {'Face1.brp': data})
    members = bs.brep_members(path)
    assert members['Face1.brp'] == hashlib.sha256(data).hexdigest()


def test_brep_members_is_empty_for_a_document_with_no_brep_members(tmp_path):
    path = tmp_path / 'part.FCStd'
    _make_fcstd(path, {'Document.xml': b'<xml/>'})
    assert bs.brep_members(path) == {}


# ------------------------------------------------------------
# digest
# ------------------------------------------------------------

def test_digest_matches_a_hand_computed_hash_over_name_and_member_hash(tmp_path):
    path = tmp_path / 'part.FCStd'
    _make_fcstd(path, {'A.brp': b'aaa', 'B.brp': b'bbb'})
    count, dg = bs.digest(path)
    assert count == 2

    expected = hashlib.sha256()
    for name in ('A.brp', 'B.brp'):   # sorted namelist order
        expected.update(name.encode())
        expected.update(hashlib.sha256({'A.brp': b'aaa', 'B.brp': b'bbb'}[name]
                                       ).hexdigest().encode())
    assert dg == expected.hexdigest()


def test_digest_is_stable_across_repeated_calls_on_the_same_file(tmp_path):
    path = tmp_path / 'part.FCStd'
    _make_fcstd(path, {'A.brp': b'aaa'})
    assert bs.digest(path) == bs.digest(path)


def test_digest_changes_when_a_member_is_renamed_even_with_identical_content():
    """The module's own contract: 'name included so a rename is a difference' -- a rename
    with unchanged geometry bytes must still produce a different digest."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p1, p2 = Path(d) / 'a.FCStd', Path(d) / 'b.FCStd'
        _make_fcstd(p1, {'Face1.brp': b'same'})
        _make_fcstd(p2, {'Face2.brp': b'same'})
        assert bs.digest(p1)[1] != bs.digest(p2)[1]


def test_digest_changes_when_member_content_changes(tmp_path):
    path_a = tmp_path / 'a.FCStd'
    path_b = tmp_path / 'b.FCStd'
    _make_fcstd(path_a, {'Face1.brp': b'geometry-1'})
    _make_fcstd(path_b, {'Face1.brp': b'geometry-2'})
    assert bs.digest(path_a)[1] != bs.digest(path_b)[1]


# ------------------------------------------------------------
# capture
# ------------------------------------------------------------

def test_capture_returns_1_and_reports_when_no_fcstd_files_exist(tmp_path, capsys):
    root = tmp_path / 'empty_dir'
    root.mkdir()
    out_path = tmp_path / 'snap.json'
    assert bs.capture(root, out_path) == 1
    assert not out_path.exists()
    assert 'no .FCStd found' in capsys.readouterr().err


def test_capture_writes_a_snapshot_with_digest_and_members_per_document(tmp_path, capsys):
    root = tmp_path / 'parts'
    root.mkdir()
    _make_fcstd(root / 'bulkhead.FCStd', {'Face1.brp': b'geo'})
    _make_fcstd(root / 'corner.FCStd', {'Face1.brp': b'geo2', 'Face2.brp': b'geo3'})
    out_path = tmp_path / 'snap.json'

    assert bs.capture(root, out_path) == 0
    snap = json.loads(out_path.read_text(encoding='utf-8'))
    assert snap['root'] == 'parts'
    docs = snap['documents']
    assert docs['bulkhead.FCStd']['brep_members'] == 1
    assert docs['corner.FCStd']['brep_members'] == 2
    assert docs['corner.FCStd']['digest'] == bs.digest(root / 'corner.FCStd')[1]
    assert 'captured 2 document(s)' in capsys.readouterr().out


def test_capture_finds_fcstd_files_in_nested_directories(tmp_path):
    root = tmp_path / 'parts'
    (root / 'nested').mkdir(parents=True)
    _make_fcstd(root / 'nested' / 'bulkhead.FCStd', {'Face1.brp': b'geo'})
    out_path = tmp_path / 'snap.json'
    assert bs.capture(root, out_path) == 0
    snap = json.loads(out_path.read_text(encoding='utf-8'))
    assert 'nested/bulkhead.FCStd' in snap['documents']


def test_capture_records_an_error_for_a_document_that_is_not_a_valid_zip(tmp_path):
    root = tmp_path / 'parts'
    root.mkdir()
    (root / 'broken.FCStd').write_bytes(b'not a zip file')
    out_path = tmp_path / 'snap.json'
    assert bs.capture(root, out_path) == 0
    snap = json.loads(out_path.read_text(encoding='utf-8'))
    assert 'error' in snap['documents']['broken.FCStd']


# ------------------------------------------------------------
# compare
# ------------------------------------------------------------

def test_compare_reports_identical_when_snapshots_match(tmp_path, capsys):
    root = tmp_path / 'parts'
    root.mkdir()
    _make_fcstd(root / 'part.FCStd', {'Face1.brp': b'geo'})
    before = tmp_path / 'before.json'
    after = tmp_path / 'after.json'
    bs.capture(root, before)
    bs.capture(root, after)

    assert bs.compare(before, after) == 0
    out = capsys.readouterr().out
    assert 'identical B-rep across 1 document(s)' in out


def test_compare_reports_a_changed_member_within_a_document(tmp_path, capsys):
    root_a = tmp_path / 'a'
    root_b = tmp_path / 'b'
    root_a.mkdir()
    root_b.mkdir()
    _make_fcstd(root_a / 'part.FCStd', {'Face1.brp': b'geo-before'})
    _make_fcstd(root_b / 'part.FCStd', {'Face1.brp': b'geo-after'})
    before, after = tmp_path / 'before.json', tmp_path / 'after.json'
    bs.capture(root_a, before)
    bs.capture(root_b, after)

    assert bs.compare(before, after) == 1
    out = capsys.readouterr().out
    assert 'CHANGED  part.FCStd' in out
    assert 'Face1.brp' in out
    assert 'B-REP CHANGED -- 1 document(s) differ' in out


def test_compare_reports_a_structural_change_when_a_member_is_added(tmp_path, capsys):
    root_a = tmp_path / 'a'
    root_b = tmp_path / 'b'
    root_a.mkdir()
    root_b.mkdir()
    _make_fcstd(root_a / 'part.FCStd', {'Face1.brp': b'geo'})
    _make_fcstd(root_b / 'part.FCStd', {'Face1.brp': b'geo', 'Face2.brp': b'new'})
    before, after = tmp_path / 'before.json', tmp_path / 'after.json'
    bs.capture(root_a, before)
    bs.capture(root_b, after)

    assert bs.compare(before, after) == 1
    out = capsys.readouterr().out
    assert '1 member(s) added or removed' in out
    assert 'Face2.brp' in out


def test_compare_reports_a_document_that_disappeared_as_gone(tmp_path, capsys):
    root_a = tmp_path / 'a'
    root_b = tmp_path / 'b'
    root_a.mkdir()
    root_b.mkdir()
    _make_fcstd(root_a / 'gone.FCStd', {'Face1.brp': b'geo'})
    _make_fcstd(root_b / 'still_here.FCStd', {'Face1.brp': b'geo'})
    before, after = tmp_path / 'before.json', tmp_path / 'after.json'
    bs.capture(root_a, before)
    bs.capture(root_b, after)

    assert bs.compare(before, after) == 1
    out = capsys.readouterr().out
    assert 'GONE     gone.FCStd' in out


def test_compare_reports_a_new_document_as_new(tmp_path, capsys):
    root_a = tmp_path / 'a'
    root_b = tmp_path / 'b'
    root_a.mkdir()
    root_b.mkdir()
    _make_fcstd(root_a / 'existing.FCStd', {'Face1.brp': b'geo'})
    _make_fcstd(root_b / 'existing.FCStd', {'Face1.brp': b'geo'})
    _make_fcstd(root_b / 'brand_new.FCStd', {'Face1.brp': b'geo'})
    before, after = tmp_path / 'before.json', tmp_path / 'after.json'
    bs.capture(root_a, before)
    bs.capture(root_b, after)

    assert bs.compare(before, after) == 1
    out = capsys.readouterr().out
    assert 'NEW      brand_new.FCStd' in out
