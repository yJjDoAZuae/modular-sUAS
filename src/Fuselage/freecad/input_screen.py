"""IP-WTM-41: build and save one wall per design-input case, so `ring_scan` can read the other axis.

**The bound this is here to remove.** IP-WTM-40 scanned all twelve distinct corpus walls at 1 mm
axially -- 1 704 stations, none severed -- which answers `cowl.md` OQ-DES-CW26's alternative 1 as
far as the saved walls go. Its own limit is recorded with it: **those twelve vary in `U` alone**,
with every other design input at the parameter sheet's literal. So nothing is known about a
configuration the corpus does not contain, and the severed ring is a property of the *rib cut*,
whose tools are placed and sized by rows that `U` does not touch.

**Why this builds rather than reads.** A 21-case free-parameter screen was run on 2026-09-30 and
found no construction failure, but it tested the **round-0** construction -- fit, dilate, cut -- for
validity and saved nothing. `ring_scan` reads a finished wall off disk, and a finished wall needs
`shell_solid`: the cell extension, the notched cut, the seam strip and the mirror. So the walls have
to exist first, and this is the step that makes them.

**One process a case, and the case's own record written by it.** `freecadcmd` exits 0 even when the
script raised, so the JSON is the only honest statement of how far a run got; a tail case is about
1 000 s and a screen is tens of them, so a crash must cost one case and not the ones already paid
for. Every case therefore writes `out/screen/records/<label>.json` and its own BREP, and
`ring_scan.py --family=screen` picks them up afterwards.

**What this deliberately does not measure.** No tessellated volume, no canonical hash (except on
request), and no 12-station `wall_thickness` sweep. The volume and the hash are about 100 s on a
tail wall each and answer reproducibility, which is not this item's question; the 12-station sweep
is strictly dominated by the dense scan that follows, which reads the same walls at 1 mm. What is
recorded instead is a cheap fingerprint -- solids, faces, edges, bounding box -- and it is not
decoration: `inputs.unmoved` uses it to name the cases whose override did not change the wall at
all, because a screen in which no override reached the geometry is an untested screen rather than a
clean one.

`--hash` turns the canonical hash on for one case. **Worth it for the baseline and only there**: the
baseline is the sheet's own configuration, which the 2026-10-06 soak already built and recorded a
hash for, so hashing it is a direct control on whether this harness builds what that one built. On
an excursion there is nothing to compare against.

Usage, one `--pass` per argument (see `tau_study.py` for why)::

    freecadcmd input_screen.py --pass --list=tail_shell
    freecadcmd input_screen.py --pass --check=tail_shell --pass --u=0.5
    freecadcmd input_screen.py --pass --refingerprint=1
    freecadcmd input_screen.py --pass --kind=tail_shell --pass --u=0.5 \
                               --pass --case=base --pass --hash=1
    freecadcmd input_screen.py --pass --kind=tail_shell --pass --u=0.5 \
                               --pass --case=top_diag_angle_hi

The whole screen, resumably -- skip a case that already has a record, and run the cheap kind
first so a finding arrives inside the hour rather than at the end of the night::

    for k in nose_cowl_shell:0.5 tail_shell:0.5; do
      kind=${k%%:*}; u=${k##*:}
      for c in $(freecadcmd input_screen.py --pass "--list=$kind" | sed -n 's/^CASE //p'); do
        [ -f "out/screen/records/${kind}_U${u}_${c}.json" ] && continue
        freecadcmd input_screen.py --pass "--kind=$kind" --pass "--u=$u" --pass "--case=$c" \
            > "out/screen/logs/${kind}_U${u}_${c}.log" 2>&1
      done
    done

Prints exactly one line to stdout among `cowl_tree`'s own build notes, prefixed so a driver can
find it::

    SCREEN_RESULT {"label": ..., "case": ..., "solids": ..., "brep": ..., "build_s": ...}
    SCREEN_ERROR  {"label": ..., "case": ..., "error": "..."}

**A build failure is a result, not a crash.** The construction refusing a configuration is one of
the three outcomes this screen can have, and it is the safe one -- the existing checks declining to
hand back a broken part. It is recorded as `error` on the case's own record so the screen's verdict
can count it, and the process still exits non-zero so a driver loop can see it.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', 'tools')))

import FreeCAD as App                                                   # noqa: E402,N813
import Part                                                             # noqa: E402

import cowl_interior as ci                                              # noqa: E402
import cowl_tree                                                        # noqa: E402
from corner_common import is_entry_point                                # noqa: E402

from wall_measure import corpus, inputs                                 # noqa: E402

BUILDERS = {'tail_shell': cowl_tree.tail_shell, 'nose_cowl_shell': cowl_tree.nose_cowl_shell}
BASE_PARAMS = {'tail_shell': cowl_tree.PARAMS_TAIL_SHELL,
               'nose_cowl_shell': cowl_tree.PARAMS_NOSE_COWL_SHELL}

#: `soak_cowl_shell.VOLUME_DEFLECTION`'s value, used only when `--hash` is asked for, so that a
#: hash from here is comparable with the one the 2026-10-06 soak recorded. A hash taken at a
#: different deflection is a different triangle set and would not compare.
HASH_DEFLECTION = 0.001


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    if default is None:
        raise SystemExit('missing --%s=' % name)
    return default


def _write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, 'w') as handle:
        json.dump(payload, handle, default=str, indent=1)


def list_cases(kind, u, out=None, pairs=False):
    """Print the case names for one kind, one a line, for a driver loop to read."""
    out = out if out is not None else sys.stdout
    rows = inputs.pair_cases(kind, u) if pairs else inputs.cases(kind, u)
    for case in rows:
        out.write('CASE %s\n' % case.name)
    for case in rows:
        out.write('#   %-56s %-24s %-9s %s\n'
                  % (case.name, case.alias or '-',
                     '' if case.is_baseline else '%+g' % case.delta, case.why))
    out.flush()
    return 0


def refingerprint(records_dir=None, out=None):
    """Fill `volume_raw` in on every saved screen record that lacks it. **No build.**

    `inputs.fingerprint` needs a geometric quantity, not only solids, faces, edges and the box: the
    nose screen's first report named `extrusion_width_lo` `unmoved` although it takes the wall from
    0.6 mm to 0.4 mm, because a thinner wall keeps the same outer surface and therefore the same
    topology and the same bounding box. The field was added after those walls were built, and this
    reads it back off the BREP rather than rebuilding them -- 0.2 s a nose wall against 54 s to
    build one, and about 1 s against 727 s on a tail.

    `Part` is needed to load a shape, which is why this is here and not in `wall_measure.inputs`.
    """
    out = out if out is not None else sys.stdout
    done, skipped = 0, 0
    for rec in corpus.screen():
        row = rec.recorded
        if row is None:
            out.write('  no record for %s\n' % rec.label)
            continue
        if row.get('volume_raw') is not None:
            skipped += 1
            continue
        shape = corpus.load(Part, rec)
        row['volume_raw'] = shape.Volume
        row['volume_raw_source'] = 'refingerprint from the saved BREP'
        _write_json(os.path.join(records_dir or inputs.SCREEN_RECORDS, '%s.json' % rec.label), row)
        out.write('  %-50s volume_raw %.4f\n' % (rec.label, row['volume_raw']))
        done += 1
    out.write('refingerprint: %d filled, %d already had one\n' % (done, skipped))
    out.flush()
    return 0


def check_cases(kind, u, out=None):
    """Apply every case to the real sheet and print the cell it produces. No build, no geometry.

    **The pre-flight, and it exists because of what a typo costs here.** `inputs.EXCURSIONS` names
    rows by alias and `inputs.override` raises when the sheet has no such row -- correctly, since a
    silently-ignored override would run the baseline under a case's name and report it as coverage.
    But raising at build time means finding out one case into a screen that is six hours long, with
    the failure arriving after the first 1 000 s build. This asks the same question for every case
    at once, for the cost of starting FreeCAD, and is the step to run before a tail screen.

    Returns 0 when every case resolves, 1 otherwise, and prints the offending case either way.
    """
    out = out if out is not None else sys.stdout
    rows = BASE_PARAMS[kind]
    bad = 0
    for case in inputs.cases(kind, u):
        try:
            applied = inputs.apply_case(rows, case)
        except ValueError as exc:
            out.write('BAD  %-34s %s\n' % (case.name, exc))
            bad += 1
            continue
        if case.is_baseline:
            out.write('OK   %-34s %-24s U = %s\n'
                      % (case.name, '-', inputs.value_of(applied, 'U')))
            continue
        was, now = inputs.value_of(rows, case.alias), inputs.value_of(applied, case.alias)
        # **Checked, not assumed.** A delta of 0, or a coefficient bump that lands back on the
        # sheet's own text, would give a case whose build is the baseline's -- which is exactly the
        # vacuous coverage `inputs.unmoved` exists to catch, and is cheaper to catch here.
        if was == now:
            out.write('BAD  %-34s %-24s unchanged at %s\n' % (case.name, case.alias, now))
            bad += 1
            continue
        out.write('OK   %-34s %-24s %s -> %s\n' % (case.name, case.alias, was, now))
    out.write('%s: %d case(s), %d unresolved\n'
              % ('FAIL' if bad else 'PASS', len(inputs.cases(kind, u)), bad))
    out.flush()
    return 1 if bad else 0


def build_case(kind, u, case, want_hash=False, shapes_dir=None, out=None):
    """Build one case to a finished wall, save it, and return the record.

    Raises whatever the construction raises. The caller turns that into a `SCREEN_ERROR` record,
    because a configuration the construction refuses is one of this screen's three outcomes and
    has to be counted rather than lost to a traceback.
    """
    out = out if out is not None else sys.stdout
    params = inputs.apply_case(BASE_PARAMS[kind], case)
    cell = inputs.value_of(params, case.alias) if not case.is_baseline else None
    out.write('%s: %s = %s%s\n'
              % (case.label, case.alias or 'U only', cell if cell else repr(float(u)),
                 '' if case.is_baseline else '  (%+g %s)' % (case.delta, case.unit)))
    out.flush()

    t0 = time.time()
    doc = App.newDocument('screen')
    tip = cowl_tree.emit(doc, None, params, BUILDERS[kind])
    doc.recompute()
    build_s = time.time() - t0

    # **Checked explicitly, not inferred from a Python exception** -- `soak_cowl_shell`'s own
    # finding, and the reason that check is there: a construction failure inside a
    # `Part::FeaturePython`'s `execute()` does not propagate, `doc.recompute()` swallows it, and
    # `tip.Shape` comes back empty. Left unchecked, this screen would save a zero-solid BREP, the
    # scan would read it as a wall with no sections anywhere, and `no_wall` at every station on an
    # excursion case would look like the severed ring the scan is hunting.
    if not tip.Shape.Solids:
        raise ValueError(
            'the wall has no solids -- the construction failed inside execute() and '
            'doc.recompute() swallowed whatever it raised. Check the freecadcmd log above '
            'this result for the real traceback.')

    t1 = time.time()
    wall = tip.Shape
    bb = wall.BoundBox
    # The body-derived station bounds, recorded for IP-WTM-18's reason: they are the one thing a
    # saved wall cannot recover, and `corpus.gate_station_grid` reads them. Not used by this item --
    # the dense scan places its own grid from the wall's real sectioning extent -- but a 727 s build
    # should not have to be repeated to get a figure that costs forty sections here.
    lo, hi = ci.z_extent(tip.Body.Shape)

    record = {
        'label': case.label, 'kind': kind, 'u': float(u), 'case': case.name,
        'alias': case.alias, 'delta': case.delta, 'unit': case.unit, 'why': case.why,
        'cell': cell,
        'solids': len(wall.Solids), 'faces': len(wall.Faces), 'edges': len(wall.Edges),
        # **A difference detector, never a measure.** IP-FC-119 measured `Shape.Volume` wrong by
        # 0.16-0.24 % on this project's B-spline solids, which is why every quantity in this
        # subsystem comes from a refined tessellation. The defect is a deterministic bias: the same
        # shape returns the same wrong number and two different shapes return different ones, so it
        # answers "is this the baseline's wall again?" soundly while answering "how big is it?"
        # wrongly. `inputs.fingerprint` has why the four topological fields are not enough on their
        # own -- they cannot see a 0.6 mm wall become a 0.4 mm one.
        'volume_raw': wall.Volume,
        'wall_bbox': [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax],
        'station_z_lo': lo + 1.0, 'station_z_hi': hi - 1.0,
        'partition_slip': tip.PartitionSlip, 'inset': float(tip.Inset),
        'build_s': build_s,
    }

    if want_hash:
        # Only ever asked for on the baseline: see the module docstring. `mesh_stats` lives on the
        # driver side but imports cleanly under freecadcmd, the same reach-across `soak_cowl_shell`
        # makes, and `canonical_hash` is the screen OQ-ARCH-19 decided on.
        import mesh_stats
        verts, facets = wall.tessellate(HASH_DEFLECTION)
        record['wall_hash'] = mesh_stats.canonical_hash(
            [[(verts[i].x, verts[i].y, verts[i].z), (verts[j].x, verts[j].y, verts[j].z),
              (verts[k].x, verts[k].y, verts[k].z)] for i, j, k in facets])
        record['hash_deflection'] = HASH_DEFLECTION

    shapes_dir = shapes_dir or inputs.SCREEN_SHAPES
    if not os.path.isdir(shapes_dir):
        os.makedirs(shapes_dir)
    brep = os.path.join(shapes_dir, '%s.brep' % case.label)
    wall.exportBrep(brep)
    record['brep'] = brep
    record['measure_s'] = time.time() - t1
    App.closeDocument(doc.Name)
    return record


def main():
    if _opt('list', ''):
        return list_cases(_opt('list'), float(_opt('u', '0.5')),
                          pairs=bool(_opt('pairs', '')))
    if _opt('check', ''):
        return check_cases(_opt('check'), float(_opt('u', '0.5')))
    if _opt('refingerprint', ''):
        return refingerprint(_opt('records', inputs.SCREEN_RECORDS))
    kind = _opt('kind')
    u = float(_opt('u'))
    name = _opt('case')
    if kind not in BUILDERS:
        raise SystemExit('unknown kind %r -- tail_shell or nose_cowl_shell' % kind)
    # **`--pairs` selects a different population, not an option on the same one.** OQ-DES-CW26's
    # alternative 1 leaves two-input interactions untested, and those walls are a third corpus
    # beside the `U` soak and the one-row screen. They get their own case list, their own shapes
    # and their own records, so a count taken across "the screen" keeps meaning what it meant.
    pairs = bool(_opt('pairs', ''))
    case = (inputs.find_pair(kind, u, name) if pairs else inputs.find(kind, u, name))
    if case is None:
        raise SystemExit('unknown %s case %r for %s; --list=%s prints them'
                         % ('pair' if pairs else 'screen', name, kind, kind))

    records_dir = _opt('records', inputs.PAIR_RECORDS if pairs else inputs.SCREEN_RECORDS)
    shapes_dir = _opt('shapes', inputs.PAIR_SHAPES if pairs else inputs.SCREEN_SHAPES)
    path = os.path.join(records_dir, '%s.json' % case.label)
    started = time.time()
    try:
        record = build_case(kind, u, case, want_hash=bool(_opt('hash', '')),
                            shapes_dir=shapes_dir)
    except Exception as exc:                                            # noqa: BLE001
        # **`build_s` on the failure path too.** What a refused configuration costs is a figure
        # OQ-DES-CW32 quotes, and the first version of this record did not carry it -- so the
        # 85-108 s a refused tail case takes had to be read out of a driver's progress log, which
        # is not an artifact anything regresses.
        record = {'label': case.label, 'kind': kind, 'u': float(u), 'case': case.name,
                  'alias': case.alias, 'delta': case.delta, 'unit': case.unit,
                  'build_s': time.time() - started,
                  'error': '%s: %s' % (type(exc).__name__, exc)}
        _write_json(path, record)
        print('SCREEN_ERROR ' + json.dumps(record, default=str))
        sys.stdout.flush()
        return 1
    _write_json(path, record)
    print('SCREEN_RESULT ' + json.dumps(record, default=str))
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
