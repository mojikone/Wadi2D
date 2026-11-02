import sys, shutil, tempfile, pathlib, numpy as np
from hecdss import HecDss
def load(f):
    d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(f, d/"r.dss"); r = HecDss(str(d/"r.dss"))
    out = {}
    for n in [str(p) for p in r.get_catalog().items]:
        if "/PRECIP-INC/" in n: out[n.split("/")[2]] = np.asarray(r.get(n).values, float)*25.4
    r.close(); return out
a, b = load(sys.argv[1]), load(sys.argv[2])
for k in a: print(k, "base total %.3f mm, clipped-frames total %.3f mm, max hourly difference %.6f mm" % (np.nansum(a[k]), np.nansum(b[k]), np.nanmax(np.abs(a[k]-b[k]))))
