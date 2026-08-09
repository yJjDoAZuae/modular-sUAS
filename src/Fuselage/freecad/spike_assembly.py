"""IP-FC-35: can the Assembly workbench be driven from `freecadcmd`, with no GUI?

IP-FC-19 wants assemblies built from parameters, solved, and then *checked* -- each solved
placement asserted against the placement the parameters say it should have. That is only
worth planning if the whole loop runs headless, because the sweep is a batch process and a
step that needs a window is a step that cannot be in it.

The parts of the loop that have to work, and none of them are obvious from the workbench's
documentation, which is written for the GUI:

    1. import Assembly at all -- it is a Mod/, not a lib/, and it pulls in coin and Qt
    2. create Assembly::AssemblyObject and put parts in it
    3. create joints without the task dialog that normally creates them
    4. solve, and have the solver actually move something
    5. read the solved placement back as data

Run:

    freecadcmd spike_assembly.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import is_entry_point

V = App.Vector

# The check is that the two mated faces end up coincident, measured on the solved shapes in
# global coordinates. Asserting a specific placement instead would be asserting whichever
# number came out, and would also bake in the solver's choice of which way to flip the
# joint -- neither of which is the thing IP-FC-19 needs to know.
TOLERANCE = 1e-6
COINCIDENT = 1e-4


def _joint(doc, assembly, name, kind, ref1, ref2):
    """A joint, built the way the task dialog builds one but without the dialog.

    `JointObject.Joint` is a proxy class -- it attaches to a plain App::FeaturePython and
    adds the properties itself, so nothing here needs a ViewProvider. The GUI only ever
    supplies the two references and the type, which is exactly what this passes.

    **The object has to be created *inside* the assembly**, via `assembly.newObject`, not
    added to it afterwards. `Joint.__init__` ends by calling `setJointConnectors`, which
    walks up to the owning assembly to decide what the references mean; created loose, that
    walk returns None and the constructor dies on `'NoneType' object has no attribute
    'Type'` -- an error that names neither the joint nor the assembly. The GUI never hits
    this because its command creates the object in the assembly to begin with.
    """
    import JointObject

    joint = assembly.newObject('App::FeaturePython', name)
    JointObject.Joint(joint, JointObject.JointTypes.index(kind))

    # **Both references go in through setJointConnectors, and assigning them directly does
    # not work.** Reference1/Reference2 accept the assignment and read back correctly, but
    # the joint coordinate systems -- Placement1 and Placement2, which are what the solver
    # actually constrains -- stay at the identity, so the solve converges immediately having
    # been asked for nothing. Worse, `setJointConnectors(joint, [])` *clears* both
    # references, which is how the constructor initialises them, so calling it afterwards to
    # "refresh" the placements silently undoes the assignment. Passing the pair is the whole
    # operation: it sets the references, derives each placement with findPlacement, and
    # solves.
    joint.Proxy.setJointConnectors(joint, [ref1, ref2])
    return joint


def _ground(doc, assembly, part):
    """Fix one part, or the solver has nothing to solve against and everything is free."""
    import JointObject

    grounded = assembly.newObject('App::FeaturePython', 'Ground_' + part.Name)
    JointObject.GroundedJoint(grounded, part)
    return grounded


def build(doc):
    assembly = doc.addObject('Assembly::AssemblyObject', 'Assembly')

    a = doc.addObject('Part::Box', 'BoxA')
    b = doc.addObject('Part::Box', 'BoxB')
    for box in (a, b):
        box.Length, box.Width, box.Height = 10, 10, 10
        assembly.addObject(box)

    # Displaced on purpose. A solver that does nothing would leave it here, and a test whose
    # parts already start in the answer cannot tell "solved" from "not solved".
    b.Placement = App.Placement(V(40, 25, -7), App.Rotation(V(0, 0, 1), 30))

    doc.recompute()

    _ground(doc, assembly, a)
    # **Two entries in the sub list, not one.** findPlacement reads ref[1][0] as the element
    # and ref[1][1] as the point on it -- the GUI's click. With one entry the second read
    # comes back empty, the function falls through to its whole-part branch and returns the
    # identity placement, so both joint coordinate systems sit at the part origins. The
    # solve then succeeds, reports convergence, and mates the two origins: a wrong answer
    # that looks exactly like a right one. Naming the face twice selects its centre of
    # gravity, which is what a scripted assembly wants, having no click to offer.
    #
    # Referenced as (part, [...]) and not (assembly, ['BoxA.Face2', ...]). The path form
    # assigns and reads back fine, but it makes a joint *inside* the assembly depend on the
    # assembly -- "The graph must be a DAG", and the joint stays touched after every
    # recompute. The path form is for reaching into a nested sub-assembly.
    _joint(doc, assembly, 'FixA_B', 'Fixed',
           (a, ['Face2', 'Face2']),       # +x face of the grounded box, at its centre
           (b, ['Face1', 'Face1']))       # -x face of the free box
    doc.recompute()
    return assembly, a, b


def _face_centre(part, index):
    """A face's centre in assembly coordinates -- the shape's own, with its placement on."""
    return part.Shape.Faces[index].CenterOfGravity


def main():
    doc = App.newDocument('spike_assembly')

    # `build` places BoxB away from the answer and the joint solves during construction, so
    # the displaced position has to be read before that: setJointConnectors solves as its
    # last step when the joint is in an assembly.
    start = App.Placement(V(40, 25, -7), App.Rotation(V(0, 0, 1), 30))
    assembly, a, b = build(doc)

    after_build = App.Vector(b.Placement.Base)
    result = assembly.solve()
    doc.recompute()
    after = b.Placement.Base

    mated_a = _face_centre(a, 1)       # Face2
    mated_b = _face_centre(b, 0)       # Face1
    gap = (mated_a - mated_b).Length

    print('SPIKE:: Assembly under freecadcmd')
    print('  solve() returned    %r' % (result,))
    print('  BoxA placement      %s  (grounded)' % (a.Placement.Base,))
    print('  BoxB placed at      %s' % (start.Base,))
    print('  BoxB after build    %s  (setJointConnectors solves)' % (after_build,))
    print('  BoxB after solve    %s' % (after,))
    print('  mated face centres  %s  and  %s' % (mated_a, mated_b))
    print('  gap between them    %.9f mm' % gap)

    fail = []
    if (after_build - start.Base).Length < TOLERANCE:
        fail.append('the solver did not move anything -- joints are not being applied')
    if gap > COINCIDENT:
        fail.append('mated faces are %.6f mm apart, so the joint coordinate systems are '
                    'not on the faces' % gap)
    if (after - after_build).Length > TOLERANCE:
        fail.append('an explicit solve() moved a part the build had already settled -- '
                    'the solve is not idempotent')

    # The point of the whole spike for IP-FC-19: the solved result has to come back as
    # data. A placement that reads back is one an assertion can compare against the
    # placement the parameters predict.
    readback = doc.getObject(b.Name).Placement
    if readback.Base != after:
        fail.append('placement does not read back from the document')

    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok -- headless assembly works'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
