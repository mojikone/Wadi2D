"""Block 2 case of the hand-back: S1 and S2 in 2D, a line across the wadi a little way down R1, R1 lumped, back near J2.

Two runs of the same flood, nothing tuned:

- ``handback``: the line takes S1 and S2's flow into R1, HMS's own Muskingum-Cunge reach of 26 km, and its outflow
  comes back 300 m above R1's end, where the section J2 reads it.
- ``full2d``: no line; the same water runs the 26 km of R1 on the grid to the same section.

S3, the subbasin R1 runs through, is masked in both, so the difference is the reach and nothing else: a lumped S3 with
a table inflow of zeros under its own name. That is a device of this comparison, said here and in the README.

    python block2_case.py build <runs folder>     # writes the two jobs
    python block2_case.py run <runs folder> <name>
    python block2_case.py compare <runs folder>   # writes block2_case.json here
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import shapely
from shapely.geometry import mapping

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # this branch's wadi2d, not the editable install of the main checkout
sys.path.insert(
    0, str(HERE.parent / "W1 research and design note" / "validation" / "block2_full" / "scripts")
)
from common import CN, DEM, HMS, polygons, storm  # noqa: E402

from wadi2d.hms import sqlite as hms_sqlite  # noqa: E402
from wadi2d.hydrology.routing import MuskingumCunge  # noqa: E402

UP = ["S1", "S2"]
CORRIDOR = "S3"
LINE_AT_M = 400.0
"""Distance down R1 from its head where the line crosses the wadi."""
LINE_HALF_M = 700.0
BACK_ABOVE_END_M = 300.0
SECTION_ABOVE_END_M = 150.0
DX = 20.0
HOURS = 30.0
STEP_MIN = 5.0


def _cross(line: shapely.LineString, at: float, half: float) -> list[tuple[float, float]]:
    """A straight line through the point ``at`` metres along ``line``, square to it."""
    p = line.interpolate(at)
    q = line.interpolate(min(at + 20.0, line.length))
    dx, dy = q.x - p.x, q.y - p.y
    n = np.hypot(dx, dy)
    nx, ny = -dy / n, dx / n
    return [(p.x - half * nx, p.y - half * ny), (p.x + half * nx, p.y + half * ny)]


def geometry() -> dict:
    polys = polygons()
    (r1,) = hms_sqlite.reach_lines(HMS / "Basin_1.sqlite", ["R1"])
    reach = shapely.LineString(r1.shape().coords) if r1.shape().geom_type == "LineString" else r1.shape()
    if reach.geom_type == "MultiLineString":
        reach = shapely.line_merge(reach)
    up = shapely.union_all([polys[n] for n in UP])
    head = reach.interpolate(0.0)
    if head.distance(up) > reach.interpolate(reach.length).distance(up):
        reach = reach.reverse()
    domain = shapely.union_all([polys[n].buffer(40.0) for n in [*UP, CORRIDOR]]).buffer(0.0)
    end = reach.interpolate(reach.length)
    back = reach.interpolate(reach.length - BACK_ABOVE_END_M)
    return {
        "reach_km": reach.length / 1000.0,
        "domain": domain,
        "line": _cross(reach, LINE_AT_M, LINE_HALF_M),
        "back": (back.x, back.y),
        "section": _cross(reach, reach.length - SECTION_ABOVE_END_M, LINE_HALF_M),
        "at_line": _cross(reach, LINE_AT_M - 60.0, LINE_HALF_M),
        "outlet": _cross(reach, reach.length - 20.0, LINE_HALF_M),
        "up_km2": up.area / 1e6,
        "end": (end.x, end.y),
    }


def jobs(runs: Path) -> dict[str, dict]:
    g = geometry()
    runs.mkdir(parents=True, exist_ok=True)
    domain = runs / "domain.geojson"
    feature = {"type": "Feature", "properties": {"name": "S1 S2 S3"}, "geometry": mapping(g["domain"])}
    domain.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
    zero = {
        "name": CORRIDOR,
        "x": g["back"][0],
        "y": g["back"][1],
        "times_s": [0.0, HOURS * 3600.0],
        "flows": [0.0, 0.0],
    }
    base = {
        "project": {"name": "block2_handback", "description": "W25 Block 2 hand-back case"},
        "grid": {"dx": DX, "domain": str(domain), "cache_dir": str(runs / "cache")},
        "terrain": {"dem": str(DEM), "manning": 0.04, "cn_raster": str(CN)},
        "storm": storm(g["up_km2"]),
        "hydrology": {
            "curve_number": 88.0,
            "hms_basin": str(HMS / "Basin_1.basin"),
            "hms_sqlite": str(HMS / "Basin_1.sqlite"),
            "time_step_min": STEP_MIN,
            "subbasins": [{"name": CORRIDOR, "mode": "lumped"}],
            "inflows": [zero],
        },
        "boundaries": [{"kind": "normal", "slope": 0.01, "coordinates": g["outlet"]}],
        "outputs": {
            "map_every_s": 0.0, "series_every_s": 60.0, "live_every_s": 0.0, "pixels": {"enabled": False},
            "lines": [{"name": "J2", "coordinates": g["section"]}, {"name": "At line", "coordinates": g["at_line"]}],
        },
        "run": {"duration_s": HOURS * 3600.0, "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }  # fmt: skip
    handback = json.loads(json.dumps(base))
    handback["hydrology"]["handbacks"] = [{"name": "R1 head", "coordinates": g["line"], "element": "R1"}]
    handback["hydrology"]["inflows"].append(
        {"name": "R1 end", "x": g["back"][0], "y": g["back"][1], "element": "R1"}
    )
    out = {"handback": handback, "full2d": base}
    for name, data in out.items():
        (runs / f"{name}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    meta = {k: v for k, v in g.items() if k != "domain"}
    (runs / "geometry.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return out


def _series(out: Path, kind: str, name: str, column: str) -> tuple[np.ndarray, np.ndarray]:
    with h5py.File(out / "results.h5", "r") as f:
        g = f[f"series/{kind}/{name}"]
        return g["t_s"][()], g[column][()]


def _event(out: Path) -> dict:
    lines = (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(s) for s in lines if '"ev": "done"' in s or '"ev":"done"' in s][-1]


def compare(runs: Path) -> dict:
    hb, full = runs / "run_handback", runs / "run_full2d"
    report: dict = {"geometry": json.loads((runs / "geometry.json").read_text(encoding="utf-8"))}
    report["balance"] = _event(hb)["balance"]
    t, q_hb = _series(hb, "lines", "J2", "discharge_m3s")
    _t, q_full = _series(full, "lines", "J2", "discharge_m3s")
    q_hb, q_full = np.abs(q_hb), np.abs(q_full)
    _ta, at_full = _series(full, "lines", "At_line", "discharge_m3s")
    tk, crossed = _series(hb, "handbacks", "R1_head", "inflow_m3s")
    _tk, network = _series(hb, "network", "R1", "outflow_m3s")
    reach = MuskingumCunge(26008.98, 0.01241, 0.1, 60.0, 0.7, 1.524)
    by_hand = reach.route(crossed, STEP_MIN)
    dt = STEP_MIN * 60.0

    def peak(times, q):
        k = int(np.argmax(q))
        return {"peak_m3s": float(q[k]), "at_h": float(times[k] / 3600.0)}

    report["sections"] = {
        "crossed at the line, period means": {**peak(tk - dt / 2.0, crossed), "volume_m3": float(crossed.sum() * dt)},
        "2D at the line position, full 2D run": {**peak(_ta, np.abs(at_full)),
                                                 "volume_m3": float(np.trapezoid(np.abs(at_full), _ta))},
        "R1 lumped, as the network gave it": {**peak(tk, network), "volume_m3": float(network.sum() * dt)},
        "R1 routed by hand on the same inflow": {**peak(tk, by_hand), "volume_m3": float(by_hand.sum() * dt)},
        "J2, hand-back run": {**peak(t, q_hb), "volume_m3": float(np.trapezoid(q_hb, t))},
        "J2, full 2D run": {**peak(t, q_full), "volume_m3": float(np.trapezoid(q_full, t))},
    }  # fmt: skip
    report["network_equals_by_hand"] = float(np.abs(network - by_hand[: network.size]).max())
    (HERE / "block2_case.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    command, runs = sys.argv[1], Path(sys.argv[2])
    if command == "build":
        jobs(runs)
    elif command == "run":
        import wadi2d
        from wadi2d.run import load_job, run_job

        name = sys.argv[3]
        print("wadi2d from", wadi2d.__file__, flush=True)
        summary = run_job(load_job(runs / f"{name}.json"), runs / f"run_{name}")
        print(name, summary.exit_code, summary.message, summary.balance)
    else:
        print(json.dumps(compare(runs), indent=1))
