"""Step 0: draw the inputs (domain, bank lines by drainage area, thalwegs, dam axis) and list the longest bank pairs.

usage: python s00_inputs.py
writes fig_00_inputs.png and inputs.json beside this script.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import HERE, bank_lines, dam_axis, domain, thalwegs

poly = domain()
banks = bank_lines()
thal = thalwegs()
axis = dam_axis()

fig, ax = plt.subplots(figsize=(16, 12))
x, y = poly.exterior.xy
ax.plot(x, y, color="0.3", lw=0.8, label="domain (20 m job)")
for t in thal:
    tx, ty = t["line"].xy
    ax.plot(tx, ty, color="deepskyblue", lw=0.6, alpha=0.8)
areas = np.array([b["area_km2"] for b in banks])
cmap = plt.get_cmap("viridis")
for b in banks:
    bx, by = b["line"].xy
    c = cmap(np.log10(b["area_km2"] + 1) / np.log10(areas.max() + 1))
    ax.plot(bx, by, color=c, lw=1.2)
    if b["area_km2"] >= 30:
        mid = b["line"].interpolate(0.5, normalized=True)
        ax.annotate(f"{b['fid']}{b['side'][0]}", (mid.x, mid.y), fontsize=7, color="k")
ax.plot(*axis.xy, color="red", lw=2.5, label="dam axis")
ax.set_aspect("equal")
ax.set_title("Faydh 01: W26 stream-bank lines coloured by drainage area (label fid+side where >= 30 km2), thalwegs blue")
ax.legend(loc="lower left")
fig.tight_layout()
fig.savefig(HERE / "fig_00_inputs.png", dpi=130)

# A zoom on the main gorge near the dam axis
ax.set_xlim(axis.centroid.x - 4500, axis.centroid.x + 1500)
ax.set_ylim(axis.centroid.y - 2500, axis.centroid.y + 2500)
for b in banks:
    if b["area_km2"] >= 10 and b["line"].intersects(
        __import__("shapely").box(axis.centroid.x - 4500, axis.centroid.y - 2500, axis.centroid.x + 1500, axis.centroid.y + 2500)
    ):
        mid = b["line"].interpolate(0.5, normalized=True)
        ax.annotate(f"{b['fid']}{b['side'][0]} {b['area_km2']:.0f}", (mid.x, mid.y), fontsize=8, color="darkred")
fig.savefig(HERE / "fig_00_inputs_zoom.png", dpi=130)

big = sorted(banks, key=lambda b: (-b["area_km2"], -b["length_m"]))
out = []
for b in big[:40]:
    ln = b["line"]
    out.append(
        {
            "fid": b["fid"],
            "side": b["side"],
            "area_km2": b["area_km2"],
            "length_m": round(b["length_m"], 1),
            "height_m": round(b["height_m"], 2),
            "start": [round(v, 1) for v in ln.coords[0]],
            "end": [round(v, 1) for v in ln.coords[-1]],
            "dist_to_axis_m": round(ln.distance(axis), 1),
            "nverts": len(ln.coords),
        }
    )
json.dump(out, open(HERE / "inputs.json", "w"), indent=1)
for o in out[:24]:
    print(o)
print("banks", len(banks), "thalwegs", len(thal), "domain km2", round(poly.area / 1e6, 3))
