"""How the pixel maps are drawn: smooth class polygons, a depth drawing with a soft wet edge, a smooth domain outline.

The rasters stay the numbers of record; these only show them. Classes are drawn from cumulative masks (H3 and above,
H4 and above, ...), each softened by the same Gaussian and contoured at one half, so an edge moves by less than the
width of the blur, and because a softened mask of a smaller set is everywhere lower, the contours of neighbouring
classes nest and never cross. Each contour is read at the value that holds the raw area of its cumulative class,
which is what keeps a class's area through the blur. The polygon of a class is the difference of two contours, so
classes share their edges exactly, with no gaps and no overlaps. Work goes block by block, so memory stays the same on
any domain.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import pairwise
from pathlib import Path

import contourpy
import numpy as np
import rasterio
import shapely
from rasterio.enums import Resampling
from rasterio.windows import Window
from scipy import ndimage

from wadi2d.config.constants import M2_PER_KM2
from wadi2d.config.schema import RunConfig
from wadi2d.io.geopackage import VectorLayer, add_layer, write_geopackage
from wadi2d.io.geotiff import THREADS, raster_profile
from wadi2d.products.hazard import DRY, class_names
from wadi2d.products.setup_layers import setup_layers
from wadi2d.products.smooth_geometry import chaikin_rings
from wadi2d.tables import GridTables

LAYERS_FILE = "map_layers.gpkg"
CLASS_LAYER = "hazard_classes"
DOMAIN_LAYER = "domain"
DRAWING_FILE = "depth_drawing.tif"
DRAWING_NODATA = -9999.0
ISO = 0.5
"""The contour of a soft mask: half way between out and in."""
ISO_LOW, ISO_HIGH = 0.2, 0.8
"""How far the contour may move from one half to hold a class's area, so an edge stays within the blur."""
ISO_STEPS = 10
"""Halvings of that range: the contour is found to a thousandth."""
GAUSS_REACH = 4.0
"""Gaussian kernel reach, in sigmas."""
EDGE_LOW, EDGE_HIGH = 0.25, 0.75
"""A soft mask below the low value draws nothing, above the high one draws all of the depth."""
OVERVIEWS = (2, 4, 8, 16)
"""Of the depth drawing, so a whole sheet does not read every drawing pixel."""
DOMAIN_CHAIKIN = 2
"""Corner-cutting passes on the domain outline."""


def block_ranges(size: int, block: int) -> Iterator[tuple[int, int]]:
    """Overlapping (first, last) index ranges over -1 .. size: a block's last line is the next one's first."""
    first = -1
    while first < size:
        last = min(first + block, size)
        yield first, last
        first = last


def window(a: np.ndarray, r0: int, r1: int, c0: int, c1: int, fill) -> np.ndarray:
    """``a[r0:r1, c0:c1]`` with anything off the array as ``fill``."""
    out = np.full((r1 - r0, c1 - c0), fill, a.dtype)
    top, left = max(r0, 0), max(c0, 0)
    bottom, right = min(r1, a.shape[0]), min(c1, a.shape[1])
    if top < bottom and left < right:
        out[top - r0 : bottom - r0, left - c0 : right - c0] = a[top:bottom, left:right]
    return out


def support(mask: np.ndarray, pad: int) -> tuple[slice, slice] | None:
    """The box of ``mask``'s true pixels widened by ``pad`` each way and clipped to the array; None when it has none.

    A block's class masks fill a small part of it, and labelling, blurring and contouring cost what the array costs:
    done on this box they are the same masks, fields and rings, for a fraction of the work (W50)."""
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size == 0:
        return None
    cols = np.flatnonzero(mask.any(axis=0))
    return (
        slice(max(int(rows[0]) - pad, 0), min(int(rows[-1]) + 1 + pad, mask.shape[0])),
        slice(max(int(cols[0]) - pad, 0), min(int(cols[-1]) + 1 + pad, mask.shape[1])),
    )


def _small_parts(mask: np.ndarray, smallest: int) -> np.ndarray:
    """Patches under ``smallest`` pixels that do not reach the window's edge, which may go on beyond it."""
    labels, _count = ndimage.label(mask)
    sizes = np.bincount(labels.ravel())
    small = sizes < smallest
    small[0] = False
    edge = np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1]))
    small[edge] = False
    return small[labels]


