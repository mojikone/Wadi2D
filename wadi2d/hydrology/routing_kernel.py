"""The compiled core of the Muskingum-Cunge reach: trapezoid hydraulics and the cell step.

Interface: :func:`route_cells`, :func:`muskingum_coefficients`, :func:`normal_depth`. Numba kernels on plain floats
and arrays, so they carry no objects; every knob arrives as an argument from :mod:`wadi2d.hydrology.routing`. The
conserving variant in :mod:`wadi2d.hydrology.routing_conserving` shares the trapezoid hydraulics and nothing else.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

MANNING_EXPONENT = 2.0 / 3.0
WIDE_CHANNEL_POWER = 5.0 / 3.0
START_DEPTH = 1.0
THREE_POINTS = 3.0
FOUR_POINTS = 4.0
HALF = 0.5


@njit(cache=True)
def muskingum_coefficients(courant: float, reynolds: float) -> tuple[float, float, float]:
    """The weights of old inflow, new inflow and old outflow; they sum to one."""
    denominator = 1.0 + courant + reynolds
    old_inflow = (1.0 + courant - reynolds) / denominator
    new_inflow = (courant + reynolds - 1.0) / denominator
    old_outflow = (1.0 - courant + reynolds) / denominator
    return old_inflow, new_inflow, old_outflow


@njit(cache=True)
def normal_depth(
    flow: float, width: float, side: float, conveyance: float, guess: float, iterations: int, tolerance: float
) -> float:
    """Manning depth by Newton from ``guess``; ``conveyance`` is sqrt(S) / n."""
    wet_side = 2.0 * math.sqrt(1.0 + side * side)
    depth = guess if guess > 0.0 else START_DEPTH
    for _ in range(iterations):
        area = (width + side * depth) * depth
        perimeter = width + wet_side * depth
        top = width + 2.0 * side * depth
        radius = area / perimeter
        power = radius**MANNING_EXPONENT
        residual = conveyance * area * power - flow
        slope = conveyance * power * (WIDE_CHANNEL_POWER * top - MANNING_EXPONENT * radius * wet_side)
        step = residual / slope
        updated = depth - step
        depth = updated if updated > 0.0 else HALF * depth
        if abs(step) < tolerance:
            break
    return depth


@njit(cache=True)
def _numbers(
    flow: float,
    dt: float,
    dx: float,
    width: float,
    side: float,
    slope: float,
    conveyance: float,
    depth: float,
    iterations: int,
    tolerance: float,
) -> tuple[float, float, float]:
    """Courant and cell Reynolds numbers at a reference flow, and the depth to start the next solve from."""
    depth = normal_depth(flow, width, side, conveyance, depth, iterations, tolerance)
    area = (width + side * depth) * depth
    top = width + 2.0 * side * depth
    perimeter = width + 2.0 * depth * math.sqrt(1.0 + side * side)
    wet_side = 2.0 * math.sqrt(1.0 + side * side)
    celerity = flow / area * (WIDE_CHANNEL_POWER - MANNING_EXPONENT * area / perimeter * wet_side / top)
    return celerity * dt / dx, flow / (top * slope * celerity * dx), depth


@njit(cache=True)
def route_cells(
    inflow: np.ndarray,
    n_cells: int,
    dt: float,
    dx: float,
    width: float,
    side: float,
    slope: float,
    roughness: float,
    route_iterations: int,
    depth_iterations: int,
    depth_tolerance: float,
    relative_tolerance: float,
    low_flow: float,
) -> np.ndarray:
    """Route ``inflow`` through ``n_cells`` cells upstream to downstream; the outflow has its length.

    The HMS replication rules are explained in :mod:`wadi2d.hydrology.routing`: the low-flow mean, the iterated
    reference flow, and the negative new-inflow weight split between the other two.
    """
    conveyance = math.sqrt(slope) / roughness
    upstream = inflow.copy()
    outflow = inflow.copy()
    for _ in range(n_cells):
        outflow = np.empty_like(upstream)
        outflow[0] = upstream[0]
        depth = START_DEPTH
        for step in range(1, len(upstream)):
            old_in = upstream[step - 1]
            new_in = upstream[step]
            old_out = outflow[step - 1]
            known = old_in + new_in + old_out
            reference = known / THREE_POINTS
            if reference < low_flow:
                outflow[step] = reference
                continue
            result = math.inf
            for _ in range(route_iterations):
                courant, reynolds, depth = _numbers(
                    reference,
                    dt,
                    dx,
                    width,
                    side,
                    slope,
                    conveyance,
                    depth,
                    depth_iterations,
                    depth_tolerance,
                )
                weight_old_in, weight_new_in, weight_old_out = muskingum_coefficients(courant, reynolds)
                if weight_new_in < 0.0:
                    weight_old_in += HALF * weight_new_in
                    weight_old_out += HALF * weight_new_in
                    weight_new_in = 0.0
                updated = weight_old_in * old_in + weight_new_in * new_in + weight_old_out * old_out
                updated = max(updated, 0.0)
                settled = abs(updated - result) < relative_tolerance * updated
                result = updated
                if settled:
                    break
                reference = (known + result) / FOUR_POINTS
            outflow[step] = result
        upstream = outflow
    return outflow
