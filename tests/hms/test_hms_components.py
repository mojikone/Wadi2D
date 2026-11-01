"""The small typed files: met, control, nals, pdata, project, run."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from wadi2d.hms import (
    control,
    load_control,
    load_met,
    load_nals,
    load_pdata,
    load_project,
    load_run,
    met,
    nals,
    pdata,
    project,
    text,
    typed,
)


def test_hypothetical_storm(fixtures: Path) -> None:
    model = load_met(fixtures / "sample.met")
    assert model.name == "Storm 100"
    assert model.header.precipitation_method == "Hypothetical Storm"
    assert model.header.evapotranspiration_method == "No Evapotranspiration"
    assert model.header.use_basin_models == ["Sample Basin", "Other Basin"]
    storm = model.storm
    assert (storm.storm_depth, storm.storm_area, storm.storm_duration) == (205.4, 300.0, 24.0)
    assert (storm.pattern_name, storm.reduction_table_name) == ("Pattern A", "ARF A")
    assert (storm.depth_area_reduction_method, storm.uniform_depth) == ("User-Specified", "Yes")
    assert model.frequency_storm is None
    assert model.unknown_report() == []


def test_subbasin_depths(fixtures: Path) -> None:
    model = load_met(fixtures / "sample.met")
    assert model.subbasins["S1"].depth is None
    assert model.subbasins["S2"].depth == 12.5


def test_frequency_storm_stays_raw(fixtures: Path) -> None:
    model = load_met(fixtures / "frequency.met")
    assert model.storm is None
    raw = model.frequency_storm
    assert raw.get("Intensity Position") == "50"
    assert raw.get_all("Depth") == ["10.5", "22.5", "205.4"]


def test_control(fixtures: Path) -> None:
    model = load_control(fixtures / "sample.control")
    assert model.name == "Control 1"
    assert model.start == datetime(2000, 1, 1)
    assert model.end == datetime(2000, 1, 2, 12)
    assert model.interval == timedelta(minutes=15)
    assert model.n_steps == 145
    assert model.time_zone_gmt_offset == 14400000
    assert model.unknown_report() == []


def test_control_without_a_window() -> None:
    model = control.from_document(text.parse(b"Control: C\r\nEnd:\r\n"))
    assert (model.start, model.end, model.interval, model.n_steps) == (None, None, None, None)


def test_nals(fixtures: Path) -> None:
    model = load_nals(fixtures / "sample.nals")
    assert [a.name for a in model.analyses] == ["DA 100", "DA 200"]
    analysis = model.analysis("DA 100")
    assert analysis.points == ["S1", "J1", "Z Outlet"]
    assert (analysis.basin_model_name, analysis.met_model_name) == ("Sample Basin", "Storm 100")
    assert (analysis.dss_file, analysis.time_zone_gmt_offset) == ("DA_100.dss", -28800000)
    assert analysis.n_steps == 577
    assert model.analysis("DA 200").n_steps == 25
    assert model.unknown_report() == []
    with pytest.raises(KeyError):
        model.analysis("nope")


def test_pdata(fixtures: Path) -> None:
    model = load_pdata(fixtures / "sample.pdata")
    assert list(model.tables) == ["Elev-Dis", "ARF A", "Pattern A"]
    table = model.tables["ARF A"]
    assert table.table_type == "Area-Reduction Factor"
    assert table.pathname == "//ARF A/AREA-REDUCTION FACTOR///TABLE/"
    assert (table.x_units, table.y_units, table.interpolation) == ("KM2", None, "Linear Interpolation")
    assert list(model.of_type("Percent Graph")) == ["Pattern A"]
    assert model.unknown_report() == []


def test_project(fixtures: Path) -> None:
    model = load_project(fixtures / "sample.hms")
    assert model.name == "Sample Project"
    assert (model.header.version, model.header.dss_file_name) == ("4.12", "sample.dss")
    assert list(model.mets) == ["Storm 100", "Storm Classic"]
    assert list(model.basins) == ["Sample Basin"]
    assert model.path_of(model.basins["Sample Basin"]) == fixtures / "sample.basin"
    assert model.controls["Control 1"].file == r"subfolder\sample.control"
    assert model.path_of(model.controls["Control 1"]) == fixtures / "subfolder" / "sample.control"
    assert [(e.where, e.key) for e in model.unknown_report()] == [("Mystery Component M1", "block")]


def test_project_without_a_folder_cannot_resolve(fixtures: Path) -> None:
    model = project.from_document(text.load(fixtures / "sample.hms"))
    with pytest.raises(ValueError, match="cannot resolve"):
        model.path_of(model.basins["Sample Basin"])


def test_run(fixtures: Path) -> None:
    model = load_run(fixtures / "sample.run")
    run = model.run("Run 100")
    assert (run.basin, run.precip, run.control) == ("Sample Basin", "Storm 100", "Control 1")
    assert (run.dss_file, run.log_file, run.time_series_output) == ("Run_100.dss", "Run_100.log", "Save All")
    assert [r.name for r in model.runs] == ["Run 100", "Run Classic"]
    assert model.unknown_report() == []
    with pytest.raises(KeyError):
        model.run("nope")


@pytest.mark.parametrize(
    ("module", "message"),
    [
        (met, "not a met"),
        (control, "not a control"),
        (nals, "not a depth-area"),
        (pdata, "not a paired-data"),
    ],
)
def test_wrong_file_type(module: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        module.from_document(text.parse(b"Basin: B\r\nEnd:\r\n"))


def test_project_wrong_file_type() -> None:
    with pytest.raises(ValueError, match="not a project"):
        project.from_document(text.parse(b"Basin: B\r\nEnd:\r\n"))


@pytest.mark.parametrize(
    ("date_text", "time_text", "expected"),
    [
        ("31 December 1999", "24:00", datetime(2000, 1, 1)),
        ("2 January 2000", "00:05", datetime(2000, 1, 2, 0, 5)),
        ("2 January 2000", "09:36:22", datetime(2000, 1, 2, 9, 36, 22)),
    ],
)
def test_parse_date_time(date_text: str, time_text: str, expected: datetime) -> None:
    assert typed.parse_date_time(date_text, time_text) == expected


def test_parse_stamp() -> None:
    assert typed.parse_stamp("01Jan2000, 15:35") == datetime(2000, 1, 1, 15, 35)
    assert typed.parse_stamp("31Dec1999, 24:00") == datetime(2000, 1, 1)
