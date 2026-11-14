"""Flow hydrograph lines (W61): HEC-RAS's Flow Hydrograph boundary on the grid. Interface: :func:`open_lines`,
:func:`flow_lines`, :func:`line_injections`, :func:`flow_series`, :class:`LineInjection`.

A ``flow`` boundary prescribes no level. Its line picks cells as every boundary does (``cells_along``, with ``snap_m``
for a line drawn just off the domain), those cells stay in the model, and the hydrograph enters them as volume through
the source vector, refreshed every ``run.source_every_s`` like a point inflow, so the uniform grid, the quadtree and a
strip job (whose strip keeps squares under every boundary line) take it alike, CPU and GPU from one source.

How the flow is shared across the line, HEC-RAS's way [Likely: the 6.x 2D manual describes the energy slope and the
conveyance weighting; its exact weighting is not published]: from Q and the energy slope a normal-depth water surface is
found across the line, and each cell takes its conveyance under that surface, w / n * hbar^(5/3), w the length of line
in the cell, hbar the cell's own sub-grid mean depth at that level. Cells whose ground stands above the surface take
nothing. ``conveyance`` instead weights each cell at its own water level, the normal depth only while the line is dry.

Momentum (W70, ``flow.momentum``, on by default): HEC-RAS puts a flow line's water through the boundary faces and
TUFLOW HPC feeds a QT line through a level boundary with a uniform energy along it, so in both the water enters moving.
Here each cell's share Q brings Q U normal to the line, U = Q over the cell's flow area across the line (its width of
line times its sub-grid mean depth at the level that shared the flow), capped at ``numerics.u_max``, onto the cell's
downstream x and y faces (:func:`momentum_kick`, applied by ``solver.momentum``). The uniform step only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely

from wadi2d.config.schema import FLOW_CONVEYANCE, Boundary, RunConfig
from wadi2d.engine.observed import KINDS_READ, TO_SI
from wadi2d.forcing import Forcing, Injection, cells_along, manning_grid
from wadi2d.io.series import FLOW as WANT_FLOW
from wadi2d.io.series import SECONDS_PER_MINUTE, read_record
from wadi2d.solver.layout import TILE
from wadi2d.solver.momentum import FaceKick
from wadi2d.solver.state import state_index
from wadi2d.tables import GridTables, hbar_at_level

FLOW_KIND = "flow"
FIVE_THIRDS = 5.0 / 3.0
BISECTIONS = 60
REACH_M = 1000.0
"""Deepest normal depth looked for above the lowest cell of a line, m."""


def open_lines(boundaries: list[Boundary]) -> list[Boundary]:
    """The lines whose cells are boundary cells: every kind but ``flow``."""
    return [b for b in boundaries if b.kind != FLOW_KIND]


def flow_lines(boundaries: list[Boundary]) -> list[tuple[str, Boundary]]:
    """The ``flow`` lines with what warnings call them, numbered as the job lists its boundaries."""
    return [(b.name or f"Inflow line {n}", b) for n, b in enumerate(boundaries, start=1) if b.kind == FLOW_KIND]


def flow_series(b: Boundary, cfg: RunConfig) -> tuple[np.ndarray, np.ndarray]:
    """(t_s from the run's start, m3/s) of a flow line: its table, or its CSV or DSS record put on the run's clock."""
    f = b.flow
    if f.file is None:
        return np.asarray(f.times_s, np.float64), np.asarray(f.flows, np.float64)
    record = read_record(f.file, f.record, f.time_unit, f.time_format, want=WANT_FLOW)
    if record.kind not in KINDS_READ:
        raise ValueError(f"{record.source} is a {record.kind} record, not a flow")
    origin = f.start or cfg.storm.rain_start
    if record.dated and origin is None:
        raise ValueError(f"{record.source} has dates: give the line's flow.start, the date of the run's minute zero")
    units = (record.units or "m3/s").strip().lower()
    if units not in TO_SI["flow"]:
        raise ValueError(f"{record.source}: flow in {record.units!r}, which is neither m3/s nor cfs")
    t = np.asarray(record.minutes_from(None if origin is None else np.datetime64(origin, "s")), np.float64)
    q = np.asarray(record.values, np.float64) * TO_SI["flow"][units]
    keep = np.isfinite(q)
    if np.any(q[keep] < 0.0):
        raise ValueError(f"{record.source}: a negative flow; a flow line only brings water in")
    return t[keep] * SECONDS_PER_MINUTE, q[keep]


def cell_tables(tables: GridTables, j: np.ndarray, i: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each cell's storage table (``hc``, ``dtab``), read from the tiles at raster cells (j, i)."""
    grid = tables.grid
    if getattr(grid, "quad", False):
        t, oj, oi = grid.locate_raster(j, i)
    else:
        t, oj, oi = grid.tile_of[j // TILE, i // TILE], j % TILE, i % TILE
    return np.asarray(tables.hc[t, oj, oi], np.float64), np.asarray(tables.dtab[t, oj, oi], np.float64)


@dataclass
class LineInjection(Injection):
    """A hydrograph shared across a line's cells by conveyance."""

    width: np.ndarray | None = None
    """Length of line in each cell, m."""
    manning: np.ndarray | None = None
    ground: np.ndarray | None = None
    """Lowest ground of each cell, the datum of the solver's level, m."""
    hc: np.ndarray | None = None
    dtab: np.ndarray | None = None
    distribution: str = "normal_depth"
    slope: float = 0.005
    level: float = float("nan")
    """The last normal-depth water surface across the line, m."""
    east: np.ndarray | None = None
    south: np.ndarray | None = None
    """Unit normal of the line at each cell, pointing where the water goes: east and south components (W70)."""
    face_x: np.ndarray | None = None
    face_y: np.ndarray | None = None
    """State indices of each cell's west and east, and north and south faces, (2, n), -1 against a wall (W70)."""
    last_q: float = 0.0
    last_weights: np.ndarray | None = None
    last_levels: np.ndarray | None = None
    """The window's flow, shares and the level each cell's share was found at (W70)."""

    def conveyance(self, level: float | np.ndarray) -> np.ndarray:
        """w / n * hbar^(5/3) of each cell at a water level, m3/s at unit slope."""
        hbar = np.maximum(np.asarray(hbar_at_level(level, self.ground, self.hc, self.dtab), np.float64), 0.0)
        return self.width / self.manning * hbar**FIVE_THIRDS

    def normal_level(self, q: float) -> float:
        """The level across the line that carries ``q`` at the energy slope, by bisection."""
        root = np.sqrt(self.slope)
        low = float(self.ground.min())
        high = low + 1.0
        while self.conveyance(high).sum() * root < q:
            high = low + 2.0 * (high - low)
            if high - low > REACH_M:
                raise ValueError(f"{self.name}: {q:.1f} m3/s finds no normal depth within {REACH_M:g} m")
        for _ in range(BISECTIONS):
            mid = 0.5 * (low + high)
            if self.conveyance(mid).sum() * root < q:
                low = mid
            else:
                high = mid
        return high

    def mean_flow(self, t0: float, t1: float) -> float:
        q = super().mean_flow(t0, t1)
        if q <= 0.0:
            self.last_q = 0.0  # a window with no flow brings no momentum; the forcing skips its weights
        return q

    def weights(self, depth: np.ndarray, q: float) -> np.ndarray:
        out, levels = self._weights(depth, q)
        self.last_q, self.last_weights, self.last_levels = q, out, levels
        return out

    def _weights(self, depth: np.ndarray, q: float) -> tuple[np.ndarray, np.ndarray]:
        if self.distribution == FLOW_CONVEYANCE:
            wet = depth >= self.min_depth
            if wet.any():
                own = self.ground + np.asarray(depth, np.float64)
                k = np.where(wet, self.conveyance(own), 0.0)
                if k.sum() > 0.0:
                    return k / k.sum(), own
        self.level = self.normal_level(q)
        k = self.conveyance(self.level)
        levels = np.full(k.size, self.level)
        if k.sum() <= 0.0:
            return self.share(depth), self.ground + np.asarray(depth, np.float64)
        return k / k.sum(), levels

    def velocity(self, u_max: float) -> np.ndarray:
        """Each cell's speed across the line in the last window: its share over its flow area, capped."""
        if self.last_weights is None or self.last_q <= 0.0:
            return np.zeros(self.cells.size)
        hbar = np.maximum(np.asarray(hbar_at_level(self.last_levels, self.ground, self.hc, self.dtab), np.float64), 0.0)
        area = self.width * hbar
        share = self.last_q * self.last_weights
        with np.errstate(divide="ignore", invalid="ignore"):
            u = np.where(area > 1e-9, share / area, 0.0)
        return np.minimum(u, u_max)


def _positions(forcing: Forcing, index: np.ndarray, name: str) -> np.ndarray:
    """Where state indices stand in the source vector; a cell that is not interior is refused by name."""
    state = forcing.state[: forcing.n_lattice]
    order = np.argsort(state, kind="stable")
    found = np.minimum(np.searchsorted(state, index, sorter=order), state.size - 1)
    pos = order[found]
    missing = state[pos] != index
    if missing.any():
        raise ValueError(
            f"{name}: {int(missing.sum())} of its cells are cells of another open boundary or hand-back line; "
            "a flow line must not share cells with one"
        )
    return pos


def _check_strip(tables: GridTables, b: Boundary, name: str) -> None:
    """A line over squares a strip replaced would put its flow in the squares beside the corridor: refused. The
    centres generator keeps squares under every boundary line, so its corridors stop short of the line."""
    strip = getattr(tables, "strip", None)
    if strip is None or not strip.strip.masked[0].size:
        return
    grid = tables.grid
    replaced = np.zeros(grid.shape, bool)
    replaced[strip.strip.masked[0], strip.strip.masked[1]] = True
    line = shapely.LineString(b.coordinates)
    pts = shapely.line_interpolate_point(line, np.linspace(0.0, line.length, max(int(4 * line.length / grid.dx), 2)))
    j = np.floor((grid.y0 - shapely.get_y(pts)) / grid.dx).astype(np.int64)
    i = np.floor((shapely.get_x(pts) - grid.x0) / grid.dx).astype(np.int64)
    inside = (j >= 0) & (j < grid.shape[0]) & (i >= 0) & (i < grid.shape[1])
    if replaced[j[inside], i[inside]].any():
        raise ValueError(
            f"{name} crosses the cells of an aligned corridor, which a flow line cannot feed: end the corridor clear "
            "of the line, or build the strip with strips.generator 'centres', which keeps squares under boundary lines"
        )


SIDE_CELLS = 2.0
"""How far either side of the line, in cells, the automatic direction looks at the ground."""


def _normals(line: shapely.LineString, x: np.ndarray, y: np.ndarray, dx: float) -> tuple[np.ndarray, np.ndarray]:
    """Unit normal to the left of the line as drawn, at the point of the line nearest each cell centre: (x, y)."""
    at = shapely.line_locate_point(line, shapely.points(x, y))
    step = min(0.5 * dx, 0.5 * line.length)
    a = shapely.line_interpolate_point(line, np.maximum(at - step, 0.0))
    b = shapely.line_interpolate_point(line, np.minimum(at + step, line.length))
    tx, ty = shapely.get_x(b) - shapely.get_x(a), shapely.get_y(b) - shapely.get_y(a)
    norm = np.maximum(np.hypot(tx, ty), 1e-12)
    return -ty / norm, tx / norm


def _side(grid, zmin: np.ndarray, x: np.ndarray, y: np.ndarray, nx: np.ndarray, ny: np.ndarray, sign: float):
    """Active cells and their mean lowest ground, a few cells to one side of the line."""
    px, py = x + sign * SIDE_CELLS * grid.dx * nx, y + sign * SIDE_CELLS * grid.dx * ny
    j = np.floor((grid.y0 - py) / grid.dx).astype(np.int64)
    i = np.floor((px - grid.x0) / grid.dx).astype(np.int64)
    inside = (j >= 0) & (j < grid.shape[0]) & (i >= 0) & (i < grid.shape[1])
    active = np.zeros(j.size, bool)
    active[inside] = grid.mask[j[inside], i[inside]]
    ground = float(np.mean(zmin[j[active], i[active]])) if active.any() else float("inf")
    return int(active.sum()), ground


def _direction(b: Boundary, grid, zmin, x, y, nx, ny) -> float:
    """+1 where the water goes to the left of the line as drawn, -1 to the right."""
    choice = b.flow.direction
    if choice != "auto":
        return 1.0 if choice == "left" else -1.0
    left, z_left = _side(grid, zmin, x, y, nx, ny, 1.0)
    right, z_right = _side(grid, zmin, x, y, nx, ny, -1.0)
    if max(left, right) > 0 and abs(left - right) > 0.25 * max(left, right):
        return 1.0 if left > right else -1.0  # a line on the domain's edge: into the domain
    return 1.0 if z_left <= z_right else -1.0  # inside the domain: downhill


def _cell_faces(grid, j, i) -> tuple[np.ndarray, np.ndarray]:
    """State indices of each cell's two x faces (west, east) and two y faces (north, south), shape (2, n): a face is
    stored at the cell south or east of it, so the east face is the east neighbour's. -1 where the cell beyond the
    face is not active: a wall takes no momentum."""
    out = []
    own = np.asarray(state_index(grid, j, i), np.int64)
    for dj, di in ((0, 1), (1, 0)):
        index = np.full((2, j.size), -1, np.int64)
        for side, sign in enumerate((-1, 1)):
            jn, i_n = j + sign * dj, i + sign * di
            ok = (jn >= 0) & (i_n >= 0) & (jn < grid.shape[0]) & (i_n < grid.shape[1])
            ok[ok] = grid.mask[jn[ok], i_n[ok]]
            if sign < 0:
                index[side, ok] = own[ok]
            else:
                index[side, ok] = np.asarray(state_index(grid, jn[ok], i_n[ok]), np.int64)
        out.append(index)
    return out[0], out[1]


def momentum_kick(injections: list[LineInjection], dx: float, u_max: float) -> FaceKick | None:
    """The momentum the lines' water brings this window, as rates on faces. A cell's source Q U n is shared half to
    each of its two faces in each direction, the staggered scheme's own average of a cell quantity to a face; S / L =
    Q U n / (2 dx). On a line against a wall the wall's half is lost, and the scheme's centred discharge, half of Q at
    the cell centre, carries the other half in: a whole Q U, as through a boundary face."""
    parts: list[list[np.ndarray]] = [[], [], [], []]
    for inj in injections:
        if inj.east is None:
            continue
        flux = inj.last_q * (inj.last_weights if inj.last_weights is not None else 0.0) * inj.velocity(u_max)
        for n, (faces, comp) in enumerate(((inj.face_x, inj.east), (inj.face_y, inj.south))):
            for face in faces:
                keep = (face >= 0) & (flux > 0.0) & (np.abs(comp) > 1e-9)
                parts[2 * n].append(face[keep])
                parts[2 * n + 1].append(0.5 * flux[keep] * comp[keep] / dx)
    if not any(p.size for p in parts[0] + parts[2]):
        return None
    return FaceKick.build(*(np.concatenate(p) if p else np.zeros(0) for p in parts))


def line_injections(
    cfg: RunConfig, tables: GridTables, forcing: Forcing, crs: str = ""
) -> tuple[list[LineInjection], list[str]]:
    """The injections of the job's flow lines, and warnings for lines that open much less than their length."""
    grid = tables.grid
    out, notes = [], []
    manning = manning_grid(cfg, grid, crs)
    for name, b in flow_lines(cfg.boundaries):
        _check_strip(tables, b, name)
        j, i = cells_along(grid, b.coordinates, cfg.grid.line_samples, b.snap_m)
        line = shapely.LineString(b.coordinates)
        if j.size * grid.dx < b.min_share * line.length:
            notes.append(
                f"{name}: the line is {line.length / 1000.0:.1f} km long but opens only {j.size * grid.dx / 1000.0:.1f} "
                f"km of the domain: much of it lies more than {b.snap_m:g} m off the active cells. Its flow enters the "
                "cells it found. Draw it on or just inside the domain edge."
            )
        boxes = shapely.box(
            grid.x0 + i * grid.dx, grid.y0 - (j + 1) * grid.dx, grid.x0 + (i + 1) * grid.dx, grid.y0 - j * grid.dx
        )
        inside = shapely.length(shapely.intersection(boxes, line))
        pos, back = np.unique(_positions(forcing, np.asarray(state_index(grid, j, i), np.int64), name), return_inverse=True)
        width = np.zeros(pos.size)
        np.add.at(width, back, inside)
        size = np.full(pos.size, grid.dx) if forcing.areas is None else np.sqrt(forcing.areas[pos])
        width = np.where(width > 0.0, width, size)  # a cell found off the line, by the snap, takes its own width
        jj, ii = forcing.jj[pos], forcing.ii[pos]
        n = np.full(pos.size, float(manning)) if np.isscalar(manning) else np.asarray(manning, np.float64)[jj, ii]
        hc, dtab = cell_tables(tables, jj, ii)
        times, flows = flow_series(b, cfg)
        ground = np.asarray(forcing.zmin[pos], np.float64)
        index = forcing.model.device_index(forcing.state[pos])
        inj = LineInjection(
            name, pos, index, int(np.argmin(ground)), times, flows, cfg.hydrology.inject_min_depth,
            width=width, manning=n, ground=ground, hc=hc, dtab=dtab, distribution=b.flow.distribution,
            slope=b.flow.slope,
        )  # fmt: skip
        if b.flow.momentum and not getattr(grid, "quad", False):
            x, y = forcing.x[pos], forcing.y[pos]
            nx, ny = _normals(line, x, y, grid.dx)
            sign = _direction(b, grid, tables.zmin, x, y, nx, ny)
            inj.east, inj.south = sign * nx, -sign * ny
            inj.face_x, inj.face_y = _cell_faces(grid, jj, ii)
        out.append(inj)
    return out, notes


def momentum_lines(cfg: RunConfig, kicks: bool) -> tuple[bool, list[str]]:
    """Whether the run carries the flow lines' momentum, and the warning when a default could not be honoured. A line
    that asks for it in so many words on a step that cannot take it is refused."""
    asked = [(name, b) for name, b in flow_lines(cfg.boundaries) if b.flow.momentum]
    if not asked or kicks:
        return bool(asked), []
    named = [name for name, b in asked if "momentum" in b.flow.model_fields_set]
    if named:
        raise ValueError(
            f"{named[0]}: flow.momentum needs the uniform step; the quadtree and local time stepping take a flow line "
            "only as volume at rest. Set flow.momentum false, or run on the uniform grid without local time stepping"
        )
    return False, [
        "Flow lines enter as volume at rest on this run: their momentum needs the uniform step, and the job uses the "
        "quadtree or local time stepping. Depth next to a line reads high (W61, W70)"
    ]
