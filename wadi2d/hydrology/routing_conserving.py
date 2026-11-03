"""The mass-conservative, storage-consistent Muskingum-Cunge of Todini (2007), beside the HMS-faithful kernel.

Interface: :func:`route_cells_conserving`, :func:`corrected_numbers`, :func:`storage_weights`. Numba kernels on
plain floats and arrays; every knob arrives as an argument from :mod:`wadi2d.hydrology.routing`, and the trapezoid
hydraulics are the ones of :mod:`wadi2d.hydrology.routing_kernel`, so both variants read the same section.

Todini, E. (2007), A mass conservative and water storage consistent variable parameter Muskingum-Cunge approach,
Hydrol. Earth Syst. Sci. 11, 1645-1659. The scheme is the Muskingum storage equation written with the parameters of
each time level on its own side, so the storage a step ends with is the storage the next one starts from (eq. 30, 34):

    2 [k e]' I' + 2 [k(1-e)]' O' - 2 [k e] I - 2 [k(1-e)] O = dt (I' + I) - dt (O' + O)

with ' the new time level. Summed over a flood, every term but the end storages cancels, so the routed volume equals
the inflow volume less what the reach still holds, to round-off, whatever the parameters do from step to step. The
parameters are the corrected ones of eq. 44 and 49-51: the travel time k* = dx / v of a parcel, not dx / c of a wave,
so the steady storage is the section's A dx; and D* = D / beta, beta = c / v, so the diffusion dt D / C is unchanged.
Eq. 52 as printed carries the old level in the numerator of C1; eq. 36 and 37, which it rewrites, carry the new one,
and the storage form above is what this kernel solves, so the printed index does not arise.

Two guards keep the identity and answer what the paper leaves open on an ephemeral wadi, measured on Block 2 (W29):
a parcel speed floor, since a trickle in a 60 m bed would otherwise hold a cell's water for hours and the reach would
take days to drain; and a floor on D* at 1 - C*, the point where the weight of the new inflow turns negative, which
is the conservative counterpart of the rule HMS applies by zeroing that weight. Without the second the scheme reads
-9 % of the peak as a dip on Block 2's R1; without the first the tail never drains.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

from wadi2d.hydrology.routing_kernel import MANNING_EXPONENT, WIDE_CHANNEL_POWER, normal_depth

HALF = 0.5
TWO = 2.0


@njit(cache=True)
def corrected_numbers(
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
    flow_floor: float,
    min_velocity: float,
) -> tuple[float, float, float]:
    """Todini's C* and D* at a reference flow, and the depth to start the next solve from.

    The hydraulics are read at no less than ``flow_floor``, where the celerity and beta are otherwise 0 / 0, and the
    parcel speed at no less than ``min_velocity``.
    """
    reference = max(flow, flow_floor)
    depth = normal_depth(reference, width, side, conveyance, depth, iterations, tolerance)
    area = (width + side * depth) * depth
    top = width + TWO * side * depth
    wet_side = TWO * math.sqrt(1.0 + side * side)
    perimeter = width + wet_side * depth
    celerity = reference / area * (WIDE_CHANNEL_POWER - MANNING_EXPONENT * area / perimeter * wet_side / top)
    velocity = max(reference / area, min_velocity)
    beta = celerity / velocity
    courant = velocity * dt / dx
    reynolds = reference / (beta * top * slope * celerity * dx)
    return courant, reynolds, depth


@njit(cache=True)
def storage_weights(courant: float, reynolds: float, dt: float) -> tuple[float, float]:
    """``[k e]`` and ``[k (1 - e)]`` of one time level, eq. 44, with D* held at or above 1 - C*."""
    reynolds = max(reynolds, 1.0 - courant)
    travel = dt / courant
    return HALF * travel * (1.0 - reynolds), HALF * travel * (1.0 + reynolds)


@njit(cache=True)
def route_cells_conserving(
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
    flow_floor: float,
    min_velocity: float,
) -> tuple[np.ndarray, float]:
    """Route ``inflow`` through ``n_cells`` cells; the outflow has its length, and with it what the reach holds at
    the end of the series, m3, so that inflow volume = outflow volume + storage to round-off.

    Each step starts from Todini's first guess, O + (I' - I), and iterates the reference flow (I' + O') / 2 until
    the outflow settles to ``relative_tolerance``, at most ``route_iterations`` times; the paper repeats it twice.
    Nothing is clipped: a clipped ordinate would break the identity.
    """
    conveyance = math.sqrt(slope) / roughness
    upstream = inflow.copy()
    outflow = inflow.copy()
    storage = 0.0
    for _ in range(n_cells):
        outflow = np.empty_like(upstream)
        outflow[0] = upstream[0]
        depth = 1.0
        courant, reynolds, depth = corrected_numbers(
            HALF * (upstream[0] + outflow[0]), dt, dx, width, side, slope, conveyance, depth,
            depth_iterations, depth_tolerance, flow_floor, min_velocity,
        )  # fmt: skip
        wedge_old, prism_old = storage_weights(courant, reynolds, dt)
        wedge_new, prism_new = wedge_old, prism_old
        for step in range(1, len(upstream)):
            old_in = upstream[step - 1]
            new_in = upstream[step]
            old_out = outflow[step - 1]
            guess = old_out + (new_in - old_in)
            for _ in range(route_iterations):
                courant, reynolds, depth = corrected_numbers(
                    HALF * (new_in + guess), dt, dx, width, side, slope, conveyance, depth,
                    depth_iterations, depth_tolerance, flow_floor, min_velocity,
                )  # fmt: skip
                wedge_new, prism_new = storage_weights(courant, reynolds, dt)
                updated = (
                    (dt - TWO * wedge_new) * new_in
                    + (TWO * wedge_old + dt) * old_in
                    + (TWO * prism_old - dt) * old_out
                ) / (TWO * prism_new + dt)
                settled = abs(updated - guess) <= relative_tolerance * abs(updated)
                guess = updated
                if settled:
                    break
            outflow[step] = guess
            wedge_old, prism_old = wedge_new, prism_new
        storage += wedge_old * upstream[-1] + prism_old * outflow[-1]
        upstream = outflow
    return outflow, storage
