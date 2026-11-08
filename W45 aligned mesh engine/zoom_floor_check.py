"""His zoom window (2026-11-07): why the 5 % floor edges are missing along the wadi, where the corridor bulges beyond
the bed, and what a height-above-thalweg floor would give instead. Geometry only, no model run.

Cross-sections every 60 m across each 1 km2 thalweg in the window, 300 m each side at 5 m: the engine's slope rule
(ground climbing over 5 % for 40 m and standing 2 m over the bed, looked for within 300 m) against a height above
the thalweg (HAND) at 1, 2 and 3 m. Figure: hillshade, the thalwegs, the floor edges the Suggest found, the corridor
cells, HAND contours; a table of how often each rule finds an edge and the widths it gives."""

from __future__ import annotations

import sys
from pathlib import Path

import fiona
import matplotlib
import numpy as np
import rasterio
import shapely
from rasterio.windows import from_bounds
from scipy import ndimage
from scipy.spatial import cKDTree

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402

WORK = Path(__file__).resolve().parent / "stream_corridors"
DEM = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif")
MESH = WORK / "mesh_his_fixed.gpkg"
BOX = (440365.0, 2709262.0, 442672.0, 2711062.0)  # his screenshot, QGIS at 1:8,472
PAD = 400.0
STEP = 60.0
REACH = 300.0
SLOPE, RUN, RISE = 0.05, 40.0, 2.0
HAND_LEVELS = (1.0, 2.0, 3.0)


def hillshade(z: np.ndarray, px: float, az: float = 315.0, alt: float = 45.0) -> np.ndarray:
    gy, gx = np.gradient(z, px)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, h = np.radians(az), np.radians(alt)
    return np.clip(np.sin(h) * np.cos(slope) + np.cos(h) * np.sin(slope) * np.cos(a - aspect), 0, 1)


def read(layer: str, box: shapely.Polygon) -> list[dict]:
    with fiona.open(MESH, layer=layer) as src:
        return [{"geometry": shapely.geometry.shape(f["geometry"]), **f["properties"]} for f in src.filter(bbox=box.bounds)]


