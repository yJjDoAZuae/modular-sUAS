"""IP-WTM-41: the design-input axis the `U` corpus does not cover, as a case list code can iterate.

**What this is for.** `cowl.md` OQ-DES-CW26 asks whether an unperturbed build can reach the
severed-ring state -- a finished wall whose cross-section ring is broken while every one of the
construction's five checks passes. IP-WTM-40 answered that as far as the saved corpus can: all
twelve distinct walls scanned at 1 mm axially, 1 704 stations, none severed. That scan's own bound
is recorded in the same place and is the reason this module exists: **those twelve walls vary in `U`
alone**, with every other design input at the parameter sheet's literal, so the scan says nothing
about a configuration the corpus does not contain.

**Why a new corpus and not the 2026-09-30 screen's.** A free-parameter screen of 21 cases was run
then and produced no construction failure, but it tested construction *validity* (`isValid()`) on
the **round-0** construction -- fit, dilate, cut -- and did not run `shell_solid` to a finished wall
or save anything. `ring_scan` reads a finished wall off disk. So the walls have to be built.

**Deltas are in the row's own units, which for a fraction row is the fraction.** The sheet states
design values as fractions of `unit_width` and placements as expressions over it
(`cowl_tree.PARAMS_TAIL`'s comment has the reasoning), which is what makes `U` alone sufficient to
rescale a cowl. A case written as "+1 mm" would therefore mean a different design at every `U`; a
case written as "+0.02 of `unit_width`" is the same design at all of them. `bump` applies the delta
to the coefficient and keeps the expression form, so a case is portable across `U` even though this
screen runs at one.

**The sign convention is the coefficient's, not the position's.** `side1_x` is
`=-unit_width * 0.30`; a positive delta there makes the coefficient larger and the placement *more*
negative. Stated because it is the kind of thing that silently inverts a reading, not because any
case here depends on it.

**Eleven tools, and why the `side*` and `bottom*` placements get no case of their own.** Four of the
excursions below -- `buttress_cut_thickness`, `buttress_r_inset`, `overhang_angle_from_bed` and
`extrusion_width` -- move *every* tool at once: how wide each cuts, how far each is set in, how its
dilation ramp leans, and how thick the wall it has to leave is. Crowding between neighbouring ribs
is what IP-FC-137's follow-up reproduced a pathological topology from, and those four change the
crowding of all eleven. A case per placement would add eleven tail builds at about 1 000 s each to
cover the same axis one rib at a time.

**What bounds the input space is `RIB_FACETS`, and the screen found it in its first two cases.**
`cowl_interior.dilated_notches` builds a tool's dilation as the union of `RIB_FACETS` = 48 translated
copies on a circle of radius `t`, so adjacent copies sit `2 t sin(pi / N)` apart and the union is a
solid only while that is smaller than the slab's own in-plane thickness. The buildable region is
therefore

    in_plane / t  >  2 sin(pi / RIB_FACETS)  =  0.130806

and the nose sits at `0.1 / 0.6` = 0.166667, which is 1.274x the floor. **That margin is consumed by
a single-parameter excursion in either direction**: `buttress_cut_thickness` 0.1 -> 0.07 mm is
refused (needs 55 facets) and `extrusion_width` 0.6 -> 0.8 mm is refused (needs 52), both before any
wall exists to scan. `RIB_FACETS`' own note prices the headroom as "26 %" in facet count at the
sheet's values; this is the same fact read along the design inputs, where it says the floor is
`buttress_cut_thickness` > 0.0785 mm at `t` = 0.6 and `extrusion_width` < 0.7644 mm at one
perimeter. It is a fixed **count** standing against a ratio that two design rows move, which is the
sixth place in this subsystem where that pattern has turned up and the first where it bounds what
can be built rather than biasing what is measured. What to do about it is `cowl.md` OQ-DES-CW32.

**Nothing here imports a vendor module**, in keeping with the rest of this package: the rows in and
out are the sheet's own `(alias, text)` pairs, so the case arithmetic is testable without FreeCAD
and without a build. The driver is `freecad/input_screen.py`; the scan that reads the walls back is
`freecad/ring_scan.py --family=screen`.
"""
import json
import os
import re
import sys

