"""Adapters from the :mod:`wadi2d.hms` file models to the engine's objects.

Interface: :func:`basin_from_hms`, :func:`grid_from_hms`, :func:`storm_from_hms`, :func:`load_project_tables`,
:class:`ProjectTables`, :func:`find_grid_file`, :func:`grid_storm`. The engine never sees an HMS model: this module
is the whole coupling, and a selector or an option it cannot map raises instead of running something else.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any

import numpy as np

from wadi2d.config.schema import REACH_HMS
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
from wadi2d.hydrology.diversion import (
    CONSTANT_DIVERSION,
    INFLOW_DIVERSION,
    LATERAL_WEIR_DIVERSION,
    PUMP_STATION_DIVERSION,
    SPECIFIED_DIVERSION,
    ChannelRating,
    DiversionLimits,
)
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
from wadi2d.hydrology.routing import LAG, MUSKINGUM_CUNGE, NO_ROUTING, ROUTING_METHODS, MuskingumCunge
from wadi2d.hydrology.structures import (
    CULVERT,
    HEAD_DISCHARGE_PUMP,
    LEVEL_DAM_TOP,
    ORIFICE,
    RADIAL_GATE,
    RATING_SPILLWAY,
    SLUICE_GATE,
    STRUCTURE_KINDS,
    TABULAR_SEEPAGE,
    Culvert,
    MonthlyEvaporation,
    SpillwayGate,
    Structure,
)
from wadi2d.hydrology.transforms import CLARK_UH, SCS_UH, TRANSFORM_METHODS
from wadi2d.storm import ArfTable, HypotheticalStorm, PercentPattern, StormBySubbasin, SubbasinRain
from wadi2d.storm.grid_depth import DepthGrid, centroid_of

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
FIXED_STAGE = "Fixed Stage"
ADAPTIVE_ON = "On"
ELEVATION_UNITS = "M"
AREA_UNITS = "M2"
FLOW_UNITS = "M3/S"
ELEVATION_STORAGE = "Elevation-Storage"
STORAGE_UNITS = "THOU M3"  # HMS 4.12 refuses "1000 M3" on a paired table (W59)
THOUSAND = 1000.0
# Reservoir structure blocks and keys, each one written back by HEC-HMS 4.12 on re-saving W59's test basins.
CONDUIT_BLOCK = "Conduit"
DAM_TOP_BLOCK = "Dam Top"
SEEPAGE_BLOCK = "Dam Seepage"
MONTHLY_EVAPORATION = "Monthly Evaporation"
EVAPORATION_RATE_KEY = "Evaporation Rate"
SPILLWAY_OUTLET_KEY = "Spillway Outlet"
CONDUIT_OUTLET_KEY = "Conduit Outlet"
DAM_TOP_OUTLET_KEY = "Dam Top Outlet"
SEEPAGE_OUTLET_KEY = "Dam Seepage Outlet"
RATING_TABLE_KEY = "Spillway Rating Curve Name"
SEEPAGE_OUT_KEY = "Pool-To-Tailwater Table Name"
SEEPAGE_IN_KEY = "Tailwater-To-Pool Table Name"
RATING_SPILLWAY_KEYS = frozenset({SPILLWAY_OUTLET_KEY, RATING_TABLE_KEY})
ORIFICE_KEYS = frozenset(
    {CONDUIT_OUTLET_KEY, "Number Barrels", "Centerline Elevation", "Orifice Area", "Orifice Coefficient"}
)
LEVEL_DAM_KEYS = frozenset({DAM_TOP_OUTLET_KEY, "Top Elevation", "Top Length", "Overflow Coefficient"})
SEEPAGE_KEYS = frozenset({SEEPAGE_OUTLET_KEY, SEEPAGE_OUT_KEY, SEEPAGE_IN_KEY})
# W62's, each written back by HEC-HMS 4.12 on re-saving its test basins.
BROAD_KEYS = frozenset(
    {SPILLWAY_OUTLET_KEY, "Spillway Crest Elevation", "Spillway Crest Length", "Spillway Coefficient"}
)
GATE_BLOCK = "Spillway Gate"
GATE_CONTROL_BLOCK = "Gate Control"
FIXED_OPENING = "Fixed Opening"
GATE_OPENING_KEY = "Gate Opening"
# W76's, written back by HEC-HMS 4.12 on re-saving its test basins; the names are hms.jar's (hydraulics enum I).
PERCENT_TIME_SERIES = "Percent Time Series"
MAXIMUM_OPENING_KEY = "Maximum Gate Opening"
PERCENT_GAGE_KEY = "Percent Gage Name"
PERCENT_TIME_SERIES_KEYS = frozenset({MAXIMUM_OPENING_KEY, PERCENT_GAGE_KEY})
UNIDENTIFIED_GATE_CONTROLS = {
    "Percent Annual Pattern": "HMS reads its pattern record in a way W76 did not identify (on a pattern of 25 to "
    "100 % it opened the gate to 75.07 % throughout), so it is not routed",
    "Adjustable Gate Control": "it is driven by HMS's rule-based reservoir operations, which are not built",
}
PERCENT_GAGE_TYPE = "Percent"
PERCENT_UNITS = "%"
SLUICE_KEYS = frozenset({"Number Gates", "Gate Width", "Gate Coefficient", "Orifice Coefficient"})
RADIAL_KEYS = SLUICE_KEYS | {"Trunnion Height", "Trunnion Exponent", "Opening Exponent", "Head Exponent"}
GATE_KEYS = {SLUICE_GATE: SLUICE_KEYS, RADIAL_GATE: RADIAL_KEYS}
PUMP_BLOCK = "Pump"
PUMP_OUTLET_KEY = "Pump Outlet"
PUMP_TABLE_KEY = "Head-Discharge Table Name"
PUMP_KEYS = frozenset({
    PUMP_OUTLET_KEY, "Number Of Pumps", "Intake Elevation", "Discharge Elevation", "Switch-On Elevation",
    "Switch-Off Elevation", "Minimum Run Time", "Minimum Rest Time", PUMP_TABLE_KEY, "Equipment Head Loss",
})
# W67's, each written back by HEC-HMS 4.12 on re-saving its test basins (the box ones are also HMS's river_bend's).
CULVERT_COMMON_KEYS = frozenset({
    CONDUIT_OUTLET_KEY, "Culvert Shape", "Chart Number", "Scale Number", "Solution Control", "Number Barrels",
    "Culvert Length", "Entrance Loss Coefficient", "Exit Loss Coefficient", "Top Manning's n",
    "Inlet Invert Elevation", "Outlet Invert Elevation",
})
CULVERT_SIZE_KEYS = {"Box": ("Rise", "Span"), "Circular": ("Diameter",)}
GATE_WIDTH_TOLERANCE_M = 1.0e-6
NO_UNIFORM_DEPTH = "No"
# Diverter names and keys, each written back by HEC-HMS 4.12 on re-saving W72's test basins.
HMS_CONSTANT = "Constant"
HMS_SPECIFIED = "Specified"
HMS_PUMP = "Pump"
CONSTANT_FLOW_KEY = "Constant Flow"
FLOW_GAGE_KEY = "Flow Gage"
DIVERTER_RATING_KEY = "Diverter Rating Table Name"
TAILWATER_RATING_KEY = "Tailwater Rating Table Name"
MAX_DIVERSION_FLOW_KEY = "Maximum Diversion Flow"
MAX_DIVERSION_VOLUME_KEY = "Maximum Diversion Volume"
LIMIT_KEYS = frozenset({MAX_DIVERSION_FLOW_KEY, MAX_DIVERSION_VOLUME_KEY})
STATION_PUMP_OUTLET = "Auxiliary"
FLOW_GAGE_TYPE = "Flow"


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


def _reach(element: HmsReach, reach_routing: str) -> Reach:
    routing = _build(ROUTING_METHODS, ROUTING_PARAMETERS, element.route, NO_ROUTING)
    if isinstance(routing, MuskingumCunge):
        routing = replace(routing, scheme=reach_routing)
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
    if block.blocks:
        raise ValueError(f"{element}: a gated spillway is read by _gated_spillway")
    return Spillway(
        crest_elevation_m=float(block.get("Spillway Crest Elevation") or "nan"),
        crest_length_m=float(block.get("Spillway Crest Length") or "nan"),
        coefficient=float(block.get("Spillway Coefficient") or "nan"),
        outlet=SPILLWAY_OUTLETS[block.get("Spillway Outlet") or ""],
    )


def _fields(element: str, block: RawBlock, known: frozenset[str]) -> RawBlock:
    """The block, once every key in it is one this reader maps; another key raises by name."""
    unknown = sorted({f.key for f in block.fields} - known)
    if unknown:
        raise ValueError(f"{element}: {block.kind} {block.name!r} keys not read: {unknown}")
    return block


def _number(element: str, block: RawBlock, key: str) -> float:
    value = block.get(key)
    if value is None or value == "":
        raise ValueError(f"{element}: {block.kind} {block.name!r} has no {key}")
    return float(value)


def _outlet(element: str, block: RawBlock, key: str) -> int:
    value = block.get(key) or ""
    if value not in SPILLWAY_OUTLETS:
        raise ValueError(f"{element}: {block.kind} {block.name!r} {key} {value!r}")
    return SPILLWAY_OUTLETS[value]


def _rating_spillway(element: str, block: RawBlock, tables: ProjectTables | None) -> Structure:
    _fields(element, block, RATING_SPILLWAY_KEYS)
    table = _table(tables, block.get(RATING_TABLE_KEY), element)
    return STRUCTURE_KINDS.build(
        RATING_SPILLWAY, elevations_m=table.x, flows_m3s=table.y, outlet=_outlet(element, block, SPILLWAY_OUTLET_KEY)
    )


def _orifice(element: str, block: RawBlock, _tables: ProjectTables | None) -> Structure:
    _fields(element, block, ORIFICE_KEYS)
    barrels = _number(element, block, "Number Barrels")
    if barrels != int(barrels) or barrels < 1:
        raise ValueError(f"{element}: orifice barrels {barrels}")
    return STRUCTURE_KINDS.build(
        ORIFICE,
        centre_elevation_m=_number(element, block, "Centerline Elevation"),
        area_m2=_number(element, block, "Orifice Area"),
        coefficient=_number(element, block, "Orifice Coefficient"),
        barrels=int(barrels),
        outlet=_outlet(element, block, CONDUIT_OUTLET_KEY),
    )


def _level_dam_top(element: str, block: RawBlock, _tables: ProjectTables | None) -> Structure:
    _fields(element, block, LEVEL_DAM_KEYS)
    return STRUCTURE_KINDS.build(
        LEVEL_DAM_TOP,
        crest_elevation_m=_number(element, block, "Top Elevation"),
        crest_length_m=_number(element, block, "Top Length"),
        coefficient=_number(element, block, "Overflow Coefficient"),
        outlet=_outlet(element, block, DAM_TOP_OUTLET_KEY),
    )


def _tabular_seepage(element: str, block: RawBlock, tables: ProjectTables | None) -> Structure:
    """The pool-to-tailwater table; the tailwater-to-pool table is read for its name only, since it changed
    nothing in any W59 run, a tailwater above the pool included."""
    _fields(element, block, SEEPAGE_KEYS)
    table = _table(tables, block.get(SEEPAGE_OUT_KEY), element)
    return STRUCTURE_KINDS.build(
        TABULAR_SEEPAGE, heads_m=table.x, flows_m3s=table.y, outlet=_outlet(element, block, SEEPAGE_OUTLET_KEY)
    )


def _gate_opening(
    element: str, control: RawBlock, tables: ProjectTables | None, start: datetime | None
) -> dict[str, Any]:
    """A gate's opening: HMS's Fixed Opening, or a Percent Time Series as a schedule in minutes from the run's start
    (W76: HMS's opening at each time is the maximum times the gage's percent, linear in the gage, to round-off).
    Percent Annual Pattern and Adjustable Gate Control raise by name."""
    if control.name == FIXED_OPENING:
        _fields(element, control, frozenset({GATE_OPENING_KEY}))
        return {"opening_m": _number(element, control, GATE_OPENING_KEY)}
    if control.name == PERCENT_TIME_SERIES:
        _fields(element, control, PERCENT_TIME_SERIES_KEYS)
        gage = control.get(PERCENT_GAGE_KEY) or ""
        if tables is None or gage not in tables.percents:
            raise ValueError(f"{element}: percent gage {gage!r} is not available (a Percent gage in % INST-VAL in "
                             "the project .gage)")
        if start is None:
            raise ValueError(f"{element}: a Percent Time Series gate needs the run's start date (storm.rain_start)")
        record = tables.percents[gage]
        minutes = (np.asarray(record.times) - np.datetime64(start, "s")) / np.timedelta64(1, "m")
        maximum = _number(element, control, MAXIMUM_OPENING_KEY)
        return {
            "opening_m": maximum, "maximum_opening_m": maximum,
            "schedule_minutes": tuple(float(m) for m in minutes),
            "schedule_percent": tuple(float(p) for p in record.flows),
        }
    if control.name in UNIDENTIFIED_GATE_CONTROLS:
        raise ValueError(f"{element}: gate control {control.name!r}: {UNIDENTIFIED_GATE_CONTROLS[control.name]}")
    raise ValueError(f"{element}: gate control {control.name!r} is not supported")


def _gate(
    element: str, block: RawBlock, crest: float, weir: float, outlet: int,
    tables: ProjectTables | None = None, start: datetime | None = None,
) -> SpillwayGate:
    """One Spillway Gate block: a group of identical sluice or radial gates, its opening by :func:`_gate_opening`."""
    if block.kind != GATE_BLOCK or block.name not in GATE_KEYS:
        raise ValueError(f"{element}: spillway sub-block {block.kind} {block.name!r} is not supported")
    _fields(element, block, GATE_KEYS[block.name])
    controls = block.blocks
    if len(controls) != 1 or controls[0].kind != GATE_CONTROL_BLOCK:
        raise ValueError(f"{element}: a {block.name} gate needs one Gate Control")
    opening = _gate_opening(element, controls[0], tables, start)
    gates = _number(element, block, "Number Gates")
    if gates != int(gates) or gates < 1:
        raise ValueError(f"{element}: {gates} gates")
    radial = {}
    if block.name == RADIAL_GATE:
        radial = {
            "trunnion_height_m": _number(element, block, "Trunnion Height"),
            "trunnion_exponent": _number(element, block, "Trunnion Exponent"),
            "opening_exponent": _number(element, block, "Opening Exponent"),
            "head_exponent": _number(element, block, "Head Exponent"),
        }
    return SpillwayGate(
        kind=block.name,
        crest_elevation_m=crest,
        weir_coefficient=weir,
        gates=int(gates),
        width_m=_number(element, block, "Gate Width"),
        coefficient=_number(element, block, "Gate Coefficient"),
        outlet=outlet,
        **opening,
        **radial,
    )


def _gated_spillway(
    element: str, block: RawBlock, tables: ProjectTables | None = None, start: datetime | None = None
) -> list[Structure]:
    """A broad-crested spillway carrying gates: one structure per gate group; the crest passes nothing else.

    HMS requires the gates' widths to add up to the crest length (its error 42204), and so does this reader."""
    _fields(element, block, BROAD_KEYS)
    crest = _number(element, block, "Spillway Crest Elevation")
    weir = _number(element, block, "Spillway Coefficient")
    outlet = _outlet(element, block, SPILLWAY_OUTLET_KEY)
    gates = [_gate(element, sub, crest, weir, outlet, tables, start) for sub in block.blocks]
    length = _number(element, block, "Spillway Crest Length")
    widths = sum(gate.total_width_m for gate in gates)
    if abs(widths - length) > GATE_WIDTH_TOLERANCE_M:
        raise ValueError(f"{element}: the gates are {widths} m wide on a crest of {length} m; HMS refuses that")
    return list(gates)


