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


def _fills():
    from wadi2d.config.schema import Pixels as PixelRule
    from wadi2d.products.strip_pixels import BlockStripMaxima
    from wadi2d.strips.pixels import StripMaxima

    ptr, cell, relief, water = _newton_case()
    old, new = StripMaxima.__new__(StripMaxima), BlockStripMaxima.__new__(BlockStripMaxima)
    for held in (old, new):
        held.xp, held.rule, held.n, held.cell = np, PixelRule(), ptr.size - 1, cell
        held.npix_cell = np.diff(ptr).astype(np.float32)
    new.ptr, new.kernels = ptr, StripKernels(np)
    return old, new, ptr, cell, relief, water


def test_a_cell_stopping_on_its_own_step_holds_its_water_and_stays_within_the_tolerance_of_the_old_fill() -> None:
    """The old fill went on until every cell of the strip had settled; a cell now stops on its own step. Both hold
    the cell's water, and they part by less than the fill's tolerance."""
    from wadi2d.products.surface import FILL_TOLERANCE

    old, new, ptr, cell, relief, water = _fills()
    was, now = old._fill_offset(relief, water), new._fill_offset(relief, water)
    assert np.abs(now - was).max() < FILL_TOLERANCE
    held = np.zeros(ptr.size - 1)
    np.add.at(held, cell, np.maximum(now[cell] - relief, 0.0))
    pixels = np.maximum(np.diff(ptr), 1)
    assert (np.abs(held - water) / pixels).max() < 2.0 * FILL_TOLERANCE  # a mean depth off by under a step


def test_a_cells_fill_does_not_depend_on_the_cells_worked_with_it() -> None:
    """Half the cells filled alone get what they get among all of them, to the digit: blocks cannot move a pixel."""
    _old, new, ptr, _cell, relief, water = _fills()
    whole = new._fill_offset(relief, water)
    n = ptr.size - 1
    part = np.arange(n // 2, n)
    lo = ptr[n // 2]
    new.ptr, new.n, new.npix_cell = ptr[n // 2 :] - lo, part.size, np.diff(ptr)[part].astype(np.float32)
    np.testing.assert_array_equal(new._fill_offset(relief[lo:], water[part]), whole[part])


def _warp_kernels_are_the_thread_kernels(cp, card: StripKernels, rng) -> None:
    """A warp to a cell (W93) gives the one-thread-a-cell sums to the digit, on cells of 0 to 2,000 pixels."""
    sizes = rng.integers(0, 2000, 700)
    sizes[:5] = (0, 1, 31, 32, 33)
    ptr = np.zeros(sizes.size + 1, np.int64)
    np.cumsum(sizes, out=ptr[1:])
    n, total = sizes.size, int(ptr[-1])
    relief = (rng.normal(0.0, 2.0, total) * rng.random(total)).astype(np.float32)
    water = (rng.random(n) * sizes * 0.3).astype(np.float32)
    dptr, drelief, dwater = cp.asarray(ptr), cp.asarray(relief), cp.asarray(water)
    old = cp.empty(n, cp.float32)
    card._launch("cell_sums", n, (dptr, drelief, old, np.int64(n)))
    np.testing.assert_array_equal(card.cell_sums(dptr, drelief).get(), old.get())
    start = old / cp.maximum(cp.asarray(sizes, cp.float32), 1.0)
    one = [start.copy(), cp.zeros(n, cp.float32), cp.ones(n, bool)]
    warp = [start.copy(), cp.zeros(n, cp.float32), cp.ones(n, bool)]
    for _ in range(8):
        card._launch("newton", n, (dptr, drelief, dwater, *one, np.int64(n), np.float32(1e-4)))
        card.newton(dptr, drelief, dwater, *warp, 1e-4)
        for a, b in zip(one, warp, strict=True):
            np.testing.assert_array_equal(b.get(), a.get())


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
        host.newton(ptr, relief, water, *state, 1e-4)
        card.newton(cp.asarray(ptr), cp.asarray(relief), cp.asarray(water), *on_card, 1e-4)
        for a, b in zip(state, on_card, strict=True):
            np.testing.assert_array_equal(b.get(), a)
    _warp_kernels_are_the_thread_kernels(cp, card, rng)
    label = rng.integers(0, 200, 1500).astype(np.int64)
    own = (rng.random(1500) * 50.0).astype(np.float32)
    weight = (rng.random(1500) < 0.7).astype(np.float32)
    want = host.label_sums(label, None, own, weight)
    held = cp.asarray(label)
    got = card.label_sums(held, card.label_order(held), cp.asarray(own), cp.asarray(weight))
    for a, b in zip(want, got, strict=True):
        np.testing.assert_array_equal(b.get(), a)
