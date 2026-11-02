"""Dry-bed transmission loss on 2D routing cells: a rate over the wetted bed, booked on its own line.

The method is HEC-HMS's percolation channel loss, a constant rate over the wetted area, taken per cell: the wetted
share of the cell plan comes from the sub-grid tables, so a thread 8 m wide in a 20 m cell loses over 8 m. An optional
total per square metre of bed stands for the storage of the alluvium above rock or the water table.

It runs on the Python side, through the source refresh, not in the kernels. Honest about the time scale: the rate is
held for a window of ``run.source_every_s``, and at 100 mm/h a 30 s window takes 0.8 mm from a cell that holds at least
``min_depth_m`` of level, so the state does not move under it. And it cannot touch a run with the loss off, because no
kernel changed. What it gives up: a cell can drain between refreshes and be overdrawn, which ``water_share`` makes rare;
the kernels floor such a cell at zero, and that shows in the balance as error, never as a loss that did not happen.
"""

from __future__ import annotations

import h5py
import numpy as np
import shapely

from wadi2d.config.constants import MM_PER_M
from wadi2d.config.schema import RunConfig
from wadi2d.engine.monitor import Balance, Monitor
from wadi2d.forcing import Forcing
from wadi2d.solver.model import Model
from wadi2d.tables import GridTables
from wadi2d.terrain.vector import read_features

SECONDS_PER_HOUR = 3600.0
GROUP = "transmission"
"""Group of a checkpoint that holds what each bed has taken."""


class BedLoss:
    """Bound to one run: which cells may lose water, and what each has lost so far."""

    def __init__(
        self,
        cfg: RunConfig,
        tables: GridTables,
        model: Model,
        forcing: Forcing,
        crs: str,
        monitor: Monitor,
    ) -> None:
        t = cfg.transmission
        self.model = model
        self.rate = t.rate_mm_h / MM_PER_M / SECONDS_PER_HOUR
        self.room = np.inf if t.max_depth_mm is None else t.max_depth_mm / MM_PER_M
        self.min_depth = t.min_depth_m
        self.share = t.water_share
        self.window_s = cfg.run.source_every_s
        self.cells = self._cells(t.area, tables, forcing, crs)
        self.index = model.device_index(forcing.state[self.cells])
        area = forcing.area if forcing.areas is None else forcing.areas[self.cells]
        self.areas = np.broadcast_to(np.asarray(area, np.float64), self.cells.shape)
        self.used = np.zeros(self.cells.size)
        """Depth each square metre of bed has taken, m."""
        self.last = np.zeros(self.cells.size)
        self.span = (0.0, 1.0)
        monitor.parts.append(self)

    @staticmethod
    def _cells(area: str | None, tables: GridTables, forcing: Forcing, crs: str) -> np.ndarray:
        """Positions in the source vector of the cells it applies to."""
        if area is None:
            return np.arange(forcing.state.size)
        shape = shapely.union_all([geometry for _properties, geometry in read_features(area, crs)])
        x, y = tables.grid.xy_of(forcing.jj, forcing.ii)
        return np.nonzero(shapely.contains_xy(shape, x, y))[0]

    def notes(self) -> list[str]:
        """Plain words for a setting that will not do what it says."""
        if self.cells.size == 0:
            return ["transmission loss: no cell lies inside its area, so nothing will be lost"]
        per_window = self.rate * self.window_s
        if self.min_depth > 0.0 and per_window > self.share * self.min_depth:
            return [
                f"transmission loss: {per_window * MM_PER_M:.1f} mm per source window is more than the water share "
                "of the thinnest channel cell, so those cells lose less than the rate: shorten run.source_every_s "
                "or raise min_depth_m"
            ]
        return []

    def apply(self, out: np.ndarray, t0: float, t1: float) -> float:
        """Take the loss of [t0, t1] from the net source ``out``; the volume it will take, m3."""
        step = t1 - t0
        self.span = (t0, t1)
        self.last[:] = 0.0
        if self.cells.size == 0:
            return 0.0
        read = self.model.read_cells
        plan = read("om", self.index).astype(np.float64)
        water = read("h", self.index).astype(np.float64)
        channel = read("d", self.index) >= self.min_depth
        bed = np.minimum(self.rate, np.maximum(self.room - self.used, 0.0) / step)
        take = np.where(channel, np.minimum(bed * plan, self.share * water / step), 0.0)
        before = out[self.cells]
        after = before - take.astype(np.float32)
        out[self.cells] = after
        taken = before.astype(np.float64) - after.astype(np.float64)
        self.last = np.divide(taken * step, plan, out=np.zeros_like(taken), where=plan > 0.0)
        self.used += self.last
        return float(np.dot(taken, self.areas)) * step

    def finish(self, t: float, balance: Balance) -> None:
        """The balance's line has been kept window by window; nothing to add."""

    def figures(self, balance: Balance) -> dict[str, float]:
        return {"transmission_m3": balance.transmission}

    def write(self, results, out) -> None:
        """The volume is the record; a map of it can come when someone asks for one."""

    def _used_now(self) -> np.ndarray:
        """What has really been taken at the model's time: a stop can fall inside a window."""
        t0, t1 = self.span
        ahead = (t1 - min(self.model.stepper.t, t1)) / (t1 - t0)
        return self.used - ahead * self.last

    def save(self, f: h5py.File) -> None:
        f.create_dataset(f"{GROUP}/used", data=self._used_now())

    def load(self, f: h5py.File) -> None:
        if GROUP not in f:
            raise ValueError(
                "this checkpoint has no record of what the beds took, so they would start dry again: "
                "run without --resume in a new folder"
            )
        self.used = f[f"{GROUP}/used"][()]