def _minutes(element: str, block: RawBlock, key: str) -> float:
    """A pump's minimum run or rest time, minutes (W62: 2000 binds a pump on for 2000 min); blank is none."""
    value = block.get(key)
    return 0.0 if value in (None, "") else float(value)


def _pump(element: str, block: RawBlock, tables: ProjectTables | None) -> Structure:
    _fields(element, block, PUMP_KEYS)
    units = _number(element, block, "Number Of Pumps")
    if units != int(units) or units < 1:
        raise ValueError(f"{element}: {units} pumps")
    table = _table(tables, block.get(PUMP_TABLE_KEY), element)
    return STRUCTURE_KINDS.build(
        HEAD_DISCHARGE_PUMP,
        heads_m=table.x,
        flows_m3s=table.y,
        units=int(units),
        intake_m=_number(element, block, "Intake Elevation"),
        discharge_elevation_m=_number(element, block, "Discharge Elevation"),
        on_m=_number(element, block, "Switch-On Elevation"),
        off_m=_number(element, block, "Switch-Off Elevation"),
        head_loss_m=_number(element, block, "Equipment Head Loss"),
        run_min=_minutes(element, block, "Minimum Run Time"),
        rest_min=_minutes(element, block, "Minimum Rest Time"),
        outlet=_outlet(element, block, PUMP_OUTLET_KEY),
    )


