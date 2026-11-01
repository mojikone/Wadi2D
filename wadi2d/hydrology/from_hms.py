"""Adapters from the :mod:`wadi2d.hms` file models to the engine's objects.

Interface: :func:`basin_from_hms`, :func:`grid_from_hms`, :func:`storm_from_hms`, :func:`load_project_tables`,
:class:`ProjectTables`, :func:`find_grid_file`, :func:`grid_storm`. The engine never sees an HMS model: this module
is the whole coupling, and a selector or an option it cannot map raises instead of running something else.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path, PureWindowsPath
from typing import Any

import numpy as np

from wadi2d.hms import PairedDataFile, load_document, open_dss
from wadi2d.hms.basin import Basin as HmsBasin
from wadi2d.hms.basin import Diversion as HmsDiversion
from wadi2d.hms.basin import Junction as HmsJunction
from wadi2d.hms.basin import Reach as HmsReach
from wadi2d.hms.basin import Reservoir as HmsReservoir
from wadi2d.hms.basin import Sink as HmsSink
from wadi2d.hms.basin import Subbasin as HmsSubbasin
from wadi2d.hms.dss import DssFile, DssLookupError
from wadi2d.hms.met import HypotheticalStorm as HmsStorm
from wadi2d.hms.methods import ClarkTransform as HmsClark
from wadi2d.hms.methods import (
    LagRoute,
    MuskingumCungeRoute,
    RecessionBaseflow,
    ReservoirRoute,
    ScsLoss,
    ScsTransform,
)
from wadi2d.hms.pdata import Table
from wadi2d.hms.sqlite import subbasin_polygons
from wadi2d.hms.typed import Method, RawBlock, TimeWindowModel
from wadi2d.hydrology.baseflow import BASEFLOW_METHODS, NO_BASEFLOW, RECESSION
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.depth_area import StormAtPoint
from wadi2d.hydrology.diversion import INFLOW_DIVERSION
from wadi2d.hydrology.losses import LOSS_METHODS, NO_LOSS, SCS_CN
from wadi2d.hydrology.model import (
    Basin,
    Diversion,
    Element,
    Junction,
    Reach,
    Reservoir,
    Subbasin,
    TimeGrid,
)
from wadi2d.hydrology.reservoir import (
    AUXILIARY_OUTLET,
    MAIN_OUTLET,
    RESERVOIR_OUTFLOW_CURVE,
    RESERVOIR_OUTFLOW_STRUCTURES,
    Spillway,
)
from wadi2d.hydrology.routing import LAG, MUSKINGUM_CUNGE, NO_ROUTING, ROUTING_METHODS
from wadi2d.hydrology.transforms import CLARK_UH, SCS_UH, TRANSFORM_METHODS
from wadi2d.storm import ArfTable, HypotheticalStorm, PercentPattern, StormBySubbasin, SubbasinRain
from wadi2d.storm.grid_depth import DepthGrid

METRIC = "Metric"
TRAPEZOID = "Trapezoid"
AUTOMATIC_DX_DT = "Automatic DX and DT"
INDEX_CELERITY = "Index Celerity"
NO_CHANNEL_LOSS = "None"
SPECIFIED_PATTERN = "Specified Pattern"
PERCENT_GRAPH = "Percent Graph"
AREA_REDUCTION = "Area-Reduction Factor"
USER_REDUCTION = "User-Specified"
NO_METHOD = "None"
GRID_KIND = "Grid"
GRID_FILE_KEY = "Filename"
ELEVATION_AREA = "Elevation-Area"
STAGE_FLOW = "Stage-Flow"
INFLOW_DIVERSION_TABLE = "Inflow-Diversion"
AREA_OUTFLOW_CURVE = "Elevation-Area-Outflow"
OUTFLOW_CURVE_ROUTE = "Modified Puls"
STRUCTURES_ROUTE = "Controlled Outflow"
SPILLWAY_BLOCK = "Spillway"
EVAPORATION_BLOCK = "Evaporation Method"
BROAD_CRESTED = "Broad-Crested Spillway"
ZERO_EVAPORATION = "Zero Evaporation"
DIVERTER_BLOCK = "Diverter"
DIVERTER_TABLE_KEY = "Inflow Diversion Table Name"
SPILLWAY_OUTLETS = {"Main": MAIN_OUTLET, "Auxiliary": AUXILIARY_OUTLET}
NO_TAILWATER = "None"
ADAPTIVE_ON = "On"
ELEVATION_UNITS = "M"
AREA_UNITS = "M2"
FLOW_UNITS = "M3/S"
NO_UNIFORM_DEPTH = "No"


def _scs_loss(method: ScsLoss) -> dict[str, Any]:
    return {
        "curve_number": method.curve_number,
        "initial_abstraction_mm": method.initial_abstraction,
        "percent_impervious": method.percent_impervious or 0.0,
    }


def _scs_transform(method: ScsTransform) -> dict[str, Any]:
    return {"lag_minutes": method.lag}


def _clark_transform(method: HmsClark) -> dict[str, Any]:
    return {
        "time_of_concentration_minutes": method.time_of_concentration,
        "storage_coefficient_minutes": method.storage_coefficient,
    }


def _recession(method: RecessionBaseflow) -> dict[str, Any]:
    return {
        "recession_constant": method.recession_factor,
        "initial_m3s_km2": method.initial_flow_area_ratio,
        "threshold_ratio": method.threshold_flow_to_peak_ratio,
    }


def _muskingum_cunge(method: MuskingumCungeRoute) -> dict[str, Any]:
    supported = (
        method.channel == TRAPEZOID
        and method.space_time_method == AUTOMATIC_DX_DT
        and method.index_parameter_type == INDEX_CELERITY
        and method.channel_loss in (None, NO_CHANNEL_LOSS)
    )
    if not supported:
        raise ValueError(f"unsupported Muskingum-Cunge options: {method}")
    return {
        "length_m": method.length,
        "slope": method.energy_slope,
        "roughness": method.mannings_n,
        "bottom_width_m": method.bottom_width,
        "side_slope": method.side_slope,
        "index_celerity": method.index_celerity,
        "route_iterations": method.maximum_route_step_iterations,
        "depth_iterations": method.maximum_depth_iterations,
    }


def _lag(method: LagRoute) -> dict[str, Any]:
    return {"lag_minutes": method.lag}


def _nothing(_method: Method) -> dict[str, Any]:
    return {}


Parameters = Callable[[Any], dict[str, Any]]
LOSS_PARAMETERS: dict[str, Parameters] = {SCS_CN: _scs_loss, NO_LOSS: _nothing}
TRANSFORM_PARAMETERS: dict[str, Parameters] = {SCS_UH: _scs_transform, CLARK_UH: _clark_transform}
BASEFLOW_PARAMETERS: dict[str, Parameters] = {NO_BASEFLOW: _nothing, RECESSION: _recession}
ROUTING_PARAMETERS: dict[str, Parameters] = {
    MUSKINGUM_CUNGE: _muskingum_cunge,
    LAG: _lag,
    NO_ROUTING: _nothing,
}


def _build(registry: Any, parameters: dict[str, Parameters], method: Method | None, default: str) -> Any:
    """The engine object of an HMS method; ``default`` stands in for a missing selector."""
    selector = default if method is None else method.method
    if selector not in parameters:
        raise ValueError(f"HMS method {selector!r} has no engine implementation")
    return registry.build(selector, **parameters[selector](method))


def _subbasin(element: HmsSubbasin) -> Subbasin:
    if element.area is None:
        raise ValueError(f"subbasin {element.name} has no area")
    return Subbasin(
        name=element.name,
        downstream=element.downstream or None,
        area_km2=element.area,
        loss=_build(LOSS_METHODS, LOSS_PARAMETERS, element.loss, NO_LOSS),
        transform=_build(TRANSFORM_METHODS, TRANSFORM_PARAMETERS, element.transform, NO_METHOD),
        baseflow=_build(BASEFLOW_METHODS, BASEFLOW_PARAMETERS, element.baseflow, NO_BASEFLOW),
    )


def _reach(element: HmsReach) -> Reach:
    routing = _build(ROUTING_METHODS, ROUTING_PARAMETERS, element.route, NO_ROUTING)
    return Reach(name=element.name, downstream=element.downstream or None, routing=routing)


def _table(tables: ProjectTables | None, name: str | None, element: str) -> PairedColumns:
    """A paired table of a reservoir or a diversion; one missing raises."""
    if tables is None or name is None or name not in tables.paired:
        raise ValueError(f"{element}: paired table {name!r} is not available")
    return tables.paired[name]


def _outflow_curve(element: HmsReservoir, route: ReservoirRoute, tables: ProjectTables | None) -> Any:
    if route.routing_curve != AREA_OUTFLOW_CURVE or route.primary_table != ELEVATION_AREA:
        raise ValueError(
            f"{element.name}: outflow curve {route.routing_curve}, {route.primary_table} primary"
        )
    if element.blocks:
        raise ValueError(f"{element.name}: outlets on an outflow curve are not supported")
    area = _table(tables, route.elevation_area_table, element.name)
    outflow = _table(tables, route.elevation_outflow_table, element.name)
    return ROUTING_METHODS.build(
        RESERVOIR_OUTFLOW_CURVE,
        elevations_m=area.x,
        areas_m2=area.y,
        outflow_elevations_m=outflow.x,
        outflows_m3s=outflow.y,
        initial_elevation_m=route.initial_elevation,
    )


def _spillway(element: str, block: RawBlock) -> Spillway:
    if block.name != BROAD_CRESTED:
        raise ValueError(f"{element}: spillway {block.name!r} is not supported")
    return Spillway(
        crest_elevation_m=float(block.get("Spillway Crest Elevation") or "nan"),
        crest_length_m=float(block.get("Spillway Crest Length") or "nan"),
        coefficient=float(block.get("Spillway Coefficient") or "nan"),
        outlet=SPILLWAY_OUTLETS[block.get("Spillway Outlet") or ""],
    )


def _outflow_structures(element: HmsReservoir, route: ReservoirRoute, tables: ProjectTables | None) -> Any:
    if route.routing_curve != ELEVATION_AREA:
        raise ValueError(f"{element.name}: storage method {route.routing_curve} is not supported")
    if route.adaptive_control != ADAPTIVE_ON:
        raise ValueError(f"{element.name}: only Adaptive Control On was measured against HMS")
    tailwater = {route.main_tailwater_condition, route.auxiliary_tailwater_condition}
    if tailwater - {NO_TAILWATER, None}:
        raise ValueError(f"{element.name}: tailwater {tailwater} is not supported")
    spillways: list[Spillway] = []
    for block in element.blocks:
        if block.kind == SPILLWAY_BLOCK:
            spillways.append(_spillway(element.name, block))
        elif block.kind != EVAPORATION_BLOCK or block.name != ZERO_EVAPORATION:
            raise ValueError(f"{element.name}: outlet or option {block.kind} {block.name} is not supported")
    area = _table(tables, route.elevation_area_table, element.name)
    return ROUTING_METHODS.build(
        RESERVOIR_OUTFLOW_STRUCTURES,
        elevations_m=area.x,
        areas_m2=area.y,
        spillways=tuple(spillways),
        initial_elevation_m=route.initial_elevation,
    )


ReservoirBuilder = Callable[[HmsReservoir, ReservoirRoute, "ProjectTables | None"], Any]
RESERVOIR_ROUTES: dict[str, ReservoirBuilder] = {
    OUTFLOW_CURVE_ROUTE: _outflow_curve,
    STRUCTURES_ROUTE: _outflow_structures,
}


def _reservoir(element: HmsReservoir, tables: ProjectTables | None) -> Reservoir:
    route = element.route
    if not isinstance(route, ReservoirRoute) or route.method not in RESERVOIR_ROUTES:
        raise ValueError(f"reservoir {element.name}: HMS method {route} has no engine implementation")
    if element.unknown:
        raise ValueError(f"reservoir {element.name}: options not read: {[f.key for f in element.unknown]}")
    if route.initial_elevation is None:
        raise ValueError(f"reservoir {element.name}: only an initial elevation is supported")
    builder = RESERVOIR_ROUTES[route.method]
    return Reservoir(
        name=element.name,
        downstream=element.downstream or None,
        routing=builder(element, route, tables),
        branch=route.auxiliary_flow_to or None,
    )


def _diversion(element: HmsDiversion, tables: ProjectTables | None) -> Diversion:
    diverters = [block for block in element.blocks if block.kind == DIVERTER_BLOCK]
    if len(diverters) != 1 or diverters[0].name != INFLOW_DIVERSION or len(element.blocks) != 1:
        raise ValueError(f"diversion {element.name}: only one {INFLOW_DIVERSION} is supported")
    table = _table(tables, diverters[0].get(DIVERTER_TABLE_KEY), element.name)
    return Diversion(
        name=element.name,
        downstream=element.downstream or None,
        routing=ROUTING_METHODS.build(INFLOW_DIVERSION, inflows_m3s=table.x, diverted_m3s=table.y),
        branch=element.divert_to,
    )


def basin_from_hms(basin: HmsBasin, tables: ProjectTables | None = None) -> Basin:
    """The engine's basin of an HMS basin model; metric only, as nothing here converts units.

    ``tables`` holds the paired data of reservoirs and diversions; a model with neither needs none.
    """
    if basin.unit_system != METRIC:
        raise ValueError(f"unit system {basin.unit_system!r}: only {METRIC} basin models are read")
    elements: list[Element] = []
    for element in basin.elements:
        if isinstance(element, HmsSubbasin):
            elements.append(_subbasin(element))
        elif isinstance(element, HmsReach):
            elements.append(_reach(element))
        elif isinstance(element, HmsJunction | HmsSink):
            elements.append(Junction(name=element.name, downstream=element.downstream or None))
        elif isinstance(element, HmsReservoir):
            elements.append(_reservoir(element, tables))
        elif isinstance(element, HmsDiversion):
            elements.append(_diversion(element, tables))
        else:
            raise ValueError(f"element {element.name} of type {type(element).__name__} is not supported")
    return Basin(basin.name, elements)


def grid_from_hms(window: TimeWindowModel) -> TimeGrid:
    """The time grid of a control specification or a depth-area analysis."""
    if window.time_interval is None or window.start is None or window.end is None:
        raise ValueError(f"{window.name} has no complete time window")
    span = (window.end - window.start).total_seconds() / SECONDS_PER_MINUTE
    return TimeGrid(window.time_interval, round(span / window.time_interval))


@dataclass(frozen=True, eq=False)
class PairedColumns:
    """The two columns of a reservoir or diversion table, in SI."""

    x: np.ndarray
    y: np.ndarray


@dataclass(frozen=True)
class ProjectTables:
    """The paired tables of a project, by table name: storms in the first two, the network in ``paired``."""

    patterns: dict[str, PercentPattern]
    area_reductions: dict[str, ArfTable]
    paired: dict[str, PairedColumns] = field(default_factory=dict)


def _read_si(dss: DssFile, table: Table, units: dict[str, tuple[str, str]]) -> PairedColumns | None:
    """A network table in the units nothing here has to convert; another unit or a missing record leaves it out."""
    expected = units[table.table_type or ""]
    if table.pathname is None or (table.x_units, table.y_units) != expected:
        return None
    try:
        record = dss.read_paired(table.pathname)
    except DssLookupError:
        return None
    return PairedColumns(np.asarray(record.x), np.asarray(record.y))


def load_project_tables(pdata: PairedDataFile, project_dss: str | Path) -> ProjectTables:
    """Read the paired tables from the project DSS file; an ARF table follows HMS below its smallest area."""
    patterns: dict[str, PercentPattern] = {}
    reductions: dict[str, ArfTable] = {}
    paired: dict[str, PairedColumns] = {}
    units = {
        ELEVATION_AREA: (ELEVATION_UNITS, AREA_UNITS),
        STAGE_FLOW: (ELEVATION_UNITS, FLOW_UNITS),
        INFLOW_DIVERSION_TABLE: (FLOW_UNITS, FLOW_UNITS),
    }
    with open_dss(project_dss) as dss:
        for name, table in pdata.of_type(PERCENT_GRAPH).items():
            if table.pathname is not None:
                record = dss.read_paired(table.pathname)
                patterns[name] = PercentPattern(record.x, record.y)
        for name, table in pdata.of_type(AREA_REDUCTION).items():
            if table.pathname is not None:
                record = dss.read_paired(table.pathname)
                reductions[name] = ArfTable(record.x, record.y, reduces_below_table=False)
        for kind in units:
            for name, table in pdata.of_type(kind).items():
                columns = _read_si(dss, table, units)
                if columns is not None:
                    paired[name] = columns
    return ProjectTables(patterns, reductions, paired)


def storm_from_hms(
    storm: HmsStorm, tables: ProjectTables, depth_mm: float | None = None
) -> HypotheticalStorm:
    """The engine's storm. ``depth_mm`` replaces the point depth, for a grid-depth storm that has none."""
    if storm.storm_type != SPECIFIED_PATTERN or storm.pattern_name is None or storm.storm_duration is None:
        raise ValueError(f"only a specified pattern is supported: {storm}")
    depth = depth_mm if depth_mm is not None else storm.storm_depth
    if depth is None:
        raise ValueError("a precipitation-frequency grid storm needs its depth from the grid")
    if storm.uniform_depth == NO_UNIFORM_DEPTH and depth_mm is None:
        raise ValueError("a point depth by subbasin is not supported")
    method = storm.depth_area_reduction_method
    if method not in (USER_REDUCTION, NO_METHOD, None):
        raise ValueError(f"area reduction {method!r} is not supported")
    uses_table = method == USER_REDUCTION and storm.reduction_table_name is not None
    return HypotheticalStorm(
        depth_mm=depth,
        pattern=tables.patterns[storm.pattern_name],
        duration_hours=storm.storm_duration,
        storm_area_km2=storm.storm_area,
        arf=tables.area_reductions[storm.reduction_table_name] if uses_table else None,
    )


