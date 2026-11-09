"""American English in the source tree, including the identifiers.

`doc_check.py` holds this project's British-to-American word list and enforces it across
`doc/`. This module applies the same rule to the code: comments, docstrings, message strings and
**identifier names**. It is separate from `doc_check` because the hazards are different -- a
document can be rewritten freely, while renaming `artefact_fraction` has to reach every call
site in the same change or nothing imports.

**How a rename is kept honest.** A plain word-boundary replacement cannot touch a compound:
there is no boundary before the `centre` in `_face_centre`, so `\\bcentre\\b` leaves it alone.
That is the safe direction -- it means no compound is ever half-renamed by accident. Every
compound this project actually holds is therefore listed in `RENAMES`, applied as a whole token,
and **anything carrying a British stem inside a longer token that is not in that list is
reported rather than changed**. A new compound shows up as a finding instead of being mangled.

    python source_spelling.py            # what is left, and where
    python source_spelling.py --fix      # rewrite it

**Two files are exempt and must stay British**, because their subject is these words:
`doc_check.py`, whose `BRITISH` dictionary is the list of spellings to find, and
`test_doc_check.py`, whose fixtures assert the fixer changes them. Spell-correcting a spelling
checker's own dictionary deletes the checker.

Read and written as bytes, decoded explicitly: text mode would translate line endings, and every
text file here is stored with Unix endings on purpose.
"""
import io
import os
import re
import subprocess
import sys

import doc_check
import identity_inventory

HERE = os.path.dirname(os.path.abspath(__file__))

#: The repository root, from `src/Fuselage/tools`.
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))

#: Extensions carrying prose or identifiers worth correcting. `.scad` is included because its
#: British spellings are all in comments, checked before this list was written -- no OpenSCAD
#: module or variable name carries one, so no geometry changes.
EXTENSIONS = ('.py', '.scad', '.md', '.txt', '.cfg', '.ini', '.toml', '.yaml', '.yml',
              '.json', '.csv', '.cpp', '.h', '.hpp')

#: Extensionless text files worth checking by name. A dotfile carries prose in its comments --
#: `.gitignore` explained a directory as "hand-modelled" and nothing was looking at it.
BARE_FILES = ('.gitignore', '.gitattributes', '.editorconfig', 'Makefile', 'LICENSE')

#: **Formats whose own vocabulary is British, and must stay that way.** A STEP file declares its
#: units as `SI_UNIT(.MILLI.,.METRE.)`; `.METRE.` is an ISO 10303 enumeration literal, not this
#: project's prose, and Americanizing it would make the file non-conformant and unreadable to
#: every importer. This is an exclusion on correctness grounds, not a deferral.
STANDARD_VOCABULARY = ('.step', '.stp', '.igs', '.iges', '.stl', '.3mf', '.dxf', '.svg')

#: Path fragments never touched, and why each one.
SKIP = (
    'variant_output_original',   # frozen 2025 snapshot; never edited without being asked
    'variant_output',            # generated sweep output
    os.sep + 'out' + os.sep,     # generated measurement artifacts, untracked
    '__pycache__',
    '.pytest_cache',
    'pytest-cache-files',
)

#: `doc/`'s markdown belongs to `doc_check`, which masks code spans so a backticked identifier
#: is never corrected into a reference that does not resolve. Checking it here too would apply
#: the plainer rule to it, so it is left to the tool that knows about spans.
DOC_TREE = 'doc' + os.sep

#: Files whose British spellings are their subject, with the reason stated.
EXEMPT = {
    'doc_check.py': 'its BRITISH dictionary is the list of spellings to detect',
    'source_spelling.py': 'it names the same words to apply them',
    'test_doc_check.py': 'its fixtures assert that British spellings get corrected',
    'test_source_spelling.py': 'same',
}

