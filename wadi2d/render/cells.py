"""One saved map drawn by its cell values: a view so far out that a cell is a few screen pixels, or a run with no pixels.

The numbers are the cell slider's (:func:`wadi2d.products.time_slider.cell_frame`): the depth at a cell's deepest point,
its speed, and the class those two give; a cell under the depth floor is dry. Where a screen pixel covers several cells
it takes the highest of them, so a wadi one cell wide stays on the map at any scale.
"""

from __future__ import annotations

import math

import numpy as np

from wadi2d.config.schema import Pixels
from wadi2d.products.hazard import classify
from wadi2d.render.frame_pixels import DEPTH, FIELDS, SPEED
from wadi2d.render.run_source import RunSource
from wadi2d.render.view import View


def _pooled(xp, values, n: int):
    """The highest value of each n x n block; NaN where the whole block is dry. A last block may hang over the grid."""
    ny, nx = -(-values.shape[0] // n), -(-values.shape[1] // n)
    low = xp.full((ny * n, nx * n), -xp.inf, xp.float32)
    low[: values.shape[0], : values.shape[1]] = xp.where(xp.isnan(values), -xp.inf, values)
    top = low.reshape(ny, n, nx, n).max(axis=(1, 3))
    return xp.where(xp.isinf(top), xp.nan, top).astype(xp.float32)


def draw_cells(xp, source: RunSource, frame: int, view: View, field: str, rule: Pixels):
    """The field at every screen pixel of the view, float32, NaN where dry, and the metres one drawn value covers."""
    if field not in FIELDS:
        raise ValueError(f"no field {field!r}: one of {', '.join(FIELDS)}")
    dx = source.dx
    n = max(math.ceil(view.screen_m / dx - 1e-6), 1)  # a block no smaller than a screen pixel: no cell falls between two
    nothing = xp.full((view.height, view.width), xp.nan, xp.float32)
    rows, cols = view.cells(source.x0, source.y0, dx, source.shape)
    rows = (rows[0] // n * n, min(-(-rows[1] // n) * n, source.shape[0]))  # from a whole block: they stand still under a pan
    cols = (cols[0] // n * n, min(-(-cols[1] // n) * n, source.shape[1]))
    if rows[1] <= rows[0] or cols[1] <= cols[0]:
        return nothing, dx * n
    data = source.window(frame, rows, cols)
    depth, speed = xp.asarray(data["depth"]), xp.asarray(data["speed"])
    wet = (depth >= rule.depth_floor) & xp.asarray(source.mask[rows[0] : rows[1], cols[0] : cols[1]])
    if field == DEPTH:
        value = depth
    elif field == SPEED:
        value = speed
    else:
        value = classify(depth, speed, depth * speed, rule, xp).astype(xp.float32)
    value = xp.where(wet, value, xp.nan).astype(xp.float32)
    if n > 1:
        value = _pooled(xp, value, n)
    size = dx * n
    block_rows, block_cols = view.samples(source.x0 + cols[0] * dx, source.y0 - rows[0] * dx, size)
    ny, nx = value.shape
    inside = xp.asarray((block_rows >= 0) & (block_rows < ny))[:, None] & xp.asarray((block_cols >= 0) & (block_cols < nx))[None, :]
    picked = value[xp.asarray(np.clip(block_rows, 0, ny - 1))[:, None], xp.asarray(np.clip(block_cols, 0, nx - 1))[None, :]]
    return xp.where(inside, picked, nothing), size
