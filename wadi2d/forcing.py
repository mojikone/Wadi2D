"""Job + grid -> what the solver consumes: net source per cell, boundary cells, recorded cells and faces.

Rain falls on every active cell except under lumped subbasins (decision 5). Losses are the HMS cumulative
difference per cell, so a refresh is a difference of cumulative excess and volumes add up whatever the refresh
step. Hydrographs enter a few cells around a point: all to the lowest cell while those cells are dry, then in
proportion to their depth (design note section 6). Boundary cells take neither rain nor inflow, because their
level is overwritten; the balance counts what crosses the faces into them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio import features
from scipy.integrate import cumulative_trapezoid

from wadi2d.config.constants import MM_PER_M
from wadi2d.config.schema import Boundary, Hydrology, RunConfig
from wadi2d.grid.tiles import TileGrid
from wadi2d.hms import load_basin
from wadi2d.hms import sqlite as hms_sqlite
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.losses import ScsCurveNumber
from wadi2d.io.geotiff import grid_transform
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.layout import STRIDE2
from wadi2d.solver.model import Model
from wadi2d.solver.state import state_index
from wadi2d.storm import STORM_METHODS, ArfTable, HypotheticalStorm, PercentPattern, Storm, UniformStorm
from wadi2d.storm.hypothetical import HYPOTHETICAL_STORM, MINUTES_PER_HOUR
from wadi2d.storm.uniform import UNIFORM_STORM
from wadi2d.tables import GridTables, hbar_at_level
from wadi2d.terrain.crest import NORTH, staircase

SAMPLES_PER_CELL = 4
"""Points per cell when a polyline picks the cells it crosses."""

KIND_FIXED, KIND_FREE, KIND_FOLLOW = 0, 1, 2


def build_storm(cfg: RunConfig) -> Storm | None:
    """The job's storm through the storm registry; None when no rain falls."""
    s = cfg.storm
    if s.kind == "none" or s.depth_mm <= 0.0:
        return None
    arf = None if s.arf is None else ArfTable(np.asarray(s.arf.areas_km2), np.asarray(s.arf.factors))
    if s.kind == "uniform":
        storm: UniformStorm = STORM_METHODS.build(
            UNIFORM_STORM, depth_mm=s.depth_mm, duration_minutes=s.duration_min,
            storm_area_km2=s.storm_area_km2, arf=arf,
        )  # fmt: skip
        return storm
    pattern = PercentPattern(np.asarray(s.time_percent), np.asarray(s.depth_percent))
    built: HypotheticalStorm = STORM_METHODS.build(
        HYPOTHETICAL_STORM, depth_mm=s.depth_mm, pattern=pattern,
        duration_hours=s.duration_min / MINUTES_PER_HOUR, storm_area_km2=s.storm_area_km2, arf=arf,
    )  # fmt: skip
    return built


def load_polygons(h: Hydrology) -> dict[str, shapely.Geometry]:
    """Subbasin polygons by name, from the basin .sqlite or a GeoJSON with a ``name`` property."""
    out: dict[str, shapely.Geometry] = {}
    if h.hms_sqlite is not None:
        out.update({row.name: row.shape() for row in hms_sqlite.subbasin_polygons(h.hms_sqlite)})
    if h.polygons is not None:
        data = json.loads(Path(h.polygons).read_text(encoding="utf-8"))
        for feature in data["features"]:
            out[str(feature["properties"]["name"])] = shapely.geometry.shape(feature["geometry"])
    return out


def _labels(grid: TileGrid, polygons: list[shapely.Geometry]) -> np.ndarray:
    """Grid of 1-based polygon numbers by cell centre; 0 outside all of them."""
    if not polygons:
        return np.zeros(grid.shape, np.int32)
    shapes = [(p, n + 1) for n, p in enumerate(polygons)]
    return features.rasterize(
        shapes, out_shape=grid.shape, transform=grid_transform(grid), fill=0, dtype="int32"
    )


