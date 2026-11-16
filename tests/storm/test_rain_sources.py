"""W95's rain sources and table store, on their own: the schema, the stored tables by name, the patterns as the storm
builders take them, and the old kinds left as they were."""

from __future__ import annotations

import json

import numpy as np
import pytest
from pydantic import ValidationError

from tests.engine.conftest import job, write_dem
from wadi2d.config.rain import PatternTable, StormPattern
from wadi2d.config.schema import RunConfig, Storm
from wadi2d.forcing import build_storm
from wadi2d.run import job_hash, load_job
from wadi2d.storm import HypotheticalStorm, UniformStorm
from wadi2d.storm.patterns import SCS_CURVES, SCS_HOURS, percent_pattern

CURVE = {"areas_km2": [10.0, 1000.0], "factors": [1.0, 0.5], "table_type": "test table"}
FRONT = {"time": [0.0, 25.0, 100.0], "depth": [0.0, 60.0, 100.0]}
DEPTH = {"kind": "depth", "depth_mm": 80.0, "duration_min": 120.0}


def _cfg(storm: dict, **parts) -> RunConfig:
    return job("x.tif", 8, 8, 4.0, storm=storm, **parts)


def test_a_depth_storm_with_no_pattern_is_the_uniform_storm_to_the_digit() -> None:
    new = build_storm(_cfg(DEPTH))
    old = build_storm(_cfg({"kind": "uniform", "depth_mm": 80.0, "duration_min": 120.0}))
    assert isinstance(new, UniformStorm)
    minutes = np.linspace(-10.0, 130.0, 57)
    assert np.array_equal(new.cumulative_depth(minutes), old.cumulative_depth(minutes))
    assert np.array_equal(new.increments(5.0, 30), old.increments(5.0, 30))


def test_a_depth_storm_with_a_table_is_the_hypothetical_storm_to_the_digit() -> None:
    new = build_storm(_cfg({**DEPTH, "pattern": {"kind": "table", "values": FRONT}}))
    old = build_storm(
        _cfg({"kind": "hypothetical", "depth_mm": 80.0, "duration_min": 120.0, "time_percent": FRONT["time"],
              "depth_percent": FRONT["depth"]})
    )  # fmt: skip
    assert isinstance(new, HypotheticalStorm)
    minutes = np.linspace(0.0, 120.0, 49)
    assert np.array_equal(new.cumulative_depth(minutes), old.cumulative_depth(minutes))


@pytest.mark.parametrize(
    ("table", "at_30"),
    [
        ({"time": [0.0, 0.25, 1.0], "depth": [0.0, 3.0, 5.0], "time_units": "fraction"}, 48.0),
        ({"time": [0.0, 0.5, 2.0], "depth": [0.0, 30.0, 50.0], "time_units": "hours"}, 48.0),
        ({"time": [30.0, 120.0], "depth": [3.0, 2.0], "time_units": "minutes", "form": "incremental"}, 48.0),
        ({"time": [25.0, 100.0], "depth": [0.6, 0.4], "form": "incremental"}, 48.0),
    ],
)
def test_every_spelling_of_a_pattern_puts_the_whole_depth_in_the_storm(table, at_30) -> None:
    storm = build_storm(_cfg({**DEPTH, "pattern": {"kind": "table", "values": table}}))
    assert storm.cumulative_depth(np.array([30.0]))[0] == pytest.approx(at_30, rel=1e-12)
    assert storm.increments(5.0, 30).sum() == pytest.approx(80.0, rel=1e-12)
    assert storm.cumulative_depth(np.array([120.0, 500.0])) == pytest.approx([80.0, 80.0], rel=1e-12)


@pytest.mark.parametrize("scs_type", list(SCS_CURVES))
def test_the_scs_types_are_24_hour_curves_that_hold_the_whole_depth(scs_type) -> None:
    curve = np.asarray(SCS_CURVES[scs_type])
    assert len(curve) == len(SCS_HOURS) and curve[0] == 0.0 and curve[-1] == 1.0
    assert np.all(np.diff(curve) >= 0.0)
    storm = build_storm(_cfg({**DEPTH, "duration_min": 1440.0, "pattern": {"kind": "scs", "scs_type": scs_type}}))
    assert storm.increments(60.0, 24).sum() == pytest.approx(80.0, rel=1e-12)
    hours = np.asarray(SCS_HOURS, np.float64)
    assert storm.cumulative_depth(hours * 60.0) == pytest.approx(80.0 * curve, rel=1e-12)
    with pytest.raises(ValidationError, match="24-hour distribution"):
        _cfg({**DEPTH, "pattern": {"kind": "scs", "scs_type": scs_type}})


