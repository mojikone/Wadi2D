"""Read a run folder: peaks, times, volumes through the lines, against the lumped engine at the run's storm area."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import HEADWATERS, OUT, SITES, hms_reference  # noqa: E402
from lumped_ref import TIMES_H, run_at, stats  # noqa: E402

from wadi2d.io.results import safe_name  # noqa: E402


def series(run: Path, name: str, kind: str = "line") -> tuple[np.ndarray, np.ndarray]:
    path = run / "series" / f"{kind}_{safe_name(name)}.csv"
    rows = list(csv.reader(path.open()))
    data = np.array(rows[1:], dtype=np.float64)
    return data[:, 0], data[:, 1]


def line_stats(run: Path, name: str) -> dict[str, float]:
    t, q = series(run, name)
    q = np.abs(q) if abs(q.min()) > abs(q.max()) else q
    k = int(np.argmax(q))
    return {"peak": float(q[k]), "t_h": float(t[k] / 3600.0), "vol_m3": float(np.trapezoid(q, t)), "end_q": float(q[-1])}


def done_event(run: Path) -> dict:
    last = None
    start = None
    steps = []
    for line in (run / "progress.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("ev") == "done":
            last = e
        elif e.get("ev") == "start":
            start = e
        elif e.get("ev") == "step":
            steps.append(e)
    return {"done": last, "start": start, "steps": steps}


def table(run: Path, area: float | None = None) -> list[dict]:
    if area is None:
        cfg = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
        area = cfg["storm"]["storm_area_km2"]
    lump = run_at(area).outflow
    rows = []
    for site in SITES:
        a = line_stats(run, site)
        rr = line_stats(run, f"{site} ring")
        ref = stats(lump[site])
        rows.append({"site": site, "area": area, "line": a, "ring": rr, "lumped": ref})
    return rows


def show(run: Path, area: float | None = None) -> None:
    e = done_event(run)
    d, s = e["done"], e["start"]
    if d:
        b = d["balance"]
        print(f"{run.name}: cells {s['cells']} tiles {s['tiles']} tables {s['tables_s']} s loop {d['loop_s']} s steps {d['steps']} dt_min {d['dt_min']:.3f} "
              f"mean dt {d['t']/d['steps']:.3f} wet {d['wet_area_km2']} km2; rain {b['rain_m3']/1e6:.2f} inflow {b['inflow_m3']/1e6:.2f} out {b['outflow_m3']/1e6:.2f} "
              f"store {b['storage_end_m3']/1e6:.3f} err {b['relative_error']:.2e}")
    for r in table(run, area):
        a, g, h = r["line"], r["ring"], r["lumped"]
        print(f"  {r['site']:9s} A={r['area']:.1f} lumped {h['peak']:7.1f} @{h['t_h']:5.2f} {h['vol_m3']/1e6:6.2f} | line {a['peak']:7.1f} @{a['t_h']:5.2f} {a['vol_m3']/1e6:6.2f} "
              f"ratio {a['peak']/h['peak']:.3f} vol {a['vol_m3']/h['vol_m3']:.3f} | ring {g['peak']:7.1f} @{g['t_h']:5.2f} {g['vol_m3']/1e6:6.2f} ratio {g['peak']/h['peak']:.3f} vol {g['vol_m3']/h['vol_m3']:.3f}")


def headwaters(run: Path, area: float | None = None) -> None:
    if area is None:
        cfg = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
        area = cfg["storm"]["storm_area_km2"]
    lump = run_at(area).outflow
    for n in HEADWATERS:
        a = line_stats(run, f"{n} ring")
        h = stats(lump[n])
        print(f"  {n:4s} lumped {h['peak']:7.1f} @{h['t_h']:5.2f} {h['vol_m3']/1e6:6.2f} | ring {a['peak']:7.1f} @{a['t_h']:5.2f} {a['vol_m3']/1e6:6.2f} ratio {a['peak']/h['peak']:.3f} vol {a['vol_m3']/h['vol_m3']:.3f}")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        run = OUT / "runs" / name
        show(run)
        headwaters(run)
