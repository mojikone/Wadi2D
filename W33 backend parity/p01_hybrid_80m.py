"""Why the CPU twin and the GPU part on the Block 2 hybrid (W32 item 1): a backend fault, or a run that magnifies any
difference at all?

The Block 2 hybrid at 80 m, as W32 ran it: the HMS basin lumped, the HMS 100-yr storm, rain on the plain, the sixteen
lines of the validation job. One variant per call, each in its own process, because ``gpu_exact`` replaces CuPy's
``RawModule`` for the whole process:

    gpu        the engine as it is (``--use_fast_math``)
    gpu_exact  the same kernels compiled without ``--use_fast_math``
    cpu        the Numba twin
    gpu_nudge  the GPU with the Courant number one part in a million lower: a perturbation no physics can see

If ``gpu_nudge`` parts from ``gpu`` as far as ``cpu`` does, the split is the run's sensitivity, not the backend.
Writes ``results_p01.json`` and keeps each run's line series under ``runs/``.

usage: python p01_hybrid_80m.py <variant> [--bidah]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.engine.hms_import import build_job  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
JOB = ROOT / "W1 research and design note/validation/block2_full/jobs/c10_A74_h100.json"
DX = 80.0
SERIES_S = 60.0
QUARTER_S = 900.0
CFL = 0.45
NUDGE = 1.0e-6
FAST_MATH = "--use_fast_math"
VARIANTS = {
    "gpu": {"run": {"backend": "gpu"}},
    "gpu_exact": {"run": {"backend": "gpu"}},
    "cpu": {"run": {"backend": "cpu"}},
    "gpu_nudge": {"run": {"backend": "gpu"}, "numerics": {"cfl": CFL * (1.0 - NUDGE)}},
    "cpu_nudge": {"run": {"backend": "cpu"}, "numerics": {"cfl": CFL * (1.0 - NUDGE)}},
}


def exact_kernels() -> None:
    """Compile every CuPy module of this process without fast math; nothing else changes."""
    import cupy

    original = cupy.RawModule

    def plain(*args, options=(), **kwargs):
        return original(*args, options=tuple(o for o in options if o != FAST_MATH), **kwargs)

    cupy.RawModule = plain


def job(variant: str) -> RunConfig:
    base = json.loads(JOB.read_text(encoding="utf-8"))
    imported = json.loads(build_job(HMS, "Basin_1.basin", "FM_100yr.met", "Control_1.control").model_dump_json())
    data = {
        "project": {"name": f"block2_80m_{variant}"},
        "grid": {**base["grid"], "dx": DX, "cache_dir": str(HERE / "runs" / "cache_block2_80")},
        "terrain": base["terrain"],
        "storm": imported["storm"],
        "hydrology": {**imported["hydrology"], "curve_number": base["hydrology"]["curve_number"]},
        "boundaries": base["boundaries"],
        "run": {**imported["run"], "checkpoint_every_s": 0.0},
        "outputs": {
            "map_every_s": 0.0, "live_every_s": 0.0, "series_every_s": SERIES_S, "progress_every_s": 60.0,
            "lines": base["outputs"]["lines"], "pixels": {"enabled": False}, "smooth": {"enabled": False},
        },
    }  # fmt: skip
    for key, value in VARIANTS[variant].items():
        data[key] = {**data.get(key, {}), **value}
    return RunConfig.model_validate(data)


def readings(folder: Path, name: str) -> dict:
    rows = np.loadtxt(folder / "series" / f"line_{name}.csv", delimiter=",", skiprows=1, ndmin=2)
    t, q = rows[:, 0], np.abs(rows[:, 1])
    width = round(QUARTER_S / SERIES_S)
    quarter = np.convolve(q, np.ones(width) / width, mode="valid")
    return {
        "peak": float(q.max()),
        "hour": float(t[q.argmax()]) / 3600.0,
        "peak_15min": float(quarter.max()),
        "volume_m3": float(np.trapezoid(q, t)),
    }


def network(folder: Path) -> dict:
    """Peak of every lumped element's own series, which the grid does not touch until its outflow enters it."""
    out = {}
    for path in sorted((folder / "series").glob("network_*.csv")):
        rows = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
        out[path.stem.removeprefix("network_")] = float(np.abs(rows[:, 1:]).max())
    return out


def main(variant: str) -> None:
    if variant == "gpu_exact":
        exact_kernels()
    cfg = job(variant)
    out = HERE / "runs" / variant
    run = run_job(cfg, out)
    if run.exit_code:
        raise RuntimeError(f"{variant}: {run.message}")
    row = {
        "variant": variant,
        "backend": run.backend,
        "steps": run.steps,
        "mass_error": run.balance.relative,
        "lines": {line.name: readings(out, line.name.replace(" ", "_")) for line in cfg.outputs.lines},
        "network": network(out),
    }
    results_file = HERE / "results_p01.json"
    results = json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {}
    results[variant] = row
    results_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"variant": variant, "backend": run.backend, "steps": run.steps}))


if __name__ == "__main__":
    main(sys.argv[1])
