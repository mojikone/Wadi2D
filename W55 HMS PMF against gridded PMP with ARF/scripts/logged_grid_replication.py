"""Diagnostic only: the 26 Basin 2 and 3 analyses with RIJ-R11 and RIJ-R17 on the grid HMS logged for them.

The engine is not changed: `MuskingumCunge.grid` is patched in this process for the two lengths, to show that the
whole of the remaining difference to HMS is those two reaches' grid. Writes ``results/logged_grid_replication.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from wadi2d.hydrology import routing
from wadi2d.hydrology.replication import replicate

HERE = Path(__file__).resolve().parents[1]
HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.hms")
LOGGED = {227.9: (2, 113.95, 4), 400.1: (2, 200.05, 2)}  # length: (cells, dx, sub-steps) from the HMS logs
original = routing.MuskingumCunge.grid


def logged_grid(self, dt_seconds):
    for length, grid in LOGGED.items():
        if abs(self.length_m - length) < 1e-6 and abs(dt_seconds - 300.0) < 1e-9:
            return grid
    return original(self, dt_seconds)


def summarise(replication):
    out = {}
    for analysis in replication.analyses:
        rows = replication.of(analysis)
        worst = max(rows, key=lambda c: abs(c.error_percent))
        out[analysis] = {"worst_percent": worst.error_percent, "at": worst.point,
                         "max_steps": max(abs(c.time_steps) for c in rows)}
    return out


wanted = [f"DA {s} B{b}" for b in (2, 3) for s in
          ("PMP", "2yr", "5yr", "10yr", "25yr", "50yr", "100yr", "200yr", "500yr", "1000yr", "2000yr", "5000yr",
           "10000yr")]
rule = summarise(replicate(HMS, wanted))
routing.MuskingumCunge.grid = logged_grid
logged = summarise(replicate(HMS, wanted))
result = {a: {"rule": rule[a], "logged_grid": logged[a]} for a in rule}
(HERE / "results" / "logged_grid_replication.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
for a, row in result.items():
    r, g = row["rule"], row["logged_grid"]
    print(f"{a:16s} rule {r['worst_percent']:+.4f} at {r['at']:9s} steps {r['max_steps']} | logged grid "
          f"{g['worst_percent']:+.4f} at {g['at']:9s} steps {g['max_steps']}")
