"""From ``basin.json`` to the lumped engine's objects, so :class:`LumpedEngine` runs on it unchanged.

Interface: :func:`load_network`. An incomplete element raises and names what it lacks. With ``skip_incomplete`` the network holds
only what can run: an incomplete subbasin leaves, an incomplete reach cuts the network (the element above it becomes an outlet of
the lumped network, its water for the 2D grid), and a reservoir with no rating passes its inflow as a junction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from wadi2d.basin.contract import (
    REACH,
    RESERVOIR,
    SUBBASIN,
    Element,
    Model,
    check_model,
    read_model,
    refresh,
    value_of,
)
from wadi2d.hydrology.losses import LOSS_METHODS, SCS_CN
from wadi2d.hydrology.model import Basin, Junction, Reach, Reservoir, Subbasin
from wadi2d.hydrology.reservoir import RESERVOIR_OUTFLOW_STRUCTURES, Spillway
from wadi2d.hydrology.routing import MUSKINGUM_CUNGE, ROUTING_METHODS
from wadi2d.hydrology.transforms import SCS_UH, TRANSFORM_METHODS


def _subbasin(element: Element, downstream: str | None) -> Subbasin:
    return Subbasin(
        name=element["name"],
        downstream=downstream,
        area_km2=value_of(element, "area_km2"),
        loss=LOSS_METHODS.build(SCS_CN, curve_number=value_of(element, "curve_number")),
        transform=TRANSFORM_METHODS.build(SCS_UH, lag_minutes=value_of(element, "lag_minutes")),
    )


def _reach(element: Element, downstream: str | None) -> Reach:
    routing = ROUTING_METHODS.build(
        MUSKINGUM_CUNGE,
        length_m=value_of(element, "length_m"),
        slope=value_of(element, "slope"),
        roughness=value_of(element, "manning_n"),
        bottom_width_m=value_of(element, "bottom_width_m"),
        side_slope=value_of(element, "side_slope"),
        index_celerity=value_of(element, "index_celerity"),
    )
    return Reach(name=element["name"], downstream=downstream, routing=routing)


def _reservoir(element: Element, downstream: str | None) -> Reservoir:
    routing = ROUTING_METHODS.build(
        RESERVOIR_OUTFLOW_STRUCTURES,
        elevations_m=np.asarray(value_of(element, "elevation_m"), dtype=np.float64),
        areas_m2=np.asarray(value_of(element, "area_m2"), dtype=np.float64),
        spillways=tuple(Spillway(**rating) for rating in value_of(element, "spillways")),
        initial_elevation_m=value_of(element, "initial_elevation_m"),
    )
    return Reservoir(name=element["name"], downstream=downstream, routing=routing)


def _as_model(source: str | Path | Model) -> Model:
    return read_model(source) if isinstance(source, str | Path) else refresh(check_model(source))


def _complete(model: Model) -> tuple[list[Element], set[str]]:
    """The elements kept, and the names the network is cut at."""
    kept: list[Element] = []
    cut: set[str] = set()
    for element in model["elements"]:
        if not element["missing"] or element["kind"] == RESERVOIR:
            kept.append(element)
        elif element["kind"] == REACH:
            cut.add(element["name"])
    return kept, cut


def load_network(source: str | Path | Model, skip_incomplete: bool = False) -> Basin:
    """The engine's basin of a model, or of its file."""
    model = _as_model(source)
    incomplete = {e["name"]: e["missing"] for e in model["elements"] if e["missing"]}
    if incomplete and not skip_incomplete:
        raise ValueError(f"incomplete elements: {incomplete}")
    kept, cut = _complete(model)
    built: list[Any] = []
    for element in kept:
        downstream = None if element["downstream"] in cut else element["downstream"]
        if element["kind"] == SUBBASIN:
            built.append(_subbasin(element, downstream))
        elif element["kind"] == REACH:
            built.append(_reach(element, downstream))
        elif element["kind"] == RESERVOIR and not element["missing"]:
            built.append(_reservoir(element, downstream))
        else:
            built.append(Junction(name=element["name"], downstream=downstream))
    return Basin(model["name"], built)
