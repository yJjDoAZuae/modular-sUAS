"""Tests for source_spelling.py, which applies the American-English rule to the code.

**The rule that matters here is the one about compounds.** A word-boundary replacement cannot
reach the `centre` in `_face_centre`, which is the safe direction -- it means no identifier is
ever half-renamed. So every compound the project holds is listed in `RENAMES` and applied as a
whole token, and anything carrying a British stem inside a longer token with no entry is
*reported instead of changed*. The tests below pin both halves of that, because the failure mode
they prevent is a rename that reaches a definition and not its call sites.

`test_the_source_tree_is_american` is the assertion that fails when new British prose or a new
British identifier lands.
"""
import os

import pytest
import source_spelling as ss


# ------------------------------------------------------------
# the word pass
# ------------------------------------------------------------

def test_a_standalone_british_word_is_corrected():
    assert ss.fix_words('the behaviour here')[:2] == ('the behavior here', 1)


def test_case_is_preserved():
    assert ss.fix_words('Behaviour and ARTEFACT')[0] == 'Behavior and ARTIFACT'


def test_american_prose_is_untouched():
    assert ss.fix_words('the behavior here') == ('the behavior here', 0, [])


def test_a_compound_is_not_half_renamed_by_the_word_pass():
    # There is no word boundary before the `centre` in `_face_centre`, and that is what keeps a
    # bare replacement from producing `_face_center` in one file and leaving it in another.
    text = 'x = some_unlisted_centre_thing'
    out, n, leftover = ss.fix_words(text)
    assert out == text and n == 0
    assert [t for t, _o in leftover] == ['some_unlisted_centre_thing']


def test_an_unlisted_compound_is_reported_not_changed():
    _out, _n, leftover = ss.fix_words('def in_millimetres(x): pass')
    assert [t for t, _o in leftover] == ['in_millimetres']


# ------------------------------------------------------------
# the rename pass
# ------------------------------------------------------------

def test_a_listed_compound_is_renamed_as_a_whole_token():
    assert ss.rename_tokens('artefact_fraction(rows)') == ('artifact_fraction(rows)', 1)


def test_a_rename_reaches_every_occurrence_in_the_text():
    text = 'def artefact_fraction(r):\n    return artefact_fraction(r)\n'
    out, n = ss.rename_tokens(text)
    assert n == 2 and 'artefact_fraction' not in out


def test_a_rename_does_not_fire_inside_a_longer_name():
    # `\\bartefact_fraction\\b` must not match `my_artefact_fraction_cache`.
    text = 'my_artefact_fraction_cache = 1'
    assert ss.rename_tokens(text) == (text, 0)


def test_renames_are_applied_longest_first():
    # A short key that is a prefix of a long one must not corrupt the long one.
    long_name = 'test_the_artefact_fraction_is_how_much_refinement_removed'
    out, _n = ss.rename_tokens('def %s():' % long_name)
    assert out == 'def %s():' % ss.RENAMES[long_name]


def test_no_rename_maps_a_name_onto_an_existing_different_name():
    assert len(set(ss.RENAMES.values())) == len(ss.RENAMES)
    assert not set(ss.RENAMES) & set(ss.RENAMES.values())


def test_every_rename_actually_changes_the_name():
    for old, new in ss.RENAMES.items():
        assert old != new


def test_every_rename_target_is_american():
    for new in ss.RENAMES.values():
        out, n, _l = ss.fix_words(new.replace('_', ' '))
        assert n == 0, '%s still reads British' % new


# ------------------------------------------------------------
# fix_text, the whole repair
# ------------------------------------------------------------

def test_fix_text_renames_then_corrects_prose():
    text = '# the centred artefact_fraction behaviour\nartefact_fraction()\n'
    out, renamed, worded, leftover = ss.fix_text(text)
    assert renamed == 2
    assert 'artefact_fraction' not in out
    assert 'centered' in out and 'behavior' in out
    assert leftover == []


