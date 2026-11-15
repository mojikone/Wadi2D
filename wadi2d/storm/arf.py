"""Area-reduction factors. Interface: :class:`ArfTable`, :class:`GivenFactor`, :func:`factor_at`."""

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

    def step_areas(self, low_km2: float, high_km2: float, largest_change: float) -> list[float]:
        """Storm areas from ``low_km2`` to ``high_km2``, both included, with the factor changing by at most
        ``largest_change`` between neighbours, in as few runs as that allows.

        The factor is read as :meth:`factor` reads it, so the bound holds on the factors the runs apply. The table's
        total change over the span is split into equal steps of at most ``largest_change``: no run sits a hair below
        the end, which a greedy walk leaves. A factor that rises again is counted by its whole path, up and down.
        """
        if largest_change <= 0.0:
            raise ValueError("the largest change of the area-reduction factor must be above zero")
        if high_km2 <= low_km2 * (1.0 + 1e-9):
            return [float(low_km2)]
        first = float(self.areas_km2[0])
        knots = sorted({float(low_km2), float(high_km2), *(float(a) for a in self.areas_km2 if low_km2 < a < high_km2)})
        values = [self.factor(a) for a in knots]
        if not self.reduces_below_table and low_km2 < first < high_km2:  # the whole depth just below the first area
            at = knots.index(first)
            knots.insert(at, first)
            values.insert(at, 1.0)
        path = np.concatenate(([0.0], np.cumsum(np.abs(np.diff(values)))))
        steps = max(1, int(np.ceil(path[-1] / largest_change - 1e-9)))
        found = [float(low_km2)]
        for target in path[-1] * np.arange(1, steps) / steps:
            k = int(np.searchsorted(path, target, side="left"))  # the segment whose path reaches the target
            k = min(max(k, 1), len(knots) - 1)
            share = (target - path[k - 1]) / (path[k] - path[k - 1]) if path[k] > path[k - 1] else 1.0
            found.append(float(knots[k - 1] + share * (knots[k] - knots[k - 1])))
        found.append(float(high_km2))
        return sorted(set(found))


@dataclass(frozen=True)
class GivenFactor:
    """One factor the user gives, at every storm area (W83, his word of 2026-11-15: 0.7 is a 30 % reduction).

    It answers :meth:`ArfTable.factor` at any area, so a storm takes it where it would take a table; it needs no storm
    area, and a depth-area study refuses it, since every run would be the same run.
    """

    value: float

    def __post_init__(self) -> None:
        if not 0.0 < self.value <= 1.0:
            raise ValueError("a given area-reduction factor lies above 0 and at most 1")

    def factor(self, _area_km2: float | None = None) -> float:
        """The factor, whatever the area."""
        return self.value


def factor_at(arf: ArfTable | GivenFactor | None, area_km2: float | None) -> float:
    """What a storm's depths are multiplied by: 1 with no reduction, or a table with no storm area; the given factor
    always; else the table at the area."""
    if arf is None:
        return 1.0
    if isinstance(arf, GivenFactor):
        return arf.value
    if area_km2 is None:
        return 1.0
    return arf.factor(area_km2)