#: Where `input_screen.py` leaves its walls and records, relative to this file. A directory of its
#: own rather than the soak's: `corpus.available` parses `kind_U<u>_r<n>.brep` and these walls are
#: not that, and a screen wall silently joining the `U` corpus would make a figure taken across
#: "the corpus" mean two different things.
_HERE = os.path.dirname(os.path.abspath(__file__))
SCREEN_DIR = os.path.normpath(os.path.join(_HERE, '..', '..', 'freecad', 'out', 'screen'))
SCREEN_SHAPES = os.path.join(SCREEN_DIR, 'shapes')
SCREEN_RECORDS = os.path.join(SCREEN_DIR, 'records')

#: `=unit_width * 0.07`, `=-unit_width * 0.30`. The only expression form a case may perturb: the
#: coefficient is the design fraction and bumping it is a design change. Anything else -- a derived
#: row like `=cut_len + buttress_z_offset`, or `=U * 100` -- raises rather than being guessed at,
#: because a regex that matched them would be editing a *relationship* and not a value.
_COEFFICIENT = re.compile(r'^=\s*(-?)unit_width\s*\*\s*(-?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*$')

#: The baseline case's name: the sheet's own literals, nothing overridden. Run first and not for
#: form's sake -- it is the control that says this harness builds what the soak built.
BASELINE = 'base'


class Excursion(object):
    """One design input moved off the sheet's value, in that row's own units, with the reason.

    `delta` is applied in both directions by default, giving a `_lo` and a `_hi` case. `why` is
    carried into the record and the table because a screen whose case list has no stated reasoning
    cannot be argued with later -- the 2026-09-30 screen's magnitudes are the example, chosen at
    0.5 mm and later found to be larger than the 0.6 mm wall they were perturbing.

    **`signs` exists for the row whose other direction is not a design.** `cowl_n_perimeters` is a
    count of extruded perimeters: 2 is a configuration and 0 is not a wall at all. A screen that
    generated the low case anyway would spend a build refusing an input nobody would ask for, and
    would report that refusal beside the ones that mean something.
    """

    __slots__ = ('alias', 'delta', 'unit', 'why', 'signs')

    def __init__(self, alias, delta, unit, why, signs=(-1.0, +1.0)):
        self.alias = alias
        self.delta = float(delta)
        self.unit = unit
        self.why = why
        self.signs = tuple(float(s) for s in signs)

    def __repr__(self):
        return '<Excursion %s %+g %s>' % (self.alias, self.delta, self.unit)


class Case(object):
    """One build in the screen: a kind, a `U`, and at most one overridden row."""

    __slots__ = ('kind', 'u', 'name', 'alias', 'delta', 'unit', 'why')

    def __init__(self, kind, u, name, alias=None, delta=0.0, unit='', why=''):
        self.kind = kind
        self.u = float(u)
        self.name = name
        self.alias = alias
        self.delta = float(delta)
        self.unit = unit
        self.why = why

    @property
    def is_baseline(self):
        return self.alias is None

    @property
    def label(self):
        return '%s_U%s_%s' % (self.kind, _u_text(self.u), self.name)

    def __repr__(self):
        return '<Case %s>' % self.label


