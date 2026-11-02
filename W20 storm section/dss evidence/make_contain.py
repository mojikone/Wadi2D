"""Every wet frame clipped to its own rectangle, smaller than the file's and different per frame, with every basin cell kept inside."""
import sys, re, shutil, tempfile, pathlib, numpy as np
from hecdss import HecDss
from hecdss.gridded_data import GriddedData
src, cellsf, out = sys.argv[1:4]
d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(src, d/"g.dss")
xs, ys = [], []
for line in open(cellsf):
    m = re.match(r"\s*GRIDCELL:\s*(\d+)\s+(\d+)", line)
    if m: xs.append(int(m[1])); ys.append(int(m[2]))
h = HecDss(str(d/"g.dss")); o = HecDss(out)
n = 0
for i, p in enumerate(h.get_catalog().uncondensed_paths):
    r = h.get(p); a = np.asarray(r.data, float).copy(); a[a < -1e30] = np.nan
    # Rectangle that holds the basin box, with a margin that changes frame by frame.
    x0 = min(xs) - 3 - i % 5; x1 = max(xs) + 3 + i % 7; y0 = min(ys) - 3 - i % 4; y1 = max(ys) + 3 + i % 6
    c0, c1 = x0 - r.lowerLeftCellX, x1 - r.lowerLeftCellX + 1; r0, r1 = y0 - r.lowerLeftCellY, y1 - r.lowerLeftCellY + 1
    sub = a[r0:r1, c0:c1]; n += 1
    s = o.put(GriddedData.create(path=p, type=r.type, dataType=r.data_type, lowerLeftCellX=x0, lowerLeftCellY=y0, numberOfCellsX=sub.shape[1], numberOfCellsY=sub.shape[0],
        dataUnits=r.dataUnits, dataSource=r.dataSource, srsName=r.srsName, srsDefinition=r.srsDefinition, timeZoneID=r.timeZoneID, cellSize=r.cellSize, nullValue=r.nullValue, data=sub))
print("frames clipped", n)
o.close(); h.close()
