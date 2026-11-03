"""The smallest case that shows the ring flicker: one steady inflow into a V valley at 40 m, a closed ring whose edge
runs through the cells that take the inflow, and a straight line 1 km below it.

A steady inflow makes the reading plain: once the valley has filled, every line across it should read the inflow and
nothing else. Each case changes one thing against ``base``. Writes ``results.json`` and the series beside this file.

usage: python s01_smallest_case.py [case ...]   (no argument runs every case)
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tests.engine.conftest import X0, Y0, write_dem  # noqa: E402
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

PIXEL = 2.0
WIDTH, HEIGHT = 3200.0, 1200.0
YC = Y0 - HEIGHT / 2.0
FALL, SIDE = 0.01, 0.04
Q = 400.0
DURATION = 7200.0
SETTLED = 3600.0
"""The valley has filled by then: every line should read the inflow."""
X_IN = X0 + 600.0
"""A lattice corner at 40 m and at 20 m: four cells share it, each centre 28.3 m or 14.1 m away."""
SERIES = 5.0
MINUTE = 60.0


def valley(path: Path, side: float = SIDE, yc: float = YC, sill: float = 0.0) -> Path:
    """A V valley falling east; ``yc`` is its thalweg, on a lattice row by default, ``side`` its bank slope.

    ``sill`` raises the bed by that much over the cell two cells below the inflow, so the inflow cells pond behind
    it as the S5 outlet cells do behind their narrow exit.
    """
    nx, ny = int(WIDTH / PIXEL), int(HEIGHT / PIXEL)
    x = X0 + (np.arange(nx) + 0.5) * PIXEL
    y = Y0 - (np.arange(ny) + 0.5) * PIXEL
    z = 100.0 - FALL * (x[None, :] - X0) + side * np.abs(y[:, None] - yc)
    if sill:
        z[:, (x >= X_IN + 80.0) & (x < X_IN + 120.0)] += sill
    return write_dem(path, z, PIXEL)


def ring(x_east: float) -> list[tuple[float, float]]:
    """A closed rectangle whose east edge is the lattice column at ``x_east``."""
    west, south, north = X0 + 100.0, Y0 - HEIGHT + 100.0, Y0 - 100.0
    return [(west, north), (west, south), (x_east, south), (x_east, north), (west, north)]


def cross(x: float) -> list[tuple[float, float]]:
    return [(x, Y0 - 50.0), (x, Y0 - HEIGHT + 50.0)]


def job(
    dem: Path, out: Path, point: tuple[float, float], ring_x: float, dx: float = 40.0, **parts
) -> RunConfig:
    data = {
        "grid": {"dx": dx, "extent": (X0, Y0 - HEIGHT, X0 + WIDTH, Y0), "cache_dir": str(out.parent / f"cache_{dx:g}")},
        "terrain": {"dem": str(dem), "manning": 0.04},
        "run": {"backend": "cpu", "duration_s": DURATION, "checkpoint_every_s": 0.0},
        "numerics": {},
        "hydrology": {
            "inflows": [{"name": "in", "x": point[0], "y": point[1], "times_s": [0.0, 600.0, DURATION], "flows": [0.0, Q, Q]}]
        },
        "boundaries": [{"kind": "normal", "slope": FALL, "coordinates": [(X0 + WIDTH - 1.0, Y0), (X0 + WIDTH - 1.0, Y0 - HEIGHT)]}],
        "outputs": {
            "map_every_s": 0.0, "live_every_s": 0.0, "series_every_s": SERIES, "progress_every_s": 5.0,
            "lines": [{"name": "ring", "coordinates": ring(ring_x)}, {"name": "cross", "coordinates": cross(X_IN + 1000.0)}],
            "pixels": {"enabled": False},
        },
    }  # fmt: skip
    for key, value in parts.items():
        data[key] = {**data.get(key, {}), **value}
    return RunConfig.model_validate(data)


CASES: dict[str, dict] = {
    # the inflow point, the ring's east edge, and what else changes
    "base": {"point": (X_IN, YC), "ring_x": X_IN},
    "base_again": {"point": (X_IN, YC), "ring_x": X_IN},
    "base_gpu": {"point": (X_IN, YC), "ring_x": X_IN, "run": {"backend": "gpu"}},
    "two_cells": {"point": (X_IN, YC + 20.0), "ring_x": X_IN},
    "one_cell": {"point": (X_IN - 20.0, YC + 20.0), "ring_x": X_IN},
    "ring_below": {"point": (X_IN, YC), "ring_x": X_IN + 120.0},
    "refresh_10": {"point": (X_IN, YC), "ring_x": X_IN, "run": {"source_every_s": 10.0}},
    "refresh_60": {"point": (X_IN, YC), "ring_x": X_IN, "run": {"source_every_s": 60.0}},
    "refresh_120": {"point": (X_IN, YC), "ring_x": X_IN, "run": {"source_every_s": 120.0}},
    "lowest_only": {"point": (X_IN, YC), "ring_x": X_IN, "hydrology": {"inject_min_depth": 5.0}},
    "no_mirror": {"point": (X_IN, YC), "ring_x": X_IN, "numerics": {"mirror_dry_faces": False}},
    "dx20": {"point": (X_IN, YC), "ring_x": X_IN, "dx": 20.0},
    # the thalweg 10 m north of the corner: the north pair of cells is lower than the south pair
    "thalweg_off": {"point": (X_IN, YC), "ring_x": X_IN, "valley": {"yc": YC + 10.0}},
    "steep_bank": {"point": (X_IN, YC), "ring_x": X_IN, "valley": {"side": 0.10, "yc": YC + 10.0}},
    "steep_bank_lowest": {
        "point": (X_IN, YC),
        "ring_x": X_IN,
        "valley": {"side": 0.10, "yc": YC + 10.0},
        "hydrology": {"inject_min_depth": 5.0},
    },
    "steep_bank_refresh_10": {
        "point": (X_IN, YC),
        "ring_x": X_IN,
        "valley": {"side": 0.10, "yc": YC + 10.0},
        "run": {"source_every_s": 10.0},
    },
    # a gorge: 1:1 banks, so 400 m3/s runs about 9 m deep, as at the S5 outlet
    "gorge": {"point": (X_IN, YC), "ring_x": X_IN, "valley": {"side": 1.0, "yc": YC + 10.0}},
    "gorge_lowest": {
        "point": (X_IN, YC),
        "ring_x": X_IN,
        "valley": {"side": 1.0, "yc": YC + 10.0},
        "hydrology": {"inject_min_depth": 5.0},
    },
    "gorge_refresh_120": {
        "point": (X_IN, YC),
        "ring_x": X_IN,
        "valley": {"side": 1.0, "yc": YC + 10.0},
        "run": {"source_every_s": 120.0},
    },
    "gorge_cfl_half": {
        "point": (X_IN, YC),
        "ring_x": X_IN,
        "valley": {"side": 1.0, "yc": YC + 10.0},
        "numerics": {"cfl": 0.225},
    },
    "gorge_ring_below": {
        "point": (X_IN, YC),
        "ring_x": X_IN + 120.0,
        "valley": {"side": 1.0, "yc": YC + 10.0},
    },
    "gorge_dx20": {"point": (X_IN, YC), "ring_x": X_IN, "valley": {"side": 1.0, "yc": YC + 10.0}, "dx": 20.0},
    "gorge_gpu": {"point": (X_IN, YC), "ring_x": X_IN, "valley": {"side": 1.0, "yc": YC + 10.0}, "run": {"backend": "gpu"}},
    # a pocket: the gorge with a 3 m sill two cells below the inflow, so the inflow cells form a pond with an exit
    "pocket": {"point": (X_IN, YC), "ring_x": X_IN, "valley": {"side": 1.0, "yc": YC + 10.0, "sill": 3.0}},
    "pocket_cfl_half": {
        "point": (X_IN, YC),
        "ring_x": X_IN,
        "valley": {"side": 1.0, "yc": YC + 10.0, "sill": 3.0},
        "numerics": {"cfl": 0.225},
    },
    "pocket_one_cell": {
        "point": (X_IN - 20.0, YC + 20.0),
        "ring_x": X_IN,
        "valley": {"side": 1.0, "yc": YC + 10.0, "sill": 3.0},
    },
}


def read(folder: Path, name: str) -> tuple[np.ndarray, np.ndarray]:
    rows = np.loadtxt(folder / "series" / f"line_{name}.csv", delimiter=",", skiprows=1, ndmin=2)
    return rows[:, 0], np.abs(rows[:, 1])


def stats(t: np.ndarray, q: np.ndarray) -> dict:
    """Readings after the valley has filled, at the saved step and at a minute, as the dock reads them."""
    keep = t >= SETTLED
    t, q = t[keep], q[keep]
    marks = np.arange(np.ceil(t[0] / MINUTE) * MINUTE, t[-1] + 1e-6, MINUTE)
    qm = q[np.abs(t[None, :] - marks[:, None]).argmin(axis=1)]
    return {
        "mean": round(float(q.mean()), 2),
        "min": round(float(q.min()), 2),
        "max": round(float(q.max()), 2),
        "step_5s": round(float(np.abs(np.diff(q)).max()), 2),
        "max_1min": round(float(qm.max()), 2),
        "step_1min": round(float(np.abs(np.diff(qm)).max()), 2),
    }


def run_case(name: str, spec: dict, dem: Path) -> dict:
    out = HERE / "runs" / name
    shutil.rmtree(out, ignore_errors=True)
    spec = dict(spec)
    shape = spec.pop("valley", None)
    if shape is not None:
        out.mkdir(parents=True)
        dem = valley(out / "valley.tif", **shape)
    cfg = job(dem, out, spec.pop("point"), spec.pop("ring_x"), spec.pop("dx", 40.0), **spec)
    run = run_job(cfg, out)
    if run.exit_code:
        raise RuntimeError(f"{name}: {run.message}")
    row = {"case": name, "backend": run.backend, "steps": run.steps, "mass_error": run.balance.relative}
    for line in ("ring", "cross"):
        t, q = read(out, line)
        row[line] = stats(t, q)
        shutil.copy(out / "series" / f"line_{line}.csv", HERE / "series" / f"{name}_{line}.csv")
    row["bitwise_as_base"] = None
    if name != "base" and (HERE / "series" / "base_ring.csv").exists():
        row["bitwise_as_base"] = (HERE / "series" / "base_ring.csv").read_bytes() == (
            HERE / "series" / f"{name}_ring.csv"
        ).read_bytes()
    return row


def main(argv: list[str]) -> None:
    (HERE / "runs").mkdir(exist_ok=True)
    (HERE / "series").mkdir(exist_ok=True)
    dem = valley(HERE / "runs" / "valley.tif")
    wanted = argv or list(CASES)
    results_file = HERE / "results_s01.json"
    results = json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {}
    for name in wanted:
        row = run_case(name, CASES[name], dem)
        results[name] = row
        print(json.dumps(row))
        results_file.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
