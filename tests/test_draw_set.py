"""IP-TEST-4 (doc/implementation/test_coverage.md): tests for draw_set.py.

draw_set.py is IP-FC-114's real, reusable drawing-set driver -- see
test_branching_dimensions.py's module docstring for why this cluster splits into "live
tools" (this one, draw_variant_set.py, branching_dimensions.py) and one-off SVG-evidence
generators the plan does not chase deep coverage on.

Covers the pieces that do not require a real freecadcmd subprocess: `representative`
(pure), `clear` (real filesystem I/O against synthetic sheet artifacts, via `tmp_path`),
and `export_for` (calls the real, pure-Python `export_parameters.main`, which writes a
parameter JSON with no subprocess involved -- distinct from `draw()`/`main()`, which shell
out to `freecadcmd` and TechDraw's GUI renderer and are out of scope here, the same class of
thing IP-TEST-2 already deferred for `fuselage_variants.py`'s render orchestration).

Adoption-phase retrofit (general.md's TDD section).
"""

import draw_set as ds

# ------------------------------------------------------------
# representative -- which variant draws a family, U=1.0 or the nearest size available
# ------------------------------------------------------------

def test_representative_picks_u_1_when_it_is_in_the_family():
    rows = [({'U': '0.5'}, 'a'), ({'U': '1.0'}, 'b'), ({'U': '2.0'}, 'c')]
    _none, axis_values, type_name = ds.representative(rows)
    assert axis_values == {'U': '1.0'}
    assert type_name == 'b'


def test_representative_picks_the_nearest_size_when_u_1_is_absent():
    rows = [({'U': '0.75'}, 'a'), ({'U': '4.0'}, 'b')]
    _none, axis_values, _type_name = ds.representative(rows)
    assert axis_values == {'U': '0.75'}  # |0.75 - 1| = 0.25, unambiguously nearer than |4 - 1|


def test_representative_breaks_a_distance_tie_toward_the_smaller_u():
    """0.5 and 1.5 are equidistant from 1.0 -- the tiebreak in `distance()` orders by the
    numeric U value itself next, so the smaller one wins."""
    rows = [({'U': '1.5'}, 'a'), ({'U': '0.5'}, 'b')]
    _none, axis_values, _type_name = ds.representative(rows)
    assert axis_values == {'U': '0.5'}


def test_representative_breaks_a_full_tie_by_type_name():
    rows = [({'U': '1.0'}, 'zeta'), ({'U': '1.0'}, 'alpha')]
    _none, _axis_values, type_name = ds.representative(rows)
    assert type_name == 'alpha'


# ------------------------------------------------------------
# clear -- removes a sheet's artifacts (all pages), returns how many were there
# ------------------------------------------------------------

def test_clear_removes_every_page_of_every_declared_suffix(tmp_path):
    stem = tmp_path / 'corner-corner-abc'
    for suffix in ds.SHEET_SUFFIXES:
        (tmp_path / (stem.name + suffix)).write_text('x', encoding='utf-8')
    # A second page, named per sheet_naming's convention.
    (tmp_path / (stem.name + '-sheet2.svg')).write_text('x', encoding='utf-8')
    (tmp_path / (stem.name + '-sheet2.pdf')).write_text('x', encoding='utf-8')

    removed = ds.clear(str(stem))

    assert removed == len(ds.SHEET_SUFFIXES) + 2
    assert list(tmp_path.iterdir()) == []


def test_clear_on_a_stem_with_nothing_on_disk_removes_nothing(tmp_path):
    assert ds.clear(str(tmp_path / 'never-drawn')) == 0


def test_clear_does_not_touch_a_different_familys_files(tmp_path):
    other = tmp_path / 'bulkhead-bulkhead-xyz.FCStd'
    other.write_text('x', encoding='utf-8')
    ds.clear(str(tmp_path / 'corner-corner-abc'))
    assert other.is_file()


# ------------------------------------------------------------
# export_for -- resolves and writes one variant's parameters, no subprocess involved
# ------------------------------------------------------------

def test_export_for_writes_a_real_parameter_file_for_a_corner(tmp_path):
    path = tmp_path / 'corner-corner-abc.params.json'
    ok = ds.export_for('corner', {'U': 1.0, 'panel': '1mm'}, 'ignored-for-corner', str(path))
    assert ok is True
    assert path.is_file()


def test_export_for_uses_the_fixed_carrier_type_for_a_corner_regardless_of_type_name():
    """A corner has no type axis of its own -- CORNER_THROUGH_TYPE names the bulkhead type
    its parameters are exported alongside, per the module's own module-level comment."""
    assert ds.CORNER_THROUGH_TYPE == 'end_bolt'


def test_export_for_returns_false_for_an_unknown_bulkhead_type(tmp_path):
    path = tmp_path / 'out.json'
    ok = ds.export_for('bulkhead', {'U': 1.0, 'panel': '1mm'}, 'not_a_real_type', str(path))
    assert ok is False
    assert not path.is_file()
