"""Check lumped outlets against the dam lines: upstream, on the wadi, and how far from the HMS junction."""
import sys

import rasterio
import shapely

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import ACC, AXES, HMS, lumped_outlets, polygons

from wadi2d.hms import load_basin

b = load_basin(HMS / "Basin_1.basin")
polys = polygons()
out = lumped_outlets()
axes = {k: shapely.LineString(v) for k, v in AXES.items()}
with rasterio.open(ACC) as s:
    for n, (x, y) in out.items():
        p = shapely.Point(x, y)
        e = b.subbasins[n]
        j = b.junctions[e.downstream]
        dj = p.distance(shapely.Point(j.canvas_x, j.canvas_y))
        dist = min((p.distance(a), k) for k, a in axes.items())
        acc = next(s.sample([(x, y)]))[0] * 25e-6
        print(f"{n:4s} -> {e.downstream:9s} ({x:.0f},{y:.0f}) d_junction {dj:6.0f} m, acc {acc:6.1f} km2 (A sub {e.area:.1f}); nearest axis {dist[1]} {dist[0]:.0f} m")
