"""The ``.basin`` typed layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from wadi2d.hms import basin, load_basin, methods, text
from wadi2d.hms.typed import RawField, UnknownMethod


@pytest.fixture(scope="module")
def model(fixtures: Path) -> basin.Basin:
    return load_basin(fixtures / "sample.basin")


def test_header(model: basin.Basin) -> None:
    assert model.name == "Sample Basin"
    assert model.unit_system == "Metric"
    assert model.header.version == "4.12"
    assert model.header.enable_sediment_routing == "No"
    assert model.header.unknown == []


def test_element_groups_in_file_order(model: basin.Basin) -> None:
    assert list(model.subbasins) == ["S1", "S2", "S3", "S4"]
    assert list(model.reaches) == ["R1", "R2", "R3", "R4"]
    assert list(model.junctions) == ["J1", "J2", "Z Outlet"]
    assert list(model.sinks) == ["Sink 1"]
    assert list(model.sources) == ["Src 1"]
    assert list(model.reservoirs) == ["Res 1"]
    assert list(model.diversions) == ["D1"]
    assert model.elements[0].name == "S1"


def test_scs_subbasin(model: basin.Basin) -> None:
    s1 = model.subbasins["S1"]
    assert (s1.area, s1.downstream, s1.latitude, s1.canvas_x) == (10.5, "J1", 24.5, 100.5)
    assert (s1.discretization, s1.file, s1.canopy, s1.surface) == ("None", "sample.sqlite", "None", "None")
    assert isinstance(s1.loss, methods.ScsLoss)
    assert (s1.loss.method, s1.loss.curve_number, s1.loss.initial_abstraction) == ("SCS", 85.0, 8.96)
    assert s1.loss.percent_impervious == 2.5
    assert isinstance(s1.transform, methods.ScsTransform)
    assert (s1.transform.lag, s1.transform.unitgraph_type) == (60.0, "STANDARD")
    assert isinstance(s1.baseflow, methods.NoMethod)
    assert s1.unknown == []


def test_other_method_variants(model: basin.Basin) -> None:
    s2, s3 = model.subbasins["S2"], model.subbasins["S3"]
    assert isinstance(s2.loss, methods.InitialConstantLoss)
    assert (s2.loss.initial_loss, s2.loss.constant_loss_rate) == (12.0, 3.5)
    assert isinstance(s2.transform, methods.ClarkTransform)
    assert (s2.transform.time_of_concentration, s2.transform.storage_coefficient) == (90.0, 45.0)
    assert isinstance(s2.baseflow, methods.RecessionBaseflow)
    assert (s2.baseflow.recession_factor, s2.baseflow.initial_baseflow) == (0.9, 1.5)
    assert isinstance(s3.loss, methods.DeficitConstantLoss)
    assert s3.loss.maximum_deficit == 40.0
    assert isinstance(s3.transform, methods.SnyderTransform)
    assert (s3.transform.snyder_tp, s3.transform.snyder_cp) == (3.5, 0.6)
    assert isinstance(s3.baseflow, methods.LinearReservoirBaseflow)


def test_canopy_and_surface_sub_blocks(model: basin.Basin) -> None:
    s2 = model.subbasins["S2"]
    assert (s2.canopy, s2.surface) == ("Simple", "Simple")
    assert [b.kind for b in s2.blocks] == ["Canopy", "Surface"]
    assert s2.blocks[0].get("Canopy Storage Capacity") == "2"
    assert s2.unknown == []


def test_unknown_selector_and_keys_are_kept_and_reported(model: basin.Basin) -> None:
    s4 = model.subbasins["S4"]
    assert isinstance(s4.loss, UnknownMethod)
    assert s4.loss.method == "Green and Ampt"
    assert isinstance(s4.transform, methods.ModifiedClarkTransform)
    assert s4.unknown == [
        RawField(key="Moisture Deficit", value="0.3"),
        RawField(key="Wetting Front Suction", value="120"),
        RawField(key="Future Key In HMS 5", value="Keep Me"),
        RawField(key="Future Key In HMS 5", value="Keep Me Too"),
    ]
    report = {(entry.where, entry.key, entry.value) for entry in model.unknown_report()}
    assert ("Subbasin S4", "method selector", "Green and Ampt") in report
    assert ("Subbasin S4", "Future Key In HMS 5", "Keep Me Too") in report
    assert ("Source Src 1", "Flow Method", "Constant") in report


def test_report_leaves_out_display_blocks(model: basin.Basin) -> None:
    assert {b.kind for b in model.other_blocks} == {
        "Computation Point",
        "Basin Layer Properties",
        "Basin Schematic Properties",
    }
    assert not any(entry.key == "block" for entry in model.unknown_report())


def test_unknown_block_is_reported() -> None:
    document = text.parse(b"Basin: B\r\nEnd:\r\n\r\nWidget: W\r\n     A: 1\r\nEnd:\r\n")
    model = basin.from_document(document)
    assert model.unknown_report()[0].where == "Widget W"
    assert model.other_blocks[0].get("A") == "1"


def test_bad_number_is_reported_not_raised() -> None:
    document = text.parse(b"Basin: B\r\nEnd:\r\nSubbasin: S\r\n     Area: abc\r\nEnd:\r\n")
    subbasin = basin.from_document(document).subbasins["S"]
    assert subbasin.area is None
    assert subbasin.unknown == [RawField(key="Area", value="abc")]


def test_empty_number_is_none_without_a_report() -> None:
    document = text.parse(b"Basin: B\r\nEnd:\r\nSubbasin: S\r\n     Area: \r\nEnd:\r\n")
    subbasin = basin.from_document(document).subbasins["S"]
    assert subbasin.area is None
    assert subbasin.unknown == []


def test_raw_line_in_a_block_is_reported() -> None:
    document = text.parse(b"Basin: B\r\nEnd:\r\nJunction: J\r\n     free text\r\n\r\nEnd:\r\n")
    junction = basin.from_document(document).junctions["J"]
    assert junction.unknown == [RawField(key="", value="free text")]


def test_reach_variants(model: basin.Basin) -> None:
    r1 = model.reaches["R1"]
    assert isinstance(r1.route, methods.MuskingumCungeRoute)
    route = r1.route
    assert (route.channel, route.length, route.energy_slope) == ("Trapezoid", 2500.5, 0.012)
    assert (route.mannings_n, route.bottom_width, route.side_slope) == (0.1, 60.0, 0.7)
    assert (route.number_subreaches, route.maximum_depth_iterations) == (1, 20)
    assert route.channel_loss == "None"
    assert r1.from_canvas_x == 140.5
    assert isinstance(model.reaches["R2"].route, methods.MuskingumRoute)
    assert model.reaches["R2"].route.muskingum_steps == 3
    assert isinstance(model.reaches["R3"].route, methods.LagRoute)
    assert model.reaches["R3"].route.lag == 25.0
    assert isinstance(model.reaches["R4"].route, methods.ModifiedPulsRoute)
    assert model.reaches["R4"].route.storage_outflow_table == "SQ 1"


def test_reservoir(model: basin.Basin) -> None:
    reservoir = model.reservoirs["Res 1"]
    assert isinstance(reservoir.route, methods.ReservoirRoute)
    assert (reservoir.route.initial_elevation, reservoir.route.elevation_storage_table) == (205.5, "ES 1")
    spillways = reservoir.outlets_of("Spillway")
    assert [s.get("Spillway Crest Length") for s in spillways] == ["72", "20"]
    assert [s.name for s in reservoir.outlets_of("Conduit")] == ["Culvert"]
    assert reservoir.unknown == []


def test_diversion(model: basin.Basin) -> None:
    diversion = model.diversions["D1"]
    assert (diversion.downstream, diversion.divert_to) == ("J2", "R3")
    assert diversion.blocks[0].kind == "Diverter"


def test_spatial(model: basin.Basin) -> None:
    assert model.spatial.terrain == "Sample Terrain"
    assert model.spatial.coordinate_system.startswith("PROJCS[")
    assert [(p.number, p.x, p.y) for p in model.spatial.break_points] == [
        ("1", 431019.5, 2733413.25),
        ("2", 438599.5, 2727058.25),
    ]
    assert model.spatial.unknown == []


def test_connectivity(model: basin.Basin) -> None:
    network = model.connectivity()
    assert network.downstream["S1"] == "J1"
    assert network.downstream["Sink 1"] is None
    assert network.upstream["J1"] == ["S1", "S2"]
    assert set(network.upstream["J2"]) == {"R2", "R3", "R4", "D1"}
    assert network.upstream["S1"] == []
    assert network.outlets == ["Sink 1", "Z Outlet"]
    assert network.dangling == []


def test_dangling_target() -> None:
    document = text.parse(b"Basin: B\r\nEnd:\r\nJunction: J\r\n     Downstream: Ghost\r\nEnd:\r\n")
    network = basin.from_document(document).connectivity()
    assert network.dangling == [("J", "Ghost")]
    assert network.outlets == []


def test_empty_downstream_is_terminal() -> None:
    document = text.parse(b"Basin: B\r\nEnd:\r\nJunction: J\r\n     Downstream: \r\nEnd:\r\n")
    assert basin.from_document(document).connectivity().outlets == ["J"]


def test_model_dump_keeps_the_variant_fields(model: basin.Basin) -> None:
    dumped = model.subbasins["S1"].model_dump()
    assert dumped["loss"]["curve_number"] == 85.0


def test_not_a_basin_file() -> None:
    with pytest.raises(ValueError, match="not a basin file"):
        basin.from_document(text.parse(b"Control: C\r\nEnd:\r\n"))
