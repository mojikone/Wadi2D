"""The network, the depth-area analysis and the HMS adapter on synthetic data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from wadi2d.hms import Basin as HmsBasin
from wadi2d.hms import load_basin, load_control
from wadi2d.hydrology import Basin, Junction, LumpedEngine, Reach, Subbasin, TimeGrid, analyse, point_storm
from wadi2d.hydrology.baseflow import NoBaseflow, RecessionBaseflow
from wadi2d.hydrology.constants import M3_PER_MM_KM2, SECONDS_PER_MINUTE
from wadi2d.hydrology.from_hms import basin_from_hms, grid_from_hms, storm_from_hms
from wadi2d.hydrology.losses import NoLoss, ScsCurveNumber
from wadi2d.hydrology.model import Element
from wadi2d.hydrology.replication import Comparison, Replication, render
from wadi2d.hydrology.routing import LagRouting, MuskingumCunge
from wadi2d.hydrology.transforms import ClarkUnitHydrograph, ScsUnitHydrograph
from wadi2d.storm import ArfTable, UniformStorm

FIXTURES = Path(__file__).parents[1] / "data" / "hms"
GRID = TimeGrid(5.0, 400)
ARF = ArfTable(np.array([1.0, 100.0]), np.array([1.0, 0.5]))


def subbasin(name: str, downstream: str | None, area: float = 10.0, loss: object | None = None) -> Subbasin:
    return Subbasin(name, downstream, area, loss or NoLoss(), ScsUnitHydrograph(30.0))  # type: ignore[arg-type]


def small_basin() -> Basin:
    return Basin(
        "small",
        [
            subbasin("A", "J1", 10.0),
            subbasin("B", "J1", 30.0),
            Junction("J1", "R1"),
            Reach("R1", "OUT", LagRouting(10.0)),
            subbasin("C", "OUT", 20.0),
            Junction("OUT", None),
        ],
    )


def volume_mm(flow: np.ndarray, area_km2: float) -> float:
    return float(flow.sum() * GRID.dt_seconds / (area_km2 * M3_PER_MM_KM2))


def test_topological_order_puts_every_element_after_its_upstream() -> None:
    basin = small_basin()
    order = basin.topological_order()
    assert sorted(order) == sorted(basin.elements)
    for name, element in basin.elements.items():
        if element.downstream is not None:
            assert order.index(name) < order.index(element.downstream)


def test_topological_order_does_not_depend_on_file_order() -> None:
    elements: list[Element] = [Junction("OUT", None), Reach("R", "OUT", LagRouting(5.0)), subbasin("S", "R")]
    assert Basin("reversed", elements).topological_order() == ["S", "R", "OUT"]


def test_a_cycle_is_refused() -> None:
    with pytest.raises(ValueError, match="cycle"):
        Basin("loop", [Junction("A", "B"), Junction("B", "A")]).topological_order()


def test_an_unknown_downstream_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown element"):
        Basin("dangling", [Junction("A", "NOWHERE")])


def test_upstream_set_and_drainage_area() -> None:
    basin = small_basin()
    assert basin.upstream_of("R1") == {"A", "B", "J1", "R1"}
    assert basin.drainage_area("R1") == pytest.approx(40.0)
    assert basin.drainage_area("OUT") == pytest.approx(60.0)


def test_a_junction_sums_its_inflows_and_a_reach_shifts_them() -> None:
    run = LumpedEngine(small_basin()).run(UniformStorm(10.0, 60.0), GRID)
    assert run.outflow["J1"] == pytest.approx(run.outflow["A"] + run.outflow["B"])
    assert run.outflow["R1"][2:] == pytest.approx(run.outflow["J1"][:-2])
    assert run.inflow["OUT"] == pytest.approx(run.outflow["R1"] + run.outflow["C"])


def test_the_run_conserves_water_from_rain_to_the_outlet() -> None:
    run = LumpedEngine(small_basin()).run(UniformStorm(10.0, 60.0), GRID)
    assert volume_mm(run.outflow["OUT"], 60.0) == pytest.approx(10.0, rel=1e-6)


def test_a_run_of_a_sub_network_computes_only_that() -> None:
    engine = LumpedEngine(small_basin())
    run = engine.run(UniformStorm(10.0, 60.0), GRID, only=engine.basin.upstream_of("J1"))
    assert set(run.outflow) == {"A", "B", "J1"}


def test_losses_are_booked_per_subbasin() -> None:
    basin = Basin("one", [subbasin("S", None, loss=ScsCurveNumber(80.0))])
    water = LumpedEngine(basin).run(UniformStorm(100.0, 60.0), GRID).water["S"]
    assert water.precipitation.sum() == pytest.approx(100.0)
    assert water.excess.sum() + water.loss.sum() == pytest.approx(100.0)


def test_depth_area_reduces_each_point_by_its_own_drainage_area() -> None:
    engine = LumpedEngine(small_basin())
    storm = UniformStorm(10.0, 60.0, arf=ARF)
    results = analyse(engine, point_storm(storm), GRID, ["A", "OUT"])
    assert results["A"].storm_area_km2 == pytest.approx(10.0)
    assert results["OUT"].storm_area_km2 == pytest.approx(60.0)
    assert results["A"].run.water["A"].precipitation.sum() == pytest.approx(10.0 * ARF.factor(10.0))
    assert results["OUT"].run.water["A"].precipitation.sum() == pytest.approx(10.0 * ARF.factor(60.0))
    assert set(results["A"].run.outflow) == {"A"}


def test_point_result_reports_peak_time_and_volume() -> None:
    engine = LumpedEngine(small_basin())
    result = analyse(engine, point_storm(UniformStorm(10.0, 60.0)), GRID, ["OUT"])["OUT"]
    assert result.peak == pytest.approx(float(result.outflow.max()))
    assert result.peak_minutes == pytest.approx(5.0 * float(np.argmax(result.outflow)))
    assert result.volume_m3 == pytest.approx(10.0 * 60.0 * M3_PER_MM_KM2, rel=1e-6)


def test_time_grid() -> None:
    assert GRID.n_times == 401
    assert GRID.dt_seconds == pytest.approx(5.0 * SECONDS_PER_MINUTE)
    assert GRID.minutes[-1] == pytest.approx(2000.0)


SMALL_BASIN = """Basin: Small
     Unit System: Metric
