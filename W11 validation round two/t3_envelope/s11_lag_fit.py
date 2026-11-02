"""Observed response of Bani Umar near Lihban (DB839224AD, 197.5 km2): the SCS lag that fits gauged rain and gauged flow.

Excess is built from the gauged rain with a loss chosen to give the observed volume exactly, so volume is not free to
compensate. Two loss forms bracket the timing: a constant phi rate, and a constant runoff fraction. The lag is then
fitted by least squares on 5 min steps, with a free start shift of the clock of up to +/-30 min between the two
records. The project's HMS calibration used lag 140 min and CN 92 and overshot volume by 1.64. Read only.
"""
from __future__ import annotations

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
rows = [list(r) for r in wb["Shaheen"].iter_rows(values_only=True)]
rain = [(int(r[3]), float(r[4]), float(r[5])) for r in rows[2:] if r[0] and str(r[0]).startswith("DM") and isinstance(r[5], (int, float))]
hyd = [list(r) for r in wb["Recorded Hydrograph"].iter_rows(values_only=True)]
print(hyd[0][:6], hyd[1][:6], hyd[2][:6], hyd[3][:6])
minute = []
q = []
for r in hyd[3:]:
    if isinstance(r[0], (int, float)) and isinstance(r[5], (int, float)):
        minute.append(float(r[0]))
        q.append(float(r[5]))
minute, q = np.array(minute), np.array(q)
print("flow", len(q), minute[:3], minute[-3:], "peak", q.max(), "at min", minute[q.argmax()])
vol = float(np.trapezoid(q, minute * 60.0))
print("volume Mm3", vol / 1e6, "mm over basin", vol / AREA / 1e3)

# rain on minutes from 00:00 of 4 Oct
r = np.array(rain)
# The Time column runs on from the start of the record; the Day column flips from 3 to 4 between 656 and 658, so
# minute 657 is midnight of 3/4 October. That puts the two bursts at 00:00-03:00 and 03:40-05:40 on the 4th, as the
# project's HMS run has them, and before the 04:00 flood peak.
tm = r[:, 1] - 657.0
print("rain total", r[:, 2].sum(), "from", tm.min(), "to", tm.max())
t0 = -660.0
n = int((1500.0 - t0) / DT)
edges = t0 + DT * np.arange(n + 1)
p, _ = np.histogram(tm, bins=edges, weights=r[:, 2])
print("rain in window", p.sum(), "peak 5 min", p.max(), "at", edges[p.argmax()] + DT, "peak 1 h", np.convolve(p, np.ones(12))[11:].max())
tq = edges[:-1] + DT  # the step ends here, HMS's convention
obs = np.interp(tq, minute, q, left=0.0, right=0.0)
base = float(np.median(q[:3]))


def excess_phi(p: np.ndarray, depth: float) -> np.ndarray:
    lo, hi = 0.0, p.max()
    for _ in range(60):
        m = 0.5 * (lo + hi)
        if np.maximum(p - m, 0.0).sum() > depth:
            lo = m
        else:
            hi = m
    return np.maximum(p - hi, 0.0)


def fit(ex: np.ndarray, label: str, shifts=np.arange(-30, 35, 5)) -> dict:
    best = None
    for lag in np.arange(10.0, 241.0, 2.0):
        uh = ScsUnitHydrograph(float(lag)).unit_hydrograph(AREA, DT)
        f = convolve(ex, uh, n)
        for s in shifts:
            k = int(round(s / DT))
            g = np.roll(f, k)
            e = float(((g - obs) ** 2).sum())
            if best is None or e < best[0]:
                best = (e, float(lag), float(s), float(g.max()), float(tq[int(np.argmax(g))]))
    nse = 1.0 - best[0] / ((obs - obs.mean()) ** 2).sum()
    print(f"{label}: lag {best[1]:.0f} min, shift {best[2]:.0f}, peak {best[3]:.0f} at {best[4]:.0f}, NSE {nse:.3f}")
    return {"lag_min": best[1], "shift_min": best[2], "peak": best[3], "t_peak_min": best[4], "nse": float(nse)}


depth = vol / AREA / 1e3  # mm
out = {"area_km2": AREA, "obs_peak": float(q.max()), "obs_t_peak_min": float(minute[q.argmax()]), "obs_volume_Mm3": vol / 1e6,
       "obs_depth_mm": depth, "rain_mm": float(p.sum())}  # fmt: skip
phi = excess_phi(p, depth)
frac = p * depth / p.sum()
out["phi"] = fit(phi, "phi loss, whole storm")
out["fraction"] = fit(frac, "constant fraction, whole storm")
# the first burst alone: rain and flow up to the trough before the second flood rise
mask = tq <= 330.0
obs_all = obs.copy()
for name, ex in (("phi", phi), ("fraction", frac)):
    e = ex.copy()
    best = None
    for lag in np.arange(10.0, 241.0, 2.0):
        uh = ScsUnitHydrograph(float(lag)).unit_hydrograph(AREA, DT)
        f = convolve(e, uh, n)
        for s in np.arange(-30, 35, 5):
            g = np.roll(f, int(round(s / DT)))
            err = float(((g[mask] - obs[mask]) ** 2).sum())
            if best is None or err < best[0]:
                best = (err, float(lag), float(s), float(g[mask].max()))
    print(f"rising limb and first peak only, {name}: lag {best[1]:.0f}, shift {best[2]:.0f}, peak {best[3]:.0f}")
    out[f"first_peak_{name}"] = {"lag_min": best[1], "shift_min": best[2], "peak": best[3]}
# what lag 140 gives with the observed volume
for name, ex in (("phi", phi), ("fraction", frac)):
    uh = ScsUnitHydrograph(140.0).unit_hydrograph(AREA, DT)
    f = convolve(ex, uh, n)
    print(f"lag 140 with the observed volume, {name}: peak {f.max():.0f}")
    out[f"lag140_{name}_peak"] = float(f.max())
# centroid lag: rain excess centroid to flow centroid, independent of any unit hydrograph
for name, ex in (("phi", phi), ("fraction", frac)):
    cr = float((ex * (tq - DT / 2)).sum() / ex.sum())
    cq = float(np.trapezoid(q * minute, minute) / np.trapezoid(q, minute))
    print(f"centroid to centroid, {name}: {cq - cr:.0f} min")
    out[f"centroid_lag_{name}"] = cq - cr
(HERE / "shaheen_fit.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
np.savetxt(HERE / "shaheen_5min.csv", np.column_stack((tq, p, obs)), delimiter=",", header="t_min_from_4Oct,rain_mm,flow_m3s", comments="", fmt="%.1f,%.2f,%.1f")
