"""W71: a breach of Bidah's dam on real ground, the pool full to the 100 m spillway crest, on 20 m squares, the 20 m
centre mesh and the quadtree (20 m finest).

The dam, the spillway, the domain, the DEM and the two normal boundaries are the validation job's
(`W1 .../validation/block2_full/jobs/dam_Bidah03_100yr_20.json`, as W34 used them); the storm and the inflow are left out,
so the only water is the pool. The main crest piece carries the name the breach and the pool start read; the two short
pieces keep their crest at 105 m and are walls here.

Breach: time trigger at 600 s, centre 620 m along the main piece (the flat floor, 85.1 to 85.5 m, clear of the spillway
at 428 to 500 m), bottom 85.0 m (never below the ground), width, side slopes and formation time by Froehlich (2008) from
the pool's volume when the breach starts. Run 3 h.

Usage: python bidah_breach.py <mesh> [backend]   mesh: squares_levels | squares | centres | quadtree | all
(squares_levels: the pool by dam_levels; the others start from its cells as an initial_levels polygon)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

SOURCE = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\jobs\dam_Bidah03_100yr_20.json")
POOL_Z, CENTRE_S, BOTTOM_Z = 100.0, 620.0, 85.0
TRIGGER_S, DURATION_S = 600.0, 10800.0
POOL_M3 = 5_632_675.0
"""The grid pool at 100 m on this DEM, 2,202 cells of 20 m, as the first squares run reported it. W34's 3.833 Mm3 was
the same pool on the GGC 5 m DEM, which stands 2.39 m above the NSA datum of the dam levels (Block 2 finding)."""


def below_line(main: list) -> list:
    """The main piece's first segment moved 300 m downstream (north-east), as a result line across the valley."""
    (x0, y0), (x1, y1) = main[0], main[1]
    d = np.array([x1 - x0, y1 - y0]) / np.hypot(x1 - x0, y1 - y0)
    n = np.array([-d[1], d[0]])  # left of the line's direction: north-east here
    return [tuple(np.array(p) + 300.0 * n) for p in ((x0, y0), (x1, y1))]


POOL_FILE = HERE / "bidah_pool_100m.geojson"


def pool_polygon() -> list:
    """The grid pool of ``dam_levels`` at 100 m on the 20 m squares, as one polygon of its cells. ``dam_levels`` fills a
    grid pool on the uniform grid only, so every mesh starts from this polygon through ``initial_levels`` (W69 did the
    same on the synthetic valley); the squares run with ``dam_levels`` itself is the check that the two agree."""
    if POOL_FILE.exists():
        return json.loads(POOL_FILE.read_text(encoding="utf-8"))["coordinates"]
    import rasterio.features
    import shapely
    from affine import Affine

    from wadi2d.dam_levels import grid_pool_depth
    from wadi2d.run import prepare_grid

    cfg = job("squares", "cpu", HERE / "runs" / "pool", pool="levels")
    tables, _crs = prepare_grid(cfg, HERE / "runs" / "cache")
    g = tables.grid
    from wadi2d.run import boundary_set, open_lines, sink_lines

    lines = [*open_lines(cfg.boundaries), *sink_lines(cfg.hydrology.handbacks)]
    depth, notes = grid_pool_depth(cfg, tables, boundary_set(lines, tables, cfg.grid.line_samples).mask, {})
    print(notes)
    wet = (depth > 0.0).astype(np.uint8)
    shapes = [shapely.geometry.shape(s) for s, v in rasterio.features.shapes(wet, mask=wet > 0, transform=Affine(g.dx, 0, g.x0, 0, -g.dx, g.y0)) if v]
    poly = max(shapely.unary_union(shapes).geoms if hasattr(shapely.unary_union(shapes), "geoms") else [shapely.unary_union(shapes)], key=lambda p: p.area)
    ring = [tuple(map(float, c)) for c in poly.exterior.coords[:-1]]
    POOL_FILE.write_text(json.dumps({"type": "Polygon", "coordinates": ring, "cells": int(wet.sum())}), encoding="utf-8")
    return ring


