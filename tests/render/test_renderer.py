"""A frame drawn on demand against the product step: the same rule, the same numbers, on a real run."""

from __future__ import annotations

import time

import h5py
import numpy as np
import pytest

from tests.render.conftest import CELL, PIXEL, Finished, read_record, whole_domain
from wadi2d.products import step
from wadi2d.products.pixels import array_module, halo, to_host
from wadi2d.products.time_slider import cell_frame, run_mesh
from wadi2d.render.renderer import FrameRenderer
from wadi2d.render.run_source import CELLS, open_run
from wadi2d.render.run_source import PIXEL as AT_PIXEL
from wadi2d.render.view import View

RULE_TOLERANCE = 2e-4
"""Metres. The fill stops within 1e-4 m, and a window and the whole domain reach that from a few float32 bits apart."""
PEAK_FRAME = 5


@pytest.fixture(scope="module")
def renderer(finished: Finished):
    made = FrameRenderer(open_run(finished.run), "cpu")
    yield made
    made.close()


def native(extent, pixel: float = PIXEL) -> View:
    return View.of(extent, round((extent[2] - extent[0]) / pixel), round((extent[3] - extent[1]) / pixel))


def same(drawn: np.ndarray, record: np.ndarray, tolerance: float) -> float:
    """The largest difference; dry must be dry in both."""
    assert drawn.shape == record.shape
    assert np.array_equal(np.isnan(drawn), np.isnan(record))
    wet = ~np.isnan(record)
    assert wet.any()
    worst = float(np.abs(drawn[wet] - record[wet]).max())
    assert worst <= tolerance, worst
    return worst


def test_the_run_opens_at_the_pixel(renderer) -> None:
    source = renderer.source
    assert source.detail == AT_PIXEL and source.note == ""
    assert len(source.names) == 8
    assert renderer.store.pixel == PIXEL and renderer.store.steps == [1, 2, 4, 8]


@pytest.mark.parametrize("frame", [2, PEAK_FRAME, 7])
def test_a_frame_at_the_native_pixel_is_what_the_product_step_computes(finished, renderer, frame) -> None:
    yardstick = whole_domain(finished, frame)
    t = float(renderer.source.times[frame])
    drawn = {field: renderer.draw(t, native(yardstick.extent), field) for field in ("depth", "speed", "hazard")}
    assert all(d.frame == frame and d.detail == AT_PIXEL and d.pixel_m == PIXEL for d in drawn.values())
    same(to_host(drawn["depth"].values), yardstick.depth, RULE_TOLERANCE)
    same(to_host(drawn["speed"].values), yardstick.speed, RULE_TOLERANCE)
    classes = np.nan_to_num(to_host(drawn["hazard"].values), nan=0.0).astype(np.uint8)
    assert (classes != yardstick.hazard).mean() < 1e-4  # a pixel on a class limit may fall either side of it


def test_a_window_inside_the_domain_equals_the_whole_domain_answer(finished, renderer) -> None:
    """The view's cells are cut out with a margin; inside it nothing may show that the window has an edge."""
    yardstick = whole_domain(finished, PEAK_FRAME)
    west, south, east, north = yardstick.extent
    reach = halo(finished.cfg.outputs.pixels) * CELL
    assert east - west > 2 * reach + 6 * CELL, "the domain must be wider than the window, or this proves nothing"
    middle = round((west + east) / 2.0 / CELL) * CELL
    extent = (middle - 2 * CELL, south, middle + 4 * CELL, north)
    window = yardstick.window(extent)
    drawn = renderer.draw(float(renderer.source.times[PEAK_FRAME]), native(extent), "depth")
    same(to_host(drawn.values), yardstick.depth[window], RULE_TOLERANCE)


def test_the_highest_of_the_frames_is_the_record_where_its_peak_is_a_saved_frame(peak_from_a_frame) -> None:
    folder, _peak = peak_from_a_frame
    record_depth, extent = read_record(folder, step.DEPTH_FILE)
    record_speed, _ = read_record(folder, step.SPEED_FILE)
    made = FrameRenderer(open_run(folder), "cpu")
    try:
        highest = {"depth": np.full(record_depth.shape, np.nan, np.float32), "speed": np.full(record_depth.shape, np.nan, np.float32)}
        for t in made.source.times:
            for field, held in highest.items():
                highest[field] = np.fmax(held, to_host(made.draw(float(t), native(extent), field).values))
    finally:
        made.close()
    wet = ~np.isnan(record_depth)
    assert wet.sum() > 1000
    # the record's depth is the highest depth; a pixel is on it when its highest depth passes the floor
    assert np.array_equal(np.isnan(highest["depth"]), ~wet)
    assert float(np.abs(highest["depth"][wet] - record_depth[wet]).max()) <= RULE_TOLERANCE
    assert float(np.abs(np.nan_to_num(highest["speed"][wet]) - record_speed[wet]).max()) <= RULE_TOLERANCE


