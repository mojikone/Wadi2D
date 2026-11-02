"""The hybrid setup as map layers: subbasins with their mode, inflow points, 2D domain, open boundaries, dam sections, reaches.
Reads the run's own job.json, so the map shows what the engine was given. Writes layers/*.geojson and setup.json."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import pyogrio
from shapely.geometry import Point, mapping

HERE = Path(__file__).resolve().parent
RUN = Path(sys.argv[1])
SHP = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Claude Block 02\W1\output\shp")
OUT = HERE / "layers"
OUT.mkdir(exist_ok=True)
CRS = {"type": "name", "properties": {"name": "EPSG:32640"}}


def write(name, features):
    (OUT / f"{name}.geojson").write_text(json.dumps({"type": "FeatureCollection", "crs": CRS, "features": features}), encoding="utf-8")


job = json.loads((RUN / "job.json").read_text(encoding="utf-8")) if (RUN / "job.json").exists() else json.loads((RUN.parent / "job.json").read_text(encoding="utf-8"))
subs = {s["name"]: s for s in job["hydrology"]["subbasins"]}

polygons = pyogrio.read_dataframe(SHP / "Subbasins_B1.shp").to_crs(32640)
name_field = next(c for c in polygons.columns if c.lower() in ("name", "subbasin", "basin", "id"))
print("subbasin name field", name_field, polygons[name_field].tolist()[:6])
features = []
area_lumped = area_2d = 0.0
for _, row in polygons.iterrows():
    name = str(row[name_field])
    mode = subs.get(name, {}).get("mode", "?")
    km2 = row.geometry.area * 1e-6
    if mode == "lumped":
        area_lumped += km2
    else:
        area_2d += km2
    label = f"{name}\nlumped HMS" if mode == "lumped" else f"{name}\n2D rain-on-grid"
    features.append({"type": "Feature", "properties": {"name": name, "mode": mode, "km2": round(km2, 1), "label": label}, "geometry": mapping(row.geometry)})
write("subbasins", features)

points: dict = defaultdict(list)
for name, s in subs.items():
    if s.get("mode") == "lumped" and s.get("outlet"):
        points[tuple(round(v, 1) for v in s["outlet"])].append(name)
write("inflows", [
    {"type": "Feature", "properties": {"label": "Inflow " + ", ".join(names), "names": ",".join(names)}, "geometry": mapping(Point(xy))}
    for xy, names in points.items()
])  # fmt: skip

write("boundaries", [
    {"type": "Feature", "properties": {"label": f"Open boundary {n + 1}"}, "geometry": {"type": "LineString", "coordinates": b["coordinates"]}}
    for n, b in enumerate(job["boundaries"])
])  # fmt: skip

design = json.loads((RUN.parent / "run" / "inputs" / "design_points.geojson").read_text(encoding="utf-8")) if (RUN.parent / "run" / "inputs" / "design_points.geojson").exists() else None
lines = job.get("outputs", {}).get("lines", [])
write("sections", [{"type": "Feature", "properties": {"label": k["name"]}, "geometry": {"type": "LineString", "coordinates": k["coordinates"]}} for k in lines if not k["name"].endswith("_ring") and "ring" not in k["name"].lower()])

domain = json.loads(Path(job["grid"]["domain"]).read_text(encoding="utf-8"))
geom = domain["features"][0]["geometry"]
(OUT / "domain.geojson").write_text(json.dumps({"type": "FeatureCollection", "crs": CRS, "features": [{"type": "Feature", "properties": {"label": "2D model domain"}, "geometry": geom}]}), encoding="utf-8")

reach_file = SHP / "Reaches_B1.shp"
if reach_file.exists():
    r = pyogrio.read_dataframe(reach_file).to_crs(32640)
    field = next((c for c in r.columns if c.lower() in ("name", "reach", "id")), None)
    write("reaches", [{"type": "Feature", "properties": {"label": str(row[field]) if field else ""}, "geometry": mapping(row.geometry)} for _, row in r.iterrows()])
    print("reaches", len(r), field)
storm = job["storm"]
print("sections", [k["name"] for k in lines], "inflow points", len(points))
(HERE / "setup.json").write_text(json.dumps({
    "lumped_n": sum(1 for s in subs.values() if s["mode"] == "lumped"), "two_d": [n for n, s in subs.items() if s["mode"] != "lumped"],
    "lumped_km2": round(area_lumped, 1), "two_d_subbasin_km2": round(area_2d, 1), "inflow_points": len(points), "boundaries": len(job["boundaries"]),
    "dx": job["grid"]["dx"], "storm_mm": storm["depth_mm"], "storm_area": storm.get("storm_area_km2"), "duration_h": job["run"]["duration_s"] / 3600,
    "manning": job["terrain"].get("manning"), "cn_raster": bool(job["terrain"].get("cn_raster")),
}, indent=1), encoding="utf-8")  # fmt: skip
