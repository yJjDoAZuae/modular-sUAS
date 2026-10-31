"""The seeded station sets a screen leaves behind, as a population a question can be asked of.

`src/Fuselage/freecad/station_gaps.py` writes one JSON a configuration: the uniform seed, the notch
edges, their union, the tightest gaps in it, and what `_thin_stations(zs, station_floor(t))` keeps.
That script prints a table a person reads. This module is what *code* reads, and it exists because
the question the screen was run to answer is about the population and not about any one case.

**The question.** `cowl_interior_surface.md` section 4.4 measures that the interior fit amplifies a
one-row displacement by 1 / the gap when a near-duplicate station pair sits beside the displaced
row. `cowl.md` OQ-DES-CW26 alternative 1 then asks whether a real build's station set ever contains
such a pair, and names the two-input axis -- two design rows moved together -- as the part a
one-row screen cannot reach. A pair screen answers it only if someone can say, across 242 cases,
which cases seeded a gap tighter than the baseline's and which of those the floor did not remove.

**Three traps this module exists to not fall into.**

*The floor is not a constant.* `t` is `cowl_n_perimeters` times `extrusion_width`, and both are rows
the screen moves, so a case that moves either one is measured against a *different* floor than the
baseline. Comparing every case's gap to the baseline's floor would report breaches that are not
there and miss ones that are, so `breaches_floor` always uses the record's own `station_floor_mm`.

*A patch is not the part.* `cavity` splits the body at its creases and seeds each patch
independently, so a record holds several patches and the tightest gap in the configuration is the
minimum over them. Reading the first patch would silently report the nose of the part.

*A tight gap in a pair case is not an interaction.* If one of the pair's two rows seeds that same
gap on its own, the pair inherited it. `interactions` therefore refuses to return a verdict for a
pair whose single-row members are not both present, rather than treating an absent member as clean
-- the distinction between "neither member does this alone" and "nobody looked" is the whole point.

Pure stdlib, like everything else here: the records are JSON on disk and no vendor module is needed
to read them.
"""
import json
import os
import sys

#: Where `station_gaps.py` writes, relative to this file.
_HERE = os.path.dirname(os.path.abspath(__file__))
RECORDS = os.path.normpath(os.path.join(_HERE, '..', '..', 'freecad', 'out', 'station_gaps'))

#: What `pair_cases` joins a pair's two member names with.
PAIR_JOIN = '__'

#: Float slack when comparing a gap against the floor. The gaps are millimeters near 1e-4 and the
#: floor is 0.6, so this only absorbs the last bit of a round trip through JSON.
FLOOR_TOL = 1.0e-12


