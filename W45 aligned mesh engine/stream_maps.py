"""Maps of the stream corridors on Block 2 at 30 m (his request of 2026-11-07, evening): the mesh around the 1 km2
streams at a confluence, on the plain, at a bend the corridor could not follow, and on a straight hill reach, with an
overview of the whole domain. Geometry only; no solver runs.

    .venv\\Scripts\\python "W45 aligned mesh engine\\stream_maps.py" <work folder of stream_corridors.py>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from bed_types import hillshade  # noqa: E402
from stream_corridors import DX, JOB, specs_along, thalweg_lines  # noqa: E402
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.grid.tiles import TileGrid  # noqa: E402
from wadi2d.run import domain_mask, grid_window  # noqa: E402
from wadi2d.strips.mesher import Corridor, build_strip_mesh  # noqa: E402
from wadi2d.terrain import RasterBed  # noqa: E402
from wadi2d.terrain.vector import read_features  # noqa: E402

HALF = 450.0
"""Half the side of a close window, m: 30 cells of 30 m across."""


def cell_rings(geo) -> list[np.ndarray]:
    start, node = np.asarray(geo.ring_start), np.asarray(geo.ring_node)
    x, y = np.asarray(geo.x), np.asarray(geo.y)
    return [np.column_stack((x[node[start[c] : start[c + 1]]], y[node[start[c] : start[c + 1]]])) for c in range(len(start) - 1)]


def pick_windows(lines: list[dict], polygons: list[shapely.Polygon], domain: shapely.Geometry) -> dict[str, tuple]:
    """Centres of the windows: a confluence, the flattest plain reach, a bend the corridor left, a steep hill reach."""
    by_area = sorted(lines, key=lambda t: -t["area_km2"])
    tree = shapely.STRtree([t["line"] for t in by_area])
    picks: dict[str, tuple] = {}
    # a confluence: a tributary's downstream end on a bigger thalweg
    best = None
    for k, t in enumerate(by_area):
        end = shapely.Point(t["line"].coords[-1])
        for m in tree.query(end, predicate="dwithin", distance=6.0):
            if m == k or by_area[m]["area_km2"] <= t["area_km2"]:
                continue
            score = min(t["area_km2"], by_area[m]["area_km2"])
            if best is None or score > best[0]:
                best = (score, end.x, end.y, t["area_km2"], by_area[m]["area_km2"])
    if best:
        picks["confluence"] = (best[1], best[2], f"confluence: a {best[3]:.1f} km2 wadi joining a {best[4]:.1f} km2 one")
    # the plain: the least incised reach among the big wadis
    big = [t for t in by_area if t["area_km2"] >= 20.0] or by_area[:10]
    flat = min(big, key=lambda t: t.get("incised_m", 0.0))
    p = flat["line"].interpolate(0.5, normalized=True)
    picks["plain"] = (p.x, p.y, f"plain: {flat['area_km2']:.1f} km2 wadi, incised {flat.get('incised_m', 0):.1f} m")
    # the bend: the longest stretch of thalweg no corridor covers, clear of the domain edge
    covered = shapely.unary_union(polygons).buffer(5.0)
    edge = domain.boundary.buffer(150.0)
    uncovered = shapely.unary_union([t["line"] for t in by_area]).difference(covered).difference(edge)
    parts = sorted(shapely.get_parts(uncovered), key=lambda g: -g.length)
    inner = [g for g in parts if g.length > 100.0 and g.length < 1500.0]
    if inner:
        g = inner[0]
        p = g.interpolate(0.5, normalized=True)
        picks["bend"] = (p.x, p.y, f"a stretch of {g.length:.0f} m the corridor could not follow")
    # a steep hill reach: the most incised wadi over 5 km2
    hill = max((t for t in by_area if t["area_km2"] >= 5.0), key=lambda t: t.get("incised_m", 0.0))
    p = hill["line"].interpolate(0.5, normalized=True)
    picks["hills"] = (p.x, p.y, f"hill reach: {hill['area_km2']:.1f} km2 wadi, incised {hill.get('incised_m', 0):.1f} m")
    return picks


def main(work: Path) -> None:
    data = json.loads(JOB.read_text(encoding="utf-8"))
    data.setdefault("mesh", {})["stream_area_mid_km2"] = 1.0
    data["mesh"]["enabled"] = False
    data.pop("strips", None)
    cfg = RunConfig.model_validate(data)
    lines = thalweg_lines(work / "suggest_1km2" / "suggested_breaklines.gpkg")
    domain = shapely.union_all([shape for _p, shape in read_features(cfg.grid.domain, "")])
    specs, _cut = specs_along(lines, domain, [-DX, 0.0, DX], DX)
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
    grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
    corridors = [Corridor(s["name"], shapely.LineString(s["centre"]), np.asarray(s["offsets"]), DX, {}) for s in specs]
    strip = build_strip_mesh(grid, corridors, 0.5 * DX, 5)
    rings = cell_rings(strip.geometry)
    _area, cx, cy = strip.geometry.areas_centroids()
    kept = grid.mask.copy()
    kept[strip.masked] = False
    picks = pick_windows(lines, strip.polygons, domain)
    print("windows:", {k: v[2] for k, v in picks.items()})

    fig, axes = plt.subplots(2, 2, figsize=(16, 16), dpi=120)
    with rasterio.open(cfg.terrain.dem) as dem:
        for ax, (label, (x, y, words)) in zip(axes.ravel(), picks.items(), strict=False):
            box = (x - HALF, y - HALF, x + HALF, y + HALF)
            shade, _z = hillshade(dem, box)
            ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1, alpha=0.85)
            # the squares still in the lattice
            j0 = max(0, int((grid.y0 - box[3]) // DX) - 1)
            j1 = min(grid.shape[0], int((grid.y0 - box[1]) // DX) + 2)
            i0 = max(0, int((box[0] - grid.x0) // DX) - 1)
            i1 = min(grid.shape[1], int((box[2] - grid.x0) // DX) + 2)
            squares = []
            for j in range(j0, j1):
                for i in range(i0, i1):
                    if kept[j, i]:
                        xa, ya = grid.x0 + i * DX, grid.y0 - (j + 1) * DX
                        squares.append(np.array([[xa, ya], [xa + DX, ya], [xa + DX, ya + DX], [xa, ya + DX]]))
            if squares:
                ax.add_collection(PolyCollection(squares, facecolors="none", edgecolors="#707070", linewidths=0.35))
            inside = (cx > box[0] - 60) & (cx < box[2] + 60) & (cy > box[1] - 60) & (cy < box[3] + 60)
            corr = [rings[c] for c in np.nonzero(inside & (strip.corridor >= 0))[0]]
            tri = [rings[c] for c in np.nonzero(inside & (strip.corridor < 0))[0]]
            if tri:
                ax.add_collection(PolyCollection(tri, facecolors="#f0a03040", edgecolors="#c86400", linewidths=0.5))
            if corr:
                ax.add_collection(PolyCollection(corr, facecolors="#2a7fd440", edgecolors="#1b4f8a", linewidths=0.6))
            segs = []
            for t in lines:
                if t["line"].intersects(shapely.box(*box)):
                    segs.append(np.asarray(t["line"].coords))
            if segs:
                ax.add_collection(LineCollection(segs, colors="#d40000", linewidths=1.2, linestyles="--"))
            ax.set_title(f"{words}: {len(corr)} corridor cells, {len(tri)} gap triangles, {len(squares)} squares in view", fontsize=9)
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
            ax.set_aspect("equal")
            ax.tick_params(labelsize=6)
            ax.ticklabel_format(useOffset=False, style="plain")
    fig.suptitle("Block 2 at 30 m: the 1 km2 streams (red dashed) as corridors of two 30 m cells (blue), the gap triangles (orange) and the squares that stay (grey); no banks, no crests", fontsize=10)
    fig.savefig(work / "stream_maps.png", bbox_inches="tight")
    print("wrote", work / "stream_maps.png")

    # the overview
    x0, y0, x1, y1 = domain.bounds
    fig, ax = plt.subplots(figsize=(12, 12 * (y1 - y0) / (x1 - x0)), dpi=120)
    with rasterio.open(cfg.terrain.dem) as dem:
        win = from_bounds(x0, y0, x1, y1, transform=dem.transform)
        scale = max(1, int(round(min(win.width, win.height) / 2000)))
        z = dem.read(1, window=win, out_shape=(int(win.height // scale), int(win.width // scale)), resampling=Resampling.average).astype(np.float64)
        z = np.where(z < -1000, np.nan, z)
        gy, gx = np.gradient(np.nan_to_num(z, nan=np.nanmean(z)), dem.res[0] * scale)
        az, alt = np.radians(315.0), np.radians(45.0)
        slope = np.arctan(np.hypot(gx, gy))
        aspect = np.arctan2(-gx, gy)
        shade = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
    ax.imshow(shade, extent=(x0, x1, y0, y1), cmap="gray", vmin=0, vmax=1, alpha=0.9)
    ax.add_collection(PolyCollection([np.asarray(p.exterior.coords) for p in strip.polygons], facecolors="#2a7fd4", edgecolors="#1b4f8a", linewidths=0.3))
    for key, (x, y, _w) in picks.items():
        ax.add_patch(plt.Rectangle((x - HALF, y - HALF), 2 * HALF, 2 * HALF, fill=False, edgecolor="#ffa500", lw=1.5))
        ax.annotate(key, (x + HALF, y + HALF), color="#ffa500", fontsize=9)
    ax.set_title(f"Block 2 job domain at 30 m: {len(strip.polygons)} corridors along the 1 km2 streams (blue), the four close windows in orange", fontsize=10)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=6)
    ax.ticklabel_format(useOffset=False, style="plain")
    fig.savefig(work / "stream_maps_overview.png", bbox_inches="tight")
    print("wrote", work / "stream_maps_overview.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