def _culvert(element: str, block: RawBlock, _tables: ProjectTables | None) -> Structure:
    """A box or circular culvert; the reservoir hands it its tailwater and pool-table top (``_outflow_structures``)."""
    shape = block.get("Culvert Shape") or ""
    if shape not in CULVERT_SIZE_KEYS:
        raise ValueError(f"{element}: culvert shape {shape!r} is not supported, only {sorted(CULVERT_SIZE_KEYS)}")
    _fields(element, block, CULVERT_COMMON_KEYS | set(CULVERT_SIZE_KEYS[shape]))
    sizes = [_number(element, block, key) for key in CULVERT_SIZE_KEYS[shape]]
    barrels = _number(element, block, "Number Barrels")
    if barrels != int(barrels) or barrels < 1:
        raise ValueError(f"{element}: culvert barrels {barrels}")
    return STRUCTURE_KINDS.build(
        CULVERT,
        shape=shape,
        chart=int(_number(element, block, "Chart Number")),
        scale=int(_number(element, block, "Scale Number")),
        control=block.get("Solution Control") or "",
        rise_m=sizes[0],
        span_m=sizes[-1],
        barrels=int(barrels),
        length_m=_number(element, block, "Culvert Length"),
        entrance=_number(element, block, "Entrance Loss Coefficient"),
        exit=_number(element, block, "Exit Loss Coefficient"),
        n=_number(element, block, "Top Manning's n"),
        inlet_m=_number(element, block, "Inlet Invert Elevation"),
        outlet_m=_number(element, block, "Outlet Invert Elevation"),
        outlet=_outlet(element, block, CONDUIT_OUTLET_KEY),
    )


