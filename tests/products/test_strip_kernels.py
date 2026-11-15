"""W86: the sums of a strip's pixel maps, in one order on the host and on the card, and that order the old one."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.products.pixels import array_module
from wadi2d.products.strip_kernels import StripKernels


@pytest.mark.parametrize("width", [4, 7, 8, 9, 15, 16, 19])
def test_a_pixels_node_slots_are_summed_as_numpy_sums_a_row(width: int) -> None:
    """The strip's surface at a pixel is a row of products summed; the kernel takes them in NumPy's own order, so
    the block's pixels are the old whole-strip pixels to the digit whatever the widest ring."""
    rng = np.random.default_rng(width)
    slots = (rng.random((50, width)) * 300.0).astype(np.float32)
    cell = rng.integers(0, 50, 4000).astype(np.int32)
    weights = rng.random((4000, width)).astype(np.float32)
    weights[rng.random(weights.shape) < 0.2] = 0.0
    want = (slots[cell] * weights).sum(axis=1)
    np.testing.assert_array_equal(StripKernels(np).at_pixels(slots, cell, weights), want)


def _newton_case(seed: int = 5):
    rng = np.random.default_rng(seed)
    counts = rng.integers(0, 60, 300)
    counts[:3] = 0  # cells with no pixel
    ptr = np.concatenate(([0], np.cumsum(counts))).astype(np.int64)
    cell = np.repeat(np.arange(counts.size), counts).astype(np.int32)
    relief = (rng.random(cell.size) * 4.0 + 100.0).astype(np.float32)
    water = (rng.random(counts.size) * 0.5 * counts).astype(np.float32)
    return ptr, cell, relief, water


def test_the_fill_in_loops_is_the_fill_in_scatter_adds_to_the_digit() -> None:
    """A cell whose offset has stopped moving is left alone, and gets what going on would give it."""
    from wadi2d.config.schema import Pixels as PixelRule
    from wadi2d.products.strip_pixels import BlockStripMaxima
    from wadi2d.strips.pixels import StripMaxima

    ptr, cell, relief, water = _newton_case()
    old, new = StripMaxima.__new__(StripMaxima), BlockStripMaxima.__new__(BlockStripMaxima)
    for held in (old, new):
        held.xp, held.rule, held.n, held.cell = np, PixelRule(), ptr.size - 1, cell
        held.npix_cell = np.diff(ptr).astype(np.float32)
    new.ptr, new.kernels = ptr, StripKernels(np)
    np.testing.assert_array_equal(new._fill_offset(relief, water), old._fill_offset(relief, water))


def test_the_cards_sums_are_the_hosts_to_the_digit() -> None:
    """One order of summing on both backends: the strip's pixels made on the card are those made on the host."""
    cp = pytest.importorskip("cupy")
    if array_module("auto") is np:
        pytest.skip("no GPU")
    host, card = StripKernels(np), StripKernels(cp)
    rng = np.random.default_rng(9)
    for width in (5, 8, 11):
        slots = (rng.random((40, width)) * 300.0).astype(np.float32)
        cell = rng.integers(0, 40, 3000).astype(np.int32)
        weights = rng.random((3000, width)).astype(np.float32)
        got = card.at_pixels(cp.asarray(slots), cp.asarray(cell), cp.asarray(weights))
        np.testing.assert_array_equal(got.get(), host.at_pixels(slots, cell, weights))
    ptr, _cell, relief, water = _newton_case()
    np.testing.assert_array_equal(card.cell_sums(cp.asarray(ptr), cp.asarray(relief)).get(), host.cell_sums(ptr, relief))
    n = ptr.size - 1
    start = host.cell_sums(ptr, relief) / np.maximum(np.diff(ptr), 1).astype(np.float32)
    state = [start, np.zeros(n, np.float32), np.ones(n, bool)]
    on_card = [cp.asarray(a) for a in state]
    for _ in range(6):
        host.newton(ptr, relief, water, *state)
        card.newton(cp.asarray(ptr), cp.asarray(relief), cp.asarray(water), *on_card)
        for a, b in zip(state, on_card, strict=True):
            np.testing.assert_array_equal(b.get(), a)
    label = rng.integers(0, 200, 1500).astype(np.int64)
    own = (rng.random(1500) * 50.0).astype(np.float32)
    weight = (rng.random(1500) < 0.7).astype(np.float32)
    want = host.label_sums(label, None, own, weight)
    held = cp.asarray(label)
    got = card.label_sums(held, card.label_order(held), cp.asarray(own), cp.asarray(weight))
    for a, b in zip(want, got, strict=True):
        np.testing.assert_array_equal(b.get(), a)
