"""The surface of a shaped object: one formula for all of them.

Across a section two surfaces bound the new ground: ``high``, the cut (bed, then the inner slope carried up without
end) and ``low``, the fill (inner slope, crest, outer slope). The new ground is the old ground clamped between them,
so each pixel settles itself: above the cut it is cut, below the fill it is filled, between them it stays. A channel
has only ``high``, an embankment only ``low``, a channel with dykes both, and a bank turns from dyke to cut exactly
where the ground passes its top, with no step.
"""

from __future__ import annotations

import numpy as np

from wadi2d.terrain.sections import SectionAt


def rise(run: np.ndarray, slope: np.ndarray) -> np.ndarray:
    """Height gained over ``run`` on a slope of ``slope`` H:V; a vertical slope gains everything at once."""
    run = np.maximum(np.asarray(run, dtype=np.float64), 0.0)
    slope = np.asarray(slope, dtype=np.float64)
    out = np.where(run > 0.0, np.inf, 0.0)
    return np.divide(run, slope, out=out, where=slope > 0.0)


def crest_edge(section: SectionAt) -> np.ndarray:
    """Offset where the inner slope reaches the top: the inner edge of a dyke crest."""
    return section.half + section.inner * (section.top - section.bed)


def cut_surface(section: SectionAt, a: np.ndarray) -> np.ndarray:
    """The bed, then the inner slope carried up."""
    return section.bed + rise(a - section.half, section.inner)


def fill_surface(section: SectionAt, edge: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Flat at the top out to the crest's outer edge, then the outer slope down."""
    return section.top - rise(a - edge - section.crest, section.outer)


def nose_surface(section: SectionAt, edge: np.ndarray, a: np.ndarray, gap: np.ndarray) -> np.ndarray:
    """A raised part ``gap`` past its last section: the outer slope carried round the end of the crest."""
    lateral = np.maximum(np.maximum(edge - a, a - edge - section.crest), 0.0)
    return section.top - rise(np.hypot(gap, lateral), section.outer)


def clamp(ground: np.ndarray, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """The ground between its two limits."""
    return np.minimum(np.maximum(ground, low), high)
