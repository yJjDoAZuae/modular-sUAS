"""Reproduce the figures published in cowl_interior_surface.md section 6.4 and 6.5.

**This module exists so that every number in those two sections has a command behind it.** The
standing rule in this project is that a measurement quoted in a design document must be
re-derivable: a figure whose only provenance is a scratch script cannot be checked by anyone else
and cannot be regressed. The corpus sweep that produced section 6.4's table was first run from a
thin scratchpad entry point, which is better than a heredoc and still not durable, so the entry
point moved here.

Two halves, with different costs:

* `prediction_report` needs nothing but the two artifacts on disk -- the soak's log and the sweep's
  JSONL -- and runs from the project's own interpreter in well under a second. This is section 6.5
  in full.
* `sweep_report` re-measures the saved walls and therefore needs `Part` and `App`, so it runs under
  `freecadcmd` or through the geometry bridge. It is the expensive half, roughly 28 x 30 s, and it
  writes its own JSONL so `prediction_report` can be re-run against it afterwards.

Run the cheap half with::

    python -m wall_measure.report

Nothing here imports a vendor module **anywhere**, not even inside a function: `Part` and `App`
arrive as arguments, the same rule the rest of this package holds itself to, and a test in
`tests/test_wall_measure_sweep.py` walks every module's AST to enforce it. An earlier version of
`main` imported them lazily under `--sweep` and that test caught it.
"""
import os
import sys

from . import corpus, prediction

#: The measures section 6.4 publishes, incumbent first so a reader sees the comparison in the
#: direction the document makes it.
INCUMBENT = 'C0_nearest_point_min'
SELECTED = 'C4_corner_excluded_min'

NOMINAL = 0.6
WALL_TOL = prediction.WALL_TOL


def _rule(text):
    return '%s\n%s' % (text, '=' * len(text))


def prediction_report(log=None, sweep_path=None, out=None):
    """Section 6.5's table and verdict, for both measures. Returns the text and prints it."""
    out = out if out is not None else sys.stdout
    lines = [_rule('Pass 2 prediction against the real wall (section 6.5)'), '']
    builds = prediction.parse_build_log(log)
    closed = [b for b in builds if b.converged]
    if builds:
        lines.append('builds in the log           %d (%d converged, %d raised Unconverged)'
                     % (len(builds), len(closed), len(builds) - len(closed)))
        lines.append('worst pass 2 prediction     %.4f mm against TAU = %.3f mm'
                     % (max(b.predicted for b in closed), prediction.TAU))
        lines.append('')
    for name in (INCUMBENT, SELECTED):
        lines.append(prediction.table(name, log, sweep_path))
        v = prediction.verdict(name, log, sweep_path)
        lines.append('')
        lines.append('  %s' % name)
        if not v['builds_paired']:
            lines.append('    no build has both a prediction and a full-coverage real reading')
            lines.append('')
            continue
        lines.append('    builds paired                      %d' % v['builds_paired'])
        lines.append('    every prediction within TAU        %s' % v['predictions_within_tau'])
        lines.append('    real wall worse than TAU           %d of %d'
                     % (v['builds_real_worse_than_tau'], v['builds_paired']))
        lines.append('    real wall worse than WALL_TOL      %d of %d'
                     % (v['builds_real_worse_than_tolerance'], v['builds_paired']))
        lines.append('    meeting WALL_TOL = %.3f mm        %d'
                     % (v['tolerance'], v['builds_meeting_tolerance']))
        lines.append('    mean shortfall                     %.4f mm' % v['mean_shortfall'])
        lines.append('    worst                              %s, predicted %.4f, real %.4f, '
                     'short by %.4f mm'
                     % (v['worst_label'], v['worst_predicted'], v['worst_real'],
                        v['worst_shortfall']))
        lines.append('')
    text = '\n'.join(lines)
    out.write(text + '\n')
    return text


