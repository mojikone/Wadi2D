"""The four jobs of the rerun (2026-11-15), from one base: ``wadi2d hms-import`` of Basin 3, FM_200yr.met and
Control_1.control.

Common to all: the 200-yr storm of FM_200yr.met (251 mm, the FM 10-1000yr pattern, 24 h) with its ARF FM table read at
one storm area of 100 km2 (his choice of 2026-11-15; the first attempt read it at Basin 3's 1,370.77 km2); 48 h and the
5-minute lumped step of Control_1; dams start empty (no dam_levels entry; Basin 3's reservoirs start at the bottom of
their tables, the grid pools dry). 2D runs: the domain to the sea, the aligned centre mesh at 20 m, the 0.5 m pixel
(pixel_stride 1), GPU, GGC 0.5 m terrain, W1's Manning rule, the CN raster of his HMS project with CN 88 where it has
none, the sea, side and north outlets as normal lines, maps every 15 min, the five dam lines (W1's) and a line round each
pool's upstream edge, pixel maps on, polygons and drawing off.

The ARF, his decisions of 2026-11-15:

1. Full 2D: no lumped element, rain on every cell at 100 km2; the five dams as crest lines and spillways on the grid.
2. Full HMS way: Basin 3 on the lumped engine alone (s03_lumped.py), every junction and reservoir at its own total
   upstream area, HMS's depth-area analysis; the job carries the 100 km2 base only.
3. Hybrid: the 18 dam catchments (S1 to S18) lumped with their reaches and the five reservoirs, each subbasin at its
   dam's area (``storm_area_km2`` of the subbasin), so each reservoir's outflow is the dam's at its own area; it enters
   the grid 200 m below its dam; the 86 plain subbasins lumped at 100 km2, each entering at its own wadi outlet; rain on
   the cells outside every polygon at 100 km2; no dam on the grid.
4. Hybrid, routing in 2D: every subbasin lumped and entering at its wadi outlet, no reach or reservoir routed; a
   subbasin draining to a dam at that dam's area, the rest and the rain on the grid at 100 km2; the five dams as crest
   lines and spillways on the grid, as run 1.
"""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import (  # noqa: E402
    BASIN,
    CACHE,
    CN,
    CONTROL,
    DAM_AREA_KM2,
    DAMS,
    DEM,
    DOMAIN_NO_RIM,
    DX,
    HMS_DIR,
    INPUTS,
    JOBS,
    MET,
    REPO,
    RESERVOIR,
    RUN_NAMES,
    RUN_TITLES,
    RUNS,
    SET,
    STORM_AREA_KM2,
    load_json,
    write_json,
)

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.hms import load_basin  # noqa: E402

MANNING_PLAIN = 0.04
CN_FALLBACK = 88.0
"""W1's value, for the 0.4 % of cells where his CN raster holds no data (the coast strip): the run refuses them otherwise."""
SIDE_KM2 = 0.95
SIDE_SLOPE = 0.005
SIDE_HALF_M = 250.0
"""A stream of 1 km2 or more that leaves through the domain's side, away from the sea (the first try of run 1 found
Wadi Fizh's southern branch, 274.7 km2, leaving 2 km inland through Basin 3's south-east edge): the edge there is
opened as a `normal` line 500 m long at 0.005 [Guessing: the fan's slope, not measured], so it is not dammed. The limit
was 1 km2; the north edge's 1.01 km2 stream at (439069, 2740618) reads 0.997 km2 on the outline without the rim, so the
limit is 0.95 to keep that outlet in both sets (no other crossing lies between 0.65 and 1.0 km2 in either). On the
outline without the rim the two 2 km2 streams at the south end near the sea no longer leave (they enter: 2.06 km2, and
leave as 0.5 km2 pieces), so the ``rerun2`` jobs have three side lines where the first set has five."""
NORTH = (432446.0, 2740899.0)
NORTH_SLOPE = 0.0057
"""His decision of 2026-11-14: the edge check's 276.65 km2 crossing of the north edge (Wadi HAT's main stem, HAT-R4,
where the outline runs on a 107 to 110 m terrace beside the bed and the HDSM ends just outside) gets a `normal` line
too, at the ground's slope along HAT-R4 over 2 km either side (0.0057 on the 5 m DEM; HMS's reach slope 0.0063)."""
NORTH_REACH_M = 150.0
"""The crossing is looked for this near the point: the outline without the rim lies 40 m inside the first one."""
SUGGEST = RUNS / "inputs" / "suggest" / "suggested_breaklines.gpkg"
"""The Suggest breaklines file of this domain (``wadi2d breaklines`` on run 1's job, the 1 km2 streams as W45 and W46
made it for Block 2 at 30 m): its thalwegs are the centre generator's guide lines."""


