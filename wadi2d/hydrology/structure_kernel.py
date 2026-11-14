"""The compiled core of a reservoir with outflow structures: each structure a law Q(pool, tailwater), summed in one
implicit trapezoid step with HMS's adaptive bisection.

Interface: :func:`structure_flows`, :func:`route_structures`. Numba kernels on plain arrays; the structures arrive packed
by :mod:`wadi2d.hydrology.structures` as a kind code, an outlet code, three parameters and a slice of one shared table.

Every law was measured against HEC-HMS 4.12 headless on a metric test project (W59), not taken from the manual alone:

- broad-crested spillway and level dam top, C L H^1.5 on the pool head over the crest;
- rating-curve spillway, the table read at the pool, linear between rows, never drowned by a tailwater;
- orifice, K A sqrt(2 g H) with H from the higher of the centreline and the tailwater, g = 9.80665 m/s2 (HMS's own);
- tabular seepage, the pool-to-tailwater table read at the pool minus the tailwater, or minus the bottom of the storage
  table when there is no tailwater, extended below its first row along its first segment, so a tailwater above the pool
  gives a negative seepage on the main outlet, as HMS does;
- evaporation, a rate times the pool area, lost from the books and not sent to an outlet.

The step is :mod:`wadi2d.hydrology.reservoir_kernel`'s, in the same order of operations, so a reservoir of
broad-crested spillways alone routes here to the same bits as there (``tests/hydrology/test_hms_structures.py``).
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

HALF = 0.5
WEIR_POWER = 1.5
WEIR_SLOPE_POWER = 0.5
GRAVITY = 9.80665
"""HMS's gravity: the orifice flows of W59's runs equal K A sqrt(2 g H) to the last bit with it, not with 9.81."""

BROAD_CRESTED = 0
RATING_CURVE = 1
ORIFICE = 2
LEVEL_DAM_TOP = 3
TABULAR_SEEPAGE = 4

MAIN_OUTLET = 0
AUXILIARY_OUTLET = 1


@njit(cache=True)
def _interpolate(value: float, nodes: np.ndarray, values: np.ndarray) -> float:
    """Linear between rows, the first row below the table and the last above it."""
    if value <= nodes[0]:
        return values[0]
    row = int(np.searchsorted(nodes, value, side="right")) - 1
    if row >= len(nodes) - 1:
        return values[-1]
    fraction = (value - nodes[row]) / (nodes[row + 1] - nodes[row])
    return values[row] + fraction * (values[row + 1] - values[row])


@njit(cache=True)
def _row_slope(value: float, nodes: np.ndarray, values: np.ndarray, extend_low: bool) -> float:
    """The slope of the table's row that holds ``value``; zero outside the table unless extended below it."""
    if value <= nodes[0]:
        if extend_low:
            return (values[1] - values[0]) / (nodes[1] - nodes[0])
        return 0.0
    row = int(np.searchsorted(nodes, value, side="right")) - 1
    if row >= len(nodes) - 1:
        return 0.0
    return (values[row + 1] - values[row]) / (nodes[row + 1] - nodes[row])


@njit(cache=True)
def _structure(
    index: int,
    level: float,
    kinds: np.ndarray,
    outlets: np.ndarray,
    parameters: np.ndarray,
    table_x: np.ndarray,
    table_y: np.ndarray,
    table_start: np.ndarray,
    table_end: np.ndarray,
    tailwater: np.ndarray,
    bottom: float,
) -> tuple[float, float]:
    """The flow of one structure at a pool level, m3/s, and its dQ/dz."""
    kind = kinds[index]
    stage = tailwater[outlets[index]]
    if kind in (BROAD_CRESTED, LEVEL_DAM_TOP):
        head = level - parameters[index, 0]
        if head <= 0.0:
            return 0.0, 0.0
        flow = parameters[index, 2] * parameters[index, 1] * head**WEIR_POWER
        return flow, WEIR_POWER * parameters[index, 2] * parameters[index, 1] * head**WEIR_SLOPE_POWER
    if kind == ORIFICE:
        base = parameters[index, 0]
        if not math.isnan(stage) and stage > base:
            base = stage
        head = level - base
        if head <= 0.0:
            return 0.0, 0.0
        root = math.sqrt(2.0 * GRAVITY * head)
        return parameters[index, 1] * root, parameters[index, 1] * GRAVITY / root
    nodes = table_x[table_start[index] : table_end[index]]
    values = table_y[table_start[index] : table_end[index]]
    if kind == RATING_CURVE:
        return _interpolate(level, nodes, values), _row_slope(level, nodes, values, False)
    # TABULAR_SEEPAGE: the head over the tailwater, or over the bottom of the storage table with none
    head = level - (bottom if math.isnan(stage) else stage)
    slope = _row_slope(head, nodes, values, True)
    if head <= nodes[0]:
        return values[0] + (head - nodes[0]) * slope, slope
    return _interpolate(head, nodes, values), slope