# (block kind, block name) -> builder; the keys are the ones HEC-HMS 4.12 wrote back on re-saving W59's, W62's and
# W67's test basins.
StructureBuilder = Callable[[str, RawBlock, "ProjectTables | None"], Structure]
STRUCTURE_BUILDERS: dict[tuple[str, str], StructureBuilder] = {
    (SPILLWAY_BLOCK, RATING_SPILLWAY): _rating_spillway,
    (CONDUIT_BLOCK, ORIFICE): _orifice,
    (DAM_TOP_BLOCK, LEVEL_DAM_TOP): _level_dam_top,
    (SEEPAGE_BLOCK, TABULAR_SEEPAGE): _tabular_seepage,
    (PUMP_BLOCK, HEAD_DISCHARGE_PUMP): _pump,
    (CONDUIT_BLOCK, CULVERT): _culvert,
}


def _evaporation(element: str, block: RawBlock) -> MonthlyEvaporation | None:
    if block.name == ZERO_EVAPORATION:
        return None
    if block.name != MONTHLY_EVAPORATION:
        raise ValueError(f"{element}: evaporation {block.name!r} is not supported")
    _fields(element, block, frozenset({EVAPORATION_RATE_KEY}))
    return MonthlyEvaporation(tuple(float(value) for value in block.get_all(EVAPORATION_RATE_KEY)))


