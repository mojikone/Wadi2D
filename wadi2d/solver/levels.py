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
    interfaces: np.ndarray | None = None,
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
    level = _graded(level, active, nbr, interfaces)
    dt0 = float((want[active] / (1 << level[active])).min()) if active.size else rule.dt_max
    return level, dt0


def _graded(
    level: np.ndarray, active: np.ndarray, nbr: np.ndarray, interfaces: np.ndarray | None = None
) -> np.ndarray:
    """Lower levels until neighbours differ by at most one; inactive neighbours do not count.

    Across an interface the small cells never step slower than the large ones, so its faces follow the fine tile.
    """
    high = np.iinfo(np.int32).max // 2
    around = np.full(level.size, high, np.int32)
    around[active] = level[active]
    links = nbr[active]
    while True:
        lowest = around[links].min(axis=1)
        fixed = np.minimum(around[active], lowest + 1)
        same = np.array_equal(fixed, around[active])
        around[active] = fixed
        if interfaces is not None and interfaces.size:
            fine, coarse = interfaces[:, 0], interfaces[:, 2]
            keep = around[fine].copy()
            np.minimum.at(around, fine, around[coarse])
            same = same and np.array_equal(keep, around[fine])
        if same:
            break
    out = np.zeros_like(level)
    out[active] = around[active]
    return out


Sized = list[tuple[int, np.ndarray]]
"""Lists per tile size: (size level, entries)."""


@dataclass
class Plan:
    """One cycle's lists, in host form, indexed by time level. ``upto[k]`` is every tile of level <= k."""

    level: np.ndarray
    top: int
    groups: list[Sized]
    upto: list[np.ndarray]
    halo: list[np.ndarray]
    """The tiles whose halos a step of that level needs: ``upto``, and the owners of the faces in ``strips``."""
    coarse: list[np.ndarray]
    """The tiles with a neighbour at a finer time level: their old values are wanted."""
    edges_x: list[Sized]
    edges_y: list[Sized]
    """Rows (fine tile, side, coarse tile, edge number) by the fine tile's level, one list per axis."""
    strips: list[Sized]
    """The rows of edges whose faces the coarse tile owns."""
    level_with: list[Sized]
    level_above: list[Sized]
    """Interface rows by the fine tile's level: coarse tile at the same time level, or one above. The residual of a
    coarse cell is written without a lock, so each entry holds one axis."""


def _by_size(entries: np.ndarray, sizes: np.ndarray) -> Sized:
    return [(int(s), entries[sizes == s]) for s in np.unique(sizes)]


def plan_cycle(
    level: np.ndarray,
    active: np.ndarray,
    same: np.ndarray,
    size: np.ndarray | None = None,
    interfaces: np.ndarray | None = None,
) -> Plan:
    """The lists for ``level``. ``same`` gives each tile's neighbour of its own cell size per side."""
    size = np.zeros(level.size, np.int32) if size is None else size
    interfaces = np.zeros((0, 7), np.int32) if interfaces is None else interfaces
    top = int(level[active].max()) if active.size else 0
    span = range(top + 1)
    on = np.zeros(level.size, bool)
    on[active] = True
    groups = [_by_size(g, size[g]) for g in (active[level[active] == n] for n in span)]
    upto = [active[level[active] <= n] for n in span]
    rows = []
    for side in range(4):
        other = same[active, side]
        hit = on[other] & (level[other] > level[active])
        rows.append(np.column_stack((active[hit], np.full(hit.sum(), side), other[hit])))
    row = np.vstack(rows).astype(np.int32)
    row = np.column_stack((row, np.arange(row.shape[0], dtype=np.int32)))
    fine_level = level[row[:, 0]]
    fine_size = size[row[:, 0]]

    def pick(wanted: np.ndarray) -> list[Sized]:
        return [
            _by_size(row[wanted & (fine_level == n)], fine_size[wanted & (fine_level == n)]) for n in span
        ]

    edges_x, edges_y = pick(row[:, 1] % 2 == 0), pick(row[:, 1] % 2 == 1)
    strips = pick(row[:, 1] >= EAST)
    used = interfaces[on[interfaces[:, 0]] & on[interfaces[:, 2]]]
    gap = level[used[:, 2]] - level[used[:, 0]]
    fine = level[used[:, 0]]

    def interface_lists(wanted: np.ndarray, n: int) -> Sized:
        """One entry per axis, so no launch writes one coarse cell twice."""
        out: Sized = []
        for axis in (0, 1):
            rows_ = used[wanted & (fine == n) & (used[:, 1] % 2 == axis)]
            out += _by_size(rows_, size[rows_[:, 0]])
        return out

    level_with = [interface_lists(gap == 0, n) for n in span]
    level_above = [interface_lists(gap > 0, n) for n in span]
    has_finer = np.zeros(level.size, bool)
    has_finer[row[:, 2]] = True
    has_finer[used[gap > 0, 2]] = True
    coarse = [active[(level[active] == n) & has_finer[active]] for n in span]
    owners = [np.concatenate([e[:, 2] for _s, e in strips[n]] or [np.zeros(0, np.int32)]) for n in span]
    halo = [np.union1d(upto[n], np.concatenate(owners[: n + 1])).astype(np.int32) for n in span]
    return Plan(level, top, groups, upto, halo, coarse, edges_x, edges_y, strips, level_with, level_above)
