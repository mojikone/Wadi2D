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

What it does not do: the water enters with no momentum, as the point inflows do; a momentum source normal to the line
would be a kernel change on three kernels (tiles, polygons, GPU) and is not built.
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

    def weights(self, depth: np.ndarray, q: float) -> np.ndarray:
        if self.distribution == FLOW_CONVEYANCE:
            wet = depth >= self.min_depth
            if wet.any():
                k = np.where(wet, self.conveyance(self.ground + np.asarray(depth, np.float64)), 0.0)
                if k.sum() > 0.0:
                    return k / k.sum()
        self.level = self.normal_level(q)
        k = self.conveyance(self.level)
        if k.sum() <= 0.0:
            return self.share(depth)
        return k / k.sum()


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
        out.append(
            LineInjection(
                name, pos, index, int(np.argmin(ground)), times, flows, cfg.hydrology.inject_min_depth,
                width=width, manning=n, ground=ground, hc=hc, dtab=dtab, distribution=b.flow.distribution,
                slope=b.flow.slope,
            )
        )
    return out, notes