def despeck(mask: np.ndarray, smallest: int) -> np.ndarray:
    """Without patches and holes under ``smallest`` pixels.

    On the mask's box with a ring of one pixel round it: a patch or a hole that meets the ring there meets the
    window's edge in the whole array, through the empty ground beyond the box, and labelling joins 4-neighbours
    only, so the same parts are kept and filled (W50)."""
    if smallest <= 1 or not mask.any():
        return mask
    box = support(mask, 1)
    part = mask[box]
    kept = part & ~_small_parts(part, smallest)
    out = np.zeros_like(mask)
    out[box] = kept | _small_parts(~kept, smallest)
    return out


def soft(mask: np.ndarray, sigma: float) -> np.ndarray:
    return ndimage.gaussian_filter(mask.astype(np.float32), sigma, truncate=GAUSS_REACH)


def soft_near(mask: np.ndarray, sigma: float) -> np.ndarray:
    """``soft`` blurred only on the mask's box widened by the kernel's reach, and zero beyond it, as ``soft`` gives.

    Past the reach every tap reads an empty pixel, so the blur is exactly zero there; the box's own edges reflect
    empty pixels as the whole array's do, so every pixel inside is summed from the same values in the same order
    (W50)."""
    reach = int(GAUSS_REACH * float(sigma) + 0.5) + 1
    box = support(mask, reach)
    out = np.zeros(mask.shape, np.float32)
    if box is not None:
        out[box] = soft(mask[box], sigma)
    return out


def contour_near(field: np.ndarray, level: float = ISO) -> tuple[list[shapely.Polygon], int, int]:
    """``contour_polygons`` of the box where ``field`` is above zero, a pixel round it, and that box's first row and
    column: its rings are the whole field's moved by them, up to the last bit of a coordinate (W50)."""
    box = support(field > 0.0, 1)
    if box is None:
        return [], 0, 0
    return contour_polygons(field[box], level), box[0].start, box[1].start


def contour_polygons(field: np.ndarray, level: float = ISO) -> list[shapely.Polygon]:
    """Polygons of ``field >= level`` in (column, row) coordinates of the array."""
    points, offsets = _generator(field).filled(level, np.inf)
    polygons = []
    for ring_points, ring_offsets in zip(points, offsets, strict=True):
        rings = [ring_points[a:b] for a, b in pairwise(ring_offsets)]
        polygons.append(shapely.Polygon(rings[0], rings[1:]))
    return polygons


def as_map(geometry, x0: float, y0: float, pixel: float, first_col: int, first_row: int):
    """From (column, row) of a window to map coordinates; a raster's pixel 0 is centred half a pixel in."""
    return shapely.transform(
        geometry,
        lambda p: np.column_stack(
            (x0 + (p[:, 0] + first_col + 0.5) * pixel, y0 - (p[:, 1] + first_row + 0.5) * pixel)
        ),
    )


def multi(parts: list) -> shapely.Geometry:
    """A valid area from polygons that may touch at a point."""
    if not parts:
        return shapely.MultiPolygon()
    valid = shapely.make_valid(np.asarray(parts, dtype=object))
    return shapely.union_all(valid, grid_size=None) if len(parts) < 2 else shapely.coverage_union_all(valid)


def _block_cumulative(classes, levels, r0, r1, c0, c1, reach, smallest, sigma, watch):
    """The soft cumulative masks of one block, cut to the block; ``None`` for a level absent here."""
    wide = window(classes, r0 - reach, r1 + 1 + reach, c0 - reach, c1 + 1 + reach, DRY)
    masks = [None] * (levels + 1)
    for k in range(levels, 0, -1):
        mask = despeck(wide >= k, smallest)
        if k < levels and masks[k + 1] is not None:
            mask = mask | masks[k + 1]
        masks[k] = mask if mask.any() else None
    cut = (slice(reach, -reach), slice(reach, -reach))
    raw = wide[cut]
    fields: list = [None] * (levels + 1)
    for k in range(1, levels + 1):
        watch.check()
        if masks[k] is not None:
            field = soft_near(masks[k], sigma)[cut]
            fields[k] = (field, area_iso(field, block_area(raw >= k)))
    return raw > DRY, fields


