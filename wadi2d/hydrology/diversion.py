"""Diversions, HEC-HMS 4.12's five methods with its two limits. Interface: :class:`InflowDiversion`,
:class:`ConstantDiversion`, :class:`SpecifiedDiversion`, :class:`LateralWeirDiversion`, :class:`PumpStationDiversion`,
:class:`DiversionLimits`, each registered in the routing registry.

Every method gives what stays in the main channel and what is diverted, per ordinate. The rules, each read off HMS
4.12's own output on W72's test basins (``W72 HMS diversions/README.md``):

- the diverted flow never exceeds the inflow (HMS warns "diversion flow set to inflow");
- then the maximum flow caps it, then the maximum volume: the volume is the sum of each ordinate's flow times the
  step, from the first ordinate; the ordinate that would pass it diverts the remainder over its step, and none after;
- an inflow-diversion table is read linearly, and an inflow above its last row raises, as HMS refuses it (ERROR 42824);
- a lateral weir and a pump station read the channel stage from the channel rating at the flow that stays in the
  channel, solved with it each ordinate; a weir drowns by W67's submergence table on the tailwater rating read at the
  diverted flow;
- a pump station switches on when the stage of the whole inflow reaches its switch-on level, and pumps at that level's
  head on that ordinate; it switches off, pumping nothing, when its own draw would pull the stage under the switch-off
  level and the whole inflow stands under the switch-on level. When the whole inflow stands over the switch-on level
  at the same time, HMS holds the head at the switch-off level for a step or two by a rule not identified, so that
  case raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.routing import ROUTING_METHODS
from wadi2d.hydrology.structure_kernel import SUBMERGED_SHARE, SUBMERGENCE, WEIR_POWER
from wadi2d.storm.base import FloatArray

INFLOW_DIVERSION = "Inflow-Diversion Table"
CONSTANT_DIVERSION = "Constant Flow"
SPECIFIED_DIVERSION = "Specified Flow"
LATERAL_WEIR_DIVERSION = "Lateral Weir"
PUMP_STATION_DIVERSION = "Pump Station"
SOLVE_TOLERANCE_M3S = 1.0e-9
"""The flow solves of the weir and the pump stop within this, m3/s; HMS's own sit within 3e-4 (W72)."""


