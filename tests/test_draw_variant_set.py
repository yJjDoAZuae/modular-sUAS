"""IP-TEST-4 (doc/implementation/test_coverage.md): tests for draw_variant_set.py.

See test_branching_dimensions.py's module docstring for why this module gets real coverage
where the one-off SVG-evidence generators alongside it do not.

Covers `clear`, `export_for`, and `pair_dir` (no freecadcmd subprocess involved), plus a
structural consistency check on `PARTS`/`FIXED_PANEL` -- the same style of self-check as
`drawing_families.check_topology_fields`: a `FIXED_PANEL` entry naming a type not in `PARTS`
would silently do nothing, and nothing else would say so. `build_set`/`draw_variant`/`main`
call `freecadcmd` as a real subprocess and are out of scope here, the same class of thing
IP-TEST-2 already deferred for `fuselage_variants.py`'s render orchestration.

Adoption-phase retrofit (general.md's TDD section).
"""
import draw_variant_set as dvs

# ------------------------------------------------------------
# clear -- identical contract to draw_set.clear (deliberately duplicated there, not
# imported, per this module's own comment -- so tested the same way, independently)
# ------------------------------------------------------------

def test_clear_removes_every_page_of_every_declared_suffix(tmp_path):
    stem = tmp_path / 'corner'
    for suffix in dvs.SHEET_SUFFIXES:
        (tmp_path / (stem.name + suffix)).write_text('x', encoding='utf-8')
    (tmp_path / (stem.name + '-sheet2.svg')).write_text('x', encoding='utf-8')

    removed = dvs.clear(str(stem))

    assert removed == len(dvs.SHEET_SUFFIXES) + 1
    assert list(tmp_path.iterdir()) == []


def test_clear_on_a_stem_with_nothing_on_disk_removes_nothing(tmp_path):
    assert dvs.clear(str(tmp_path / 'never-drawn')) == 0


# ------------------------------------------------------------
# export_for -- pure-Python parameter export, no subprocess
# ------------------------------------------------------------

def test_export_for_writes_a_real_parameter_file():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.json'
        ok = dvs.export_for(1.0, 'end_bolt', '1mm', str(path))
        assert ok is True
        assert path.is_file()


def test_export_for_returns_false_for_a_combination_outside_the_swept_axes():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.json'
        ok = dvs.export_for(1.0, 'not_a_real_type', '1mm', str(path))
        assert ok is False
        assert not path.is_file()


# ------------------------------------------------------------
# pair_dir -- where one (U, panel) set lives, shared with sweep_variant_sets.py
# ------------------------------------------------------------

def test_pair_dir_names_the_directory_by_u_and_panel():
    assert dvs.pair_dir('out', 1.0, '3/16in') == dvs.os.path.join('out', 'U1.0_3-16in')


def test_pair_dir_escapes_a_slash_in_the_panel_name():
    """A panel name can contain '/' (fractional-inch stock); the directory name cannot."""
    assert '/' not in dvs.pair_dir('out', 1.0, '3/16in').split(dvs.os.sep)[-1]


# ------------------------------------------------------------
# PARTS / FIXED_PANEL -- structural self-consistency, the same class of check
# drawing_families.check_topology_fields runs for TOPOLOGY_FIELDS
# ------------------------------------------------------------

def test_fixed_panel_only_names_types_that_are_actually_in_parts():
    part_types = {type_name for _label, type_name, _kind in dvs.PARTS}
    assert set(dvs.FIXED_PANEL) <= part_types


def test_parts_labels_are_unique():
    labels = [label for label, _t, _k in dvs.PARTS]
    assert len(labels) == len(set(labels))


def test_parts_type_names_are_unique_within_each_draw_kind():
    """Not globally unique -- CORNER_THROUGH_TYPE ('end_bolt') legitimately repeats the real
    bulkhead_end_bolt row's own type name, since the corner rides on it purely to get a
    valid export. What must not repeat is two rows of the *same* draw_kind resolving through
    the same type name, which would make one of them unreachable."""
    by_kind = {}
    for _label, type_name, kind in dvs.PARTS:
        by_kind.setdefault(kind, []).append(type_name)
    for kind, types in by_kind.items():
        assert len(types) == len(set(types)), kind


def test_corner_is_drawn_through_a_real_bulkhead_type():
    """CORNER_THROUGH_TYPE has to be one of PARTS' own bulkhead type names -- it is the
    fixture the corner rides on, per the module's own docstring."""
    bulkhead_types = {t for _label, t, kind in dvs.PARTS if kind == 'bulkhead'}
    assert dvs.CORNER_THROUGH_TYPE in bulkhead_types
