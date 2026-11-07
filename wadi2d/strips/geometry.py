# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The geometry contract of a polygon mesh: nodes, one ring of nodes per cell, one pair of nodes and of cells per
face (W45, stage 2). What the mesher writes, what the table builder and the kernels read; MeshKernel is never imported
here.

Rings are counter-clockwise in map coordinates (x east, y north). A face's two cells are ``left`` and ``right`` with
the unit normal pointing from left to right; a boundary face has ``right`` -1 and is not stepped: the strip's outer
faces are either interface faces to tile cells (stage 3 gives them their tile index) or walls.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MeshGeometry:
    """Nodes, rings and faces, with what the kernels derive from them."""

    x: np.ndarray
    y: np.ndarray
    ring_start: np.ndarray
    """(ncells + 1,) offsets into ``ring_node``."""
    ring_node: np.ndarray
    face_node: np.ndarray
    """(nfaces, 2) the two nodes of each face."""
    face_cell: np.ndarray
    """(nfaces, 2) left and right cell; right -1 on the boundary."""

    @property
    def ncells(self) -> int:
        return int(self.ring_start.size - 1)

    @property
    def nfaces(self) -> int:
        return int(self.face_node.shape[0])

    def ring(self, c: int) -> np.ndarray:
        return self.ring_node[self.ring_start[c] : self.ring_start[c + 1]]

    def areas_centroids(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Signed area (positive counter-clockwise) and centroid of every ring, by the shoelace rule."""
        n = self.ncells
        area = np.zeros(n)
        cx = np.zeros(n)
        cy = np.zeros(n)
        for c in range(n):
            r = self.ring(c)
            xq, yq = self.x[r], self.y[r]
            x1, y1 = np.roll(xq, -1), np.roll(yq, -1)
            cross = xq * y1 - x1 * yq
            a = 0.5 * cross.sum()
            area[c] = a
            if abs(a) > 0.0:
                cx[c] = ((xq + x1) * cross).sum() / (6.0 * a)
                cy[c] = ((yq + y1) * cross).sum() / (6.0 * a)
            else:
                cx[c], cy[c] = xq.mean(), yq.mean()
        return area, cx, cy

    def faces(self, cx: np.ndarray, cy: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Length, unit normal from left to right, and midpoint of every face; the normal is flipped where it points
        from right to left, so the contract's orientation holds whatever the mesher wrote."""
        a, b = self.face_node[:, 0], self.face_node[:, 1]
        dx, dy = self.x[b] - self.x[a], self.y[b] - self.y[a]
        length = np.hypot(dx, dy)
        safe = np.maximum(length, 1e-12)
        nx, ny = dy / safe, -dx / safe
        left, right = self.face_cell[:, 0], self.face_cell[:, 1]
        inner = right >= 0
        to_right_x = np.where(inner, cx[np.where(inner, right, 0)] - cx[left], 0.0)
        to_right_y = np.where(inner, cy[np.where(inner, right, 0)] - cy[left], 0.0)
        # a boundary face points outward: away from its one cell
        xf, yf = 0.5 * (self.x[a] + self.x[b]), 0.5 * (self.y[a] + self.y[b])
        out_x = np.where(inner, to_right_x, xf - cx[left])
        out_y = np.where(inner, to_right_y, yf - cy[left])
        flip = nx * out_x + ny * out_y < 0.0
        nx = np.where(flip, -nx, nx)
        ny = np.where(flip, -ny, ny)
        return length, nx, ny, xf, yf

    def check(self) -> list[str]:
        """What is wrong with the mesh, in words; empty when nothing is."""
        notes = []
        area, _cx, _cy = self.areas_centroids()
        bad = int((area <= 0.0).sum())
        if bad:
            notes.append(f"{bad} cells have a clockwise or empty ring")
        tiny = int((np.abs(area) < 1e-6 * np.abs(area).max()).sum()) if area.size else 0
        if tiny:
            notes.append(f"{tiny} cells are slivers under 1e-6 of the largest")
        if self.face_cell[:, 0].min() < 0:
            notes.append("a face has no left cell")
        if (self.face_cell[:, 0] >= self.ncells).any() or (self.face_cell[:, 1] >= self.ncells).any():
            notes.append("a face names a cell the mesh does not have")
        return notes

    @classmethod
    def from_rings(cls, x: np.ndarray, y: np.ndarray, rings: list[np.ndarray]) -> MeshGeometry:
        """A mesh from node coordinates and one ring of node indices per cell; faces are found from shared edges."""
        start = np.zeros(len(rings) + 1, np.int64)
        start[1:] = np.cumsum([len(r) for r in rings])
        ring_node = np.concatenate([np.asarray(r, np.int64) for r in rings]) if rings else np.zeros(0, np.int64)
        edges: dict[tuple[int, int], list[int]] = {}
        for c, r in enumerate(rings):
            r = np.asarray(r, np.int64)
            for k in range(r.size):
                a, b = int(r[k]), int(r[(k + 1) % r.size])
                edges.setdefault((min(a, b), max(a, b)), []).append(c)
        face_node = np.array(list(edges), np.int64).reshape(-1, 2)
        face_cell = np.full((face_node.shape[0], 2), -1, np.int64)
        for f, cells in enumerate(edges.values()):
            face_cell[f, : len(cells[:2])] = cells[:2]
        return cls(np.asarray(x, np.float64), np.asarray(y, np.float64), start, ring_node, face_node, face_cell)