#: **The screen, by kind.** Magnitudes are roughly a third of the sheet's own value where it is
#: non-zero, and an absolute step where it is zero -- large enough to be a different design rather
#: than a numerical nudge, which is the point here. This is a coverage screen, not a resilience
#: probe: the question is whether a *legitimate* configuration other than the sheet's can sever the
#: ring, so an excursion that is too small to change the design would not answer it. That is the
#: opposite of the 2026-09-30 screen's problem, where the magnitudes were too *large* to compare
#: against the row-nudge probe's 0.01 mm threshold -- a different question, needing the other bound.
EXCURSIONS = {
    'tail_shell': (
        # Every tool at once: how wide it cuts, how far in it sits, how its ramp leans, how thick
        # a wall it must leave. The crowding axis, and the reason there is no case per placement.
        #
        # **`buttress_cut_thickness` is absolute millimetres, not a fraction**, and it is the one
        # row on these sheets that looks like a fraction and is not: `cowl.py`'s own note says it
        # "is the *cut*, and it is deliberately 0.1 mm", and `cowl.py`'s absolute sheet carries the
        # same 0.1 where `cut_len` goes 0.06 -> 6.0 and `buttress_r_inset` 0.03 -> 3.0. So +-0.03
        # here is +-30 % of a 0.1 mm slot and not 3 mm of anything. Labeled wrongly in this
        # module's first draft and corrected by the screen's own first case.
        Excursion('buttress_cut_thickness', 0.03, 'mm',
                  'how wide every rib tool cuts, so how much neighbours overlap'),
        Excursion('buttress_r_inset', 0.02, 'fraction of unit_width',
                  'how far every tool is set in from the OML'),
        Excursion('overhang_angle_from_bed', 5.0, 'degrees',
                  "the dilation ramp's lean, which sets how far each comb reaches"),
        Excursion('extrusion_width', 0.2, 'mm',
                  'the wall thickness itself; absolute, because a nozzle does not scale'),
        # **One-sided, and a prediction rather than an exploration.** See the nose list.
        Excursion('cowl_n_perimeters', 1.0, 'perimeters',
                  'the other half of the wall thickness', signs=(+1.0,)),
        # The diagonal, which the 2026-09-30 screen found moved the worst station.
        Excursion('top_diag_angle', 5.0, 'degrees',
                  'the diagonal buttresses, the pair the tail has and the nose does not'),
        Excursion('top_diag_depth', 0.01, 'fraction of unit_width',
                  'how far the diagonal reaches in'),
        Excursion('top_diag_z_start', 0.05, 'fraction of unit_width',
                  'where the diagonal starts, so which stations it is near'),
        # The two top placements, both tested in 2026-09-30 and kept for continuity with it.
        Excursion('top1_angle', 5.0, 'degrees', 'where Top1Safe sits around the section'),
        Excursion('top1_y', 0.02, 'fraction of unit_width', 'how far out Top1Safe sits'),
        Excursion('top2_angle', 5.0, 'degrees', 'where Top2Safe sits around the section'),
        Excursion('top2_y', 2.0, 'mm',
                  'how far out Top2Safe sits; a literal 0.0 on the sheet, so the step is absolute'),
    ),
    'nose_cowl_shell': (
        # Absolute millimetres: see the note on the tail's row of the same name.
        Excursion('buttress_cut_thickness', 0.03, 'mm',
                  'how wide every rib tool cuts, so how much neighbours overlap'),
        Excursion('buttress_r_inset', 0.01, 'fraction of unit_width',
                  'how far every tool is set in from the OML'),
        Excursion('overhang_angle_from_bed', 5.0, 'degrees',
                  "the dilation ramp's lean, which sets how far each comb reaches"),
        Excursion('extrusion_width', 0.2, 'mm',
                  'the wall thickness itself; absolute, because a nozzle does not scale'),
        # **One-sided, and added to test a prediction rather than to explore.** The screen's first
        # two refusals -- `buttress_cut_thickness` down to 0.07 mm and `extrusion_width` up to
        # 0.8 mm -- are both `dilated_notches`' facet precondition, which builds only while
        # `in_plane > 2 t sin(pi / RIB_FACETS)`, i.e. `in_plane / t > 0.130806` at `RIB_FACETS` =
        # 48. `Inset` is `cowl_n_perimeters * extrusion_width`, so 2 perimeters puts `t` at
        # 1.2 mm and the ratio at 0.0833, which that inequality says must be refused. A second
        # perimeter is a 2x step on the same axis `extrusion_width` moves by 1.33x, so this case
        # checks the closed form where it is not merely interpolating between two failures.
        # `cowl_n_perimeters` = 0 is not a wall, hence one sign.
        Excursion('cowl_n_perimeters', 1.0, 'perimeters',
                  'the other half of the wall thickness', signs=(+1.0,)),
        Excursion('buttress_r_end', 0.02, 'fraction of unit_width',
                  'how far around the section each tool runs'),
        Excursion('buttress_z_offset', 0.01, 'fraction of unit_width',
                  'where the tools start in z, and so buttress_z_end with them'),
        Excursion('cut_len', 0.02, 'fraction of unit_width',
                  "the cell cut's length, which also moves buttress_z_end"),
        Excursion('butt_angle', 5.0, 'degrees', "the buttress ring's own rotation"),
    ),
}


