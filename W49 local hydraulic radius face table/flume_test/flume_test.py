"""The local hydraulic radius against measured flumes (W49, 2026-11-08). Data: `data_sources.md`, transcribed CSVs.

1. Lansford & Mitchell 1949 (Illinois Bulletin 381): a 5 ft rectangular flume, S0 0.003, one artificial roughness on
   bed and walls (cross-sections 2 and 4), measured normal depth and discharge. For each run the Manning n that each
   friction law needs to carry the measured Q at the measured depth: the strips sum (plan width, no wall shear,
   Wadi2D's default), Spada et al.'s local hydraulic radius (beta 9, the engine's own `_local_radius_conveyance` on the
   section at 1/200 of the width), and Manning on the section's hydraulic radius. One roughness on the whole
   perimeter: the law that is right needs the same n at every breadth-to-depth ratio.
2. Knight, Demetriou & Hamed 1984 (via Chlebek 2009, Table 3.1): smooth rectangular channels 70 to 610 mm wide, the
   measured share of the boundary shear force carried by the walls, against the share each law implies: none for the
   strips sum, the perimeter share for section Manning, and for the local radius 1 - sum(R_i dy) / A on its own
   premise that the bed under pixel i carries rho g R_i S0.

    .venv\Scripts\python "W49 local hydraulic radius face table\flume_test\flume_test.py"
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from wadi2d.tables.core import _local_radius_conveyance  # noqa: E402

FT = 0.3048
CFS = 0.028316846592
BETA = 9.0
ACROSS = 200
"""Pixels across the channel's width."""


def rows(name: str) -> list[dict]:
    with open(HERE / name, encoding="utf-8") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def lhrm(b: float, h: float, beta: float = BETA) -> tuple[float, float]:
    """K at n = 1 of a rectangle b wide, h deep, and the share of the shear on its walls, by the engine's function."""
    px = b / ACROSS
    side = int(np.ceil(beta * h / px)) + 2
    ext = np.concatenate((np.full(side, 1e3), np.zeros(ACROSS), np.full(side, 1e3)))
    tab = np.zeros((2, 2))
    _local_radius_conveyance(ext, side, side + ACROSS, 0.0, h, px, 1.0, np.ones(ACROSS), 1.0, beta, tab)
    k = float(tab[1, 1]) ** (5.0 / 3.0)
    # the local radius of each pixel, for the shear: repeat the window sums directly (the function keeps them inside)
    d = np.full(ACROSS, h)
    per = np.full(ACROSS, px)
    per[0] += h
    per[-1] += h
    i = np.arange(ACROSS)
    w = beta * d / px
    r = np.empty(ACROSS)
    for t in range(ACROSS):
        nw = np.clip(1.0 - np.abs(i - t) / w[t], 0.0, None)
        r[t] = px * np.sum(d * nw) / np.sum(per * nw)
    share = 1.0 - float(np.sum(r * px)) / (b * h)
    return k, share


def k_strips(b: float, h: float) -> float:
    return b * h ** (5.0 / 3.0)


def k_section(b: float, h: float) -> float:
    return b * h * (b * h / (b + 2.0 * h)) ** (2.0 / 3.0)


def lansford() -> list[dict]:
    b, s0 = 5.0 * FT, 0.003
    out = []
    for table in ("lansford_mitchell_1949_T50_current_meter.csv", "lansford_mitchell_1949_T51_normal_depth_observations.csv"):
        for r in rows(table):
            xs, depth = r["xs_as_printed"], r["normal_depth_ft"]
            if not depth:
                continue
            h_ft = float(depth)
            if xs in ("2", "1,2"):
                group = "a (XS2)"  # XS1 is XS2 below 1.5 ft; every '1,2' run is below it
            elif xs == "4":
                group = "b (XS4)"
            else:
                continue
            h, q = h_ft * FT, float(r["Q_cfs"]) * CFS
            k_lr, _ = lhrm(b, h)
            run = {"table": table.split("_")[3], "xs": xs, "group": group, "h_m": h, "Q_m3s": q, "b_over_h": b / h}
            for law, k in (("strips", k_strips(b, h)), ("local_radius", k_lr), ("section", k_section(b, h))):
                run[f"n_{law}"] = k * s0**0.5 / q
            out.append(run)
    return out


def knight() -> list[dict]:
    s0 = 9.66e-4
    out = []
    for r in rows("knight_et_al_1984_rectangular_smooth_via_chlebek2009_T3-1.csv"):
        b, h = float(r["B_mm"]) / 1000.0, float(r["H_mm"]) / 1000.0
        _k, share = lhrm(b, h)
        out.append({"exp": int(r["exp"]), "B_m": b, "h_m": h, "b_over_h": b / h, "measured": float(r["pct_SF_walls"]) / 100.0,
                    "strips": 0.0, "local_radius": share, "section": 2.0 * h / (b + 2.0 * h)})
    return out


def summary(runs: list[dict]) -> dict:
    res = {}
    for g in sorted({r["group"] for r in runs}):
        sel = [r for r in runs if r["group"] == g]
        x = np.log(np.array([r["b_over_h"] for r in sel]))
        res[g] = {"runs": len(sel), "b_over_h": [min(r["b_over_h"] for r in sel), max(r["b_over_h"] for r in sel)]}
        for law in ("strips", "local_radius", "section"):
            n = np.array([r[f"n_{law}"] for r in sel])
            slope = float(np.polyfit(x, n / n.mean(), 1)[0])
            narrow = n[np.exp(x) < 4.0].mean() if np.any(np.exp(x) < 4.0) else np.nan
            wide = n[np.exp(x) > 8.0].mean() if np.any(np.exp(x) > 8.0) else np.nan
            res[g][law] = {"mean": float(n.mean()), "cv": float(n.std(ddof=1) / n.mean()), "slope_per_ln_bh": slope,
                           "narrow_over_wide": float(narrow / wide)}
    return res


if __name__ == "__main__":
    lm = lansford()
    s = summary(lm)
    print("Lansford & Mitchell 1949: the n each law needs; one roughness on the whole perimeter")
    for g, v in s.items():
        print(f"  {g}: {v['runs']} runs, b/h {v['b_over_h'][0]:.1f} to {v['b_over_h'][1]:.1f}")
        for law in ("strips", "local_radius", "section"):
            t = v[law]
            print(f"    {law:13s} n mean {t['mean']:.4f}  scatter (CV) {100 * t['cv']:4.1f} %  trend {100 * t['slope_per_ln_bh']:+5.1f} % per ln(b/h)  narrow (b/h<4) / wide (b/h>8) {t['narrow_over_wide']:.3f}")
    kn = knight()
    print("\nKnight, Demetriou & Hamed 1984, smooth: the walls' share of the shear force, measured against each law")
    err = {law: np.array([r[law] - r["measured"] for r in kn]) for law in ("strips", "local_radius", "section")}
    for r in kn:
        print(f"  exp {r['exp']:2d}  B {r['B_m'] * 1000:4.0f} mm  b/h {r['b_over_h']:6.2f}  measured {100 * r['measured']:5.1f} %  local radius {100 * r['local_radius']:5.1f} %  section {100 * r['section']:5.1f} %")
    for law, e in err.items():
        print(f"  {law:13s} mean error {100 * e.mean():+6.1f} points, RMS {100 * np.sqrt(np.mean(e * e)):5.1f} points")
    (HERE / "flume_test.json").write_text(json.dumps({"lansford_mitchell": {"summary": s, "runs": lm}, "knight_1984": kn}, indent=1), encoding="utf-8")
