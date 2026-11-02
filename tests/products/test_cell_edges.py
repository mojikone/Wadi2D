"""A cell filled to its own water must not draw as a block: the surface runs through a joined edge without a step."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.config.schema import Pixels
from wadi2d.products.ground import CellPixels
from wadi2d.products.pixels import PixelMaxima, array_module
from wadi2d.products.surface import AROUND, OWN, edge_basis

K = 10
PIXEL = 2.0


def _case(ground: np.ndarray, level: np.ndarray, mean: np.ndarray, rule: Pixels, xp=np, sill: float = -50.0):
    """One map on cells of K x K pixels. ``ground`` is (ny, nx, K, K); the sills let every wet neighbour join."""
    ny, nx = level.shape
    keep = np.ones((ny, nx), bool)
    rows, cols = np.nonzero(keep)
    cells = CellPixels(rows, cols, K, PIXEL, 0.0, ground.reshape(ny * nx, K * K).astype(np.float32))
    zmin = ground.min(axis=(2, 3)).astype(np.float32)
    sills = np.full((ny, nx), sill, np.float32)
    maxima = PixelMaxima(xp, cells, zmin, sills, sills, keep, rule)
    depth = (level - zmin).astype(np.float32)
    maxima.add(depth, mean.astype(np.float32), np.zeros((ny, nx), np.float32))
    return maxima.result()[0].reshape(ny, nx, K, K), ground


def _uneven(blocks: int = 4, seed: int = 5):
    """A row of cells over a channel that keeps changing width, which is what makes the offsets differ."""
    rng = np.random.default_rng(seed)
    across = (np.arange(K) + 0.5) / K - 0.5
    ground = np.zeros((1, blocks, K, K))
    for i in range(blocks):
        ground[0, i] = np.abs(across)[:, None] * rng.uniform(2.0, 16.0)
    mean = rng.uniform(0.2, 1.6, (1, blocks))
    return ground, ground.min(axis=(2, 3)) + mean, mean


def _steps(depth: np.ndarray, ground: np.ndarray) -> float:
    """Mean step of the water surface between the two pixel columns either side of each cell edge."""
    surface = np.where(depth > 0.0, depth + ground, np.nan)
    a, b = surface[0, :-1, :, -1], surface[0, 1:, :, 0]
    return float(np.nanmean(np.abs(a - b)))


def test_weights_sum_to_one_and_the_middle_of_a_cell_reads_only_itself() -> None:
    k = 20
    basis = edge_basis(np, k, 0.3)
    assert basis.shape == (k * k, 9)
    assert basis.sum(axis=1) == pytest.approx(np.ones(k * k), abs=1e-6)
    middle = (k // 2) * k + k // 2
    assert basis[middle, AROUND.index(OWN)] == pytest.approx(1.0)


def test_two_cells_read_the_same_at_their_edge() -> None:
    k = 200
    basis = edge_basis(np, k, 0.3)
    row = (k // 2) * k  # the middle row, its first pixel: the west edge
    assert basis[row, AROUND.index(OWN)] == pytest.approx(0.5, abs=0.01)
    assert basis[row, AROUND.index((0, -1))] == pytest.approx(0.5, abs=0.01)
    assert basis[row, AROUND.index((0, 1))] == 0.0


def test_the_cells_mean_is_mostly_its_own() -> None:
    """What makes the refill converge in a few passes."""
    assert edge_basis(np, 200, 0.3)[:, AROUND.index(OWN)].mean() == pytest.approx(0.7225, abs=0.01)


def test_the_step_at_an_edge_goes_and_the_water_stays() -> None:
    ground, level, mean = _uneven()
    blocks, _ = _case(ground, level, mean, Pixels(edge_passes=0))
    joined, _ = _case(ground, level, mean, Pixels(edge_passes=3))
    assert _steps(blocks, ground) > 0.1
    assert _steps(joined, ground) < 0.25 * _steps(blocks, ground)
    assert joined.mean(axis=(2, 3)) == pytest.approx(mean, abs=1e-4)


def test_no_passes_is_the_plain_fill() -> None:
    """The old surface stays reachable, so a change in a map can be traced to this step."""
    ground, level, mean = _uneven()
    plain, _ = _case(ground, level, mean, Pixels(edge_passes=0))
    assert plain.mean(axis=(2, 3)) == pytest.approx(mean, abs=1e-4)
    assert _steps(plain, ground) > 0.1


def test_a_uniform_sheet_is_left_alone() -> None:
    """Every cell the same: no step to remove, so the pass must change nothing."""
    ground = np.zeros((2, 3, K, K))
    level = np.full((2, 3), 0.5)
    mean = np.full((2, 3), 0.5)
    joined, _ = _case(ground, level, mean, Pixels(edge_passes=3))
    assert joined == pytest.approx(np.full_like(joined, 0.5), abs=1e-5)


def test_a_step_at_a_bank_stays() -> None:
    """Cells that are not one body of water keep their own surface: the blend must not carry it over the bank."""
    ground, level, mean = _uneven()
    joined, _ = _case(ground, level, mean, Pixels(edge_passes=3), sill=1000.0)
    alone, _ = _case(ground, level, mean, Pixels(edge_passes=0), sill=1000.0)
    assert joined == pytest.approx(alone, abs=1e-5)


@pytest.mark.gpu
def test_both_backends_give_the_same_surface() -> None:
    xp = array_module("auto")
    if xp is np:
        pytest.skip("no GPU")
    ground, level, mean = _uneven()
    gpu, _ = _case(ground, level, mean, Pixels(), xp)
    cpu, _ = _case(ground, level, mean, Pixels())
    assert gpu == pytest.approx(cpu, abs=2e-3)
