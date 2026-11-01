"""Reservoirs, diversions and branches: hand-checkable physics, and the adapter's refusals. No project data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from wadi2d.hms import load_basin
from wadi2d.hms.basin import Basin as HmsBasin
from wadi2d.hydrology import (
    Diversion,
    InflowDiversion,
    Junction,
    LumpedEngine,
    Reach,
    Reservoir,
    ReservoirOutflowCurve,
    ReservoirOutflowStructures,
    Spillway,
    Subbasin,
    TimeGrid,
)
from wadi2d.hydrology.from_hms import PairedColumns, ProjectTables, basin_from_hms
from wadi2d.hydrology.losses import NoLoss
from wadi2d.hydrology.model import Basin
from wadi2d.hydrology.reservoir import (
    ADAPTIVE_LEVEL_CHANGE_M,
    AUXILIARY_OUTLET,
    conic_storage,
)
from wadi2d.hydrology.routing import ROUTING_METHODS, NoRouting
from wadi2d.hydrology.transforms import ScsUnitHydrograph
from wadi2d.storm import UniformStorm

STEP_MINUTES = 5.0
STEP_SECONDS = 300.0
AREA_M2 = 1.0e6
ELEVATIONS = np.linspace(0.0, 100.0, 11)
FLAT_AREAS = np.full(11, AREA_M2)
CREST_M = 10.0
LENGTH_M = 20.0
COEFFICIENT = 2.0


def flood(peak: float = 400.0, steps: int = 200) -> np.ndarray:
    """A triangular inflow, zero at both ends."""
    return np.interp(np.arange(steps + 1.0), [0.0, 40.0, 120.0, steps], [0.0, peak, 0.0, 0.0])


def weir(outlet: int = 0, crest: float = CREST_M) -> Spillway:
    return Spillway(crest, LENGTH_M, COEFFICIENT, outlet)


def pool(
    spillways: tuple[Spillway, ...], initial: float = 5.0, bisections: int = 0
) -> ReservoirOutflowStructures:
    return ReservoirOutflowStructures(ELEVATIONS, FLAT_AREAS, spillways, initial, bisections)


def test_conic_storage_of_a_prism_and_a_cone() -> None:
    assert conic_storage(np.array([0.0, 2.0]), np.array([5.0, 5.0]))[-1] == pytest.approx(10.0)
    apex_up = conic_storage(np.array([0.0, 3.0]), np.array([0.0, 9.0]))
    assert apex_up[-1] == pytest.approx(9.0 * 3.0 / 3.0)
    assert apex_up[0] == 0.0


def test_outflow_curve_on_a_linear_reservoir_is_the_trapezoidal_recursion() -> None:
    """S = K Q: the storage-indication step reduces to a closed recursion."""
    storage_constant = 1.0e5
    rate = AREA_M2 / storage_constant
    method = ReservoirOutflowCurve(ELEVATIONS, FLAT_AREAS, ELEVATIONS, rate * ELEVATIONS, 0.0)
    inflow = flood()
    expected = np.zeros_like(inflow)
    weight = STEP_SECONDS / (2.0 * storage_constant)
    for step in range(len(inflow) - 1):
        known = (1.0 - weight) * expected[step] + weight * (inflow[step] + inflow[step + 1])
        expected[step + 1] = known / (1.0 + weight)
    assert method.route(inflow, STEP_MINUTES) == pytest.approx(expected, abs=1e-9)


def test_outflow_curve_reads_the_outflow_curve_at_the_primary_rows() -> None:
    method = ReservoirOutflowCurve(
        ELEVATIONS, FLAT_AREAS, np.array([0.0, 100.0]), np.array([0.0, 1000.0]), 0.0
    )
    assert method.outflow_m3s == pytest.approx(10.0 * ELEVATIONS)


def test_outflow_curve_has_no_auxiliary_flow_and_starts_at_its_initial_outflow() -> None:
    method = ReservoirOutflowCurve(ELEVATIONS, FLAT_AREAS, ELEVATIONS, ELEVATIONS, 40.0)
    main, auxiliary = method.branches(np.zeros(5), STEP_MINUTES)
    assert main[0] == pytest.approx(40.0)
    assert np.all(auxiliary == 0.0)


@pytest.mark.parametrize(
    "method",
    [
        ReservoirOutflowCurve(ELEVATIONS, FLAT_AREAS, ELEVATIONS, 0.0 * ELEVATIONS, 0.0),
        ReservoirOutflowStructures(ELEVATIONS, FLAT_AREAS, (weir(0, 1000.0),), 0.0),
    ],
)
def test_a_pool_above_its_table_raises_instead_of_guessing(method) -> None:
    with pytest.raises(ValueError, match="top of its table"):
        method.route(np.full(50, 1.0e6), STEP_MINUTES)


def test_initial_elevation_outside_the_table_raises() -> None:
    with pytest.raises(ValueError, match="outside the table"):
        ReservoirOutflowStructures(ELEVATIONS, FLAT_AREAS, (weir(),), 500.0)


def test_spillway_holds_nothing_below_its_crest_and_keeps_every_cubic_metre() -> None:
    inflow = flood(400.0)
    method = pool((weir(),))
    outflow = method.route(inflow, STEP_MINUTES)
    assert outflow[0] == 0.0
    assert 0.0 < outflow.max() < inflow.max()
    assert int(np.argmax(outflow)) > int(np.argmax(inflow))
    level_at_end = CREST_M + (outflow[-1] / (COEFFICIENT * LENGTH_M)) ** (2.0 / 3.0)
    stored = (level_at_end - 5.0) * AREA_M2
    balance = STEP_SECONDS * (np.trapezoid(inflow) - np.trapezoid(outflow))
    assert stored == pytest.approx(balance, rel=1e-9)


def test_main_and_auxiliary_spill_the_same_on_the_same_head() -> None:
    main, auxiliary = pool((weir(), weir(AUXILIARY_OUTLET))).branches(flood(), STEP_MINUTES)
    assert main.max() > 0.0
    assert main == pytest.approx(auxiliary)


def test_a_step_past_the_level_limit_is_cut_in_two_with_the_inflow_at_its_mean() -> None:
    """One control step by hand: two implicit trapezoids of 150 s at the mean inflow."""
    inflow = np.array([0.0, 2000.0])
    start = CREST_M + 1.0
    rate = COEFFICIENT * LENGTH_M
    first = rate * 1.0

    def part(level: float, flow: float) -> tuple[float, float]:
        low, high = level, level + 5.0
        known = level * AREA_M2 + 150.0 * (1000.0 - 0.5 * flow)
        for _ in range(200):
            middle = 0.5 * (low + high)
            value = middle * AREA_M2 + 75.0 * rate * (middle - CREST_M) ** 1.5
            low, high = (middle, high) if value < known else (low, middle)
        return middle, rate * (middle - CREST_M) ** 1.5

    level, flow = part(start, first)
    level, flow = part(level, flow)
    assert level - start > ADAPTIVE_LEVEL_CHANGE_M
    outflow = pool((weir(),), start, 1).route(inflow, STEP_MINUTES)
    assert outflow[-1] == pytest.approx(flow, rel=1e-9)
    assert outflow[-1] != pytest.approx(pool((weir(),), start, 0).route(inflow, STEP_MINUTES)[-1], rel=1e-5)


def test_a_slow_step_is_not_bisected() -> None:
    inflow = np.full(20, 20.0)
    bisected = pool((weir(),), CREST_M + 1.0, 8).route(inflow, STEP_MINUTES)
    single = pool((weir(),), CREST_M + 1.0, 0).route(inflow, STEP_MINUTES)
    assert bisected == pytest.approx(single)


def test_the_methods_are_in_the_routing_registry() -> None:
    assert "Reservoir Outflow Curve" in ROUTING_METHODS
    assert "Reservoir Outflow Structures" in ROUTING_METHODS
    assert "Inflow-Diversion Table" in ROUTING_METHODS


def test_diversion_splits_by_its_table_and_conserves_flow() -> None:
    method = InflowDiversion(np.array([0.0, 100.0]), np.array([0.0, 40.0]))
    main, diverted = method.branches(np.array([0.0, 50.0, 100.0]), STEP_MINUTES)
    assert diverted == pytest.approx([0.0, 20.0, 40.0])
    assert main + diverted == pytest.approx([0.0, 50.0, 100.0])


def test_diversion_above_its_table_raises() -> None:
    with pytest.raises(ValueError, match="above the table"):
        InflowDiversion(np.array([0.0, 10.0]), np.array([0.0, 5.0])).route(np.array([11.0]), STEP_MINUTES)


def branched_basin() -> Basin:
    """S1 > D1 > J1, with half of D1 diverted to J2, where S2 also arrives."""

    def subbasin(name: str, target: str, area: float) -> Subbasin:
        return Subbasin(name, target, area, NoLoss(), ScsUnitHydrograph(30.0))

    half = InflowDiversion(np.array([0.0, 1.0e6]), np.array([0.0, 5.0e5]))
    return Basin(
        "branched",
        [
            subbasin("S1", "D1", 10.0),
            Diversion("D1", "J1", half, branch="J2"),
            subbasin("S2", "J2", 3.0),
            Junction("J1", None),
            Junction("J2", "R1"),
            Reach("R1", None, NoRouting()),
        ],
    )


def test_a_branch_is_computed_but_stays_out_of_the_drainage_area() -> None:
    basin = branched_basin()
    assert basin.upstream_of("J2") == {"J2", "S2", "D1", "S1"}
    assert basin.drainage_area("J2") == pytest.approx(3.0)
    assert basin.drainage_area("J1") == pytest.approx(10.0)
    assert basin.topological_order().index("D1") < basin.topological_order().index("J2")


def test_a_branch_carries_its_flow_to_its_target() -> None:
    engine = LumpedEngine(branched_basin())
    run = engine.run(UniformStorm(50.0, 60.0), TimeGrid(STEP_MINUTES, 60))
    assert run.branched["D1"].max() > 0.0
    assert run.outflow["J1"] == pytest.approx(0.5 * run.inflow["D1"])
    assert run.inflow["J2"] == pytest.approx(run.branched["D1"] + run.outflow["S2"])


def test_a_sub_network_above_a_branch_target_gets_the_branch() -> None:
    engine = LumpedEngine(branched_basin())
    grid = TimeGrid(STEP_MINUTES, 60)
    whole = engine.run(UniformStorm(50.0, 60.0), grid)
    part = engine.run(UniformStorm(50.0, 60.0), grid, only=engine.basin.upstream_of("R1"))
    assert part.outflow["R1"] == pytest.approx(whole.outflow["R1"])
    assert "J1" not in part.outflow


def test_an_element_may_not_send_both_outflows_to_one_target() -> None:
    with pytest.raises(ValueError, match="both its outflows"):
        Basin("bad", [Reservoir("R", "J", NoRouting(), branch="J"), Junction("J", None)])  # type: ignore[arg-type]


def test_a_branch_to_an_unknown_element_raises() -> None:
    with pytest.raises(ValueError, match="unknown element"):
        Basin("bad", [Reservoir("R", None, NoRouting(), branch="J")])  # type: ignore[arg-type]


RESERVOIR_BASIN = """Basin: small
     Version: 4.12
     Unit System: Metric
