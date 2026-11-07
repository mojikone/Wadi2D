"""Where lumped water enters the grid: on the wadi, clear above every result and hand-back line (W41).

A lumped hydrograph that enters on the cells a result line crosses, or just below them, never crosses the line on the
grid. On Block 2 the HMS icons of the dam junctions lie 0.4 to 87 m below every dam line, and at 80 m four of the five
dam lines read 0.003 to 0.86 of the flow that W1's placement gives them. W1's validated mode (b) put each subbasin at
the largest drainage area inside its polygon eroded 80 m. This module does the same on the run's own grid, then walks up
the wadi until the cells the injection reaches are clear of every line.

- A subbasin with ``entry: wadi`` and a polygon starts at the cell of largest drainage area inside the polygon, eroded
  by ``hydrology.entry_erode_m`` (or inside the whole polygon when the erosion leaves no cell). It walks up only through
  cells inside the polygon.
- An inflow with ``entry: wadi`` (a generated basin's junction) starts at the cell of its point. It walks up the wadi
  through any cell.
- "Clear" means no cell within ``inject_radius`` plus one cell of the entry is a cell either side of a face under a
  line. That is the footprint of the injection, and a margin of one cell. A walk that starts on a line's own cells
  says so: that line now counts all of the entry, which is right for a dam line on a polygon's edge, and an
  over-count where a line cuts through the middle of a subbasin.
- The walk steps to the neighbour draining into the current cell with the largest drainage area. A walk that ends
  without clearing a line, or that runs out of steps, keeps its start, and the note says so.

Drainage comes from each cell's lowest ground (``tables.zmin``), breached and routed by WhiteboxTools, as the basin
generator does. Uniform grids only: on a mesh the entries stay at their points, and the note says so.

Interface: :func:`place_entries`, :func:`with_entries`, :class:`Placed`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import shapely
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage

from wadi2d.basin.delineate import flow_surface
from wadi2d.basin.kernels import NONE
from wadi2d.config.schema import ENTRY_WADI, RunConfig
from wadi2d.engine.line_checks import touched_cells

MAX_WALK_CELLS = 400
"""A walk up the wadi longer than this keeps its start: a line drawn along a wadi has no clear cell above it."""
NEIGHBOURS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


@dataclass(frozen=True)
class Placed:
    """One entry: where it was asked for, where it enters, and why."""

    name: str
    kind: str
    asked: tuple[float, float] | None
    point: tuple[float, float]
    moved_m: float
    clear: bool
    note: str

    def record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _Want:
    name: str
    kind: str
    point: tuple[float, float] | None
    polygon: shapely.Geometry | None


def _wanted(cfg: RunConfig, polygons: dict[str, shapely.Geometry]) -> list[_Want]:
    h = cfg.hydrology
    out = [
        _Want(s.name, "subbasin", s.outlet, polygons.get(s.name))
        for s in h.subbasins
        if s.mode == "lumped" and s.entry == ENTRY_WADI
    ]
    out += [_Want(i.name, "inflow", (i.x, i.y), None) for i in h.inflows if i.entry == ENTRY_WADI]
    return out


def _lines(cfg: RunConfig) -> list[list[tuple[float, float]]]:
    """Every line a lumped entry must stay clear of: the result lines and the hand-back lines."""
    return [list(line.coordinates) for line in cfg.outputs.lines] + [
        list(line.coordinates) for line in cfg.hydrology.handbacks
    ]


def _on_lines(grid, lines) -> np.ndarray:
    """The cells either side of a face under a line."""
    on = np.zeros(grid.mask.shape, dtype=bool)
    for coordinates in lines:
        for j, i in touched_cells(grid, coordinates):
            if 0 <= j < on.shape[0] and 0 <= i < on.shape[1]:
                on[j, i] = True
    return on


def _near(on: np.ndarray, dx: float, reach_m: float) -> np.ndarray:
    """Cells closer than ``reach_m`` to a cell of ``on``."""
    if not on.any():
        return on.copy()
    return ndimage.distance_transform_edt(~on) * dx <= reach_m


def _inside(grid, polygon: shapely.Geometry) -> np.ndarray:
    """Active cells whose centres lie in the polygon."""
    if polygon is None or polygon.is_empty:
        return np.zeros(grid.mask.shape, dtype=bool)
    transform = Affine(grid.dx, 0.0, grid.x0, 0.0, -grid.dx, grid.y0)
    inside = features.geometry_mask([polygon], out_shape=grid.mask.shape, transform=transform, invert=True)
    return inside & grid.mask


def _cell_of(grid, point: tuple[float, float]) -> tuple[int, int]:
    """The active cell nearest to a point."""
    jj, ii = np.nonzero(grid.mask)
    x, y = grid.xy_of(jj, ii)
    k = int(np.argmin(np.hypot(x - point[0], y - point[1])))
    return int(jj[k]), int(ii[k])


class _Drainage:
    """D8 receivers and drainage counts on the grid, from each cell's lowest ground."""

    def __init__(self, grid, zmin: np.ndarray, crs: str) -> None:
        z = np.where(grid.mask, zmin, np.nan).astype(np.float64)
        surface = flow_surface(z, grid.dx, grid.x0, grid.y0, crs)
        self.shape = z.shape
        self.down = surface.down.reshape(z.shape)
        self.acc = surface.count.reshape(z.shape)

    def donors(self, j: int, i: int) -> list[tuple[int, int]]:
        """The neighbours that drain into (j, i)."""
        ny, nx = self.shape
        flat = j * nx + i
        found = []
        for dj, di in NEIGHBOURS:
            a, b = j + dj, i + di
            if 0 <= a < ny and 0 <= b < nx and self.down[a, b] != NONE and int(self.down[a, b]) == flat:
                found.append((a, b))
        return found


