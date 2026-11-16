"""The catchments a run leaves out of its 2D mesh (W88, the owner's design of 2026-11-15).

One project-wide 2D domain stays in the job. With ``grid.exclude_lumped`` every cell whose centre lies in a *carried*
lumped subbasin leaves the active mask: a subbasin with no outlet of its own, whose water the lumped network (reaches,
reservoirs) brings to an entry elsewhere, at an inflow from an element below it or at the end of a hand-back's route.
``grid.exclude_subbasins`` names lumped subbasins outright. A lumped subbasin that enters at its own outlet is not
carried: the grid routes its water through its own polygon, so its cells stay (run 4 of W79).

- The cells are picked as the rain mask picks them (:func:`wadi2d.forcing._labels`): by the cell's centre, a polygon at
  a time. So a cell is left out, or it is in the mesh and rained on or masked as before; no rim of cells between the
  two rules. An aligned strip is built on the mask that is left, so its cells end at the same edge.
- The edge on a left-out catchment is the domain's edge there: a closed wall, to the tables, the pit check and the
  strip alike.
- An entry whose point lies in a left-out cell moves to the wadi just outside: the lowest cell of the mesh that touches
  the catchments that entry itself brings in, within ``hydrology.entry_snap_m`` of the point. The pour point of a
  catchment is the lowest point of its edge, so this is the wadi; none within reach stops the run, in words. An inflow
  with ``entry: edge`` (a last point's, W105) moves to the lowest cell on the whole edge of its catchments, wherever its
  point lies.

Interface: :class:`LeftOut`, :func:`choose`, :func:`snap_entries`, :class:`Snapped`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import shapely
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage

from wadi2d.config.constants import M2_PER_KM2
from wadi2d.config.schema import ENTRY_EDGE, RunConfig

EDGE_CELLS = (1, 2)
"""An entry lands on a cell that touches the left-out area; where none does within reach (an aligned strip's cell,
whose centre may stand a little further), on one a cell further out."""
NEIGHBOURS = np.ones((3, 3), bool)


@dataclass
class LeftOut:
    """The subbasins a run leaves out of its mesh, with their polygons."""

    owner: dict[str, str]
    """Each left-out subbasin and the entry that brings its water to the grid, by name."""
    polygons: dict[str, shapely.Geometry]
    cells_out: int = 0
    """Cells of the domain the mesh lost to them (set when the grid is made)."""
    entries: list[tuple[float, float]] = field(default_factory=list)
    """Where entries were moved onto the edge of the left-out area (set by :func:`snap_entries`): flowing water
    stands against the wall there, and the edge check after the run does not call it a pool."""

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.owner)

    @property
    def area(self) -> shapely.Geometry:
        """The left-out catchments as one shape."""
        return shapely.union_all([shapely.make_valid(self.polygons[name]) for name in self.owner])

    @property
    def area_km2(self) -> float:
        return float(self.area.area) / M2_PER_KM2

    def cells(
        self, x0: float, y0: float, dx: float, shape: tuple[int, int], names: list[str] | None = None
    ) -> np.ndarray:
        """Cells of a lattice whose centre lies in a left-out polygon (those of ``names`` alone when given);
        ``x0`` is its west edge and ``y0`` its north edge."""
        chosen = [self.polygons[name] for name in (self.owner if names is None else names)]
        if not chosen:
            return np.zeros(shape, bool)
        burned = features.rasterize(
            [(polygon, 1) for polygon in chosen], out_shape=shape, transform=Affine(dx, 0.0, x0, 0.0, -dx, y0),
            fill=0, dtype="uint8",
        )  # fmt: skip
        return burned.astype(bool)

    def on(self, grid, names: list[str] | None = None) -> np.ndarray:
        """The same on a run's grid."""
        return self.cells(grid.x0, grid.y0, grid.dx, grid.shape, names)

    def brought_by(self, entry: str) -> list[str]:
        """The left-out subbasins an entry brings in."""
        return [name for name, by in self.owner.items() if by == entry]

    def entry_cells(self, grid) -> np.ndarray:
        """The cells of the moved entries, as a mask of the grid."""
        mask = np.zeros(grid.shape, bool)
        for x, y in self.entries:
            j, i = grid.cell_of(x, y)
            if 0 <= j < mask.shape[0] and 0 <= i < mask.shape[1]:
                mask[j, i] = True
        return mask


def cells_key(cells: np.ndarray) -> str:
    """A hash of the cells taken out, for the grid cache."""
    return hashlib.sha1(np.packbits(np.ascontiguousarray(cells, bool)).tobytes()).hexdigest() + str(cells.shape)


def choose(cfg: RunConfig, carried: dict[str, str], polygons: dict[str, shapely.Geometry]) -> LeftOut | None:
    """What the job leaves out: the carried subbasins when ``grid.exclude_lumped`` is on, and those it names.

    ``carried`` is every carried lumped subbasin with the entry that brings it in. Raises ``ValueError``, in words, for
    a name that is no lumped subbasin and for a left-out subbasin with no polygon. None when the job asks for nothing.
    """
    g = cfg.grid
    if not g.exclude_lumped and not g.exclude_subbasins:
        return None
    lumped = {s.name for s in cfg.hydrology.subbasins if s.mode == "lumped"}
    owner = dict(carried) if g.exclude_lumped else {}
    for name in g.exclude_subbasins:
        if name not in lumped:
            raise ValueError(
                f"grid.exclude_subbasins names {name}, which is not a lumped subbasin of the job: only a lumped "
                "subbasin's cells can be left out of the mesh; a 2D subbasin's rain falls on its cells"
            )
        owner.setdefault(name, carried.get(name, name))
    missing = [name for name in owner if name not in polygons]
    if missing:
        raise ValueError(
            f"subbasins {', '.join(missing)} are to be left out of the mesh but have no polygon: give "
            "hydrology.hms_sqlite or hydrology.polygons"
        )
    return LeftOut(owner, {name: polygons[name] for name in owner})


