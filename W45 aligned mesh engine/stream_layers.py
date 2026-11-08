"""The stream corridors of Block 2 at 30 m as GIS layers for QGIS, in the colours of the maps, and three more plain
windows (his request of 2026-11-07, evening). Geometry only; no solver runs.

    .venv\\Scripts\\python "W45 aligned mesh engine\\stream_layers.py" <work folder of stream_corridors.py>

Writes ``<work>/stream_mesh.gpkg`` (corridor_cells, gap_triangles, corridors, thalwegs) and
``<work>/stream_squares.gpkg`` (the squares that stay), and ``<work>/stream_maps_plain.png``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import fiona  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from bed_types import hillshade  # noqa: E402
from stream_corridors import DX, JOB, specs_along, thalweg_lines  # noqa: E402
from stream_maps import HALF, cell_rings  # noqa: E402
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.grid.tiles import TileGrid  # noqa: E402
from wadi2d.run import domain_mask, grid_window  # noqa: E402
from wadi2d.strips.mesher import Corridor, build_strip_mesh  # noqa: E402
from wadi2d.terrain import RasterBed  # noqa: E402
from wadi2d.terrain.vector import read_features  # noqa: E402


def write_layer(path: Path, layer: str, crs, schema: dict, rows) -> None:
    with fiona.open(path, "w", driver="GPKG", layer=layer, schema=schema, crs=crs) as dst:
        dst.writerecords(rows)


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
        crs = bed.crs.to_wkt() if bed.crs is not None else None
    grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
    corridors = [Corridor(s["name"], shapely.LineString(s["centre"]), np.asarray(s["offsets"]), DX, {}) for s in specs]
    strip = build_strip_mesh(grid, corridors, 0.5 * DX, 5)
    rings = cell_rings(strip.geometry)
    kept = grid.mask.copy()
    kept[strip.masked] = False
    print(f"mesh: {int((strip.corridor >= 0).sum()):,} corridor cells, {int((strip.corridor < 0).sum()):,} triangles, {int(kept.sum()):,} squares kept")

    t0 = time.perf_counter()
    mesh_path = work / "stream_mesh.gpkg"
    if mesh_path.exists():
        mesh_path.unlink()
    poly = {"geometry": "Polygon", "properties": {"corridor": "int", "row": "int", "area_m2": "float"}}
    _area, _cx, _cy = strip.geometry.areas_centroids()
    is_corr = strip.corridor >= 0
    write_layer(mesh_path, "corridor_cells", crs, poly, (
        {"geometry": {"type": "Polygon", "coordinates": [[tuple(p) for p in rings[c]] + [tuple(rings[c][0])]]},
         "properties": {"corridor": int(strip.corridor[c]), "row": int(strip.row[c]), "area_m2": float(_area[c])}}
        for c in np.nonzero(is_corr)[0]
    ))
    write_layer(mesh_path, "gap_triangles", crs, poly, (
        {"geometry": {"type": "Polygon", "coordinates": [[tuple(p) for p in rings[c]] + [tuple(rings[c][0])]]},
         "properties": {"corridor": -1, "row": -1, "area_m2": float(_area[c])}}
        for c in np.nonzero(~is_corr)[0]
    ))
    write_layer(mesh_path, "corridors", crs, {"geometry": "Polygon", "properties": {"name": "str", "length_m": "float"}}, (
        {"geometry": shapely.geometry.mapping(p), "properties": {"name": s["name"], "length_m": float(shapely.LineString(s["centre"]).length)}}
        for p, s in zip(strip.polygons, specs, strict=True) if p.geom_type == "Polygon"
    ))
    write_layer(mesh_path, "thalwegs", crs, {"geometry": "LineString", "properties": {"area_km2": "float", "incised_m": "float", "length_m": "float"}}, (
        {"geometry": shapely.geometry.mapping(t["line"]), "properties": {"area_km2": float(t["area_km2"]), "incised_m": float(t.get("incised_m", 0.0)), "length_m": float(t["line"].length)}}
        for t in lines
    ))
    print(f"wrote {mesh_path} in {time.perf_counter() - t0:.0f} s")
    t0 = time.perf_counter()
    squares_path = work / "stream_squares.gpkg"
    if squares_path.exists():
        squares_path.unlink()
    jj, ii = np.nonzero(kept)
    xa, ya = grid.x0 + ii * DX, grid.y0 - (jj + 1) * DX
    write_layer(squares_path, "squares_kept", crs, {"geometry": "Polygon", "properties": {"j": "int", "i": "int"}}, (
        {"geometry": {"type": "Polygon", "coordinates": [[(x, y), (x + DX, y), (x + DX, y + DX), (x, y + DX), (x, y)]]}, "properties": {"j": int(j), "i": int(i)}}
        for x, y, j, i in zip(xa.tolist(), ya.tolist(), jj.tolist(), ii.tolist(), strict=True)
    ))
    print(f"wrote {squares_path} ({jj.size:,} squares) in {time.perf_counter() - t0:.0f} s")

    # three plain windows: the least incised wadis over 5 km2, at least 3 km apart
    plain = sorted((t for t in lines if t["area_km2"] >= 5.0), key=lambda t: t.get("incised_m", 0.0))
    chosen: list[dict] = []
    for t in plain:
        p = t["line"].interpolate(0.5, normalized=True)
        if all(p.distance(c["line"].interpolate(0.5, normalized=True)) > 3000.0 for c in chosen):
            chosen.append(t)
        if len(chosen) == 3:
            break
    _area2, cx, cy = strip.geometry.areas_centroids()
    fig, axes = plt.subplots(1, 3, figsize=(21, 7.4), dpi=120)
    with rasterio.open(cfg.terrain.dem) as dem:
        for ax, t in zip(axes, chosen, strict=False):
            p = t["line"].interpolate(0.5, normalized=True)
            box = (p.x - HALF, p.y - HALF, p.x + HALF, p.y + HALF)
            shade, _z = hillshade(dem, box)
            ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1, alpha=0.85)
            j0, j1 = max(0, int((grid.y0 - box[3]) // DX) - 1), min(grid.shape[0], int((grid.y0 - box[1]) // DX) + 2)
            i0, i1 = max(0, int((box[0] - grid.x0) // DX) - 1), min(grid.shape[1], int((box[2] - grid.x0) // DX) + 2)
            sq = [np.array([[grid.x0 + i * DX, grid.y0 - (j + 1) * DX], [grid.x0 + (i + 1) * DX, grid.y0 - (j + 1) * DX], [grid.x0 + (i + 1) * DX, grid.y0 - j * DX], [grid.x0 + i * DX, grid.y0 - j * DX]]) for j in range(j0, j1) for i in range(i0, i1) if kept[j, i]]
            if sq:
                ax.add_collection(PolyCollection(sq, facecolors="none", edgecolors="#707070", linewidths=0.35))
            inside = (cx > box[0] - 60) & (cx < box[2] + 60) & (cy > box[1] - 60) & (cy < box[3] + 60)
            tri = [rings[c] for c in np.nonzero(inside & ~is_corr)[0]]
            corr = [rings[c] for c in np.nonzero(inside & is_corr)[0]]
            if tri:
                ax.add_collection(PolyCollection(tri, facecolors="#f0a03040", edgecolors="#c86400", linewidths=0.5))
            if corr:
                ax.add_collection(PolyCollection(corr, facecolors="#2a7fd440", edgecolors="#1b4f8a", linewidths=0.6))
            segs = [np.asarray(u["line"].coords) for u in lines if u["line"].intersects(shapely.box(*box))]
            if segs:
                ax.add_collection(LineCollection(segs, colors="#d40000", linewidths=1.2, linestyles="--"))
            ax.set_title(f"plain: {t['area_km2']:.1f} km2 wadi, incised {t.get('incised_m', 0):.1f} m over 200 m; {len(corr)} corridor cells, {len(tri)} triangles", fontsize=9)
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
            ax.set_aspect("equal")
            ax.tick_params(labelsize=6)
            ax.ticklabel_format(useOffset=False, style="plain")
    fig.suptitle("Block 2 at 30 m, three plain reaches: the 1 km2 stream (red dashed) as a corridor of two 30 m cells (blue), gap triangles (orange), squares (grey)", fontsize=10)
    fig.savefig(work / "stream_maps_plain.png", bbox_inches="tight")
    print("wrote", work / "stream_maps_plain.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
