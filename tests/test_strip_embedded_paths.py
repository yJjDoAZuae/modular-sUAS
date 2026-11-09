"""Tests for `strip_embedded_paths`, the binary path remover.

Every fixture here is synthesized rather than copied from a real asset, for two reasons. A real
`.blend` is 11 MB, which is not a unit test. And the string being removed must not appear in this
repository at all -- including in a test -- so the needle is a made-up path that resembles the
shape of the real thing without being it.

The properties worth asserting are the ones the history rewrite depends on being true:

  * a PNG edit drops a whole chunk and leaves every `IDAT` byte alone;
  * a `.blend` edit never changes the file's length, because a length change invalidates every
    block offset after it;
  * an edit covers the *whole* embedded string, not just the bytes the pattern matched;
  * and the tool refuses rather than truncating when a replacement will not fit.
"""
import re
import struct
import zlib

import pytest
import strip_embedded_paths as sep

#: A path-shaped needle that is not anyone's real path. The tool is pattern-driven, so the test
#: supplies its own list exactly as the gate and the rewrite do.
NEEDLE = rb'Zyzzy'
PATTERN = re.compile(NEEDLE)

#: A full path containing the needle in the middle, so a test can tell whether the edit covered
#: the whole string or only the matched fragment.
FAKE_PATH = rb'Q:\Zyzzy\Designs\thing.blend'


# ----------------------------------------------------------------------------- PNG fixtures


def png_chunk(name, payload):
    body = name + payload
    return struct.pack('>I', len(payload)) + body + struct.pack('>I', zlib.crc32(body)
                                                                & 0xFFFFFFFF)


def make_png(text_chunks=(), width=1, height=1):
    """A structurally valid 1x1 grayscale PNG, plus whatever text chunks are asked for."""
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
    raw = b''.join(b'\x00' + b'\x80' * width for _ in range(height))
    out = sep.PNG_SIG + png_chunk(b'IHDR', ihdr)
    for keyword, value in text_chunks:
        out += png_chunk(b'tEXt', keyword + b'\x00' + value)
    out += png_chunk(b'IDAT', zlib.compress(raw)) + png_chunk(b'IEND', b'')
    return out


# --------------------------------------------------------------------------- blend fixtures


def blend_block(code, payload, sdna=0, nr=1):
    """One `BHead` for an 8-byte-pointer little-endian file, plus its payload."""
    head = struct.Struct('<4siQii')
    return head.pack(code, len(payload), 0, sdna, nr) + payload


def make_blend(field, field_size=64):
    """A minimal `BLENDER-v405` file carrying `field` in one NUL-padded fixed-size slot."""
    assert len(field) <= field_size
    padded = field + b'\x00' * (field_size - len(field))
    body = b'\x01' * 8 + padded + b'\x02' * 8
    return (b'BLENDER-v405'
            + blend_block(b'DATA', body)
            + blend_block(b'DNA1', b'SDNANAME')
            + blend_block(b'ENDB', b''))


# --------------------------------------------------------------------------------- PNG tests


class TestThePngEditDropsAChunkAndLeavesThePictureAlone:
    def test_a_synthesized_png_is_valid_to_begin_with(self):
        info = sep.png_validate(make_png())
        assert info['kinds'] == ['IDAT', 'IEND', 'IHDR']
        assert info['idat'] == 1

    def test_the_matching_text_chunk_is_removed(self):
        data = make_png([(b'File', FAKE_PATH)])
        clean, removed = sep.png_strip_text(data, PATTERN)
        assert len(removed) == 1
        assert removed[0][0] == 'tEXt'
        assert NEEDLE in removed[0][1]
        assert not sep.residue(clean, PATTERN)

    def test_idat_is_byte_identical_across_the_edit(self):
        data = make_png([(b'File', FAKE_PATH)])
        clean, _ = sep.png_strip_text(data, PATTERN)
        assert sep.png_idat(clean) == sep.png_idat(data)

    def test_the_cleaned_png_still_validates_including_crcs(self):
        data = make_png([(b'File', FAKE_PATH)])
        clean, _ = sep.png_strip_text(data, PATTERN)
        assert sep.png_validate(clean)['idat'] == 1

    def test_the_file_shrinks_by_exactly_the_chunk_it_lost(self):
        """12 bytes of chunk overhead plus the payload, and not one byte more."""
        payload = b'File\x00' + FAKE_PATH
        data = make_png([(b'File', FAKE_PATH)])
        clean, _ = sep.png_strip_text(data, PATTERN)
        assert len(data) - len(clean) == len(payload) + 12

    def test_a_text_chunk_that_does_not_match_is_left_in_place(self):
        """The converse that decides whether the edit is targeted or indiscriminate."""
        data = make_png([(b'Date', b'2025/10/12'), (b'File', FAKE_PATH)])
        clean, removed = sep.png_strip_text(data, PATTERN)
        assert len(removed) == 1
        kept = [p for n, _s, _e, p in sep.png_chunks(clean) if n == 'tEXt']
        assert kept == [b'Date\x002025/10/12']

    def test_a_corrupted_crc_is_caught(self):
        data = bytearray(make_png())
        data[-5] ^= 0xFF
        with pytest.raises(sep.FormatError, match='CRC'):
            sep.png_validate(bytes(data))

    def test_a_truncated_file_is_caught_rather_than_half_walked(self):
        with pytest.raises(sep.FormatError):
            sep.png_validate(make_png()[:-6])

    def test_a_non_png_is_refused_by_signature(self):
        with pytest.raises(sep.FormatError, match='not a PNG'):
            sep.png_validate(b'this is not a png at all')


