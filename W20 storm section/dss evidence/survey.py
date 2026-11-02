import sys, shutil, tempfile, pathlib, numpy as np, collections
from hecdss import HecDss
src = sys.argv[1]
d = pathlib.Path(tempfile.mkdtemp()); c = d / "x.dss"; shutil.copy2(src, c)
h = HecDss(str(c)); cat = h.get_catalog()
print("recordTypes", collections.Counter(getattr(cat, "recordTypes", [])))
paths = cat.uncondensed_paths
print(paths[:3]); print(paths[-3:])
ext = collections.Counter(); nulls = collections.Counter(); units=collections.Counter(); kinds=collections.Counter()
rows = []
for p in paths:
    g = h.get(p)
    a = np.asarray(g.data, float)
    ext[(g.lowerLeftCellX, g.lowerLeftCellY, g.numberOfCellsX, g.numberOfCellsY)] += 1
    nulls[g.nullValue] += 1; units[g.dataUnits] += 1; kinds[(g.type, g.data_type, g.isInterval, g.isTimeStamped)] += 1
    wet = a > 0
    edge = (wet[0].any(), wet[-1].any(), wet[:,0].any(), wet[:,-1].any())
    rows.append((p, a.shape, float(np.nanmax(a)), int(wet.sum()), int((a < -1e30).sum()), int((a<0).sum()), edge))
print("extents", ext.most_common(8)); print("null", nulls); print("units", units); print("kinds (type,dataType,isInterval,isTimeStamped)", kinds)
for r in rows[:6]: print(r)
print("records with very-negative cells:", sum(r[4] > 0 for r in rows), " any negative:", sum(r[5]>0 for r in rows), " all dry:", sum(r[3]==0 for r in rows))
h.close()
