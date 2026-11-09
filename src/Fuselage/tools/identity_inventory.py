"""Enumerate every machine-specific or personal string in the repository's whole object store.

**Why this exists, and why it does not take a list.** Three times in this project a
dictionary-driven check has passed while missing entries nobody had given it. A gate built from
an authored list can only ever prove it copied that list; it cannot report the thing it was never
told about. So this tool does not start from names. It starts from *shapes* -- a drive-letter
path, a UNC path, a user-profile directory -- which are properties of the text itself, and it
finds whatever occupies them. The git-derived identities are added as a second, independent
source, so the two can disagree and the disagreement is visible.

**Why it walks objects rather than commits.** A string that ever existed lives in some blob, and
a blob is stored once however many commits reference it. Scanning 1 979 distinct blobs is both
cheaper than scanning 159 commit trees and strictly more complete: it reaches blobs in orphaned
lineages that no ref points at any more, which a `git grep` over refs would miss entirely and
which are still sitting in the object store.

**The report is never committed.** It is, by construction, a file full of the exact strings this
project forbids. It is written to an ignored path and carries its own warning header.

    python identity_inventory.py                     # scan and write the report
    python identity_inventory.py --print             # to stdout instead
    python identity_inventory.py --reachable-only    # skip orphaned objects
"""
import collections
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import doc_check  # noqa: E402 - the path insert above is what makes this importable

#: The repository root, derived from this file rather than the working directory.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

#: Where the report lands. Ignored by `.gitignore`; see this module's docstring for why that is
#: not optional.
REPORT = 'identity_inventory.local.txt'

#: Structural shapes that are machine-specific whatever they contain. These are what let the
#: inventory find a path belonging to someone whose name is on no list.
#:
#: Each is deliberately anchored on punctuation rather than on any word, so adding a name to the
#: project never changes what these match.
#: A note on the escaping, because getting it wrong here is silent. These are *raw* bytes
#: literals, so every backslash reaches the regex engine as written, and the engine then reads
#: `\\` as one literal backslash. A UNC prefix is two backslashes, so it needs four here. Written
#: with eight -- which looks right -- the shape matches a path with four backslashes, which does
#: not exist, and the scan reports a confident zero. It did exactly that until it was tested
#: against a known-positive sample.
#: One path character: printable ASCII, minus space and the delimiters a path is usually quoted
#: or bracketed by.
#:
#: **Restricting this to printable bytes is what makes the shapes usable on a binary.** Written
#: as a plain negated class, a match inside a JPEG runs straight on through the compressed data,
#: because arbitrary bytes are not whitespace and not delimiters either. The match then arrives
#: long enough and separator-rich enough to pass any plausibility filter, so the gate reported
#: `X:/`, `N:\` and `l:\@e` out of photographs as though they were paths.
PCH = rb'[^\x00-\x20\x7f-\xff"\'<>|)\]]'

SHAPES = (
    ('user_profile', re.compile(rb'[A-Za-z]:[\\/]Users[\\/](?:(?![\\/])' + PCH + rb')+')),
    ('posix_home', re.compile(rb'/(?:Users|home)/(?:(?!/)' + PCH + rb')+')),
    # Windows' extended-length form, which is its own prefix and is not matched by `unc`.
    ('unc_extended', re.compile(rb'\\\\\?\\UNC\\' + PCH + rb'*')),
    ('unc', re.compile(rb'\\\\[A-Za-z0-9._-]+\\' + PCH + rb'*')),
    ('drive', re.compile(rb'(?<![A-Za-z0-9])[A-Za-z]:[\\/]' + PCH + rb'*')),
)

#: The host out of a UNC match, so the forward-slash spelling of the same share can be hunted
#: in a second pass without any share name being written down here.
UNC_HOST = re.compile(rb'\\\\(?:\?\\UNC\\)?([A-Za-z0-9._-]+)\\')

