"""IP-FC-97: DRW-7, the half of determinism that one process cannot see.

    freecadcmd check_placement_determinism.py
    freecadcmd check_placement_determinism.py --pass --perturb

**What DRW-7 says.** The same family produces byte-identical placement on every run: no
unseeded randomness, no dependence on dictionary or set iteration order, every tie broken by a
stated total order. It exists because a generator whose output moves between runs makes *"did
this drawing change?"* unanswerable, and a drawing set that cannot be diffed cannot be
reviewed. [dimension_scheme.md](../../../doc/design/dimension_scheme.md) section 5.5 says not to
introduce a second source of nondeterminism where a human is the consumer; the project already
has one in OpenSCAD's facet ordering.

**What was already checked, and what it could not reach.** `check_dimension_placement.py`
places every case twice with the inputs reversed and compares the signatures, which covers
*input order*. It cannot cover *iteration order*, because *`PYTHONHASHSEED` is fixed for the
life of a process*: a placer that iterated a `set` of strings would produce the same wrong
order in both halves of that comparison and pass. The failure DRW-7 names is only visible
across processes, and that is what this adds.

**Verified 2026-09-06 that the seeding actually takes effect**, because a cross-process hash
test that silently fails to vary the seed is a check that compares nothing: `freecadcmd`
honours `PYTHONHASHSEED`, giving `hash('probe')` of 7018796803104437630, 4008879868145172077
and -9081287195077309814 for seeds 1, 2 and 3. **The check re-establishes this every run** --
each child reports its own `hash` probe, and identical probes are a failure rather than a pass,
whatever the digests say. That is the difference between this check and one that would go green
on a machine where the seeding quietly stopped working.

**The comparison is over a digest of the whole corpus**, not a per-case pass. Placement is
serialised to text -- letter, side, lane, offset and text box for each dimension; key, side and
box for each note; and the *refusals*, since a refusal that flips between runs is exactly the
nondeterminism being looked for -- and hashed. Two runs agree or they do not.

**A determinism check that has never failed is indistinguishable from one that compares
nothing**, so `--perturb` breaks the placer on purpose and requires the check to go red.

- *Output order.* `place` is wrapped to return its layout ordered by `hash(letter)` instead of
  canonically. This mimics a placer that emitted its annotations in set-iteration order, and it
  is hash-seed dependent by construction, so it **must** be caught. If it is not, this check is
  broken and says so.
- *Search order.* `_note_assignments` is wrapped to yield candidate side-assignments in
  hash order rather than best-first, which mimics a search whose tie-breaking came from a set.
  It was carried as the one that might legitimately change nothing -- if only one assignment
  ever placed cleanly, reordering the candidates could not alter the winner -- so its result is
  reported rather than required. **Measured 2026-09-06 it changes everything: four seeds, four
  different digests.** More than one side assignment places cleanly on this corpus, so
  `_note_assignments` yielding *best first* is load-bearing rather than a preference, and a
  note's side is decided by that order. This is the movement section 5.5 was written against at
  its largest: not a lane shuffle but an annotation crossing to the other side of the sheet.

The corpus is `check_dimension_placement`'s, reused rather than restated: the same seven
placement cases and the same corner family and single-variant sheets over every frame region.
Two statements of one corpus would drift, and the one that moved would win silently.
"""
import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_dimension_placement as cdp
import dimension_placement as dp
from corner_common import is_entry_point

#: The seeds the children are run under. Four, because the question is whether *any* pair
#: disagrees and a wider spread costs only startup -- measured at 0.24 s per `freecadcmd`
#: (IP-FC-1). They are fixed rather than random so a failure can be reproduced by hand.
SEEDS = ('1', '2', '3', '17')

#: What each child prints, and this parses. Tagged so `freecadcmd`'s own banner and any
#: warning the corpus emits cannot be mistaken for a result.
PROBE_TAG = 'PROBE '
DIGEST_TAG = 'DIGEST '


def _flag(name):
    return ('--%s' % name) in sys.argv


def perturb_output_order():
    """Return the layout in `hash(letter)` order: a placer that emitted from a set."""
    original = dp.place

    def placed_in_hash_order(*args, **kwargs):
        layout = original(*args, **kwargs)
        return dp.Layout(sorted(layout, key=lambda p: hash(p.letter)), layout.notes)

    dp.place = placed_in_hash_order


def perturb_search_order():
    """Yield side-assignments in hash order: a search whose ties came from a set."""
    original = dp._note_assignments

    def assignments_in_hash_order(notes, geometry_bbox):
        candidates = list(original(notes, geometry_bbox))
        candidates.sort(key=lambda a: hash(tuple(sorted((str(k), v) for k, v in a.items()))))
        return iter(candidates)

    dp._note_assignments = assignments_in_hash_order


def corpus():
    """Every layout the placer produces on the project's corpus, in a fixed order.

    A refusal is a result and is recorded as one. `PlacementError` carries the reason, and a
    reason that changes between runs is as much a diff in the drawing set as a moved lane.
    """
    out = []
    for name, build in cdp.CASES:
        try:
            out.append((name, dp.place(build(), cdp.BBOX, cdp.FRAME, cdp.EDGES)))
        except dp.PlacementError as exc:
            out.append((name, exc))

    for region, width, height in cdp.sheet_regions():
        frame = cdp.centred_frame(width, height)
        for product, notes, valued in (('family sheet', cdp.NOTES_FAMILY, False),
                                       ('single-variant', cdp.NOTES_VARIANT, True)):
            label = '%s / %s' % (region, product)
            try:
                out.append((label, dp.place(cdp.corner_dimensions(valued), cdp.CORNER_BBOX,
                                            frame, cdp.CORNER_EDGES,
                                            notes=cdp.corner_notes(notes))))
            except dp.PlacementError as exc:
                out.append((label, exc))
    return out


