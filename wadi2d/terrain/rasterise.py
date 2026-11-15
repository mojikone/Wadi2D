"""GDAL's rasterise, one call at a time (W85).

The pixel edits of burn lines and shaped objects rasterise a strip into the window they are asked through, and since
W81 the tables are built on threads, so those calls ran several at once. rasterio then warned, on about a third of
the calls from 16 threads, that its in-memory dataset "has no geotransform". 4,000 such calls gave the masks of the
same calls on one thread, pixel for pixel, so no table is known to be wrong; a call that warns it has lost its
transform is still not one to build tables on. One lock makes the calls take turns: the mask is the same call's, and a
rasterise of a tile window is milliseconds beside the tile's tables.
"""

from __future__ import annotations

import threading

import numpy as np
from rasterio import features

LOCK = threading.Lock()
"""Held for the length of one rasterise, by every caller that may run on a table thread."""


def rasterize(shapes, out_shape, transform, **options) -> np.ndarray:
    """``rasterio.features.rasterize`` with the same arguments, never two at once."""
    with LOCK:
        return features.rasterize(shapes, out_shape=out_shape, transform=transform, **options)
