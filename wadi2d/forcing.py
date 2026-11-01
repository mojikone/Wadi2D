"""Job + grid -> what the solver consumes: net source per cell, boundary cells, recorded cells and faces.

Rain falls on every active cell except under lumped subbasins (decision 5). Losses are the HMS cumulative
difference per cell, so a refresh is a difference of cumulative excess and volumes add up whatever the refresh
step. Hydrographs enter a few cells around a point: all to the lowest cell while those cells are dry, then in
proportion to their depth (design note section 6). Boundary cells take neither rain nor inflow, because their
level is overwritten; the balance counts what crosses the faces into them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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
from wadi2d.terrain.sampling import raster_at_cells
from wadi2d.terrain.vector import read_features

UNIT_DEPTH = 1.0
"""A depth-grid storm is built on 1 mm: it gives each time's share of the depth, the ARF included."""
NAME_FIELD = "name"

KIND_FIXED, KIND_FREE, KIND_FOLLOW = 0, 1, 2


def build_storm(cfg: RunConfig) -> Storm | None:
    """The job's storm through the storm registry; None when the job has no rain.

    A storm with no depth is refused: rain 0 with exit 0 is the worst thing this function could return.
    """
    s = cfg.storm
    if s.kind == "none":
        return None
    if s.depth_grid is None and s.depth_mm <= 0.0:
        raise ValueError(f"storm kind {s.kind!r} has no depth: set storm.depth_mm or storm.depth_grid")
    depth = UNIT_DEPTH if s.depth_grid is not None else s.depth_mm
    arf = None
    if s.arf is not None:
        arf = ArfTable(
            np.asarray(s.arf.areas_km2),
            np.asarray(s.arf.factors),
            reduces_below_table=s.arf.reduces_below_table,
        )
    if s.kind == "uniform":
        storm: UniformStorm = STORM_METHODS.build(
            UNIFORM_STORM, depth_mm=depth, duration_minutes=s.duration_min,
            storm_area_km2=s.storm_area_km2, arf=arf,
        )  # fmt: skip
        return storm
    pattern = PercentPattern(np.asarray(s.time_percent), np.asarray(s.depth_percent))
    built: HypotheticalStorm = STORM_METHODS.build(
        HYPOTHETICAL_STORM, depth_mm=depth, pattern=pattern,
        duration_hours=s.duration_min / MINUTES_PER_HOUR, storm_area_km2=s.storm_area_km2, arf=arf,
    )  # fmt: skip
    return built


def load_polygons(h: Hydrology, crs: str = "") -> dict[str, shapely.Geometry]:
    """Subbasin polygons by name, from the basin .sqlite or a vector file with a ``name`` property."""
    out: dict[str, shapely.Geometry] = {}
    if h.hms_sqlite is not None:
        out.update({row.name: row.shape() for row in hms_sqlite.subbasin_polygons(h.hms_sqlite)})
    if h.polygons is not None:
        for properties, shape in read_features(h.polygons, crs):
            if NAME_FIELD not in properties:
                raise ValueError(f"{h.polygons}: a polygon has no {NAME_FIELD!r} property")
            out[str(properties[NAME_FIELD])] = shape
    return out


def _labels(grid: TileGrid, polygons: list[shapely.Geometry]) -> np.ndarray:
    """Grid of 1-based polygon numbers by cell centre; 0 outside all of them."""
    if not polygons:
        return np.zeros(grid.shape, np.int32)
    shapes = [(p, n + 1) for n, p in enumerate(polygons)]
    return features.rasterize(
        shapes, out_shape=grid.shape, transform=grid_transform(grid), fill=0, dtype="int32"
    )


def manning_grid(cfg: RunConfig, grid: TileGrid, crs: str = "") -> float | np.ndarray:
    """One value, or a grid where a Manning raster gives one."""
    if cfg.terrain.manning_raster is None:
        return cfg.terrain.manning
    n = raster_at_cells(cfg.terrain.manning_raster, grid, crs)
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


def curve_numbers(
    cfg: RunConfig, grid: TileGrid, polygons: dict[str, shapely.Geometry], crs: str = ""
) -> np.ndarray:
    """CN per cell, NaN for no losses. A raster beats a subbasin value, which beats the job's default."""
    h = cfg.hydrology
    cn = np.full(grid.shape, np.nan if h.curve_number is None else h.curve_number)
    named = [(name, value) for name, value in _subbasin_curve_numbers(h).items() if name in polygons]
    labels = _labels(grid, [polygons[name] for name, _value in named])
    for n, (_name, value) in enumerate(named):
        cn[labels == n + 1] = value
    if cfg.terrain.cn_raster is not None:
        raster = raster_at_cells(cfg.terrain.cn_raster, grid, crs)
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


def cells_along(
    grid: TileGrid, coordinates: list[tuple[float, float]], samples: int = 4
) -> tuple[np.ndarray, np.ndarray]:
    """Active cells a polyline crosses; a sample just off the domain takes the nearest active cell in reach."""
    line = shapely.LineString(coordinates)
    n = max(int(np.ceil(line.length / grid.dx * samples)), 2)
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


