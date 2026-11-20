"""Where one section outline touches another: the runs of samples within a tolerance of it.

**What it is for.** When a cut returns the wall in several solids, each detached strip parted from
the main body somewhere, and the place it parted is the question. At one station the strip's
section is an outline; walking along it, the samples that lie on the main body's section mark the
seam, and the samples that do not are free boundary (a slot face, say, with air across it). This
module turns a list of per-sample distances into those seams.

**A seam is a run, not a point.** Contact can be one crossing point or a stretch, and an outline
can touch in more than one place, so the answer is a list of runs, each reported by its first,
last and middle sample. The middle sample is the one a caller measures at.

**A closed outline wraps.** A section wire is closed, so a run that crosses the sample list's end
is one run, not two. `closed=True` joins them.

**Kernel-free by the package rule.** The caller computes the distances under `freecadcmd`; here
they are only numbers, which is what lets a test place a seam exactly where it wants one.
"""


def contact_runs(distances_m, tol_m, closed=True):
    """The runs of consecutive samples with `distance <= tol_m`, as `(first, last, middle)`.

    Indices refer to `distances_m`. A run that wraps the end of a closed outline has
    `first > last`, and its `middle` is counted around the wrap. An outline wholly in contact is
    one run, `(0, n - 1, n // 2)`. Returns `[]` for no contact or no samples.
    """
    n = len(distances_m)
    hit = [d <= tol_m for d in distances_m]
    if n == 0 or not any(hit):
        return []
    if all(hit):
        return [(0, n - 1, n // 2)]
    runs = []
    i = 0
    while i < n:
        if not hit[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and hit[j + 1]:
            j += 1
        runs.append([i, j])
        i = j + 1
    if closed and len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == n - 1:
        last = runs.pop()
        runs[0] = [last[0], runs[0][1]]
    out = []
    for first, last in runs:
        length = (last - first) % n + 1
        out.append((first, last, (first + length // 2) % n))
    return out