def serialise(entries):
    """The corpus as text, which is what actually gets compared."""
    lines = []
    for label, result in entries:
        if isinstance(result, dp.PlacementError):
            lines.append('%s\tREFUSED\t%s' % (label, str(result).replace(chr(10), ' | ')))
            continue
        lines.append('%s\t%r\t%r' % (label, cdp._placement_signature(result),
                                     cdp._note_signature(result)))
    return chr(10).join(lines)


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


#: The deliberate breakages, each run on its own so its effect is attributable. Keyed by the
#: flag the child is given, since `freecadcmd` forwards flags and not objects.
PERTURBATIONS = (('output-order', 'perturb-output', True),
                 ('search-order', 'perturb-search', False))


def emit():
    """The child. One line of probe, one of digest, and nothing else that matters."""
    if _flag('perturb-output'):
        perturb_output_order()
    if _flag('perturb-search'):
        perturb_search_order()
    print('%s%d' % (PROBE_TAG, hash('probe')))
    print('%s%s' % (DIGEST_TAG, digest(serialise(corpus()))))
    sys.stdout.flush()
    return 0


def run_child(seed, flag=None):
    """One placement run in its own interpreter, under `seed`.

    `freecadcmd` forwards one script argument per `--pass`, so each flag needs its own.
    """
    env = dict(os.environ)
    env['PYTHONHASHSEED'] = seed
    argv = [sys.executable, os.path.abspath(__file__), '--pass', '--emit']
    if flag:
        argv += ['--pass', '--%s' % flag]
    done = subprocess.run(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    probe = found = None
    for line in done.stdout.decode('utf-8', 'replace').splitlines():
        if line.startswith(PROBE_TAG):
            probe = line[len(PROBE_TAG):].strip()
        elif line.startswith(DIGEST_TAG):
            found = line[len(DIGEST_TAG):].strip()
    if found is None:
        raise RuntimeError('the child under PYTHONHASHSEED=%s printed no digest.%s%s'
                           % (seed, chr(10),
                              done.stderr.decode('utf-8', 'replace')[-2000:]))
    return probe, found


def across_processes(flag=None):
    """Run the corpus under every seed. Returns `(probes, digests)` keyed by seed."""
    probes, digests = {}, {}
    for seed in SEEDS:
        probes[seed], digests[seed] = run_child(seed, flag)
        print('    seed %-3s  hash(probe) %21s  digest %s'
              % (seed, probes[seed], digests[seed][:16]))
    return probes, digests


def main():
    if _flag('emit'):
        return emit()

    fail = []
    print('CHECK:: placement determinism (DRW-7)')

    # ---- one process, twice. The cheap half, and it covers the run-to-run state a module
    # ---- can accumulate -- caches, counters, anything the second call sees and the first
    # ---- did not. Input-order independence is `check_dimension_placement`'s and is not
    # ---- repeated here.
    first, second = serialise(corpus()), serialise(corpus())
    print('  same process, placed twice   %s'
          % ('identical' if first == second else 'DIFFERENT'))
    if first != second:
        fail.append('the placer does not reproduce within a single process')

    # ---- across processes, which is the half nothing reached before.
    print('  across processes, %d seeds:' % len(SEEDS))
    probes, digests = across_processes()

    if len(set(probes.values())) == 1:
        print('    every child hashed the same, so PYTHONHASHSEED is not taking effect and '
              'this comparison proves nothing')
        fail.append('PYTHONHASHSEED did not vary between children: the cross-process test is '
                    'vacuous, and a green result here would be meaningless')
    elif len(set(digests.values())) == 1:
        print('    one digest across %d hash seeds: placement does not depend on iteration '
              'order' % len(SEEDS))
    else:
        print('    %d different digests: placement depends on something that varies between '
              'runs' % len(set(digests.values())))
        fail.append('placement is not reproducible across processes')

    # ---- and the check must be able to fail.
    if _flag('perturb'):
        for name, flag, required in PERTURBATIONS:
            print('  deliberately broken -- %s:' % name)
            _p, broken = across_processes(flag)
            spread = len(set(broken.values()))
            if spread > 1:
                print('    %d digests from %d seeds: the comparison sees this disorder'
                      % (spread, len(SEEDS)))
            elif set(broken.values()) != set(digests.values()):
                print('    one digest, but not the clean one: this changes the layout the '
                      'same way every run, so it is not a determinism failure to catch')
            elif required:
                print('    one digest, equal to the clean one  <-- FAIL')
                fail.append('the %s perturbation was not detected, so this check cannot see '
                            'the failure it exists for' % name)
            else:
                print('    no effect, and that is a fact about the corpus rather than about '
                      'the check: only one side assignment places cleanly, so reordering the '
                      'candidates cannot change which one wins')

    print('')
    for problem in fail:
        print('  FAIL: %s' % problem)
    print('DRW-7: %s' % ('OK' if not fail else '%d CHECK(S) FAILED' % len(fail)))
    sys.stdout.flush()
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
