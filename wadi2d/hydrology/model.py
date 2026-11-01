"""The lumped network: elements, connectivity, the time grid.

Interface: :class:`Basin`, :class:`Subbasin`, :class:`Reach`, :class:`Junction`, :class:`Reservoir`,
:class:`Diversion`, :class:`TimeGrid`. Elements are plain data holding method objects from the registries; nothing
here computes a flow. SI units with km2 and minutes, as the HMS files carry them.

A reservoir outlet or a diversion can send water to a second element. Such a branch feeds the network but not the
drainage area: on Block 6, HMS lists every element above a branch under an analysis point and computes them, while
its storm area counts only what reaches the point through `Downstream` links.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from wadi2d.hydrology.baseflow import BaseflowMethod, NoBaseflow
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.losses import LossMethod
from wadi2d.hydrology.routing import RoutingMethod
from wadi2d.hydrology.transforms import TransformMethod
from wadi2d.storm.base import FloatArray


@dataclass(frozen=True)
class TimeGrid:
    """A run of ``n_intervals`` steps of ``dt_minutes``; flows live on ``n_intervals + 1`` times."""

    dt_minutes: float
    n_intervals: int

    @property
    def dt_seconds(self) -> float:
        """The step, s."""
        return self.dt_minutes * SECONDS_PER_MINUTE

    @property
    def n_times(self) -> int:
        """Flow ordinates, both ends of the run included."""
        return self.n_intervals + 1

    @property
    def minutes(self) -> FloatArray:
        """The time of every flow ordinate, minutes from the start."""
        return self.dt_minutes * np.arange(self.n_times, dtype=np.float64)


@dataclass(frozen=True)
class Element:
    """What every element has: a name and where it drains; None at an outlet."""

    name: str
    downstream: str | None


@dataclass(frozen=True)
class Subbasin(Element):
    """A lumped subbasin."""

    area_km2: float
    loss: LossMethod
    transform: TransformMethod
    baseflow: BaseflowMethod = field(default_factory=NoBaseflow)


@dataclass(frozen=True)
class Reach(Element):
    """A channel reach."""

    routing: RoutingMethod


@dataclass(frozen=True)
class Junction(Element):
    """A junction: its outflow is the sum of its inflows."""


class BranchingMethod(Protocol):
    """What an element with two ways out computes."""

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        """The flow to ``downstream`` and the flow to ``branch`` at the times of the inflow, m3/s."""
        ...


@dataclass(frozen=True)
class Branching(Element):
    """An element with a second way out; ``branch`` names its target, None when there is none."""

    routing: BranchingMethod
    branch: str | None = None


@dataclass(frozen=True)
class Reservoir(Branching):
    """A reservoir; ``branch`` receives the auxiliary outlet."""


@dataclass(frozen=True)
class Diversion(Branching):
    """A diversion; ``branch`` receives the diverted flow."""


def _targets(element: Element) -> list[str]:
    """Where an element sends water."""
    second = element.branch if isinstance(element, Branching) else None
    return [target for target in (element.downstream, second) if target is not None]


class Basin:
    """A network of elements in file order."""

    def __init__(self, name: str, elements: Iterable[Element]) -> None:
        self.name = name
        self.elements: dict[str, Element] = {element.name: element for element in elements}
        self.upstream: dict[str, list[str]] = {name: [] for name in self.elements}
        self.main_upstream: dict[str, list[str]] = {name: [] for name in self.elements}
        for element in self.elements.values():
            targets = _targets(element)
            if len(set(targets)) != len(targets):
                raise ValueError(f"{element.name} sends both its outflows to {targets[0]}")
            for target in targets:
                if target not in self.elements:
                    raise ValueError(f"{element.name} drains to unknown element {target}")
                self.upstream[target].append(element.name)
            if element.downstream is not None:
                self.main_upstream[element.downstream].append(element.name)

    @property
    def subbasins(self) -> Mapping[str, Subbasin]:
        """The subbasins by name."""
        return {name: e for name, e in self.elements.items() if isinstance(e, Subbasin)}

    def topological_order(self, only: Iterable[str] | None = None) -> list[str]:
        """Every element after all its upstream elements; ties keep file order. A cycle raises."""
        chosen = set(self.elements if only is None else only)
        pending = {name: sum(u in chosen for u in self.upstream[name]) for name in chosen}
        ready = [name for name in self.elements if name in chosen and pending[name] == 0]
        order: list[str] = []
        while ready:
            name = ready.pop(0)
            order.append(name)
            for target in _targets(self.elements[name]):
                if target in pending:
                    pending[target] -= 1
                    if pending[target] == 0:
                        ready.append(target)
        if len(order) != len(chosen):
            raise ValueError(f"cycle in basin {self.name}: {sorted(chosen - set(order))}")
        return order

    @staticmethod
    def _walk(links: Mapping[str, list[str]], name: str) -> set[str]:
        found = {name}
        stack = [name]
        while stack:
            for parent in links[stack.pop()]:
                if parent not in found:
                    found.add(parent)
                    stack.append(parent)
        return found

    def upstream_of(self, name: str) -> set[str]:
        """The element and everything that sends it water, branches included: what must be computed."""
        return self._walk(self.upstream, name)

    def drainage_area(self, name: str) -> float:
        """The area of the subbasins above an element through `Downstream` links only, km2."""
        chosen = self._walk(self.main_upstream, name)
        return sum(subbasin.area_km2 for key, subbasin in self.subbasins.items() if key in chosen)
