"""The designer's own layers for W104, as he would draw or type them before opening the dock.

Run once with the project's venv. Writes into ``inputs/`` (in git, small):

- ``rough_outline.gpkg``: a rough outline of Block 2, drawn towards the mountains and to the sea. Within 100 m of the
  four outflow lines it follows W79's domain (the edges a designer draws exactly: the coast and the three side
  outlets); elsewhere one vertex in every 4 km of W79's edge, so the hill side is off by up to about a kilometre and
  Complete upstream has to find the divides itself.
- ``outflow_lines.gpkg``: the sea line, Wadi HAT's north line, Wadi Fizh's branch and the 1 km2 north stream, the four
  lines of W79's jobs, with a name only; the kind and slope are typed in the dock's Boundaries table.
- ``crest_lines.gpkg`` (name, z) and ``spillways.gpkg`` (name, z, c, length): the five dams of W79
  (``W79 .../inputs/dams.geojson``: W1's Bidah 03 and Faydh 01 on the GGC datum, R5A, R2A and Z4C from
  Det_Design_DAMS), as the design input a designer draws.
- ``dam_lines.gpkg``: the five dam lines along the crests, the result lines of record.
- ``storm_numbers.json``: what is typed into the dock: 251 mm in 24 h, the 24 h pattern of his FM_200yr.met as percent
  of time and depth, his ARF FM table, the 100 km2 area of the 2D part, the four slopes, and the places a designer
  clicks for the basin points (200 m below each dam, W79's entries; HAT-J4's icon of his HMS basin).

Nothing of his is written: his files are read only, W79's are read only.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import shapely
from shapely.geometry import LineString, Polygon, shape

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parent
W79 = REPO / "W79 Block 2 four ways"
INPUTS = HERE / "inputs"
CRS = "EPSG:32640"
EXACT_M = 100.0
"""The outline follows W79's domain this close to an outflow line: an edge drawn exactly."""
ROUGH_STEP_M = 4000.0
"""Elsewhere one vertex in this much of W79's edge."""


SWING_M = (1000.0, -700.0)
"""A hand's swing: the rough vertices lie alternately this far out from and in towards the middle of the block."""


def rough_ring(ring: list[tuple[float, float]], lines: shapely.Geometry, middle: shapely.Point) -> list[tuple[float, float]]:
    near = lines.buffer(EXACT_M)
    out, run, turn = [], ROUGH_STEP_M, 0
    for a, b in zip(ring[:-1], ring[1:], strict=True):
        point = shapely.Point(a)
        if near.buffer(ROUGH_STEP_M / 4).contains(point):  # the drawn edges, and a short run to and from them
            if near.contains(point):
                out.append(a)
            run = ROUGH_STEP_M
            continue
        run += point.distance(shapely.Point(b))
        if run >= ROUGH_STEP_M:
            dx, dy = a[0] - middle.x, a[1] - middle.y
            far = (dx * dx + dy * dy) ** 0.5
            swing = SWING_M[turn % 2]
            out.append((a[0] + swing * dx / far, a[1] + swing * dy / far))
            turn += 1
            run = 0.0
    out.append(out[0])
    return out


