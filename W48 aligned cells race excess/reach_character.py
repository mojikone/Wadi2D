"""What the reaches where the strip loses water have in common (W48): every 20 m along Faydh's main stem, from the
0.5 m DEM, the true thalweg (the lowest pixel within 40 m either side of the guide line, on the perpendicular), its
offset from the guide line the strip is built on, the bed slope of the true thalweg, and the wet width and depth of
the 2 m squares' steady surface; per 2 km bin beside the strip's level deficit from where_the_water_is.py.

    .venv\\Scripts\\python "W48 aligned cells race excess\\reach_character.py"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W47 face level carried to the face"))
import steady_surfaces as ss  # noqa: E402

from wadi2d.strips.banks import read_thalwegs  # noqa: E402
from wadi2d.strips.centres import chain_streams  # noqa: E402

RUNS = ROOT / "W47 face level carried to the face" / "depth_carry" / "steady"
W26 = ROOT / "W26 suggested breaklines" / "suggested" / "faydh" / "suggested_breaklines.gpkg"
OUT = Path(__file__).resolve().parent / "where_the_water_is"
HALF = 40.0
STEP = 20.0


def main() -> None:
    main_line = chain_streams(read_thalwegs(W26))[0]["line"]
    level2, ltr, _t = ss.final_lattice_level(RUNS / "sq2")
    s_all = np.arange(4000.0, 20000.0, STEP)
    rows = []
    with rasterio.open(ss.DEM) as dem:
        for s in s_all:
            p = np.asarray(main_line.interpolate(s).coords)[0]
            a = np.asarray(main_line.interpolate(s - 10.0).coords)[0]
            b = np.asarray(main_line.interpolate(s + 10.0).coords)[0]
            t = (b - a) / max(np.hypot(*(b - a)), 1e-9)
            n = np.array([-t[1], t[0]])
            offs = np.arange(-HALF, HALF + 0.25, 0.5)
            pts = p[None, :] + offs[:, None] * n[None, :]
            z = np.array([v[0] for v in dem.sample(pts.tolist())], np.float64)
            z[z > 1e30] = np.nan
            if not np.isfinite(z).any():
                continue
            k = int(np.nanargmin(z))
            col = ((pts[:, 0] - ltr.c) / ltr.a).astype(int)
            row = ((pts[:, 1] - ltr.f) / ltr.e).astype(int)
            ok = (row >= 0) & (row < level2.shape[0]) & (col >= 0) & (col < level2.shape[1])
            lev = np.full(offs.size, np.nan)
            lev[ok] = level2[row[ok], col[ok]]
            wet = np.isfinite(lev) & (lev - z > 0.05)
            rows.append({"s": float(s), "offset_m": float(offs[k]), "zbed": float(z[k]), "wet_width_m": float(wet.sum() * 0.5),
                         "depth_m": float(np.nanmax(lev - z)) if wet.any() else 0.0})
    zb = np.array([r["zbed"] for r in rows])
    sv = np.array([r["s"] for r in rows])
    slope = -np.gradient(zb, sv)
    for r, sl in zip(rows, slope, strict=True):
        r["slope"] = float(sl)
    deficit = {b["from_m"]: b for b in json.loads((OUT / "ce20.json").read_text())["along"]}
    print("bin km   guide offset |m| (median, 90th)   bed slope %   wet width m   depth m   strip pair level m")
    out = []
    for a0 in range(4000, 20000, 2000):
        m = (sv >= a0) & (sv < a0 + 2000)
        off = np.abs([r["offset_m"] for r, mm in zip(rows, m, strict=True) if mm])
        sl = slope[m]
        ww = np.array([r["wet_width_m"] for r, mm in zip(rows, m, strict=True) if mm])
        dp = np.array([r["depth_m"] for r, mm in zip(rows, m, strict=True) if mm])
        d = deficit.get(a0, {}).get("pair_level_m", float("nan"))
        out.append({"from_m": a0, "offset_median": float(np.median(off)), "offset_p90": float(np.percentile(off, 90)), "slope_median": float(np.median(sl)),
                    "wet_width_median": float(np.median(ww)), "depth_median": float(np.median(dp)), "pair_level_m": d})
        print(f"{a0 / 1000:4.0f}-{(a0 + 2000) / 1000:<3.0f}   {np.median(off):5.1f}, {np.percentile(off, 90):5.1f}            {100 * np.median(sl):5.2f}       {np.median(ww):6.1f}      {np.median(dp):5.2f}     {d:+.3f}")
    keys = ("offset_median", "offset_p90", "slope_median", "wet_width_median", "depth_median")
    lv = np.array([o["pair_level_m"] for o in out])
    print("\ncorrelation of the pair level deficit with each, over the 8 bins:")
    for key in keys:
        v = np.array([o[key] for o in out])
        print(f"  {key:18s} r = {np.corrcoef(v, lv)[0, 1]:+.2f}")
    (OUT / "reach_character.json").write_text(json.dumps({"stations": rows, "bins": out}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
