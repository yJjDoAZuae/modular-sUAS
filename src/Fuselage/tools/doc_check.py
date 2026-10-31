"""The documentation's own structural invariants, checked by running something.

**Why this exists.** The design and implementation documents carry a lot of bookkeeping that is
true by convention and nowhere enforced: an open question's summary table lists exactly the
questions still open, a blocked work item names what blocks it and that thing is really open, a
link with an anchor points at a heading that is really there, a plan's header count matches its
own table. Every one of those drifts silently as the documents grow, and the drift is only ever
found by reading carefully -- which means it is found at random, one item at a time, long after
it stopped being true.

Nothing here reads a number and decides whether it is *right*. These are the properties that can
be settled by looking at the documents alone, and the point of settling them mechanically is to
leave attention for the claims that need judgment.

    python doc_check.py                  # every check, grouped, with a count
    python doc_check.py --quiet          # findings only
    python doc_check.py --check=links,plans
    python doc_check.py --fix-spelling   # the one class that is safe to rewrite

Spelling is the only finding this tool will repair. Every other class needs a person to decide
what the document should say instead, which is the whole reason they are reported rather than
patched.

Exit code is 1 when anything is found, so this is usable from a test or a hook. The checks are
also importable one at a time, which is how `tests/test_doc_check.py` drives them against
synthetic pages rather than against the real documents.

**A finding is not always a defect.** `known.py`-style suppression is deliberately absent: three
broken anchors in the guideline documents predate this tool and are reported every run, because a
suppression list is the mechanism by which a checker stops being read.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: The repository root, from `src/Fuselage/tools`.
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))

#: Everything this tool reads. One tree, so a page's own relative links resolve against it.
DOC = os.path.join(ROOT, 'doc')

#: Where the implementation plans live, and the master index that must list them.
PLAN_DIR = os.path.join('implementation')
PLAN_INDEX = os.path.join(PLAN_DIR, 'PLANS.md')

#: A declaration that closes an open question says so in one of these words. There is no
#: strikethrough convention here and there must not be one: a closed question says so in words.
#:
#: **Matched in capitals, and that is not cosmetic.** The marker is always written in caps --
#: `-- DECIDED 2026-08-30` -- while the same words occur constantly in the titles themselves as
#: ordinary prose. Matching case-insensitively read "the facet count is fixed" in OQ-DES-CW32's
#: own title as a closure marker and reported the question as resolved while it was open, which
#: then reported every work item blocked on it as blocked on nothing.
CLOSED_WORDS = ('RESOLVED', 'DECIDED', 'WITHDRAWN', 'CLOSED', 'SUPERSEDED', 'ANSWERED', 'FIXED')

#: `CLOSED_WORDS` as one case-sensitive, word-bounded pattern.
CLOSED_RE = re.compile(r'\b(%s)\b' % '|'.join(CLOSED_WORDS))

#: British spellings, with the American form to use. Checked outside code spans only: a name in
#: backticks is a reference to code, so correcting it here would make the document cite a symbol
#: that does not exist. Whether the symbol itself should be renamed is a separate question, and
#: `source_spelling.py` is what answers it -- it shares this dictionary and renames the
#: identifiers across the source tree in one change, so the two never disagree.
BRITISH = {
    'behaviour': 'behavior', 'behaviours': 'behaviors',
    'centre': 'center', 'centred': 'centered', 'centres': 'centers',
    'artefact': 'artifact', 'artefacts': 'artifacts',
    'neighbour': 'neighbor', 'neighbours': 'neighbors',
    'neighbouring': 'neighboring', 'neighbourhood': 'neighborhood',
    'colour': 'color', 'coloured': 'colored', 'colours': 'colors',
    'analyse': 'analyze', 'analysed': 'analyzed', 'analyses': 'analyzes',
    'modelled': 'modeled', 'modelling': 'modeling',
    'favour': 'favor', 'favoured': 'favored',
    'organise': 'organize', 'organised': 'organized',
    'recognise': 'recognize', 'recognised': 'recognized',
    'normalise': 'normalize', 'normalised': 'normalized',
    'catalogue': 'catalog', 'licence': 'license',
    'labelled': 'labeled', 'labelling': 'labeling',
    'cancelled': 'canceled', 'travelled': 'traveled',
    'behavioural': 'behavioral',
    # Inflections found by the source pass. They were reported rather than guessed at: each one
    # turned up as a British stem inside a longer word that no entry covered.
    'unrecognise': 'unrecognize', 'unrecognised': 'unrecognized',
    'colouring': 'coloring', 'mislabelled': 'mislabeled', 'mislabelling': 'mislabeling',
    'catalogued': 'cataloged', 'cataloguing': 'cataloging',
    'organising': 'organizing', 'recognising': 'recognizing',
    'normalising': 'normalizing', 'analysing': 'analyzing',
    'favouring': 'favoring', 'favours': 'favors',
    # The compounds are listed individually because a word boundary does not fall before the
    # `-metre` in `millimetre`, so `metre` alone matches neither it nor `nanometre`. These are
    # the forms the tree actually holds, counted rather than guessed.
    'metre': 'meter', 'metres': 'meters',
    'millimetre': 'millimeter', 'millimetres': 'millimeters',
    'nanometre': 'nanometer', 'nanometres': 'nanometers',
    'micrometre': 'micrometer', 'micrometres': 'micrometers',
    'centimetre': 'centimeter', 'centimetres': 'centimeters',
    'centreline': 'centerline', 'centrelines': 'centerlines',
    'fibre': 'fiber', 'fibres': 'fibers',
}


class Finding(object):
    """One thing found, in one place. `where` is a page-relative line number when there is one."""

    def __init__(self, check, page, detail, where=None):
        self.check = check
        self.page = page
        self.detail = detail
        self.where = where

    def __repr__(self):
        at = '' if self.where is None else ':%d' % self.where
        return '%-14s %s%s  %s' % (self.check, self.page, at, self.detail)

    def __eq__(self, other):
        return repr(self) == repr(other)


def slug(title):
    """GitHub's heading anchor: lowercase, drop all but word characters, spaces and hyphens.

    Underscores survive, because they are word characters -- stripping them breaks every
    `WALL_TOL` and `__file__` anchor. One hyphen per space and not one per run, which is why an
    em dash between two spaces leaves a double hyphen in the anchor.

    **The space a stripped symbol leaves behind becomes a hyphen, and is not trimmed.** GitHub's
    slugger lowercases, drops the characters it drops, and only then replaces spaces -- so
    `### (warning sign) The OpenSCAD path ...` anchors as `-the-openscad-path-...` with a leading
    hyphen. Trimming first made this function disagree with a link that was correct, and the
    checker reported the document as broken. The heading text arrives already stripped of its
    own leading and trailing whitespace, so nothing else is affected.
    """
    s = re.sub(r'[`*]', '', title.lower())
    s = re.sub(r'[^\w\s-]', '', s)
    return re.sub(r'\s', '-', s)


def strip_code(text):
    """Inline code spans and fenced blocks blanked out, so prose checks do not read identifiers.

    Replaced by spaces of the same length rather than removed, so line and column numbers of
    everything after them are unchanged.
    """
    def blank(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    text = re.sub(r'```.*?```', blank, text, flags=re.S)
    return re.sub(r'`[^`\n]*`', blank, text)


class Page(object):
    """One markdown file: its text, its heading anchors, and the tables this tool reads."""

    def __init__(self, rel, path, text):
        self.rel = rel.replace(os.sep, '/')
        self.path = path
        self.text = text
        self.lines = text.split('\n')
        self.anchors = set()
        self.headings = []
        #: Filled by `open_questions`, which is where a second declaration is detectable.
        self.duplicate_declarations = []
        #: `{id: 'heading'|'bold'}`, also filled by `open_questions`.
        self.declaration_form = {}
        for n, line in enumerate(self.lines, 1):
            m = re.match(r'^(#{1,6})\s+(.*?)\s*$', line)
            if m:
                self.headings.append((n, len(m.group(1)), m.group(2)))
                self.anchors.add(slug(m.group(2)))

    @property
    def is_plan(self):
        return self.rel.startswith('implementation/') and not self.rel.endswith('PLANS.md')


def read_pages(root=DOC):
    """Every markdown page under `root`, keyed by its path relative to `root`, in sorted order."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith('.md'):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            with io.open(path, encoding='utf-8') as fh:
                out[rel.replace(os.sep, '/')] = Page(rel, path, fh.read())
    return out


