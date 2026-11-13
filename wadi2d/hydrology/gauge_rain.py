"""Gauge rain on the 2D cells. Interface: :class:`GaugeCellRain`.

Each cell takes the gauge weights of its centre and its own curve number; it answers the same two questions the gridded
rain does (:class:`~wadi2d.hydrology.cell_rain.CellRain`), so the forcing treats them alike. Under Thiessen a cell has
one gauge, and cells sharing a gauge and a curve number share one excess: a refresh computes a few pairs. Under inverse
distance every cell has its own weights, so the excess is per cell, as it is under a depth grid; the last two answers
are kept, because a refresh asks for the end of the window it asked for a moment before.
"""

from __future__ import annotations

import numpy as np

from wadi2d.config.gauges import THIESSEN
from wadi2d.hydrology.cell_rain import NO_LOSS_KEY
from wadi2d.hydrology.losses import ScsCurveNumber
from wadi2d.storm.base import FloatArray
from wadi2d.storm.gauge_weights import nearest
from wadi2d.storm.gauges import GaugeStorm

KEPT = 2


class GaugeCellRain:
    """``pair_of`` gives each cell its row of :meth:`excess_mm`; ``x`` and ``y`` are in the gauges' system."""

    def __init__(self, storm: GaugeStorm, x: np.ndarray, y: np.ndarray, cn: np.ndarray, rained: np.ndarray) -> None:
        self.storm = storm
        self.beyond = 0
        """Rained cells with no gauge within the search radius, which took their nearest gauge."""
        if storm.method == THIESSEN:
            self.gauge_of = nearest(x, y, storm.xy)
            values, cn_class = np.unique(np.where(np.isfinite(cn), cn, NO_LOSS_KEY), return_inverse=True)
            keys = self.gauge_of * values.size + cn_class.ravel()
            _pairs, first, self.pair_of = np.unique(keys, return_index=True, return_inverse=True)
            self.column = self.gauge_of[first]
            self.weights = None
            pair_cn = cn[first]
        else:
            self.gauge_of = None
            wet, self.beyond = storm.weights_at(x[rained], y[rained])  # a cell with no rain needs no weights
            self.weights = np.zeros((x.size, len(storm.names)), wet.dtype)
            self.weights[rained] = wet
            self.pair_of = np.arange(x.size)
            pair_cn = cn
        self.has_loss = np.isfinite(pair_cn)
        self.loss = ScsCurveNumber(curve_number=pair_cn[self.has_loss])
        self._kept: dict[float, FloatArray] = {}

    def rain_mm(self, minutes: float) -> FloatArray:
        """Cumulative rain per pair, before losses."""
        depths = self.storm.depths_at(minutes)
        if self.weights is None:
            return depths[self.column].astype(np.float64)
        return np.asarray(self.weights @ depths, np.float64)

    def excess_mm(self, minutes: float) -> FloatArray:
        """Cumulative excess per pair; rain passes whole where there is no curve number."""
        if minutes in self._kept:
            return self._kept[minutes]
        rain = self.rain_mm(minutes)
        with np.errstate(divide="ignore", invalid="ignore"):
            rain[self.has_loss] = np.nan_to_num(self.loss.cumulative_excess(rain[self.has_loss]))
        if len(self._kept) >= KEPT:
            self._kept.pop(next(iter(self._kept)))
        self._kept[minutes] = rain
        return rain

    def notes(self) -> list[str]:
        if not self.beyond:
            return []
        return [f"{self.beyond} rained cells have no gauge within {self.storm.search_radius_m:g} m and took their nearest gauge"]

    def cell_shares(self, rained: np.ndarray, areas: np.ndarray | float) -> dict[str, float]:
        """The share of the rained area each gauge carries, for the run's record: under Thiessen, its polygon's share."""
        area = np.broadcast_to(np.asarray(areas, np.float64), rained.shape) * rained
        whole = float(area.sum())
        if whole <= 0.0:
            return {}
        if self.weights is None:
            carried = np.bincount(self.gauge_of, weights=area, minlength=len(self.storm.names))
        else:
            carried = np.asarray(self.weights, np.float64).T @ area
        return {name: round(float(c / whole), 4) for name, c in zip(self.storm.names, carried, strict=True) if c > 0.0}
