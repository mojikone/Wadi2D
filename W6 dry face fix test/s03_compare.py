"""Bidah against the frozen baseline and HEC-RAS with the fix on. Writes compare.json."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "W1 research and design note" / "validation" / "ras_rain_on_grid"


def line(folder: Path, name: str):
    with (folder / "series" / f"line_{name}.csv").open() as h:
        d = np.array([[float(v) for v in r] for r in list(csv.reader(h))[1:]])
    return d[:, 0], d[:, 1]


def done(folder: Path) -> dict:
    return [json.loads(s) for s in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines() if '"done"' in s][-1]


out = {}
for name in ("20m_n050_em", "10m_n050_em"):
    new = HERE / "runs" / f"bidah_{name}"
    z = np.load(BASE / f"series_{name}.npz")
    row: dict = {}
    for sec, key in (("axis", "axis"), ("s13_edge", "s13_edge")):
        t0, q0 = line(BASE / "wadi_runs" / name, sec)
        t1, q1 = line(new, sec)
        tr, qr = z[f"{key}_tr"], z[f"{key}_qr"]
        q_i = np.interp(tr, t1, q1)
        row[sec] = {
            "ras": float(qr.max()), "before": float(q0.max()), "after": float(q1.max()),
            "ratio_before": float(q0.max() / qr.max()), "ratio_after": float(q1.max() / qr.max()),
            "t_ras_h": float(tr[int(np.argmax(qr))] / 3600), "t_after_h": float(t1[int(np.argmax(q1))] / 3600),
            "nse_after": float(1 - ((q_i - qr) ** 2).sum() / ((qr - qr.mean()) ** 2).sum()),
        }  # fmt: skip
    a, b = done(BASE / "wadi_runs" / name), done(new)
    row["steps"] = [a["steps"], b["steps"]]
    row["loop_s"] = [a["loop_s"], b["loop_s"]]
    row["mass"] = b["balance"]["relative_error"]
    out[name] = row
    print(name, json.dumps(row)[:520])
(HERE / "compare.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