def block_area(mask: np.ndarray) -> float:
    """Pixels of a mask inside its block: the block's edges run through pixel centres, so they count by half."""
    return (
        float(mask.sum())
        - 0.5 * float(mask[0].sum() + mask[-1].sum() + mask[:, 0].sum() + mask[:, -1].sum())
        + 0.25 * float(mask[0, 0]) + 0.25 * float(mask[0, -1]) + 0.25 * float(mask[-1, 0]) + 0.25 * float(mask[-1, -1])
    )


def _generator(field: np.ndarray):
    ny, nx = field.shape
    return contourpy.contour_generator(
        np.arange(nx, dtype=np.float64),
        np.arange(ny, dtype=np.float64),
        field.astype(np.float64),
        name="serial",
        fill_type=contourpy.FillType.OuterOffset,
    )


def _held_area(made, level: float) -> float:
    """Area inside the contour, pixels; contourpy turns outer rings and holes opposite ways, so they net out."""
    total = 0.0
    for points, offsets in zip(*made.filled(level, np.inf), strict=True):
        for a, b in pairwise(offsets):
            x, y = points[a : b - 1, 0], points[a : b - 1, 1]
            total += 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    return abs(total)


def area_iso(field: np.ndarray, pixels: float) -> float:
    """The contour of a soft mask that holds the area of the raw class: thin, broken patches shrink at one half."""
    if pixels <= 0:
        return ISO
    box = support(field > 0.0, 1)  # the area inside a contour does not move with the box (W50)
    if box is None:
        return ISO_LOW
    made = _generator(field[box])
    low, high = ISO_LOW, ISO_HIGH
    if _held_area(made, low) <= pixels:
        return low
    if _held_area(made, high) >= pixels:
        return high
    for _ in range(ISO_STEPS):
        middle = 0.5 * (low + high)
        low, high = (middle, high) if _held_area(made, middle) > pixels else (low, middle)
    return 0.5 * (low + high)


def _block_bands(classes, box: tuple, index: int, levels: int, reach: int, smallest: int, profile, smooth, watch):
    """The class polygons of one block: rows, area drawn per class, wet pixels added and removed."""
    transform = profile["transform"]
    pixel, x0, y0 = transform.a, transform.c, transform.f
    r0, r1, c0, c1 = box
    raw_wet, fields = _block_cumulative(classes, levels, r0, r1, c0, c1, reach, smallest, smooth.sigma_px, watch)
    added = removed = 0
    if fields[1] is not None:
        smooth_wet = fields[1][0] >= fields[1][1]
        added = int((smooth_wet & ~raw_wet).sum())
        removed = int((raw_wet & ~smooth_wet).sum())
    rows = []
    shown = np.zeros(levels + 1)
    above = shapely.MultiPolygon()
    for k in range(levels, 0, -1):
        watch.check()
        if fields[k] is None:
            continue
        parts, dr, dc = contour_near(*fields[k])
        area = multi([as_map(p, x0, y0, pixel, c0 + dc, r0 + dr) for p in parts])
        if smooth.simplify_px > 0.0:
            area = shapely.simplify(area, smooth.simplify_px * pixel)
        band = shapely.difference(area, above)
        above = shapely.union(area, above)  # contours read at different values can cross where classes pinch
        if not band.is_empty:
            rows.append((k, index, band))
            shown[k] = shapely.area(band) / M2_PER_KM2
    return rows, shown, added, removed


