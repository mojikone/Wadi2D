"""A drawing of a run: which frame, how fine, and by which rule.

A view where a cell is at least ``outputs.slider.cell_pixels`` screen pixels wide is drawn at the pixel, on the
ground at the coarsest pixel step no coarser than a screen pixel. Ground not read yet is waited for a moment; past
that the drawing takes a coarser ground already here, or the cell values, and says how many tiles are still to come,
so the caller can ask again. Further out, cells are drawn by their own values. Time is not interpolated: a drawing
shows the last saved map at or before the time asked for.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.products.pixels import array_module
from wadi2d.render.cells import draw_cells
from wadi2d.render.frame_pixels import FIELDS, WindowPixels, halo
from wadi2d.render.ground_store import GroundStore
from wadi2d.render.run_source import CELLS, PIXEL, RunSource
from wadi2d.render.view import View
from wadi2d.solver.layout import TILE

GPU, CPU = "gpu", "cpu"
WINDOWS_HELD = 2
"""Windows kept ready: the map canvas and one other drawing."""


@dataclass
class Drawn:
    values: object
    """(height, width) float32 on the device or the host, NaN where dry."""
    frame: int
    t_s: float
    detail: str
    pixel_m: float
    """Metres one drawn value covers."""
    pending: int = 0
    """Tiles of ground still being read for a finer drawing of this view."""


class FrameRenderer:
    def __init__(self, source: RunSource, backend: str = "auto") -> None:
        self.source = source
        self.xp = array_module(backend)
        self.rule = source.cfg.outputs.pixels
        self.slider = source.cfg.outputs.slider
        self.store = None
        if source.detail == PIXEL:
            self.store = GroundStore(source.cfg, source.tables.grid, source.tables.datum)
        self.windows: dict[tuple, WindowPixels] = {}
        self.note = ""

    @property
    def backend(self) -> str:
        return CPU if self.xp is np else GPU

    def close(self) -> None:
        if self.store is not None:
            self.store.close()

    def _to_host(self) -> None:
        """The card is full, perhaps with someone else's work: this process draws on the CPU from here on."""
        self.windows.clear()
        self.xp.get_default_memory_pool().free_all_blocks()
        self.xp = np
        self.note = "The drawing did not fit on the GPU, so it is made on the CPU, more slowly."

    def draw(self, t_s: float | None, view: View, field: str, wait_s: float | None = None, aside: bool = False) -> Drawn:
        """One field of the frame at ``t_s`` over a view. ``wait_s`` None waits for the ground however long it takes.

        ``aside`` marks a drawing beside the main one (a value under the cursor): it leaves the main one's reads alone."""
        if field not in FIELDS:
            raise ValueError(f"no field {field!r}: one of {', '.join(FIELDS)}")
        if view.width * view.height > self.slider.max_pixels:
            raise ValueError(f"a drawing of {view.width} x {view.height} pixels is over outputs.slider.max_pixels")
        try:
            return self._draw(t_s, view, field, wait_s, aside)
        except Exception as error:
            if self.xp is np or type(error).__name__ != "OutOfMemoryError":
                raise
            self._to_host()
            return self._draw(t_s, view, field, wait_s, aside)

    def _draw(self, t_s, view: View, field: str, wait_s, aside: bool) -> Drawn:
        source = self.source
        frame = source.frame_at(t_s)
        at = float(source.times[frame])
        pending = 0
        if self.store is not None and source.dx / view.screen_m >= self.slider.cell_pixels:
            rows, cols = view.cells(source.x0, source.y0, source.dx, source.shape, halo(self.rule))
            if rows[1] <= rows[0] or cols[1] <= cols[0]:
                nothing = self.xp.full((view.height, view.width), self.xp.nan, self.xp.float32)
                return Drawn(nothing, frame, at, PIXEL, self.store.pixel)
            m, pending = self._ground(view, rows, cols, wait_s, aside)
            if m is not None:
                window = self._window(m, rows, cols)
                values = window.draw(source.window(frame, rows, cols), view, source.x0, source.y0, field)
                return Drawn(values, frame, at, PIXEL, window.pixel, pending)
        values, size = draw_cells(self.xp, source, frame, view, field, self.rule)
        return Drawn(values, frame, at, CELLS, size, pending)

    def _tiles(self, rows: tuple[int, int], cols: tuple[int, int]) -> list[tuple[int, int]]:
        """The tiles of the window that hold a kept cell."""
        keep = self.source.tables.keep
        found = []
        for tile_row in range(rows[0] // TILE, -(-rows[1] // TILE)):
            for tile_col in range(cols[0] // TILE, -(-cols[1] // TILE)):
                r = (max(tile_row * TILE, rows[0]), min((tile_row + 1) * TILE, rows[1]))
                c = (max(tile_col * TILE, cols[0]), min((tile_col + 1) * TILE, cols[1]))
                if keep[r[0] : r[1], c[0] : c[1]].any():
                    found.append((tile_row, tile_col))
        return found

    def _ground(self, view: View, rows, cols, wait_s, aside: bool) -> tuple[int | None, int]:
        """The pixel step whose ground is here for this window, and the tiles still coming for the one wanted."""
        store = self.store
        tiles = self._tiles(rows, cols)
        wanted = store.step_for(view.screen_m)
        keys = [(wanted, *tile) for tile in tiles]
        store.want(keys, also=aside)
        pending = store.wait(keys, wait_s)
        if pending == 0:
            return wanted, 0
        for m in store.steps:  # a coarser ground read for an earlier view, finest first
            if m > wanted and store.missing([(m, *tile) for tile in tiles]) == 0:
                return m, pending
        return None, pending

    def _window(self, m: int, rows, cols) -> WindowPixels:
        key = (m, rows, cols)
        window = self.windows.pop(key, None)
        if window is None:
            window = WindowPixels(self.xp, self.source.tables, self.store, m, rows, cols, self.rule)
        self.windows[key] = window
        while len(self.windows) > WINDOWS_HELD:
            self.windows.pop(next(iter(self.windows)))
        return window

    def point(self, t_s: float | None, x: float, y: float) -> dict:
        """Depth, speed and class under a point at the finest the run can be drawn, with the frame they belong to."""
        source = self.source
        size = self.store.pixel if self.store is not None else source.dx
        half = min(size, source.dx / self.slider.cell_pixels) / 2.0  # one screen pixel, small enough to be drawn at the pixel
        view = View.of((x - half, y - half, x + half, y + half), 1, 1)
        found = {}
        for field in FIELDS:
            drawn = self.draw(t_s, view, field, None, aside=True)
            value = float(drawn.values[0, 0])
            found[field] = None if np.isnan(value) else round(value, 4)
        return {**found, "frame": drawn.frame, "t_s": drawn.t_s, "detail": drawn.detail, "pixel_m": drawn.pixel_m}
