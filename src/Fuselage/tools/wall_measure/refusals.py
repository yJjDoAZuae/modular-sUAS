"""Keeping the shape a refusal was measured on, instead of discarding it with the exception.

**Why this exists.** `cowl_interior`'s checks refuse rather than ship a defective wall, and until
2026-10-29 a refusal carried only a sentence. Measured that day: the post-cut pass refused a
`tail_shell` at `U` = 3.0 reporting the finished wall closed to **0.0001 mm at `z` = -73.1818**,
and the cut cavity that reading came from was destroyed as the exception propagated -- so the only
question the refusal raises, what the geometry actually looks like there, cost another 1.94 hour
build to even ask. `Unconverged` now carries `shape` and `z`; this module is the side that writes
them down.

**The construction does not write to disk and this module does not import the kernel.** The
exporter is an argument. Under `freecadcmd` a caller passes something that calls
`Shape.exportBrep`; in `tests/test_wall_measure_refusals.py` it is a function that records what it
was asked to write. That is the same division `ring_breaks` uses for its classifier, and it is what
makes the traps below testable at all -- every one of them is about an exception or a path, and
none of them needs a solid.

**The rule this module exists to enforce: saving evidence must never fail the refusal.** `save`
runs inside a caller's `except` block. An exception raised here would replace the refusal being
diagnosed with a failure to diagnose it, which loses the finding *and* the reason for it. So
`save` returns a record rather than raising, reports the export's own failure in that record, and
treats "this refusal has no shape" as the ordinary case it is rather than an error.
"""
import os

import units

#: BREP, not STEP or STL. It is the kernel's own format, so it round-trips the exact topology the
#: refusal is about -- and a refusal is frequently *about* the topology, invalid faces and all,
#: which a mesh export silently repairs and a STEP export may reinterpret.
EXT = 'brep'

#: Refusal artifacts go in their own subdirectory, never beside the healthy walls. A reader
#: should not have to consult a filename to know whether a shape is a result or a diagnosis.
DIRNAME = 'refusals'


#: Below this, a boolean residue's volume is not distinguishable from the kernel's own noise on
#: near-tangent operands. It is a floor on *volume only*, never a verdict on its own -- see
#: `escape`. 1.0e-15 m3 is the 1.0e-6 mm3 this was until IP-FC-163 converted it.
ESCAPE_TOL_M3 = 1.0e-15

#: A piece narrower than this in every direction is at the scale IP-FC-137's sliver was found at
#: (a ~10 micron bounding box), which is reported as a sliver rather than as material. 5.0e-5 m is
#: the 0.05 mm this was until IP-FC-163 converted it.
SLIVER_M = 5.0e-5

CONTAINED, ESCAPED, SLIVER, INVALID = 'contained', 'escaped', 'sliver', 'invalid'


def escape(volume_m3, pieces, valid, span_m=None, tol_m3=ESCAPE_TOL_M3,
           sliver_m=SLIVER_M):
    """Did the cavity leave the blank? `(verdict, why)`.

    The question is asked by cutting the blank out of the cavity: whatever is left is cavity that
    is not inside the blank, so a contained cavity leaves nothing.

    **Volume alone cannot answer it, and this project has already paid for learning that.**
    IP-FC-137's near-tangency sliver read **0.000000 mm3** and so passed a volume-only check,
    while being a genuine invalid five-face shape occupying a ten-micron bounding box. A residue
    with real topology and no measurable volume is the signature of a near-tangency, which is the
    most interesting answer this measurement can return -- so it is reported as `sliver`, never
    folded into `contained`.

    **`pieces` is any topology the cut left, not its solid count**, and that distinction is the
    same finding read twice: the sliver that defeated the volume check was five *faces* and not a
    valid solid, so a caller counting `len(shape.Solids)` would hand this function a zero and be
    told `contained` -- reintroducing the exact blind spot by a different route. A caller counts
    solids where there are solids and faces where there are not.

    The verdicts: `contained` when there is no residue at all; `escaped` when its volume is above
    `tol`, which is material outside the blank; `sliver` when pieces exist but hold no measurable
    volume; and `invalid` when the residue's own topology is broken, which is reported ahead of
    the volume because a figure measured on an invalid shape is not a figure.
    """
    if not pieces:
        return CONTAINED, 'the cut left no topology at all'
    # **The arithmetic is SI and only the message is millimeters.** A refusal is read by a person
    # against a kernel log, so the figures it quotes stay in the units that log prints -- which
    # `doc/guidelines/general.md` places at the display boundary, not the storage one.
    volume_mm3 = volume_m3 * units.MM3_PER_M3
    if valid is False:
        return INVALID, ('%d piece(s) at %.6f mm3, and the residue is not a valid shape -- its '
                         'volume is not a figure to read' % (pieces, volume_mm3))
    if volume_m3 > tol_m3:
        return ESCAPED, ('%d piece(s) totalling %.6f mm3 of cavity outside the blank'
                         % (pieces, volume_mm3))
    narrow = span_m is not None and span_m <= sliver_m
    return SLIVER, ('%d piece(s) with %.6f mm3 between them, under the %.1e mm3 floor%s -- real '
                    'topology with no measurable volume is a near-tangency, not an empty cut'
                    % (pieces, volume_mm3, tol_m3 * units.MM3_PER_M3,
                       '' if span_m is None else ', %.6f mm across%s'
                       % (units.m_to_mm(span_m), ' (sliver scale)' if narrow else '')))