# --------------------------------------------------------------------------- links and images


def check_links(pages):
    """Every cross-document link with an anchor points at a heading that is really there.

    Same-page anchors (`#foo`) are checked too. A link to a path outside the tree, or to any
    `http` target, is left alone -- this tool does not reach the network.
    """
    found = []
    for rel, page in sorted(pages.items()):
        base = os.path.dirname(rel)
        for m in re.finditer(r'(?<!!)\[[^\]]*\]\(([^)\s]*)#([^)\s]+)\)', page.text):
            target, anchor = m.group(1), m.group(2).lower()
            where = page.text[:m.start()].count('\n') + 1
            if target.startswith('http'):
                continue
            if not target:
                if anchor not in page.anchors:
                    found.append(Finding('links', rel, 'no such heading on this page: #%s'
                                         % anchor, where))
                continue
            if not target.endswith('.md'):
                continue
            tgt = os.path.normpath(os.path.join(base, target)).replace(os.sep, '/')
            if tgt not in pages:
                found.append(Finding('links', rel, 'no such file: %s' % target, where))
            elif anchor not in pages[tgt].anchors:
                found.append(Finding('links', rel, 'no such heading: %s#%s'
                                     % (target, anchor), where))
    return found


def check_images(pages):
    """Every image a page shows exists on disk."""
    found = []
    for rel, page in sorted(pages.items()):
        base = os.path.dirname(os.path.join(DOC, rel))
        for m in re.finditer(r'!\[[^\]]*\]\(([^)\s]+)', page.text):
            target = m.group(1).split('#')[0]
            if target.startswith('http'):
                continue
            if not os.path.isfile(os.path.join(base, target)):
                where = page.text[:m.start()].count('\n') + 1
                found.append(Finding('images', rel, 'missing image: %s' % target, where))
    return found