End:

Subbasin: S1
     Area: 12.5
     Downstream: J1
     LossRate: SCS
     Percent Impervious Area: 5.0
     Curve Number: 85
     Initial Abstraction: 9.0
     Transform: SCS
     Lag: 40
     Unitgraph Type: STANDARD
     Baseflow: None
End:

Subbasin: S2
     Area: 3
     Downstream: J1
     LossRate: None
     Transform: Clark
     Time of Concentration: 60
     Storage Coefficient: 30
     Baseflow: Recession
     Recession Factor: 0.9
     Initial Flow/Area Ratio: 0.01
     Threshold Flow to Peak Ratio: 0.1
End:

Junction: J1
     Downstream: R1
End:

Reach: R1
     Downstream: J2
     Route: Muskingum Cunge
     Channel: Trapezoid
     Length: 1000
     Energy Slope: 0.01
     Mannings n: 0.05
     Bottom Width: 20
     Side Slope: 1
     Space-Time Method: Automatic DX and DT
     Index Parameter Type: Index Celerity
     Index Celerity: 1.5
     Number Subreaches: 1
     Maximum Depth Iterations: 20
     Maximum Route Step Iterations: 30
     Channel Loss: None
End:

Reach: R2
     Downstream: J2
     Route: Lag
     Lag: 10
End:

Junction: J2
End:
"""


def small_hms_basin(tmp_path: Path) -> HmsBasin:
    path = tmp_path / "small.basin"
    path.write_text(SMALL_BASIN, encoding="utf-8")
    return load_basin(path)


def test_adapter_maps_every_supported_method(tmp_path: Path) -> None:
    basin = basin_from_hms(small_hms_basin(tmp_path))
    first, second = basin.subbasins["S1"], basin.subbasins["S2"]
    assert first.loss == ScsCurveNumber(85.0, 9.0, 5.0)
    assert first.transform == ScsUnitHydrograph(40.0)
    assert isinstance(first.baseflow, NoBaseflow)
    assert isinstance(second.loss, NoLoss)
    assert second.transform == ClarkUnitHydrograph(60.0, 30.0)
    assert second.baseflow == RecessionBaseflow(0.9, 0.01, 0.1)
    reach = basin.elements["R1"]
    assert isinstance(reach, Reach)
    assert reach.routing == MuskingumCunge(1000.0, 0.01, 0.05, 20.0, 1.0, 1.5, 30, 20)
    assert basin.topological_order()[-1] == "J2"
    run = LumpedEngine(basin).run(UniformStorm(50.0, 60.0), GRID)
    assert run.outflow["J2"].max() > 0.0


def test_adapter_refuses_a_method_it_does_not_implement() -> None:
    with pytest.raises(ValueError, match="no engine implementation"):
        basin_from_hms(load_basin(FIXTURES / "sample.basin"))


def test_time_grid_of_a_control_file() -> None:
    assert grid_from_hms(load_control(FIXTURES / "sample.control")).n_intervals > 0


def test_adapter_refuses_an_english_basin_model(tmp_path: Path) -> None:
    hms = small_hms_basin(tmp_path)
    hms.header.unit_system = "English"
    with pytest.raises(ValueError, match="unit system"):
        basin_from_hms(hms)


@dataclass
class FakeStorm:
    storm_type: str = "SCS"
    pattern_name: str | None = None
    storm_duration: float | None = None


def test_adapter_refuses_a_storm_it_cannot_build() -> None:
    with pytest.raises(ValueError, match="specified pattern"):
        storm_from_hms(FakeStorm(), None)  # type: ignore[arg-type]


def test_render_lists_summary_dams_and_every_point() -> None:
    rows = [
        Comparison("DA 2yr B1", "Z4C", 100.0, 101.0, 600.0, 605.0, 5.0),
        Comparison("DA 2yr B1", "S1", 50.0, 50.0, 300.0, 300.0, 5.0),
    ]
    text = render(Replication(rows, {"DA PMP B1": "grid not readable"}), ["Z4C"], "DA 2yr B1", "# Title")
    assert "| DA 2yr B1 | +1.000 | Z4C | +1.000 | Z4C | 1 |" in text
    assert "| S1 | +0.000 |" in text
    assert "DA PMP B1: grid not readable" in text
