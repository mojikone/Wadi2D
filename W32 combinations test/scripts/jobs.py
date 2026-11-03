"""Jobs on a generated Bidah basin, shared by items 2 to 6: generation, the subbasins above the dam, the lines."""

from __future__ import annotations

import json
import math
from pathlib import Path

import common as c

RESERVOIR = "Bidah 03"
POOL = {"name": "pool", "x": 438300.0, "y": 2726860.0}
"""W1's pool point behind the dam."""


def _shifted(line: list[list[float]], metres: float) -> list[list[float]]:
    """The axis moved square to itself; positive is towards the north-east, downstream of the dam."""
    (x0, y0), (x1, y1) = line
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy)
    nx, ny = -dy / n, dx / n  # the axis runs south-east, so this normal points north-east
    return [[x0 + metres * nx, y0 + metres * ny], [x1 + metres * nx, y1 + metres * ny]]


def _shifted_many(line: list[list[float]], metres: float) -> list[list[float]]:
    """A polyline moved square to the dam axis by ``metres``; positive is downstream (north-east)."""
    (x0, y0), (x1, y1) = c.AXIS
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy)
    nx, ny = -dy / n, dx / n
    return [[x + metres * nx, y + metres * ny] for x, y in line]


ABOVE = _shifted(c.AXIS, -250.0)
"""Across the valley 250 m upstream of the crest, above the pool and above the built hand-back line (3 cells)."""
BELOW = _shifted(c.AXIS, 150.0)
"""Across the valley 150 m downstream of the crest: what passes the spillway and the crest faces."""
LINES = [
    {"name": "Bidah 03", "coordinates": c.DAM_LINE},
    {"name": "axis", "coordinates": c.AXIS},
    {"name": "above", "coordinates": ABOVE},
    {"name": "below", "coordinates": BELOW},
]


def generate(scratch: Path, name: str, threshold: float = 2.0, lag: str = "nrcs", pixel: float | None = None, **settings) -> dict:
    """``wadi2d basin`` on the Bidah ground with the dam objects; returns the event with ``basin`` (basin.json) and the wall time."""
    job = c.bidah_job(f"gen_{name}", scratch / "cache", storm=c.design_storm(), hours=30.0)
    job["basin"] = {"stream_threshold_km2": threshold, "lag_method": lag, **settings}
    if pixel is not None:
        job["basin"]["analysis_pixel"] = pixel
    path = c.write(job, scratch / name / "gen.json")
    code, wall, text = c.engine("basin", str(path), "--out", str(scratch / name / "basin"), log=scratch / name / "basin.log")
    event = c.last_json(text)
    event.update({"exit": code, "wall_s": round(wall, 1)})
    return event


def model(basin_json: Path) -> dict:
    return json.loads(Path(basin_json).read_text(encoding="utf-8"))


def elements(basin_json: Path, kind: str | None = None) -> list[dict]:
    found = model(basin_json)["elements"]
    return [e for e in found if kind is None or e["kind"] == kind]


def upstream_subbasins(basin_json: Path, element: str) -> list[str]:
    """Every subbasin whose water reaches ``element`` through the network, the direct ones included."""
    by_name = {e["name"]: e for e in model(basin_json)["elements"]}
    found = []
    for e in by_name.values():
        if e["kind"] != "subbasin":
            continue
        down = e.get("downstream")
        seen = set()
        while down is not None and down not in seen:
            if down == element:
                found.append(e["name"])
                break
            seen.add(down)
            down = by_name.get(down, {}).get("downstream")
    return found


def summary(event: dict) -> str:
    counts = event.get("counts") or {k: event.get(k) for k in ("subbasins", "reaches", "junctions", "reservoirs")}
    return f"{counts}, notes {event.get('notes')}, {event.get('wall_s')} s"


def two_d_above_dam(name: str, basin_json: Path, cache: Path, dx: float = 20.0, hours: float = 36.0, **parts) -> dict:
    """The 100-yr storm; every subbasin above the reservoir as rain-on-grid, the rest lumped by default."""
    above = upstream_subbasins(basin_json, RESERVOIR)
    job = c.bidah_job(name, cache, dx=dx, hours=hours, storm=c.design_storm())
    job["hydrology"] = {"basin_json": str(basin_json), "time_step_min": 5.0, "subbasins": [{"name": n, "mode": "2d"} for n in above]}
    job["outputs"]["lines"] = LINES
    job["outputs"]["points"] = [POOL]
    for key, value in parts.items():
        if isinstance(value, dict) and isinstance(job.get(key), dict):
            job[key].update(value)
        else:
            job[key] = value
    return job


def lumped_default(name: str, basin_json: Path, cache: Path, dx: float = 20.0, hours: float = 30.0, two_d: list[str] = (), **parts) -> dict:
    job = c.bidah_job(name, cache, dx=dx, hours=hours, storm=c.design_storm())
    job["hydrology"] = {"basin_json": str(basin_json), "time_step_min": 5.0, "subbasins": [{"name": n, "mode": "2d"} for n in two_d]}
    job["outputs"]["lines"] = LINES
    job["outputs"]["points"] = [POOL]
    for key, value in parts.items():
        if isinstance(value, dict) and isinstance(job.get(key), dict):
            job[key].update(value)
        else:
            job[key] = value
    return job


def network_peaks(folder: Path, names: list[str]) -> dict:
    out = {}
    for n in names:
        safe = n.replace(" ", "_")
        path = Path(folder) / "series" / f"network_{safe}.csv"
        if path.exists():
            out[n] = {
                "inflow": c.peak(folder, f"network_{safe}", "inflow_m3s"),
                "outflow": c.peak(folder, f"network_{safe}", "outflow_m3s"),
                "outflow_m3": c.volume(folder, f"network_{safe}", "outflow_m3s"),
            }
    return out


def handback_peaks(folder: Path) -> dict:
    out = {}
    for f in sorted((Path(folder) / "series").glob("handback_*.csv")):
        out[f.stem[9:]] = {"crossed": c.peak(folder, f.stem, "inflow_m3s"), "crossed_m3": c.volume(folder, f.stem, "inflow_m3s")}
    return out


def read_run(folder: Path) -> dict:
    """Everything one run says that the items compare."""
    start, done = c.start_event(folder), c.done_event(folder)
    reservoirs = [e["name"] for e in elements_of_run(folder)]
    return {
        "exit": done.get("code"), "backend": start.get("backend"), "cells": start.get("cells"), "steps": done.get("steps"),
        "loop_s": done.get("loop_s"), "balance": done.get("balance", {}), "lines": c.line_peaks(folder),
        "network": network_peaks(folder, reservoirs), "handbacks": handback_peaks(folder),
        "warnings": c.warnings(folder), "basin_event": (c.events(folder, "basin") or [{}])[0],
    }  # fmt: skip


def elements_of_run(folder: Path) -> list[dict]:
    resolved = Path(folder) / "config.resolved.json"
    if not resolved.exists():
        return []
    cfg = json.loads(resolved.read_text(encoding="utf-8"))
    basin = cfg.get("hydrology", {}).get("basin_json")
    if not basin or not Path(basin).exists():
        return []
    return [e for e in elements(Path(basin)) if e["kind"] in ("reservoir", "junction", "reach")]
