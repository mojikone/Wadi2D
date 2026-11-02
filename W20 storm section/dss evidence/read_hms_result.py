import sys, json, shutil, tempfile, pathlib, re, numpy as np
from hecdss import HecDss
for v, f in (("yes", sys.argv[1]), ("no", sys.argv[2])):
    if not pathlib.Path(f).exists(): print(v, "no result file"); continue
    d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(f, d/"r.dss")
    r = HecDss(str(d/"r.dss")); ex = json.load(open(sys.argv[3]))
    m = re.search(r"/(\d\d)JAN1996:(\d\d)00/(\d\d)JAN1996:(\d\d)00/", ex["hot"]); end = np.datetime64(f"1996-01-{m[3]}T{m[4]}:00")
    names = [str(p) for p in r.get_catalog().items]
    print("== missing to default:", v)
    for sub, e in ex["expect"].items():
        p = next(n for n in names if f"/{sub}/PRECIP-INC/" in n)
        ts = r.get(p); t = np.array(ts.times, "datetime64[m]"); val = np.asarray(ts.values, float)*(25.4 if str(ts.units).upper().startswith("IN") else 1)
        got = val[t == end]
        print(f"  {sub:4} cells {e['cells_in']:3}/{e['cells']:3}  HMS {got[0]:.4f} mm | outside=0 {e['outside_zero_mm']:.4f} | outside=missing {e['outside_missing_mean_mm'] if e['outside_missing_mean_mm'] is None else round(e['outside_missing_mean_mm'],4)} | unclipped {e['full_mm']:.4f}")
    r.close()
