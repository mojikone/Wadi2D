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
from wadi2d.breach.strip import StripFaces, build_strip_faces
from wadi2d.breach.strip import face_tables as strip_face_tables
from wadi2d.breach.strip import read_back as strip_read_back
from wadi2d.breach.strip import write as strip_write
from wadi2d.config.constants import G
from wadi2d.config.schema import Breach, RunConfig

DAM_KINDS = ("crest_line", "embankment")
SERIES_HEADER = "t_s,formed,bottom_m,bottom_width_m,pipe_top_m,pool_level_m,tail_level_m,pipe_q_m3s"


def refusal(cfg: RunConfig) -> str | None:
    """Why this job cannot take a breach, or None."""
    if cfg.mesh.enabled:
        return "a breach runs on the uniform grid and its corridors in this version: untick the mesh refinement"
    if cfg.numerics.local_time_stepping:
        return "a breach is not tested with local time stepping: switch it off"
    return None


@dataclass
class BreachRun:
    b: Breach
    faces: BreachFaces | None
    """The dam's faces on the squares, None where it has none there."""
    geo: Geometry
    model: object
    rows: int
    e_lo: float
    e_hi: float
    cells: tuple[int, int]
    """The two cells beside the centre face, first the one the face's normal points away from: a state index on the
    squares, a cell index on the strip (W69)."""
    floors: tuple[float, float]
    areas: tuple[float, float]
    entries: tuple[int, int] | None
    """Positions of the two cells in the forcing's rate array, for a pipe."""
    strip: StripFaces | None = None
    """The dam's faces on the strip (W69), None where it has none there."""
    on_strip: tuple[bool, bool] = (False, False)
    started: float | None = None
    collapsed: float | None = None
    formed: float | None = None
    above_since: float | None = None
    next_check: float = -math.inf
    cut: bool = False
    pipe_q: float = 0.0
    """m3/s out of the pool cell into the one below."""
    pool_side: int = 0
    base: tuple[float, float] = (0.0, 0.0)
    rows_out: list = field(default_factory=list)

    @property
    def hybrid(self):
        return getattr(self.model.backend, "hooks", None)

    # --- reading the water
    def _read(self, name: str, which: int) -> float:
        if self.on_strip[which]:
            return float(self.hybrid.strip_host(name)[self.cells[which]])
        m = self.model
        return float(m.read_cells(name, m.device_index(np.array([self.cells[which]], np.int64)))[0])

    def levels(self) -> tuple[float, float]:
        if not any(self.on_strip):
            m = self.model
            d = m.read_cells("d", m.device_index(np.array(self.cells, np.int64)))
            return self.floors[0] + float(d[0]), self.floors[1] + float(d[1])
        return self.floors[0] + self._read("d", 0), self.floors[1] + self._read("d", 1)

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
        changed_any = False
        f = self.faces
        if f is not None:
            lowered = np.minimum(f.crested, surface(self.geo, cut, f.s))
            prof = np.maximum(f.free, lowered)
            prof = np.minimum(np.maximum(prof, np.maximum(f.zmin_l, f.zmin_r)[:, None]), f.crested)
            changed = np.any(prof < f.crested - 1e-9, axis=1)
            if changed.any():
                cw = np.where(changed, self.b.weir_coefficient, f.cw0)
                ft = face_tables(f, np.where(changed[:, None], prof, f.crested), cw, self.rows, self.e_lo, self.e_hi)
                write(self.model.backend, f, ft, self.rows, only=changed)
                changed_any = True
        sf = self.strip
        if sf is not None:
            lowered = np.minimum(sf.crested, surface(self.geo, cut, sf.s))
            floor = np.repeat(np.maximum(sf.zmin_l, sf.zmin_r), np.diff(sf.start))
            prof = np.minimum(np.maximum(np.maximum(sf.free, lowered), floor), sf.crested)
            changed = sf.any_below(prof)
            if changed.any():
                cw = np.where(changed, self.b.weir_coefficient, sf.cw0)
                pick = np.repeat(changed, np.diff(sf.start))
                ft, zf = strip_face_tables(sf, np.where(pick, prof, sf.crested), cw, self.rows, self.e_lo, self.e_hi)
                strip_write(self.hybrid, sf, ft, zf, self.rows, changed)
                changed_any = True
        if changed_any:
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
        h = self._read("h", side)
        return min(q, 0.5 * h * self.areas[side] / self.b.update_s)

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
        if q == 0.0 and self.pipe_q == 0.0:
            return
        self.pipe_q, self.pool_side = q, side
        self.patch()

    def pair(self) -> tuple[float, float]:
        """Source rates of the two cells the pipe adds, m/s: equal and opposite volumes over each cell's area."""
        q = self.pipe_q
        a, b = self.areas
        return (-q / a, q / b) if self.pool_side == 0 else (q / a, -q / b)

    def patch(self) -> None:
        add = self.pair()
        values = np.array([self.base[0] + add[0], self.base[1] + add[1]], np.float32)
        if not any(self.on_strip):
            backend = self.model.backend
            idx = np.array(self.cells, np.int64)
            cp = getattr(backend, "cp", None)
            if cp is None:
                backend.src[idx] = values
            else:
                backend.src[cp.asarray(idx)] = cp.asarray(values)
            return
        for which in (0, 1):
            src = self.hybrid.state.src if self.on_strip[which] else self.model.backend.src
            src[int(self.cells[which])] = values[which]


