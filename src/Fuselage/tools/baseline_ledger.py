"""The list of differences from the frozen baseline that are known, explained and accepted.

OQ-ARCH-15 decided on 2026-08-18 that `variant_output_baseline` does not move for the rest
of the port. That decision only works if departures from it are *enumerated and justified*
rather than absorbed: re-baselining compares each change against the state just before it,
so every step passes while the total wanders. The ledger is where the accumulated wandering
is written down, one group per cause, so that a comparison can be green on what is known and
red the instant something new appears.

**A ledger entry is a claim that a difference is correct, not that it is small.** Each group
names the commit that caused it and why that commit was right. A part not in the ledger is a
failure by default, which is the whole point -- silence is not acceptance.

**What it does not do** is decide whether the accumulated total is acceptable. That judgement
belongs to the review at the `PartDesign::` end state, where OQ-ARCH-15 places a person
signing off on the whole accumulated difference before the baseline is retired.

Usage, from the repository root:

    uv run python src/Fuselage/tools/baseline_ledger.py check <tree> [--manifest M] [--ledger L]

Compares a rendered tree against the manifest, subtracts the accepted departures, and reports
only what is left. Exit 0 when everything that differs is accounted for.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesh_stats  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "baseline_manifest.json"
DEFAULT_LEDGER = HERE / "baseline_ledger.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def accepted_parts(ledger: dict) -> dict[str, str]:
    """Map of part path -> the id of the group that accepts it."""
    out = {}
    for group in ledger.get("accepted", []):
        for part in group["parts"]:
            out[part] = group["id"]
    return out


def check(tree: Path, manifest_path: Path, ledger_path: Path) -> int:
    manifest = load(manifest_path)["parts"]
    ledger = load(ledger_path)
    accepted = accepted_parts(ledger)

    unexplained, accounted, missing = [], 0, []
    for rel, want in sorted(manifest.items()):
        p = tree / rel
        if not p.exists():
            missing.append(rel)
            continue
        try:
            got = mesh_stats.mesh_stats(p)
        except (mesh_stats.TruncatedMesh, ValueError, OSError) as exc:
            unexplained.append((rel, f"unreadable: {exc}"))
            continue
        if mesh_stats.same_geometry(want, got, u=mesh_stats.u_of_name(rel)):
            continue
        if rel in accepted:
            accounted += 1
            continue
        unexplained.append((rel, mesh_stats.describe_difference(want, got)))

    for rel, why in unexplained:
        print(f"  UNEXPLAINED  {rel}\n               {why}")
    for rel in missing:
        print(f"  MISSING      {rel}")

    print("-" * 72)
    print(f"{len(manifest)} part(s): {accounted} accepted departure(s), "
          f"{len(unexplained)} unexplained, {len(missing)} missing")
    for group in ledger.get("accepted", []):
        print(f"    {group['id']:44} {len(group['parts']):>4} part(s)  {group['commit']}")
    if unexplained or missing:
        print("\nNOT ACCOUNTED FOR -- every difference from the frozen baseline must be "
              "either in the ledger with a reason, or fixed")
        return 1
    print("\nevery difference from the frozen baseline is accounted for")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("check",))
    parser.add_argument("tree", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args(argv)
    if not args.tree.is_dir():
        sys.stderr.write(f"not a directory: {args.tree}\n")
        return 1
    return check(args.tree, args.manifest, args.ledger)


if __name__ == "__main__":
    raise SystemExit(main())
