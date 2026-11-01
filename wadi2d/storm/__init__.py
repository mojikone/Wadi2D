"""Rainfall: storms as cumulative depth curves, area reduction, the registry of storm methods."""

from __future__ import annotations

from wadi2d.storm.arf import ArfTable
from wadi2d.storm.base import STORM_METHODS, CumulativeStorm, Storm, SubbasinRain
from wadi2d.storm.by_subbasin import StormBySubbasin
from wadi2d.storm.hypothetical import HYPOTHETICAL_STORM, HypotheticalStorm, PercentPattern
from wadi2d.storm.registry import Registry
from wadi2d.storm.uniform import UNIFORM_STORM, UniformStorm

__all__ = [
    "HYPOTHETICAL_STORM",
    "STORM_METHODS",
    "UNIFORM_STORM",
    "ArfTable",
    "CumulativeStorm",
    "HypotheticalStorm",
    "PercentPattern",
    "Registry",
    "Storm",
    "StormBySubbasin",
    "SubbasinRain",
    "UniformStorm",
]