def _u_text(u):
    """`U` in a filename the way the soak writes it: `0.5`, `1.0`, `4.0`."""
    return ('%g' % float(u)) if float(u) != int(float(u)) else '%.1f' % float(u)


def bump(value_text, delta):
    """A sheet cell moved by `delta` in its own units, keeping literal or expression form.

    A literal becomes a literal; `=unit_width * c` becomes `=unit_width * (c + delta)` with the
    sign kept where it was. Any other expression raises: see `_COEFFICIENT`.
    """
    text = value_text.strip()
    if text.startswith('='):
        m = _COEFFICIENT.match(text)
        if m is None:
            raise ValueError('%r is a relationship, not a value a case may bump' % value_text)
        sign, coeff = m.group(1), float(m.group(2))
        return '=%sunit_width * %s' % (sign, repr(coeff + delta))
    return repr(float(text) + delta)


def override(rows, alias, value_text):
    """A copy of `rows` with one alias's cell replaced. Raises if the sheet has no such row.

    Generalizes `soak_cowl_shell.with_u`, and raises for the same reason that function does: a
    silently-ignored override would run the baseline under a case's name and report it as coverage
    of an input the build never saw.
    """
    out, found = [], False
    for row_alias, value in rows:
        if row_alias == alias:
            out.append((row_alias, value_text))
            found = True
        else:
            out.append((row_alias, value))
    if not found:
        raise ValueError('no %r row on this sheet' % alias)
    return out


def value_of(rows, alias):
    """One alias's cell text. Raises if absent, for the same reason `override` does."""
    for row_alias, value in rows:
        if row_alias == alias:
            return value
    raise ValueError('no %r row on this sheet' % alias)


def apply_case(rows, case):
    """`rows` with `case`'s `U` set and its one excursion applied. The baseline sets `U` only."""
    out = override(rows, 'U', repr(float(case.u)))
    if case.is_baseline:
        return out
    return override(out, case.alias, bump(value_of(out, case.alias), case.delta))


def cases(kind, u, excursions=None):
    """The screen for one kind at one `U`, baseline first then each excursion low and high.

    **Ordered by what the mechanism implicates, not alphabetically**, because a tail case is about
    1 000 s and a run may be interrupted: `EXCURSIONS` lists the four that move every tool first,
    then the diagonal, then the individual placements, and this preserves that order. An
    interrupted screen therefore leaves the crowding axis covered.
    """
    exc = EXCURSIONS[kind] if excursions is None else excursions
    out = [Case(kind, u, BASELINE, why='the sheet as it stands; the control on the harness')]
    for e in exc:
        for sign in e.signs:
            suffix = 'lo' if sign < 0 else 'hi'
            out.append(Case(kind, u, '%s_%s' % (e.alias, suffix), e.alias, sign * e.delta,
                            e.unit, e.why))
    return out


def find(kind, u, name, excursions=None):
    """One case by name, or `None`."""
    for case in cases(kind, u, excursions):
        if case.name == name:
            return case
    return None


