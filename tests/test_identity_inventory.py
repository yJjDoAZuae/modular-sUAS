"""Tests for `identity_inventory`, the object-store scanner that finds what no list contains.

Every sample here is invented. The strings this tool hunts must not appear in this repository,
including in a test, so the fixtures use a made-up host and a made-up account that have the
*shape* of the real thing without being it.

The test that matters most is the escaping one. The `unc` shape originally shipped with eight
backslashes in a raw bytes literal where the regex engine needed four, so it could not match any
real path and reported a confident zero -- a list-driven blind spot arriving in the very tool
built to avoid them. Nothing about that failure was visible from the output: zero matches reads
exactly like a clean repository. So each shape is now pinned against a known-positive sample.
"""
import re

import identity_inventory as inv
import path_fixtures as fx
import pytest

#: Samples with the shape of the real thing, from the one exempt module that may hold them. See
#: `tests/path_fixtures.py` for why they live there rather than inline.
UNC = fx.UNC
UNC_DOUBLED = fx.UNC_DOUBLED
UNC_EXT = fx.UNC_EXT
UNC_FWD = fx.UNC_FWD
PROFILE = fx.PROFILE
DRIVE = fx.DRIVE
POSIX = fx.POSIX


def shape(name):
    return dict(inv.SHAPES)[name]


class TestEveryShapeMatchesAKnownPositive:
    """The regression suite for the escaping class of bug. A shape that matches nothing is
    indistinguishable from a clean repository, so each one is pinned to a sample."""

    def test_the_unc_shape_matches_a_real_unc_path(self):
        got = shape('unc').findall(UNC)
        assert got, 'the unc shape matched nothing; check the backslash escaping'
        assert got[0].startswith(rb'\\hostname')

    def test_the_unc_shape_matches_the_doubled_form_source_code_uses(self):
        assert shape('unc').search(UNC_DOUBLED) is not None

    def test_the_extended_length_form_has_its_own_shape(self):
        got = shape('unc_extended').findall(UNC_EXT)
        assert got and got[0].startswith(rb'\\?\UNC\hostname')

    def test_the_extended_form_is_not_also_caught_by_the_plain_unc_shape(self):
        """They are different prefixes; conflating them would miscount both."""
        assert shape('unc').search(rb'\\?\UNC\hostname\x') is None

    def test_the_user_profile_shape_matches(self):
        got = shape('user_profile').findall(PROFILE)
        assert got and b'someacct' in got[0]

    def test_the_drive_shape_matches_a_mapped_drive_path(self):
        got = shape('drive').findall(DRIVE)
        assert got and got[0].startswith(rb'R:\someacct')

    def test_the_posix_home_shape_matches_both_spellings(self):
        got = shape('posix_home').findall(POSIX)
        assert len(got) == 2

    def test_no_shape_is_an_empty_pattern(self):
        """A shape that matched everything would be as useless as one that matched nothing."""
        for name, pat in inv.SHAPES:
            assert pat.search(b'ordinary prose with no path in it at all') is None, name


class TestTheBenignFilterDropsWhatIsAlreadyFixed:
    def test_an_anonymized_profile_path_is_benign(self):
        assert inv.BENIGN.search(rb'C:\Users\<user>\AppData') is not None

    def test_a_placeholder_share_root_is_benign(self):
        assert inv.BENIGN.search(rb'\\<server>\<share>\proj') is not None

    def test_a_url_is_not_a_drive_letter(self):
        assert inv.BENIGN.search(rb'https://example.com/x') is not None

    def test_a_real_path_is_not_benign(self):
        assert inv.BENIGN.search(PROFILE) is None


class TestHostDiscoveryFeedsTheSecondPass:
    def test_a_host_is_recovered_from_a_unc_path(self):
        assert b'hostname' in inv.hosts_in(UNC)

    def test_a_host_is_recovered_from_the_extended_form(self):
        assert b'hostname' in inv.hosts_in(UNC_EXT)

    def test_single_character_captures_are_dropped(self):
        """Escape sequences in source produce one-character captures that are not hosts."""
        assert inv.hosts_in(rb'"a\\b\\c"') == set()

    def test_the_forward_slash_pattern_is_none_without_hosts(self):
        """No discovered host means no second pass, rather than a pattern matching anything."""
        assert inv.forward_slash_pattern(set()) is None

    def test_the_forward_slash_pattern_finds_the_split_argument_spelling(self):
        """`os.path.join('//host', 'Archive', ...)` leaves the host alone in the literal, with no
        trailing slash. Requiring one missed this form entirely."""
        pat = inv.forward_slash_pattern({b'hostname'})
        assert pat.findall(UNC_FWD) == [b'//hostname']

    def test_the_forward_slash_pattern_also_finds_the_whole_path_spelling(self):
        pat = inv.forward_slash_pattern({b'hostname'})
        got = pat.findall(rb"sys.path.insert(0, '//hostname/Archive/proj/src')")
        assert got and got[0] == b'//hostname/Archive/proj/src'

    def test_the_forward_slash_pattern_ignores_an_unrelated_host(self):
        """The converse: the second pass is targeted, not a general `//` sweep. This is what
        keeps base64 payloads -- which are full of `//token/token` -- out of the report."""
        pat = inv.forward_slash_pattern({b'hostname'})
        assert pat.search(rb'//Kd5usbVFZq75Gxw6J17Ive4c2spwv2LrN1Mlsf/93hVVsHk9') is None


