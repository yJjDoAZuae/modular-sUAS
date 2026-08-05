"""Render preview PNGs for every STL under a directory tree, in parallel.

A separate pass rather than a step inside the sweep. Imaging and geometry
generation have no reason to be coupled: previews can be regenerated after a
look change without re-solving any CSG, the pass can be re-run over output that
already exists, and -- because each STL is read and each PNG written with nothing
shared between them -- it parallelizes without coordination.

Processes, not threads. The work here is numpy-bound rather than blocked on a
subprocess, so threads would serialize on the GIL. (The reverse is true of the
OpenSCAD calls inside the sweep itself, where threads are correct precisely
because the wait happens inside a child process.)

Usage, from the repository root:

    uv run python src/Fuselage/tools/render_previews.py <dir> [options]

    --workers N     override the worker count
    --size WxH      output resolution (default 2048x1080)
    --force         re-render even when an up-to-date PNG exists
    --no-edges      disable edge detection
    --no-occlusion  disable ambient occlusion
    --dry-run       list what would be rendered and stop
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stl_preview  # noqa: E402


def choose_workers(requested: int | None = None) -> tuple[int, str]:
    """Pick a worker count, leaving one core for the rest of the machine.

    os.cpu_count() reports logical cores; these renders are arithmetic-bound and
    gain little from hyperthreading, so the physical count is the useful number and
    logical // 2 is the closest estimate available without adding psutil.
    """
    if requested:
        return max(1, requested), "requested"
    logical = os.cpu_count() or 2
    physical = max(1, logical // 2)
    return max(1, physical - 1), f"{physical} physical core(s) of {logical} logical, 1 reserved"


def find_jobs(root: Path, force: bool) -> list[Path]:
    """Every .stl under `root` that needs a preview, in a stable order.

    A PNG counts as current only if it is newer than its STL, so a re-run after a
    partial sweep picks up exactly what changed.
    """
    jobs = []
    for stl in sorted(root.rglob("*.stl")):
        png = stl.with_suffix(".png")
        if force or not png.exists() or png.stat().st_mtime < stl.stat().st_mtime:
            jobs.append(stl)
    return jobs


def _render_one(args: tuple[str, tuple[int, int], bool, bool]) -> tuple[str, str | None]:
    """Worker entry point. Returns (path, error) so a failure names its own file."""
    stl_path, size, edges, occlusion = args
    try:
        stl_preview.render_stl_to_png(
            stl_path,
            Path(stl_path).with_suffix(".png"),
            size=size,
            edges=edges,
            occlusion=occlusion,
        )
        return stl_path, None
    except Exception as exc:  # noqa: BLE001 - reported per file, never swallowed
        return stl_path, f"{type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="directory to walk for .stl files")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--size", default="2048x1080")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-edges", action="store_true")
    parser.add_argument("--no-occlusion", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        parser.error(f"not a directory: {args.root}")
    try:
        width, height = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        parser.error(f"--size must look like 2048x1080, got {args.size!r}")

    jobs = find_jobs(args.root, args.force)
    workers, why = choose_workers(args.workers)

    print(f"root      : {args.root}")
    print(f"to render : {len(jobs)} STL(s)")
    print(f"size      : {width}x{height}")
    print(f"workers   : {workers}  ({why})")
    print(f"edges     : {not args.no_edges}    occlusion: {not args.no_occlusion}")
    if not jobs:
        print("nothing to do -- every PNG is newer than its STL (use --force to override)")
        return 0
    if args.dry_run:
        for stl in jobs[:20]:
            print(f"  would render {stl}")
        if len(jobs) > 20:
            print(f"  ... and {len(jobs) - 20} more")
        return 0

    payload = [
        (str(p), (width, height), not args.no_edges, not args.no_occlusion) for p in jobs
    ]
    failures: list[tuple[str, str]] = []
    start = time.time()

    print("-" * 68, flush=True)
    with ProcessPoolExecutor(workers) as pool:
        futures = {pool.submit(_render_one, item): item[0] for item in payload}
        for done, future in enumerate(as_completed(futures), start=1):
            path, error = future.result()
            if error:
                failures.append((path, error))
                print(f"  FAILED  {Path(path).name}: {error}", flush=True)
            if done % 10 == 0 or done == len(payload):
                rate = (time.time() - start) / done
                remaining = (len(payload) - done) * rate
                print(
                    f"  {done}/{len(payload)}  {rate:.2f} s/render  "
                    f"~{remaining / 60:.1f} min left",
                    flush=True,
                )

    elapsed = time.time() - start
    print("-" * 68)
    print(f"rendered {len(payload) - len(failures)}/{len(payload)} in {elapsed / 60:.1f} min")
    if failures:
        print(f"{len(failures)} failure(s):")
        for path, error in failures[:20]:
            print(f"  {path}\n    {error}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
