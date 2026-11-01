"""Model: tables + backend + stepper, the object tests, the run driver and the benchmarks use."""

from __future__ import annotations

import numpy as np

from wadi2d.config.schema import Numerics
from wadi2d.solver.backend import BoundaryCells, NumericsRecord, select_backend
from wadi2d.solver.layout import HALO, STRIDE, STRIDE2, TILE, local_index
from wadi2d.solver.state import HostState, from_state, level_field
from wadi2d.solver.stepper import Stepper
from wadi2d.tables.builder import GridTables


class Model:
    def __init__(self, tables: GridTables, num: Numerics | None = None, backend: str = "auto") -> None:
        self.tables = tables
        self.grid = tables.grid
        self.num = num or Numerics()
        record = NumericsRecord.from_config(self.num, self.grid.dx)
        self.backend = select_backend(backend, tables, record)
        self.stepper = Stepper(self.backend, self.grid, self.num)
        self.host = HostState(self.grid, {})
        self.boundary_tiles = np.zeros(0, np.int64)

    def set_depth(self, hbar: np.ndarray) -> None:
        """Set the mean depth grid, with levels through the table and zero velocities."""
        h = np.where(self.grid.mask, hbar, 0.0)
        d = level_field(self.tables, h)
        self.backend.set_field("h", self.host.to_state(h))
        self.backend.set_field("d", self.host.to_state(d))
        self.stepper.backend.wet[:] = self._tile_wet(h)
        self.stepper.rebuild_active()

    def _tile_wet(self, h: np.ndarray) -> np.ndarray:
        grid = self.grid
        out = np.zeros(grid.ntiles, np.int32)
        for t in range(1, grid.ntiles):
            tj, ti = grid.tiles[t]
            out[t] = int(np.any(h[tj * TILE : (tj + 1) * TILE, ti * TILE : (ti + 1) * TILE] > 0.0))
        if hasattr(self.backend, "cp"):
            return self.backend.cp.asarray(out)
        return out

    def set_velocity(self, ucell: np.ndarray, vcell: np.ndarray) -> None:
        """Set face velocities from cell-centred ones; momentum and discharge follow. Call after set_depth."""
        dx = self.grid.dx
        h = self.field("h")
        for axis, (uname, mname, qname), cell in (
            (1, ("u", "mx", "qx"), ucell),
            (0, ("v", "my", "qy"), vcell),
        ):
            un = np.roll(cell, 1, axis=axis)
            hn = np.roll(h, 1, axis=axis)
            face = 0.5 * (cell + un)
            face = np.where((h > 0.0) & (hn > 0.0), face, 0.0)
            abar = 0.5 * (h + hn) * dx
            up = np.where(face > 0.0, hn, h) * dx
            self.backend.set_field(uname, self.host.to_state(face))
            self.backend.set_field(mname, self.host.to_state(abar * face))
            self.backend.set_field(qname, self.host.to_state(up * face))

    def set_source(self, rate: np.ndarray) -> None:
        """Net source rate per cell, m/s, on a (ny, nx) grid; its tiles stay active."""
        self.backend.set_field("src", self.host.to_state(np.where(self.grid.mask, rate, 0.0)))
        grid = self.grid
        keep = self.stepper.keep_active
        keep[:] = False
        for t in range(1, grid.ntiles):
            tj, ti = grid.tiles[t]
            keep[t] = bool(np.any(rate[tj * TILE : (tj + 1) * TILE, ti * TILE : (ti + 1) * TILE] != 0.0))
        keep[self.boundary_tiles] = True
        self.stepper.rebuild_active()

    def set_source_cells(self, cells: np.ndarray, rate: np.ndarray) -> None:
        """The fast form of ``set_source``: ``rate`` per entry of ``cells``, state indices of own cells."""
        src = np.zeros(self.grid.ntiles * STRIDE2, np.float32)
        src[cells] = rate
        self.backend.set_field("src", src)
        keep = self.stepper.keep_active
        keep[:] = False
        keep[cells[rate != 0.0] // STRIDE2] = True
        keep[self.boundary_tiles] = True
        self.stepper.rebuild_active()

    def device_index(self, index: np.ndarray):
        """State indices in the form ``read_cells`` takes."""
        cp = getattr(self.backend, "cp", None)
        return index if cp is None else cp.asarray(index)

    def read_cells(self, name: str, index) -> np.ndarray:
        """Entries of a state array at indices from ``device_index``, without reading the whole array."""
        a = getattr(self.backend, name)[index]
        cp = getattr(self.backend, "cp", None)
        return a if cp is None else cp.asnumpy(a)

    def set_boundary(self, bc: BoundaryCells) -> None:
        self.backend.set_boundary(bc)
        self.boundary_tiles = np.unique(bc.cell // STRIDE2)
        self.stepper.keep_active[self.boundary_tiles] = True
        self.stepper.rebuild_active()

    def advance(self, t_end: float, on_step=None) -> float:
        return self.stepper.advance(t_end, on_step)

    def field(self, name: str) -> np.ndarray:
        """A state array as a (ny, nx) grid."""
        self.backend.synchronize()
        return from_state(self.grid, self.backend.get_field(name))

    def discharge_x(self) -> np.ndarray:
        """Discharge through west faces, m3/s, positive eastward."""
        return self.field("qx")

    def discharge_y(self) -> np.ndarray:
        """Discharge through north faces, m3/s, positive southward."""
        return self.field("qy")

    def volume(self) -> float:
        return float(self.field("h").sum(dtype=np.float64) * self.grid.dx**2)

    def cell_state_index(self, j: int, i: int) -> int:
        t, oj, oi = self.grid.locate(j, i)
        return int(local_index(t, oj + HALO, oi + HALO))


__all__ = ["HALO", "STRIDE", "BoundaryCells", "Model"]
