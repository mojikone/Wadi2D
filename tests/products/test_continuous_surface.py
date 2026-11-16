"""The continuous water surface of the maps (W100): one surface through the cell corners, depth the surface over the
ground at each pixel, no cell cut and no refill of a cell afterwards; and it must not carry water over high ground."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.config.schema import Pixels
from wadi2d.products.ground import CellPixels, auto_stride
from wadi2d.products.pixels import PixelMaxima, array_module, halo, kept_cells

K = 10
"""Pixels along a cell."""
PIXEL = 2.0
CELL = K * PIXEL
EDGE_TOLERANCE = 0.002
"""Metres. How much more the depth may change between two pixels either side of a cell edge than between two pixels
inside a cell, on average: the surface is one plane-wise sheet, so the two should be the same but for float32."""


def flat_level(ground: np.ndarray, mean_depth: float) -> float:
    """The level a cell's flat fill of ``mean_depth`` stands at over its pixels ``ground`` (the sub-grid level)."""
    z = np.sort(ground.ravel())
    water = mean_depth * z.size
    for n in range(1, z.size + 1):
        level = (water + z[:n].sum()) / n
        if n == z.size or level <= z[n]:
            return float(level)
    return float(z[-1])


def draw(ground: np.ndarray, level: np.ndarray, mean: np.ndarray, rule: Pixels, sill_x=None, sill_y=None, xp=np):
    """One map on cells of K x K pixels, every cell kept; ``ground`` (ny, nx, K, K). The face grounds default to the
    lowest ground along each face, as the tables give them."""
    ny, nx = level.shape
    keep = np.ones((ny, nx), bool)
    rows, cols = np.nonzero(keep)
    cells = CellPixels(rows, cols, K, PIXEL, 0.0, ground.reshape(ny * nx, K * K).astype(np.float32))
    zmin = ground.min(axis=(2, 3)).astype(np.float32)
    if sill_x is None:
        west = np.minimum(ground[:, :, :, 0], np.roll(ground, 1, axis=1)[:, :, :, -1]).min(axis=2)
        sill_x = west.astype(np.float32)
    if sill_y is None:
        north = np.minimum(ground[:, :, 0, :], np.roll(ground, 1, axis=0)[:, :, -1, :]).min(axis=2)
        sill_y = north.astype(np.float32)
    maxima = PixelMaxima(xp, cells, zmin, sill_x, sill_y, keep, rule)
    depth = np.where(level > -np.inf, level - zmin, 0.0).astype(np.float32)
    maxima.add(np.maximum(depth, 0.0), mean.astype(np.float32), np.zeros((ny, nx), np.float32))
    return maxima.result()[0].reshape(ny, nx, K, K)


def jumps(depth: np.ndarray) -> tuple[float, float]:
    """Mean change of depth between neighbouring pixels across cell edges, and inside cells, east to west."""
    raster = depth.transpose(0, 2, 1, 3).reshape(depth.shape[0] * K, depth.shape[1] * K)
    step = np.abs(np.diff(raster, axis=1))
    edge = (np.arange(1, raster.shape[1]) % K) == 0
    return float(step[:, edge].mean()), float(step[:, ~edge].mean())


def tilted(ny: int, nx: int, slope: float) -> np.ndarray:
    x = (np.arange(nx * K) + 0.5) * PIXEL
    y = (np.arange(ny * K) + 0.5) * PIXEL
    plane = 100.0 - slope * x[None, :] - 0.3 * slope * y[:, None]
    return plane.reshape(ny, K, nx, K).transpose(0, 2, 1, 3)


