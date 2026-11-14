"""The compiled core of a reservoir with outflow structures: each structure a law Q(pool, tailwater), summed in one
implicit trapezoid step with HMS's adaptive bisection.

Interface: :func:`structure_flows`, :func:`route_structures`. Numba kernels on plain arrays; the structures arrive packed
by :mod:`wadi2d.hydrology.structures` as a kind code, an outlet code, three parameters and a slice of one shared table.

Every law was measured against HEC-HMS 4.12 headless on a metric test project (W59), not taken from the manual alone:

- broad-crested spillway and level dam top, C L H^1.5 on the pool head over the crest, drowned by a tailwater over
  the crest through one tabulated reduction on the submergence (tailwater over pool heads), linear between its
  rows, the same for both (W67);
- rating-curve spillway, the table read at the pool, linear between rows, never drowned by a tailwater;
- orifice, K A sqrt(2 g H) with H from the higher of the centreline and the tailwater, g = 9.80665 m/s2 (HMS's own);
- tabular seepage, the pool-to-tailwater table read at the pool minus the tailwater, or minus the bottom of the storage
  table when there is no tailwater, extended below its first row along its first segment, so a tailwater above the pool
  gives a negative seepage on the main outlet, as HMS does;
- evaporation, a rate times the pool area, lost from the books and not sent to an outlet;
- a gate on a broad-crested spillway (W62): weir flow C L H^1.5 over the gates' width while the head over the crest
  is at most the opening, the gate law from 1.25 openings (sluice C W B k sqrt(H), radial C k W T^TE B^BE H^HE),
  linear in H/B between, with HMS's own constant k = 4.42869 for sqrt(2 g); drowned by a tailwater over the crest
  (W76): r = (pool - tailwater) / B, up to 1 the free flow reduced by the weirs' submergence share, from 1.25 the
  gate law on the head over the tailwater times sqrt(3), linear in r between; an opening that varies in time is
  passed in per step (HMS's Percent Time Series: the opening at each time, linear in the gage);
- a pump (W62): the head-discharge table read at the discharge elevation less the pool plus the equipment loss, times
  the units, while the pump is on. On and off are a state carried from step to step: decided at the start of every
  step part from the pool there and the time in the state, and held over the part.

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
GATE = 5
PUMP = 6
GATE_SQRT_2G = 4.42869
"""HMS's sqrt(2 g) in the gate laws, a literal: W62's sluice and radial flows divided by their laws read 4.42869 to
the last digit, where sqrt(2 x 9.80665) is 4.4286906."""
GATE_WEIR_BELOW = 1.0
GATE_LAW_ABOVE = 1.25
"""Head over the crest in openings: weir flow up to the first, the gate law from the second, linear between (W62)."""
GATE_BASE = 5
GATE_OPENING_EXPONENT = 6
"""A gate's parameters past W62's five: the gate factor without its opening term, and the opening exponent, so an
opening given per step sets the factor as base x B^BE (W76)."""
GATE_DROWNED_FACTOR = math.sqrt(3.0)
"""HMS's drowned gate law over its free law on the head over the tailwater (W76): every drowned step of ten runs,
sluice and radial, four gate coefficients, reads sqrt(3) to the last digit; the Orifice Coefficient changes nothing."""
PUMP_ON = 0
PUMP_OFF = 1
PUMP_INTAKE = 2
PUMP_HEAD_AT_ZERO = 3
PUMP_UNITS = 4
PUMP_RUN = 5
PUMP_REST = 6
"""A pump's parameters: on, off and intake levels, discharge elevation plus equipment loss, units, minimum run and
rest, s."""
PUMP_SWITCH_ON_TOLERANCE_M = 5.0e-4
"""A pump switches on at a step whose start lies within half a millimetre under its switch-on level (W62: HMS did at
0.22, 0.36 and 0.38 mm under, and did not at 0.59 and 1.3 mm under; [Likely] it compares levels to the millimetre)."""

SUBMERGENCE = np.array([0.76, 0.84, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 0.995, 1.0])
SUBMERGED_SHARE = np.array([1.0, 0.985, 0.96, 0.93, 0.88, 0.82, 0.72, 0.575, 0.38, 0.0])
"""HMS's drowned broad-crested spillway and level dam top (W67): the share of free flow against the submergence
(tailwater - crest) / (pool - crest), linear between rows, none from 1. Read off HMS's output: the slope of the
share between neighbouring steps is constant to 1e-3 between these rows and changes at each, on three runs and
both structures; the table gives HMS's flows to round-off."""

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
def _gate_free(level: float, row: np.ndarray, factor: float, opening: float) -> tuple[float, float]:
    """A gate group with no tailwater over its crest: ``row`` is crest, weir C x width, gate factor F (flow
    F H^HE), opening, HE; ``factor`` and ``opening`` the ones in force (the row's own for a fixed opening)."""
    head = level - row[0]
    if head <= 0.0 or opening <= 0.0:
        return 0.0, 0.0
    weir = row[1] * head**WEIR_POWER
    weir_slope = WEIR_POWER * row[1] * head**WEIR_SLOPE_POWER
    ratio = head / opening
    if ratio <= GATE_WEIR_BELOW:
        return weir, weir_slope
    gate = factor * head ** row[4]
    gate_slope = row[4] * factor * head ** (row[4] - 1.0)
    if ratio >= GATE_LAW_ABOVE:
        return gate, gate_slope
    span = GATE_LAW_ABOVE - GATE_WEIR_BELOW
    share = (ratio - GATE_WEIR_BELOW) / span
    flow = weir + share * (gate - weir)
    return flow, weir_slope + share * (gate_slope - weir_slope) + (gate - weir) / (span * opening)


