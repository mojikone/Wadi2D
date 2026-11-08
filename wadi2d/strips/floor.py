# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the bed ends either side of a stream, station by station (W46).

His rules of 2026-11-08: going outward from the centre line, the bank is the first of a scarp inside one step, a
rise of ``bank_scarp_m`` within ``bank_scarp_run_m`` read on the sub-grid pixels (a terrace edge or a channel wall,
what the eye reads as the bank), and the ground standing ``bank_rise_m`` above the bed (height above the channel,
which decides where there is no scarp, the fans); the slope over ``bank_run_m`` is a cap only. Past
``bank_reach_m`` a side has no bank and the stream keeps the squares there. The first ``bank_offset_cells`` cells
are bed whatever the ground does, so the lip of the low-flow channel never passes for the bank (W45).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.breaklines.banks import _bed
from wadi2d.breaklines.window import Window
from wadi2d.config.schema import Breaklines


@dataclass(frozen=True)
class FloorRule:
    """The numbers of the bank rule, in metres and m/m."""

    rise_m: float = 2.0
    scarp_m: float = 1.0
    scarp_run_m: float = 10.0
    slope_cap: float | None = 0.05
    slope_run_m: float = 40.0
    reach_m: float = 300.0
    offset_m: float = 30.0

    @classmethod
    def from_settings(cls, cfg: Breaklines, dx: float) -> FloorRule:
        return cls(
            rise_m=cfg.bank_rise_m,
            scarp_m=cfg.bank_scarp_m,
            scarp_run_m=cfg.bank_scarp_run_m,
            slope_cap=cfg.bank_slope if cfg.bank_slope_cap else None,
            slope_run_m=cfg.bank_run_m,
            reach_m=cfg.bank_reach_m,
            offset_m=cfg.bank_offset_cells * dx,
        )


def _first_true(mask: np.ndarray, off: np.ndarray, distances: np.ndarray) -> np.ndarray:
    """Per column the distance of the first True row, NaN where none or where the raster ran out before it."""
    first = np.argmax(mask, axis=0)
    found = mask.any(axis=0)
    seen_off = np.cumsum(off, axis=0)[first, np.arange(mask.shape[1])] > 0
    ok = found & ~seen_off
    return np.where(ok, distances[first], np.nan)


def floor_distances(win: Window, centres: np.ndarray, normals: np.ndarray, rule: FloorRule, sign: float) -> np.ndarray:
    """Distance from each station to the bank on one side (``sign`` +1 left, -1 right), NaN where that side has no
    bank within the reach: the first of the scarp, the rise and the slope cap, and never under the offset."""
    if centres.shape[0] == 0:
        return np.zeros(0)
    px = win.pixel
    runs = max(rule.scarp_run_m, rule.slope_run_m if rule.slope_cap is not None else 0.0)
    distances = np.arange(px, rule.reach_m + runs + 1e-9, px)
    z = win.sample(win.z, centres[None, :, :] + sign * normals[None, :, :] * distances[:, None, None])  # (nd, n)
    bed = _bed(win, centres, normals)
    within = distances[:, None] <= rule.reach_m + 1e-9
    beyond = distances[:, None] >= rule.offset_m - 1e-9
    rise = (z - bed[None, :]) >= rule.rise_m
    trigger = rise & within & beyond
    steps = max(1, int(round(rule.scarp_run_m / px)))
    if z.shape[0] > steps:
        scarp = np.zeros_like(rise)
        scarp[:-steps] = (z[steps:] - z[:-steps]) >= rule.scarp_m
        trigger |= scarp & within & beyond
    if rule.slope_cap is not None:
        # the cap fires where a climb steeper than the cap begins and holds over the run: the slope over the scarp's
        # short run and over the long run both at or over it (a forward run alone fired a run's length early, at the
        # foot of a scarp it had not reached, which is how the 5 % rule read the lip of every channel as its bank)
        long = max(1, int(round(rule.slope_run_m / px)))
        short = max(1, min(steps, long))
        if z.shape[0] > long:
            cap = np.zeros_like(rise)
            cap[:-long] = ((z[long:] - z[:-long]) / (long * px) >= rule.slope_cap) & ((z[short : z.shape[0] - long + short] - z[:-long]) / (short * px) >= rule.slope_cap)
            trigger |= cap & within & beyond
    d = _first_true(trigger, np.isnan(z), distances)
    return np.where(np.isfinite(d), np.maximum(d, rule.offset_m), np.nan)


def floor_of_line(win: Window, xy: np.ndarray, rule: FloorRule) -> tuple[np.ndarray, np.ndarray]:
    """The bank distances left and right at the vertices of a resampled line (its stations), the normals from the
    mean of the two segments at each vertex."""
    seg = np.diff(xy, axis=0)
    ahead = np.vstack((seg, seg[-1:]))
    behind = np.vstack((seg[:1], seg))
    tang = ahead + behind
    tang /= np.maximum(np.hypot(tang[:, 0], tang[:, 1]), 1e-12)[:, None]
    normals = np.column_stack((-tang[:, 1], tang[:, 0]))
    left = floor_distances(win, xy, normals, rule, 1.0)
    right = floor_distances(win, xy, normals, rule, -1.0)
    return left, right


__all__ = ["FloorRule", "floor_distances", "floor_of_line"]
