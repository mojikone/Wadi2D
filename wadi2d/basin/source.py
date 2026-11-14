"""A source element (W73): an external hydrograph entering the lumped network at a junction, HEC-HMS's Source with a
discharge gage.

The lumped engine has no element of its own for it, so a source runs as a reach with no inflow whose routing returns
its hydrograph: :class:`SourceHydrograph`, registered in the routing registry. ``basin.json`` carries the hydrograph
itself (``minutes`` from the start of the run and ``flow_m3s``), read from the point's file when the basin was generated,
so a run never depends on that file. Read linearly between its times; before its first time and after its last the
source gives nothing.

Interface: :data:`SOURCE_HYDROGRAPH`, :class:`SourceHydrograph`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.hydrology.routing import ROUTING_METHODS
from wadi2d.storm.base import FloatArray

SOURCE_HYDROGRAPH = "Source hydrograph"


@ROUTING_METHODS.register(SOURCE_HYDROGRAPH)
@dataclass(frozen=True, eq=False)
class SourceHydrograph:
    """A hydrograph at the times of a run, whatever flows in."""

    minutes: FloatArray
    flow_m3s: FloatArray

    def __post_init__(self) -> None:
        if self.minutes.size != self.flow_m3s.size or self.minutes.size < 2:
            raise ValueError("a source hydrograph needs two times or more, one flow per time")
        if np.any(np.diff(self.minutes) <= 0.0):
            raise ValueError("a source hydrograph's times must rise")

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """The inflow, nothing at a source, plus the hydrograph, m3/s."""
        times = np.arange(inflow_m3s.size, dtype=np.float64) * dt_minutes
        return inflow_m3s + np.interp(times, self.minutes, self.flow_m3s, left=0.0, right=0.0)
