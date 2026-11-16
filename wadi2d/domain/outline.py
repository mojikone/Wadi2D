"""A 2D domain completed from a drawn outline (W97): every catchment draining into the outline is added, and where the
outline was drawn over a divide into ground draining elsewhere it is cut back, so the mountain edge is a divide of the
D8 lines and a hybrid model has no rain-on-grid rim there.

The user draws the downstream part exactly (to the sea, say) and the rest roughly. The exact part is told by **kept
lines**: the job's boundary lines and any lines given. Water crosses a kept edge where its D8 step over the outline
lies within ``keep_m`` of a kept line and makes 30 degrees or more with it (a step along it, at the corner where a rough
edge meets a kept one, does not). The rule, pixel by pixel on the basin generator's D8 lines (the same reading, breach,
walls and burns):

- a pixel whose way down passes through the outline belongs to the domain when its water last leaves the outline
  across a kept edge; with no kept line, wherever it leaves (then nothing is cut back);
- a pixel outside the outline whose water enters it across a kept edge is not added: the drawn edge stays, and the
  report names the inflow it then needs.

So a pixel inside the outline whose water leaves across a rough edge and never comes back is removed, and a pixel
outside whose water comes in across a rough edge is added. The domain's edge follows the analysis pixels where it moved
and the drawn outline where it did not. The stream threshold of the job's basin settings names the changes: an entry or
an exit draining at least that much is a catchment, the rest are hillslope slivers.

Interface: :class:`Change`, :class:`Completed`, :func:`complete_outline`, :func:`kept_lines`, :func:`read_outline`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio import features
from rasterio.windows import from_bounds

from wadi2d.basin.barriers import ground_edits
from wadi2d.basin.delineate import Surface, analysis_pixel, flow_surface
from wadi2d.basin.kernels import NONE
from wadi2d.config.schema import BasinSettings, DomainSettings, RunConfig
from wadi2d.domain.walks import gate_in, last_inside
from wadi2d.mesh.streams import read_coarse
from wadi2d.terrain.vector import read_features

ADDED, REMOVED, NOT_ADDED = "added", "removed", "not added"
"""Kinds of a change: ground joined to the outline, ground taken out of it, and ground draining in across a kept edge
that stays outside."""
NO_THRESHOLD_KM2 = 1.0
"""What names a catchment among the changes when the basin settings break at the pour points only."""
EDGE_BAND_PIXELS = 1.5
"""Half-width of the band round the drawn outline where it replaces the pixel staircase, where nothing moved."""
MAX_GROWS = 8
CROSSING_SINE = 0.5
"""A D8 step crosses a kept line when it makes 30 degrees or more with it: a step along it, where a rough edge meets a
kept one at a corner, does not."""


@dataclass
class Change:
    """One piece of ground the completion moved, or would have."""

    kind: str
    geometry: shapely.Geometry
    km2: float
    x: float
    """Where its water crosses the outline: the pixel inside on the edge, m."""
    y: float
    catchment: bool
    """It drains at least the stream threshold through one crossing; else the hillslope slivers of that kind."""


@dataclass
class Completed:
    polygon: shapely.Polygon
    changes: list[Change]
    report: dict = field(default_factory=dict)


def read_outline(path: str | Path, crs: str = "") -> shapely.Geometry:
    """The polygons of a layer joined."""
    shapes = [shapely.make_valid(s) for _p, s in read_features(path, crs) if s.geom_type.endswith("Polygon")]
    if not shapes:
        raise ValueError(f"{path}: no polygon")
    return shapely.union_all(shapes)


def kept_lines(cfg: RunConfig, path: str | Path | None, crs: str = "") -> list[shapely.Geometry]:
    """The job's boundary lines and the lines of a layer (a polygon gives its outline)."""
    lines: list[shapely.Geometry] = [
        shapely.LineString(b.coordinates) for b in cfg.boundaries if len(b.coordinates) > 1
    ]
    if path is not None:
        for _p, shape in read_features(path, crs):
            lines.append(shape.boundary if shape.geom_type.endswith("Polygon") else shape)
    return lines


