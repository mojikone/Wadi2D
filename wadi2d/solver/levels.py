"""Time levels of the tiles: which tile steps when, and the edges between tiles that step at different rates.

A tile at level L steps 2^L x the smallest step. Levels are host arithmetic, redone once per cycle; the device sees
lists of tiles and lists of edges. Neighbours differ by at most one level, so a coarse step holds exactly two fine ones.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.grid.tiles import NEIGHBOURS

SIDES = (3, 1, 4, 6)
"""Index in ``TileGrid.nbr`` of the west, north, east and south neighbours; the position is the side number."""
EAST, SOUTH = 2, 3
LOG_MARGIN = 1e-9
"""So a tile exactly on a power of two is not rounded down by the logarithm."""
HOLD = 0.85
"""The smallest step may stay this far under the fastest tile's step before a level drops."""
CLIMB = 0.25
"""A tile climbs a level only this far past the mark, in levels."""
assert all(NEIGHBOURS[n] == d for n, d in zip(SIDES, ((0, -1), (-1, 0), (0, 1), (1, 0)), strict=True))


@dataclass
class LevelRule:
    """What a tile's step depends on."""

    cfl: float
    wave_floor: float
    buffer: float
    dt_max: float
    top: int
    hold: float = HOLD
    climb: float = CLIMB


def assign_levels(
    wave: np.ndarray,
    active: np.ndarray,
    nbr: np.ndarray,
    dx: float | np.ndarray,
    rule: LevelRule,
    pinned: np.ndarray,
    previous: np.ndarray | None = None,
) -> tuple[np.ndarray, float]:
    """(level per tile, smallest step). ``wave`` is the fastest wave seen in each tile.

    A tile also respects its neighbours' waves, scaled by ``rule.buffer``: a front can enter it within the cycle. A
    pinned tile stays at level 0, because the boundary tally counts every smallest step. Levels are sticky: a tile
    keeps its level while the smallest step need not fall below ``hold`` of what the fastest tile allows, and climbs
    only ``climb`` of a level past the mark, because every change costs a new set of lists.
    """
    n = nbr.shape[0]
    speed = np.zeros(n)
    speed[active] = np.maximum(wave[active], rule.wave_floor)
    around = speed[nbr[active]].max(axis=1)
    felt = speed.copy()
    felt[active] = np.maximum(speed[active], rule.buffer * around)
    want = np.full(n, np.inf)
    want[active] = np.minimum(rule.cfl * (dx if np.isscalar(dx) else dx[active]) / felt[active], rule.dt_max)
    fastest = float(want[active].min()) if active.size else rule.dt_max
    room = np.log2(want[active] / fastest) + LOG_MARGIN
    best = np.clip(np.floor(room), 0, rule.top).astype(np.int32)
    if previous is not None:
        old = previous[active]
        keep = (old <= room - np.log2(rule.hold)) & (room < old + 1 + rule.climb)
        best = np.where(keep, old, best)
    level = np.zeros(n, np.int32)
    level[active] = best
    level[pinned] = 0
    level = _graded(level, active, nbr)
    dt0 = float((want[active] / (1 << level[active])).min()) if active.size else rule.dt_max
    return level, dt0


def _graded(level: np.ndarray, active: np.ndarray, nbr: np.ndarray) -> np.ndarray:
    """Lower levels until neighbours differ by at most one; inactive neighbours do not count."""
    high = np.iinfo(np.int32).max // 2
    around = np.full(level.size, high, np.int32)
    around[active] = level[active]
    links = nbr[active]
    while True:
        lowest = around[links].min(axis=1)
        fixed = np.minimum(around[active], lowest + 1)
        if np.array_equal(fixed, around[active]):
            break
        around[active] = fixed
    out = np.zeros_like(level)
    out[active] = around[active]
    return out


@dataclass
class Plan:
    """One cycle's lists, in host form. ``upto[k]`` is every tile of level <= k."""

    level: np.ndarray
    top: int
    groups: list[np.ndarray]
    upto: list[np.ndarray]
    halo: list[np.ndarray]
    """Per level, the tiles whose halos a step of that level needs: ``upto``, and the owners of the faces in ``strips``."""
    coarse: list[np.ndarray]
    """Per level, the tiles with a finer neighbour: their old values are wanted."""
    edges_x: list[np.ndarray]
    edges_y: list[np.ndarray]
    """Per fine level, rows (fine tile, side, coarse tile, edge number), one list per axis."""
    strips: list[np.ndarray]
    """Per fine level, the rows of edges whose faces the coarse tile owns."""


def plan_cycle(level: np.ndarray, active: np.ndarray, nbr: np.ndarray) -> Plan:
    """The lists for ``level``; an edge joins two active tiles of different levels."""
    top = int(level[active].max()) if active.size else 0
    groups = [active[level[active] == n] for n in range(top + 1)]
    upto = [active[level[active] <= n] for n in range(top + 1)]
    on = np.zeros(level.size, bool)
    on[active] = True
    rows = []
    for side, slot in enumerate(SIDES):
        other = nbr[active, slot]
        hit = on[other] & (level[other] > level[active])
        rows.append(np.column_stack((active[hit], np.full(hit.sum(), side), other[hit])))
    row = np.vstack(rows).astype(np.int32)
    row = np.column_stack((row, np.arange(row.shape[0], dtype=np.int32)))
    fine_level = level[row[:, 0]]
    edges_x = [row[(fine_level == n) & (row[:, 1] % 2 == 0)] for n in range(top + 1)]
    edges_y = [row[(fine_level == n) & (row[:, 1] % 2 == 1)] for n in range(top + 1)]
    strips = [row[(fine_level == n) & (row[:, 1] >= EAST)] for n in range(top + 1)]
    has_finer = np.zeros(level.size, bool)
    has_finer[row[:, 2]] = True
    coarse = [g[has_finer[g]] for g in groups]
    halo = [np.union1d(upto[n], np.concatenate([e[:, 2] for e in strips[: n + 1]])) for n in range(top + 1)]
    return Plan(
        level, top, groups, upto, [h.astype(np.int32) for h in halo], coarse, edges_x, edges_y, strips
    )
