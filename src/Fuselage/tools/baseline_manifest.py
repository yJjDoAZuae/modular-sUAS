"""Make the frozen reference baseline a tracked artifact instead of an untracked tree.

OQ-ARCH-15 decided on 2026-08-18 that `variant_output_baseline` does not move for the
rest of the port: it stays the authority, and every departure from it is enumerated and
justified rather than absorbed by re-baselining. Re-establishing the reference as work
proceeds compares each change against the state just before it, so every individual step
passes while the total wanders -- the drift is undetectable precisely because no single
comparison ever sees it.

Freezing a reference raises two questions this module answers, and one it cannot.

**What is the baseline?** Nothing recorded it. The tree carries no statement of the
commit that produced it, and it is not in fact a render of this repository at all: its
stored `.stl.scad` files name their library under the pre-migration
`Archive\\Alex\\Designs\\modular_sUAS\\Fuselage\\` tree. A ledger of departures means
nothing without a statement of what they depart from, so the manifest records that
provenance explicitly rather than leaving it to be rediscovered by whoever next reads a
generated file.

**Where does the authority live?** In an untracked directory -- `.gitignore` excludes
`variant_output*/`, so all 576 parts and 2.4 GB of it are outside version control. An
authority that is frozen for the length of a migration and exists only on one share is
one disk failure from gone, and this project has already lost the share for long enough
to notice. So the manifest stores each part's *measured geometry* rather than a hash of
its bytes. That makes it the reference in its own right: 576 rows that fit in version
control, that a comparison can run against with the 2.4 GB tree absent entirely, and
that cost the same single read pass to produce as a checksum would have.

**What it cannot answer** is whether the accumulated difference is acceptable. That is a
judgement, taken at review time against the ledger of accepted departures (IP-FC-80),
and OQ-ARCH-15 places it after the `PartDesign::` end state with a person signing it off.

Usage, from the repository root:

    uv run python src/Fuselage/tools/baseline_manifest.py capture <tree> <manifest.json>
    uv run python src/Fuselage/tools/baseline_manifest.py verify  <tree> <manifest.json>

`capture` reads every `.stl` under the tree and measures it. `verify` re-measures and
reports any part that has moved, which is how the frozen baseline is checked for having
been altered underneath the work that depends on it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesh_stats  # noqa: E402

MANIFEST_VERSION = 1

# Recorded rather than inferred. The baseline predates this repository, so "the commit it
# was built from" does not exist and must not be fabricated by writing down whatever HEAD
# happened to be at capture time. See the module docstring.
PROVENANCE_NOTE = (
    "This tree is NOT a render of this repository. Its stored .stl.scad files name their "
    "library under the pre-migration Archive/Alex/Designs/modular_sUAS/Fuselage tree, so "
    "no commit here produced it and none should be recorded as though one had. It is the "
    "frozen reference for the FreeCAD port per OQ-ARCH-15, and is retired only after the "
    "PartDesign end state, on a reviewed sign-off."
)


def git_head() -> str | None:
    """The commit the manifest was *captured* at -- not the one the tree was built from."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def measure_tree(tree: Path) -> tuple[dict, list[str]]:
    """Measure every `.stl` under `tree`, keyed by path relative to it.

    Unreadable and truncated parts are collected rather than raised on, because a
    baseline with a bad file in it is a fact to report, not a reason to produce nothing.
    """
    parts, bad = {}, []
    for stl in sorted(tree.rglob("*.stl")):
        if stl.name.endswith(".partial.stl"):
            continue
        rel = stl.relative_to(tree).as_posix()
        try:
            parts[rel] = mesh_stats.mesh_stats(stl)
        except (mesh_stats.TruncatedMesh, ValueError, OSError) as exc:
            bad.append(f"{rel}: {exc}")
    return parts, bad


def capture(tree: Path, out: Path) -> int:
    parts, bad = measure_tree(tree)
    if not parts:
        sys.stderr.write(f"no .stl found under {tree}\n")
        return 1
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "tree_name": tree.name,
        "note": PROVENANCE_NOTE,
        "captured_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "captured_at_repo_commit": git_head(),
        "source_repository": "pre-migration Archive/Alex/Designs/modular_sUAS -- see note",
        "part_count": len(parts),
        "unreadable": bad,
        "parts": parts,
    }
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"captured {len(parts)} part(s) -> {out}")
    if bad:
        print(f"  {len(bad)} unreadable, recorded in the manifest:")
        for line in bad[:10]:
            print(f"    {line}")
    return 0


def verify(tree: Path, manifest_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = manifest["parts"]
    measured, bad = measure_tree(tree)

    moved, missing = [], []
    for rel, want in sorted(recorded.items()):
        got = measured.get(rel)
        if got is None:
            missing.append(rel)
            continue
        if not mesh_stats.same_geometry(want, got, u=mesh_stats.u_of_name(rel)):
            moved.append((rel, mesh_stats.describe_difference(want, got)))
    added = sorted(set(measured) - set(recorded))

    for rel, why in moved:
        print(f"  MOVED    {rel}\n           {why}")
    for rel in missing:
        print(f"  MISSING  {rel}")
    for rel in added:
        print(f"  ADDED    {rel}")
    for line in bad:
        print(f"  UNREADABLE  {line}")

    print("-" * 72)
    if moved or missing or added or bad:
        print(f"BASELINE ALTERED -- {len(moved)} moved, {len(missing)} missing, "
              f"{len(added)} added, {len(bad)} unreadable")
        return 1
    print(f"baseline intact across {len(recorded)} part(s)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("capture", "verify"):
        p = sub.add_parser(name)
        p.add_argument("tree", type=Path, help="the rendered baseline tree")
        p.add_argument("manifest", type=Path, help="the manifest JSON to write or read")
    args = parser.parse_args(argv)
    if not args.tree.is_dir():
        sys.stderr.write(f"not a directory: {args.tree}\n")
        return 1
    return capture(args.tree, args.manifest) if args.action == "capture" \
        else verify(args.tree, args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
