# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which tiles an aligned strip's water can reach between two checks of the active list (W90).

A tile may sleep while no water and no source lies within reach of its cells: water moves one cell a step at most,
so "within reach" is a count of cells. On the lattice alone the count is a tile's width and the stepper's own rule
covers it: a wet tile wakes its eight neighbours. A strip is a second way in: its cells need not be the lattice's
size, it passes water to the squares it touches (its ghosts) anywhere inside a tile, and it takes water from them.
So the reach is counted here on the model's own cells, squares and strip cells together, each joined to its face
neighbours and each ghost to the strip cells it opens onto: from every tile's cells outward ``reach`` cells, noting
the tiles whose squares were met and the tiles in which the strip cells met have their centres (their home tiles).
While none of those holds water or a source, no flow can touch the tile before the next check, and it sleeps.

Before this a tile that held a ghost was stepped whatever the water did, and with it its neighbours: on Block 2
at 20 m, 2,276 tiles and 3,479 with their neighbours, of 3,604.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit
from scipy import sparse

from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import TILE
from wadi2d.solver.poly.mesh import PolyMesh

MARGIN = 2
"""Cells of reach beyond the steps between two checks: a tile is awake one whole step before a cell next to it can
be wet, so its halos and face buffers are a waking tile's when the first water arrives."""


def _csr(row: np.ndarray, col: np.ndarray, nrows: int) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(row, kind="stable")
    ptr = np.zeros(nrows + 1, np.int64)
    np.add.at(ptr, row + 1, 1)
    return np.cumsum(ptr), col[order].astype(np.int64)


