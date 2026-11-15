"""W86: the pixel maps made a block of the rasters at a time are the maps every saved map over every pixel gave.

The reference in each test is the product step as it was before W86: one ``PixelMaxima`` over all the kept cells, one
``StripMaxima`` over the whole strip, every map through both, then one spread of the lot.
"""

from __future__ import annotations

from contextlib import closing

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import tilted_box, write_dem
from tests.engine.test_strips_run import corridor, plane_job
from tests.products.test_step import wadi_job
from wadi2d.products import blocks, step
from wadi2d.products.blocks import plan_bands, plan_blocks
from wadi2d.products.cell_maps import strip_on_lattice
from wadi2d.products.frames import frame_names, read_frames, run_maxima
from wadi2d.products.ground import face_sills, read_cells
from wadi2d.products.hazard import DRY, classify
from wadi2d.products.pixels import PixelMaxima, array_module
from wadi2d.products.step import PIXEL_DIR, Watch, make_products
from wadi2d.run import prepare_grid, run_job

QUIET = Watch(lambda *_a, **_k: None, lambda: False)
FILES = (step.HAZARD_FILE, step.DEPTH_FILE, step.SPEED_FILE, step.DV_FILE)


def test_blocks_hold_every_window_once_and_fit_their_budgets() -> None:
    rng = np.random.default_rng(3)
    cost = rng.random((13, 17)) * 10.0
    cost[rng.random(cost.shape) < 0.5] = 0.0
    cost[4, 9] = 500.0  # one window over any budget: a block of its own
    other = cost[::-1, ::-1] * 0.5
    budget = 40.0
    seen = np.zeros(cost.shape, int)
    bands = plan_bands(cost.sum(axis=1), 150.0)
    assert bands[0][0] == 0 and bands[-1][1] == cost.shape[0]
    assert all(cost[a:b].sum() <= 150.0 or b - a == 1 for a, b in bands)
    for band in bands:
        for b in plan_blocks([cost, other], [budget, budget], band):
            assert band[0] <= b.row0 < b.row1 <= band[1]
            seen[b.row0 : b.row1, b.col0 : b.col1] += 1
            one_window = b.row1 - b.row0 == 1 and b.col1 - b.col0 == 1
            for held in (cost, other):
                assert held[b.row0 : b.row1, b.col0 : b.col1].sum() <= budget or one_window
    assert (seen == 1).all()


def _rasters(run) -> dict[str, np.ndarray]:
    out = {}
    for name in FILES:
        with rasterio.open(run / PIXEL_DIR / name) as src:
            out[name] = src.read(1)
            out[name + ":at"] = (src.transform.c, src.transform.f, src.transform.a)
    return out


def _whole_squares(cfg, tables, run):
    """The kept cells' classes and maxima as one ``PixelMaxima`` over all of them gives them."""
    rule = cfg.outputs.pixels
    results = run / "results.h5"
    peak = run_maxima(results)
    keep = peak["mean_depth"] > rule.cell_depth
    cells = read_cells(cfg, tables, keep)
    zmin = (tables.zmin - cells.datum).astype(np.float32)
    maxima = PixelMaxima(np, cells, zmin, *face_sills(tables, cells.datum), keep, rule)
    with closing(read_frames(results, frame_names(results))) as frames:
        for depth, mean_depth, speed in frames:
            maxima.add(depth, mean_depth, speed)
    maxima.add(peak["depth"], peak["mean_depth"], peak["speed"], moment=False)
    maxima.lift_dv(peak["hazard"])
    depth, speed, dv = maxima.result()
    return cells, classify(depth, speed, dv, rule), depth, speed, dv


