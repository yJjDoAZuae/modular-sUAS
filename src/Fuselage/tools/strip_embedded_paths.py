"""Remove an absolute path embedded inside a binary asset, without disturbing what it draws.

**Why this exists.** A Blender document and a Cycles render can carry an absolute user-profile
path in their internal data without any of it being an asset reference -- a last-used directory,
a paste-buffer temp path, a render stamp naming the `.blend` a picture came from. Nothing needs
relinking in that case, so re-exporting the file would rewrite thousands of unrelated bytes to
fix a few dozen, and would leave the geometry equal only by assumption rather than by
construction. This tool exists so that repair can be made by construction instead, and it stays
because the commit gate needs something that reads bytes rather than decoded text.

Both formats admit a repair that is provably confined to the offending bytes:

  * a PNG is a sequence of self-delimiting chunks, so a text chunk can be dropped outright and
    every remaining chunk -- including every `IDAT` byte, which is the picture -- is untouched;
  * a `.blend` stores its paths in fixed-size NUL-padded char arrays inside length-prefixed
    blocks, so overwriting a path *in span* with NUL padding changes no block length, no file
    offset and no entry in the SDNA table.

The second point is the one that matters for the history rewrite: `filter-repo --replace-text`
substitutes without padding, which shortens the file and invalidates every offset after the
edit. That is why these blobs need a callback rather than a replacement list.

Nothing here decides *what* counts as a path worth removing. The caller supplies the pattern, so
the same tool serves the identity gate and the rewrite without either one owning the list.

    python strip_embedded_paths.py --scan  media/splode.blend
    python strip_embedded_paths.py --write media/splode.blend --out cleaned.blend
    python strip_embedded_paths.py --verify media/splode.blend cleaned.blend
"""
import re
import struct
import sys
import zlib

#: A PNG's fixed eight-byte signature.
PNG_SIG = b'\x89PNG\r\n\x1a\n'

#: PNG chunks that carry human-readable text, and so can carry a path. `zTXt` is compressed, so
#: a pattern will not match its payload directly -- it is listed because it must still be
#: *considered* when deciding whether a file is clean, not because scanning finds it.
PNG_TEXT_CHUNKS = ('tEXt', 'iTXt', 'zTXt')

#: A `.blend` begins with this, then one char for pointer size and one for endianness, then a
#: three-character version. `BLENDER-v405` is 8-byte pointers, little-endian, version 4.05.
BLEND_MAGIC = b'BLENDER'

#: The default replacement is nothing at all: the span is filled with NUL bytes, which both
#: formats read as an unset string. A placeholder would have to be a plausible value for
#: whichever field it landed in, and there is no single string that is plausible for a
#: directory, a temp file and a render stamp at once.
EMPTY = b''


class FormatError(Exception):
    """The file is not the format its signature claims, or its structure does not parse."""


# --------------------------------------------------------------------------------------- PNG


def png_chunks(data):
    """Yield `(name, start, end, payload)` for every chunk, `start` at the length field.

    Raises `FormatError` rather than returning a partial walk, because a caller that is about to
    *edit* the file needs to know the structure was understood completely.
    """
    if data[:8] != PNG_SIG:
        raise FormatError('not a PNG: signature is %r' % data[:8])
    pos = 8
    seen_end = False
    while pos + 12 <= len(data):
        (length,) = struct.unpack('>I', data[pos:pos + 4])
        name = data[pos + 4:pos + 8].decode('latin-1')
        end = pos + 12 + length
        if end > len(data):
            raise FormatError('chunk %r at %d runs past end of file' % (name, pos))
        yield name, pos, end, data[pos + 8:pos + 8 + length]
        if name == 'IEND':
            seen_end = True
            pos = end
            break
        pos = end
    if not seen_end:
        raise FormatError('no IEND chunk')


def png_validate(data):
    """Check the structure and every chunk's CRC. Returns a dict; raises on a real defect.

    A length-preserving edit cannot break a CRC it does not touch, but dropping a chunk changes
    the file's length, and a mistake there would be silent until something tried to decode the
    image. So this is checked rather than argued.
    """
    names = []
    for name, start, end, _payload in png_chunks(data):
        names.append(name)
        (stored,) = struct.unpack('>I', data[end - 4:end])
        actual = zlib.crc32(data[start + 4:end - 4]) & 0xFFFFFFFF
        if stored != actual:
            raise FormatError('chunk %r at %d has CRC %08x, computed %08x'
                              % (name, start, stored, actual))
    if not names or names[0] != 'IHDR':
        raise FormatError('first chunk is %r, not IHDR' % (names[0] if names else None))
    if names[-1] != 'IEND':
        raise FormatError('last chunk is %r, not IEND' % names[-1])
    if 'IDAT' not in names:
        raise FormatError('no IDAT chunk, so the file carries no image')
    return {'chunks': len(names), 'kinds': sorted(set(names)), 'idat': names.count('IDAT')}


