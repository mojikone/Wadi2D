"""From the 6-hourly snapshots of a run: which cell has the largest |u| + sqrt(g d) with d above h_cfl."""
import sys
import h5py, numpy as np
run = sys.argv[1]
f = h5py.File(f"runs/{run}/results.h5", "r")
print(list(f.keys()))
def walk(n, o):
    if isinstance(o, h5py.Dataset) and o.ndim >= 2: print(n, o.shape)
g = f["maps"] if "maps" in f else f
names = sorted(g.keys())
print(names[:12])
for n in names:
    o = g[n]
    if not isinstance(o, h5py.Group) or "depth" not in o: continue
    d = o["depth"][()]; s = o["speed"][()]; h = o["mean_depth"][()]
    w = np.where(d > 0.01, s + np.sqrt(9.81 * np.maximum(d, 0)), 0)
    j, i = np.unravel_index(np.argmax(w), w.shape)
    fast = np.where(d > 0.01, s, 0); jf, jf2 = np.unravel_index(np.argmax(fast), w.shape)
    print(n, f"max wave {w[j,i]:.2f} at (j{j},i{i}) d {d[j,i]:.3f} h {h[j,i]:.4f} s {s[j,i]:.2f} | fastest {fast[jf,jf2]:.2f} d {d[jf,jf2]:.3f} h {h[jf,jf2]:.5f} | dt implied {0.45*20/max(w[j,i],1e-3):.3f}")
