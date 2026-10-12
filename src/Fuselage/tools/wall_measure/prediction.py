"""Pass 2's own prediction, read back out of a build log and set against the real wall.

`cowl_interior.cavity` converges a *prediction* of the finished wall's thinness: after the rib cut
it slices the cut cavity and the finished exterior at each scanned station and measures the distance
between the two contours, never performing `shell_solid`'s real `notched.cut(inside)` boolean. Where
a point reads more than `TAU` = 0.05 mm thinner than nominal it inserts a station and re-cuts,
bounded by `POST_CUT_ROUNDS` = 6, after which it raises `Unconverged` rather than shipping. A build
that returns a solid therefore carries a guarantee from pass 2: **its predicted thinness is at most
`TAU` everywhere pass 2 scanned.**

OQ-DES-CW23 asked what to do about "the resulting small residual gap" between that prediction and
the real cut. The figures it was argued on came from one build's 12 stations, with the real side read
by the nearest-point minimum — the measure since shown not to converge
(doc/implementation/wall_thickness_measure.md, gate G2). **What this module measures is what withdrew
that item:** there is no small residual gap. It is zero below `U` = 3, where the prediction is
conservative, and 0.1084 to 0.1743 mm at `U` = 3 and 4 — eleven to seventeen times `WALL_TOL`. The
question was never a design choice; it was missing information, and this is the information. The
answer costs no build, because both sides are already on disk:

- the **prediction** is in the soak's own log, one `cavity closed: ... worst finished wall error`
  line per build, which is `cavity`'s `worst_finished` from the last, passing round;
- the **real** reading is `sweep.write_jsonl`'s output for the same 28 walls, under any measure.

**The two sides are maxima over different grids, and the comparison is built as a one-sided
inequality because of it.** Pass 2 scans a near-complete grid — a uniform pass over every patch plus
extra density around each notch edge, 57 to several hundred points — so its maximum is close to the
whole wall's true worst. A sweep reads 12 stations, so its maximum is a *lower bound* on the real
wall's true worst. That asymmetry only ever hides real thinness; it can never invent it. So
`real_worst > predicted_worst` is sound as stated — the real wall is thinner somewhere than pass 2's
whole-wall scan predicted anywhere — while the reverse comparison is not, and `shortfall` below is
deliberately clamped at zero rather than reported signed. Do not read these as per-station gaps.
"""
import json
import os
import re

from . import corpus

#: `=== nose_cowl_shell U=0.5 repeat=0 ===`
_HEADER = re.compile(r'^===\s*(?P<kind>\S+)\s+U=(?P<u>[0-9.]+)\s+repeat=(?P<repeat>\d+)\s*===')

#: `cavity closed: 1 solids, valid=True, 5980.6207 mm3, worst finished wall error 0.0019 mm, 29 s`
_CLOSED = re.compile(r'cavity closed:.*?worst finished wall error\s+(?P<gap>[0-9.]+)\s*mm')

#: `patch 1/1  z ... 10 seeded -> 10 stations  worst wall 0.0064   11.9 s`
_PATCH = re.compile(r'patch\s+\d+/\d+\s+z\s.*?worst wall\s+(?P<gap>[0-9.]+)')

#: `patch 1/1 scan: 40 uniform + 18 edge-focused (4 notch edge(s)) -> 57 points`
_SCAN = re.compile(r'patch\s+\d+/\d+\s+scan:.*?->\s*(?P<points>\d+)\s*points')

#: `post-cut refine: round 1, worst finished-wall gap 0.0601 mm over 0.050, inserting 2 station(s)`
_ROUND = re.compile(r'post-cut refine:\s*round\s+(?P<round>\d+),\s*worst finished-wall gap\s+'
                    r'(?P<gap>[0-9.]+)\s*mm')

#: `cowl_interior.TAU`, pass 2's own stopping criterion. Carried here so a reader of this module's
#: output does not have to go and find it, and asserted against the log's own printed figure.
TAU = 0.05

#: `cowl_interior.WALL_TOL`, what the finished part is held to. Five times tighter than `TAU`.
WALL_TOL = 0.01

DEFAULT_LOG = os.path.join(corpus.SOAK_DIR, 'soak_log.txt')

