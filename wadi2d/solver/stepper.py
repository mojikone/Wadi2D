"""Stepper: the one time loop. It knows nothing of storms or files: it advances a backend and calls back."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from wadi2d.config.schema import Numerics
from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import STRIDE2


class NumericalFailure(RuntimeError):
    """The time step collapsed or a NaN appeared."""


@dataclass
class Stepper:
    backend: object
    grid: TileGrid
    num: Numerics
    t: float = 0.0
    dt: float = 0.01
    nsteps: int = 0

    def __post_init__(self) -> None:
        self.adaptive_active = True
        self.keep_active = np.zeros(self.grid.ntiles, bool)
        self.refresh_due = True
        self.dt = self.num.cfl * self.grid.dx / self.num.wave_floor
        """Tiles that stay active whatever the water does: sources and boundaries."""

    def rebuild_active(self, retain: bool = False) -> None:
        """Active: a wet tile, a tile with a source, and all their neighbours; water moves under a cell per step.

        ``retain`` keeps the tiles already active: the wet flags may be old, and only a step that has just written
        them may drop a tile. Without this a tile can leave the list with water in it.
        """
        wet = self.backend.wet_flags().astype(bool) | self.keep_active
        wet[0] = False
        act = wet.copy()
        act[self.grid.nbr[wet].ravel()] = True
        if retain:
            act[self.backend.active_tiles] = True
        act[0] = False
        self.backend.set_active(np.nonzero(act)[0].astype(np.int32))

    def advance(self, t_end: float, on_step: Callable[[Stepper], None] | None = None) -> float:
        """Run to ``t_end`` exactly."""
        b = self.backend
        num = self.num
        dx = self.grid.dx
        while self.t < t_end - 1e-9:
            refresh = self.refresh_due or self.nsteps % num.dt_every == 0
            self.refresh_due = False
            activate = self.nsteps % num.active_every == 0
            dt = min(self.dt, t_end - self.t, num.dt_max)
            b.step(dt, refresh, activate)
            self.t += dt
            self.nsteps += 1
            if refresh:
                w = b.max_wave()
                if not np.isfinite(w):
                    raise NumericalFailure(f"non-finite wave speed at t = {self.t:.3f} s")
                self.dt = min(num.cfl * dx / max(w, num.wave_floor), num.dt_max)
                if self.dt < num.dt_min:
                    raise NumericalFailure(
                        f"time step {self.dt:.2e} s below the minimum at t = {self.t:.3f} s"
                    )
            if activate and self.adaptive_active:
                self.rebuild_active()
            if on_step is not None:
                on_step(self)
        return self.t


def state_size(grid: TileGrid) -> int:
    return grid.ntiles * STRIDE2
