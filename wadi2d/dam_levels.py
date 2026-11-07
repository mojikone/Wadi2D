"""Where a dam's pool starts: empty by default, at its spillway crest or at a level for a scenario (a breach, say).

Interface: :func:`with_dam_starts`, :func:`grid_pool_depth`.

One start per dam name, ``RunConfig.dam_levels``. A reservoir that routes in the run's lumped network takes it; any other
name is a crest line or an embankment on the grid, and the pool behind it is filled. One pool, never both, holds the
water: a reservoir that routes lumped takes the water of its grid cells through the hand-back above the dam.

The grid pool at level L is found on the cells: those whose ground is under L, joined through faces still open at L,
touching the dam's line on one side, and reaching no open boundary. The side the water lies on is never guessed: when
water on both sides stays clear of the boundaries, the run is refused, and a polygon in ``initial_levels`` does it.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from wadi2d.config.schema import DAM_EMPTY, DAM_SPILLWAY, DamLevel, RunConfig, TerrainObject
from wadi2d.hydrology.model import Basin, Reservoir
from wadi2d.hydrology.reservoir import ReservoirOutflowCurve, ReservoirOutflowStructures
from wadi2d.solver.layout import CLOSED
from wadi2d.tables.builder import GridTables, hbar_at_level
from wadi2d.terrain.crest import NORTH, staircase

DAM_KINDS = ("crest_line", "embankment")
"""Terrain objects that hold a pool on the grid."""
OPEN_BELOW = 0.5 * CLOSED
"""A face invert under this over its cell floor is a face at all; CLOSED marks a wall."""


def _spillway_level(routing) -> float:
    """Where water starts to leave: the lowest spillway crest, or the top of the outflow curve's zero rows."""
    if isinstance(routing, ReservoirOutflowStructures):
        return min(s.crest_elevation_m for s in routing.spillways)
    still = routing.elevations_m[routing.outflow_m3s <= 0.0]
    return float(still.max()) if still.size else float(routing.elevations_m[0])


def _lumped_level(name: str, routing, start: str | float) -> float:
    if start == DAM_EMPTY:
        return float(routing.elevations_m[0])
    if start == DAM_SPILLWAY:
        return _spillway_level(routing)
    level = float(start)
    if not routing.elevations_m[0] <= level <= routing.elevations_m[-1]:
        raise ValueError(
            f"dam_levels: {name} starts at {level:g} m, off its table {routing.elevations_m[0]:g} to "
            f"{routing.elevations_m[-1]:g} m"
        )
    return level


def with_dam_starts(basin: Basin, levels: list[DamLevel]) -> dict[str, float]:
    """Set the start of every reservoir the job names, in place; the levels taken, by name."""
    taken: dict[str, float] = {}
    for item in levels:
        element = basin.elements.get(item.name)
        if not isinstance(element, Reservoir):
            continue
        routing = element.routing
        if not isinstance(routing, ReservoirOutflowStructures | ReservoirOutflowCurve):
            raise ValueError(f"dam_levels: reservoir {item.name} routes by {type(routing).__name__}, which has no level")
        level = _lumped_level(item.name, routing, item.start)
        basin.elements[item.name] = replace(element, routing=replace(routing, initial_elevation_m=level))
        taken[item.name] = level
    return taken


def _dam(cfg: RunConfig, name: str) -> list[TerrainObject]:
    """Every crest line and embankment of that name: a dam drawn in pieces is one dam."""
    found = [o for o in cfg.terrain.objects if o.kind in DAM_KINDS and o.name == name]
    if not found:
        raise ValueError(
            f"dam_levels names {name}: no reservoir of that name routes in this run's lumped network, and no crest "
            "line or embankment carries the name"
        )
    return found


def _grid_level(cfg: RunConfig, name: str, pieces: list[TerrainObject], start: str | float) -> float | None:
    """The level to fill to, None for an empty pool."""
    if start == DAM_EMPTY:
        return None
    if start != DAM_SPILLWAY:
        return float(start)
    from wadi2d.basin.reservoirs import spillways_of

    ratings = [rating for piece in pieces for rating in spillways_of(piece, cfg, cfg.basin)]
    if not ratings:
        raise ValueError(
            f"dam_levels: {name} starts at its spillway, but no spillway lies within {cfg.basin.dam_join_m:g} m of its "
            "line"
        )
    return min(r["crest_elevation_m"] for r in ratings)


def _components(tables: GridTables, level: float) -> tuple[np.ndarray, np.ndarray]:
    """Every cell's component of water at ``level``, -1 where dry; and the flat indices of the wet cells."""
    grid = tables.grid
    zmin = np.asarray(tables.zmin, np.float64)
    wet = grid.mask & (zmin < level)
    flat = np.flatnonzero(wet)
    node = np.full(wet.size, -1, np.int64)
    node[flat] = np.arange(flat.size)
    pairs = []
    for fl, axis in ((grid.from_tiles(tables.flx, CLOSED), 1), (grid.from_tiles(tables.fly, CLOSED), 0)):
        invert = fl + np.roll(zmin, 1, axis=axis)
        both = wet & np.roll(wet, 1, axis=axis)
        if axis == 1:
            both[:, 0] = False
        else:
            both[0, :] = False
        crossing = both & (fl < OPEN_BELOW) & (invert < level)
        here = np.flatnonzero(crossing)
        there = here - (1 if axis == 1 else grid.shape[1])
        pairs.append((node[there], node[here]))
    a = np.concatenate([p[0] for p in pairs])
    b = np.concatenate([p[1] for p in pairs])
    graph = coo_matrix((np.ones(a.size, np.int8), (a, b)), shape=(flat.size, flat.size))
    _count, labels = connected_components(graph, directed=False)
    component = np.full(wet.size, -1, np.int64)
    component[flat] = labels
    return component.reshape(wet.shape), flat


