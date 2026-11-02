"""Rain that varies by cell and by time. Interface: :class:`GriddedStorm`, :func:`move_points`.

A 2D cell takes the pixel its centre falls in. A lumped subbasin takes the mean of the pixels under its polygon, each
weighted by the area it shares with the polygon, so a subbasin smaller than a pixel still has rain; a satellite pixel is
about 10 km wide. Observed rain has no area reduction: it already is what fell over the area.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self

import numpy as np
import pyproj
import shapely
from numpy.typing import ArrayLike

from wadi2d.storm.base import CumulativeStorm, FloatArray, Storm
from wadi2d.storm.hyetograph import HyetographStorm
from wadi2d.storm.rain_frames import PixelSeries, RainFrames

MIN_COVERED = 0.95
"""A polygon with less than this share on the rain grid gets a warning: its mean is of the part that has rain."""


def _same(left: str, right: str) -> bool:
    return not left or not right or pyproj.CRS.from_user_input(left) == pyproj.CRS.from_user_input(right)


def move_points(x: np.ndarray, y: np.ndarray, source: str, target: str) -> tuple[np.ndarray, np.ndarray]:
    """Points from one system to another; an empty system means the two are the same."""
    if _same(source, target):
        return x, y
    moved = pyproj.Transformer.from_crs(source, target, always_xy=True).transform(x, y)
    return np.asarray(moved[0]), np.asarray(moved[1])


def _moved_polygon(polygon: Any, source: str, target: str) -> Any:
    def move(points: np.ndarray) -> np.ndarray:
        return np.column_stack(move_points(points[:, 0], points[:, 1], source, target))

    return shapely.make_valid(shapely.transform(polygon, move))


def pixel_shares(frames: RainFrames, polygon: Any) -> tuple[np.ndarray, np.ndarray, float]:
    """(flat pixels, their areas inside the polygon, the share of the polygon they cover); pixels with data only."""
    left, bottom, right, top = shapely.bounds(polygon)
    first_column = max(int(np.floor((left - frames.west) / frames.dx)), 0)
    last_column = min(int(np.ceil((right - frames.west) / frames.dx)), frames.columns)
    first_row = max(int(np.floor((frames.north - top) / frames.dy)), 0)
    last_row = min(int(np.ceil((frames.north - bottom) / frames.dy)), frames.rows)
    if first_column >= last_column or first_row >= last_row:
        return np.empty(0, np.int64), np.empty(0), 0.0
    rows, columns = np.mgrid[first_row:last_row, first_column:last_column]
    xmin = frames.west + columns.ravel() * frames.dx
    ymax = frames.north - rows.ravel() * frames.dy
    boxes = shapely.box(xmin, ymax - frames.dy, xmin + frames.dx, ymax)
    areas = shapely.area(shapely.intersection(boxes, polygon))
    flat = (rows.ravel() * frames.columns + columns.ravel()).astype(np.int64)
    has_data = np.isfinite(frames.depths.reshape(frames.count, -1)[:, flat]).any(axis=0)
    keep = (areas > 0.0) & has_data
    whole = float(shapely.area(polygon))
    return flat[keep], areas[keep], float(areas[keep].sum()) / whole if whole > 0.0 else 0.0


@dataclass(eq=False)
class GriddedStorm(CumulativeStorm):
    """The frames; bound to the subbasin polygons, it gives each subbasin its own rain."""

    frames: RainFrames
    polygons: Mapping[str, Any] = field(default_factory=dict)
    polygon_crs: str = ""
    _storms: dict[str, HyetographStorm] = field(default_factory=dict, init=False, repr=False)
    _covered: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    def bind(self, polygons: Mapping[str, Any], crs: str) -> Self:
        """Make this rain able to answer for these subbasins."""
        self.polygons, self.polygon_crs = polygons, crs
        self._storms.clear()
        self._covered.clear()
        return self

    @property
    def total_depth(self) -> float:
        """The mean depth over the pixels with data, mm."""
        return float(np.nanmean(self.frames.totals()))

    def cumulative_depth(self, minutes: ArrayLike) -> FloatArray:
        """The mean over the grid, for reports; cells and subbasins read their own pixels."""
        totals = self.frames.totals()
        pixels = np.flatnonzero(np.isfinite(totals))
        series = PixelSeries(self.frames, pixels)
        return np.array([series.at(float(m)).mean() for m in np.atleast_1d(minutes)])

    def over(self, subbasin: str) -> Storm:
        """The area-weighted mean of the pixels under one subbasin."""
        if subbasin in self._storms:
            return self._storms[subbasin]
        if subbasin not in self.polygons:
            raise KeyError(f"no polygon for subbasin {subbasin}: gridded rain needs one to read its pixels")
        polygon = _moved_polygon(self.polygons[subbasin], self.polygon_crs, self.frames.crs)
        pixels, areas, covered = pixel_shares(self.frames, polygon)
        if pixels.size == 0:
            raise ValueError(f"subbasin {subbasin} lies outside the rain grid")
        series = PixelSeries(self.frames, pixels)
        storm = HyetographStorm(series.edges, series.cumulative @ (areas / areas.sum()))
        self._storms[subbasin] = storm
        self._covered[subbasin] = covered
        return storm

    def notes(self, duration_min: float) -> list[str]:
        """What a run should say about this rain; read it after the lumped network has run."""
        frames = self.frames
        found = []
        if not frames.crs:
            found.append("the rain file names no coordinate system, so it is read in the DEM's")
        missing = frames.missing_share()
        if missing > 0.0:
            found.append(f"{missing:.1%} of the rain grid has no data in its frame, and counts as no rain there")
        if frames.looks_cumulative():
            found.append(
                "every rain frame holds at least the one before: if this is rain since the start of a forecast, "
                "each frame counts it again"
            )
        if frames.ends_min[-1] > duration_min:
            found.append(f"the rain runs to {frames.ends_min[-1]:g} min and the run stops at {duration_min:g} min")
        thin = sorted(name for name, covered in self._covered.items() if covered < MIN_COVERED)
        if thin:
            found.append(f"mostly off the rain grid, so the mean is of the part on it: {', '.join(thin)}")
        return found

    def at_area(self, area_km2: float) -> Self:
        """Observed rain has no area reduction: the same rain."""
        return self
