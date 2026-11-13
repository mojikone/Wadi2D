"""Rain from gauges, spread over space by one method. Interface: :class:`GaugeStorm`, :func:`fill_gaps`.

Every gauge's rain stands on the same stretches of time (``edges``), so the rain of any place is its gauge weights
times the gauges' depths: a 2D cell takes the weights of its centre (:mod:`wadi2d.hydrology.gauge_rain`), a lumped
subbasin the mean of the weights over its polygon. Rain is linear in the gauges, so the mean of the weights gives the
mean of the rain, and a subbasin run lumped takes what its cells would take as rain-on-grid: exactly under Thiessen,
where the mean is the polygon's exact area shares, and to the sampling of ``samples`` points under inverse distance.
A subbasin with gauge weights in the job takes those instead, as HEC-HMS's Gage Weights. Observed rain has no area
reduction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self

import numpy as np
import shapely
from numpy.typing import ArrayLike

from wadi2d.config.gauges import GAPS_ERROR, GAPS_NEIGHBOURS, INVERSE_DISTANCE, THIESSEN
from wadi2d.storm.base import STORM_METHODS, CumulativeStorm, FloatArray, Storm
from wadi2d.storm.gauge_weights import inverse_distance, nearest, polygon_points, thiessen_shares
from wadi2d.storm.gridded import move_points
from wadi2d.storm.hyetograph import HyetographStorm

GAUGE_STORM = "Gauges"
SHARE_DIGITS = 4


def _moved_polygon(polygon: Any, source: str, target: str) -> Any:
    def move(points: np.ndarray) -> np.ndarray:
        return np.column_stack(move_points(points[:, 0], points[:, 1], source, target))

    return shapely.make_valid(shapely.transform(polygon, move))


def place_weights(
    x: np.ndarray, y: np.ndarray, gauges: np.ndarray, method: str, power: float, radius: float | None, quadrants: bool
) -> tuple[np.ndarray, int]:
    """(weights, places beyond the radius): gauge weights of each place under either method."""
    if method == THIESSEN:
        index = nearest(x, y, gauges)
        weights = np.zeros((index.size, gauges.shape[0]))
        weights[np.arange(index.size), index] = 1.0
        return weights, 0
    return inverse_distance(x, y, gauges, power, radius, quadrants)


def fill_gaps(depths: np.ndarray, gauges: np.ndarray, rule: str, weigh) -> np.ndarray:
    """``depths`` is (stretches, gauges) with NaN where a gauge has no value; returns it whole.

    ``zero`` counts no rain in a gap. ``neighbours`` gives the gauge what ``weigh(x, y, gauges with data)`` reads at its
    own position from the gauges that have a value in that stretch; a stretch no gauge covers stays without rain.
    """
    missing = np.isnan(depths)
    if rule != GAPS_NEIGHBOURS:
        return np.where(missing, 0.0, depths)
    out = np.where(missing, 0.0, depths)
    for pattern in np.unique(missing, axis=0):
        have = np.nonzero(~pattern)[0]
        if not pattern.any() or have.size == 0:
            continue
        rows = np.all(missing == pattern, axis=1)
        for g in np.nonzero(pattern)[0]:
            weights = weigh(gauges[g : g + 1, 0], gauges[g : g + 1, 1], gauges[have])[0]
            out[np.ix_(rows, [g])] = (depths[np.ix_(rows, have)] @ weights.T).reshape(-1, 1)
    return out


@STORM_METHODS.register(GAUGE_STORM)
@dataclass(eq=False)
class GaugeStorm(CumulativeStorm):
    """``cumulative`` is (edges, gauges): the depth each gauge has had by each edge, mm; ``xy`` their positions, m."""

    names: tuple[str, ...]
    xy: np.ndarray
    edges: FloatArray
    cumulative: np.ndarray
    method: str = THIESSEN
    power: float = 2.0
    search_radius_m: float | None = None
    quadrants: bool = True
    samples: int = 2000
    gauge_weights: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    origin: np.datetime64 | None = None
    """The date of minute zero; None for records that count from the start of the run."""
    filled: tuple[str, ...] = ()
    """What the gap rule did, in words, for the run's notes."""
    crs: str = ""
    """The system of ``xy``: the DEM's."""
    polygons: Mapping[str, Any] = field(default_factory=dict)
    polygon_crs: str = ""
    _storms: dict[str, HyetographStorm] = field(default_factory=dict, init=False, repr=False)
    _shares: dict[str, FloatArray] = field(default_factory=dict, init=False, repr=False)
    _beyond: list[str] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        count = len(self.names)
        if count == 0:
            raise ValueError("a gauges storm needs one rain gauge at least")
        if self.xy.shape != (count, 2) or self.cumulative.shape != (self.edges.size, count):
            raise ValueError("a gauges storm needs one position and one cumulative curve per gauge")
        if self.method not in (THIESSEN, INVERSE_DISTANCE):
            raise ValueError(f"unknown gauge method {self.method!r}")

    @property
    def totals(self) -> FloatArray:
        """The depth of the whole record at each gauge, mm."""
        return self.cumulative[-1]

    @property
    def total_depth(self) -> float:
        """The plain mean of the gauges' totals, mm; a report's number, no place takes it."""
        return float(self.totals.mean())

    def depths_at(self, minutes: float) -> FloatArray:
        """Depth fallen at each gauge by this time, mm: linear inside a stretch, level before the first and after the last."""
        edges = self.edges
        if minutes <= edges[0]:
            return self.cumulative[0]
        if minutes >= edges[-1]:
            return self.cumulative[-1]
        k = int(np.searchsorted(edges, minutes, side="right")) - 1
        share = (minutes - edges[k]) / (edges[k + 1] - edges[k])
        return self.cumulative[k] + (self.cumulative[k + 1] - self.cumulative[k]) * share

    def cumulative_depth(self, minutes: ArrayLike) -> FloatArray:
        """The plain mean of the gauges, for reports; cells and subbasins read their own weights."""
        return np.array([self.depths_at(float(m)).mean() for m in np.atleast_1d(minutes)])

    def weights_at(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, int]:
        """(weights, places beyond the search radius) at points in the gauges' own system."""
        return place_weights(x, y, self.xy, self.method, self.power, self.search_radius_m, self.quadrants)

    def bind(self, polygons: Mapping[str, Any], polygon_crs: str, crs: str) -> Self:
        """Make this rain able to answer for these subbasins; ``crs`` is the system the gauges stand in."""
        self.polygons, self.polygon_crs, self.crs = polygons, polygon_crs, crs
        self._storms.clear()
        self._shares.clear()
        self._beyond.clear()
        return self

    def shares_of(self, subbasin: str) -> FloatArray:
        """The gauge weights of one subbasin: the job's, else the mean of the spatial method over its polygon."""
        if subbasin in self._shares:
            return self._shares[subbasin]
        given = self.gauge_weights.get(subbasin)
        if given is not None:
            unknown = sorted(set(given) - set(self.names))
            if unknown:
                raise ValueError(f"gauge weights of subbasin {subbasin} name unknown gauges: {unknown}")
            shares = np.array([float(given.get(name, 0.0)) for name in self.names])
            shares = shares / shares.sum()
        else:
            if subbasin not in self.polygons:
                raise KeyError(f"no polygon for subbasin {subbasin}: gauge rain needs one, or gauge weights in the job")
            polygon = _moved_polygon(self.polygons[subbasin], self.polygon_crs, self.crs)
            if self.method == THIESSEN:
                shares = thiessen_shares(polygon, self.xy)
            else:
                weights, beyond = self.weights_at(*polygon_points(polygon, self.samples))
                shares = np.asarray(weights, np.float64).mean(axis=0)
                if beyond:
                    self._beyond.append(subbasin)
        self._shares[subbasin] = shares
        return shares

    def over(self, subbasin: str) -> Storm:
        """The areal mean rain over one subbasin, as a hyetograph."""
        if subbasin not in self._storms:
            self._storms[subbasin] = HyetographStorm(self.edges, self.cumulative @ self.shares_of(subbasin))
        return self._storms[subbasin]

    def subbasin_shares(self) -> dict[str, dict[str, float]]:
        """The gauge weights of every subbasin asked for so far, for the run's record."""
        return {
            name: {g: round(float(w), SHARE_DIGITS) for g, w in zip(self.names, shares, strict=True) if w > 0.0}
            for name, shares in sorted(self._shares.items())
        }

    def notes(self, duration_min: float) -> list[str]:
        """What a run should say about this rain; read it after the lumped network has run."""
        found = list(self.filled)
        if self.edges[-1] > duration_min:
            found.append(f"the gauges' rain runs to {self.edges[-1]:g} min and the run stops at {duration_min:g} min")
        if self._beyond:
            found.append(
                "no gauge within the search radius of part of these subbasins, which took their nearest gauge there: "
                + ", ".join(sorted(self._beyond))
            )
        return found

    def at_area(self, area_km2: float) -> Self:
        """Observed rain has no area reduction: the same rain."""
        return self


__all__ = ["GAPS_ERROR", "GAUGE_STORM", "GaugeStorm", "fill_gaps", "place_weights"]
