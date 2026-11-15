"""What the first build's minutes are, stage by stage, as ``prepare_grid`` does them, each timed alone.

    python s02_stage_split.py <label of an s01 run>

On the job of ``runs/<label>`` with a fresh cache of its own (``runs/<label>.stages/cache``, the DEM store hard-linked
in, so the domain mask is read cold as on a new job): the left-out catchments, the domain mask, the strip's mesh, the
Manning grid, the tables of the tiles, their save, the strip's tables and the strip's save. Writes
``runs/<label>.stages.json``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "runs"
STORE = "dem_0bedda043cf08b5074aeaac6"


def main() -> None:
    import numpy as np

    from wadi2d.demstore import open_bed
    from wadi2d.grid.tiles import TileGrid
    from wadi2d.io.cache import save_strip, save_tables
    from wadi2d.run import _domain_polygon, _wkt, grid_window, kept_domain_mask, left_out_of, load_job, manning_grid
    from wadi2d.strips.build import mask_for_strips, strip_squares, strip_tables
    from wadi2d.tables import build_tables
    from wadi2d.terrain import Ground, apply_objects
    from wadi2d.terrain.sections import with_tables

    label = sys.argv[1]
    cfg = with_tables(load_job(RUNS / f"{label}.job.json"))
    scratch = RUNS / f"{label}.stages"
    cache = scratch / "cache"
    if scratch.exists():
        shutil.rmtree(scratch)
    (cache / STORE).mkdir(parents=True)
    for f in (RUNS / "cache" / STORE).iterdir():
        if f.name == "source.json":
            shutil.copy2(f, cache / STORE / f.name)
        else:
            os.link(f, cache / STORE / f.name)
    times: dict[str, float] = {}

    def timed(name, call):
        t0 = time.perf_counter()
        out = call()
        times[name] = round(time.perf_counter() - t0, 1)
        print(name, times[name], flush=True)
        return out

    with open_bed(cfg, cache) as bed:
        crs = _wkt(bed)
        window = grid_window(cfg, bed)
        left = timed("left_out", lambda: left_out_of(cfg, crs))
        mask = timed("domain_mask", lambda: kept_domain_mask(cfg, bed, window, cache))
        if left is not None and left.names:
            mask = mask & ~(left.cells(window.x0, window.y0, cfg.grid.dx, mask.shape) & mask)
        polygon = _domain_polygon(cfg.grid.domain, crs)
        if left is not None and left.names:
            polygon = polygon.difference(left.area.buffer(cfg.grid.dx))
        mask, strip = timed("strip_mesh", lambda: mask_for_strips(cfg, mask, window.x0, window.y0, polygon))
        grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
        bed.bind(grid.x0, grid.y0)
        edits = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain, Ground(bed, grid.x0, grid.y0))
        n = timed("manning", lambda: manning_grid(cfg, grid, crs))
        tables = timed("tables", lambda: build_tables(grid, bed, cfg.tables, n, edits.crest, edits.edit, edits.lining))
        timed("save_tables", lambda: save_tables(scratch / "grid.h5", tables, "scratch"))
        jj, ii = np.nonzero(tables.grid.mask)
        sj, si = strip_squares(strip.geometry, tables.grid)
        cells = (np.concatenate((jj, sj)), np.concatenate((ii, si)))
        made = timed("strip_tables", lambda: strip_tables(cfg, tables, bed, strip, manning_grid(cfg, tables.grid, crs, cells)))
        timed("save_strip", lambda: save_strip(scratch / "strip.pkl", "scratch", mask, made))
    shutil.rmtree(scratch, ignore_errors=True)  # the store's chunks may still be mapped
    (RUNS / f"{label}.stages.json").write_text(json.dumps(times, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