def fingerprint(record):
    """A cheap identity for a built wall, or `None` when the record cannot support one.

    Solids, faces, edges, the bounding box to 1e-6 mm, **and the raw `Shape.Volume`**. `None` when
    `volume_raw` is absent, so that an old record is reported as uncomparable rather than compared
    on the weaker four.

    **The first four alone were tried and are not enough -- measured, 2026-10-14.** The nose
    screen's first report named seven of fifteen cases `unmoved`, including `extrusion_width_lo`,
    which takes the wall from 0.6 mm to 0.4 mm. A thinner wall keeps the same outer surface, the
    same face and edge counts and the same bounding box: only the interior moves, and none of those
    four can see it. The guard was wrong, not the construction.

    **`Shape.Volume` is used here as a difference detector and never as a measure.** IP-FC-119
    measured it wrong by 0.16-0.24 % on this project's B-spline solids, which is why every
    *quantity* in this subsystem comes from a refined tessellation instead. That defect is a bias,
    and it is deterministic: the same shape returns the same wrong number, and two shapes that
    differ return different ones. Asking it whether two walls are the same shape is sound; asking it
    how big either one is would not be. The alternative, `mesh_stats.canonical_hash`, needs a
    tessellation at about 100 s a tail wall and would add most of an hour to this screen to answer
    a question `Shape.Volume` answers for nothing.
    """
    if record.get('volume_raw') is None:
        return None
    bb = record.get('wall_bbox') or []
    return (int(record.get('solids') or 0), int(record.get('faces') or 0),
            int(record.get('edges') or 0), tuple(round(float(v), 6) for v in bb),
            round(float(record['volume_raw']), 6))


def uncomparable(records):
    """The built cases whose record has no `volume_raw`, so `unmoved` cannot judge them.

    **Reported rather than quietly compared on what is there.** A record written before this field
    existed can still be fingerprinted on solids, faces, edges and the box -- and that combination
    is exactly the one measured above to miss a 0.2 mm change in wall thickness. Falling back to it
    would make the vacuity guard weaker without saying so, which is the failure the guard exists to
    prevent. `input_screen.py --refingerprint` fills the field in from the saved wall for the cost
    of a file read.
    """
    return sorted(r.get('case') for r in records
                  if not r.get('error') and r.get('volume_raw') is None)


def unmoved(records):
    """The cases whose wall is indistinguishable from the baseline's. **A vacuity guard.**

    A screen reports coverage of an input axis. If an override does not change the built wall, the
    case covered nothing -- it scanned the baseline a second time under another name -- and a
    verdict that counted it would overstate what was tested. This is the seventh place in this
    subsystem where a check had to be stopped from reporting a pass from having measured nothing,
    and the first where the empty input is a *parameter* rather than a sample set.

    It is not automatically a defect. `top2_y`'s null result was measured directly in 2026-09-30 --
    `Top2Safe` moves exactly as instructed but is never the locally closest tool -- so a row the
    finished wall is genuinely blind to is a fact about the construction worth naming. The guard
    names them; it does not decide which kind each is.
    """
    base = None
    for r in records:
        if r.get('case') == BASELINE:
            base = fingerprint(r)
            break
    if base is None:
        return []
    return sorted(r.get('case') for r in records
                  if r.get('case') != BASELINE and fingerprint(r) == base)


def population(record):
    """The `(kind, u)` a record belongs to. One population has one baseline."""
    return (record.get('kind'), float(record.get('u') or 0.0))


def populations(records):
    """`records` split by `(kind, u)`, in a stable order. One screen run is one population.

    **The two kinds must not be folded together, and folding them was caught doing damage.** A
    verdict over both at once has two records named `base`, so `unmoved` picks whichever came first
    off disk and compares the *other* kind's cases against it, and the refusal list prints every
    shared case name twice. That is the same population confusion `corpus.screen` and
    `corpus.available` are kept apart to prevent, reintroduced one layer up; it happened to give
    the right answer on the 2026-10-14 run only because a nose wall and a tail wall never
    fingerprint alike.
    """
    out, order = {}, []
    for r in records:
        key = population(r)
        if key not in out:
            out[key] = []
            order.append(key)
        out[key].append(r)
    return [(key, out[key]) for key in order]


