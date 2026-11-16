"""Hazard classes from the three maxima of a pixel. The limits and the rule live in ``config.schema.Pixels``."""

from __future__ import annotations

import numpy as np

from wadi2d.config.schema import Pixels

DRY = 0
"""A pixel below the depth floor; H1 to H6 are 1 to 6."""


def classify(depth: np.ndarray, speed: np.ndarray, dv: np.ndarray, rule: Pixels, xp=np) -> np.ndarray:
    """The highest class any limit gives; wet and under every limit is H1, below the floor is dry.

    ``xp`` is NumPy, or CuPy for arrays on the device (the time slider drawn on demand, W51)."""
    out = xp.ones(depth.shape, xp.uint8)
    for index, (dv_limit, depth_limit, speed_limit) in enumerate(rule.hazard_limits, start=2):
        above = (dv > dv_limit) | (depth > depth_limit) | (speed > speed_limit)
        out[above] = index
    out[depth < rule.depth_floor] = DRY
    return out


def hazard_floor(rule: Pixels) -> float:
    """Depth under which a pixel is off the hazard map: the higher of the two floors."""
    return max(rule.depth_floor, rule.hazard_depth_floor)


def off_the_map(classes, depth, rule: Pixels, xp=np):
    """The classes as the hazard map shows them: thin water under the hazard floor takes no class (his decision of
    2026-11-16). Only for writing or drawing the hazard map: the wet mask of depth and speed stays ``classes > DRY``."""
    return xp.where(depth < hazard_floor(rule), DRY, classes).astype(classes.dtype)


def class_names(rule: Pixels) -> list[str]:
    return [f"H{k}" for k in range(1, len(rule.hazard_limits) + 2)]