class StationSet(object):
    """One configuration's seeded station set, as `station_gaps.run` recorded it."""

    __slots__ = ('path', 'row')

    def __init__(self, path, row):
        self.path = path
        #: The record as written: `kind`, `u`, `case`, `moves`, `t_mm`, `station_floor_mm`,
        #: `notch_edges`, `body_creases` and a `patches` list.
        self.row = row

    # -- what it was built from ---------------------------------------------------------------

    @property
    def kind(self):
        return self.row['kind']

    @property
    def u(self):
        return float(self.row['u'])

    @property
    def case(self):
        """The case name, or `None` for the baseline, which `station_gaps` records as a bare kind.

        Taken from the record and not from the file name. The two agree, but a name has to be
        parsed and `nose_cowl_shell` contains the same separator a case name does, so parsing it is
        a trap with no upside when the configuration is written into the file.
        """
        return self.row.get('case')

    @property
    def is_baseline(self):
        return self.case is None

    @property
    def moves(self):
        """The row moves this case applied, as `[[alias, delta], ...]`, empty for the baseline."""
        return [list(m) for m in (self.row.get('moves') or [])]

    @property
    def label(self):
        u = self.row['u']
        text = '%g' % float(u)
        return '%s_U%s' % (self.kind, text) if self.is_baseline else \
               '%s_U%s_%s' % (self.kind, text, self.case)

    @property
    def members(self):
        """A pair case's two single-case names, or `None` when this is not a pair case.

        `pair_cases` builds the name as `<row>_<sign>__<row>_<sign>`, and a single-row case name
        never contains the separator, so the split is exact rather than heuristic.
        """
        if self.is_baseline or PAIR_JOIN not in self.case:
            return None
        first, second = self.case.split(PAIR_JOIN, 1)
        return (first, second)

    # -- what it measured ---------------------------------------------------------------------

    @property
    def floor_mm(self):
        """This configuration's own station floor. **Not the baseline's** -- see the module note."""
        return float(self.row['station_floor_mm'])

    @property
    def t_mm(self):
        return float(self.row['t_mm'])

    @property
    def patches(self):
        return list(self.row.get('patches') or [])

    @property
    def tightest_union_mm(self):
        """The tightest gap anywhere in the seeded union, over every patch. `None` if unmeasured."""
        return _min_over(self.patches, 'tightest_union_mm')

    @property
    def tightest_kept_mm(self):
        """The tightest gap that survived the floor, over every patch.

        `None` when no patch reported one, which happens when a patch keeps a single station and so
        has no gap at all. That is not the same as zero and must not be compared against the floor.
        """
        return _min_over(self.patches, 'tightest_kept_mm')

    @property
    def under_floor(self):
        """How many seeded gaps were under the floor, over every patch. The floor's own workload."""
        return sum(int(p.get('under_floor') or 0) for p in self.patches)

    @property
    def stations_kept(self):
        return sum(int(p.get('kept') or 0) for p in self.patches)

    @property
    def stations_union(self):
        return sum(int(p.get('union') or 0) for p in self.patches)

    @property
    def breaches_floor(self):
        """Did a gap tighter than this configuration's own floor survive thinning?

        This is IP-FC-144's regression over the whole population: the floor exists to leave no gap
        under it, so a `True` here is a defect in the fix and not a property of the configuration.
        """
        kept = self.tightest_kept_mm
        return kept is not None and kept < self.floor_mm - FLOOR_TOL

    def __repr__(self):
        return '<StationSet %s>' % self.label


def _min_over(patches, key):
    """The minimum of one key over the patches, ignoring the ones that did not report it."""
    seen = [float(p[key]) for p in patches if p.get(key) is not None]
    return min(seen) if seen else None


def available(records_dir=None, kind=None, u=None):
    """Every station-set record, baseline first and then by case name.

    Returns an empty list when the directory is absent rather than raising, for the reason
    `corpus.available` does: these are build output and are not in version control, so a test that
    needs them should skip and not fail.

    Filtered on the record's own `kind` and `u` when either is given. `u` is compared as a float, so
    `3` finds a record written as `3.0`.
    """
    records_dir = records_dir or RECORDS
    if not os.path.isdir(records_dir):
        return []
    out = []
    for name in sorted(os.listdir(records_dir)):
        if not name.endswith('.json'):
            continue
        path = os.path.join(records_dir, name)
        # Plain `open`, not `io.open`: this package is held to an import allowlist so it stays
        # loadable under the worker interpreter. See `test_wall_measure_sweep`.
        try:
            with open(path, encoding='utf-8') as fh:
                row = json.load(fh)
        except ValueError:
            continue
        # Something else's JSON in the same directory is skipped, not guessed at.
        if not isinstance(row, dict) or 'kind' not in row or 'patches' not in row:
            continue
        rec = StationSet(path, row)
        if kind is not None and rec.kind != kind:
            continue
        if u is not None and abs(rec.u - float(u)) > 1.0e-9:
            continue
        out.append(rec)
    out.sort(key=lambda r: (r.kind, r.u, '' if r.is_baseline else r.case))
    return out


def tightest_pair(rec):
    """Which two stations form the tightest seeded gap: `(gap, z_lower, z_upper)`, or `None`.

    **Recomputed from the record's own `union_stations`, not read off `tightest_union_mm`.** The
    figure alone cannot say *where*, and where is the question: whether the tightest gap across a
    whole screen is always the same two stations is the difference between a fixed property of the
    seeding -- a notch edge landing on a seed station, which every configuration inherits -- and
    something a design row actually moves.
    """
    from .fit_response import gaps
    best = None
    for patch in rec.patches:
        found = gaps(patch.get('union_stations') or [])
        if found and (best is None or found[0][0] < best[0]):
            best = found[0]
    return best


