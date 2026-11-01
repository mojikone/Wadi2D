"""Method variants of subbasins and reaches, keyed by the value of their selector key.

Each registry maps a selector value to a model whose aliases are that method's HMS keys. Adding a method is
one class and one registry line. A selector value with no entry becomes :class:`UnknownMethod`, and its keys
stay in the element's ``unknown``. Keys are the ones HMS 4.12 writes (research note H04, finding 6); a key
misnamed here for a method Block 2 does not use is reported, not lost.
"""

from __future__ import annotations

from wadi2d.hms.typed import Cursor, Method, UnknownMethod, hms

NO_METHOD = "None"


class NoMethod(Method):
    """The selector says ``None``."""


class ScsLoss(Method):
    """``LossRate: SCS``. ``initial_abstraction`` is a depth in the file's units, not a ratio."""

    percent_impervious: float | None = hms("Percent Impervious Area")
    curve_number: float | None = hms("Curve Number")
    initial_abstraction: float | None = hms("Initial Abstraction")


class InitialConstantLoss(Method):
    """``LossRate: Initial+Constant``."""

    percent_impervious: float | None = hms("Percent Impervious Area")
    initial_loss: float | None = hms("Initial Loss")
    constant_loss_rate: float | None = hms("Constant Loss Rate")


class DeficitConstantLoss(Method):
    """``LossRate: Deficit Constant``."""

    percent_impervious: float | None = hms("Percent Impervious Area")
    initial_deficit: float | None = hms("Initial Deficit")
    maximum_deficit: float | None = hms("Maximum Deficit")
    percolation_rate: float | None = hms("Percolation Rate")
    recovery_factor: float | None = hms("Recovery Factor")


class SoilMoistureAccountLoss(Method):
    """``LossRate: Soil Moisture Account``."""

    percent_impervious: float | None = hms("Percent Impervious Area")
    initial_soil_storage: float | None = hms("Initial Soil Storage Percent")
    soil_maximum_infiltration: float | None = hms("Soil Maximum Infiltration")
    soil_storage_capacity: float | None = hms("Soil Storage Capacity")
    soil_tension_capacity: float | None = hms("Soil Tension Capacity")
    soil_maximum_percolation: float | None = hms("Soil Maximum Percolation")


class ScsTransform(Method):
    """``Transform: SCS``; ``lag`` in minutes."""

    lag: float | None = hms("Lag")
    unitgraph_type: str | None = hms("Unitgraph Type")


class SnyderTransform(Method):
    """``Transform: Snyder``."""

    snyder_method: str | None = hms("Snyder Method")
    snyder_tp: float | None = hms("Snyder Tp")
    snyder_cp: float | None = hms("Snyder Cp")


class ClarkTransform(Method):
    """``Transform: Clark``."""

    clark_method: str | None = hms("Clark Method")
    time_of_concentration: float | None = hms("Time of Concentration")
    storage_coefficient: float | None = hms("Storage Coefficient")
    time_area_method: str | None = hms("Time Area Method")


class ModifiedClarkTransform(Method):
    """``Transform: Modified Clark``."""

    mod_clark_method: str | None = hms("Mod Clark Method")
    time_of_concentration: float | None = hms("Time of Concentration")
    storage_coefficient: float | None = hms("Storage Coefficient")


class RecessionBaseflow(Method):
    """``Baseflow: Recession``."""

    recession_factor: float | None = hms("Recession Factor")
    initial_flow_area_ratio: float | None = hms("Initial Flow/Area Ratio")
    initial_baseflow: float | None = hms("Initial Baseflow")
    threshold_flow_to_peak_ratio: float | None = hms("Threshold Flow to Peak Ratio")


class LinearReservoirBaseflow(Method):
    """``Baseflow: Linear Reservoir``."""

    groundwater_layer: str | None = hms("Groundwater Layer")