def domain_file(inputs: dict) -> str:
    """The first rerun's domain is Basin 3's polygons + 40 m: its 2-cell rim lies outside every subbasin polygon, so
    runs 3 and 4 rained on it (6.2 km2 round the outline, 1.1 Mm3 of excess running into the hills from the edge; his
    finding of 2026-11-15). The ``rerun2`` set takes the domain without the rim (s16_domain_no_rim.py)."""
    return inputs["domain"] if SET == "rerun" else str(DOMAIN_NO_RIM)


def base() -> dict:
    out = RUNS / "inputs" / "hms_import_basin3_200yr.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    exe = REPO / ".venv" / "Scripts" / "wadi2d.exe"
    subprocess.run([str(exe), "hms-import", str(HMS_DIR), "--basin", BASIN, "--met", MET, "--control", CONTROL,
                    "--out", str(out)], check=True, capture_output=True)
    return load_json(out)


def objects(inputs: dict) -> list[dict]:
    out = []
    for name in DAMS:
        d = inputs["dams"][name]
        for i, line in enumerate(d["crest_lines"]):
            out.append({"kind": "crest_line", "name": name if i == 0 else f"{name} part {i + 1}",
                        "coordinates": line, "z_constant": d["crest"]})
        for i, s in enumerate(d["spillways"]):
            out.append({"kind": "spillway", "name": f"{name} spillway" + ("" if len(d["spillways"]) == 1 else f" {i + 1}"),
                        "coordinates": s["coordinates"], "z_constant": d["fsl"], "coefficient": d["c"],
                        "length": round(s["length"], 2)})
    return out


def lines(inputs: dict) -> list[dict]:
    """W1's dam lines, and a line round each pool's upstream edge, clockwise, so flow into the pool reads positive."""
    out = [{"name": n, "coordinates": inputs["dams"][n]["axis"]} for n in DAMS]
    out += [{"name": f"{n} inflow", "coordinates": inputs["dams"][n]["ring"]} for n in DAMS]
    return out


def common(job: dict, inputs: dict, number: int) -> dict:
    job = copy.deepcopy(job)
    job["project"] = {"name": RUN_NAMES[number], "description": f"W79 Block 2 four ways: {RUN_TITLES[number]}"}
    job["storm"]["storm_area_km2"] = STORM_AREA_KM2
    job["storm"]["arf"]["table_type"] = (
        "ARF FM of his HMS project, read at one storm area of 100 km2 (his choice of 2026-11-15); his met file names 300 km2"
    )
    job["grid"] = {"dx": DX, "domain": domain_file(inputs), "cache_dir": str(CACHE)}
    job["terrain"].update({"dem": str(DEM), "pixel_stride": 1, "manning": MANNING_PLAIN,
                           "manning_raster": inputs["manning_raster"], "cn_raster": str(CN), "objects": []})
    job["boundaries"] = [{"kind": "normal", "slope": inputs["sea_slope"], "coordinates": c} for c in inputs["sea"]]
    job["boundaries"] += inputs.get("sides", [])
    job["hydrology"]["curve_number"] = CN_FALLBACK
    job["outputs"].update({"map_every_s": 900.0, "series_every_s": 60.0, "live_every_s": 0.0, "lines": lines(inputs)})
    job["outputs"]["pixels"]["enabled"] = True
    job["outputs"]["smooth"]["enabled"] = False
    job["run"].update({"backend": "gpu", "checkpoint_every_s": 0.0})
    job["dam_levels"] = []
    return job


def run1(job: dict, inputs: dict) -> dict:
    job = common(job, inputs, 1)
    h = job["hydrology"]
    for key in ("hms_basin", "hms_project", "hms_sqlite"):
        h[key] = None
    h["subbasins"] = []
    job["terrain"]["objects"] = objects(inputs)
    return job


def run2(job: dict, inputs: dict) -> dict:
    job = common(job, inputs, 2)
    job["outputs"]["lines"] = []
    return job


def reaches_dam(name: str) -> str | None:
    """The dam a subbasin drains to through Basin 3's network, or None for a subbasin below every dam."""
    downstream = {e.name: e.downstream for e in load_basin(HMS_DIR / BASIN).elements}
    seen = name
    while seen in downstream and downstream[seen]:
        seen = downstream[seen]
        for dam, res in RESERVOIR.items():
            if seen == res:
                return dam
    return None


def dam_areas(job: dict) -> dict[str, list[str]]:
    """Every subbasin draining to a dam reads the ARF at that dam's area (his rule of 2026-11-15, HMS's depth-area way);
    the rest keep the storm's 100 km2."""
    above: dict[str, list[str]] = {}
    for s in job["hydrology"]["subbasins"]:
        dam = reaches_dam(s["name"])
        if dam is not None:
            above.setdefault(dam, []).append(s["name"])
            s["storm_area_km2"] = DAM_AREA_KM2[dam]
    return above


