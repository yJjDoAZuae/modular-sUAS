"""IP-WTM-38: does the interior surface survive the steps *after* `cavity`? The free half.

**What is already settled, and what is not.** IP-WTM-37 showed that the rib cut inside `cavity`
only *trims*: the fitted interior's control net comes out of it identical to the one it was handed,
worst pole 0.000e+00 mm on both kinds, so no boundary condition is imposed at a rib edge and no
displacement can propagate into a patch interior. That is one boolean out of four.
`_extend_across_cell`, `notched.cut(inside)`, `_strip_seam` and `mirror_across_cell` each carry
their own boolean and their own `removeSplitter`, and none of them was covered.

**The mirror step can be tested on the saved walls with no build at all, and that is this script.**
`shell_solid` finishes a wall by mirroring one cell across its cell planes, so a finished wall
already carries several copies of the fitted patch -- the nose at `U` = 1 reports "3 mirror step(s)".
If a mirror step refitted the surface, one copy would no longer be the rigid image of the others.

`surface_identity` cannot ask this, and asking it anyway would give the wrong answer with
confidence: a mirrored copy's poles are *supposed* to differ, so pole-for-pole equality would mean
the mirror had failed to move anything. `boolean_edges.congruent_identity` compares the control
net's own internal step lengths, which a reflection preserves exactly and a refit does not, and it
needs no knowledge of the reflection planes -- which matters, because a wall carries copies composed
through several planes and the composition is not recoverable from the shape.

**The test is non-circular because it predicts congruence from parameterization.** Surfaces are
grouped by degrees, pole counts, knots, multiplicities and periodicity, which never looks at a pole;
two surfaces on one finished wall that agree on all of that are copies of the same fit, because
nothing else in the construction produces that structure twice. Congruence is then a prediction
about their poles that is free to fail.

**A group with no mirrored copy proves nothing**, and the verdict says so rather than counting it as
a pass: that is the same error as cross-checking two measures of an empty input, which this
subsystem has now made six times (section 6.1).

What this does **not** cover: `_extend_across_cell`, `notched.cut(inside)` and `_strip_seam` all run
before the mirror and are not separable from a saved wall -- they need a build with the intermediate
shapes in hand, which is the rest of IP-WTM-38.

Costs a file read a wall; no build, no boolean, no slice.

Usage, one `--pass` per argument::

    freecadcmd wall_surface_check.py
    freecadcmd wall_surface_check.py --pass --only=tail_shell_U3.0
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))

# `App` is imported and unused on purpose: every script in this directory imports it before `Part`,
# and nothing here should be the one place that discovers whether `Part` loads without it.
import FreeCAD as App                                              # noqa: E402,N813,F401
import Part                                                        # noqa: E402

import cowl_interior as ci                                         # noqa: E402
import cowl_tree                                                   # noqa: E402
import soak_cowl_shell as soak                                     # noqa: E402
from corner_common import is_entry_point                           # noqa: E402

from wall_measure import boolean_edges as be                       # noqa: E402
from wall_measure import corpus                                    # noqa: E402


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def check_edges(wall, label='', out=None):
    """IP-WTM-35: every edge group of a finished wall not shared by exactly two faces, diagnosed.

    `face_adjacency` found one such group on the tail's `cavity` output and could only count it.
    A seam, a parameterization pole, an open boundary and a true non-manifold edge all present the
    same way to a count, and only two of the four are defects. This asks the finished wall, which
    is both free and the more useful place to ask: a free boundary on an intermediate shape may be
    closed by a later step, while one on the shipped wall is a hole in the part.
    """
    out = out if out is not None else sys.stdout
    rows = be.anomalous_edges(wall, Part=Part)
    verdict = be.edge_anomaly_verdict(rows)
    out.write('    edges: %d group(s) not shared by exactly two faces  %s\n'
              % (verdict['groups'],
                 ' '.join('%s=%d' % kv for kv in sorted(verdict['kinds'].items()))))
    if rows:
        out.write('\n'.join('      ' + line
                            for line in be.table_anomalous(rows).splitlines()) + '\n')
    if not verdict['clean']:
        out.write('      %d SERIOUS (an open boundary or a non-manifold edge on a closed solid)\n'
                  % len(verdict['serious']))
    out.flush()
    return rows, verdict


def check_wall(wall, label='', out=None):
    """One saved wall: its B-spline groups, and whether every mirrored copy is congruent."""
    out = out if out is not None else sys.stdout
    rows = be.mirror_families(wall)
    verdict = be.mirror_verdict(rows)
    out.write('%s  %d face(s), %d B-spline surface(s) in %d parameterization group(s)\n'
              % (label, len(wall.Faces), verdict['surfaces'], verdict['groups']))
    out.write('\n'.join('    ' + line for line in be.table_mirror(rows).splitlines()) + '\n')
    if verdict['vacuous']:
        out.write('    NOTHING TESTED: no group carries a mirrored copy, so congruence here is '
                  'trivially true and says nothing about the mirror steps\n')
    else:
        out.write('    %s: %d mirrored copy(ies) across %d group(s), worst step mismatch %.3e mm\n'
                  % ('CONGRUENT' if verdict['clean'] else 'NOT CONGRUENT',
                     verdict['mirrored_copies'], verdict['groups_with_a_mirrored_copy'],
                     verdict['worst_step_mm']))
    out.flush()
    return rows, verdict


def check_stages(kind, u, tau=None, out=None):
    """IP-WTM-38's remaining half: the three booleans *after* `cavity`, on a staged build.

    **Why this needs a build and the rest of this script does not.** `mirror_families` above tests
    a finished wall's mirrored copies against each other, which catches a refit applied to one copy
    and not the others. It cannot catch a refit applied *before* the mirror: every copy is then
    equally refit, every copy is congruent, and the test passes. `_extend_across_cell` and
    `notched.cut(inside)` both run before any mirror, and `_strip_seam` runs inside the first
    `mirror_across_cell`, so none of the three is visible from a saved wall.

    `shell_solid` fills a `stages` list with `(name, shape)` a step when given one, and
    `boolean_edges.stage_identity` compares each consecutive pair's fitted surface by
    parameterization -- not by face index, since a boolean renumbers faces freely and can leave one
    surface carrying several.
    """
    out = out if out is not None else sys.stdout
    doc = App.newDocument('wall_surface_stages')
    started = time.time()
    try:
        tip = cowl_tree.emit(doc, None, soak.with_u(soak.BASE_PARAMS[kind], u),
                             soak.BUILDERS[kind])
        doc.recompute()
        if not tip.Shape.Solids:
            raise ValueError('the wall has no solids -- read the log for execute()\'s traceback')
        notches = Part.makeCompound([n.Shape for n in tip.Notches])
        mirrors = [App.Vector(*[float(v) for v in s.split(',')]) for s in tip.Mirrors]
        stages = []
        ci.shell_solid(tip.Base.Shape, tip.Body.Shape, notches, float(tip.Inset), tip.Overhang,
                       mirrors, tau=float(tau) if tau is not None else ci.TAU, stages=stages)
        out.write('%s U=%s: %d stage(s) in %.0f s\n'
                  % (kind, u, len(stages), time.time() - started))
        rows = be.stage_identity(stages)
        out.write('\n'.join('    ' + line
                            for line in be.table_stages(rows).splitlines()) + '\n')
        out.flush()
        return rows, be.stage_verdict(rows)
    finally:
        App.closeDocument(doc.Name)


def main():
    only = _opt('only')
    if any(a == '--stages' for a in sys.argv):
        kind = _opt('kind', 'nose_cowl_shell')
        u = float(_opt('u', '1.0'))
        rows, verdict = check_stages(kind, u, _opt('tau'))
        print('STAGE_IDENTITY ' + json.dumps({'kind': kind, 'u': u, 'verdict': verdict,
                                              'rows': rows}, default=str), flush=True)
        return 0
    records = [r for r in corpus.distinct() if not only or only in r.label]
    print('wall_surface_check: %d wall(s)' % len(records), flush=True)
    bad, vacuous, worst, edgy = [], [], 0.0, []
    for rec in records:
        wall = corpus.load(Part, rec)
        _rows, verdict = check_wall(wall, rec.label)
        _erows, everdict = check_edges(wall, rec.label)
        if verdict['vacuous']:
            vacuous.append(rec.label)
        elif not verdict['clean']:
            bad.append(rec.label)
        if verdict['worst_step_mm'] is not None:
            worst = max(worst, verdict['worst_step_mm'])
        if not everdict['clean']:
            edgy.append((rec.label, len(everdict['serious'])))
    print('%d wall(s): %d with a non-congruent copy, %d that tested nothing; worst step mismatch '
          'anywhere %.3e mm' % (len(records), len(bad), len(vacuous), worst), flush=True)
    print('edges: %d wall(s) with an open boundary or a non-manifold edge%s'
          % (len(edgy), '' if not edgy else ' -- ' + ', '.join('%s (%d)' % e for e in edgy)),
          flush=True)
    if bad:
        print('NOT CONGRUENT: %s' % ', '.join(bad), flush=True)
    return 0


if is_entry_point(__name__):
    sys.exit(main())
