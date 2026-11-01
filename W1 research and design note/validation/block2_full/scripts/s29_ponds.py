"""Where water stands 18 h after the storm: the largest ponds in the last snapshot of a run."""
import sys
import h5py, numpy as np
from scipy import ndimage
import json
run = sys.argv[1]
f = h5py.File(f"runs/{run}/results.h5", "r")
last = sorted(f["maps"].keys())[-1]
h = f["maps"][last]["mean_depth"][()]
x0, y0 = f.attrs.get("x0"), f.attrs.get("y0")
print(last, "attrs", dict(list(f.attrs.items())[:8]) if False else "", "total Mm3", h.sum()*400/1e6)
m = h > 0.2
lab, n = ndimage.label(m)
vol = ndimage.sum(h, lab, np.arange(1, n+1))*400
idx = np.argsort(vol)[::-1][:8]
print("cells>0.2 m:", m.sum(), "components", n, "their volume Mm3", vol.sum()/1e6)
import rasterio
t = rasterio.open(f"runs/{run}/maps/max_depth.tif").transform
for k in idx:
    jj, ii = np.nonzero(lab == k+1)
    print(f"pond vol {vol[k]/1e6:.3f} Mm3 area {jj.size*400/1e6:.3f} km2 max h {h[jj,ii].max():.1f} at {t.c+(ii.mean()+.5)*t.a:.0f} {t.f+(jj.mean()+.5)*t.e:.0f}")
