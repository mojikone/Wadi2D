"""Write one configuration of the case: the RAS text project and the Wadi2D job, from one source of inputs.

usage: build_case.py NAME [--cores 8] [--map 1MIN]        NAME is a key of case.CONFIGS
"""

from __future__ import annotations

import argparse
import json

import numpy as np

import case
import ras_text

FOLDER = case.HERE


def hyetograph() -> tuple[np.ndarray, np.ndarray]:
    """End of step in minutes, depth in mm, 24 h on 5 min steps."""
    a = np.loadtxt(FOLDER / "excess_5min.csv", delimiter=",", skiprows=1)
    return a[:, 0], a[:, 1]


def ras_rain(step_end: np.ndarray, mm: np.ndarray) -> np.ndarray:
    """Period-ending table for RAS: element k is the depth of the step ending at k x 5 min; to the end of the run."""
    n = round(case.DURATION_H * 60 / 5.0) + 1
    out = np.zeros(n)
    out[np.round(step_end / 5.0).astype(int)] = mm
    return out


def seeds_of(dx: float) -> np.ndarray:
    m = np.load(FOLDER / "mask_20m.npy")
    k = round(case.COARSE / dx)
    fine = np.repeat(np.repeat(m, k, axis=0), k, axis=1)
    j, i = np.nonzero(fine)
    return np.column_stack((case.X0 + (i + 0.5) * dx, case.Y0 - (j + 0.5) * dx))


def ras_project(name: str, cfg: dict, cores: int, map_interval: str) -> None:
    per = json.loads((FOLDER / "perimeter.json").read_text(encoding="utf-8"))
    step_end, mm = hyetograph()
    p = ras_text.Project(
        name="Bidah", title=f"Bidah rain on grid {name}", perimeter=np.array(per["ring"]), seeds=seeds_of(cfg["dx"]),
        dx=cfg["dx"], manning=cfg["n"], rain_interval="5MIN", rain_mm=ras_rain(step_end, mm),
        duration_h=case.DURATION_H, equation=cfg["equation"], cores=cores, step="10SEC", map_interval=map_interval,
        bc_lines={"OutEast": np.array(per["east_outlet"]), "OutNorth": np.array(per["north_outlet"])},
        slope_out=case.SLOPE_OUT,
    )  # fmt: skip
    ras_text.write(p, FOLDER / f"ras_{name}")


def wadi_job(name: str, cfg: dict) -> None:
    """``cfg`` may carry ``numerics``, passed to the job as it stands."""
    dx = cfg["dx"]
    step_end, mm = hyetograph()
    total = float(mm.sum())
    cum = np.concatenate(([0.0], np.cumsum(mm)))
    times = np.concatenate(([0.0], step_end))
    h = 0.5 * dx
    job = {
        "project": {"name": f"ras_rog_{name}", "description": "Rain-on-grid head-to-head, same case as the RAS project"},
        "grid": {"dx": dx, "domain": str(FOLDER / f"domain_wadi_{dx:g}m.geojson"), "cache_dir": str(FOLDER / "cache")},
        "terrain": {"dem": str(case.DEM), "pixel_stride": 1, "manning": cfg["n"]},
        "storm": {
            "kind": "hypothetical", "depth_mm": total, "duration_min": float(times[-1]),
            "time_percent": (100.0 * times / times[-1]).tolist(), "depth_percent": (100.0 * cum / total).tolist(),
        },
        "boundaries": [
            {"kind": "normal", "slope": case.SLOPE_OUT,
             "coordinates": [[case.BOX_EAST + h, case.BOX_SOUTH + h], [case.BOX_EAST + h, case.Y0 - h]]},
            {"kind": "normal", "slope": case.SLOPE_OUT,
             "coordinates": [[case.BOX_WEST + h, case.Y0 + h], [case.BOX_EAST - h, case.Y0 + h]]},
        ],
        "outputs": {
            "map_every_s": 300.0, "series_every_s": case.SERIES_S, "live_every_s": 0.0,
            "lines": [{"name": k, "coordinates": v} for k, v in case.SECTIONS.items()],
        },
        "run": {"duration_s": case.DURATION_H * 3600.0, "backend": "gpu", "source_every_s": 30.0,
                "checkpoint_every_s": 0.0},
    }  # fmt: skip
    if "numerics" in cfg:
        job["numerics"] = cfg["numerics"]
    (FOLDER / "jobs").mkdir(exist_ok=True)
    (FOLDER / "jobs" / f"{name}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--cores", type=int, default=8)
    ap.add_argument("--map", default="1MIN")
    ap.add_argument("--wadi-only", action="store_true", help="a sensitivity job of case.WADI_VARIANTS, no RAS project")
    a = ap.parse_args()
    if a.wadi_only:
        cfg = case.WADI_VARIANTS[a.name]
        wadi_job(a.name, cfg)
    else:
        cfg = case.CONFIGS[a.name]
        wadi_job(a.name, cfg)
        ras_project(a.name, cfg, a.cores, a.map)
    print("written", a.name)


if __name__ == "__main__":
    main()