def main() -> None:
    INPUTS.mkdir(exist_ok=True)
    job = json.loads((W79 / "jobs" / "rerun2_run1_full_2d_aligned.json").read_text(encoding="utf-8"))
    run3 = json.loads((W79 / "jobs" / "rerun2_run3_hybrid_aligned.json").read_text(encoding="utf-8"))
    names = ["Sea", "Wadi HAT north", "Wadi Fizh branch", "North stream"]
    outflows = [(name, b) for name, b in zip(names, job["boundaries"], strict=True)]
    gpd.GeoDataFrame(
        {"name": [n for n, _b in outflows]}, geometry=[LineString(b["coordinates"]) for _n, b in outflows], crs=CRS
    ).to_file(INPUTS / "outflow_lines.gpkg", driver="GPKG")
    lines = shapely.union_all([LineString(b["coordinates"]) for _n, b in outflows])

    domain = json.loads((W79 / "inputs" / "domain_no_rim.geojson").read_text(encoding="utf-8"))
    whole = shapely.union_all([shape(f["geometry"]) for f in domain["features"]])
    biggest = max(shapely.get_parts(whole), key=lambda p: p.area)
    ring = list(biggest.exterior.coords)
    rough = Polygon(rough_ring(ring, lines, biggest.centroid)).buffer(0)
    gpd.GeoDataFrame({"name": ["Block 2, rough"]}, geometry=[rough], crs=CRS).to_file(
        INPUTS / "rough_outline.gpkg", driver="GPKG"
    )

    dams = json.loads((W79 / "inputs" / "dams.geojson").read_text(encoding="utf-8"))["features"]
    objects = job["terrain"]["objects"]
    crest = [o for o in objects if o["kind"] == "crest_line"]
    spill = [o for o in objects if o["kind"] == "spillway"]
    gpd.GeoDataFrame(
        {"name": [o["name"] for o in crest], "z": [o["z_constant"] for o in crest]},
        geometry=[LineString(o["coordinates"]) for o in crest], crs=CRS,
    ).to_file(INPUTS / "crest_lines.gpkg", driver="GPKG")  # fmt: skip
    gpd.GeoDataFrame(
        {
            "name": [o["name"] for o in spill], "z": [o["z_constant"] for o in spill],
            "c": [o["coefficient"] for o in spill], "length": [o["length"] for o in spill],
        },
        geometry=[LineString(o["coordinates"]) for o in spill], crs=CRS,
    ).to_file(INPUTS / "spillways.gpkg", driver="GPKG")  # fmt: skip
    dam_lines = [line for line in job["outputs"]["lines"] if not line["name"].endswith("inflow")]
    gpd.GeoDataFrame(
        {"name": [line["name"] for line in dam_lines]},
        geometry=[LineString(line["coordinates"]) for line in dam_lines], crs=CRS,
    ).to_file(INPUTS / "dam_lines.gpkg", driver="GPKG")

    storm = job["storm"]
    below = {f["properties"]["dam"]: f["geometry"]["coordinates"] for f in dams if f["properties"]["kind"] == "outflow_entry_run3"}
    hat = next(i for i in run3["hydrology"]["inflows"] if i["element"] == "HAT-J4")
    numbers = {
        "source": "W79 rerun2 jobs (his FM_200yr.met: 251 mm, 24 h pattern, ARF FM table); read only",
        "depth_mm": storm["depth_mm"],
        "duration_h": storm["duration_min"] / 60.0,
        "pattern": {"time_percent": storm["time_percent"], "depth_percent": storm["depth_percent"]},
        "arf_fm": {
            "areas_km2": storm["arf"]["areas_km2"], "factors": storm["arf"]["factors"],
            "reduces_below_table": storm["arf"]["reduces_below_table"],
        },
        "grid_area_km2": storm["storm_area_km2"],
        "slopes": {name: b["slope"] for name, b in outflows},
        "manning": job["terrain"]["manning"],
        "manning_raster": job["terrain"]["manning_raster"],
        "cn_raster": job["terrain"]["cn_raster"],
        "curve_number_fill": job["hydrology"]["curve_number"],
        "dem": job["terrain"]["dem"],
        "dx": job["grid"]["dx"],
        "lumped_step_min": job["hydrology"]["time_step_min"],
        "duration_hours": job["run"]["duration_s"] / 3600.0,
        "map_every_min": job["outputs"]["map_every_s"] / 60.0,
        "clicks": {
            **{f"{dam} outfall": below[dam] for dam in below},
            "HAT-J4": [hat["x"], hat["y"]],
        },
        "rough_outline_km2": rough.area / 1e6,
        "w79_domain_km2": whole.area / 1e6,
    }  # fmt: skip
    (INPUTS / "storm_numbers.json").write_text(json.dumps(numbers, indent=1), encoding="utf-8")
    print(f"rough outline {rough.area / 1e6:,.1f} km2 ({len(rough.exterior.coords)} vertices) against W79's "
          f"{whole.area / 1e6:,.1f} km2; symmetric difference {rough.symmetric_difference(whole).area / 1e6:,.1f} km2")


if __name__ == "__main__":
    main()