def _window(dem: str, wanted: tuple[float, float, float, float], pixel: float):
    """West and north edge, rows, columns of the analysis raster on DEM pixel corners, and which sides reach the DEM's
    edge (west, south, east, north)."""
    with rasterio.open(dem) as src:
        t, b = src.transform, src.bounds
    xmin, ymin = max(wanted[0], b.left), max(wanted[1], b.bottom)
    xmax, ymax = min(wanted[2], b.right), min(wanted[3], b.top)
    if xmin >= xmax or ymin >= ymax:
        raise ValueError(f"the outline {wanted} does not meet the DEM {tuple(b)}")
    window = from_bounds(xmin, ymin, xmax, ymax, t).round_offsets(op="floor")
    x0, y0 = t * (window.col_off, window.row_off)
    ny, nx = int(np.ceil((y0 - ymin) / pixel)), int(np.ceil((xmax - x0) / pixel))
    at_dem = (x0 <= b.left + pixel, y0 - ny * pixel <= b.bottom + pixel, x0 + nx * pixel >= b.right - pixel,
              y0 >= b.top - pixel)  # fmt: skip
    return x0, y0, ny, nx, at_dem


def _border(mask: np.ndarray) -> tuple[bool, bool, bool, bool]:
    """Does the mask touch the west, south, east, north edge of its raster."""
    return bool(mask[:, 0].any()), bool(mask[-1, :].any()), bool(mask[:, -1].any()), bool(mask[0, :].any())


@dataclass
class _Pixels:
    surface: Surface
    inside: np.ndarray
    domain: np.ndarray
    first: np.ndarray
    last: np.ndarray
    not_added: np.ndarray
    notes: list[str]


def _across_kept(
    surface: Surface, frm: np.ndarray, to: np.ndarray, kept: list[shapely.Geometry], keep_m: float
) -> np.ndarray:
    """Do the D8 steps ``frm`` to ``to`` cross a kept edge: the step's middle within ``keep_m`` of a kept line, and the
    step at 30 degrees or more to it. A step off the ground (``to`` NONE) needs only its pixel within ``keep_m``."""
    fx, fy = surface.xy(frm)
    off = to == NONE
    tx, ty = surface.xy(np.where(off, frm, to))
    points = shapely.points(0.5 * (fx + tx), 0.5 * (fy + ty))
    dx, dy = tx - fx, ty - fy
    step = np.where(off, 1.0, np.hypot(dx, dy))
    best, sine = np.full(frm.size, np.inf), np.zeros(frm.size)
    for line in (part for geom in kept for part in shapely.get_parts(geom) if part.length > 0.0):
        distance = shapely.distance(line, points)
        along = shapely.line_locate_point(line, points)
        a = shapely.line_interpolate_point(line, np.maximum(along - 1.0, 0.0))
        b = shapely.line_interpolate_point(line, np.minimum(along + 1.0, line.length))
        lx, ly = shapely.get_x(b) - shapely.get_x(a), shapely.get_y(b) - shapely.get_y(a)
        across = np.abs(dx * ly - dy * lx) / (step * np.maximum(np.hypot(lx, ly), 1e-9))
        closer = distance < best
        best[closer], sine[closer] = distance[closer], across[closer]
    return (best <= keep_m) & (off | (sine >= CROSSING_SINE))


def _classify(
    cfg: RunConfig, outline: shapely.Geometry, kept: list[shapely.Geometry], keep_m: float, basin: BasinSettings,
    window: tuple[float, float, int, int], pixel: float, crs: str,
) -> _Pixels:  # fmt: skip
    x0, y0, ny, nx = window
    z = read_coarse(cfg.terrain.dem, x0, y0, ny, nx, pixel, 1)
    notes: list[str] = []
    surface = flow_surface(z, pixel, x0, y0, crs, ground_edits(cfg, z, pixel, x0, y0, basin, notes))
    inside = features.geometry_mask(
        [outline], out_shape=z.shape, transform=surface.transform, invert=True
    ).ravel()
    inside &= surface.valid
    if not inside.any():
        raise ValueError("no ground of the DEM under the outline")
    down = surface.down
    gate = gate_in(down, surface.order, inside)
    last = last_inside(down, surface.order, inside)
    entered = gate != NONE
    first = np.where(entered, down[np.where(entered, gate, 0)], NONE)
    reached = last != NONE
    not_added = np.zeros(inside.size, dtype=bool)
    if not kept:
        domain = reached
    else:
        exits = np.unique(last[reached])
        leaves = np.zeros(inside.size, dtype=bool)
        leaves[exits] = _across_kept(surface, exits, down[exits], kept, keep_m)
        domain = reached & leaves[np.where(reached, last, 0)]
        gates = np.unique(gate[entered])
        arrives = np.zeros(inside.size, dtype=bool)
        arrives[gates] = _across_kept(surface, gates, down[gates], kept, keep_m)
        not_added = ~inside & domain & arrives[np.where(entered, gate, 0)]
        domain &= ~not_added
    return _Pixels(surface, inside, domain, first, last, not_added, notes)


