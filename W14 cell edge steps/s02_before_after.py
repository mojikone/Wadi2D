"""The delivered depth drawing before and after, uniform and mesh, same crop; jumps along cell edges."""
from pathlib import Path

import matplotlib
import numpy as np
import rasterio
from rasterio.windows import from_bounds

matplotlib.use("Agg")
import matplotlib.pyplot as plt

S = Path(__file__).parent
OLD_U = Path(r"D:\Mojtaba\Renardet\Wadi2D\W13 time step test\runs\cfl_0450\pixels")
OLD_M = Path(r"D:\Mojtaba\Renardet\Wadi2D\.claude\worktrees\agent-a256aed617410ea5b\W10 mesher\runs\pixels_05m\pixels")
NEW_U, NEW_M = S / "copy_uni" / "pixels", S / "copy_mesh" / "pixels"
b = (435025, 2725115, 435375, 2725465)


def read(p, name):
    with rasterio.open(p / name) as s:
        return s.read(1, window=from_bounds(*b, s.transform), masked=True).filled(np.nan).astype(np.float32)


fig, ax = plt.subplots(2, 2, figsize=(13, 13))
for a, p, t in ((ax[0, 0], OLD_U, "uniform 20 m, before"), (ax[0, 1], NEW_U, "uniform 20 m, after"),
                (ax[1, 0], OLD_M, "mesh 10-40 m, before"), (ax[1, 1], NEW_M, "mesh 10-40 m, after")):
    d = read(p, "depth_drawing.tif")
    d[d <= 0] = np.nan
    a.imshow(d, cmap="turbo", vmin=0, vmax=2.1, interpolation="nearest")
    a.set_title(t)
    a.axis("off")
    px = read(p, "pixel_depth.tif")
    jx = np.abs(np.diff(px, axis=1))
    print(t, "pixel jumps over 0.5 m:", int(np.nansum(jx > 0.5)), "over 0.25 m:", int(np.nansum(jx > 0.25)))
fig.tight_layout()
fig.savefig(S / "after.png", dpi=80)
