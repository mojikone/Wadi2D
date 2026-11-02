"""A reach's channel from cross-sections on the ground (decision 8).

Sections are cut square to the stream every ``section_spacing_m``. Each gives a width curve: from the lowest ground near the
stream, the unbroken width below each depth. The median curve over the reach stands for the channel, and a straight line
through it is the trapezoid the Muskingum-Cunge reach takes. A curve that fills the section's whole length means open ground,
not a channel, and is flagged.

Interface: :class:`SectionFit`, :func:`fit_section`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from wadi2d.basin.delineate import Surface
from wadi2d.config.schema import BasinSettings

OPEN_SHARE = 0.95
"""A median width this share of the section's length is open ground."""
HIGH_GROUND = 1.0e4
"""Above any ground, m: a section stops where the raster ends."""


@dataclass(frozen=True)
class SectionFit:
    """The trapezoid of a reach and what it was fitted to."""

    bottom_width_m: float
    side_slope: float
    depths_m: tuple[float, ...]
    widths_m: tuple[float, ...]
    stations: int
    open_ground: bool


def _stations(x: np.ndarray, y: np.ndarray, along: np.ndarray, spacing: float) -> tuple[np.ndarray, ...]:
    """Centre and unit normal of each section. The stream's direction is taken over one spacing, not one pixel."""
    length = along[-1]
    stations = np.arange(0.5 * spacing, length, spacing)
    if stations.size == 0:
        stations = np.array([0.5 * length])
    half = 0.5 * spacing
    dx = np.interp(stations + half, along, x) - np.interp(stations - half, along, x)
    dy = np.interp(stations + half, along, y) - np.interp(stations - half, along, y)
    norm = np.hypot(dx, dy)
    return np.interp(stations, along, x), np.interp(stations, along, y), -dy / norm, dx / norm


def _width_curve(profile: np.ndarray, depths: np.ndarray, pixel: float, search: int) -> np.ndarray:
    """Unbroken width below each depth above the lowest ground within ``search`` samples of the centre."""
    centre = profile.size // 2
    low = max(centre - search, 0)
    bed_index = low + int(np.argmin(profile[low : centre + search + 1]))
    bed = profile[bed_index]
    widths = np.empty(depths.size)
    for index, depth in enumerate(depths):
        above = np.flatnonzero(profile > bed + depth)
        left = above[above < bed_index]
        right = above[above > bed_index]
        first = left[-1] + 1 if left.size else 0
        last = right[0] - 1 if right.size else profile.size - 1
        widths[index] = (last - first + 1) * pixel
    return widths


def _trapezoid(depths: np.ndarray, widths: np.ndarray, pixel: float) -> tuple[float, float]:
    """Bottom width and side slope of the line W = b + 2 z h; a bed under one pixel wide is one pixel wide."""
    rise, bottom = np.polyfit(depths, widths, 1)
    if rise <= 0.0:
        return max(float(np.mean(widths)), pixel), 0.0
    if bottom >= pixel:
        return float(bottom), float(0.5 * rise)
    return pixel, float(0.5 * np.dot(widths - pixel, depths) / np.dot(depths, depths))


def fit_section(
    ground: np.ndarray,
    surface: Surface,
    x: np.ndarray,
    y: np.ndarray,
    along: np.ndarray,
    settings: BasinSettings,
) -> SectionFit:
    """The channel of the reach whose stream runs through (x, y), with ``along`` the distance at each.

    ``ground`` is :attr:`Surface.z` with its NaNs replaced by :data:`HIGH_GROUND`.
    """
    pixel = surface.pixel
    cx, cy, nx, ny = _stations(x, y, along, settings.section_spacing_m)
    reach = round(settings.section_half_width_m / pixel)
    offsets = np.arange(-reach, reach + 1) * pixel
    xs = cx[:, None] + nx[:, None] * offsets
    ys = cy[:, None] + ny[:, None] * offsets
    rows = (surface.y0 - ys) / pixel - 0.5
    cols = (xs - surface.x0) / pixel - 0.5
    profiles = ndimage.map_coordinates(ground, [rows, cols], order=1, mode="constant", cval=HIGH_GROUND)
    depths = np.linspace(0.0, settings.section_depth_m, settings.section_depths)[1:]
    search = round(settings.section_search_m / pixel)
    curves = np.array([_width_curve(profile, depths, pixel, search) for profile in profiles])
    median = np.median(curves, axis=0)
    bottom, side = _trapezoid(depths, median, pixel)
    return SectionFit(
        bottom,
        side,
        tuple(round(float(d), 3) for d in depths),
        tuple(round(float(w), 2) for w in median),
        len(profiles),
        bool(median[-1] >= OPEN_SHARE * offsets.size * pixel),
    )
