"""The square cells' fill on the card (W93): the old steps' numbers to the digit."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.products.pixels import array_module
from wadi2d.products.surface import FILL_STEPS, FILL_TOLERANCE, fill_cells, fill_offset


def _old_fill_offset(xp, surface, ground, mean_depth):
    """The fill as it stood before W93, word for word."""
    relief = ground - surface
    pixels = relief.shape[1]
    water = mean_depth * pixels
    offset = relief.mean(axis=1) + mean_depth
    moving = xp.arange(relief.shape[0])
    left = relief
    for _ in range(FILL_STEPS):
        gap = offset[moving, None] - left
        under = gap > 0.0
        excess = (gap * under).sum(axis=1) - water[moving]
        step = excess / xp.maximum(under.sum(axis=1), 1).astype(xp.float32)
        offset[moving] = offset[moving] - step
        going = step > FILL_TOLERANCE
        if not bool(going.any()):
            break
        moving, left = moving[going], left[going]
    return offset


def _case(rng, n: int, k: int):
    """Cells from deep water to thin sheets over strong relief, which take every Newton step."""
    slope = rng.normal(0.0, 3.0, (n, 1, 1)) * np.linspace(-1.0, 1.0, k)[None, None, :]
    ground = (slope + rng.normal(0.0, 0.4, (n, k, k))).reshape(n, k * k).astype(np.float32)
    surface = rng.normal(0.0, 0.5, (n, k * k)).astype(np.float32)
    depth = np.exp(rng.uniform(np.log(1e-4), np.log(5.0), n)).astype(np.float32)
    return surface, ground, depth


def test_the_cards_fill_is_the_old_fill_to_the_digit() -> None:
    cp = pytest.importorskip("cupy")
    if array_module("auto") is np:
        pytest.skip("no GPU")
    rng = np.random.default_rng(93)
    for n, k in ((1, 40), (3, 40), (257, 40), (4000, 40), (900, 10), (50, 7)):
        surface, ground, depth = (cp.asarray(a) for a in _case(rng, n, k))
        want = _old_fill_offset(cp, surface, ground, depth)
        np.testing.assert_array_equal(fill_offset(cp, surface, ground, depth).get(), want.get())
        old_depth = cp.maximum(want[:, None] - (ground - surface), 0.0)
        np.testing.assert_array_equal(fill_cells(cp, surface, ground, depth).get(), old_depth.get())


def test_the_hosts_fill_is_unchanged() -> None:
    rng = np.random.default_rng(7)
    surface, ground, depth = _case(rng, 300, 12)
    np.testing.assert_array_equal(fill_offset(np, surface, ground, depth), _old_fill_offset(np, surface, ground, depth))