def _tailwater(element: str, route: ReservoirRoute) -> float | None:
    if route.auxiliary_tailwater_condition not in (NO_TAILWATER, None):
        raise ValueError(f"{element}: auxiliary tailwater {route.auxiliary_tailwater_condition} is not supported")
    if route.main_tailwater_condition in (NO_TAILWATER, None):
        if route.main_fixed_tailwater_stage is not None:
            raise ValueError(f"{element}: a fixed tailwater stage with no Fixed Stage condition")
        return None
    if route.main_tailwater_condition != FIXED_STAGE or route.main_fixed_tailwater_stage is None:
        raise ValueError(f"{element}: main tailwater {route.main_tailwater_condition} is not supported")
    return route.main_fixed_tailwater_stage


def _outflow_structures(
    element: HmsReservoir, route: ReservoirRoute, tables: ProjectTables | None, start: datetime | None = None
) -> Any:
    if route.routing_curve not in (ELEVATION_AREA, ELEVATION_STORAGE):
        raise ValueError(f"{element.name}: storage method {route.routing_curve} is not supported")
    if route.adaptive_control != ADAPTIVE_ON:
        raise ValueError(f"{element.name}: only Adaptive Control On was measured against HMS")
    tailwater = _tailwater(element.name, route)
    spillways: list[Spillway] = []
    structures: list[Structure] = []
    evaporation: MonthlyEvaporation | None = None
    for block in element.blocks:
        if block.kind == SPILLWAY_BLOCK and block.name == BROAD_CRESTED and block.blocks:
            structures.extend(_gated_spillway(element.name, block, tables, start))
        elif block.kind == SPILLWAY_BLOCK and block.name == BROAD_CRESTED:
            spillways.append(_spillway(element.name, block))
        elif (block.kind, block.name) in STRUCTURE_BUILDERS:
            structures.append(STRUCTURE_BUILDERS[block.kind, block.name](element.name, block, tables))
        elif block.kind == EVAPORATION_BLOCK:
            evaporation = _evaporation(element.name, block)
        else:
            raise ValueError(f"{element.name}: outlet or option {block.kind} {block.name} is not supported")
    if route.routing_curve == ELEVATION_STORAGE:
        table = _table(tables, route.elevation_storage_table, element.name)
        curves = {"areas_m2": None, "storages_m3": table.y}
    else:
        table = _table(tables, route.elevation_area_table, element.name)
        curves = {"areas_m2": table.y}
    top = float(table.x[-1])
    structures = [
        replace(structure, tailwater_m=tailwater if structure.outlet == MAIN_OUTLET else None, top_m=top)
        if isinstance(structure, Culvert) else structure
        for structure in structures
    ]
    extra: dict[str, Any] = {}
    if structures:
        extra["structures"] = tuple(structures)
    if tailwater is not None:
        extra["tailwater_m"] = tailwater
    if evaporation is not None:
        extra |= {"evaporation": evaporation, "start": start}
    return ROUTING_METHODS.build(
        RESERVOIR_OUTFLOW_STRUCTURES,
        elevations_m=table.x,
        spillways=tuple(spillways),
        initial_elevation_m=route.initial_elevation,
        **curves,
        **extra,
    )


