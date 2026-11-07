"""W32's Faydh 01 -2.5 % on the dock's own job: the Block 2 hybrid as W20's storm scenario writes it through the dock,
at 80 m as W32 ran it, as GPU, GPU with the Courant number 1e-6 lower, and CPU. One variant per call.

usage: python p02_dock_job.py <the dock's runs/hms/job.json> <variant>
Writes ``results_p02.json``; ``compare_p01.py`` reads it with ``--file results_p02.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

DX = 80.0
CFL = 0.45
NUDGE = 1.0e-6
QUARTER_S = 900.0
VARIANTS = {
    "gpu": {"run": {"backend": "gpu"}},
    "gpu_nudge": {"run": {"backend": "gpu"}, "numerics": {"cfl": CFL * (1.0 - NUDGE)}},
    "cpu": {"run": {"backend": "cpu"}},
}


def job(dock_job: Path, variant: str) -> RunConfig:
    data = json.loads(dock_job.read_text(encoding="utf-8"))
    data["grid"] = {**data["grid"], "dx": DX, "cache_dir": str(HERE / "runs" / "cache_dock_80")}
    data["outputs"] = {**data["outputs"], "map_every_s": 0.0, "live_every_s": 0.0, "pixels": {"enabled": False}, "smooth": {"enabled": False}}
    data["run"] = {**data["run"], "checkpoint_every_s": 0.0}
    for key, value in VARIANTS[variant].items():
        data[key] = {**data.get(key, {}), **value}
    return RunConfig.model_validate(data)


def readings(folder: Path, name: str, every: float) -> dict:
    rows = np.loadtxt(folder / "series" / f"line_{name}.csv", delimiter=",", skiprows=1, ndmin=2)
    t, q = rows[:, 0], np.abs(rows[:, 1])
    width = max(1, round(QUARTER_S / every))
    quarter = np.convolve(q, np.ones(width) / width, mode="valid") if q.size >= width else q
    return {"peak": float(q.max()), "hour": float(t[q.argmax()]) / 3600.0, "peak_15min": float(quarter.max()),
            "volume_m3": float(np.trapezoid(q, t))}  # fmt: skip


def main(dock_job: Path, variant: str) -> None:
    cfg = job(dock_job, variant)
    out = HERE / "runs" / f"dock_{variant}"
    run = run_job(cfg, out)
    if run.exit_code:
        raise RuntimeError(f"{variant}: {run.message}")
    every = cfg.outputs.series_every_s
    lines = {line.name: readings(out, line.name.replace(" ", "_"), every) for line in cfg.outputs.lines}
    results_file = HERE / "results_p02.json"
    results = json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {}
    results[variant] = {"variant": variant, "backend": run.backend, "steps": run.steps, "mass_error": run.balance.relative,
                        "series_every_s": every, "lines": lines, "network": {}}  # fmt: skip
    results_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"variant": variant, "steps": run.steps}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
