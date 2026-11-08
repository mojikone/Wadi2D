"""His centre-based generator on Block 2 at 30 m (W46, his rules of 2026-11-08), geometry only, no solver run.

The 1 km2 thalwegs of the W45 Suggest file are the guide lines, ranked by drainage area; the floor rule reads the
banks on the 5 m DEM (scarp of 1 m within 10 m, rise of 2 m, the 5 % slope as a cap); the mesh is the Voronoi
diagram of the centres with the lattice around it. Writes ``mesh_centres.gpkg`` (line_cells, band_cells, line_faces,
thalwegs), ``centres.json``, ``mesh_centres.png`` (five windows) and ``mesh_centres_overview.png``.

    .venv\\Scripts\\python "W46 centre-based mesh generator\\block2_centres.py" [work folder]
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from bed_types import hillshade  # noqa: E402
from compare_meshes import base_config, ring_record, write_layer  # noqa: E402
from stream_maps import HALF, cell_rings, pick_windows  # noqa: E402
from wadi2d.grid.tiles import TileGrid  # noqa: E402
from wadi2d.run import domain_mask, grid_window  # noqa: E402
from wadi2d.strips.banks import read_thalwegs  # noqa: E402
from wadi2d.strips.build import centre_mesh_of  # noqa: E402
from wadi2d.terrain import RasterBed  # noqa: E402
from wadi2d.terrain.vector import read_features  # noqa: E402

W45 = ROOT / "W45 aligned mesh engine" / "stream_corridors"
BANKS = W45 / "suggest_floor" / "suggested_breaklines.gpkg"
WORK = Path(__file__).resolve().parent / "block2"
DX = 30.0
FACE_COLOURS = {4: "#d0d0d0", 5: "#ffd27f", 6: "#ffa726", 7: "#e65100", 8: "#b71c1c"}


def colour_of(faces: int, on_line: bool) -> str:
    if on_line:
        return "#2a7fd4"
    return FACE_COLOURS.get(int(min(faces, 8)), "#7b1fa2")


def main(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    path = work / "mesh_centres.gpkg"
    if path.exists():  # before the build, not after it: a QGIS window holding the file cost one run (W45's lesson)
        path.unlink()
    cfg = base_config()
    cfg = cfg.model_copy(update={"strips": cfg.strips.model_copy(update={"enabled": True, "generator": "centres", "banks": str(BANKS)})})
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        crs = bed.crs.to_wkt() if bed.crs is not None else None
    grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
    domain = shapely.union_all([shape for _p, shape in read_features(cfg.grid.domain, "")])
    t0 = time.perf_counter()
    strip = centre_mesh_of(cfg, grid)
    built_s = time.perf_counter() - t0
    geo = strip.geometry
    area, cx, cy = geo.areas_centroids()
    faces = np.diff(geo.ring_start)
    on_line = strip.corridor >= 0
    thalwegs = read_thalwegs(BANKS)
    replaced = int(strip.masked[0].size)
    kept = int(mask.sum()) - replaced
    total = kept + geo.ncells
    lines_built = int((np.array([r["cells"] for r in strip.rules]) > 0).sum())
    report = {
        "dx": DX, "squares_uniform": int(mask.sum()), "thalwegs": len(thalwegs), "lines_with_cells": lines_built,
        "line_cells": int(on_line.sum()), "band_cells": int((~on_line).sum()), "band_squares": int(((~on_line) & np.isclose(area, DX * DX) & (faces == 4)).sum()),
        "faces_histogram": {int(k): int(v) for k, v in sorted(Counter(faces.tolist()).items())},
        "cells_over_8_faces": int((faces > 8).sum()), "cells_under_0.4_square": int((area < 0.4 * DX * DX).sum()),
        "area_m2_min": round(float(area.min()), 1), "area_m2_median": round(float(np.median(area)), 1),
        "line_faces": int(sum(len(v) for v in strip.breakline_edges.values())),
        "squares_replaced": replaced, "squares_kept": kept, "total_cells": total, "against_uniform": round(total / int(mask.sum()), 4),
        "build_s": round(built_s, 1), "notes": len(strip.notes), "notes_sample": strip.notes[:12],
        "cells_across_hist": {str(k): int(v) for k, v in sorted(Counter(r["cells_across"] for r in strip.rules if r["cells"] > 0).items())},
    }  # fmt: skip
    (work / "centres.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for k, v in report.items():
        if k != "notes_sample":
            print(f"{k}: {v}")
    print("TOTAL", f"{total:,} cells against {int(mask.sum()):,} squares ({100 * (report['against_uniform'] - 1):+.1f} %)")

    # layers
    rings = cell_rings(geo)
    poly = {"geometry": "Polygon", "properties": {"line": "int", "row": "int", "faces": "int", "area_m2": "float"}}
    write_layer(path, "line_cells", crs, poly, (ring_record(rings[c], {"line": int(strip.corridor[c]), "row": int(strip.row[c]), "faces": int(faces[c]), "area_m2": float(area[c])}) for c in np.nonzero(on_line)[0]))
    write_layer(path, "band_cells", crs, poly, (ring_record(rings[c], {"line": -1, "row": -1, "faces": int(faces[c]), "area_m2": float(area[c])}) for c in np.nonzero(~on_line)[0]))
    write_layer(path, "line_faces", crs, {"geometry": "LineString", "properties": {"name": "str"}}, (
        {"geometry": {"type": "LineString", "coordinates": [(float(geo.x[a]), float(geo.y[a])), (float(geo.x[b]), float(geo.y[b]))]}, "properties": {"name": name}}
        for name, edges in strip.breakline_edges.items() for a, b in edges
    ))
    write_layer(path, "thalwegs", crs, {"geometry": "LineString", "properties": {"area_km2": "float", "incised_m": "float"}}, (
        {"geometry": shapely.geometry.mapping(t["line"]), "properties": {"area_km2": float(t["area_km2"]), "incised_m": float(t["incised_m"])}} for t in thalwegs
    ))
    # the bed as the floor rule reads it: one bank point per station and side on the stems, as lines, broken where a
    # side has no bank within the reach (his question of 2026-11-08: how is the bed defined, where are the banks)
    from wadi2d.breaklines.window import read_window
    from wadi2d.strips.centres import CentreSettings, Line, chain_streams, stations_of
    from wadi2d.strips.floor import FloorRule, floor_of_line

    win = read_window(cfg)
    rule = FloorRule.from_settings(cfg.breaklines, cfg.grid.dx)
    settings = CentreSettings(dx=cfg.grid.dx)
    records = []
    stems = chain_streams(thalwegs)
    outlines = [p for p in strip.polygons]  # one per stem, in the stems' order; empty where a stem built no cell
    others = shapely.STRtree([p if not p.is_empty else shapely.Point() for p in outlines])
    for k, t in enumerate(stems):
        if k < len(outlines) and outlines[k].is_empty:
            continue  # a stem with no cells, a braid's twin or a plain reach: its bed is not drawn
        pts, normals, _notes = stations_of(Line(f"t{k}", np.asarray(t["line"].coords), t["area_km2"]), settings)
        if pts.shape[0] < 2:
            continue
        seg = np.diff(pts, axis=0)
        normals = np.column_stack((-seg[:, 1], seg[:, 0])) / np.maximum(np.hypot(seg[:, 0], seg[:, 1]), 1e-12)[:, None]
        left, right = floor_of_line(win, pts, rule)
        mids = 0.5 * (pts[:-1] + pts[1:])
        for side, sign, dist in (("left", 1.0, 0.5 * (left[:-1] + left[1:])), ("right", -1.0, 0.5 * (right[:-1] + right[1:]))):
            bank = mids + sign * np.where(np.isfinite(dist), dist, np.nan)[:, None] * normals
            # a bank point inside another stem's cells is a station this stem gave up at a junction: no edge there
            ok = np.isfinite(bank[:, 0])
            if ok.any():
                hits = others.query(shapely.points(bank[ok]), predicate="within")
                inside = np.zeros(int(ok.sum()), bool)
                inside[hits[0][hits[1] != k]] = True
                bank[np.nonzero(ok)[0][inside]] = np.nan
            run: list[list[float]] = []
            for p in bank.tolist() + [[np.nan, np.nan]]:
                if np.isfinite(p[0]):
                    run.append(p)
                elif len(run) >= 2:
                    records.append({"geometry": {"type": "LineString", "coordinates": [tuple(q) for q in run]}, "properties": {"stem": k, "side": side, "area_km2": float(t["area_km2"]), "stations": len(run)}})
                    run = []
                else:
                    run = []
    write_layer(path, "bed_edges", crs, {"geometry": "LineString", "properties": {"stem": "int", "side": "str", "area_km2": "float", "stations": "int"}}, records)
    report["bed_edge_lines"] = len(records)
    print("wrote", path, f"with {len(records)} bed-edge lines", flush=True)

    # maps
    picks = pick_windows(thalwegs, [p if not p.is_empty else shapely.Polygon() for p in strip.polygons], domain)
    colours = np.array([colour_of(f, o) for f, o in zip(faces, on_line, strict=True)])
    fig, axes = plt.subplots(2, 3, figsize=(24, 16), dpi=100)
    with rasterio.open(cfg.terrain.dem) as dem:
        for ax, (label, (x, y, words)) in zip(axes.ravel(), picks.items(), strict=False):
            box = (x - HALF, y - HALF, x + HALF, y + HALF)
            shade, _z = hillshade(dem, box)
            ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1, alpha=0.85)
            inside = (cx > box[0] - 2 * DX) & (cx < box[2] + 2 * DX) & (cy > box[1] - 2 * DX) & (cy < box[3] + 2 * DX)
            idx = np.nonzero(inside)[0]
            ax.add_collection(PolyCollection([rings[c] for c in idx], facecolors=colours[idx], edgecolors=np.where(on_line[idx], "#1b4f8a", "#707070"), linewidths=0.4, alpha=0.6))
            for a, b in ((a, b) for edges in strip.breakline_edges.values() for a, b in edges):
                if box[0] <= geo.x[a] <= box[2] and box[1] <= geo.y[a] <= box[3]:
                    ax.plot([geo.x[a], geo.x[b]], [geo.y[a], geo.y[b]], color="#08306b", linewidth=1.2)
            ax.add_collection(LineCollection([np.asarray(t["line"].coords) for t in thalwegs], colors="#d40000", linewidths=0.8, linestyles="--"))
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
            ax.set_aspect("equal")
            n_line = int((on_line & inside).sum())
            n_band = int(((~on_line) & inside).sum())
            ax.set_title(f"{words}: {n_line} cells on the lines, {n_band} around them", fontsize=10)
    for ax in axes.ravel()[len(picks) : -1]:
        ax.axis("off")
    last = axes.ravel()[-1]
    last.axis("off")
    last.text(0.0, 0.95, "\n".join([
        "Centre generator, Block 2 at 30 m, geometry only:",
        f"  uniform squares {report['squares_uniform']:,}",
        f"  squares kept {kept:,}, replaced {replaced:,}",
        f"  cells on the lines {report['line_cells']:,} ({lines_built} of {len(thalwegs)} thalwegs)",
        f"  cells around them {report['band_cells']:,}, of which exact squares {report['band_squares']:,}",
        f"  faces per cell {report['faces_histogram']}",
        f"  over 8 faces {report['cells_over_8_faces']}, under 0.4 of a square {report['cells_under_0.4_square']}",
        f"  total {total:,} ({100 * (report['against_uniform'] - 1):+.1f} % against uniform)",
        f"  built in {built_s:.0f} s",
        "colours: blue cells on the lines (dark blue faces on the line), grey squares, yellow 5, orange 6,",
        "dark orange 7, dark red 8 faces, purple over 8; red dashed thalwegs",
    ]), family="monospace", fontsize=10, va="top")
    fig.suptitle("His rule, cells from centres: every stream a chain of faces with 4-sided cells either side, rows to the bank, polygons in between", fontsize=13)
    fig.tight_layout()
    fig.savefig(work / "mesh_centres.png")
    print("wrote", work / "mesh_centres.png", flush=True)
    # overview
    fig, ax = plt.subplots(figsize=(14, 14), dpi=100)
    with rasterio.open(cfg.terrain.dem) as dem:
        box = domain.bounds
        shade, _z = hillshade(dem, box)
        ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1, alpha=0.85)
    ax.add_collection(PolyCollection([np.asarray(q.exterior.coords) for p in strip.polygons if not p.is_empty for q in (p.geoms if hasattr(p, "geoms") else [p])], facecolors="#2a7fd4", edgecolors="#1b4f8a", linewidths=0.3))
    for label, (x, y, _w) in picks.items():
        ax.add_patch(plt.Rectangle((x - HALF, y - HALF), 2 * HALF, 2 * HALF, fill=False, edgecolor="#ff8800", linewidth=1.5))
        ax.text(x + HALF, y + HALF, label, color="#ff8800", fontsize=9)
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_aspect("equal")
    ax.set_title(f"Block 2 at 30 m: the cells on the lines of the centre generator (blue, {lines_built} lines), 30 m squares elsewhere")
    fig.tight_layout()
    fig.savefig(work / "mesh_centres_overview.png")
    print("wrote", work / "mesh_centres_overview.png", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else WORK)
