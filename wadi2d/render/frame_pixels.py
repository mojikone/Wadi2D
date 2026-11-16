"""One saved map at the pixel over a window of cells: the product step's own rule, on the cells a view needs.

:class:`wadi2d.products.pixels.PixelMaxima` keeps the maxima of a run over all its kept cells. Here the same object
is built on a window and holds one map at a time, so a frame on the slider and the rasters of record come from the same
lines of code, by the job's own ``outputs.pixels.surface`` (W100: the continuous surface by default). A cell reads its
neighbours' levels and their fill offsets: :func:`wadi2d.products.pixels.halo` cells out. The window is that much
wider than the view, and the cells inside the view then equal the whole-domain answer.
"""

from __future__ import annotations

import numpy as np

from wadi2d.config.schema import Pixels
from wadi2d.products.ground import CellPixels
from wadi2d.products.hazard import classify, hazard_floor
from wadi2d.products.pixels import PixelMaxima
from wadi2d.render.ground_store import GroundStore
from wadi2d.render.run_source import PixelTables
from wadi2d.render.view import View

DEPTH, SPEED, HAZARD = "depth", "speed", "hazard"
FIELDS = (DEPTH, SPEED, HAZARD)


class PixelFrame(PixelMaxima):
    """The maxima of one map: that map."""

    def show(self, depth: np.ndarray, mean_depth: np.ndarray, speed: np.ndarray) -> tuple:
        """(cells, k * k) depth and speed of one map, on the device."""
        xp = self.xp
        for batch in self.batches:
            shape = (batch.last - batch.first, self.k**2)
            batch.maxima = [self._rest(xp.zeros(shape, xp.float32)) for _ in range(3)]
        self.add(depth, mean_depth, speed)
        return tuple(xp.concatenate([xp.asarray(batch.maxima[n]) for batch in self.batches]) for n in (0, 1))


class WindowPixels:
    """The kept cells of a window of the grid at one pixel step, ready for any frame."""

    def __init__(self, xp, tables: PixelTables, store: GroundStore, m: int, rows: tuple[int, int], cols: tuple[int, int], rule: Pixels) -> None:
        self.xp, self.rule, self.m = xp, rule, m
        self.rows, self.cols = rows, cols
        self.k = store.pixels(m)
        self.pixel = store.pixel_m(m)
        window = (slice(*rows), slice(*cols))
        keep = tables.keep[window]
        kept_rows, kept_cols = np.nonzero(keep)
        self.count = kept_rows.size
        self.frame = None
        if self.count == 0:
            return
        ground = store.cells(m, kept_rows + rows[0], kept_cols + cols[0])
        cells = CellPixels(kept_rows, kept_cols, self.k, self.pixel, tables.datum, ground)
        self.frame = PixelFrame(xp, cells, tables.zmin[window], tables.sill_x[window], tables.sill_y[window], keep, rule)
        place = np.full(keep.shape, -1, np.int32)
        place[kept_rows, kept_cols] = np.arange(self.count, dtype=np.int32)
        self.place = xp.asarray(place)

    def draw(self, data: dict[str, np.ndarray], view: View, x0: float, y0: float, field: str):
        """The field at every screen pixel of the view, float32, NaN where dry. ``data`` is the frame over the window."""
        xp, k = self.xp, self.k
        nothing = xp.full((view.height, view.width), xp.nan, xp.float32)
        if self.frame is None:
            return nothing
        depth, speed = self.frame.show(data["depth"], data["mean_depth"], data["speed"])
        pixel_rows, pixel_cols = view.samples(x0, y0, self.pixel)
        pixel_rows, pixel_cols = pixel_rows - self.rows[0] * k, pixel_cols - self.cols[0] * k
        ny, nx = self.place.shape
        in_rows = (pixel_rows >= 0) & (pixel_rows < ny * k)
        in_cols = (pixel_cols >= 0) & (pixel_cols < nx * k)
        cell_rows = xp.asarray(np.clip(pixel_rows // k, 0, ny - 1))
        cell_cols = xp.asarray(np.clip(pixel_cols // k, 0, nx - 1))
        cell = self.place[cell_rows[:, None], cell_cols[None, :]]
        inside = (cell >= 0) & xp.asarray(in_rows)[:, None] & xp.asarray(in_cols)[None, :]
        cell = xp.maximum(cell, 0)
        within = xp.asarray((pixel_rows % k) * k)[:, None] + xp.asarray(pixel_cols % k)[None, :]
        d = depth[cell, within]
        wet = inside & (d >= self.rule.depth_floor)
        if field == DEPTH:
            value = d
        elif field == SPEED:
            value = speed[cell, within]
        elif field == HAZARD:
            s = speed[cell, within]
            value = classify(d, s, d * s, self.rule, xp).astype(xp.float32)
            wet = wet & (d >= hazard_floor(self.rule))  # thin water off the hazard map
        else:
            raise ValueError(f"no field {field!r}: one of {', '.join(FIELDS)}")
        return xp.where(wet, value, nothing)
