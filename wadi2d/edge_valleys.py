"""Domain outlines that cut valleys (W78): streams crossing a closed edge before a run, pools held by one after it.

Every edge of the domain is a wall unless a boundary line opens it. An outline drawn across a valley dams it, and the
balance closes all the same, so nothing else would tell: Faydh 01 ponds 8.5 to 12.3 m against its south edge in every
run (W56), Bidah 4.3 m on a level flat to the centimetre where its north outlet was made an inflow line (W75).

Before a run, :func:`stream_crossings` reads the ground over the domain and a margin past it, runs D8 through breached
depressions (the delineation's own calls, :mod:`wadi2d.basin.delineate`), and names every place where a stream above
``outputs.edge_check.stream_km2`` leaves the domain with no outflow line there, or enters it with no inflow line or
point there. After a run, :func:`edge_pools` groups the cells on a closed edge deeper than ``outputs.edge_depth`` and
says whether their level stands flat along the edge: a pool the edge holds, not water running along it.

Both write their points into ``edge_checks.gpkg`` in the run folder, layers ``edge_streams`` and ``edge_pools``, which the
dock puts in Inputs > Boundaries. Nothing here changes the model.

Interface: :class:`Crossing`, :class:`Pool`, :func:`stream_crossings`, :func:`edge_pools`, :func:`crossing_notes`,
:func:`pool_notes`, :func:`write_crossings`, :func:`write_pools`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage

from wadi2d.config.schema import EdgeCheck, RunConfig

FILE = "edge_checks.gpkg"
STREAMS_LAYER = "edge_streams"
POOLS_LAYER = "edge_pools"
LEAVES, ENTERS = "stream leaves", "stream enters"
POOL, BOWL, DEEP = "pool", "bowl", "deep water"
OUT_KINDS = ("stage", "normal", "free")
"""Lines that let water out of the domain."""
IN_KINDS = ("stage", "flow")
"""Lines that let water in."""
M2_PER_KM2 = 1.0e6
WET_M = 0.1
"""Depth that counts a cell as part of a pool's water, m."""


@dataclass(frozen=True)
class Crossing:
    """A stream across a closed edge: where it meets the outline, which way it runs and the area it drains there."""

    x: float
    y: float
    kind: str
    area_km2: float
    no_ground: bool = False
    """The DEM ends at the edge: where the stream goes, or comes from, is not on it."""


@dataclass(frozen=True)
class Pool:
    """Deep water against a closed edge: the deepest cell, its level, how flat the level is along the edge."""

    x: float
    y: float
    kind: str
    depth_m: float
    level_m: float
    spread_m: float
    edge_m: float
    """Length of edge the deep cells cover, m."""
    area_km2: float
    """Water within ``flat_m`` of the deepest cell's level, connected to it, km2."""


def _outline(cfg: RunConfig, crs: str) -> shapely.Geometry | None:
    from wadi2d.terrain.vector import read_features

    if cfg.grid.domain is not None:
        return shapely.union_all([shape for _props, shape in read_features(cfg.grid.domain, crs)])
    if cfg.grid.extent is not None:
        return shapely.box(*cfg.grid.extent)
    return None


def _window(dem: str, polygon: shapely.Geometry, beyond: float, pixel: float, max_pixels: int):
    """West edge, north edge, rows, columns and pixel of the analysis raster: the domain and ``beyond`` past it, on the
    DEM, the pixel coarsened by whole DEM pixels until it fits ``max_pixels``."""
    with rasterio.open(dem) as src:
        t, b = src.transform, src.bounds
    xmin, ymin, xmax, ymax = polygon.buffer(beyond).bounds
    xmin, ymin, xmax, ymax = max(xmin, b.left), max(ymin, b.bottom), min(xmax, b.right), min(ymax, b.top)
    step = max(round(pixel / t.a), 1) * t.a
    while (ymax - ymin) * (xmax - xmin) / step**2 > max_pixels:
        step *= 2.0
    col = np.floor((xmin - t.c) / t.a)
    row = np.floor((t.f - ymax) / -t.e)
    x0, y0 = t.c + col * t.a, t.f + row * t.e
    return x0, y0, int(np.ceil((y0 - ymin) / step)), int(np.ceil((xmax - x0) / step)), step


