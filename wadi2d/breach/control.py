"""Breaches during a run (W63): triggers, the growing opening, the pipe's orifice flow, the record.

Interface for the run loop: :func:`build_breaches` gives a :class:`BreachSet` or None; each window ``window_end``
shortens a window to the next known event (a trigger time, the end of a duration, the end of formation) so it starts on
the second, ``add_rates`` puts the pipes' flows into the window's source rates, the stepper's callback ``on_step``
checks the triggers and grows the breaches every ``update_s``, and ``write`` saves ``series/breach_<dam>.csv``.

The pool level is the higher of the two cells beside the dam face nearest the breach centre; the other is the tailwater.
An open breach is the faces' own flow, so its mass balance is the solver's. A pipe moves water from the pool's cell to
the cell below as an equal and opposite pair of sources, Q = C_p A (2 g H)^0.5, H the pool over the pipe's centre or over
the tailwater if higher (HEC TD-39); its rate is held at most half the pool cell's water per update, so no source ever
asks a cell for water it does not have.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from wadi2d.breach.faces import (
    INVERT_TOLERANCE_M,
    BreachFaces,
    build_faces,
    face_tables,
    mismatch,
    read_back,
    write,
)
from wadi2d.breach.shape import Geometry, Opening, final_geometry, opening, progress, surface
from wadi2d.config.constants import G
from wadi2d.config.schema import Breach, RunConfig

DAM_KINDS = ("crest_line", "embankment")
SERIES_HEADER = "t_s,formed,bottom_m,bottom_width_m,pipe_top_m,pool_level_m,tail_level_m,pipe_q_m3s"


def refusal(cfg: RunConfig) -> str | None:
    """Why this job cannot take a breach, or None."""
    if cfg.mesh.enabled:
        return "a breach runs on the uniform grid in this version: untick the mesh refinement"
    if cfg.strips.enabled:
        return "a breach runs on the uniform grid in this version: untick the corridors"
    if cfg.numerics.local_time_stepping:
        return "a breach is not tested with local time stepping: switch it off"
    return None


@dataclass
class BreachRun:
    b: Breach
    faces: BreachFaces
    geo: Geometry
    model: object
    rows: int
    e_lo: float
    e_hi: float
    cells: tuple[int, int]
    """State indices of the two cells beside the centre face: before it (west or north), its own."""
    floors: tuple[float, float]
    area: float
    entries: tuple[int, int] | None
    """Positions of the two cells in the forcing's rate array, for a pipe."""
    started: float | None = None
    collapsed: float | None = None
    formed: float | None = None
    above_since: float | None = None
    next_check: float = -math.inf
    cut: bool = False
    pipe_rate: float = 0.0
    """m/s out of the pool cell into the one below; the sign says which way."""
    pool_side: int = 0
    base: tuple[float, float] = (0.0, 0.0)
    rows_out: list = field(default_factory=list)

    # --- reading the water
    def levels(self) -> tuple[float, float]:
        m = self.model
        d = m.read_cells("d", m.device_index(np.array(self.cells, np.int64)))
        return self.floors[0] + float(d[0]), self.floors[1] + float(d[1])

    def due(self) -> list[float]:
        """Run times this breach must be stepped onto exactly."""
        b, out = self.b, []
        if self.started is None:
            if b.trigger == "time":
                out.append(b.trigger_time_s)
            elif b.trigger == "level_duration" and self.above_since is not None:
                out.append(self.above_since + b.trigger_duration_s)
        elif self.formed is None:
            out.append(self.started + self.geo.time)
        return out

    def _trigger(self, t: float, pool: float) -> None:
        b = self.b
        if b.trigger == "time":
            if t >= b.trigger_time_s - 1e-9:
                self.started = b.trigger_time_s
            return
        if pool < b.trigger_level:
            self.above_since = None
            return
        if b.trigger == "level":
            self.started = t
            return
        if self.above_since is None:
            self.above_since = t
        if t >= self.above_since + b.trigger_duration_s - 1e-9:
            self.started = self.above_since + b.trigger_duration_s

    # --- growing
    def _cut_faces(self, cut: Opening) -> None:
        f = self.faces
        lowered = np.minimum(f.crested, surface(self.geo, cut, f.s))
        prof = np.maximum(f.free, lowered)
        prof = np.minimum(np.maximum(prof, np.maximum(f.zmin_l, f.zmin_r)[:, None]), f.crested)
        changed = np.any(prof < f.crested - 1e-9, axis=1)
        if not changed.any():
            return
        cw = np.where(changed, self.b.weir_coefficient, f.cw0)
        ft = face_tables(f, np.where(changed[:, None], prof, f.crested), cw, self.rows, self.e_lo, self.e_hi)
        write(self.model.backend, f, ft, self.rows, only=changed)
        self.cut = True
        self.model.stepper.refresh_due = True

    def _pipe(self, cut: Opening, pool: float, tail: float, side: int) -> float:
        """Orifice flow through the pipe, m3/s, held to what the pool cell can give."""
        height = cut.roof - cut.bottom
        area = cut.width * height
        centre = 0.5 * (cut.roof + cut.bottom)
        head = pool - max(centre, tail)
        if area <= 0.0 or head <= 0.0:
            return 0.0
        q = self.b.piping_coefficient * area * math.sqrt(2.0 * G * head)
        h = float(
            self.model.read_cells("h", self.model.device_index(np.array([self.cells[side]], np.int64)))[0]
        )
        return min(q, 0.5 * h * self.area / self.b.update_s)

    def update(self, t: float) -> None:
        b = self.b
        a, c = self.levels()
        side = 0 if a >= c else 1
        pool, tail = (a, c) if side == 0 else (c, a)
        if self.started is None:
            self._trigger(t, pool)
            if self.started is None:
                return
        share = (t - self.started) / self.geo.time
        f = progress(share, b.progression)
        if b.mode == "piping" and self.collapsed is None:
            cut = opening(self.geo, f, b.mode, b.piping_z, False)
            ratio = (cut.roof - cut.bottom) / max(self.geo.top - self.geo.bottom, 1e-9)
            if (
                pool <= cut.roof
                or cut.roof >= self.geo.top
                or (b.collapse_ratio is not None and ratio >= b.collapse_ratio)
            ):
                self.collapsed = t
                self._set_pipe(0.0, side)
            else:
                q = self._pipe(cut, pool, tail, side)
                self._set_pipe(q, side)
                self._record(t, f, cut, pool, tail, q)
                return
        cut = opening(self.geo, f, b.mode, b.piping_z, True)
        self._cut_faces(cut)
        if share >= 1.0 - 1e-12 and self.formed is None:
            self.formed = t
        self._record(t, f, cut, pool, tail, 0.0)

    def _record(self, t, f, cut: Opening, pool, tail, q) -> None:
        roof = cut.roof if math.isfinite(cut.roof) else math.nan
        self.rows_out.append((t, f, cut.bottom, cut.width, roof, pool, tail, q))

    # --- the pipe's sources
    def _set_pipe(self, q: float, side: int) -> None:
        rate = q / self.area
        if rate == 0.0 and self.pipe_rate == 0.0:
            return
        self.pipe_rate, self.pool_side = rate, side
        self.patch()

    def pair(self) -> tuple[float, float]:
        """Source rates of the two cells the pipe adds, m/s."""
        r = self.pipe_rate
        return (-r, r) if self.pool_side == 0 else (r, -r)

    def patch(self) -> None:
        backend = self.model.backend
        add = self.pair()
        values = np.array([self.base[0] + add[0], self.base[1] + add[1]], np.float32)
        idx = np.array(self.cells, np.int64)
        cp = getattr(backend, "cp", None)
        if cp is None:
            backend.src[idx] = values
        else:
            backend.src[cp.asarray(idx)] = cp.asarray(values)


