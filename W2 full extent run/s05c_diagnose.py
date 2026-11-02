"""Why 707 m of depth and 25 m/s? Terrain pits under the deep cells, and how H5 and H6 split between real flow and film."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds

HERE = Path(__file__).resolve().parent
MAPS = HERE / "runs" / "full_30m_200yr" / "maps"


def read(name):
    with rasterio.open(MAPS / f"{name}.tif") as s:
        return s.read(1, masked=True).filled(0.0).astype("float32"), s.transform


d, tr = read("max_depth")
mean, _ = read("max_mean_depth")
v, _ = read("max_speed")
dv, _ = read("hazard")
lvl, _ = read("max_level")
with rasterio.open(HERE / "terrain" / "hazard_class.tif") as s:
    cls = s.read(1)
km2 = abs(tr.a * tr.e) * 1e-6
for t in (5, 10, 20, 50, 100, 300):
    print(f"max_depth > {t} m: {(d > t).sum()} cells; of them mean depth < 1 m: {((d > t) & (mean < 1)).sum()}")
wet = cls > 0
print("wet cells", wet.sum(), "km2", wet.sum() * km2)
for lo, hi in ((0, 1), (1, 2), (2, 4), (4, 8), (8, 15), (15, 25.1)):
    m = wet & (v > lo) & (v <= hi)
    print(f"speed {lo}-{hi}: {m.sum() * km2:8.1f} km2, median mean depth {np.median(mean[m]) if m.any() else 0:.2f} m, median low-point depth {np.median(d[m]) if m.any() else 0:.2f}")
ratio = np.divide(d, mean, out=np.zeros_like(d), where=mean > 0)
for name, m in (("H5", cls == 5), ("H6", cls == 6)):
    print(f"{name}: {m.sum() * km2:.0f} km2; mean depth < 0.1 m {(m & (mean < 0.1)).sum() * km2:.0f}; < 0.3 m {(m & (mean < 0.3)).sum() * km2:.0f}; low-point depth over 5 x mean {(m & (ratio > 5)).sum() * km2:.0f}; level above 300 m {(m & (lvl > 300)).sum() * km2:.0f}")
idx = np.argsort(d, axis=None)[-8:][::-1]
r, c = np.unravel_index(idx, d.shape)
with rasterio.open(HERE / "terrain" / "NSA5_COP30_blend.tif") as z:
    for a, b in zip(r, c):
        x, y = rasterio.transform.xy(tr, a, b)
        w = from_bounds(x - 15, y - 15, x + 15, y + 15, z.transform).round_offsets().round_lengths()
        p = z.read(1, window=w)
        print(f"({x:.0f}, {y:.0f}) depth {d[a, b]:.1f} mean {mean[a, b]:.2f} level {lvl[a, b]:.1f}; pixels min {p.min():.1f} median {np.median(p):.1f} max {p.max():.1f}")