def _handled(point: shapely.Point, lines: list[shapely.Geometry], reach: float) -> bool:
    return any(line.distance(point) <= reach for line in lines)


def _key(cfg: RunConfig, polygon: shapely.Geometry) -> str:
    """What the D8 candidates depend on: the DEM file as it stands, the outline, the analysis settings."""
    check = cfg.outputs.edge_check
    dem = Path(cfg.terrain.dem)
    stat = dem.stat()
    blob = json.dumps(
        [str(dem.resolve()), stat.st_size, stat.st_mtime_ns, shapely.to_wkb(polygon, hex=True),
         check.stream_km2, check.pixel_m, check.beyond_m, check.max_pixels]
    )  # fmt: skip
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _candidates(cfg: RunConfig, polygon: shapely.Geometry, crs: str) -> dict[str, np.ndarray]:
    """Every D8 link across the outline from a pixel draining ``stream_km2`` or more, largest first: its pixel's
    centre, 1 where the stream leaves, its area, 1 where the DEM ends under it."""
    from wadi2d.basin.delineate import flow_surface
    from wadi2d.basin.kernels import NONE
    from wadi2d.mesh.streams import read_coarse

    check = cfg.outputs.edge_check
    x0, y0, ny, nx, pixel = _window(cfg.terrain.dem, polygon, check.beyond_m, check.pixel_m, check.max_pixels)
    z = read_coarse(cfg.terrain.dem, x0, y0, ny, nx, pixel, 1)
    if not np.isfinite(z).any():
        return {k: np.empty(0) for k in ("x", "y", "leaves", "area", "no_ground")}
    surface = flow_surface(z, pixel, x0, y0, crs)
    transform = Affine(pixel, 0.0, x0, 0.0, -pixel, y0)
    inside = features.geometry_mask([polygon], out_shape=z.shape, transform=transform, invert=True).ravel()
    area = surface.count * surface.km2_per_pixel
    down = surface.down
    big = surface.valid & (area >= check.stream_km2)
    has_down = down != NONE
    target = np.where(has_down, down, 0)
    leaves = big & inside & (~has_down | ~inside[target])
    enters = big & ~inside & has_down & inside[target]
    flats = np.flatnonzero(leaves | enters)
    flats = flats[np.argsort(-area[flats], kind="stable")]
    x, y = surface.xy(flats)
    return {
        "x": x,
        "y": y,
        "leaves": leaves[flats],
        "area": area[flats],
        "no_ground": leaves[flats] & ~has_down[flats],
    }


def stream_crossings(
    cfg: RunConfig, crs: str, cache_dir: Path | None = None, left_out: shapely.Geometry | None = None
) -> list[Crossing]:
    """Streams above the threshold crossing the domain outline where no boundary line or inflow point is.

    The D8 part waits in ``cache_dir`` for the next run on the same ground and outline (an ARF study runs many).
    ``left_out`` is the area of the catchments the run leaves out of its mesh (W88): the outline along them is no
    edge of the model, the lumped network carries their water, and a stream across it there is not named.
    """
    check: EdgeCheck = cfg.outputs.edge_check
    polygon = _outline(cfg, crs)
    if not check.enabled or polygon is None or cfg.terrain.dem is None:
        return []
    cached = None if cache_dir is None else Path(cache_dir) / f"edge_streams_{_key(cfg, polygon)}.npz"
    if cached is not None and cached.is_file():
        with np.load(cached) as held:
            got = {k: held[k] for k in held.files}
    else:
        got = _candidates(cfg, polygon, crs)
        if cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            np.savez(cached, **got)
    outs = [shapely.LineString(b.coordinates) for b in cfg.boundaries if b.kind in OUT_KINDS]
    outs += [shapely.LineString(h.coordinates) for h in cfg.hydrology.handbacks]
    ins = [shapely.LineString(b.coordinates) for b in cfg.boundaries if b.kind in IN_KINDS]
    ins += [shapely.Point(p.x, p.y) for p in cfg.hydrology.inflows]
    edge = polygon.boundary
    found: list[Crossing] = []
    for px, py, out_, area, bare in zip(
        got["x"], got["y"], got["leaves"], got["area"], got["no_ground"], strict=True
    ):
        kind, lines = (LEAVES, outs) if out_ else (ENTERS, ins)
        on = edge.interpolate(edge.project(shapely.Point(float(px), float(py))))
        if _handled(on, lines, check.line_reach_m):
            continue
        if left_out is not None and left_out.distance(on) <= cfg.grid.dx:
            continue
        if any(c.kind == kind and np.hypot(c.x - on.x, c.y - on.y) < check.cluster_m for c in found):
            continue
        found.append(Crossing(float(on.x), float(on.y), kind, float(area), bool(bare)))
    return found


