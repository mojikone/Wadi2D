"""The four rasters of record of a remake against the run before, pixel for pixel (W50, 2026-11-13).

    python compare_rasters.py RUN_TAG [REFERENCE_PIXELS_DIR]

The reference is the products of 2026-11-09 (`profile/block2_b20/pixels` in the main checkout), made by the engine
before any W50 change. Grids, CRS and nodata must match; then every pixel, read in bands of rows on every core. Writes
`remake/compare_<tag>.json` and prints the largest difference of each raster and how many pixels differ.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

HERE = Path(__file__).resolve().parent / "remake"
REFERENCE = Path(r"D:\Mojtaba\Renardet\Wadi2D\W50 products speed and time slider maps\profile\block2_b20\pixels")
NAMES = ("pixel_depth.tif", "pixel_speed.tif", "pixel_dv.tif", "pixel_hazard.tif")
ROWS = 4096


def compare(a_path: Path, b_path: Path) -> dict:
    with rasterio.Env(GDAL_NUM_THREADS="ALL_CPUS"), rasterio.open(a_path) as a, rasterio.open(b_path) as b:
        same_grid = a.shape == b.shape and a.transform == b.transform and a.crs == b.crs and a.nodata == b.nodata
        out = {"shape": list(a.shape), "same_grid": bool(same_grid), "dtype": a.dtypes[0], "nodata": a.nodata}
        if not same_grid:
            return out
        worst, differ, wet = 0.0, 0, 0
        for r0 in range(0, a.height, ROWS):
            win = Window(0, r0, a.width, min(ROWS, a.height - r0))
            x, y = a.read(1, window=win), b.read(1, window=win)
            bad = x != y
            differ += int(bad.sum())
            wet += int((x != a.nodata).sum())
            if bad.any():
                worst = max(worst, float(np.abs(x[bad].astype(np.float64) - y[bad].astype(np.float64)).max()))
        out.update({"pixels_differing": differ, "max_abs_difference": worst, "pixels_with_data": wet})
        return out


def main() -> int:
    tag = sys.argv[1]
    reference = Path(sys.argv[2]) if len(sys.argv) > 2 else REFERENCE
    mine = HERE / "runs" / tag / "pixels"
    report = {"run": str(mine), "reference": str(reference), "rasters": {}}
    for name in NAMES:
        found = compare(mine / name, reference / name)
        found["bytes"] = (mine / name).stat().st_size
        found["reference_bytes"] = (reference / name).stat().st_size
        report["rasters"][name] = found
        print(name, found, flush=True)
    (HERE / f"compare_{tag}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    same = all(r["same_grid"] and r["pixels_differing"] == 0 for r in report["rasters"].values())
    print("IDENTICAL" if same else "DIFFERENT")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