#: Python code on this project spells a UNC path with forward slashes, which no structural shape
#: can find on its own: `//` followed by a dotless token is also what every base64 payload in the
#: repository looks like, and there are enough of those to bury the real finding. A first attempt
#: at a shape for it returned 1 709 matches, essentially all base64. So the forward-slash form is
#: searched only for hosts that pass 1 already discovered from a real UNC path -- structural
#: discovery first, then a targeted second pass.
def forward_slash_pattern(hosts):
    """A pattern for `//<host>[/...]` over already-discovered hosts, or `None` if there are none.

    The trailing path is optional because the host often appears alone: `os.path.join('//host',
    'Archive', ...)` splits the path across arguments, so the only thing in the string literal is
    the host itself. Requiring a following slash missed that spelling entirely.
    """
    if not hosts:
        return None
    alt = b'|'.join(re.escape(h) for h in sorted(hosts))
    return re.compile(rb'//(?:' + alt + rb')(?:/' + PCH + rb'*)?', re.I)

#: Shapes whose match is a false positive often enough to be worth naming. A URL scheme is not a
#: drive letter, and an already-anonymized path is the fix rather than the defect.
BENIGN = re.compile(rb'^(?:https?|file|git|ssh|mailto):'
                    rb'|<user>|<USER>|<server>|<share>|<redacted>'
                    rb'|\.\.\.')        # an ellipsis in a path means the rest was elided

#: Text extensions, used only to label a finding as reviewable-as-text. Everything is scanned
#: either way -- a binary carries paths too, and that is exactly the class a text search misses.
TEXT_EXT = ('.md', '.py', '.txt', '.json', '.csv', '.scad', '.cfg', '.toml', '.yaml', '.yml',
            '.ini', '.h', '.cpp', '.hpp', '.gitignore', '.gitattributes')


def git(*args, **kw):
    """Run git in the repository root and return stdout as bytes."""
    done = subprocess.run(['git'] + list(args), cwd=kw.get('cwd', ROOT),
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return done.stdout


def reachable_objects():
    """Every object reachable from any ref, as a set of hex SHAs.

    Anything in the store but *not* here is an orphan -- typically the output of a previous
    history rewrite. Those still hold the strings, so they are scanned and then reported
    separately rather than silently included or silently dropped.
    """
    out = set()
    for line in git('rev-list', '--objects', '--all').split(b'\n'):
        if line[:40]:
            out.add(line[:40].decode('latin-1'))
    return out


def all_blobs():
    """`[(sha, size)]` for every blob in the object store, reachable or not."""
    raw = git('cat-file', '--batch-all-objects', '--batch-check=%(objectname) %(objecttype) '
              '%(objectsize)')
    blobs = []
    for line in raw.split(b'\n'):
        parts = line.split()
        if len(parts) == 3 and parts[1] == b'blob':
            blobs.append((parts[0].decode('latin-1'), int(parts[2])))
    return blobs


def blob_reader():
    """A `git cat-file --batch` process, so 1 979 blobs cost one subprocess and not 1 979."""
    return subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)


def read_one(proc, sha):
    """Ask the batch process for one blob and return its bytes."""
    proc.stdin.write(sha.encode('latin-1') + b'\n')
    proc.stdin.flush()
    header = proc.stdout.readline()
    parts = header.split()
    if len(parts) != 3:
        return None
    size = int(parts[2])
    data = b''
    while len(data) < size:
        chunk = proc.stdout.read(size - len(data))
        if not chunk:
            break
        data += chunk
    proc.stdout.read(1)  # the trailing newline the batch protocol appends
    return data


def declared_identity():
    """The *effective* git identity -- what commits are actually authored as.

    This repository's local identity is deliberately pseudonymous, and that pseudonym is the
    desired author of every commit. It must therefore never reach a replacement list: scrubbing
    it would rewrite the authorship this project chose on purpose, which is the opposite of the
    repair. Reading the effective config with no scope flag is exactly what returns it, and is
    the same distinction that fixed the inverting bug in `doc_check`'s gate -- there, reading the
    effective value meant refusing the pseudonym while permitting the real name.
    """
    out = set()
    for key in ('user.name', 'user.email'):
        raw = git('config', key).decode('utf-8', 'replace').strip()
        if not raw:
            continue
        out.add(raw)
        for token in re.split(r'[^A-Za-z0-9]+', raw):
            if len(token) >= doc_check.IDENTITY_MIN and re.search(r'[A-Za-z]', token):
                out.add(token)
    return out