def test_type_ii_peaks_in_the_hour_before_noon() -> None:
    storm = build_storm(_cfg({**DEPTH, "duration_min": 1440.0, "pattern": {"kind": "scs", "scs_type": "II"}}))
    per_quarter = storm.increments(15.0, 96)
    assert int(np.argmax(per_quarter)) == 47, "11:45 to 12:00 holds the burst of the Type II curve"


def test_a_depth_grid_source_is_a_unit_storm_the_cells_multiply() -> None:
    storm = build_storm(
        _cfg({"kind": "depth_grid", "depth_grid": "d.tif", "duration_min": 60.0,
              "pattern": {"kind": "table", "values": FRONT}})
    )  # fmt: skip
    assert storm.total_depth == 1.0
    assert storm.cumulative_depth(np.array([15.0]))[0] == pytest.approx(0.6, rel=1e-12)


@pytest.mark.parametrize(
    ("storm", "words"),
    [
        ({**DEPTH, "depth_mm": 0.0}, "depth_mm above zero"),
        ({**DEPTH, "depth_grid": "d.tif"}, "kind 'depth_grid'"),
        ({"kind": "depth_grid", "duration_min": 60.0}, "needs storm.depth_grid"),
        ({"kind": "depth_grid", "depth_grid": "d.tif", "depth_mm": 50.0}, "not depth_mm"),
        ({**DEPTH, "time_percent": [0, 100], "depth_percent": [0, 100]}, "from storm.pattern"),
        ({**DEPTH, "arf": CURVE, "storm_area_km2": 50.0}, "from storm.area_reduction"),
        ({**DEPTH, "arf_factor": 0.7}, "from storm.area_reduction"),
        ({"kind": "uniform", "depth_mm": 10.0, "pattern": {"kind": "uniform"}}, "keeps its own pattern"),
        ({**DEPTH, "pattern": {"kind": "table", "values": {**FRONT, "time": [0.0, 25.0, 90.0]}}}, "ends at 100"),
        ({**DEPTH, "pattern": {"kind": "table", "values": {"time": [0.0, 1.0], "depth": [0.0, 1.0],
                                                             "time_units": "hours"}}}, "ends at 60 min"),
    ],
)  # fmt: skip
def test_a_source_that_cannot_apply_is_refused_in_words(storm, words) -> None:
    with pytest.raises(ValidationError, match=words):
        _cfg(storm)


def test_a_pattern_table_says_what_is_wrong_with_it() -> None:
    for bad, words in (
        ({"time": [0.0, 50.0], "depth": [1.0]}, "one depth per time"),
        ({"time": [0.0, 50.0, 40.0, 100.0], "depth": [0, 1, 2, 3]}, "must rise"),
        ({"time": [10.0, 100.0], "depth": [0.0, 1.0]}, "starts at time 0"),
        ({"time": [0.0, 50.0, 100.0], "depth": [0.0, 2.0, 1.0]}, "cannot fall"),
        ({"time": [0.0, 100.0], "depth": [0.0, 0.0]}, "end above zero"),
        ({"time": [0.0, 100.0], "depth": [1.0, 1.0], "form": "incremental"}, "ends after time 0"),
    ):
        with pytest.raises(ValidationError, match=words):
            PatternTable.model_validate(bad)
    with pytest.raises(ValidationError, match="scs_type alone"):
        StormPattern(kind="scs")
    with pytest.raises(ValidationError, match="takes nothing else"):
        StormPattern(kind="uniform", table="p")
    assert percent_pattern(StormPattern(), 60.0) is None


STORE = {"patterns": {"front": FRONT}, "arf_curves": {"fixed": CURVE}}
NAMED = {**DEPTH, "pattern": {"kind": "table", "table": "front"},
         "area_reduction": {"grid": {"form": "area", "curve": "fixed", "area_km2": 505.0}}}  # fmt: skip


