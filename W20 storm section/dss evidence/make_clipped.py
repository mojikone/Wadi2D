"""A copy of the real HRAP file with one wet hour clipped so that it covers only part of each subbasin."""
import sys, re, shutil, tempfile, pathlib, json, numpy as np
from hecdss import HecDss
from hecdss.gridded_data import GriddedData
src, cellsf, outs, info = sys.argv[1], sys.argv[2], sys.argv[3].split(","), sys.argv[4]
d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(src, d/"g.dss")
cells = {}; cur = None
for line in open(cellsf):
    m = re.match(r"SUBBASIN:\s*(\S+)", line)
    if m: cur = m.group(1); cells[cur] = []
    m = re.match(r"\s*GRIDCELL:\s*(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)", line)
    if m: cells[cur].append((int(m[1]), int(m[2]), float(m[4])))
h = HecDss(str(d/"g.dss")); paths = h.get_catalog().uncondensed_paths
recs = {p: h.get(p) for p in paths}
# wettest hour over the basin in the run window
def basin_rain(g):
    a = np.asarray(g.data, float); return sum(a[y-g.lowerLeftCellY, x-g.lowerLeftCellX]*ar for s in cells.values() for x, y, ar in s)
window = [p for p in paths if re.search(r"/(17|18|19|20|21)JAN1996:", p)]
hot = max(window, key=lambda p: basin_rain(recs[p]))
print("wettest hour", hot)
g = recs[hot]; a = np.asarray(g.data, float)
xs = [c[0] for s in cells.values() for c in s]; ys = [c[1] for s in cells.values() for c in s]
print("basin box x", min(xs), max(xs), "y", min(ys), max(ys))
# Keep the western and southern part: cut through the middle of the basin box.
xcut = (min(xs)+max(xs))//2; ycut = (min(ys)+max(ys))//2
nx, ny = xcut - g.lowerLeftCellX + 1, ycut - g.lowerLeftCellY + 1
sub = a[:ny, :nx].copy(); sub[sub < -1e30] = np.nan
report = {"hot": hot, "xcut": xcut, "ycut": ycut, "expect": {}}
for name, cl in cells.items():
    A = sum(c[2] for c in cl)
    inside = [(x, y, ar) for x, y, ar in cl if x <= xcut and y <= ycut]
    Ain = sum(c[2] for c in inside)
    S = sum(a[y-g.lowerLeftCellY, x-g.lowerLeftCellX]*ar for x, y, ar in inside)
    Sfull = sum(a[y-g.lowerLeftCellY, x-g.lowerLeftCellX]*ar for x, y, ar in cl)
    report["expect"][name] = {"cells_in": len(inside), "cells": len(cl), "full_mm": Sfull/A, "outside_zero_mm": S/A, "outside_missing_mean_mm": (S/Ain if Ain else None)}
json.dump(report, open(info, "w"), indent=1); print(json.dumps(report["expect"], indent=0))
for out in outs:
    o = HecDss(out)
    for p, r in recs.items():
        arr = np.asarray(r.data, float).copy(); arr[arr < -1e30] = np.nan
        ll = (r.lowerLeftCellX, r.lowerLeftCellY)
        if p == hot:
            arr = sub; 
        g2 = GriddedData.create(path=p, type=r.type, dataType=r.data_type, lowerLeftCellX=ll[0], lowerLeftCellY=ll[1], numberOfCellsX=arr.shape[1], numberOfCellsY=arr.shape[0],
            dataUnits=r.dataUnits, dataSource=r.dataSource, srsName=r.srsName, srsDefinition=r.srsDefinition, timeZoneID=r.timeZoneID, cellSize=r.cellSize, nullValue=r.nullValue, data=arr)
        s = o.put(g2)
        if s != 0: print("put failed", p, s)
    o.close()
h.close()
