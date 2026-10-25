"""Unit tests for `section_figure`, the SVG section drawing used by cowl_interior_surface.md 6.3.

No FreeCAD here by design: the module receives coordinate arrays and emits markup, so everything
it does is checkable against arithmetic. The three things worth testing are the coordinate flip
(model y up, SVG y down), that the drawing really is to scale, and that a zoom window is centered
where it claims to be -- a figure whose scale bar lies is worse than no figure.
"""
import math
import re

import pytest

from section_figure import (ENGAGEMENT_FILL, ROLE_STYLE, SectionFigure, Window,
                            draw_clearance_station, nice_length, role_polylines, _fmt, _mm)


SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _numbers(path_d):
    return [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', path_d)]


# -- Window --------------------------------------------------------------------------


def test_projection_flips_y_and_offsets_by_pad():
    win = Window(0.0, 0.0, 10.0, 10.0, scale=4.0, pad=5.0)
    # model y_lo maps to the BOTTOM of the drawing, which is the larger SVG y
    assert win.project((0.0, 0.0)) == (5.0, 45.0)
    assert win.project((0.0, 10.0)) == (5.0, 5.0)
    assert win.project((10.0, 0.0)) == (45.0, 45.0)


def test_projection_is_a_similarity_so_the_drawing_is_to_scale():
    win = Window(-3.0, 7.0, 9.0, 21.0, scale=3.25, pad=11.0)
    a, b = (1.0, 9.0), (4.0, 13.0)
    pa, pb = win.project(a), win.project(b)
    model = math.hypot(b[0] - a[0], b[1] - a[1])
    drawn = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
    assert drawn == pytest.approx(model * 3.25, rel=1e-12)


def test_size_px_covers_the_window_plus_both_pads():
    win = Window(0.0, 0.0, 8.0, 4.0, scale=10.0, pad=7.0)
    assert win.size_px == (8.0 * 10.0 + 14.0, 4.0 * 10.0 + 14.0)


def test_asymmetric_pads_reserve_bands_the_geometry_never_enters():
    """The legend sits in the top band and the title in the bottom one, so neither can land on
    the drawing -- which is what happened when both were placed over it."""
    win = Window(0.0, 0.0, 10.0, 10.0, scale=10.0, pad=8.0, pad_top=90.0, pad_bottom=40.0)
    assert win.size_px == (100.0 + 16.0, 100.0 + 130.0)
    # the topmost model point sits below the whole top band
    assert win.project((0.0, 10.0))[1] == 90.0
    assert win.project((0.0, 0.0))[1] == 190.0


def test_nice_length_returns_a_1_2_5_value_near_the_target():
    assert nice_length(100.0, 0.2) == 20.0
    assert nice_length(4.3, 0.2) == 1.0
    assert nice_length(0.9, 0.2) == 0.2
    assert nice_length(0.3, 0.2) == 0.1
    for span in (1e-4, 1e-2, 1.0, 7.3, 912.0):
        got = nice_length(span)
        assert got > 0.0
        mantissa = got / 10.0 ** math.floor(math.log10(got))
        assert round(mantissa, 6) in (1.0, 2.0, 5.0)


def test_nice_length_never_returns_zero_for_a_degenerate_span():
    assert nice_length(0.0) > 0.0


def test_mm_switches_to_nanometers_below_a_micron():
    """Several of these readings are tens of nanometers; "0.000081 mm" is a zero-counting
    exercise and the figure has to be read at a glance."""
    assert _mm(0.000081) == '81 nm'
    assert _mm(0.0785) == '0.079 mm'
    assert _mm(3.71) == '3.71 mm'
    assert _mm(20.0) == '20 mm'
    assert _mm(0.0009) == '900 nm'                 # the boundary is 1 micron, not 1 mm


def test_fit_covers_every_point_with_a_margin():
    win = Window.fit([SQUARE], width_px=200.0, margin=0.1)
    for pt in SQUARE:
        assert win.contains(pt)
    # the margin is a tenth of the 10 mm span, outside the box on every side
    assert win.x_lo == pytest.approx(-1.0)
    assert win.x_hi == pytest.approx(11.0)


def test_fit_chooses_scale_from_the_requested_pixel_width():
    win = Window.fit([SQUARE], width_px=240.0, margin=0.0)
    assert win.scale == pytest.approx(24.0)


def test_fit_of_a_degenerate_point_set_still_gives_a_usable_window():
    win = Window.fit([[(5.0, 5.0)]], width_px=100.0, margin=0.1)
    assert win.x_hi > win.x_lo and win.y_hi > win.y_lo


def test_around_is_centered_and_square():
    win = Window.around((3.0, -4.0), 0.08, width_px=300.0)
    assert (win.x_lo + win.x_hi) / 2.0 == pytest.approx(3.0)
    assert (win.y_lo + win.y_hi) / 2.0 == pytest.approx(-4.0)
    assert (win.x_hi - win.x_lo) == pytest.approx(0.08)
    assert win.scale == pytest.approx(300.0 / 0.08)


def test_around_rejects_a_non_positive_width():
    with pytest.raises(ValueError):
        Window.around((0.0, 0.0), 0.0)


def test_window_rejects_inverted_extent_and_bad_scale():
    with pytest.raises(ValueError):
        Window(1.0, 0.0, 0.0, 1.0, scale=1.0)
    with pytest.raises(ValueError):
        Window(0.0, 0.0, 1.0, 1.0, scale=0.0)


def test_fit_with_no_points_is_an_error_not_an_empty_figure():
    with pytest.raises(ValueError):
        Window.fit([])


# -- markup --------------------------------------------------------------------------


def test_closed_polyline_closes_the_path_and_open_one_does_not():
    fig = SectionFigure(Window(0.0, 0.0, 10.0, 10.0, scale=2.0, pad=0.0))
    fig.polyline(SQUARE, closed=True)
    fig.polyline([(0.0, 0.0), (1.0, 1.0)], closed=False)
    out = fig.render()
    paths = re.findall(r'<path d="([^"]+)"', out)
    assert paths[0].endswith(' Z')
    assert not paths[1].endswith(' Z')


def test_rendered_svg_is_well_formed_and_declares_its_size():
    fig = SectionFigure(Window(0.0, 0.0, 10.0, 5.0, scale=10.0, pad=10.0),
                        title='T', subtitle='S')
    fig.polyline(SQUARE, closed=True).frame().scale_bar(1.0)
    out = fig.render()
    import xml.etree.ElementTree as ET
    root = ET.fromstring(out)                      # raises if malformed
    assert root.get('width') == _fmt(120.0)
    assert root.get('height') == _fmt(70.0)
    assert root.get('viewBox') == '0 0 %s %s' % (_fmt(120.0), _fmt(70.0))


def test_title_and_subtitle_are_escaped_not_injected():
    fig = SectionFigure(Window(0.0, 0.0, 1.0, 1.0, scale=10.0),
                        title='a < b & "c"', subtitle='<desc>')
    out = fig.render()
    import xml.etree.ElementTree as ET
    ET.fromstring(out)
    assert '&lt;' in out and '&amp;' in out
    assert '<desc><desc>' not in out


def test_scale_bar_is_exactly_as_long_as_it_says():
    win = Window(0.0, 0.0, 10.0, 10.0, scale=8.0, pad=10.0)
    fig = SectionFigure(win)
    fig.scale_bar(2.5)
    out = fig.render()
    bar = re.findall(r'<path d="M ([-\d.]+) ([-\d.]+) L ([-\d.]+) ([-\d.]+)"', out)[0]
    drawn_px = abs(float(bar[2]) - float(bar[0]))
    assert drawn_px == pytest.approx(2.5 * 8.0, rel=1e-9)


def test_legend_has_one_row_per_labeled_layer_only():
    fig = SectionFigure(Window(0.0, 0.0, 10.0, 10.0, scale=4.0))
    fig.polyline(SQUARE, label='kept', stroke='#111111')
    fig.polyline(SQUARE, label=None, stroke='#222222')
    fig.polyline(SQUARE, label='also kept', stroke='#333333')
    fig.legend()
    out = fig.render()
    assert out.count('>kept<') == 1
    assert out.count('>also kept<') == 1
    assert '#222222' in out                        # drawn, just not in the legend


def test_legend_extra_rows_are_rendered_as_text():
    fig = SectionFigure(Window(0.0, 0.0, 10.0, 10.0, scale=4.0))
    fig.legend(extra=('engagement: crossing', 'fraction inside: 0.8 %'))
    out = fig.render()
    assert 'engagement: crossing' in out
    assert 'fraction inside: 0.8 %' in out


def test_measure_draws_the_segment_between_the_two_measured_points():
    win = Window(0.0, 0.0, 10.0, 10.0, scale=10.0, pad=0.0)
    fig = SectionFigure(win)
    fig.measure((2.0, 5.0), (4.0, 5.0), body='d')
    out = fig.render()
    want = 'M %s %s L %s %s' % (_fmt(20.0), _fmt(50.0), _fmt(40.0), _fmt(50.0))
    assert want in out


def test_measure_of_a_zero_length_segment_still_renders():
    """A crossing station's true in-plane distance is zero; the figure must not divide by it."""
    fig = SectionFigure(Window(0.0, 0.0, 10.0, 10.0, scale=10.0))
    fig.measure((5.0, 5.0), (5.0, 5.0), body='0')
    import xml.etree.ElementTree as ET
    ET.fromstring(fig.render())


def test_fmt_is_stable_so_two_runs_give_identical_markup():
    assert _fmt(1.0) == '1'
    assert _fmt(1.5) == '1.5'
    assert _fmt(1.23456) == '1.235'
    assert _fmt(-0.0) in ('0', '-0')
    a = SectionFigure(Window(0.0, 0.0, 10.0, 10.0, scale=3.0)).polyline(SQUARE).render()
    b = SectionFigure(Window(0.0, 0.0, 10.0, 10.0, scale=3.0)).polyline(SQUARE).render()
    assert a == b


# -- role grouping and the composite figure ------------------------------------------


def test_role_polylines_groups_by_role_and_keeps_every_edge():
    edges = [dict(role='cheek', points=[(0, 0), (1, 0)]),
             dict(role='floor', points=[(1, 0), (1, 1)]),
             dict(role='cheek', points=[(1, 1), (0, 1)])]
    grouped = role_polylines(edges)
    assert sorted(grouped) == ['cheek', 'floor']
    assert len(grouped['cheek']) == 2
    assert len(grouped['floor']) == 1


def test_every_role_the_scan_can_report_has_a_style():
    """`tool_face_roles` emits exactly these four; an unstyled role would draw as a default."""
    assert sorted(ROLE_STYLE) == ['cheek', 'end', 'floor', 'outer']


def test_only_floor_is_described_as_bounding_the_wall():
    """The point of the figure: three roles bound something that is not the wall's thickness."""
    assert 'bounds the wall' in ROLE_STYLE['floor']['label']
    for role in ('cheek', 'end', 'outer'):
        assert 'bounds the wall' not in ROLE_STYLE[role]['label']


def test_every_engagement_state_has_a_distinct_color():
    assert sorted(ENGAGEMENT_FILL) == ['clear', 'crossing', 'engulfed']
    assert len(set(ENGAGEMENT_FILL.values())) == 3


def test_draw_clearance_station_includes_all_three_geometries_and_the_measure():
    record = dict(z=-36.947, metric_a=0.000081, engagement='crossing',
                  p_surf=(5.0, 5.0), p_tool=(5.02, 5.0), role='cheek')
    surface = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]
    dilated = [[(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]]
    edges = [dict(role='cheek', points=[(4.3, 4.3), (5.7, 4.3)]),
             dict(role='floor', points=[(5.7, 4.3), (5.7, 5.7)])]
    fig = draw_clearance_station(record, surface, dilated, edges, title='t')
    out = fig.legend().render()
    import xml.etree.ElementTree as ET
    ET.fromstring(out)
    assert 'interior candidate surface' in out
    assert 'dilated by t' in out
    assert ROLE_STYLE['floor']['stroke'] in out
    assert ROLE_STYLE['cheek']['stroke'] in out
    assert 'Metric A = 81 nm' in out              # see `_mm`: microns are unreadable in mm
    assert ENGAGEMENT_FILL['crossing'] in out


def test_annotate_false_draws_the_segment_without_its_caption():
    """At part scale a micron-level number is noise; the segment still has to be drawn."""
    record = dict(metric_a=0.000081, engagement='crossing',
                  p_surf=(5.0, 5.0), p_tool=(5.02, 5.0), role='cheek')
    args = ([[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]],
            [[(4.0, 4.0), (6.0, 4.0), (6.0, 6.0)]],
            [dict(role='cheek', points=[(4.3, 4.3), (5.7, 4.3)])])
    on = draw_clearance_station(record, *args, annotate=True).render()
    off = draw_clearance_station(record, *args, annotate=False).render()
    assert 'Metric A' in on
    assert 'Metric A' not in off
    assert off.count('<path') >= 3


def test_a_role_entirely_outside_the_window_gets_no_legend_row():
    """A buttress tool's `outer` face is ~100 mm from the contact; promising it is worse than
    omitting it, because the reader then hunts for a color that is not drawn."""
    record = dict(metric_a=0.001, engagement='clear',
                  p_surf=(0.0, 0.0), p_tool=(0.001, 0.0), role='floor')
    edges = [dict(role='floor', points=[(-0.05, 0.0), (0.05, 0.0)]),
             dict(role='outer', points=[(-0.05, 100.0), (0.05, 100.0)])]
    win = Window.around((0.0, 0.0), 1.0, width_px=300.0)
    out = draw_clearance_station(record, [], [], edges, window=win).legend().render()
    assert ROLE_STYLE['floor']['label'] in out
    assert ROLE_STYLE['outer']['label'] not in out


def test_draw_clearance_station_window_covers_every_supplied_point():
    record = dict(metric_a=0.5, engagement='clear', p_surf=(0.0, 0.0), p_tool=(0.5, 0.0))
    surface = [[(-20.0, -20.0), (20.0, -20.0), (20.0, 20.0)]]
    dilated = [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]]
    edges = [dict(role='floor', points=[(0.2, 0.2), (0.8, 0.2)])]
    fig = draw_clearance_station(record, surface, dilated, edges)
    for poly in surface + dilated + [e['points'] for e in edges]:
        for pt in poly:
            assert fig.window.contains(pt)


def test_draw_clearance_station_accepts_an_explicit_zoom_window():
    record = dict(metric_a=0.001, engagement='clear', p_surf=(5.0, 5.0), p_tool=(5.001, 5.0))
    win = Window.around((5.0, 5.0), 0.01, width_px=300.0)
    fig = draw_clearance_station(
        record, [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]],
        [[(4.9, 4.9), (5.1, 4.9), (5.1, 5.1)]],
        [dict(role='cheek', points=[(4.95, 4.95), (5.05, 4.95)])], window=win)
    assert fig.window is win
    import xml.etree.ElementTree as ET
    ET.fromstring(fig.render())


def test_write_uses_lf_and_utf8(tmp_path):
    out = tmp_path / 'f.svg'
    SectionFigure(Window(0.0, 0.0, 1.0, 1.0, scale=10.0), title='x').polyline(SQUARE).write(
        str(out))
    raw = out.read_bytes()
    assert b'\r\n' not in raw
    assert raw.decode('utf-8').startswith('<?xml')