@dataclass(frozen=True)
class DiversionLimits:
    """HMS's two limits on any method, applied after it: m3/s, and m3 (HMS's file holds 1000 m3)."""

    max_flow_m3s: float | None = None
    max_volume_m3: float | None = None

    def apply(self, inflow_m3s: FloatArray, diverted_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        """What stays and what is diverted once the inflow, the flow cap and the volume cap have acted."""
        diverted = np.minimum(diverted_m3s, inflow_m3s)
        if self.max_flow_m3s is not None:
            diverted = np.minimum(diverted, self.max_flow_m3s)
        if self.max_volume_m3 is not None:
            dt = dt_minutes * SECONDS_PER_MINUTE
            before = np.concatenate(([0.0], np.cumsum(diverted * dt)[:-1]))
            room = np.maximum(self.max_volume_m3 - before, 0.0) / dt
            diverted = np.minimum(diverted, room)
        return inflow_m3s - diverted, diverted


def _monotonic(name: str, values: FloatArray) -> None:
    if np.any(np.diff(values) <= 0.0):
        raise ValueError(f"{name} must rise strictly to be read both ways")


@ROUTING_METHODS.register(INFLOW_DIVERSION)
@dataclass(frozen=True, eq=False)
class InflowDiversion:
    """A diverted flow for each inflow, read linearly."""

    inflows_m3s: FloatArray
    diverted_m3s: FloatArray
    limits: DiversionLimits = field(default_factory=DiversionLimits)

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        """What stays in the main channel and what is diverted, m3/s."""
        if inflow_m3s.max() > self.inflows_m3s[-1]:
            raise ValueError(
                f"{INFLOW_DIVERSION}: inflow {inflow_m3s.max():.1f} m3/s is above the table, which HMS refuses too"
            )
        diverted = np.interp(inflow_m3s, self.inflows_m3s, self.diverted_m3s)
        return self.limits.apply(inflow_m3s, diverted, dt_minutes)

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """What stays in the main channel, m3/s."""
        return self.branches(inflow_m3s, dt_minutes)[0]


@ROUTING_METHODS.register(CONSTANT_DIVERSION)
@dataclass(frozen=True, eq=False)
class ConstantDiversion:
    """A constant diverted flow, never more than the inflow."""

    rate_m3s: float
    limits: DiversionLimits = field(default_factory=DiversionLimits)

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        return self.limits.apply(inflow_m3s, np.full_like(inflow_m3s, self.rate_m3s), dt_minutes)

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        return self.branches(inflow_m3s, dt_minutes)[0]


@ROUTING_METHODS.register(SPECIFIED_DIVERSION)
@dataclass(frozen=True, eq=False)
class SpecifiedDiversion:
    """A flow gage's record as the diverted flow, never more than the inflow; ``start`` is the run's first ordinate.

    The record is read linearly in time; an ordinate outside it raises, as nothing says what HMS would divert there.
    """

    start: np.datetime64
    times: np.ndarray
    flows_m3s: FloatArray
    gage: str = ""
    limits: DiversionLimits = field(default_factory=DiversionLimits)

    def flows_at(self, n_times: int, dt_minutes: float) -> FloatArray:
        seconds = (self.times - self.start) / np.timedelta64(1, "s")
        at = np.arange(n_times) * dt_minutes * SECONDS_PER_MINUTE
        if at[0] < seconds[0] or at[-1] > seconds[-1]:
            raise ValueError(f"{SPECIFIED_DIVERSION}: the run lies outside gage {self.gage!r}'s record")
        return np.interp(at, seconds, self.flows_m3s)

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        return self.limits.apply(inflow_m3s, self.flows_at(inflow_m3s.size, dt_minutes), dt_minutes)

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        return self.branches(inflow_m3s, dt_minutes)[0]


@dataclass(frozen=True, eq=False)
class ChannelRating:
    """The channel at the diversion: stage, m, against flow, m3/s, both rising."""

    stages_m: FloatArray
    flows_m3s: FloatArray

    def __post_init__(self) -> None:
        _monotonic("a channel rating's stages", self.stages_m)
        _monotonic("a channel rating's flows", self.flows_m3s)

    def stage(self, flow_m3s: float) -> float:
        if flow_m3s > self.flows_m3s[-1]:
            raise ValueError(f"flow {flow_m3s:.1f} m3/s is above the rating table")
        return float(np.interp(flow_m3s, self.flows_m3s, self.stages_m))


def _solve_passed(inflow: float, diverted_at) -> tuple[float, float]:
    """(passed, diverted) with passed + diverted(passed) = inflow; diverted rises with passed, so the root is one."""
    if inflow <= 0.0:
        return inflow, 0.0
    excess = lambda p: p + diverted_at(p) - inflow  # noqa: E731
    if excess(0.0) >= 0.0:
        return 0.0, inflow
    if diverted_at(inflow) <= 0.0:
        return inflow, 0.0
    passed = brentq(excess, 0.0, inflow, xtol=SOLVE_TOLERANCE_M3S, rtol=4 * np.finfo(float).eps)
    return passed, inflow - passed


@ROUTING_METHODS.register(LATERAL_WEIR_DIVERSION)
@dataclass(frozen=True, eq=False)
class LateralWeirDiversion:
    """A broad-crested side weir, Q = C L H^1.5 with H the channel stage over the crest; ``tailwater`` (stage against
    diverted flow) drowns it by HMS's submergence table, none at and past full submergence."""

    channel: ChannelRating
    crest_m: float
    length_m: float
    coefficient: float
    tailwater: ChannelRating | None = None
    limits: DiversionLimits = field(default_factory=DiversionLimits)

    def free(self, stage_m: float) -> float:
        head = stage_m - self.crest_m
        return self.coefficient * self.length_m * head**WEIR_POWER if head > 0.0 else 0.0

    def over(self, stage_m: float) -> float:
        """The weir's flow at a channel stage, the tailwater solved with it."""
        free = self.free(stage_m)
        if free <= 0.0 or self.tailwater is None:
            return free
        head = stage_m - self.crest_m
        tailwater = self.tailwater

        def share(diverted: float) -> float:
            level = tailwater.stage(diverted)
            if level <= self.crest_m:
                return 1.0
            s = (level - self.crest_m) / head
            return 0.0 if s >= 1.0 else float(np.interp(s, SUBMERGENCE, SUBMERGED_SHARE))

        gap = lambda d: d - free * share(d)  # noqa: E731
        if gap(free) <= 0.0:
            return free
        return brentq(gap, 0.0, free, xtol=SOLVE_TOLERANCE_M3S, rtol=4 * np.finfo(float).eps)

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        diverted = np.zeros_like(inflow_m3s)
        for k, inflow in enumerate(inflow_m3s):
            diverted[k] = _solve_passed(float(inflow), lambda p: self.over(self.channel.stage(p)))[1]
        return self.limits.apply(inflow_m3s, diverted, dt_minutes)

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        return self.branches(inflow_m3s, dt_minutes)[0]


@ROUTING_METHODS.register(PUMP_STATION_DIVERSION)
@dataclass(frozen=True, eq=False)
class PumpStationDiversion:
    """``units`` identical pumps lifting from the channel: per unit the head-discharge table at
    (discharge elevation + equipment loss - channel stage). No minimum run or rest time and no tailwater: not measured."""

    channel: ChannelRating
    heads_m: FloatArray
    flows_m3s: FloatArray
    units: int
    on_m: float
    off_m: float
    lift_m: float
    """Discharge elevation plus equipment head loss, m."""
    limits: DiversionLimits = field(default_factory=DiversionLimits)

    def pumped(self, stage_m: float) -> float:
        return self.units * float(np.interp(self.lift_m - stage_m, self.heads_m, self.flows_m3s))

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        diverted = np.zeros_like(inflow_m3s)
        on = False
        for k, value in enumerate(inflow_m3s):
            inflow = float(value)
            whole = self.channel.stage(inflow)
            if not on:
                if whole >= self.on_m:
                    on = True
                    diverted[k] = min(self.pumped(self.on_m), inflow)
                continue
            passed, pumped = _solve_passed(inflow, lambda p: self.pumped(self.channel.stage(p)))
            if self.channel.stage(passed) >= self.off_m:
                diverted[k] = pumped
            elif whole < self.on_m:
                on = False
            else:
                raise ValueError(
                    f"{PUMP_STATION_DIVERSION}: at ordinate {k} the pumps would pull the stage under the switch-off "
                    f"level while the inflow stands over the switch-on level; HMS's rule there is not identified"
                )
        return self.limits.apply(inflow_m3s, diverted, dt_minutes)

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        return self.branches(inflow_m3s, dt_minutes)[0]
