"""The compiled core of level-pool routing: the two step loops, on plain floats and arrays.

Interface: :func:`route_storage_indication`, :func:`route_spillways`. Numba kernels that carry no objects; the
tables and every knob arrive as arguments from :mod:`wadi2d.hydrology.reservoir`. Both report a pool above the top
of its table instead of inventing a rule for it: what HMS does there is not known.
"""

from __future__ import annotations

import numpy as np
from numba import njit

HALF = 0.5
WEIR_POWER = 1.5
WEIR_SLOPE_POWER = 0.5
MAIN_OUTLET = 0


@njit(cache=True)
def _interpolate(value: float, nodes: np.ndarray, values: np.ndarray) -> float:
    """Linear between rows, the first row below the table. The caller has checked the top of the table."""
    if value <= nodes[0]:
        return values[0]
    row = int(np.searchsorted(nodes, value, side="right")) - 1
    if row >= len(nodes) - 1:
        return values[-1]
    fraction = (value - nodes[row]) / (nodes[row + 1] - nodes[row])
    return values[row] + fraction * (values[row + 1] - values[row])


@njit(cache=True)
def route_storage_indication(
    inflow: np.ndarray, dt: float, storage: np.ndarray, outflow: np.ndarray, initial_storage: float
) -> tuple[np.ndarray, bool]:
    """One Modified Puls step per control step; the outflow, and whether the pool passed the top of the table."""
    indication = storage / dt + HALF * outflow
    released = np.empty_like(inflow)
    held = initial_storage
    released[0] = _interpolate(held, storage, outflow)
    current = held / dt + HALF * released[0]
    for step in range(len(inflow) - 1):
        current = current - released[step] + HALF * (inflow[step] + inflow[step + 1])
        if current > indication[-1]:
            return released, True
        released[step + 1] = _interpolate(current, indication, outflow)
    return released, False


@njit(cache=True)
def _weir_flows(
    elevation: float, crests: np.ndarray, lengths: np.ndarray, coefficients: np.ndarray, outlets: np.ndarray
) -> tuple[float, float]:
    """Q = C L H^1.5 summed over the spillways of the main and of the auxiliary outlet."""
    main = 0.0
    auxiliary = 0.0
    for index in range(len(crests)):
        head = elevation - crests[index]
        if head <= 0.0:
            continue
        flow = coefficients[index] * lengths[index] * head**WEIR_POWER
        if outlets[index] == MAIN_OUTLET:
            main += flow
        else:
            auxiliary += flow
    return main, auxiliary


@njit(cache=True)
def _weir_slope(elevation: float, crests: np.ndarray, lengths: np.ndarray, coefficients: np.ndarray) -> float:
    """dQ/dz of all the spillways together."""
    slope = 0.0
    for index in range(len(crests)):
        head = elevation - crests[index]
        if head > 0.0:
            slope += WEIR_POWER * coefficients[index] * lengths[index] * head**WEIR_SLOPE_POWER
    return slope


@njit(cache=True)
def _solve_row(
    target: float,
    low: float,
    high: float,
    base_storage: float,
    storage_slope: float,
    half_dt: float,
    crests: np.ndarray,
    lengths: np.ndarray,
    coefficients: np.ndarray,
    outlets: np.ndarray,
    iterations: int,
    tolerance: float,
) -> float:
    """The level in one table row where S(z) + dt/2 Q(z) reaches ``target``: Newton, kept inside its bracket."""
    bottom = low
    level = high
    for _ in range(iterations):
        main, auxiliary = _weir_flows(level, crests, lengths, coefficients, outlets)
        residual = base_storage + storage_slope * (level - bottom) + half_dt * (main + auxiliary) - target
        if residual > 0.0:
            high = level
        else:
            low = level
        slope = storage_slope + half_dt * _weir_slope(level, crests, lengths, coefficients)
        updated = level - residual / slope if slope > 0.0 else HALF * (low + high)
        if not low <= updated <= high:
            updated = HALF * (low + high)
        settled = abs(updated - level) < tolerance
        level = updated
        if settled:
            break
    return level


