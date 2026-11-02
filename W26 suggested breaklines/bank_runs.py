"""Suggested bank lines against none, at the same cell size, with the fully fine run as the reference.

usage: python bank_runs.py bidah|faydh suggest        writes the suggestion for the case into suggested/<case>/
       python bank_runs.py bidah|faydh run NAME dx [lines [shift_m]]   one run; NAME is the folder under runs/

``shift_m`` moves every bank vertex elevation by that much, a diagnostic only: lines a metre below the ground change no
face elevation, so what they still change is the crest-face treatment itself.

The runs are the rain-on-grid head-to-head jobs frozen in W1 (Bidah) and W11 (Faydh 01), cut to 16 h, which holds the
peak, with maps off. Only the bank lines of the suggestion go in, as crest lines with their vertex elevations: that is
what the dock does with the layer once the crests are deleted. Nothing is tuned. Results append to results.jsonl.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # this checkout, not the installed one
from wadi2d.breaklines import suggest
from wadi2d.breaklines.settings import BANK, FILE
from wadi2d.config.schema import RunConfig
from wadi2d.run import load_job, run_job

HERE = Path(__file__).resolve().parent
W1 = HERE.parent / "W1 research and design note" / "validation" / "ras_rain_on_grid"
W11 = HERE.parent / "W11 validation round two" / "t2_faydh"
CASES = {
    "bidah": {"job": W1 / "jobs" / "10m_n050_em.json", "domain20": W1 / "domain_wadi_20m.geojson"},
    "faydh": {"job": W11 / "jobs" / "10m_n050_em.json", "domain20": W11 / "domain_wadi_20m.geojson"},
}
DURATION_S = 16 * 3600.0


def base(case: str, dx: float) -> dict:
    cfg = load_job(CASES[case]["job"])
    data = cfg.model_dump(mode="json")
    data["grid"]["dx"] = dx
    data["grid"]["cache_dir"] = str(HERE / "cache")
    if dx == 20.0:
        data["grid"]["domain"] = str(CASES[case]["domain20"])
    data["outputs"]["map_every_s"] = 0.0
    data["outputs"]["live_every_s"] = 0.0
    data["run"]["duration_s"] = DURATION_S
    data["run"]["backend"] = "gpu"
    return data


def bank_lines(case: str, shift: float = 0.0) -> list[dict]:
    """The bank lines of the suggestion as crest lines with Z per vertex, as the plugin builds them."""
    db = sqlite3.connect(HERE / "suggested" / case / FILE)
    out = []
    for blob, kind in db.execute("SELECT geom, kind FROM breaklines"):
        if kind != BANK:
            continue
        for part in shapely.from_wkb(blob[40:]).geoms:
            coords = np.asarray(part.coords)
            out.append({"kind": "crest_line", "coordinates": coords[:, :2].tolist(), "z": (coords[:, 2] + shift).tolist()})
    db.close()
    return out


def main() -> None:
    case, what = sys.argv[1], sys.argv[2]
    if what == "suggest":
        folder = HERE / "suggested" / case
        summary = suggest(RunConfig.model_validate(base(case, 10.0)), folder)
        (folder / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps(summary, indent=1))
        return
    name, dx = sys.argv[3], float(sys.argv[4])
    data = base(case, dx)
    shift = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
    lines = bank_lines(case, shift) if len(sys.argv) > 5 and sys.argv[5] == "lines" else []
    data["terrain"]["objects"] = lines
    summary = run_job(RunConfig.model_validate(data), HERE / "runs" / name)
    row = {
        "case": case,
        "name": name,
        "dx": dx,
        "lines": len(lines),
        "shift_m": shift,
        "status": summary.status,
        "dt_min": summary.dt_min,
        "message": summary.message[:200],
        "cells": summary.cells,
        "steps": summary.steps,
        "mass": summary.balance.relative,
        "wet_km2": summary.wet_area_km2,
        "peaks": {k: [round(v[0], 2), round(v[1])] for k, v in summary.peaks.items()},
    }
    with (HERE / "results.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row))


if __name__ == "__main__":
    main()
