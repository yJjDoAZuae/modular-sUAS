"""Tests for doc_check.py, the documentation's structural checker.

**Every test below is a trap this checker actually fell into**, which is why they are worth
keeping. The checker was written against the real documents, and its first three runs reported
confident nonsense: `OQ-DES-CW32` as resolved because its *title* contains the word "fixed", four
dangling references that were deliberate rename notes, and an ordering violation between
`OQ-DES-SR1` and `OQ-DES-D10`, which are different series. A checker that cries wolf stops being
read, so each of those rules is pinned here against a synthetic page rather than against the
tree -- the real documents change every week, and a test that asserts on them would be a test of
today's content.

The tree is also checked as a whole, in `test_the_real_documentation_tree_is_consistent`, which
is the one assertion that will fail when a document drifts.
"""
import io
import os

import doc_check as dc
import pytest


def page(text, rel='design/thing.md'):
    """One synthetic page, as `read_pages` would have produced it."""
    return dc.Page(rel, os.path.join(dc.DOC, rel), text)


def pages_of(*texts):
    """`{rel: Page}` from `(rel, text)` pairs."""
    return dict((rel, page(text, rel)) for rel, text in texts)


# ------------------------------------------------------------
# slug -- GitHub's anchor rule
# ------------------------------------------------------------

def test_slug_keeps_underscores_because_github_does():
    # Stripping them broke every `WALL_TOL` and `__file__` anchor in the tree.
    assert dc.slug('`WALL_TOL` and `__file__`') == 'wall_tol-and-__file__'


def test_slug_leaves_a_double_hyphen_where_an_em_dash_was():
    # The em dash drops out and the two spaces that surrounded it each become a hyphen.
    assert dc.slug('6.3 Rib-cut clearance — what it does not') == \
        '63-rib-cut-clearance--what-it-does-not'


def test_slug_lowercases_and_drops_punctuation():
    assert dc.slug('Is It? Yes!') == 'is-it-yes'


# ------------------------------------------------------------
# strip_code -- prose checks must not read identifiers
# ------------------------------------------------------------

def test_strip_code_blanks_spans_but_keeps_line_numbers():
    text = 'one\n`a_british_artefact_name` two\nthree'
    out = dc.strip_code(text)
    assert 'a_british_artefact_name' not in out
    assert out.count('\n') == text.count('\n')


def test_strip_code_blanks_fenced_blocks():
    assert 'behaviour' not in dc.strip_code('a\n```\nbehaviour\n```\nb')


# ------------------------------------------------------------
# open_questions -- the two declaration forms, and what closes one
# ------------------------------------------------------------

def test_a_heading_declares_an_open_question():
    oqs = dc.open_questions(page('### OQ-DES-X1 — Something undecided\n'))
    assert oqs == {'OQ-DES-X1': (1, True)}


def test_a_capitalized_marker_closes_it():
    oqs = dc.open_questions(page('### OQ-DES-X1 — Something — RESOLVED 2026-01-01\n'))
    assert oqs['OQ-DES-X1'][1] is False


def test_the_word_fixed_in_a_title_does_not_close_it():
    # The bug this pins: OQ-DES-CW32's own title says the facet count "is fixed", and a
    # case-insensitive match read that as a closure marker, reported the question resolved, and
    # then reported every work item blocked on it as blocked on nothing.
    oqs = dc.open_questions(page('### OQ-DES-X1 — The facet count is fixed, and it binds\n'))
    assert oqs['OQ-DES-X1'][1] is True


def test_a_capitalized_fixed_marker_does_close_it():
    oqs = dc.open_questions(page('### OQ-DES-X1 — Wrong argument order — FIXED 2026-01-01\n'))
    assert oqs['OQ-DES-X1'][1] is False


def test_a_bold_lead_declares_one_too():
    # bulkhead.md and corner.md predate the heading convention and use this form.
    oqs = dc.open_questions(page('**OQ-DES-X2 — What sets this? — RESOLVED 2026-01-01.**\n'))
    assert oqs == {'OQ-DES-X2': (1, False)}


