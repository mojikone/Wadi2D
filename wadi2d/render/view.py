"""One drawing asked for: an extent on the map and a size in screen pixels, and where its pixels fall on a raster."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class View:
    """North up, in the CRS of the run. ``width`` and ``height`` are screen pixels."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float
    width: int
    height: int

    @classmethod
    def of(cls, extent, width: int, height: int) -> View:
        xmin, ymin, xmax, ymax = (float(v) for v in extent)
        if not (xmax > xmin and ymax > ymin) or width < 1 or height < 1:
            raise ValueError("a drawing needs an extent with a size, and at least one pixel each way")
        return cls(xmin, ymin, xmax, ymax, int(width), int(height))

    @property
    def screen_m(self) -> float:
        """Metres a screen pixel covers; the coarser of the two ways when they differ."""
        return max((self.xmax - self.xmin) / self.width, (self.ymax - self.ymin) / self.height)

    def cells(self, x0: float, y0: float, dx: float, shape: tuple[int, int], margin: int = 0) -> tuple[tuple[int, int], tuple[int, int]]:
        """Rows [a, b) and columns [a, b) of the cells under the view, ``margin`` cells wider, inside the grid."""
        ny, nx = shape
        rows = (int(np.floor((y0 - self.ymax) / dx)) - margin, int(np.ceil((y0 - self.ymin) / dx)) + margin)
        cols = (int(np.floor((self.xmin - x0) / dx)) - margin, int(np.ceil((self.xmax - x0) / dx)) + margin)
        return (max(rows[0], 0), min(rows[1], ny)), (max(cols[0], 0), min(cols[1], nx))

    def samples(self, x0: float, y0: float, pixel: float) -> tuple[np.ndarray, np.ndarray]:
        """Row and column, on a raster of this pixel from (x0, y0), under the centre of every screen row and column."""
        xs = self.xmin + (np.arange(self.width) + 0.5) * ((self.xmax - self.xmin) / self.width)
        ys = self.ymax - (np.arange(self.height) + 0.5) * ((self.ymax - self.ymin) / self.height)
        return np.floor((y0 - ys) / pixel).astype(np.int64), np.floor((xs - x0) / pixel).astype(np.int64)