#: **The spacing-based sweep, not the first one.** `sweep_selected.jsonl` fixed the sample count at
#: 1 440 a loop, which on a part whose perimeter scales with `U` is 0.30 mm of circumferential
#: spacing at `U` = 1 and 1.45 mm at `U` = 4; its large-`U` rows are wrong by up to a factor of six
#: and the "regime change" this module once reported came from them. It is kept as
#: `sweep_selected.superseded-2026-10-10.jsonl`.
DEFAULT_SWEEP = os.path.join(corpus.SOAK_DIR, 'sweep_spacing.jsonl')


class BuildPrediction(object):
    """What pass 2 predicted for one build, and how hard it had to work to get there.

    `predicted` is the number that gated the build: pass 2's worst finished-wall thinness on its own
    scan grid, from the last round that wanted no further insertion. `converged` is whether the
    build returned a solid at all — a `False` here means the log recorded rounds but never a
    `cavity closed`, which is `Unconverged` and a build that shipped nothing.
    """

    __slots__ = ('kind', 'u', 'repeat', 'predicted', 'pass1_worst', 'scan_points', 'rounds',
                 'round_gaps')

    def __init__(self, kind, u, repeat, predicted=None, pass1_worst=None, scan_points=0,
                 rounds=0, round_gaps=None):
        self.kind = kind
        self.u = u
        self.repeat = repeat
        #: Pass 2's final worst predicted thinness, mm, or `None` if the build never closed.
        self.predicted = predicted
        #: Pass 1's worst smooth-surface deviation, mm — the largest over the build's patches.
        self.pass1_worst = pass1_worst
        #: How many points pass 2's round-0 scan covered, summed over patches. This is what makes
        #: the prediction a near-complete scan rather than a sample, and so what makes the
        #: one-sided inequality in this module's docstring sound.
        self.scan_points = scan_points
        #: How many insertion rounds pass 2 needed. 0 means round 0 passed outright.
        self.rounds = rounds
        #: The worst gap pass 2 saw at each round that inserted, in order.
        self.round_gaps = list(round_gaps or ())

    @property
    def label(self):
        return '%s_U%s_r%d' % (self.kind, self.u, self.repeat)

    @property
    def converged(self):
        return self.predicted is not None

    @property
    def key(self):
        return (self.kind, float(self.u), int(self.repeat))

    def __repr__(self):
        return '<BuildPrediction %s predicted=%s>' % (self.label, self.predicted)


def parse_build_log(path=None):
    """Every build in a soak log, as `BuildPrediction`s in log order.

    Returns an empty list when the log is absent rather than raising, for the same reason
    `corpus.available` does: the log is build output and is not in version control.
    """
    path = path or DEFAULT_LOG
    if not os.path.isfile(path):
        return []
    out = []
    cur = None
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            head = _HEADER.match(line.strip())
            if head:
                cur = BuildPrediction(head.group('kind'), head.group('u'),
                                      int(head.group('repeat')))
                out.append(cur)
                continue
            if cur is None:
                continue
            m = _CLOSED.search(line)
            if m:
                cur.predicted = float(m.group('gap'))
                continue
            m = _PATCH.search(line)
            if m:
                gap = float(m.group('gap'))
                cur.pass1_worst = gap if cur.pass1_worst is None else max(cur.pass1_worst, gap)
                continue
            m = _SCAN.search(line)
            if m:
                cur.scan_points += int(m.group('points'))
                continue
            m = _ROUND.search(line)
            if m:
                cur.rounds = max(cur.rounds, int(m.group('round')))
                cur.round_gaps.append(float(m.group('gap')))
    return out


def predictions(path=None):
    """`parse_build_log` keyed `(kind, u, repeat)`, to join against the corpus and a sweep."""
    return dict((b.key, b) for b in parse_build_log(path))


def read_sweep(path=None):
    """A `sweep.write_jsonl` file as rows keyed `(kind, u, repeat)`. Empty if absent."""
    path = path or DEFAULT_SWEEP
    if not os.path.isfile(path):
        return {}
    out = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out[(row['kind'], float(row['u']), int(row['repeat']))] = row
    return out


