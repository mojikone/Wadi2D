"""Constants of the validation package, each defined once.

``G`` lives here only until ``wadi2d.config.constants`` exists; that module will own it and this one will
import it from there, so no other file of the package may spell the number.
"""

from __future__ import annotations

G: float = 9.80665
"""Standard gravity, m/s2. To be owned by ``wadi2d.config.constants``."""

WET_DEPTH: float = 1.0e-3
"""Depth above which a cell counts as wet in the metrics, m."""

STEADY_SPINUP_TRAVERSALS: float = 20.0
"""Domain traversals by a long wave allowed for a steady case to settle."""

WAVE_ARRIVAL_SAFETY: float = 0.8
"""Fraction of the first wave arrival at the domain edge used as end time of a dam-break case."""