def screen_verdict(records, scans=None):
    """Did the screen cover an input axis, and did any case sever the ring? **One population.**

    `records` are `input_screen.py`'s per-case build records for one kind at one `U`; `scans` are
    `ring_scan.py`'s per-wall results for the same labels. The two halves are separate runs and
    either can be absent.

    Raises on records spanning more than one `(kind, u)`: a verdict needs one baseline to compare
    against, and `populations` is how a caller splits them. `screen_report` does that.

    `clean` is `True` only when every case that was scanned came back a healthy annulus throughout
    **and** at least one case moved the geometry. The second half is the point of `unmoved`: a
    screen in which no override reached the wall is not a clean screen, it is an untested one.
    """
    records = list(records or ())
    # A record with no `kind` cannot be placed in a population, so it does not contribute to the
    # span: both of `input_screen.py`'s own paths write one, but a hand-made or truncated record
    # must not turn this guard into a crash in the reporting layer.
    spans = {population(r) for r in records if r.get('kind') is not None}
    if len(spans) > 1:
        raise ValueError('records span %d populations (%s); split them with populations() -- a '
                         'verdict needs one baseline'
                         % (len(spans), ', '.join(sorted('%s U%s' % k for k in spans))))
    scans = list(scans or ())
    built = [r for r in records if not r.get('error')]
    failed = sorted(r.get('case') for r in records if r.get('error'))
    unjudged = uncomparable(built)
    still = unmoved(built)
    moved = [r.get('case') for r in built
             if r.get('case') != BASELINE and r.get('case') not in still
             and r.get('case') not in unjudged]
    severed, gaps, disagree, stations = [], [], [], 0
    for s in scans:
        label = s.get('label', '?')
        stations += int(s.get('stations') or 0)
        severed += [(label, float(z)) for z in (s.get('severed') or [])]
        gaps += [(label, float(z)) for z in (s.get('real_gaps') or [])]
        disagree += [(label, d) for d in (s.get('kernel_disagreements') or [])]
    reasons = []
    if not built:
        reasons.append('no case built')
    if not moved:
        reasons.append('no override changed the wall, so no input was covered')
    if not scans:
        reasons.append('no wall was scanned')
    if unjudged:
        reasons.append('%d built case(s) have no volume_raw, so whether their override reached '
                       'the wall is unknown; run input_screen.py --refingerprint' % len(unjudged))
    return {'cases': len(records), 'built': len(built), 'scanned': len(scans),
            'stations': stations, 'build_failures': failed, 'unmoved': still,
            'uncomparable': unjudged, 'moved': sorted(moved), 'severed': severed,
            'real_gaps': gaps, 'kernel_disagreements': disagree, 'vacuous_because': reasons,
            'clean': not (severed or gaps or disagree or reasons)}


def screen_table(records, scans=None):
    """The screen as text, one row a case: what was overridden, what it cost, what the scan said."""
    by_label = {s.get('label'): s for s in (scans or ())}
    head = '%-34s %-24s %9s %7s %7s %14s %8s %8s %8s' % (
        'case', 'row', 'delta', 'solids', 'faces', 'volume', 'build s', 'stations', 'severed')
    out = [head, '-' * len(head)]
    base = None
    for r in records:
        if r.get('case') == BASELINE:
            base = fingerprint(r)
    for r in records:
        label = r.get('label', '?')
        scan = by_label.get(label) or {}
        if r.get('error'):
            out.append('%-34s %-24s %9s %7s %7s %14s %8s %8s %8s'
                       % (r.get('case', '?'), r.get('alias') or '-', '', 'REFUSED', '', '', '',
                          '', ''))
            continue
        vol = r.get('volume_raw')
        mark = ''
        if vol is None:
            mark = '  (no volume_raw -- uncomparable)'
        elif base is not None and r.get('case') != BASELINE and fingerprint(r) == base:
            mark = '  (unmoved)'
        out.append('%-34s %-24s %9s %7d %7d %14s %8.0f %8s %8s%s'
                   % (r.get('case', '?'), r.get('alias') or '-',
                      '' if r.get('alias') is None else '%+g' % float(r.get('delta') or 0.0),
                      int(r.get('solids') or 0), int(r.get('faces') or 0),
                      '-' if vol is None else '%.4f' % float(vol),
                      float(r.get('build_s') or 0.0),
                      scan.get('stations', '-'),
                      len(scan.get('severed') or []) if scan else '-',
                      mark))
    return '\n'.join(out)


def _load_dir(where, key=None):
    """Every JSON file under `where`, as a list. Empty when the directory is absent."""
    if not where or not os.path.isdir(where):
        return []
    out = []
    for name in sorted(os.listdir(where)):
        if not name.endswith('.json'):
            continue
        with open(os.path.join(where, name), encoding='utf-8') as fh:
            payload = json.load(fh)
        # `ring_scan` writes `{'walls': [...]}`; `input_screen` writes one record.
        out += payload.get(key, []) if (key and isinstance(payload, dict)) else [payload]
    return out


