"""Where two remakes of one run differ: on the strip's pixels or on the squares'.

    python s05_split.py RUN_A RUN_B

For small runs (the rasters are read whole). The strip's pixels are found as the product step finds them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio

from wadi2d.config.schema import RunConfig
from wadi2d.products.frames import run_maxima
from wadi2d.products.strip_pixels import StripReader
from wadi2d.run import prepare_grid

FILES = ("pixel_hazard.tif", "pixel_depth.tif", "pixel_speed.tif", "pixel_dv.tif")


def main() -> None:
    a, b = (Path(p) for p in sys.argv[1:3])
    cfg = RunConfig.model_validate_json((a / "config.resolved.json").read_text(encoding="utf-8"))
    tables, _crs = prepare_grid(cfg, Path(cfg.grid.cache_dir))
    keep = run_maxima(a / "results.h5")["mean_depth"] > cfg.outputs.pixels.cell_depth
    datum = float(tables.zmin[keep].min())
    strips = StripReader(cfg, tables, tables.strip, datum)
    try:
        every = np.ones(strips.n, bool)
        block = strips.block(every, every)
    finally:
        strips.close()
    report = {}
    for name in FILES:
        with rasterio.open(a / "pixels" / name) as fa, rasterio.open(b / "pixels" / name) as fb:
            va, vb = fa.read(1).astype(np.float64), fb.read(1).astype(np.float64)
            top = round((tables.grid.y0 - fa.transform.f) / fa.transform.a)
            left = round((fa.transform.c - tables.grid.x0) / fa.transform.a)
        on_strip = np.zeros(va.shape, bool)
        on_strip[block.rows - top, block.cols - left] = True
        off = va != vb
        report[name] = {
            where: {"pixels": int(mask.sum()), "differ": int((off & mask).sum()), "largest": float(np.abs(va - vb)[off & mask].max(initial=0.0))}
            for where, mask in (("strip", on_strip), ("squares", ~on_strip))
        }  # fmt: skip
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