@njit(cache=True)
def _flows(
    level: float,
    rate: float,
    elevations: np.ndarray,
    areas: np.ndarray,
    kinds: np.ndarray,
    outlets: np.ndarray,
    parameters: np.ndarray,
    table_x: np.ndarray,
    table_y: np.ndarray,
    table_start: np.ndarray,
    table_end: np.ndarray,
    tailwater: np.ndarray,
) -> tuple[float, float, float, float]:
    """Main and auxiliary outflow, evaporation (lost), and dQ/dz of all three together."""
    main = 0.0
    auxiliary = 0.0
    slope = 0.0
    for index in range(len(kinds)):
        flow, gradient = _structure(
            index, level, kinds, outlets, parameters, table_x, table_y, table_start, table_end, tailwater,
            elevations[0],
        )
        if outlets[index] == MAIN_OUTLET:
            main += flow
        else:
            auxiliary += flow
        slope += gradient
    lost = 0.0
    if rate != 0.0:
        lost = rate * _interpolate(level, elevations, areas)
        slope += rate * _row_slope(level, elevations, areas, False)
    return main, auxiliary, lost, slope


@njit(cache=True)
def structure_flows(
    levels: np.ndarray,
    kinds: np.ndarray,
    outlets: np.ndarray,
    parameters: np.ndarray,
    table_x: np.ndarray,
    table_y: np.ndarray,
    table_start: np.ndarray,
    table_end: np.ndarray,
    tailwater: np.ndarray,
    bottom: float,
) -> np.ndarray:
    """The flow of every structure at every pool level, m3/s: one row per level, one column per structure."""
    out = np.empty((len(levels), len(kinds)))
    for row in range(len(levels)):
        for index in range(len(kinds)):
            out[row, index] = _structure(
                index, levels[row], kinds, outlets, parameters, table_x, table_y, table_start, table_end, tailwater,
                bottom,
            )[0]
    return out


@njit(cache=True)
def _solve_row(
    target: float,
    low: float,
    high: float,
    base_storage: float,
    storage_slope: float,
    half_dt: float,
    rate: float,
    elevations: np.ndarray,
    areas: np.ndarray,
    kinds: np.ndarray,
    outlets: np.ndarray,
    parameters: np.ndarray,
    table_x: np.ndarray,
    table_y: np.ndarray,
    table_start: np.ndarray,
    table_end: np.ndarray,
    tailwater: np.ndarray,
    iterations: int,
    tolerance: float,
) -> float:
    """The level in one table row where S(z) + dt/2 (Q(z) + E(z)) reaches ``target``: Newton, kept in its bracket."""
    bottom = low
    level = high
    for _ in range(iterations):
        main, auxiliary, lost, gradient = _flows(
            level, rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start, table_end,
            tailwater,
        )
        residual = base_storage + storage_slope * (level - bottom) + half_dt * (main + auxiliary + lost) - target
        if residual > 0.0:
            high = level
        else:
            low = level
        slope = storage_slope + half_dt * gradient
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
    rate: float,
    elevations: np.ndarray,
    storage: np.ndarray,
    areas: np.ndarray,
    kinds: np.ndarray,
    outlets: np.ndarray,
    parameters: np.ndarray,
    table_x: np.ndarray,
    table_y: np.ndarray,
    table_start: np.ndarray,
    table_end: np.ndarray,
    tailwater: np.ndarray,
    iterations: int,
    tolerance: float,
) -> tuple[float, float, bool]:
    """Solve S(z) + h/2 (Q(z) + E(z)) = ``known``: the level, the storage, and whether it is above the table."""
    low = 0
    high = len(elevations) - 1
    top_main, top_auxiliary, top_lost, _ = _flows(
        elevations[high], rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
        table_end, tailwater,
    )
    if known > storage[high] + half_step * (top_main + top_auxiliary + top_lost):
        return level, known, True
    bottom_main, bottom_auxiliary, bottom_lost, _ = _flows(
        elevations[0], rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
        table_end, tailwater,
    )
    if known <= storage[0] + half_step * (bottom_main + bottom_auxiliary + bottom_lost):
        return elevations[0], storage[0], False
    while high - low > 1:
        middle = (low + high) // 2
        main, auxiliary, lost, _ = _flows(
            elevations[middle], rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
            table_end, tailwater,
        )
        if storage[middle] + half_step * (main + auxiliary + lost) <= known:
            low = middle
        else:
            high = middle
    slope = (storage[low + 1] - storage[low]) / (elevations[low + 1] - elevations[low])
    solved = _solve_row(
        known, elevations[low], elevations[low + 1], storage[low], slope, half_step, rate, elevations, areas, kinds,
        outlets, parameters, table_x, table_y, table_start, table_end, tailwater, iterations, tolerance,
    )
    return solved, storage[low] + slope * (solved - elevations[low]), False