def pair(name, log=None, sweep_path=None, stations=corpus.STATIONS, full_coverage_only=True):
    """Pass 2's prediction beside the real wall under measure `name`, one row per build.

    `full_coverage_only` drops a wall the sweep could not section at every station, for the reason
    IP-WTM-19 settles: an unmeasured station is not a passing one, and the acceptance check counts it
    a failure. A row's `coverage` and `stations` are carried either way so a caller can see what was
    dropped.

    Each row carries `predicted`, `real`, and `shortfall` = `max(0, real - predicted)`. `shortfall`
    is the only direction this pairing supports: see the module docstring.
    """
    preds = predictions(log)
    rows = read_sweep(sweep_path)
    out = []
    for key in sorted(set(preds) & set(rows)):
        p, row = preds[key], rows[key]
        if not p.converged:
            continue
        worst = row.get('worst_thin', {})
        if name not in worst:
            continue
        coverage = int(row.get('stations_measured', {}).get(name, 0))
        total = int(row.get('stations', stations))
        if full_coverage_only and coverage < total:
            continue
        real = float(worst[name])
        out.append({'label': p.label, 'kind': p.kind, 'u': float(p.u), 'repeat': p.repeat,
                    'predicted': p.predicted, 'real': real,
                    'shortfall': max(0.0, real - p.predicted),
                    'pass1_worst': p.pass1_worst, 'scan_points': p.scan_points,
                    'rounds': p.rounds, 'coverage': coverage, 'stations': total})
    return out


def verdict(name, log=None, sweep_path=None, tau=TAU, tolerance=WALL_TOL, **kw):
    """Can pass 2's prediction certify the part at `tolerance`? Returns the evidence, not an opinion.

    The question is answered by two facts the pairing settles, neither of which needs a station-level
    correspondence:

    - every paired build **converged by pass 2**, so its predicted thinness is at most `tau`;
    - the real wall under `name` reads thinner than that at `builds_real_worse_than_tau` of them.

    Where the second count is non-zero, no tightening of pass 2's criterion can certify the part:
    pass 2 is already inside `tau` by its own near-complete scan while the real wall, measured by a
    converging instrument at a strict subset of places, is thinner than `tau` anyway. `worst_shortfall`
    is how much thinner, at the worst build.
    """
    rows = pair(name, log, sweep_path, **kw)
    worse_tau = [r for r in rows if r['real'] > tau]
    worse_tol = [r for r in rows if r['real'] > tolerance]
    shortfalls = [r['shortfall'] for r in rows]
    worst = max(rows, key=lambda r: r['shortfall']) if rows else None
    return {
        'measure': name,
        'tau': tau,
        'tolerance': tolerance,
        'builds_paired': len(rows),
        'max_predicted': max([r['predicted'] for r in rows]) if rows else None,
        'predictions_within_tau': all(r['predicted'] <= tau for r in rows),
        'builds_real_worse_than_tau': len(worse_tau),
        'builds_real_worse_than_tolerance': len(worse_tol),
        'builds_meeting_tolerance': len(rows) - len(worse_tol),
        'mean_shortfall': (sum(shortfalls) / len(shortfalls)) if shortfalls else None,
        'worst_shortfall': worst['shortfall'] if worst else None,
        'worst_label': worst['label'] if worst else None,
        'worst_predicted': worst['predicted'] if worst else None,
        'worst_real': worst['real'] if worst else None,
    }


def table(name, log=None, sweep_path=None, **kw):
    """The pairing as a fixed-width table, for a design document or a console."""
    rows = pair(name, log, sweep_path, **kw)
    head = ('%-26s %10s %10s %10s %7s %7s'
            % ('build', 'pass2 pred', 'real', 'shortfall', 'rounds', 'scan'))
    lines = [head, '-' * len(head)]
    for r in rows:
        lines.append('%-26s %10.4f %10.4f %10.4f %7d %7d'
                     % (r['label'], r['predicted'], r['real'], r['shortfall'],
                        r['rounds'], r['scan_points']))
    if not rows:
        lines.append('(no build has both a pass 2 prediction and a full-coverage real reading)')
    return '\n'.join(lines)