def _whole_rasters(cfg, tables, run) -> dict[str, np.ndarray]:
    """The four rasters as the step before W86 wrote them: everything at once, then one spread."""
    from wadi2d.strips.pixels import strip_pixel_maxima

    cells, classes, depth, speed, dv = _whole_squares(cfg, tables, run)
    strip = None
    if getattr(tables, "strip", None) is not None:
        strip = strip_pixel_maxima(cfg, tables, tables.strip, run, QUIET, np, cells.datum)
    box = step.pixel_box(cells, strip)
    wet = classes > DRY
    on_strip = None if strip is None else strip.classes > DRY
    out = {step.HAZARD_FILE: step.spread(cells, classes, DRY, np.uint8, box, strip, None if strip is None else strip.classes)}
    for name, values, more in (
        (step.DEPTH_FILE, depth, None if strip is None else strip.depth),
        (step.SPEED_FILE, speed, None if strip is None else strip.speed),
        (step.DV_FILE, dv, None if strip is None else strip.dv),
    ):
        marked = np.where(wet, values, step.NO_DEPTH)
        dots = None if more is None else np.where(on_strip, more, step.NO_DEPTH)
        out[name] = step.spread(cells, marked, step.NO_DEPTH, np.float32, box, strip, dots)
    grid = tables.grid
    for name in FILES:
        out[name + ":at"] = (grid.x0 + box[1] * cells.pixel, grid.y0 - box[0] * cells.pixel, cells.pixel)
    return out


def _small_blocks(monkeypatch, window: int) -> list:
    """Windows of ``window`` pixels, a block's budget of about one of them, every row of windows a band of its own
    and the saved maps read again for each band: a run of the tests' size in many blocks, through every path."""
    monkeypatch.setattr(step, "WINDOW", window)
    monkeypatch.setattr(step, "BAND_GROUND_BYTES", 1)
    monkeypatch.setattr(step, "STACK_BYTES", 1)
    monkeypatch.setenv(blocks.MEMORY_ENV, str(4 * 16 * window * window / 2**20))
    written = []
    real = step._write_block
    monkeypatch.setattr(step, "_write_block", lambda lattice, block, *rest: written.append(block) or real(lattice, block, *rest))
    return written


