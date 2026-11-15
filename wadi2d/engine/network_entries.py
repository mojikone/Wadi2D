"""Lumped water kept on the HMS network down to the grid (W88, the owner's run 3 of 2026-11-15).

``hydrology.lumped_entry: outlet`` (the default, the HMS import as it always was): each lumped subbasin's hydrograph
enters the grid at its own outlet, and the grid routes it from there (run 4 of W79). ``network``: the lumped water stays
on the HMS reaches, junctions and reservoirs as long as only lumped subbasins drain to them, and enters the grid where
the network first meets water from a rain-on-grid subbasin (run 3: at the dams and at HAT-J4).

The rule, element by element of the HMS basin:

- An element is *lumped all the way* when every subbasin above it, itself included, is lumped.
- A lumped subbasin's water goes down its ``Downstream`` links while the next element is lumped all the way. Where it
  stops is its *entry element*: the last one before a rain-on-grid subbasin's water joins, or an outlet of the network.
- At an entry element that is the subbasin itself, nothing changes: it enters at its outlet, as before.
- Every other entry element gets one inflow of its outflow at its HMS icon (a reach: its downstream end), ``entry:
  point``; the subbasins it carries lose their outlets. An inflow the job already gives from that element is kept with
  its own point (W79's dam outflows 200 m below the dams). HMS icons are schematic: with ``grid.exclude_lumped`` an icon
  inside the left-out catchments moves to the wadi just outside them (:mod:`wadi2d.engine.left_out`).
- An entry element that is an outlet of the network (a sink, or an element draining nowhere) is where the water leaves
  the model, as in HMS: its inflow is written with ``enters: false``. Its series is kept, and the subbasins above it
  count as carried, so the mesh may leave them out. With every subbasin lumped, no water enters the grid at all: the
  HMS way, run 2.
- An element whose second outlet (a diversion, a reservoir's auxiliary outlet) feeds an element that is not lumped all
  the way is refused in words: that water would reach neither the network's entry nor the grid.

Interface: :func:`route_on_network`, :func:`hms_icons`.
"""

from __future__ import annotations

from wadi2d.config.schema import ENTRY_POINT, LUMPED_ON_NETWORK, Inflow, RunConfig
from wadi2d.hydrology.model import Basin, Branching

OUTFLOW = "{element} outflow"
"""The name of an inflow made for an entry element."""


def _all_lumped(basin: Basin, lumped: set[str]) -> dict[str, bool]:
    subbasins = set(basin.subbasins)
    out = {}
    for name in basin.elements:
        above = basin.upstream_of(name) & subbasins
        out[name] = bool(above) and above <= lumped
    return out


def _entry_element(basin: Basin, start: str, complete: dict[str, bool]) -> str:
    name = start
    while True:
        element = basin.elements[name]
        below = element.downstream
        if below is None or not complete[below]:
            break
        branch = element.branch if isinstance(element, Branching) else None
        if branch is not None and not complete[branch]:
            break
        name = below
    element = basin.elements[name]
    branch = element.branch if isinstance(element, Branching) else None
    if branch is not None and not complete[branch] and name != start:
        raise ValueError(
            f"{name} sends part of its water to {branch}, which a rain-on-grid subbasin drains to: on the lumped "
            "network that part would reach neither the grid nor the network's entry. Switch the subbasins above "
            f"{branch} to lumped, or let the lumped water enter at each subbasin's outlet"
        )
    return name


def route_on_network(cfg: RunConfig, basin: Basin, icons: dict[str, tuple[float, float] | None]) -> RunConfig:
    """The job with the lumped water kept on the network (see the module's words); the job itself when it asks for
    the subbasins' outlets. ``icons`` gives each element's HMS icon. Calling it again on its own result adds nothing."""
    h = cfg.hydrology
    if h.lumped_entry != LUMPED_ON_NETWORK:
        return cfg
    lumped = {s.name for s in h.subbasins if s.mode == "lumped" and s.name in basin.elements}
    complete = _all_lumped(basin, lumped)
    entry = {name: _entry_element(basin, name, complete) for name in lumped}
    given = {i.element for i in h.inflows if i.element is not None}
    inflows = list(h.inflows)
    for element in dict.fromkeys(e for name, e in entry.items() if e != name):
        if element in given:
            continue
        point = icons.get(element)
        if point is None:
            raise ValueError(
                f"the lumped water enters the grid at {element}, which has no icon in the HMS basin: give an inflow "
                f"from element {element} with its point"
            )
        leaves = basin.elements[element].downstream is None
        inflows.append(
            Inflow(name=OUTFLOW.format(element=element), x=point[0], y=point[1], element=element, entry=ENTRY_POINT,
                   enters=not leaves)
        )  # fmt: skip
    subbasins = [
        s.model_copy(update={"outlet": None}) if s.name in entry and entry[s.name] != s.name else s
        for s in h.subbasins
    ]
    return cfg.model_copy(update={"hydrology": h.model_copy(update={"subbasins": subbasins, "inflows": inflows})})


def hms_icons(hms_basin) -> dict[str, tuple[float, float] | None]:
    """Each element's HMS icon: a reach's downstream end, any other element's own icon."""
    out = {}
    for element in hms_basin.elements:
        x, y = element.canvas_x, element.canvas_y
        out[element.name] = None if x is None or y is None else (float(x), float(y))
    return out