def test_a_bold_lead_reads_its_whole_paragraph_for_the_marker():
    oqs = dc.open_questions(page('**OQ-DES-X2 — What sets this?\nsecond line — RESOLVED.**\n'))
    assert oqs['OQ-DES-X2'][1] is False


def test_a_sentence_about_a_question_is_not_a_declaration():
    # `**OQ-DES-CW26 stays open, because ...` is commentary in an implementation plan. Reading
    # it as a declaration asked that plan for an open-question summary table.
    assert dc.open_questions(page('**OQ-DES-X3 stays open, because it is a choice.**\n')) == {}


def test_a_parenthesized_second_record_is_not_a_second_declaration():
    text = ('### OQ-ARCH-10 — What replaces it? — WITHDRAWN 2026-01-01\n\n'
            '### OQ-ARCH-10 (as originally posed) — kept for the alternatives\n')
    oqs = dc.open_questions(page(text))
    assert oqs['OQ-ARCH-10'] == (1, False)


def test_a_real_second_declaration_is_reported_as_a_duplicate():
    p = page('### OQ-DES-X1 — First\n\n### OQ-DES-X1 — Again\n')
    dc.open_questions(p)
    assert p.duplicate_declarations == [('OQ-DES-X1', 3)]


# ------------------------------------------------------------
# _oq_series -- the letters belong to the name, not the number
# ------------------------------------------------------------

def test_series_letters_are_part_of_the_series_not_the_number():
    assert dc._oq_series('OQ-DES-CW26') == ('OQ-DES-CW', 26)
    assert dc._oq_series('OQ-DES-SR1') == ('OQ-DES-SR', 1)
    assert dc._oq_series('OQ-DES-D10') == ('OQ-DES-D', 10)


def test_two_series_on_one_page_are_ordered_independently():
    # SR1 after D10 is not a violation: they are different questions in different series.
    text = '| OQ-DES-D10 |\n| OQ-DES-SR1 |\n### OQ-DES-D10 — a\n### OQ-DES-SR1 — b\n'
    assert dc.check_open_questions(pages_of(('design/t.md', text))) == []


def test_a_descending_number_within_one_series_is_a_violation():
    text = '| OQ-DES-X1 |\n| OQ-DES-X4 |\n### OQ-DES-X4 — a\n### OQ-DES-X1 — b\n'
    found = dc.check_open_questions(pages_of(('design/t.md', text)))
    assert [f.check for f in found] == ['oq-order']
    assert 'OQ-DES-X1 follows OQ-DES-X4' in found[0].detail


# ------------------------------------------------------------
# the summary-table convention
# ------------------------------------------------------------

def test_an_open_question_missing_from_the_table_is_reported():
    text = '| OQ-DES-X1 |\n### OQ-DES-X1 — a\n### OQ-DES-X2 — b\n'
    found = dc.check_open_questions(pages_of(('design/t.md', text)))
    assert len(found) == 1 and 'OQ-DES-X2 is open and missing' in found[0].detail


def test_a_closed_question_left_in_the_table_is_reported():
    text = '| OQ-DES-X1 |\n| OQ-DES-X2 |\n### OQ-DES-X1 — a\n### OQ-DES-X2 — b — DECIDED\n'
    found = dc.check_open_questions(pages_of(('design/t.md', text)))
    assert len(found) == 1 and 'OQ-DES-X2 is closed and still' in found[0].detail


def test_a_table_row_with_no_subsection_is_reported():
    text = '| OQ-DES-X1 |\n| OQ-DES-X9 |\n### OQ-DES-X1 — a\n'
    found = dc.check_open_questions(pages_of(('design/t.md', text)))
    assert len(found) == 1 and 'OQ-DES-X9 is in the summary table with no' in found[0].detail


