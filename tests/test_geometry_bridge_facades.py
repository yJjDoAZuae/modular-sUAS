"""IP-GB-17: the facade drift test, plus the facade mechanics that need no vendor.

A facade is a second surface over FreeCAD's API, and §5.6 names the hazard precisely: **a facade
that silently disagrees with the real object is worse than no facade**, because it type-checks and
then fails at run time. These tests are what make that a suite failure instead of a confused
reader.

Two tiers, for the reason the whole bridge exists:

* **No FreeCAD** -- `wrap`, `unwrap`, the lookup along the class chain, and the hierarchy facts
  the facades are built on. Milliseconds, no subprocess.
* **Real FreeCAD** -- every declared member checked against a live object of that type, and a
  facade call checked to reach the same member the proxy reaches.

The second tier is the one that catches a FreeCAD upgrade removing or renaming something.

See doc/architecture/geometry_bridge.md sections 4.10 and 5.6.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from geometry_bridge import facades as F                                 # noqa: E402
from geometry_bridge.ops import MAX_BASES, base_names                    # noqa: E402
from geometry_bridge.proxy import Remote                                 # noqa: E402

from conftest import requires_freecad                                    # noqa: E402

# ------------------------------------------------------------------------------------------
# Tier 1: no vendor needed
# ------------------------------------------------------------------------------------------


class _FakeSession(object):
    """Enough session to build a `Remote` without a transport."""

    def _queue_release(self, h):
        pass


def _remote(type_name, bases=None):
    return Remote(_FakeSession(), 1, type_name, '', bases if bases is not None else (type_name,))


def test_base_names_drops_object_and_is_leaf_first():
    class A(object):
        pass

    class B(A):
        pass

    assert base_names(B()) == ['B', 'A']


def test_base_names_caps_its_length():
    """A pathological hierarchy must not bloat every handle reply."""
    cls = object
    for i in range(40):
        cls = type('C%d' % i, (cls,), {})
    assert len(base_names(cls())) == MAX_BASES


def test_base_names_survives_an_object_without_a_type():
    """Defensive: `base_names` is called on every handle, so it may not raise."""

    class Odd(object):
        __slots__ = ()

    assert base_names(Odd()) == ['Odd']


def test_lookup_walks_the_class_chain_not_the_leaf_name():
    """The finding that drove the protocol change: a document object's leaf type is `PrimitivePy`.

    If this ever reverts to keying on the leaf name, the single most-used facade stops being
    reached -- silently, because the proxy fallback still works.
    """
    r = _remote('PrimitivePy', ('PrimitivePy', 'Feature', 'GeoFeature', 'DocumentObject'))
    assert F.facade_for(r) is F.DocumentObject
    assert isinstance(F.wrap(r), F.DocumentObject)


def test_lookup_prefers_the_most_derived_match():
    """`Solid`'s chain contains `Shape`; the `Solid` facade must win."""
    r = _remote('Solid', ('Solid', 'Shape', 'ComplexGeoData', 'Persistence'))
    assert F.facade_for(r) is F.Solid


def test_lookup_falls_back_to_the_leaf_name_when_the_chain_is_empty():
    """A worker predating the `bases` field, or a type whose MRO could not be read."""
    assert F.facade_for(_remote('Vector', ())) is F.Vector


def test_an_unfaceted_type_is_left_as_a_proxy():
    """The deliberate unevenness: no facade is not an error, it is the fallback."""
    r = _remote('Rotation', ('Rotation', 'PyObjectBase'))
    assert F.facade_for(r) is None
    assert F.wrap(r) is r


def test_shell_compound_and_compsolid_share_the_shape_facade():
    for name in ('Shell', 'Compound', 'CompSolid'):
        r = _remote(name, (name, 'Shape'))
        assert F.facade_for(r) is F.Shape, name


def test_wrap_passes_values_through_and_recurses_into_containers():
    assert F.wrap(3.5) == 3.5
    assert F.wrap(None) is None
    got = F.wrap([_remote('Vector'), 2.0])
    assert isinstance(got[0], F.Vector) and got[1] == 2.0
    got = F.wrap((_remote('Vector'),))
    assert isinstance(got, tuple) and isinstance(got[0], F.Vector)


def test_unwrap_is_the_inverse_for_facades_and_leaves_everything_else():
    r = _remote('Vector')
    assert F.unwrap(F.Vector(r)) is r
    assert F.unwrap(r) is r
    assert F.unwrap(7) == 7
    assert F.unwrap([F.Vector(r)]) == [r]
    assert isinstance(F.unwrap((F.Vector(r),)), tuple)


def test_a_facade_refuses_anything_but_a_remote():
    with pytest.raises(TypeError):
        F.Vector(object())


def test_vertex_does_not_inherit_center_of_mass():
    """The measured exception to the shape hierarchy. Asserted here as well as against the vendor,
    so the structural intent is pinned even when FreeCAD is absent."""
    assert 'CenterOfMass' in F.declared_members(F.Shape)
    assert 'CenterOfMass' not in F.declared_members(F.Vertex)
    assert not issubclass(F.Vertex, F.Shape)
    assert issubclass(F.Vertex, F.ShapeCommon)


