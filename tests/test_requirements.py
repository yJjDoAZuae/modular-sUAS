"""IP-TEST-3 (doc/implementation/test_coverage.md): tests for requirements.py.

IP-FC-91's requirement register already checks itself thoroughly -- `check_register()` and
`check_document()` -- what was missing is that nothing ran those checks as part of the
committed test suite; `python requirements.py` had to be invoked by hand. The real-data
tests below are that wiring. The synthetic-register tests go further: they prove
`check_register()` actually detects each class of defect it claims to (a dangling citation,
a citation to a disallowed tier, missing rationale, missing source, a verifier file that
does not exist) by monkeypatching in a small broken register, rather than trusting that the
real register passing means the checker works -- a checker that always says "ok" would pass
the real-data tests too.

Adoption-phase retrofit (general.md's TDD section).
"""
import requirements as rq

# ------------------------------------------------------------
# Requirement.derived
# ------------------------------------------------------------

def test_requirement_derived_is_true_only_when_cites_is_empty():
    assert rq.Requirement('x', cites=()).derived is True
    assert rq.Requirement('x', cites=('AR-OBJ-1',)).derived is False


# ------------------------------------------------------------
# resolve / order
# ------------------------------------------------------------

def test_resolve_finds_an_architecture_and_a_design_requirement():
    assert rq.resolve('AR-OBJ-1') == rq.ARCHITECTURE['AR-OBJ-1']
    assert rq.resolve('DES-1') is rq.DESIGN['DES-1']


def test_resolve_returns_none_for_an_unknown_id():
    assert rq.resolve('DES-9999') is None


def test_order_sorts_by_the_trailing_number_not_lexically():
    ids = sorted(['DES-1', 'DES-10', 'DES-2', 'DES-9'], key=rq.order)
    assert ids == ['DES-1', 'DES-2', 'DES-9', 'DES-10']


# ------------------------------------------------------------
# check_register / check_document -- wired against the real register and the real document,
# the same assertion main() already prints as "ok".
# ------------------------------------------------------------

def test_check_register_has_no_defects_against_the_real_register():
    complaints, _notes = rq.check_register()
    assert complaints == []


def test_check_document_agrees_with_system_requirements_md():
    assert rq.check_document() == []


def test_document_path_exists():
    """check_document()'s own first check -- pinned separately because an empty complaint
    list from a missing file (an early return, not "everything matched") would read as a
    false pass if this were the only test of the document check."""
    from pathlib import Path
    assert Path(rq.DOCUMENT).exists()


# ------------------------------------------------------------
# coverage -- which architectural requirements are reached, and by what
# ------------------------------------------------------------

def test_coverage_lists_every_architecture_id_including_unreached_ones():
    reached = rq.coverage()
    assert set(reached) == set(rq.ARCHITECTURE)


def test_coverage_counts_a_real_known_citation():
    # DES-1 cites AR-MOD-8 and AR-MOD-10 -- see the DESIGN table.
    reached = rq.coverage()
    assert 'DES-1' in reached['AR-MOD-8']
    assert 'DES-1' in reached['AR-MOD-10']


# ------------------------------------------------------------
# check_register's defect detection -- proven against a small synthetic, broken register
# rather than trusted because the real one happens to pass.
# ------------------------------------------------------------

def _install_synthetic_register(monkeypatch, architecture, design, other_tier, prefix):
    """Swaps in a minimal register: ARCHITECTURE plus one other tier (DES or a tier below
    it), so check_register()'s tier-specific rules (DES may cite nothing; everything below
    DES may not) can be exercised one at a time without dragging in the real ~50 entries."""
    monkeypatch.setattr(rq, 'ARCHITECTURE', architecture)
    monkeypatch.setattr(rq, 'DESIGN', design)
    registers = [('DES', design)]
    if prefix != 'DES':
        registers.append((prefix, other_tier))
    monkeypatch.setattr(rq, 'REGISTERS', tuple(registers))


def test_check_register_flags_a_citation_that_resolves_to_nothing(monkeypatch):
    design = {'DES-1': rq.Requirement('x', cites=('AR-DOES-NOT-EXIST',), verifier='review',
                                      source='s')}
    _install_synthetic_register(monkeypatch, {'AR-OBJ-1': 'y'}, design, {}, 'DES')

    complaints, _notes = rq.check_register()

    assert any('AR-DOES-NOT-EXIST' in c and 'not a requirement' in c for c in complaints)