#: Addresses belonging to the forge rather than to a person. These are no more personal than a
#: domain name, and a rewrite that replaced them would corrupt merge commits' authorship.
BENIGN_IDENTITY = {'noreply@github.com', 'github.com'}


def identity_patterns():
    """`(scrub_pattern, declared_pattern, names, declared)` from the git-derived identities.

    Two patterns, because the two populations need opposite treatment. `doc_check.git_identities`
    reads every scope including `--global`, which is what surfaces the real identity behind the
    pseudonym; `declared_identity` then separates the pseudonym back out so the rewrite does not
    destroy it.
    """
    names = doc_check.git_identities(ROOT)
    declared = {d for d in declared_identity()} | BENIGN_IDENTITY
    scrub = [n for n in names if n not in declared
             and not any(n.lower() == d.lower() for d in declared)]

    def compile_alt(items):
        if not items:
            return None
        return re.compile(rb'\b(' + b'|'.join(re.escape(i.encode('latin-1'))
                                              for i in sorted(items)) + rb')\b', re.I)

    return compile_alt(scrub), compile_alt(sorted(declared)), sorted(scrub), sorted(declared)


def expand(data, at):
    """The full printable run containing `at`, so a report shows the whole string not a fragment."""
    lo = at
    while lo > 0 and 32 <= data[lo - 1] < 127:
        lo -= 1
    hi = at
    while hi < len(data) and 32 <= data[hi] < 127:
        hi += 1
    return data[lo:hi]


def scan_blob(data, ident, extra=None):
    """Every finding in one blob, as `[(kind, matched_string, surrounding_string)]`.

    `extra` is the second-pass forward-slash pattern, built from hosts the first pass found.
    """
    found = []
    shapes = list(SHAPES)
    if extra is not None:
        shapes.append(('unc_fwd', extra))
    for kind, shape in shapes:
        for m in shape.finditer(data):
            s = m.group(0)
            if BENIGN.search(s):
                continue
            found.append((kind, s, expand(data, m.start())))
    if ident is not None:
        for m in ident.finditer(data):
            found.append(('identity', m.group(0), expand(data, m.start())))
    return found


def hosts_in(data):
    """Every UNC host named in one blob, lowercased, as a set of bytes.

    **This over-collects, on purpose.** Source code spells a Windows path with doubled
    separators, so `"R:\\\\dir\\\\sub"` presents the same two-backslash-then-token shape a UNC
    host does, and the segments of such a path are indistinguishable from host names without
    parsing the language around them. Over-collecting only widens the second pass's search, which
    is cheap and safe; under-collecting would miss a share. A length floor drops the
    single-character captures that come from escape sequences and are certainly not hosts.
    """
    return {m.group(1).lower() for m in UNC_HOST.finditer(data)
            if len(m.group(1)) >= doc_check.IDENTITY_MIN}


def paths_for_blobs():
    """`{sha: set(path)}` for blobs reachable from a ref, so a finding can name a file."""
    out = collections.defaultdict(set)
    for line in git('rev-list', '--objects', '--all').split(b'\n'):
        if len(line) > 41:
            out[line[:40].decode('latin-1')].add(line[41:].decode('utf-8', 'replace'))
    return out