# --------------------------------------------------------------------------- open questions


#: A declaring heading. The separator after the id is required for the same reason the bold form
#: requires one: `### OQ-ARCH-10 (as originally posed) -- retained for the alternatives` is a
#: second record of a question declared and withdrawn earlier in the same document, and reading
#: it as a declaration reported a withdrawn question as open. 96 of the 97 headings in the tree
#: use ` -- `; the one that does not is that sub-record.
#:
#: The separator alternatives are built from code points rather than written literally, so this
#: file stays ASCII and an em dash cannot be lost to a re-encoding on its way through a tool.
SEPARATOR = r'(?:%s|%s|--|:)' % (chr(0x2014), chr(0x2013))

OQ_HEADING = re.compile(r'^###\s+(OQ-[A-Z]+-[A-Z]*\d+)\s*' + SEPARATOR + r'(.*)$')
OQ_ROW = re.compile(r'^\|\s*(OQ-[A-Z]+-[A-Z]*\d+)\s*\|')

#: A summary-table header. Two schemas are in use and they mean different things:
#:
#:     | ID | Question | Blocking |   the current one -- lists the OPEN questions only
#:     | ID | Status | Question |     the legacy one  -- lists EVERY question, with its status
#:
#: `cowl.md` uses the first, `bulkhead.md`, `corner.md` and the architecture document use the
#: second. Checking a legacy register against the current rule would report every resolved
#: question as "closed and still in the summary table", which is the table working as intended.
OQ_TABLE_HEADER = re.compile(r'^\|\s*ID\s*\|\s*(\w+)\s*\|')

#: A legacy register's status cell, which is written in lower case -- `resolved 2026-08-06`,
#: `**open**`, `withdrawn 2026-08-07`. Deliberately *not* `CLOSED_RE`, which is capital-only
#: because it reads titles, where these same words occur as ordinary prose.
STATUS_CLOSED = re.compile(r'\b(resolved|decided|withdrawn|closed|superseded|answered|fixed|'
                           r'implemented)\b', re.I)
STATUS_OPEN = re.compile(r'\bopen\b', re.I)


def _id_aliases(oq_id):
    """Every spelling a summary table might use for `oq_id`.

    The legacy registers drop the registry prefix -- `bulkhead.md` writes `B14` and the
    architecture document writes `ARCH-21` for what the subsections call `OQ-DES-B14` and
    `OQ-ARCH-21`. Returning each hyphen-suffix covers both without hard-coding either.

    **An alias must contain a letter.** `OQ-ARCH-1`'s bare suffix is `1`, and matching that
    picked up the first column of every unrelated numbered table on the page -- which reported
    the register's own first four rows as duplicates of rows that were not open questions.
    """
    parts = oq_id.split('-')
    out = set('-'.join(parts[i:]) for i in range(len(parts)))
    return set(name for name in out if re.search(r'[A-Za-z]', name))


