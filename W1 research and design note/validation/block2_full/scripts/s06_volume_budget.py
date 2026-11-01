"""What the per-cell CN does to the volume: weighted-Q on the 20 m cell centres against HMS's composite CN.

Exact arithmetic on the rain total, no solver. Writes volume_budget.json.
"""
import json
import sys

import numpy as np
import rasterio
import rasterio.features

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import CN, HMS, OUT, SITES, UPSTREAM, polygons, storm
from lumped_ref import run_at, stats

from wadi2d.hms import load_basin
from wadi2d.storm.arf import ArfTable

polys = polygons()
b = load_basin(HMS / "Basin_1.basin")
s = storm()
arf = ArfTable(np.array(s["arf"]["areas_km2"]), np.array(s["arf"]["factors"]))


def excess(p, cn, ia=None):
    S = (1000.0 / cn - 10.0) * 25.4
    Ia = 0.2 * S if ia is None else ia
    e = np.maximum(p - Ia, 0.0)
    return e**2 / (e + S)


out = {}
with rasterio.open(CN) as src:
    for site, area in SITES.items():
        P = s["depth_mm"] * arf.factor(area)
        rows = []
        vol_cell = vol_comp = a_tot = 0.0
        for n in UPSTREAM[site]:
            poly = polys[n]
            w = rasterio.windows.from_bounds(*poly.bounds, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=w, masked=True)
            t = src.window_transform(w)
            m = rasterio.features.geometry_mask([poly], a.shape, t, invert=True) & ~np.ma.getmaskarray(a)
            cn = a.data[m].astype(float)
            e = b.subbasins[n]
            A = e.area
            comp = float(excess(P, e.loss.curve_number, e.loss.initial_abstraction))
            cell = float(excess(P, cn).mean())
            mean_cn = float(cn.mean())
            mean_cn_exc = float(excess(P, mean_cn))
            rows.append({"name": n, "A": A, "hms_cn": e.loss.curve_number, "raster_mean_cn": mean_cn, "comp_mm": comp,
                         "cell_mm": cell, "cn_min": float(cn.min()), "cn_max": float(cn.max()),
                         "cn_std": float(cn.std())})
            vol_cell += cell * A * 1e3
            vol_comp += comp * A * 1e3
            a_tot += A
        lumped = stats(run_at(area).outflow[site])
        out[site] = {"P_mm": P, "A": a_tot, "vol_cell_m3": vol_cell, "vol_comp_m3": vol_comp,
                     "ratio": vol_cell / vol_comp, "lumped": lumped, "subbasins": rows}
        print(site, f"P {P:.1f} comp {vol_comp/1e6:.3f} Mm3, per cell {vol_cell/1e6:.3f} Mm3, ratio {vol_cell/vol_comp:.4f}; lumped run vol {lumped['vol_m3']/1e6:.3f} peak {lumped['peak']:.1f} t {lumped['t_h']:.2f}")
        for r in rows:
            print("   ", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
(OUT / "volume_budget.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
