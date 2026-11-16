"""Walks down the D8 lines that the domain needs: where a pixel's way down first enters the outline, and where it last
leaves it. Flat receiver indices as in :mod:`wadi2d.basin.kernels`; Numba on plain arrays.

Interface: :func:`gate_in`, :func:`last_inside`.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from wadi2d.basin.kernels import NONE


@njit(cache=True)
def gate_in(down: np.ndarray, order: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """For a pixel outside, the last pixel outside on its way down before it first enters: its water crosses the
    outline between that pixel and its receiver. :data:`NONE` inside and for a way that never enters."""
    gate = np.full(down.size, NONE, dtype=np.int64)
    for index in range(order.size - 1, -1, -1):  # downstream first
        pixel = order[index]
        receiver = down[pixel]
        if inside[pixel] or receiver == NONE:
            continue
        gate[pixel] = pixel if inside[receiver] else gate[receiver]
    return gate


@njit(cache=True)
def last_inside(down: np.ndarray, order: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """The last pixel inside on each pixel's way down, itself included: where its water leaves the outline for good;
    :data:`NONE` for a way that never enters."""
    last = np.full(down.size, NONE, dtype=np.int64)
    for index in range(order.size - 1, -1, -1):
        pixel = order[index]
        receiver = down[pixel]
        if receiver != NONE and last[receiver] != NONE:
            last[pixel] = last[receiver]
        elif inside[pixel]:
            last[pixel] = pixel
    return last
