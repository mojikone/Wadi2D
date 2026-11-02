import sys, shutil, tempfile, pathlib, numpy as np
from hecdss import HecDss
src = sys.argv[1]
d = pathlib.Path(tempfile.mkdtemp()); c = d / "x.dss"; shutil.copy2(src, c)
h = HecDss(str(c))
cat = h.get_catalog()
print("catalog items", [(i.A,i.B,i.C,i.D,i.E,i.F, type(i).__name__) for i in cat.items][:4])
paths = cat.uncondensed_paths
print("uncondensed", paths[:4], len(paths))
g = h.get(paths[int(sys.argv[2]) if len(sys.argv)>2 else 0])
for k,v in vars(g).items():
    if k in ('data','rangeLimitTable','numberEqualOrExceedingRangeLimit','location_info'): continue
    print(f"{k:24}", repr(v)[:260])
np.set_printoptions(linewidth=140, precision=3, suppress=True)
print(g.data.shape); print(g.data if g.data.size < 200 else g.data[:3,:6])