@dataclass
class BreachSet:
    runs: list[BreachRun]
    progress: object = None
    said: set = field(default_factory=set)

    @property
    def piping(self) -> bool:
        return any(r.pipe_rate != 0.0 for r in self.runs)

    def window_end(self, t: float, t_next: float) -> float:
        for run in self.runs:
            for when in run.due():
                if t + 1e-9 < when < t_next:
                    t_next = when
        return t_next

    def add_rates(self, rate: np.ndarray) -> np.ndarray:
        """The window's rates with the pipes' pairs added; the forcing's own rates are kept for the patches between."""
        piping = [r for r in self.runs if r.entries is not None]
        if not piping:
            return rate
        rate = rate.copy()
        for run in piping:
            run.base = (float(rate[run.entries[0]]), float(rate[run.entries[1]]))
            add = run.pair()
            rate[run.entries[0]] += add[0]
            rate[run.entries[1]] += add[1]
        return rate

    def on_step(self, stepper) -> None:
        t = stepper.t
        for run in self.runs:
            if run.formed is not None and (run.b.mode == "overtopping" or run.collapsed is not None):
                continue
            due = any(abs(t - when) <= 1e-6 for when in run.due())
            if t < run.next_check and not due:
                continue
            run.next_check = t + run.b.update_s
            run.update(t)
            self._tell(run)

    def _tell(self, run: BreachRun) -> None:
        if self.progress is None:
            return
        for event, when in (("start", run.started), ("collapse", run.collapsed), ("formed", run.formed)):
            key = (run.b.dam, event)
            if when is not None and key not in self.said:
                self.said.add(key)
                self.progress.emit("breach", dam=run.b.dam, event=event, t=when)

    def write(self, out: Path) -> list[Path]:
        folder = out / "series"
        folder.mkdir(parents=True, exist_ok=True)
        paths = []
        for run in self.runs:
            path = folder / f"breach_{run.b.dam}.csv"
            rows = np.array(run.rows_out, np.float64).reshape(-1, 8)
            np.savetxt(path, rows, delimiter=",", header=SERIES_HEADER, comments="", fmt="%.6f")
            paths.append(path)
        return paths