def summary_rows(page, declared):
    """`(schema, [(oq_id, status_cell, line)])` for the page's open-question summary table.

    `schema` is `'status'` for a legacy full register, `'open'` for the current open-only
    table, and `None` when the page keeps no such table. A row whose first cell names nothing
    this page declares comes back with `oq_id` `None`, which is how a row for a deleted
    subsection is caught.
    """
    alias = {}
    for oq_id in declared:
        for name in _id_aliases(oq_id):
            alias[name] = oq_id
    schema, rows = None, []
    for n, line in enumerate(page.lines, 1):
        head = OQ_TABLE_HEADER.match(line)
        if head:
            schema = 'status' if head.group(1).lower() == 'status' else 'open'
            continue
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if not cells or set(cells[0]) <= set('- :'):
            continue
        key = re.sub(r'[`*]', '', cells[0])
        if key in alias:
            status = cells[1] if len(cells) > 1 else ''
            rows.append((alias[key], status, n))
        elif OQ_ROW.match(line):
            rows.append((None, cells[0], n))
    if schema is None and rows:
        schema = 'open'
    return schema, rows
OQ_ANY = re.compile(r'\b(OQ-[A-Z]+-[A-Z]*\d+)\b')
IP_HEADING_ID = re.compile(r'\b(IP-[A-Z]+-\d+)\b')


def _oq_series(oq_id):
    """`('OQ-DES-CW', 26)`. The series letters belong to the name, not to the number.

    `OQ-DES-SR1` and `OQ-DES-D10` are different series in the same document, so comparing their
    numbers would otherwise report an ordering violation between two unrelated questions.
    """
    m = re.match(r'^(.*?)(\d+)$', oq_id)
    return m.group(1), int(m.group(2))


def _oq_number(oq_id):
    return _oq_series(oq_id)[1]


def _by_number(item):
    return _oq_number(item[0])


#: The older declaration form, used by `bulkhead.md` and `corner.md`: a bold paragraph lead
#: rather than a heading. It carries the same information and must resolve the same way, so a
#: reference to one of those questions is not a dangling reference.
#:
#: **The separator is what makes this a declaration and not a mention.** A declaration reads
#: `**OQ-DES-B1 -- What sets ...`, while `**OQ-DES-CW26 stays open, because ...` is a sentence
#: about a question declared somewhere else. Without the separator every such sentence would
#: register as a second declaration, and the page holding it would be asked for a summary table.
OQ_BOLD = re.compile(r'^\*\*(OQ-[A-Z]+-[A-Z]*\d+)\s*' + SEPARATOR + r'\s')


def open_questions(page):
    """`{id: (line, is_open)}` for every open question a page declares, in document order.

    Two declaration forms, because the documents hold both. The current one is a level-3
    heading. `bulkhead.md` and `corner.md` predate it and declare a question as a **bold
    paragraph lead** instead -- and the closing word can fall on a later line of that paragraph,
    so the whole paragraph is read rather than the first line.
    """
    out, extra, form = {}, [], {}
    for n, level, title in page.headings:
        if level != 3:
            continue
        m = OQ_HEADING.match('### ' + title)
        if m:
            if m.group(1) in out:
                extra.append((m.group(1), n))
                continue
            out[m.group(1)] = (n, not CLOSED_RE.search(m.group(2)))
            form[m.group(1)] = 'heading'
    for n, line in enumerate(page.lines, 1):
        m = OQ_BOLD.match(line)
        if not m:
            continue
        para = []
        for later in page.lines[n - 1:]:
            if not later.strip():
                break
            para.append(later)
        if m.group(1) in out:
            extra.append((m.group(1), n))
            continue
        out[m.group(1)] = (n, not CLOSED_RE.search(' '.join(para)))
        form[m.group(1)] = 'bold'
    page.duplicate_declarations = extra
    page.declaration_form = form
    return out


