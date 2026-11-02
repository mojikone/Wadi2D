"""Shift tests tile by tile, W7 inside its own 2D area, and what kind of pixel the misses are. 5 m pixels, 0.3 m, his perimeter."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
import shapely
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
z = np.load(HERE / "layers_5m.npz")
his, w2, w7, mask = z["his"], z["w2"], z["w7"], z["mask"]
t = rasterio.Affine(*z["t"])
hills = np.load(HERE / "hills_mask.npy")
a = np.nan_to_num(his, nan=-1.0) >= 0.3
b = np.nan_to_num(w2, nan=-1.0) >= 0.3
out: dict = {}


def F(a, b, m):
    both = (a & b & m).sum()
    o1 = (a & ~b & m).sum()
    o2 = (~a & b & m).sum()
    return float(both / max(both + o1 + o2, 1)), both * 25e-6, o1 * 25e-6, o2 * 25e-6


# tile shifts
T = 400  # 2 km
rows = []
for j0 in range(0, a.shape[0] - T, T):
    for i0 in range(0, a.shape[1] - T, T):
        m = mask[j0 : j0 + T, i0 : i0 + T]
        aa, bb = a[j0 : j0 + T, i0 : i0 + T], b[j0 : j0 + T, i0 : i0 + T]
        if (aa & m).sum() * 25e-6 < 0.3:
            continue
        f0 = F(aa, bb, m)[0]
        best = (f0, 0, 0)
        for dj in range(-12, 13, 3):
            for di in range(-12, 13, 3):
                if dj == 0 and di == 0:
                    continue
                f1 = F(aa, np.roll(np.roll(bb, dj, 0), di, 1), m)[0]
                if f1 > best[0]:
                    best = (f1, di * 5, dj * 5)
        x = t.c + (i0 + T / 2) * 5
        y = t.f - (j0 + T / 2) * 5
        rows.append((x, y, f0, best[0], best[1], best[2], bool(hills[j0 + T // 2, i0 + T // 2])))
r = np.array(rows, float)
print("tiles", len(r), "median F no shift", np.median(r[:, 2]), "best shift", np.median(r[:, 3]), "median gain", np.median(r[:, 3] - r[:, 2]))
print("share of tiles whose best shift is over 30 m", (np.hypot(r[:, 4], r[:, 5]) > 30).mean(), "median shift m", np.median(np.hypot(r[:, 4], r[:, 5])))
print("mean shift dE, dN", r[:, 4].mean(), r[:, 5].mean())
out["tile_shift"] = {"tiles": len(r), "median_F": float(np.median(r[:, 2])), "median_F_best_shift": float(np.median(r[:, 3])), "median_shift_m": float(np.median(np.hypot(r[:, 4], r[:, 5]))), "mean_dE": float(r[:, 4].mean()), "mean_dN": float(r[:, 5].mean())}

# W7 in its own 2D area
lay = ROOT / "W7 plugin test" / "maps" / "layers"
dom = json.loads((lay / "domain.geojson").read_text(encoding="utf-8"))
sub = json.loads((lay / "subbasins.geojson").read_text(encoding="utf-8"))
print([f["properties"] for f in sub["features"]][:3])
from shapely.geometry import shape

D = shapely.union_all([shape(f["geometry"]) for f in dom["features"]])
L = shapely.union_all([shape(f["geometry"]) for f in sub["features"] if str(f["properties"].get("mode", "")).lower().startswith("lump")])
area2d = D.difference(L.buffer(0))
m7 = rasterio.features.geometry_mask([area2d], out_shape=a.shape, transform=t, invert=True) & mask
c = np.nan_to_num(w7, nan=-1.0) >= 0.3
for name, lyr in (("W7 hybrid", c), ("W2", b)):
    print(name, "inside W7's 2D area", np.round(F(a, lyr, m7), 3))
    out[f"{name} in W7 2D area"] = F(a, lyr, m7)
print("W7 2D area km2", m7.sum() * 25e-6)

# thin or broad: width of the missed patches
for name, miss in (("his only", a & ~b & mask), ("W2 only", b & ~a & mask)):
    dist = ndimage.distance_transform_edt(miss) * 5.0
    lab, n = ndimage.label(miss)
    area = ndimage.sum(miss, lab, range(1, n + 1)) * 25e-6
    width = ndimage.maximum(dist, lab, range(1, n + 1)) * 2.0
    for lo, hi in ((0, 20), (20, 60), (60, 200), (200, 1e6)):
        k = (width >= lo) & (width < hi)
        print(f"{name}: patches {lo}-{hi} m wide: {area[k].sum():.1f} km2 in {k.sum()}")
    out[name] = {f"{lo}-{hi}": float(area[(width >= lo) & (width < hi)].sum()) for lo, hi in ((0, 20), (20, 60), (60, 200), (200, 1e6))}
(HERE / "channels.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