def test_a_page_with_no_table_is_reported_once_not_once_per_question():
    text = '### OQ-DES-X1 — a\n### OQ-DES-X2 — b\n### OQ-DES-X3 — c — DECIDED\n'
    found = dc.check_open_questions(pages_of(('design/t.md', text)))
    assert len(found) == 1
    assert 'keeps no summary table' in found[0].detail
    assert 'OQ-DES-X1, OQ-DES-X2' in found[0].detail and 'X3' not in found[0].detail


def test_a_page_whose_questions_are_all_closed_needs_no_table():
    assert dc.check_open_questions(
        pages_of(('design/t.md', '### OQ-DES-X1 — a — DECIDED 2026-01-01\n'))) == []


# ------------------------------------------------------------
# links and images
# ------------------------------------------------------------

def test_a_cross_document_anchor_must_exist():
    tree = pages_of(('design/a.md', '[x](b.md#gone)\n'), ('design/b.md', '## Here\n'))
    found = dc.check_links(tree)
    assert len(found) == 1 and 'no such heading: b.md#gone' in found[0].detail


def test_a_resolving_cross_document_anchor_is_silent():
    tree = pages_of(('design/a.md', '[x](b.md#here)\n'), ('design/b.md', '## Here\n'))
    assert dc.check_links(tree) == []


def test_a_same_page_anchor_is_checked_too():
    found = dc.check_links(pages_of(('design/a.md', '[x](#nope)\n\n## Yes\n')))
    assert len(found) == 1 and 'no such heading on this page: #nope' in found[0].detail


def test_a_relative_path_resolves_from_the_linking_page():
    tree = pages_of(('implementation/p.md', '[x](../design/b.md#here)\n'),
                    ('design/b.md', '## Here\n'))
    assert dc.check_links(tree) == []


def test_an_http_link_is_left_alone():
    assert dc.check_links(pages_of(('design/a.md', '[x](https://e.com/p#frag)\n'))) == []


# ------------------------------------------------------------
# work items
# ------------------------------------------------------------

PLAN = 'implementation/plan.md'


def test_work_item_columns_are_read_from_both_ends():
    # A title legitimately contains a pipe, inside a nested table or a code span. Counting
    # columns from the left would then read the title as the dependency column.
    p = page('| IP-X-2 | todo | a | b | title with | a pipe | IP-X-1 | [r](r.md) |\n', PLAN)
    assert dc.work_items(p) == [('IP-X-2', 'todo', 'IP-X-1', 1)]


def test_a_blocked_item_must_name_what_blocks_it_in_the_status_cell():
    text = '| IP-X-1 | blocked | t | — | [r](r.md) |\n'
    found = dc.check_plans(pages_of((PLAN, text)))
    assert any('no ids in the status cell' in f.detail for f in found)


def test_a_blocked_item_needs_a_reason_note():
    text = ('| IP-X-1 | todo | t | — | [r](r.md) |\n'
            '| IP-X-2 | blocked (IP-X-1) | t | — | [r](r.md) |\n')
    found = dc.check_plans(pages_of((PLAN, text)))
    assert [f.detail for f in found] == ['IP-X-2 is blocked with no blocked-reason note']


def test_a_reason_note_satisfies_it():
    text = ('| IP-X-1 | todo | t | — | [r](r.md) |\n'
            '| IP-X-2 | blocked (IP-X-1) | t | — | [r](r.md) |\n\n'
            '> **IP-X-2 blocked reason:** because.\n')
    assert dc.check_plans(pages_of((PLAN, text))) == []


def test_blocking_on_a_resolved_question_is_reported():
    # The check that goes stale the moment a question is answered, and the one most worth running.
    tree = pages_of((PLAN, '| IP-X-1 | blocked (OQ-DES-X1) | t | — | [r](r.md) |\n\n'
                           '> **IP-X-1 blocked reason:** because.\n'),
                    ('design/d.md', '### OQ-DES-X1 — a — RESOLVED 2026-01-01\n'))
    found = dc.check_plans(tree)
    assert any('blocked on OQ-DES-X1, which is already resolved' in f.detail for f in found)