def scan(reachable_only=False, progress=None):
    """Scan the object store. Returns a dict of aggregated findings."""
    ident, declared_pat, names, declared = identity_patterns()
    reach = reachable_objects()
    where = paths_for_blobs()
    every = all_blobs()
    blobs = [(s, n) for s, n in every if s in reach] if reachable_only else every

    strings = collections.Counter()
    kinds = collections.Counter()
    by_string_paths = collections.defaultdict(set)
    orphan_only = collections.Counter()
    scanned = 0
    hosts = set()
    extra = None

    # Two passes. The first finds everything a structural shape can find on its own, and
    # collects the UNC hosts. The second looks for those hosts' forward-slash spelling, which is
    # not separable from base64 noise without knowing the host first.
    for phase in (1, 2):
        if phase == 2:
            extra = forward_slash_pattern(hosts)
            if extra is None:
                break
        proc = blob_reader()
        try:
            for i, (sha, _size) in enumerate(blobs):
                data = read_one(proc, sha)
                if data is None:
                    continue
                if phase == 1:
                    scanned += 1
                    hosts |= hosts_in(data)
                hits = scan_blob(data, ident, extra) if phase == 2 else scan_blob(data, ident)
                if phase == 2:
                    hits = [h for h in hits if h[0] == 'unc_fwd']
                if progress and i and i % 500 == 0:
                    progress('  pass %d: %d/%d blobs' % (phase, i, len(blobs)))
                for kind, _s, whole in hits:
                    key = whole.decode('latin-1')
                    strings[key] += 1
                    kinds[kind] += 1
                    for p in where.get(sha, ()):
                        by_string_paths[key].add(p)
                    if sha not in reach:
                        orphan_only[key] += 1
        finally:
            proc.stdin.close()
            proc.wait()

    messages = git('log', '--all', '--format=%B%n%an%n%ae%n%cn%n%ce')
    msg_hits = collections.Counter()
    for _kind, _s, whole in scan_blob(messages, ident, forward_slash_pattern(hosts)):
        msg_hits[whole.decode('latin-1')] += 1
    declared_hits = collections.Counter()
    if declared_pat is not None:
        for m in declared_pat.finditer(messages):
            declared_hits[expand(messages, m.start()).decode('latin-1')] += 1

    return {'blobs_scanned': scanned, 'blobs_total': len(every),
            'orphan_blobs': len([s for s, _n in blobs if s not in reach]),
            'identities': names, 'declared': declared, 'strings': strings, 'kinds': kinds,
            'hosts': sorted(h.decode('latin-1') for h in hosts),
            'paths': by_string_paths, 'orphan_only': orphan_only,
            'commit_metadata': msg_hits, 'declared_in_metadata': declared_hits}


def tracked_files(root=None):
    """Every tracked path, whatever its extension. Returns `[]` if git cannot be reached."""
    raw = git('ls-files', '-z', cwd=root or ROOT)
    return [p.decode('utf-8', 'replace') for p in raw.split(b'\x00') if p]


#: Absolute roots that are machine-specific but not *personal*. A path under one of these names
#: an installed program or the operating system, carries no account name, and is exactly the kind
#: of thing a guideline or an error message legitimately quotes.
SYSTEM_ROOTS = (b'program files', b'programdata', b'windows\\', b'windows/', b'system32')

#: A gate finding must look like a path and not like coincidence. Compressed image data throws up
#: short drive-letter and UNC lookalikes constantly -- `P:/`, `N:\,`, `T:/$xN`, `\\\R\R` were all
#: reported by the first version of this gate, every one of them noise inside a PNG. A real
#: embedded path carries several separators and some length; the noise carries one and almost
#: none.
GATE_MIN_LENGTH = 10
GATE_MIN_SEPARATORS = 2

#: The shapes the gate will refuse a commit over, which is narrower than what the inventory
#: reports. This follows the guideline's own wording: in scope are a name, an address, a machine
#: or share name, and an absolute path *beneath a user profile*. A `drive` match is therefore
#: deliberately absent -- `C:\does\not\exist\x.exe` in a test and `C:/path/without/extension` in
#: a docstring are fabricated examples carrying nobody's identity, and a real drive path that
#: does carry a name is caught by the `identity` source instead.
#:
#: **The residual gap, stated rather than papered over:** a drive-letter path containing an
#: account name is refused only because the name is in the identity list. On a machine with no
#: configured git identity, such a path would pass the gate. The inventory is the recall
#: instrument for that case and is run deliberately, not on commit.
GATE_KINDS = ('identity', 'user_profile', 'posix_home', 'unc', 'unc_extended', 'unc_fwd')

