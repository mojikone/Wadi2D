"""W93: a strip pixel's Wachspress weights from the compiled loop are NumPy's to the digit."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.products.strip_weights import wachspress_into
from wadi2d.strips.pixels import _wachspress


@pytest.mark.parametrize("m", [3, 4, 5, 6, 7, 8, 9, 12])
def test_the_compiled_weights_are_numpys_to_the_digit(m: int) -> None:
    rng = np.random.default_rng(m)
    n, cells = 20000, 300
    # convex rings counter-clockwise, at coordinates of a UTM grid, cells of 5 to 40 m
    angle = np.sort(rng.random((cells, m)) * 2 * np.pi, axis=1)
    radius = rng.uniform(5.0, 40.0, (cells, 1))
    centre = np.column_stack([rng.uniform(4.0e5, 5.0e5, cells), rng.uniform(2.6e6, 2.7e6, cells)])
    x = (centre[:, :1] + radius * np.cos(angle)).ravel()
    y = (centre[:, 1:] + radius * np.sin(angle)).ravel()
    cell = rng.integers(0, cells, n)
    nodes = cell[:, None] * m + np.arange(m)[None, :]
    t = rng.random((n, m)) ** 2
    t /= t.sum(axis=1, keepdims=True)
    px, py = (t * x[nodes]).sum(axis=1), (t * y[nodes]).sum(axis=1)  # points inside their rings
    want = np.zeros((n, m + 2), np.float32)
    want[:, :m] = _wachspress(px, py, x[nodes], y[nodes])
    got = np.zeros((n, m + 2), np.float32)
    padded = np.concatenate([nodes, nodes[:, :2]], axis=1)
    wachspress_into(px, py, padded, np.full(n, m, np.int64), x, y, got)
    np.testing.assert_array_equal(got, want)
