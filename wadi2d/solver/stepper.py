"""Stepper: the one time loop. It knows nothing of storms or files: it advances a backend and calls back."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from wadi2d.config.schema import Numerics
from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import STRIDE2

SLEEP_CHECKS = 2
"""Checks in a row that must find a tile and its surroundings dry before it leaves the active list (W90): by then
both of its face buffers and its wave speed have been rewritten as a dry tile's, so asleep it is what it would be awake."""


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
        self.pinned = np.zeros(self.grid.ntiles, bool)
        """Tiles that stay active for the whole run, whatever the sources: a strip's ghost tiles (W45)."""
        self.refresh_due = True
        self.dt = self.num.cfl * self.grid.dx / self.num.wave_floor
        """Tiles that stay active whatever the water does: sources and boundaries."""
        self.kick = None
        """A momentum source on faces (W70, ``solver.momentum.FaceKick``), applied before every step; the uniform
        step only."""
        self.wake_rules: list[Callable[[np.ndarray], np.ndarray]] = []
        """What else wakes a tile (W90): each takes the tiles that hold water or a source and returns the tiles that
        water beside the lattice (an aligned strip's) can reach before the next check."""
        self.idle = np.zeros(self.grid.ntiles, np.int32)
        """Checks in a row at which a tile was not wanted; it sleeps at ``SLEEP_CHECKS``."""

    def pin(self, tiles: np.ndarray) -> None:
        """Tiles that must see every smallest step; the uniform step has no other kind."""

    def check_period(self) -> int:
        """The most steps between two checks of the active list: how far water can move unseen, in cells."""
        return int(self.num.active_every)

    def rebuild_active(self, retain: bool = False, check: bool = False) -> None:
        """Active: a wet tile, a tile with a source, and all their neighbours; water moves under a cell per step.
        A wake rule adds the tiles that water outside the lattice can reach (a strip's ghosts).

        ``retain`` keeps the tiles already active: the wet flags may be old, and only a step that has just written
        them may drop a tile. Without this a tile can leave the list with water in it. ``check`` is the time
        loop's own call: a tile then leaves only after ``SLEEP_CHECKS`` checks in a row that did not want it.
        With neither, the host has just written the state (a start, a checkpoint): the list is made afresh and no
        tile is touched. With ``adaptive_active`` off every tile is always stepped: the reference a sleeping run
        must equal.
        """
        ntiles = self.grid.ntiles
        if not self.adaptive_active:
            if int(self.backend.nact) != ntiles - 1:
                self.backend.set_active(np.arange(1, ntiles, dtype=np.int32))
            return
        wet = self.backend.wet_flags().astype(bool) | self.keep_active
        wet[0] = False
        act = wet.copy()
        act[self.grid.nbr[wet].ravel()] = True
        for rule in self.wake_rules:
            act |= rule(wet)
        current = np.zeros(ntiles, bool)
        current[self.backend.active_tiles] = True
        if retain:
            act |= current
        elif check:
            self.idle[act] = 0
            self.idle[~act] += 1
            act |= current & (self.idle < SLEEP_CHECKS)
        else:
            self.idle[:] = 0
        act[0] = False
        woken = act & ~current
        self.backend.set_active(np.nonzero(act)[0].astype(np.int32))
        if (retain or check) and woken.any():  # a tile that slept is dry; one the host has just filled is not
            self._wake(np.nonzero(woken)[0].astype(np.int32))

    def _wake(self, tiles: np.ndarray) -> None:
        """A tile that joins the list is made what it would be had it never slept: its wet share written by the
        kernel's own arithmetic (asleep it kept the host's), and every halo of the list filled, its own from its
        neighbours and its neighbours' from it."""
        self.backend.refresh_plan(tiles)
        self.backend.refresh_halos()

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
            if self.kick is not None:
                self.kick.apply(b, dt)
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
                self.rebuild_active(check=True)
            if on_step is not None:
                on_step(self)
        return self.t


def state_size(grid: TileGrid) -> int:
    return grid.ntiles * STRIDE2
