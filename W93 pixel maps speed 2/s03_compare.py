"""Two runs' rasters of record compared pixel for pixel, a window at a time.

    python s03_compare.py RUN_A RUN_B

For each of the four rasters: the same size and place, how many pixels differ, the largest difference, and how many
pixels are wet in one and dry in the other. Exit code 0 when all four are identical, 1 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

FILES = ("pixel_hazard.tif", "pixel_depth.tif", "pixel_speed.tif", "pixel_dv.tif")
STEP = 4096


def compare(a: Path, b: Path) -> dict:
    with rasterio.open(a) as fa, rasterio.open(b) as fb:
        if fa.shape != fb.shape or fa.transform != fb.transform:
            return {"same_grid": False, "a": [fa.shape, list(fa.transform)[:6]], "b": [fb.shape, list(fb.transform)[:6]]}
        differ, largest, wet_dry, wet = 0, 0.0, 0, 0
        for row in range(0, fa.height, STEP):
            for col in range(0, fa.width, STEP):
                window = Window(col, row, min(STEP, fa.width - col), min(STEP, fa.height - row))
                va, vb = fa.read(1, window=window), fb.read(1, window=window)
                off = va != vb
                wet += int((va != fa.nodata).sum())
                if off.any():
                    differ += int(off.sum())
                    dry = (va == fa.nodata) != (vb == fb.nodata)
                    wet_dry += int(dry.sum())
                    both = off & ~dry
                    if both.any():
                        largest = max(largest, float(np.abs(va[both].astype(np.float64) - vb[both]).max()))
        return {"same_grid": True, "shape": list(fa.shape), "wet_pixels": wet, "differ": differ, "largest": largest, "wet_in_one_only": wet_dry}


def main() -> int:
    a, b = (Path(p) / "pixels" for p in sys.argv[1:3])
    report = {name: compare(a / name, b / name) for name in FILES}
    stats = [json.loads((p / "pixels.json").read_text(encoding="utf-8")) for p in (a, b)]
    report["pixels.json equal"] = stats[0] == stats[1]
    print(json.dumps(report, indent=1))
    same = all(r.get("same_grid") and r["differ"] == 0 for name, r in report.items() if name in FILES)
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