def _outflow_curve_builder(
    element: HmsReservoir, route: ReservoirRoute, tables: ProjectTables | None, start: datetime | None = None
) -> Any:
    return _outflow_curve(element, route, tables)


ReservoirBuilder = Callable[[HmsReservoir, ReservoirRoute, "ProjectTables | None", "datetime | None"], Any]
RESERVOIR_ROUTES: dict[str, ReservoirBuilder] = {
    OUTFLOW_CURVE_ROUTE: _outflow_curve_builder,
    STRUCTURES_ROUTE: _outflow_structures,
}


def reservoir_from_hms(
    element: HmsReservoir, tables: ProjectTables | None = None, start: datetime | None = None
) -> Reservoir:
    """The engine's reservoir of one HMS reservoir element; ``start`` dates the first step (monthly evaporation)."""
    return _reservoir(element, tables, start)


def _reservoir(element: HmsReservoir, tables: ProjectTables | None, start: datetime | None = None) -> Reservoir:
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
        routing=builder(element, route, tables, start),
        branch=route.auxiliary_flow_to or None,
    )


def _limits(element: str, block: RawBlock) -> DiversionLimits:
    """The diverter's maximum flow, m3/s, and maximum volume, which HMS's metric file holds in 1000 m3 (W72)."""
    flow = block.get(MAX_DIVERSION_FLOW_KEY)
    volume = block.get(MAX_DIVERSION_VOLUME_KEY)
    return DiversionLimits(
        max_flow_m3s=float(flow) if flow else None,
        max_volume_m3=float(volume) * THOUSAND if volume else None,
    )


def _rating(element: str, block: RawBlock, key: str, tables: ProjectTables | None) -> ChannelRating | None:
    """A Stage-Flow table named by ``key`` as a rating, stage on x; None when the key is blank."""
    name = block.get(key)
    if not name:
        return None
    table = _table(tables, name, element)
    return ChannelRating(stages_m=table.x, flows_m3s=table.y)


def _inflow_function(element: str, block: RawBlock, tables: ProjectTables | None, _ctx: DiversionContext) -> dict:
    table = _table(tables, block.get(DIVERTER_TABLE_KEY), element)
    return {"method": INFLOW_DIVERSION, "inflows_m3s": table.x, "diverted_m3s": table.y}


def _constant_flow(element: str, block: RawBlock, _tables: ProjectTables | None, _ctx: DiversionContext) -> dict:
    return {"method": CONSTANT_DIVERSION, "rate_m3s": _number(element, block, CONSTANT_FLOW_KEY)}


def _specified_flow(element: str, block: RawBlock, tables: ProjectTables | None, ctx: DiversionContext) -> dict:
    gage = block.get(FLOW_GAGE_KEY) or ""
    if tables is None or gage not in tables.flows:
        raise ValueError(f"{element}: flow gage {gage!r} is not available (a Flow gage in M3/S in the project .gage)")
    if ctx.start is None:
        raise ValueError(f"{element}: a Specified Flow diversion needs the run's start date (storm.rain_start)")
    record = tables.flows[gage]
    return {
        "method": SPECIFIED_DIVERSION, "start": np.datetime64(ctx.start, "s"), "times": record.times,
        "flows_m3s": record.flows, "gage": gage,
    }


def _lateral_weir(element: str, block: RawBlock, tables: ProjectTables | None, _ctx: DiversionContext) -> dict:
    return {
        "method": LATERAL_WEIR_DIVERSION,
        "channel": _rating(element, block, DIVERTER_RATING_KEY, tables) or _table(tables, None, element),
        "crest_m": _number(element, block, "Weir Elevation"),
        "length_m": _number(element, block, "Weir Length"),
        "coefficient": _number(element, block, "Weir Coefficient"),
        "tailwater": _rating(element, block, TAILWATER_RATING_KEY, tables),
    }


