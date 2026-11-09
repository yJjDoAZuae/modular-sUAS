"""The history rewrite's specification: what gets replaced, and the proof that it was.

**Why this is a module and not a `--replace-text` file.** `git filter-repo --replace-text` reads
a file of `regex:...==>replacement` lines, which means every pattern is hand-escaped text in a
format nothing checks. That is exactly where a rule under-matches without saying so, and a rule
that under-matches is indistinguishable from a clean result: zero replacements and nothing to
replace produce the same output. This project has already been bitten by that shape of bug in a
pattern written with eight backslashes where the regex engine needed four, which matched nothing
and reported a confident zero.

So the rules are built in Python, where they can be unit-tested against known-positive samples,
and the rewrite runs through a callback rather than a replacement list.

**The rules are derived, not authored.** The identities come from
`identity_inventory.identity_patterns`, which reads every git config scope plus the history's own
authors, and which separates out the *declared* pseudonym so the rewrite cannot destroy the
authorship this project chose on purpose.

**Binaries are not text-substituted.** A `.blend` stores length-prefixed blocks, so a
substitution that changes length invalidates every offset after it. Those blobs go through
`strip_embedded_paths`, which is length-neutral for a `.blend` and drops a whole chunk for a PNG.

    python history_rewrite.py --plan                  # print the rules, change nothing
    python history_rewrite.py --audit                 # what WOULD change, across every object
    python history_rewrite.py --apply <clone-path>    # rewrite that clone, never this repo
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import identity_inventory as inv  # noqa: E402
import strip_embedded_paths as sep  # noqa: E402

ROOT = inv.ROOT

#: What each class of identifier becomes. These match the placeholders already adopted in the
#: working tree, so a rewritten historical file reads the same way the current one does -- and
#: `identity_inventory.BENIGN` already recognizes them, so the gate does not then flag its own
#: replacement as a finding.
USER = b'<user>'
EMAIL = b'<email>'
DOMAIN = b'<domain>'
SERVER = b'<server>'
SHARE = b'<share>'


#: Where the removal and redaction targets are read from. Ignored, and absent by default.
#:
#: **Substitution is the wrong instrument when the content itself is the problem.** A file whose
#: *subject* is sensitive carries no forbidden identifier -- the gate passes on it -- and there is
#: no string to replace. It has to leave history entirely. A passage inside a file that must stay
#: is the same case at smaller scale: the passage goes, the file remains.
#:
#: **But a committed list of such targets names them.** A reader would learn exactly which path
#: was removed and could go looking for it in an archived copy, which is most of what removing it
#: was for. So this module carries the mechanism and a local file carries the targets -- the same
#: split the identity inventory uses for its measured string list, and for the same reason.
#:
#: Format, one directive per line, `#` for comments:
#:
#:     remove: <path/in/the/repository>
#:     redact: <python regex, multiline, replaced with nothing>
#:
#: With no such file the rewrite performs identity replacement only, which is the right default:
#: a removal is always a deliberate, named act and should never happen because a tool defaulted
#: to it.
TARGETS_FILE = 'history_rewrite_targets.local.txt'


def load_targets(root=None):
    """`(path_removals, redactions)` from `TARGETS_FILE`, or two empty tuples if it is absent."""
    path = os.path.join(root or ROOT, TARGETS_FILE)
    if not os.path.exists(path):
        return (), ()
    removals, redactions = [], []
    with open(path, encoding='utf-8') as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            key, _, value = line.partition(':')
            key, value = key.strip(), value.strip()
            if key == 'remove' and value:
                removals.append(value.encode('utf-8'))
            elif key == 'redact' and value:
                redactions.append((re.compile(value.encode('utf-8'), re.M), b''))
    return tuple(removals), tuple(redactions)


def _host_rules(hosts):
    """Host rules, longest-context first so a share name is consumed before the bare host.

    Order matters and the ordering is not cosmetic. `\\\\host\\Archive\\...` must become
    `\\<server>\\<share>\\...` in one step; if the bare host were replaced first, the share name
    would be left stranded next to a placeholder and a second rule would have to recognize that
    hybrid. Anchoring the share to the host is also what keeps the word out of ordinary prose --
    an unanchored rule would rewrite every sentence containing it.
    """
    # A share name has to start with an alphanumeric. Without that floor the class accepts a
    # bare `...`, and documentation reading `\\host\...` -- where the ellipsis means the rest was
    # elided -- comes out as `\\<server>\<share>`, asserting a share by that name. The bare-host
    # rule below then handles such a case correctly on its own, leaving `\\<server>\...` intact.
    share = rb'[A-Za-z0-9][A-Za-z0-9._-]*'
    out = []
    for host in sorted(hosts, key=len, reverse=True):
        h = re.escape(host.encode('latin-1') if isinstance(host, str) else host)
        out.append((re.compile(rb'\\\\\?\\UNC\\' + h + rb'\\' + share, re.I),
                    rb'\\\\?\\UNC\\' + SERVER + rb'\\' + SHARE))
        out.append((re.compile(rb'\\\\' + h + rb'\\' + share, re.I),
                    rb'\\\\' + SERVER + rb'\\' + SHARE))
        out.append((re.compile(rb'//' + h + rb'/' + share, re.I),
                    b'//' + SERVER + b'/' + SHARE))
        out.append((re.compile(rb'\b' + h + rb'\b', re.I), SERVER))
    return out


def rules(names=None, hosts=None, redactions=None):
    """`[(compiled_pattern, replacement)]`, in the order they must be applied.

    Full name before either part of it, address before the domain inside it, host-plus-share
    before the bare host. Every rule is word-bounded or punctuation-anchored, so none of them can
    reach inside a longer token.
    """
    if names is None:
        _scrub_pat, _decl_pat, names, _declared = inv.identity_patterns()
    if hosts is None:
        hosts = [h for h in _discover_hosts()]

    emails = sorted((n for n in names if '@' in n), key=len, reverse=True)
    words = sorted((n for n in names if '@' not in n), key=len, reverse=True)

    out = []
    # An address first: it contains the domain and often the given name, and replacing either of
    # those first would leave a mangled address behind rather than remove it.
    for e in emails:
        out.append((re.compile(re.escape(e.encode('latin-1')), re.I), EMAIL))
    # Then any multi-word run of the name parts, so "First Last" becomes one placeholder rather
    # than two side by side.
    for a in words:
        for b in words:
            if a.lower() != b.lower():
                out.append((re.compile(rb'\b' + re.escape(a.encode('latin-1')) + rb'\s+'
                                       + re.escape(b.encode('latin-1')) + rb'\b', re.I), USER))
    out.extend(_host_rules(hosts))
    out.extend(load_targets()[1] if redactions is None else redactions)
    for w in words:
        wb = re.escape(w.encode('latin-1'))
        repl = DOMAIN if _looks_like_domain(w, emails) else USER
        out.append((re.compile(rb'\b' + wb + rb'\b', re.I), repl))
    return out


def _looks_like_domain(word, emails):
    """Is this token the domain part of an address rather than a person's name?

    Decided from the addresses themselves rather than from a list: a token appearing after the
    `@` of a known address is a domain, and one appearing before it is not. Taking the addresses
    as an argument keeps this answerable without reading git, which is what lets it be tested.
    """
    return any(word.lower() in e.split('@', 1)[1].lower() for e in emails if '@' in e)


#: A UNC host, discovered strictly enough that a regex escape is not mistaken for one.
#:
#: Two mistakes are possible here and both are serious. Discovering a host too loosely invents a
#: rule that rewrites real source: a source file can contain `\\bwidget\b` and
#: `\\bwidget_total\\b`, and a loose pattern reads those as a host followed by a
#: one-character share -- which would then produce a rule substituting `<server>` into a regex
#: literal. Discovering too narrowly misses a share and leaves it in history.
#:
#: Requiring **host, then a share of at least two characters, then another separator** separates
#: them on structure alone: a real share path has depth, and `\b` does not.
#: **Discovery uses the backslash form only.** The forward-slash spelling `//host/share/` cannot
#: be discovered structurally, because base64 is built from an alphabet that includes `/` and
#: nothing else, so encoded data is wall-to-wall `//token/token/`. Asking for it directly
#: produced **1 771** rules over this object store, essentially all of them random base64 runs
#: promoted to hostnames -- and a bogus host rule does not merely add noise, it substitutes
#: `<server>` into whatever that string really was.
#:
#: A backslash cannot occur in base64 at all, so the backslash form is unambiguous. The
#: forward-slash rule is then generated per discovered host, which is the same
#: discover-then-target split the inventory uses.
HOST_STRICT = (
    re.compile(rb'\\\\(?:\?\\UNC\\)?([A-Za-z0-9._-]{3,30})\\[A-Za-z0-9._-]{2,}\\'),
)


def _discover_hosts(progress=None):
    """The UNC hosts, discovered over **the object store** rather than the working tree.

    Scanning the working tree would be the wrong source and would fail silently: the tracked
    files have already been cleaned, so the hostname survives only in history -- which is exactly
    what the rewrite is for. A discovery pass that reads the current checkout therefore returns
    nothing and produces a rule set with no host rule in it at all, while looking complete.
    """
    found = set()

    # **Reachable blobs only, and both halves of that matter.**
    #
    # Scanning the whole object store also reads blobs no ref points at: the previous rewrite's
    # orphans, and -- less obviously -- whatever is sitting in the index from a `git add` that
    # has not been committed. A host found only in those produces a rule with nothing to apply
    # to, because `filter-repo` rewrites refs; worse, it makes discovery depend on staging state,
    # so the same repository yields different rules before and after an unrelated `git add`.
    #
    # Blobs living only at an identity-exempt path are skipped for a second, separate reason.
    # `tests/path_fixtures.py` holds deliberately invented hosts so the pattern tests have
    # something real-looking to match. Scanning it discovers those hosts and promotes them to
    # rewrite rules -- the fixtures would manufacture the very hosts they stand in for.
    reachable, exempt = set(), set()
    for line in inv.git('rev-list', '--objects', '--all').split(b'\n'):
        if len(line) > 41:
            sha = line[:40].decode('latin-1')
            reachable.add(sha)
            if os.path.basename(line[41:].decode('utf-8', 'replace')) \
                    in inv.doc_check.IDENTITY_EXEMPT:
                exempt.add(sha)
            else:
                exempt.discard(sha)      # also lives at a path that is not exempt
    blobs = [(s, n) for s, n in inv.all_blobs() if s in reachable and s not in exempt]

    proc = inv.blob_reader()
    try:
        for i, (sha, _size) in enumerate(blobs):
            data = inv.read_one(proc, sha)
            if data is None:
                continue
            for pattern in HOST_STRICT:
                for m in pattern.finditer(data):
                    found.add(m.group(1).lower())
            if progress and i and i % 500 == 0:
                progress('  host discovery %d/%d blobs' % (i, len(blobs)))
    finally:
        proc.stdin.close()
        proc.wait()
    for pattern in HOST_STRICT:
        for m in pattern.finditer(inv.git('log', '--all', '--format=%B')):
            found.add(m.group(1).lower())
    return sorted(h.decode('latin-1') for h in found)


def apply_text(data, table):
    """Substitute every rule into `data`. Returns `(new_data, total_substitutions)`."""
    total = 0
    for pattern, repl in table:
        data, n = pattern.subn(repl, data)
        total += n
    return data, total


def clean(data, table, pattern=None):
    """Rewrite one blob by whichever means its format allows. Returns `(new, changed)`."""
    if sep.kind_of(data) is not None:
        pattern = pattern or _residue_pattern(table)
        if not pattern.search(data):
            return data, False
        new, _report = sep.clean(data, pattern)
        return new, new != data
    new, n = apply_text(data, table)
    return new, n > 0


def _residue_pattern(table):
    """One pattern matching anything the table would replace, for binaries and for verification."""
    return re.compile(rb'|'.join(b'(?:' + p.pattern + b')' for p, _r in table), re.I)


def audit(table=None, progress=None):
    """What the rewrite would change, across every object in the store. Writes nothing."""
    table = table or rules()
    residue = _residue_pattern(table)
    blobs = inv.all_blobs()
    changed, unchanged, binary, text = 0, 0, 0, 0
    leftover = []
    proc = inv.blob_reader()
    try:
        for i, (sha, _size) in enumerate(blobs):
            data = inv.read_one(proc, sha)
            if data is None:
                continue
            if not residue.search(data):
                unchanged += 1
                continue
            new, did = clean(data, table, residue)
            if did:
                changed += 1
                if sep.kind_of(data) is not None:
                    binary += 1
                else:
                    text += 1
                if residue.search(new):
                    leftover.append((sha, sep.kind_of(data) or 'text'))
            if progress and i and i % 400 == 0:
                progress('  %d/%d blobs' % (i, len(blobs)))
    finally:
        proc.stdin.close()
        proc.wait()
    return {'blobs': len(blobs), 'changed': changed, 'unchanged': unchanged,
            'binary_changed': binary, 'text_changed': text, 'leftover': leftover,
            'rules': len(table)}


def apply_to(target, table=None):
    """Run the rewrite over the repository at `target`. **Never this repository.**

    Refuses a target that is this working tree, because a rewrite is irreversible and the live
    repository is not where it gets proven. Refuses a dirty target, because `filter-repo` cannot
    reconcile uncommitted changes with rewritten history.
    """
    import git_filter_repo as fr

    target = os.path.abspath(target)
    if os.path.normcase(target) == os.path.normcase(os.path.abspath(ROOT)):
        raise SystemExit('refusing to rewrite the live repository; pass a clone')
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=target,
                           stdout=subprocess.PIPE).stdout.strip()
    if dirty:
        raise SystemExit('target has uncommitted changes; filter-repo needs a clean tree')

    table = table or rules()
    removals, _redactions = load_targets()
    residue = _residue_pattern(table)
    counts = {'blobs': 0, 'changed': 0, 'messages': 0, 'removed': 0}

    def blob_callback(blob, _metadata):
        counts['blobs'] += 1
        new, did = clean(blob.data, table, residue)
        if did:
            counts['changed'] += 1
            blob.data = new

    def commit_callback(commit, _metadata):
        new, n = apply_text(commit.message, table)
        if n:
            counts['messages'] += 1
            commit.message = new
        # A blob callback can only change a file's contents; dropping a path is a change to the
        # commit's file list, so it happens here.
        if removals:
            keep = [fc for fc in commit.file_changes if fc.filename not in removals]
            if len(keep) != len(commit.file_changes):
                counts['removed'] += len(commit.file_changes) - len(keep)
                commit.file_changes = keep

    # `RepoFilter` operates on the repository in the *current* directory, not on anything named
    # in its arguments. Without this chdir the rewrite would silently run against whichever repo
    # the shell happened to be in -- which, run from a normal session, is the live one the check
    # above exists to protect.
    here = os.getcwd()
    try:
        os.chdir(target)
        args = fr.FilteringOptions.parse_args(['--force'], error_on_empty=False)
        fr.RepoFilter(args, blob_callback=blob_callback,
                      commit_callback=commit_callback).run()
    finally:
        os.chdir(here)
    return counts


def verify(target, progress=None):
    """Scan a rewritten repository with the **inventory's** instrument, not with the rules.

    This is the whole point of the exercise, and the step most easily skipped. Checking a rewrite
    with the patterns that performed it proves only that the substitution is idempotent -- the
    rules cannot report the case they do not cover. The
    inventory's shapes are derived from the structure of a path rather than from this rewrite's
    replacement list, so they are capable of disagreeing, which is what makes agreement
    informative.

    Returns a dict of findings per object, with the paths that carry them.
    """
    target = os.path.abspath(target)
    scrub_pat, _decl, _names, _declared = inv.identity_patterns()

    def tgit(*args):
        return inv.git(*args, cwd=target)

    raw = tgit('cat-file', '--batch-all-objects',
               '--batch-check=%(objectname) %(objecttype) %(objectsize)')
    blobs = [(p[0].decode('latin-1'), int(p[2]))
             for p in (ln.split() for ln in raw.split(b'\n'))
             if len(p) == 3 and p[1] == b'blob']

    where = {}
    for line in tgit('rev-list', '--objects', '--all').split(b'\n'):
        if len(line) > 41:
            where.setdefault(line[:40].decode('latin-1'), set()).add(
                line[41:].decode('utf-8', 'replace'))

    proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=target,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    findings = []
    try:
        for i, (sha, _size) in enumerate(blobs):
            data = inv.read_one(proc, sha)
            if data is None:
                continue
            for kind, matched, whole in inv.scan_blob(data, scrub_pat):
                if not inv.gate_worthy(kind, matched, whole):
                    continue
                findings.append((sha, kind, whole.decode('latin-1'),
                                 sorted(where.get(sha, ()))[:3]))
            if progress and i and i % 500 == 0:
                progress('  verify %d/%d blobs' % (i, len(blobs)))
    finally:
        proc.stdin.close()
        proc.wait()

    messages = tgit('log', '--all', '--format=%B%n%an%n%ae%n%cn%n%ce')
    msg = [w.decode('latin-1') for _k, _m, w in inv.scan_blob(messages, scrub_pat)]

    # The removals and redactions are verified by their own absence, not by the rewrite's report.
    # A path is checked against every tree in history, not just the tip, because the whole point
    # of removing it is that no checkout of any commit should produce it.
    survivors = []
    every_path = set()
    for line in tgit('rev-list', '--objects', '--all').split(b'\n'):
        if len(line) > 41:
            every_path.add(line[41:])
    for path in load_targets()[0]:
        if path in every_path:
            survivors.append(path.decode('utf-8', 'replace'))

    unredacted = []
    proc2 = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=target,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
    try:
        for sha, _size in blobs:
            data = inv.read_one(proc2, sha)
            if data is None:
                continue
            for pattern, _repl in load_targets()[1]:
                if pattern.search(data):
                    unredacted.append(sha)
                    break
    finally:
        proc2.stdin.close()
        proc2.wait()

    return {'blobs': len(blobs), 'findings': findings, 'metadata': msg,
            'survivors': survivors, 'unredacted': unredacted,
            'commits': len([c for c in tgit('rev-list', '--all').split(b'\n') if c])}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    table = rules()

    if '--plan' in argv or not argv:
        print('%d rule(s), applied in this order:' % len(table))
        for i, (pattern, repl) in enumerate(table, 1):
            print('  %2d  %-62s -> %s' % (i, pattern.pattern.decode('latin-1')[:62],
                                          repl.decode('latin-1')))
        print('')
        print('Binaries are not text-substituted: a .blend is length-prefixed, so they go')
        print('through strip_embedded_paths instead, which is length-neutral.')
        return 0

    if '--audit' in argv:
        result = audit(table, progress=None if '--quiet' in argv else lambda m: print(m))
        print('')
        print('objects:            %d blob(s)' % result['blobs'])
        print('would change:       %d  (%d text, %d binary)'
              % (result['changed'], result['text_changed'], result['binary_changed']))
        print('already clean:      %d' % result['unchanged'])
        print('rules:              %d' % result['rules'])
        if result['leftover']:
            print('')
            print('LEFTOVER -- %d blob(s) would still match after rewriting. The rules are '
                  'incomplete:' % len(result['leftover']))
            for sha, kind in result['leftover'][:20]:
                print('    %s  %s' % (sha, kind))
            return 1
        print('')
        print('no residue: every object the rules touch comes back clean under the same '
              'patterns.')
        return 0

    if '--verify' in argv:
        rest = [a for a in argv if not a.startswith('--')]
        if len(rest) != 1:
            print('--verify needs exactly one repository path')
            return 2
        result = verify(rest[0], progress=None if '--quiet' in argv else lambda m: print(m))
        print('')
        print('scanned %d blob(s) across %d commit(s), with the inventory\'s shapes rather '
              'than this rewrite\'s rules' % (result['blobs'], result['commits']))
        print('findings in file content:        %d' % len(result['findings']))
        print('findings in commit metadata:     %d' % len(result['metadata']))
        print('removed paths still in history:  %d' % len(result['survivors']))
        print('blobs still carrying a redacted passage: %d' % len(result['unredacted']))
        for sha, kind, text, paths in result['findings'][:20]:
            print('    %s  %-14s %-50s %s' % (sha[:9], kind, text[:50], paths))
        for m in result['metadata'][:10]:
            print('    metadata: %s' % m)
        for s in result['survivors']:
            print('    SURVIVED: %s' % s)
        bad = (result['findings'] or result['metadata'] or result['survivors']
               or result['unredacted'])
        print('')
        print('NOT CLEAN -- the rewrite is incomplete' if bad
              else 'CLEAN under an instrument that did not perform the rewrite')
        return 1 if bad else 0

    if '--apply' in argv:
        rest = [a for a in argv if not a.startswith('--')]
        if len(rest) != 1:
            print('--apply needs exactly one target repository path')
            return 2
        counts = apply_to(rest[0], table)
        print('rewrote %s' % rest[0])
        print('  blobs seen %d, changed %d, commit messages changed %d, file entries removed %d'
              % (counts['blobs'], counts['changed'], counts['messages'], counts['removed']))
        return 0

    print(__doc__.strip().split('\n\n')[-1])
    return 2


if __name__ == '__main__':
    sys.exit(main())