def crossing_notes(found: list[Crossing], check: EdgeCheck) -> list[str]:
    """The run's warnings, the largest first, at most ``max_listed`` of each kind."""
    notes = []
    for kind in (LEAVES, ENTERS):
        mine = [c for c in found if c.kind == kind]
        for c in mine[: check.max_listed]:
            if kind == LEAVES:
                beyond = " where the DEM ends" if c.no_ground else ""
                notes.append(
                    f"a stream draining {c.area_km2:.2f} km2 leaves the domain at ({c.x:.0f}, {c.y:.0f}){beyond} with no "
                    "outflow line there: the edge is a wall and will dam it; open it with a boundary line or draw the "
                    "domain past the valley"
                )
            else:
                notes.append(
                    f"a stream draining {c.area_km2:.2f} km2 beyond the edge enters the domain at ({c.x:.0f}, {c.y:.0f}) "
                    "with no inflow line or point there: its water never reaches the model; draw the domain over its "
                    "catchment or give it a flow line"
                )
        if len(mine) > check.max_listed:
            notes.append(
                f"{len(mine) - check.max_listed} more streams {kind.split()[1]} through closed edges: see {FILE}"
            )
    return notes


def edge_pools(
    grid,
    depth: np.ndarray,
    zmin: np.ndarray,
    open_cells: np.ndarray,
    reach: int,
    depth_limit: float,
    check: EdgeCheck,
    domain: np.ndarray | None = None,
) -> list[Pool]:
    """Groups of closed-edge cells deeper than ``depth_limit``, the deepest first: a pool where the level is flat.

    ``domain`` is the domain's own cells when they differ from the active mask: on a strip run the squares an aligned
    corridor replaced are inactive, and a square beside them is a join to the strip, not an edge (W80)."""
    edge = grid.mask & ~ndimage.binary_erosion(grid.mask if domain is None else domain, border_value=0)
    closed = edge & ~ndimage.binary_dilation(open_cells, iterations=reach)
    deep = closed & (depth > depth_limit)
    if not deep.any():
        return []
    level = np.where(grid.mask, zmin + depth, np.nan)
    labels, _count = ndimage.label(deep, structure=np.ones((3, 3), bool))
    groups = []
    for k, found in enumerate(ndimage.find_objects(labels), start=1):
        cells = np.zeros(depth.shape, bool)
        cells[found] = labels[found] == k
        j, i = np.unravel_index(int(np.argmax(np.where(cells, depth, -1.0))), depth.shape)
        groups.append((float(depth[j, i]), int(j), int(i), cells))
    owner = np.full(
        depth.shape, -1, dtype=np.int64
    )  # which pool's water a cell is, so one pool is named once
    pools: list[Pool] = []
    for d, j, i, cells in sorted(groups, key=lambda g: -g[0]):
        top = float(level[j, i])
        spread = float(np.nanmax(level[cells]) - np.nanmin(level[cells]))
        edge_m = float(cells.sum()) * grid.dx
        k = owner[j, i]
        if (
            k >= 0 and abs(pools[k].level_m - top) <= check.flat_m
        ):  # another stretch of edge holding the same water
            p = pools[k]
            pools[k] = Pool(
                p.x, p.y, p.kind, p.depth_m, p.level_m, max(p.spread_m, spread), p.edge_m + edge_m, p.area_km2
            )
            continue
        held = grid.mask & (depth > WET_M) & (np.abs(level - top) <= check.flat_m)
        region, _ = ndimage.label(held)
        water = (region == region[j, i]) if region[j, i] else cells
        count = int(water.sum())
        owner[water & (owner < 0)] = len(pools)
        x, y = grid.xy_of(j, i)
        kind = DEEP if spread > check.flat_m else (POOL if count >= check.pool_cells else BOWL)
        pools.append(Pool(float(x), float(y), kind, d, top, spread, edge_m, count * grid.dx**2 / M2_PER_KM2))
    return pools