def png_idat(data):
    """Every `IDAT` payload concatenated -- the compressed picture, and nothing else.

    This is what makes "the image is unchanged" a measurement instead of a claim: compare this
    between the original and the cleaned file and the pixels are identical if the bytes are.
    """
    return b''.join(p for name, _s, _e, p in png_chunks(data) if name == 'IDAT')


def png_strip_text(data, pattern):
    """Drop every text chunk whose payload matches `pattern`. Returns `(new_data, removed)`.

    Chunks are self-delimiting and a PNG holds no internal byte offsets, so removing one needs no
    fix-up anywhere else. `removed` lists `(name, payload)` for the caller to report.
    """
    out = bytearray(data[:8])
    removed = []
    for name, start, end, payload in png_chunks(data):
        if name in PNG_TEXT_CHUNKS and pattern.search(payload):
            removed.append((name, bytes(payload)))
            continue
        out += data[start:end]
    return bytes(out), removed


# ------------------------------------------------------------------------------------- blend


def blend_header(data):
    """`(pointer_size, endian_char, version)` from the 12-byte header, or raise."""
    if data[:7] != BLEND_MAGIC:
        raise FormatError('not an uncompressed .blend: header is %r' % data[:12])
    ptr = data[7:8]
    if ptr not in (b'_', b'-'):
        raise FormatError('unknown pointer-size flag %r' % ptr)
    endian = data[8:9]
    if endian not in (b'v', b'V'):
        raise FormatError('unknown endianness flag %r' % endian)
    return (4 if ptr == b'_' else 8), endian.decode('latin-1'), data[9:12].decode('latin-1')


def blend_blocks(data):
    """Yield `(code, start, data_start, length)` for every block in the file.

    Each block is a `BHead` -- a four-character code, a payload length, the old pointer, an SDNA
    index and a count -- followed by its payload. Walking the whole chain and arriving exactly at
    `ENDB` is the static check that a length-neutral edit left the container intact.
    """
    ptr, endian, _version = blend_header(data)
    order = '<' if endian == 'v' else '>'
    head = struct.Struct('%s4si%sii' % (order, 'Q' if ptr == 8 else 'I'))
    pos = 12
    while pos + head.size <= len(data):
        code, length, _old, _sdna, _nr = head.unpack(data[pos:pos + head.size])
        name = code.rstrip(b'\x00').decode('latin-1')
        body = pos + head.size
        if length < 0 or body + length > len(data):
            raise FormatError('block %r at %d claims %d bytes, past end of file'
                              % (name, pos, length))
        yield name, pos, body, length
        if name == 'ENDB':
            return
        pos = body + length
    raise FormatError('block chain ran off the end without reaching ENDB')


def blend_validate(data):
    """Walk every block and confirm the file is structurally whole. Returns a dict."""
    codes = []
    for name, _start, _body, _length in blend_blocks(data):
        codes.append(name)
    if codes[-1] != 'ENDB':
        raise FormatError('block chain ends with %r, not ENDB' % codes[-1])
    if 'DNA1' not in codes:
        raise FormatError('no DNA1 block, so the file carries no structure table')
    ptr, endian, version = blend_header(data)
    return {'blocks': len(codes), 'pointer_size': ptr, 'endian': endian, 'version': version,
            'has_dna': True}


# -------------------------------------------------------------------------------- both kinds


def printable_span(data, at):
    """The full run of printable bytes containing offset `at`, as `(lo, hi)`.

    A pattern matches somewhere in the middle of a path. The field holds the whole string, so the
    edit has to cover the whole string -- otherwise a fragment of the original is left behind.
    """
    lo = at
    while lo > 0 and 32 <= data[lo - 1] < 127:
        lo -= 1
    hi = at
    while hi < len(data) and 32 <= data[hi] < 127:
        hi += 1
    return lo, hi


