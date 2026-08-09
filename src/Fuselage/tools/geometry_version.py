"""IP-FC-11: a fingerprint of the geometry code a part was built from.

`--resume` decides a part is current by comparing the definition file it would write now
against the one on disk. That catches every change to the *parameters*. It catches nothing
about the code that turns parameters into geometry, and both backends have that hole:

    OpenSCAD   the generated .stl.scad is a `use <...>` line and a call. Editing
               fuselage_bulkhead_geometry.scad leaves it byte-identical.
    FreeCAD    the definition is the parameter table. Editing bulkhead_full.py leaves
               it byte-identical.

So a resumed sweep after a geometry edit skips exactly the parts that edit invalidated --
the failure `--resume` exists to prevent -- and says "already rendered" while doing it. It
was found while wiring the FreeCAD backend (IP-FC-10), but it is not a backend regression:
the OpenSCAD path has behaved this way since `--resume` was added.

The fix is to put a digest of the geometry sources into the definition file, where the
existing comparison already looks. Nothing in `render_definition` changes; the digest just
becomes part of what a definition *is*.

**Deliberately over-sensitive.** The digest is over file bytes, so a comment or docstring
edit re-renders parts whose geometry did not move. That is the safe direction and the cheap
one: a false re-render costs minutes of CPU, a false skip ships a part that does not match
its own source and is invisible until someone measures it. Normalising -- stripping
comments, parsing to an AST -- would trade a real guarantee for a fragile one.

What it does not cover: assets referenced by *value* at render time rather than by source
text, which today means the OML meshes a cowl imports. Their filename is in the definition
but their content is not, so replacing oml/nose_round.stl in place is still invisible to a
resume. Narrower than the hole this closes, and recorded as such rather than left implied.
"""
from __future__ import annotations

import hashlib
import os
import re

# `use <x.scad>` / `include <x.scad>`, the only two ways one .scad file reaches another.
#
# **The semicolon is optional and that is not a nicety** -- OpenSCAD does not require one,
# and not one of the hand-written modules in scad/ writes it. Requiring it made this walk
# stop at the first file: the bulkhead's closure came back as one module instead of three,
# so an edit to fuselage_corner_geometry.scad, which the bulkhead includes, still looked
# like no change at all. The self-test that caught it is why it walks a real chain rather
# than a fixture. solid2's generated files do emit the semicolon, which is why
# fuselage_variants._SCAD_REF_RE can require it -- that one only ever sees generated files.
_SCAD_REF = re.compile(r'(?m)^\s*(?:use|include)\s*<([^>]+)>\s*;?')

# `import x` / `from x import y`, unanchored to indentation so a deferred import inside a
# function is seen too -- corner_tree.py has one. Names that do not resolve to a file in the
# search directory are dropped, which is what keeps FreeCAD's own modules, the standard
# library, and prose in a docstring that happens to start with "from" out of the closure.
_PY_IMPORT = re.compile(r'(?m)^\s*(?:import|from)\s+(\w+)')

_CACHE = {}


def _digest(paths):
    """One hex digest over a set of files, identified by basename rather than full path.

    So a **rename** changes the digest and a **move** does not. That is the right way round
    for this: both closures live in a single directory, and the absolute path of that
    directory is a property of the machine -- keying on it would make every checkout produce
    a different digest for identical sources, and a definition file that cannot be compared
    between machines is not much of a staleness key.

    Short on purpose: this sits in a definition file a person reads. 16 hex characters is
    64 bits, and the thing it has to survive is accidental collision between successive
    edits of the same file, not an adversary.
    """
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: os.path.basename(p).lower()):
        h.update(os.path.basename(path).encode('utf-8'))
        h.update(b'\0')
        with open(path, 'rb') as f:
            h.update(hashlib.sha256(f.read()).digest())
    return h.hexdigest()[:16]


def _resolved(paths):
    return [os.path.normcase(os.path.abspath(p)) for p in paths]


def _closure(roots, dependencies_of):
    """Every file reachable from `roots`, including them. Cycles terminate.

    `include <>` in OpenSCAD is textual and self-referential includes are legal, so the
    visited set is not optional here.
    """
    seen = {}
    pending = list(roots)
    while pending:
        path = os.path.normcase(os.path.abspath(pending.pop()))
        if path in seen or not os.path.isfile(path):
            continue
        seen[path] = True
        pending.extend(dependencies_of(path))
    return list(seen)


def _scad_dependencies(path):
    """The files this .scad reaches, resolved the way OpenSCAD resolves them.

    Relative to the directory of the file containing the reference -- not the working
    directory and not the root document. The generated sweep files rely on this; it is why
    `relativize_scad_references` can rewrite them to relative form at all.
    """
    here = os.path.dirname(path)
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    return [os.path.join(here, ref.strip()) for ref in _SCAD_REF.findall(text)]


def _python_dependencies(path, search_dir):
    """Sibling modules this .py imports. Only siblings: the port is one flat directory."""
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    return [os.path.join(search_dir, name + '.py')
            for name in _PY_IMPORT.findall(text)]


def scad_version(generated_scad_path):
    """The geometry version of a generated `.stl.scad`, from its own `use <>` lines.

    Taking the roots from the generated file rather than from the call site is what makes
    this cover every part the sweep produces -- cowls, tails, plates, booms -- instead of
    only the kinds someone remembered to annotate. The generated file already names its
    geometry module; it is the one place that cannot be forgotten.

    The generated file itself is excluded: it holds the parameters, which the definition
    comparison already sees, and including it would make the digest depend on itself.
    """
    roots = _scad_dependencies(generated_scad_path)
    # Keyed on the resolved paths, not the ones written in the file. The sweep's `use <>`
    # lines are relative to each part's own directory, so the same module is spelled a
    # different number of `../` deep for every output directory -- keying on the text would
    # give ~1800 cache entries for the handful of distinct closures that actually exist.
    key = ('scad', tuple(sorted(_resolved(roots))))
    if key not in _CACHE:
        files = _closure(roots, _scad_dependencies)
        _CACHE[key] = (_digest(files), sorted(os.path.basename(f) for f in files))
    return _CACHE[key]


def freecad_version(entry_modules, search_dir):
    """The geometry version of a FreeCAD part, from the modules its builder imports.

    `entry_modules` is the builder plus the kind's top module -- `build_part.py` is in
    there because LINEAR_DEFLECTION lives in it, and the tessellation setting changes the
    exported mesh just as surely as a sketch does.
    """
    roots = [os.path.join(search_dir, m) if m.endswith('.py')
             else os.path.join(search_dir, m + '.py')
             for m in entry_modules]
    key = ('freecad', tuple(sorted(_resolved(roots))))
    if key not in _CACHE:
        files = _closure(roots, lambda p: _python_dependencies(p, search_dir))
        _CACHE[key] = (_digest(files), sorted(os.path.basename(f) for f in files))
    return _CACHE[key]


def clear_cache():
    """Forget memoised digests. For tests that edit a source file mid-process.

    A sweep does not need this: the sources cannot change while it runs, and hashing the
    bulkhead's three .scad files once instead of ~600 times is the difference between
    free and noticeable.
    """
    _CACHE.clear()
