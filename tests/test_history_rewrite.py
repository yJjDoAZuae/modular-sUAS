"""Tests for `history_rewrite`, the specification the history rewrite runs from.

Every fixture is invented. The identifiers this tool removes must not appear in the repository,
including in a test, so the names and the host here have the shape of the real thing without
being it.

**The tests that matter most are the ones about over-matching.** A rule that misses something
leaves an identifier in history, which is the failure everyone expects. A rule that matches too
much is worse and less obvious: it silently rewrites source code. Two real near-misses are pinned
below -- host discovery reading a regex word boundary as a UNC host, which would have substituted
a placeholder into this project's own regex literals, and a share-name class accepting a bare
ellipsis, which turned "the rest is elided" into a claim about a share by that name.
"""
import os

import history_rewrite as hr
import path_fixtures as fx
import pytest

NAMES = ['Thingummy Whatsit', 'Thingummy', 'Whatsit', 'thingummy@nowhere.test', 'nowhere']
HOSTS = [fx.HOST_ALT]


def table():
    return hr.rules(names=NAMES, hosts=HOSTS)


class TestRuleOrderingPutsTheLongestContextFirst:
    def test_the_address_is_replaced_before_the_name_inside_it(self):
        out, n = hr.apply_text(b'mail thingummy@nowhere.test now', table())
        assert out == b'mail ' + hr.EMAIL + b' now'
        assert n == 1

    def test_a_full_name_becomes_one_placeholder_not_two(self):
        out, _n = hr.apply_text(b'decided by Thingummy Whatsit today', table())
        assert out == b'decided by ' + hr.USER + b' today'

    def test_each_name_part_alone_is_still_replaced(self):
        for part in (b'Thingummy', b'Whatsit'):
            out, _n = hr.apply_text(b'by ' + part + b' today', table())
            assert out == b'by ' + hr.USER + b' today'

    def test_the_domain_gets_its_own_placeholder(self):
        """Decided from the address itself: a token after the `@` is a domain, not a person."""
        out, _n = hr.apply_text(b'the nowhere org', table())
        assert out == b'the ' + hr.DOMAIN + b' org'

    def test_host_and_share_are_replaced_together(self):
        out, _n = hr.apply_text(fx.UNC_ALT, table())
        assert out == rb'on \\<server>\<share>\proj here'

    def test_the_extended_length_form_is_handled(self):
        out, _n = hr.apply_text(fx.UNC_ALT_EXT, table())
        assert rb'\\?\UNC\<server>\<share>' in out

    def test_the_forward_slash_spelling_is_handled(self):
        out, _n = hr.apply_text(fx.UNC_ALT_FWD, table())
        assert b'//<server>/<share>' in out

    def test_a_bare_host_is_replaced_too(self):
        out, _n = hr.apply_text(b'the hostbox machine', table())
        assert out == b'the ' + hr.SERVER + b' machine'


class TestTheRulesDoNotOverMatch:
    """Over-matching rewrites real content. These are the cases that nearly shipped."""

    def test_an_elided_path_keeps_its_ellipsis(self):
        r"""`\\host\...` means the rest was elided. A share class accepting a bare `...` turned
        that into `\\<server>\<share>`, asserting a share by that name."""
        out, _n = hr.apply_text(rb'a share (`\\hostbox\...`) fails', table())
        assert out == rb'a share (`\\<server>\...`) fails'

    def test_a_longer_token_containing_a_name_is_untouched(self):
        for word in (b'Thingummyish', b'unWhatsit', b'nowhereness'):
            out, n = hr.apply_text(b'x ' + word + b' y', table())
            assert n == 0, word
            assert out == b'x ' + word + b' y'

    def test_clean_text_is_returned_unchanged(self):
        data = b'an ordinary line with no identifier in it'
        out, n = hr.apply_text(data, table())
        assert n == 0 and out == data

    def test_the_rules_do_not_alter_this_project_s_own_regex_literals(self):
        r"""The real near-miss. Loose host discovery read `\\bwidget\b` as host `bwidget`, which
        would have produced a rule substituting `<server>` into a regex literal in live source."""
        src = (rb"BRITISH = re.compile(rb'\\bwidget\\b')" + b'\n'
               + rb"OTHER = re.compile(rb'\\bwidget_total\\b')")
        out, n = hr.apply_text(src, table())
        assert n == 0
        assert out == src