def _walk(
    drainage: _Drainage, start: tuple[int, int], near: np.ndarray, on: np.ndarray, allowed: np.ndarray | None
) -> tuple[tuple[int, int], bool, bool]:
    """Up the wadi from ``start`` until clear of ``near``: the cell, whether it is clear, and whether the walk left a
    line's own cells on the way. The start again when no clear cell is reached."""
    cell, crossed = start, False
    for _ in range(MAX_WALK_CELLS):
        if not near[cell]:
            return cell, True, crossed
        crossed = crossed or bool(on[cell])
        donors = [d for d in drainage.donors(*cell) if allowed is None or allowed[d]]
        if not donors:
            break
        cell = max(donors, key=lambda d: drainage.acc[d])
    return (cell, True, crossed) if not near[cell] else (start, False, False)


def _start(grid, drainage: _Drainage, want: _Want, erode_m: float) -> tuple[tuple[int, int], np.ndarray | None, str]:
    """The cell a walk starts from, the cells it may walk through, and how the start was found."""
    if want.kind == "subbasin" and want.polygon is not None:
        whole = _inside(grid, want.polygon)
        inner = _inside(grid, want.polygon.buffer(-erode_m)) if erode_m > 0.0 else whole
        pool = inner if inner.any() else whole
        if pool.any():
            jj, ii = np.nonzero(pool)
            k = int(np.argmax(drainage.acc[jj, ii]))
            how = "the wadi outlet of its polygon" if inner.any() else "the wadi outlet of its polygon, not eroded"
            return (int(jj[k]), int(ii[k])), whole, how
    if want.point is None:
        raise ValueError(f"lumped subbasin {want.name} has neither a polygon on the grid nor an outlet")
    how = "its point" if want.kind == "inflow" else "its outlet: the polygon holds no cell of the grid"
    return _cell_of(grid, want.point), None, how


def place_entries(cfg: RunConfig, tables, polygons: dict[str, shapely.Geometry], crs: str = "") -> list[Placed]:
    """Where every ``entry: wadi`` subbasin and inflow enters; an empty list when the job asks for none."""
    wanted = _wanted(cfg, polygons)
    if not wanted:
        return []
    grid = tables.grid
    if getattr(grid, "quad", False) or np.shape(tables.zmin) != grid.mask.shape:
        return [
            Placed(w.name, w.kind, w.point, w.point, 0.0, False, "on a mesh, a lumped entry stays at its point")
            for w in wanted
            if w.point is not None
        ]
    h = cfg.hydrology
    on = _on_lines(grid, _lines(cfg))
    near = _near(on, grid.dx, h.inject_radius + grid.dx)
    drainage = _Drainage(grid, np.asarray(tables.zmin), crs)
    placed = []
    for want in wanted:
        start, allowed, how = _start(grid, drainage, want, h.entry_erode_m)
        cell, clear, crossed = _walk(drainage, start, near, on, allowed)
        x, y = (float(v) for v in grid.xy_of(np.array(cell[0]), np.array(cell[1])))
        asked = want.point
        moved = 0.0 if asked is None else float(np.hypot(x - asked[0], y - asked[1]))
        walked = cell != start
        words = f"enters at {how}" + (", moved up the wadi clear of every line" if walked else "")
        if crossed:
            words += ": it started on a line's cells, so that line now counts all of it, and a part of what feeds it may lie below the line"
        if not clear:
            words = f"enters at {how}, but no cell up the wadi is clear of the lines: a line there reads part of it"
        placed.append(Placed(want.name, want.kind, asked, (x, y), moved, clear, words))
    return placed


def with_entries(flows: list, placed: list[Placed]) -> list:
    """The hydrographs with each placed entry's point replaced."""
    where = {p.name: p.point for p in placed}
    return [(name, where.get(name, point), times, q) for name, point, times, q in flows]
