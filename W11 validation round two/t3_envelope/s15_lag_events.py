"""The same lag fit on the other three gauged events at Lihban: 2007, 2013, 2019. Mean of the gauges that recorded. Read only."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import openpyxl

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W11 validation round two\engine_f976c23")
from wadi2d.hydrology.transforms import ScsUnitHydrograph, convolve  # noqa: E402

F = Path(r"W:\2331 Flood Hazard Maps for Muscat-Dhofar-Musandam_MWR\06-WORKING\03-Hydrology\0.13 REPORTS\Hydrology Final Report- Flood Data Analysis\Data for model calibration- hydrograph\DB839224AD.xlsx")
HERE = Path(__file__).resolve().parent
AREA = 197.51
DT = 5.0
wb = openpyxl.load_workbook(F, read_only=True, data_only=True)
hyd = [list(r) for r in wb["Recorded Hydrograph"].iter_rows(values_only=True)]
ra = [list(r) for r in wb["Rainfall"].iter_rows(values_only=True)]
print(ra[0][:22])
print(ra[1][:22])
print(ra[2][:22])
starts = hyd[1]
events = []
head = ra[0]
col = [i for i, v in enumerate(head) if isinstance(v, dt.datetime)]
print(col, [head[i] for i in col])
MON = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
out = {}
for n, c in enumerate(col):
    d0 = head[c]
    rows = []
    for r in ra[2:]:
        if r[c] and str(r[c]).startswith("DM") and isinstance(r[c + 5], (int, float)):
            y, mo, day, tm, v = r[c + 1], r[c + 2], r[c + 3], r[c + 4], r[c + 5]
            if isinstance(tm, dt.time):
                when = dt.datetime(int(y), MON[str(mo).strip()], int(day), tm.hour, tm.minute, tm.second)
            elif isinstance(tm, dt.datetime):
                when = tm
            else:
                continue
            rows.append((str(r[c]), when, float(v)))
    if not rows:
        continue
    fc = 2 + n
    start_t = starts[fc]
    start = dt.datetime(d0.year, d0.month, d0.day, start_t.hour, start_t.minute)
    t, q = [], []
    for r in hyd[3:]:
        if isinstance(r[0], (int, float)) and isinstance(r[fc], (int, float)):
            t.append(float(r[0]))
            q.append(float(r[fc]))
    t, q = np.array(t), np.array(q)
    if q.size == 0:
        continue
    sites = sorted({a for a, _, _ in rows})
    tm = np.array([(w - start).total_seconds() / 60.0 for _, w, _ in rows])
    v = np.array([x for _, _, x in rows])
    site = np.array([a for a, _, _ in rows])
    print(d0.date(), "sites", sites, "totals", [round(float(v[site == s].sum()), 1) for s in sites], "flow peak", q.max(), "at min", t[q.argmax()], "rain from", tm.min(), "to", tm.max())
    t0 = -360.0
    N = int((t.max() + 300.0 - t0) / DT)
    edges = t0 + DT * np.arange(N + 1)
    p = np.zeros(N)
    for s in sites:
        p += np.histogram(tm[site == s], bins=edges, weights=v[site == s])[0]
    p /= len(sites)
    tq = edges[:-1] + DT
    obs = np.interp(tq, t, q, left=0.0, right=0.0)
    vol = float(np.trapezoid(q, t * 60.0))
    depth = vol / AREA / 1e3
    lo, hi = 0.0, p.max()
    for _ in range(60):
        m = 0.5 * (lo + hi)
        if np.maximum(p - m, 0.0).sum() > depth:
            lo = m
        else:
            hi = m
    ex = np.maximum(p - hi, 0.0)
    best = None
    for lag in np.arange(10.0, 241.0, 2.0):
        uh = ScsUnitHydrograph(float(lag)).unit_hydrograph(AREA, DT)
        f = convolve(ex, uh, N)
        for sh in np.arange(-30, 35, 5):
            g = np.roll(f, int(round(sh / DT)))
            e = float(((g - obs) ** 2).sum())
            if best is None or e < best[0]:
                best = (e, float(lag), float(sh), float(g.max()))
    nse = 1.0 - best[0] / ((obs - obs.mean()) ** 2).sum()
    cr = float((ex * (tq - DT / 2)).sum() / ex.sum())
    cq = float(np.trapezoid(q * t, t) / np.trapezoid(q, t))
    print(f"   rain mean {p.sum():.1f} mm, runoff {depth:.2f} mm ({100 * depth / max(p.sum(), 1e-6):.1f} %), lag {best[1]:.0f} shift {best[2]:.0f} fit peak {best[3]:.0f} NSE {nse:.2f}, centroid lag {cq - cr:.0f} min")
    out[str(d0.date())] = {"rain_mm": float(p.sum()), "runoff_mm": depth, "peak": float(q.max()), "lag_min": best[1], "shift": best[2], "fit_peak": best[3], "nse": float(nse), "centroid_lag_min": cq - cr}
(HERE / "lag_events.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