def overwrite_in_span(data, pattern, replacement=EMPTY):
    """NUL-pad `replacement` over every matching string, in place. Returns `(new_data, spans)`.

    Length-neutral by construction: each string's own bytes are overwritten and nothing outside
    them is touched, so the file size, every block length and every offset are unchanged. Raises
    if `replacement` will not fit, rather than silently truncating a path into a shorter one that
    still carries part of the original.
    """
    out = bytearray(data)
    spans = []
    seen = set()
    for m in pattern.finditer(bytes(data)):
        lo, hi = printable_span(data, m.start())
        if (lo, hi) in seen:
            continue
        seen.add((lo, hi))
        if len(replacement) > hi - lo:
            raise FormatError('replacement %r is %d bytes, will not fit the %d-byte field at %d'
                              % (replacement, len(replacement), hi - lo, lo))
        spans.append((lo, hi, bytes(data[lo:hi])))
        out[lo:hi] = replacement + b'\x00' * (hi - lo - len(replacement))
    return bytes(out), spans


def kind_of(data):
    """`'png'`, `'blend'`, or `None` for something this tool must not touch."""
    if data[:8] == PNG_SIG:
        return 'png'
    if data[:7] == BLEND_MAGIC:
        return 'blend'
    return None


def clean(data, pattern, replacement=EMPTY):
    """Strip `pattern` from one blob by whichever means its format allows.

    Returns `(new_data, report)`. The report says what was done so a caller can print it and a
    reviewer can see the edit was confined to what was claimed.
    """
    kind = kind_of(data)
    if kind == 'png':
        new, removed = png_strip_text(data, pattern)
        png_validate(new)
        if png_idat(new) != png_idat(data):
            raise FormatError('IDAT changed, which must never happen when dropping a text chunk')
        return new, {'kind': 'png', 'chunks_removed': removed,
                     'bytes_before': len(data), 'bytes_after': len(new), 'idat_identical': True}
    if kind == 'blend':
        new, spans = overwrite_in_span(data, pattern, replacement)
        blend_validate(new)
        if len(new) != len(data):
            raise FormatError('length changed by %d bytes, which invalidates every later offset'
                              % (len(new) - len(data)))
        return new, {'kind': 'blend', 'spans': spans,
                     'bytes_before': len(data), 'bytes_after': len(new),
                     'length_preserved': True}
    raise FormatError('unrecognized format, first bytes %r' % data[:12])


def residue(data, pattern):
    """Every remaining match, as `(offset, string)`, so "it is gone" can be checked not assumed."""
    out = []
    for m in pattern.finditer(data):
        lo, hi = printable_span(data, m.start())
        out.append((lo, data[lo:hi].decode('latin-1')))
    return out


# ----------------------------------------------------------------------------------- the CLI


def read_bytes(path):
    with open(path, 'rb') as fh:
        return fh.read()


def write_bytes(path, data):
    with open(path, 'wb') as fh:
        fh.write(data)


def _usage():
    print(__doc__.strip().split('\n\n')[-1])
    return 2


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    words = [a for a in argv if not a.startswith('--')]
    flags = [a for a in argv if a.startswith('--')]
    pat = None
    for f in flags:
        if f.startswith('--pattern='):
            pat = f.split('=', 1)[1]
    if not words or not pat:
        if not pat:
            print('a --pattern= is required: this tool does not own the list of what to remove')
        return _usage()
    pattern = re.compile(pat.encode('latin-1'))

    if '--verify' in flags:
        if len(words) != 2:
            return _usage()
        before, after = (read_bytes(w) for w in words)
        print('original %s -- %d bytes' % (words[0], len(before)))
        print('cleaned  %s -- %d bytes' % (words[1], len(after)))
        kind = kind_of(after)
        info = png_validate(after) if kind == 'png' else blend_validate(after)
        print('static inspection: PASS  %s' % info)
        left = residue(after, pattern)
        print('remaining matches: %d%s' % (len(left), '' if not left else '  ' + repr(left[:3])))
        if kind == 'png':
            same = png_idat(before) == png_idat(after)
            print('IDAT byte-identical: %s' % same)
        else:
            print('length preserved: %s' % (len(before) == len(after)))
        return 0 if not left else 1

    for path in words:
        data = read_bytes(path)
        if '--scan' in flags:
            left = residue(data, pattern)
            print('%s -- %s, %d match(es)' % (path, kind_of(data), len(left)))
            for off, s in left:
                print('    %10d  %s' % (off, s[:120]))
            continue
        new, report = clean(data, pattern)
        out = None
        for f in flags:
            if f.startswith('--out='):
                out = f.split('=', 1)[1]
        out = out or (path + '.clean')
        write_bytes(out, new)
        print('%s -> %s' % (path, out))
        for k, v in sorted(report.items()):
            print('    %-16s %s' % (k, v if k != 'spans' else
                                    [(lo, hi, s[:60]) for lo, hi, s in v]))
        left = residue(new, pattern)
        print('    %-16s %d' % ('residue', len(left)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
