"""His 200-yr layer and the two Wadi2D layers on one 5 m lattice, inside his model's perimeter; F by threshold and zone."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import rasterio
import rasterio.features
import shapely
from rasterio.enums import Resampling
from rasterio.warp import reproject

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
HIS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Raster\Block2_Depth_200Year.tif")
W2 = ROOT / "W2 full extent run" / "terrain" / "pixel_depth_sloped_5m.tif"
W7 = ROOT / "W7 plugin test" / "maps" / "terrain" / "pixel_depth_sloped_5m.tif"
M = Path(r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\04-Hydraulic\03 Additional Task Hydraulic\10 Workshops with stakeholders\Hydraulic Models\Block2\Block02")

for p in (HIS, W2, W7):
    with rasterio.open(p) as s:
        print(p.name, s.width, s.height, s.res, [round(b, 2) for b in s.bounds], s.nodata, s.dtypes[0])

with h5py.File(M / "Block02.g02.hdf", "r") as f:
    per = f["Geometry/2D Flow Areas/Perimeter 1/Perimeter"][:]
poly = shapely.Polygon(per)
print("perimeter km2", poly.area / 1e6, poly.bounds)
(HERE / "his_perimeter.json").write_text(json.dumps(per.tolist()), encoding="utf-8")

dx = 5.0
b = poly.bounds
# the W2 lattice, cropped to his perimeter
with rasterio.open(W2) as s:
    t0 = s.transform
    c0 = int(np.floor((b[0] - t0.c) / dx))
    r0 = int(np.floor((t0.f - b[3]) / dx))
    c1 = int(np.ceil((b[2] - t0.c) / dx))
    r1 = int(np.ceil((t0.f - b[1]) / dx))
    win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
    t = s.window_transform(win)
    w2 = s.read(1, window=win, masked=True).filled(np.nan).astype(np.float32)
shape = w2.shape
print("lattice", shape, t)


def warp(path: Path, how=Resampling.nearest) -> np.ndarray:
    out = np.full(shape, np.nan, np.float32)
    with rasterio.open(path) as s:
        reproject(rasterio.band(s, 1), out, dst_transform=t, dst_crs="EPSG:32640", dst_nodata=np.nan, resampling=how)
    return out


his = warp(HIS)
w7 = warp(W7)
mask = rasterio.features.geometry_mask([poly], out_shape=shape, transform=t, invert=True)
np.savez_compressed(HERE / "layers_5m.npz", his=his, w2=w2, w7=w7, mask=mask, t=np.array(t)[:6])
print("saved", {k: float(np.isfinite(v).sum() * 25e-6) for k, v in (("his", his), ("w2", w2), ("w7", w7))})