def _polygons(mask: np.ndarray, surface: Surface) -> list[shapely.Polygon]:
    """The pieces of a mask, largest first."""
    if not mask.any():
        return []
    found = features.shapes(
        mask.reshape(surface.shape).astype(np.uint8),
        mask=mask.reshape(surface.shape),
        transform=surface.transform,
    )
    return sorted((shapely.geometry.shape(g) for g, _v in found), key=lambda p: p.area, reverse=True)


def _changes(
    kind: str, mask: np.ndarray, crossing: np.ndarray, px: _Pixels, threshold_km2: float
) -> list[Change]:
    """The pixels of one kind, grouped by where their water crosses the outline: one change per crossing that drains
    at least the threshold, the rest as one change of slivers."""
    surface = px.surface
    if not mask.any():
        return []
    where = crossing[mask]
    crossings, counts = np.unique(where, return_counts=True)
    big = counts * surface.km2_per_pixel >= threshold_km2
    label = np.zeros(mask.size, dtype=np.int32)
    rank = np.zeros(crossings.size, dtype=np.int32)
    rank[big] = np.arange(1, int(big.sum()) + 1)
    slivers = int(big.sum()) + 1
    rank[~big] = slivers
    label[mask] = rank[np.searchsorted(crossings, where)]
    grid = label.reshape(surface.shape)
    pieces: dict[int, list[shapely.Geometry]] = {}
    for geom, value in features.shapes(grid, mask=grid > 0, transform=surface.transform):
        pieces.setdefault(int(value), []).append(shapely.geometry.shape(geom))
    out: list[Change] = []
    for n, flat in enumerate(crossings[big]):
        x, y = surface.xy(flat)
        out.append(Change(kind, shapely.union_all(pieces[n + 1]), float(counts[big][n] * surface.km2_per_pixel),
                          float(x), float(y), True))  # fmt: skip
    if (~big).any():
        x, y = surface.xy(crossings[~big][np.argmax(counts[~big])])
        out.append(Change(kind, shapely.union_all(pieces[slivers]), float(counts[~big].sum() * surface.km2_per_pixel),
                          float(x), float(y), False))  # fmt: skip
    return sorted(out, key=lambda c: (not c.catchment, -c.km2))


def _assemble(
    outline: shapely.Geometry, px: _Pixels, moved: list[Change], notes: list[str]
) -> tuple[shapely.Polygon, float, float]:
    """The domain polygon: the pixels' outline where the edge moved, the drawn outline where it did not. Returns it, the
    area of the pieces left apart and the area of the holes filled, km2."""
    pieces = _polygons(px.domain, px.surface)
    if not pieces:
        raise ValueError("no ground drains to the kept edges through the outline: check the kept lines")
    pixel = px.surface.pixel
    band = outline.boundary.buffer(EDGE_BAND_PIXELS * pixel)
    if moved:
        band = band.difference(
            shapely.union_all([c.geometry for c in moved]).buffer(EDGE_BAND_PIXELS * pixel)
        )
    whole = shapely.union_all(pieces)
    shaped = shapely.make_valid(shapely.union(whole.difference(band), outline.intersection(band)))
    parts = sorted(getattr(shaped, "geoms", [shaped]), key=lambda g: g.area, reverse=True)
    parts = [p for p in parts if p.geom_type == "Polygon"]
    domain = parts[0]
    apart = sum(p.area for p in parts[1:]) / 1e6
    if apart > 0.0:
        notes.append(f"{len(parts) - 1} pieces apart from the domain left out, {apart:.3f} km2")
    filled = shapely.Polygon(domain.exterior)
    holes = (filled.area - domain.area) / 1e6
    if holes > 0.0:
        notes.append(f"{len(domain.interiors)} holes inside the domain filled, {holes:.3f} km2")
    return shapely.set_precision(filled, 0.01), apart, holes


