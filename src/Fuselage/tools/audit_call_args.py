"""Audit OpenSCAD module calls for positional-argument mismatches.

Found after OQ-DES-B10: greeble_bolt_web's one call site passes its last three arguments in
rotated order. OpenSCAD matches positionally and says nothing, and two of the three values
were equal at the driver's settings, so nothing looked wrong. If one call drifted, others
may have.

Only flags a position where the caller passes a BARE IDENTIFIER that is itself a parameter
name of the enclosing module, and that name differs from the declared parameter -- so
expressions and literals are ignored and the signal stays clean.
"""
import glob
import os
import re
import sys

SCAD = sys.argv[1] if len(sys.argv) > 1 else 'src/Fuselage/scad'

sig_re = re.compile(r'^\s*module\s+(\w+)\s*\((.*?)\)\s*\{?', re.S | re.M)


def split_args(text):
    out, depth, cur = [], 0, ''
    for ch in text:
        if ch in '([': depth += 1
        elif ch in ')]': depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


sigs = {}
sources = {}
for path in sorted(glob.glob(os.path.join(SCAD, '*.scad'))):
    src = open(path, encoding='utf-8', errors='replace').read()
    sources[path] = src
    for m in sig_re.finditer(src):
        params = [p.split('=')[0].strip() for p in split_args(m.group(2))]
        sigs[m.group(1)] = (params, path)

findings = 0
for path, src in sources.items():
    # the enclosing module for each offset, so we know which names are parameters there
    bounds = [(m.start(), m.group(1)) for m in sig_re.finditer(src)]
    for name, (params, _) in sigs.items():
        for call in re.finditer(r'(?<![\w.])' + name + r'\s*\(', src):
            start = call.end()
            depth, i = 1, start
            while i < len(src) and depth:
                if src[i] == '(': depth += 1
                elif src[i] == ')': depth -= 1
                i += 1
            if depth:
                continue
            inner = src[start:i - 1]
            if re.match(r'^\s*$', inner) or src[:call.start()].rstrip().endswith('module'):
                continue
            args = split_args(inner)
            if len(args) != len(params):
                continue
            enclosing = None
            for off, mod in bounds:
                if off < call.start():
                    enclosing = mod
            scope = set(sigs.get(enclosing, ([], None))[0])
            # Only a PERMUTATION is a defect: the passed name is itself one of the
            # callee's own parameters, just not the one at this position. A caller using a
            # more specific name for a generic parameter is normal and correct.
            pset = set(params)
            bad = [(k, a, p) for k, (a, p) in enumerate(zip(args, params))
                   if re.fullmatch(r'\w+', a) and a in scope and a != p and a in pset]
            if bad:
                findings += 1
                line = src[:call.start()].count('\n') + 1
                print('%s:%d  %s() called from %s()' % (os.path.basename(path), line,
                                                        name, enclosing))
                for k, a, p in bad:
                    print('    arg %d: passes %-22s -> parameter %s' % (k + 1, a, p))
print('')
print('%d call site(s) with a positional mismatch' % findings)
