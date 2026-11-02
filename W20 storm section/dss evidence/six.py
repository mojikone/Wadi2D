import sys, pathlib, collections, numpy as np
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D")
from wadi2d.hms.dss import open_dss
from wadi2d.io.rain.dss_grid import read_dss_grid, dss_choices
from wadi2d.storm.rain_frames import RainSpec
for n in sys.argv[1:]:
    f = pathlib.Path(n); print("==", f.name, "version", open(f, "rb").read(20)[16:20])
    with open_dss(f) as d:
        ps = d.grid_pathnames(); ext = collections.Counter(); null = collections.Counter(); units = collections.Counter()
        for p in ps:
            r = d.read_grid(p); ext[(r.lower_left_x, r.lower_left_y) + r.values.shape] += 1; null[r.null_value] += 1; units[r.units] += 1
    print("  records", len(ps), "first", ps[0] if ps else None); print("  extents", ext.most_common(4), "distinct", len(ext), "units", dict(units), "null", dict(null))
    print("  choices", dss_choices(f))
    for spec in (RainSpec(), RainSpec(interval_min=30.0)):
        try:
            fr = read_dss_grid(f, spec); print("  READ", fr.depths.shape, "origin", fr.origin, "west", fr.west, "north", fr.north, "max %.2f" % np.nanmax(fr.depths)); break
        except ValueError as e:
            print("  REFUSED:", str(e)[:150])
