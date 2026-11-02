"""How water leaves each junction of a basin model, for the rule that decides what stays out of the 2D grid.

A reservoir counts as a junction here. The route is ``reach`` only where the reach below can run; a reach that lacks a
parameter is named, with what it lacks, and the route is ``none``: that water runs in 2D to the next junction.

Interface: :class:`JunctionRoute`, :func:`junction_routes`.
"""

from __future__ import annotations

from dataclasses import dataclass

from wadi2d.basin.contract import JUNCTION, REACH, RESERVOIR, Model

ROUTE_REACH = "reach"
ROUTE_NONE = "none"


@dataclass(frozen=True)
class JunctionRoute:
    """One junction: how it drains and to which junction; ``next_junction`` is None at an outlet."""

    junction: str
    route: str
    reach: str | None
    next_junction: str | None
    reach_missing: tuple[str, ...] = ()


def junction_routes(model: Model) -> dict[str, JunctionRoute]:
    """The route of every junction of a model."""
    elements = {element["name"]: element for element in model["elements"]}
    routes: dict[str, JunctionRoute] = {}
    for element in model["elements"]:
        if element["kind"] in (JUNCTION, RESERVOIR):
            name, below = element["name"], element["downstream"]
            target = None if below is None else elements[below]
            if target is not None and target["kind"] == REACH:
                missing = tuple(target["missing"])
                route = ROUTE_NONE if missing else ROUTE_REACH
                routes[name] = JunctionRoute(name, route, below, target["downstream"], missing)
            else:
                routes[name] = JunctionRoute(name, ROUTE_NONE, None, below)
    return routes
