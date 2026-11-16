"""Where a frame of the pixel maps spends its time: the product step on a run, with a timer round every part.

    python s04_profile.py RUN OUT [--blocks N] [--backend gpu|cpu]

Run with the engine folder as the working directory (its ``wadi2d`` is the one imported). RUN is a remake folder of
``s02_remake.py`` (its configuration and a link to the run's results); the rasters land in OUT. The device is
synchronised before and after each timed part, so the parts add up and do not overlap; the whole is then a little
slower than the step alone. ``--blocks`` stops after that many blocks. Writes OUT/profile.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.io.progress import Progress  # noqa: E402
from wadi2d.products import blocks as blocks_mod  # noqa: E402
from wadi2d.products import pixels as pixels_mod  # noqa: E402
from wadi2d.products import step as step_mod  # noqa: E402
from wadi2d.products import strip_pixels as strip_mod  # noqa: E402
from wadi2d.products import surface as surface_mod  # noqa: E402

TIMES: dict[str, float] = defaultdict(float)
COUNTS: dict[str, int] = defaultdict(int)
XP = [np]


class Enough(Exception):
    pass


def sync() -> None:
    if XP[0] is not np:
        XP[0].cuda.Device().synchronize()


def timed(name: str, fn, host: bool = False):
    """``host``: work on the host alone, timed without waiting on the card (it may run on a lane beside it)."""

    def inner(*a, **k):
        if not host:
            sync()
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            if not host:
                sync()
            TIMES[name] += time.perf_counter() - t
            COUNTS[name] += 1

    return inner


def patch_light(max_blocks: int) -> None:
    """Only the block's parts and what the main thread waits on: the lanes' work is not synchronised (W93)."""
    import concurrent.futures as cf
    import threading

    from wadi2d.products.ground import CellReader

    main_thread = threading.main_thread()
    real_result = cf.Future.result

    def result(self, *a, **k):
        if threading.current_thread() is not main_thread:
            return real_result(self, *a, **k)
        t = time.perf_counter()
        try:
            return real_result(self, *a, **k)
        finally:
            TIMES["main waits on a lane"] += time.perf_counter() - t
            COUNTS["main waits on a lane"] += 1

    cf.Future.result = result
    CellReader.read = timed("lane: squares ground read", CellReader.read, True)
    strip_mod.StripReader.block = timed("lane: strip block", strip_mod.StripReader.block, True)
    step_mod.Lattice.squares = timed("main: block squares (card)", step_mod.Lattice.squares)
    step_mod.Lattice.strip = timed("main: block strip (card)", step_mod.Lattice.strip)
    original = step_mod._write_block
    seen = [0]

    def write(*a, **k):
        original(*a, **k)
        seen[0] += 1

    step_mod._write_block = timed("lane: write block", write, True)
    real_tick = step_mod.Lattice.tick

    def tick(self, *a, **k):
        if max_blocks and seen[0] >= max_blocks:
            raise Enough
        return real_tick(self, *a, **k)

    step_mod.Lattice.tick = tick


def patch(max_blocks: int) -> None:
    # reading
    blocks_mod.read_square_stack = timed("read square maps (h5)", blocks_mod.read_square_stack)
    step_mod.read_square_stack = blocks_mod.read_square_stack
    blocks_mod.read_strip_stack = timed("read strip maps (h5)", blocks_mod.read_strip_stack)
    step_mod.read_strip_stack = blocks_mod.read_strip_stack
    from wadi2d.products.ground import CellReader

    CellReader.read = timed("squares ground read", CellReader.read, True)
    strip_mod.StripReader.sets = timed("strip sets", strip_mod.StripReader.sets)
    strip_mod.StripReader.block = timed("strip block ground+weights", strip_mod.StripReader.block, True)
    strip_mod.StripReader._pixels = timed("strip block: pixels and ground", strip_mod.StripReader._pixels, True)
    strip_mod.StripReader._weights = timed("strip block: weights", strip_mod.StripReader._weights, True)
    # squares, map by map
    pm = pixels_mod.PixelMaxima
    pm.__init__ = timed("squares setup (upload)", pm.__init__)
    for name in ("face_links", "corner_groups", "corner_means", "offsets_around", "around_links"):
        setattr(pixels_mod, name, timed("squares cell-level: " + name, getattr(pixels_mod, name)))
    pixels_mod.fill_offset = timed("squares pass fills", pixels_mod.fill_offset)
    pm._shape = timed("squares shape (matmuls)", pm._shape)
    try:
        from wadi2d.products import fill_kernels

        fill_kernels.may_raise = timed("squares may_raise", fill_kernels.may_raise)
    except ImportError:
        pass
    pm._join_edges = timed("squares edge passes (3 fills)", pm._join_edges)
    pixels_mod.fill_cells = timed("squares final fill", pixels_mod.fill_cells)
    pixels_mod.at_pixels = timed("squares at_pixels (shape, speed)", surface_mod.at_pixels)
    surface_mod.at_pixels = pixels_mod.at_pixels
    pm._add = timed("squares map total", pm._add)
    pm.add_listed = timed("squares add_listed total", pm.add_listed)
    pm.result = timed("squares result down", pm.result)
    # strip, map by map
    sm = strip_mod.BlockStripMaxima
    sm.__init__ = timed("strip setup (upload)", sm.__init__)
    sm._fill_offset = timed("strip fills (4 a map)", sm._fill_offset)
    sm._at_pixels = timed("strip at_pixels", sm._at_pixels)
    sm._node_means = timed("strip node means", sm._node_means)
    sm.add = timed("strip map total", sm.add)
    sm.result = timed("strip result down", sm.result)
    # writing
    original = step_mod._write_block
    seen = [0]

    def write(*a, **k):
        original(*a, **k)
        seen[0] += 1
        if max_blocks and seen[0] >= max_blocks:
            raise Enough

    step_mod._write_block = timed("write block", write, True)
    step_mod.Lattice.squares = timed("block squares total", step_mod.Lattice.squares)
    step_mod.Lattice.strip = timed("block strip total", step_mod.Lattice.strip)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--blocks", type=int, default=0)
    parser.add_argument("--backend", default="gpu")
    parser.add_argument("--light", action="store_true", help="time the block parts and the main thread's waits only")
    args = parser.parse_args()
    from wadi2d.run import prepare_grid

    run, out = args.run.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cfg = RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8"))
    cache = Path(cfg.grid.cache_dir) if cfg.grid.cache_dir else run / "cache"
    events = []
    start = time.perf_counter()
    with Progress(out / "profile_progress.jsonl", echo=False) as progress:
        tables, crs = prepare_grid(cfg, cache, progress)
        prepared = time.perf_counter() - start
        XP[0] = pixels_mod.array_module(args.backend)
        (patch_light if args.light else patch)(args.blocks)

        def emit(ev, **k):
            if k.get("kind") == "pixel_blocks":
                events.append(k)
            progress.emit(ev, **k)

        watch = step_mod.Watch(emit, lambda: False, step_mod.STAGES_RECORD)
        t = time.perf_counter()
        stopped = False
        try:
            step_mod.lattice_pixels(cfg, tables, crs, run, out, None, watch, XP[0])
        except Enough:
            stopped = True
        total = time.perf_counter() - t
    report = {
        "run": str(run), "backend": args.backend, "prepare_s": round(prepared, 1), "pixels_s": round(total, 1),
        "stopped_after_blocks": args.blocks if stopped else None, "plan": events,
        "parts_s": {k: round(v, 2) for k, v in sorted(TIMES.items(), key=lambda kv: -kv[1])},
        "calls": dict(COUNTS),
    }  # fmt: skip
    (out / "profile.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