class TestHostDiscoveryIsStrict:
    def test_a_regex_word_boundary_is_not_a_host(self):
        for esc in (rb'"\\bwidget\b"', rb'"\\bwidget_total\\b"'):
            for pattern in hr.HOST_STRICT:
                assert not pattern.findall(esc), esc

    def test_a_real_unc_path_yields_its_host(self):
        got = [m for p in hr.HOST_STRICT for m in p.findall(fx.UNC_ALT_PATH)]
        assert got == [b'hostbox']

    def test_the_extended_form_yields_its_host(self):
        got = [m for p in hr.HOST_STRICT for m in p.findall(fx.UNC_ALT_EXT)]
        assert got == [b'hostbox']

    def test_discovery_uses_no_forward_slash_pattern(self):
        """Base64 is built from an alphabet containing `/`, so a `//token/token/` shape matches
        encoded data constantly -- it produced 1 771 bogus host rules over this object store.
        A backslash cannot occur in base64 at all."""
        for pattern in hr.HOST_STRICT:
            assert b'//' not in pattern.pattern

    def test_base64_yields_no_host(self):
        blob = fx.BASE64_RUN
        for pattern in hr.HOST_STRICT:
            assert not pattern.findall(blob)


class TestBinariesTakeTheOtherPath:
    def test_a_png_is_dispatched_to_the_lossless_cleaner(self):
        import struct
        import zlib

        def chunk(name, payload):
            body = name + payload
            return (struct.pack('>I', len(payload)) + body
                    + struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF))

        png = (b'\x89PNG\r\n\x1a\n'
               + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0))
               + chunk(b'tEXt', rb'File' + b'\x00' + fx.UNC_ALT_BLEND)
               + chunk(b'IDAT', zlib.compress(b'\x00\x80'))
               + chunk(b'IEND', b''))
        new, changed = hr.clean(png, table())
        assert changed
        assert b'hostbox' not in new
        assert hr.sep.png_idat(new) == hr.sep.png_idat(png)

    def test_text_goes_through_substitution_not_the_cleaner(self):
        new, changed = hr.clean(b'by Thingummy here', table())
        assert changed and new == b'by ' + hr.USER + b' here'

    def test_an_unmatched_binary_is_left_alone(self):
        png = b'\x89PNG\r\n\x1a\n' + b'nothing parseable here'
        new, changed = hr.clean(png, table())
        assert not changed and new == png


class TestTheApplyGuardRefusesTheLiveRepository:
    def test_the_live_repo_is_refused_by_path(self):
        with pytest.raises(SystemExit, match='refusing to rewrite the live repository'):
            hr.apply_to(hr.ROOT, table())

    def test_the_guard_is_case_insensitive_about_the_path(self):
        """Windows paths differ in case without differing in identity."""
        with pytest.raises(SystemExit, match='refusing'):
            hr.apply_to(os.path.abspath(hr.ROOT).upper(), table())