def main(out: Path, box_xy: tuple[float, float, float, float] = BOX, tag: str = "") -> None:
    BOX = box_xy  # noqa: N806
    x0, y0, x1, y1 = BOX[0] - PAD, BOX[1] - PAD, BOX[2] + PAD, BOX[3] + PAD
    box = shapely.box(x0, y0, x1, y1)
    with rasterio.open(DEM) as src:
        win = from_bounds(x0, y0, x1, y1, src.transform)
        z = src.read(1, window=win).astype(np.float64)
        tr = src.window_transform(win)
        nodata = src.nodata
    if nodata is not None:
        z[z == nodata] = np.nan
    px = tr.a
    gx0, gy0 = tr.c, tr.f  # the upper-left corner

    def sample(xy: np.ndarray) -> np.ndarray:
        c = (xy[:, 0] - gx0) / px
        r = (gy0 - xy[:, 1]) / px
        return ndimage.map_coordinates(z, [r, c], order=1, mode="nearest")

    thalwegs = read("thalwegs", box)
    edges = read("floor_edges", box)
    cells = read("corridor_cells", box)
    # HAND: height above the nearest thalweg sample (every 5 m along every 1 km2 stream in the window)
    pts = np.vstack([shapely.get_coordinates(shapely.line_interpolate_point(t["geometry"], np.arange(0.0, t["geometry"].length, 5.0))) for t in thalwegs])
    zt = sample(pts)
    rows, cols = np.indices(z.shape)
    gxy = np.column_stack(((cols.ravel() + 0.5) * px + gx0, gy0 - (rows.ravel() + 0.5) * px))
    _d, k = cKDTree(pts).query(gxy)
    hand = (z.ravel() - zt[k]).reshape(z.shape)

    # cross-sections
    report = []
    sections = []
    for t in sorted(thalwegs, key=lambda t: -t["area_km2"]):
        line = t["geometry"]
        if t["area_km2"] < 3.0:
            continue
        s = np.arange(STEP / 2, line.length, STEP)
        cen = shapely.get_coordinates(shapely.line_interpolate_point(line, s))
        ahead = shapely.get_coordinates(shapely.line_interpolate_point(line, np.minimum(s + 10.0, line.length)))
        behind = shapely.get_coordinates(shapely.line_interpolate_point(line, np.maximum(s - 10.0, 0.0)))
        tang = ahead - behind
        tang /= np.maximum(np.hypot(tang[:, 0], tang[:, 1]), 1e-9)[:, None]
        normal = np.column_stack((-tang[:, 1], tang[:, 0]))
        off = np.arange(0.0, REACH + px, px)
        found = {"left": [], "right": []}
        widths = {h: {"left": [], "right": []} for h in HAND_LEVELS}
        for i in range(cen.shape[0]):
            if not box.contains(shapely.Point(cen[i])):
                continue
            zbed = float(sample(cen[i][None, :])[0])
            for side, sign in (("left", 1.0), ("right", -1.0)):
                prof = sample(cen[i][None, :] + sign * off[:, None] * normal[i][None, :])
                n = int(round(RUN / px))
                climb = (prof[n:] - prof[:-n]) / RUN  # slope over the 40 m run starting at each point
                over = (climb >= SLOPE) & (prof[n:] - zbed >= RISE)
                j = np.argmax(over) if over.any() else -1
                found[side].append(float(off[j]) if j >= 0 else np.nan)
                hp = prof - zbed
                for h in HAND_LEVELS:
                    m = hp >= h
                    widths[h][side].append(float(off[np.argmax(m)]) if m.any() else np.nan)
                sections.append((cen[i], cen[i] + sign * (off[j] if j >= 0 else REACH) * normal[i], j >= 0))
        n = len(found["left"])
        if n == 0:
            continue
        row = {"stream_km2": t["area_km2"], "sections": n}
        for side in ("left", "right"):
            f = np.array(found[side])
            row[f"5pct_{side}_found"] = f"{100 * np.isfinite(f).mean():.0f} %"
            row[f"5pct_{side}_median_m"] = round(float(np.nanmedian(f)), 0) if np.isfinite(f).any() else None
            for h in HAND_LEVELS:
                w = np.array(widths[h][side])
                row[f"hand{h:g}_{side}_found"] = f"{100 * np.isfinite(w).mean():.0f} %"
                row[f"hand{h:g}_{side}_median_m"] = round(float(np.nanmedian(w)), 0) if np.isfinite(w).any() else None
        report.append(row)
    for row in report:
        print(row)

    # figure
    fig, ax = plt.subplots(figsize=(16, 12.5), dpi=110)
    ax.imshow(hillshade(np.nan_to_num(z, nan=np.nanmean(z)), px), extent=(gx0, gx0 + z.shape[1] * px, gy0 - z.shape[0] * px, gy0), cmap="gray", vmin=0, vmax=1, alpha=0.85)
    xs = gx0 + (np.arange(z.shape[1]) + 0.5) * px
    ys = gy0 - (np.arange(z.shape[0]) + 0.5) * px
    cs = ax.contour(xs, ys, hand, levels=list(HAND_LEVELS), colors=["#ff00ff", "#9900cc", "#330066"], linewidths=[1.2, 1.0, 0.8])
    ax.clabel(cs, fmt=lambda v: f"HAND {v:g} m", fontsize=7)
    ax.add_collection(PolyCollection([shapely.get_coordinates(c["geometry"].exterior) for c in cells], facecolors="#2a7fd4", edgecolors="#1b4f8a", linewidths=0.3, alpha=0.35))
    ax.add_collection(LineCollection([shapely.get_coordinates(e["geometry"]) for e in edges], colors="#008000", linewidths=1.6))
    ax.add_collection(LineCollection([shapely.get_coordinates(t["geometry"]) for t in thalwegs], colors="#d40000", linewidths=1.0, linestyles="--"))
    hit = [(a, b) for a, b, ok in sections if ok]
    miss = [(a, b) for a, b, ok in sections if not ok]
    ax.add_collection(LineCollection(hit, colors="#404040", linewidths=0.5, alpha=0.6))
    ax.add_collection(LineCollection(miss, colors="#ff8800", linewidths=0.7, alpha=0.8))
    ax.set_xlim(BOX[0], BOX[2])
    ax.set_ylim(BOX[1], BOX[3])
    ax.set_aspect("equal")
    ax.set_title(
        "His zoom window: the Suggest's 5 % floor edges (green) against height above the thalweg (HAND, magenta 1 m, purple 2 m, dark 3 m)\n"
        "grey sections: the 5 % rule found an edge on that side; orange: none within 300 m. Blue: the fixed-cell corridors as built."
    )
    fig.tight_layout()
    fig.savefig(out / f"zoom_floor_check{tag}.png")
    print("wrote", out / f"zoom_floor_check{tag}.png")


if __name__ == "__main__":
    # zoom_floor_check.py [out_dir] [x0 y0 x1 y1 [tag]]
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else WORK
    if len(sys.argv) >= 6:
        main(out_dir, tuple(float(v) for v in sys.argv[2:6]), sys.argv[6] if len(sys.argv) > 6 else "")
    else:
        main(out_dir)