def _side(line: shapely.LineString, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """+1 left of the line, -1 right, by the segment nearest each point."""
    coords = np.asarray(line.coords)
    seg = np.array([shapely.LineString(coords[k : k + 2]).distance(shapely.Point(px, py))
                    for px, py in zip(x, y, strict=True) for k in range(len(coords) - 1)])  # fmt: skip
    nearest = seg.reshape(len(x), len(coords) - 1).argmin(axis=1)
    p0, p1 = coords[nearest], coords[nearest + 1]
    cross = (p1[:, 0] - p0[:, 0]) * (y - p0[:, 1]) - (p1[:, 1] - p0[:, 1]) * (x - p0[:, 0])
    return np.sign(cross)


def _beside(tables: GridTables, component: np.ndarray, piece: TerrainObject) -> tuple[np.ndarray, np.ndarray]:
    """The components of the wet cells either side of one piece of a dam, and the side of the line each lies on."""
    grid = tables.grid
    st = staircase(grid, piece.coordinates)
    north = st.axis == NORTH
    jb, ib = st.j, st.i
    ja, ia = np.where(north, jb - 1, jb), np.where(north, ib, ib - 1)
    js, is_ = np.concatenate([ja, jb]), np.concatenate([ia, ib])
    inside = (js >= 0) & (is_ >= 0) & (js < grid.shape[0]) & (is_ < grid.shape[1])
    js, is_ = js[inside], is_[inside]
    labels = component[js, is_]
    keep = labels >= 0
    js, is_, labels = js[keep], is_[keep], labels[keep]
    x, y = grid.xy_of(js, is_)
    sides = _side(shapely.LineString(piece.coordinates), np.asarray(x, np.float64), np.asarray(y, np.float64))
    return labels, sides


def _pool(tables: GridTables, open_cells: np.ndarray, name: str, pieces: list[TerrainObject], level: float) -> np.ndarray:
    """The cells of the pool behind the dam ``name`` at ``level``, as a mask.

    Each piece is judged alone, as the pieces of one dam may be drawn either way: water held on both sides of one piece
    is refused. Water held below the dam that touches only another piece would be filled: the count of cells and the
    volume in the run's notes are the check.
    """
    component, _flat = _components(tables, level)
    leaking = set(np.unique(component[open_cells & (component >= 0)]).tolist())
    held: set[int] = set()
    wet_beside = False
    for piece in pieces:
        labels, sides = _beside(tables, component, piece)
        wet_beside = wet_beside or labels.size > 0
        kept = {
            (label, side)
            for label, side in zip(labels.tolist(), sides.tolist(), strict=True)
            if label not in leaking and side != 0
        }
        if len({side for _label, side in kept}) > 1:
            raise ValueError(
                f"dam_levels: water at {level:g} m beside {name} is held on both sides of one of its lines, so which "
                "side is the pool cannot be told; draw it as a polygon in initial_levels"
            )
        held |= {label for label, _side in kept}
    if not wet_beside:
        raise ValueError(f"dam_levels: {name} at {level:g} m wets no cell beside its line: check the datum")
    if not held:
        raise ValueError(
            f"dam_levels: water at {level:g} m behind {name} reaches an open boundary on both sides: the line does not "
            "close the valley at that level, or the pool runs out of the domain"
        )
    return np.isin(component, list(held))


def grid_pool_depth(
    cfg: RunConfig, tables: GridTables, open_cells: np.ndarray, taken: dict[str, float]
) -> tuple[np.ndarray, list[str]]:
    """The mean depth that fills every named dam's grid pool, and what was done, in words.

    ``open_cells`` marks the open boundary cells; ``taken`` the names a lumped reservoir already took.
    """
    grid = tables.grid
    out = np.zeros(grid.shape)
    notes = [f"dam {name}: the lumped reservoir starts at {level:g} m" for name, level in taken.items()]
    wanted = [item for item in cfg.dam_levels if item.name not in taken]
    if not wanted:
        return out, notes
    if getattr(grid, "quad", False):
        raise ValueError("dam_levels: a grid pool is filled on a uniform grid only; on the mesh, draw it in initial_levels")
    hc, dtab = grid.from_tiles(tables.hc), grid.from_tiles(tables.dtab)
    zmin = np.asarray(tables.zmin, np.float64)
    for item in wanted:
        pieces = _dam(cfg, item.name)
        level = _grid_level(cfg, item.name, pieces, item.start)
        if level is None:
            notes.append(f"dam {item.name}: the pool on the grid starts empty")
            continue
        pool = _pool(tables, open_cells, item.name, pieces, level)
        depth = np.asarray(hbar_at_level(level, zmin[pool], hc[pool], dtab[pool]))
        out[pool] = np.maximum(out[pool], depth)
        volume = float(depth.sum()) * grid.dx * grid.dx
        notes.append(f"dam {item.name}: the pool on the grid starts at {level:g} m, {int(pool.sum())} cells, {volume:,.0f} m3")
    return out, notes