#: Compound identifiers, renamed as whole tokens. Every entry is a name this project defines --
#: none is an external API, which was checked before the list was written, because renaming a
#: FreeCAD attribute would simply break the call.
RENAMES = {
    '_face_centre': '_face_center',
    '_on_centreline': '_on_centerline',
    'artefact_fraction': 'artifact_fraction',
    'centre_at': 'center_at',
    'centred_frame': 'centered_frame',
    'neighbours_solid': 'neighbors_solid',
    # Test names. They are part of the sentence a failure prints, so they are prose as much as
    # identifiers, and leaving them British would keep the spelling in the test report.
    'test_a_feature_not_centred_on_the_x_axis_is_still_found':
        'test_a_feature_not_centered_on_the_x_axis_is_still_found',
    'test_a_neighbour_returning_an_annulus_means_the_gap_was_the_slicers':
        'test_a_neighbor_returning_an_annulus_means_the_gap_was_the_slicers',
    'test_a_severed_neighbour_does_not_excuse_the_gap':
        'test_a_severed_neighbor_does_not_excuse_the_gap',
    'test_around_is_centred_and_square': 'test_around_is_centered_and_square',
    'test_every_engagement_state_has_a_distinct_colour':
        'test_every_engagement_state_has_a_distinct_color',
    'test_legend_has_one_row_per_labelled_layer_only':
        'test_legend_has_one_row_per_labeled_layer_only',
    'test_mm_switches_to_nanometres_below_a_micron':
        'test_mm_switches_to_nanometers_below_a_micron',
    'test_the_artefact_fraction_is_how_much_refinement_removed':
        'test_the_artifact_fraction_is_how_much_refinement_removed',
    'test_the_artefact_fraction_is_none_when_the_coarse_reading_was_zero':
        'test_the_artifact_fraction_is_none_when_the_coarse_reading_was_zero',
    'test_the_station_itself_does_not_count_as_its_own_neighbour':
        'test_the_station_itself_does_not_count_as_its_own_neighbor',
    'test_thin_stations_keeps_the_last_station_displacing_its_neighbour':
        'test_thin_stations_keeps_the_last_station_displacing_its_neighbor',
    # The `panelled` family, added 2026-11-07 with the dictionary entries that found it. This
    # is the first British spelling in this project to have reached *code* rather than only
    # prose: `is_panelled` was a module-level predicate in `check_drawing.py`, and
    # `unpanelled` a local in four modules and eleven places in one test file. It survived
    # every earlier pass because no pass had the word.
    #
    # None of these is an external API: the predicate is defined and called in
    # `check_drawing.py` alone, and the rest are locals and test names, checked before the
    # list was written for the reason the note above gives.
    'is_panelled': 'is_paneled',
    'unpanelled': 'unpaneled',
    'unpanelled_p': 'unpaneled_p',
    'test_boom_bulkhead_annotations_drops_panel_quantities_when_unpanelled':
        'test_boom_bulkhead_annotations_drops_panel_quantities_when_unpaneled',
    'test_bulkhead_construction_draws_four_panels_when_panelled':
        'test_bulkhead_construction_draws_four_panels_when_paneled',
    'test_bulkhead_views_plan_carries_panel_span_only_when_panelled':
        'test_bulkhead_views_plan_carries_panel_span_only_when_paneled',
    'test_corner_annotations_drops_panel_quantities_when_unpanelled':
        'test_corner_annotations_drops_panel_quantities_when_unpaneled',
    'test_corner_construction_draws_panels_only_when_panelled':
        'test_corner_construction_draws_panels_only_when_paneled',
    'test_check_families_counts_cowl_sets_separately_from_panelled_families':
        'test_check_families_counts_cowl_sets_separately_from_paneled_families',
    'test_scaling_family_of_a_metric_panelled_part':
        'test_scaling_family_of_a_metric_paneled_part',
    'test_scaling_family_of_a_panelled_part_is_u_plus_unit_plus_panel':
        'test_scaling_family_of_a_paneled_part_is_u_plus_unit_plus_panel',
}

BRITISH = doc_check.BRITISH

_WORD = re.compile(r'\b(%s)\b' % '|'.join(sorted(BRITISH)), re.I)
_STEM = re.compile(r'(%s)' % '|'.join(sorted(BRITISH)), re.I)
_TOKEN_CHAR = re.compile(r'[A-Za-z0-9_]')


def _match_case(word, replacement):
    if word.isupper():
        return replacement.upper()
    if word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _token_around(text, start, end):
    """The full identifier-ish token containing `text[start:end]`."""
    lo, hi = start, end
    while lo > 0 and _TOKEN_CHAR.match(text[lo - 1]):
        lo -= 1
    while hi < len(text) and _TOKEN_CHAR.match(text[hi]):
        hi += 1
    return lo, hi, text[lo:hi]


