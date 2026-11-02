"""Why did HMS change the rain? Check the clipped file is right, then test which index HMS used for each frame."""
import sys, re, shutil, tempfile, pathlib, numpy as np
from hecdss import HecDss
grid, base, run, cellsf = sys.argv[1:5]
def cp(f):
    d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(f, d/"x.dss"); return HecDss(str(d/"x.dss"))
cells = {}; cur = None
for line in open(cellsf):
    m = re.match(r"SUBBASIN:\s*(\S+)", line)
    if m: cur = m.group(1); cells[cur] = []
    m = re.match(r"\s*GRIDCELL:\s*(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)", line)
    if m: cells[cur].append((int(m[1]), int(m[2]), float(m[4])))
g = cp(grid); b = cp(base); r = cp(run)
paths = g.get_catalog().uncondensed_paths
def end(p):
    m = re.search(r"/(\d\d)JAN1996:(\d\d)(\d\d)/(\d\d)JAN1996:(\d\d)(\d\d)/", p)
    return np.datetime64(f"1996-01-{m[4]}T00:00") + np.timedelta64(int(m[5]), "h")
rec = {end(p): g.get(p) for p in paths}
order = sorted(rec)
first = rec[order[0]]
print("first frame in time: ll", first.lowerLeftCellX, first.lowerLeftCellY, "shape", first.numberOfCellsX, first.numberOfCellsY)
cat_first = g.get(paths[0]); print("first in catalogue: ll", cat_first.lowerLeftCellX, cat_first.lowerLeftCellY, cat_first.numberOfCellsX, cat_first.numberOfCellsY)
def series(h, sub):
    n = next(str(p) for p in h.get_catalog().items if f"/{sub}/PRECIP-INC/" in str(p)); ts = h.get(n)
    return np.array(ts.times, "datetime64[m]"), np.asarray(ts.values, float)*25.4
for sub, cl in cells.items():
    t, hms = series(r, sub); t0, truth = series(b, sub)
    area = np.array([c[2] for c in cl]); xs = np.array([c[0] for c in cl]); ys = np.array([c[1] for c in cl])
    right, kept_ll, kept_cat = [], [], []
    for tt, v, tv in zip(t, hms, truth):
        tt = np.datetime64(tt, "h").astype("datetime64[m]")
        k = next((o for o in order if o.astype("datetime64[m]") == tt), None)
        if k is None: continue
        f = rec[k]; a = np.asarray(f.data, float); a[a < -1e30] = 0
        def at(llx, lly):
            c = xs - llx; w = ys - lly
            ok = (c >= 0) & (c < a.shape[1]) & (w >= 0) & (w < a.shape[0])
            out = np.zeros(xs.size); out[ok] = a[w[ok], c[ok]]
            return (out*area).sum()/area.sum()
        right.append((tv, at(f.lowerLeftCellX, f.lowerLeftCellY)))
        kept_ll.append((v, at(first.lowerLeftCellX, first.lowerLeftCellY)))
        kept_cat.append((v, at(cat_first.lowerLeftCellX, cat_first.lowerLeftCellY)))
    right, kept_ll, kept_cat = map(np.array, (right, kept_ll, kept_cat))
    print(f"{sub}: clipped file read at each frame's own lower-left vs true rain: max diff {np.abs(right[:,0]-right[:,1]).max():.5f} mm")
    print(f"     HMS on clipped file vs its own frame read with the first frame's lower-left: max diff {np.abs(kept_ll[:,0]-kept_ll[:,1]).max():.5f} mm;  rms {np.sqrt(((kept_ll[:,0]-kept_ll[:,1])**2).mean()):.5f}")
