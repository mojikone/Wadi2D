"""Which summation GDAL's average uses: variants of a block mean against read_coarse on one plain piece.

    python e02_gdal_order.py <job.json>
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s01_mesh import cache_folder

from wadi2d.breaklines.window import pixel_factor
from wadi2d.demstore import open_bed
from wadi2d.mesh.streams import read_coarse
from wadi2d.run import grid_window, load_job

cfg = load_job(Path(sys.argv[1]))
dx = cfg.grid.dx
factor = pixel_factor(dx, cfg.mesh.analysis_pixel)
with open_bed(cfg, cache_folder()) as bed:
    w = grid_window(cfg, bed)
    j0, i0, n = 1170, 1221, 50
    x0, y0 = w.x0 + i0 * dx, w.y0 - j0 * dx
    a = read_coarse(cfg.terrain.dem, x0, y0, n, n, dx, factor).astype(np.float32)
    t = bed.src.transform
    col = round((x0 - t.c) / t.a)
    row = round((t.f - y0) / -t.e)
    k = 10
    z, m = bed._window(row, col, n * factor * k, n * factor * k)
    z = z.copy().astype(np.float32)
N = n * factor
rows = z.reshape(N, k, N, k).transpose(0, 2, 1, 3)  # (N, N, k rows, k cols)
d = rows.astype(np.float64)
variants = {}
s = np.zeros((N, N))
for r in range(k):
    for c in range(k):
        s = s + d[..., r, c]
variants["double seq rowmajor"] = s / (k * k)
s = np.zeros((N, N))
for c in range(k):
    for r in range(k):
        s = s + d[..., r, c]
variants["double seq colmajor"] = s / (k * k)
s = np.zeros((N, N), np.float32)
for r in range(k):
    for c in range(k):
        s = (s + rows[..., r, c]).astype(np.float32)
variants["float seq rowmajor"] = s / np.float32(k * k)
s = np.zeros((N, N))
for r in range(k):
    rs = np.zeros((N, N))
    for c in range(k):
        rs = rs + d[..., r, c]
    s = s + rs
variants["double row sums then total"] = s / (k * k)
s = np.zeros((N, N), np.float32)
for r in range(k):
    rs = np.zeros((N, N), np.float32)
    for c in range(k):
        rs = (rs + rows[..., r, c]).astype(np.float32)
    s = (s + rs).astype(np.float32)
variants["float row sums then total"] = s / np.float32(k * k)
s = np.zeros((N, N), np.float32)
for r in range(k):
    rs = np.zeros((N, N), np.float64)
    for c in range(k):
        rs = rs + d[..., r, c]
    s = (s + rs.astype(np.float32)).astype(np.float32)
variants["double rows, float total"] = s / np.float32(k * k)
for lanes in (2, 4, 8):
    s = np.zeros((N, N, lanes))
    for r in range(k):
        for c in range(k):
            s[..., c % lanes] += d[..., r, c]
    acc = s[..., 0].copy()
    for q in range(1, lanes):
        acc = acc + s[..., q]
    variants[f"double {lanes} lanes"] = acc / (k * k)
    s = np.zeros((N, N, lanes), np.float32)
    for r in range(k):
        for c in range(k):
            s[..., c % lanes] = (s[..., c % lanes] + rows[..., r, c]).astype(np.float32)
    acc = s[..., 0].copy()
    for q in range(1, lanes):
        acc = (acc + s[..., q]).astype(np.float32)
    variants[f"float {lanes} lanes"] = acc / np.float32(k * k)
    s = np.zeros((N, N, lanes), np.float32)
    for r in range(k):
        for c in range(k):
            s[..., (r * k + c) % lanes] = (s[..., (r * k + c) % lanes] + rows[..., r, c]).astype(np.float32)
    acc = s[..., 0].copy()
    for q in range(1, lanes):
        acc = (acc + s[..., q]).astype(np.float32)
    variants[f"float {lanes} lanes flat"] = acc / np.float32(k * k)
variants["double rowmajor x (1/n)"] = variants["double seq rowmajor"] * (k * k) * (1.0 / (k * k))
for name, v in variants.items():
    v32 = np.asarray(v).astype(np.float32)
    print(f"{name:32s} differing {int((v32 != a).sum())} of {a.size}")

# the same window without the boundless VRT
import rasterio  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.windows import Window as RWindow  # noqa: E402

with rasterio.open(cfg.terrain.dem) as src:
    plain = src.read(1, window=RWindow(col, row, N * k, N * k), out_shape=(N, N), masked=True, resampling=Resampling.average).filled(np.nan)
    nomask = src.read(1, window=RWindow(col, row, N * k, N * k), out_shape=(N, N), resampling=Resampling.average)
mine = variants["double seq rowmajor"].astype(np.float32)
print("plain/boundless", int((plain != a).sum()), "plain/mine", int((plain != mine).sum()), "unmasked/boundless", int((nomask != a).sum()), "unmasked/mine", int((nomask != mine).sum()))
total = np.zeros((N, N))
for r in range(k):
    for c in range(k):
        total = total + d[..., r, c]
row_means = np.zeros((N, N))
for r in range(k):
    rs = np.zeros((N, N))
    for c in range(k):
        rs = rs + d[..., r, c]
    row_means = row_means + rs / k
col_means = np.zeros((N, N))
for c in range(k):
    cs = np.zeros((N, N))
    for r in range(k):
        cs = cs + d[..., r, c]
    col_means = col_means + cs / k
welford = np.zeros((N, N))
q = 0
for r in range(k):
    for c in range(k):
        q += 1
        welford = welford + (d[..., r, c] - welford) / q
row_scaled = np.zeros((N, N))
for r in range(k):
    for c in range(k):
        row_scaled = row_scaled + d[..., r, c] * (1.0 / (k * k))
hmean = np.zeros((N, N, k))
for r in range(k):
    for c in range(k):
        hmean[..., r] += d[..., r, c]
hmean = hmean / k
vm = np.zeros((N, N))
for r in range(k):
    vm = vm + hmean[..., r]
vm32 = np.zeros((N, N))
h32 = hmean.astype(np.float32).astype(np.float64)
for r in range(k):
    vm32 = vm32 + h32[..., r]
inv = 1.0 / (k * k)
gt = np.zeros((N, N))
for r in range(k):
    line = d[..., r, 0] * inv * 1.0
    for c in range(1, k - 1):
        line = line + d[..., r, c] * inv
    line = line + d[..., r, k - 1] * inv * 1.0
    gt = gt + line * 1.0
gdal_nomask = (k * k) * (gt / ((k * 1.0) * (k * 1.0)))
for name, v in {
    "gdal no-mask path": gdal_nomask,
    "total * (1/n)": total * (1.0 / (k * k)),
    "mean of row means": row_means / k,
    "mean of column means": col_means / k,
    "welford": welford,
    "sum of v/n": row_scaled,
    "row means summed / k": vm / k,
    "row means as float32, then mean": vm32 / k,
}.items():
    if v is None:
        continue
    print(f"{name:32s} differing {int((v.astype(np.float32) != a).sum())} of {a.size}")
mean64 = total / (k * k)
lo = mean64.astype(np.float32)
tie = np.zeros((N, N), bool)
up = np.nextafter(lo, np.float32(np.inf))
dn = np.nextafter(lo, np.float32(-np.inf))
tie |= (up.astype(np.float64) + lo.astype(np.float64)) / 2 == mean64
tie |= (dn.astype(np.float64) + lo.astype(np.float64)) / 2 == mean64
diff = mine != a
odd_gdal = (a.view(np.uint32) & 1).astype(bool)
print("ties", int(tie.sum()), "differing", int(diff.sum()), "differing and tie", int((diff & tie).sum()),
      "gdal odd at ties", int((odd_gdal & tie).sum()), "gdal larger at ties", int(((a > lo) | ((a == lo) & False))[tie].sum()),
      "gdal away from zero (larger) at ties", int((a.astype(np.float64) > mean64)[tie].sum()))
for r, c in np.argwhere(mine != a)[:3]:
    b = d[r, c].ravel()
    print(r, c, repr(a[r, c]), repr(mine[r, c]), "sum", repr(b.sum()), "mean64", repr(b.sum() / b.size))
