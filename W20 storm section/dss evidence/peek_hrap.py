import sys, numpy as np
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D")
from hecdss import HecDss
import shutil, tempfile, pathlib
src = sys.argv[1]
d = pathlib.Path(tempfile.mkdtemp())
c = d / "x.dss"; shutil.copy2(src, c)
h = HecDss(str(c))
cat = h.get_catalog()
print(len(cat.items), [str(type(i)) for i in cat.items[:1]])
names = [i.A+"/"+i.B+"/"+i.C+"/"+i.D+"/"+i.E+"/"+i.F for i in cat.items]
print(names[:5], names[-3:])
print(cat.uncondensed_paths[:3] if hasattr(cat,'uncondensed_paths') else None)
p = cat.uncondensed_paths[0]
g = h.get(p)
for k,v in vars(g).items():
    if k in ('data','rangeLimitTable','numberEqualOrExceedingRangeLimit','location_info'): continue
    print(k, repr(v)[:300])
print(g.data.shape, np.nanmin(g.data), np.nanmax(g.data))
h.close()
