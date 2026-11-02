"""W5's highway test rerun on the same ground with the crest detector as built: found and elsewhere lengths.

Same corridor, terrain and reference as `W5 automatic breaklines test/s01_highway.py`: Bathinah Highway CL inside a 3 km
corridor over the frame of the Block 2 200-yr layer, terrain `W2 full extent run/terrain/NSA5_COP30_blend.tif` at 5 m. Found
is the share of highway samples within 30 m of a suggested line; elsewhere is the length of suggested lines away from it.
Three readings: the raw skeleton as W5 scored it (disc 40 m, 0.5 m), the lines as written with no slope cap, and the
lines as written. Nothing here edits W5. Writes results.json beside this file.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyogrio
import rasterio
import shapely
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from scipy import ndimage
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wadi2d.breaklines import DEFAULTS
from wadi2d.breaklines.crests import crests_of, raised, top_hat
from wadi2d.breaklines.pixels import length_of, thin
from wadi2d.breaklines.window import Window

HERE = Path(__file__).resolve().parent
REPO = Path(r"D:\Mojtaba\Renardet\Wadi2D")
DEM = REPO / "W2 full extent run" / "terrain" / "NSA5_COP30_blend.tif"
ROAD = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\SHP\Roads\Bathinah Highway CL.shp"
FRAME = box(410964, 2699707, 458976, 2742718)
CORRIDOR_M = 3000.0
REACH_M = 30.0
PIX = 5.0


def main() -> None:
    road = pyogrio.read_dataframe(ROAD).to_crs(32640).geometry.union_all().intersection(FRAME)
    zone = road.buffer(CORRIDOR_M)
    with rasterio.open(DEM) as s:
        w = from_bounds(*zone.bounds, s.transform).round_offsets().round_lengths()
        z = s.read(1, window=w, masked=True).filled(np.nan).astype("float64")
        tr = s.window_transform(w)
        crs = s.crs.to_wkt()
    inside = ~geometry_mask([zone.__geo_interface__], z.shape, tr)
    near_road = ~geometry_mask([road.buffer(REACH_M).__geo_interface__], z.shape, tr)
    samples = [road.interpolate(d) for d in np.arange(0.0, road.length, 20.0)]
    win = Window(z, inside & np.isfinite(z), tr.c, tr.f, PIX, 10.0, crs)
    out = {"highway_km": road.length / 1000, "corridor_km2": zone.area * 1e-6, "rows": {}}

    top = top_hat(win.z, PIX, DEFAULTS.disc_radius_m)
    skeleton = thin(raised(top, win.inside, DEFAULTS.crest_height_m, DEFAULTS.min_length_m, PIX))
    d = ndimage.distance_transform_edt(~skeleton) * PIX
    rc = np.array([rasterio.transform.rowcol(tr, p.x, p.y) for p in samples])
    out["rows"]["raw skeleton, as W5 scored it"] = {
        "found": float((d[rc[:, 0], rc[:, 1]] <= REACH_M).mean()),
        "km_elsewhere": float((skeleton & ~near_road).sum() * PIX * 1.1 / 1000),
    }
    print(out["rows"], flush=True)

    near = road.buffer(REACH_M)
    for name, settings in (("lines, no slope cap", replace(DEFAULTS, ground_slope_max=10.0)), ("lines as written", DEFAULTS)):
        crests = crests_of(win, [], 0.5, settings)
        lines = [shapely.LineString(c.xy) for c in crests]
        tree = shapely.STRtree(lines)
        found = np.mean([tree.query(p.buffer(REACH_M), predicate="intersects").size > 0 for p in samples])
        on = sum(ln.intersection(near).length for ln in lines)
        total = sum(length_of(c.xy) for c in crests)
        out["rows"][name] = {
            "found": float(found),
            "km_on_highway": on / 1000,
            "km_elsewhere": (total - on) / 1000,
            "lines": len(crests),
            "kinds": {k: sum(c.kind == k for c in crests) for k in {c.kind for c in crests}},
        }
        print(name, out["rows"][name], flush=True)
    (HERE / "highway_results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