class TestRemovalsAndRedactions:
    """Two cases where substituting a string is the wrong instrument: the content itself is the
    problem, so there is nothing to replace.

    The targets are read from an untracked local file rather than written into the module, so
    these tests supply their own synthetic ones. That is not only for isolation -- a committed
    test naming a removed path names it just as effectively as a committed list would."""

    DIRECTIVES = ('# a comment, ignored\n'
                  'remove: doc/somewhere/gone.md\n'
                  r'redact: ^\| \[gone\.md\].*\|[ \t]*$\n?' + '\n'
                  '\n'
                  'a line with no directive on it\n')

    ROW = b'| [gone.md](gone.md) | A plan that restated what it should not have. | Draft |\n'
    OTHER = (b'| [geometry_bridge.md](geometry_bridge.md) | The adaptation library that lets '
             b'pytest drive FreeCAD. | Active |\n')

    @pytest.fixture
    def targets(self, tmp_path):
        (tmp_path / hr.TARGETS_FILE).write_text(self.DIRECTIVES, encoding='utf-8')
        return hr.load_targets(str(tmp_path))

    def test_an_absent_file_means_no_removals_at_all(self, tmp_path):
        """The safe default. A removal is a deliberate, named act and must never happen because
        a tool defaulted to it."""
        assert hr.load_targets(str(tmp_path)) == ((), ())

    def test_the_removal_list_holds_bytes_not_strings(self, targets):
        """`commit.file_changes` filenames are bytes; a str entry would silently never match."""
        removals, _red = targets
        assert removals == (b'doc/somewhere/gone.md',)
        assert all(isinstance(p, bytes) for p in removals)

    def test_comments_and_junk_lines_are_ignored(self, targets):
        removals, redactions = targets
        assert len(removals) == 1 and len(redactions) == 1

    def test_a_redaction_removes_the_matching_row(self, targets):
        _rm, redactions = targets
        out, _n = hr.apply_text(self.ROW, list(redactions))
        assert out == b''

    def test_other_rows_survive(self, targets):
        """The redaction is anchored on the link text, which is what made the row that row."""
        _rm, redactions = targets
        out, n = hr.apply_text(self.OTHER, list(redactions))
        assert n == 0 and out == self.OTHER

    def test_the_surrounding_file_is_untouched(self, targets):
        _rm, redactions = targets
        doc = b'# Index\n\n| Plan | Scope | Status |\n' + self.OTHER + self.ROW + b'\nTail.\n'
        out, _n = hr.apply_text(doc, list(redactions))
        assert self.OTHER in out
        assert b'gone.md' not in out
        assert out.startswith(b'# Index\n')
        assert out.endswith(b'\nTail.\n')

    def test_prose_naming_the_file_is_not_a_table_row(self, targets):
        """Line-anchored on a table row, so a rule this blunt still only does what it says."""
        _rm, redactions = targets
        _out, n = hr.apply_text(b'Something once called gone.md its own thing.\n',
                                list(redactions))
        assert n == 0

    def test_the_module_itself_names_no_target(self):
        """The whole reason the targets are external: a committed module listing removed paths
        tells a reader exactly what to go looking for in an archived copy.

        Checked against whatever targets are actually configured, never against a literal -- an
        assertion spelling a path out would name it exactly as effectively as the list did, and
        this test would then be the leak it exists to prevent."""
        import inspect
        source = inspect.getsource(hr)
        assert 'PATH_REMOVALS' not in source
        for path in hr.load_targets()[0]:
            stem = os.path.basename(path.decode('utf-8')).rsplit('.', 1)[0]
            assert stem not in source, 'the module names a removed path'


class TestTheResiduePatternCoversEveryRule:
    def test_it_matches_anything_the_table_would_replace(self):
        residue = hr._residue_pattern(table())
        for sample in (b'thingummy@nowhere.test', b'Thingummy', b'Whatsit',
                       fx.UNC_ALT_SHORT, b'hostbox'):
            assert residue.search(sample), sample

    def test_it_does_not_match_clean_text(self):
        residue = hr._residue_pattern(table())
        assert not residue.search(b'a wholly unremarkable line')

    def test_the_placeholders_are_recognized_as_benign_by_the_gate(self):
        """Otherwise the gate would flag the rewrite's own output as a finding."""
        for placeholder in (hr.USER, hr.SERVER, hr.SHARE):
            assert hr.inv.BENIGN.search(placeholder), placeholder


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
