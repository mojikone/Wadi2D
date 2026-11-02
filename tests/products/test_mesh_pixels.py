"""Pixel maps on a mesh: each coarse cell holds its own water, and a sloped surface does not jump at a level interface."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.config.schema import Numerics, Pixels, RunConfig, Tables
from wadi2d.engine.cli import main
from wadi2d.grid.quad import QuadGrid
from wadi2d.products.ground import CellPixels
from wadi2d.products.mesh import MeshMaxima, mesh_sills, own_cells, spread
from wadi2d.products.pixels import array_module
from wadi2d.products.step import (
    DEPTH_FILE,
    HAZARD_FILE,
    PIXEL_DIR,
    SPEED_FILE,
    STATS_FILE,
    Watch,
    make_products,
)
from wadi2d.run import prepare_grid, run_job
from wadi2d.solver.layout import STRIDE, TILE
from wadi2d.solver.model import Model
from wadi2d.tables import ArrayBed
from wadi2d.tables.quad import build_quad_tables

pytest.importorskip("whitebox")

DX, K = 4.0, 2
"""Finest cell, and pixels along it."""
SLOPE = 0.02
DEPTH = 0.6


def _grid(level) -> QuadGrid:
    level = np.array(level, np.int32)
    ny, nx = level.shape[0] * TILE, level.shape[1] * TILE
    mask = np.zeros((ny, nx), bool)
    mask[2:-2, 2:-2] = True
    return QuadGrid.from_levels(mask, 0.0, ny * DX, DX, level)


def _plane(grid: QuadGrid, slope_x: float, slope_y: float = 0.0) -> np.ndarray:
    """The bed at the pixels, 4 extra cells all round."""
    ny, nx = grid.shape
    pad = 4 * K
    p = DX / K
    x = (np.arange(nx * K + 2 * pad) - pad + 0.5) * p
    y = (np.arange(ny * K + 2 * pad) - pad + 0.5) * p
    return 100.0 - slope_x * x[None, :] - slope_y * y[:, None]


def _parts(grid: QuadGrid, bed: np.ndarray, keep: np.ndarray, datum: float) -> dict[int, CellPixels]:
    size = grid.from_tiles(
        np.broadcast_to(grid.level[:, None, None], (grid.ntiles, TILE, TILE)).astype(np.int32), -1
    )
    parts = {}
    pad = 4 * K
    for s in range(int(grid.level.max()) + 1):
        own = own_cells(size, keep, s)
        if not own.any():
            continue
        rows, cols = np.nonzero(own)
        k = K << s
        down = rows[:, None, None] * k + np.arange(k)[None, :, None]
        across = cols[:, None, None] * k + np.arange(k)[None, None, :]
        ground = bed[down + pad, across + pad].reshape(rows.size, -1) - datum
        parts[s] = CellPixels(rows, cols, k, DX / K, datum, ground.astype(np.float32))
    return parts


def _surface_case(grid: QuadGrid, slope_x: float, slope_y: float = 0.0):
    """Water ``DEPTH`` deep over a plane, on the tables of a real mesh. Depth at every pixel should read ``DEPTH``."""
    bed = _plane(grid, slope_x, slope_y)
    tables = build_quad_tables(grid, ArrayBed(bed, DX / K, 4 * K, 4 * K), Tables(), 0.03)
    keep = grid.mask.copy()
    datum = float(tables.zmin[keep].min())
    zmin = (tables.zmin - datum).astype(np.float32)
    parts = _parts(grid, bed, keep, datum)
    maxima = MeshMaxima(np, grid, parts, keep, zmin, mesh_sills(tables, datum), Pixels())
    rel = grid.from_tiles(_cell_mean(grid, bed)) - tables.zmin  # mean bed over the lowest point
    depth = np.where(keep, rel + DEPTH, 0.0).astype(np.float32)
    mean = np.where(keep, DEPTH, 0.0).astype(np.float32)
    maxima.add(depth, mean, np.zeros(grid.shape, np.float32))
    held = maxima.result()
    return parts, {s: held[s][0] for s in held}, maxima


def _cell_mean(grid: QuadGrid, bed: np.ndarray) -> np.ndarray:
    out = np.zeros((grid.ntiles, TILE, TILE))
    pad = 4 * K
    for t in range(1, grid.ntiles):
        k = K << int(grid.level[t])
        r0, c0 = int(grid.tiles[t, 0]) * TILE * K + pad, int(grid.tiles[t, 1]) * TILE * K + pad
        block = bed[r0 : r0 + TILE * k, c0 : c0 + TILE * k]
        out[t] = block.reshape(TILE, k, TILE, k).mean(axis=(1, 3))
    return out


@pytest.mark.parametrize(
    "level, slopes",
    [
        ([[0, 0, 1, 1], [0, 0, 1, 1]], (SLOPE, 0.0)),
        ([[1, 1, 0, 0], [1, 1, 0, 0]], (SLOPE, 0.0)),
        ([[1, 1], [1, 1], [0, 0], [0, 0]], (0.0, SLOPE)),
        ([[0, 0, 1, 1], [0, 0, 1, 1]], (SLOPE, SLOPE)),
    ],
    ids=["fine west", "coarse west", "coarse north", "diagonal fall"],
)
def test_a_sloped_surface_reads_one_depth_across_an_interface(level, slopes):
    """The whole point: a plane of water over a plane of ground, with a level interface through it."""
    grid = _grid(level)
    parts, depth, _maxima = _surface_case(grid, *slopes)
    assert len(parts) == 2
    raster = spread(parts, depth, np.nan, np.float32)
    inner = raster[6 * K : -6 * K, 6 * K : -6 * K]
    assert np.nanmax(np.abs(inner - DEPTH)) < 0.012


def test_without_the_coarse_surface_a_step_would_show():
    """The check above must be able to fail: read the ghosts flat, and the interface steps by a quarter cell of slope."""
    grid = _grid([[0, 0, 1, 1], [0, 0, 1, 1]])
    bed = _plane(grid, 0.2)
    tables = build_quad_tables(grid, ArrayBed(bed, DX / K, 4 * K, 4 * K), Tables(), 0.03)
    keep = grid.mask.copy()
    datum = float(tables.zmin[keep].min())
    zmin = (tables.zmin - datum).astype(np.float32)
    parts = _parts(grid, bed, keep, datum)
    flat = MeshMaxima(np, grid, parts, keep, zmin, mesh_sills(tables, datum), Pixels())
    flat._ghosts = lambda *_a: None
    good = MeshMaxima(np, grid, parts, keep, zmin, mesh_sills(tables, datum), Pixels())
    rel = grid.from_tiles(_cell_mean(grid, bed)) - tables.zmin
    depth = np.where(keep, rel + DEPTH, 0.0).astype(np.float32)
    mean = np.where(keep, DEPTH, 0.0).astype(np.float32)
    errors = []
    for maxima in (flat, good):
        maxima.add(depth, mean, np.zeros(grid.shape, np.float32))
        held = maxima.result()
        raster = spread(parts, {s: held[s][0] for s in held}, np.nan, np.float32)
        errors.append(float(np.nanmax(np.abs(raster[6 * K : -6 * K, 6 * K : -6 * K] - DEPTH))))
    assert errors[0] > 2.0 * errors[1]


def test_each_coarse_cell_holds_its_own_water():
    """A channel in part of a coarse cell: spread over the raster, its water would stand on the bank too."""
    grid = _grid([[0, 0, 1, 1], [0, 0, 1, 1]])
    bed = _plane(grid, 0.0)
    pad = 4 * K
    rows = bed.shape[0]
    channel = pad + rows // 2 - 3 * K
    bed[channel : channel + 3 * K, :] -= 1.5  # a channel, narrower than the cells either side of it
    tables = build_quad_tables(grid, ArrayBed(bed, DX / K, 4 * K, 4 * K), Tables(), 0.03)
    keep = grid.mask.copy()
    datum = float(tables.zmin[keep].min())
    zmin = (tables.zmin - datum).astype(np.float32)
    parts = _parts(grid, bed, keep, datum)
    maxima = MeshMaxima(np, grid, parts, keep, zmin, mesh_sills(tables, datum), Pixels())
    water = np.full(grid.shape, 99.0)  # below the plain: only the channel is wet
    depth = np.where(keep, np.maximum(water - tables.zmin, 0.0), 0.0).astype(np.float32)
    maxima.add(
        depth, _held_water(grid, bed, water, keep).astype(np.float32), np.zeros(grid.shape, np.float32)
    )
    result = maxima.result()
    raster = spread(parts, {s: result[s][0] for s in result}, 0.0, np.float32)
    top, left = parts_top(parts), parts_left(parts)
    ground = bed[pad + top : pad + top + raster.shape[0], pad + left : pad + left + raster.shape[1]]
    bank = ground > 99.5
    assert raster[bank].max() == 0.0
    assert raster[~bank].max() == pytest.approx(0.5, abs=0.02)


def parts_top(parts) -> int:
    return min(int(p.rows.min()) * p.k for p in parts.values())


def parts_left(parts) -> int:
    return min(int(p.cols.min()) * p.k for p in parts.values())


def _held_water(grid, bed, water, keep) -> np.ndarray:
    """Mean depth of each cell, painted, for a level over the true pixels."""
    pad = 4 * K
    out = np.zeros((grid.ntiles, TILE, TILE))
    level = grid.to_tiles(water, np.float64)
    for t in range(1, grid.ntiles):
        k = K << int(grid.level[t])
        r0, c0 = int(grid.tiles[t, 0]) * TILE * K + pad, int(grid.tiles[t, 1]) * TILE * K + pad
        block = bed[r0 : r0 + TILE * k, c0 : c0 + TILE * k].reshape(TILE, k, TILE, k)
        out[t] = np.maximum(level[t][:, None, :, None] - block, 0.0).mean(axis=(1, 3))
    return np.where(keep, grid.from_tiles(out), 0.0)


def _sheet(dem, mesh: dict | None = None):
    """A sheet down a 1 % plane, held by a stage along its whole head: planar flow, with no jet to confuse the reading."""
    stage = 100.0 - 0.01 * 16.0 + 0.5
    parts = {
        "boundaries": [
            {"kind": "stage", "coordinates": [(X0 + 16.0, Y0), (X0 + 16.0, Y0 - 256.0)], "stage": stage},
            {"kind": "free", "coordinates": [(X0 + 1016.0, Y0), (X0 + 1016.0, Y0 - 256.0)]},
        ],
        "terrain": {"manning": 0.03},
        "run": {"duration_s": 900.0, "backend": "cpu", "source_every_s": 30.0},
        "outputs": {"map_every_s": 150.0, "live_every_s": 0.0},
    }
    if mesh:
        parts["mesh"] = mesh
        parts["numerics"] = {"local_time_stepping": True}
    return job(dem, 256, 64, 4.0, **parts)


def _across(folder, xs: np.ndarray) -> np.ndarray:
    """Pixel depth along the flow, the mean of the rows around the middle of the sheet."""
    with rasterio.open(folder / PIXEL_DIR / DEPTH_FILE) as src:
        depth = src.read(1, masked=True).filled(0.0)
        x0 = src.transform.c
    row = depth.shape[0] // 2
    return depth[row - 8 : row + 8][:, np.round((xs - x0) / 2.0).astype(int)].mean(axis=0)


@pytest.fixture(scope="module")
def sheet(tmp_path_factory):
    """The sheet on a mesh and on the uniform grid of the same ground."""
    tmp = tmp_path_factory.mktemp("sheet")
    px = (np.arange(512) + 0.5) * 2.0
    dem = write_dem(tmp / "plane.tif", np.tile(100.0 - 0.01 * px, (128, 1)), 2.0)
    head = [(X0, Y0), (X0 + 200.0, Y0), (X0 + 200.0, Y0 - 256.0), (X0, Y0 - 256.0)]
    mesh = {
        "enabled": True, "coarse_dx": 8.0, "min_dx": 1.0, "analysis_pixel": 2.0, "stream_area_fine_km2": 100.0,
        "stream_area_mid_km2": 100.0, "zones": [{"coordinates": head, "dx": 4.0}],
    }  # fmt: skip
    cfg = _sheet(dem, mesh)
    summary = run_job(cfg, tmp / "mesh")
    assert summary.exit_code == 0, summary.message
    assert summary.products == "finished"
    assert run_job(_sheet(dem), tmp / "uniform").products == "finished"
    return cfg, tmp


def test_planar_flow_crosses_both_interfaces_with_no_step_in_the_pixel_depth(sheet):
    """Through the engine, fine into coarse and coarse into fine, against the uniform run on the same ground."""
    cfg, tmp = sheet
    grid = prepare_grid(cfg, tmp / "c")[0].grid
    columns = grid.tiles[grid.level > 0, 1]
    assert grid.level.max() == 1
    for edge in (int(columns.min()), int(columns.max()) + 2):
        xs = grid.x0 + edge * TILE * DX + np.arange(-48.0, 48.0, 4.0)
        here, plain = _across(tmp / "mesh", xs), _across(tmp / "uniform", xs)
        assert here.min() > 0.3
        assert np.abs(np.diff(here)).max() < 0.01
        assert np.abs(here - plain).max() < 0.015


def test_a_mesh_run_writes_every_file_of_the_step(sheet):
    folder = sheet[1] / "mesh" / PIXEL_DIR
    stats = json.loads((folder / STATS_FILE).read_text(encoding="utf-8"))
    assert stats["cell_sizes_m"] == [4.0, 8.0]
    assert sum(stats["class_km2"].values()) > 0.0
    assert (folder / "map_layers.gpkg").is_file()
    with rasterio.open(folder / HAZARD_FILE) as src:
        assert src.read(1).max() >= 1


def _remade(cfg, tables, crs, run, folder, backend):
    folder.mkdir()
    (folder / "results.h5").write_bytes((run / "results.h5").read_bytes())
    make_products(cfg, tables, crs, folder, Watch(lambda *_a, **_k: None, lambda: False), backend)


def test_cpu_and_gpu_give_the_same_answer_on_a_mesh(sheet, tmp_path):
    pytest.importorskip("cupy")
    if array_module("auto") is np:
        pytest.skip("no GPU")
    cfg, tmp = sheet
    tables, crs = prepare_grid(cfg, tmp / "c")
    _remade(cfg, tables, crs, tmp / "mesh", tmp_path / "gpu", "gpu")
    _remade(cfg, tables, crs, tmp / "mesh", tmp_path / "cpu", "cpu")
    for name, tolerance in ((HAZARD_FILE, 0), (DEPTH_FILE, 1e-3), (SPEED_FILE, 1e-3)):
        with (
            rasterio.open(tmp_path / "gpu" / PIXEL_DIR / name) as a,
            rasterio.open(tmp_path / "cpu" / PIXEL_DIR / name) as b,
        ):
            assert np.abs(a.read(1).astype(float) - b.read(1).astype(float)).max() <= tolerance


def _with_pixel(cfg, size: float) -> RunConfig:
    data = cfg.model_dump(mode="json")
    data["outputs"]["pixels"]["pixel_m"] = size
    return RunConfig.model_validate(data)


def test_a_coarser_pixel_is_a_setting_on_a_mesh_too(sheet, tmp_path):
    cfg, tmp = sheet
    tables, crs = prepare_grid(cfg, tmp / "c")
    _remade(_with_pixel(cfg, 4.0), tables, crs, tmp / "mesh", tmp_path / "px", "cpu")
    with rasterio.open(tmp_path / "px" / PIXEL_DIR / DEPTH_FILE) as src:
        assert abs(src.transform.a) == 4.0
        depth = src.read(1, masked=True).filled(0.0)
    assert depth.max() > 0.3


def test_a_pixel_that_does_not_fit_the_dem_is_refused_on_a_mesh(sheet, tmp_path):
    cfg, tmp = sheet
    tables, crs = prepare_grid(cfg, tmp / "c")
    with pytest.raises(ValueError, match="pixel"):
        _remade(_with_pixel(cfg, 3.0), tables, crs, tmp / "mesh", tmp_path / "px", "cpu")


def test_the_command_line_remakes_them_on_a_mesh_run(sheet):
    run = sheet[1] / "mesh"
    with rasterio.open(run / PIXEL_DIR / DEPTH_FILE) as src:
        before = src.read(1)
    assert main(["products", str(run), "--backend", "cpu"]) == 0
    with rasterio.open(run / PIXEL_DIR / DEPTH_FILE) as src:
        np.testing.assert_array_equal(src.read(1), before)


def test_the_speed_of_a_coarse_cell_comes_from_its_own_faces():
    grid = _grid([[0, 0, 1, 1], [0, 0, 1, 1]])
    tables = build_quad_tables(grid, ArrayBed(_plane(grid, 0.0), DX / K, 4 * K, 4 * K), Tables(), 0.03)
    model = Model(tables, Numerics(), "cpu")
    u = np.zeros((grid.ntiles, STRIDE, STRIDE), np.float32)
    u[1:] = 3.0
    model.backend.set_field("u", u.reshape(-1))
    speed = model.cell_speed()
    assert speed[grid.mask].min() == pytest.approx(3.0)
    assert speed[grid.mask].max() == pytest.approx(3.0)
