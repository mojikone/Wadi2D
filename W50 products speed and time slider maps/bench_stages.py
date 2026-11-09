"""Time one product stage at a time on Block 2's real arrays (W50), so a change is measured without a 27-minute remake.

    .venv\Scripts\python "W50 products speed and time slider maps\bench_stages.py" drawing|polygons [tag]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.io.geotiff import raster_profile  # noqa: E402

RUN = HERE / "profile" / "block2_b20"
OUT = HERE / "bench"


class Watch:
    def tick(self, *a, **k):
        pass

    def emit(self, *a, **k):
        pass


def load():
    cfg = RunConfig.model_validate_json((RUN / "config.resolved.json").read_text(encoding="utf-8"))
    with rasterio.open(RUN / "pixels" / "pixel_depth.tif") as s:
        depth = s.read(1)
        depth = np.where(depth == s.nodata, 0.0, depth).astype(np.float32)
        t, crs = s.transform, s.crs
    return cfg, depth, t, crs


if __name__ == "__main__":
    what, tag = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "now")
    OUT.mkdir(exist_ok=True)
    cfg, depth, t, crs = load()
    t0 = time.perf_counter()
    if what == "drawing":
        from wadi2d.products.smooth import depth_drawing

        path = depth_drawing(cfg, depth, raster_profile(depth.shape, t.a, t.c, t.f, crs), OUT / f"drawing_{tag}.tif", Watch())
    spent = time.perf_counter() - t0
    print(f"{what} {tag}: {spent:.1f} s", flush=True)
    (OUT / f"{what}_{tag}.json").write_text(json.dumps({"seconds": spent}), encoding="utf-8")
