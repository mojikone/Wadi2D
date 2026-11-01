"""Dam data: EAV at key levels, dike pieces, ground along the axes, the PMP inflow."""
import csv
import sys

import numpy as np
import rasterio
import shapefile
import shapely

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import AXES, BLOCK, DAMS, HMS

EAV = DAMS.parent / "EAV"
for name, fsl, crest in (("Bidah 03", 100.0, 105.0), ("Faydh 01", 230.0, 235.0)):
    rows = np.loadtxt(EAV / f"{name} EAV.csv", delimiter=",", skiprows=1, encoding="utf-8")
    a = rows[:, 0]
    z = rows[:, 1]
    v = rows[:, 2]
    print(name, "z", z.min(), z.max(), "dz", np.unique(np.round(np.diff(z), 3))[:6], "n", z.size)
    for zz in (fsl - 10, fsl - 5, fsl, fsl + 2.5, crest, crest + 1, crest + 2):
        print(f"   z {zz}: A {np.interp(zz, z, a):.0f} m2  V {np.interp(zz, z, v)/1e6:.3f} Mm3")
    # check the area integrates to the volume
    vi = np.concatenate(([0.0], np.cumsum(0.5 * (a[1:] + a[:-1]) * np.diff(z))))
    print("   V(trapz of A) at FSL", np.interp(fsl, z, vi) / 1e6, "area sat at z >=", z[np.argmax(a >= 0.999 * a.max())], a.max())

r = shapefile.Reader(str(DAMS / "Reservoirs.shp"))
polys = {}
for sr in r.shapeRecords():
    g = shapely.geometry.shape(sr.shape.__geo_interface__)
    print("reservoir", list(sr.record), g.geom_type, g.area / 1e6, g.bounds, g.is_valid)
d = shapefile.Reader(str(DAMS / "Dikes.shp"))
for sr in d.shapeRecords():
    p = np.array(sr.shape.points)
    print(list(sr.record), "parts", list(sr.shape.parts), "n", len(p))
    seg = np.hypot(*np.diff(p, axis=0).T)
    print("   segs", np.round(seg, 0).tolist())
    print("   pts", np.round(p, 1).tolist())
with rasterio.open(BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif") as s:
    for n in ("Bidah 03", "Faydh 01"):
        line = shapely.LineString(AXES[n])
        ds = np.arange(0.0, line.length, 20.0)
        pts = [line.interpolate(x) for x in ds]
        zz = np.array([v[0] for v in s.sample([(p.x, p.y) for p in pts])])
        print(n, "length", round(line.length), "ground along axis every 40 m:", np.round(zz[::2], 1).tolist())
        print("   min", zz.min(), "at s", ds[int(np.argmin(zz))], pts[int(np.argmin(zz))])