class TestTheDeclaredIdentityIsExcludedFromTheScrubList:
    """The pseudonym every commit is authored as must never reach a replacement list, or the
    rewrite destroys the authorship the project chose on purpose."""

    def test_the_forge_addresses_are_treated_as_non_personal(self):
        assert 'noreply@github.com' in inv.BENIGN_IDENTITY

    def test_a_declared_name_is_removed_from_the_scrub_set(self, monkeypatch):
        monkeypatch.setattr(inv.doc_check, 'git_identities',
                            lambda root=None: ['Pseudo', 'RealName'])
        monkeypatch.setattr(inv, 'declared_identity', lambda: {'Pseudo'})
        scrub_pat, declared_pat, scrub, declared = inv.identity_patterns()
        assert scrub == ['RealName']
        assert 'Pseudo' in declared
        assert scrub_pat.search(b'by RealName here') is not None
        assert scrub_pat.search(b'by Pseudo here') is None
        assert declared_pat.search(b'by Pseudo here') is not None

    def test_everything_declared_means_nothing_to_scrub(self, monkeypatch):
        monkeypatch.setattr(inv.doc_check, 'git_identities', lambda root=None: ['Pseudo'])
        monkeypatch.setattr(inv, 'declared_identity', lambda: {'Pseudo'})
        scrub_pat, _declared_pat, scrub, _declared = inv.identity_patterns()
        assert scrub == []
        assert scrub_pat is None


class TestScanBlobLabelsAndExpands:
    def test_a_finding_carries_its_shape_name(self):
        hits = inv.scan_blob(PROFILE, None)
        assert {k for k, _s, _w in hits} <= {n for n, _p in inv.SHAPES}
        assert 'user_profile' in {k for k, _s, _w in hits}

    def test_the_surrounding_string_is_the_whole_run_not_the_match(self):
        data = b'\x00\x00' + DRIVE + b'\x00\x00'
        hits = inv.scan_blob(data, None)
        assert any(b'use <R:' in whole for _k, _s, whole in hits)

    def test_an_identity_pattern_is_applied_when_given(self):
        ident = re.compile(rb'\b(RealName)\b', re.I)
        hits = inv.scan_blob(b'decided by RealName on a date', ident)
        assert [k for k, _s, _w in hits] == ['identity']

    def test_clean_text_yields_nothing(self):
        assert inv.scan_blob(b'a wholly unremarkable line of prose', None) == []

    def test_expand_stops_at_non_printable_bytes(self):
        data = b'\x00' + DRIVE + b'\x00'
        assert inv.expand(data, 5) == DRIVE


class TestTheReportIsSafeByConstruction:
    def test_the_header_warns_against_committing_it(self):
        assert 'DO NOT COMMIT' in inv.HEADER

    def test_the_report_filename_is_covered_by_gitignore(self):
        """The file is generated full of forbidden strings; the ignore rule is not optional."""
        import os
        root = inv.ROOT
        with open(os.path.join(root, '.gitignore'), encoding='utf-8') as fh:
            rules = fh.read()
        assert inv.REPORT in rules or '*.local.txt' in rules

    def test_the_report_separates_the_keep_list(self):
        import collections
        result = {'blobs_scanned': 1, 'blobs_total': 1, 'orphan_blobs': 0, 'identities': [],
                  'declared': ['Pseudo'], 'strings': collections.Counter(),
                  'kinds': collections.Counter(), 'hosts': [], 'paths': {},
                  'orphan_only': collections.Counter(),
                  'commit_metadata': collections.Counter(),
                  'declared_in_metadata': collections.Counter()}
        text = inv.report(result)
        assert 'DO NOT put any of this in a replacement list' in text
        assert 'keep  Pseudo' in text


