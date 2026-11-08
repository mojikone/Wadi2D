"""Three ways to mesh Block 2 at 30 m around its 1 km2 streams, built side by side for him to check (2026-11-07):

- ``streams``: every stream as a corridor of two 30 m cells, the stream on the shared face, no banks, no edge.
- ``floor``: his rule, under 5 % is floodplain: the floor's edges where the ground climbs over 5 % for 40 m and
  stands 2 m over the bed (``bank_method: slope``), cells of 30 m repeated across the floor, no row outside; a stream
  with no edge within 300 m on a side (a fan, a plain) gets no corridor and stays squares.
- ``dock``: what the Mesh section builds today: banks where the ground rises 2 m over the bed, cells across a quarter
  of the width between 20 and 50 m, one row outside each bank.

Geometry only, no solver. Writes ``<work>/mesh_<kind>.gpkg`` (corridor_cells, gap_triangles, corridors, banks,
thalwegs), ``<work>/lattice_squares.gpkg`` once (the plain 30 m squares), ``<work>/compare_meshes.json``,
``<work>/mesh_<kind>.png`` on the four windows of ``stream_maps.py`` and ``<work>/mesh_compare.png`` with the three
side by side.

    .venv\\Scripts\\python "W45 aligned mesh engine\\compare_meshes.py" <work folder of stream_corridors.py>
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
from stream_maps import HALF, cell_rings, pick_windows  # noqa: E402
from wadi2d.breaklines import suggest  # noqa: E402
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.grid.tiles import TileGrid  # noqa: E402
from wadi2d.run import domain_mask, grid_window  # noqa: E402
from wadi2d.strips.banks import CellRule, corridor_specs, pair_banks, read_layers  # noqa: E402
from wadi2d.strips.mesher import Corridor, build_strip_mesh  # noqa: E402
from wadi2d.terrain import RasterBed  # noqa: E402
from wadi2d.terrain.vector import read_features  # noqa: E402

KINDS = {
    "streams": "every 1 km2 stream as two 30 m cells, no banks",
    "floor": "under 5 % is floodplain: 30 m cells repeated across the floor between its edges",
    "dock": "the Mesh section today: banks 2 m over the bed, cells a quarter of the width within 20 to 50 m, a row outside",
}
COLOURS = {"corridor": ("#2a7fd440", "#1b4f8a"), "triangle": ("#f0a03040", "#c86400")}


def base_config() -> RunConfig:
    data = json.loads(JOB.read_text(encoding="utf-8"))
    data.setdefault("mesh", {})["stream_area_mid_km2"] = 1.0
    data["mesh"]["enabled"] = False
    data.pop("strips", None)
    return RunConfig.model_validate(data)


def write_layer(path: Path, layer: str, crs, schema: dict, rows) -> None:
    with fiona.open(path, "w", driver="GPKG", layer=layer, schema=schema, crs=crs) as dst:
        dst.writerecords(rows)


def ring_record(ring: np.ndarray, props: dict) -> dict:
    return {"geometry": {"type": "Polygon", "coordinates": [[tuple(p) for p in ring] + [tuple(ring[0])]]}, "properties": props}


def build(kind: str, cfg: RunConfig, work: Path, grid: TileGrid, domain: shapely.Geometry, report: dict) -> tuple:
    """The corridor specs and the strip mesh of one kind, with the banks it used (None for streams)."""
    t0 = time.perf_counter()
    banks = None
    if kind == "streams":
        lines = thalweg_lines(work / "suggest_1km2" / "suggested_breaklines.gpkg")
        specs, cut = specs_along(lines, domain, [-DX, 0.0, DX], DX)
        rules = []
    else:
        if kind == "floor":
            out = work / "suggest_floor"
            if not (out / "suggested_breaklines.gpkg").is_file():
                floor_cfg = cfg.model_copy(update={"breaklines": cfg.breaklines.model_copy(update={"bank_method": "slope"})})
                summary = suggest(floor_cfg, out)
                (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
            rule = CellRule(DX, DX, 1.0, 0)
        else:
            out = work / "suggest_1km2"
            rule = CellRule()
        banks_raw, thalwegs = read_layers(out / "suggested_breaklines.gpkg")
        banks = banks_raw
        pairs = pair_banks(banks_raw, thalwegs)
        report[kind]["bank_lines"], report[kind]["bank_km"] = len(banks_raw), round(sum(b["line"].length for b in banks_raw) / 1000.0, 1)
        report[kind]["pairs"] = len(pairs)
        specs, cut, rules = corridor_specs(pairs, domain, rule, DX)
    report[kind]["corridors"] = len(specs)
    report[kind]["corridor_km"] = round(sum(float(np.hypot(*np.diff(np.asarray(s["centre"]), axis=0).T).sum()) for s in specs) / 1000.0, 1)
    report[kind]["cut"] = len(cut)
    if rules:
        across = [r["cells_across"] for r in rules]
        report[kind]["cells_across"] = {str(k): int(sum(1 for a in across if a == k)) for k in sorted(set(across))}
        report[kind]["across_m_median"] = round(float(np.median([r["across_m"] for r in rules])), 1)
        report[kind]["width_m_median"] = round(float(np.median([r["width_m"] for r in rules])), 1)
    report[kind]["build_s"] = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    corridors = [Corridor(s["name"], shapely.LineString(s["centre"]), np.asarray(s["offsets"]), DX, {row["row"]: shapely.LineString(row["coordinates"]) for row in s["snap"]}) for s in specs]
    strip = build_strip_mesh(grid, corridors, 0.5 * DX, 5)
    squares = int(grid.mask.sum())
    cells, triangles, replaced = int((strip.corridor >= 0).sum()), int((strip.corridor < 0).sum()), int(strip.masked[0].size)
    total = squares - replaced + cells + triangles
    report[kind].update(
        corridor_cells=cells, gap_triangles=triangles, squares_replaced=replaced, total_cells=total,
        extra_cells=total - squares, extra_share=round((total - squares) / squares, 4), mesh_s=round(time.perf_counter() - t0, 1),
    )
    print(f"{kind}: {len(specs)} corridors along {report[kind]['corridor_km']} km, {cells:,} cells, {triangles:,} triangles, {replaced:,} replaced: {total:,} against {squares:,} ({100 * (total - squares) / squares:+.2f} %)", flush=True)
    return specs, strip, banks


def write_mesh(kind: str, work: Path, crs, specs: list[dict], strip, banks, lines: list[dict]) -> Path:
    path = work / f"mesh_{kind}.gpkg"
    if path.exists():
        path.unlink()
    rings = cell_rings(strip.geometry)
    area, _cx, _cy = strip.geometry.areas_centroids()
    poly = {"geometry": "Polygon", "properties": {"corridor": "int", "row": "int", "area_m2": "float"}}
    is_corr = strip.corridor >= 0
    write_layer(path, "corridor_cells", crs, poly, (ring_record(rings[c], {"corridor": int(strip.corridor[c]), "row": int(strip.row[c]), "area_m2": float(area[c])}) for c in np.nonzero(is_corr)[0]))
    write_layer(path, "gap_triangles", crs, poly, (ring_record(rings[c], {"corridor": -1, "row": -1, "area_m2": float(area[c])}) for c in np.nonzero(~is_corr)[0]))
    write_layer(path, "corridors", crs, {"geometry": "Polygon", "properties": {"name": "str", "length_m": "float", "rows": "int"}}, (
        {"geometry": shapely.geometry.mapping(p), "properties": {"name": s["name"], "length_m": float(shapely.LineString(s["centre"]).length), "rows": len(s["offsets"]) - 1}}
        for p, s in zip(strip.polygons, specs, strict=True) if p.geom_type == "Polygon"
    ))
    if banks:
        write_layer(path, "banks", crs, {"geometry": "LineString", "properties": {"side": "str", "area_km2": "float"}}, (
            {"geometry": shapely.geometry.mapping(b["line"]), "properties": {"side": b["side"], "area_km2": float(b["area_km2"])}} for b in banks
        ))
    write_layer(path, "thalwegs", crs, {"geometry": "LineString", "properties": {"area_km2": "float", "incised_m": "float"}}, (
        {"geometry": shapely.geometry.mapping(t["line"]), "properties": {"area_km2": float(t["area_km2"]), "incised_m": float(t.get("incised_m", 0.0))}} for t in lines
    ))
    return path


def draw(ax, dem, box, grid, kept, strip, rings, cx, cy, lines, banks, title: str) -> None:
    shade, _z = hillshade(dem, box)
    ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1, alpha=0.85)
    j0, j1 = max(0, int((grid.y0 - box[3]) // DX) - 1), min(grid.shape[0], int((grid.y0 - box[1]) // DX) + 2)
    i0, i1 = max(0, int((box[0] - grid.x0) // DX) - 1), min(grid.shape[1], int((box[2] - grid.x0) // DX) + 2)
    sq = [np.array([[grid.x0 + i * DX, grid.y0 - (j + 1) * DX], [grid.x0 + (i + 1) * DX, grid.y0 - (j + 1) * DX], [grid.x0 + (i + 1) * DX, grid.y0 - j * DX], [grid.x0 + i * DX, grid.y0 - j * DX]]) for j in range(j0, j1) for i in range(i0, i1) if kept[j, i]]
    if sq:
        ax.add_collection(PolyCollection(sq, facecolors="none", edgecolors="#707070", linewidths=0.35))
    inside = (cx > box[0] - 60) & (cx < box[2] + 60) & (cy > box[1] - 60) & (cy < box[3] + 60)
    tri = [rings[c] for c in np.nonzero(inside & (strip.corridor < 0))[0]]
    corr = [rings[c] for c in np.nonzero(inside & (strip.corridor >= 0))[0]]
    if tri:
        ax.add_collection(PolyCollection(tri, facecolors=COLOURS["triangle"][0], edgecolors=COLOURS["triangle"][1], linewidths=0.5))
    if corr:
        ax.add_collection(PolyCollection(corr, facecolors=COLOURS["corridor"][0], edgecolors=COLOURS["corridor"][1], linewidths=0.6))
    window = shapely.box(*box)
    segs = [np.asarray(t["line"].coords) for t in lines if t["line"].intersects(window)]
    if segs:
        ax.add_collection(LineCollection(segs, colors="#d40000", linewidths=1.1, linestyles="--"))
    if banks:
        bsegs = [np.asarray(b["line"].coords) for b in banks if b["line"].intersects(window)]
        if bsegs:
            ax.add_collection(LineCollection(bsegs, colors="#008000", linewidths=1.0))
    ax.set_title(f"{title}: {len(corr)} corridor cells, {len(tri)} triangles", fontsize=8.5)
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_aspect("equal")
    ax.tick_params(labelsize=6)
    ax.ticklabel_format(useOffset=False, style="plain")


def main(work: Path) -> None:
    cfg = base_config()
    lines = thalweg_lines(work / "suggest_1km2" / "suggested_breaklines.gpkg")
    domain = shapely.union_all([shape for _p, shape in read_features(cfg.grid.domain, "")])
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        crs = bed.crs.to_wkt() if bed.crs is not None else None
    grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
    lattice = work / "lattice_squares.gpkg"
    if not lattice.exists():
        jj, ii = np.nonzero(grid.mask)
        xa, ya = grid.x0 + ii * DX, grid.y0 - (jj + 1) * DX
        write_layer(lattice, "squares", crs, {"geometry": "Polygon", "properties": {"j": "int", "i": "int"}}, (
            {"geometry": {"type": "Polygon", "coordinates": [[(x, y), (x + DX, y), (x + DX, y + DX), (x, y + DX), (x, y)]]}, "properties": {"j": int(j), "i": int(i)}}
            for x, y, j, i in zip(xa.tolist(), ya.tolist(), jj.tolist(), ii.tolist(), strict=True)
        ))
        print(f"lattice: {jj.size:,} squares written", flush=True)
    report: dict = {k: {"what": v} for k, v in KINDS.items()}
    report["squares"] = int(grid.mask.sum())
    built = {}
    for kind in KINDS:
        specs, strip, banks = build(kind, cfg, work, grid, domain, report)
        write_mesh(kind, work, crs, specs, strip, banks, lines)
        built[kind] = (specs, strip, banks)
        (work / "compare_meshes.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    picks = pick_windows(lines, built["streams"][1].polygons, domain)
    fig_all, axes_all = plt.subplots(3, 4, figsize=(26, 19.5), dpi=100)
    with rasterio.open(cfg.terrain.dem) as dem:
        for r, kind in enumerate(KINDS):
            specs, strip, banks = built[kind]
            rings = cell_rings(strip.geometry)
            _a, cx, cy = strip.geometry.areas_centroids()
            kept = grid.mask.copy()
            kept[strip.masked] = False
            fig, axes = plt.subplots(2, 2, figsize=(16, 16), dpi=110)
            for ax, ax_all, (label, (x, y, words)) in zip(axes.ravel(), axes_all[r], picks.items(), strict=False):
                box = (x - HALF, y - HALF, x + HALF, y + HALF)
                draw(ax, dem, box, grid, kept, strip, rings, cx, cy, lines, banks, words)
                draw(ax_all, dem, box, grid, kept, strip, rings, cx, cy, lines, banks, f"{kind}, {label}")
            fig.suptitle(f"Block 2 at 30 m, {kind}: {KINDS[kind]}. Blue corridor cells, orange gap triangles, grey squares, red dashed thalwegs, green the banks used. {report[kind]['total_cells']:,} cells, {100 * report[kind]['extra_share']:+.1f} % over the squares", fontsize=10)
            fig.savefig(work / f"mesh_{kind}.png", bbox_inches="tight")
            plt.close(fig)
            print("wrote", work / f"mesh_{kind}.png", flush=True)
    fig_all.suptitle("Block 2 at 30 m, the three meshes on the same four windows. Rows: streams as two-cell corridors; the under-5 % floor with 30 m cells across; the Mesh section's rule today", fontsize=11)
    fig_all.savefig(work / "mesh_compare.png", bbox_inches="tight")
    print("wrote", work / "mesh_compare.png", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
