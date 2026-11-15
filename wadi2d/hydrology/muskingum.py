"""Muskingum reach routing as HEC-HMS 4.12 computes it. Interface: :class:`Muskingum`, :data:`MUSKINGUM`,
:func:`stable_subreaches`, :func:`reach_notes`.

The method is two numbers and a count: K, the travel time of the flood wave through the reach, X, the weight of the
inflow in the reach's storage S = K [X I + (1 - X) O], and the number of subreaches. HMS routes each subreach with
K / n and the same X by the coefficient form of its Technical Reference Manual ("Muskingum Model", eq. 6; the same as
EM 1110-2-1417, eq. 9-16 to 9-19), at the control step, starting with outflow equal to inflow:

    O2 = C1 I2 + C2 I1 + C3 O1
    C1 = (dt - 2KX) / (2K(1-X) + dt),  C2 = (dt + 2KX) / (2K(1-X) + dt),  C3 = (2K(1-X) - dt) / (2K(1-X) + dt)

Measured on HEC-HMS 4.12 run headless (`W89 Muskingum routing`): the series above is HMS's to round-off (1e-12 m3/s
of 400) on fourteen cases, inside and outside the range 2KX <= dt <= 2K(1-X) of a subreach. Outside it HMS does not
refuse and does not correct: it prints WARNING 41169, "Muskingum routing is unstable with the given parameters", and
routes with the negative coefficient, so the outflow dips below the inflow's lowest value or rises above its peak,
and on a dry bed goes below zero (the element below then sets it to zero, WARNING 41201). This class does the same
and says so through :func:`reach_notes`; nothing is clipped, because a clipped ordinate would create water.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numba import njit

from wadi2d.hydrology.constants import MINUTES_PER_HOUR, SECONDS_PER_HOUR
from wadi2d.hydrology.model import Basin, Reach
from wadi2d.hydrology.routing import ROUTING_METHODS
from wadi2d.storm.base import FloatArray

MUSKINGUM = "Muskingum"
X_MIN, X_MAX = 0.0, 0.5
"""The range HMS takes: 0.0 is the most attenuation, a linear reservoir; 0.5 none, a wave that only travels (HMS
Technical Reference Manual; EM 1110-2-1417, paragraph 9-3c)."""
RANGE_GUARD = 1.0e-9
"""A step on the edge of the stable range counts as inside it: K / n equal to the step at X = 0.5 is the pure
translation HMS routes without a warning."""


@njit(cache=True)
def route_subreaches(inflow: np.ndarray, subreaches: int, c1: float, c2: float, c3: float) -> np.ndarray:
    """The coefficient form through every subreach in turn; each starts with outflow equal to inflow."""
    flow = inflow.copy()
    for _ in range(subreaches):
        out = np.empty_like(flow)
        out[0] = flow[0]
        for t in range(1, flow.size):
            out[t] = c1 * flow[t] + c2 * flow[t - 1] + c3 * out[t - 1]
        flow = out
    return flow


def stable_subreaches(k_hours: float, x: float, dt_minutes: float) -> tuple[int, int]:
    """The fewest and the most subreaches that keep 2KX <= dt <= 2K(1-X) in each; the most is 0 when the whole reach
    travels in under half a step, and no count is stable."""
    k_minutes = k_hours * MINUTES_PER_HOUR
    fewest = max(1, math.ceil(2.0 * k_minutes * x / dt_minutes - RANGE_GUARD))
    most = math.floor(2.0 * k_minutes * (1.0 - x) / dt_minutes + RANGE_GUARD)
    return fewest, most


@ROUTING_METHODS.register(MUSKINGUM)
@dataclass(frozen=True)
class Muskingum:
    """Muskingum with constant K and X, in ``subreaches`` equal parts, as HEC-HMS 4.12 routes it."""

    k_hours: float
    x: float
    subreaches: int = 1

    def __post_init__(self) -> None:
        if not (isinstance(self.k_hours, int | float) and math.isfinite(self.k_hours) and self.k_hours > 0.0):
            raise ValueError(f"Muskingum K {self.k_hours!r}: a travel time above zero, hours")
        if not (isinstance(self.x, int | float) and X_MIN <= self.x <= X_MAX):
            raise ValueError(f"Muskingum X {self.x!r}: between {X_MIN:g} and {X_MAX:g}")
        if not (isinstance(self.subreaches, int) and self.subreaches >= 1):
            raise ValueError(f"Muskingum subreaches {self.subreaches!r}: a whole number, 1 or more")

    def coefficients(self, dt_minutes: float) -> tuple[float, float, float]:
        """C1, C2 and C3 of one subreach: the weights of new inflow, old inflow and old outflow; they sum to one."""
        k = self.k_hours * MINUTES_PER_HOUR / self.subreaches
        denominator = 2.0 * k * (1.0 - self.x) + dt_minutes
        return (
            (dt_minutes - 2.0 * k * self.x) / denominator,
            (dt_minutes + 2.0 * k * self.x) / denominator,
            (2.0 * k * (1.0 - self.x) - dt_minutes) / denominator,
        )

    def stable_range_minutes(self) -> tuple[float, float]:
        """The steps a subreach is stable at, 2KX to 2K(1-X), minutes."""
        k = self.k_hours * MINUTES_PER_HOUR / self.subreaches
        return 2.0 * k * self.x, 2.0 * k * (1.0 - self.x)

    def is_stable(self, dt_minutes: float) -> bool:
        """Whether no coefficient is negative at this step."""
        low, high = self.stable_range_minutes()
        return low - RANGE_GUARD * dt_minutes <= dt_minutes <= high + RANGE_GUARD * dt_minutes

    def note(self, name: str, dt_minutes: float) -> str | None:
        """What a run says of this reach when a coefficient is negative; None inside the stable range."""
        if self.is_stable(dt_minutes):
            return None
        low, high = self.stable_range_minutes()
        fewest, most = stable_subreaches(self.k_hours, self.x, dt_minutes)
        if dt_minutes < low:
            what = (
                f"the step of {dt_minutes:g} min is under 2KX = {low:.3g} min of a subreach, so the new inflow's "
                "weight is negative and the outflow dips before it rises, below zero on a dry bed"
            )
        else:
            what = (
                f"the step of {dt_minutes:g} min is over 2K(1-X) = {high:.3g} min of a subreach, so the old "
                "outflow's weight is negative and the outflow swings about the inflow, below zero as a flood ends"
            )
        if fewest <= most:
            cure = f"{fewest} to {most} subreaches are stable at this step" if fewest < most else (
                f"{fewest} subreach{'es are' if fewest > 1 else ' is'} stable at this step")
        else:
            cure = "no number of subreaches is stable: the wave crosses the reach in under half a step"
        return (
            f"reach {name}: Muskingum routing is unstable with K {self.k_hours:g} h, X {self.x:g} and "
            f"{self.subreaches} subreach{'es' if self.subreaches > 1 else ''}: {what}. HEC-HMS warns the same "
            f"(41169) and routes it as given, and so does this run; {cure}"
        )

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """The outflow at the times of the inflow, m3/s."""
        c1, c2, c3 = self.coefficients(dt_minutes)
        return route_subreaches(np.ascontiguousarray(inflow_m3s, dtype=np.float64), self.subreaches, c1, c2, c3)

    def storage_m3(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """What the reach holds at each time, S = K [X I + (1 - X) O] summed over the subreaches, m3."""
        c1, c2, c3 = self.coefficients(dt_minutes)
        k_seconds = self.k_hours * SECONDS_PER_HOUR / self.subreaches
        flow = np.ascontiguousarray(inflow_m3s, dtype=np.float64)
        held = np.zeros_like(flow)
        for _ in range(self.subreaches):
            out = route_subreaches(flow, 1, c1, c2, c3)
            held += k_seconds * (self.x * flow + (1.0 - self.x) * out)
            flow = out
        return held


def reach_notes(basin: Basin, dt_minutes: float) -> list[str]:
    """The warning of every Muskingum reach of a basin that is outside its stable range at this step."""
    notes = []
    for name, element in basin.elements.items():
        if isinstance(element, Reach) and isinstance(element.routing, Muskingum):
            note = element.routing.note(name, dt_minutes)
            if note is not None:
                notes.append(note)
    return notes