def screen_report(records_dir=None, scan_dir=None, out=None):
    """The screen's table and verdict, from the two directories of JSON. **No geometry.**

    The builds and the scans are separate runs of separate scripts -- a process a case and a
    process a wall, for `ring_scan`'s reason: `freecadcmd` exits 0 on an uncaught exception, so the
    artifact on disk is the only honest record of how far a run got. This is the step that puts
    them back together, and it needs neither FreeCAD nor the walls::

        python -m wall_measure.inputs
        python -m wall_measure.inputs --records=DIR --scan=DIR
    """
    out = out if out is not None else sys.stdout
    records = _load_dir(records_dir or SCREEN_RECORDS)
    all_scans = _load_dir(scan_dir or os.path.join(SCREEN_DIR, 'scan'), key='walls')
    verdicts, clean = {}, True
    for (kind, u), rows in populations(records):
        labels = {r.get('label') for r in rows}
        scans = [s for s in all_scans if s.get('label') in labels]
        out.write('\n%s at U = %g -- %d case(s)\n' % (kind, u, len(rows)))
        out.write(screen_table(rows, scans) + '\n')
        verdict = screen_verdict(rows, scans)
        for case in verdict['build_failures']:
            out.write('  REFUSED  %s\n' % case)
        for case in verdict['unmoved']:
            out.write('  UNMOVED  %s -- the override did not change the wall\n' % case)
        for case in verdict.get('uncomparable') or []:
            out.write('  UNJUDGED %s -- no volume_raw; run input_screen.py '
                      '--refingerprint\n' % case)
        for label, z in verdict['severed']:
            out.write('  SEVERED  %-46s z %.4f\n' % (label, z))
        for label, z in verdict['real_gaps']:
            out.write('  GAP      %-46s z %.4f\n' % (label, z))
        for label, d in verdict['kernel_disagreements']:
            out.write('  DISAGREE %-46s %s\n' % (label, d))
        for reason in verdict['vacuous_because']:
            out.write('  VACUOUS  %s\n' % reason)
        out.write('VERDICT %s U%g: %s -- %d case(s), %d built, %d refused, %d scanned, '
                  '%d station(s), %d severed, %d confirmed gap(s)\n'
                  % (kind, u, 'CLEAN' if verdict['clean'] else 'FINDINGS', verdict['cases'],
                     verdict['built'], len(verdict['build_failures']), verdict['scanned'],
                     verdict['stations'], len(verdict['severed']), len(verdict['real_gaps'])))
        verdicts['%s_U%g' % (kind, u)] = verdict
        clean = clean and verdict['clean']
    # **The roll-up is a conjunction, never a re-computation over the merged records.** Merging
    # them would give two baselines and one `unmoved` comparison across kinds; see `populations`.
    out.write('\nSCREEN %s -- %d population(s), %d station(s) over %d scanned wall(s)\n'
              % ('CLEAN' if (clean and verdicts) else 'FINDINGS', len(verdicts),
                 sum(v['stations'] for v in verdicts.values()),
                 sum(v['scanned'] for v in verdicts.values())))
    out.write('SCREEN_SUMMARY ' + json.dumps({'clean': bool(clean and verdicts),
                                              'populations': verdicts}, default=str) + '\n')
    out.flush()
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    def opt(name, default=None):
        for arg in argv:
            if arg.startswith('--%s=' % name):
                return arg.split('=', 1)[1]
        return default

    if opt('cases'):
        for case in cases(opt('cases'), float(opt('u', '0.5'))):
            sys.stdout.write('%-34s %-24s %-9s %s\n'
                             % (case.name, case.alias or '-',
                                '' if case.is_baseline else '%+g' % case.delta, case.why))
        return 0
    return screen_report(opt('records'), opt('scan'))


if __name__ == '__main__':                                                  # pragma: no cover
    sys.exit(main())