def _pump_station(element: str, block: RawBlock, tables: ProjectTables | None, _ctx: DiversionContext) -> dict:
    """W72 measured one pump group with no run or rest time and no tailwater; anything else raises."""
    if block.get(TAILWATER_RATING_KEY):
        raise ValueError(f"{element}: a pump station's tailwater rating is not measured against HMS")
    pumps = block.blocks
    if len(pumps) != 1 or (pumps[0].kind, pumps[0].name) != (PUMP_BLOCK, HEAD_DISCHARGE_PUMP):
        raise ValueError(f"{element}: a pump station needs one {PUMP_BLOCK}: {HEAD_DISCHARGE_PUMP}")
    pump = _fields(element, pumps[0], PUMP_KEYS)
    if (pump.get(PUMP_OUTLET_KEY) or STATION_PUMP_OUTLET) != STATION_PUMP_OUTLET:
        raise ValueError(f"{element}: a station pump's outlet is {STATION_PUMP_OUTLET} (HMS writes it so)")
    if _minutes(element, pump, "Minimum Run Time") or _minutes(element, pump, "Minimum Rest Time"):
        raise ValueError(f"{element}: a pump station's minimum run or rest time is not measured against HMS")
    units = _number(element, pump, "Number Of Pumps")
    if units != int(units) or units < 1:
        raise ValueError(f"{element}: {units} pumps")
    table = _table(tables, pump.get(PUMP_TABLE_KEY), element)
    return {
        "method": PUMP_STATION_DIVERSION,
        "channel": _rating(element, block, DIVERTER_RATING_KEY, tables) or _table(tables, None, element),
        "heads_m": table.x,
        "flows_m3s": table.y,
        "units": int(units),
        "on_m": _number(element, pump, "Switch-On Elevation"),
        "off_m": _number(element, pump, "Switch-Off Elevation"),
        "lift_m": _number(element, pump, "Discharge Elevation") + _number(element, pump, "Equipment Head Loss"),
    }


@dataclass(frozen=True)
class DiversionContext:
    """What a diverter may need besides its block and the tables: the date of the run's first ordinate."""

    start: datetime | None = None


DiverterBuilder = Callable[[str, RawBlock, "ProjectTables | None", DiversionContext], dict]
# HMS's internal name -> (builder, the keys besides the limits); each key written back by HEC-HMS 4.12 on re-saving
# W72's test basins.
DIVERTER_BUILDERS: dict[str, tuple[DiverterBuilder, frozenset[str]]] = {
    INFLOW_DIVERSION: (_inflow_function, frozenset({DIVERTER_TABLE_KEY})),
    HMS_CONSTANT: (_constant_flow, frozenset({CONSTANT_FLOW_KEY})),
    HMS_SPECIFIED: (_specified_flow, frozenset({FLOW_GAGE_KEY})),
    LATERAL_WEIR_DIVERSION: (
        _lateral_weir,
        frozenset({"Weir Elevation", "Weir Length", "Weir Coefficient", DIVERTER_RATING_KEY, TAILWATER_RATING_KEY}),
    ),
    HMS_PUMP: (_pump_station, frozenset({DIVERTER_RATING_KEY, TAILWATER_RATING_KEY})),
}


def diversion_from_hms(
    element: HmsDiversion, tables: ProjectTables | None = None, start: datetime | None = None
) -> Diversion:
    """The engine's diversion of one HMS diversion element; ``start`` dates the first step (Specified Flow)."""
    return _diversion(element, tables, start)


def _diversion(element: HmsDiversion, tables: ProjectTables | None, start: datetime | None = None) -> Diversion:
    diverters = [block for block in element.blocks if block.kind == DIVERTER_BLOCK]
    if len(diverters) != 1 or len(element.blocks) != 1:
        raise ValueError(f"diversion {element.name}: one Diverter block is read, and nothing else")
    block = diverters[0]
    if block.name not in DIVERTER_BUILDERS:
        raise ValueError(f"diversion {element.name}: diverter {block.name!r} is not supported")
    builder, keys = DIVERTER_BUILDERS[block.name]
    _fields(element.name, block, keys | LIMIT_KEYS)
    if block.blocks and block.name != HMS_PUMP:
        raise ValueError(f"diversion {element.name}: sub-blocks of a {block.name} diverter are not read")
    parameters = builder(element.name, block, tables, DiversionContext(start))
    method = parameters.pop("method")
    return Diversion(
        name=element.name,
        downstream=element.downstream or None,
        routing=ROUTING_METHODS.build(method, limits=_limits(element.name, block), **parameters),
        branch=element.divert_to or None,
    )