# ------------------------------------------------------------------------------- blend tests


class TestTheBlendEditNeverChangesTheLength:
    def test_a_synthesized_blend_parses(self):
        info = sep.blend_validate(make_blend(FAKE_PATH))
        assert info['pointer_size'] == 8
        assert info['version'] == '405'
        assert info['has_dna']

    def test_the_length_is_preserved_exactly(self):
        data = make_blend(FAKE_PATH)
        clean, spans = sep.overwrite_in_span(data, PATTERN)
        assert len(clean) == len(data)
        assert len(spans) == 1

    def test_the_whole_path_is_overwritten_not_just_the_matched_bytes(self):
        """The needle sits mid-string; a fragment-only edit would leave the rest behind."""
        data = make_blend(FAKE_PATH)
        clean, spans = sep.overwrite_in_span(data, PATTERN)
        _lo, _hi, was = spans[0]
        assert was == FAKE_PATH
        assert b'Designs' not in clean
        assert b'Q:' not in clean
        assert not sep.residue(clean, PATTERN)

    def test_the_block_chain_still_walks_after_the_edit(self):
        data = make_blend(FAKE_PATH)
        clean, _ = sep.overwrite_in_span(data, PATTERN)
        assert sep.blend_validate(clean)['blocks'] == 3

    def test_the_bytes_around_the_field_are_untouched(self):
        """Padding must not bleed past the string into the neighboring values."""
        data = make_blend(FAKE_PATH)
        clean, _ = sep.overwrite_in_span(data, PATTERN)
        assert clean.count(b'\x01' * 8) == 1
        assert clean.count(b'\x02' * 8) == 1

    def test_a_replacement_that_will_not_fit_is_refused(self):
        data = make_blend(b'Zyzzy')
        with pytest.raises(sep.FormatError, match='will not fit'):
            sep.overwrite_in_span(data, PATTERN, b'a replacement far longer than the field')

    def test_a_short_replacement_is_nul_padded_to_the_original_span(self):
        data = make_blend(FAKE_PATH)
        clean, spans = sep.overwrite_in_span(data, PATTERN, b'Q:\\')
        lo, hi, _was = spans[0]
        assert clean[lo:hi] == b'Q:\\' + b'\x00' * (hi - lo - 3)
        assert len(clean) == len(data)

    def test_a_blend_without_a_structure_table_is_refused(self):
        broken = b'BLENDER-v405' + blend_block(b'DATA', b'x' * 8) + blend_block(b'ENDB', b'')
        with pytest.raises(sep.FormatError, match='DNA1'):
            sep.blend_validate(broken)

    def test_a_bad_pointer_flag_is_refused(self):
        with pytest.raises(sep.FormatError, match='pointer-size'):
            sep.blend_header(b'BLENDERXv405')


# ------------------------------------------------------------------------- dispatch and span


class TestDispatchRefusesWhatItDoesNotUnderstand:
    def test_png_and_blend_are_recognized(self):
        assert sep.kind_of(make_png()) == 'png'
        assert sep.kind_of(make_blend(FAKE_PATH)) == 'blend'

    def test_anything_else_is_not(self):
        assert sep.kind_of(b'\x00\x01\x02\x03 arbitrary bytes') is None

    def test_clean_raises_on_an_unrecognized_format(self):
        with pytest.raises(sep.FormatError, match='unrecognized format'):
            sep.clean(b'\x00\x01\x02\x03 arbitrary bytes', PATTERN)

    def test_clean_reports_the_png_case_with_idat_proof(self):
        report = sep.clean(make_png([(b'File', FAKE_PATH)]), PATTERN)[1]
        assert report['kind'] == 'png'
        assert report['idat_identical'] is True
        assert report['bytes_after'] < report['bytes_before']

    def test_clean_reports_the_blend_case_with_length_proof(self):
        report = sep.clean(make_blend(FAKE_PATH), PATTERN)[1]
        assert report['kind'] == 'blend'
        assert report['length_preserved'] is True
        assert report['bytes_after'] == report['bytes_before']

    def test_printable_span_stops_at_non_printable_bytes(self):
        data = b'\x00\x00' + FAKE_PATH + b'\x00\x00'
        lo, hi = sep.printable_span(data, 2 + FAKE_PATH.index(NEEDLE))
        assert data[lo:hi] == FAKE_PATH

    def test_residue_is_empty_once_the_edit_is_done(self):
        for fixture in (make_png([(b'File', FAKE_PATH)]), make_blend(FAKE_PATH)):
            clean, _report = sep.clean(fixture, PATTERN)
            assert sep.residue(clean, PATTERN) == []