def check_open_questions(pages):
    """The three conventions that make an open-question section readable.

    The summary table lists exactly the questions still open, so a reader can trust it as the
    list of what is undecided. The subsections run in ascending numerical order with resolved and
    open interleaved, so a question keeps its place when it closes. And nothing is listed twice.
    """
    found = []
    for rel, page in sorted(pages.items()):
        oqs = open_questions(page)
        if not oqs:
            continue
        for oq_id, line in page.duplicate_declarations:
            found.append(Finding('oq-duplicate', rel, '%s is declared again here; the first '
                                 'declaration is the one that counts' % oq_id, line))
        schema, table = summary_rows(page, oqs)
        seen = set()
        for oq_id, _status, n in table:
            if oq_id is None:
                continue
            if oq_id in seen:
                found.append(Finding('oq-table', rel, '%s listed twice in the summary table'
                                     % oq_id, n))
            seen.add(oq_id)
        listed = dict((oq_id, n) for oq_id, _s, n in table if oq_id is not None)
        rows = [(oq_id, n) for oq_id, _s, n in table if oq_id is not None]
        # Ascending order is checked per id prefix, because one page can hold two series and
        # their numbers are independent of each other.
        #
        # **Only the heading form is ordered.** The convention this enforces is about
        # subsections -- "the full subsections are always kept in ascending order" -- and the
        # legacy bold-lead entries in `corner.md` are not subsections. That document hoists one
        # *answered* question above its block of *resolved* ones on purpose and says so in
        # prose, and demanding a numerical sort there would be enforcing a rule the convention
        # does not state against a document that predates it.
        by_prefix = {}
        for oq_id, (line, _o) in oqs.items():
            if page.declaration_form.get(oq_id) != 'heading':
                continue
            by_prefix.setdefault(_oq_series(oq_id)[0], []).append((oq_id, line))
        for _prefix, group in sorted(by_prefix.items()):
            group.sort(key=lambda pair: pair[1])
            numbers = [_oq_number(i) for i, _l in group]
            for i in range(1, len(numbers)):
                if numbers[i] < numbers[i - 1]:
                    found.append(Finding('oq-order', rel, '%s follows %s, breaking ascending '
                                         'order' % (group[i][0], group[i - 1][0]), group[i][1]))
        # A page with no row at all keeps no summary table, which is the older convention rather
        # than a dropped row. Reported once, so it reads as one convention gap and not as one
        # finding per question -- and the per-question checks below are then meaningless.
        if not rows:
            still_open = sorted(i for i, (_l, o) in oqs.items() if o)
            if still_open:
                found.append(Finding('oq-table', rel, 'keeps no summary table, so the %d open '
                                     'question(s) here (%s) are listed nowhere'
                                     % (len(still_open), ', '.join(still_open)),
                                     oqs[still_open[0]][0]))
            continue
        if schema == 'status':
            # A full register: every question belongs in it, and its status cell has to agree
            # with the marker on its own declaration. That disagreement is the drift this
            # schema is prone to -- a question gets answered, the table is updated, and the
            # declaration keeps the wording it had.
            for oq_id, (line, is_open) in sorted(oqs.items(), key=_by_number):
                if oq_id not in listed:
                    found.append(Finding('oq-table', rel, '%s is missing from the register'
                                         % oq_id, line))
            for oq_id, status, n in table:
                if oq_id is None:
                    continue
                said_closed = bool(STATUS_CLOSED.search(status))
                said_open = bool(STATUS_OPEN.search(status)) and not said_closed
                is_open = oqs[oq_id][1]
                if said_closed and is_open:
                    found.append(Finding('oq-table', rel, '%s reads %r in the register and its '
                                         'own declaration carries no closing marker'
                                         % (oq_id, status), n))
                elif said_open and not is_open:
                    found.append(Finding('oq-table', rel, '%s reads open in the register and '
                                         'its own declaration is closed' % oq_id, n))
        else:
            for oq_id, (line, is_open) in sorted(oqs.items(), key=_by_number):
                if is_open and oq_id not in listed:
                    found.append(Finding('oq-table', rel, '%s is open and missing from the '
                                         'summary table' % oq_id, line))
                if not is_open and oq_id in listed:
                    found.append(Finding('oq-table', rel, '%s is closed and still in the '
                                         'summary table' % oq_id, listed[oq_id]))
        for oq_id, status, n in table:
            if oq_id is None:
                found.append(Finding('oq-table', rel, '%s is in the summary table with no '
                                     'subsection' % status, n))
    return found


