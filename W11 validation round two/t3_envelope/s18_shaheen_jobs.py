"""Wadi2D rain-on-grid on the Lihban basin under the gauged Shaheen rain, excess volume equal to the observed volume."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
import shapefile
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
B = Path(r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\03-Hydrology\calibration\HMS_Albatinah_Calibration")
DEM = ROOT / "W2 full extent run" / "terrain" / "NSA5_COP30_blend.tif"
r = shapefile.Reader(str(B / "Basin_DB839224AD.shp"))
print(len(r), r.fields[1:5], r.record(0))
g = shape(r.shape(0).__geo_interface__)
crs = CRS.from_wkt((B / "Basin_DB839224AD.prj").read_text())
print(crs.name, g.bounds)
if crs.to_epsg() != 32640:
    tr = Transformer.from_crs(crs, 32640, always_xy=True)
    g = shapely.transform(g, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1])))
g = shapely.make_valid(g)
if g.geom_type != "Polygon":
    g = max(g.geoms, key=lambda p: p.area)
print("basin km2", g.area / 1e6, g.bounds)
GX, GY = 488963.0, 2632307.0
pt = shapely.Point(GX, GY)
print("gauge inside", g.contains(pt), "distance", g.exterior.distance(pt))
with rasterio.open(DEM) as s:
    z = [v[0] for v in s.sample([(GX, GY), (GX - 3000, GY - 3000), (GX + 500, GY + 500)])]
    print("dem around the gauge", z, s.nodata)
    w = rasterio.windows.from_bounds(GX - 1500, GY - 1500, GX + 1500, GY + 1500, s.transform)
    a = s.read(1, window=w)
    j, i = np.unravel_index(np.argmin(a), a.shape)
    t = s.window_transform(w)
    print("lowest within 1.5 km", a.min(), t * (i, j))
a = np.loadtxt(HERE / "shaheen_5min.csv", delimiter=",", skiprows=1)
tq, p, obs = a[:, 0], a[:, 1], a[:, 2]
depth = json.loads((HERE / "shaheen_fit.json").read_text())["obs_depth_mm"]
lo, hi = 0.0, p.max()
for _ in range(60):
    m = 0.5 * (lo + hi)
    if np.maximum(p - m, 0.0).sum() > depth:
        lo = m
    else:
        hi = m
ex = {"phi": np.maximum(p - hi, 0.0), "fraction": p * depth / p.sum()}
print("phi rate mm/5min", hi, "mm/h", hi * 12)
box = shapely.box(GX - 250, GY - 250, GX + 1600, GY + 1800)  # below the gauge only: the wadi leaves north-east through the gap
dom = shapely.union_all([g, box]).buffer(0)
(HERE / "domain_lihban.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "lihban"}, "geometry": mapping(dom)}]}), encoding="utf-8")
for name, e in ex.items():
    k0 = int(np.argmax(e > 0.0))
    k1 = len(e) - int(np.argmax(e[::-1] > 0.0))
    cum = np.concatenate(([0.0], np.cumsum(e[k0:k1])))
    dur = 5.0 * (k1 - k0)
    times = 5.0 * np.arange(k1 - k0 + 1)
    start = tq[k0] - 5.0
    job = {
        "project": {"name": f"lihban_{name}", "description": f"Shaheen, excess {name}, starts {start:.0f} min from 00:00 4 Oct"},
        "grid": {"dx": 20.0, "domain": str(HERE / "domain_lihban.geojson"), "cache_dir": str(HERE / "cache")},
        "terrain": {"dem": str(DEM), "pixel_stride": 1, "manning": 0.05},
        "storm": {"kind": "hypothetical", "depth_mm": float(e.sum()), "duration_min": float(dur), "time_percent": (100.0 * times / times[-1]).tolist(), "depth_percent": (100.0 * cum / cum[-1]).tolist()},
        "boundaries": [
            {"kind": "normal", "slope": 0.008, "coordinates": [[GX + 1590, GY + 60], [GX + 1590, GY + 1790]]},
            {"kind": "normal", "slope": 0.008, "coordinates": [[GX + 60, GY + 1790], [GX + 1590, GY + 1790]]},
        ],
        "outputs": {"map_every_s": 1800.0, "series_every_s": 120.0, "live_every_s": 0.0, "lines": [{"name": "gauge", "coordinates": [[GX + 700, GY - 700], [GX - 700, GY + 700]]}]},
        "run": {"duration_s": float(dur * 60.0 + 12 * 3600.0), "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }
    (HERE / "jobs").mkdir(exist_ok=True)
    (HERE / "jobs" / f"lihban_{name}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print(name, "depth", e.sum(), "dur min", dur, "start min", start, "peak 5 min", e.max())
