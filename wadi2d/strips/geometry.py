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
        """Signed area (positive counter-clockwise) and centroid of every ring, by the shoelace rule on coordinates
        taken from the ring's first node. On map coordinates themselves (UTM, 1e5 to 1e6 m) the products cancel to
        a few metres of error in a small cell's centroid (W52: up to 4 m, median 0.5 m on cells under 100 m2).

        A ring at a time in Python: 18 s on Block 2's 190,000 strip cells, asked four times by one strip build. The
        answer is kept for the nodes and rings it was made from, checked by their bytes on every call, so a geometry
        edited in place is measured again (W91); the copy kept never goes into a pickle."""
        key = self._fingerprint()
        held = self.__dict__.get("_areas")
        if held is None or held[0] != key:
            held = (key, self._areas_centroids())
            self.__dict__["_areas"] = held
        return tuple(a.copy() for a in held[1])

    def _fingerprint(self) -> bytes:
        import hashlib

        digest = hashlib.blake2b(digest_size=16)
        for a in (self.x, self.y, self.ring_start, self.ring_node):
            a = np.ascontiguousarray(a)
            digest.update(f"{a.dtype.str}{a.shape}".encode())
            digest.update(a.tobytes())
        return digest.digest()

    def __getstate__(self) -> dict:
        state = dict(self.__dict__)
        state.pop("_areas", None)  # a strip cache holds what it held before W91
        return state

    def _areas_centroids(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = self.ncells
        area = np.zeros(n)
        cx = np.zeros(n)
        cy = np.zeros(n)
        for c in range(n):
            r = self.ring(c)
            ox, oy = self.x[r[0]], self.y[r[0]]
            xq, yq = self.x[r] - ox, self.y[r] - oy
            x1, y1 = np.roll(xq, -1), np.roll(yq, -1)
            cross = xq * y1 - x1 * yq
            a = 0.5 * cross.sum()
            area[c] = a
            if abs(a) > 0.0:
                cx[c] = ox + ((xq + x1) * cross).sum() / (6.0 * a)
                cy[c] = oy + ((yq + y1) * cross).sum() / (6.0 * a)
            else:
                cx[c], cy[c] = ox + xq.mean(), oy + yq.mean()
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
        # every ring's edges in ring order; a face is an edge's first appearance, its cells the rings of its first two
        # (the order a dict of edges gave, on whole arrays: W92, 8 s of Block 2's mesh in Python)
        lengths = np.diff(start)
        ring_of = np.repeat(np.arange(len(rings), dtype=np.int64), lengths)
        following = np.arange(1, ring_node.size + 1, dtype=np.int64)
        if ring_node.size:
            following[start[1:][lengths > 0] - 1] = start[:-1][lengths > 0]  # a ring's last node closes on its first
        a, b = ring_node, ring_node[following] if ring_node.size else ring_node
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        span = int(hi.max()) + 1 if hi.size else 1
        code = lo * span + hi
        order = np.argsort(code, kind="stable")
        sorted_code = code[order]
        head = np.ones(order.size, bool)
        head[1:] = sorted_code[1:] != sorted_code[:-1]
        group = np.nonzero(head)[0]
        first = order[group]
        size = np.diff(np.append(group, order.size))
        second = np.where(size > 1, order[np.minimum(group + 1, order.size - 1)], -1)
        by_first = np.argsort(first, kind="stable")
        first, second = first[by_first], second[by_first]
        face_node = np.column_stack((lo[first], hi[first])).astype(np.int64).reshape(-1, 2)
        face_cell = np.column_stack((ring_of[first], np.where(second >= 0, ring_of[np.maximum(second, 0)], -1))).astype(np.int64).reshape(-1, 2)
        return cls(np.asarray(x, np.float64), np.asarray(y, np.float64), start, ring_node, face_node, face_cell)
