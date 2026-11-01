"""The readers on the real Block 2 project, which stays read-only: DSS files go through scratch copies."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from wadi2d.hms import (
    daa_fpart,
    load_basin,
    load_control,
    load_met,
    load_nals,
    load_pdata,
    load_project,
    load_results,
    load_run,
    met_fpart,
    open_dss,
    sqlite,
    text,
)

pytestmark = pytest.mark.data

GRAMMAR_SUFFIXES = {
    ".hms",
    ".basin",
    ".met",
    ".control",
    ".nals",
    ".pdata",
    ".run",
    ".grid",
    ".terrain",
    ".gage",
}
OTHER_TEXT_SUFFIXES = {".log", ".out", ".results"}
DA_100 = "DA 100yr B1"


@pytest.fixture(scope="module")
def basin_model(hms_project_dir: Path):
    return load_basin(hms_project_dir / "Basin_1.basin")


def test_every_text_file_round_trips_byte_exact(hms_project_dir: Path, tmp_path: Path) -> None:
    folders = [hms_project_dir, hms_project_dir / "results"]
    files = [p for folder in folders for p in folder.iterdir() if p.is_file()]
    grammar = [p for p in files if p.suffix in GRAMMAR_SUFFIXES]
    others = [p for p in files if p.suffix in OTHER_TEXT_SUFFIXES]
    assert len(grammar) >= 20
    for path in grammar + others:
        target = tmp_path / path.name
        document = text.load(path)
        text.dump(document, target)
        assert target.read_bytes() == path.read_bytes(), path.name
    for path in grammar:
        assert text.load(path).unclosed() == [], path.name


def test_counts_and_nothing_unknown(basin_model) -> None:
    assert len(basin_model.subbasins) == 18
    assert len(basin_model.reaches) == 8
    assert len(basin_model.junctions) == 14
    assert basin_model.unit_system == "Metric"
    assert basin_model.unknown_report() == []
    assert len(basin_model.spatial.break_points) == 5


def test_subbasins(basin_model) -> None:
    s1, s18 = basin_model.subbasins["S1"], basin_model.subbasins["S18"]
    assert (s1.area, s1.loss.curve_number, s1.transform.lag) == (59.078, 90.7, 112.0)
    assert (s18.area, s18.transform.lag) == (1.6696, 31.5)
    assert s1.loss.initial_abstraction == 5.22
    assert s1.baseflow.method == "None"


def test_total_area(basin_model) -> None:
    assert sum(s.area for s in basin_model.subbasins.values()) == pytest.approx(599.33, abs=0.005)


def test_reach_r1(basin_model) -> None:
    route = basin_model.reaches["R1"].route
    assert (route.length, route.energy_slope) == (26008.98, 0.01241)
    assert (route.bottom_width, route.side_slope) == (60.0, 0.7)
    assert route.mannings_n == 0.1


def test_outlets(basin_model) -> None:
    network = basin_model.connectivity()
    assert set(network.outlets) == {"Z4C", "R2A", "Faydh 01", "Bidah 03", "R5A"}
    assert network.dangling == []
    assert network.upstream["J1"] == ["S1", "S2"]


def test_met_100yr(hms_project_dir: Path) -> None:
    model = load_met(hms_project_dir / "FM_100yr.met")
    storm = model.storm
    assert (storm.storm_depth, storm.storm_area, storm.pattern_name) == (205.4, 300.0, "FM 10-1000yr")
    assert storm.reduction_table_name == "ARF FM"
    assert model.unknown_report() == []


def test_met_pmp(hms_project_dir: Path) -> None:
    storm = load_met(hms_project_dir / "FM_PMP.met").storm
    assert (storm.precipitation_method, storm.precip_freq_grid_name) == (
        "Precipitation-Frequency Grid",
        "PMP",
    )


def test_control(hms_project_dir: Path) -> None:
    model = load_control(hms_project_dir / "Control_1.control")
    assert model.time_interval == 5
    assert model.n_steps == 577
    assert model.start == datetime(2000, 1, 1)
    assert model.unknown_report() == []


def test_nals(hms_project_dir: Path) -> None:
    model = load_nals(hms_project_dir / "HEC_HMS_Block_02.nals")
    assert len(model.analyses) == 13
    assert all(len(analysis.points) == 40 for analysis in model.analyses)
    assert model.analysis(DA_100).dss_file == "DA_100yr_B1.dss"
    assert model.unknown_report() == []


def test_pdata_project_and_run(hms_project_dir: Path) -> None:
    tables = load_pdata(hms_project_dir / "HEC_HMS_Block_02.pdata")
    assert tables.tables["ARF FM"].pathname == "//ARF FM/AREA-REDUCTION FACTOR///TABLE/"
    project = load_project(hms_project_dir / "HEC_HMS_Block_02.hms")
    assert (len(project.mets), list(project.basins)) == (13, ["Basin 1"])
    assert project.path_of(project.basins["Basin 1"]).is_file()
    assert project.path_of(project.controls["Control 1"]).is_file()
    assert project.unknown_report() == []
    runs = load_run(hms_project_dir / "HEC_HMS_Block_02.run")
    assert len(runs.runs) == 13
    assert runs.run("FM 100yr").dss_file == "FM_100yr.dss"
    assert runs.unknown_report() == []


def test_sqlite(hms_project_dir: Path) -> None:
    path = hms_project_dir / "Basin_1.sqlite"
    polygons = {p.name: p for p in sqlite.subbasin_polygons(path)}
    assert len(polygons) == 18
    assert polygons["S1"].shape().area / 1e6 == pytest.approx(59.078, abs=0.001)
    assert {line.name for line in sqlite.reach_lines(path, [f"R{i}" for i in range(1, 9)])} == {
        f"R{i}" for i in range(1, 9)
    }
    assert sqlite.reach_statistics(path)["R1"].length == pytest.approx(26008.98, abs=0.01)
    assert sqlite.subbasin_statistics(path)["S1"].length_10_85 == pytest.approx(19623, abs=1)


def test_results_xml(hms_project_dir: Path) -> None:
    results = load_results(hms_project_dir / "results" / "DAA_DA_100yr_B1.results")
    assert results.name == DA_100
    assert len(results.points) == 40
    z4c = results.element("Z4C")
    assert z4c.outflow_max == pytest.approx(1666.4, abs=0.05)
    assert z4c.outflow_max_time == datetime(2000, 1, 1, 15, 35)
    assert z4c.drainage_area == pytest.approx(211.085)
    s3 = results.element("S3")
    assert s3.precipitation == pytest.approx(189.31, abs=0.01)
    assert s3.excess == pytest.approx(159.21, abs=0.01)
    assert s3.loss == pytest.approx(30.10, abs=0.01)
    assert results.element("Z4C", "S3").outflow_max == pytest.approx(655.22, abs=0.01)


def test_dss_peak_matches_the_results(hms_project_dir: Path) -> None:
    results = load_results(hms_project_dir / "results" / "DAA_DA_100yr_B1.results")
    with open_dss(hms_project_dir / "DA_100yr_B1.dss") as file:
        assert file.record_count == 2928
        assert len(file.catalog()) == 1151
        series = file.read_timeseries("Z4C", "FLOW", daa_fpart(DA_100, "Z4C"))
    peak = int(np.argmax(series.values))
    assert str(series.pathname) == f"//Z4C/FLOW/31Dec1999-02Jan2000/5Minute/{daa_fpart(DA_100, 'Z4C')}/"
    assert series.values.size == 577
    assert series.values[peak] == pytest.approx(1666.40, abs=0.005)
    assert series.values[peak] == pytest.approx(results.element("Z4C").outflow_max, rel=1e-6)
    assert series.times[peak] == np.datetime64("2000-01-01T15:35:00")
    assert series.units == "M3/S"


def test_dss_precipitation_is_period_ending(hms_project_dir: Path) -> None:
    with open_dss(hms_project_dir / "FM_100yr.dss") as file:
        series = file.read_timeseries("S3", "PRECIP-INC", met_fpart("FM 100yr", "S3"))
    assert series.values.size == 576
    assert series.times[0] == np.datetime64("2000-01-01T00:05:00")
    assert series.period_start_times()[0] == np.datetime64("2000-01-01T00:00:00")
    assert series.values.sum() == pytest.approx(189.31, abs=0.01)


def test_paired_data(hms_project_dir: Path) -> None:
    tables = load_pdata(hms_project_dir / "HEC_HMS_Block_02.pdata").tables
    with open_dss(hms_project_dir / "HEC_HMS_Block_02.dss") as file:
        assert file.record_count == 6
        arf = file.read_paired(tables["ARF FM"].pathname)
        pattern = file.read_paired(tables["FM 10-1000yr"].pathname)
    assert arf.x.size == 12
    assert (arf.x[0], arf.y[0]) == (1.0, 0.999)
    assert (arf.x[-1], arf.y[-1]) == (2000.0, 0.606)
    assert arf.x_units == "KM2"
    assert pattern.x.size == 145
