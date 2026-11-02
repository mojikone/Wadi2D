"""Every monitoring station within 40 km of the Block 2 box, from the ministry KMZ and wadigauge.dbf. Read only."""
import json
from pathlib import Path

import numpy as np
import shapefile

HERE = Path(__file__).resolve().parent
B = Path(r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\03-Hydrology")
s = json.loads((HERE / "stations_all.json").read_text(encoding="utf-8"))
print(len(s))
keys = list(next(iter(s.values())).keys())
print(keys)
box = (418000, 2699000, 445000, 2741000)


def dist(x, y):
    dx = max(box[0] - x, 0, x - box[2])
    dy = max(box[1] - y, 0, y - box[3])
    return np.hypot(dx, dy) / 1e3


rows = sorted((dist(v["x"], v["y"]), k, v) for k, v in s.items())
for d, k, v in rows:
    if d > 40:
        break
    print(f"{d:5.1f} {k} {v.get('LONG_NAME') or v.get('LOCAL_ID')} type={v.get('SITE_TYPE')} {round(v['x'])} {round(v['y'])} catch={v.get('CATCHMENT')}")

r = shapefile.Reader(str(B / "Meteorology" / "Layers" / "wadigauge.shp"))
names = [f[0] for f in r.fields[1:]]
print(names, len(r))
rec = []
for sr in r.iterShapeRecords():
    d = sr.record.as_dict()
    x, y = sr.shape.points[0]
    rec.append((x, y, d))
print(rec[0])
out = []
for x, y, d in rec:
    if x < 1000:  # lon lat
        from pyproj import Transformer

        x, y = Transformer.from_crs(4326, 32640, always_xy=True).transform(x, y)
    dd = dist(x, y)
    if dd < 40:
        out.append((dd, d))
for dd, d in sorted(out, key=lambda a: a[0]):
    print(round(dd, 1), {k: d[k] for k in list(d)[:8]})
