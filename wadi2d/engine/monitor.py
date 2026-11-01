"""What watches a run: maxima, series, the water balance, progress, the live raster, the stop file, checkpoints.

The stepper calls :meth:`Monitor.on_step` after every step, so everything here is a counter check until something
is due. Sampling the boundary flow only on the steps that already synchronise keeps the cost of the balance low.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.engine.maxima import Maxima
from wadi2d.forcing import BoundarySet, LineFaces, line_faces
from wadi2d.io.geotiff import LiveRaster
from wadi2d.io.progress import Progress
from wadi2d.io.results import Results
from wadi2d.solver.model import Model
from wadi2d.solver.state import state_index
from wadi2d.solver.stepper import Stepper
from wadi2d.tables import GridTables


class StopRequested(RuntimeError):
    """The stop file appeared."""


@dataclass
class Balance:
    """Water accounts of the interior cells, m3. The boundary is sampled and integrated by the trapezoid rule."""

    rain: float = 0.0
    inflow: float = 0.0
    outflow: float = 0.0
    storage0: float = 0.0
    storage: float = 0.0
    last_t: float = 0.0
    last_q: float = 0.0
    last_step: int = 0

    @property
    def error(self) -> float:
        return self.rain + self.inflow - self.outflow - (self.storage - self.storage0)

    @property
    def relative(self) -> float:
        """Error over the water that entered the model."""
        scale = max(self.rain + self.inflow + max(-self.outflow, 0.0) + self.storage0, 1e-9)
        return self.error / scale


@dataclass
class Series:
    """One recorded location: columns by quantity, appended at each record time."""

    name: str
    kind: str
    columns: dict[str, list[float]] = field(default_factory=dict)


class Monitor:
    """Bound to one model and one run folder."""

    def __init__(
        self,
        cfg: RunConfig,
        tables: GridTables,
        model: Model,
        boundary: BoundarySet,
        results: Results,
        progress: Progress,
        out: Path,
        crs,
    ) -> None:
        o = cfg.outputs
        self.cfg, self.tables, self.model, self.boundary = cfg, tables, model, boundary
        self.results, self.progress, self.out = results, progress, out
        grid = tables.grid
        self.maxima = Maxima(model, o.arrival_depth, o.speed_depth)
        self.balance = Balance()
        self.stop_file = out / "stop"
        self.max_every = o.maxima_every
        self.bal_every = cfg.run.balance_every
        self.started = time.monotonic()
        self.next_tick = self.started + o.progress_every_s
        self.next_live = self.started
        self.next_check = self.started + cfg.run.checkpoint_every_s
        self.next_series = 0.0
        self.next_map = 0.0
        self.times: list[float] = []
        self.dt_min = np.inf
        self.checkpoint_due = False
        self.window = (0.0, 1.0, 0.0, 0.0)
        self.settled = 0.0
        self.live = None
        if o.live_every_s > 0.0:
            self.live = LiveRaster(out / "live" / "depth.tif", grid, crs, o.live_stride)

        inner = grid.mask & ~boundary.mask
        self.storage_index = np.asarray(state_index(grid, *np.nonzero(inner)), np.int64)
        idx = model.device_index
        self.bx, self.by = idx(boundary.xfaces), idx(boundary.yfaces)

        self.point_cells = []
        self.series: list[Series] = []
        for p in o.points:
            j, i = grid.cell_of(p.x, p.y)
            if not (0 <= j < grid.shape[0] and 0 <= i < grid.shape[1] and grid.mask[j, i]):
                progress.emit("warn", message=f"point {p.name} is outside the domain")
                continue
            k = state_index(grid, np.array([j]), np.array([i]))
            self.point_cells.append((idx(np.asarray(k, np.int64)), float(tables.zmin[j, i])))
            self.series.append(Series(p.name, "points", {"depth_m": [], "mean_depth_m": [], "level_m": []}))
        self.lines: list[tuple[object, np.ndarray, object, np.ndarray]] = []
        self.line_series: list[Series] = []
        for ln in o.lines:
            faces: LineFaces = line_faces(grid, ln.coordinates)
            if faces.xfaces.size + faces.yfaces.size == 0:
                progress.emit("warn", message=f"line {ln.name} crosses no active face")
            self.lines.append((idx(faces.xfaces), faces.xsign, idx(faces.yfaces), faces.ysign))
            self.line_series.append(Series(ln.name, "lines", {"discharge_m3s": []}))

    def open_window(self, t0: float, t1: float, rain: float, inflow: float) -> None:
        """The source of [t0, t1] enters the accounts as the run advances through it."""
        self.window = (t0, t1, rain, inflow)
        self.settled = t0

    def settle(self, t: float) -> None:
        """Credit the source up to time t."""
        t0, t1, rain, inflow = self.window
        share = (min(t, t1) - self.settled) / (t1 - t0)
        self.balance.rain += rain * share
        self.balance.inflow += inflow * share
        self.settled = min(t, t1)

    def storage(self) -> float:
        h = self.model.backend.get_field("h")
        return float(h[self.storage_index].sum(dtype=np.float64)) * self.tables.grid.dx**2

    def boundary_flow(self) -> float:
        """Flow out of the interior now, m3/s."""
        b = self.boundary
        if b.size == 0:
            return 0.0
        m = self.model
        return float(
            np.dot(m.read_cells("qx", self.bx), b.xsign) + np.dot(m.read_cells("qy", self.by), b.ysign)
        )

    def sample_balance(self, t: float, step: int) -> None:
        """Integrate the boundary flow since the last sample.

        A step's stored flow is the flow of that step, so the mean over the M steps since the last sample, taken
        as linear in the step number, weighs the new sample (M + 1) / 2M and the old (M - 1) / 2M: exact at M = 1,
        second order above.
        """
        q = self.boundary_flow()
        bal = self.balance
        m = step - bal.last_step
        if m > 0:
            bal.outflow += (t - bal.last_t) * ((m + 1) * q + (m - 1) * bal.last_q) / (2 * m)
            bal.last_t, bal.last_q, bal.last_step = t, q, step

    def record(self, t: float) -> None:
        m = self.model
        self.times.append(t)
        points = zip(self.point_cells, self.series, strict=True)
        for (index, zmin), s in points:
            d = float(m.read_cells("d", index)[0])
            s.columns["depth_m"].append(d)
            s.columns["mean_depth_m"].append(float(m.read_cells("h", index)[0]))
            s.columns["level_m"].append(zmin + d)
        for (ix, sx, iy, sy), s in zip(self.lines, self.line_series, strict=True):
            q = np.dot(m.read_cells("qx", ix), sx) + np.dot(m.read_cells("qy", iy), sy)
            s.columns["discharge_m3s"].append(float(q))

    def snapshot(self, t: float) -> None:
        m = self.model
        d = m.field("d")
        u, v = m.field("u"), m.field("v")
        speed = np.hypot(0.5 * (u + np.roll(u, -1, axis=1)), 0.5 * (v + np.roll(v, -1, axis=0)))
        self.results.snapshot(t, {"depth": d, "mean_depth": m.field("h"), "speed": speed})
        self.progress.emit("output", kind="map", t=t)

    def _tick(self, st: Stepper, now: float) -> None:
        o = self.cfg.outputs
        self.next_tick = now + o.progress_every_s
        self.settle(st.t)
        self.sample_balance(st.t, st.nsteps)
        self.balance.storage = self.storage()
        self.progress.emit(
            "step",
            t=round(st.t, 3),
            dt=round(st.dt, 4),
            steps=st.nsteps,
            active_tiles=int(st.backend.nact),
            volume=round(self.balance.storage, 1),
            mass_error=float(f"{self.balance.relative:.3e}"),
            wall=round(now - self.started, 2),
        )
        if self.stop_file.exists():
            raise StopRequested
        if self.live is not None and now >= self.next_live:
            self.next_live = now + o.live_every_s
            self.live.write(self.model.field("d"))

    def on_step(self, st: Stepper) -> None:
        n = st.nsteps
        t = st.t
        if st.dt < self.dt_min:
            self.dt_min = st.dt
        if n % self.max_every == 0:
            self.maxima.update(t)
        if n % self.bal_every == 0:
            self.sample_balance(t, n)
        if t >= self.next_series:
            self.record(t)
            self.next_series = t + self.cfg.outputs.series_every_s
        every = self.cfg.outputs.map_every_s
        if every > 0.0 and t >= self.next_map:
            self.snapshot(t)
            self.next_map = t + every
        now = time.monotonic()
        if now >= self.next_tick:
            self._tick(st, now)
        if self.cfg.run.checkpoint_every_s > 0.0 and now >= self.next_check:
            self.next_check = now + self.cfg.run.checkpoint_every_s
            self.checkpoint_due = True

    def finish(self, t: float, step: int) -> None:
        """Final samples at time t."""
        self.settle(t)
        self.maxima.update(t)
        self.sample_balance(t, step)
        self.record(t)
        self.balance.storage = self.storage()
