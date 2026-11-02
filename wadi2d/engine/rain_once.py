"""A cell never gets two rainfalls (the owner's rule, work order item 9): the check before a run.

A lumped subbasin's polygon masks the rain under it, because its rain is in its hydrograph. Where two lumped polygons
overlap, the ground they share is counted in both hydrographs; where a 2D subbasin's polygon lies under a lumped one,
its cells there get no rain. Both are measured as what they are: the overlapping area, in cells of the domain, as a
share of the smaller polygon. Over ``hydrology.overlap_share`` the run stops, with the cell count and the names; under
it the run says so and goes on, because digitised polygons meet along slivers (Block 2's own HMS polygons share
0.1 % of the catchment at 40 m), and a sliver masks its rain once and is no double count worth a stop.

Only polygon overlap counts. A cell whose centre falls exactly on a shared edge is burned for both by the rasteriser
and masked once by the forcing; that is a tie, not an overlap, and it is not reported.

Interface: :func:`check_rain_once`.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import shapely
from rasterio import features

from wadi2d.grid.tiles import TileGrid
from wadi2d.io.geotiff import grid_transform

PERCENT = 100.0


def _cells(grid: TileGrid, geometry: shapely.Geometry) -> int:
    burned = features.rasterize(
        [(geometry, 1)], out_shape=grid.shape, transform=grid_transform(grid), fill=0, dtype="uint8"
    )
    return int(np.count_nonzero(burned.astype(bool) & grid.mask))


def _overlap(a: shapely.Geometry, b: shapely.Geometry) -> shapely.Geometry | None:
    """The area two polygons share, or None when they only touch."""
    if not a.intersects(b):
        return None
    shared = a.intersection(b)
    parts = [p for p in shapely.get_parts(shared) if p.geom_type == "Polygon" and p.area > 0.0]
    return shapely.union_all(parts) if parts else None


def check_rain_once(
    grid: TileGrid,
    polygons: Mapping[str, shapely.Geometry],
    lumped: list[str],
    two_d: list[str],
    share: float,
) -> list[str]:
    """Notes on every pair that overlaps; raises, in words, when a pair shares more than ``share`` of the smaller."""
    notes: list[str] = []
    held = [name for name in lumped if name in polygons]
    pairs = [(a, b) for n, a in enumerate(held) for b in held[n + 1 :]]
    pairs += [(name, other) for name in two_d if name in polygons for other in held]
    for a, b in pairs:
        shared = _overlap(polygons[a], polygons[b])
        if shared is None:
            continue
        cells = _cells(grid, shared)
        if cells == 0:
            continue
        fraction = shared.area / min(polygons[a].area, polygons[b].area)
        if a in two_d:
            what = f"{cells} cells of 2D subbasin {a} lie under lumped {b}"
            harm = "the rain there is masked for the one and counted for the other"
        else:
            what = f"{cells} cells lie under both lumped subbasins {a} and {b}"
            harm = "their rain would be counted in both hydrographs"
        text = f"{what} ({fraction * PERCENT:.2f} % of the smaller polygon)"
        if fraction > share:
            raise ValueError(
                f"{text}: {harm}. Polygons must not overlap; hydrology.overlap_share ({share:g}) is what a sliver "
                "along a shared edge may take"
            )
        notes.append(f"{text}: a sliver along a shared edge, under hydrology.overlap_share; the rain there is masked once")
    return notes
