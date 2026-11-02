"""Score plan_min 0.05 against the frozen baseline and HEC-RAS, with the pass mark fixed in s01_jobs.py."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "W1 research and design note" / "validation" / "ras_rain_on_grid"


def line(folder: Path, name: str = "axis"):
    with (folder / "series" / f"line_{name}.csv").open() as h:
        d = np.array([[float(v) for v in r] for r in list(csv.reader(h))[1:]])
    return d[:, 0], d[:, 1]


def done(folder: Path) -> dict:
    return [json.loads(s) for s in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines() if '"done"' in s][-1]


out = {}
for name in ("20m_n050_em", "10m_n050_em"):
    t0, q0 = line(BASE / "wadi_runs" / name)
    t1, q1 = line(HERE / "runs" / f"{name}_planmin05")
    ras = np.load(BASE / f"series_{name}.npz")
    p_ras = float(ras["axis_qr"].max())
    a, b = done(BASE / "wadi_runs" / name), done(HERE / "runs" / f"{name}_planmin05")
    k0, k1 = int(np.argmax(q0)), int(np.argmax(q1))
    row = {
        "peak_base": float(q0[k0]), "peak_new": float(q1[k1]), "peak_change_pct": float((q1[k1] / q0[k0] - 1) * 100),
        "t_shift_min": float((t1[k1] - t0[k0]) / 60), "ratio_ras_base": float(q0[k0] / p_ras), "ratio_ras_new": float(q1[k1] / p_ras),
        "steps_base": a["steps"], "steps_new": b["steps"], "steps_change_pct": float((b["steps"] / a["steps"] - 1) * 100),
        "loop_s_base": a["loop_s"], "loop_s_new": b["loop_s"], "mass_new": b["balance"]["relative_error"],
    }  # fmt: skip
    row["pass"] = abs(row["peak_change_pct"]) <= 1.0 and abs(row["t_shift_min"]) <= 2.0 and abs(row["ratio_ras_new"] - 1) <= 0.10 and abs(row["mass_new"]) < 1e-6
    out[name] = row
    print(name, json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}))
(HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
