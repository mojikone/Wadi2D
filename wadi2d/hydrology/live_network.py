"""The part of a lumped network that runs during a 2D run: below a hand-back, down to a re-entry or the end.

Interface: :func:`plan_routes`, :class:`Routes`, :class:`LiveNetwork`, :class:`Accounts`. Nothing here knows the grid:
a line's water arrives as a series on the time grid of the network, one ordinate per step.

Everything above a hand-back's element reaches it through the grid, so the links into that element are cut. A
re-entry hands its outflow to the grid, so the link below it is cut too: water runs in the network between the two
and nowhere else, which is the owner's double-count rule.

Routing methods are causal: outflow k depends on inflows up to k. So the network reruns on the series so far, and no
method needs a streaming form or a saved state; a checkpoint keeps the series and loses nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np

from wadi2d.hydrology.model import Basin, Branching, Reach, Subbasin, TimeGrid
from wadi2d.hydrology.network import LumpedEngine, Run
from wadi2d.storm.base import FloatArray

DRAIN_STEPS = 64
"""Steps of the first attempt to drain the network after the run."""
DRAIN_ROUNDS = 8
"""Doublings of the drain before what is left stays where it is."""
DRAINED_M3S = 1e-6
"""A reach below this flow has drained."""


@dataclass(frozen=True)
class Routes:
    """What hand-backs do to a network."""

    live: tuple[str, ...]
    """Elements that run during the 2D run, each after everything above it."""
    cut: frozenset[tuple[str, str]]
    """Links that carry no water: (parent, element)."""
    ends: tuple[tuple[str, bool], ...]
    """Where water leaves the network other than to the grid: (element, True for its second outlet)."""
    above: tuple[str, ...]
    """Elements a hand-back enters."""


def plan_routes(basin: Basin, entries: Iterable[str], exits: Iterable[str]) -> Routes:
    """Walk down from each hand-back's element to a re-entry or the end of the network; a route that cannot hold water
    honestly raises, in words.
    """
    above = tuple(dict.fromkeys(entries))
    leaving = set(exits)
    for name in above:
        if name not in basin.elements:
            raise ValueError(f"hand-back into unknown element {name}")
    cut = {(parent, name) for name in above for parent in basin.upstream[name]}
    live: set[str] = set()
    ends: list[tuple[str, bool]] = []
    stack = list(above)
    while stack:
        name = stack.pop()
        if name in live:
            continue
        element = basin.elements[name]
        if isinstance(element, Subbasin):
            raise ValueError(
                f"a hand-back's route runs through subbasin {name}: a subbasin takes no live inflow; "
                "give the route a re-entry above it"
            )
        live.add(name)
        main = element.downstream
        second = element.branch if isinstance(element, Branching) else None
        if name in leaving:
            if main is not None:
                cut.add((name, main))
                main = None
        elif main is None:
            ends.append((name, False))
        if isinstance(element, Branching) and second is None:
            ends.append((name, True))
        for target in (main, second):
            if target is None:
                continue
            if target in above:
                raise ValueError(
                    f"water routed through {name} reaches {target}, where a hand-back replaces all that arrives: "
                    f"it would be lost. Give that route a re-entry above {target}."
                )
            stack.append(target)
    for name in leaving - live:
        target = basin.elements[name].downstream
        if target in live:
            cut.add((name, target))
    return Routes(tuple(basin.topological_order(live)), frozenset(cut), tuple(ends), above)


class NoRain:
    """The storm of a job with no rain: a network still has its subbasins, and they give nothing."""

    def over(self, _subbasin: str) -> NoRain:
        return self

    def increments(self, _dt_minutes: float, n_intervals: int) -> FloatArray:
        return np.zeros(n_intervals)


def _padded(series: FloatArray, n: int) -> FloatArray:
    """The first n ordinates, with zeros after the end of the series."""
    if series.size >= n:
        return series[:n]
    return np.concatenate((series, np.zeros(n - series.size)))


@dataclass(frozen=True)
class Accounts:
    """The network's books at the end of a run, m3."""

    lateral: float
    """What lumped subbasins put into the live part."""
    storage: float
    """Water still in it: what would yet drain out, and what a reservoir keeps."""
    defect: float
    """What came in and neither left nor is stored: the routing method's own mass error."""
    drained: bool
    """False when reaches still ran after the longest drain; ``defect`` then holds what was left in them."""