End:

Subbasin: S1
     Area: 10
     Downstream: Dam
     LossRate: None
     Transform: SCS
     Lag: 30
     Baseflow: None
End:

Reservoir: Dam
     Downstream: Out
     Auxiliary Flow To: Side

     Route: Controlled Outflow
     Routing Curve: Elevation-Area
     Initial Elevation: 5
     Elevation-Area Table: EA
     Adaptive Control: On
     Main Tailwater Condition: None
     Auxiliary Tailwater Condition: None

     Spillway: Broad-Crested Spillway
     Spillway Outlet: Main
     Spillway Crest Length: 20
     Spillway Crest Elevation: 10
     Spillway Coefficient: 2
     End Spillway:

     Spillway: Broad-Crested Spillway
     Spillway Outlet: Auxiliary
     Spillway Crest Length: 20
     Spillway Crest Elevation: 10
     Spillway Coefficient: 2
     End Spillway:

     Evaporation Method: Zero Evaporation
     End Evaporation:
End:

Sink: Out
End:

Sink: Side
End:
"""
CURVE_BASIN = """Basin: small
     Version: 4.12
     Unit System: Metric
End:

Reservoir: Dam

     Route: Modified Puls
     Routing Curve: Elevation-Area-Outflow
     Initial Elevation: 0
     Elevation-Area Table: EA
     Elevation-Outflow Table: EQ
     Primary Table: Elevation-Area