@dataclass
class BreachSet:
    runs: list[BreachRun]
    progress: object = None
    said: set = field(default_factory=set)

    @property
    def piping(self) -> bool:
        return any(r.pipe_q != 0.0 for r in self.runs)

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


def _strip_cells(sf: StripFaces, mesh, m: int) -> tuple[list[int], list[bool], list[float], list[float]]:
    """The two cells of strip face ``m``: a real strip cell by its index, a ghost as the tile cell it stands for."""
    cells, on, floors, areas = [], [], [], []
    for c in (int(sf.left[m]), int(sf.right[m])):
        floors.append(float(mesh.zmin[c]))
        areas.append(float(mesh.area[c]))
        if c < mesh.real:
            cells.append(c)
            on.append(True)
        else:
            cells.append(int(mesh.ghost_state[c - mesh.real]))
            on.append(False)
    return cells, on, floors, areas


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
            free_edit = edits.edit
            if obj.kind == "embankment":  # the ground without this dam keeps every other edit (W69; W63 took the raw DEM)
                others = [o for o in cfg.terrain.objects if o is not obj]
                free_edit = apply_objects(grid, others, bed.pixel, cfg.terrain, Ground(bed, grid.x0, grid.y0)).edit
            faces = build_faces(tables, bed, edits, obj, manning, snap, free_edit)
            strip = build_strip_faces(cfg, tables, bed, edits, free_edit, obj, model)
            if faces is None and strip is None:
                raise ValueError(f"breach: no open crest face of '{obj.name}' on the grid")
            run = _make_run(cfg, tables, model, forcing, b, obj, faces, strip, shapely, progress)
            runs.append(run)
    return BreachSet(runs, progress)


def _check(b: Breach, built, rebuilt, where: str) -> None:
    dz, dt = mismatch(built, rebuilt)
    if dz > INVERT_TOLERANCE_M or dt > 1e-3:
        raise ValueError(
            f"breach of {b.dam}: its faces {where}cannot be rebuilt as the tables built them (invert off by {dz:.3g} m, "
            f"table by {dt:.2g}); a lined channel or a Manning raster under the dam is not handled"
        )


def _make_run(
    cfg, tables, model, forcing, b: Breach, obj, faces: BreachFaces | None, strip: StripFaces | None, shapely, progress
) -> BreachRun:
    grid = tables.grid
    rows, e_lo, e_hi = cfg.tables.rows, cfg.tables.face_depth_min, cfg.tables.face_depth_max
    if faces is not None:
        _check(b, read_back(model.backend, faces, rows), face_tables(faces, faces.crested, faces.cw0, rows, e_lo, e_hi), "")
    hybrid = getattr(model.backend, "hooks", None)
    if strip is not None:
        rebuilt, _zf = strip_face_tables(strip, strip.crested, strip.cw0, rows, e_lo, e_hi)
        _check(b, strip_read_back(hybrid, strip, rows), rebuilt, "on the corridors ")
    length = shapely.LineString(obj.coordinates).length
    if b.station_m is not None and b.station_m > length:
        raise ValueError(
            f"breach of {b.dam}: station {b.station_m:g} m lies past the line's end at {length:.0f} m"
        )
    # every sample of both parts, the squares' first: stations, crested and free ground
    s_all = np.concatenate([p for p in (None if faces is None else faces.s.ravel(), None if strip is None else strip.s) if p is not None])
    crest_all = np.concatenate([p for p in (None if faces is None else faces.crested.ravel(), None if strip is None else strip.crested) if p is not None])
    free_all = np.concatenate([p for p in (None if faces is None else faces.free.ravel(), None if strip is None else strip.free) if p is not None])
    centre = b.station_m
    if centre is None:
        centre = float(s_all[np.argmin(free_all)])
    top = float(crest_all[np.argmin(np.abs(s_all - centre))])
    geo, note = final_geometry(b, centre, top)
    if progress is not None and note is not None:
        progress.emit("breach", dam=b.dam, event="estimated", note=note)
    gap_sq = math.inf if faces is None else float(np.min(np.abs(faces.s.mean(axis=1) - centre)))
    gap_st = math.inf
    if strip is not None:
        means = strip.per_face(strip.s, np.mean)
        gap_st = float(np.min(np.abs(means - centre)))
    on_strip = (False, False)
    if gap_sq <= gap_st:
        m = _centre_face(faces, centre)
        (jl, il), (jr, ir) = faces.cells(m)
        cells = (model.cell_state_index(jl, il), model.cell_state_index(jr, ir))
        floors = (float(tables.zmin[jl, il]), float(tables.zmin[jr, ir]))
        areas = (grid.dx * grid.dx, grid.dx * grid.dx)
    else:
        m = int(np.argmin(np.abs(means - centre)))
        c, on, fl, ar = _strip_cells(strip, tables.strip.mesh, m)
        cells, on_strip, floors, areas = tuple(c), tuple(on), tuple(fl), tuple(ar)
    entries = None
    if b.mode == "piping":
        lattice = np.asarray(forcing.state[: forcing.n_lattice])
        where = []
        for c, own in zip(cells, on_strip, strict=True):
            where.append(np.array([forcing.n_lattice + c]) if own else np.nonzero(lattice == c)[0])
        if any(w.size != 1 for w in where):
            raise ValueError(f"breach of {b.dam}: the pipe's cells are not interior cells of the grid")
        entries = (int(where[0][0]), int(where[1][0]))
    return BreachRun(
        b, faces, geo, model, rows, e_lo, e_hi, cells, floors, areas, entries, strip=strip, on_strip=on_strip
    )