class TestTheFixtureExemptionIsSafe:
    """`path_fixtures.py` is exempt from the identity gate so it can hold real-looking paths.
    That exemption is only safe while every token in it is invented, so this asserts it rather
    than trusting the comment -- an exemption nothing checks is how a real path would get in."""

    def test_no_fixture_token_is_a_real_identity(self):
        _sp, _dp, names, declared = inv.identity_patterns()
        known = {n.lower() for n in names} | {d.lower() for d in declared}
        for token in fx.tokens():
            assert token.lower() not in known, token

    def test_no_fixture_token_shares_text_with_a_real_identity(self):
        """A token need not match exactly to leak: one appearing inside a real name would do."""
        _sp, _dp, names, _declared = inv.identity_patterns()
        for token in fx.tokens():
            for real in names:
                assert token.lower() not in real.lower(), (token, 'inside an identity')
                assert real.lower() not in token.lower(), (token, 'contains an identity')

    def test_no_fixture_token_is_a_host_this_repository_knows(self):
        """Hosts are discovered structurally from the object store, so this is checked against
        what is really in the repository rather than against a list."""
        import history_rewrite as hr
        hosts = {h.lower() for h in hr._discover_hosts()}
        for token in fx.tokens():
            assert token.lower() not in hosts, token

    def test_the_fixtures_module_is_the_only_exempt_source_file(self):
        """The hole stays narrow: one named file, not a category."""
        exempt = [k for k in inv.doc_check.IDENTITY_EXEMPT if k.endswith('.py')]
        assert exempt == ['path_fixtures.py']

    def test_the_exemption_carries_a_reason(self):
        assert inv.doc_check.IDENTITY_EXEMPT['path_fixtures.py'].strip()


class TestTheGateIsNarrowerThanTheInventory:
    """The inventory optimizes recall and a person reads it. The gate runs unattended, so a false
    positive makes it something to be bypassed. These pin the difference."""

    def test_a_name_is_always_gate_worthy(self):
        assert inv.gate_worthy('identity', b'RealName', b'by RealName here')

    def test_a_user_profile_path_is_gate_worthy(self):
        m = fx.PROFILE_DOCS
        assert inv.gate_worthy('user_profile', m, m)

    def test_a_bare_drive_path_is_not(self):
        """`C:\\does\\not\\exist\\x.exe` in a test and `C:/path/without/extension` in a docstring
        are fabricated examples carrying nobody's identity. The guideline's scope is a path
        *beneath a user profile*; a drive path that does name someone is caught as an identity."""
        m = rb'C:\does\not\exist\freecadcmd.exe'
        assert not inv.gate_worthy('drive', m, m)

    def test_an_already_anonymized_path_is_not(self):
        """The whole run has to be inspected, not the match: the shape stops at `<`, so only the
        surrounding string reveals the placeholder."""
        whole = rb'C:\Users\<user>\AppData\Local'
        assert not inv.gate_worthy('user_profile', b'C:\\Users\\', whole)

    def test_an_elided_path_is_not(self):
        whole = rb'\\?\UNC\<server>\<share>\...\python.exe'
        assert not inv.gate_worthy('unc_extended', whole, whole)

    def test_a_system_location_is_not(self):
        m = rb'\\host\Program Files\OpenVSP\python'
        assert not inv.gate_worthy('unc', m, m)

    def test_a_short_match_is_not(self):
        assert not inv.gate_worthy('unc', rb'\\a\b', rb'\\a\b')

    def test_a_posix_home_path_is_gate_worthy(self):
        m = fx.POSIX_HOME
        assert inv.gate_worthy('posix_home', m, m)

    def test_a_single_separator_is_not(self):
        """One separator is the signature of coincidence rather than a path -- `P:/` and `;\\J\\`
        were both reported out of compressed image data."""
        assert not inv.gate_worthy('unc_fwd', rb'//hostabc', rb'//hostabc')

    def test_a_regex_word_boundary_is_not_a_unc_path(self):
        r"""A source file can contain `\\bwidget\b` and `\\bwidget_total\\b`, and the `unc`
        shape reads the escape as a host plus a one-character share. This is the converse that
        decides how the plausibility rule is written."""
        for esc in (rb'\\bwidget\b', rb'\\bwidget_total\\b'):
            assert not inv.gate_worthy('unc', esc, esc), esc

    def test_a_plausible_unc_path_is_gate_worthy(self):
        m = fx.UNC_BLEND
        assert inv.gate_worthy('unc', m, m)

    def test_the_gate_fails_closed_when_git_lists_nothing(self, monkeypatch):
        """A check that did not run must not read as a check that passed."""
        monkeypatch.setattr(inv, 'tracked_files', lambda root=None: [])
        found = inv.gate()
        assert len(found) == 1
        assert found[0][2] == 'not-run'
        assert 'not' in found[0][3] and 'clean' in found[0][3]

    def test_every_gate_kind_is_a_real_shape_or_identity(self):
        """A typo in GATE_KINDS would silently disable a whole class of finding."""
        known = {n for n, _p in inv.SHAPES} | {'identity', 'unc_fwd'}
        assert set(inv.GATE_KINDS) <= known

    def test_the_gate_covers_every_tracked_path_not_just_source_extensions(self):
        """The binary half exists precisely because the text gates walk extensions."""
        paths = inv.tracked_files()
        assert any(p.endswith('.blend') for p in paths)
        assert any(p.endswith('.png') for p in paths)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