def class_polygons(cfg: RunConfig, classes: np.ndarray, profile: dict, watch) -> tuple[list, dict]:
    """Rows of (class, block, geometry) and the area accounts, against the raw classes."""
    smooth, rule = cfg.outputs.smooth, cfg.outputs.pixels
    pixel = profile["transform"].a
    levels = len(rule.hazard_limits) + 1
    smallest = int(np.ceil(smooth.speckle_m2 / pixel**2))
    reach = int(np.ceil(GAUSS_REACH * smooth.sigma_px)) + max(int(np.ceil(np.sqrt(smallest))), 2) + 2
    height, width = classes.shape
    rows_of = list(block_ranges(height, smooth.block_px))
    cols_of = list(block_ranges(width, smooth.block_px))
    blocks = [(*r, *c) for r in rows_of for c in cols_of]
    wet = [box for box in blocks if (window(classes, box[0], box[1] + 1, box[2], box[3] + 1, DRY) > DRY).any()]
    workers = smooth.workers or max((os.cpu_count() or 2) // 2, 1)
    rows: list[tuple[int, int, shapely.Geometry]] = []
    km2 = pixel**2 / M2_PER_KM2
    shown = np.zeros(levels + 1)
    added = removed = 0
    with ThreadPoolExecutor(workers) as pool:  # GEOS and SciPy let go of the GIL
        tasks = [
            pool.submit(_block_bands, classes, box, index, levels, reach, smallest, profile, smooth, watch)
            for index, box in enumerate(wet)
        ]
        try:
            for finished, task in enumerate(as_completed(tasks)):
                watch.tick("smooth", finished, 2 * len(tasks))
                found, drawn, plus, minus = task.result()
                rows.extend(found)
                shown += drawn
                added += plus
                removed += minus
        except BaseException:
            for task in tasks:
                task.cancel()
            raise
    rows.sort(key=lambda row: (row[1], row[0]))
    names = class_names(rule)
    raw = {name: float((classes == k + 1).sum()) * km2 for k, name in enumerate(names)}
    drawn_km2 = {name: float(shown[k + 1]) for k, name in enumerate(names)}
    accounts = {
        "raw_km2": {name: round(value, 4) for name, value in raw.items()},
        "drawn_km2": {name: round(value, 4) for name, value in drawn_km2.items()},
        "change_pct": {
            name: round(100.0 * (drawn_km2[name] - raw[name]) / raw[name], 3) if raw[name] else 0.0 for name in names
        },
        "wet_added_km2": round(added * km2, 4),
        "wet_removed_km2": round(removed * km2, 4),
    }
    return rows, accounts


def domain_outline(tables: GridTables, sigma_cells: float) -> shapely.Geometry:
    """The active cells as a smooth outline, not a staircase; the walls of the run are where the cells are."""
    grid = tables.grid
    field = soft(np.pad(grid.mask, 2), sigma_cells)
    parts = [as_map(p, grid.x0, grid.y0, grid.dx, -2, -2) for p in contour_polygons(field)]
    return chaikin_rings(multi(parts), DOMAIN_CHAIKIN)


def hazard_layer(rows: list, names: list[str]) -> VectorLayer:
    """The class polygons as a GeoPackage layer."""
    return VectorLayer(
        CLASS_LAYER,
        {"class": int, "name": str, "area_km2": float, "block": int},
        [(k, names[k - 1], shapely.area(g) / M2_PER_KM2, b) for k, b, g in rows],
        [g for _k, _b, g in rows],
    )


def domain_layer(domain) -> VectorLayer:
    return VectorLayer(DOMAIN_LAYER, {"label": str}, [("2D model domain",)], [domain])


def class_layers(rows: list, domain, names: list[str]) -> list[VectorLayer]:
    """The class polygons and the outline, as GeoPackage layers."""
    return [hazard_layer(rows, names), domain_layer(domain)]


def run_layers(cfg: RunConfig, tables: GridTables, crs) -> list[VectorLayer]:
    """The outline of the domain and what the engine was given: in the GeoPackage of every run, drawn or not, because
    the map sheets and the layers a run loads read them (W50)."""
    domain = domain_outline(tables, cfg.outputs.smooth.domain_sigma_cells)
    return [domain_layer(domain), *setup_layers(cfg, crs_text(crs))]


def _fill_dry(depth, wet, nd=ndimage):
    """Depth carried out over the dry pixels, so the blur of a wet edge does not fade into zero."""
    if bool(wet.all()) or not bool(wet.any()):
        return depth
    nearest = nd.distance_transform_edt(~wet, return_distances=False, return_indices=True)
    return depth[tuple(nearest)]


def draw_block(depth: np.ndarray, scale: int, sigma: float, edge: float, xp=np) -> np.ndarray:
    """The depth drawing of a window: blurred, ``scale`` times finer, fading to nothing over the wet edge.

    ``xp`` is numpy or cupy: on the GPU the same steps run through ``cupyx.scipy.ndimage`` (W50), and the drawing comes
    back to the host. It is a picture of the depth raster, not a number of record."""
    nd = ndimage
    if xp is not np:
        import cupyx.scipy.ndimage as nd
    d = xp.asarray(depth)
    wet = d > 0.0
    full = _fill_dry(d, wet, nd)
    fine = xp.repeat(xp.repeat(full, scale, axis=0), scale, axis=1)
    fine_wet = xp.repeat(xp.repeat(wet, scale, axis=0), scale, axis=1)
    if sigma > 0.0:
        fine = nd.gaussian_filter(fine, sigma * scale, truncate=GAUSS_REACH)
    fade = (nd.gaussian_filter(fine_wet.astype(xp.float32), edge * scale, truncate=GAUSS_REACH) - EDGE_LOW) / (EDGE_HIGH - EDGE_LOW)
    fade = xp.clip(fade, 0.0, 1.0)
    out = (fine * fade * fade * (3.0 - 2.0 * fade)).astype(xp.float32)
    return out if xp is np else xp.asnumpy(out)


def _draw(wide: np.ndarray, smooth, xp) -> np.ndarray:
    """One block on the GPU when there is one; a block the card cannot hold is drawn on the CPU."""
    if xp is not np:
        try:
            return draw_block(wide, smooth.depth_scale, smooth.depth_sigma_px, smooth.wet_edge_px, xp)
        except Exception as error:
            if type(error).__name__ != "OutOfMemoryError":
                raise
            xp.get_default_memory_pool().free_all_blocks()
    return draw_block(wide, smooth.depth_scale, smooth.depth_sigma_px, smooth.wet_edge_px)


def depth_drawing(cfg: RunConfig, depth: np.ndarray, profile: dict, path: Path, watch, xp=np) -> Path:
    """The depth drawing, block by block, into a raster ``depth_scale`` times finer than the pixel; on the GPU when
    ``xp`` is cupy (W50)."""
    smooth = cfg.outputs.smooth
    scale = smooth.depth_scale
    t = profile["transform"]
    height, width = depth.shape
    fine = {
        **profile,
        "height": height * scale,
        "width": width * scale,
        "transform": t * t.scale(1.0 / scale),
        "dtype": "float32",
        "nodata": DRAWING_NODATA,
    }
    reach = int(np.ceil(GAUSS_REACH * max(smooth.depth_sigma_px, smooth.wet_edge_px))) + 2
    tmp = path.with_name(f"{path.stem}.tmp{path.suffix}")
    block = smooth.block_px
    corners = [(r, c) for r in range(0, height, block) for c in range(0, width, block)]
    try:
        with rasterio.open(tmp, "w", **fine) as out:
            for index, (r0, c0) in enumerate(corners):
                watch.tick("smooth", len(corners) + index, 2 * len(corners))
                r1, c1 = min(r0 + block, height), min(c0 + block, width)
                wide = window(depth, r0 - reach, r1 + reach, c0 - reach, c1 + reach, 0.0)
                if not (wide > 0.0).any():
                    continue
                drawn = _draw(wide, smooth, xp)
                cut = drawn[reach * scale : -reach * scale, reach * scale : -reach * scale]
                box = Window(c0 * scale, r0 * scale, (c1 - c0) * scale, (r1 - r0) * scale)
                out.write(cut, 1, window=box)
            with rasterio.Env(GDAL_NUM_THREADS=THREADS):
                out.build_overviews(OVERVIEWS, Resampling.average)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
    return path


def make_drawings(
    cfg, classes: np.ndarray, depth: np.ndarray, profile: dict, folder: Path, crs, watch, xp=np, layers: list | None = None
) -> dict:
    """The class polygons and the depth drawing of a class raster and its depth; what was drawn against what the
    pixels say. ``layers`` are the run's other layers, written with the polygons into a new GeoPackage; without
    them the polygons go into the one the run already has (W50)."""
    rows, accounts = class_polygons(cfg, classes, profile, watch)
    hazard = hazard_layer(rows, class_names(cfg.outputs.pixels))
    if layers is None:
        add_layer(folder / LAYERS_FILE, hazard, crs_text(crs))
    else:
        write_geopackage(folder / LAYERS_FILE, [hazard, *layers], crs_text(crs))
    depth_drawing(cfg, depth, raster_profile(depth.shape, *_pixel_origin(profile), crs), folder / DRAWING_FILE, watch, xp)
    watch.tick("smooth", 1, 1)
    return accounts


def crs_text(crs) -> str:
    return crs.to_wkt() if hasattr(crs, "to_wkt") else crs


def _pixel_origin(profile: dict) -> tuple[float, float, float]:
    t = profile["transform"]
    return t.a, t.c, t.f
