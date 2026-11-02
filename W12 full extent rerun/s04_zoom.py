"""A close look at the delivered depth drawing, before and after the cell-edge fix, on the busiest 3 km square of the coastal plain."""
from pathlib import Path

import matplotlib
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window, from_bounds

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
RUN = HERE / "runs" / "full_30m_200yr"
SIZE = 3000.0
with rasterio.open(RUN / "pixels" / "pixel_depth.tif") as s:
    k = 64
    a = s.read(1, out_shape=(s.height // k, s.width // k), resampling=Resampling.average, masked=True).filled(0.0)
    step = int(SIZE / (s.transform.a * k))
    wet = (a > 0.3).astype(float)
    area = np.cumsum(np.cumsum(wet, 0), 1)
    score = area[step:, step:] - area[:-step, step:] - area[step:, :-step] + area[:-step, :-step]
    score[score > 0.55 * step * step] = 0.0  # channels with dry ground between, not a sheet
    j, i = np.unravel_index(np.argmax(score), score.shape)
    x0, y1 = s.transform * (i * k, j * k)
bounds = (x0, y1 - SIZE, x0 + SIZE, y1)
print("window", bounds)
fig, ax = plt.subplots(1, 2, figsize=(14, 7.4))
for a, name, title in ((ax[0], "pixels_before_edge_fix", "Before: each 30 m cell shows"), (ax[1], "pixels", "After: delivered drawing")):
    with rasterio.open(RUN / name / "depth_drawing.tif") as s:
        d = s.read(1, window=from_bounds(*bounds, s.transform), masked=True).filled(np.nan)
    d[d <= 0] = np.nan
    a.imshow(d, cmap="Blues", vmin=0, vmax=3, interpolation="nearest", extent=(0, SIZE / 1000, 0, SIZE / 1000))
    a.set_title(title)
    a.set_xlabel("km")
fig.suptitle(f"Maximum depth, 0 to 3 m, 3 km square at E {x0:,.0f}, N {y1:,.0f}")
fig.tight_layout()
fig.savefig(HERE / "before_after_zoom.png", dpi=110)
