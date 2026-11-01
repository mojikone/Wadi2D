"""Rainfall-to-runoff transforms. Interface: :class:`TransformMethod`, :data:`TRANSFORM_METHODS`.

A transform gives a unit hydrograph for its control step; :func:`convolve` applies it. ``ordinates[i]`` is the
flow per mm of excess ``i`` steps after the end of the excess period, in m3/s. Both methods renormalise the
discrete ordinates to one mm over the area, which is what the ``Unit hydrograph volume ... is 1.0000 mm`` note
of the HMS log reports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from scipy.interpolate import CubicSpline

from wadi2d.hydrology.constants import M3_PER_MM_KM2, SECONDS_PER_MINUTE
from wadi2d.storm.base import FloatArray
from wadi2d.storm.registry import Registry

SCS_UH = "SCS"
CLARK_UH = "Clark"

# NEH 630 chapter 16, table 16-1: t/Tp against q/qp, peak rate factor 484.
SCS_T_RATIO = np.array(
    [
        0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9,
        2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.2, 3.4, 3.6, 3.8, 4.0, 4.5, 5.0,
    ]
)  # fmt: skip
SCS_Q_RATIO = np.array(
    [
        0.000, 0.030, 0.100, 0.190, 0.310, 0.470, 0.660, 0.820, 0.930, 0.990, 1.000, 0.990, 0.930, 0.860,
        0.780, 0.680, 0.560, 0.460, 0.390, 0.330, 0.280, 0.207, 0.147, 0.107, 0.077, 0.055, 0.040, 0.029,
        0.021, 0.015, 0.011, 0.005, 0.000,
    ]
)  # fmt: skip
SCS_SPLINE_BOUNDARY = "natural"
CLARK_TIME_AREA_COEFFICIENT = 1.414
CLARK_TIME_AREA_EXPONENT = 1.5
CLARK_VOLUME_FRACTION = 0.995
MAX_CLARK_ORDINATES = 100_000


class TransformMethod(Protocol):
    """A transform of one subbasin."""

    def unit_hydrograph(self, area_km2: float, dt_minutes: float) -> FloatArray:
        """Flow per mm of excess at the steps after the excess period, m3/s; sums to one mm over the area."""
        ...


TRANSFORM_METHODS: Registry[TransformMethod] = Registry("transform")


def _unit_volume(ordinates: FloatArray, area_km2: float, dt_minutes: float) -> FloatArray:
    """Scale the ordinates so that they carry exactly one mm over the area."""
    volume = ordinates.sum() * dt_minutes * SECONDS_PER_MINUTE
    return ordinates * (area_km2 * M3_PER_MM_KM2 / volume)


@TRANSFORM_METHODS.register(SCS_UH)
@dataclass(frozen=True)
class ScsUnitHydrograph:
    """SCS standard unit hydrograph; the peak falls at ``Tp = dt / 2 + lag``."""

    lag_minutes: float

    def unit_hydrograph(self, area_km2: float, dt_minutes: float) -> FloatArray:
        """Table 16-1 sampled at the end of each step, then renormalised.

        HMS reads the table through a natural cubic spline, not linearly: deconvolving its flows from its
        excess on all 18 Block 2 subbasins gives these ordinates to 2e-14 of the peak. Linear interpolation
        misses its peaks by 0.3 %.
        """
        time_to_peak = dt_minutes / 2.0 + self.lag_minutes
        count = math.ceil(SCS_T_RATIO[-1] * time_to_peak / dt_minutes)
        ratios = dt_minutes * np.arange(1, count + 1, dtype=np.float64) / time_to_peak
        shape = CubicSpline(SCS_T_RATIO, SCS_Q_RATIO, bc_type=SCS_SPLINE_BOUNDARY)
        return _unit_volume(np.where(ratios < SCS_T_RATIO[-1], shape(ratios), 0.0), area_km2, dt_minutes)


def _clark_time_area(fraction: FloatArray) -> FloatArray:
    """The default HMS time-area curve."""
    tau = np.clip(fraction, 0.0, 1.0)
    return np.where(
        tau <= 0.5,
        CLARK_TIME_AREA_COEFFICIENT * tau**CLARK_TIME_AREA_EXPONENT,
        1.0 - CLARK_TIME_AREA_COEFFICIENT * (1.0 - tau) ** CLARK_TIME_AREA_EXPONENT,
    )


@TRANSFORM_METHODS.register(CLARK_UH)
@dataclass(frozen=True)
class ClarkUnitHydrograph:
    """Clark unit hydrograph with the default time-area curve; both parameters in minutes."""

    time_of_concentration_minutes: float
    storage_coefficient_minutes: float

    def unit_hydrograph(self, area_km2: float, dt_minutes: float) -> FloatArray:
        """A translation hydrograph through a linear reservoir, truncated at 99.5 % and renormalised."""
        storage = self.storage_coefficient_minutes
        if dt_minutes >= 2.0 * storage:
            raise ValueError(f"Clark needs dt < 2 R: dt {dt_minutes} min, R {storage} min")
        ca = dt_minutes / (storage + 0.5 * dt_minutes)
        count = MAX_CLARK_ORDINATES
        times = dt_minutes * np.arange(count + 1, dtype=np.float64)
        translation = np.diff(_clark_time_area(times / self.time_of_concentration_minutes))
        ordinates: list[float] = []
        outflow = 0.0
        carried = 0.0
        for step in range(count):
            previous, outflow = outflow, ca * float(translation[step]) + (1.0 - ca) * outflow
            ordinates.append(0.5 * (previous + outflow))
            carried += ordinates[-1]
            if carried >= CLARK_VOLUME_FRACTION:
                break
        return _unit_volume(np.array(ordinates), area_km2, dt_minutes)


def convolve(excess_mm: FloatArray, ordinates: FloatArray, n_times: int) -> FloatArray:
    """Direct runoff at ``n_times`` times from period-ending excess; the first time is the run start."""
    flow = np.zeros(n_times, dtype=np.float64)
    runoff = np.convolve(excess_mm, ordinates)[: n_times - 1]
    flow[1 : 1 + len(runoff)] = runoff
    return flow