def job(mesh: str, backend: str, out: Path, pool: str = "polygon") -> RunConfig:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    objects = data["terrain"]["objects"]
    names = ["Bidah main", "Bidah west", "Bidah north"]
    for o, name in zip([o for o in objects if o["kind"] == "crest_line"], names, strict=True):
        o["name"] = name
    main = objects[0]["coordinates"]
    data["project"] = {"name": f"W71 Bidah breach {mesh}", "description": "Bidah dam, pool at 100 m, breach at 600 s"}
    data["grid"]["cache_dir"] = str(HERE / "runs" / "cache")
    data.pop("hydrology", None)
    if pool == "levels":
        data["dam_levels"] = [{"name": "Bidah main", "start": POOL_Z}]
    else:
        data["initial_levels"] = [{"coordinates": pool_polygon(), "level": POOL_Z}]
    data["breaches"] = [{
        "dam": "Bidah main", "station_m": CENTRE_S, "bottom_z": BOTTOM_Z, "trigger": "time", "trigger_time_s": TRIGGER_S,
        "update_s": 5.0, "estimator": {"method": "froehlich_2008", "pool_volume_m3": POOL_M3},
    }]  # fmt: skip
    data["outputs"] = {
        "map_every_s": 0.0, "live_every_s": 0.0, "series_every_s": 30.0,
        "lines": [
            {"name": "axis", "coordinates": main[:2]},
            {"name": "below", "coordinates": below_line(main)},
        ],
        "points": [{"name": "pool", "x": 438300.0, "y": 2726860.0}, {"name": "tail", "x": 438700.0, "y": 2727060.0}],
    }  # fmt: skip
    data["run"] = {"duration_s": DURATION_S, "backend": backend, "source_every_s": 30.0, "checkpoint_every_s": 0.0}
    if mesh == "centres":
        data["strips"] = {"enabled": True, "generator": "centres"}
    elif mesh == "quadtree":
        data["mesh"] = {"enabled": True, "coarse_dx": 80.0}
    cfg = RunConfig.model_validate(data)
    out.mkdir(parents=True, exist_ok=True)
    (out / "w71_job.json").write_text(cfg.model_dump_json(indent=1), encoding="utf-8")
    return cfg


def series(path: Path) -> np.ndarray:
    return np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)


def froehlich_1995_peak(volume: float, depth: float) -> float:
    """Froehlich (1995b), Q_p = 0.607 V_w^0.295 h_w^1.24 (HEC TD-39), m3/s."""
    return 0.607 * volume**0.295 * depth**1.24


def one(mesh: str, backend: str) -> dict:
    out = HERE / "runs" / mesh
    base, _, how = mesh.partition("_")
    cfg = job(base, backend, out, pool="levels" if how == "levels" else "polygon")
    t0 = time.perf_counter()
    s = run_job(cfg, out)
    wall = time.perf_counter() - t0
    row = {"mesh": mesh, "exit": s.exit_code, "message": s.message, "wall_s": round(wall, 1), "backend": s.backend}
    if s.exit_code != 0:
        return row
    b = series(out / "series" / "breach_Bidah main.csv")
    axis = series(out / "series" / "line_axis.csv")
    below = series(out / "series" / "line_below.csv")
    pool = series(out / "series" / "point_pool.csv")
    formed = b[b[:, 1] >= 1.0 - 1e-12]
    k = int(np.argmax(np.abs(axis[:, 1])))
    j = int(np.argmax(np.abs(below[:, 1])))
    pool0 = float(b[0, 5])
    row.update(
        storage0_m3=round(s.balance.storage0, 0),
        storage_end_m3=round(s.balance.storage, 0),
        outflow_m3=round(s.balance.outflow, 0),
        balance_rel=s.balance.relative,
        start_s=float(b[0, 0]),
        formed_s=float(formed[0, 0]) if formed.size else None,
        bottom_width_m=float(b[-1, 3]),
        pool_start_m=round(pool0, 3),
        pool_at_formed_m=round(float(b[-1, 5]), 3),
        pool_point_end_m=round(float(pool[-1, 3]), 3),
        pool_point_1h_after_m=round(float(np.interp(TRIGGER_S + 3600.0, pool[:, 0], pool[:, 3])), 3),
        peak_axis_m3s=round(float(abs(axis[k, 1])), 1),
        t_peak_axis_s=float(axis[k, 0]),
        peak_below_m3s=round(float(abs(below[j, 1])), 1),
        t_peak_below_s=float(below[j, 0]),
        froehlich_1995_m3s=round(froehlich_1995_peak(s.balance.storage0, pool0 - BOTTOM_Z), 0),
    )
    return row


def main() -> None:
    meshes = ["squares_levels", "squares", "centres", "quadtree"] if sys.argv[1] == "all" else [sys.argv[1]]
    backend = sys.argv[2] if len(sys.argv) > 2 else "gpu"
    rows = []
    for mesh in meshes:
        row = one(mesh, backend)
        print(json.dumps(row), flush=True)
        rows.append(row)
        path = HERE / f"bidah_{mesh}.json"
        path.write_text(json.dumps(row, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