def complete_outline(
    cfg: RunConfig,
    outline: shapely.Geometry,
    kept: list[shapely.Geometry],
    basin: BasinSettings,
    settings: DomainSettings,
) -> Completed:
    """The outline completed with every catchment draining into it, cut back where its rough edges reach ground draining
    elsewhere; ``kept`` are the lines the exact edges lie on (none: nothing is cut back)."""
    if cfg.terrain.dem is None:
        raise ValueError("the domain needs terrain.dem")
    started = time.perf_counter()
    pixel = analysis_pixel(cfg, basin)
    threshold = basin.stream_threshold_km2 or NO_THRESHOLD_KM2
    with rasterio.open(cfg.terrain.dem) as src:
        crs = src.crs.to_wkt() if src.crs is not None else ""
    margin, grows, xmin, ymin, xmax, ymax = settings.margin_m, 0, *outline.bounds
    while True:
        x0, y0, ny, nx, at_dem = _window(
            cfg.terrain.dem, (xmin - margin, ymin - margin, xmax + margin, ymax + margin), pixel
        )
        if ny * nx > basin.max_pixels:
            raise ValueError(f"the domain's delineation would take {ny * nx:,} pixels of {pixel} m, above max_pixels "
                             f"{basin.max_pixels:,}: use a coarser analysis pixel")  # fmt: skip
        px = _classify(cfg, outline, kept, settings.keep_m, basin, (x0, y0, ny, nx), pixel, crs)
        ground = px.domain.reshape(px.surface.shape) & np.isfinite(px.surface.z)
        touching = _border(ground)
        short = [t and not d for t, d in zip(touching, at_dem, strict=True)]
        if not any(short) or grows == MAX_GROWS:
            break
        margin *= 2.0
        grows += 1
    notes = px.notes
    if any(short):
        notes.append(
            "a catchment still runs to the edge of the analysis window after the last widening: it is cut there"
        )
    if any(t and d for t, d in zip(touching, at_dem, strict=True)):
        notes.append(
            "a catchment runs to the edge of the DEM: the ground beyond it is not known and is not in the domain"
        )
    added = ~px.inside & px.domain
    removed = px.inside & ~px.domain
    changes = (
        _changes(ADDED, added, px.first, px, threshold)
        + _changes(REMOVED, removed, px.last, px, threshold)
        + _changes(NOT_ADDED, px.not_added, px.first, px, threshold)
    )
    moved = [c for c in changes if c.kind != NOT_ADDED]
    polygon, apart, holes = _assemble(outline, px, moved, notes)
    km2 = px.surface.km2_per_pixel

    def listed(kind: str) -> list[dict]:
        return [{"km2": round(c.km2, 4), "x": round(c.x, 1), "y": round(c.y, 1)}
                for c in changes if c.kind == kind and c.catchment]  # fmt: skip

    def slivers(kind: str) -> float:
        return round(sum(c.km2 for c in changes if c.kind == kind and not c.catchment), 4)

    for c in changes:
        if c.kind == NOT_ADDED and c.catchment:
            notes.append(f"{c.km2:.2f} km2 drains in across a kept edge at ({c.x:.0f}, {c.y:.0f}) and stays outside: "
                         "it needs an inflow there")  # fmt: skip
    report = {
        "pixel_m": pixel,
        "stream_threshold_km2": threshold,
        "window": {"x0": x0, "y0": y0, "rows": ny, "columns": nx, "margin_m": margin, "widened": grows},
        "kept_lines": len(kept),
        "outline_km2": round(outline.area / 1e6, 4),
        "domain_km2": round(polygon.area / 1e6, 4),
        "added_km2": round(float(added.sum()) * km2, 4),
        "removed_km2": round(float(removed.sum()) * km2, 4),
        "not_added_km2": round(float(px.not_added.sum()) * km2, 4),
        "catchments_added": listed(ADDED),
        "slivers_added_km2": slivers(ADDED),
        "catchments_removed": listed(REMOVED),
        "slivers_removed_km2": slivers(REMOVED),
        "catchments_not_added": listed(NOT_ADDED),
        "pieces_apart_km2": round(apart, 4),
        "holes_filled_km2": round(holes, 4),
        "seconds": round(time.perf_counter() - started, 1),
        "notes": notes,
    }
    return Completed(polygon, changes, report)