def test_no_frame_stands_above_the_record_of_the_real_run(finished, renderer) -> None:
    record, extent = read_record(finished.run, step.DEPTH_FILE)
    for t in renderer.source.times:
        drawn = to_host(renderer.draw(float(t), native(extent), "depth").values)
        over = np.nan_to_num(drawn) - np.nan_to_num(record)
        assert float(over.max()) <= RULE_TOLERANCE


COARSE_SHARE = 0.1
"""On the continuous surface (W100) a coarser drawing reads the same surface over ground read one pixel in two, and
a cell's move to hold its water is found over those pixels: the water drawn changes by a little."""


def test_a_coarser_pixel_draws_about_the_same_water(finished, renderer) -> None:
    """One pixel in every two: the water drawn (depth times pixel area) is the native drawing's within a tenth. Under
    W9's rule this test held each cell's mean depth to 2e-4 m: that rule refilled every cell, this one does not."""
    source = renderer.source
    extent = source.extent()
    t = float(source.times[PEAK_FRAME])
    coarse = renderer.draw(t, native(extent, 2 * PIXEL), "depth")
    assert coarse.detail == AT_PIXEL and coarse.pixel_m == 2 * PIXEL
    fine = to_host(renderer.draw(t, native(extent, PIXEL), "depth").values)
    water_fine = float(np.nansum(fine)) * PIXEL**2
    water_coarse = float(np.nansum(to_host(coarse.values))) * (2 * PIXEL) ** 2
    assert water_fine > 0.0
    assert water_coarse == pytest.approx(water_fine, rel=COARSE_SHARE)


def test_far_out_a_cell_draws_the_cell_slider_s_numbers(finished, renderer) -> None:
    source = renderer.source
    west, south, east, north = source.extent()
    view = View.of((west, south, east, north), round((east - west) / CELL), round((north - south) / CELL))
    with h5py.File(source.results, "r") as f:
        group = f["maps"][source.names[PEAK_FRAME]]
        depth, speed = group["depth"][:], group["speed"][:]
    mesh = run_mesh(finished.run, finished.cfg)
    cells = cell_frame(depth, speed, mesh, finished.cfg.outputs.pixels)
    rows, cols = view.samples(source.x0, source.y0, CELL)
    for field in ("depth", "speed", "hazard"):
        drawn = renderer.draw(float(source.times[PEAK_FRAME]), view, field)
        assert drawn.detail == CELLS and drawn.pixel_m == CELL
        got = to_host(drawn.values)[np.searchsorted(rows, mesh.rows), np.searchsorted(cols, mesh.columns)]
        expected = np.where(cells[field] < 0.0, np.nan, cells[field])  # the file's fill value is a dry cell
        assert np.array_equal(np.isnan(got), np.isnan(expected))
        assert np.nanmax(np.abs(got - expected)) < 1e-6


