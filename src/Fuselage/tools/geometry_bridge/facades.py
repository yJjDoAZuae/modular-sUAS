"""Typed facades -- hand-written classes with real signatures, delegating to a `Remote`.

A proxy forwards attributes dynamically, so an editor cannot complete ``shape.`` and a type
checker cannot catch ``shape.Volum``. These classes recover that for the types the project
actually uses. **The set is not a guess**: it is the survey in
doc/architecture/geometry_bridge.md section 4.10, which asked FreeCAD for each candidate's public
members, counted every attribute access in the 101 modules under `src/Fuselage/freecad`, and
intersected the two. Five types carry 90.5% of unambiguous member use.

**Written out longhand on purpose.** Generating these delegators in a loop would be shorter and
would reproduce the exact problem they exist to solve: a name created by ``setattr`` is invisible
to an editor and to a type checker, which is the proxy's own limitation with extra machinery
attached. The value here *is* the static text, so the static text is what gets written.

Four things this module's shape comes from, each a measurement rather than a preference:

**One shared `Shape`, not one facade per shape type.** `Shape` and `Solid` have **zero**
unambiguous member uses -- every member they expose is shared across the `Part.Shape` subclasses,
because that is what they are. 137 of the members are common to all six of `Shape`, `Solid`,
`Face`, `Edge`, `Wire` and `Vertex`. So the shared surface lives in one place and the subtypes add
only what is genuinely theirs: `Face.Surface`, `Edge.split`, `Vertex.Point`, `Wire.OrderedEdges`.

**`Vertex` branches off the shared base, because `CenterOfMass` is the one member that breaks the
hierarchy.** Of every member this module declares, exactly one -- `CenterOfMass` -- is on `Shape`,
`Solid`, `Face`, `Edge` and `Wire` but *not* on `Vertex`. Measured, not assumed. So `ShapeCommon`
carries what all six have, `Shape` adds `CenterOfMass`, and `Vertex` extends `ShapeCommon`
directly. A flat hierarchy would have had `Vertex` advertising a member it does not have, which is
the precise failure mode section 5.6 calls worse than no facade at all: it type-checks, then
raises at run time.

**Facade lookup walks the class chain, never the leaf type name.** A `Part::Box` document object
reports its type as ``PrimitivePy``; ``DocumentObject`` is four classes up its MRO. Keying on the
leaf name would have faceted everything except `DocumentObject`, the single most-used type in the
project at 361 uses -- and silently, since an unmatched type falls back to the working proxy. See
`ops.base_names`.

**The document side dominates, not the geometry side.** The top three by unambiguous use are
`DocumentObject` (361), `Vector` (317) and `Document` (241), and `setExpression` alone accounts
for 93. This project's FreeCAD code is parametric-document driven.

Coverage is deliberately uneven. A type outside this set keeps the dynamic proxy, which always
works and offers no completion; that fallback is what keeps the set small enough to be worth
writing. `tests/test_geometry_bridge_facades.py` checks every member declared here against a live
vendor object, so drift is caught by the suite rather than by a confused reader.

See doc/architecture/geometry_bridge.md sections 4.10 and 5.6.
"""
from .proxy import Remote

#: Attributes belonging to the facade itself rather than to the vendor object.
_OWN = frozenset(('_r',))


def unwrap(obj):
    """A facade's proxy, a proxy as-is, a container's elements unwrapped, anything else untouched.

    Called on every argument crossing out, so a facade can be passed wherever a proxy can:
    ``solid.cut(other_facade)`` has to work, since the whole point is to write ordinary Python.
    """
    if isinstance(obj, (Facade, RemoteSequence)):
        return obj._r
    if isinstance(obj, (list, tuple)):
        kind = type(obj)
        return kind(unwrap(x) for x in obj)
    return obj


#: Vendor-side container types. A member like `Shape.Faces` is a Python list of vendor objects,
#: which cannot cross as a value, so it arrives as a handle *to the list*.
_CONTAINER_NAMES = ('list', 'tuple')


