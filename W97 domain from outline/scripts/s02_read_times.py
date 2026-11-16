"""W97: the analysis raster of the Block 2 check read both ways, timed, on the same window.

    python s02_read_times.py [pixel_m]

The window of ``complete_outline``'s first pass over ``runs/rough_outline.geojson`` (s01): through GDAL
(``read_coarse``, the basin generator's read before W92) and from the W79 job's chunk store (``read_coarse_from``,
W92). Writes ``read_times_<pixel>m.json``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from shapely.geometry import shape

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parent
sys.path.insert(0, str(REPO))
from wadi2d.config.schema import DomainSettings  # noqa: E402
from wadi2d.demstore import cache_folder, open_bed  # noqa: E402
from wadi2d.demstore.coarse import can_average, read_coarse_from  # noqa: E402
from wadi2d.domain.outline import _window  # noqa: E402
from wadi2d.mesh.streams import read_coarse  # noqa: E402
from wadi2d.run import load_job  # noqa: E402

JOB = REPO / "W79 Block 2 four ways" / "jobs" / "rerun2_run3_hybrid_aligned.json"


def main() -> None:
    pixel = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    cfg = load_job(JOB)
    rough = shape(
        json.loads((HERE / "runs" / "rough_outline_sea.geojson").read_text("utf-8"))["features"][0][
            "geometry"
        ]
    )
    m = DomainSettings().margin_m
    b = rough.bounds
    x0, y0, ny, nx, _edge = _window(cfg.terrain.dem, (b[0] - m, b[1] - m, b[2] + m, b[3] + m), pixel)
    out = {"pixel_m": pixel, "rows": ny, "columns": nx}
    with open_bed(cfg, cache_folder(cfg), stride=1) as bed:
        out["store_used"] = bool(can_average(bed, x0, y0, ny, nx, pixel))
        t = time.perf_counter()
        stored = read_coarse_from(bed, cfg.terrain.dem, x0, y0, ny, nx, pixel, 1)
        out["store_s"] = round(time.perf_counter() - t, 1)
    t = time.perf_counter()
    gdal = read_coarse(cfg.terrain.dem, x0, y0, ny, nx, pixel, 1)
    out["gdal_s"] = round(time.perf_counter() - t, 1)
    same = (stored == gdal) | (np.isnan(stored) & np.isnan(gdal))
    out["pixels_differing"] = int((~same).sum())
    (HERE / f"read_times_{pixel:g}m.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
