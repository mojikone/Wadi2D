"""Can raised linear features be found from the 5 m DEM alone? Scored against Bathinah Highway CL, the one layer that is
fully built, inside a 3 km corridor over the frame of the Block 2 200-yr layer.

Detection: morphological top-hat (ground less its opening), so a feature narrower than the structuring disc stands out;
threshold on height; drop short objects; thin to a skeleton. A sweep over height and disc radius, fixed before running.
Recall: share of the highway within REACH_M of a detected line. Other lines: detected length away from the highway. Those
are not all false, because the corridor holds other roads and dykes; the test has no layer for them.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyogrio
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from scipy import ndimage
from shapely.geometry import box
from skimage.measure import label, regionprops
from skimage.morphology import disk, skeletonize

HERE = Path(__file__).resolve().parent
DEM = HERE.parent / "W2 full extent run" / "terrain" / "NSA5_COP30_blend.tif"
ROAD = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\SHP\Roads\Bathinah Highway CL.shp"
FRAME = box(410964, 2699707, 458976, 2742718)  # the Block 2 200-yr layer
CORRIDOR_M = 3000.0
REACH_M = 30.0
MIN_LENGTH_M = 100.0
HEIGHTS_M = (0.3, 0.5, 1.0, 1.5)
RADII_M = (40.0, 60.0, 100.0)
PIX = 5.0


def main() -> None:
    road = pyogrio.read_dataframe(ROAD).to_crs(32640).geometry.union_all().intersection(FRAME)
    zone = road.buffer(CORRIDOR_M)
    print(f"highway in the frame {road.length / 1000:.1f} km; corridor {zone.area * 1e-6:.0f} km2", flush=True)
    with rasterio.open(DEM) as s:
        w = from_bounds(*zone.bounds, s.transform).round_offsets().round_lengths()
        z = s.read(1, window=w).astype("float32")
        tr = s.window_transform(w)
    inside = ~geometry_mask([zone.__geo_interface__], z.shape, tr)
    near_road = ~geometry_mask([road.buffer(REACH_M).__geo_interface__], z.shape, tr)
    print("window", z.shape, flush=True)
    samples = [road.interpolate(d) for d in np.arange(0.0, road.length, 20.0)]
    rc = np.array([rasterio.transform.rowcol(tr, p.x, p.y) for p in samples])
    out = []
    for radius in RADII_M:
        opened = ndimage.grey_opening(z, footprint=disk(int(radius / PIX)))
        top = z - opened
        for height in HEIGHTS_M:
            raised = (top >= height) & inside
            lab = label(raised, connectivity=2)
            keep = np.zeros(lab.max() + 1, bool)
            for p in regionprops(lab):
                keep[p.label] = p.major_axis_length * PIX >= MIN_LENGTH_M
            lines = skeletonize(keep[lab])
            d = ndimage.distance_transform_edt(~lines) * PIX
            hit = d[rc[:, 0], rc[:, 1]] <= REACH_M
            on = (lines & near_road).sum() * PIX * 1.1 / 1000
            off = (lines & ~near_road).sum() * PIX * 1.1 / 1000
            row = {"radius_m": radius, "height_m": height, "recall": float(hit.mean()), "km_on_highway": float(on), "km_elsewhere": float(off), "km_elsewhere_per_km2": float(off / (zone.area * 1e-6))}
            out.append(row)
            print(row, flush=True)
    (HERE / "results.json").write_text(json.dumps({"highway_km": road.length / 1000, "corridor_km2": zone.area * 1e-6, "rows": out}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
