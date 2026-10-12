"""Has the *shape* of a rib's boolean edge ever been checked? No. This checks it.

**The gap.** Section 4.2's three-dimensional identity moves the rib creases out of the fitted
surface and into a boolean: `dilated_notches` argues that "the creases then arrive as the edges of
a boolean between two well-formed solids, which is where a crease belongs". That says where a
crease comes from. Nothing in the build has ever checked that the crease the kernel returned is
where it should be -- on the fitted interior surface and on the dilated tool's own face plane,
both at once, which is what the intersection of those two surfaces means.

What `cavity` does check after the cut is a **volume** and a **count**: at most `RIB_RESIDUE`
= 0.01 mm3 of tool left inside, and exactly one solid. Both are necessary and neither constrains
the cut's geometry. A trimming curve that has wandered 0.05 mm off the surface it is supposed to
lie on changes the residue volume by nothing measurable and splits nothing, and the wall is
0.05 mm wrong along it. IP-FC-137's own synthetic result is the precedent: a genuinely invalid
five-face sliver "passed the existing volume-only OK/retry check" at 0.000000 mm3.

Three things in the cut are entitled to move geometry, and the first two are not bounded by
anything the wall is measured against:

1. `smooth.cut(tool, RIB_CUT_FUZZ)` is a **fuzzy** boolean. Its own constant note records the
   fuzz doing exactly what a fuzz does -- "a snap of the near-tangent geometry together".
2. `removeSplitter()` merges faces it judges co-surface and **refits** the merged boundary. On a
   B-spline that is a real change of geometry, and it runs on both operands and on the result.
3. a near-tangency between a dilated diagonal and the interior surface is already documented
   (`RIB_CUT_FUZZ`, the `Diag12Safe` sliver at `U` = 0.75), and a tangency is where a trimming
   curve is worst determined.

**The three operands are already available, so nothing in the builder changes.** `cavity`'s
`report` hands out `smooth_shape` (the pre-cut fitted interior) and `rib_tool` (the fused
dilation), and returns the cut cavity. That is `S`, `T` and `S - T`, which is everything the
check needs.

`wall_measure.boolean_edges` holds the measurement and its tests; this module builds a cell, runs
one `cavity`, and reports.

**Cost, and it is two cavities, not one.** `build_cell`'s `recompute()` is what produces the cell
shapes `cavity` needs, so it pays a full build first and `operands` then pays a second `cavity` on
the same inputs -- measured on `tail_shell` at `U` = 0.5, 745 s each. The nose at `U` = 0.5 is the
cheapest configuration there is at about 30 s a cavity; start there, and only pay for a tail once
the rig is known to work. The nose has 4 notch edges and the tail 19 to 26, so the tail is also
where a defect of this kind would be densest. Avoiding the second cavity would mean
`cowl_tree._CowlShell.execute` passing a report out of its own build, which is a change to the
production path and not worth making for a diagnostic.

Usage, one `--pass` per argument (see `tau_study.py` for why)::

    freecadcmd rib_edge_check.py --pass --kind=nose_cowl_shell --pass --u=0.5
    freecadcmd rib_edge_check.py --pass --kind=tail_shell --pass --u=0.5 --pass --arc=0.5
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))

import FreeCAD as App                                              # noqa: E402,N813
import Part                                                        # noqa: E402

import cowl_interior as ci                                         # noqa: E402
from corner_common import is_entry_point                           # noqa: E402
from tau_study import _opt, build_cell                             # noqa: E402

from wall_measure import boolean_edges as be                       # noqa: E402

#: How many of the worst samples get re-measured with `distToShape` against the real trimmed
#: faces. The cheap measures are both optimistic in a known direction (`boolean_edges`' module
#: note), so this is not optional; it is capped because a kernel distance against a compound of
#: every operand face is the expensive call here, not the arithmetic.
KERNEL_CHECK = 16

#: How many interior probes per fitted face `patch_deviation` takes. The question it answers is
#: whether a deviation grows with distance from a rib edge, which needs enough probes to fill the
#: distance bands rather than enough to resolve the surface.
PATCH_PROBES = 600

#: How many of those probes also get normals. A position is one kernel call and a normal is
#: twelve, so this is the term that sets the run time.
NORMAL_PROBES = 150

#: How many rib-edge samples get a crease angle. Ranked worst-first by the edge conformance
#: above, so a tangency at the least-conformant edge cannot be missed by the cap.
CREASE_SAMPLES = 200


def operands(shell, tau=None):
    """Build the cavity and hand back `(cut, smooth, tool, report)`: `S - T`, `S` and `T`.

    Calls `cavity` rather than `shell_solid`: the extend, cell cut and mirror steps that follow it
    are not part of the rib cut and would only add time. The report is returned whole, so a caller
    can set a figure here against `worst_wall`, `rib_residue` and the station positions from the
    same build rather than from a different one.
    """
    notches = Part.makeCompound([n.Shape for n in shell.Notches])
    report = {}
    kw = {} if tau is None else {'tau': float(tau)}
    cut = ci.cavity(shell.Body.Shape, shell.Base.Shape, notches, shell.Inset, shell.Overhang,
                    report=report, **kw)
    return cut, report['smooth_shape'], report['rib_tool'], report


def check(cut, smooth, tool, arc=be.SAMPLE_ARC, probes=PATCH_PROBES,
          normal_limit=NORMAL_PROBES, out=None):
    """Classify the cut's faces, find the rib edges, measure them, then measure the surface itself.

    Two questions in sequence, and the second is not implied by the first: whether the rib edges
    sit on both surfaces they are the intersection of, and whether the surface the boolean handed
    back is the one it was given. An edge can be in exactly the right place on a surface that has
    moved underneath it.
    """
    out = out if out is not None else sys.stdout
    at = time.time()
    reference = be.smooth_reference(Part, smooth)
    planes = be.plane_set(tool)
    out.write('  %d cut faces, %d cut edges; tool has %d planar faces; smooth has %d fitted '
              'face(s) and %d closing face(s)  [%.0f s]\n'
              % (len(cut.Faces), len(cut.Edges), len(planes[0]), len(reference[1].Faces),
                 len(reference[2].Faces), time.time() - at))
    out.flush()

    at = time.time()
    face_rows = be.classify_faces(Part, cut, reference, planes)
    tally = {}
    for row in face_rows:
        tally[row['on']] = tally.get(row['on'], 0) + 1
    out.write('  face classification: %s  [%.0f s]\n' % (tally, time.time() - at))
    # **A `neither` is the one classification that means a defect, so it is printed, not counted.**
    # Three of this rig's own four wrong answers showed up first as an unexplained `neither` count,
    # and each time the three distances were what identified it.
    odd = [r for r in face_rows if r['on'] in (be.ON_NEITHER, be.ON_AMBIGUOUS)]
    for row in odd[:12]:
        out.write('    face %-4d %-16s %-10s surface %10.3e  lid %10.3e  tool %10.3e\n'
                  % (row['face'], row['surface'], row['on'], row['d_surface_mm'],
                     row['d_lid_mm'], row['d_tool_mm']))
    if len(odd) > 12:
        out.write('    ... and %d more\n' % (len(odd) - 12))
    out.flush()

    at = time.time()
    groups, nonmanifold = be.face_adjacency(cut, face_rows)
    kinds = be.edge_kinds(cut, face_rows, groups)
    edge_rows = be.rib_edges(cut, face_rows, groups)
    total_mm = sum(r['length_mm'] for r in edge_rows)
    out.write('  %d edge group(s), %d not shared by exactly two faces  [%.0f s]\n'
              % (len(groups), nonmanifold, time.time() - at))
    for key in sorted(kinds, key=lambda k: -kinds[k]):
        out.write('    %-28s %4d\n' % (key, kinds[key]))
    out.write('  %d rib edge(s) where the fitted surface meets a tool face, %.2f mm in all\n'
              % (len(edge_rows), total_mm))
    out.flush()

    at = time.time()
    samples, truncated = be.edge_conformance(Part, edge_rows, planes, reference[1], arc=arc)
    summary = be.summarize(samples)
    out.write('  sampled at %.3f mm, %d point(s), %d edge(s) dropped on the budget  [%.0f s]\n'
              % (arc, len(samples), truncated, time.time() - at))
    out.flush()

    agreement = []
    if samples:
        at = time.time()
        agreement = be.agrees_with_kernel(Part, App, samples, smooth, tool, worst=KERNEL_CHECK)
        out.write('  kernel cross-check on the worst %d  [%.0f s]\n'
                  % (len(agreement), time.time() - at))
    out.write(be.table(summary, agreement))
    out.flush()

    # ---------------------------------------------------------------- the surface, not the edge
    # Position on both surfaces constrains the trim curve, not the surface it is drawn on. These
    # three ask whether the boolean handed back the surface it was given.
    at = time.time()
    identity = []
    pre = be.bspline_surfaces(smooth)
    for index, surf in be.bspline_surfaces(cut):
        row = be.surface_identity(surf, pre[0][1]) if pre else {'identical': False}
        row['face'] = index
        identity.append(row)
    out.write('  %d distinct B-spline surface(s) on the cut, %d on the pre-cut solid  [%.0f s]\n'
              % (len(identity), len(pre), time.time() - at))
    out.flush()

    at = time.time()
    edge_shapes = [r['edge'] for r in edge_rows]
    patch_rows = be.patch_deviation(Part, cut, reference[1], edge_shapes, probes=probes,
                                   normal_limit=normal_limit)
    patch = be.summarize_patch(patch_rows)
    out.write('  patch interior sampled: %d probe(s), %d with normals  [%.0f s]\n'
              % (len(patch_rows), patch.get('normals_measured', 0), time.time() - at))
    at = time.time()
    creases = be.crease_angles(Part, samples, cut, reference[1], planes, worst=CREASE_SAMPLES)
    out.write('  crease angles on %d rib-edge sample(s)  [%.0f s]\n'
              % (len(creases), time.time() - at))
    out.write(be.table_patch(patch, identity, creases))
    out.flush()

    return {'faces': tally, 'edges': len(edge_rows), 'edge_length_mm': total_mm,
            'edge_groups': len(groups), 'nonmanifold_groups': nonmanifold,
            'edge_kinds': kinds, 'truncated_edges': truncated, 'summary': summary,
            'agreement': agreement, 'face_rows': face_rows,
            'identity': identity, 'patch': patch, 'creases': creases}


def main():
    kind = _opt('kind', 'nose_cowl_shell')
    u = float(_opt('u', '0.5'))
    arc = float(_opt('arc', be.SAMPLE_ARC))
    tau = _opt('tau')
    started = time.time()
    doc, shell = build_cell(kind, u)
    t = float(shell.Inset)
    print('rib_edge_check %s U=%s, t = %.4f mm, %d tools  [%.0f s to build the cell]'
          % (kind, u, t, len(shell.Notches), time.time() - started), flush=True)
    at = time.time()
    cut, smooth, tool, report = operands(shell, tau)
    print('  cavity: %d solids, valid=%s, worst_wall %.5f mm, rib_residue %.6f mm3, '
          '%d patch(es), %d station(s)  [%.0f s]'
          % (len(cut.Solids), cut.isValid(), report.get('worst_wall', float('nan')),
             report.get('rib_residue', float('nan')), report.get('patches', -1),
             report.get('stations', -1), time.time() - at), flush=True)
    result = check(cut, smooth, tool, arc=arc, probes=int(_opt('probes', PATCH_PROBES)),
                   normal_limit=int(_opt('normals', NORMAL_PROBES)))
    result.pop('face_rows', None)
    print('RIB_EDGE_CHECK ' + json.dumps(
        {'kind': kind, 'u': u, 't': t, 'arc': arc, 'tau': tau,
         'worst_wall': report.get('worst_wall'), 'rib_residue': report.get('rib_residue'),
         'patches': report.get('patches'), 'stations': report.get('stations'),
         'result': result}, default=str))
    sys.stdout.flush()
    App.closeDocument(doc.Name)
    return 0


if is_entry_point(__name__):
    sys.exit(main())
