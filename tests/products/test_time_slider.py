"""The frames file: the real cells, the saved frames on them, and the text attributes QGIS's reader needs."""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest
from rasterio.crs import CRS

from tests.engine.conftest import job, tilted_box, write_dem
from wadi2d.config.schema import Pixels
from wadi2d.engine.cli import main
from wadi2d.grid.quad import QuadGrid
from wadi2d.grid.tiles import TileGrid
from wadi2d.products.cell_grid import write_cell_grid
from wadi2d.products.time_slider import (
    FILL,
    FRAMES_FILE,
    cell_frame,
    frame_seconds,
    read_tiles,
    tile_mesh,
    uniform_mesh,
    write_frames,
)
from wadi2d.run import run_job
from wadi2d.solver.layout import TILE

DX = 5.0


def areas(mesh) -> np.ndarray:
    """Shoelace on each face: positive means counter-clockwise on the map."""
    x, y = mesh.x[mesh.faces], mesh.y[mesh.faces]
    return 0.5 * (x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y).sum(axis=1)


def test_four_cells_share_nine_corners() -> None:
    mesh = uniform_mesh(np.ones((2, 2), bool), 100.0, 200.0, DX)
    assert mesh.count == 4
    assert mesh.x.size == 9
    assert sorted(set(mesh.x)) == [100.0, 105.0, 110.0]
    assert sorted(set(mesh.y)) == [190.0, 195.0, 200.0]
    assert (areas(mesh) == DX**2).all()


def test_a_cell_left_out_of_the_domain_is_left_out_of_the_mesh() -> None:
    mask = np.ones((3, 3), bool)
    mask[1, 1] = False
    mesh = uniform_mesh(mask, 0.0, 0.0, DX)
    assert mesh.count == 8
    assert not ((mesh.rows == 1) & (mesh.columns == 1)).any()


def test_a_mesh_keeps_each_tile_at_its_size_and_covers_the_ground_once() -> None:
    mask = np.ones((TILE * 4, TILE * 4), bool)
    grid = QuadGrid.from_levels(mask, 0.0, TILE * 4 * DX, DX, np.array([[0, 1], [1, 2]], np.int32))
    tiles = [(int(grid.tiles[t, 0]), int(grid.tiles[t, 1]), int(grid.level[t])) for t in range(1, grid.ntiles)]
    mesh = tile_mesh(grid.mask, tiles, grid.x0, grid.y0, DX)
    assert mesh.count == grid.cell_count
    assert sorted(set(areas(mesh))) == sorted({float(v) ** 2 for v in grid.tile_dx[1:]})
    assert areas(mesh).sum() == grid.mask.sum() * DX**2


def test_a_coarse_cell_reads_the_frame_inside_itself() -> None:
    mask = np.ones((TILE * 2, TILE * 2), bool)
    mesh = tile_mesh(mask, [(0, 0, 1)], 0.0, 0.0, DX)
    assert mesh.count == TILE * TILE
    assert (mesh.rows % 2 == 1).all() and (mesh.columns % 2 == 1).all()


def test_the_tiles_come_back_from_the_cell_grid(tmp_path: Path) -> None:
    mask = np.ones((TILE * 4, TILE * 4), bool)
    grid = QuadGrid.from_levels(mask, 0.0, 0.0, DX, np.array([[0, 1], [1, 2]], np.int32))
    write_cell_grid(grid, CRS.from_epsg(32640).to_wkt(), tmp_path)
    wanted = {(int(grid.tiles[t, 0]), int(grid.tiles[t, 1]), int(grid.level[t])) for t in range(1, grid.ntiles)}
    assert set(read_tiles(tmp_path)) == wanted


def test_a_dry_cell_is_left_out_of_all_three_fields() -> None:
    mesh = uniform_mesh(np.ones((1, 2), bool), 0.0, 0.0, DX)
    rule = Pixels()
    depth = np.array([[0.0, 2.0]])
    speed = np.array([[1.0, 3.0]])
    frame = cell_frame(depth, speed, mesh, rule)
    assert [frame[name][0] for name in ("depth", "speed", "hazard")] == [FILL, FILL, FILL]
    assert frame["depth"][1] == 2.0 and frame["speed"][1] == 3.0 and frame["hazard"][1] >= 1.0


def test_frame_names_are_seconds() -> None:
    assert frame_seconds(["t000000900", "t000001800"]).tolist() == [900.0, 1800.0]


@pytest.fixture
def finished(tmp_path: Path) -> Path:
    dem = write_dem(tmp_path / "dem.tif", tilted_box(40, 40, 5.0, 0.01), 5.0)
    cfg = job(
        dem, 40, 40, 5.0,
        run={"duration_s": 120.0},
        storm={"kind": "uniform", "depth_mm": 300.0, "duration_min": 2.0},
        outputs={"map_every_s": 60.0, "pixels": {"enabled": False}},
    )  # fmt: skip
    assert run_job(cfg, tmp_path / "run").exit_code == 0
    return tmp_path / "run"


def test_the_file_holds_the_saved_frames_on_the_cells(finished: Path) -> None:
    path = write_frames(finished)
    with h5py.File(finished / "results.h5", "r") as r, h5py.File(path, "r") as f:
        names = sorted(r["maps"])
        mask = r["mask"][:]
        assert f["time"][:].tolist() == [float(int(n[1:])) for n in names]
        assert f["depth"].shape == (len(names), int(mask.sum()))
        last = r["maps"][names[-1]]["depth"][:][mask]
        written = f["depth"][-1, :]
        floor = Pixels().depth_floor
        wet = last >= floor
        assert wet.any()
        assert np.allclose(np.sort(written[written != FILL]), np.sort(last[wet]))


def test_text_attributes_are_fixed_length(finished: Path) -> None:
    """QGIS's reader skips the mesh on variable-length text, and opens the file as a raster with no time."""
    path = write_frames(finished)
    with h5py.File(path, "r") as f:
        for owner, key in ((f["Mesh2"], "cf_role"), (f["time"], "units"), (f["depth"], "mesh")):
            assert owner.attrs.get_id(key).dtype.kind == "S"
        assert f["time"].attrs["units"] == b"seconds since 2000-01-01 00:00:00"


def test_a_file_newer_than_the_results_is_used_as_it_stands(finished: Path) -> None:
    path = write_frames(finished)
    stamp = path.stat().st_mtime_ns
    assert write_frames(finished).stat().st_mtime_ns == stamp


def test_the_command_says_where_it_wrote(finished: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["frames", str(finished)]) == 0
    assert json.loads(capsys.readouterr().out)["path"].endswith(FRAMES_FILE)


def test_a_run_that_saved_no_maps_is_told_so(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    dem = write_dem(tmp_path / "dem.tif", tilted_box(40, 40, 5.0, 0.01), 5.0)
    assert run_job(job(dem, 40, 40, 5.0, run={"duration_s": 30.0}), tmp_path / "run").exit_code == 0
    assert main(["frames", str(tmp_path / "run")]) == 3
    assert "a time slider needs two" in capsys.readouterr().err


def test_the_uniform_grid_needs_no_cell_grid_file(finished: Path) -> None:
    (finished / "cell_grid.gpkg").unlink()
    assert write_frames(finished).is_file()


def test_uniform_cells_are_the_tile_grids_cells() -> None:
    grid = TileGrid.from_mask(np.ones((40, 40), bool), 0.0, 0.0, DX)
    assert uniform_mesh(grid.mask, grid.x0, grid.y0, DX).count == int(grid.mask.sum())
