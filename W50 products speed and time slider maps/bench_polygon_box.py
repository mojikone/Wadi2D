"""The polygons of real Block 2 blocks with the class masks boxed (W50, 2026-11-13) against the code before it.

    python "W50 products speed and time slider maps\bench_polygon_box.py" [BLOCKS] [RUN_TAG]

The class raster is a remake's (`remake/runs/<tag>`, default `new2_off`); the code before is `wadi2d/products/smooth.py`
of commit 6d56ad7, read from git. Times each block both ways on one thread and compares every band: identical to the
byte, or the largest Hausdorff distance and area change. Prints a line per block and a summary.
"""

import subprocess
import sys
import time
import types
from pathlib import Path
import numpy as np, rasterio, shapely
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
RUN = HERE / "remake" / "runs" / (sys.argv[2] if len(sys.argv) > 2 else "new2_off")
BEFORE = "6d56ad7"
from wadi2d.config.schema import RunConfig
from wadi2d.products import smooth as new
from wadi2d.io.geotiff import raster_profile
old = types.ModuleType("smooth_before")
code = subprocess.run(["git", "show", f"{BEFORE}:wadi2d/products/smooth.py"], cwd=HERE, capture_output=True, check=True).stdout
exec(compile(code, "smooth_before.py", "exec"), old.__dict__)  # noqa: S102 - this repository's own code
cfg = RunConfig.model_validate_json((RUN / "config.resolved.json").read_text(encoding="utf-8"))
with rasterio.Env(GDAL_NUM_THREADS="ALL_CPUS"), rasterio.open(RUN / "pixels" / "pixel_hazard.tif") as s:
    classes = s.read(1); t = s.transform; crs = s.crs
profile = raster_profile(classes.shape, t.a, t.c, t.f, crs)
class W:
    def check(self): pass
smooth, rule = cfg.outputs.smooth, cfg.outputs.pixels
levels = len(rule.hazard_limits) + 1
smallest = int(np.ceil(smooth.speckle_m2 / t.a**2))
reach = int(np.ceil(new.GAUSS_REACH * smooth.sigma_px)) + max(int(np.ceil(np.sqrt(smallest))), 2) + 2
blocks = [(*r, *c) for r in new.block_ranges(classes.shape[0], smooth.block_px) for c in new.block_ranges(classes.shape[1], smooth.block_px)]
wet = [b for b in blocks if (new.window(classes, b[0], b[1] + 1, b[2], b[3] + 1, 0) > 0).any()]
n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
pick = np.linspace(0, len(wet) - 1, n).astype(int)
t_old = t_new = 0.0
same = close = 0; worst_area = 0.0; worst_h = 0.0
for i in pick:
    a0 = time.perf_counter(); ro = old._block_bands(classes, wet[i], int(i), levels, reach, smallest, profile, smooth, W()); a1 = time.perf_counter()
    rn = new._block_bands(classes, wet[i], int(i), levels, reach, smallest, profile, smooth, W()); a2 = time.perf_counter()
    t_old += a1 - a0; t_new += a2 - a1
    assert ro[2:] == rn[2:], (ro[2:], rn[2:])
    print("  shown km2 diff", np.abs(ro[1] - rn[1]).max(), "exact" if np.array_equal(ro[1], rn[1]) else "")
    assert [r[:2] for r in ro[0]] == [r[:2] for r in rn[0]]
    for (k, b, g1), (_k, _b, g2) in zip(ro[0], rn[0]):
        if shapely.equals_exact(g1, g2, 0.0):
            same += 1
        else:
            close += 1
            worst_area = max(worst_area, abs(g1.area - g2.area))
            worst_h = max(worst_h, shapely.hausdorff_distance(g1, g2))
    print(i, wet[i], f"old {a1-a0:.1f} s new {a2-a1:.1f} s", flush=True)
print(f"blocks {len(pick)}: old {t_old:.1f} s, new {t_new:.1f} s; bands identical {same}, differing {close}, worst area {worst_area:.3e} m2, worst hausdorff {worst_h:.3e} m")
