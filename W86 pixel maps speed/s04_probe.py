"""What one saved map costs at the pixel, per pixel, on the card and on the host: the squares and the strip apart.

    python s04_probe.py RUN [--backend gpu|cpu] [--maps N]

On a finished run (the Bidah window, say): the kept squares as one block and the strip as one block, ``N`` saved
maps from the middle of the run through each, timed, with the most the device's pool held per pixel. The figures
size the blocks (``SQUARE_PIXEL_BYTES``, ``WORK_PIXEL_BYTES``, ``STRIP_PIXEL_BYTES``) and give Block 2's time by
proportion before the card is free for the whole run.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.products.blocks import read_square_stack, read_strip_stack
from wadi2d.products.frames import frame_names, run_maxima, strip_run_maxima
from wadi2d.products.ground import CellPixels, CellReader, face_sills
from wadi2d.products.pixels import PixelMaxima, array_module
from wadi2d.products.strip_pixels import BlockStripMaxima, StripReader
from wadi2d.run import prepare_grid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--backend", default="gpu")
    parser.add_argument("--maps", type=int, default=20)
    args = parser.parse_args()
    cfg = RunConfig.model_validate_json((args.run / "config.resolved.json").read_text(encoding="utf-8"))
    tables, _crs = prepare_grid(cfg, Path(cfg.grid.cache_dir))
    xp = array_module(args.backend)
    rule = cfg.outputs.pixels
    results = args.run / "results.h5"
    names = frame_names(results)
    middle = names[len(names) // 2 - args.maps // 2 :][: args.maps]
    peak = run_maxima(results)
    keep = peak["mean_depth"] > rule.cell_depth
    report: dict = {"backend": args.backend, "maps": len(middle)}

    def pool_peak(work) -> tuple[float, int]:
        """Seconds of ``work(step)`` and the most the pool held while it ran; ``step`` is called after each map."""
        most = [0]
        if xp is not np:
            pool = xp.get_default_memory_pool()
            pool.free_all_blocks()

            def step() -> None:
                xp.cuda.Stream.null.synchronize()
                most[0] = max(most[0], pool.total_bytes())
        else:

            def step() -> None:
                return None

        start = time.perf_counter()
        work(step)
        if xp is not np:
            xp.cuda.Stream.null.synchronize()
        return time.perf_counter() - start, most[0]

    with CellReader(cfg, tables, keep) as reader:
        ground = reader.read(0, reader.rows.size)
        cells = CellPixels(reader.rows, reader.cols, reader.k, reader.pixel, reader.datum, ground)
        stack = read_square_stack(results, middle, reader.rows, reader.cols, 0, reader.rows.size, lambda _a, _b: None)
        zmin = (tables.zmin - reader.datum).astype(np.float32)
        maxima = PixelMaxima(xp, cells, zmin, *face_sills(tables, reader.datum), keep, rule)
        maxima.tidy = False
        at = np.arange(reader.rows.size)

        def squares(step) -> None:
            for index in range(stack.maps):
                maxima.add_listed(*stack.of(index, at))
                step()

        seconds, held = pool_peak(squares)
        pixels = ground.size
        report["squares"] = {
            "pixels": int(pixels), "resident": bool(maxima.resident), "s_per_map": round(seconds / stack.maps, 4),
            "ns_per_pixel_map": round(1e9 * seconds / stack.maps / pixels, 3), "pool_bytes_per_pixel": round(held / pixels, 1),
        }  # fmt: skip
        datum = reader.datum
        del ground, cells
    if getattr(tables, "strip", None) is not None and strip_run_maxima(results) is not None:
        strips = StripReader(cfg, tables, tables.strip, datum)
        try:
            start = time.perf_counter()
            every = np.ones(strips.n, bool)
            block = strips.block(every, every)
            read_s = time.perf_counter() - start
        finally:
            strips.close()
        strip_stack = read_strip_stack(results, middle, block.ids)
        strip_maxima = BlockStripMaxima(xp, block, rule)
        at = strip_stack.at(block.ids)

        def strip(step) -> None:
            for index in range(strip_stack.maps):
                strip_maxima.add(*strip_stack.of(index, at))
                step()

        seconds, held = pool_peak(strip)
        report["strip"] = {
            "cells": int(block.ids.size), "pixels": block.count, "width": int(block.weights.shape[1]),
            "ground_and_weights_s": round(read_s, 2), "s_per_map": round(seconds / strip_stack.maps, 4),
            "ns_per_pixel_map": round(1e9 * seconds / strip_stack.maps / block.count, 3),
            "pool_bytes_per_pixel": round(held / block.count, 1),
        }  # fmt: skip
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