@njit(cache=True)
def _drowned(flow: float, slope: float, head: float, submergence: float) -> tuple[float, float]:
    """A weir's free flow and dQ/dz reduced at a submergence s = h2 / h1: Q f(s), and since ds/dz = -s / h1,
    dQ/dz = f dQ/dz + Q f'(s) (-s / h1). None at and past 1, no reverse flow."""
    if submergence >= 1.0:
        return 0.0, 0.0
    share = _interpolate(submergence, SUBMERGENCE, SUBMERGED_SHARE)
    if submergence <= SUBMERGENCE[0]:
        return flow * share, slope * share
    tilt = _row_slope(submergence, SUBMERGENCE, SUBMERGED_SHARE, False)
    return flow * share, slope * share - flow * tilt * submergence / head


@njit(cache=True)
def _gate(level: float, row: np.ndarray, stage: float, opening: float) -> tuple[float, float]:
    """A gate group: the free law of :func:`_gate_free`, drowned when the tailwater ``stage`` stands over the crest
    (W76); ``opening`` NaN for the row's own fixed opening, else the opening in force (factor base x B^BE)."""
    factor = row[2]
    if math.isnan(opening):
        opening = row[3]
    else:
        factor = row[GATE_BASE] * opening ** row[GATE_OPENING_EXPONENT]
    free, free_slope = _gate_free(level, row, factor, opening)
    if math.isnan(stage) or stage <= row[0]:
        return free, free_slope
    head = level - row[0]
    if head <= 0.0 or opening <= 0.0:
        return 0.0, 0.0
    low, low_slope = _drowned(free, free_slope, head, (stage - row[0]) / head)
    drop = level - stage
    ratio = drop / opening
    if ratio <= GATE_WEIR_BELOW:
        return low, low_slope
    high = GATE_DROWNED_FACTOR * factor * drop ** row[4]
    high_slope = GATE_DROWNED_FACTOR * row[4] * factor * drop ** (row[4] - 1.0)
    if ratio >= GATE_LAW_ABOVE:
        return high, high_slope
    span = GATE_LAW_ABOVE - GATE_WEIR_BELOW
    share = (ratio - GATE_WEIR_BELOW) / span
    flow = low + share * (high - low)
    return flow, low_slope + share * (high_slope - low_slope) + (high - low) / (span * opening)


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
    active: np.ndarray,
    openings: np.ndarray,
) -> tuple[float, float]:
    """The flow of one structure at a pool level, m3/s, and its dQ/dz; ``active`` is 0 for a pump that is off."""
    kind = kinds[index]
    stage = tailwater[outlets[index]]
    if kind == GATE:
        return _gate(level, parameters[index], stage, openings[index])
    if kind in (BROAD_CRESTED, LEVEL_DAM_TOP):
        head = level - parameters[index, 0]
        if head <= 0.0:
            return 0.0, 0.0
        flow = parameters[index, 2] * parameters[index, 1] * head**WEIR_POWER
        slope = WEIR_POWER * parameters[index, 2] * parameters[index, 1] * head**WEIR_SLOPE_POWER
        if math.isnan(stage) or stage <= parameters[index, 0]:
            return flow, slope
        return _drowned(flow, slope, head, (stage - parameters[index, 0]) / head)
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
    if kind == PUMP:
        if active[index] == 0.0:
            return 0.0, 0.0
        head = parameters[index, PUMP_HEAD_AT_ZERO] - level
        units = parameters[index, PUMP_UNITS]
        return units * _interpolate(head, nodes, values), -units * _row_slope(head, nodes, values, False)
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
    active: np.ndarray,
    openings: np.ndarray,
) -> tuple[float, float, float, float]:
    """Main and auxiliary outflow, evaporation (lost), and dQ/dz of all three together."""
    main = 0.0
    auxiliary = 0.0
    slope = 0.0
    for index in range(len(kinds)):
        flow, gradient = _structure(
            index, level, kinds, outlets, parameters, table_x, table_y, table_start, table_end, tailwater,
            elevations[0], active, openings,
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
    active: np.ndarray,
    openings: np.ndarray,
) -> np.ndarray:
    """The flow of every structure at every pool level, m3/s: one row per level, one column per structure;
    ``active`` holds each structure's state at each level (a pump's on or off), the same shape, and ``openings``
    each gate's opening there, NaN for a fixed one."""
    out = np.empty((len(levels), len(kinds)))
    for row in range(len(levels)):
        for index in range(len(kinds)):
            out[row, index] = _structure(
                index, levels[row], kinds, outlets, parameters, table_x, table_y, table_start, table_end, tailwater,
                bottom, active[row], openings[row],
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
    active: np.ndarray,
    openings: np.ndarray,
    iterations: int,
    tolerance: float,
) -> float:
    """The level in one table row where S(z) + dt/2 (Q(z) + E(z)) reaches ``target``: Newton, kept in its bracket."""
    bottom = low
    level = high
    for _ in range(iterations):
        main, auxiliary, lost, gradient = _flows(
            level, rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start, table_end,
            tailwater, active, openings,
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
    active: np.ndarray,
    openings: np.ndarray,
    iterations: int,
    tolerance: float,
) -> tuple[float, float, bool]:
    """Solve S(z) + h/2 (Q(z) + E(z)) = ``known``: the level, the storage, and whether it is above the table."""
    low = 0
    high = len(elevations) - 1
    top_main, top_auxiliary, top_lost, _ = _flows(
        elevations[high], rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
        table_end, tailwater, active, openings,
    )
    if known > storage[high] + half_step * (top_main + top_auxiliary + top_lost):
        return level, known, True
    bottom_main, bottom_auxiliary, bottom_lost, _ = _flows(
        elevations[0], rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
        table_end, tailwater, active, openings,
    )
    if known <= storage[0] + half_step * (bottom_main + bottom_auxiliary + bottom_lost):
        return elevations[0], storage[0], False
    while high - low > 1:
        middle = (low + high) // 2
        main, auxiliary, lost, _ = _flows(
            elevations[middle], rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
            table_end, tailwater, active, openings,
        )
        if storage[middle] + half_step * (main + auxiliary + lost) <= known:
            low = middle
        else:
            high = middle
    slope = (storage[low + 1] - storage[low]) / (elevations[low + 1] - elevations[low])
    solved = _solve_row(
        known, elevations[low], elevations[low + 1], storage[low], slope, half_step, rate, elevations, areas, kinds,
        outlets, parameters, table_x, table_y, table_start, table_end, tailwater, active, openings, iterations, tolerance,
    )
    return solved, storage[low] + slope * (solved - elevations[low]), False


