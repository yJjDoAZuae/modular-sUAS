"""The codec: what crosses as a value, what stays behind a handle, and numeric fidelity.

Numeric fidelity is the one a reader should not skip. This project asserts a construction identity
at about 1e-13 mm and a wall tolerance at 0.01 mm, so a transport that rounded in the twelfth digit
would manufacture error indistinguishable from a geometry defect. These tests pin the property
rather than trusting a comment, because a future change of wire format could break it silently.
"""
import json
import math

import pytest

from geometry_bridge import codec


class TestWhatCrossesAsAValue:

    @pytest.mark.parametrize('obj', [None, True, False, 0, -17, 3.5, '', 'text'])
    def test_scalars_are_values(self, obj):
        assert codec.is_value(obj)

    @pytest.mark.parametrize('obj', [[], [1, 2], (1, 2), {'a': 1}, {'a': [1, {'b': 2}]}])
    def test_shallow_containers_of_scalars_are_values(self, obj):
        assert codec.is_value(obj)

    def test_a_dict_with_a_non_string_key_is_not_a_value(self):
        """JSON object keys are strings; silently coercing would be a lossy conversion."""
        assert not codec.is_value({1: 'a'})

    def test_bytes_are_not_a_value(self):
        """Encoding bytes as a string would be exactly the kind of silent lossy conversion
        this project's measurement history warns about."""
        assert not codec.is_value(b'abc')

    def test_an_arbitrary_object_is_not_a_value(self):
        assert not codec.is_value(object())

    def test_nesting_deeper_than_the_cap_is_not_a_value(self):
        shallow = [[[1]]]
        deep = [[[[1]]]]
        assert codec.MAX_VALUE_DEPTH == 3
        assert codec.is_value(shallow)
        assert not codec.is_value(deep), 'past the cap it must become a handle, not be walked'

    def test_a_container_holding_an_object_is_not_a_value(self):
        assert not codec.is_value([1, object()])


class TestNumericFidelity:

    @pytest.mark.parametrize('want', [
        0.1,
        1.0 / 3.0,
        1e-13,                      # the rib-gap identity's own order
        1.0 + 1e-15,
        0.01,                       # WALL_TOL
        290850.6976,                # a measured cavity volume
        math.pi,
        2.2250738585072014e-308,    # smallest normal double
        5e-324,                     # a subnormal
        1.7976931348623157e308,     # largest finite double
        -0.0,
    ])
    def test_a_float_survives_a_json_round_trip_bit_exactly(self, want):
        got = json.loads(json.dumps(codec.encode_value(want)))
        assert got == want
        assert repr(got) == repr(want), 'bit pattern must be preserved, not merely the value'

    def test_negative_zero_keeps_its_sign(self):
        got = json.loads(json.dumps(codec.encode_value(-0.0)))
        assert math.copysign(1.0, got) == -1.0

    @pytest.mark.parametrize('name,want', [
        ('inf', float('inf')), ('-inf', float('-inf'))])
    def test_non_finite_floats_cross_intact(self, name, want):
        """Python's json emits Infinity, which is NOT standard JSON.

        Pinned deliberately: both ends are CPython so it is safe today, and this test is what will
        fail if the transport is ever changed to something stricter.
        """
        got = json.loads(json.dumps(codec.encode_value(want)))
        assert got == want

    def test_nan_crosses_and_is_still_nan(self):
        got = json.loads(json.dumps(codec.encode_value(float('nan'))))
        assert math.isnan(got)

    def test_a_large_float_list_round_trips_exactly(self):
        """The shape of a bulk read: many floats in one payload."""
        want = [i * 1.0000000001 for i in range(2000)]
        got = json.loads(json.dumps(codec.encode_value(want)))
        assert got == want


class TestDocumentedLossyMappings:

    def test_a_tuple_becomes_a_list(self):
        """Known and documented. A test that needs tuple-ness uses a handle instead."""
        assert codec.encode_value((1, 2, 3)) == [1, 2, 3]

    def test_a_nested_tuple_becomes_nested_lists(self):
        assert codec.encode_value(((1, 2), (3,))) == [[1, 2], [3]]


class TestArgumentEncoding:

    def test_a_proxy_becomes_a_handle_reference(self):
        marker = object()
        out = codec.encode_argument(marker, lambda v: 7 if v is marker else None)
        assert out == {codec.HANDLE_KEY: 7}

    def test_proxies_nested_in_containers_are_found(self):
        a, b = object(), object()
        ids = {id(a): 1, id(b): 2}
        out = codec.encode_argument([a, {'k': b}, 5], lambda v: ids.get(id(v)))
        assert out == [{codec.HANDLE_KEY: 1}, {'k': {codec.HANDLE_KEY: 2}}, 5]

    def test_decoding_resolves_handles_through_the_given_resolver(self):
        sentinel = object()
        got = codec.decode_argument({codec.HANDLE_KEY: 4}, lambda h: sentinel if h == 4 else None)
        assert got is sentinel

    def test_a_dict_that_merely_contains_the_marker_key_is_not_a_handle(self):
        """A one-key dict is a handle; anything else is ordinary data and must pass through."""
        payload = {codec.HANDLE_KEY: 1, 'other': 2}
        got = codec.decode_argument(payload, lambda h: pytest.fail('should not resolve'))
        assert got == payload

    def test_decoding_is_recursive_through_lists_and_dicts(self):
        got = codec.decode_argument(
            [{codec.HANDLE_KEY: 1}, {'k': [{codec.HANDLE_KEY: 2}]}],
            lambda h: 'obj%d' % h)
        assert got == ['obj1', {'k': ['obj2']}]
