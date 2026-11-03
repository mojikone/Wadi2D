"""The Block 2 hybrid at 40 m, the W20 scenario's run without the dock: the HMS basin lumped, rain on the plain,
the sixteen lines of the validation job, series every 5 s so the flicker's shape can be seen.

The job is the validation job with the import of the HMS project in it, as the dock merges them. Each variant
changes one thing. Writes ``results_s02.json`` and the series of every line beside this file.

usage: python s02_block2_40m.py [variant ...]
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.engine.hms_import import build_job  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
JOB = HERE.parent / "W1 research and design note/validation/block2_full/jobs/c10_A74_h100.json"
DX = 40.0
SERIES = 5.0
MINUTE, QUARTER = 60.0, 900.0

VARIANTS: dict[str, dict] = {
    "w20": {},
    "w20_points": {"outputs": {"series_every_s": 1.0}, "points": True},
    "lowest_only": {"hydrology": {"inject_min_depth": 5.0}, "points": True},
    "refresh_10": {"run": {"source_every_s": 10.0}, "points": True},
    "refresh_120": {"run": {"source_every_s": 120.0}, "points": True},
    "radius_100": {"hydrology": {"inject_radius": 100.0}, "points": True},
    "cfl_half": {"numerics": {"cfl": 0.225}, "points": True},
    "cpu": {"run": {"backend": "cpu"}, "points": True},
    "dx20": {"grid": {"dx": 20.0, "cache_dir": str(HERE / "runs" / "cache_block2_20")}},
}


def injection_points(found: dict) -> list[dict]:
    """Point series at the cells that take each ringed subbasin's hydrograph, from ``s03``."""
    out = []
    for name, item in found.items():
        x0, y0 = item["grid_origin"]
        for n, cell in enumerate(item["cells"]):
            x, y = x0 + (cell["i"] + 0.5) * DX, y0 - (cell["j"] + 0.5) * DX
            out.append({"name": f"{name}_cell{n}_{'in' if cell['inside_ring'] else 'out'}", "x": x, "y": y})
    return out


def job(variant: dict) -> RunConfig:
    base = json.loads(JOB.read_text(encoding="utf-8"))
    imported = json.loads(
        build_job(HMS, "Basin_1.basin", "FM_100yr.met", "Control_1.control").model_dump_json()
    )
    data = {
        "project": {"name": "block2_40m_hybrid"},
        "grid": {**base["grid"], "dx": DX, "cache_dir": str(HERE / "runs" / "cache_block2")},
        "terrain": base["terrain"],
        "storm": imported["storm"],
        "hydrology": {**imported["hydrology"], "curve_number": base["hydrology"]["curve_number"]},
        "boundaries": base["boundaries"],
        "run": {**imported["run"], "backend": "gpu", "checkpoint_every_s": 0.0},
        "outputs": {
            "map_every_s": 0.0, "live_every_s": 0.0, "series_every_s": SERIES, "progress_every_s": 10.0,
            "lines": base["outputs"]["lines"], "pixels": {"enabled": False},
        },
    }  # fmt: skip
    variant = dict(variant)
    if variant.pop("points", False):
        found = json.loads((HERE / "injection_cells.json").read_text(encoding="utf-8"))
        data["outputs"]["points"] = injection_points(found)
    for key, value in variant.items():
        data[key] = {**data.get(key, {}), **value}
    return RunConfig.model_validate(data)


def read(folder: Path, name: str) -> tuple[np.ndarray, np.ndarray]:
    rows = np.loadtxt(folder / "series" / f"line_{name}.csv", delimiter=",", skiprows=1, ndmin=2)
    return rows[:, 0], np.abs(rows[:, 1])


def at(t: np.ndarray, q: np.ndarray, every: float) -> np.ndarray:
    marks = np.arange(0.0, t[-1] + 1e-6, every)
    return q[np.abs(t[None, :] - marks[:, None]).argmin(axis=1)]


def readings(t: np.ndarray, q: np.ndarray) -> dict:
    """The dock's readings: the raw peak at a minute, the step change near it, and the 15-minute mean's peak."""
    qm = at(t, q, MINUTE)
    k = int(qm.argmax())
    near = qm[max(k - 120, 0) : k + 120]
    width = round(QUARTER / MINUTE)
    quarter = np.convolve(qm, np.ones(width) / width, mode="valid") if qm.size >= width else qm
    return {
        "peak_1min": round(float(qm.max()), 1),
        "hour": round(float(t[np.abs(q - qm.max()).argmin()]) / 3600.0, 2),
        "step_1min_rms": round(float(np.sqrt(np.mean(np.diff(near) ** 2))), 1),
        "step_1min_max": round(float(np.abs(np.diff(near)).max()), 1),
        "peak_15min": round(float(quarter.max()), 1),
        "peak_5s": round(float(q.max()), 1),
        "step_5s_max": round(float(np.abs(np.diff(q)).max()), 1),
    }


def main(argv: list[str]) -> None:
    (HERE / "series").mkdir(exist_ok=True)
    wanted = argv or list(VARIANTS)
    results_file = HERE / "results_s02.json"
    results = json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {}
    for name in wanted:
        out = HERE / "runs" / f"block2_{name}"
        shutil.rmtree(out, ignore_errors=True)
        cfg = job(VARIANTS[name])
        run = run_job(cfg, out)
        if run.exit_code:
            raise RuntimeError(f"{name}: {run.message}")
        row = {
            "variant": name,
            "backend": run.backend,
            "steps": run.steps,
            "mass_error": run.balance.relative,
            "lines": {},
        }
        for line in cfg.outputs.lines:
            t, q = read(out, line.name.replace(" ", "_"))
            row["lines"][line.name] = readings(t, q)
            shutil.copy(
                out / "series" / f"line_{line.name.replace(' ', '_')}.csv",
                HERE / "series" / f"block2_{name}_{line.name.replace(' ', '_')}.csv",
            )
        results[name] = row
        print(json.dumps(row))
        results_file.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