def run3(job: dict, inputs: dict) -> dict:
    job = common(job, inputs, 3)
    above = dam_areas(job)
    for s in job["hydrology"]["subbasins"]:
        if s.get("storm_area_km2") is not None:
            s["outlet"] = None  # carried by its reservoir's inflow
    job["hydrology"]["inflows"] = [
        {"name": f"{dam} outflow", "x": inputs["dams"][dam]["entry"][0], "y": inputs["dams"][dam]["entry"][1],
         "element": RESERVOIR[dam], "entry": "point"}
        for dam in DAMS
    ]
    print("run 3, subbasins carried by each reservoir:", {k: sorted(v) for k, v in above.items()})
    return job


def run4(job: dict, inputs: dict) -> dict:
    job = common(job, inputs, 4)
    job["terrain"]["objects"] = objects(inputs)
    above = dam_areas(job)
    print("run 4, subbasins at each dam's area:", {k: sorted(v) for k, v in above.items()})
    return job


STRIP_STRIDE = 1
"""The 0.5 m pixel. The first attempt ran at every second pixel (1 m), because the strip's table builder read the DEM
over the bounding box of every aligned cell at once (66.5 GiB at 0.5 m, exit 7); W81 reads it in pieces (13.4 GB peak)."""


def aligned(job: dict) -> dict:
    """His decision of 2026-11-14: the aligned centre mesh at 20 m (W46) in place of plain squares."""
    job["strips"] = {"enabled": True, "generator": "centres", "banks": str(SUGGEST)}
    job["terrain"]["pixel_stride"] = STRIP_STRIDE
    return job


def suggest(job: dict) -> None:
    """The Suggest file of this domain, made once from run 1's job (the engine's own command, as the dock's button)."""
    if SUGGEST.is_file():
        return
    probe = write_json(RUNS / "inputs" / "suggest_job.json", job)
    exe = REPO / ".venv" / "Scripts" / "wadi2d.exe"
    subprocess.run([str(exe), "breaklines", str(probe), "--out", str(SUGGEST.parent)], check=True)


def side_outlets(b: dict, inputs: dict) -> list[dict]:
    """The engine's own edge check (W78) on the domain with the sea line only; each side crossing becomes an outlet."""
    import rasterio
    import shapely

    from wadi2d.edge_valleys import LEAVES, stream_crossings

    probe = common(b, {**inputs, "sides": []}, 1)
    probe["hydrology"].update({"hms_basin": None, "hms_project": None, "hms_sqlite": None, "subbasins": []})
    cfg = RunConfig.model_validate(probe)
    with rasterio.open(DEM) as src:
        crs = src.crs.to_wkt()
    dom = shapely.geometry.shape(load_json(Path(domain_file(inputs)))["features"][0]["geometry"])
    out = []
    for c in stream_crossings(cfg, crs, CACHE):
        north = c.kind == LEAVES and abs(c.x - NORTH[0]) < NORTH_REACH_M and abs(c.y - NORTH[1]) < NORTH_REACH_M
        if not north and (c.kind != LEAVES or c.area_km2 < SIDE_KM2 or c.no_ground):
            print("left closed:", c)
            continue
        piece = dom.exterior.intersection(shapely.Point(c.x, c.y).buffer(SIDE_HALF_M))
        piece = shapely.line_merge(piece) if piece.geom_type == "MultiLineString" else piece
        piece = max(piece.geoms, key=lambda g: g.length) if hasattr(piece, "geoms") else piece
        print(f"side outlet at {c.x:.0f}, {c.y:.0f}: {c.area_km2:.2f} km2, {piece.length:.0f} m")
        slope = NORTH_SLOPE if north else SIDE_SLOPE
        out.append({"kind": "normal", "slope": slope, "coordinates": [list(map(float, q)) for q in piece.coords]})
    return out


def main() -> None:
    inputs = load_json(INPUTS / "inputs.json")
    b = base()
    inputs["sides"] = side_outlets(b, inputs)
    suggest(run1(b, inputs))
    for number, make in ((1, run1), (2, run2), (3, run3), (4, run4)):
        job = make(b, inputs)
        if number != 2:
            job = aligned(job)
        RunConfig.model_validate(job)
        path = write_json(JOBS / f"{RUN_NAMES[number]}.json", job)
        print("wrote", path.name, "subbasins", len(job["hydrology"]["subbasins"]),
              "lumped with outlet", sum(1 for s in job["hydrology"]["subbasins"] if s.get("outlet")),
              "inflows", len(job["hydrology"].get("inflows", [])), "objects", len(job["terrain"]["objects"]))


if __name__ == "__main__":
    main()
