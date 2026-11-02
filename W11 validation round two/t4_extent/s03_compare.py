"""F by threshold and zone, whole-map shifts, and a picture. Same mask, same threshold on both layers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio.features
import rasterio.transform
import shapely

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import polygons  # noqa: E402

HERE = Path(__file__).resolve().parent
z = np.load(HERE / "layers_5m.npz")
his, w2, w7, mask = z["his"], z["w2"], z["w7"], z["mask"]
t = rasterio.Affine(*z["t"])
shape = his.shape
hills_poly = shapely.union_all([p.buffer(5.0) for p in polygons().values()])
hills = rasterio.features.geometry_mask([hills_poly], out_shape=shape, transform=t, invert=True)
np.save(HERE / "hills_mask.npy", hills)
ZONES = {"all": mask, "hills (HMS subbasins)": mask & hills, "plain (below them)": mask & ~hills}
print({k: round(v.sum() * 25e-6, 1) for k, v in ZONES.items()})


def f(a, b, m):
    both = (a & b & m).sum()
    oa = (a & ~b & m).sum()
    ob = (~a & b & m).sum()
    return {"F": float(both / max(both + oa + ob, 1)), "both_km2": both * 25e-6, "his_only_km2": oa * 25e-6, "other_only_km2": ob * 25e-6}


res = {}
for th in (0.05, 0.1, 0.3, 0.5, 1.0, 2.0):
    a = np.nan_to_num(his, nan=-1.0) >= th
    for name, lay in (("W2", w2), ("W7", w7)):
        b = np.nan_to_num(lay, nan=-1.0) >= th
        for zn, m in ZONES.items():
            r = f(a, b, m)
            res[f"{name}|{zn}|{th}"] = r
            print(f"{name:3s} {zn:24s} >={th:4.2f}: F {r['F']:.3f} both {r['both_km2']:7.1f} his {r['his_only_km2']:7.1f} other {r['other_only_km2']:7.1f}")

# depth distributions
for name, lay in (("his", his), ("W2", w2), ("W7", w7)):
    v = lay[mask & np.isfinite(lay)]
    print(name, "wet km2", v.size * 25e-6, "pct 1,10,50,90,99", np.round(np.percentile(v, [1, 10, 50, 90, 99]), 3))

# whole-map shift of W2 against his layer, plain, 0.3 m, in steps of 10 m
a = np.nan_to_num(his, nan=-1.0) >= 0.3
b = np.nan_to_num(w2, nan=-1.0) >= 0.3
m = ZONES["plain (below them)"]
best = []
for dj in range(-8, 9, 2):
    for di in range(-8, 9, 2):
        bb = np.roll(np.roll(b, dj, axis=0), di, axis=1)
        best.append((f(a, bb, m)["F"], di * 5, -dj * 5))
best.sort(reverse=True)
print("best shifts (F, dE m, dN m)", best[:5], "no shift", [x for x in best if x[1] == 0 and x[2] == 0])
res["shifts_top"] = best[:5]

(HERE / "compare.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

k = 8
ny, nx = shape[0] // k, shape[1] // k


def block(x):
    return x[: ny * k, : nx * k].reshape(ny, k, nx, k).any(axis=(1, 3))


A, B = block(a & mask), block(b & mask)
img = np.ones((ny, nx, 3))
img[A & ~B] = (0.1, 0.3, 0.9)
img[B & ~A] = (0.9, 0.2, 0.1)
img[A & B] = (0.1, 0.1, 0.1)
fig, ax = plt.subplots(1, 1, figsize=(13, 12))
ext = (t.c, t.c + nx * k * 5, t.f - ny * k * 5, t.f)
ax.imshow(img, extent=ext, interpolation="nearest")
x, y = (hills_poly.exterior.xy if hills_poly.geom_type == "Polygon" else max(hills_poly.geoms, key=lambda g: g.area).exterior.xy)
ax.plot(x, y, color="#2a8f2a", lw=0.8)
ax.set_title("Depth >= 0.3 m, 40 m blocks. Black both, blue his only, red Wadi2D full-extent only. Green: HMS subbasins")
plt.tight_layout()
plt.savefig(HERE / "fig_extent_w2.png", dpi=75)
