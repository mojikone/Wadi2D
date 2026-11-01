"""Manning rasters for the hill sensitivity: hills (non-wadi cells inside the 18 polygons) get n_hill, everything else 0.04.

A wadi is a 5 m flow-accumulation pixel of 1 km2 or more (the HMS terrain's flowaccum.tif), one 20 m cell either side;
the plain outside the polygons stays at the wadi value. One cell, one n: a wadi thread gives its whole 20 m cell the
wadi value. Rasters at 10 m so they serve every grid here; aligned to the DEM origin.
"""
import sys

import numpy as np
import rasterio
import rasterio.features
from rasterio.transform import from_origin
from scipy import ndimage

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import ACC, DEM, OUT, polygons, domain

PIX = 10.0
WADI_KM2 = 1.0
N_WADI = 0.04

with rasterio.open(DEM) as s:
    left, top = s.transform.c, s.transform.f
    crs = s.crs
b = domain().bounds
col = int((b[0] - left) // PIX)
row = int((top - b[3]) // PIX)
x0, y0 = left + col * PIX, top - row * PIX
nx = int(np.ceil((b[2] - x0) / PIX))
ny = int(np.ceil((y0 - b[1]) / PIX))
t = from_origin(x0, y0, PIX, PIX)
hills = rasterio.features.rasterize(polygons().values(), out_shape=(ny, nx), transform=t, fill=0, default_value=1, dtype="uint8").astype(bool)
wadi = np.zeros((ny, nx), bool)
with rasterio.open(ACC) as src:
    w = rasterio.windows.from_bounds(x0, y0 - ny * PIX, x0 + nx * PIX, y0, src.transform).round_offsets().round_lengths()
    a = src.read(1, window=w, masked=True).filled(0.0) * src.res[0] ** 2 * 1e-6
    tt = src.window_transform(w)
    r, c = np.nonzero(a >= WADI_KM2)
    xs = tt.c + (c + 0.5) * tt.a
    ys = tt.f + (r + 0.5) * tt.e
jj = ((y0 - ys) // PIX).astype(int)
ii = ((xs - x0) // PIX).astype(int)
ok = (jj >= 0) & (jj < ny) & (ii >= 0) & (ii < nx)
wadi[jj[ok], ii[ok]] = True
wadi = ndimage.binary_dilation(wadi, iterations=2)
print("hills km2", hills.sum() * PIX**2 * 1e-6, "wadi in polygons km2", (wadi & hills).sum() * PIX**2 * 1e-6)
folder = OUT / "manning"
folder.mkdir(exist_ok=True)
for n_hill in (0.05, 0.1, 0.2):
    n = np.where(hills & ~wadi, n_hill, N_WADI).astype(np.float32)
    path = folder / f"hills_{int(n_hill * 1000):03d}.tif"
    with rasterio.open(path, "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32", crs=crs, transform=t, compress="deflate") as d:
        d.write(n, 1)
    print(path)