def test_every_shape_subtype_inherits_the_shared_surface():
    shared = F.declared_members(F.ShapeCommon)
    assert len(shared) > 40
    for cls in (F.Shape, F.Solid, F.Face, F.Edge, F.Wire, F.Vertex):
        missing = shared - F.declared_members(cls)
        assert not missing, '%s is missing %s' % (cls.__name__, sorted(missing))


def test_declared_members_excludes_the_facades_own_surface():
    """`remote`, `remote_type` and `VENDOR` are the facade's, not the vendor's, and must not be
    checked against the vendor object."""
    members = F.declared_members(F.Shape)
    for name in ('remote', 'remote_type', 'VENDOR'):
        assert name not in members


def test_a_facade_is_truthy_and_unhashable_like_the_proxy():
    v = F.Vector(_remote('Vector'))
    assert bool(v) is True
    with pytest.raises(TypeError):
        hash(v)


def test_every_facade_declares_at_least_one_vendor_name():
    for cls in F.ALL_FACADES:
        assert cls.VENDOR, cls.__name__
        for name in cls.VENDOR:
            assert isinstance(name, str)


def test_the_lookup_table_covers_every_facade():
    mapped = set(F.BY_VENDOR_NAME.values())
    for cls in F.ALL_FACADES:
        assert cls in mapped, cls.__name__


# ------------------------------------------------------------------------------------------
# Tier 2: the drift test proper
# ------------------------------------------------------------------------------------------

#: One live object per facade, built from a single box. Keyed by facade class name.
#:
#: **The `Shape` facade is checked against a `Shell`, not against `box.Shape`.** `box.Shape` is a
#: `Solid` -- the vendor has no object whose leaf type is a bare `Part.Shape` carrying real
#: geometry, since every populated shape is one of the subclasses. A `Shell` is the honest stand-in:
#: it is a `Part.Shape` subclass with no facade of its own, so it both resolves to `Shape` and
#: carries the whole surface that facade declares.
_LIVE = {
    'DocumentObject': 'box',
    'Document': 'doc',
    'Vector': 'vector',
    'Placement': 'placement',
    'BoundBox': 'boundbox',
    'Shape': 'shell',
    'Solid': 'solid',
    'Face': 'face',
    'Edge': 'edge',
    'Wire': 'wire',
    'Vertex': 'vertex',
}


@pytest.fixture
def live(fc):
    """A proxy for one object of each faceted type, from one recomputed box."""
    App = fc.module('FreeCAD')
    doc = App.newDocument('facade_drift')
    box = doc.addObject('Part::Box', 'Box')
    box.Length = 10.0
    box.Width = 6.0
    box.Height = 4.0
    doc.recompute()
    shape = box.Shape
    return {
        'doc': doc,
        'box': box,
        'vector': App.Vector(1.0, 2.0, 3.0),
        'placement': box.Placement,
        'boundbox': shape.BoundBox,
        'shape': shape,
        'shell': shape.Shells[0],
        'solid': shape.Solids[0],
        'face': shape.Faces[0],
        'edge': shape.Edges[0],
        'wire': shape.Wires[0],
        'vertex': shape.Vertexes[0],
    }


@requires_freecad
@pytest.mark.parametrize('facade_name', sorted(_LIVE))
def test_every_declared_member_exists_on_the_live_vendor_object(live, facade_name):
    """**The drift test.** Each facade member must exist on the real object.

    This is what catches a FreeCAD upgrade that renames or removes something: without it the
    facade keeps type-checking and starts failing at run time, which §5.6 calls worse than having
    no facade.
    """
    cls = getattr(F, facade_name)
    obj = live[_LIVE[facade_name]]
    missing = []
    for name in sorted(F.declared_members(cls)):
        try:
            getattr(obj, name)
        except AttributeError:
            missing.append(name)
    assert not missing, '%s declares members absent from the live %s: %s' % (
        facade_name, obj.remote_type, ', '.join(missing))


@requires_freecad
def test_vertex_really_lacks_center_of_mass_on_the_live_object(live):
    """The converse of the hierarchy decision, against the vendor rather than the source.

    Without this, `Vertex` extending `ShapeCommon` instead of `Shape` would look like an arbitrary
    choice, and a later tidy-up would flatten it.
    """
    with pytest.raises(AttributeError):
        live['vertex'].CenterOfMass
    assert live['solid'].CenterOfMass is not None


@requires_freecad
@pytest.mark.parametrize('facade_name', sorted(_LIVE))
def test_the_live_object_resolves_to_the_expected_facade(live, facade_name):
    """The class chain the worker sends actually selects the facade intended for that type."""
    obj = live[_LIVE[facade_name]]
    assert F.facade_for(obj) is getattr(F, facade_name), (
        '%s resolved to %r, chain %r' % (facade_name, F.facade_for(obj), obj.remote_bases))


