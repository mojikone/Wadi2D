"""The pixel maps a block of the rasters at a time: how the blocks are cut and where their maps come from (W86).

Before, every saved map went over every kept pixel of the run, and the ground and the three maxima of all of them
had to be somewhere: on Block 2 at the 0.5 m pixel 16 GB for the squares alone, more than the card, so every map
carried them to the card and back, 10 s a map; the strip's pixels asked for more than the machine holds. Now the
rasters' windows are grouped into blocks that fit the device, and a block is finished before the next begins: its
ground goes up once, every saved map runs on it there, its maxima come down once and are written. Memory follows the
block, not the run.

The saved maps are read from the run's file once and held reduced to the cells that take pixels, a few bytes a cell
and map, so a block's maps are a slice of memory and not a read of the file.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wadi2d.products.frames import read_frames, read_strip_frames

DEVICE_SHARE = 0.75
"""Share of the card's free memory a block is cut to fit; the pool is capped a little above it."""
POOL_SHARE = 0.85
HOST_BLOCK_BYTES = 4 << 30
"""What a block may take on the host when the maps are made there, on the CPU."""
MEMORY_ENV = "WADI2D_PIXEL_MEMORY_MB"
"""The environment variable that caps a block's memory, MB: for a card or a machine shared with other work."""
SQUARE_PIXEL_BYTES = 16
"""Ground and the three maxima of a square cell's pixel."""
WORK_PIXEL_BYTES = 32
"""The work arrays of a batch of pixels while a map is laid over it."""
HOST_RESULT_BYTES = 6 << 30
"""What one block's pixels may take on the host while they are gathered and written, whatever the device: Block 2's
run 3 cut by the card alone held 27 GB at its peak (W86)."""
SQUARE_HOST_BYTES = 32
"""Host bytes a square pixel takes while its block is written: three maxima come down, are picked, classed and
painted."""
BAND_GROUND_BYTES = 2 << 30
"""Ground of a band of windows read at once on the host, at most (a band is one row of windows at least)."""
STACK_BYTES = 6 << 30
"""Saved maps held at once on the host, reduced to the cells that take pixels; past it the file is read again
for each group of bands."""
STACK_VALUE_BYTES = 12
"""Depth, mean depth and speed of a cell in one saved map."""


def device_budget(xp, batch_pixels: int, squeeze: float = 1.0) -> tuple[float, float]:
    """(bytes a block's resident arrays may take, cap of the device's pool) for the maps made with ``xp``;
    ``squeeze`` cuts the blocks to that share of the room and leaves the pool its cap."""
    if xp is np:
        room = pool = float(HOST_BLOCK_BYTES)
    else:
        free = float(xp.cuda.Device().mem_info[0])
        room, pool = DEVICE_SHARE * free, POOL_SHARE * free
    given = os.environ.get(MEMORY_ENV, "").strip()
    if given:
        cap = float(given) * (1 << 20)
        room, pool = min(room, cap), min(pool, cap / DEVICE_SHARE * POOL_SHARE)
    return squeeze * max(room - WORK_PIXEL_BYTES * float(batch_pixels), room / 4.0), pool


@dataclass(frozen=True)
class Block:
    """Windows ``[row0, row1)`` x ``[col0, col1)`` of the rasters."""

    row0: int
    row1: int
    col0: int
    col1: int


def plan_bands(rows_cost: np.ndarray, budget: float) -> list[tuple[int, int]]:
    """Rows of windows grouped into bands, each within ``budget`` unless it is one row."""
    bands, start, total = [], 0, 0.0
    for r, cost in enumerate(rows_cost):
        if r > start and total + cost > budget:
            bands.append((start, r))
            start, total = r, 0.0
        total += float(cost)
    if len(rows_cost) > start:
        bands.append((start, len(rows_cost)))
    return bands


def plan_blocks(costs: list[np.ndarray], budgets: list[float], band: tuple[int, int]) -> list[Block]:
    """The blocks of one band: runs of its columns of windows, each within every budget, the band halved where a
    single column is not. Together they hold every window of the band once; a block of one window may be over."""
    r0, r1 = band
    columns = [cost[r0:r1].sum(axis=0) for cost in costs]
    over = any(float(c.max(initial=0.0)) > b for c, b in zip(columns, budgets, strict=True))
    if over and r1 - r0 > 1:
        middle = (r0 + r1) // 2
        return plan_blocks(costs, budgets, (r0, middle)) + plan_blocks(costs, budgets, (middle, r1))
    blocks, start, totals = [], 0, [0.0] * len(costs)
    width = columns[0].size
    for c in range(width):
        if c > start and any(t + float(col[c]) > b for t, col, b in zip(totals, columns, budgets, strict=True)):
            blocks.append(Block(r0, r1, start, c))
            start, totals = c, [0.0] * len(costs)
        totals = [t + float(col[c]) for t, col in zip(totals, columns, strict=True)]
    blocks.append(Block(r0, r1, start, width))
    return blocks


def square_window_pixels(rows: np.ndarray, cols: np.ndarray, k: int, size: int, top: int, left: int, shape) -> np.ndarray:
    """How many kept pixels each window of ``size`` pixels holds, a cell counted where its first pixel is."""
    out = np.zeros(shape)
    r = (rows.astype(np.int64) * k - top) // size
    c = (cols.astype(np.int64) * k - left) // size
    np.add.at(out, (np.clip(r, 0, shape[0] - 1), np.clip(c, 0, shape[1] - 1)), float(k * k))
    return out


@dataclass
class Stack:
    """Saved maps of some cells: ``values[field][map]`` holds the cells listed in ``cells``, in that order."""

    cells: np.ndarray
    values: tuple[np.ndarray, np.ndarray, np.ndarray]
    """(maps, cells) each: depth or level above the cell's lowest ground, mean depth, speed."""

    @property
    def maps(self) -> int:
        return int(self.values[0].shape[0])

    def at(self, cells: np.ndarray) -> np.ndarray:
        """Where ``cells`` (rising, all held) stand in the stack."""
        return np.searchsorted(self.cells, cells)

    def of(self, index: int, at: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return tuple(v[index, at] for v in self.values)


def read_square_stack(
    results: Path, names: list[str], rows: np.ndarray, cols: np.ndarray, a: int, b: int, tick: Callable[[int, int], None]
) -> Stack:
    """The saved maps at kept cells ``[a, b)`` of the list (rows, cols), one pass over the file."""
    r, c = rows[a:b], cols[a:b]
    values = tuple(np.empty((len(names), b - a), np.float32) for _ in range(3))
    with closing(read_frames(results, names)) as frames:
        for index, fields in enumerate(frames):
            tick(index, len(names))
            for held, field in zip(values, fields, strict=True):
                held[index] = field[r, c]
    return Stack(np.arange(a, b), values)


def read_strip_stack(results: Path, names: list[str], cells: np.ndarray) -> Stack:
    """The strip's cells ``cells`` (rising) in every saved map that holds the strip."""
    held: tuple[list, list, list] = ([], [], [])
    for fields in read_strip_frames(results, names):
        for into, field in zip(held, fields, strict=True):
            into.append(np.asarray(field, np.float32)[cells])
    width = cells.size
    return Stack(cells, tuple(np.array(v, np.float32).reshape(len(v), width) for v in held))


__all__ = [
    "HOST_RESULT_BYTES",
    "SQUARE_HOST_BYTES",
    "Block",
    "Stack",
    "device_budget",
    "plan_bands",
    "plan_blocks",
    "read_square_stack",
    "read_strip_stack",
    "square_window_pixels",
]
