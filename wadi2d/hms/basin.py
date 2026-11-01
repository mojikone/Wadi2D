"""The ``.basin`` file: header, elements in file order, connectivity.

Interface: :func:`load`, :func:`from_document`, :class:`Basin`, :class:`Connectivity` and the element
models. Geometry does not come from here: ``Canvas X/Y`` are icon positions, polygons and lines live in the
``.sqlite``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import Field, SerializeAsAny

from wadi2d.hms import text
from wadi2d.hms.methods import (
    BASEFLOW_METHODS,
    LOSS_METHODS,
    RESERVOIR_ROUTE_METHODS,
    ROUTE_METHODS,
    TRANSFORM_METHODS,
    build_method,
)
from wadi2d.hms.text import Document
from wadi2d.hms.typed import BlockModel, Cursor, HmsModel, Method, RawBlock, UnknownEntry, hms

HEADER_KIND = "Basin"
SPATIAL_KIND = "Basin Spatial Properties"
BREAK_POINT_KIND = "Break Point"
# Display state of the HMS interface and result-graph settings: kept raw, not worth reporting.
DISPLAY_KINDS = frozenset({"Basin Layer Properties", "Basin Schematic Properties", "Computation Point"})


class Element(BlockModel):
    """What every hydrologic element carries. Terminal elements have no ``downstream``."""

    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")
    description: str | None = hms("Description")
    latitude: float | None = hms("Latitude Degrees")
    longitude: float | None = hms("Longitude Degrees")
    canvas_x: float | None = hms("Canvas X")
    canvas_y: float | None = hms("Canvas Y")
    from_canvas_x: float | None = hms("From Canvas X")
    from_canvas_y: float | None = hms("From Canvas Y")
    downstream: str | None = hms("Downstream")


class Subbasin(Element):
    """A subbasin; ``area`` in the file's units (km2 when metric); methods keyed by their selector values."""

    area: float | None = hms("Area")
    discretization: str | None = hms("Discretization")
    file: str | None = hms("File")
    canopy: str | None = hms("Canopy")
    allow_simultaneous_precip_et: str | None = hms("Allow Simultaneous Precip Et")
    plant_uptake_method: str | None = hms("Plant Uptake Method")
    surface: str | None = hms("Surface")
    loss_rate: str | None = hms("LossRate")
    transform_method: str | None = hms("Transform")
    baseflow_method: str | None = hms("Baseflow")
    loss: SerializeAsAny[Method] | None = None
    transform: SerializeAsAny[Method] | None = None
    baseflow: SerializeAsAny[Method] | None = None

    @classmethod
    def extra_values(cls, cursor: Cursor, values: dict[str, Any]) -> dict[str, Any]:
        """Build the loss, transform and baseflow variants."""
        return {
            "loss": build_method(LOSS_METHODS, values["loss_rate"], cursor),
            "transform": build_method(TRANSFORM_METHODS, values["transform_method"], cursor),
            "baseflow": build_method(BASEFLOW_METHODS, values["baseflow_method"], cursor),
        }


class Reach(Element):
    """A reach with its routing variant."""

    route_method: str | None = hms("Route")
    route: SerializeAsAny[Method] | None = None

    @classmethod
    def extra_values(cls, cursor: Cursor, values: dict[str, Any]) -> dict[str, Any]:
        """Build the routing variant."""
        return {"route": build_method(ROUTE_METHODS, values["route_method"], cursor)}


class Junction(Element):
    """A junction; the dam sites of Block 2 are junctions with no downstream."""


class Sink(Element):
    """A sink."""


class Source(Element):
    """A source; its keys are not seen in any project on this machine, so they arrive in ``unknown``."""


class Diversion(Element):
    """A diversion; ``divert_to`` names the element that receives the diverted flow."""

    divert_to: str | None = hms("Divert To")


class Reservoir(Element):
    """A reservoir; ``Spillway``, ``Conduit`` and ``Pump`` sub-blocks stay raw in file order."""

    route_method: str | None = hms("Route")
    route: SerializeAsAny[Method] | None = None

    @classmethod
    def extra_values(cls, cursor: Cursor, values: dict[str, Any]) -> dict[str, Any]:
        """Build the routing variant."""
        return {"route": build_method(RESERVOIR_ROUTE_METHODS, values["route_method"], cursor)}

    def outlets_of(self, kind: str) -> list[RawBlock]:
        """The outlet sub-blocks of one kind (``Spillway``, ``Conduit``, ``Pump``)."""
        return [block for block in self.blocks if block.kind == kind]


class BasinHeader(BlockModel):
    """The ``Basin:`` block; ``unit_system`` tells the units of every value in the file."""

    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")
    description: str | None = hms("Description")
    version: str | None = hms("Version")
    filepath_separator: str | None = hms("Filepath Separator")
    unit_system: str | None = hms("Unit System")
    missing_flow_to_zero: str | None = hms("Missing Flow To Zero")
    enable_flow_ratio: str | None = hms("Enable Flow Ratio")
    compute_local_flow_at_junctions: str | None = hms("Compute Local Flow At Junctions")
    unregulated_output_required: str | None = hms("Unregulated Output Required")
    enable_sediment_routing: str | None = hms("Enable Sediment Routing")


