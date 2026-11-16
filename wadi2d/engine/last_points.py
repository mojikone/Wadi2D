"""Where the lumped model ends: its last points (W105, his rule of 2026-11-16).

His words: "the dams are actually the last point of the lumped model", and "in Lumped and Hybrid Lumped, the ARF applies
to each point's upstream area. But in Hybrid 2D, the ARF applies to the area upstream of the last point of each basin,
like the dams and the one defined in HAT, since in Hybrid 2D we cannot run the 2D model for each upstream point."

- **The last points** are every dam of the lumped network (an HMS reservoir, a generated basin's dam) unless
  ``hydrology.last_points`` names them; a list names them all (dams and junctions alike, W79's HAT-J4 on Block 2), and
  ``[]`` none.
- **Hybrid Lumped** (``hydrology.lumped_entry: network``): the lumped water stops at the lowest last point on its way
  and enters the grid there, never further down a reach (:mod:`wadi2d.engine.network_entries`). Each element is
  reported at its own drainage area and the grid takes the last point's own hydrograph, at its own area: W98's rule,
  unchanged (:mod:`wadi2d.engine.entry_area`).
- **Hybrid 2D**: a lumped subbasin that enters the grid at its own outlet, the grid routing it from there, is read on
  the lumped curve at the drainage area of the first last point at or below it, one factor per dam: the 2D routing
  runs once, so it cannot be read at each point's own area. With no last point below it, its own area (W98).
- **Lumped**: every element at its own drainage area, HMS's depth-area analysis, unchanged.

Interface: :func:`last_points`, :func:`first_last_point`.
"""

from __future__ import annotations

from collections.abc import Iterable

from wadi2d.hydrology.model import Basin, Reservoir


def last_points(given: list[str] | None, basin: Basin) -> list[str]:
    """The last points of ``basin``: ``given`` (``hydrology.last_points``), or every reservoir when it is None, in file
    order. ``ValueError`` in words for a name the basin does not hold."""
    if given is None:
        return [name for name, element in basin.elements.items() if isinstance(element, Reservoir)]
    unknown = [name for name in given if name not in basin.elements]
    if unknown:
        raise ValueError(
            f"hydrology.last_points names {', '.join(unknown)}, which the lumped network does not hold: a last point "
            "is one of its elements, a dam or a junction"
        )
    return list(dict.fromkeys(given))


def first_last_point(basin: Basin, points: Iterable[str]) -> dict[str, str]:
    """Every element at or above a last point, with the first last point at or below it: of two, the one of smaller
    drainage area, which its water reaches first; a last point is its own."""
    points = list(points)
    area = {point: basin.drainage_area(point) for point in points}
    found: dict[str, str] = {}
    for point in points:
        for name in basin.upstream_of(point):
            held = found.get(name)
            if held is None or (held != name and (point == name or area[point] < area[held])):
                found[name] = point
    return found