def _raster_at_cells(path: str, grid: TileGrid) -> np.ndarray:
    """A raster sampled at the cell centres (nearest), NaN off it or on its nodata."""
    ny, nx = grid.shape
    with rasterio.open(path) as src:
        jj = np.arange(ny)
        ii = np.arange(nx)
        x, y = grid.xy_of(jj, ii)
        inv = ~src.transform
        cols = np.floor(inv.a * x + inv.c).astype(np.int64)
        rows = np.floor(inv.e * y + inv.f).astype(np.int64)
        c0, c1 = max(cols.min(), 0), min(cols.max() + 1, src.width)
        r0, r1 = max(rows.min(), 0), min(rows.max() + 1, src.height)
        out = np.full((ny, nx), np.nan)
        if c0 >= c1 or r0 >= r1:
            return out
        window = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
        a = src.read(1, window=window, masked=True).astype(np.float64).filled(np.nan)
    rkeep = (rows >= r0) & (rows < r1)
    ckeep = (cols >= c0) & (cols < c1)
    out[np.ix_(rkeep, ckeep)] = a[np.ix_(rows[rkeep] - r0, cols[ckeep] - c0)]
    return out


def manning_grid(cfg: RunConfig, grid: TileGrid) -> float | np.ndarray:
    """One value, or a grid where a Manning raster gives one."""
    if cfg.terrain.manning_raster is None:
        return cfg.terrain.manning
    n = _raster_at_cells(cfg.terrain.manning_raster, grid)
    return np.where(np.isfinite(n), n, cfg.terrain.manning)


def _subbasin_curve_numbers(h: Hydrology) -> dict[str, float]:
    """CN of the 2D subbasins: the job's value, else the HMS loss method's."""
    from_hms: dict[str, float] = {}
    if h.hms_basin is not None and any(s.mode == "2d" and s.curve_number is None for s in h.subbasins):
        for name, element in load_basin(h.hms_basin).subbasins.items():
            number = getattr(element.loss, "curve_number", None)
            if number is not None:
                from_hms[name] = number
    out = {s.name: s.curve_number or from_hms.get(s.name) for s in h.subbasins if s.mode == "2d"}
    return {name: value for name, value in out.items() if value is not None}


def curve_numbers(cfg: RunConfig, grid: TileGrid, polygons: dict[str, shapely.Geometry]) -> np.ndarray:
    """CN per cell, NaN for no losses. A raster beats a subbasin value, which beats the job's default."""
    h = cfg.hydrology
    cn = np.full(grid.shape, np.nan if h.curve_number is None else h.curve_number)
    named = [(name, value) for name, value in _subbasin_curve_numbers(h).items() if name in polygons]
    labels = _labels(grid, [polygons[name] for name, _value in named])
    for n, (_name, value) in enumerate(named):
        cn[labels == n + 1] = value
    if cfg.terrain.cn_raster is not None:
        raster = _raster_at_cells(cfg.terrain.cn_raster, grid)
        cn = np.where(np.isfinite(raster), raster, cn)
    return cn


@dataclass
class BoundarySet:
    """Boundary cells, and the faces where water crosses into them."""

    cells: BoundaryCells
    mask: np.ndarray
    xfaces: np.ndarray
    xsign: np.ndarray
    yfaces: np.ndarray
    ysign: np.ndarray

    @property
    def size(self) -> int:
        return int(self.cells.cell.size)


