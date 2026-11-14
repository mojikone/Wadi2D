"""The centre mesh at 5 m (W48's finding: +59 % water on the tight gorge, Faydh refused by the tiling guard): what is
wrong with its cells, mesh only, no tables or solver.

    .venv\Scripts\python "W52 gorge rows in the aligned mesh\mesh5_check.py" [case] [ce5|ce10|ce20]
"""

from __future__ import annotations

import sys

import numpy as np
import shapely

import gorges as g
from wadi2d.config import RunConfig
from wadi2d.run import RasterBed, _domain_polygon, _wkt, domain_mask, grid_window, with_tables
from wadi2d.strips.build import mask_for_strips


def check(case: str, mesh: str) -> None:
    _n, data = g.job(case, mesh)
    cfg = with_tables(RunConfig.model_validate(data))
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        crs = _wkt(bed)
    polygon = _domain_polygon(cfg.grid.domain, crs)
    new_mask, strip = mask_for_strips(cfg, mask, window.x0, window.y0, polygon)
    geo = strip.geometry
    area, cx, cy = geo.areas_centroids()
    polys = [shapely.Polygon(np.column_stack((geo.x[geo.ring(c)], geo.y[geo.ring(c)]))) for c in range(geo.ncells)]
    union = shapely.union_all(polys)
    jj, ii = strip.masked
    dx = cfg.grid.dx
    squares = shapely.union_all([shapely.box(window.x0 + (i - 1) * dx, window.y0 - j * dx, window.x0 + i * dx, window.y0 - (j - 1) * dx) for j, i in zip(jj, ii)])
    print(f"{case} {mesh}: {geo.ncells} cells, sum of areas {area.sum():.1f} m2, union {union.area:.1f} m2 (overlap {area.sum() - union.area:.1f}),"
          f" squares masked {len(jj) * dx * dx:.1f} m2, union minus squares {union.difference(squares).area:.1f}, squares minus union {squares.difference(union).area:.1f}")
    invalid = [c for c, p in enumerate(polys) if not p.is_valid]
    print(f"  invalid (self-crossing) rings: {len(invalid)}; negative areas {(area <= 0).sum()}; ring sizes {np.diff(geo.ring_start).min()} to {np.diff(geo.ring_start).max()}")
    print("  notes:", strip.notes[:6])
    if invalid:
        for c in invalid[:5]:
            print("   ", c, "corridor", strip.corridor[c], "row", strip.row[c], "area", round(float(area[c]), 2), "centroid", round(float(cx[c]) - g.wp.X0, 1), round(float(cy[c]) - g.wp.Y0, 1), shapely.is_valid_reason(polys[c]))
    big = np.argsort(area)[-3:]
    print("  largest cells:", [(int(c), round(float(area[c]), 1), int(strip.corridor[c]), int(strip.row[c])) for c in big], "dx^2", dx * dx)


if __name__ == "__main__":
    case = next((a for a in sys.argv[1:] if a.startswith("narrow")), "narrow_sine")
    mesh = next((a for a in sys.argv[1:] if a.startswith("ce")), "ce5")
    check(case, mesh)
