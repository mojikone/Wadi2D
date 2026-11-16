"""The water a map draws against the water the run holds, at one saved moment, over the whole run.

    python s05_volume.py RUN CACHE OUT --map NAME [--rules a,b] [--pixel M] [--backend gpu]

The product step is run on the one saved map NAME alone (the run's own peaks, which are not one moment, are left
out), with the depth floor at a micrometre so every drop is drawn, and the volume of the drawn depth (pixel depth
times pixel area, summed) is set against the run's own volume at that moment (each cell's mean depth times its area,
squares and aligned cells). Writes ``OUT/volume_<rule>.json`` and the raster beside it.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import h5py
import numpy as np
import rasterio

from wadi2d.config.schema import RunConfig
from wadi2d.products import step as step_module
from wadi2d.products.frames import run_maxima, strip_run_maxima
from wadi2d.products.step import STAGES_RECORD, Watch, make_products
from wadi2d.run import prepare_grid

FLOOR = 1e-6


def run_volume(results: Path, name: str, tables) -> dict:
    """The run's own water at map ``name``: squares by their cell area, aligned cells by theirs."""
    with h5py.File(results, "r") as f:
        group = f["maps"][name]
        mean_depth = group["mean_depth"][:].astype(np.float64)
        mask = f["mask"][:]
        strip = group["strip_mean_depth"][:].astype(np.float64).ravel() if "strip_mean_depth" in group else None
    dx = tables.grid.dx
    squares = float((mean_depth * mask).sum() * dx * dx)
    out = {"squares_m3": squares, "strip_m3": 0.0}
    if strip is not None and getattr(tables, "strip", None) is not None:
        area, _cx, _cy = tables.strip.strip.geometry.areas_centroids()
        n = strip.size
        out["strip_m3"] = float((strip * np.abs(area[:n])).sum())
    out["total_m3"] = out["squares_m3"] + out["strip_m3"]
    return out


def map_volume(raster: Path) -> float:
    with rasterio.open(raster) as src:
        pixel = src.transform.a
        total = 0.0
        for _ij, window in src.block_windows(1):
            a = src.read(1, window=window).astype(np.float64)
            total += float(a[a > 0.0].sum())
    return total * pixel * pixel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--map", required=True)
    parser.add_argument("--rules", default="cell_fill,corners,continuous")
    parser.add_argument("--pixel", type=float, default=2.0)
    parser.add_argument("--backend", default="gpu")
    args = parser.parse_args()
    cfg = RunConfig.model_validate_json((args.run / "config.resolved.json").read_text(encoding="utf-8"))
    cfg = cfg.model_copy(update={"grid": cfg.grid.model_copy(update={"cache_dir": str(args.cache.resolve())})})
    tables, crs = prepare_grid(cfg, args.cache)
    results = args.run / "results.h5"
    held = run_volume(results, args.map, tables)
    peak, strip_peak = run_maxima(results), strip_run_maxima(results)

    def one_map(_results):
        return [args.map]

    def peaks_for_keep(_results):  # the cells that take pixels as the step picks them; no peak map laid over them
        return {**{k: np.zeros_like(v) for k, v in peak.items()}, "mean_depth": peak["mean_depth"]}

    def strip_peaks(_results):
        return None if strip_peak is None else {k: np.zeros_like(v) for k, v in strip_peak.items()}

    step_module.frame_names = one_map
    step_module.run_maxima = peaks_for_keep
    step_module.strip_run_maxima = strip_peaks
    quiet = Watch(lambda *_a, **_k: None, lambda: False, STAGES_RECORD)
    for rule in args.rules.split(","):
        update = {"surface": rule, "pixel_m": args.pixel, "depth_floor": FLOOR, "max_error_m": 0.0, "overviews": False}
        if rule == "cell_fill":
            update["cell_depth"] = 0.0  # every wet cell, so the rule's own volume is the run's to the fill's tolerance
        pixels = cfg.outputs.pixels.model_copy(update=update)
        job = cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"pixels": pixels})})
        folder = args.out / f"volume_{rule}"
        began = time.time()
        make_products(job, tables, crs, args.run, quiet, args.backend, None, None, folder)
        drawn = map_volume(folder / step_module.DEPTH_FILE)
        report = {
            "map": args.map, "rule": rule, "pixel_m": args.pixel, "seconds": round(time.time() - began, 1),
            "run_m3": held, "map_m3": drawn, "map_over_run": drawn / held["total_m3"] if held["total_m3"] else None,
        }  # fmt: skip
        (args.out / f"volume_{rule}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
