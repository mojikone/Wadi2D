"""Area-reduction factors. Interface: :class:`ArfTable`."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.storm.base import FloatArray


@dataclass(frozen=True, eq=False)
class ArfTable:
    """A (storm area, factor) table, read by linear interpolation in area.

    Linear is what HMS does with a user ``Area-Reduction Factor`` table: it reproduces every factor HMS logged
    on Block 2 to 2e-6. Beyond the table the end factor holds, unless ``reduces_below_table`` is False, which is
    what HMS does at the small end: below the smallest area it logs `No area reduction performed` and the depth
    stays whole (Block 6, 0.789 km2, against a first factor of 0.999). Its behaviour above the largest area is
    unverified; no project reaches it.
    """

    areas_km2: FloatArray
    factors: FloatArray
    reduces_below_table: bool = True

    def __post_init__(self) -> None:
        if len(self.areas_km2) != len(self.factors) or len(self.areas_km2) < 1:
            raise ValueError("an ARF table needs one factor per area")
        if np.any(np.diff(self.areas_km2) <= 0.0):
            raise ValueError("ARF table areas must increase")

    def factor(self, area_km2: float) -> float:
        """The factor at ``area_km2``."""
        if area_km2 < self.areas_km2[0] and not self.reduces_below_table:
            return 1.0
        return float(np.interp(area_km2, self.areas_km2, self.factors))