def _safe(text):
    """One path component, with anything that would make it more than one removed."""
    out = str(text)
    for bad in (os.sep, os.altsep, '/', '\\', ':'):
        if bad:
            out = out.replace(bad, '_')
    return out.strip() or 'unnamed'


def shape_of(exc):
    """The shape an exception carries, or `None`.

    **`getattr`, not `exc.shape`**, because most things raised here do not carry one:
    `PreconditionFailed` never does, an `Unconverged` from a site that has no single shape in
    scope does not, and a caller's `except` clause catches several types at once. An
    `AttributeError` from the diagnosis path would be the worst possible outcome -- see the module
    note.
    """
    return getattr(exc, 'shape', None)


def station_of(exc):
    """The station a refusal's worst reading was at, or `None` when it is not about one."""
    z = getattr(exc, 'z', None)
    return None if z is None else float(z)


def artifact_name(kind, u, z=None, delta=None, tag=None, ext=EXT):
    """The file name for one refusal's shape.

    Every part is optional except the kind and `u`, and an absent part is left out rather than
    rendered: `'%.4f' % None` raises, and a name containing the word `None` reads as a station
    called None rather than as a refusal that had no station. `u` is `%g`, so `U3` and not
    `U3.0`, matching every other artifact this package writes.

    `z` is carried at four decimals, which is what the round note and the `Unconverged` message
    print, so a file can be matched to the line in the log that produced it by eye.
    """
    parts = ['%s_U%g' % (_safe(kind), u)]
    if delta is not None:
        parts.append('_d%g' % delta)
    if z is not None:
        parts.append('_z%.4f' % z)
    if tag is not None:
        parts.append('_%s' % _safe(tag))
    return ''.join(parts) + '.' + _safe(ext)


def save(exc, out_dir, kind, u, export, delta=None, tag=None, dirname=DIRNAME):
    """Write the shape `exc` carries. Returns `None` when it carries none, else a record.

    The record is `path`, `z`, `bytes` where the written file could be measured, and `error` when
    the export itself failed -- a string, never a raised exception, because this runs inside the
    caller's `except` block.

    `export` is called as `export(shape, path)`. Anything it raises is caught and recorded: a
    28 MB write to a network path is a real thing to fail, and a refusal that also cannot be
    written down is still a refusal worth reporting.
    """
    shape = shape_of(exc)
    if shape is None:
        return None
    z = station_of(exc)
    folder = os.path.join(out_dir, _safe(dirname)) if dirname else out_dir
    path = os.path.join(folder, artifact_name(kind, u, z=z, delta=delta, tag=tag))
    rec = {'path': path, 'z': z}
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        export(shape, path)
    except Exception as exc_save:                                     # noqa: BLE001
        rec['error'] = '%s: %s' % (type(exc_save).__name__, str(exc_save)[:160])
        return rec
    try:
        rec['bytes'] = os.path.getsize(path)
    except OSError:
        # A stub exporter writes nothing, and a size that cannot be read is not a failure to
        # save -- the export itself reported success. Left absent rather than guessed.
        pass
    return rec
