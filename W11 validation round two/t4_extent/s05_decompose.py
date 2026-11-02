"""Where F 0.40 comes from. Rebuild it, then change one thing at a time. And: did his 100-yr layer come from the Block02 model?"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
import shapely
from rasterio.enums import Resampling
from rasterio.warp import reproject

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
HIS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Raster\Block2_Depth_200Year.tif")
W2 = ROOT / "W2 full extent run" / "terrain" / "pixel_depth_sloped_5m.tif"
CELL = ROOT / "W2 full extent run" / "runs" / "full_30m_200yr" / "maps" / "max_mean_depth.tif"
GGC5 = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif")

per = np.array(json.loads((HERE / "his_perimeter.json").read_text(encoding="utf-8")))
poly = shapely.Polygon(per)
with rasterio.open(HIS) as s:
    frame = s.bounds
# 30 m lattice of the W2 run over his frame
with rasterio.open(CELL) as s:
    tr = s.transform
    c0 = int(np.floor((frame.left - tr.c) / 30))
    r0 = int(np.floor((tr.f - frame.top) / 30))
    c1 = int(np.ceil((frame.right - tr.c) / 30))
    r1 = int(np.ceil((tr.f - frame.bottom) / 30))
    win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
    t30 = s.window_transform(win)
    cell = s.read(1, window=win, masked=True).filled(0.0).astype(np.float32)
sh30 = cell.shape
print("frame km2", sh30[0] * sh30[1] * 900e-6)

# his 3 m depth averaged to 30 m, dry pixels as dry, as s03_check
with rasterio.open(HIS) as s:
    a = s.read(1)
    a = np.where(a == s.nodata, 0.0, a).astype(np.float32)
    t3 = s.transform
his30 = np.zeros(sh30, np.float32)
reproject(a, his30, src_transform=t3, src_crs="EPSG:32640", dst_transform=t30, dst_crs="EPSG:32640", resampling=Resampling.average)
del a
# W2 pixel depth averaged to 30 m, dry as dry
with rasterio.open(W2) as s:
    w = s.read(1, window=rasterio.windows.from_bounds(*frame, s.transform), masked=True).filled(0.0).astype(np.float32)
    tw = s.window_transform(rasterio.windows.from_bounds(*frame, s.transform))
pix30 = np.zeros(sh30, np.float32)
reproject(w, pix30, src_transform=tw, src_crs="EPSG:32640", dst_transform=t30, dst_crs="EPSG:32640", resampling=Resampling.average)
inside = rasterio.features.geometry_mask([poly], out_shape=sh30, transform=t30, invert=True)
everywhere = np.ones(sh30, bool)


def F(a, b, m, km2=900e-6):
    both = (a & b & m).sum()
    o1 = (a & ~b & m).sum()
    o2 = (~a & b & m).sum()
    return {"F": round(float(both / max(both + o1 + o2, 1)), 3), "both": round(both * km2, 1), "his_only": round(o1 * km2, 1), "wadi_only": round(o2 * km2, 1)}


th = 0.3
out = {
    "A cell mean 30 m, his frame (the 0.40)": F(his30 >= th, cell >= th, everywhere),
    "B same, inside his model perimeter only": F(his30 >= th, cell >= th, inside),
    "C pixel depth averaged to 30 m, his frame": F(his30 >= th, pix30 >= th, everywhere),
    "D pixel depth averaged to 30 m, perimeter": F(his30 >= th, pix30 >= th, inside),
}
for k, v in out.items():
    print(k, v)
print("Wadi2D wet >=0.3 outside his perimeter, km2", ((cell >= th) & ~inside).sum() * 900e-6, " his outside", ((his30 >= th) & ~inside).sum() * 900e-6)
print("cell mean at 0.1:", F(his30 >= 0.1, cell >= 0.1, everywhere), F(his30 >= 0.1, cell >= 0.1, inside))

# 5 m pixels over his frame and over the perimeter
th5 = {}
z = np.load(HERE / "layers_5m.npz")
out["E 5 m pixels, perimeter"] = F(np.nan_to_num(z["his"], nan=-1) >= th, np.nan_to_num(z["w2"], nan=-1) >= th, z["mask"], 25e-6)
print(out["E 5 m pixels, perimeter"])
(HERE / "decompose.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

# his 100-yr layer against the Block02 C100 model: water surface from the layer, on the GGC 5 m ground
b = np.load(HERE / "block02_c100.npz")
cc, wse, zmin, his = b["cc"], b["wse"], b["zmin"], b["his"]
m = np.isfinite(his) & (his > 0.3)
idx = np.nonzero(m)[0][::5]
with rasterio.open(GGC5) as s:
    g = np.array([v[0] for v in s.sample(cc[idx].tolist())], float)
    nd = s.nodata
ok = g != nd
dz = (his[idx] + g - wse[idx])[ok]
print("100-yr: his depth + GGC 5 m ground - model max WSE, m: mean", dz.mean(), "rms", np.sqrt((dz**2).mean()), "p5,50,95", np.percentile(dz, [5, 50, 95]), "n", dz.size)
print("wse range", wse[idx][ok].min(), wse[idx][ok].max(), "ground", g[ok].min(), g[ok].max())
