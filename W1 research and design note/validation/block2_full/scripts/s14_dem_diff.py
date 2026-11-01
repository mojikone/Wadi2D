"""GGC_2_MERGE_HDSM against NSA_Batinah at 5 m: is the difference a datum, and where. Reads only."""
import json
import sys

import numpy as np
import rasterio
import rasterio.features
import shapefile
import shapely
from rasterio.warp import Resampling, reproject

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import BLOCK, DAMS, OUT, polygons

a_path = BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif"
b_path = BLOCK / "Terrain" / "NSA_Batinah_5m.tif"
r = shapefile.Reader(str(DAMS / "Reservoirs.shp"))
shapes = [shapely.geometry.shape(s.__geo_interface__) for s in r.shapes()]
res = {"Bidah 03 reservoir": shapes[0], "Faydh 01 reservoir": shapes[1]}
polys = polygons()
items = dict(res)
items.update({"all 18 subbasins": shapely.union_all(list(polys.values())),
              "plain box": shapely.box(437000, 2725000, 443000, 2735000),
              "S1": polys["S1"], "S13": polys["S13"], "S12": polys["S12"]})
out = {}
with rasterio.open(a_path) as A, rasterio.open(b_path) as B:
    for name, g in items.items():
        w = rasterio.windows.from_bounds(*g.bounds, A.transform).round_offsets().round_lengths()
        a = A.read(1, window=w, masked=True).astype(np.float64).filled(np.nan)
        t = A.window_transform(w)
        b = np.full(a.shape, np.nan)
        reproject(rasterio.band(B, 1), b, dst_transform=t, dst_crs=A.crs, resampling=Resampling.bilinear, dst_nodata=np.nan)
        m = rasterio.features.geometry_mask([g], a.shape, t, invert=True) & np.isfinite(a) & np.isfinite(b)
        d = (a - b)[m]
        out[name] = {"mean": float(d.mean()), "median": float(np.median(d)), "p5": float(np.percentile(d, 5)),
                     "p95": float(np.percentile(d, 95)), "std": float(d.std()), "n": int(m.sum())}
        print(name, {k: round(v, 3) for k, v in out[name].items()})
(OUT / "dem_difference.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