@requires_freecad
def test_a_document_object_is_faceted_despite_its_leaf_type(live):
    """The measured case the protocol change exists for, end to end against FreeCAD."""
    box = live['box']
    assert box.remote_type == 'PrimitivePy'
    assert 'DocumentObject' in box.remote_bases
    assert isinstance(F.wrap(box), F.DocumentObject)


@requires_freecad
def test_a_facade_read_equals_the_proxy_read(live):
    """A facade must not change what a member returns -- only how it is spelled."""
    shape = live['shape']
    f = F.wrap(shape)
    assert f.Volume == shape.Volume
    assert f.Area == shape.Area
    assert f.isValid() == shape.isValid()
    assert f.BoundBox.ZMax == shape.BoundBox.ZMax
    assert len(f.Faces) == len(shape.Faces)


@requires_freecad
def test_a_box_measures_what_a_box_should_through_the_facade(live):
    """Independent of the proxy comparison above: the numbers are right, not merely equal."""
    f = F.wrap(live['shape'])
    assert f.Volume == pytest.approx(10.0 * 6.0 * 4.0, rel=1e-9)
    assert f.BoundBox.XLength == pytest.approx(10.0, rel=1e-9)
    assert f.BoundBox.YLength == pytest.approx(6.0, rel=1e-9)
    assert f.BoundBox.ZLength == pytest.approx(4.0, rel=1e-9)
    assert len(f.Faces) == 6
    assert len(f.Edges) == 12
    assert len(f.Vertexes) == 8


@requires_freecad
def test_chaining_through_facades_stays_typed(live):
    """`shape.BoundBox.Center.x` crosses three facades and lands on a float."""
    f = F.wrap(live['shape'])
    bb = f.BoundBox
    assert isinstance(bb, F.BoundBox)
    center = bb.Center
    assert isinstance(center, F.Vector)
    assert center.x == pytest.approx(5.0, rel=1e-9)
    assert isinstance(f.Faces[0], F.Face)
    assert isinstance(f.Faces[0].OuterWire, F.Wire)
    assert isinstance(f.Edges[0], F.Edge)
    assert isinstance(f.Vertexes[0], F.Vertex)


@requires_freecad
def test_a_facade_can_be_passed_where_a_proxy_is_expected(live, fc):
    """`unwrap` on the argument path is what makes a boolean between two facades work."""
    Part = fc.module('Part')
    a = F.wrap(live['shape'])
    b = F.wrap(Part.makeBox(4.0, 4.0, 4.0))
    cut = a.cut(b)
    assert isinstance(cut, F.Shape)
    assert cut.Volume == pytest.approx(10.0 * 6.0 * 4.0 - 4.0 ** 3, rel=1e-6)
    assert cut.isValid()


@requires_freecad
def test_an_undeclared_member_falls_back_to_the_proxy(live):
    """The fallback has to work, or the facade set would have to be complete to be usable."""
    f = F.wrap(live['shape'])
    assert f.ShapeType == 'Solid'
    # `Matrix` is on no facade's declared list; it must still be reachable.
    assert F.wrap(live['placement']).Matrix is not None


@requires_freecad
def test_a_run_time_property_is_reachable_through_the_document_object_facade(live, fc):
    """A property added at run time cannot be declared, and must still read and write.

    This is why `DocumentObject`'s attribute reads are uncacheable, and the facade must not
    interfere with that.
    """
    box = F.wrap(live['box'])
    box.remote.addProperty('App::PropertyFloat', 'unit_width', 'Cowl', 'test property')
    box.unit_width = 12.5
    assert box.unit_width == pytest.approx(12.5)


@requires_freecad
def test_setattr_through_a_facade_reaches_the_document(live):
    """The 93-use `setExpression` case's plainer sibling: a declared, writable property."""
    box = F.wrap(live['box'])
    box.Length = 20.0
    assert box.Length.Value == pytest.approx(20.0)
    assert live['box'].Length.Value == pytest.approx(20.0)


@requires_freecad
def test_set_expression_is_reachable_and_takes_effect(live, fc):
    """`setExpression` is the second-most-used member in the whole survey."""
    doc = live['doc']
    box = F.wrap(live['box'])
    box.setExpression('Height', 'Box.Length / 4')
    doc.recompute()
    assert box.Height.Value == pytest.approx(box.Length.Value / 4.0)


@requires_freecad
def test_a_facade_does_not_add_round_trips_to_a_read(live, fc):
    """A facade is a spelling, not a layer with its own cost.

    Guards against a future refactor that resolves facades by asking the worker what something is
    -- which would double every read.
    """
    f = F.wrap(live['shape'])
    before = fc.round_trips
    f.Volume
    assert fc.round_trips - before == 1


@requires_freecad
def test_the_facade_set_matches_the_documented_survey_order():
    """The build order in §4.10 is the survey's ranking; keep the source agreeing with the doc."""
    assert [c.__name__ for c in F.ALL_FACADES[:5]] == [
        'DocumentObject', 'Vector', 'Document', 'BoundBox', 'Placement']
