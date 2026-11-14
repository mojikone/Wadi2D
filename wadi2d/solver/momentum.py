"""A momentum source on faces (W70): the rate at which inflowing water brings momentum to a face's control volume.

The face update reads ``us = (m - dt * flux / L) / Abar``, so a source S (m4/s2, the momentum flux entering the face's
control volume) is ``m += dt * S / L`` before the faces are stepped: the same equation with the source on its right.
``rate`` holds S / L per face, m3/s2. Nothing here runs unless a source is set, so a job without one steps through
exactly the code it always did.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

F = np.float32


@dataclass
class FaceKick:
    """Momentum source rates on x faces (``mx``, positive east) and y faces (``my``, positive south)."""

    faces_x: np.ndarray
    rate_x: np.ndarray
    faces_y: np.ndarray
    rate_y: np.ndarray

    @staticmethod
    def build(faces_x, rate_x, faces_y, rate_y) -> FaceKick:
        """Duplicate faces summed, so the update is one plain indexed add on either backend."""
        parts = []
        for faces, rate in ((faces_x, rate_x), (faces_y, rate_y)):
            faces = np.asarray(faces, np.int64)
            if faces.size == 0:
                parts += [np.zeros(0, np.int64), np.zeros(0, F)]
                continue
            unique, back = np.unique(faces, return_inverse=True)
            total = np.zeros(unique.size, np.float64)
            np.add.at(total, back, np.asarray(rate, np.float64))
            parts += [unique, total.astype(F)]
        return FaceKick(*parts)

    def on(self, backend) -> FaceKick:
        """The same kick with its arrays where the backend keeps its state."""
        cp = getattr(backend, "cp", None)
        if cp is None:
            return self
        return FaceKick(*(cp.asarray(a) for a in (self.faces_x, self.rate_x, self.faces_y, self.rate_y)))

    def apply(self, backend, dt: float) -> None:
        step = F(dt)
        if self.faces_x.size:
            backend.mx[self.faces_x] += step * self.rate_x
        if self.faces_y.size:
            backend.my[self.faces_y] += step * self.rate_y
