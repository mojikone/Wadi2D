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
RECORD = {"surface": "cell_fill", "pixel_m": 0.0, "max_error_m": 0.0, "dv_raster": True}
"""The maps W86 and W93 compared to the digit: W9's rule, the DEM's pixel, every digit kept, depth x speed written.
W100 made other defaults; these tests keep guarding the blocks on the rule they were written for."""
CONTINUOUS = {**RECORD, "surface": "continuous"}
"""The continuous surface of W100 on the same terms, so blocks can be compared to the digit."""


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
    cfg = wadi_job(tmp, map_every_s=120.0, pixels=RECORD)
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
    pixels = cfg.outputs.pixels.model_copy(update={"enabled": True, **RECORD})
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


@pytest.mark.parametrize("case", ["wadi", "striped"])
def test_cells_a_map_cannot_raise_are_left_unfilled_with_the_same_rasters(case, request, tmp_path, monkeypatch) -> None:
    """W93: on the card a map's cell is filled only where the map may raise one of its pixels' maxima; the rasters
    are those of filling every wet cell of every map, to the digit, in one block and in many."""
    pytest.importorskip("cupy")
    if array_module("auto") is np:
        pytest.skip("no GPU")
    cfg, tables, crs, run = request.getfixturevalue(case)
    counts = []
    real_init = PixelMaxima.__init__

    def counted(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        counts.append(self)

    made = {}
    # each cut against the same cut filling every cell: on the card the squares' corner products are cuBLAS's,
    # whose kernel, and so its last digit, changes with the number of cells a block holds (found in W93)
    for skip, blocks_of in ((False, 0), (True, 0), (False, 8), (True, 8)):
        folder = tmp_path / f"{skip}_{blocks_of}"
        folder.mkdir()
        (folder / "results.h5").write_bytes((run / "results.h5").read_bytes())
        with monkeypatch.context() as patch:
            if blocks_of:
                _small_blocks(patch, blocks_of)
            patch.setattr(PixelMaxima, "__init__", counted)
            patch.setattr(PixelMaxima, "skip", skip, raising=False)
            counts.clear()
            make_products(cfg, tables, crs, folder, QUIET, "gpu")
        made[(skip, blocks_of)] = _rasters(folder)
        if skip and not blocks_of:
            offered = sum(m.offered for m in counts)
            assert 0 < sum(m.filled for m in counts) < offered, "some cells filled and some left alone"
    for blocks_of in (0, 8):
        for name in made[(True, blocks_of)]:
            got, want = made[(True, blocks_of)][name], made[(False, blocks_of)][name]
            np.testing.assert_array_equal(got, want, err_msg=f"{blocks_of} {name}")


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

    def tight(*args, **kwargs):
        squeezes.append(args[-1])
        if len(squeezes) == 1:
            raise OutOfMemoryError
        return real(*args, **kwargs)

    monkeypatch.setattr(step, "lattice_pixels", tight)
    make_products(cfg, tables, crs, tmp_path, Watch(lambda ev, **_k: events.append(ev), lambda: False), "gpu")
    assert squeezes == [1.0, 0.5] and "warn" not in events
    np.testing.assert_array_equal(_rasters(tmp_path)[step.HAZARD_FILE], _rasters(run)[step.HAZARD_FILE])


def _continuous(cfg):
    pixels = cfg.outputs.pixels.model_copy(update=CONTINUOUS)
    return cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"pixels": pixels})})