class MuskingumCungeRoute(Method):
    """``Route: Muskingum Cunge``."""

    channel: str | None = hms("Channel")
    length: float | None = hms("Length")
    energy_slope: float | None = hms("Energy Slope")
    mannings_n: float | None = hms("Mannings n")
    bottom_width: float | None = hms("Bottom Width")
    side_slope: float | None = hms("Side Slope")
    initial_variable: str | None = hms("Initial Variable")
    space_time_method: str | None = hms("Space-Time Method")
    index_parameter_type: str | None = hms("Index Parameter Type")
    index_celerity: float | None = hms("Index Celerity")
    number_subreaches: int | None = hms("Number Subreaches")
    maximum_depth_iterations: int | None = hms("Maximum Depth Iterations")
    maximum_route_step_iterations: int | None = hms("Maximum Route Step Iterations")
    channel_loss: str | None = hms("Channel Loss")


class MuskingumRoute(Method):
    """``Route: Muskingum``."""

    muskingum_k: float | None = hms("Muskingum K")
    muskingum_x: float | None = hms("Muskingum x")
    muskingum_steps: int | None = hms("Muskingum Steps")
    initial_variable: str | None = hms("Initial Variable")
    channel_loss: str | None = hms("Channel Loss")


class LagRoute(Method):
    """``Route: Lag``; ``lag`` in minutes."""

    lag: float | None = hms("Lag")
    initial_variable: str | None = hms("Initial Variable")
    channel_loss: str | None = hms("Channel Loss")


class ModifiedPulsRoute(Method):
    """``Route: Modified Puls`` on a reach."""

    number_of_reaches: int | None = hms("Number of Reaches")
    storage_outflow_table: str | None = hms("Storage Outflow Table Name")
    initial_variable: str | None = hms("Initial Variable")
    channel_loss: str | None = hms("Channel Loss")


class ReservoirRoute(Method):
    """``Route`` of a reservoir (``Controlled Outflow``, ``Modified Puls``); outlets are sub-blocks."""

    routing_curve: str | None = hms("Routing Curve")
    initial_elevation: float | None = hms("Initial Elevation")
    elevation_storage_table: str | None = hms("Elevation-Storage Table")
    elevation_area_table: str | None = hms("Elevation-Area Table")
    elevation_outflow_table: str | None = hms("Elevation-Outflow Table")
    primary_table: str | None = hms("Primary Table")
    adaptive_control: str | None = hms("Adaptive Control")
    main_tailwater_condition: str | None = hms("Main Tailwater Condition")
    auxiliary_tailwater_condition: str | None = hms("Auxiliary Tailwater Condition")
    auxiliary_flow_to: str | None = hms("Auxiliary Flow To")


Registry = dict[str, type[Method]]

LOSS_METHODS: Registry = {
    NO_METHOD: NoMethod,
    "SCS": ScsLoss,
    "Initial+Constant": InitialConstantLoss,
    "Deficit Constant": DeficitConstantLoss,
    "Soil Moisture Account": SoilMoistureAccountLoss,
}
TRANSFORM_METHODS: Registry = {
    NO_METHOD: NoMethod,
    "SCS": ScsTransform,
    "Snyder": SnyderTransform,
    "Clark": ClarkTransform,
    "Modified Clark": ModifiedClarkTransform,
}
BASEFLOW_METHODS: Registry = {
    NO_METHOD: NoMethod,
    "Recession": RecessionBaseflow,
    "Linear Reservoir": LinearReservoirBaseflow,
}
ROUTE_METHODS: Registry = {
    NO_METHOD: NoMethod,
    "Muskingum Cunge": MuskingumCungeRoute,
    "Muskingum": MuskingumRoute,
    "Lag": LagRoute,
    "Modified Puls": ModifiedPulsRoute,
}
RESERVOIR_ROUTE_METHODS: Registry = {
    NO_METHOD: NoMethod,
    "Controlled Outflow": ReservoirRoute,
    "Modified Puls": ReservoirRoute,
}


def build_method(registry: Registry, selector: str | None, cursor: Cursor) -> Method | None:
    """The variant a selector value names, filled from the cursor; None when the block has no selector."""
    if selector is None:
        return None
    model = registry.get(selector)
    if model is None:
        return UnknownMethod(method=selector)
    return model(method=selector, **cursor.fill(model))