def boundary_set(boundaries: list[Boundary], tables: GridTables, samples: int = 4) -> BoundarySet:
    """All boundary cells, and the faces between them and the interior with the sign of an outflow."""
    grid = tables.grid
    taken = np.zeros(grid.shape, bool)
    picked = [cells_along(grid, b.coordinates, samples) for b in boundaries]
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
    """A hydrograph, linear between its table times, and the cells that take it."""

    name: str
    cells: np.ndarray
    """Positions in the source vector."""
    index: object
    """Device form of the same cells' state indices."""
    lowest: int
    """Position within ``cells`` of the lowest one."""
    times: np.ndarray
    flows: np.ndarray
    min_depth: float

    def __post_init__(self) -> None:
        if np.any(np.diff(self.times) <= 0.0):
            raise ValueError(f"inflow {self.name}: table times must increase")
        self.volume = np.concatenate(([0.0], cumulative_trapezoid(self.flows, self.times)))

    def volume_at(self, t: float) -> float:
        """The exact integral of the piecewise-linear flow up to t; interpolating volumes would flatten it."""
        times = self.times
        if t <= times[0]:
            return 0.0
        if t >= times[-1]:
            return float(self.volume[-1])
        k = int(np.searchsorted(times, t, side="right")) - 1
        flow = self.flows[k] + (self.flows[k + 1] - self.flows[k]) * (t - times[k]) / (
            times[k + 1] - times[k]
        )
        return float(self.volume[k] + 0.5 * (self.flows[k] + flow) * (t - times[k]))

    def mean_flow(self, t0: float, t1: float) -> float:
        return (self.volume_at(t1) - self.volume_at(t0)) / (t1 - t0)

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
        crs: str = "",
    ) -> None:
        grid = tables.grid
        self.model = model
        self.storm = storm
        self.area = grid.dx**2
        interior = grid.mask & ~boundary.mask
        self.jj, self.ii = np.nonzero(interior)
        self.state = np.asarray(state_index(grid, self.jj, self.ii), np.int64)
        self.tile = self.state // STRIDE2

        names = [s.name for s in cfg.hydrology.subbasins if s.mode == "lumped"]
        missing = [name for name in names if name not in polygons]
        if missing:
            raise ValueError(
                f"lumped subbasins without a polygon would take their rain twice: {missing}; "
                "give hydrology.hms_sqlite or hydrology.polygons"
            )
        self.rained = _labels(grid, [polygons[name] for name in names])[self.jj, self.ii] == 0
        cn = curve_numbers(cfg, grid, polygons, crs)
        self._check_curve_numbers(cfg, cn)
        self.depths = None
        if cfg.storm.depth_grid is not None:
            self.depths = self._read_depths(cfg, grid, crs)
        self.cell_loss = None
        self.classes, self.class_of = self._loss_classes(cn)
        if self.depths is not None and self.classes is not None:
            has = self.class_of >= 0
            self.cell_loss = ScsCurveNumber(curve_number=cn[self.jj, self.ii][has])
        self.injections = [self._injection(cfg, tables, *h) for h in hydrographs]

    def _check_curve_numbers(self, cfg: RunConfig, cn: np.ndarray) -> None:
        """A CN raster must cover the cells it is meant for: a hole would run off without losses."""
        if cfg.terrain.cn_raster is None:
            return
        holes = int(np.count_nonzero(np.isnan(cn[self.jj, self.ii]) & self.rained))
        if holes:
            raise ValueError(
                f"terrain.cn_raster gives no CN on {holes} rained cells of {self.rained.size}, and nothing "
                "else does: extend the raster or set hydrology.curve_number"
            )

    def _read_depths(self, cfg: RunConfig, grid: TileGrid, crs: str) -> np.ndarray:
        """The depth grid per interior cell; a rained cell without a depth is refused."""
        values = raster_at_cells(cfg.storm.depth_grid, grid, crs)[self.jj, self.ii]
        holes = int(np.count_nonzero(~np.isfinite(values) & self.rained))
        if holes:
            raise ValueError(f"storm.depth_grid has no depth on {holes} rained cells of {self.rained.size}")
        return np.nan_to_num(values)

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
        offset = float(dist.min())
        if offset > cfg.hydrology.inject_max_offset:
            raise ValueError(
                f"inflow {name} at {tuple(point)} is {offset:.0f} m from the nearest domain cell; the limit is "
                f"{cfg.hydrology.inject_max_offset:.0f} m (hydrology.inject_max_offset)"
            )
        near = np.nonzero(dist <= cfg.hydrology.inject_radius)[0]
        if near.size == 0:
            near = np.array([int(np.argmin(dist))])
        lowest = int(np.argmin(tables.zmin[self.jj[near], self.ii[near]]))
        index = self.model.device_index(self.state[near])
        return Injection(
            name, near, index, lowest, np.asarray(times, np.float64), np.asarray(flows, np.float64),
            cfg.hydrology.inject_min_depth,
        )  # fmt: skip

    def _excess_mm(self, t: float) -> np.ndarray:
        """Cumulative excess at time t: per class with the plain rain last, or per cell under a depth grid."""
        depth = float(self.storm.cumulative_depth(np.array([t / SECONDS_PER_MINUTE]))[0])
        if self.depths is not None:
            rain = depth * self.depths
            if self.cell_loss is None:
                return rain
            has = self.class_of >= 0
            with np.errstate(divide="ignore", invalid="ignore"):
                rain[has] = np.nan_to_num(self.cell_loss.cumulative_excess(rain[has]))
            return rain
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
            excess = (self._excess_mm(t1) - self._excess_mm(t0)) / (MM_PER_M * step)
            out[:] = (excess if self.depths is not None else excess[self.class_of]) * self.rained
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
