"""Streams as breaklines, no banks (his direction of 2026-11-07, evening): corridors of 30 m cells along the
thalwegs of the 1 km2 streams on Block 2 at 30 m, the stream on the shared face row of two cells across (what a
HEC-RAS breakline does), no snapping, no banks, no crest. The question: how many cells, and how many more than the
plain squares.

    .venv\\Scripts\\python "W45 aligned mesh engine\\stream_corridors.py" <work folder> [rows_across]

Writes ``<work>/suggest_1km2/`` (the thalwegs at 1 km2), ``<work>/stream_corridors.json`` and a count per stage.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wadi2d.breaklines import suggest  # noqa: E402
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.grid.tiles import TileGrid  # noqa: E402
from wadi2d.run import domain_mask, grid_window  # noqa: E402
from wadi2d.strips.banks import CLEAR_M, fold_free_specs  # noqa: E402
from wadi2d.strips.mesher import Corridor, build_strip_mesh, corridor_nodes, corridor_polygon  # noqa: E402
from wadi2d.terrain import RasterBed  # noqa: E402
from wadi2d.terrain.vector import read_features  # noqa: E402

JOB = ROOT / "W45 aligned mesh engine" / "scale_block2" / "block2_30m.json"
DX = 30.0
MIN_LENGTH_M = 300.0


def thalweg_lines(path: Path) -> list[dict]:
    import fiona

    out = []
    with fiona.open(path, layer="thalwegs") as src:
        for f in src:
            g = shapely.geometry.shape(f["geometry"])
            if g.geom_type == "MultiLineString":
                g = max(g.geoms, key=lambda part: part.length)
            out.append({"line": shapely.LineString(np.asarray(g.coords)[:, :2]), **dict(f["properties"])})
    return out


def specs_along(lines: list[dict], domain: shapely.Geometry, offsets: list[float], along: float) -> tuple[list[dict], list[dict]]:
    """A corridor along every thalweg, biggest first, cut clear of the accepted ones, the domain edge and its folds."""
    extent = offsets[-1]
    outside = domain.envelope.buffer(4.0 * extent).difference(domain.buffer(-along))
    accepted, polygons, cut = [], [], []
    for k, t in enumerate(sorted(lines, key=lambda t: -t["area_km2"])):
        if t["line"].length < MIN_LENGTH_M:
            continue
        spec = {"name": f"s{k}_{t['area_km2']:.1f}km2", "centre": [[float(x), float(y)] for x, y in t["line"].coords], "offsets": offsets, "snap": []}
        keep_out = shapely.unary_union([outside, *[p.buffer(CLEAR_M) for p in polygons]])
        pieces, words = fold_free_specs(spec, along, keep_out=keep_out, min_length=MIN_LENGTH_M)
        cut.extend({"name": spec["name"], "why": w} for w in words)
        for piece in pieces:
            accepted.append(piece)
            built = Corridor(piece["name"], shapely.LineString(piece["centre"]), np.asarray(offsets), along, {})
            polygons.append(corridor_polygon(*corridor_nodes(built)))
    return accepted, cut


def main(work: Path, rows: int) -> None:
    work.mkdir(parents=True, exist_ok=True)
    data = json.loads(JOB.read_text(encoding="utf-8"))
    data.setdefault("mesh", {})["stream_area_mid_km2"] = 1.0
    data["mesh"]["enabled"] = False
    data.pop("strips", None)
    cfg = RunConfig.model_validate(data)
    report: dict = {"dx": cfg.grid.dx, "stream_area_km2": 1.0, "rows_across": rows}
    t0 = time.perf_counter()
    out = work / "suggest_1km2"
    if not (out / "suggested_breaklines.gpkg").is_file():
        summary = suggest(cfg, out)
        (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    report["suggest_s"] = round(time.perf_counter() - t0, 1)
    lines = thalweg_lines(out / "suggested_breaklines.gpkg")
    km = sum(t["line"].length for t in lines) / 1000.0
    incised = [t for t in lines if t.get("incised_m", 0.0) >= cfg.mesh.incision_depth]
    report.update(thalwegs=len(lines), thalweg_km=round(km, 1), incised_thalwegs=len(incised), incised_km=round(sum(t["line"].length for t in incised) / 1000.0, 1))
    print(f"streams at 1 km2: {len(lines)} thalwegs over {km:.0f} km ({report['incised_km']} km incised over {cfg.mesh.incision_depth} m), suggest {report['suggest_s']} s")

    domain = shapely.union_all([shape for _p, shape in read_features(cfg.grid.domain, "")])
    half = 0.5 * rows * DX
    offsets = [float(v) for v in np.linspace(-half, half, rows + 1)]
    t0 = time.perf_counter()
    specs, cut = specs_along(lines, domain, offsets, DX)
    corridor_km = sum(float(np.hypot(*np.diff(np.asarray(s["centre"]), axis=0).T).sum()) for s in specs) / 1000.0
    report.update(corridors=len(specs), corridor_km=round(corridor_km, 1), cut=len(cut), specs_s=round(time.perf_counter() - t0, 1))
    print(f"corridors: {len(specs)} along {corridor_km:.0f} km in {report['specs_s']} s, {len(cut)} pieces cut at folds, edges or neighbours")

    t0 = time.perf_counter()
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
    grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
    squares = int(grid.mask.sum())
    report.update(squares=squares, grid_s=round(time.perf_counter() - t0, 1))
    print(f"plain squares at {DX:g} m: {squares:,} in {report['grid_s']} s")

    t0 = time.perf_counter()
    corridors = [Corridor(s["name"], shapely.LineString(s["centre"]), np.asarray(s["offsets"]), DX, {}) for s in specs]
    strip = build_strip_mesh(grid, corridors, 0.5 * DX, 5)
    cells = int((strip.corridor >= 0).sum())
    triangles = int((strip.corridor < 0).sum())
    replaced = int(strip.masked[0].size)
    total = squares - replaced + cells + triangles
    report.update(
        corridor_cells=cells, triangles=triangles, replaced=replaced, total_cells=total,
        extra_cells=total - squares, extra_share=round((total - squares) / squares, 4), strip_s=round(time.perf_counter() - t0, 1),
    )
    print(f"strip mesh: {cells:,} corridor cells, {triangles:,} gap triangles, {replaced:,} squares replaced, in {report['strip_s']} s")
    print(f"TOTAL {total:,} cells against {squares:,} squares: {total - squares:+,} ({100 * (total - squares) / squares:+.2f} %)")
    (work / f"stream_corridors_{rows}rows.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 2)