def _centre_face(faces: BreachFaces, centre: float) -> int:
    return int(np.argmin(np.abs(faces.s.mean(axis=1) - centre)))


def build_breaches(cfg: RunConfig, tables, model, forcing, crs: str, progress=None) -> BreachSet | None:
    """The job's breaches on this model, or None; refuses in words (ValueError) what it cannot do."""
    if not cfg.breaches:
        return None
    why = refusal(cfg)
    if why is not None:
        raise ValueError(why)
    import shapely

    from wadi2d.forcing import manning_grid
    from wadi2d.terrain import Ground, RasterBed, apply_objects

    grid = tables.grid
    named = {o.name: o for o in cfg.terrain.objects if o.kind in DAM_KINDS and o.name}
    runs = []
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        bed.bind(grid.x0, grid.y0)
        edits = apply_objects(
            grid, cfg.terrain.objects, bed.pixel, cfg.terrain, Ground(bed, grid.x0, grid.y0)
        )
        manning = manning_grid(cfg, grid, crs)
        for b in cfg.breaches:
            obj = named.get(b.dam)
            if obj is None:
                raise ValueError(f"breach: no crest line or embankment named '{b.dam}'")
            width = obj.section.width if obj.kind == "embankment" and obj.section is not None else 0.0
            snap = 0.75 * grid.dx + 0.5 * width
            faces = build_faces(tables, bed, edits, obj, manning, snap)
            run = _make_run(cfg, tables, model, forcing, b, obj, faces, shapely, progress)
            runs.append(run)
    return BreachSet(runs, progress)


def _make_run(
    cfg, tables, model, forcing, b: Breach, obj, faces: BreachFaces, shapely, progress
) -> BreachRun:
    grid = tables.grid
    rows, e_lo, e_hi = cfg.tables.rows, cfg.tables.face_depth_min, cfg.tables.face_depth_max
    built = read_back(model.backend, faces, rows)
    rebuilt = face_tables(faces, faces.crested, faces.cw0, rows, e_lo, e_hi)
    dz, dt = mismatch(built, rebuilt)
    if dz > INVERT_TOLERANCE_M or dt > 1e-3:
        raise ValueError(
            f"breach of {b.dam}: its faces cannot be rebuilt as the tables built them (invert off by {dz:.3g} m, table "
            f"by {dt:.2g}); a lined channel or a Manning raster under the dam is not handled"
        )
    length = shapely.LineString(obj.coordinates).length
    if b.station_m is not None and b.station_m > length:
        raise ValueError(
            f"breach of {b.dam}: station {b.station_m:g} m lies past the line's end at {length:.0f} m"
        )
    centre = b.station_m
    if centre is None:
        low = np.unravel_index(np.argmin(faces.free), faces.free.shape)
        centre = float(faces.s[low])
    near = np.unravel_index(np.argmin(np.abs(faces.s - centre)), faces.s.shape)
    top = float(faces.crested[near])
    geo, note = final_geometry(b, centre, top)
    if progress is not None and note is not None:
        progress.emit("breach", dam=b.dam, event="estimated", note=note)
    m = _centre_face(faces, centre)
    (jl, il), (jr, ir) = faces.cells(m)
    cells = (model.cell_state_index(jl, il), model.cell_state_index(jr, ir))
    floors = (float(tables.zmin[jl, il]), float(tables.zmin[jr, ir]))
    entries = None
    if b.mode == "piping":
        lattice = np.asarray(forcing.state[: forcing.n_lattice])
        where = [np.nonzero(lattice == c)[0] for c in cells]
        if any(w.size != 1 for w in where):
            raise ValueError(f"breach of {b.dam}: the pipe's cells are not interior cells of the grid")
        entries = (int(where[0][0]), int(where[1][0]))
    return BreachRun(b, faces, geo, model, rows, e_lo, e_hi, cells, floors, grid.dx * grid.dx, entries)