#: A plausible UNC path names a host and then a share. A regex word boundary does not: source
#: files in this project contain `\\bwidget\b` and `\\bwidget_total\\b`, and the `unc` shape
#: reads the escape as a host followed by a one-character share. Requiring two characters in the
#: segment after the host separates the two without naming either.
UNC_PLAUSIBLE = re.compile(rb'\\\\(?:\?\\UNC\\)?[A-Za-z0-9._-]{3,}\\[A-Za-z0-9._-]{2,}')


def gate_worthy(kind, matched, whole):
    """Is this finding precise enough to refuse a commit over?

    The inventory is deliberately broad, because its job is recall: it should surface a candidate
    even at the cost of noise, and a person reads it. A gate's job is the opposite. It runs
    unattended, and a false positive makes it something to be bypassed -- so the same breadth
    that makes the inventory useful would make the gate worthless.
    """
    if BENIGN.search(whole):
        return False        # the expanded string, not just the match: a shape stops at the `<`
                            # of a placeholder, so only the whole run shows it is already fixed
    if kind not in GATE_KINDS:
        return False
    if kind == 'identity':
        return True         # a name needs no corroborating structure
    if len(matched) < GATE_MIN_LENGTH:
        return False
    if sum(matched.count(c) for c in (b'\\', b'/')) < GATE_MIN_SEPARATORS:
        return False
    if kind in ('unc', 'unc_extended') and not UNC_PLAUSIBLE.search(matched):
        return False
    low = whole.lower()
    return not any(r in low for r in SYSTEM_ROOTS)


def gate(root=None, paths=None):
    """`[(path, where, kind, string)]` for every tracked file carrying a forbidden string.

    `paths` restricts the scan to the files named, which is what the commit hook passes: a hook
    should check what is being committed rather than rescan the tree, and scanning 533 tracked
    files costs about fourteen seconds where the staged set costs a fraction of one.

    **The half of the identity gate that reads bytes rather than text.** `doc_check` and
    `source_spelling` decode a file as UTF-8 and match names in it, which covers prose, code and
    manifests and misses binaries entirely -- and a binary is exactly where an embedded path hides
    from `git grep`. This scans every tracked path with the structural shapes, so a `.blend`'s
    last-used directory or a PNG's render stamp is caught by the same run.

    It also does not depend on git having an identity to offer. The shapes are properties of the
    text, so this still finds a user-profile path on a machine where no `user.name` is configured
    -- the case where a name-only gate silently passes everything.

    Fails closed: if git lists no tracked file at all, that is returned as a finding rather than
    as a clean result, because a check that did not run must not read as a check that passed.
    """
    base = root or ROOT
    if paths is None:
        paths = tracked_files(base)
        if not paths:
            return [('(repository)', 0, 'not-run',
                     'git listed no tracked files, so this check did NOT run -- it was skipped, '
                     'not clean')]
    ident, _declared_pat, _names, _declared = identity_patterns()
    found = []
    for rel in paths:
        if os.path.basename(rel) in doc_check.IDENTITY_EXEMPT:
            continue
        full = os.path.join(base, rel)
        try:
            with open(full, 'rb') as fh:
                data = fh.read()
        except OSError:
            continue
        for kind, matched, whole in scan_blob(data, ident):
            if not gate_worthy(kind, matched, whole):
                continue
            where = data[:data.find(matched)].count(b'\n') + 1
            found.append((rel, where, kind, whole.decode('latin-1')))
    return found


HEADER = """\
IDENTITY INVENTORY -- DO NOT COMMIT THIS FILE
=============================================

This file lists, verbatim, the personal and machine-specific strings that
doc/guidelines/general.md forbids in this repository. It exists so the gate and the history
rewrite can be built from a measured list rather than an authored one. It is ignored by
.gitignore for that reason, and committing it would be the exact defect it is here to repair.

Regenerate with: python src/Fuselage/tools/identity_inventory.py
"""


