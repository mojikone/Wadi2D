import sys, pathlib, re, numpy as np, collections
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D")
from wadi2d.hms.dss import open_dss
from wadi2d.io.rain.dss_grid import read_dss_grid, _cut_to_rain, _depth, _stamp
from wadi2d.storm.rain_frames import RainSpec
f = pathlib.Path(sys.argv[1])
with open_dss(f) as dss:
    ps = dss.grid_pathnames()
    print("records", len(ps), "with E", sum(1 for p in ps if p.e))
    rows = []
    for p in ps:
        r = dss.read_grid(p)
        d = _depth(r, 60.0, "auto")
        wet = np.nan_to_num(d) > 0
        sides = (bool(wet[0].any()), bool(wet[-1].any()), bool(wet[:,0].any()), bool(wet[:,-1].any()))
        rows.append((_stamp(p.d, "x"), p.d, p.e, r.lower_left_x, r.lower_left_y, r.values.shape, r.cell_size, r.srs[:40], float(np.nanmax(d)), int(wet.sum()), sides, _cut_to_rain(d)))
rows.sort(key=lambda r: r[0])
for extent, group in sorted(collections.Counter((r[3], r[4], r[5], r[6], r[7]) for r in rows).items(), key=str):
    g = [r for r in rows if (r[3], r[4], r[5], r[6], r[7]) == extent]
    print("extent", extent, "n", group, "from", g[0][1], "to", g[-1][1], "E", repr(g[0][2]), "cut_to_rain true:", sum(r[11] for r in g), "wet any:", sum(r[9] > 0 for r in g), "max", max(r[8] for r in g))
same_time = [k for k, v in collections.Counter(r[0] for r in rows).items() if v > 1]
print("instants held by two domains:", len(same_time))
print("order by time (first 3 / where the extent changes):")
prev = None
for r in rows:
    key = r[5]
    if key != prev: print("  ", r[1], r[2], r[3], r[4], r[5], "sides", r[10], "max %.2f" % r[8])
    prev = key
for spec in (RainSpec(), RainSpec(interval_min=60.0)):
    try:
        fr = read_dss_grid(f, spec)
        print("READ", fr.depths.shape, "west", fr.west, "north", fr.north, "missing share %.3f" % fr.missing_share())
    except ValueError as e:
        print("REFUSED:", str(e)[:170])