@njit(cache=True)
def _switch_pumps(
    level: float, clock: float, kinds: np.ndarray, parameters: np.ndarray, active: np.ndarray, since: np.ndarray
) -> bool:
    """Turn each pump on or off at the start of a step part; True when any changed.

    On at the switch-on level (within :data:`PUMP_SWITCH_ON_TOLERANCE_M`) once rested for the minimum rest; off
    below the switch-off level once run for the minimum run, and below the intake at once. HMS refuses a switch-off level under the intake.
    """
    changed = False
    for index in range(len(kinds)):
        if kinds[index] != PUMP:
            continue
        row = parameters[index]
        held = clock - since[index]
        if active[index] != 0.0:
            if level < row[PUMP_INTAKE] or (level < row[PUMP_OFF] and held >= row[PUMP_RUN]):
                active[index] = 0.0
                since[index] = clock
                changed = True
        elif level >= row[PUMP_ON] - PUMP_SWITCH_ON_TOLERANCE_M and held >= row[PUMP_REST]:
            active[index] = 1.0
            since[index] = clock
            changed = True
    return changed


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
    schedule: np.ndarray,
    initial_elevation: float,
    iterations: int,
    tolerance: float,
    level_change_limit: float,
    max_bisections: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, bool]:
    """Implicit trapezoid steps, a step that moves the pool past the limit bisected up to ``max_bisections``.

    ``rates`` is the evaporation rate of each control step, m/s, by the month the step starts in. Returns the main
    and auxiliary outflow, the evaporation, m3/s, at the times of the inflow, the pool level and storage there, the
    state of each structure over the step that ends there (a pump's 1 on, 0 off; 1 for every other structure), and
    whether the pool passed the top of the table. A pump starts off, rested; a change of state at the start of a part
    sets the flows that part's trapezoid starts from. ``schedule`` holds each structure's gate opening at each time
    of the inflow, NaN for a fixed one; a part's end takes it linearly between its step's two times (W76).
    """
    count = len(inflow)
    main_out = np.zeros(count)
    auxiliary_out = np.zeros(count)
    lost_out = np.zeros(count)
    level_out = np.zeros(count)
    storage_out = np.zeros(count)
    active = np.ones(len(kinds))
    since = np.full(len(kinds), -np.inf)
    for index in range(len(kinds)):
        if kinds[index] == PUMP:
            active[index] = 0.0
    level = initial_elevation
    clock = 0.0
    openings = schedule[0].copy()
    ahead = schedule[0].copy()
    _switch_pumps(level, clock, kinds, parameters, active, since)
    active_out = np.ones((count, len(kinds)))
    active_out[0] = active
    held = _interpolate(level, elevations, storage)
    rate = rates[0] if len(rates) > 0 else 0.0
    main, auxiliary, lost, _ = _flows(
        level, rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start, table_end,
        tailwater, active, openings,
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
                table_end, tailwater, active, openings,
            )
        pending[0] = 0
        waiting = 1
        while waiting > 0:
            waiting -= 1
            depth = pending[waiting]
            part = dt / 2.0**depth
            if _switch_pumps(level, clock, kinds, parameters, active, since):
                main, auxiliary, lost, _ = _flows(
                    level, rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
                    table_end, tailwater, active, openings,
                )
            known = held + part * (mean_inflow - HALF * (main + auxiliary + lost))
            reach = min(max((clock + part) / dt - step, 0.0), 1.0)
            for index in range(len(kinds)):
                ahead[index] = schedule[step, index] + reach * (schedule[step + 1, index] - schedule[step, index])
            solved, stored, above = _pool_after(
                level, known, HALF * part, rate, elevations, storage, areas, kinds, outlets, parameters, table_x,
                table_y, table_start, table_end, tailwater, active, ahead, iterations, tolerance,
            )
            if (above or abs(solved - level) > level_change_limit) and depth < max_bisections:
                pending[waiting] = depth + 1
                pending[waiting + 1] = depth + 1
                waiting += 2
                continue
            if above:
                return main_out, auxiliary_out, lost_out, level_out, storage_out, active_out, True
            level = solved
            held = stored
            clock += part
            openings[:] = ahead
            main, auxiliary, lost, _ = _flows(
                level, rate, elevations, areas, kinds, outlets, parameters, table_x, table_y, table_start,
                table_end, tailwater, active, openings,
            )
        main_out[step + 1], auxiliary_out[step + 1], lost_out[step + 1] = main, auxiliary, lost
        level_out[step + 1], storage_out[step + 1] = level, held
        active_out[step + 1] = active
    return main_out, auxiliary_out, lost_out, level_out, storage_out, active_out, False
