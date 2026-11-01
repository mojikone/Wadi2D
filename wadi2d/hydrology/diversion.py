"""Diversions. Interface: :class:`InflowDiversion`, registered in the routing registry.

The diverted flow is the inflow-diversion table read at the inflow; the rest stays in the main channel. An inflow
above the table raises: what HMS does there is not known.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.hydrology.routing import ROUTING_METHODS
from wadi2d.storm.base import FloatArray

INFLOW_DIVERSION = "Inflow-Diversion Table"


@ROUTING_METHODS.register(INFLOW_DIVERSION)
@dataclass(frozen=True, eq=False)
class InflowDiversion:
    """A diverted flow for each inflow, read linearly."""

    inflows_m3s: FloatArray
    diverted_m3s: FloatArray

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        """What stays in the main channel and what is diverted, m3/s."""
        if inflow_m3s.max() > self.inflows_m3s[-1]:
            raise ValueError(f"{INFLOW_DIVERSION}: inflow {inflow_m3s.max():.1f} m3/s is above the table")
        diverted = np.interp(inflow_m3s, self.inflows_m3s, self.diverted_m3s)
        return inflow_m3s - diverted, diverted

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """What stays in the main channel, m3/s."""
        return self.branches(inflow_m3s, dt_minutes)[0]
