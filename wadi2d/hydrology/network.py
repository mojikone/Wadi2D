"""The lumped engine: a storm through a network. Interface: :class:`LumpedEngine`, :class:`Run`."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field

import numpy as np

from wadi2d.hydrology.model import Basin, Branching, Element, Junction, Reach, Subbasin, TimeGrid
from wadi2d.hydrology.transforms import convolve
from wadi2d.storm.base import FloatArray, Storm, SubbasinRain


@dataclass(frozen=True)
class SubbasinWater:
    """The period-ending depths of one subbasin, mm."""

    precipitation: FloatArray
    excess: FloatArray

    @property
    def loss(self) -> FloatArray:
        """Rain that did not run off, mm per step."""
        return self.precipitation - self.excess


@dataclass(frozen=True)
class Run:
    """What one run produced: outflow, second outflow and combined inflow by element, depths by subbasin."""

    grid: TimeGrid
    outflow: dict[str, FloatArray] = field(default_factory=dict)
    branched: dict[str, FloatArray] = field(default_factory=dict)
    inflow: dict[str, FloatArray] = field(default_factory=dict)
    water: dict[str, SubbasinWater] = field(default_factory=dict)


class LumpedEngine:
    """Runs a basin; unit hydrographs are cached per (subbasin, step), so repeated runs stay cheap."""

    def __init__(self, basin: Basin) -> None:
        self.basin = basin
        self._unit_hydrographs: dict[tuple[str, float], FloatArray] = {}

    def run(
        self,
        storm: SubbasinRain | None,
        grid: TimeGrid,
        only: Iterable[str] | None = None,
        external: Mapping[str, FloatArray] | None = None,
        cut: Collection[tuple[str, str]] = (),
    ) -> Run:
        """Compute every element, or the given sub-network.

        ``external`` adds a series to the inflow of an element, and ``cut`` holds (parent, element) links that carry
        no water. A hand-back uses both; without them the arithmetic is the plain network's. ``storm`` may be None
        when no subbasin is computed.
        """
        result = Run(grid)
        depths: dict[Storm, FloatArray] = {}
        for name in self.basin.topological_order(only):
            self._compute(self.basin.elements[name], storm, depths, result, external or {}, cut)
        return result

    def _inflow(
        self, name: str, result: Run, external: Mapping[str, FloatArray], cut: Collection[tuple[str, str]]
    ) -> FloatArray:
        inflow = np.zeros(result.grid.n_times, dtype=np.float64)
        for parent in self.basin.upstream[name]:
            if parent in result.outflow and (parent, name) not in cut:
                flows = result.outflow if self.basin.elements[parent].downstream == name else result.branched
                inflow = inflow + flows[parent]
        if name in external:
            inflow = inflow + external[name]
        return inflow

    def _compute(
        self,
        element: Element,
        storm: SubbasinRain | None,
        depths: dict[Storm, FloatArray],
        result: Run,
        external: Mapping[str, FloatArray],
        cut: Collection[tuple[str, str]],
    ) -> None:
        grid = result.grid
        name = element.name
        inflow = self._inflow(name, result, external, cut)
        result.inflow[name] = inflow
        if isinstance(element, Subbasin):
            if storm is None:
                raise ValueError(f"subbasin {name} needs a storm")
            over = storm.over(name)
            if over not in depths:
                depths[over] = over.increments(grid.dt_minutes, grid.n_intervals)
            rain = depths[over]
            excess = element.loss.excess(rain)
            result.water[name] = SubbasinWater(rain, excess)
            direct = convolve(excess, self._unit_hydrograph(element, grid.dt_minutes), grid.n_times)
            outflow = element.baseflow.total_flow(direct, grid.dt_minutes, element.area_km2)
            result.outflow[name] = inflow + outflow
        elif isinstance(element, Reach):
            result.outflow[name] = element.routing.route(inflow, grid.dt_minutes)
        elif isinstance(element, Branching):
            result.outflow[name], result.branched[name] = element.routing.branches(inflow, grid.dt_minutes)
        elif isinstance(element, Junction):
            result.outflow[name] = inflow
        else:
            raise TypeError(f"no computation for {type(element).__name__}")

    def _unit_hydrograph(self, subbasin: Subbasin, dt_minutes: float) -> FloatArray:
        key = (subbasin.name, dt_minutes)
        if key not in self._unit_hydrographs:
            self._unit_hydrographs[key] = subbasin.transform.unit_hydrograph(subbasin.area_km2, dt_minutes)
        return self._unit_hydrographs[key]