def test_check_register_flags_a_citation_to_a_disallowed_tier(monkeypatch):
    """A DRW requirement citing another DRW requirement: PARENTS['DRW'] only allows DES/AR,
    so this must be flagged even though the cited id resolves to something real."""
    design = {'DES-1': rq.Requirement('x', cites=('AR-OBJ-1',), verifier='review', source='s')}
    drw = {'DRW-1': rq.Requirement('y', cites=('DRW-2',), verifier='review', source='s'),
           'DRW-2': rq.Requirement('z', cites=('DES-1',), verifier='review', source='s')}
    _install_synthetic_register(monkeypatch, {'AR-OBJ-1': 'a'}, design, drw, 'DRW')

    complaints, _notes = rq.check_register()

    assert any('DRW-1' in c and 'DRW-2' in c and 'not a tier' in c for c in complaints)


def test_check_register_flags_a_below_design_requirement_that_cites_nothing(monkeypatch):
    design = {'DES-1': rq.Requirement('x', cites=('AR-OBJ-1',), verifier='review', source='s')}
    drw = {'DRW-1': rq.Requirement('y', cites=(), verifier='review', source='s')}
    _install_synthetic_register(monkeypatch, {'AR-OBJ-1': 'a'}, design, drw, 'DRW')

    complaints, _notes = rq.check_register()

    assert any('DRW-1' in c and 'cites nothing' in c for c in complaints)


def test_check_register_flags_a_design_requirement_with_no_citation_and_no_rationale(
        monkeypatch):
    design = {'DES-1': rq.Requirement('x', cites=(), rationale=None, verifier='review',
                                      source='s')}
    _install_synthetic_register(monkeypatch, {}, design, {}, 'DES')

    complaints, _notes = rq.check_register()

    assert any('DES-1' in c and 'no rationale' in c for c in complaints)


def test_check_register_allows_a_design_requirement_with_no_citation_but_a_rationale(
        monkeypatch):
    design = {'DES-1': rq.Requirement('x', cites=(), rationale='because', verifier='review',
                                      source='s')}
    _install_synthetic_register(monkeypatch, {}, design, {}, 'DES')

    complaints, _notes = rq.check_register()

    assert complaints == []


def test_check_register_flags_a_requirement_with_no_source(monkeypatch):
    design = {'DES-1': rq.Requirement('x', cites=(), rationale='because', verifier='review',
                                      source=None)}
    _install_synthetic_register(monkeypatch, {}, design, {}, 'DES')

    complaints, _notes = rq.check_register()

    assert any('DES-1' in c and 'no source' in c for c in complaints)


def test_check_register_flags_a_verifier_path_that_does_not_exist(monkeypatch):
    design = {'DES-1': rq.Requirement('x', cites=(), rationale='because',
                                      verifier='src/Fuselage/tools/not_a_real_file.py',
                                      source='s')}
    _install_synthetic_register(monkeypatch, {}, design, {}, 'DES')

    complaints, _notes = rq.check_register()

    assert any('DES-1' in c and 'not in the repository' in c for c in complaints)


def test_check_register_notes_a_level_skip_without_treating_it_as_a_complaint(monkeypatch):
    """A DRW citing AR directly is a level skip -- reported as a note, not a defect, per the
    module's own docstring."""
    design = {}
    drw = {'DRW-1': rq.Requirement('y', cites=('AR-OBJ-1',), verifier='review', source='s')}
    _install_synthetic_register(monkeypatch, {'AR-OBJ-1': 'a'}, design, drw, 'DRW')

    complaints, notes = rq.check_register()

    assert complaints == []
    assert any('DRW-1' in n and 'skipping the design tier' in n for n in notes)


def test_check_register_notes_a_requirement_verified_by_nothing(monkeypatch):
    design = {'DES-1': rq.Requirement('x', cites=(), rationale='because', verifier=None,
                                      source='s')}
    _install_synthetic_register(monkeypatch, {}, design, {}, 'DES')

    complaints, notes = rq.check_register()

    assert complaints == []
    assert any('DES-1' in n and 'verified by nothing' in n for n in notes)