def pair_census(records, places=7):
    """How many configurations share each tightest-gap station pair, most common first.

    A single entry covering the whole population says the tightest gap is structural and no
    screened row moves it. Several entries say the opposite, and name the rows that did.
    """
    counts, order = {}, []
    for rec in records:
        found = tightest_pair(rec)
        if found is None:
            continue
        key = (round(found[1], places), round(found[2], places))
        if key not in counts:
            counts[key] = []
            order.append(key)
        counts[key].append(rec)
    out = [(key, counts[key]) for key in order]
    out.sort(key=lambda item: (-len(item[1]), item[0]))
    return out


def baseline(records):
    """The baseline record in a collection, or `None`. The control every comparison needs."""
    for rec in records:
        if rec.is_baseline:
            return rec
    return None


def by_case(records):
    """The records keyed by case name, with the baseline under `None`."""
    return dict((rec.case, rec) for rec in records)


def tighter_than_baseline(records, factor=1.0):
    """Cases whose seeded union holds a gap tighter than the baseline's, tightest first.

    `factor` scales the baseline's gap before comparing, so `0.5` asks for cases that at least
    halved it. Returns an empty list when there is no baseline to compare against, because a
    "tighter than" list with nothing on the right-hand side would be meaningless rather than empty.
    """
    base = baseline(records)
    if base is None or base.tightest_union_mm is None:
        return []
    limit = base.tightest_union_mm * float(factor)
    out = [r for r in records
           if not r.is_baseline and r.tightest_union_mm is not None
           and r.tightest_union_mm < limit]
    out.sort(key=lambda r: r.tightest_union_mm)
    return out


def floor_breaches(records):
    """Every record where a gap under its own floor survived thinning. Empty is the pass.

    Each is measured against its own floor, so a case that moved `extrusion_width` or
    `cowl_n_perimeters` -- the two rows that change `t` -- is judged by the floor it actually had.
    """
    return [r for r in records if r.breaches_floor]


class Interaction(object):
    """One pair case set against its two single-row members.

    `verdict` is the whole reason this type exists instead of a tuple:

    * `'interaction'` -- the pair seeded a tighter gap than either member did alone. The thing the
      two-input axis was screened for.
    * `'inherited'` -- a member seeds the same gap or tighter on its own, so the pair shows nothing
      the one-row screen did not already have.
    * `'unmeasured'` -- a member's own record is absent, so nothing can be concluded. **Reported
      rather than skipped**, because an absent member and a clean member are not the same finding.
    """

    __slots__ = ('pair', 'first', 'second', 'verdict')

    def __init__(self, pair, first, second, verdict):
        self.pair = pair
        self.first = first
        self.second = second
        self.verdict = verdict

    @property
    def missing(self):
        """Which member names have no record, for the `'unmeasured'` case."""
        names = self.pair.members or ()
        return [n for n, rec in zip(names, (self.first, self.second)) if rec is None]

    @property
    def gaps_mm(self):
        """The pair's tightest seeded gap and each member's, members `None` when absent."""
        return (self.pair.tightest_union_mm,
                None if self.first is None else self.first.tightest_union_mm,
                None if self.second is None else self.second.tightest_union_mm)

    def __repr__(self):
        return '<Interaction %s %s>' % (self.pair.label, self.verdict)


def interactions(records, singles=None):
    """Every pair case judged against its own two single-row members.

    `singles` is where the member records come from, and defaults to `records` itself so one
    directory holding both families works. The single-row family is a separate run
    (`station_gaps.py --family=single`), and when it has not been run every pair comes back
    `'unmeasured'` -- which is the honest answer, not a failure.

    A pair is an interaction only when its tightest seeded gap is *strictly* tighter than both
    members'. Equal is `'inherited'`: two configurations that seed the same gap are the same
    finding, and calling that an interaction would manufacture 242 of them out of the baseline's
    own notch edges, which every case carries.
    """
    pool = by_case(records if singles is None else singles)
    out = []
    for rec in records:
        names = rec.members
        if names is None:
            continue
        first, second = pool.get(names[0]), pool.get(names[1])
        if first is None or second is None:
            out.append(Interaction(rec, first, second, 'unmeasured'))
            continue
        mine = rec.tightest_union_mm
        theirs = [m.tightest_union_mm for m in (first, second)]
        if mine is None or any(t is None for t in theirs):
            out.append(Interaction(rec, first, second, 'unmeasured'))
        elif mine < min(theirs) - FLOOR_TOL:
            out.append(Interaction(rec, first, second, 'interaction'))
        else:
            out.append(Interaction(rec, first, second, 'inherited'))
    return out


