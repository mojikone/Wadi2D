"""His mesh rule of 2026-11-07, late: the centre lines drive the cells in the wadis, the under-5 % floor says how far
the 30 m cells repeat across a defined wadi, the plains stay 30 m squares, and the mountains, where the ground is
steeper than 20 % over a continuous area, take 60 m cells (the quadtree doubles, so 60 m on a 30 m grid; 50 m would
need a 25 m grid). Built on Block 2 at 30 m as geometry only, no solver: the corridors on the 30 m lattice, the
coarse tiles from the engine's own quadtree with a slope rule for the levels. The engine cannot yet run the two
together; this is the mesh it will make once they are joined.

    .venv\\Scripts\\python "W45 aligned mesh engine\\his_mesh.py" <work folder of stream_corridors.py>

Writes ``<work>/mesh_his.gpkg`` (corridor_cells, gap_triangles, corridors, floor_edges, thalwegs, cells_30,
cells_60), ``<work>/his_mesh.json``, ``<work>/mesh_his.png`` (five windows) and ``<work>/mesh_his_overview.png``.
"""

from __future__ import annotations

import json
import sys
import time
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
from scipy import ndimage  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from bed_types import hillshade  # noqa: E402
from compare_meshes import base_config, ring_record, write_layer  # noqa: E402
from stream_corridors import DX  # noqa: E402
from stream_maps import HALF, cell_rings, pick_windows  # noqa: E402
from wadi2d.grid.quad import QuadGrid, pad_to_lattice  # noqa: E402
from wadi2d.grid.tiles import TileGrid  # noqa: E402
from wadi2d.mesh.streams import read_coarse  # noqa: E402
from wadi2d.run import domain_mask, grid_window  # noqa: E402
from wadi2d.solver.layout import TILE  # noqa: E402
from wadi2d.strips.banks import corridor_specs_thalweg, read_layers, read_thalwegs  # noqa: E402
from wadi2d.strips.build import snap_geometry  # noqa: E402
from wadi2d.strips.mesher import Corridor, build_strip_mesh  # noqa: E402
from wadi2d.terrain import RasterBed  # noqa: E402
from wadi2d.terrain.vector import read_features  # noqa: E402

STEEP = 0.20
"""His mountain: ground steeper than this, m/m."""
STEEP_SHARE = 0.9
"""A tile is mountain when this share of its active cells is steep: his 'continuous slope'."""
ANALYSIS_M = 5.0


def quad_cells(quad: QuadGrid, level: int) -> list[np.ndarray]:
    """Polygons of every active cell of the tiles at ``level``."""
    out = []
    for t in range(1, quad.ntiles):
        if int(quad.level[t]) != level:
            continue
        size = quad.dx * (1 << level)
        tj, ti = int(quad.tiles[t, 0]), int(quad.tiles[t, 1])
        x0 = quad.x0 + ti * TILE * quad.dx
        y0 = quad.y0 - tj * TILE * quad.dx
        for a, b in np.argwhere(quad.cells[t]):
            x, y = x0 + b * size, y0 - (a + 1) * size
            out.append(np.array([[x, y], [x + size, y], [x + size, y + size], [x, y + size]]))
    return out


