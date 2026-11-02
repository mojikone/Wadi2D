"""Test-4 jobs with an outlet that really opens: the domain edge inset by 2 cells, clipped to his Sea stretch.

Every point of the line lies inside the active cells, so the engine's one-cell search cannot drop it. s13_boundary_check.py
gates these jobs before any run. Earlier sets t_ and b_ are kept but are not valid: their lines opened 4 to 42 % of their length.
"""
from __future__ import annotations

import json
from pathlib import Path

import shapely
from shapely.ops import linemerge

HERE = Path(__file__).resolve().parent
per = json.loads((HERE / "his_perimeter.json").read_text(encoding="utf-8"))
poly = shapely.make_valid(shapely.Polygon(per))
if poly.geom_type != "Polygon":
    poly = max(poly.geoms, key=lambda g: g.area)
sea_coords = json.loads((HERE / "jobs" / "t0_base.json").read_text(encoding="utf-8"))["boundaries"][0]["coordinates"]
sea = shapely.LineString(sea_coords)
print("sea to perimeter, m: max", max(poly.exterior.distance(shapely.Point(p)) for p in sea_coords))


def outlet(dx: float) -> list[list[list[float]]]:
    inner = poly.buffer(-2.0 * dx, join_style="mitre", mitre_limit=4.0)
    if inner.geom_type != "Polygon":
        inner = max(inner.geoms, key=lambda g: g.area)
    near = inner.exterior.intersection(sea.buffer(2.0 * dx + 300.0))
    parts = [near] if near.geom_type == "LineString" else list(linemerge(near).geoms) if near.geom_type == "MultiLineString" and linemerge(near).geom_type == "MultiLineString" else [linemerge(near)]
    parts = [g.simplify(1.0) for g in parts if g.length > 200.0]
    print(f"dx {dx:g}: {len(parts)} lines, km", [round(g.length / 1e3, 2) for g in parts])
    return [[[float(x), float(y)] for x, y in g.coords] for g in parts]


for n in ("t0_base", "t1_rain228", "t2_n060", "t3_ggc", "t4_dx15", "t5_all"):
    j = json.loads((HERE / "jobs" / f"{n}.json").read_text(encoding="utf-8"))
    dx = j["grid"]["dx"]
    j["boundaries"] = [{"kind": "normal", "slope": 0.0065, "coordinates": c} for c in outlet(dx)]
    j["project"]["name"] = j["project"]["name"] + "_sea"
    (HERE / "jobs" / f"c_{n}.json").write_text(json.dumps(j, indent=1), encoding="utf-8")