def sheet(ground: np.ndarray, seed: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """A thin sheet of 4 to 6 cm a cell, its levels the cells' own flat fills, as the sub-grid tables hold them."""
    rng = np.random.default_rng(seed)
    ny, nx = ground.shape[:2]
    mean = rng.uniform(0.04, 0.06, (ny, nx))
    level = np.array([[flat_level(ground[j, i], mean[j, i]) for i in range(nx)] for j in range(ny)])
    return level, mean


def test_a_thin_sheet_on_a_tilted_plane_has_no_step_at_cell_edges() -> None:
    """10 % slope, 20 m cells, sheets of 4 to 6 cm: the flat fill puts each cell's water in a wedge 0.6 m deep at its
    low corner. The surface through the corners runs parallel to the ground and reads the sheet, with no step at an
    edge; the corners alone lose it under the ground (RAS Mapper's sloping mode), the old rule without its passes
    draws every cell as a block."""
    ground = tilted(6, 8, 0.10)
    level, mean = sheet(ground)
    continuous = draw(ground, level, mean, Pixels(surface="continuous"))
    corners = draw(ground, level, mean, Pixels(surface="corners"))
    blocks = draw(ground, level, mean, Pixels(surface="cell_fill", edge_passes=0, cell_depth=0.0))
    inner = (slice(1, -1), slice(1, -1))
    at_edges, inside = jumps(continuous[inner])
    assert at_edges <= inside + EDGE_TOLERANCE
    assert continuous[inner].mean() == pytest.approx(mean[inner].mean(), rel=0.15)  # the sheet is there
    assert corners[inner].mean() < 0.2 * mean[inner].mean()  # ... and the levels alone lose it
    assert jumps(blocks[inner])[0] > 2.0 * jumps(blocks[inner])[1]  # the old cut blocks step at every edge


def test_no_cell_is_cut_for_its_mean_depth() -> None:
    """W100: a cell of 3 cm beside one of 8 cm is not left out; under ``cell_fill`` it still is."""
    peak = np.array([[0.03, 0.08, 0.0]], np.float32)
    assert kept_cells(peak, Pixels()).tolist() == [[True, True, False]]
    assert kept_cells(peak, Pixels(surface="cell_fill")).tolist() == [[False, True, False]]


def test_a_terrace_beside_a_channel_stays_dry() -> None:
    """A channel 1.5 m deep, its bank in the middle of the second column of cells, a terrace 3 m above its bed beyond,
    a film on the terrace: the film's water passes the terrace's face down into the channel's cell, but weighted by
    depth the channel's surface stays its own, and no terrace pixel takes water drawn up from the channel."""
    ground = np.full((3, 4, K, K), 103.0)
    ground[:, 0] = 100.0
    ground[:, 1, :, : K // 2] = 100.0
    level = np.array([[101.5, 101.5, 103.01, 103.01]] * 3)
    mean = np.array([[1.5, 0.75, 0.01, 0.01]] * 3)
    depth = draw(ground, level, mean, Pixels())
    terrace = ground >= 103.0
    assert depth[terrace].max() < Pixels().depth_floor  # the film stays under the floor: the terrace is dry
    assert depth[1][~terrace[1]].mean() == pytest.approx(1.5, abs=0.02)


def test_a_crest_line_is_not_crossed() -> None:
    """A pool at 101 m west of a crest at 102 m, low ground at 100 m east of it with 20 cm of its own: the east
    cells draw their own 20 cm, never the pool's metre."""
    ground = np.full((3, 4, K, K), 100.0)
    level = np.array([[101.0, 101.0, 100.2, 100.2]] * 3)
    mean = np.array([[1.0, 1.0, 0.2, 0.2]] * 3)
    sill_x = np.full((3, 4), 100.0, np.float32)
    sill_x[:, 2] = 102.0  # the crest, on the west face of the third column
    sill_y = np.full((3, 4), 100.0, np.float32)
    depth = draw(ground, level, mean, Pixels(), sill_x=sill_x, sill_y=sill_y)
    assert depth[:, 2:].max() == pytest.approx(0.2, abs=1e-4)
    assert depth[:, :2].min() == pytest.approx(1.0, abs=1e-4)
    dry = draw(ground, np.array([[101.0, 101.0, -np.inf, -np.inf]] * 3), np.array([[1.0, 1.0, 0.0, 0.0]] * 3), Pixels(), sill_x, sill_y)
    assert dry[:, 2:].max() == 0.0  # a dry cell beyond the crest takes nothing


def test_water_spilling_into_a_dry_cell_ends_on_its_ground() -> None:
    """A wet cell whose water passes the face into a dry neighbour: the dry cell takes pixels too, and the water ends
    where the ground rises through the surface, not at the cell edge."""
    x = (np.arange(3 * K) + 0.5) * PIXEL
    row = 100.0 + 0.05 * np.maximum(x - CELL, 0.0)  # flat in the first cell, rising after it
    ground = np.tile(row.reshape(3, K)[None, :, None, :], (3, 1, K, 1))
    level = np.array([[100.5, -np.inf, -np.inf]] * 3)
    mean = np.array([[0.5, 0.0, 0.0]] * 3)
    depth = draw(ground, level, mean, Pixels(surface="corners"))
    middle = depth[1, 1]  # the dry cell next to the wet one
    assert middle[:, 0].max() > 0.0  # water carried past the cell edge ...
    assert middle[:, -1].max() == 0.0  # ... and ending on the rising ground inside the cell


def test_a_deep_pool_is_drawn_flat() -> None:
    """A bowl 12 m deep at its middle, filled to 105 m: every pixel reads 105 m less its ground."""
    x = (np.arange(5 * K) + 0.5) * PIXEL - 2.5 * CELL
    bowl = 93.0 + 0.004 * (x[None, :] ** 2 + x[:, None] ** 2)
    ground = bowl.reshape(5, K, 5, K).transpose(0, 2, 1, 3)
    mean = np.maximum(105.0 - ground, 0.0).mean(axis=(2, 3))
    level = np.where(mean > 0.0, 105.0, -np.inf)
    for surface in ("continuous", "corners"):
        depth = draw(ground, level, mean, Pixels(surface=surface))
        wet = level > -np.inf
        expected = np.maximum(105.0 - ground, 0.0)
        assert np.abs(depth[wet] - expected[wet]).max() < 1e-3, surface


@pytest.mark.gpu
@pytest.mark.parametrize("surface", ["continuous", "corners"])
def test_the_card_draws_what_the_host_draws(surface: str) -> None:
    xp = array_module("auto")
    if xp is np:
        pytest.skip("no GPU")
    ground = tilted(6, 8, 0.10)
    level, mean = sheet(ground)
    gpu = draw(ground, level, mean, Pixels(surface=surface), xp=xp)
    cpu = draw(ground, level, mean, Pixels(surface=surface))
    assert np.abs(gpu - cpu).max() < 1e-3


def test_the_halo_follows_the_rule() -> None:
    assert halo(Pixels()) == 3 and halo(Pixels(surface="corners")) == 2
    assert halo(Pixels(surface="cell_fill")) == Pixels().edge_passes + 2


@pytest.mark.parametrize(
    "dx, native, stride, expected",
    [(20.0, 0.5, 1, 4), (10.0, 0.5, 1, 2), (5.0, 0.5, 1, 1), (30.0, 0.5, 1, 4), (25.0, 0.5, 1, 2), (20.0, 5.0, 1, 1), (20.0, 0.5, 2, 4), (20.0, 1.0, 3, 3)],
)
def test_the_maps_pixel_left_empty(dx: float, native: float, stride: int, expected: int) -> None:
    """The coarsest DEM stride within 2 m that divides the cell and gives it 8 pixels across, never finer than the
    job's own: Block 2's 20 m cells on the 0.5 m DEM map at 2 m."""
    assert auto_stride(dx, native, stride, 2.0, 8) == expected