def test_a_stored_table_is_filled_in_by_name_and_runs_as_the_one_given_inline() -> None:
    named = _cfg(NAMED, data_tables=STORE)
    assert named.storm.pattern.values == PatternTable.model_validate(FRONT)
    assert named.storm.area_reduction.grid.table.factors == [1.0, 0.5]
    inline = _cfg({**DEPTH, "pattern": {"kind": "table", "values": FRONT},
                   "area_reduction": {"grid": {"form": "area", "table": CURVE, "area_km2": 505.0}}})  # fmt: skip
    minutes = np.linspace(0.0, 120.0, 25)
    assert np.array_equal(build_storm(named).cumulative_depth(minutes), build_storm(inline).cumulative_depth(minutes))
    assert build_storm(named).total_depth == pytest.approx(80.0 * 0.75, rel=1e-12)
    again = RunConfig.model_validate(named.model_dump(mode="json"))  # config.resolved.json read back: the same job
    assert again == named


def test_a_name_the_store_does_not_hold_or_two_tables_for_one_name_is_refused() -> None:
    with pytest.raises(ValidationError, match=r"names pattern 'back'.*it holds: front"):
        _cfg({**NAMED, "pattern": {"kind": "table", "table": "back"}}, data_tables=STORE)
    with pytest.raises(ValidationError, match=r"names curve 'fixed'.*it holds: none"):
        _cfg(NAMED, data_tables={"patterns": STORE["patterns"]})
    other = {**FRONT, "depth": [0.0, 50.0, 100.0]}
    with pytest.raises(ValidationError, match="give one of the two"):
        _cfg({**NAMED, "pattern": {"kind": "table", "table": "front", "values": other}}, data_tables=STORE)


def test_a_sidecar_file_beside_the_job_adds_its_tables(tmp_path) -> None:
    (tmp_path / "tables.json").write_text(json.dumps(STORE), encoding="utf-8")
    data = job("x.tif", 8, 8, 4.0, storm=DEPTH).model_dump(mode="json")
    data["storm"] = NAMED
    data["data_tables"] = {"file": "tables.json"}
    (tmp_path / "job.json").write_text(json.dumps(data), encoding="utf-8")
    cfg = load_job(tmp_path / "job.json")
    assert cfg.data_tables.file == str((tmp_path / "tables.json").resolve())
    assert cfg.storm.area_reduction.grid.table.table_type == "test table"
    assert cfg.storm == _cfg(NAMED, data_tables=STORE).storm, "the storm holds the numbers, wherever they were kept"
    (tmp_path / "tables.json").write_text(json.dumps({**STORE, "hydrographs": {}}), encoding="utf-8")
    with pytest.raises(Exception, match="only 'patterns' and 'arf_curves'"):
        load_job(tmp_path / "job.json")
    (tmp_path / "tables.json").write_text(json.dumps({"patterns": {"front": {**FRONT, "depth": [0, 1, 2]}}}), "utf-8")
    data["data_tables"] = {"file": "tables.json", **STORE}
    (tmp_path / "job.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(Exception, match=r"in the job and in tables\.json with other numbers"):
        load_job(tmp_path / "job.json")


def test_an_old_job_keeps_its_hash_and_its_meaning(tmp_path) -> None:
    dem = write_dem(tmp_path / "d.tif", np.zeros((8, 8)), 4.0)
    storm = {"kind": "hypothetical", "depth_mm": 50.0, "duration_min": 60.0, "time_percent": [0, 100],
             "depth_percent": [0, 100], "arf": CURVE, "storm_area_km2": 50.0}  # fmt: skip
    old = job(dem, 8, 8, 4.0, storm=storm)
    data = old.model_dump(mode="json")
    for name in ("pattern", "area_reduction"):
        data["storm"].pop(name)
    data.pop("data_tables")
    assert job_hash(RunConfig.model_validate(data)) == job_hash(old)
    tables = job(dem, 8, 8, 4.0, storm=storm, data_tables=STORE)
    assert job_hash(tables) == job_hash(old), "tables nothing names change no water"
    named = job(dem, 8, 8, 4.0, storm=NAMED, data_tables=STORE)
    given = named.storm.model_dump(mode="json")
    given["pattern"]["table"] = given["area_reduction"]["grid"]["curve"] = None
    inline = job(dem, 8, 8, 4.0, storm=given)
    assert job_hash(named) == job_hash(inline), "the hash holds the numbers, not the store they came from"
    assert Storm.model_validate({"kind": "uniform", "depth_mm": 10.0}).pattern is None
