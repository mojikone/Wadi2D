"""The owner's 24 gridded design storms as the engine reads them: 12 NetCDF files and their 12 DSS twins.

usage: inventory.py OUT.json [NAME ...]      (venv python, PYTHONPATH on this checkout; NAME as RP200 or PMP)

For every file: the grid, its coordinate system, the time axis, the units as the file states them, and the depth of the
whole event over each of the 18 HMS subbasins of Block 2 (Basin 1), over the Bidah 03 test domain and over the Block 2
domain. A polygon's depth is the mean of the pixels under it, each weighted by the area it shares with the polygon:
the engine's own rule for a lumped subbasin (``GriddedStorm.over``). The files are read in place and never written:
the DSS reader works on a scratch copy.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pyproj
import shapely

from wadi2d.hms import load_basin
from wadi2d.hms import sqlite as hms_sqlite
from wadi2d.hms.dss import open_dss
from wadi2d.io.rain import read_rain
from wadi2d.io.rain.netcdf import _pick, rain_variables  # noqa: F401  the reader's own choice of variable
from wadi2d.io.rain.netcdf_file import open_netcdf
from wadi2d.storm.gridded import GriddedStorm, _moved_polygon, pixel_shares
from wadi2d.storm.rain_frames import RainSpec
from wadi2d.terrain.vector import read_features

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
GRID = BLOCK / "Grid"
HMS = BLOCK / "HEC_HMS_Block_02"
VALIDATION = REPO / "W1 research and design note" / "validation" / "block2_full"
NAMES = ("RP5", "RP10", "RP25", "RP50", "RP100", "RP200", "RP500", "RP1000", "RP2000", "RP5000", "RP10000", "PMP")
DOMAINS = {"Bidah 03 domain": VALIDATION / "domain_Bidah03.geojson", "Block 2 domain": VALIDATION / "domain.geojson"}
UTM = "EPSG:32640"
DAMS = {"Bidah 03": ["S13"]}


def files(name: str) -> dict[str, Path]:
    return {
        "nc": GRID / "netCDF" / f"Precipitation_{name}_10min.nc",
        "dss": GRID / "DSS" / f"Precipitation_{name}_10min.dss",
    }


def stated(path: Path) -> dict:
    """What the file says about itself, before any conversion: the variable or series, and its units."""
    if path.suffix == ".nc":
        with open_netcdf(path) as variables:
            v = _pick(variables, None, path.name)
            return {"series": v.name, "units": str(v.attrs.get("units", "")), "dims": list(v.dims)}
    with open_dss(path) as dss:
        names = dss.grid_pathnames()
        first = dss.read_grid(sorted(names, key=str)[0])
        return {
            "series": f"{names[0].b}/{names[0].c}/{names[0].f}", "units": first.units, "records": len(names),
            "grid_type": first.grid_type, "a_part": names[0].a,
        }  # fmt: skip


def weighted(frames, polygon, crs: str) -> dict:
    moved = _moved_polygon(polygon, crs, frames.crs)
    pixels, areas, covered = pixel_shares(frames, moved)
    totals = frames.totals().ravel()[pixels]
    return {"mean_mm": float(totals @ (areas / areas.sum())), "pixels": int(pixels.size), "covered": covered}


def read(path: Path, polygons: dict, sub_crs: str, domains: dict) -> dict:
    t0 = time.monotonic()
    frames = read_rain(path, RainSpec())
    seconds = time.monotonic() - t0
    totals = frames.totals()
    periods = frames.ends_min - frames.starts_min
    crs = pyproj.CRS.from_user_input(frames.crs) if frames.crs else None
    storm = GriddedStorm(frames).bind(polygons, sub_crs)
    out = {
        "file": path.name, "bytes": path.stat().st_size, "read_s": round(seconds, 2), **stated(path),
        "frames": frames.count, "period_min": [float(periods.min()), float(periods.max())],
        "start": str(frames.origin), "duration_min": float(frames.ends_min[-1] - frames.starts_min[0]),
        "gaps": bool(np.any(frames.starts_min[1:] > frames.ends_min[:-1])),
        "rows": frames.rows, "columns": frames.columns, "pixel_m": [frames.dx, frames.dy],
        "west": frames.west, "north": frames.north, "crs": crs.name if crs else "", "epsg": crs.to_epsg() if crs else None,
        "missing_share": frames.missing_share(), "cumulative": frames.looks_cumulative(),
        "grid_mean_mm": float(np.nanmean(totals)), "grid_max_mm": float(np.nanmax(totals)),
        "frame_max_mm": float(np.nanmax(frames.depths)), "negative": int(np.count_nonzero(frames.depths < 0.0)),
        "subbasins_mm": {name: float(storm.over(name).total_depth) for name in polygons},
        "domains": {name: weighted(frames, polygon, UTM) for name, polygon in domains.items()},
    }  # fmt: skip
    return out


def main() -> None:
    target = Path(sys.argv[1])
    names = sys.argv[2:] or NAMES
    basin = load_basin(HMS / "Basin_1.basin")
    sub_crs = basin.spatial.coordinate_system if basin.spatial is not None else UTM
    rows = {row.name: row for row in hms_sqlite.subbasin_polygons(HMS / "Basin_1.sqlite")}
    polygons = {name: rows[name].shape() for name in basin.subbasins}
    areas = {name: float(element.area) for name, element in basin.subbasins.items()}
    domains = {name: shapely.union_all([s for _p, s in read_features(path, UTM)]) for name, path in DOMAINS.items()}
    found = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}
    found.update(subbasin_areas_km2=areas, subbasin_crs=str(sub_crs)[:60])
    found.setdefault("storms", {})
    for name in names:
        entry = found["storms"].setdefault(name, {})
        for key, path in files(name).items():
            try:
                entry[key] = read(path, polygons, sub_crs or UTM, domains)
                e = entry[key]
                print(f"{name} {key}: {e['frames']} frames, {e['columns']} x {e['rows']}, S13 {e['subbasins_mm']['S13']:.2f} mm, {e['read_s']} s", flush=True)
            except Exception as problem:  # the table says which file did not read, and why
                entry[key] = {"file": path.name, "error": f"{type(problem).__name__}: {problem}"}
                print(f"{name} {key}: FAILED {problem}", flush=True)
        if "error" not in entry["nc"] and "error" not in entry["dss"]:
            nc, dss = entry["nc"], entry["dss"]
            total = sum(areas.values())
            entry["dss_over_nc"] = {
                "S13": dss["subbasins_mm"]["S13"] / nc["subbasins_mm"]["S13"] - 1.0,
                "subbasins_worst": max(
                    (abs(dss["subbasins_mm"][n] / nc["subbasins_mm"][n] - 1.0) for n in areas), default=0.0
                ),
                "basin_mean": sum(dss["subbasins_mm"][n] * areas[n] for n in areas)
                / sum(nc["subbasins_mm"][n] * areas[n] for n in areas)
                - 1.0,
                **{
                    name: dss["domains"][name]["mean_mm"] / nc["domains"][name]["mean_mm"] - 1.0
                    for name in DOMAINS
                },
            }
            entry["basin_mean_mm"] = {
                key: sum(entry[key]["subbasins_mm"][n] * areas[n] for n in areas) / total for key in ("nc", "dss")
            }
        target.write_text(json.dumps(found, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
