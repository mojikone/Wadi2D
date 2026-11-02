"""Rebuild HMS's subbasin rain from the raw hecdss array: which row order and index offset does HMS itself use?"""
import sys, shutil, tempfile, pathlib, re, numpy as np
from hecdss import HecDss
base = pathlib.Path(sys.argv[1]); cells_file = pathlib.Path(sys.argv[2])
d = pathlib.Path(tempfile.mkdtemp())
shutil.copy2(base/"hrap.dss", d/"g.dss"); shutil.copy2(base/"jan96.dss", d/"r.dss")
# cells per subbasin
cells = {}; cur = None
for line in cells_file.read_text().splitlines():
    m = re.match(r"SUBBASIN:\s*(\S+)", line)
    if m: cur = m.group(1); cells[cur] = []
    m = re.match(r"\s*GRIDCELL:\s*(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)", line)
    if m: cells[cur].append((int(m[1]), int(m[2]), float(m[4])))
print({k: len(v) for k, v in cells.items()})
g = HecDss(str(d/"g.dss")); r = HecDss(str(d/"r.dss"))
rc = r.get_catalog()
names = [str(p) for p in rc.items]
print([n for n in names if "PRECIP" in n][:8])
def stamp(s):
    m = re.match(r"(\d\d)([A-Z]{3})(\d{4}):(\d{4})", s)
    day = np.datetime64(f"{m[3]}-{ {'JAN':'01'}[m[2]] }-{m[1]}", "m")
    return day + np.timedelta64(int(m[4][:2]), "h") + np.timedelta64(int(m[4][2:]), "m")
stack = {}
for p in g.get_catalog().uncondensed_paths:
    q = p.split("/"); gd = g.get(p)
    a = np.asarray(gd.data, float); a[a < -1e30] = np.nan
    stack[stamp(q[5])] = a
ll = (gd.lowerLeftCellX, gd.lowerLeftCellY); ny, nx = a.shape
print("ll", ll, "shape", a.shape, "frames", len(stack))
for sub, cl in cells.items():
    path = next((n for n in names if f"/{sub}/PRECIP-INC/" in n.upper()), None)
    if path is None: print("no result for", sub); continue
    ts = r.get(path)
    t = np.array(ts.times, dtype="datetime64[m]"); v = np.asarray(ts.values, float)
    mmv = v*25.4 if str(ts.units).upper().startswith("IN") else v
    print(f"\nsubbasin {sub}: {path} units {ts.units} n={v.size} total {np.nansum(mmv):.3f} mm, {len(cl)} cells")
    area = np.array([c[2] for c in cl]); xs = np.array([c[0] for c in cl]); ys = np.array([c[1] for c in cl])
    keep = [i for i, tt in enumerate(t) if tt in stack]
    rain = np.stack([stack[t[i]] for i in keep])
    obs = mmv[keep]
    results = []
    for flip in (False, True):
        for oy in range(-3, 4):
            for ox in range(-3, 4):
                col = xs - ll[0] + ox
                row = ys - ll[1] + oy
                if flip: row = ny - 1 - row   # the alternative: stored row 0 is the north row
                if (row < 0).any() or (row >= ny).any() or (col < 0).any() or (col >= nx).any(): continue
                est = (rain[:, row, col] * area).sum(1) / area.sum()
                err = np.nanmax(np.abs(est - obs)); rms = np.sqrt(np.nanmean((est - obs)**2))
                results.append((rms, err, flip, ox, oy, np.nansum(est)))
    results.sort(key=lambda r: r[0])
    for r_ in results[:3]: print("  rms %.5f mm  max %.5f mm  stored-row-0-north=%s  ox=%d oy=%d  total %.3f" % r_)
    wrong = [x for x in results if x[2] and x[3] == 0 and x[4] == 0]
    if wrong: print("  the north-first reading at zero offset: rms %.5f mm  max %.5f  total %.3f" % (wrong[0][0], wrong[0][1], wrong[0][5]))
g.close(); r.close()
