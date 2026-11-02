"""Hazard classes from the three maxima of a pixel. The limits and the rule live in ``config.schema.Pixels``."""

from __future__ import annotations

import numpy as np

from wadi2d.config.schema import Pixels

DRY = 0
"""A pixel below the depth floor; H1 to H6 are 1 to 6."""


def classify(depth: np.ndarray, speed: np.ndarray, dv: np.ndarray, rule: Pixels) -> np.ndarray:
    """The highest class any limit gives; wet and under every limit is H1, below the floor is dry."""
    out = np.ones(depth.shape, np.uint8)
    for index, (dv_limit, depth_limit, speed_limit) in enumerate(rule.hazard_limits, start=2):
        above = (dv > dv_limit) | (depth > depth_limit) | (speed > speed_limit)
        out[above] = index
    out[depth < rule.depth_floor] = DRY
    return out


def class_names(rule: Pixels) -> list[str]:
    return [f"H{k}" for k in range(1, len(rule.hazard_limits) + 2)]