@pytest.fixture(scope="module")
def wadi(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("blocks")
    cfg = wadi_job(tmp, map_every_s=120.0)
    tables, crs = prepare_grid(cfg, tmp / "cache")
    summary = run_job(cfg, tmp / "run", tables=(tables, crs))
    assert summary.exit_code == 0, summary.message
    return cfg, tables, crs, tmp / "run"


def test_one_block_is_the_whole_run_to_the_digit(wadi) -> None:
    cfg, tables, _crs, run = wadi
    made, whole = _rasters(run), _whole_rasters(cfg, tables, run)
    assert (made[step.HAZARD_FILE] > DRY).any()
    for name in made:
        np.testing.assert_array_equal(made[name], whole[name], err_msg=name)


def test_many_blocks_are_the_whole_run_to_the_digit(wadi, tmp_path, monkeypatch) -> None:
    """Squares: a block's cells are worked with a halo of cells round them, and read what the whole domain gives."""
    cfg, tables, crs, run = wadi
    (tmp_path / "results.h5").write_bytes((run / "results.h5").read_bytes())
    written = _small_blocks(monkeypatch, 8)
    make_products(cfg, tables, crs, tmp_path, QUIET, "cpu")
    assert len(set(written)) > 8 and len({block.row0 for block in written}) > 1
    made, whole = _rasters(tmp_path), _rasters(run)
    for name in made:
        np.testing.assert_array_equal(made[name], whole[name], err_msg=name)
    assert (tmp_path / PIXEL_DIR / step.STATS_FILE).read_text("utf-8") == (run / PIXEL_DIR / step.STATS_FILE).read_text("utf-8")


@pytest.fixture(scope="module")
def striped(tmp_path_factory, tilted_dem_module):
    tmp = tmp_path_factory.mktemp("striped")
    cfg = plane_job(tilted_dem_module, corridor())
    heavy = cfg.storm.model_copy(update={"depth_mm": 400.0})  # enough for the squares to be kept too
    pixels = cfg.outputs.pixels.model_copy(update={"enabled": True})
    outputs = cfg.outputs.model_copy(update={"map_every_s": 150.0, "pixels": pixels})
    cfg = cfg.model_copy(update={"storm": heavy, "outputs": outputs})
    tables, crs = prepare_grid(cfg, tmp / "cache")
    summary = run_job(cfg, tmp / "run", tables=(tables, crs))
    assert summary.exit_code == 0, summary.message
    return cfg, tables, crs, tmp / "run"


@pytest.fixture(scope="module")
def tilted_dem_module(tmp_path_factory):
    """The engine tests' tilted plane at 1 m pixels, with a little relief inside the cells."""
    rough = tilted_box(200, 96, 1.0, 0.01) + np.random.default_rng(2).random((96, 200)) * 0.05
    return write_dem(tmp_path_factory.mktemp("tilted") / "tilted.tif", rough, 1.0)


def test_a_strip_keeps_the_old_whole_strips_pixels_within_the_fills_tolerance(striped) -> None:
    """Against the step before W86 (the whole strip at once, its fill going on until every cell had settled): the
    squares to the digit, and a strip pixel within the fill's tolerance, 0.1 mm of depth, a cell now stopping on its
    own step."""
    from wadi2d.products.surface import FILL_TOLERANCE

    cfg, tables, _crs, run = striped
    made, whole = _rasters(run), _whole_rasters(cfg, tables, run)
    rows, cols, _cell = strip_on_lattice(tables)
    k = round(tables.grid.dx / made[step.DEPTH_FILE + ":at"][2])
    box_top = round((tables.grid.y0 - made[step.DEPTH_FILE + ":at"][1]) / made[step.DEPTH_FILE + ":at"][2])
    box_left = round((made[step.DEPTH_FILE + ":at"][0] - tables.grid.x0) / made[step.DEPTH_FILE + ":at"][2])
    on_strip = np.zeros(made[step.DEPTH_FILE].shape, bool)
    for r, c in zip(rows, cols, strict=True):
        on_strip[max(r * k - box_top, 0) : (r + 1) * k - box_top, max(c * k - box_left, 0) : (c + 1) * k - box_left] = True
    assert on_strip.any() and not on_strip.all()
    for name in FILES:
        assert made[name + ":at"] == whole[name + ":at"]
        np.testing.assert_array_equal(made[name][~on_strip], whole[name][~on_strip], err_msg=name)
    wet = (made[step.DEPTH_FILE] != step.NO_DEPTH) & (whole[step.DEPTH_FILE] != step.NO_DEPTH)
    assert (wet[on_strip]).mean() > 0.5
    assert np.abs(made[step.DEPTH_FILE][wet] - whole[step.DEPTH_FILE][wet]).max() < FILL_TOLERANCE
    assert (made[step.HAZARD_FILE] != whole[step.HAZARD_FILE]).mean() < 1e-3


def test_a_strip_in_many_blocks_is_the_strip_in_one_to_the_digit(striped, tmp_path, monkeypatch) -> None:
    """A block's strip cells are worked with the rings of cells their surface reads, and a cell's fill stops on its
    own step: however the strip is cut, its pixels are the same, as the squares' beside it are."""
    cfg, tables, crs, run = striped
    (tmp_path / "results.h5").write_bytes((run / "results.h5").read_bytes())
    written = _small_blocks(monkeypatch, 16)
    make_products(cfg, tables, crs, tmp_path, QUIET, "cpu")
    assert len(set(written)) > 8 and len({block.row0 for block in written}) > 1
    made, whole = _rasters(tmp_path), _rasters(run)
    for name in made:
        np.testing.assert_array_equal(made[name], whole[name], err_msg=name)


def test_a_try_that_does_not_fit_the_card_is_made_again_in_smaller_blocks(wadi, tmp_path, monkeypatch) -> None:
    pytest.importorskip("cupy")
    if array_module("auto") is np:
        pytest.skip("no GPU")
    cfg, tables, crs, run = wadi
    (tmp_path / "results.h5").write_bytes((run / "results.h5").read_bytes())

    class OutOfMemoryError(Exception):
        pass

    squeezes, events = [], []
    real = step.lattice_pixels

    def tight(*args):
        squeezes.append(args[-1])
        if len(squeezes) == 1:
            raise OutOfMemoryError
        return real(*args)

    monkeypatch.setattr(step, "lattice_pixels", tight)
    make_products(cfg, tables, crs, tmp_path, Watch(lambda ev, **_k: events.append(ev), lambda: False), "gpu")
    assert squeezes == [1.0, 0.5] and "warn" not in events
    np.testing.assert_array_equal(_rasters(tmp_path)[step.HAZARD_FILE], _rasters(run)[step.HAZARD_FILE])