@pytest.mark.parametrize("case", ["wadi", "striped"])
def test_the_continuous_surface_in_many_blocks_is_the_one_in_one_to_the_digit(case, request, tmp_path, monkeypatch) -> None:
    """W100: a block's squares read their corners from a halo wide enough for one fill a cell and its neighbours',
    its strip cells read the rings their nodes do, and the join of the two the squares' surface beside it: however the
    run is cut, the rasters are the same."""
    cfg, tables, crs, run = request.getfixturevalue(case)
    cfg = _continuous(cfg)
    made = {}
    for blocks_of in (0, 8 if case == "wadi" else 16):
        folder = tmp_path / f"cut_{blocks_of}"
        folder.mkdir()
        (folder / "results.h5").write_bytes((run / "results.h5").read_bytes())
        with monkeypatch.context() as patch:
            written = _small_blocks(patch, blocks_of) if blocks_of else []
            make_products(cfg, tables, crs, folder, QUIET, "cpu")
        if blocks_of:
            assert len(set(written)) > 8
        made[blocks_of] = _rasters(folder)
    one, many = made.values()
    assert (one[step.HAZARD_FILE] > DRY).any()
    for name in one:
        np.testing.assert_array_equal(many[name], one[name], err_msg=name)


@pytest.mark.parametrize("case", ["wadi", "striped"])
def test_a_window_is_the_whole_run_s_rasters_there(case, request, tmp_path) -> None:
    """W100, ``wadi2d window``: the rasters of a drawn window are the whole run's rasters at those pixels, to the
    digit: the cells round it it reads, the whole run's datum."""
    cfg, tables, crs, run = request.getfixturevalue(case)
    cfg = _continuous(cfg)
    whole = tmp_path / "whole"
    whole.mkdir()
    (whole / "results.h5").write_bytes((run / "results.h5").read_bytes())
    make_products(cfg, tables, crs, whole, QUIET, "cpu")
    full = _rasters(whole)
    pixel = full[step.DEPTH_FILE + ":at"][2]
    west, north = full[step.DEPTH_FILE + ":at"][:2]
    height, width = full[step.DEPTH_FILE].shape
    box = (west + 0.3 * width * pixel, north - 0.8 * height * pixel, west + 0.7 * width * pixel, north - 0.2 * height * pixel)
    folder = tmp_path / "window"
    make_products(cfg, tables, crs, whole, QUIET, "cpu", None, box, folder)
    for name in FILES:
        with rasterio.open(folder / name) as src:
            part = src.read(1)
            t = src.transform
        row, col = round((north - t.f) / pixel), round((t.c - west) / pixel)
        assert part.shape[0] < height and part.shape[1] < width
        np.testing.assert_array_equal(part, full[name][row : row + part.shape[0], col : col + part.shape[1]], err_msg=name)


def test_the_strip_and_the_squares_meet_without_a_step(striped, tmp_path) -> None:
    """W100: the squares take the strip cells beside them as neighbours and the strip takes the squares' surface at
    the nodes it shares with them, so across the join the depth changes as it does inside the cells; before, a square
    beside the strip saw nothing there and the surface stepped along the whole join."""
    cfg, tables, crs, run = striped
    cfg = _continuous(cfg)
    (tmp_path / "results.h5").write_bytes((run / "results.h5").read_bytes())
    make_products(cfg, tables, crs, tmp_path, QUIET, "cpu")
    made = _rasters(tmp_path)
    depth = made[step.DEPTH_FILE].astype(np.float64)
    west, north, pixel = made[step.DEPTH_FILE + ":at"]
    rows, cols, _cell = strip_on_lattice(tables)
    k = round(tables.grid.dx / pixel)
    top, left = round((tables.grid.y0 - north) / pixel), round((west - tables.grid.x0) / pixel)
    on_strip = np.zeros(depth.shape, bool)
    for r, c in zip(rows, cols, strict=True):
        on_strip[max(r * k - top, 0) : max((r + 1) * k - top, 0), max(c * k - left, 0) : max((c + 1) * k - left, 0)] = True
    wet = depth != step.NO_DEPTH
    jump = np.abs(np.diff(depth, axis=1))
    both = wet[:, 1:] & wet[:, :-1]
    across = on_strip[:, 1:] != on_strip[:, :-1]
    assert (both & across).sum() > 20
    at_join, inside = float(jump[both & across].mean()), float(jump[both & ~across].mean())
    assert at_join <= 2.0 * inside + 0.005
