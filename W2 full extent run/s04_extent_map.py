"""Extent against his 200-yr layer with dry pixels counted as dry, dam peaks as magnitudes, and the framed white map."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LinearSegmentedColormap, Normalize
from PIL import Image
from rasterio.warp import Resampling, reproject

HERE = Path(__file__).resolve().parent
RUN = HERE / "runs" / "full_30m_200yr"
HIS = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Raster\Block2_Depth_200Year.tif"
out: dict = {}

for name in ("Faydh_01", "Bidah_03", "R5A", "R2A", "Z4C"):
    with (RUN / "series" / f"line_{name}.csv").open() as h:
        d = np.array([[float(v) for v in r] for r in list(csv.reader(h))[1:]])
    q = np.abs(d[:, 1])
    k = int(np.argmax(q))
    out[name] = {"peak": float(q[k]), "t_h": float(d[k, 0] / 3600), "volume_Mm3": float(np.trapezoid(q, d[:, 0]) / 1e6)}
    print(f"{name:9s} {q[k]:8.1f} m3/s at {d[k, 0] / 3600:5.2f} h, {out[name]['volume_Mm3']:6.2f} Mm3")

with rasterio.open(RUN / "maps" / "max_mean_depth.tif") as m:
    wadi = m.read(1, masked=True).filled(0.0)
    tr, crs = m.transform, m.crs
    cell = ~np.ma.getmaskarray(m.read(1, masked=True))
with rasterio.open(HIS) as h:
    a = h.read(1, masked=True).astype("float32").filled(0.0)
    a[a > 50.0] = 0.0  # the spike in his raster
    hist = h.transform
    f = 10  # 3 m to 30 m
    ny, nx = a.shape[0] // f, a.shape[1] // f
    block = a[: ny * f, : nx * f].reshape(ny, f, nx, f).mean(axis=(1, 3))
    frame_h = rasterio.Affine(hist.a * f, 0, hist.c, 0, hist.e * f, hist.f)
his = np.full(wadi.shape, np.nan, "float32")
reproject(block, his, src_transform=frame_h, src_crs=crs, dst_transform=tr, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.nearest)
frame = np.isfinite(his) & cell
km2 = abs(tr.a * tr.e) * 1e-6
print(f"his raster frame inside the model {frame.sum() * km2:,.0f} km2")
for t in (0.1, 0.3, 0.5, 1.0):
    h_w, m_w = (np.nan_to_num(his) >= t) & frame, (wadi >= t) & frame
    both, union = (h_w & m_w).sum(), (h_w | m_w).sum()
    out[f"extent_{t}"] = {"his": float(h_w.sum() * km2), "wadi": float(m_w.sum() * km2), "both": float(both * km2), "F": float(both / union)}
    print(f"mean depth >= {t}: his {h_w.sum() * km2:6.0f}, Wadi2D {m_w.sum() * km2:6.0f}, both {both * km2:6.0f} km2, F {both / union:.3f}")
gap = (wadi - np.nan_to_num(his))[(np.nan_to_num(his) >= 0.5) & (wadi >= 0.5) & frame]
print(f"both >= 0.5 m: Wadi2D minus his, median {np.median(gap):+.2f} m, p5 {np.percentile(gap, 5):+.2f}, p95 {np.percentile(gap, 95):+.2f}")
out["depth_gap_median_m"] = float(np.median(gap))
(HERE / "s04_extent.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

png = HERE / "terrain" / "map_white_full.png"
if png.exists():
    img = Image.open(png).convert("RGB")
    x0, y0, x1, y1 = json.loads((HERE / "terrain" / "map_full_extent.json").read_text())
    w, h = img.size
    fig = plt.figure(figsize=(10, 11.6), dpi=200, facecolor="white")
    ax = fig.add_axes([0.02, 0.075, 0.96, 0.85])
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation="antialiased")
    ax.set_axis_off()
    fig.text(0.02, 0.970, "Wadi2D rain-on-grid, full project extent: maximum depth", fontsize=15, fontweight="bold", va="center")
    fig.text(0.02, 0.946, "Block 2 200-yr storm over the whole boundary, 251 mm at storm area 300 km2. 30 m grid, NSA 5 m with Copernicus.", fontsize=10, va="center")
    stops = [(0.0, "#f7fbff"), (0.5 / 3, "#a2cae5"), (1.0 / 3, "#73b2d8"), (1.5 / 3, "#2979b9"), (1.0, "#08306b")]
    cax = fig.add_axes([0.02, 0.043, 0.42, 0.014])
    bar = fig.colorbar(plt.cm.ScalarMappable(Normalize(0, 3), LinearSegmentedColormap.from_list("his", stops)), cax=cax,
                       orientation="horizontal", ticks=[0, 0.5, 1, 1.5, 3])  # fmt: skip
    bar.ax.set_xticklabels(["0", "0.5", "1", "1.5", "3+ m"], fontsize=9)
    bar.ax.tick_params(length=2)
    fig.text(0.47, 0.050, "Cell-mean depth, 70 % opacity", fontsize=9, va="center")
    jpg = HERE / "Wadi2D_full_extent_depth_200yr_block2_storm.jpg"
    fig.savefig(jpg, dpi=200, facecolor="white", pil_kwargs={"quality": 92})
    print(jpg, jpg.stat().st_size)
