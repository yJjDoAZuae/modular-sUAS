"""Compare FreeCAD-built parts by their serialized B-rep, exactly.

The counterpart of `params_snapshot.py` for the FreeCAD side, and the strongest verification
tier the project has: **it needs no tolerance at all.**

IP-FC-32 asked whether identical parameters produce byte-identical B-rep serialization.
Measured 2026-08-18 across five builds in five separate `freecadcmd` processes, two part
kinds: **they do.** The bulkhead's 150 `.brp` members hash identically across three runs, the
corner's 84 across two, and the exported STL is byte-identical in both kinds. So a B-rep
comparison is exact -- a difference is a difference, with no threshold to argue about and no
proxy standing in for the geometry.

**Compare the `.brp` members, never the `.FCStd` file.** A `.FCStd` is a zip, and 73 of the
bulkhead's 224 members differ between two runs that produced identical geometry:

- `Document.xml` -- creation and modification timestamps, a fresh UUID per document, and the
  document name, which follows the output filename.
- `StringHasher.Table.txt` -- FreeCAD's topological-naming hash IDs, assigned per session, so
  the same face is `H1323` in one run and `Ha75` in the next.
- `*.Shape.Map.txt` -- the element-name maps that reference those IDs.

None of that is geometry. Comparing whole documents, or their sizes, reports differences that
are not differences -- the same trap `mesh_stats` fell into with triangle counts (OQ-ARCH-16),
arriving by a different route.

**What this tier cannot do** is speak for the OpenSCAD path, which has no B-rep, or for parts
FreeCAD does not yet generate. It also says nothing about whether a *changed* B-rep changed
the shape meaningfully; when it reports a difference, `mesh_stats` and `surface_distance`
are what size it.

Usage, from the repository root:

    uv run python src/Fuselage/tools/brep_snapshot.py digest  <part.FCStd>
    uv run python src/Fuselage/tools/brep_snapshot.py capture <dir> <out.json>
    uv run python src/Fuselage/tools/brep_snapshot.py compare <before.json> <after.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

# Members that carry geometry. Everything else in the container is naming or metadata.
BREP_SUFFIX = ".brp"


def brep_members(path: Path) -> dict[str, str]:
    """Map of member name -> sha256, for the geometry members of one `.FCStd`."""
    with zipfile.ZipFile(path) as z:
        return {n: hashlib.sha256(z.read(n)).hexdigest()
                for n in sorted(z.namelist()) if n.lower().endswith(BREP_SUFFIX)}


def digest(path: Path) -> tuple[int, str]:
    """One hash over every geometry member, name included so a rename is a difference."""
    members = brep_members(path)
    h = hashlib.sha256()
    for name, member_hash in members.items():
        h.update(name.encode())
        h.update(member_hash.encode())
    return len(members), h.hexdigest()


def capture(root: Path, out: Path) -> int:
    docs = sorted(root.rglob("*.FCStd"))
    if not docs:
        sys.stderr.write(f"no .FCStd found under {root}\n")
        return 1
    snap = {}
    for d in docs:
        try:
            count, dg = digest(d)
        except (zipfile.BadZipFile, OSError) as exc:
            snap[d.relative_to(root).as_posix()] = {"error": str(exc)}
            continue
        snap[d.relative_to(root).as_posix()] = {"brep_members": count, "digest": dg,
                                                "members": brep_members(d)}
    out.write_text(json.dumps({"root": root.name, "documents": snap}, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"captured {len(snap)} document(s) -> {out}")
    return 0


def compare(before: Path, after: Path) -> int:
    a = json.loads(before.read_text(encoding="utf-8"))["documents"]
    b = json.loads(after.read_text(encoding="utf-8"))["documents"]
    changed, gone, added = [], sorted(set(a) - set(b)), sorted(set(b) - set(a))

    for name in sorted(set(a) & set(b)):
        if a[name].get("digest") != b[name].get("digest"):
            am, bm = a[name].get("members", {}), b[name].get("members", {})
            moved = [m for m in sorted(set(am) & set(bm)) if am[m] != bm[m]]
            changed.append((name, moved, sorted(set(am) ^ set(bm))))

    for name, moved, structural in changed:
        print(f"  CHANGED  {name}")
        if structural:
            print(f"           {len(structural)} member(s) added or removed: "
                  f"{', '.join(structural[:4])}")
        for m in moved[:6]:
            print(f"           {m}")
        if len(moved) > 6:
            print(f"           ... and {len(moved) - 6} more")
    for name in gone:
        print(f"  GONE     {name}")
    for name in added:
        print(f"  NEW      {name}")

    print("-" * 72)
    if changed or gone or added:
        print(f"B-REP CHANGED -- {len(changed)} document(s) differ, {len(gone)} gone, "
              f"{len(added)} new")
        return 1
    print(f"identical B-rep across {len(a)} document(s)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    d = sub.add_parser("digest")
    d.add_argument("path", type=Path)
    c = sub.add_parser("capture")
    c.add_argument("root", type=Path)
    c.add_argument("out", type=Path)
    p = sub.add_parser("compare")
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    args = parser.parse_args(argv)

    if args.action == "digest":
        count, dg = digest(args.path)
        print(f"{count} brep member(s)  {dg}")
        return 0
    if args.action == "capture":
        return capture(args.root, args.out)
    return compare(args.before, args.after)


if __name__ == "__main__":
    raise SystemExit(main())