def cells_along(grid: TileGrid, coordinates: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    """Active cells a polyline crosses; a sample just off the domain takes the nearest active cell in reach."""
    line = shapely.LineString(coordinates)
    n = max(int(np.ceil(line.length / grid.dx * SAMPLES_PER_CELL)), 2)
    pts = shapely.line_interpolate_point(line, np.linspace(0.0, line.length, n))
    jj = np.floor((grid.y0 - shapely.get_y(pts)) / grid.dx).astype(np.int64)
    ii = np.floor((shapely.get_x(pts) - grid.x0) / grid.dx).astype(np.int64)
    ny, nx = grid.shape
    found: set[tuple[int, int]] = set()
    for j, i in zip(jj, ii, strict=True):
        for dj, di in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            a, b = j + dj, i + di
            if 0 <= a < ny and 0 <= b < nx and grid.mask[a, b]:
                found.add((int(a), int(b)))
                break
    if not found:
        raise ValueError(f"line from {coordinates[0]} does not touch the domain")
    cells = np.array(sorted(found), np.int64)
    return cells[:, 0], cells[:, 1]


def _one_boundary(b: Boundary, j: np.ndarray, i: np.ndarray, tables: GridTables, taken: np.ndarray):
    """Kind, follow reference and prescribed values of one boundary's cells."""
    grid = tables.grid
    n = j.size
    zmin = tables.zmin[j, i]
    kind = np.full(n, KIND_FIXED, np.int32)
    ref = np.array(state_index(grid, j, i), np.int64)
    d0 = np.zeros(n)
    h0 = np.zeros(n)
    if b.kind == "stage":
        hc = grid.from_tiles(tables.hc)[j, i]
        dtab = grid.from_tiles(tables.dtab)[j, i]
        d0 = np.maximum(b.stage - zmin, 0.0)
        h0 = np.asarray(hbar_at_level(b.stage, zmin, hc, dtab))
    elif b.kind == "free":
        kind[:] = KIND_FREE
    else:
        kind[:] = KIND_FOLLOW
        ny, nx = grid.shape
        for m in range(n):
            options = [
                (a, c)
                for a, c in ((j[m] - 1, i[m]), (j[m] + 1, i[m]), (j[m], i[m] - 1), (j[m], i[m] + 1))
                if 0 <= a < ny and 0 <= c < nx and grid.mask[a, c] and not taken[a, c]
            ]
            if not options:
                kind[m] = KIND_FREE
                continue
            a, c = max(options, key=lambda cell: tables.zbar[cell])
            ref[m] = state_index(grid, np.array(a), np.array(c))
            # level lowered by S dx, but never deeper than the inner cell: a boundary cell in a pit below a dry
            # neighbour would otherwise hold metres of level with no water, and set the time step of the run
            d0[m] = min(tables.zmin[a, c] - zmin[m] - b.slope * grid.dx, 0.0)
    return kind, ref, d0, h0


def boundary_set(boundaries: list[Boundary], tables: GridTables) -> BoundarySet:
    """All boundary cells, and the faces between them and the interior with the sign of an outflow."""
    grid = tables.grid
    taken = np.zeros(grid.shape, bool)
    picked = [cells_along(grid, b.coordinates) for b in boundaries]
    for j, i in picked:
        taken[j, i] = True
    parts = []
    for b, (j, i) in zip(boundaries, picked, strict=True):
        kind, ref, d0, h0 = _one_boundary(b, j, i, tables, taken)
        parts.append((np.array(state_index(grid, j, i), np.int32), ref.astype(np.int32), kind, d0, h0))
    if not parts:
        cells = BoundaryCells.empty()
    else:
        cat = [np.concatenate(a) for a in zip(*parts, strict=True)]
        cells = BoundaryCells(
            cat[0], cat[1], cat[2].astype(np.int32), cat[3].astype(np.float32), cat[4].astype(np.float32)
        )
    inner = grid.mask & ~taken
    faces = []
    for axis in (1, 0):
        out_low = inner & np.roll(taken, -1, axis=axis)  # the interior cell is on the face's low side
        j, i = np.nonzero(out_low)
        if axis == 1:
            i = i + 1
        else:
            j = j + 1
        into = inner & np.roll(
            taken, 1, axis=axis
        )  # the face is the interior cell's own: outflow is negative
        ja, ia = np.nonzero(into)
        index = np.concatenate((state_index(grid, j, i), state_index(grid, ja, ia))).astype(np.int64)
        sign = np.concatenate((np.ones(j.size), -np.ones(ja.size)))
        faces.append((index, sign))
    return BoundarySet(cells, taken, faces[0][0], faces[0][1], faces[1][0], faces[1][1])


@dataclass
class LineFaces:
    """State indices and signs of the faces a design line crosses."""

    xfaces: np.ndarray
    xsign: np.ndarray
    yfaces: np.ndarray
    ysign: np.ndarray


def line_faces(grid: TileGrid, coordinates: list[tuple[float, float]]) -> LineFaces:
    """Faces under a line; discharge is positive to its right."""
    st = staircase(grid, coordinates)
    keep = grid.mask[st.j, st.i]
    north = st.axis == NORTH
    x = keep & ~north
    y = keep & north
    return LineFaces(
        np.asarray(state_index(grid, st.j[x], st.i[x]), np.int64),
        st.side[x].astype(np.float64),
        np.asarray(state_index(grid, st.j[y], st.i[y]), np.int64),
        st.side[y].astype(np.float64),
    )


@dataclass
class Injection:
    """A hydrograph as cumulative volume, and the cells that take it."""

    name: str
    cells: np.ndarray
    """Positions in the source vector."""
    index: object
    """Device form of the same cells' state indices."""
    lowest: int
    """Position within ``cells`` of the lowest one."""
    times: np.ndarray
    volume: np.ndarray
    min_depth: float

    def mean_flow(self, t0: float, t1: float) -> float:
        v = np.interp((t0, t1), self.times, self.volume)
        return float((v[1] - v[0]) / (t1 - t0))

    def share(self, depth: np.ndarray) -> np.ndarray:
        """Weights over the cells."""
        wet = depth >= self.min_depth
        if not wet.any():
            out = np.zeros(depth.size)
            out[self.lowest] = 1.0
            return out
        weights = np.where(wet, depth, 0.0).astype(np.float64)
        return weights / weights.sum()


class Forcing:
    """The net source vector over the interior cells, refreshed once per ``run.source_every_s``."""

    def __init__(
        self,
        cfg: RunConfig,
        tables: GridTables,
        model: Model,
        boundary: BoundarySet,
        storm: Storm | None,
        polygons: dict[str, shapely.Geometry],
        hydrographs: list[tuple[str, tuple[float, float], np.ndarray, np.ndarray]],
    ) -> None:
        grid = tables.grid
        self.model = model
        self.storm = storm
        self.area = grid.dx**2
        interior = grid.mask & ~boundary.mask
        self.jj, self.ii = np.nonzero(interior)
        self.state = np.asarray(state_index(grid, self.jj, self.ii), np.int64)
        self.tile = self.state // STRIDE2

        lumped = [
            polygons[s.name] for s in cfg.hydrology.subbasins if s.mode == "lumped" and s.name in polygons
        ]
        self.rained = _labels(grid, lumped)[self.jj, self.ii] == 0
        self.classes, self.class_of = self._loss_classes(curve_numbers(cfg, grid, polygons))
        self.injections = [self._injection(cfg, tables, *h) for h in hydrographs]

    def _loss_classes(self, cn: np.ndarray) -> tuple[ScsCurveNumber | None, np.ndarray]:
        """Few distinct CN values, so a refresh computes each once; class -1 means rain passes whole."""
        values = cn[self.jj, self.ii]
        has = np.isfinite(values)
        if not has.any():
            return None, np.full(values.size, -1, np.int64)
        unique, inverse = np.unique(values[has], return_inverse=True)
        out = np.full(values.size, -1, np.int64)
        out[has] = inverse
        return ScsCurveNumber(curve_number=unique), out

    def _injection(self, cfg, tables, name, point, times, flows) -> Injection:
        grid = tables.grid
        x, y = grid.xy_of(self.jj, self.ii)
        dist = np.hypot(x - point[0], y - point[1])
        near = np.nonzero(dist <= max(cfg.hydrology.inject_radius, 0.0))[0]
        if near.size == 0:
            near = np.array([int(np.argmin(dist))])
        lowest = int(np.argmin(tables.zmin[self.jj[near], self.ii[near]]))
        volume = np.concatenate(([0.0], cumulative_trapezoid(flows, times)))
        index = self.model.device_index(self.state[near])
        return Injection(
            name, near, index, lowest, np.asarray(times, np.float64), volume, cfg.hydrology.inject_min_depth
        )

    def _excess_mm(self, t: float) -> np.ndarray:
        """Cumulative excess at time t: one value per class, with the plain rain last."""
        depth = float(self.storm.cumulative_depth(np.array([t / SECONDS_PER_MINUTE]))[0])
        if self.classes is None:
            return np.array([depth])
        with np.errstate(divide="ignore", invalid="ignore"):
            excess = self.classes.cumulative_excess(np.array(depth))
        return np.append(np.nan_to_num(excess), depth)

    def rate(self, t0: float, t1: float) -> tuple[np.ndarray, float, float]:
        """Mean net rate over [t0, t1] per interior cell, m/s, with rain and inflow volumes of the window."""
        step = t1 - t0
        out = np.zeros(self.state.size, np.float32)
        rain = 0.0
        if self.storm is not None:
            per_class = (self._excess_mm(t1) - self._excess_mm(t0)) / (MM_PER_M * step)
            out[:] = per_class[self.class_of] * self.rained
            rain = float(out.sum(dtype=np.float64)) * self.area * step
        inflow = 0.0
        for inj in self.injections:
            q = inj.mean_flow(t0, t1)
            if q <= 0.0:
                continue
            added = q * inj.share(self.model.read_cells("d", inj.index)) / self.area
            out[inj.cells] += added.astype(np.float32)
            inflow += float(np.float32(added).sum(dtype=np.float64)) * self.area * step
        return out, rain, inflow
