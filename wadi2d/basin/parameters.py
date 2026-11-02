"""What the terrain and the job's rasters say about an element.

Interface: :func:`nrcs_lag_minutes`, :func:`hms_kirpich_lag_minutes`, :func:`index_celerity`, :func:`land_slope`,
:func:`zonal_mean`, :func:`read_on_surface`.
Pure functions; which of them an element gets, and from what source, is decided in :mod:`wadi2d.basin.elements`.
"""

from __future__ import annotations

import math

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds

from wadi2d.basin.delineate import Surface
from wadi2d.basin.kernels import NONE
from wadi2d.hydrology.constants import PERCENT
from wadi2d.hydrology.losses import CN_NUMERATOR, CN_OFFSET
from wadi2d.hydrology.routing_kernel import MANNING_EXPONENT, WIDE_CHANNEL_POWER

FEET_PER_METRE = 1.0 / 0.3048
NRCS_LENGTH_POWER = 0.8
NRCS_RETENTION_POWER = 0.7
NRCS_DIVISOR = 1900.0
"""NEH 630 chapter 15, the watershed lag method: L = l^0.8 (S + 1)^0.7 / (1900 Y^0.5), hours, l in ft, S in inches, Y in %."""
MINUTES_PER_HOUR = 60.0
KIRPICH_COEFFICIENT, KIRPICH_LENGTH_POWER, KIRPICH_SLOPE_POWER = 0.0195, 0.77, -0.385
"""Kirpich (1940): tc = 0.0195 L^0.77 S^-0.385, minutes, L in m, S in m/m (0.0078 with L in ft)."""
HMS_LAG_RATIO = 0.474
"""Lag over Kirpich's tc on the longest path and the 10-85 slope: what all 18 lags of the Block 2 HEC-HMS model are, to
0.3 % (`W24 basin model`). The textbook ratio is 0.6; where 0.474 comes from is not in the files. A finding, not a law."""


def kirpich_minutes(flow_length_m: float, slope_10_85: float) -> float:
    """Kirpich's time of concentration on the longest path and its 10-85 slope."""
    return KIRPICH_COEFFICIENT * flow_length_m**KIRPICH_LENGTH_POWER * slope_10_85**KIRPICH_SLOPE_POWER


def hms_kirpich_lag_minutes(flow_length_m: float, slope_10_85: float) -> float:
    """The lag rule under the Block 2 HMS model: ``HMS_LAG_RATIO`` times Kirpich."""
    return HMS_LAG_RATIO * kirpich_minutes(flow_length_m, slope_10_85)


def nrcs_lag_minutes(flow_length_m: float, curve_number: float, slope: float) -> float:
    """The NRCS watershed lag; ``slope`` is the mean land slope of the subbasin, m/m."""
    retention_inches = CN_NUMERATOR / curve_number - CN_OFFSET
    length_ft = flow_length_m * FEET_PER_METRE
    hours = (
        length_ft**NRCS_LENGTH_POWER
        * (retention_inches + 1.0) ** NRCS_RETENTION_POWER
        / (NRCS_DIVISOR * math.sqrt(slope * PERCENT))
    )
    return hours * MINUTES_PER_HOUR


def index_celerity(
    manning_n: float, slope: float, bottom_width_m: float, side_slope: float, depth_m: float
) -> float:
    """Kinematic celerity on the trapezoid at ``depth_m``, m/s: 5/3 of the Manning velocity."""
    area = (bottom_width_m + side_slope * depth_m) * depth_m
    perimeter = bottom_width_m + 2.0 * depth_m * math.sqrt(1.0 + side_slope * side_slope)
    velocity = (area / perimeter) ** MANNING_EXPONENT * math.sqrt(slope) / manning_n
    return WIDE_CHANNEL_POWER * velocity


def land_slope(z: np.ndarray, pixel: float) -> np.ndarray:
    """Slope of the ground at each pixel, m/m, by central differences; NaN beside the edge of the ground."""
    rows, cols = np.gradient(z, pixel)
    return np.hypot(rows, cols).ravel()


def zonal_mean(values: np.ndarray, label: np.ndarray, labels: int) -> tuple[np.ndarray, np.ndarray]:
    """Mean of finite ``values`` per label, and the share of each label they cover."""
    held = label != NONE
    names = label[held]
    numbers = values[held]
    finite = np.isfinite(numbers)
    pixels = np.bincount(names, minlength=labels)
    covered = np.bincount(names[finite], minlength=labels)
    totals = np.bincount(names[finite], weights=numbers[finite], minlength=labels)
    with np.errstate(invalid="ignore", divide="ignore"):
        return totals / covered, covered / pixels


def read_on_surface(path: str, surface: Surface) -> np.ndarray:
    """A raster averaged onto the analysis pixels, flat; NaN where it has no data."""
    ny, nx = surface.shape
    with rasterio.open(path) as src:
        same = src.crs is None or not surface.crs or src.crs == CRS.from_wkt(surface.crs)
        if same:
            bounds = (
                surface.x0,
                surface.y0 - ny * surface.pixel,
                surface.x0 + nx * surface.pixel,
                surface.y0,
            )
            band = src.read(
                1,
                window=from_bounds(*bounds, src.transform),
                out_shape=(ny, nx),
                boundless=True,
                masked=True,
                resampling=Resampling.average,
            )
        else:
            with WarpedVRT(
                src,
                crs=surface.crs,
                transform=surface.transform,
                width=nx,
                height=ny,
                resampling=Resampling.average,
            ) as warped:
                band = warped.read(1, masked=True)
    return np.asarray(band.astype(np.float64).filled(np.nan)).ravel()
