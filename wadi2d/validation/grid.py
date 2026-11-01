"""The uniform square-cell grid every validation case is sampled on.

Arrays have shape ``(ny, nx)``. Row 0 is at y-min unless ``flip_y`` is set, which puts it at y-max (the
raster convention). Every case evaluates its fields through :meth:`UniformGrid.mesh`, so the flag needs no
other code.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray

type FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class UniformGrid:
    """Square cells of side ``dx``; ``(x0, y0)`` is the lower-left corner of the domain, a cell corner."""

    x0: float
    y0: float
    dx: float
    nx: int
    ny: int
    flip_y: bool = False

    def __post_init__(self) -> None:
        if self.dx <= 0.0 or self.nx < 1 or self.ny < 1:
            raise ValueError(f"invalid grid: dx={self.dx}, nx={self.nx}, ny={self.ny}")

    @classmethod
    def square(cls, length: float, n: int, x0: float = 0.0, y0: float = 0.0) -> UniformGrid:
        """A square domain of side ``length`` with ``n`` cells per side."""
        return cls(x0, y0, length / n, n, n)

    @property
    def length_x(self) -> float:
        """Domain length along x, m."""
        return self.nx * self.dx

    @property
    def length_y(self) -> float:
        """Domain length along y, m."""
        return self.ny * self.dx

    @property
    def cell_area(self) -> float:
        """Plan area of one cell, m2."""
        return self.dx * self.dx

    @property
    def centre(self) -> tuple[float, float]:
        """Centre of the domain, (x, y)."""
        return self.x0 + 0.5 * self.length_x, self.y0 + 0.5 * self.length_y

    @property
    def x(self) -> FloatArray:
        """Cell-centre x, one value per column."""
        return self.x0 + (np.arange(self.nx, dtype=np.float64) + 0.5) * self.dx

    @property
    def y(self) -> FloatArray:
        """Cell-centre y, one value per row, in row order."""
        y = self.y0 + (np.arange(self.ny, dtype=np.float64) + 0.5) * self.dx
        return y[::-1] if self.flip_y else y

    def mesh(self) -> tuple[FloatArray, FloatArray]:
        """Cell-centre coordinates ``(x, y)``, each of shape ``(ny, nx)``."""
        x, y = np.meshgrid(self.x, self.y)
        return x, y

    def refine(self, k: int) -> UniformGrid:
        """The same domain with every cell split into ``k x k`` cells, same corner and row order."""
        if k < 1:
            raise ValueError(f"refinement factor must be positive, got {k}")
        return replace(self, dx=self.dx / k, nx=self.nx * k, ny=self.ny * k)
