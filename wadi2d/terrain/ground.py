"""Ground under scattered points: a crest line or a long profile, read without loading the raster they cross.

Points are grouped into blocks of pixels and each block is one window read, so a 20 km line on a 0.5 m DEM costs what
it touches. The values are the raw DEM: an object's checks and crest lines look at the ground it was drawn on.
"""

from __future__ import annotations

import numpy as np

from wadi2d.tables.builder import BedSource

BLOCK_PIXELS = 512


class Ground:
    """Elevations at (x, y) from a bed bound to the origin (x0, y0)."""

    def __init__(self, bed: BedSource, x0: float, y0: float) -> None:
        self.bed = bed
        self.x0 = x0
        self.y0 = y0

    def __call__(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
        pixel = self.bed.pixel
        rows = np.floor((self.y0 - y) / pixel).astype(np.int64)
        cols = np.floor((x - self.x0) / pixel).astype(np.int64)
        out = np.empty(x.shape)
        keys = np.column_stack((rows // BLOCK_PIXELS, cols // BLOCK_PIXELS))
        blocks, members = np.unique(keys, axis=0, return_inverse=True)
        for index, (br, bc) in enumerate(blocks):
            on = members.ravel() == index
            r0, c0 = int(br) * BLOCK_PIXELS, int(bc) * BLOCK_PIXELS
            window = self.bed.read(r0, c0, BLOCK_PIXELS, BLOCK_PIXELS)
            out[on] = window[rows[on] - r0, cols[on] - c0]
        return out
