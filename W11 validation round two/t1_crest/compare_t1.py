"""Test 1: crest line against 2D Connection. usage: compare_t1.py NAME [RAS_NAME]   (Wadi2D run NAME, RAS project ras_RAS_NAME)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import h5py
import numpy as np
import rasterio

import t1case as c

HERE = c.HERE
X0, Y0 = c.base.X0, c.base.Y0
AREA = "Bidah"
TS = "Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series"
SM = "Results/Unsteady/Output/Output Blocks/Base Output/Summary Output/2D Flow Areas/" + AREA


def stage_points() -> dict[str, tuple[float, float]]:
    a = np.array(c.AXIS)
    leg = np.hypot(*np.diff(a, axis=0).T)
    s = 450.0
    k = 0
    while s > leg[k]:
        s -= leg[k]
        k += 1
    d = (a[k + 1] - a[k]) / leg[k]
    p = a[k] + s * d
    n = np.array([d[1], -d[0]])  # right of south-east to north-west walk is north-east, downstream
    n = -n if n[0] > 0 else n  # so upstream points south-west
    return {"pool150": tuple(p + 150.0 * n), "pool400": tuple(p + 400.0 * n), "tail100": tuple(p - 100.0 * n)}


def series(name: str, line: str) -> tuple[np.ndarray, np.ndarray]:
    with open(HERE / "wadi_runs" / name / "series" / f"line_{line}.csv", encoding="utf-8") as f:
        a = np.array(list(csv.reader(f))[1:], np.float64)
    return a[:, 0], a[:, 1]


def shape(t, q) -> dict:
    i = int(np.argmax(q))
    return {"peak": float(q[i]), "t_h": float(t[i] / 3600.0), "volume_Mm3": float(np.trapezoid(q, t) / 1e6)}


def first_over(t, q, frac=0.01):
    k = np.nonzero(q > frac * q.max())[0]
    return float(t[k[0]] / 3600.0)


def main() -> None:
    name = sys.argv[1]
    rname = sys.argv[2] if len(sys.argv) > 2 else name
    pts = stage_points()
    out: dict = {"name": name, "ras": rname, "points": {k: list(map(float, v)) for k, v in pts.items()}}
    # RAS
    f = h5py.File(HERE / f"ras_{rname}" / "Bidah.p01.hdf", "r")
    d = f[TS + f"/2D Flow Areas/{AREA}/2D Hyd Conn/Embankment/Structure Variables"]
    labels = [x[0].decode() for x in d.attrs["Variable_Unit"]]
    sv = d[:].astype(np.float64)
    tr = f[TS + "/Time"][:] * 86400.0
    qr = sv[:, labels.index("Total Flow")]
    m = f[f"Geometry/2D Flow Areas/{AREA}"]
    nc = int(f["Geometry/2D Flow Areas/Attributes"]["Cell Count"][0])
    cc = m["Cells Center Coordinate"][:nc]
    wse_max = f[SM + "/Maximum Water Surface"][0, :nc].astype(np.float64)
    out["ras_labels"] = labels
    out["ras_stage_hw_max"] = float(sv[:, labels.index("Stage HW")].max())
    out["ras_stage_tw_max"] = float(sv[:, labels.index("Stage TW")].max())
    va = f["Results/Unsteady/Summary/Volume Accounting"].attrs
    out["ras_vol_error_pct"] = float(va["Error Percent"])
    pa = f["Geometry/Structures/Attributes"][0]
    out["ras_use_2d"] = int(pa["Use 2D for Overflow"])
    ip = int(np.argmax(qr))
    wname = TS + f"/2D Flow Areas/{AREA}/2D Hyd Conn/Embankment/Weir Variables"
    if wname in f:  # absent when the overflow runs by the 2D equations
        wv = f[wname]
        wlab = [x[0].decode() for x in wv.attrs["Variable_Unit"]]
        w = wv[:].astype(np.float64)
        out["ras_at_peak"] = {k: float(w[ip, i]) for i, k in enumerate(wlab)}
    # Wadi2D
    tw, qw = series(name, "crest")
    sr, sw = shape(tr, qr), shape(tw, qw)
    out["peak_ras"] = sr
    out["peak_wadi"] = sw
    out["peak_ratio_wadi_over_ras"] = sw["peak"] / sr["peak"]
    out["volume_ratio"] = sw["volume_Mm3"] / sr["volume_Mm3"]
    out["t_peak_diff_min"] = (sw["t_h"] - sr["t_h"]) * 60.0
    out["onset_h"] = {"ras": first_over(tr, qr), "wadi": first_over(tw, qw)}
    with rasterio.open(HERE / "wadi_runs" / name / "maps" / "max_level.tif") as s:
        lv = s.read(1, masked=True).astype(np.float64).filled(np.nan)
        tt = s.transform
    dx = float(tt.a)
    rows = {}
    for k, (x, y) in pts.items():
        j = np.argmin(((cc[:, 0] - x) ** 2 + (cc[:, 1] - y) ** 2))
        r = int((tt.f - cc[j, 1]) / dx)
        ci = int((cc[j, 0] - tt.c) / dx)
        rows[k] = {"cell": [float(cc[j, 0]), float(cc[j, 1])], "ras": float(wse_max[j]), "wadi": float(lv[r, ci]), "diff_wadi_minus_ras": float(lv[r, ci] - wse_max[j])}
    out["stage"] = rows
    # the whole pool: cells within 1 km upstream of the axis, level difference
    from shapely import contains_xy
    from shapely.geometry import LineString

    band = LineString(c.AXIS).buffer(800.0, single_sided=True)  # left of the south-east to north-west walk is south-west
    inb = contains_xy(band, cc[:, 0], cc[:, 1])
    rr = ((tt.f - cc[:, 1]) / dx).astype(int)
    ci = ((cc[:, 0] - tt.c) / dx).astype(int)
    ok = (rr >= 0) & (rr < lv.shape[0]) & (ci >= 0) & (ci < lv.shape[1])
    lev = np.full(nc, np.nan)
    lev[ok] = lv[rr[ok], ci[ok]]
    zmin = m["Cells Minimum Elevation"][:nc]
    deep = inb & ok & ((wse_max - zmin) > 0.5) & np.isfinite(lev)
    dl = (lev - wse_max)[deep]
    out["pool_band_800m"] = {"cells": int(deep.sum()), "mean": float(dl.mean()), "rms": float(np.sqrt((dl**2).mean())), "p5": float(np.percentile(dl, 5)), "p95": float(np.percentile(dl, 95))}
    # verdict of the rule on the primary only
    out["rule"] = {"q_within_10pct": bool(abs(out["peak_ratio_wadi_over_ras"] - 1.0) <= 0.10), "stage_within_0.15": bool(abs(rows["pool150"]["diff_wadi_minus_ras"]) <= 0.15)}
    (HERE / f"results_{name}{'' if rname == name else '_vs_' + rname}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    np.savez_compressed(HERE / f"series_{name}{'' if rname == name else '_vs_' + rname}.npz", tr=tr, qr=qr, tw=tw, qw=qw)


if __name__ == "__main__":
    main()
