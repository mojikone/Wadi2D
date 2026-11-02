"""Draw a suggestion over its DEM: banks blue, crests by kind, thalwegs dashed. usage: python draw.py CASE [x y half_width]"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import shapely
from rasterio.windows import from_bounds

HERE = Path(__file__).resolve().parent
REPO = Path(r"D:\Mojtaba\Renardet\Wadi2D")
"""The terrain of the frozen cases is not committed: it lives in the main checkout, read here and never written."""
DEMS = {
    "bidah": REPO / "W1 research and design note" / "validation" / "ras_rain_on_grid" / "terrain" / "bidah_0p5m.tif",
    "faydh": REPO / "W11 validation round two" / "t2_faydh" / "terrain" / "faydh_0p5m.tif",
}
COLOURS = {"stream bank": "#0a63c9", "dam": "#d40000", "road": "#303030", "other crest": "#e07b00"}


def read(case: str, layer: str):
    db = sqlite3.connect(HERE / "suggested" / case / "suggested_breaklines.gpkg")
    cols = [r[1] for r in db.execute(f"PRAGMA table_info({layer})")][2:]
    out = [(shapely.from_wkb(b[40:]), dict(zip(cols, v, strict=True))) for b, *v in db.execute(f"SELECT geom, {', '.join(cols)} FROM {layer}")]
    db.close()
    return out


def main() -> None:
    case = sys.argv[1]
    lines, thalwegs = read(case, "breaklines"), read(case, "thalwegs")
    if len(sys.argv) > 2:
        x, y, half = (float(v) for v in sys.argv[2:5])
        bounds = (x - half, y - half, x + half, y + half)
    else:
        bounds = shapely.total_bounds([g for g, _r in lines + thalwegs])
    with rasterio.open(DEMS[case]) as src:
        w = from_bounds(*bounds, src.transform)
        scale = max(1, round((bounds[2] - bounds[0]) / src.transform.a / 2000))
        z = src.read(1, window=w, out_shape=(int(w.height / scale), int(w.width / scale)), masked=True).astype("float64")
    dy, dx = np.gradient(z.filled(np.nan))
    shade = np.clip(0.5 + 0.5 * (-dx + dy) / (np.hypot(dx, dy).max() + 1e-9) * 3, 0, 1)
    fig, ax = plt.subplots(figsize=(12, 12 * (bounds[3] - bounds[1]) / (bounds[2] - bounds[0])))
    ax.imshow(shade, cmap="gray", extent=(bounds[0], bounds[2], bounds[1], bounds[3]), vmin=0, vmax=1)
    for g, _r in thalwegs:
        for part in g.geoms:
            xy = np.asarray(part.coords)
            ax.plot(xy[:, 0], xy[:, 1], "--", color="#22a7f0", lw=0.8)
    for g, r in lines:
        for part in g.geoms:
            xy = np.asarray(part.coords)
            ax.plot(xy[:, 0], xy[:, 1], color=COLOURS[r["kind"]], lw=1.2 if r["kind"] == "stream bank" else 0.8)
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_title(f"{case}: {sum(r['kind'] == 'stream bank' for _g, r in lines)} banks (blue), {sum(r['kind'] != 'stream bank' for _g, r in lines)} crests (orange, red dam, black road), thalwegs dashed")
    name = "all" if len(sys.argv) <= 2 else f"{int(x)}_{int(y)}"
    fig.savefig(HERE / "suggested" / case / f"draw_{name}.png", dpi=110, bbox_inches="tight")
    print(HERE / "suggested" / case / f"draw_{name}.png")


if __name__ == "__main__":
    main()