def sweep_report(Part, App, measures=None, records=None, out=None, write_to=None,
                 nominal=NOMINAL, tolerance=WALL_TOL):
    """Section 6.4's corpus table: several measures over every saved wall, on identical sections.

    **Pairing the measures on the same sections is what makes the comparison valid.** The soak's own
    recorded figures were taken on the body-derived station grid, which a saved wall cannot
    reproduce (`corpus.station_grid`), so a figure from here may not be differenced against one the
    soak recorded. Two measures run here were handed the same sections, so a difference between them
    is a difference between instruments and nothing else.

    Returns `(results, text)`. `write_to` defaults to the sweep file `prediction` reads, so running
    this and then `prediction_report` reproduces both published sections in order.
    """
    from . import candidates, sweep                              # local: keeps imports cheap
    out = out if out is not None else sys.stdout
    measures = measures or {INCUMBENT: candidates.nearest_point_min,
                            SELECTED: candidates.corner_excluded_min}
    records = records if records is not None else corpus.available()
    names = [n for n in (INCUMBENT, SELECTED) if n in measures] or sorted(measures)
    write_to = write_to if write_to is not None else prediction.DEFAULT_SWEEP

    out.write(_rule('Corpus sweep (section 6.4)') + '\n\n')
    out.write('sweeping %d saved walls with %d measures on identical stations\n\n'
              % (len(records), len(measures)))
    out.flush()

    def progress(r):
        out.write('  %-26s %s  cov %s  %4.0f s\n'
                  % (r['label'],
                     '  '.join('%s %.4f' % (n.split('_')[0], r['worst_thin'][n]) for n in names),
                     '/'.join(str(r['stations_measured'][n]) for n in names),
                     r['elapsed_s']))
        out.flush()

    results = sweep.sweep(measures, Part, App, nominal, records=records, on_wall=progress)
    if write_to:
        sweep.write_jsonl(results, write_to)

    lines = ['', sweep.table(results, tolerance, names=names), '']
    for name in names:
        v = sweep.verdict(results, tolerance, name)
        lines.append('  %s at WALL_TOL = %.3f mm' % (name, tolerance))
        lines.append('    walls measured at every station    %d of %d'
                     % (v['walls_with_full_coverage'], v['walls']))
        lines.append('    of those, meeting the tolerance    %d' % v['meets_tolerance'])
        # The gate counts a sectionless station a failure, not a skip (IP-WTM-19), so the three
        # outcomes are reported together and they account for every wall.
        lines.append('    fails: %d thin, %d for coverage     (%d in all, of %d walls)'
                     % (v['fails_tolerance'], v['fails_coverage'], v['fails_total'], v['walls']))
        if v['worst_label']:
            lines.append('    worst                              %s at %.4f mm'
                         % (v['worst_label'], v['worst_thin']))
        lines.append('')
    dis = sweep.disagreements(results, names[0], names[-1], tolerance) if len(names) > 1 else []
    lines.append('walls where the two measures disagree on the verdict: %d' % len(dis))
    for d in dis:
        lines.append('  %-26s %s %.4f  %s %.4f  (coverage %d of %d)'
                     % (d['label'], names[0], d[names[0]], names[-1], d[names[-1]],
                        d['coverage'], d['stations']))
    if write_to:
        lines.append('written %s' % write_to)
    text = '\n'.join(lines)
    out.write(text + '\n')
    return results, text


def main(argv=None, Part=None, App=None):
    """The cheap half, which needs no vendor module. Returns a shell exit status.

    **`Part` and `App` are parameters, not imports, and that is enforced by a test.** This package
    is importable from the project's own interpreter as well as from `freecadcmd`, so no module in
    it may import a vendor module anywhere -- not even inside a function, which is why `--sweep`
    takes the modules from its caller rather than importing them itself::

        import FreeCAD as App, Part
        from wall_measure import report
        report.main(['--sweep'], Part=Part, App=App)
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--sweep' in argv:
        if Part is None or App is None:
            sys.stderr.write('--sweep needs Part and App passed in; run this under freecadcmd '
                             'or a bridge session and call main(argv, Part=Part, App=App)\n')
            return 2
        if not corpus.available():
            sys.stderr.write('no saved walls in %s; nothing to sweep\n' % corpus.SHAPES_DIR)
            return 1
        sweep_report(Part, App)
    if not os.path.isfile(prediction.DEFAULT_LOG):
        sys.stderr.write('no soak log at %s\n' % prediction.DEFAULT_LOG)
        return 1
    prediction_report()
    return 0


if __name__ == '__main__':                                       # pragma: no cover
    sys.exit(main())
