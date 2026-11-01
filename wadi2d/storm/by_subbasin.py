"""One pattern and one area reduction, a depth for each subbasin. Interface: :class:`StormBySubbasin`.

HMS's `Uniform Depth: No`: the depth of a precipitation-frequency grid is averaged over each subbasin on its own,
not over everything above the analysis point. Reproduces all 168 subbasin depths HMS logged on Majlas and Block 6.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Self

from wadi2d.storm.base import Storm
from wadi2d.storm.hypothetical import HypotheticalStorm


@dataclass(frozen=True, eq=False)
class StormBySubbasin:
    """``storm`` gives the pattern and the area reduction, ``depths_mm`` the point depth over each subbasin."""

    storm: HypotheticalStorm
    depths_mm: Mapping[str, float]
    _storms: dict[str, HypotheticalStorm] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        storms = {name: replace(self.storm, depth_mm=depth) for name, depth in self.depths_mm.items()}
        object.__setattr__(self, "_storms", storms)

    def over(self, subbasin: str) -> Storm:
        """The storm over one subbasin; one with no depth raises."""
        if subbasin not in self._storms:
            raise KeyError(f"no storm depth for subbasin {subbasin}")
        return self._storms[subbasin]

    def at_area(self, area_km2: float) -> Self:
        """The same storm with its storm area set to ``area_km2``."""
        return replace(self, storm=self.storm.at_area(area_km2))