def basin_from_hms(
    basin: HmsBasin,
    tables: ProjectTables | None = None,
    reach_routing: str = REACH_HMS,
    start: datetime | None = None,
) -> Basin:
    """The engine's basin of an HMS basin model; metric only, as nothing here converts units.

    ``tables`` holds the paired data of reservoirs and diversions; a model with neither needs none.
    ``reach_routing`` is the job's ``hydrology.reach_routing``, the scheme of every Muskingum-Cunge reach.
    ``start`` dates the first step; only a reservoir with monthly evaporation needs it, and refuses to route without.
    """
    if basin.unit_system != METRIC:
        raise ValueError(f"unit system {basin.unit_system!r}: only {METRIC} basin models are read")
    elements: list[Element] = []
    for element in basin.elements:
        if isinstance(element, HmsSubbasin):
            elements.append(_subbasin(element))
        elif isinstance(element, HmsReach):
            elements.append(_reach(element, reach_routing))
        elif isinstance(element, HmsJunction | HmsSink):
            elements.append(Junction(name=element.name, downstream=element.downstream or None))
        elif isinstance(element, HmsReservoir):
            elements.append(_reservoir(element, tables, start))
        elif isinstance(element, HmsDiversion):
            elements.append(_diversion(element, tables, start))
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


@dataclass(frozen=True, eq=False)
class FlowRecord:
    """A flow gage's record: DSS times, and flows in m3/s."""

    times: np.ndarray
    flows: np.ndarray


@dataclass(frozen=True)
class ProjectTables:
    """The paired tables of a project, by table name: storms in the first two, the network in ``paired``; the flow
    gages a Specified Flow diversion reads, by gage name, in ``flows``; the percent gages a Percent Time Series gate
    reads in ``percents`` (the record's values are percents)."""

    patterns: dict[str, PercentPattern]
    area_reductions: dict[str, ArfTable]
    paired: dict[str, PairedColumns] = field(default_factory=dict)
    flows: dict[str, FlowRecord] = field(default_factory=dict)
    percents: dict[str, FlowRecord] = field(default_factory=dict)


def load_flow_gages(
    gage_file: str | Path | None, kind: str = FLOW_GAGE_TYPE, units: str = FLOW_UNITS
) -> dict[str, FlowRecord]:
    """The Flow gages of a ``.gage`` file in M3/S, instantaneous, whose record is found; any other is left out.
    ``kind`` and ``units`` read another type of gage the same way (W76's Percent gages in %)."""
    from wadi2d.hms import gage as hms_gage

    found: dict[str, FlowRecord] = {}
    if gage_file is None:
        return found
    for item in hms_gage.load(gage_file):
        usable = item.kind == kind and item.units == units and item.data_type == "INST-VAL"
        if not usable or item.dss_file is None or item.pathname is None or not item.dss_file.is_file():
            continue
        parts = item.pathname.split("/")
        try:
            with open_dss(item.dss_file) as dss:
                series = dss.read_timeseries(parts[2], parts[3], parts[6] or None, e=None)
        except (DssLookupError, IndexError):
            continue
        found[item.name] = FlowRecord(series.times, series.values)
    return found


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


def load_project_tables(
    pdata: PairedDataFile, project_dss: str | Path, gage_file: str | Path | None = None
) -> ProjectTables:
    """Read the paired tables from the project DSS file; an ARF table follows HMS below its smallest area. With
    ``gage_file``, the flow gages too (:func:`load_flow_gages`)."""
    patterns: dict[str, PercentPattern] = {}
    reductions: dict[str, ArfTable] = {}
    paired: dict[str, PairedColumns] = {}
    units = {
        ELEVATION_AREA: (ELEVATION_UNITS, AREA_UNITS),
        STAGE_FLOW: (ELEVATION_UNITS, FLOW_UNITS),
        INFLOW_DIVERSION_TABLE: (FLOW_UNITS, FLOW_UNITS),
        ELEVATION_STORAGE: (ELEVATION_UNITS, STORAGE_UNITS),
    }
    scale = {ELEVATION_STORAGE: THOUSAND}
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
                    paired[name] = PairedColumns(columns.x, columns.y * scale[kind]) if kind in scale else columns
    return ProjectTables(
        patterns, reductions, paired, load_flow_gages(gage_file),
        load_flow_gages(gage_file, PERCENT_GAGE_TYPE, PERCENT_UNITS),
    )


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
    shapes = {polygon.name: polygon.shape() for polygon in subbasin_polygons(sqlite)}
    cells = {name: depths.cells_in(shape) for name, shape in shapes.items()}
    if by_subbasin:
        means = {
            name: depths.mean_of([cells[name]], centroid_of([shapes[name]])) for name in basin.subbasins
        }
        rain = StormBySubbasin(storm, means)
        return lambda _point, area_km2: rain.at_area(area_km2)

    def at_point(point: str, area_km2: float) -> SubbasinRain:
        above = basin.upstream_of(point)
        upstream = [name for name in cells if name in above]
        centroid = centroid_of(shapes[name] for name in upstream)
        depth = depths.mean_of((cells[name] for name in upstream), centroid)
        return replace(storm, depth_mm=depth).at_area(area_km2)

    return at_point