#: A series of ids that was renamed, declared by the document that performed the rename:
#:
#:     <!-- doc_check: retired-series OQ-DES-DV -> OQ-DES-DB -->
#:
#: **Why this is a marker and not a suppression list.** The documents legitimately name a retired
#: id when they record the rename -- "`OQ-DES-DV3` is now `OQ-DES-DB3`" is the useful sentence in
#: such a note, and it can only be written with the old id in it. Without a marker those
#: sentences read as dangling references forever, which is how a checker's output stops being
#: read. With one, the fact lives in the document rather than in this file, and the retirement is
#: stated once where a reader of that document will see it.
RETIRED = re.compile(r'<!--\s*doc_check:\s*retired-series\s+(\S+)\s*->\s*(\S+)\s*-->')


def retired_series(pages):
    """`{old prefix: new prefix}` from every retirement marker in the tree."""
    out = {}
    for _rel, page in sorted(pages.items()):
        for m in RETIRED.finditer(page.text):
            out[m.group(1)] = m.group(2)
    return out


def all_open_questions(pages):
    """`{id: (page, is_open)}` across every page, so a reference can be resolved from anywhere."""
    out = {}
    for rel, page in sorted(pages.items()):
        for oq_id, (_line, is_open) in open_questions(page).items():
            out[oq_id] = (rel, is_open)
    return out


# --------------------------------------------------------------------------- plans


ITEM_ROW = re.compile(r'^\|\s*(IP-[A-Z]+-\d+)\s*\|')

#: The work-item status vocabulary. Fixed, because the column is read by eye to answer "what is
#: left" and by this tool to check the header count -- and because a status that is a sentence
#: cannot be either. Prose belongs in the title, which has no length limit.
#:
#: `withdrawn` is here beside `superseded`: an item raised on a premise that turned out to be
#: false is not superseded by anything, and saying so is more useful than flattening it.
STATUS_OK = re.compile(r'^(todo|active|done|superseded|withdrawn|blocked \(.+\))$')

#: Statuses that mean no further work is scheduled against the item.
FINISHED = ('done', 'superseded', 'withdrawn')
BLOCKED_NOTE = re.compile(r"^>\s*\*\*(IP-[A-Z]+-\d+)(?:'s former)?\s+blocked reason")
STATUS_LINE = re.compile(r'(\d+)\s+items done,\s*(\d+)\s*`?todo`?,\s*(\d+)\s+blocked')


def work_items(page):
    """One entry per work-item row: `(id, status, depends, line)`.

    The id, status, dependency and design-reference columns are read from the two ends of the
    row rather than by index, because a title legitimately contains a pipe inside a table or a
    code span and counting from the left would then read the wrong column.
    """
    out = []
    for n, line in enumerate(page.lines, 1):
        if not ITEM_ROW.match(line):
            continue
        fields = line.split('|')
        if len(fields) < 6:
            out.append((fields[1].strip(), fields[2].strip() if len(fields) > 2 else '',
                        '', n))
            continue
        out.append((fields[1].strip(), fields[2].strip(), fields[-3].strip(), n))
    return out


def _ids_in(text):
    return set(IP_HEADING_ID.findall(text)) | set(OQ_ANY.findall(text))