def test_blocking_on_an_open_question_is_silent():
    tree = pages_of((PLAN, '| IP-X-1 | blocked (OQ-DES-X1) | t | — | [r](r.md) |\n\n'
                           '> **IP-X-1 blocked reason:** because.\n'),
                    ('design/d.md', '| OQ-DES-X1 |\n### OQ-DES-X1 — a\n'))
    assert dc.check_plans(tree) == []


def test_blocking_on_a_question_that_does_not_exist_is_reported():
    tree = pages_of((PLAN, '| IP-X-1 | blocked (OQ-DES-X9) | t | — | [r](r.md) |\n\n'
                           '> **IP-X-1 blocked reason:** because.\n'))
    found = dc.check_plans(tree)
    assert any('blocked on OQ-DES-X9, which does not exist' in f.detail for f in found)


def test_a_dependency_on_a_missing_item_is_reported():
    text = '| IP-X-1 | todo | t | IP-X-9 | [r](r.md) |\n'
    found = dc.check_plans(pages_of((PLAN, text)))
    assert any('depends on IP-X-9, which does not exist' in f.detail for f in found)


def test_an_item_standing_before_its_dependency_is_reported():
    # Both ends unfinished, which is the only case where the ordering still means anything --
    # see test_ordering_is_not_checked_once_either_end_is_finished.
    text = ('| IP-X-1 | todo | t | IP-X-2 | [r](r.md) |\n'
            '| IP-X-2 | todo | t | — | [r](r.md) |\n')
    found = dc.check_plans(pages_of((PLAN, text)))
    assert [f.check for f in found] == ['topo']


def test_a_cross_plan_dependency_is_not_an_ordering_violation():
    # Two plans have no order relative to each other, so only same-plan rows are compared.
    tree = pages_of((PLAN, '| IP-X-1 | todo | t | IP-Y-1 | [r](r.md) |\n'),
                    ('implementation/other.md', '| IP-Y-1 | done | t | — | [r](r.md) |\n'))
    assert dc.check_plans(tree) == []


def test_the_header_count_must_match_the_table():
    text = ('**Status, 2026-01-01: 2 items done, 0 `todo`, 0 blocked.**\n\n'
            '| IP-X-1 | done | t | — | [r](r.md) |\n')
    found = dc.check_plans(pages_of((PLAN, text)))
    assert any('header says 2 done / 0 todo / 0 blocked; the table has 1 / 0 / 0' in f.detail
               for f in found)


def test_a_matching_header_count_is_silent():
    text = ('**Status, 2026-01-01: 1 items done, 0 `todo`, 0 blocked.**\n\n'
            '| IP-X-1 | done | t | — | [r](r.md) |\n')
    assert dc.check_plans(pages_of((PLAN, text))) == []


def test_a_status_outside_the_vocabulary_is_reported():
    # `in progress` and `done (residue in IP-FC-115, ...)` were both in the tree. A status that
    # is a sentence cannot be counted, which is what the header-count check needs it for.
    text = '| IP-X-1 | in progress | t | — | [r](r.md) |\n'
    found = dc.check_plans(pages_of((PLAN, text)))
    assert any("has status 'in progress'" in f.detail for f in found)


@pytest.mark.parametrize('status', ['todo', 'active', 'done', 'superseded', 'withdrawn',
                                    'blocked (IP-X-2)'])
def test_every_vocabulary_status_is_accepted(status):
    text = ('| IP-X-1 | %s | t | — | [r](r.md) |\n'
            '| IP-X-2 | todo | t | — | [r](r.md) |\n\n'
            '> **IP-X-1 blocked reason:** because.\n' % status)
    assert [f for f in dc.check_plans(pages_of((PLAN, text))) if f.check == 'status'] == []


