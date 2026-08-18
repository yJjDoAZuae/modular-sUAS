"""Prove a change to a `.scad` library altered no geometry, by re-rendering real parts.

The companion to `scad_snapshot.py`, for the case that tool cannot cover.

A generated `.scad` names its library by path and contains none of its text, so
editing a module under `scad/` leaves every generated file byte-identical.
`scad_snapshot.py compare` will report IDENTICAL no matter how badly such an edit
broke the geometry -- a false negative, and the one way that tooling can actively
mislead. Anything under `src/Fuselage/scad/` must be checked here instead.

The method: re-render the `.stl.scad` files already sitting in an output tree. Those
files pin every parameter exactly as it was when the reference `.stl` beside them was
produced, so the library is the only variable. Compare the results by measured
geometry -- triangle count, enclosed volume, bounding box -- via `mesh_stats`.

Each staged copy is written beside its original, because a generated `.scad` refers to
its library with a path relative to its own location; rendering it from anywhere else
would resolve `use <../../../../../scad/...>` to nothing.

Usage, from the repository root:

    uv run python src/Fuselage/tools/verify_scad_change.py <output_dir> [options]

    --scratch DIR    where to write the re-rendered STLs (default: a temp directory)
    --per-kind N     parts to sample per part kind (default 2)
    --workers N      concurrent OpenSCAD renders
    --tol FLOAT      volume tolerance, RELATIVE to each part's own volume (default 1e-6)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesh_stats  # noqa: E402

# One representative of each thing the sweep builds. A library change usually touches
# only some of these, but rendering all five is cheap next to being wrong.
PART_KINDS = ("corner", "bulkhead", "boom_bulkhead", "nose", "tail")


def openscad_binary():
    """Path to the OpenSCAD executable, or a clear failure.

    OPENSCADPATH holds the binary *directory* on this project -- a non-standard use
    that solid_render also depends on. See doc/guidelines/general.md.
    """
    root = os.environ.get("OPENSCADPATH")
    if not root:
        raise SystemExit(
            "OPENSCADPATH is not set. It must point at the OpenSCAD install "
            "directory, e.g. C:\\Program Files\\OpenSCAD"
        )
    return os.path.join(root, "openscad")


def sample_parts(output_dir: Path, per_kind: int) -> list[Path]:
    """A spread of parts per kind, taken across the range rather than adjacent.

    Sampling neighbours would exercise one corner of the parameter space; striding
    picks small and large U, which is where scale-dependent breakage shows up.
    """
    chosen: list[Path] = []
    for kind in PART_KINDS:
        matches = sorted(
            p for p in output_dir.rglob("*.stl.scad")
            if kind in p.name
            and not (kind == "bulkhead" and "boom_bulkhead" in p.name)
        )
        if not matches:
            continue
        step = max(1, len(matches) // per_kind)
        chosen.extend(matches[::step][:per_kind])
    return chosen


def _render(job):
    staged, out_stl, binary = job
    done = subprocess.run([binary, "-o", str(out_stl), str(staged)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return staged, out_stl, done.returncode


def verify(output_dir: Path, scratch: Path, per_kind=2, workers=4, tol=1e-6) -> int:
    binary = openscad_binary()
    parts = sample_parts(output_dir, per_kind)
    if not parts:
        print(f"no .stl.scad files under {output_dir} -- nothing to verify")
        return 1

    scratch.mkdir(parents=True, exist_ok=True)
    print(f"re-rendering {len(parts)} part(s) against the current library\n")

    jobs, staged_files = [], []
    for scad in parts:
        staged = scad.parent / (scad.stem + ".verify.scad")
        shutil.copyfile(scad, staged)
        staged_files.append(staged)
        jobs.append((staged, scratch / scad.name.replace(".stl.scad", ".stl"), binary))

    failures = []
    try:
        with concurrent.futures.ThreadPoolExecutor(workers) as pool:
            for _staged, out_stl, code in pool.map(_render, jobs):
                if code:
                    failures.append((out_stl.name, code))
    finally:
        # Always clean up, including on Ctrl-C: these sit inside the user's output
        # tree, where a stray .verify.scad would look like real output.
        for staged in staged_files:
            staged.unlink(missing_ok=True)

    mismatches = []
    for scad in parts:
        name = scad.name.replace(".stl.scad", ".stl")
        before, after = scad.parent / name, scratch / name
        if not after.is_file():
            continue
        try:
            a, b = mesh_stats.mesh_stats(before), mesh_stats.mesh_stats(after)
        except (mesh_stats.TruncatedMesh, ValueError, OSError) as exc:
            mismatches.append((name, f"unreadable: {exc}"))
            continue
        if mesh_stats.same_geometry(a, b, tol, mesh_stats.u_of_name(name)):
            print(f"  OK    {name[:66]}")
        else:
            print(f"  DIFF  {name[:66]}")
            mismatches.append((name, mesh_stats.describe_difference(a, b)))

    print("-" * 72)
    for name, why in mismatches:
        print(f"  DIFFERS  {name}\n           {why}")
    for name, code in failures:
        print(f"  RENDER FAILED  {name} (exit {code})")

    if mismatches or failures:
        print("GEOMETRY CHANGED -- investigate before continuing")
        return 1
    print(f"IDENTICAL GEOMETRY across {len(parts)} part(s)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="an output tree with rendered parts")
    parser.add_argument("--scratch", type=Path, default=None)
    parser.add_argument("--per-kind", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--tol", type=float, default=mesh_stats.VOLUME_TOL,
                        help="volume tolerance, relative to the part's own volume")
    args = parser.parse_args(argv)

    if not args.output.is_dir():
        parser.error(f"not a directory: {args.output}")

    if args.scratch:
        return verify(args.output, args.scratch, args.per_kind, args.workers, args.tol)
    with tempfile.TemporaryDirectory(prefix="verify_scad_") as tmp:
        return verify(args.output, Path(tmp), args.per_kind, args.workers, args.tol)


if __name__ == "__main__":
    raise SystemExit(main())