def report(records, show=10, singles=None):
    """The population as lines of text, for a check script or a document to quote.

    Every line prints the number it is about, because a report that says "no breaches" without the
    tightest surviving gap cannot be checked by its reader.

    `singles` is handed to `interactions`, so a pair screen can be read against the single-row
    family's own directory. Without it the pair verdicts are all `'unmeasured'`, which the report
    states rather than hides.
    """
    lines = []
    if not records:
        lines.append('no station-set records in %s' % RECORDS)
        return lines
    base = baseline(records)
    lines.append('%d station-set record(s), %d pair case(s), %d single or baseline'
                 % (len(records),
                    len([r for r in records if r.members is not None]),
                    len([r for r in records if r.members is None])))
    if base is not None:
        lines.append('baseline %s: floor %.3f mm, tightest seeded %.7f mm, tightest kept %s, '
                     '%d under the floor'
                     % (base.label, base.floor_mm, base.tightest_union_mm or 0.0,
                        _mm(base.tightest_kept_mm), base.under_floor))
    census = pair_census(records)
    lines.append('tightest-gap station pair(s) across the population: %d' % len(census))
    for (z_lo, z_hi), holders in census[:show]:
        lines.append('  %12.7f mm  between %.7f and %.7f  in %d of %d case(s)'
                     % (z_hi - z_lo, z_lo, z_hi, len(holders), len(records)))
    # **How hard the floor had to work, not just whether it held.** A population where every case
    # hands the floor the same few gaps is a weaker result than one where the workload varies: the
    # second says the floor was exercised across its range and still left nothing under it.
    workload = sorted(records, key=lambda r: r.under_floor)
    if workload:
        lines.append('gaps handed to the floor: %d to %d across the population'
                     % (workload[0].under_floor, workload[-1].under_floor))
        lines.append('  fewest %d: %s (floor %.3f mm)'
                     % (workload[0].under_floor, workload[0].label, workload[0].floor_mm))
        lines.append('  most    %d: %s (floor %.3f mm)'
                     % (workload[-1].under_floor, workload[-1].label, workload[-1].floor_mm))
    breaches = floor_breaches(records)
    lines.append('floor breaches: %d' % len(breaches))
    for rec in breaches[:show]:
        lines.append('  %s kept %.7f mm under its own %.3f mm floor'
                     % (rec.label, rec.tightest_kept_mm, rec.floor_mm))
    tighter = tighter_than_baseline(records)
    lines.append('cases seeding a tighter gap than the baseline: %d' % len(tighter))
    for rec in tighter[:show]:
        lines.append('  %12.7f mm  %2d under the floor  %s'
                     % (rec.tightest_union_mm, rec.under_floor, rec.label))
    found = interactions(records, singles=singles)
    if found:
        counts = {}
        for item in found:
            counts[item.verdict] = counts.get(item.verdict, 0) + 1
        lines.append('pair verdicts: %s'
                     % ', '.join('%s %d' % (k, counts[k]) for k in sorted(counts)))
        for item in found:
            if item.verdict != 'interaction':
                continue
            pair, first, second = item.gaps_mm
            lines.append('  %s seeded %.7f mm against %.7f and %.7f alone'
                         % (item.pair.label, pair, first, second))
    return lines


def _mm(value):
    return 'none' if value is None else '%.7f mm' % value


def main(argv=None):
    """Print the report for one screen. `python -m wall_measure.station_sets [--kind= --u=]`.

    Pure stdlib and no vendor module, so this runs under the project's own interpreter rather than
    `freecadcmd`: reading 243 records is not a geometry operation and should not need the kernel.
    """
    argv = list(sys.argv[1:] if argv is None else argv)

    def opt(name, default=None):
        for arg in argv:
            if arg.startswith('--%s=' % name):
                return arg.split('=', 1)[1]
        return default

    u = opt('u')
    records = available(opt('records'), opt('kind'), None if u is None else float(u))
    singles = available(opt('singles')) if opt('singles') else None
    for line in report(records, int(opt('show', '10')), singles=singles):
        sys.stdout.write(line + '\n')
    return 0


if __name__ == '__main__':                                                  # pragma: no cover
    sys.exit(main())
