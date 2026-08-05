"""Verify a sweep's output: completeness, integrity, and agreement with a reference.

Three checks the sweep itself cannot make, because each needs a view of the whole
output tree rather than of one part:

**Integrity** -- every `.stl` parses as a whole mesh. A killed render leaves a
partial file that existence checks treat as finished, so counting files proves
nothing. See `mesh_stats.TruncatedMesh`.

**Family completeness** -- every scaling family carries the same set of parts. A
family is one `U` scale plus one panel stock, which is what makes a set of parts
mutually buildable. Sweep totals look correct while one family is quietly short,
because a total cannot see the shape of what is missing.

**Reference agreement** -- each part matches a known-good render by measured
geometry rather than by bytes. Generated output is not stable byte-for-byte, so a
file diff reports differences that are not differences.

Usage, from the repository root:

    uv run python src/Fuselage/tools/sweep_check.py <output_dir> [options]

    --reference DIR   compare every part against the same part in DIR
    --tol FLOAT       volume tolerance for the comparison (default 1e-6)
    --quiet           report only failures

Originally written for a migration tool that has since been discarded. See the
guidelines on keeping capability in the durable code.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesh_stats  # noqa: E402


def scaling_family(rel: str) -> str:
    """The family a part belongs to: one U scale plus one panel stock.

    That pair defines a set of parts as mutually compatible, so it is the unit
    worth checking -- a directory here is meant to be a buildable set. Cowls carry
    no panel level, because a cowl is defined against the OML, not against a panel.
    """
    parts = rel.replace(os.sep, "/").split("/")
    if len(parts) >= 3 and parts[1] in ("imperial", "metric"):
        return "/".join(parts[:3])
    return parts[0]


def part_id(rel: str) -> str:
    """A part's identity within its family: its name minus the scale/panel prefix.

    `U_2.0__imperial_panel_1_8in__corner_FX_3.0.stl` -> `corner_FX_3.0.stl`, which
    every other family should also carry.
    """
    return rel.replace(os.sep, "/").rsplit("/", 1)[-1].split("__")[-1]


def find_stls(root: Path) -> list[tuple[Path, str]]:
    """Every .stl under root, paired with its path relative to root."""
    return [(p, str(p.relative_to(root))) for p in sorted(root.rglob("*.stl"))]


def check_integrity(entries, quiet=False):
    """Measure every mesh. Returns (stats_by_rel, failures)."""
    stats, failures = {}, []
    for path, rel in entries:
        try:
            stats[rel] = mesh_stats.mesh_stats(path)
        except (mesh_stats.TruncatedMesh, ValueError, OSError) as exc:
            failures.append((rel, str(exc)))
            stats[rel] = None
    if not quiet:
        whole = sum(1 for v in stats.values() if v)
        print(f"  integrity : {whole}/{len(entries)} meshes parse as complete")
    for rel, msg in failures:
        print(f"    TRUNCATED  {rel}\n               {msg}")
    return stats, failures


def check_families(entries, quiet=False):
    """Flag scaling families short of parts. Returns the list of short families.

    The expected set is what *most* families carry, not the union of all of them.
    Some legitimately carry more: the panel_0mm family also holds the cowling
    bulkheads, which mate the fuselage to a cowl and so are dimensioned against the
    OML rather than any panel stock. Measured against the union, those extras make
    most families read as short of parts they were never meant to have.
    """
    families: dict[str, set[str]] = {}
    for _path, rel in entries:
        families.setdefault(scaling_family(rel), set()).add(part_id(rel))

    panelled = {k: v for k, v in families.items() if "/" in k}
    if not panelled:
        return []

    counts: dict[frozenset, int] = {}
    for parts in panelled.values():
        key = frozenset(parts)
        counts[key] = counts.get(key, 0) + 1
    expected = max(counts, key=lambda k: (counts[k], len(k)))

    short = sorted((k for k in panelled if expected - panelled[k]),
                   key=lambda k: (len(panelled[k]), k))
    extra = sorted(k for k in panelled if panelled[k] - expected)

    if not quiet:
        print(f"  families  : {len(panelled)} (one U scale + one panel stock each), "
              f"{len(families) - len(panelled)} cowl set(s)")
        if extra:
            sample = sorted(panelled[extra[0]] - expected)
            print(f"              {len(extra)} carry parts beyond the common set of "
                  f"{len(expected)}, as expected: "
                  + ", ".join(sample[:3]) + (" ..." if len(sample) > 3 else ""))
        if not short:
            print(f"              every family carries all {len(expected)} common parts")

    for key in short[:12]:
        missing = sorted(expected - panelled[key])
        print(f"    SHORT  {key:<38} {len(panelled[key])}/{len(expected)}  missing "
              + ", ".join(missing[:3]) + (" ..." if len(missing) > 3 else ""))
    if len(short) > 12:
        print(f"    ... {len(short) - 12} more short families")
    return short


def check_reference(stats, reference: Path, tol: float, quiet=False):
    """Compare each measured part against the same part in a reference tree."""
    mismatches, missing = [], []
    ref_index = {str(p.relative_to(reference)): p for p in reference.rglob("*.stl")}

    for rel, measured in stats.items():
        ref_path = ref_index.get(rel)
        if ref_path is None:
            missing.append(rel)
            continue
        try:
            expected = mesh_stats.mesh_stats(ref_path)
        except (mesh_stats.TruncatedMesh, ValueError, OSError) as exc:
            mismatches.append((rel, f"reference unreadable: {exc}"))
            continue
        if not mesh_stats.same_geometry(measured, expected, tol):
            mismatches.append((rel, mesh_stats.describe_difference(expected, measured)))

    only_in_ref = sorted(set(ref_index) - set(stats))
    if not quiet:
        print(f"  reference : {len(stats) - len(mismatches) - len(missing)}"
              f"/{len(stats)} parts match {reference.name}")
    for rel in missing[:10]:
        print(f"    NOT IN REFERENCE  {rel}")
    for rel in only_in_ref[:10]:
        print(f"    MISSING FROM OUTPUT  {rel}")
    for rel, why in mismatches[:10]:
        print(f"    DIFFERS  {rel}\n             {why}")
    if len(mismatches) > 10:
        print(f"    ... {len(mismatches) - 10} more differing parts")
    return mismatches, missing, only_in_ref


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="sweep output directory to check")
    parser.add_argument("--reference", type=Path, default=None)
    parser.add_argument("--tol", type=float, default=1e-6)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.output.is_dir():
        parser.error(f"not a directory: {args.output}")
    if args.reference and not args.reference.is_dir():
        parser.error(f"not a directory: {args.reference}")

    entries = find_stls(args.output)
    print(f"checking {len(entries)} STL(s) under {args.output}")
    if not entries:
        print("  nothing to check")
        return 1

    stats, truncated = check_integrity(entries, args.quiet)
    short = check_families(entries, args.quiet)

    mismatches = missing = only_in_ref = []
    if args.reference:
        mismatches, missing, only_in_ref = check_reference(
            {k: v for k, v in stats.items() if v}, args.reference, args.tol, args.quiet
        )

    problems = len(truncated) + len(short) + len(mismatches) + len(missing) + len(only_in_ref)
    print("-" * 68)
    if problems:
        print(f"FAILED: {len(truncated)} truncated, {len(short)} short families, "
              f"{len(mismatches)} differing, {len(missing) + len(only_in_ref)} unpaired")
    else:
        print("OK: every mesh complete, every family full"
              + (", every part matches the reference" if args.reference else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