def report(result):
    """The inventory as text, ordered so the most widespread string reads first."""
    out = [HEADER]
    out.append('blobs scanned: %d of %d in the object store (%d of them orphaned, reachable '
               'from no ref)' % (result['blobs_scanned'], result['blobs_total'],
                                 result['orphan_blobs']))
    out.append('git-derived identities to scrub: %d' % len(result['identities']))
    out.append('UNC hosts discovered structurally: %d (%s)'
               % (len(result['hosts']), ', '.join(result['hosts'])))
    out.append('distinct strings found: %d' % len(result['strings']))
    out.append('by shape: %s' % ', '.join('%s=%d' % kv for kv in
                                          sorted(result['kinds'].items())))
    out.append('')
    out.append('--- distinct strings, by how many blobs carry them ---')
    for s, n in result['strings'].most_common():
        orph = result['orphan_only'].get(s, 0)
        paths = sorted(result['paths'].get(s, ()))
        out.append('%6d blob(s)%s  %s' % (n, '  [%d orphan-only]' % orph if orph else '', s))
        for p in paths[:6]:
            out.append('              %s' % p)
        if len(paths) > 6:
            out.append('              ... and %d more path(s)' % (len(paths) - 6))
    out.append('')
    out.append('--- commit messages and author/committer metadata ---')
    if not result['commit_metadata']:
        out.append('clean: no match in any commit message or identity field')
    for s, n in result['commit_metadata'].most_common():
        out.append('%6d  %s' % (n, s))
    out.append('')
    out.append('--- DELIBERATE: the declared identity. DO NOT put any of this in a replacement '
               'list ---')
    out.append('The effective git identity is what every commit is authored as, on purpose.')
    out.append('Rewriting it would destroy the pseudonymous authorship this project chose,')
    out.append('which is the opposite of the repair. Listed here so it is visibly excluded')
    out.append('rather than silently absent.')
    out.append('')
    for d in result['declared']:
        if d.lower() in doc_check.NOT_PERSONAL:
            continue        # a generic word from tokenizing the address, not an identity
        out.append('    keep  %s' % d)
    out.append('')
    out.append('occurrences in commit metadata, which are expected and correct:')
    for s, n in result['declared_in_metadata'].most_common(8):
        out.append('%6d  %s' % (n, s))
    return '\n'.join(out) + '\n'


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    # The commit hook's entry point. Non-zero on any finding, and it names the file and the
    # string so the message is actionable without a second command.
    if '--gate' in argv:
        files = [a for a in argv if not a.startswith('--')] or None
        found = gate(paths=files)
        for path, where, kind, text in found:
            print('%s:%s: %s -- %s' % (path, where, kind, text[:100]))
        if found:
            print('')
            print('%d finding(s). doc/guidelines/general.md forbids a personal identifier or a '
                  'machine-specific path in any tracked file.' % len(found))
            print('For a binary, use src/Fuselage/tools/strip_embedded_paths.py. For text, '
                  'rewrite the line.')
            return 1
        print('identity gate: clean (%s)'
              % ('%d staged file(s)' % len(files) if files else 'whole tree'))
        return 0

    result = scan(reachable_only='--reachable-only' in argv,
                  progress=None if '--quiet' in argv else lambda m: print(m))
    text = report(result)
    if '--print' in argv:
        print(text)
        return 0
    dest = os.path.join(ROOT, REPORT)
    with open(dest, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    print('wrote %s' % dest)
    print('  %d distinct string(s) across %d blob(s)'
          % (len(result['strings']), result['blobs_scanned']))
    print('  by shape: %s' % ', '.join('%s=%d' % kv for kv in sorted(result['kinds'].items())))
    print('  commit metadata: %d match(es)' % sum(result['commit_metadata'].values()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