def check_plans(pages, oqs=None):
    """What an implementation plan promises about its own work items.

    A `blocked` status names what blocks it, inside the status cell, so the reader never has to
    find a note to learn that. Every id it names exists. Every open question it names is really
    open -- the check that goes stale the moment a question is answered, and the one most worth
    running. Every blocked item has its reason note. Every dependency exists, and no row stands
    before a row it depends on.
    """
    found = []
    oqs = all_open_questions(pages) if oqs is None else oqs
    known, status_of = {}, {}
    for rel, page in sorted(pages.items()):
        if page.is_plan:
            for item_id, status, _d, _n in work_items(page):
                known[item_id] = rel
                status_of[item_id] = status.split('(')[0].strip()
    for rel, page in sorted(pages.items()):
        if not page.is_plan:
            continue
        items = work_items(page)
        notes = set(m.group(1) for m in
                    (BLOCKED_NOTE.match(l) for l in page.lines) if m)
        order = dict((item_id, i) for i, (item_id, _s, _d, _n) in enumerate(items))
        for item_id, status, depends, line in items:
            if not STATUS_OK.match(status):
                found.append(Finding('status', rel, '%s has status %r, which is not one of '
                                     'todo / active / done / superseded / withdrawn / '
                                     'blocked (ids)' % (item_id, status[:60]), line))
            bare = status.split('(')[0].strip()
            if bare == 'blocked':
                if '(' not in status:
                    found.append(Finding('blocked', rel, '%s is blocked with no ids in the '
                                         'status cell' % item_id, line))
                else:
                    for ref in sorted(_ids_in(status)):
                        if ref.startswith('OQ-'):
                            if ref not in oqs:
                                found.append(Finding('blocked', rel, '%s is blocked on %s, '
                                                     'which does not exist'
                                                     % (item_id, ref), line))
                            elif not oqs[ref][1]:
                                found.append(Finding('blocked', rel, '%s is blocked on %s, '
                                                     'which is already resolved'
                                                     % (item_id, ref), line))
                        elif ref not in known:
                            found.append(Finding('blocked', rel, '%s is blocked on %s, which '
                                                 'does not exist' % (item_id, ref), line))
                        elif status_of[ref] in FINISHED:
                            # The same drift as blocking on a resolved question: the blocker
                            # finished and the status cell kept its name.
                            found.append(Finding('blocked', rel, '%s is blocked on %s, which is '
                                                 'already %s'
                                                 % (item_id, ref, status_of[ref]), line))
                if item_id not in notes:
                    found.append(Finding('blocked', rel, '%s is blocked with no blocked-reason '
                                         'note' % item_id, line))
            for ref in sorted(IP_HEADING_ID.findall(depends)):
                if ref not in known:
                    found.append(Finding('depends', rel, '%s depends on %s, which does not exist'
                                         % (item_id, ref), line))
                elif known[ref] == rel and order[ref] > order[item_id] and \
                        status.split('(')[0].strip() not in FINISHED and \
                        status_of[ref] not in FINISHED:
                    # Order is a scheduling property: nothing should be *planned* before what it
                    # needs. It stops meaning anything once either end is finished -- a done
                    # item's position is a historical record, and a dependency that is already
                    # done is satisfied wherever it sits. Re-sorting those rows would churn a
                    # long table to no effect.
                    found.append(Finding('topo', rel, '%s stands before %s, which it depends on'
                                         % (item_id, ref), line))
        m = STATUS_LINE.search(page.text)
        if m:
            counts = {'done': 0, 'todo': 0, 'blocked': 0}
            for _i, status, _d, _n in items:
                bare = status.split('(')[0].strip()
                if bare in counts:
                    counts[bare] += 1
            said = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            real = (counts['done'], counts['todo'], counts['blocked'])
            if said != real:
                where = page.text[:m.start()].count('\n') + 1
                found.append(Finding('plan-count', rel, 'header says %d done / %d todo / %d '
                                     'blocked; the table has %d / %d / %d'
                                     % (said + real), where))
    return found


def check_plan_index(pages):
    """Every plan is registered in the master index, and the index lists nothing that is gone."""
    found = []
    index = pages.get(PLAN_INDEX.replace(os.sep, '/'))
    if index is None:
        return [Finding('plan-index', PLAN_INDEX, 'the master index is missing')]
    # Resolved the way the index's own links resolve, from its own directory -- the index links
    # `../roadmap.md` as well as its plans, and that is a real page one level up.
    base = os.path.dirname(PLAN_INDEX.replace(os.sep, '/'))
    listed = {}
    for m in re.finditer(r'\[([^\]]+\.md)\]\(([^)\s]+\.md)\)', index.text):
        target = m.group(2).split('#')[0]
        listed[target] = os.path.normpath(os.path.join(base, target)).replace(os.sep, '/')
    for rel, page in sorted(pages.items()):
        if page.is_plan and rel not in listed.values():
            found.append(Finding('plan-index', PLAN_INDEX, '%s is not registered in the master '
                                 'index' % os.path.basename(rel)))
    for target, resolved in sorted(listed.items()):
        if resolved not in pages:
            found.append(Finding('plan-index', PLAN_INDEX,
                                 'the index lists %s, which does not exist' % target))
    return found


# --------------------------------------------------------------------------- references, prose


