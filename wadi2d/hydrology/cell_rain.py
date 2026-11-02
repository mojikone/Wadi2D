"""Gridded rain on the 2D cells. Interface: :func:`rain_pixels`, :class:`CellRain`.

Each cell takes the pixel its centre falls in, and its own curve number. Cells sharing a pixel and a curve number have
the same excess, so a refresh computes each pair once: a rain grid has thousands of pixels where the domain has millions
of cells, and refreshing per cell would cost more than the rain is worth.
"""

from __future__ import annotations

import numpy as np

from wadi2d.hydrology.losses import ScsCurveNumber
from wadi2d.storm.base import FloatArray
from wadi2d.storm.gridded import GriddedStorm, move_points
from wadi2d.storm.rain_frames import PixelSeries

NO_LOSS_KEY = -1.0


def rain_pixels(storm: GriddedStorm, x: np.ndarray, y: np.ndarray, crs: str) -> np.ndarray:
    """The rain pixel of each point as a raster value: NaN off the grid and on a pixel that never had data."""
    frames = storm.frames
    pixel = frames.pixel_of(*move_points(x, y, crs, frames.crs))
    known = pixel >= 0
    known[known] = np.isfinite(frames.totals().ravel()[pixel[known]])
    return np.where(known, pixel.astype(np.float64), np.nan)


class CellRain:
    """``pair_of`` gives each cell its pair; :meth:`excess_mm` gives cumulative excess per pair."""

    def __init__(self, storm: GriddedStorm, pixels: np.ndarray, cn: np.ndarray, rained: np.ndarray) -> None:
        frames = storm.frames
        known = np.isfinite(pixels)
        holes = int(np.count_nonzero(rained & ~known))
        if holes:
            raise ValueError(
                f"the rain grid gives nothing on {holes} rained cells of {rained.size}: it does not cover the domain"
            )
        filler = pixels[known][0] if known.any() else float(np.nanargmax(frames.totals()))
        pixel = np.where(known, pixels, filler).astype(np.int64)  # a masked cell's value is never used
        values, cn_class = np.unique(np.where(np.isfinite(cn), cn, NO_LOSS_KEY), return_inverse=True)
        keys = pixel * values.size + cn_class.ravel()
        _pairs, first, self.pair_of = np.unique(keys, return_index=True, return_inverse=True)
        used, self.column = np.unique(pixel[first], return_inverse=True)
        self.series = PixelSeries(frames, used)
        pair_cn = cn[first]
        self.has_loss = np.isfinite(pair_cn)
        self.loss = ScsCurveNumber(curve_number=pair_cn[self.has_loss])

    def excess_mm(self, minutes: float) -> FloatArray:
        """Cumulative excess per pair; rain passes whole where there is no curve number."""
        rain = self.series.at(minutes)[self.column]
        with np.errstate(divide="ignore", invalid="ignore"):
            rain[self.has_loss] = np.nan_to_num(self.loss.cumulative_excess(rain[self.has_loss]))
        return rain