class BreakPoint(HmsModel):
    """A subbasin break point of the delineation."""

    number: str
    x: float | None = None
    y: float | None = None


class BasinSpatial(BlockModel):
    """The ``Basin Spatial Properties`` block."""

    coordinate_system: str | None = hms("Coordinate System")
    terrain: str | None = hms("Terrain")
    reach_prefix: str | None = hms("reach_prefix")
    junction_insert: str | None = hms("junction_insert")
    junction_prefix: str | None = hms("junction_prefix")
    subbasin_prefix: str | None = hms("subbasin_prefix")

    @property
    def break_points(self) -> list[BreakPoint]:
        """The break points in file order."""

        def number(block: RawBlock, key: str) -> float | None:
            value = block.get(key)
            return None if value is None else float(value)

        return [
            BreakPoint(number=b.name, x=number(b, "X Coordinate"), y=number(b, "Y Coordinate"))
            for b in self.blocks
            if b.kind == BREAK_POINT_KIND
        ]


ELEMENT_MODELS: dict[str, type[Element]] = {
    "Subbasin": Subbasin,
    "Reach": Reach,
    "Junction": Junction,
    "Sink": Sink,
    "Source": Source,
    "Reservoir": Reservoir,
    "Diversion": Diversion,
}

ElementT = TypeVar("ElementT", bound=Element)


@dataclass(frozen=True)
class Connectivity:
    """The network: ``downstream[e]`` (None at a terminal), ``upstream[e]`` in file order, ``outlets``,
    and ``dangling`` as (element, target) pairs whose target is not in the basin."""

    downstream: dict[str, str | None]
    upstream: dict[str, list[str]]
    outlets: list[str]
    dangling: list[tuple[str, str]]


class Basin(HmsModel):
    """A basin model: header, spatial block, elements in file order, everything else raw."""

    header: BasinHeader
    spatial: BasinSpatial | None = None
    elements: list[SerializeAsAny[Element]] = Field(default_factory=list)
    other_blocks: list[RawBlock] = Field(default_factory=list)

    def _of(self, model: type[ElementT]) -> dict[str, ElementT]:
        return {e.name: e for e in self.elements if isinstance(e, model)}

    @property
    def name(self) -> str:
        """The basin model name."""
        return self.header.name

    @property
    def unit_system(self) -> str | None:
        """``Metric`` or ``English``."""
        return self.header.unit_system

    @property
    def subbasins(self) -> dict[str, Subbasin]:
        """Subbasins by name, in file order."""
        return self._of(Subbasin)

    @property
    def reaches(self) -> dict[str, Reach]:
        """Reaches by name, in file order."""
        return self._of(Reach)

    @property
    def junctions(self) -> dict[str, Junction]:
        """Junctions by name, in file order."""
        return self._of(Junction)

    @property
    def sinks(self) -> dict[str, Sink]:
        """Sinks by name, in file order."""
        return self._of(Sink)

    @property
    def sources(self) -> dict[str, Source]:
        """Sources by name, in file order."""
        return self._of(Source)

    @property
    def reservoirs(self) -> dict[str, Reservoir]:
        """Reservoirs by name, in file order."""
        return self._of(Reservoir)

    @property
    def diversions(self) -> dict[str, Diversion]:
        """Diversions by name, in file order."""
        return self._of(Diversion)

    def connectivity(self) -> Connectivity:
        """Upstream and downstream maps and the terminal elements of the network."""
        names = {e.name for e in self.elements}
        downstream = {e.name: e.downstream or None for e in self.elements}
        upstream: dict[str, list[str]] = {name: [] for name in downstream}
        dangling: list[tuple[str, str]] = []
        for name, target in downstream.items():
            if target is None:
                continue
            if target in names:
                upstream[target].append(name)
            else:
                dangling.append((name, target))
        outlets = [name for name, target in downstream.items() if target is None]
        return Connectivity(downstream, upstream, outlets, dangling)

    def unknown_report(self) -> list[UnknownEntry]:
        """Everything in the file this reader did not recognise."""
        entries = list(self.header.unknown_report())
        entries += self.spatial.unknown_report() if self.spatial else []
        for element in self.elements:
            entries += element.unknown_report()
        for block in self.other_blocks:
            if block.kind not in DISPLAY_KINDS:
                entries.append(UnknownEntry(f"{block.kind} {block.name}".strip(), "block", block.kind))
        return entries


def from_document(document: Document) -> Basin:
    """Type a tokenized ``.basin`` file."""
    header: BasinHeader | None = None
    spatial: BasinSpatial | None = None
    elements: list[Element] = []
    other: list[RawBlock] = []
    for block in document.blocks():
        if block.kind == HEADER_KIND and header is None:
            header = BasinHeader.from_block(block)
        elif block.kind == SPATIAL_KIND:
            spatial = BasinSpatial.from_block(block)
        elif block.kind in ELEMENT_MODELS:
            elements.append(ELEMENT_MODELS[block.kind].from_block(block))
        else:
            other.append(RawBlock.from_block(block))
    if header is None:
        raise ValueError(f"no '{HEADER_KIND}:' block: not a basin file")
    return Basin(header=header, spatial=spatial, elements=elements, other_blocks=other)


def load(path: str | Path) -> Basin:
    """Read a ``.basin`` file."""
    return from_document(text.load(path))
