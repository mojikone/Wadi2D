"""``wadi2d terrain``: everything the objects do to the ground, with no table and no run.

This is what the plugin's Preview loads: the modified terrain, the change, cut and fill, the checks in plain words,
and the long profile and sections as data to draw.
"""

from __future__ import annotations

from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.grid.tiles import TileGrid
from wadi2d.run import InvalidJob, check_inputs, check_terrain, domain_mask, grid_window
from wadi2d.terrain import Ground, RasterBed, apply_objects
from wadi2d.terrain.report import preview_data, survey, write_preview
from wadi2d.terrain.sections import with_tables


def preview_terrain(cfg: RunConfig, out: str | Path) -> dict:
    """Write the terrain rasters, the tables and the preview data into ``out``; return what the plugin shows."""
    check_inputs(cfg)
    cfg = with_tables(cfg)
    folder = Path(out)
    notes = check_terrain(cfg)
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        if not mask.any():
            raise InvalidJob("the domain holds no active cell")
        grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
        bed.bind(grid.x0, grid.y0)
        ground = Ground(bed, grid.x0, grid.y0)
        edits = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain, ground)
        report = survey(cfg.terrain, grid, bed, edits, folder, bed.crs)
        data = preview_data(cfg.terrain.objects, ground, cfg.grid.dx, cfg.terrain, edits.shapes)
    return {
        "notes": notes,
        "volumes": report.volumes,
        "files": {**report.files, "preview": str(write_preview(data, folder))},
        "tiles": report.tiles,
    }