class LiveNetwork:
    """``base`` is the network run once before the 2D run, with the routes' links cut and nothing from the grid.

    ``reentries`` holds the inflows where the routes end, by name: element.
    """

    def __init__(self, basin: Basin, routes: Routes, base: Run, reentries: Mapping[str, str]) -> None:
        self.basin = basin
        self.routes = routes
        self.reentries = dict(reentries)
        self.grid = base.grid
        self.engine = LumpedEngine(basin)
        self.lateral = self._frozen(base)

    def _frozen(self, base: Run) -> dict[str, FloatArray]:
        """What elements outside the live part send into it: known before the run, and untouched by the grid."""
        live = set(self.routes.live)
        out: dict[str, FloatArray] = {}
        for name in self.routes.live:
            for parent in self.basin.upstream[name]:
                if parent in live or (parent, name) in self.routes.cut:
                    continue
                main = self.basin.elements[parent].downstream == name
                flow = (base.outflow if main else base.branched)[parent]
                out[name] = out.get(name, 0.0) + flow
        return out

    def route(self, inflow: Mapping[str, FloatArray], lateral_through: int | None = None) -> Run:
        """The live part on the series so far; every series holds the same ordinates from time zero.

        ``lateral_through`` stops the frozen flows after that ordinate, for a drain after a run that stopped early.
        """
        n = max(series.size for series in inflow.values())
        external = {}
        for name, flow in self.lateral.items():
            kept = flow if lateral_through is None else flow[: lateral_through + 1]
            external[name] = _padded(kept, n)
        for name, series in inflow.items():
            external[name] = external[name] + series if name in external else series
        grid = TimeGrid(self.grid.dt_minutes, n - 1)
        return self.engine.run(None, grid, self.routes.live, external, self.routes.cut)

    def _exits(self, run: Run) -> FloatArray:
        """Everything leaving the live part at each ordinate."""
        total = np.zeros(run.grid.n_times)
        for name in self.reentries.values():
            total = total + run.outflow[name]
        for name, second in self.routes.ends:
            total = total + (run.branched if second else run.outflow)[name]
        return total

    def _drained(self, run: Run) -> bool:
        reaches = (n for n in self.routes.live if isinstance(self.basin.elements[n], Reach))
        return all(abs(run.outflow[name][-1]) <= DRAINED_M3S for name in reaches)

    def _drain(self, inflow: Mapping[str, FloatArray], through: int) -> tuple[Run, bool]:
        """The route run on until the reaches are empty: the inflow stops, and with it the frozen flows."""
        extra = DRAIN_STEPS
        for _round in range(DRAIN_ROUNDS):
            n = through + 1 + extra
            run = self.route({name: _padded(s, n) for name, s in inflow.items()}, through)
            if self._drained(run):
                return run, True
            extra *= 2
        return run, False

    def _kept(self, run: Run) -> float:
        """What reservoirs hold at the end of the drain, by their own continuity."""
        dt = run.grid.dt_seconds
        kept = 0.0
        for name in self.routes.live:
            if isinstance(self.basin.elements[name], Branching):
                gone = run.outflow[name] + run.branched[name]
                kept += float(np.trapezoid(run.inflow[name] - gone, dx=dt))
        return kept

    def settle(
        self, inflow: Mapping[str, FloatArray], line_m3: float, through: int, left_m3: float
    ) -> Accounts:
        """The books at the end of a run. ``line_m3`` crossed the lines, ``left_m3`` has left the network so far.

        Storage is measured, not taken as the difference: the network is drained and what comes out is what was in
        it. So the defect is a true number, not zero by construction. A plain lag gives exactly zero; a variable
        Muskingum-Cunge does not conserve volume to the last drop, and this says by how much.
        """
        run, drained = self._drain(inflow, through)
        dt = run.grid.dt_seconds
        total_out = float(self._exits(run).sum()) * dt
        kept = self._kept(run)
        lateral = sum(float(flow[: through + 1].sum()) * dt for flow in self.lateral.values())
        storage = total_out - left_m3 + kept
        return Accounts(lateral, storage, line_m3 + lateral - left_m3 - storage, drained)
