"""Rain-on-grid over the basin of the Fizh near Sabakh gauge, 262 km2, holding S1 to S4 (the Z4C catchment) and the plain.

A check outside the four tests' rules, reported as such: what does the 2D model give at a real gauge? 100-yr Block 2 storm
at storm area 262 km2, project CN grid, n 0.05, 20 m, as Block 2 mode (c), natural ground, no dams. A section at the gauge
and one on the Z4C axis.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import shapefile
import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import AXES, CN, DEM, storm  # noqa: E402

HERE = Path(__file__).resolve().parent
L = Path(r"W:\2331 Flood Hazard Maps for Muscat-Dhofar-Musandam_MWR\06-WORKING\03-Hydrology\0.13 REPORTS\Hydrology Final Report- Flood Data Analysis\Layers\Wadi Gauges Basin")
r = shapefile.Reader(str(L / "DC417300AD.shp"))
g = shape(r.shape(0).__geo_interface__)
tr = Transformer.from_crs(4326, 32640, always_xy=True)
g = shapely.transform(g, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1])))
g = shapely.make_valid(g)
if g.geom_type != "Polygon":
    g = max(g.geoms, key=lambda p: p.area)
print("basin km2", g.area / 1e6, g.bounds)
for x in (446000, 447000, 447400, 447550):
    sec = g.intersection(shapely.LineString([(x, 2690000), (x, 2730000)]))
    print(x, sec.length, sec.bounds if not sec.is_empty else None)
GX, GY = 447523.0, 2713540.0
print("gauge in polygon?", g.contains(shapely.Point(GX, GY)), "distance", g.exterior.distance(shapely.Point(GX, GY)))
box = shapely.box(446800.0, GY - 2500.0, 449300.0, GY + 2500.0)
dom = shapely.union_all([g, box]).buffer(0)
(HERE / "domain_fizh.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "fizh"}, "geometry": mapping(dom)}]}), encoding="utf-8")
area = g.area / 1e6
job = {
    "project": {"name": "fizh_gauge", "description": "2D at the Fizh near Sabakh gauge"},
    "grid": {"dx": 20.0, "domain": str(HERE / "domain_fizh.geojson"), "cache_dir": str(HERE / "cache")},
    "terrain": {"dem": str(DEM), "pixel_stride": 2, "manning": 0.05, "cn_raster": str(CN)},
    "storm": {**storm(area)},
    "hydrology": {"curve_number": 88.0},
    "boundaries": [{"kind": "normal", "slope": 0.008, "coordinates": [[449290.0, GY - 2500.0], [449290.0, GY + 2500.0]]}],
    "outputs": {"map_every_s": 3600.0, "series_every_s": 120.0, "live_every_s": 0.0, "lines": [
        {"name": "gauge", "coordinates": [[GX, GY - 2500.0], [GX, GY + 2500.0]]},
        {"name": "z4c", "coordinates": [list(p) for p in AXES["Z4C"]]},
    ]},
    "run": {"duration_s": 36 * 3600.0, "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
}
(HERE / "jobs").mkdir(exist_ok=True)
(HERE / "jobs" / "fizh_gauge.json").write_text(json.dumps(job, indent=1, default=float), encoding="utf-8")
print("written; storm depth", job["storm"]["depth_mm"], "area", job["storm"]["storm_area_km2"])
