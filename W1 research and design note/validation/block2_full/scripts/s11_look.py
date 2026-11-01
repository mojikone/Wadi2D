"""Diagnostic plots of one run: line hydrographs against the lumped engine, max depth map around a window."""
import sys

import numpy as np
import rasterio
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from analyze import series
from common import AXES, HEADWATERS, OUT, SITES, polygons
from lumped_ref import TIMES_H, run_at

import json

name = sys.argv[1]
run = OUT / "runs" / name
cfg = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
area = cfg["storm"]["storm_area_km2"]
lump = run_at(area).outflow
fig, axs = plt.subplots(3, 4, figsize=(20, 12))
axs = axs.ravel()
for k, s in enumerate(list(SITES) + HEADWATERS):
    ax = axs[k]
    if s in SITES:
        t, q = series(run, s)
        ax.plot(t / 3600, np.abs(q) if abs(q.min()) > abs(q.max()) else q, label="line")
        t, q = series(run, f"{s} ring")
        ax.plot(t / 3600, q, label="ring")
    else:
        t, q = series(run, f"{s} ring")
        ax.plot(t / 3600, q, label="ring")
    ax.plot(TIMES_H, lump[s], "k--", label="lumped")
    ax.set_title(s)
    ax.set_xlim(0, 48)
    ax.legend()
    ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(run / "hydrographs.png", dpi=60)
with rasterio.open(run / "maps" / "max_depth.tif") as src:
    a = src.read(1, masked=True)
    t = src.transform
    ext = (src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top)
    print(src.nodata, a.min(), a.max(), np.percentile(a.compressed(), [50, 90, 99, 99.9]))
fig, ax = plt.subplots(figsize=(13, 14))
im = ax.imshow(np.ma.masked_less(a, 0.2), extent=ext, cmap="turbo", vmin=0, vmax=8)
plt.colorbar(im, ax=ax, fraction=0.03)
for n, p in polygons().items():
    for g in getattr(p, "geoms", [p]):
        x, y = g.exterior.xy
        ax.plot(x, y, "k", lw=0.4)
for n, c in AXES.items():
    c = np.array(c)
    ax.plot(c[:, 0], c[:, 1], "m", lw=1.2)
fig.tight_layout()
fig.savefig(run / "max_depth.png", dpi=70)
# deepest cells
idx = np.argsort(a.filled(0).ravel())[-12:][::-1]
for k in idx:
    j, i = np.unravel_index(k, a.shape)
    print(f"depth {a[j, i]:.2f} at {t.c + (i + .5) * t.a:.0f} {t.f + (j + .5) * t.e:.0f}")