def test_blocking_on_a_finished_item_is_reported():
    text = ('| IP-X-1 | blocked (IP-X-2) | t | — | [r](r.md) |\n'
            '| IP-X-2 | done | t | — | [r](r.md) |\n\n'
            '> **IP-X-1 blocked reason:** because.\n')
    found = dc.check_plans(pages_of((PLAN, text)))
    assert any('blocked on IP-X-2, which is already done' in f.detail for f in found)


def test_ordering_is_not_checked_once_either_end_is_finished():
    # A done item's position is history, and a dependency that is already done is satisfied
    # wherever it sits. Re-sorting those rows would churn a long table to no effect.
    done_item = ('| IP-X-1 | done | t | IP-X-2 | [r](r.md) |\n'
                 '| IP-X-2 | todo | t | — | [r](r.md) |\n')
    done_dep = ('| IP-X-1 | todo | t | IP-X-2 | [r](r.md) |\n'
                '| IP-X-2 | done | t | — | [r](r.md) |\n')
    assert dc.check_plans(pages_of((PLAN, done_item))) == []
    assert dc.check_plans(pages_of((PLAN, done_dep))) == []


# ------------------------------------------------------------
# the legacy full-register schema
# ------------------------------------------------------------

REGISTER = ('| ID | Status | Question |\n| --- | --- | --- |\n'
            '| B1 | resolved 2026-08-06 | What sets it? |\n'
            '| B2 | **open** | Should it be split? |\n\n'
            '### OQ-DES-B1 — What sets it? — RESOLVED 2026-08-06\n'
            '### OQ-DES-B2 — Should it be split?\n')


def test_a_legacy_register_lists_resolved_questions_without_complaint():
    # The current rule -- the table holds only open questions -- would report every resolved row
    # of a full register as "closed and still in the summary table", which is it working.
    assert dc.check_open_questions(pages_of(('design/b.md', REGISTER))) == []


def test_a_short_form_id_in_a_register_resolves():
    # `bulkhead.md` writes `B14` and the architecture document writes `ARCH-21`.
    schema, rows = dc.summary_rows(page(REGISTER, 'design/b.md'),
                                   {'OQ-DES-B1': (0, False), 'OQ-DES-B2': (0, True)})
    assert schema == 'status'
    assert [r[0] for r in rows] == ['OQ-DES-B1', 'OQ-DES-B2']


def test_a_register_status_disagreeing_with_the_declaration_is_reported():
    # The real case: bulkhead.md's register said B14 was resolved and implemented while its own
    # heading carried no closing marker at all.
    text = REGISTER.replace('### OQ-DES-B1 — What sets it? — RESOLVED 2026-08-06',
                            '### OQ-DES-B1 — What sets it?')
    found = dc.check_open_questions(pages_of(('design/b.md', text)))
    assert len(found) == 1
    assert 'carries no closing marker' in found[0].detail


def test_a_question_missing_from_a_register_is_reported():
    text = REGISTER + '### OQ-DES-B3 — A third one — DECIDED 2026-08-08\n'
    found = dc.check_open_questions(pages_of(('design/b.md', text)))
    assert len(found) == 1 and 'OQ-DES-B3 is missing from the register' in found[0].detail


def test_a_bare_number_does_not_alias_a_question_id():
    # OQ-ARCH-1's bare suffix is `1`, and matching it picked up the first column of every
    # unrelated numbered table on the page.
    assert '1' not in dc._id_aliases('OQ-ARCH-1')
    assert 'ARCH-1' in dc._id_aliases('OQ-ARCH-1')
    assert 'B14' in dc._id_aliases('OQ-DES-B14')


# ------------------------------------------------------------
# fix_spelling
# ------------------------------------------------------------

def test_fix_spelling_corrects_prose_and_counts_it():
    assert dc.fix_spelling('the behaviour here') == ('the behavior here', 1)


def test_fix_spelling_preserves_case():
    assert dc.fix_spelling('Behaviour and ARTEFACT')[0] == 'Behavior and ARTIFACT'