End:
"""
TABLES = ProjectTables(
    {},
    {},
    {"EA": PairedColumns(ELEVATIONS, FLAT_AREAS), "EQ": PairedColumns(ELEVATIONS, ELEVATIONS)},
)


def hms_basin(tmp_path: Path, text: str) -> HmsBasin:
    path = tmp_path / "small.basin"
    path.write_text(text, encoding="utf-8")
    return load_basin(path)


def test_adapter_builds_a_controlled_outflow_reservoir_with_its_auxiliary_branch(tmp_path: Path) -> None:
    basin = basin_from_hms(hms_basin(tmp_path, RESERVOIR_BASIN), TABLES)
    dam = basin.elements["Dam"]
    assert isinstance(dam, Reservoir)
    assert dam.branch == "Side"
    assert isinstance(dam.routing, ReservoirOutflowStructures)
    assert [spillway.outlet for spillway in dam.routing.spillways] == [0, AUXILIARY_OUTLET]
    assert isinstance(basin.elements["Out"], Junction)
    run = LumpedEngine(basin).run(UniformStorm(1000.0, 60.0), TimeGrid(STEP_MINUTES, 200))
    assert run.outflow["Side"].max() > 0.0
    assert run.outflow["Side"] == pytest.approx(run.outflow["Out"])


def test_adapter_builds_an_outflow_curve_reservoir(tmp_path: Path) -> None:
    basin = basin_from_hms(hms_basin(tmp_path, CURVE_BASIN), TABLES)
    assert isinstance(basin.elements["Dam"].routing, ReservoirOutflowCurve)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("Adaptive Control: On", "Adaptive Control: Off"), "Adaptive Control"),
        (("Main Tailwater Condition: None", "Main Tailwater Condition: Fixed Stage"), "tailwater"),
        (("Routing Curve: Elevation-Area", "Routing Curve: Elevation-Storage"), "storage method"),
        (("Spillway: Broad-Crested Spillway", "Spillway: Ogee Spillway"), "not supported"),
        (("Evaporation Method: Zero Evaporation", "Evaporation Method: Monthly"), "not supported"),
        (("Elevation-Area Table: EA", "Elevation-Area Table: Missing"), "not available"),
        (("Initial Elevation: 5", "Initial Storage: 5"), "not read|initial elevation"),
    ],
)
def test_adapter_refuses_what_was_never_measured(
    tmp_path: Path, change: tuple[str, str], message: str
) -> None:
    text = RESERVOIR_BASIN.replace(*change)
    with pytest.raises(ValueError, match=message):
        basin_from_hms(hms_basin(tmp_path, text), TABLES)


def test_adapter_refuses_a_reservoir_without_tables(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not available"):
        basin_from_hms(hms_basin(tmp_path, RESERVOIR_BASIN))


def test_adapter_refuses_an_outflow_curve_of_another_kind(tmp_path: Path) -> None:
    text = CURVE_BASIN.replace("Primary Table: Elevation-Area", "Primary Table: Elevation-Outflow")
    with pytest.raises(ValueError, match="primary"):
        basin_from_hms(hms_basin(tmp_path, text), TABLES)
