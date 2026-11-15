"""Rain whose named subbasins read the area reduction at an area of their own. Interface: :class:`OwnAreas`.

HMS's depth-area analysis at a dam runs everything above the dam with the storm area set to the dam's drainage area.
In one run with a grid below the dams, each subbasin above a dam takes that dam's area this way, and the rest of the
model, the 2D cells and the other subbasins, the storm's own area (``hydrology.subbasins[].storm_area_km2``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from wadi2d.storm.base import Storm, SubbasinRain


@dataclass(frozen=True, eq=False)
class OwnAreas:
    """``rain`` as it is, except over the subbasins of ``areas_km2``, which read it at their own area."""

    rain: SubbasinRain
    areas_km2: Mapping[str, float]
    _storms: dict[str, Storm] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        own = {name: self.rain.over(name).at_area(area) for name, area in self.areas_km2.items()}
        object.__setattr__(self, "_storms", own)

    def over(self, subbasin: str) -> Storm:
        """The storm over one subbasin: at its own area if it has one."""
        if subbasin in self._storms:
            return self._storms[subbasin]
        return self.rain.over(subbasin)

    def at_area(self, area_km2: float) -> OwnAreas:
        """The rest of the rain at ``area_km2``; the named subbasins keep their own area."""
        return OwnAreas(self.rain.at_area(area_km2), self.areas_km2)