def test_fix_spelling_leaves_code_spans_alone():
    assert dc.fix_spelling('`a_british_artefact_name` here') == (
        '`a_british_artefact_name` here', 0)


def test_fix_spelling_handles_compounds_a_word_boundary_misses():
    # There is no boundary before the `metre` in `millimetre`, so the compounds are listed
    # individually and this is what pins that.
    assert dc.fix_spelling('24 millimetres')[0] == '24 millimeters'
    assert dc.fix_spelling('a nanometre')[0] == 'a nanometer'


def test_fix_spelling_is_idempotent():
    once, _n = dc.fix_spelling('the behaviour was centred on millimetres')
    assert dc.fix_spelling(once) == (once, 0)


# ------------------------------------------------------------
# references and retired series
# ------------------------------------------------------------

def test_a_reference_to_a_nonexistent_work_item_is_reported():
    found = dc.check_references(pages_of(('design/a.md', 'see IP-X-9 for that\n')))
    assert len(found) == 1 and 'IP-X-9 is referenced' in found[0].detail


def test_a_reference_to_a_nonexistent_question_is_reported():
    found = dc.check_references(pages_of(('design/a.md', 'see OQ-DES-X9\n')))
    assert len(found) == 1 and 'OQ-DES-X9 is referenced' in found[0].detail


def test_a_retired_series_is_named_freely_once_the_rename_is_declared():
    # A rename note can only be written with the old id in it. Without the marker, those
    # sentences read as dangling references forever.
    text = ('<!-- doc_check: retired-series OQ-DES-DV -> OQ-DES-DB -->\n'
            '`OQ-DES-DV3` is now `OQ-DES-DB3`.\n\n'
            '| OQ-DES-DB3 |\n### OQ-DES-DB3 — a\n')
    assert dc.check_references(pages_of(('design/a.md', text))) == []


def test_the_retirement_marker_is_read_from_anywhere_in_the_tree():
    tree = pages_of(('design/a.md',
                     '<!-- doc_check: retired-series OQ-DES-DV -> OQ-DES-DB -->\n'),
                    ('design/b.md', 'history: OQ-DES-DV7 became OQ-DES-DB7\n'),
                    ('design/c.md', '| OQ-DES-DB7 |\n### OQ-DES-DB7 — a\n'))
    assert dc.check_references(tree) == []


# ------------------------------------------------------------
# spelling
# ------------------------------------------------------------

def test_a_british_spelling_in_prose_is_reported():
    found = dc.check_spelling(pages_of(('design/a.md', 'the behaviour was centred\n')))
    assert sorted(f.detail for f in found) == ['behaviour -- use behavior',
                                               'centred -- use centered']


def test_a_british_spelling_inside_a_code_span_is_left_alone():
    # A name in backticks is a reference to code, so correcting it here would make the document
    # cite a symbol that does not exist. Renaming the symbol is `source_spelling.py`'s job, and
    # it shares this dictionary so the two cannot disagree.
    assert dc.check_spelling(pages_of(('design/a.md', 'see `a_british_artefact_name`\n'))) == []


def test_american_prose_is_silent():
    assert dc.check_spelling(pages_of(('design/a.md', 'the behavior was centered\n'))) == []


# ------------------------------------------------------------
# the real tree
# ------------------------------------------------------------

def test_the_real_documentation_tree_is_consistent():
    """Every structural invariant, against the documents as they stand.

    This is the assertion that fails when a document drifts -- a question closed without its
    summary row removed, a work item blocked on something already decided, an anchor pointing at
    a renamed heading. The failure message lists what to fix.
    """
    found = dc.run()
    assert not found, '%d finding(s):\n%s' % (len(found), '\n'.join(repr(f) for f in found))


def test_every_markdown_page_is_readable_as_utf8():
    for rel, p in sorted(dc.read_pages().items()):
        with io.open(p.path, encoding='utf-8') as fh:
            assert fh.read() == p.text, rel
