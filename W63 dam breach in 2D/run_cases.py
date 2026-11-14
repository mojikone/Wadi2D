"""W63: the synthetic V valley's breach cases, CPU and one GPU run; prints the numbers the README quotes."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.engine import test_breach as T  # noqa: E402
from tests.engine.conftest import X0, Y0  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

LINE = {"lines": [{"name": "Below", "coordinates": [(X0 + 216.0, Y0), (X0 + 216.0, Y0 - T.NY * T.DX)]}]}


def case(work: Path, name: str, breach: dict, backend: str = "cpu", duration: float = 1500.0) -> dict:
    cfg = T.dam_job(work / "valley.tif", [breach], duration=duration, outputs=LINE)
    cfg = cfg.model_copy(update={"run": cfg.run.model_copy(update={"backend": backend})})
    out = work / name
    s = run_job(cfg, out)
    rows = T.series(out, "breach_Dam.csv")
    line = T.series(out, "line_Below.csv")
    k = int(np.argmax(np.abs(line[:, 1])))  # positive to the right of a southward line: westward
    piping = rows[np.isfinite(rows[:, 4])]
    return {
        "case": name, "backend": s.backend, "exit": s.exit_code, "pool_m3": round(s.balance.storage0, 1),
        "left_m3": round(s.balance.storage, 1), "outflow_m3": round(s.balance.outflow, 1),
        "balance_relative": s.balance.relative, "start_s": rows[0, 0],
        "collapse_s": float(rows[~np.isfinite(rows[:, 4]), 0].min()) if piping.size else None,
        "pipe_peak_m3s": float(piping[:, 7].max()) if piping.size else None,
        "peak_below_m3s": round(abs(float(line[k, 1])), 2), "peak_t_s": float(line[k, 0]),
    }  # fmt: skip


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="w63_"))
    x = (np.arange(T.NX * T.DX / T.PIXEL) + 0.5) * T.PIXEL
    y = (np.arange(T.NY * T.DX / T.PIXEL) + 0.5) * T.PIXEL
    T.write_dem(work / "valley.tif", T.ground(x[None, :], y[:, None]), T.PIXEL)
    over = T.breach(station_m=T.MID)
    pipe = T.breach(mode="piping", piping_z=100.0, formation_time_s=600.0, trigger="level", trigger_level=102.0)
    sine = T.breach(station_m=T.MID, progression="sine")
    out = [case(work, "overtopping", over), case(work, "overtopping_sine", sine), case(work, "piping", pipe)]
    if "--gpu" in sys.argv:
        out.append(case(work, "overtopping_gpu", over, "gpu"))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