def pool_notes(pools: list[Pool], check: EdgeCheck) -> list[str]:
    """The run's warnings: pools, then deep water running along the edge, then bowls, each deepest first; each opens as
    the edge warning always has."""
    notes = []
    rank = {POOL: 0, DEEP: 1, BOWL: 2}
    pools = sorted(pools, key=lambda p: (rank[p.kind], -p.depth_m))
    for p in pools[: check.max_listed]:
        said = f"water stood {p.depth_m:.1f} m deep against the domain edge at ({p.x:.0f}, {p.y:.0f})"
        if p.kind == POOL:
            notes.append(
                f"{said}, its level {p.level_m:.2f} m flat within {p.spread_m:.2f} m over {p.edge_m:.0f} m of edge and "
                f"{p.area_km2:.3f} km2 of water behind it: a pool the edge holds, so the domain polygon likely cuts a "
                "valley there; draw it past the valley or open the edge with a boundary line"
            )
        elif p.kind == BOWL:
            notes.append(
                f"{said}, in {p.area_km2 * M2_PER_KM2:.0f} m2 of edge cells and no more: cells on the outline whose "
                "ground falls outward, past a divide, hold their own rain against the wall; little water, but the "
                "outline there runs beyond the catchment"
            )
        else:
            notes.append(f"{said}: an edge is a wall, so check the domain polygon there")
    if len(pools) > check.max_listed:
        notes.append(
            f"{len(pools) - check.max_listed} more places with deep water against the domain edge: see {FILE}"
        )
    return notes


def _layer(name: str, columns: dict, rows: list[tuple], points: list[tuple[float, float]]):
    from wadi2d.io.geopackage import POINTS, VectorLayer

    return VectorLayer(name, columns, rows, [shapely.Point(x, y) for x, y in points], POINTS)


STREAM_COLUMNS = {"kind": str, "area_km2": float, "no_ground": int}
POOL_COLUMNS = {
    "kind": str,
    "depth_m": float,
    "level_m": float,
    "spread_m": float,
    "edge_m": float,
    "area_km2": float,
}


def _put(path: Path, layers: list, crs: str) -> Path:
    """Layers into the file: in place when it exists (QGIS may hold it open from the last run), else a new file."""
    from wadi2d.io.geopackage import add_layer, write_geopackage

    if not path.is_file():
        return write_geopackage(path, layers, crs)
    for layer in layers:
        add_layer(path, layer, crs)
    return path


def write_crossings(out: Path, found: list[Crossing], crs: str) -> Path | None:
    """The crossings into ``edge_checks.gpkg``, the last run's pools emptied; nothing written for a clean job with no
    file from before."""
    path = out / FILE
    if not found and not path.is_file():
        return None
    rows = [(c.kind, round(c.area_km2, 3), int(c.no_ground)) for c in found]
    streams = _layer(STREAMS_LAYER, STREAM_COLUMNS, rows, [(c.x, c.y) for c in found])
    _put(path, [streams, _layer(POOLS_LAYER, POOL_COLUMNS, [], [])], crs)
    return path if found else None


def write_pools(out: Path, pools: list[Pool], crs: str) -> Path | None:
    """The pools into ``edge_checks.gpkg``, beside the crossings when the run wrote them."""
    path = out / FILE
    if not pools and not path.is_file():
        return None
    rows = [
        (
            p.kind,
            round(p.depth_m, 3),
            round(p.level_m, 3),
            round(p.spread_m, 3),
            round(p.edge_m, 1),
            round(p.area_km2, 4),
        )
        for p in pools
    ]
    _put(path, [_layer(POOLS_LAYER, POOL_COLUMNS, rows, [(p.x, p.y) for p in pools])], crs)
    return path if pools else None