def test_further_out_a_screen_pixel_takes_the_highest_of_its_cells(renderer) -> None:
    source = renderer.source
    west, north = source.x0, source.y0
    ny, nx = source.shape
    whole = (west, north - ny * CELL, west + nx * CELL, north)
    one = to_host(renderer.draw(float(source.times[PEAK_FRAME]), View.of(whole, nx, ny), "depth").values)
    three = renderer.draw(float(source.times[PEAK_FRAME]), View.of(whole, nx // 3 + 1, ny // 3 + 1), "depth")
    assert three.detail == CELLS and three.pixel_m == 3 * CELL
    blocks = np.full((-(-ny // 3) * 3, -(-nx // 3) * 3), -np.inf, np.float32)
    blocks[:ny, :nx] = np.nan_to_num(one, nan=-np.inf)
    highest = blocks.reshape(-1, 3, blocks.shape[1] // 3, 3).max(axis=(1, 3))
    view = View.of(whole, nx // 3 + 1, ny // 3 + 1)
    rows, cols = view.samples(west, north, 3 * CELL)
    inside = (rows[:, None] < highest.shape[0]) & (cols[None, :] < highest.shape[1])
    expected = np.where(inside, highest[np.minimum(rows, highest.shape[0] - 1)[:, None], np.minimum(cols, highest.shape[1] - 1)[None, :]], -np.inf)
    got = np.nan_to_num(to_host(three.values), nan=-np.inf)
    assert np.array_equal(got, expected)
    assert np.isfinite(got).sum() > 20


def test_time_shows_the_last_frame_at_or_before_it(renderer) -> None:
    source = renderer.source
    times = source.times
    assert source.frame_at(times[0] - 100.0) == 0
    assert source.frame_at(times[3]) == 3
    assert source.frame_at(times[3] + 0.4 * (times[4] - times[3])) == 3
    assert source.frame_at(times[4] - 0.3) == 4  # within half a second of a frame is that frame
    assert source.frame_at(times[-1] + 9e9) == len(times) - 1
    assert source.frame_at(None) == len(times) - 1


def test_a_point_reads_the_native_pixel(finished, renderer) -> None:
    yardstick = whole_domain(finished, PEAK_FRAME)
    wet = np.argwhere(~np.isnan(yardstick.depth))
    row, col = wet[len(wet) // 2]
    x = yardstick.extent[0] + (col + 0.3) * PIXEL
    y = yardstick.extent[3] - (row + 0.6) * PIXEL
    found = renderer.point(float(renderer.source.times[PEAK_FRAME]), x, y)
    assert found["frame"] == PEAK_FRAME and found["detail"] == AT_PIXEL and found["pixel_m"] == PIXEL
    assert found["depth"] == pytest.approx(float(yardstick.depth[row, col]), abs=RULE_TOLERANCE)
    assert found["speed"] == pytest.approx(float(yardstick.speed[row, col]), abs=RULE_TOLERANCE)
    assert found["hazard"] == float(yardstick.hazard[row, col])
    dry = renderer.point(float(renderer.source.times[PEAK_FRAME]), yardstick.extent[0] - 500.0, y)
    assert dry["depth"] is None and dry["hazard"] is None


def test_ground_not_read_yet_draws_cells_first_and_the_pixels_when_it_is_here(finished) -> None:
    made = FrameRenderer(open_run(finished.run), "cpu")
    try:
        store = made.store
        read = store._read

        def slow(key):
            time.sleep(0.4)
            return read(key)

        store._read = slow
        source = made.source
        view = native(source.extent())
        t = float(source.times[PEAK_FRAME])
        first = made.draw(t, view, "depth", 0.0)
        assert first.detail == CELLS and first.pending > 0
        second = made.draw(t, view, "depth", None)
        assert second.detail == AT_PIXEL and second.pending == 0 and second.pixel_m == PIXEL
        coarse_view = native(source.extent(), 2 * PIXEL)
        assert made.draw(t, coarse_view, "depth", None).pixel_m == 2 * PIXEL
        store.tiles = type(store.tiles)((key, tile) for key, tile in store.tiles.items() if key[0] == 2)
        fallback = made.draw(t, view, "depth", 0.0)  # the finer ground is gone again: the coarser one stands in
        assert fallback.detail == AT_PIXEL and fallback.pixel_m == 2 * PIXEL and fallback.pending > 0
    finally:
        made.close()


def test_a_drawing_too_large_is_refused(renderer) -> None:
    with pytest.raises(ValueError, match="max_pixels"):
        renderer.draw(None, View.of(renderer.source.extent(), 8000, 8000), "depth")
    with pytest.raises(ValueError, match="no field"):
        renderer.draw(None, View.of(renderer.source.extent(), 8, 8), "level")


@pytest.mark.gpu
def test_gpu_and_cpu_draw_the_same(finished, renderer) -> None:
    pytest.importorskip("cupy")
    if array_module("auto") is np:
        pytest.skip("no GPU")
    on_gpu = FrameRenderer(open_run(finished.run), "gpu")
    try:
        assert on_gpu.backend == "gpu"
        t = float(renderer.source.times[PEAK_FRAME])
        west, south, east, north = renderer.source.extent()
        for pixel in (PIXEL, 2 * PIXEL, CELL, 3 * CELL):
            view = native((west, south, east, north), pixel)
            for field, tolerance in (("depth", 1e-3), ("speed", 1e-3)):
                a = to_host(on_gpu.draw(t, view, field).values)
                b = to_host(renderer.draw(t, view, field).values)
                assert (np.isnan(a) != np.isnan(b)).mean() < 1e-4
                both = ~np.isnan(a) & ~np.isnan(b)
                assert float(np.abs(a[both] - b[both]).max()) <= tolerance
            a = np.nan_to_num(to_host(on_gpu.draw(t, view, "hazard").values))
            b = np.nan_to_num(to_host(renderer.draw(t, view, "hazard").values))
            assert (a != b).mean() < 1e-4
    finally:
        on_gpu.close()


@pytest.mark.parametrize("part", ["mesh", "strips"])
def test_a_mesh_or_aligned_cells_draw_cell_values_and_say_so(finished, tmp_path, part) -> None:
    """Pixels on a quadtree or beside aligned cells are not drawn on demand yet: such a run falls back to its cells."""
    import json
    import shutil

    shutil.copy(finished.run / "results.h5", tmp_path / "results.h5")
    config = json.loads((finished.run / "config.resolved.json").read_text(encoding="utf-8"))
    config[part]["enabled"] = True
    (tmp_path / "config.resolved.json").write_text(json.dumps(config), encoding="utf-8")
    made = FrameRenderer(open_run(tmp_path), "cpu")
    try:
        assert made.source.detail == CELLS and made.store is None
        assert ("mesh" if part == "mesh" else "aligned") in made.source.note
        west, south, east, north = made.source.extent()
        drawn = made.draw(None, native((west, south, east, north), PIXEL), "depth")
        assert drawn.detail == CELLS and drawn.pixel_m == CELL and (np.nan_to_num(to_host(drawn.values)) > 0).any()
    finally:
        made.close()
