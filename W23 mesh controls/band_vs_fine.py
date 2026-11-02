"""A refined band against a fully fine run: Bidah, rain on grid, the frozen W1 job, 10 m cells.

Rule, fixed before the first run: the peak at every line within 5 % of the fully fine run, the gate of W10 Stage C.

W3 section 8 is why this is not one number at one long line: a mesh with the wadi at 10 m and coarse slopes kept the total peak
and lost 18 % of the wadi peak, so a section across the whole valley flatters it. Here the job's two long lines stay, and short
sections across the main wadi alone are added. Streams are off in the band cases, so that the band is the line's own doing.

usage: python band_vs_fine.py SCRATCH_FOLDER [case ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import shapely

from wadi2d.config.schema import RunConfig
from wadi2d.mesh.streams import drainage_area, read_coarse
from wadi2d.run import domain_mask, grid_window, load_job, run_job
from wadi2d.terrain import RasterBed

MAIN = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\ras_rain_on_grid\jobs\10m_n050_em.json")
HERE = Path(__file__).parent
LINE_FILE = HERE / "wadi_line.geojson"
RULE = 0.05
ANALYSIS = 5.0
HEAD_M2 = 1.0e6
"""The main stem stops where it drains less than this."""
SECTIONS = (0.25, 0.5, 0.75)
"""Shares of the stem, from the outlet, that get a section across the wadi."""
SECTION_HALF = 120.0
SIMPLIFY = 15.0
NEIGHBOURS = [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]
BAND = {"near_dx": 10.0, "rows": 8, "far_dx": 40.0}
NO_STREAMS = {"stream_area_fine_km2": 1.0e6, "stream_area_mid_km2": 1.0e6}
MESH = {"enabled": True, "coarse_dx": 40.0}
SERIES_S = 60.0


def stem(cfg: RunConfig) -> list[tuple[float, float]]:
    """The main wadi: from the largest drainage area in the domain upstream by the largest neighbour."""
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        crs = bed.crs.to_wkt()
    factor = round(cfg.grid.dx / ANALYSIS)
    z = read_coarse(cfg.terrain.dem, window.x0, window.y0, window.ny, window.nx, cfg.grid.dx, factor)
    area = drainage_area(z, ANALYSIS, window.x0, window.y0, crs)
    inside = np.repeat(np.repeat(mask, factor, axis=0), factor, axis=1)
    where = area * inside
    j, i = np.unravel_index(int(where.argmax()), where.shape)
    path = [(int(j), int(i))]
    while where[j, i] >= HEAD_M2:
        best, step = 0.0, None
        for a, b in NEIGHBOURS:
            y, x = j + a, i + b
            if 0 <= y < where.shape[0] and 0 <= x < where.shape[1] and best < where[y, x] < where[j, i]:
                best, step = float(where[y, x]), (y, x)
        if step is None:
            break
        j, i = step
        path.append((int(j), int(i)))
    points = [(window.x0 + (b + 0.5) * ANALYSIS, window.y0 - (a + 0.5) * ANALYSIS) for a, b in path]
    return list(shapely.LineString(points).simplify(SIMPLIFY).coords)


def sections(line: list[tuple[float, float]]) -> dict[str, list[tuple[float, float]]]:
    """Short lines square to the stem, across the wadi alone."""
    stem_line = shapely.LineString(line)
    out = {}
    for share in SECTIONS:
        at = share * stem_line.length
        a = stem_line.interpolate(at - 20.0)
        b = stem_line.interpolate(at + 20.0)
        centre = stem_line.interpolate(at)
        along = np.array([b.x - a.x, b.y - a.y])
        across = np.array([-along[1], along[0]]) / np.hypot(*along) * SECTION_HALF
        out[f"wadi_{round(share * 100)}"] = [
            (centre.x - across[0], centre.y - across[1]),
            (centre.x + across[0], centre.y + across[1]),
        ]
    return out


def job_of(case: str, line: list[tuple[float, float]], cross: dict, folder: Path) -> RunConfig:
    data = load_job(MAIN).model_dump(mode="json")
    data["grid"]["cache_dir"] = str(folder / "cache")
    data["outputs"]["map_every_s"] = 0.0
    data["outputs"]["series_every_s"] = SERIES_S
    data["outputs"]["lines"] += [{"name": name, "coordinates": coords} for name, coords in cross.items()]
    if case != "fine":
        data["numerics"]["local_time_stepping"] = True
        data["mesh"] = {**data["mesh"], **MESH}
    if case == "band":
        data["mesh"].update(NO_STREAMS, lines=[{"name": "Wadi", "coordinates": line, **BAND}])
    elif case == "band_wide":
        data["mesh"].update(NO_STREAMS, lines=[{"name": "Wadi", "coordinates": line, **BAND, "rows": 40}])
    elif case == "band_all":  # the control: a band over the whole domain must come back to the fine run
        data["mesh"].update(NO_STREAMS, lines=[{"name": "Wadi", "coordinates": line, **BAND, "rows": 1000}])
    elif case == "rules_band":  # how a user would work: the default stream rules, and a band on top
        data["mesh"].update(lines=[{"name": "Wadi", "coordinates": line, **BAND}])
    elif case == "no_band":
        data["mesh"].update(NO_STREAMS)
    return RunConfig.model_validate(data)


def main() -> None:
    folder = Path(sys.argv[1])
    wanted = sys.argv[2:] or ["fine", "band", "band_wide", "band_all", "no_band", "rules", "rules_band"]
    base = load_job(MAIN)
    if LINE_FILE.exists():
        stored = json.loads(LINE_FILE.read_text(encoding="utf-8"))
        line = [tuple(p) for p in stored["features"][0]["geometry"]["coordinates"]]
        cross = {f["properties"]["name"]: [tuple(p) for p in f["geometry"]["coordinates"]] for f in stored["features"][1:]}
    else:
        line = stem(base)
        cross = sections(line)
        features = [{"type": "Feature", "properties": {"name": "Wadi"}, "geometry": {"type": "LineString", "coordinates": line}}]
        features += [
            {"type": "Feature", "properties": {"name": n}, "geometry": {"type": "LineString", "coordinates": c}}
            for n, c in cross.items()
        ]
        crs = {"type": "name", "properties": {"name": "EPSG:32640"}}
        LINE_FILE.write_text(json.dumps({"type": "FeatureCollection", "crs": crs, "features": features}), encoding="utf-8")
    print(f"stem {shapely.LineString(line).length:.0f} m, {len(line)} vertices, sections {list(cross)}")
    results = HERE / "band_vs_fine.json"
    done = json.loads(results.read_text(encoding="utf-8")) if results.exists() else {}
    for case in wanted:
        summary = run_job(job_of(case, line, cross, folder), folder / case)
        done[case] = {
            "status": summary.status,
            "message": summary.message[:200],
            "cells": summary.cells,
            "mass": summary.balance.relative,
            "peaks": {k: [round(v[0], 3), round(v[1], 0)] for k, v in summary.peaks.items()},
        }
        results.write_text(json.dumps(done, indent=1), encoding="utf-8")
        print(case, summary.status, summary.cells, flush=True)
    fine = done.get("fine")
    if fine:
        names = list(fine["peaks"])
        print("case".ljust(11) + "cells".rjust(9) + "".join(n.rjust(11) for n in names))
        print("fine".ljust(11) + f"{fine['cells']:>9}" + "".join(f"{fine['peaks'][n][0]:>11.1f}" for n in names))
        for case, row in done.items():
            if case != "fine":
                gaps = [row["peaks"][n][0] / fine["peaks"][n][0] - 1.0 for n in names]
                verdict = "pass" if max(abs(g) for g in gaps) <= RULE else "FAIL"
                print(case.ljust(11) + f"{row['cells']:>9}" + "".join(f"{g * 100:>10.2f}%" for g in gaps) + "  " + verdict)


if __name__ == "__main__":
    main()
