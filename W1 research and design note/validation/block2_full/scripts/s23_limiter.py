"""What sets the time step: the cells with the largest |u| + sqrt(g d) in the max maps, and what lies under them."""
import sys
import numpy as np, rasterio
run = sys.argv[1]
d = rasterio.open(f"runs/{run}/maps/max_depth.tif"); D = d.read(1, masked=True).filled(0)
S = rasterio.open(f"runs/{run}/maps/max_speed.tif").read(1, masked=True).filled(0)
H = rasterio.open(f"runs/{run}/maps/max_mean_depth.tif").read(1, masked=True).filled(0)
L = rasterio.open(f"runs/{run}/maps/max_level.tif").read(1, masked=True).filled(0)
t = d.transform
w = np.sqrt(9.81 * D)
print("cells depth>10 m:", (D > 10).sum(), ">20:", (D > 20).sum(), ">30:", (D > 30).sum(), "speed>=24:", (S >= 24).sum(), "speed>15:", (S > 15).sum())
idx = np.argsort(w.ravel())[-10:][::-1]
for k in idx:
    j, i = np.unravel_index(k, D.shape)
    print(f"d {D[j,i]:6.2f} mean depth {H[j,i]:6.2f} speed {S[j,i]:5.2f} level {L[j,i]:7.2f} at {t.c+(i+.5)*t.a:.0f} {t.f+(j+.5)*t.e:.0f}")
idx = np.argsort((S).ravel())[-5:][::-1]
for k in idx:
    j, i = np.unravel_index(k, D.shape)
    print(f"fast: d {D[j,i]:6.2f} mean depth {H[j,i]:6.2f} speed {S[j,i]:5.2f} at {t.c+(i+.5)*t.a:.0f} {t.f+(j+.5)*t.e:.0f}")
