"""A dam of the job as a reservoir of the lumped network.

The pool behind a crest line is measured on the ground: at each level, the pixels at or below it that drain through the line
and touch it. The rating is the job's spillway object, Q = C L H^1.5. Levels are on the datum of the DEM; the job's crest and
spillway levels must be on that datum too, which on Block 2 they are not for the GGC terrain (2.39 m apart).

Interface: :class:`PoolTable`, :func:`pool_table`, :func:`spillways_of`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely
from scipy import ndimage

from wadi2d.basin.delineate import Surface
from wadi2d.basin.kernels import above
from wadi2d.config.schema import BasinSettings, RunConfig, TerrainObject
from wadi2d.hydrology.reservoir import MAIN_OUTLET

ALL_NEIGHBOURS = np.ones((3, 3), dtype=np.int8)


@dataclass(frozen=True)
class PoolTable:
    """Elevation, area and volume behind a dam, from the lowest ground on its line up."""

    elevation_m: np.ndarray
    area_m2: np.ndarray
    volume_m3: np.ndarray


def crest_of(obj: TerrainObject) -> float:
    """The level of a crest or spillway: its lowest point when it varies."""
    return float(obj.z_constant) if obj.z_constant is not None else float(min(obj.z))


def pool_table(surface: Surface, line: np.ndarray, top_m: float, step_m: float) -> PoolTable:
    """The table of a dam whose line covers the flat pixels ``line``, up to ``top_m``."""
    seeds = np.zeros(surface.down.size, dtype=bool)
    seeds[line] = True
    behind = above(surface.down, surface.order, seeds).reshape(surface.shape) & (surface.z <= top_m)
    rows, cols = np.nonzero(behind)
    crop = (slice(rows.min(), rows.max() + 1), slice(cols.min(), cols.max() + 1))
    ground, inside, on_line = surface.z[crop], behind[crop], seeds.reshape(surface.shape)[crop]
    bed = float(surface.z.ravel()[line].min())
    levels = np.arange(bed, top_m + 0.5 * step_m, step_m)
    areas = np.empty(levels.size)
    volumes = np.empty(levels.size)
    per_pixel = surface.pixel * surface.pixel
    for index, level in enumerate(levels):
        wet = inside & (ground <= level)
        parts, count = ndimage.label(wet, structure=ALL_NEIGHBOURS)
        touching = np.zeros(count + 1, dtype=bool)
        touching[parts[on_line & wet]] = True
        touching[0] = False
        pool = touching[parts]
        areas[index] = np.count_nonzero(pool) * per_pixel
        volumes[index] = np.sum(level - ground[pool]) * per_pixel
    return PoolTable(levels, areas, volumes)


def spillways_of(
    crest: TerrainObject, cfg: RunConfig, settings: BasinSettings
) -> list[dict[str, float | int]]:
    """Every spillway object of the job on this crest line, as a rating."""
    line = shapely.LineString(crest.coordinates)
    ratings: list[dict[str, float | int]] = []
    for obj in cfg.terrain.objects:
        if obj.kind == "spillway":
            crest_line = shapely.LineString(obj.coordinates)
            if line.distance(crest_line) <= settings.dam_join_m:
                ratings.append(
                    {
                        "crest_elevation_m": crest_of(obj),
                        "crest_length_m": crest_line.length if obj.length is None else float(obj.length),
                        "coefficient": float(obj.coefficient),
                        "outlet": MAIN_OUTLET,
                    }
                )
    return ratings
