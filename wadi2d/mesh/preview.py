"""Build mesh before any run (W101 item 4): the cells a run of the job would step, drawn and counted.

The squares, the quadtree and the aligned centre mesh alike: ``cell_grid.gpkg`` holds the square cells as one line
feature per tile (W17's layer), ``strip_mesh.gpkg`` the aligned cells as polygons, and ``mesh.json`` the numbers the
dock shows. The cells are made the way ``prepare_grid`` makes them for a run, on the same domain mask, the same
catchments left out and the same strip builder, so what is drawn is what a run steps; no table is built, so it
takes the mesher's time and not the tables'. A refusal of the mesher is the run's own, raised as it would be.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import shapely

from wadi2d.config.schema import RunConfig
from wadi2d.io.geopackage import POLYGONS, VectorLayer, write_geopackage
from wadi2d.products.cell_grid import CELL_GRID_FILE, write_cell_grid
from wadi2d.products.smooth import crs_text
from wadi2d.strips.products import CELLS_LAYER, STRIP_MESH_FILE

SQUARES, QUADTREE, ALIGNED = "squares", "quadtree", "aligned"
SUMMARY_FILE = "mesh.json"


def strip_cells_layer(strip) -> VectorLayer:
    """The aligned cells of a strip mesh as polygons, with what each is; the run's own layer adds its depths."""
    geo = strip.geometry
    area, _cx, _cy = geo.areas_centroids()
    cells = VectorLayer(
        CELLS_LAYER, {"cell": int, "corridor": int, "row": int, "kind": str, "area_m2": float}, kind=POLYGONS
    )
    for c in range(geo.ncells):
        nodes = geo.ring(c)
        cells.geometries.append(shapely.Polygon(np.column_stack((geo.x[nodes], geo.y[nodes]))))
        kind = "corridor" if strip.corridor[c] >= 0 else "triangle"
        cells.rows.append((c, int(strip.corridor[c]), int(strip.row[c]), kind, abs(float(area[c]))))
    return cells


def build_preview(cfg: RunConfig, out: str | Path) -> dict:
    """The cells of the job, written in ``out``, and the summary the dock shows; raises the mesher's refusals."""
    from wadi2d.demstore.bed import cache_folder, open_bed
    from wadi2d.grid.tiles import TileGrid
    from wadi2d.run import (
        InvalidJob,
        _domain_polygon,
        _wkt,
        grid_window,
        kept_domain_mask,
        left_out_of,
        with_tables,
    )

    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    cfg = with_tables(cfg)
    cache = cache_folder(cfg, folder)
    dx = cfg.grid.dx
    with open_bed(cfg, cache) as bed:
        crs = _wkt(bed)
        window = grid_window(cfg, bed)
        mask = kept_domain_mask(cfg, bed, window, cache)
        if not mask.any():
            raise InvalidJob("the domain holds no active cell")
        domain = mask
        left = left_out_of(cfg, crs)
        gone = None
        if left is not None and left.names:  # the preview shows the mesh the run steps (W88)
            gone = left.cells(window.x0, window.y0, dx, mask.shape) & mask
            mask = mask & ~gone
        if not mask.any():
            raise InvalidJob(
                "every cell of the domain lies under a catchment left out of the mesh: the job is a lumped run"
            )
        uniform = int(mask.sum())
        summary: dict = {"left_out": list(left.names) if gone is not None else [], "notes": []}
        written: dict = {}
        if cfg.mesh.enabled:
            if cfg.strips.enabled:
                raise InvalidJob(
                    "corridors run on the uniform grid in this version: untick the mesh refinement or the corridors"
                )
            from wadi2d.mesh.build import build_grid, line_sizes, report, write_preview
            from wadi2d.terrain.ground import Ground

            bed.bind(window.x0, window.y0)
            grid = build_grid(cfg, mask, window.x0, window.y0, crs, Ground(bed, window.x0, window.y0))
            quad = report(grid, uniform, dx, line_sizes(cfg))
            written.update(write_preview(grid, crs, folder, quad))
            summary.update(json.loads(Path(written["summary"]).read_text(encoding="utf-8")))
            summary.update(kind=QUADTREE, smallest_m=float(grid.tile_dx[1:].min()), squares=grid.cell_count)
        elif cfg.strips.enabled:
            from wadi2d.strips.build import mask_for_strips

            polygon = _domain_polygon(cfg.grid.domain, crs)
            if polygon is None:
                polygon = shapely.box(
                    window.x0, window.y0 - mask.shape[0] * dx, window.x0 + mask.shape[1] * dx, window.y0
                )
            if gone is not None:  # as a run builds it: a cell clear of the left-out catchments
                polygon = polygon.difference(left.area.buffer(dx))
            try:
                mask, strip = mask_for_strips(cfg, mask, window.x0, window.y0, polygon, domain, str(cache))
            except (ValueError, OSError) as error:
                raise InvalidJob(str(error)) from error
            grid = TileGrid.from_mask(mask, window.x0, window.y0, dx)
            area = np.abs(strip.geometry.areas_centroids()[0])
            squares = int(mask.sum())
            aligned = int(strip.geometry.ncells)
            path = write_geopackage(folder / STRIP_MESH_FILE, [strip_cells_layer(strip)], crs_text(crs))
            written["strip_cells"] = str(path)
            summary.update(
                kind=ALIGNED, cells=squares + aligned, squares=squares, aligned=aligned,
                replaced=int(strip.masked[0].size), cells_uniform=uniform,
                ratio=round(uniform / max(squares + aligned, 1), 3),
                smallest_m2=float(area.min()) if area.size else dx * dx,
                smallest_m=float(np.sqrt(area.min())) if area.size else dx,
                tiles_by_size={f"{dx:g} m": int(grid.ntiles - 1)}, notes=list(strip.notes),
            )  # fmt: skip
        else:
            grid = TileGrid.from_mask(mask, window.x0, window.y0, dx)
            summary.update(
                kind=SQUARES, cells=uniform, squares=uniform, cells_uniform=uniform, ratio=1.0, smallest_m=dx,
                tiles_by_size={f"{dx:g} m": int(grid.ntiles - 1)},
            )  # fmt: skip
    written["grid"] = str(write_cell_grid(grid, crs, folder))
    js = folder / SUMMARY_FILE
    js.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    written["summary"] = str(js)
    return {**written, "kind": summary["kind"], "cells": summary["cells"], "ratio": summary["ratio"]}


__all__ = [
    "ALIGNED",
    "CELL_GRID_FILE",
    "QUADTREE",
    "SQUARES",
    "SUMMARY_FILE",
    "build_preview",
    "strip_cells_layer",
]