@dataclass(frozen=True)
class Snapped:
    """An entry moved out of the left-out area."""

    name: str
    asked: tuple[float, float]
    point: tuple[float, float]
    moved_m: float
    note: str


def _positions(tables, near: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Centre and lowest ground of every cell of the mesh that stands in a lattice square of ``near``: the squares,
    and an aligned strip's cells by the square their centre stands in."""
    grid = tables.grid
    jj, ii = np.nonzero(near & grid.mask)
    x, y = (np.asarray(v, np.float64) for v in grid.xy_of(jj, ii))
    zmin = np.asarray(tables.zmin)
    z = zmin[jj, ii].astype(np.float64) if zmin.shape == grid.mask.shape else np.zeros(jj.size)
    strip = getattr(tables, "strip", None)
    if strip is not None:
        mesh = strip.mesh
        n = mesh.real
        cx, cy = np.asarray(mesh.cx[:n], np.float64), np.asarray(mesh.cy[:n], np.float64)
        sj = np.clip(np.floor((grid.y0 - cy) / grid.dx).astype(np.int64), 0, grid.shape[0] - 1)
        si = np.clip(np.floor((cx - grid.x0) / grid.dx).astype(np.int64), 0, grid.shape[1] - 1)
        keep = near[sj, si]
        x, y = np.concatenate((x, cx[keep])), np.concatenate((y, cy[keep]))
        z = np.concatenate((z, np.asarray(mesh.zmin[:n], np.float64)[keep]))
    return x, y, z


def snap_entries(cfg: RunConfig, tables, flows: list, left: LeftOut | None) -> list[Snapped]:
    """Every entry of ``flows`` whose point lies in a left-out cell, moved to the wadi just outside; and every inflow
    with ``entry: edge`` that brings in left-out catchments (a last point's, W105), moved to their pour point wherever
    its point lies: the lowest cell on the whole edge of the catchments it brings in, since they all drain through the
    last point. An HMS icon is schematic: on Block 2 the reach-limited search from R2A's icon found the dam's second
    chute, 740 m from its main one, where the whole edge's lowest cell lies 35 m from the dam axis.

    Raises ``ValueError`` when no cell of the mesh touches that entry's catchments within ``hydrology.entry_snap_m``
    (an ``edge`` inflow: anywhere). The moved points are kept on ``left`` for the edge check after the run.
    """
    if left is None or not left.names:
        return []
    grid = tables.grid
    out = left.on(grid)
    edge = {i.name for i in cfg.hydrology.inflows if i.entry == ENTRY_EDGE}
    moved: list[Snapped] = []
    for name, point, _times, _flows in flows:
        if point is None:
            continue
        j, i = grid.cell_of(float(point[0]), float(point[1]))
        inside = 0 <= j < out.shape[0] and 0 <= i < out.shape[1] and out[j, i]
        own = left.brought_by(name)
        pour = name in edge and bool(own)
        if not inside and not pour:
            continue
        reach = np.inf if pour else cfg.hydrology.entry_snap_m
        mine = left.on(grid, own) if own else out
        for rings in EDGE_CELLS:
            near = ndimage.binary_dilation(mine, structure=NEIGHBOURS, iterations=rings) & ~out
            x, y, z = _positions(tables, near)
            d = np.hypot(x - point[0], y - point[1])
            within = d <= reach
            if within.any():
                break
        whose = f"the {len(own)} catchments it brings in" if own else "the left-out catchments"
        if not within.any():
            nearest = f"the nearest is {d.min():.0f} m away" if d.size else "there is none"
            where = "brings in catchments left out of the mesh" if pour else "lies in the catchments left out of the mesh"
            limit = "at all" if pour else f"within {reach:g} m of it ({nearest})"
            raise ValueError(
                f"inflow {name} at ({point[0]:.0f}, {point[1]:.0f}) {where}, and no cell of the mesh on the edge of "
                f"{whose} lies {limit}: move the point to the wadi below them, or raise hydrology.entry_snap_m"
            )
        low = z[within].min()
        pick = np.nonzero(within & (z <= low + 1e-9))[0]
        k = int(pick[np.argmin(d[pick])])
        to = (float(x[k]), float(y[k]))
        if pour:
            note = (
                f"is a last point of the lumped model: it enters {d[k]:.0f} m from its point at ({to[0]:.0f}, "
                f"{to[1]:.0f}), the lowest cell on the whole edge of {whose}, their pour point"
            )
        else:
            note = (
                f"lies in the catchments left out of the mesh: it enters {d[k]:.0f} m away at ({to[0]:.0f}, "
                f"{to[1]:.0f}), the lowest cell on the edge of {whose}"
            )
        moved.append(Snapped(name, (float(point[0]), float(point[1])), to, float(d[k]), note))
    left.entries = [m.point for m in moved]
    return moved
