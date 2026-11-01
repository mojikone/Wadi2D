"""Adapters from the :mod:`wadi2d.hms` file models to the engine's objects.

Interface: :func:`basin_from_hms`, :func:`grid_from_hms`, :func:`storm_from_hms`, :func:`load_project_tables`,
:class:`ProjectTables`, :func:`find_grid_file`, :func:`grid_storm`. The engine never sees an HMS model: this module is the whole coupling, and a selector it
cannot map raises instead of running something else.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path, PureWindowsPath
from typing import Any

from wadi2d.hms import PairedDataFile, load_document, open_dss
from wadi2d.hms.basin import Basin as HmsBasin
from wadi2d.hms.basin import Junction as HmsJunction
from wadi2d.hms.basin import Reach as HmsReach
from wadi2d.hms.basin import Subbasin as HmsSubbasin
from wadi2d.hms.met import HypotheticalStorm as HmsStorm
from wadi2d.hms.methods import ClarkTransform as HmsClark
from wadi2d.hms.methods import LagRoute, MuskingumCungeRoute, RecessionBaseflow, ScsLoss, ScsTransform
from wadi2d.hms.sqlite import subbasin_polygons
from wadi2d.hms.typed import Method, TimeWindowModel
from wadi2d.hydrology.baseflow import BASEFLOW_METHODS, NO_BASEFLOW, RECESSION
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.depth_area import StormAtPoint
from wadi2d.hydrology.losses import LOSS_METHODS, NO_LOSS, SCS_CN
from wadi2d.hydrology.model import Basin, Element, Junction, Reach, Subbasin, TimeGrid
from wadi2d.hydrology.routing import LAG, MUSKINGUM_CUNGE, NO_ROUTING, ROUTING_METHODS
from wadi2d.hydrology.transforms import CLARK_UH, SCS_UH, TRANSFORM_METHODS
from wadi2d.storm import ArfTable, HypotheticalStorm, PercentPattern, Storm
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


def basin_from_hms(basin: HmsBasin) -> Basin:
    """The engine's basin of an HMS basin model; metric only, as nothing here converts units."""
    if basin.unit_system != METRIC:
        raise ValueError(f"unit system {basin.unit_system!r}: only {METRIC} basin models are read")
    elements: list[Element] = []
    for element in basin.elements:
        if isinstance(element, HmsSubbasin):
            elements.append(_subbasin(element))
        elif isinstance(element, HmsReach):
            elements.append(_reach(element))
        elif isinstance(element, HmsJunction):
            elements.append(Junction(name=element.name, downstream=element.downstream or None))
        else:
            raise ValueError(f"element {element.name} of type {type(element).__name__} is not supported")
    return Basin(basin.name, elements)


def grid_from_hms(window: TimeWindowModel) -> TimeGrid:
    """The time grid of a control specification or a depth-area analysis."""
    if window.time_interval is None or window.start is None or window.end is None:
        raise ValueError(f"{window.name} has no complete time window")
    span = (window.end - window.start).total_seconds() / SECONDS_PER_MINUTE
    return TimeGrid(window.time_interval, round(span / window.time_interval))


@dataclass(frozen=True)
class ProjectTables:
    """The paired tables a project's storms refer to, by table name."""

    patterns: dict[str, PercentPattern]
    area_reductions: dict[str, ArfTable]


def load_project_tables(pdata: PairedDataFile, project_dss: str | Path) -> ProjectTables:
    """Read the percent graphs and area-reduction tables from the project DSS file."""
    patterns: dict[str, PercentPattern] = {}
    reductions: dict[str, ArfTable] = {}
    with open_dss(project_dss) as dss:
        for name, table in pdata.of_type(PERCENT_GRAPH).items():
            if table.pathname is not None:
                record = dss.read_paired(table.pathname)
                patterns[name] = PercentPattern(record.x, record.y)
        for name, table in pdata.of_type(AREA_REDUCTION).items():
            if table.pathname is not None:
                record = dss.read_paired(table.pathname)
                reductions[name] = ArfTable(record.x, record.y)
    return ProjectTables(patterns, reductions)


def storm_from_hms(
    storm: HmsStorm, tables: ProjectTables, depth_mm: float | None = None
) -> HypotheticalStorm:
    """The engine's storm. ``depth_mm`` replaces the point depth, for a grid-depth storm that has none."""
    if storm.storm_type != SPECIFIED_PATTERN or storm.pattern_name is None or storm.storm_duration is None:
        raise ValueError(f"only a specified pattern is supported: {storm}")
    depth = depth_mm if depth_mm is not None else storm.storm_depth
    if depth is None:
        raise ValueError("a precipitation-frequency grid storm needs its depth from the grid")
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


def grid_storm(storm: HypotheticalStorm, depths: DepthGrid, basin: Basin, sqlite: str | Path) -> StormAtPoint:
    """The storm of a precipitation-frequency grid: its depth is the grid mean above each analysis point."""
    shapes = {polygon.name: polygon.shape() for polygon in subbasin_polygons(sqlite)}

    def at_point(point: str, area_km2: float) -> Storm:
        upstream = basin.upstream_of(point)
        depth = depths.mean_over(shape for name, shape in shapes.items() if name in upstream)
        return replace(storm, depth_mm=depth).at_area(area_km2)

    return at_point