@njit(cache=True)
def route_structures(
    inflow: np.ndarray,
    dt: float,
    elevations: np.ndarray,
    storage: np.ndarray,
    areas: np.ndarray,
    rates: np.ndarray,
    kinds: np.ndarray,
    outlets: np.ndarray,
    parameters: np.ndarray,
    table_x: np.ndarray,
    table_y: np.ndarray,
    table_start: np.ndarray,
    table_end: np.ndarray,
    tailwater: np.ndarray,
    initial_elevation: float,
    iterations: int,
    tolerance: float,
    level_change_limit: float,
    max_bisections: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, bool]:
    """Implicit trapezoid steps, a step that moves the pool past the limit bisected up to ``max_bisections``.

    ``rates`` is the evaporation rate of each control step, m/s, by the month the step starts in. Returns the main
    and auxiliary outflow, the evaporation, m3/s, at the times of the inflow, the pool level and storage there, and
    whether the pool passed the top of the table.
    """
    count = len(inflow)
    main_out = np.zeros(count)
    auxiliary_out = np.zeros(count)
    lost_out = np.zeros(count)
    level_out = np.zeros(count)
    storage_out = np.zeros(count)
    level = initial_elevation
    held = _interpolate(level, elevations, storage)
    rate = rates[0] if len(rates) > 0 else 0.0
    main, auxiliary, lost, _ = _flows(
        level, rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start, table_end,
        tailwater,
    )
    main_out[0], auxiliary_out[0], lost_out[0] = main, auxiliary, lost
    level_out[0], storage_out[0] = level, held
    pending = np.empty(max_bisections + 2, dtype=np.int64)
    for step in range(count - 1):
        mean_inflow = HALF * (inflow[step] + inflow[step + 1])
        if rates[step] != rate:
            rate = rates[step]
            main, auxiliary, lost, _ = _flows(
                level, rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
                table_end, tailwater,
            )
        pending[0] = 0
        waiting = 1
        while waiting > 0:
            waiting -= 1
            depth = pending[waiting]
            part = dt / 2.0**depth
            known = held + part * (mean_inflow - HALF * (main + auxiliary + lost))
            solved, stored, above = _pool_after(
                level, known, HALF * part, rate, elevations, storage, areas, kinds, outlets, parameters, table_x,
                table_y, table_start, table_end, tailwater, iterations, tolerance,
            )
            if (above or abs(solved - level) > level_change_limit) and depth < max_bisections:
                pending[waiting] = depth + 1
                pending[waiting + 1] = depth + 1
                waiting += 2
                continue
            if above:
                return main_out, auxiliary_out, lost_out, level_out, storage_out, True
            level = solved
            held = stored
            main, auxiliary, lost, _ = _flows(
                level, rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
                table_end, tailwater,
            )
        main_out[step + 1], auxiliary_out[step + 1], lost_out[step + 1] = main, auxiliary, lost
        level_out[step + 1], storage_out[step + 1] = level, held
    return main_out, auxiliary_out, lost_out, level_out, storage_out, False