def check_references(pages):
    """Every `IP-` and `OQ-` id a document mentions in prose resolves to something real.

    This is what catches a reference to a work item that was never filed, and a reference to an
    open question that has been renumbered. Ids inside a page's own tables count as mentions too,
    so a dependency column naming a deleted item is caught here as well as by `check_plans`.

    An id in a series a document has declared retired is left alone -- see `RETIRED`. A *link*
    to one still fails, through `check_links`, because that is the case a reader can trip over.
    """
    found = []
    known_ip = set()
    for rel, page in sorted(pages.items()):
        if page.is_plan:
            known_ip |= set(i for i, _s, _d, _n in work_items(page))
    oqs = all_open_questions(pages)
    retired = retired_series(pages)
    for rel, page in sorted(pages.items()):
        seen = {}
        for n, line in enumerate(page.lines, 1):
            for ref in _ids_in(line):
                seen.setdefault(ref, n)
        for ref, n in sorted(seen.items()):
            if any(ref.startswith(old) for old in retired):
                continue
            if ref.startswith('IP-') and ref not in known_ip:
                found.append(Finding('references', rel, '%s is referenced and is not a work item '
                                     'in any plan' % ref, n))
            if ref.startswith('OQ-') and ref not in oqs:
                found.append(Finding('references', rel, '%s is referenced and has no subsection '
                                     'in any document' % ref, n))
    return found


def check_spelling(pages):
    """American English throughout, outside code spans."""
    found = []
    pattern = re.compile(r'\b(%s)\b' % '|'.join(sorted(BRITISH)), re.I)
    for rel, page in sorted(pages.items()):
        prose = strip_code(page.text)
        for m in pattern.finditer(prose):
            word = m.group(1)
            where = prose[:m.start()].count('\n') + 1
            found.append(Finding('spelling', rel, '%s -- use %s'
                                 % (word, BRITISH[word.lower()]), where))
    return found


def _match_case(word, replacement):
    if word.isupper():
        return replacement.upper()
    if word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def fix_spelling(text):
    """`(new_text, n)` with British spellings replaced outside code spans, case preserved.

    Driven off `strip_code`'s mask rather than off the text itself, and the mask is the same
    length as the text, so a match's offsets in the mask are its offsets in the original. That
    is what keeps a backticked identifier untouched while the prose around it is corrected.
    """
    pattern = re.compile(r'\b(%s)\b' % '|'.join(sorted(BRITISH)), re.I)
    masked = strip_code(text)
    out, last, n = [], 0, 0
    for m in pattern.finditer(masked):
        word = text[m.start():m.end()]
        if word.lower() not in BRITISH:
            continue
        out.append(text[last:m.start()])
        out.append(_match_case(word, BRITISH[word.lower()]))
        last = m.end()
        n += 1
    out.append(text[last:])
    return ''.join(out), n


def fix_spelling_tree(root=DOC):
    """Apply `fix_spelling` to every page. Returns `[(rel, n)]` for the pages that changed.

    Read and written as **bytes**, decoded and encoded explicitly: text mode would translate
    line endings on this platform, and every text file in this repository is stored with Unix
    endings on purpose -- `tools/geometry_version.py` fingerprints sources by content.
    """
    changed = []
    for rel, page in sorted(read_pages(root).items()):
        new, n = fix_spelling(page.text)
        if not n:
            continue
        with open(page.path, 'wb') as fh:
            fh.write(new.encode('utf-8'))
        changed.append((rel, n))
    return changed


CHECKS = (
    ('links', check_links),
    ('images', check_images),
    ('open-questions', check_open_questions),
    ('plans', check_plans),
    ('plan-index', check_plan_index),
    ('references', check_references),
    ('spelling', check_spelling),
)


def run(root=DOC, only=None):
    """Every check, or the named ones. Returns the findings in check order."""
    pages = read_pages(root)
    found = []
    for name, fn in CHECKS:
        if only and name not in only:
            continue
        found.extend(fn(pages))
    return found


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    quiet = '--quiet' in argv
    only = None
    for arg in argv:
        if arg.startswith('--check='):
            only = set(arg.split('=', 1)[1].split(','))
    if '--fix-spelling' in argv:
        changed = fix_spelling_tree()
        for rel, n in changed:
            print('    %-46s %d' % (rel, n))
        print('%d replacement(s) across %d page(s)'
              % (sum(n for _r, n in changed), len(changed)))
        return 0
    found = run(only=only)
    groups = {}
    for f in found:
        groups.setdefault(f.check, []).append(f)
    for name in sorted(groups):
        if not quiet:
            print('')
            print('%s  (%d)' % (name, len(groups[name])))
        for f in groups[name]:
            print('    %r' % f)
    if not quiet:
        print('')
        ran = [n for n, _f in CHECKS if not only or n in only]
        print('%d finding(s) from %d check(s): %s'
              % (len(found), len(ran), ', '.join(ran)))
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
