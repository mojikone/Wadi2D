"""What the Block02 stakeholder model holds, and whether his 100-yr layer came from it. Read only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import rasterio

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
H = Path(r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\04-Hydraulic")
M = H / r"03 Additional Task Hydraulic\10 Workshops with stakeholders\Hydraulic Models\Block2\Block02"
R = H / r"00 Data\Layers\Flood Maps\Depth\Rasters OK\B2 Depth Rasters"
HERE = Path(__file__).resolve().parent

f = h5py.File(M / "Block02.p04.hdf", "r")
A = "Perimeter 1"
g = f["Geometry/2D Flow Areas"]
print(list(g.keys()))
print(g["Attributes"][()][0])
m = g[A]
print(list(m.keys())[:30])
nc = int(g["Attributes"]["Cell Count"][0])
cc = m["Cells Center Coordinate"][:nc]
area = m["Cells Surface Area"][:nc]
print("cells", nc, "area km2", area.sum() / 1e6, "x", cc[:, 0].min(), cc[:, 0].max(), "y", cc[:, 1].min(), cc[:, 1].max())
print("cell area pct 5,50,95 m2", np.percentile(area, [5, 50, 95]), "equivalent dx", np.sqrt(np.percentile(area, [5, 50, 95])))
per = m["Perimeter"][:]
print("perimeter pts", per.shape, per.min(axis=0), per.max(axis=0))
print(dict(f["Plan Data/Plan Parameters"].attrs).keys())
pp = f["Plan Data/Plan Parameters"].attrs
for k in ("2D Equation Set", "2D Theta", "2D Cores (per mesh)", "Time Window"):
    if k in pp:
        print(k, pp[k])
print({k: (v.decode() if isinstance(v, bytes) else v) for k, v in f["Plan Data/Plan Information"].attrs.items()})
va = f["Results/Unsteady/Summary/Volume Accounting"].attrs
print({k: (float(v) if not isinstance(v, (bytes, str)) else v) for k, v in va.items()})
def show(n, o):
    if "Infiltr" in n or "Land Cover" in n or "Precip" in n:
        print(n, getattr(o, "shape", None))
f.visititems(show)
wse = f[f"Results/Unsteady/Output/Output Blocks/Base Output/Summary Output/2D Flow Areas/{A}/Maximum Water Surface"][0, :nc].astype(np.float64)
zmin = m["Cells Minimum Elevation"][:nc]
d = wse - zmin
print("wet cells >0.1", (d > 0.1).sum(), "depth p50,p95", np.percentile(d[d > 0.1], [50, 95]))
# his 100-yr layer at the cell centres: depth over the pixel beneath, against the model's water surface
with rasterio.open(R / "Block2_Depth_100Year.tif") as s:
    print(s.bounds, s.res, s.nodata)
    v = np.array([x[0] for x in s.sample(cc[::1].tolist())], np.float64)
    v[v == s.nodata] = np.nan
wet_h = np.isfinite(v)
wet_m = d > 0.05
print("cells wet in his layer", wet_h.sum(), "in model >0.05", wet_m.sum(), "both", (wet_h & wet_m).sum(), "F", (wet_h & wet_m).sum() / (wet_h | wet_m).sum())
np.savez_compressed(HERE / "block02_c100.npz", cc=cc, area=area, wse=wse, zmin=zmin, his=v)