def rename_tokens(text):
    """`(new_text, n)` with every `RENAMES` key replaced as a whole token."""
    n = 0
    for old in sorted(RENAMES, key=len, reverse=True):
        pattern = re.compile(r'\b%s\b' % re.escape(old))
        text, count = pattern.subn(RENAMES[old], text)
        n += count
    return text, n


def fix_words(text):
    """`(new_text, n, leftover)` for standalone British words, case preserved.

    `leftover` lists `(token, offset)` for every British stem sitting inside a longer token that
    `RENAMES` did not cover. Those are **not** changed: a half-renamed identifier is worse than
    a British one, so they are handed back to be looked at.
    """
    out, last, n = [], 0, 0
    leftover = []
    for m in _WORD.finditer(text):
        word = m.group(1)
        if word.lower() not in BRITISH:
            continue
        lo, hi, token = _token_around(text, m.start(), m.end())
        if token != word:
            leftover.append((token, m.start()))
            continue
        out.append(text[last:m.start()])
        out.append(_match_case(word, BRITISH[word.lower()]))
        last = m.end()
        n += 1
    out.append(text[last:])
    # A stem that is not a whole word anywhere -- `millimetres` inside `in_millimetres` -- is
    # found by the stem pass, which the word pass above cannot see.
    joined = ''.join(out)
    for m in _STEM.finditer(joined):
        lo, hi, token = _token_around(joined, m.start(), m.end())
        if token != m.group(1):
            leftover.append((token, m.start()))
    return joined, n, leftover


def fix_text(text):
    """`(new_text, renamed, worded, leftover)` -- the whole repair for one file's contents."""
    text, renamed = rename_tokens(text)
    text, worded, leftover = fix_words(text)
    return text, renamed, worded, leftover


def _wanted(rel, name):
    """Is this tracked path one this module should correct?"""
    if any(frag in os.sep + rel for frag in SKIP):
        return False
    if rel.startswith(DOC_TREE) and name.endswith('.md'):
        return False
    if name in EXEMPT:
        return False
    ext = os.path.splitext(name)[1].lower()
    if ext in STANDARD_VOCABULARY:
        return False
    return ext in EXTENSIONS or name in BARE_FILES


def source_files(root=None):
    """Every file this module is willing to touch, as absolute paths, sorted.

    Driven from `git ls-files` rather than a directory walk, so a tracked file cannot sit
    outside the trees somebody remembered to list. `.gitignore` carried a British spelling for
    exactly that reason: nothing walked the repository root.

    Falls back to walking `src` and `tests` where git is unavailable, so the check still runs.
    """
    root = ROOT if root is None else root
    try:
        listed = subprocess.check_output(['git', 'ls-files'], cwd=root).decode('utf-8').split('\n')
    except Exception:
        listed = []
        for base in ('src', 'tests'):
            top = os.path.join(root, base)
            for dirpath, _dirs, files in os.walk(top):
                for name in files:
                    listed.append(os.path.relpath(os.path.join(dirpath, name),
                                                  root).replace(os.sep, '/'))
    out = []
    for rel in listed:
        if not rel:
            continue
        rel = rel.replace('/', os.sep)
        name = os.path.basename(rel)
        if not _wanted(rel, name):
            continue
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            out.append(path)
    return sorted(out)


def check(root=None):
    """`[(path, n_words, n_renames, leftover)]` for every file that still needs repair."""
    found = []
    for path in source_files(root):
        with io.open(path, 'rb') as fh:
            text = fh.read().decode('utf-8')
        new, renamed, worded, leftover = fix_text(text)
        if renamed or worded or leftover:
            found.append((path, worded, renamed, leftover))
    return found


def fix(root=None):
    """Apply the repair. Returns `[(path, n_words, n_renames, leftover)]` for files changed."""
    changed = []
    for path, worded, renamed, leftover in check(root):
        with io.open(path, 'rb') as fh:
            text = fh.read().decode('utf-8')
        new, _r, _w, _l = fix_text(text)
        if new != text:
            with io.open(path, 'wb') as fh:
                fh.write(new.encode('utf-8'))
        changed.append((path, worded, renamed, leftover))
    return changed


