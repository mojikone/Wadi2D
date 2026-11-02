"""A cell never gets two rainfalls (the owner's rule, work order item 9): the check that stops a run.

A lumped subbasin's polygon masks the rain under it, because its rain is in its hydrograph. So a cell under two lumped
polygons counts the same rain twice, once in each hydrograph, and a cell of a 2D subbasin under a lumped polygon loses
the rain it should get. Both are refused by name and cell count, before the run starts. The cells are the ones
``Forcing`` masks: cell centres inside a polygon, the same rule as :func:`wadi2d.forcing._labels`.

Interface: :func:`check_rain_once`.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import shapely
from rasterio import features

from wadi2d.grid.tiles import TileGrid
from wadi2d.io.geotiff import grid_transform

SHOWN = 6
"""Names listed in a message before the rest is counted."""


def _mask(grid: TileGrid, polygon: shapely.Geometry) -> np.ndarray:
    return features.rasterize(
        [(polygon, 1)], out_shape=grid.shape, transform=grid_transform(grid), fill=0, dtype="uint8"
    ).astype(bool)


def _said(names: list[str]) -> str:
    if len(names) <= SHOWN:
        return ", ".join(names)
    return f"{', '.join(names[:SHOWN])} and {len(names) - SHOWN} more"


def check_rain_once(
    grid: TileGrid, polygons: Mapping[str, shapely.Geometry], lumped: list[str], two_d: list[str]
) -> None:
    """Raise, in words, where a cell of the domain would count rain twice or lose it."""
    held = np.zeros(grid.shape, np.int16)
    masks: dict[str, np.ndarray] = {}
    for name in lumped:
        if name in polygons:
            masks[name] = _mask(grid, polygons[name]) & grid.mask
            held += masks[name]
    doubled = held > 1
    if doubled.any():
        guilty = [name for name, mask in masks.items() if (mask & doubled).any()]
        raise ValueError(
            f"{int(doubled.sum())} cells lie under two lumped subbasins ({_said(guilty)}): their rain would be "
            "counted in both hydrographs. Lumped polygons must not overlap"
        )
    under = held > 0
    for name in two_d:
        if name not in polygons:
            continue
        shared = _mask(grid, polygons[name]) & grid.mask & under
        if shared.any():
            over = [other for other, mask in masks.items() if (mask & shared).any()]
            raise ValueError(
                f"{int(shared.sum())} cells of 2D subbasin {name} lie under lumped {_said(over)}: the rain there is "
                "masked for the one and counted for the other. Polygons must not overlap"
            )
