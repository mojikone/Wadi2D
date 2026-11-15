"""The cut-and-fill survey with each fill and burn line read in its own box and left out of the tiles it cannot
reach (W91): the old numbers to the digit, the station table included."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from wadi2d.config.schema import Terrain, TerrainObject
from wadi2d.grid import TileGrid
from wadi2d.tables import ArrayBed
from wadi2d.terrain import Ground, apply_objects
from wadi2d.terrain import report as report_module
from wadi2d.terrain.report import survey


def square(x: float, y: float, side: float) -> np.ndarray:
    return np.array([(x, y), (x + side, y), (x + side, y + side), (x, y + side)], np.float64)


def rough_bed(cells: int) -> tuple[TileGrid, ArrayBed]:
    grid = TileGrid.from_mask(np.ones((cells, cells), bool), 0.0, float(cells * 10), 10.0)
    rows, cols = grid.shape[0] * 10, grid.shape[1] * 10
    yy, xx = np.mgrid[0:rows, 0:cols]
    z = 100.0 + 0.01 * xx + 2.0 * np.sin(xx / 37.0) * np.cos(yy / 23.0)
    return grid, ArrayBed(z, 1.0)


def old_survey(cfg: Terrain, grid, bed, edits, folder: Path) -> list[dict]:
    """The survey as it was before W91: every object's edit on every tile any object reaches, read on the whole tile."""
    tallies = [report_module.Tally.of(o, cfg.volume_step) for o, _e in edits.steps]
    near = set().union(*report_module._near_tiles(grid, tallies, edits.shapes, bed.levels))
    k = round(grid.dx / bed.pixel)
    block = report_module.TILE * k
    every = list(range(len(tallies)))
    for t in sorted(near):
        tj, ti = grid.tiles[t]
        z = bed.read(int(tj) * block, int(ti) * block, block, block)
        report_module._tile(z, int(tj) * block, int(ti) * block, edits, tallies, grid, bed.pixel, every, [None] * len(tallies))
    folder.mkdir(parents=True, exist_ok=True)
    return report_module._write_tables(tallies, folder)


def stations(folder: Path) -> list[list[str]]:
    with (folder / report_module.STATIONS_CSV).open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_the_survey_in_each_objects_box_gives_the_old_numbers_to_the_digit(tmp_path):
    grid, bed = rough_bed(150)
    cfg = Terrain(volume_step=25.0)
    objects = [
        TerrainObject(kind="fill", name="pit fill 1", coordinates=square(310.0, 310.0, 10.0).tolist(), z_constant=104.0),
        TerrainObject(kind="fill", name="pit fill 2", coordinates=square(315.0, 330.0, 10.0).tolist(), z_constant=107.0),
        TerrainObject(kind="fill", name="pit fill 3", coordinates=square(60.0, 1450.0, 10.0).tolist(), z_constant=106.0),
        TerrainObject(kind="burn_line", name="cut", coordinates=[(20.0, 20.0), (1400.0, 1300.0)], depth=0.7),
        TerrainObject(kind="burn_line", name="invert", coordinates=[(100.0, 1450.0), (1200.0, 600.0)], z_constant=101.0, width=3.0),
        TerrainObject(kind="embankment", name="bank", coordinates=[(400.0, 200.0), (1000.0, 280.0)], z_constant=106.0,
                      section={"width": 4.0, "left_slope": 2.0, "right_slope": 2.0}),
    ]  # fmt: skip
    edits = apply_objects(grid, objects, bed.pixel, cfg, Ground(bed, grid.x0, grid.y0))
    new = survey(cfg, grid, bed, edits, tmp_path / "new", None, write_maps=False)
    want = old_survey(cfg, grid, bed, apply_objects(grid, objects, bed.pixel, cfg, Ground(bed, grid.x0, grid.y0)), tmp_path / "old")
    assert new.volumes == want
    tallies = [report_module.Tally.of(o, cfg.volume_step) for o, _e in edits.steps]
    reaches = report_module._near_tiles(grid, tallies, edits.shapes, bed.levels)
    assert len(reaches[2]) < len(set().union(*reaches))  # the far fill is left out of some tiles walked
    assert all(row["fill_m3"] > 0.0 or row["cut_m3"] > 0.0 for row in want), want
    assert stations(tmp_path / "new") == stations(tmp_path / "old")
