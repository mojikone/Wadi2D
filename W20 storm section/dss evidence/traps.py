import sys, shutil, tempfile, pathlib, numpy as np
from hecdss import HecDss
for f in sys.argv[1:]:
    d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(f, d/"x.dss")
    h = HecDss(str(d/"x.dss")); cat = h.get_catalog(); ps = cat.uncondensed_paths
    print("==", f[-14:], len(ps), "catalog-sorted?", ps == sorted(ps))
    for p in ps[:6]: print("  ", p)
    g = h.get(ps[len(ps)//2]); a = np.asarray(g.data, float)
    print("   mid: nulls", int((a < -1e30).sum()), "neg", int(((a<0)&(a>-1e30)).sum()), "max", np.nanmax(a), "isInterval", g.isInterval, "isTimeStamped", g.isTimeStamped, "tz", repr(g.timeZoneID), g.timeZoneRawOffset, "type", g.type, g.data_type)
    h.close()