def wrap(obj):
    """Put a facade around a proxy when one exists; pass values and unfaceted types through.

    Applied to every result coming back, so chains stay typed: ``shape.BoundBox.ZMin`` goes
    `Shape` facade to `BoundBox` facade to float without the caller doing anything.

    **A remote container becomes a `RemoteSequence`, not a materialized list.** ``shape.Faces``
    is a handle to a list, and the obvious implementation -- read every element and wrap it --
    would allocate a handle per face the moment the attribute is touched. On a tail cowl shell
    that is thousands of handles for a caller who wanted ``len()``. The sequence wrapper keeps the
    read lazy and still wraps what comes out of it.
    """
    if isinstance(obj, Remote):
        if obj.remote_isinstance(*_CONTAINER_NAMES):
            return RemoteSequence(obj)
        cls = facade_for(obj)
        return obj if cls is None else cls(obj)
    if isinstance(obj, list):
        return [wrap(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(wrap(x) for x in obj)
    return obj


def facade_for(remote):
    """The facade class for a proxy, found by walking its class chain. `None` if none fits."""
    for name in remote.remote_bases:
        cls = BY_VENDOR_NAME.get(name)
        if cls is not None:
            return cls
    return BY_VENDOR_NAME.get(remote.remote_type)


class RemoteSequence(object):
    """A vendor-side list or tuple, read lazily, with every element wrapped on its way out.

    ``shape.Faces`` is a handle to a list. Indexing, iterating and ``len`` each forward to the
    vendor, and what comes back is faceted, so ``shape.Faces[0].OuterWire`` is typed the whole
    way. Nothing is read until asked for: materializing the list on attribute access would
    allocate a handle per element for a caller who may only want its length.
    """

    __slots__ = ('_r',)

    def __init__(self, remote):
        self._r = remote

    @property
    def remote(self):
        """The `Remote` for the container itself."""
        return self._r

    def __repr__(self):
        return '<RemoteSequence %r>' % (self._r,)

    def __len__(self):
        return len(self._r)

    def __getitem__(self, index):
        return wrap(self._r[index])

    def __iter__(self):
        """One round trip for the whole sequence, not one per element."""
        return iter(wrap(x) for x in self._r.items())

    def __bool__(self):
        """Empty vendor lists are common -- ``if shape.Solids:`` must mean what it reads as."""
        return len(self._r) > 0

    def items(self):
        """Every element, faceted, in one round trip."""
        return [wrap(x) for x in self._r.items()]

    def project(self, *paths):
        """Read the same attribute paths from every element, in one round trip.

        ``shape.Vertexes.project('X', 'Y', 'Z')`` costs one trip where the loop costs 3n.
        """
        return self._r.project(*paths)


class Facade(object):
    """Base for every facade: holds one proxy, delegates what it does not declare."""

    __slots__ = ('_r',)

    #: Vendor class names this facade stands for, in the form `ops.base_names` reports them. The
    #: drift test uses the first as the type to build and check against.
    VENDOR = ()

    def __init__(self, remote):
        if not isinstance(remote, Remote):
            raise TypeError('%s wraps a Remote, got %r' % (type(self).__name__, type(remote)))
        object.__setattr__(self, '_r', remote)

    # -- the proxy underneath

    @property
    def remote(self):
        """The `Remote` this facade delegates to, for the operations only a proxy has."""
        return self._r

    @property
    def remote_type(self):
        """The vendor-side leaf type name."""
        return self._r.remote_type

    def __repr__(self):
        return '<%s %r>' % (type(self).__name__, self._r)

    def __bool__(self):
        """Always true, matching `Remote`: a facade references a real object."""
        return True

    #: Unhashable, matching `Remote`, and for the same reason.
    __hash__ = None

    # -- fallback

    def __getattr__(self, name):
        """Anything not declared above goes to the proxy, untyped but working.

        Only reached for names the facade does not define, since a declared property or method is
        found by the descriptor protocol first.
        """
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        return wrap(getattr(self._r, name))

    def __setattr__(self, name, value):
        if name in _OWN:
            object.__setattr__(self, name, value)
            return
        setattr(self._r, name, unwrap(value))

    def __eq__(self, other):
        return self._r == unwrap(other)

    def __ne__(self, other):
        return self._r != unwrap(other)


# ---------------------------------------------------------------------------------------------
# 1. DocumentObject -- 361 unambiguous uses, the most-used type in the project
# ---------------------------------------------------------------------------------------------

class DocumentObject(Facade):
    """A document object: `Part::Box`, `App::FeaturePython`, a sketch, a cowl feature.

    **Run-time properties are the normal case here, not an edge case.** `addProperty` means two
    objects of the same vendor type can carry different attributes, which is why the worker, not
    the client, decides whether an attribute read may be cached (`ops.default_is_dynamic`). The
    facade therefore declares the members every document object has; a parametric property added
    at run time -- `obj.unit_width` on a cowl feature -- arrives through the proxy fallback, which
    is the right answer for a name that does not exist until the document is built.
    """

    VENDOR = ('DocumentObject',)

    # -- attributes

    @property
    def Shape(self):
        """The object's computed shape. 195 uses, the single most-used member in the survey."""
        return wrap(self._r.Shape)

    @property
    def Name(self):
        """The object's immutable internal name, unique within its document."""
        return self._r.Name

    @property
    def Label(self):
        """The object's user-visible, editable label."""
        return self._r.Label

    @property
    def Placement(self):
        """The object's placement."""
        return wrap(self._r.Placement)

    @Placement.setter
    def Placement(self, value):
        setattr(self._r, 'Placement', unwrap(value))

    @property
    def Document(self):
        """The document this object belongs to."""
        return wrap(self._r.Document)

    @property
    def State(self):
        """The object's state flags, e.g. ``['Touched']`` or ``['Invalid']``."""
        return self._r.State

    @property
    def TypeId(self):
        """The vendor type id, e.g. ``'Part::Box'``."""
        return self._r.TypeId

    @property
    def Visibility(self):
        """Whether the object is visible. Writable."""
        return self._r.Visibility

    @Visibility.setter
    def Visibility(self, value):
        setattr(self._r, 'Visibility', value)

    @property
    def ExpressionEngine(self):
        """The object's bound expressions, as ``(property, expression)`` pairs."""
        return self._r.ExpressionEngine

    @property
    def InList(self):
        """The objects that depend on this one."""
        return wrap(self._r.InList)

    @property
    def OutList(self):
        """The objects this one depends on."""
        return wrap(self._r.OutList)

    @property
    def PropertiesList(self):
        """Every property name this object carries, including those added at run time."""
        return self._r.PropertiesList

    # Dimension properties. Quantities, not floats -- `.Value` gives the number.

    @property
    def Length(self):
        """A length property, as a `Quantity`. 33 uses."""
        return wrap(self._r.Length)

    @Length.setter
    def Length(self, value):
        setattr(self._r, 'Length', unwrap(value))

    @property
    def Width(self):
        """A width property, as a `Quantity`."""
        return wrap(self._r.Width)

    @Width.setter
    def Width(self, value):
        setattr(self._r, 'Width', unwrap(value))

    @property
    def Height(self):
        """A height property, as a `Quantity`. 19 uses."""
        return wrap(self._r.Height)

    @Height.setter
    def Height(self, value):
        setattr(self._r, 'Height', unwrap(value))

    @property
    def MapMode(self):
        """The attachment map mode."""
        return self._r.MapMode

    @MapMode.setter
    def MapMode(self, value):
        setattr(self._r, 'MapMode', value)

    @property
    def AttachmentSupport(self):
        """The attachment's support references."""
        return wrap(self._r.AttachmentSupport)

    @property
    def AttachmentOffset(self):
        """The attachment's offset placement."""
        return wrap(self._r.AttachmentOffset)

    # -- methods

    def setExpression(self, path, expression):
        """Bind `path` to `expression`, or clear it with `None`. 93 uses -- the second-most-used
        unambiguous member in the whole survey, and the reason `setattr` is a protocol operation.
        """
        return wrap(self._r.setExpression(path, expression))

    def recompute(self, recursive=False):
        """Recompute this object. 170 uses across `DocumentObject` and `Document`."""
        return wrap(self._r.recompute(recursive))

    def isValid(self):
        """Is the object valid?"""
        return self._r.isValid()

    def isDerivedFrom(self, type_name):
        """Is the object's type `type_name` or a descendant of it?"""
        return self._r.isDerivedFrom(type_name)

    def touch(self):
        """Mark the object as changed, so the next recompute includes it."""
        return wrap(self._r.touch())

    def addProperty(self, type_name, name, group='', doc='', attr=0, read_only=False,
                    hidden=False, locked=False, enum_vals=None):
        """Add a run-time property. What makes this type's attribute reads uncacheable."""
        if enum_vals is None:
            return wrap(self._r.addProperty(type_name, name, group, doc, attr, read_only,
                                            hidden, locked))
        return wrap(self._r.addProperty(type_name, name, group, doc, attr, read_only,
                                        hidden, locked, enum_vals))

    def getEnumerationsOfProperty(self, name):
        """The enumeration strings of an enum property, or `None` if it is not one."""
        return self._r.getEnumerationsOfProperty(name)


# ---------------------------------------------------------------------------------------------
# 2. Vector -- 317 unambiguous uses
# ---------------------------------------------------------------------------------------------

class Vector(Facade):
    """A 3-D vector. `x`, `y` and `z` alone account for 277 uses.

    **The in-place methods return the vector, and that is a vendor trap the facade does not
    hide.** `normalize`, `scale` and `multiply` mutate the receiver *and* return it, so
    ``b = a.normalize()`` leaves `a` normalized too. The facade forwards faithfully rather than
    copying, because silently differing from the vendor here would make a test that passes through
    the bridge disagree with the same code run in FreeCAD.
    """

    VENDOR = ('Vector',)

    @property
    def x(self):
        """The x component. 107 uses."""
        return self._r.x

    @x.setter
    def x(self, value):
        setattr(self._r, 'x', value)

    @property
    def y(self):
        """The y component. 101 uses."""
        return self._r.y

    @y.setter
    def y(self, value):
        setattr(self._r, 'y', value)

    @property
    def z(self):
        """The z component. 70 uses."""
        return self._r.z

    @z.setter
    def z(self, value):
        setattr(self._r, 'z', value)

    @property
    def Length(self):
        """The vector's magnitude."""
        return self._r.Length

    def normalize(self):
        """Normalize **in place** to unit length, and return self."""
        return wrap(self._r.normalize())

    def dot(self, other):
        """The scalar product with `other`."""
        return self._r.dot(unwrap(other))

    def cross(self, other):
        """The vector product with `other`."""
        return wrap(self._r.cross(unwrap(other)))

    def add(self, other):
        """The sum of this vector and `other`, as a new vector."""
        return wrap(self._r.add(unwrap(other)))

    def sub(self, other):
        """The difference of this vector and `other`, as a new vector."""
        return wrap(self._r.sub(unwrap(other)))

    def scale(self, x, y, z):
        """Scale **in place**, per component, and return self."""
        return wrap(self._r.scale(x, y, z))

    def multiply(self, factor):
        """Multiply every component **in place** by `factor`, and return self."""
        return wrap(self._r.multiply(factor))

    def negative(self):
        """The opposite vector, as a new vector."""
        return wrap(self._r.negative())

    def distanceToPoint(self, point):
        """The distance to `point`."""
        return self._r.distanceToPoint(unwrap(point))


# ---------------------------------------------------------------------------------------------
# 3. Document -- 241 unambiguous uses
# ---------------------------------------------------------------------------------------------

class Document(Facade):
    """An open FreeCAD document."""

    VENDOR = ('Document',)

    @property
    def Name(self):
        """The document's internal name."""
        return self._r.Name

    @property
    def Label(self):
        """The document's user-visible label."""
        return self._r.Label

    @property
    def Objects(self):
        """Every object in the document. 35 uses."""
        return wrap(self._r.Objects)

    @property
    def FileName(self):
        """The path the document was loaded from or last saved to."""
        return self._r.FileName

    @property
    def Tip(self):
        """The document's tip object, or `None`."""
        return wrap(self._r.Tip)

    @property
    def TypeId(self):
        """The document's vendor type id."""
        return self._r.TypeId

    @property
    def InList(self):
        """Documents that depend on this one."""
        return wrap(self._r.InList)

    def addObject(self, type_name, name=None, obj_proxy=None, view_proxy=None, attach=False,
                  view_type=None):
        """Add an object of `type_name`. 95 uses -- the most-used `Document` member."""
        if name is None:
            return wrap(self._r.addObject(type_name))
        return wrap(self._r.addObject(type_name, name))

    def getObject(self, name):
        """The object with internal name `name`, or `None`. 76 uses."""
        return wrap(self._r.getObject(name))

    def removeObject(self, name):
        """Remove the object with internal name `name`."""
        return wrap(self._r.removeObject(name))

    def recompute(self, objs=None):
        """Recompute the document, returning how many features were recomputed."""
        if objs is None:
            return wrap(self._r.recompute())
        return wrap(self._r.recompute(unwrap(objs)))

    def save(self):
        """Save the document to its existing path."""
        return wrap(self._r.save())

    def saveAs(self, path):
        """Save the document to `path`, which becomes its path."""
        return wrap(self._r.saveAs(path))

    def load(self, path):
        """Load a document from `path`."""
        return wrap(self._r.load(path))

    def isDerivedFrom(self, type_name):
        """Is the document's type `type_name` or a descendant?"""
        return self._r.isDerivedFrom(type_name)

    def addProperty(self, type_name, name, group='', doc='', attr=0, read_only=False,
                    hidden=False, locked=False):
        """Add a run-time property to the document itself."""
        return wrap(self._r.addProperty(type_name, name, group, doc, attr, read_only,
                                        hidden, locked))

    def getEnumerationsOfProperty(self, name):
        """The enumeration strings of an enum property, or `None`."""
        return self._r.getEnumerationsOfProperty(name)


# ---------------------------------------------------------------------------------------------
# 4. BoundBox -- 184 unambiguous uses
# ---------------------------------------------------------------------------------------------

class BoundBox(Facade):
    """An axis-aligned bounding box.

    The project reads `ZMin` and `ZMax` more than any other members here, because the cowl work is
    station-based along z.
    """

    VENDOR = ('BoundBox',)

    @property
    def XMin(self):
        """The minimum x. 27 uses."""
        return self._r.XMin

    @property
    def XMax(self):
        """The maximum x. 26 uses."""
        return self._r.XMax

    @property
    def YMin(self):
        """The minimum y. 22 uses."""
        return self._r.YMin

    @property
    def YMax(self):
        """The maximum y. 23 uses."""
        return self._r.YMax

    @property
    def ZMin(self):
        """The minimum z. 37 uses, the most-used member of this type."""
        return self._r.ZMin

    @property
    def ZMax(self):
        """The maximum z. 31 uses."""
        return self._r.ZMax

    @property
    def XLength(self):
        """The extent in x."""
        return self._r.XLength

    @property
    def YLength(self):
        """The extent in y."""
        return self._r.YLength

    @property
    def ZLength(self):
        """The extent in z."""
        return self._r.ZLength

    @property
    def Center(self):
        """The box's center, as a `Vector`."""
        return wrap(self._r.Center)

    @property
    def DiagonalLength(self):
        """The length of the box's space diagonal."""
        return self._r.DiagonalLength

    def isValid(self):
        """Is the box valid? An empty or uninitialized box is not."""
        return self._r.isValid()

    def isInside(self, other):
        """Is `other` -- a point or another box -- inside this box?"""
        return self._r.isInside(unwrap(other))

    def add(self, other):
        """Enlarge this box **in place** to contain `other`."""
        return wrap(self._r.add(unwrap(other)))

    def scale(self, x, y, z):
        """Scale the box **in place**, per component."""
        return wrap(self._r.scale(x, y, z))

    def enlarge(self, amount):
        """Grow the box **in place** by `amount` on every side."""
        return wrap(self._r.enlarge(amount))


# ---------------------------------------------------------------------------------------------
# 5. Placement -- 139 unambiguous uses
# ---------------------------------------------------------------------------------------------

class Placement(Facade):
    """A rigid-body placement: a translation and a rotation. `Base` alone is 103 uses."""

    VENDOR = ('Placement',)

    @property
    def Base(self):
        """The translation, as a `Vector`. 103 uses."""
        return wrap(self._r.Base)

    @Base.setter
    def Base(self, value):
        setattr(self._r, 'Base', unwrap(value))

    @property
    def Rotation(self):
        """The rotation. 36 uses. No facade: `Rotation` has no unambiguous uses in the survey."""
        return wrap(self._r.Rotation)

    @Rotation.setter
    def Rotation(self, value):
        setattr(self._r, 'Rotation', unwrap(value))

    @property
    def Matrix(self):
        """The placement as a 4x4 matrix."""
        return wrap(self._r.Matrix)

    @property
    def isNull(self):
        """Is this the identity placement? A property on `Placement`, not a method."""
        return self._r.isNull

    def copy(self):
        """A copy of this placement."""
        return wrap(self._r.copy())

    def multiply(self, other):
        """This placement right-multiplied by `other`."""
        return wrap(self._r.multiply(unwrap(other)))

    def translate(self, vector):
        """Translate **in place** by `vector`."""
        return wrap(self._r.translate(unwrap(vector)))

    def rotate(self, center, axis, angle, comp=False):
        """Rotate **in place** about `axis` through `center` by `angle` degrees."""
        return wrap(self._r.rotate(unwrap(center), unwrap(axis), angle, comp))

    def inverse(self):
        """The inverse placement."""
        return wrap(self._r.inverse())


# ---------------------------------------------------------------------------------------------
# 6. The shape kin -- zero unambiguous uses apiece, 137 members shared, so one base
# ---------------------------------------------------------------------------------------------

class ShapeCommon(Facade):
    """The surface every `Part.Shape` subclass carries, `Vertex` included.

    Membership here was measured, not assumed: these are members present on all six of `Shape`,
    `Solid`, `Face`, `Edge`, `Wire` and `Vertex`. The one used member that is *not* --
    `CenterOfMass`, absent from `Vertex` -- lives on `Shape` below instead.
    """

    VENDOR = ('Shape',)

    # -- measurements

    @property
    def Volume(self):
        """The enclosed volume. 181 uses, the most-used member in the project.

        **On this project's B-spline solids it is wrong by 0.16 to 0.24%**, which is the same
        order as differences the reproducibility work exists to detect, so volume comparisons go
        through a refined tessellation instead -- `solid_measure.mesh_volume`. Declared here
        because the vendor has it and the facade must not pretend otherwise.
        """
        return self._r.Volume

    @property
    def Area(self):
        """The total surface area.

        **`Face.Area` reads 23% off on this project's B-spline faces**; the wire's signed area is
        what the project uses there.
        """
        return self._r.Area

    @property
    def Length(self):
        """The total length of the shape's edges."""
        return self._r.Length

    @property
    def BoundBox(self):
        """The axis-aligned bounding box. 65 uses."""
        return wrap(self._r.BoundBox)

    @property
    def Placement(self):
        """The shape's placement."""
        return wrap(self._r.Placement)

    @Placement.setter
    def Placement(self, value):
        setattr(self._r, 'Placement', unwrap(value))

    @property
    def Orientation(self):
        """``'Forward'`` or ``'Reversed'``."""
        return self._r.Orientation

    @property
    def TypeId(self):
        """The vendor type id, e.g. ``'Part::TopoShape'``."""
        return self._r.TypeId

    @property
    def ShapeType(self):
        """``'Solid'``, ``'Face'``, ``'Edge'``, ``'Wire'``, ``'Vertex'``, ``'Shell'``, …"""
        return self._r.ShapeType

    # -- sub-shapes

    @property
    def Solids(self):
        """The solids, as a list. 116 uses -- usually to assert there is exactly one."""
        return wrap(self._r.Solids)

    @property
    def Shells(self):
        """The shells, as a list."""
        return wrap(self._r.Shells)

    @property
    def Faces(self):
        """The faces, as a list. 81 uses."""
        return wrap(self._r.Faces)

    @property
    def Wires(self):
        """The wires, as a list."""
        return wrap(self._r.Wires)

    @property
    def Edges(self):
        """The edges, as a list."""
        return wrap(self._r.Edges)

    @property
    def Vertexes(self):
        """The vertices, as a list.

        Reading coordinates one at a time costs a round trip each; `Remote.project` reads them in
        one -- ``shape.remote.Vertexes.project('X', 'Y', 'Z')``.
        """
        return wrap(self._r.Vertexes)

    # -- predicates

    def isValid(self):
        """Is the shape neither null, empty, nor corrupt? 96 uses."""
        return self._r.isValid()

    def isNull(self):
        """Is the shape null?"""
        return self._r.isNull()

    def isClosed(self):
        """Is the shape closed?"""
        return self._r.isClosed()

    def isInside(self, point, tolerance, check_face):
        """Is `point` inside the shape, within `tolerance`?"""
        return self._r.isInside(unwrap(point), tolerance, check_face)

    def isDerivedFrom(self, type_name):
        """Is the shape's type `type_name` or a descendant?"""
        return self._r.isDerivedFrom(type_name)

    def check(self, run_bop_check=False):
        """Check the shape's structure and report errors.

        ``check(True)`` is what finds the invalid-sub-shape orientation defects the cowl
        investigation turned up; a volume check alone passes them.
        """
        return wrap(self._r.check(run_bop_check))

    # -- booleans

    def cut(self, tool):
        """This shape minus `tool`. 40 uses."""
        return wrap(self._r.cut(unwrap(tool)))

    def fuse(self, tool):
        """The union of this shape and `tool`."""
        return wrap(self._r.fuse(unwrap(tool)))

    def common(self, tool):
        """The intersection of this shape and `tool`."""
        return wrap(self._r.common(unwrap(tool)))

    def section(self, tool, approximation=False):
        """The section of this shape against `tool`."""
        return wrap(self._r.section(unwrap(tool), approximation))

    def multiFuse(self, tools, tolerance=0.0):
        """The union of this shape and every shape in `tools`."""
        return wrap(self._r.multiFuse(unwrap(tools), tolerance))

    def slice(self, direction, distance):
        """The wires where a plane at `distance` along `direction` cuts this shape."""
        return wrap(self._r.slice(unwrap(direction), distance))

    def removeSplitter(self):
        """A copy with redundant edges merged."""
        return wrap(self._r.removeSplitter())

    # -- transforms

    def copy(self, copy_geom=True, copy_mesh=False):
        """A copy of this shape."""
        return wrap(self._r.copy(copy_geom, copy_mesh))

    def translate(self, vector):
        """Translate **in place** by `vector`."""
        return wrap(self._r.translate(unwrap(vector)))

    def translated(self, vector):
        """A new shape translated by `vector`."""
        return wrap(self._r.translated(unwrap(vector)))

    def rotate(self, base, direction, degrees):
        """Rotate **in place** about `direction` through `base` by `degrees`."""
        return wrap(self._r.rotate(unwrap(base), unwrap(direction), degrees))

    def scale(self, factor, base=None):
        """Scale **in place** by `factor` about `base`."""
        if base is None:
            return wrap(self._r.scale(factor))
        return wrap(self._r.scale(factor, unwrap(base)))

    def mirror(self, base, normal):
        """A new shape mirrored in the plane through `base` with normal `normal`."""
        return wrap(self._r.mirror(unwrap(base), unwrap(normal)))

    def reverse(self):
        """Reverse this shape's orientation **in place**."""
        return wrap(self._r.reverse())

    def reversed(self):
        """A copy with reversed orientation."""
        return wrap(self._r.reversed())

    # -- construction

    def extrude(self, vector):
        """Extrude this shape along `vector`."""
        return wrap(self._r.extrude(unwrap(vector)))

    def revolve(self, base, direction, angle):
        """Revolve this shape about `direction` through `base` by `angle` degrees."""
        return wrap(self._r.revolve(unwrap(base), unwrap(direction), angle))

    def makeOffset2D(self, offset, join=0, fill=False, open_result=False, intersection=False):
        """A 2-D offset of this shape. The erosion step of the cowl interior uses it."""
        return wrap(self._r.makeOffset2D(offset, join, fill, open_result, intersection))

    def makeOffsetShape(self, offset, tolerance, inter=False, self_inter=False, offset_mode=0,
                        join=0, fill=False):
        """A 3-D offset of this shape."""
        return wrap(self._r.makeOffsetShape(offset, tolerance, inter, self_inter, offset_mode,
                                            join, fill))

    def sewShape(self):
        """Sew this shape's faces **in place**, closing small gaps."""
        return wrap(self._r.sewShape())

    # -- measurement and export

    def distToShape(self, other):
        """``(distance, points, infos)`` -- the minimum distance to `other`.

        The instrument the project trusts for surface comparison, because it samples and never
        integrates, so an unpaired tessellation edge cannot corrupt it the way it corrupts a
        volume.
        """
        return wrap(self._r.distToShape(unwrap(other)))

    def tessellate(self, deflection):
        """``(vertices, facets)`` at `deflection`. How volume is really measured here."""
        return wrap(self._r.tessellate(deflection))

    def read(self, filename):
        """Read an IGES, STEP or BREP file into this shape."""
        return wrap(self._r.read(filename))

    def exportBrep(self, filename):
        """Write this shape to `filename` in BREP format."""
        return wrap(self._r.exportBrep(filename))

    def importBrep(self, filename):
        """Read this shape from a BREP file."""
        return wrap(self._r.importBrep(filename))

    def exportStep(self, filename):
        """Write this shape to `filename` in STEP format."""
        return wrap(self._r.exportStep(filename))

    def exportStl(self, filename):
        """Write this shape to `filename` as an STL mesh."""
        return wrap(self._r.exportStl(filename))

    def dumps(self):
        """This shape serialized to a BREP string."""
        return self._r.dumps()

    def loads(self, data):
        """Load this shape from a BREP string."""
        return wrap(self._r.loads(data))


class Shape(ShapeCommon):
    """A shape of any kind, and the facade for `Shell`, `Compound` and `CompSolid` too.

    Adds `CenterOfMass`, the one used member present on every shape type except `Vertex`.
    """

    VENDOR = ('Shape',)

    @property
    def CenterOfMass(self):
        """The center of mass, as a `Vector`. Not available on `Vertex`."""
        return wrap(self._r.CenterOfMass)

    @property
    def CenterOfGravity(self):
        """The center of gravity, as a `Vector`."""
        return wrap(self._r.CenterOfGravity)


class Solid(Shape):
    """A solid. Carries nothing of its own: it had zero unambiguous member uses in the survey."""

    VENDOR = ('Solid',)


class Face(Shape):
    """A face. `Surface` (26 uses) and `Wire` (12) are its own."""

    VENDOR = ('Face',)

    @property
    def Surface(self):
        """The underlying geometric surface -- `Plane`, `BSplineSurface`, `Cylinder`, …"""
        return wrap(self._r.Surface)

    @property
    def Wire(self):
        """The face's outer wire. FreeCAD's older spelling of `OuterWire`."""
        return wrap(self._r.Wire)

    @property
    def OuterWire(self):
        """The face's outer wire."""
        return wrap(self._r.OuterWire)

    @property
    def ParameterRange(self):
        """``(uMin, uMax, vMin, vMax)`` over the face's surface."""
        return self._r.ParameterRange

    def normalAt(self, u, v):
        """The surface normal at parameters `u`, `v`."""
        return wrap(self._r.normalAt(u, v))

    def valueAt(self, u, v):
        """The point at parameters `u`, `v`."""
        return wrap(self._r.valueAt(u, v))


class Edge(Shape):
    """An edge. `split` (29 uses) and `discretize` (27) are the ones that earn this class."""

    VENDOR = ('Edge',)

    @property
    def Curve(self):
        """The underlying geometric curve -- `Line`, `BSplineCurve`, `Circle`, …"""
        return wrap(self._r.Curve)

    @property
    def FirstParameter(self):
        """The curve parameter at the edge's start."""
        return self._r.FirstParameter

    @property
    def LastParameter(self):
        """The curve parameter at the edge's end."""
        return self._r.LastParameter

    @property
    def ParameterRange(self):
        """``(first, last)``."""
        return self._r.ParameterRange

    def split(self, parameter):
        """A wire made by splitting this edge at `parameter`."""
        return wrap(self._r.split(parameter))

    def discretize(self, number=None, **kwargs):
        """Points along this edge, by count or by one of the vendor's keyword modes."""
        if number is not None:
            return wrap(self._r.discretize(number))
        return wrap(self._r.discretize(**kwargs))

    def normalAt(self, parameter):
        """The normal direction at `parameter`, where defined."""
        return wrap(self._r.normalAt(parameter))

    def valueAt(self, parameter):
        """The point at `parameter`."""
        return wrap(self._r.valueAt(parameter))


class Wire(Shape):
    """A wire."""

    VENDOR = ('Wire',)

    @property
    def OrderedEdges(self):
        """The wire's edges in connection order, not in storage order."""
        return wrap(self._r.OrderedEdges)

    @property
    def OrderedVertexes(self):
        """The wire's vertices in connection order."""
        return wrap(self._r.OrderedVertexes)

    def discretize(self, number=None, **kwargs):
        """Points along this wire, by count or by one of the vendor's keyword modes."""
        if number is not None:
            return wrap(self._r.discretize(number))
        return wrap(self._r.discretize(**kwargs))

    def add(self, edge):
        """Add `edge` to this wire **in place**."""
        return wrap(self._r.add(unwrap(edge)))

    def approximate(self, tol2d=1e-6, tol3d=1e-4, max_segments=10, max_degree=3):
        """A B-spline curve approximating this wire."""
        return wrap(self._r.approximate(tol2d, tol3d, max_segments, max_degree))


class Vertex(ShapeCommon):
    """A vertex. **Extends `ShapeCommon`, not `Shape`, because it has no `CenterOfMass`.**

    That is the one place the vendor's shape hierarchy does not line up with a flat facade
    hierarchy, and it was found by checking all six types member by member rather than by
    assuming. Inheriting from `Shape` would have had this class advertise a member the vendor does
    not provide.
    """

    VENDOR = ('Vertex',)

    @property
    def Point(self):
        """The vertex position, as a `Vector`. 25 uses."""
        return wrap(self._r.Point)

    @property
    def X(self):
        """The x coordinate."""
        return self._r.X

    @property
    def Y(self):
        """The y coordinate."""
        return self._r.Y

    @property
    def Z(self):
        """The z coordinate."""
        return self._r.Z


#: Vendor class name to facade. Consulted along a proxy's whole class chain, leaf first, so a
#: `Part::Box` document object reporting `PrimitivePy` still finds `DocumentObject`.
#:
#: `Shell`, `Compound` and `CompSolid` are mapped to `Shape` deliberately: they are
#: `Part.Shape` subclasses with no members of their own in the survey, so the shared facade is
#: exactly right for them and a class each would be three empty classes.
BY_VENDOR_NAME = {
    'DocumentObject': DocumentObject,
    'Vector': Vector,
    'Document': Document,
    'BoundBox': BoundBox,
    'Placement': Placement,
    'Solid': Solid,
    'Face': Face,
    'Edge': Edge,
    'Wire': Wire,
    'Vertex': Vertex,
    'Shell': Shape,
    'Compound': Shape,
    'CompSolid': Shape,
    'Shape': Shape,
}

#: Every facade class, for the drift test to iterate.
ALL_FACADES = (DocumentObject, Vector, Document, BoundBox, Placement,
               Shape, Solid, Face, Edge, Wire, Vertex)


def declared_members(cls):
    """Every vendor member name `cls` declares, including inherited ones.

    Derived from the classes themselves rather than from a hand-kept list, so the drift test
    cannot pass by the list going stale alongside the code it checks.
    """
    out = set()
    for klass in cls.__mro__:
        if klass in (Facade, object):
            continue
        for name, value in vars(klass).items():
            if name.startswith('_') or name.isupper():
                continue
            if isinstance(value, (property, staticmethod, classmethod)) or callable(value):
                out.add(name)
    return out
