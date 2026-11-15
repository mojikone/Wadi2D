"""inputs/domain_no_rim.geojson: the domain without the 40 m rim round Basin 3's polygons.

The first domain (s01_inputs.py) is the polygons joined + 40 m, plus the coast strip. Rain falls on every active cell
whose centre lies outside every lumped polygon (the engine's rule, decision 5), so in runs 3 and 4, where all 104
subbasins are lumped, the rim was rained on: 14,250 squares and 1,139 aligned cells, 6.2 km2, 1.1 Mm3 of excess, running
into the hills from the outline (his finding on the max depth maps, 2026-11-15). Here the land side of the domain is
the polygons' own outline (holes filled, simplified by 1 m only, so a cell centre inside the domain is inside a polygon
but for a handful), and
the coast strip stays, with the 40 m band between the polygons and the strip, which is rain-on-grid ground in every
run. The mask and the labels both go by the cell centre, so the check below counts what would still be rained.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import shapely
from affine import Affine
from rasterio import features
from shapely.geometry import mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import BASIN, DOMAIN_NO_RIM, DX, HMS_DIR, INPUTS, load_json  # noqa: E402

from wadi2d.config.schema import Hydrology  # noqa: E402
from wadi2d.forcing import load_polygons  # noqa: E402

RIM_M = 40.0
JOIN_M = 46.0
SIMPLIFY_M = 1.0
"""The outline moves by at most this, against cells of 20 m: unsimplified the file is 42 MB."""


def main() -> None:
    old = shape(load_json(INPUTS / "domain.geojson")["features"][0]["geometry"])
    h = Hydrology(hms_basin=str(HMS_DIR / BASIN), hms_sqlite=str(HMS_DIR / BASIN.replace(".basin", ".sqlite")))
    polys = [shapely.make_valid(p).buffer(0) for p in load_polygons(h).values()]
    joined = shapely.union_all([p.buffer(1.0) for p in polys]).buffer(-1.0)
    parts = sorted(getattr(joined, "geoms", [joined]), key=lambda g: g.area, reverse=True)
    land = shapely.Polygon(parts[0].exterior)
    beyond = old.difference(land.buffer(RIM_M + 1.0))
    strip = max(getattr(beyond, "geoms", [beyond]), key=lambda g: g.area)
    inner = land.buffer(-(SIMPLIFY_M + 0.5))  # so the simplified outline stays inside the polygons
    dom = shapely.union_all([inner, strip.buffer(JOIN_M).intersection(old)]).buffer(0.5).buffer(-0.5)
    dom = shapely.Polygon(max(getattr(dom, "geoms", [dom]), key=lambda g: g.area).exterior)
    dom = shapely.set_precision(dom.simplify(SIMPLIFY_M), 0.01)
    DOMAIN_NO_RIM.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "W79 domain without the rim"}, "geometry": mapping(dom)}]},
        separators=(",", ":")), encoding="utf-8")
    print("vertices", len(dom.exterior.coords), "file MB", round(DOMAIN_NO_RIM.stat().st_size / 1e6, 2))
    x0, y1 = np.floor(old.bounds[0] / DX) * DX, np.ceil(old.bounds[3] / DX) * DX
    shape_ = (int(np.ceil((y1 - old.bounds[1]) / DX)), int(np.ceil((old.bounds[2] - x0) / DX)))
    t = Affine(DX, 0, x0, 0, -DX, y1)
    labels = features.rasterize([(p, 1) for p in polys], out_shape=shape_, transform=t, fill=0, dtype="uint8")
    for name, geom in (("with the rim", old), ("without", dom)):
        mask = features.geometry_mask([geom], out_shape=shape_, transform=t, invert=True)
        rained = mask & (labels == 0)
        jj, ii = np.nonzero(rained)
        far = shapely.distance(strip, shapely.points(x0 + (ii + 0.5) * DX, y1 - (jj + 0.5) * DX)) > JOIN_M + DX
        print(f"{name}: {geom.area / 1e6:,.2f} km2, {int(mask.sum()):,} cells, outside every polygon {int(rained.sum()):,}, "
              f"of those away from the coast strip {int(far.sum()):,} ({far.sum() * DX * DX / 1e6:.3f} km2)")


if __name__ == "__main__":
    main()