def main(work: Path) -> None:
    cfg = base_config()
    banks, _by_area = read_layers(work / "suggest_floor" / "suggested_breaklines.gpkg")
    thalwegs = read_thalwegs(work / "suggest_floor" / "suggested_breaklines.gpkg")
    domain = shapely.union_all([shape for _p, shape in read_features(cfg.grid.domain, "")])
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        crs = bed.crs.to_wkt() if bed.crs is not None else None
    grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
    report: dict = {"dx": DX, "coarse_dx": 2 * DX, "steep": STEEP, "steep_share": STEEP_SHARE, "squares_uniform": int(mask.sum())}

    t0 = time.perf_counter()
    specs, cut, rules = corridor_specs_thalweg(thalwegs, banks, domain, cell=DX, along=DX)
    corridors = [Corridor(s["name"], shapely.LineString(s["centre"]), np.asarray(s["offsets"]), DX, {r["row"]: snap_geometry(r["coordinates"]) for r in s["snap"]}, snap_nearest=False) for s in specs]
    strip = build_strip_mesh(grid, corridors, 0.5 * DX, 5)
    cells_c, tri, replaced = int((strip.corridor >= 0).sum()), int((strip.corridor < 0).sum()), int(strip.masked[0].size)
    across = [r["cells_across"] for r in rules]
    report.update(
        thalwegs=len(thalwegs), thalweg_km=round(sum(t["line"].length for t in thalwegs) / 1000.0, 1),
        corridors=len(specs), corridor_km=round(sum(float(np.hypot(*np.diff(np.asarray(s["centre"]), axis=0).T).sum()) for s in specs) / 1000.0, 1),
        rejected={w: sum(1 for c in cut if c["why"].startswith(w)) for w in ("a bank on one side", "banks on both sides", "inside an accepted", "free stretches")},
        cells_across={str(k): int(sum(1 for a in across if a == k)) for k in sorted(set(across))},
        width_m_median=round(float(np.median([r["width_m"] for r in rules])), 1) if rules else None,
        corridor_cells=cells_c, gap_triangles=tri, squares_replaced=replaced, corridor_s=round(time.perf_counter() - t0, 1),
    )
    print(f"corridors: {len(specs)} along {report['corridor_km']} km of {report['thalweg_km']} km, {cells_c:,} cells, {tri:,} triangles, {replaced:,} squares replaced; cells across {report['cells_across']}; rejected {report['rejected']}", flush=True)

    # the mountains: slope per 30 m cell from the 5 m ground, a tile coarse where nine in ten cells are steep
    t0 = time.perf_counter()
    ny, nx = mask.shape
    factor = int(round(DX / ANALYSIS_M))
    z = read_coarse(cfg.terrain.dem, window.x0, window.y0, ny, nx, DX, factor)
    filled = np.where(np.isfinite(z), z, np.nanmean(z))
    gy, gx = np.gradient(filled, ANALYSIS_M)
    slope = np.hypot(gx, gy).reshape(ny, factor, nx, factor).mean(axis=(1, 3))
    steep = (slope > STEEP) & mask
    padded, rows, cols = pad_to_lattice(mask, 1)
    px, py = window.x0 - cols * DX, window.y0 + rows * DX
    steep_p = np.zeros(padded.shape, bool)
    steep_p[rows : rows + ny, cols : cols + nx] = steep
    nty, ntx = padded.shape[0] // TILE, padded.shape[1] // TILE
    active = padded.reshape(nty, TILE, ntx, TILE).sum(axis=(1, 3))
    share = steep_p.reshape(nty, TILE, ntx, TILE).sum(axis=(1, 3)) / np.maximum(active, 1)
    level = ((share >= STEEP_SHARE) & (active > 0)).astype(np.int32)
    # the wadis stay fine: tiles with a corridor cell or a thalweg
    jj, ii = strip.masked  # one cell north and west of the mask, as the strip grid is padded: the lattice's own indices
    level[(jj + rows - 1) // TILE, (ii + cols - 1) // TILE] = 0
    for t in thalwegs:
        pts = shapely.get_coordinates(shapely.line_interpolate_point(t["line"], np.arange(0.0, t["line"].length, DX)))
        tj = ((py - pts[:, 1]) // DX).astype(int) // TILE
        ti = ((pts[:, 0] - px) // DX).astype(int) // TILE
        ok = (tj >= 0) & (tj < nty) & (ti >= 0) & (ti < ntx)
        level[tj[ok], ti[ok]] = 0
    quad = QuadGrid.from_levels(padded, px, py, DX, level)
    fine = quad_cells(quad, 0)
    coarse = quad_cells(quad, 1)
    steep_km2 = float(steep.sum()) * DX * DX * 1e-6
    report.update(
        steep_km2=round(steep_km2, 1), domain_km2=round(float(mask.sum()) * DX * DX * 1e-6, 1),
        coarse_tiles=int((quad.level == 1).sum()), fine_tiles=int((quad.level[1:] == 0).sum()),
        cells_30=len(fine) - replaced, cells_60=len(coarse), mountain_s=round(time.perf_counter() - t0, 1),
    )
    total = report["cells_30"] + report["cells_60"] + cells_c + tri
    report.update(total_cells=total, against_uniform=round(total / report["squares_uniform"], 4))
    print(f"mountains: {steep_km2:.0f} of {report['domain_km2']} km2 steeper than 20 %; {report['coarse_tiles']} coarse tiles of 60 m cells ({len(coarse):,} cells) and {report['fine_tiles']} fine; 30 m squares kept {report['cells_30']:,}", flush=True)
    print(f"TOTAL {total:,} cells against {report['squares_uniform']:,} uniform squares ({100 * (report['against_uniform'] - 1):+.1f} %)", flush=True)
    (work / "his_mesh.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

    # layers
    path = work / "mesh_his.gpkg"
    if path.exists():
        path.unlink()
    rings = cell_rings(strip.geometry)
    area, cx, cy = strip.geometry.areas_centroids()
    poly = {"geometry": "Polygon", "properties": {"corridor": "int", "row": "int", "area_m2": "float"}}
    is_corr = strip.corridor >= 0
    write_layer(path, "corridor_cells", crs, poly, (ring_record(rings[c], {"corridor": int(strip.corridor[c]), "row": int(strip.row[c]), "area_m2": float(area[c])}) for c in np.nonzero(is_corr)[0]))
    write_layer(path, "gap_triangles", crs, poly, (ring_record(rings[c], {"corridor": -1, "row": -1, "area_m2": float(area[c])}) for c in np.nonzero(~is_corr)[0]))
    write_layer(path, "corridors", crs, {"geometry": "Polygon", "properties": {"name": "str", "rows": "int", "width_m": "float"}}, (
        {"geometry": shapely.geometry.mapping(p), "properties": {"name": s["name"], "rows": len(s["offsets"]) - 1, "width_m": float(s["offsets"][-1] - s["offsets"][0])}}
        for p, s in zip(strip.polygons, specs, strict=True) if p.geom_type == "Polygon"
    ))
    write_layer(path, "floor_edges", crs, {"geometry": "LineString", "properties": {"side": "str", "area_km2": "float"}}, (
        {"geometry": shapely.geometry.mapping(b["line"]), "properties": {"side": b["side"], "area_km2": float(b["area_km2"])}} for b in banks
    ))
    write_layer(path, "thalwegs", crs, {"geometry": "LineString", "properties": {"area_km2": "float", "incised_m": "float"}}, (
        {"geometry": shapely.geometry.mapping(t["line"]), "properties": {"area_km2": float(t["area_km2"]), "incised_m": float(t["incised_m"])}} for t in thalwegs
    ))
    kept = np.ones(len(fine), bool)
    if replaced:
        removed = {(float(x), float(y)) for x, y in zip(*grid.xy_of(jj, ii), strict=True)}
        kept = np.array([(float(r[:, 0].mean()), float(r[:, 1].mean())) not in removed for r in fine])
    sq = {"geometry": "Polygon", "properties": {"size_m": "float"}}
    write_layer(path, "cells_30", crs, sq, (ring_record(r, {"size_m": DX}) for r, k in zip(fine, kept, strict=True) if k))
    write_layer(path, "cells_60", crs, sq, (ring_record(r, {"size_m": 2 * DX}) for r in coarse))
    print("wrote", path, flush=True)

    # maps: the four windows and a mountain one
    picks = pick_windows(thalwegs, strip.polygons, domain)
    coarse_map = np.zeros((nty, ntx), bool)
    for t in range(1, quad.ntiles):
        if quad.level[t] == 1:
            tj, ti = quad.tiles[t]
            coarse_map[tj : tj + 2, ti : ti + 2] = True
    dist = ndimage.distance_transform_cdt(coarse_map)
    tj, ti = np.unravel_index(int(np.argmax(dist)), dist.shape)
    picks["mountain"] = (px + (ti + 0.5) * TILE * DX, py - (tj + 0.5) * TILE * DX, f"mountain: {int(dist.max())} tiles deep in ground over 20 %")
    fine_kept = [r for r, k in zip(fine, kept, strict=True) if k]
    fine_c = np.array([[r[:, 0].mean(), r[:, 1].mean()] for r in fine_kept]) if fine_kept else np.zeros((0, 2))
    coarse_c = np.array([[r[:, 0].mean(), r[:, 1].mean()] for r in coarse]) if coarse else np.zeros((0, 2))
    fig, axes = plt.subplots(2, 3, figsize=(24, 16), dpi=100)
    with rasterio.open(cfg.terrain.dem) as dem:
        for ax, (label, (x, y, words)) in zip(axes.ravel(), picks.items(), strict=False):
            half = HALF if label != "mountain" else 2.0 * HALF
            box = (x - half, y - half, x + half, y + half)
            shade, _z = hillshade(dem, box)
            ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1, alpha=0.85)
            inside = (fine_c[:, 0] > box[0] - 60) & (fine_c[:, 0] < box[2] + 60) & (fine_c[:, 1] > box[1] - 60) & (fine_c[:, 1] < box[3] + 60) if fine_c.size else np.zeros(0, bool)
            if inside.any():
                ax.add_collection(PolyCollection([fine_kept[k] for k in np.nonzero(inside)[0]], facecolors="none", edgecolors="#707070", linewidths=0.3))
            inside = (coarse_c[:, 0] > box[0] - 60) & (coarse_c[:, 0] < box[2] + 60) & (coarse_c[:, 1] > box[1] - 60) & (coarse_c[:, 1] < box[3] + 60) if coarse_c.size else np.zeros(0, bool)
            if inside.any():
                ax.add_collection(PolyCollection([coarse[k] for k in np.nonzero(inside)[0]], facecolors="#50505018", edgecolors="#303030", linewidths=0.6))
            near = (cx > box[0] - 60) & (cx < box[2] + 60) & (cy > box[1] - 60) & (cy < box[3] + 60)
            tri_r = [rings[c] for c in np.nonzero(near & ~is_corr)[0]]
            cor_r = [rings[c] for c in np.nonzero(near & is_corr)[0]]
            if tri_r:
                ax.add_collection(PolyCollection(tri_r, facecolors="#f0a03040", edgecolors="#c86400", linewidths=0.5))
            if cor_r:
                ax.add_collection(PolyCollection(cor_r, facecolors="#2a7fd440", edgecolors="#1b4f8a", linewidths=0.6))
            w = shapely.box(*box)
            segs = [np.asarray(t["line"].coords) for t in thalwegs if t["line"].intersects(w)]
            if segs:
                ax.add_collection(LineCollection(segs, colors="#d40000", linewidths=1.1, linestyles="--"))
            bsegs = [np.asarray(b["line"].coords) for b in banks if b["line"].intersects(w)]
            if bsegs:
                ax.add_collection(LineCollection(bsegs, colors="#008000", linewidths=1.0))
            ax.set_title(f"{words}: {len(cor_r)} corridor cells, {len(tri_r)} triangles", fontsize=9)
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
            ax.set_aspect("equal")
            ax.tick_params(labelsize=6)
            ax.ticklabel_format(useOffset=False, style="plain")
        axes.ravel()[-1].axis("off")
        axes.ravel()[-1].text(0.02, 0.95, "\n".join([
            "His rule, Block 2 at 30 m, geometry only:",
            f"  uniform squares {report['squares_uniform']:,}",
            f"  30 m squares kept {report['cells_30']:,}",
            f"  60 m cells on the mountains {report['cells_60']:,} ({report['coarse_tiles']} tiles)",
            f"  corridor cells {cells_c:,} ({len(specs)} corridors, {report['corridor_km']} km of {report['thalweg_km']} km)",
            f"  gap triangles {tri:,}",
            f"  total {total:,} ({100 * (report['against_uniform'] - 1):+.1f} % against uniform)",
            f"  cells across the floor: {report['cells_across']}",
            f"  streams left as squares: {report['rejected']}",
            "colours: blue corridor cells, orange triangles, grey 30 m squares,",
            "dark grey 60 m cells, red dashed thalwegs, green the 5 % floor edges",
        ]), va="top", fontsize=11, family="monospace")
    fig.suptitle("His rule: 30 m cells on wadis and plains, corridors across the under-5 % floor on the 1 km2 streams, 60 m cells where the mountains are steeper than 20 %", fontsize=11)
    fig.savefig(work / "mesh_his.png", bbox_inches="tight")
    print("wrote", work / "mesh_his.png", flush=True)

    x0, y0, x1, y1 = domain.bounds
    fig, ax = plt.subplots(figsize=(12, 12 * (y1 - y0) / (x1 - x0)), dpi=120)
    with rasterio.open(cfg.terrain.dem) as dem:
        win = from_bounds(x0, y0, x1, y1, transform=dem.transform)
        scale = max(1, int(round(min(win.width, win.height) / 2000)))
        zz = dem.read(1, window=win, out_shape=(int(win.height // scale), int(win.width // scale)), resampling=Resampling.average).astype(np.float64)
        zz = np.where(zz < -1000, np.nan, zz)
        gy, gx = np.gradient(np.nan_to_num(zz, nan=np.nanmean(zz)), dem.res[0] * scale)
        az, alt = np.radians(315.0), np.radians(45.0)
        sl = np.arctan(np.hypot(gx, gy))
        asp = np.arctan2(-gx, gy)
        shade = np.clip(np.sin(alt) * np.cos(sl) + np.cos(alt) * np.sin(sl) * np.cos(az - asp), 0, 1)
    ax.imshow(shade, extent=(x0, x1, y0, y1), cmap="gray", vmin=0, vmax=1, alpha=0.9)
    tiles60 = []
    for t in range(1, quad.ntiles):
        if quad.level[t] == 1:
            tj, ti = quad.tiles[t]
            xa, ya = px + ti * TILE * DX, py - (tj + 2) * TILE * DX
            s = 2 * TILE * DX
            tiles60.append(np.array([[xa, ya], [xa + s, ya], [xa + s, ya + s], [xa, ya + s]]))
    if tiles60:
        ax.add_collection(PolyCollection(tiles60, facecolors="#50505060", edgecolors="#303030", linewidths=0.3))
    ax.add_collection(PolyCollection([np.asarray(p.exterior.coords) for p in strip.polygons], facecolors="#2a7fd4", edgecolors="#1b4f8a", linewidths=0.3))
    for key, (x, y, _w) in picks.items():
        half = HALF if key != "mountain" else 2.0 * HALF
        ax.add_patch(plt.Rectangle((x - half, y - half), 2 * half, 2 * half, fill=False, edgecolor="#ffa500", lw=1.5))
        ax.annotate(key, (x + half, y + half), color="#ffa500", fontsize=9)
    ax.set_title(f"His rule on Block 2 at 30 m: 60 m tiles on the mountains (dark grey, {report['coarse_tiles']} tiles), corridors across the floor of the 1 km2 streams (blue, {len(specs)}), 30 m squares elsewhere", fontsize=10)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=6)
    ax.ticklabel_format(useOffset=False, style="plain")
    fig.savefig(work / "mesh_his_overview.png", bbox_inches="tight")
    print("wrote", work / "mesh_his_overview.png", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