def check_identities(root=None):
    """`[(path, line, token)]` for every source file carrying a contributor's name or address.

    **The other half of `doc_check`'s identity gate, over the tree that gate cannot see.** It
    walks `doc/` only; the rule is absolute and applies to source comments, manifests, `.scad`
    files and test names just as much. The identity list and the exemptions come from
    `doc_check` rather than being restated, the same arrangement `BRITISH` already has, so the
    two halves cannot disagree about what counts as a name.

    An empty identity list means git could not be reached, and that is returned as a finding
    rather than as silence -- a check that did not run must not read as a check that passed.
    """
    names = doc_check.git_identities()
    if not names:
        return [(ROOT, 0, '(could not read any git identity -- this check did NOT run)')]
    # The forge's own addresses are no more personal than a domain name, and they arrive in the
    # identity list only because they appear as a committer on merge commits. Excluding them here
    # is what keeps this half from disagreeing with `identity_inventory`'s, which already holds
    # them out of the rewrite's replacement list for the same reason.
    names = [n for n in names if n.lower() not in identity_inventory.BENIGN_IDENTITY]
    if not names:
        return []
    pattern = re.compile(r'\b(%s)\b' % '|'.join(re.escape(n) for n in names), re.I)
    out = []
    for path in source_files(root):
        if os.path.basename(path) in doc_check.IDENTITY_EXEMPT:
            continue
        with io.open(path, 'rb') as fh:
            text = fh.read().decode('utf-8', 'replace')
        for m in pattern.finditer(text):
            out.append((path, text[:m.start()].count('\n') + 1, m.group(1)))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    identities = check_identities()
    rows = fix() if '--fix' in argv else check()
    words = sum(r[1] for r in rows)
    renames = sum(r[2] for r in rows)
    leftover = [(p, l) for p, _w, _r, ls in rows for l in ls]
    for path, worded, renamed, _ls in rows:
        print('    %-58s %3d word(s)  %2d rename(s)'
              % (os.path.relpath(path, ROOT), worded, renamed))
    print('')
    print('%d file(s), %d word(s), %d identifier rename(s)' % (len(rows), words, renames))
    if leftover:
        print('')
        print('NOT changed -- a British stem inside a longer token with no entry in RENAMES:')
        for path, (token, _off) in sorted(set((p, l) for p, l in leftover)):
            print('    %-58s %s' % (os.path.relpath(path, ROOT), token))

    # **Printed whether or not it found anything**, because "no personal name in the tree" is a
    # result and a missing line is not. `--fix` does not touch these: a name is removed by
    # rewriting the sentence around it, which no substitution table can do.
    print('')
    if identities:
        print('PERSONAL NAMES -- %d, and none of these is fixed automatically:' % len(identities))
        for path, line, token in identities:
            print('    %-58s :%-5s %s' % (os.path.relpath(path, ROOT), line, token))
        print('    Rewrite the sentence instead -- "on direct instruction", "the project '
              'owner", or drop the attribution.')
    else:
        print('personal names in source: 0')

    # **The binary half, which no text gate can see.** `check_identities` above decodes each
    # source file as UTF-8 and matches names in it, which covers prose, code, manifests and test
    # names. A `.blend`'s last-used directory and a PNG's render stamp appear in neither that
    # pass nor `git grep`, so they are scanned as bytes, over every tracked path rather than only
    # the source extensions. Printed unconditionally, for the same reason as the line above.
    embedded = identity_inventory.gate()
    print('')
    if embedded:
        print('EMBEDDED PATHS -- %d across %d tracked file(s):'
              % (len(embedded), len({p for p, _w, _k, _s in embedded})))
        for path, where, kind, text in embedded:
            print('    %-50s :%-6s %-13s %s' % (path, where, kind, text[:60]))
        print('    Use src/Fuselage/tools/strip_embedded_paths.py for a binary; rewrite the '
              'line for a text file.')
    else:
        print('embedded paths in tracked files: 0')

    return 1 if ((rows and '--fix' not in argv) or identities or embedded) else 0


if __name__ == '__main__':
    sys.exit(main())
