"""Error measures of a modelled field against a reference.

Definitions follow common flood-model benchmarking practice: the wet-cell norms of SWASHES (Delestre et al.
2013, Int. J. Numer. Meth. Fluids 72(3)) and the extent statistic F of Horritt and Bates (2001, J. Hydrology
253). ``l1`` is a mean, not a sum, so it does not depend on the cell count or size.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from wadi2d.validation.grid import FloatArray

type BoolArray = NDArray[np.bool_]


def wet_union(h: FloatArray, h_reference: FloatArray, threshold: float) -> BoolArray:
    """Cells wet in either field, so a false flood and a missed one both count."""
    return (h > threshold) | (h_reference > threshold)


def _masked(value: FloatArray, reference: FloatArray, wet: BoolArray | None) -> FloatArray:
    error = value - reference
    return error if wet is None else error[wet]


def rmse(value: FloatArray, reference: FloatArray, wet: BoolArray | None = None) -> float:
    """Root mean square error over the ``wet`` cells (all cells when None); 0 when there are none."""
    error = _masked(value, reference, wet)
    return float(np.sqrt(np.mean(error * error))) if error.size else 0.0


def l1(value: FloatArray, reference: FloatArray, wet: BoolArray | None = None) -> float:
    """Mean absolute error over the ``wet`` cells (all cells when None); 0 when there are none."""
    error = _masked(value, reference, wet)
    return float(np.mean(np.abs(error))) if error.size else 0.0


def linf(value: FloatArray, reference: FloatArray, wet: BoolArray | None = None) -> float:
    """Largest absolute error over the ``wet`` cells (all cells when None); 0 when there are none."""
    error = _masked(value, reference, wet)
    return float(np.max(np.abs(error))) if error.size else 0.0


def f_statistic(wet: BoolArray, wet_reference: BoolArray) -> float:
    """Inundation-extent fit: intersection over union of the two wet areas; 1 when both are empty."""
    union = int(np.count_nonzero(wet | wet_reference))
    return int(np.count_nonzero(wet & wet_reference)) / union if union else 1.0


def mass_balance_error(
    h: FloatArray, h_reference: FloatArray, cell_area: float, net_inflow_volume: float = 0.0
) -> float:
    """Signed volume error relative to the expected volume, ``h_reference`` plus ``net_inflow_volume``.

    The absolute error in m3 is returned when the expected volume is zero.
    """
    expected = float(np.sum(h_reference)) * cell_area + net_inflow_volume
    excess = float(np.sum(h)) * cell_area - expected
    return excess / abs(expected) if expected else excess


def peak_error(value: FloatArray, reference: FloatArray) -> float:
    """Signed relative error of the maximum of a time series, such as a hydrograph."""
    peak = float(np.max(reference))
    return (float(np.max(value)) - peak) / peak


def timing_error(t: FloatArray, value: FloatArray, t_reference: FloatArray, reference: FloatArray) -> float:
    """Time of the modelled peak minus time of the reference peak, s; the two series may differ in step."""
    return float(t[np.argmax(value)] - t_reference[np.argmax(reference)])
