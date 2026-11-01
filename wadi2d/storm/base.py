"""What a storm is to the hydrology: a cumulative depth curve in time.

Interface: :class:`Storm`, :class:`CumulativeStorm`, :data:`STORM_METHODS`. All depths are mm, all times are
minutes from the start of the storm. An increment is period-ending: element ``k`` of :meth:`Storm.increments`
is the depth that falls between ``k dt`` and ``(k + 1) dt``, stamped at the end of that period as HEC-HMS does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, Self, runtime_checkable

import numpy as np
from numpy.typing import ArrayLike, NDArray

from wadi2d.storm.registry import Registry

FloatArray = NDArray[np.float64]


@runtime_checkable
class Storm(Protocol):
    """A rainfall event over a catchment."""

    @property
    def total_depth(self) -> float:
        """Total depth after any area reduction, mm."""
        ...

    def cumulative_depth(self, minutes: ArrayLike) -> FloatArray:
        """Depth fallen by each time, mm."""
        ...

    def increments(self, dt_minutes: float, n_intervals: int) -> FloatArray:
        """Period-ending depths of ``n_intervals`` steps of ``dt_minutes``, mm."""
        ...

    def at_area(self, area_km2: float) -> Self:
        """The same storm with its storm area set to ``area_km2``."""
        ...


class CumulativeStorm(ABC):
    """Gives a storm its increments from its cumulative curve, so they sum to the curve exactly."""

    @abstractmethod
    def cumulative_depth(self, minutes: ArrayLike) -> FloatArray:
        """Depth fallen by each time, mm."""

    def increments(self, dt_minutes: float, n_intervals: int) -> FloatArray:
        """Period-ending depths of ``n_intervals`` steps of ``dt_minutes``, mm."""
        edges = dt_minutes * np.arange(n_intervals + 1, dtype=np.float64)
        return np.diff(self.cumulative_depth(edges))


STORM_METHODS: Registry[Storm] = Registry("storm")
"""Storm builders by method name."""
