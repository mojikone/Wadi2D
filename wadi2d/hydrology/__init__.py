"""Lumped hydrology: HEC-HMS methods on a network of elements, and the depth-area analysis."""

from __future__ import annotations

from wadi2d.hydrology.baseflow import BASEFLOW_METHODS
from wadi2d.hydrology.depth_area import PointResult, analyse, analyse_point, point_storm
from wadi2d.hydrology.losses import LOSS_METHODS
from wadi2d.hydrology.model import Basin, Junction, Reach, Subbasin, TimeGrid
from wadi2d.hydrology.network import LumpedEngine, Run
from wadi2d.hydrology.routing import ROUTING_METHODS
from wadi2d.hydrology.transforms import TRANSFORM_METHODS

__all__ = [
    "BASEFLOW_METHODS",
    "LOSS_METHODS",
    "ROUTING_METHODS",
    "TRANSFORM_METHODS",
    "Basin",
    "Junction",
    "LumpedEngine",
    "PointResult",
    "Reach",
    "Run",
    "Subbasin",
    "TimeGrid",
    "analyse",
    "analyse_point",
    "point_storm",
]