@njit(cache=True)
def _reach_of_tiles(
    reach, ny, nx, mask, tile_of, tiles, cell_ptr, cell_nbr, ghost_at, ghost_ptr, ghost_cell, cell_gptr, cell_ghost,
    home, capacity, room,
):  # fmt: skip
    """Per tile, the tiles whose squares and the home tiles whose strip cells lie within ``reach`` cells of its own
    cells. Returns (count, tile, kind, other) with kind 0 a tile of squares and 1 a home of strip cells; a count
    past ``capacity`` asks for a larger buffer, and -1 for more ``room``, the cells one hop's front may hold."""
    ntiles = tiles.shape[0]
    nlat = ny * nx
    nstrip = home.size
    seen_lat = np.zeros(nlat, np.int32)
    seen_strip = np.zeros(nstrip, np.int32)
    met_lat = np.zeros(ntiles, np.int32)
    met_home = np.zeros(ntiles, np.int32)
    front = np.empty(room, np.int64)
    nxt = np.empty(room, np.int64)
    out_tile = np.empty(capacity, np.int32)
    out_kind = np.empty(capacity, np.int8)
    out_other = np.empty(capacity, np.int32)
    count = 0
    for t in range(1, ntiles):
        nf = 0
        tj, ti = tiles[t, 0], tiles[t, 1]
        for j in range(tj * TILE, (tj + 1) * TILE):
            for i in range(ti * TILE, (ti + 1) * TILE):
                if mask[j, i]:
                    k = j * nx + i
                    seen_lat[k] = t
                    front[nf] = k
                    nf += 1
        met_lat[t] = t  # a tile's own squares wake it by the stepper's rule
        for _hop in range(reach):
            nn = 0
            for a in range(nf):
                node = front[a]
                if node < nlat:
                    j, i = node // nx, node % nx
                    for side in range(4):
                        if side == 0:
                            j2, i2 = j, i - 1
                        elif side == 1:
                            j2, i2 = j, i + 1
                        elif side == 2:
                            j2, i2 = j - 1, i
                        else:
                            j2, i2 = j + 1, i
                        if j2 < 0 or j2 >= ny or i2 < 0 or i2 >= nx or not mask[j2, i2]:
                            continue
                        k = j2 * nx + i2
                        if seen_lat[k] != t:
                            seen_lat[k] = t
                            if nn == room:
                                return -1, out_tile, out_kind, out_other
                            nxt[nn] = k
                            nn += 1
                    g = ghost_at[node]
                    if g >= 0:
                        for e in range(ghost_ptr[g], ghost_ptr[g + 1]):
                            c = ghost_cell[e]
                            if seen_strip[c] != t:
                                seen_strip[c] = t
                                if nn == room:
                                    return -1, out_tile, out_kind, out_other
                                nxt[nn] = nlat + c
                                nn += 1
                else:
                    c0 = node - nlat
                    for e in range(cell_ptr[c0], cell_ptr[c0 + 1]):
                        c = cell_nbr[e]
                        if seen_strip[c] != t:
                            seen_strip[c] = t
                            if nn == room:
                                return -1, out_tile, out_kind, out_other
                            nxt[nn] = nlat + c
                            nn += 1
                    for e in range(cell_gptr[c0], cell_gptr[c0 + 1]):
                        k = cell_ghost[e]
                        if seen_lat[k] != t:
                            seen_lat[k] = t
                            if nn == room:
                                return -1, out_tile, out_kind, out_other
                            nxt[nn] = k
                            nn += 1
            for a in range(nn):
                node = nxt[a]
                if node < nlat:
                    other = tile_of[(node // nx) // TILE, (node % nx) // TILE]
                    if met_lat[other] != t:
                        met_lat[other] = t
                        if count < capacity:
                            out_tile[count], out_kind[count], out_other[count] = t, 0, other
                        count += 1
                else:
                    other = home[node - nlat]
                    if met_home[other] != t:
                        met_home[other] = t
                        if count < capacity:
                            out_tile[count], out_kind[count], out_other[count] = t, 1, other
                        count += 1
            front, nxt = nxt, front
            nf = nn
            if nf == 0:
                break
    return count, out_tile, out_kind, out_other


@dataclass
class Watch:
    """A strip's cells by home tile, and per tile the tiles and homes whose water can reach it between two checks."""

    home: np.ndarray
    """The tile in which each real strip cell has its centre (the nearest tile of the grid where it has none)."""
    from_squares: sparse.csr_matrix
    """(tiles, tiles): row T holds the tiles whose squares lie within reach of T's cells."""
    from_strip: sparse.csr_matrix
    """(tiles, tiles): row T holds the home tiles of the strip cells within reach of T's cells."""
    reach: int

    def tiles_to_wake(self, squares: np.ndarray, strip: np.ndarray) -> np.ndarray:
        """The tiles that water in these tiles' squares, or in strip cells of these homes, can reach."""
        hit = self.from_squares @ squares.astype(np.int32) + self.from_strip @ strip.astype(np.int32)
        out = np.asarray(hit).ravel() > 0
        out[0] = False
        return out


def home_tiles(mesh: PolyMesh, grid: TileGrid) -> np.ndarray:
    """The tile each real cell's centre lies in; a centre in no tile takes the tile of the nearest allocated one."""
    n = mesh.real
    nty, ntx = grid.tile_of.shape
    tj = np.clip(((grid.y0 - mesh.cy[:n]) // grid.dx).astype(np.int64) // TILE, 0, nty - 1)
    ti = np.clip(((mesh.cx[:n] - grid.x0) // grid.dx).astype(np.int64) // TILE, 0, ntx - 1)
    home = grid.tile_of[tj, ti].astype(np.int32)
    lost = np.nonzero(home == 0)[0]
    if lost.size:
        kept = grid.tiles[1:].astype(np.int64)
        for c in lost:
            home[c] = 1 + int(np.argmin((kept[:, 0] - tj[c]) ** 2 + (kept[:, 1] - ti[c]) ** 2))
    return home


def build_watch(mesh: PolyMesh, grid: TileGrid, ghost_j: np.ndarray, ghost_i: np.ndarray, period: int) -> Watch:
    """The watch of a strip on a uniform grid; ``ghost_j``, ``ghost_i`` are the grid rows and columns of the
    mesh's ghosts in order, ``period`` the most steps between two checks."""
    n = mesh.real
    ny, nx = grid.shape
    left, right = np.asarray(mesh.left, np.int64), np.asarray(mesh.right, np.int64)
    inner = (left < n) & (right < n)
    a, b = left[inner], right[inner]
    cell_ptr, cell_nbr = _csr(np.concatenate((a, b)), np.concatenate((b, a)), n)
    # an interface face joins a real cell and a ghost, whichever side the mesh put the ghost on
    cell = np.concatenate((left[(left < n) & (right >= n)], right[(right < n) & (left >= n)]))
    ghost = np.concatenate((right[(left < n) & (right >= n)], left[(right < n) & (left >= n)])) - n
    ghost_node = np.asarray(ghost_j, np.int64) * nx + np.asarray(ghost_i, np.int64)
    ghost_ptr, ghost_cell = _csr(ghost, cell, int(ghost_node.size))
    cell_gptr, cell_ghost = _csr(cell, ghost_node[ghost], n)
    ghost_at = np.full(ny * nx, -1, np.int32)
    ghost_at[ghost_node] = np.arange(ghost_node.size, dtype=np.int32)
    home = home_tiles(mesh, grid)
    reach = int(period) + MARGIN
    ntiles = grid.ntiles
    capacity = 64 * ntiles
    side = TILE + 2 * reach
    room = side * side + min(n, 16 * side * side)  # the squares a tile's reach covers, and strip cells beside them
    while True:
        count, tile, kind, other = _reach_of_tiles(
            reach, ny, nx, grid.mask, grid.tile_of, grid.tiles.astype(np.int64), cell_ptr, cell_nbr, ghost_at,
            ghost_ptr, ghost_cell, cell_gptr, cell_ghost, home, capacity, room,
        )  # fmt: skip
        if count < 0:  # cells larger than the lattice's carry a front further than its own squares
            room = min(4 * room, ny * nx + n)
        elif count > capacity:
            capacity = count
        else:
            break
    tile, kind, other = tile[:count], kind[:count], other[:count]

    def matrix(on: np.ndarray) -> sparse.csr_matrix:
        ones = np.ones(int(on.sum()), np.int32)
        return sparse.csr_matrix((ones, (tile[on], other[on])), shape=(ntiles, ntiles))

    return Watch(home, matrix(kind == 0), matrix(kind == 1), reach)


def home_flags(xp, h, src, home, ntiles: int):
    """Per tile whether a strip cell with its centre there holds water or a source; ``xp`` is numpy or cupy, the
    arrays its own: one source for both backends."""
    live = (h > 0.0) | (src != 0.0)
    out = xp.zeros(ntiles, xp.bool_)
    out[home[live]] = True
    return out


__all__ = ["MARGIN", "Watch", "build_watch", "home_flags", "home_tiles"]
