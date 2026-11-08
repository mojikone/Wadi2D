"""The centre generator's mesh of a job, checked as a mesh: cracks, overlaps, non-manifold edges, walls inside the
strip, and what the hybrid would see at its boundary. The run with a wide floor on Faydh lost 5.6 % of its water
(2026-11-08); this finds where a mesh can leak before any run.

    .venv\\Scripts\\python "W46 centre-based mesh generator\\mesh_check.py" <job.json>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.grid.tiles import TileGrid  # noqa: E402
from wadi2d.run import _domain_polygon, domain_mask, grid_window  # noqa: E402
from wadi2d.strips.build import mask_for_strips  # noqa: E402
from wadi2d.terrain import RasterBed  # noqa: E402


def main(job: Path) -> None:
    cfg = RunConfig.model_validate(json.loads(job.read_text(encoding="utf-8")))
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        crs = bed.crs.to_wkt() if bed.crs is not None else ""
    polygon = _domain_polygon(cfg.grid.domain, crs)
    new_mask, strip = mask_for_strips(cfg, mask, window.x0, window.y0, polygon)
    geo = strip.geometry
    grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
    dx = cfg.grid.dx
    print("cells", geo.ncells, "faces", geo.nfaces, "nodes", geo.x.size, "masked squares", strip.masked[0].size, "notes", len(strip.notes))
    print("geometry.check:", geo.check() or "clean")
    # non-manifold edges: an edge in three rings or more
    edges: Counter = Counter()
    for c in range(geo.ncells):
        r = geo.ring(c)
        for k in range(r.size):
            a, b = int(r[k]), int(r[(k + 1) % r.size])
            edges[(min(a, b), max(a, b))] += 1
    many = [e for e, n in edges.items() if n > 2]
    print("edges in three rings or more:", len(many), [(geo.x[a], geo.y[a]) for a, b in many[:3]])
    # T-junctions: a node lying on another cell's edge without being its vertex
    area, cx, cy = geo.areas_centroids()
    polys = [shapely.Polygon(np.column_stack((geo.x[geo.ring(c)], geo.y[geo.ring(c)]))) for c in range(geo.ncells)]
    tree = shapely.STRtree(polys)
    pts = shapely.points(np.column_stack((geo.x, geo.y)))
    on_edge = 0
    examples = []
    hits = tree.query(pts, predicate="dwithin", distance=1e-6)
    node_cells: dict[int, set[int]] = {}
    for c in range(geo.ncells):
        for v in geo.ring(c).tolist():
            node_cells.setdefault(int(v), set()).add(c)
    for v, c in zip(hits[0].tolist(), hits[1].tolist(), strict=True):
        if c not in node_cells.get(v, set()) and polys[c].exterior.distance(pts[v]) < 1e-6 and not polys[c].touches(pts[v]) is False:
            on_edge += 1
            if len(examples) < 3:
                examples.append((round(float(geo.x[v]), 2), round(float(geo.y[v]), 2)))
    print("nodes on another cell's edge, not its vertex (T-junctions):", on_edge, examples)
    # overlaps
    a_idx, b_idx = tree.query(polys, predicate="overlaps")
    over = [(a, b) for a, b in zip(a_idx.tolist(), b_idx.tolist(), strict=True) if a < b and polys[a].intersection(polys[b]).area > 1e-6]
    print("overlapping cell pairs:", len(over), [(round(cx[a]), round(cy[a])) for a, b in over[:3]])
    # boundary faces: against active tile cells (interfaces), against inactive ground (walls), or inside the strip (cracks)
    _length, nfx, nfy, xf, yf = geo.faces(cx, cy)
    boundary = np.nonzero(geo.face_cell[:, 1] < 0)[0]
    px, py = xf[boundary] + 0.5 * dx * nfx[boundary], yf[boundary] + 0.5 * dx * nfy[boundary]
    j = np.floor((grid.y0 - py) / dx).astype(np.int64)
    i = np.floor((px - grid.x0) / dx).astype(np.int64)
    ny, nx = grid.shape
    inside = (j >= 0) & (j < ny) & (i >= 0) & (i < nx)
    active_beyond = np.zeros(boundary.size, bool)
    active_beyond[inside] = new_mask[j[inside] - 1, i[inside] - 1] if new_mask.shape == (ny - 1, nx - 1) else grid.mask[j[inside], i[inside]]
    masked_set = set(zip(strip.masked[0].tolist(), strip.masked[1].tolist(), strict=True))
    in_hole = np.array([(int(jj), int(ii)) in masked_set for jj, ii in zip(j.tolist(), i.tolist(), strict=True)])
    print(f"boundary faces {boundary.size}: onto active squares {int(active_beyond.sum())}, onto inactive ground {int((~active_beyond & ~in_hole).sum())}, into the strip's own hole (cracks) {int(in_hole.sum())}")
    cracks = boundary[in_hole]
    if cracks.size:
        print("  cracks near:", [(round(float(xf[f])), round(float(yf[f]))) for f in cracks[:5]])
    # the hole against the cells
    print(f"cells' area {area.sum():.1f} against masked squares {strip.masked[0].size * dx * dx:.1f}; smallest cell {area.min():.1f} m2; faces per cell max {int(np.diff(geo.ring_start).max())}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