@njit(cache=True)
def _pool_after(
    level: float,
    known: float,
    half_step: float,
    elevations: np.ndarray,
    storage: np.ndarray,
    crests: np.ndarray,
    lengths: np.ndarray,
    coefficients: np.ndarray,
    outlets: np.ndarray,
    iterations: int,
    tolerance: float,
) -> tuple[float, float, bool]:
    """Solve S(z) + h/2 Q(z) = ``known``: the level, the storage, and whether it is above the table."""
    low = 0
    high = len(elevations) - 1
    top_main, top_auxiliary = _weir_flows(elevations[high], crests, lengths, coefficients, outlets)
    if known > storage[high] + half_step * (top_main + top_auxiliary):
        return level, known, True
    bottom_main, bottom_auxiliary = _weir_flows(elevations[0], crests, lengths, coefficients, outlets)
    if known <= storage[0] + half_step * (bottom_main + bottom_auxiliary):
        return elevations[0], storage[0], False
    while high - low > 1:
        middle = (low + high) // 2
        main, auxiliary = _weir_flows(elevations[middle], crests, lengths, coefficients, outlets)
        if storage[middle] + half_step * (main + auxiliary) <= known:
            low = middle
        else:
            high = middle
    slope = (storage[low + 1] - storage[low]) / (elevations[low + 1] - elevations[low])
    solved = _solve_row(
        known,
        elevations[low],
        elevations[low + 1],
        storage[low],
        slope,
        half_step,
        crests,
        lengths,
        coefficients,
        outlets,
        iterations,
        tolerance,
    )
    return solved, storage[low] + slope * (solved - elevations[low]), False


@njit(cache=True)
def route_spillways(
    inflow: np.ndarray,
    dt: float,
    elevations: np.ndarray,
    storage: np.ndarray,
    crests: np.ndarray,
    lengths: np.ndarray,
    coefficients: np.ndarray,
    outlets: np.ndarray,
    initial_elevation: float,
    iterations: int,
    tolerance: float,
    level_change_limit: float,
    max_bisections: int,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Implicit trapezoid steps; a step that moves the pool past the limit is bisected, up to ``max_bisections``.

    The inflow stays at the mean of the control step in every part. Returns the main outflow, the auxiliary
    outflow, and whether the pool passed the top of the table.
    """
    main_out = np.zeros_like(inflow)
    auxiliary_out = np.zeros_like(inflow)
    level = initial_elevation
    held = _interpolate(level, elevations, storage)
    main, auxiliary = _weir_flows(level, crests, lengths, coefficients, outlets)
    main_out[0], auxiliary_out[0] = main, auxiliary
    pending = np.empty(max_bisections + 2, dtype=np.int64)
    for step in range(len(inflow) - 1):
        mean_inflow = HALF * (inflow[step] + inflow[step + 1])
        pending[0] = 0
        waiting = 1
        while waiting > 0:
            waiting -= 1
            depth = pending[waiting]
            part = dt / 2.0**depth
            known = held + part * (mean_inflow - HALF * (main + auxiliary))
            solved, stored, above = _pool_after(
                level,
                known,
                HALF * part,
                elevations,
                storage,
                crests,
                lengths,
                coefficients,
                outlets,
                iterations,
                tolerance,
            )
            if (above or abs(solved - level) > level_change_limit) and depth < max_bisections:
                pending[waiting] = depth + 1
                pending[waiting + 1] = depth + 1
                waiting += 2
                continue
            if above:
                return main_out, auxiliary_out, True
            level = solved
            held = stored
            main, auxiliary = _weir_flows(level, crests, lengths, coefficients, outlets)
        main_out[step + 1], auxiliary_out[step + 1] = main, auxiliary
    return main_out, auxiliary_out, False