def test_fix_text_is_idempotent():
    once, _r, _w, _l = ss.fix_text('# the behaviour of artefact_fraction\n')
    twice, renamed, worded, leftover = ss.fix_text(once)
    assert twice == once and renamed == 0 and worded == 0 and leftover == []


# ------------------------------------------------------------
# which files are in scope
# ------------------------------------------------------------

def test_the_spelling_checkers_own_files_are_exempt():
    # Spell-correcting a spelling checker's dictionary deletes the checker.
    assert 'doc_check.py' in ss.EXEMPT
    assert 'source_spelling.py' in ss.EXEMPT
    assert 'test_doc_check.py' in ss.EXEMPT
    names = [os.path.basename(p) for p in ss.source_files()]
    for exempt in ss.EXEMPT:
        assert exempt not in names


def test_the_frozen_snapshot_is_never_walked():
    # variant_output_original is a frozen 2025 snapshot and is not edited without being asked.
    assert 'variant_output_original' in ss.SKIP
    assert not [p for p in ss.source_files() if 'variant_output_original' in p]


def test_generated_output_is_not_walked():
    assert not [p for p in ss.source_files() if (os.sep + 'out' + os.sep) in p]


def test_the_inherited_docs_are_walked_after_all():
    # They describe a different repository, which is a reason not to trust them as evidence --
    # not a reason to leave a tracked file reading British. They were skipped once and that is
    # where one of the last two occurrences in the whole repository was hiding.
    assert [p for p in ss.source_files() if (os.sep + 'docs' + os.sep) in p]


def test_a_standards_format_keeps_its_own_vocabulary():
    # A STEP file declares `SI_UNIT(.MILLI.,.METRE.)`. `.METRE.` is an ISO 10303 enumeration
    # literal; correcting it would make the file non-conformant. This is the one exclusion that
    # is about correctness rather than about scope.
    assert '.step' in ss.STANDARD_VOCABULARY
    assert not [p for p in ss.source_files()
                if os.path.splitext(p)[1].lower() in ss.STANDARD_VOCABULARY]


def test_every_file_walked_is_wanted_by_extension_or_by_name():
    for p in ss.source_files():
        name = os.path.basename(p)
        ext = os.path.splitext(name)[1].lower()
        assert ext in ss.EXTENSIONS or name in ss.BARE_FILES, p


def test_dotfiles_are_covered_because_nothing_walked_the_repository_root():
    # `.gitignore` described a directory as "hand-modelled" and no directory walk reached it.
    assert '.gitignore' in ss.BARE_FILES
    assert [p for p in ss.source_files() if os.path.basename(p) == '.gitignore']


def test_the_doc_tree_is_left_to_doc_check():
    # doc_check masks markdown code spans, so a backticked identifier is never corrected into a
    # reference that does not resolve. The plainer rule here would not know to do that.
    assert not [p for p in ss.source_files()
                if (os.sep + 'doc' + os.sep) in p and (os.sep + 'src' + os.sep) not in p
                and p.endswith('.md')]


def test_the_dictionary_is_shared_with_doc_check():
    import doc_check
    assert ss.BRITISH is doc_check.BRITISH


def test_no_dictionary_entry_maps_a_word_to_itself():
    # A self-mapping would make the check report a file as needing repair forever.
    assert [k for k, v in ss.BRITISH.items() if k == v] == []


# ------------------------------------------------------------
# the real tree
# ------------------------------------------------------------

def test_the_source_tree_is_american():
    """Every file in scope, as it stands. Fails when new British prose or an identifier lands."""
    rows = ss.check()
    assert not rows, '%d file(s) need repair:\n%s' % (
        len(rows), '\n'.join('    %s  %d word(s), %d rename(s), leftover=%s'
                             % (os.path.relpath(p, ss.ROOT), w, r, [t for t, _o in l])
                             for p, w, r, l in rows))
