"""The time loop with local time stepping: each tile steps a power of two of the smallest step.

A cycle is a run of smallest steps at whose end all tiles stand at one time. Nothing outside looks between cycles,
except the boundary tally, which counts every smallest step through ``substep_hook``. See solver/levels.py for the
levels and gpu/kernels/levels.cu for what happens at an edge between levels.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from wadi2d.solver.levels import LevelRule, Plan, assign_levels, plan_cycle
from wadi2d.solver.stepper import NumericalFailure, Stepper


def trailing_level(n: int, top: int) -> int:
    """The coarsest level due at smallest step ``n``."""
    if n == 0:
        return top
    return min(top, (n & -n).bit_length() - 1)


@dataclass
class Lists:
    """A plan in the backend's form; empty lists are dropped so they cost no launch."""

    groups: list
    upto: list
    halo: list
    coarse: list
    edges_x: list
    edges_y: list
    strips: list


class LevelStepper(Stepper):
    def __post_init__(self) -> None:
        super().__post_init__()
        n = self.num
        self.ops = self.backend.level_ops()
        self.rule = LevelRule(n.cfl, n.lts_wave_floor, n.lts_buffer, n.dt_max, n.lts_levels)
        self.pinned = np.zeros(self.grid.ntiles, bool)
        self.level = np.zeros(self.grid.ntiles, np.int32)
        self.plan: Plan | None = None
        self.lists: Lists | None = None
        self.substep_hook: Callable[[float], None] | None = None
        self.since_active = 0
        self.fresh_wave = False
        self.tile_steps = 0

    def pin(self, tiles: np.ndarray) -> None:
        self.pinned[tiles] = True

    def rebuild_active(self, retain: bool = False) -> None:
        keep = self.backend.active_tiles
        super().rebuild_active(retain)
        if not np.array_equal(keep, self.backend.active_tiles):
            self.plan = None

    def _set_plan(self) -> None:
        active = np.asarray(self.backend.active_tiles)
        p = plan_cycle(self.level, active, self.grid.nbr)
        self.plan = p
        to = self.ops.lists
        self.lists = Lists(
            *(
                [to(a) if a.size else None for a in part]
                for part in (p.groups, p.upto, p.halo, p.coarse, p.edges_x, p.edges_y, p.strips)
            )
        )
        self.ops.set_level(self.level)

    def _reassign(self) -> None:
        """New levels and the smallest step, from the waves of the cycle that just ended."""
        wave = self.ops.wave()
        if not np.all(np.isfinite(wave)):
            raise NumericalFailure(f"non-finite wave speed at t = {self.t:.3f} s")
        active = np.asarray(self.backend.active_tiles)
        keep = self.level.copy()
        pinned = self.pinned & np.isin(np.arange(self.pinned.size), active)
        self.level, self.dt = assign_levels(
            wave, active, self.grid.nbr, self.grid.dx, self.rule, pinned, keep
        )
        if self.dt < self.num.dt_min:
            raise NumericalFailure(f"time step {self.dt:.2e} s below the minimum at t = {self.t:.3f} s")
        if not np.array_equal(keep, self.level):
            self.plan = None

    def _substep(self, n: int, dt0: float, wave_step: bool, wet_due: bool) -> None:
        ops, lists = self.ops, self.lists
        k = trailing_level(n, self.plan.top)
        tiles = lists.upto[k]
        if tiles is None:
            return
        dts = [dt0 * (1 << a) for a in range(k + 1)]
        groups = [(g, dts[a]) for a, g in enumerate(lists.groups[: k + 1]) if g is not None]
        wet_step = wave_step and wet_due
        ops.halo_state(lists.halo[k], n, wave_step)
        if wave_step:
            ops.clear_wave()
        for g, dt in groups:
            ops.faces(g, dt, wave_step)
        for a in range(k + 1):
            if lists.strips[a] is not None:
                ops.strips(lists.strips[a], dts[a], wave_step)
        ops.faces_done(tiles)
        for g, dt in groups:
            ops.limit(g, dt)
        ops.limit_done(tiles)
        for a in range(k + 1):
            if lists.coarse[a] is not None:
                ops.save(lists.coarse[a])
            for edges in (lists.edges_x[a], lists.edges_y[a]):
                if edges is None:
                    continue
                if a < k:
                    ops.estimate(edges)
                else:
                    ops.flux(edges, dts[a])
        if wet_step:
            ops.clear_wet()
        for g, dt in groups:
            ops.update(g, dt, wet_step, wave_step)
        ops.boundary()
        ops.commit(tiles)
        for a in range(k + 1):
            if lists.strips[a] is not None:
                ops.commit_strips(lists.strips[a])
        if self.substep_hook is not None:
            self.substep_hook(dt0)
        self.nsteps += 1
        self.tile_steps += sum(int(g.size) for g, _dt in groups)

    def advance(self, t_end: float, on_step: Callable[[Stepper], None] | None = None) -> float:
        """Run to ``t_end`` exactly."""
        num = self.num
        while self.t < t_end - 1e-9:
            if self.plan is None:
                self._set_plan()
            span = 1 << self.plan.top
            first = not self.fresh_wave
            cycle = 1 if first else span * ((max(num.dt_every, span) + span - 1) // span)
            dt0 = min(self.dt, (t_end - self.t) / cycle)
            self.since_active += cycle
            wet_due = self.since_active >= num.active_every
            for n in range(cycle):
                self._substep(n % span, dt0, n == cycle - span, wet_due)
            self.t = self.t + cycle * dt0
            self.fresh_wave = True
            self._reassign()
            if wet_due:
                self.since_active = 0
                if self.adaptive_active:
                    self.rebuild_active()
            if on_step is not None:
                on_step(self)
        return self.t


def tile_step_share(st: LevelStepper) -> float:
    """Tile-steps taken, over what a uniform step would have taken with the same tiles; for reports."""
    tiles = max(int(st.backend.nact), 1)
    return st.tile_steps / max(st.nsteps * tiles, 1)