def find_grid_file(grid_manager: str | Path, grid_name: str, roots: Iterable[Path]) -> Path:
    """The raster of a grid named in a ``.grid`` file; its path is relative to one of ``roots``."""
    block = load_document(grid_manager).block(GRID_KIND, grid_name)
    relative = None if block is None else block.get(GRID_FILE_KEY)
    if relative is None:
        raise KeyError(f"no file for grid {grid_name}")
    parts = PureWindowsPath(relative).parts
    for root in roots:
        candidate = root.joinpath(*parts)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(relative)


def grid_storm(
    storm: HypotheticalStorm,
    depths: DepthGrid,
    basin: Basin,
    sqlite: str | Path,
    by_subbasin: bool = False,
) -> StormAtPoint:
    """The storm of a precipitation-frequency grid.

    Its depth is the grid mean above each analysis point (`Uniform Depth: Yes`), or the grid mean over each
    subbasin on its own (``by_subbasin``, `Uniform Depth: No`).
    """
    cells = {polygon.name: depths.cells_in(polygon.shape()) for polygon in subbasin_polygons(sqlite)}
    if by_subbasin:
        means = {name: depths.mean_of([cells[name]]) for name in basin.subbasins}
        rain = StormBySubbasin(storm, means)
        return lambda _point, area_km2: rain.at_area(area_km2)

    def at_point(point: str, area_km2: float) -> SubbasinRain:
        upstream = basin.upstream_of(point)
        depth = depths.mean_of(indices for name, indices in cells.items() if name in upstream)
        return replace(storm, depth_mm=depth).at_area(area_km2)

    return at_point
