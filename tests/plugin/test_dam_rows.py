"""The dam start table and the initial water of the dock, without Qt, and the job they make (W34)."""

from __future__ import annotations

from pathlib import Path

from wadi2d_qgis.dam_rows import (
    START_LEVEL,
    START_SPILLWAY,
    DamRow,
    dam_levels,
    dam_names,
    dam_problems,
    initial_problems,
    merge_dams,
)
from wadi2d_qgis.job_builder import Feature, build_job, problems

from tests.plugin.test_contract import full_values
from wadi2d.config import schema as config

RING = [[[400000.0, 2699000.0], [400500.0, 2699000.0], [400500.0, 2699500.0], [400000.0, 2699000.0]]]


def test_named_lines_are_dams_once_each_and_a_nameless_one_is_none() -> None:
    assert dam_names(["Dam A", None, " ", "Dam B", "Dam A", 3]) == ["Dam A", "Dam B", "3"]


def test_a_dam_keeps_its_choice_while_the_layer_changes_and_a_new_one_starts_empty() -> None:
    old = [DamRow("Dam A", START_SPILLWAY), DamRow("Gone", START_LEVEL, 99.0)]
    rows = merge_dams(["Dam A", "Dam B"], old)
    assert [(r.name, r.start) for r in rows] == [("Dam A", "spillway"), ("Dam B", "empty")]


def test_only_a_dam_that_does_not_start_empty_reaches_the_job() -> None:
    rows = [DamRow("A"), DamRow("B", START_SPILLWAY), DamRow("C", START_LEVEL, 101.5), DamRow("D", START_LEVEL)]
    assert dam_levels(rows) == [{"name": "B", "start": "spillway"}, {"name": "C", "start": 101.5}]
    assert dam_problems(rows) == ["Dam D starts at a level: type the level."]


def test_the_dock_job_carries_dam_starts_and_initial_water_and_the_engine_takes_them(tmp_path: Path) -> None:
    ponds = [Feature("Polygon", RING, {"level": 498.5})]
    values = full_values(tmp_path, dam_levels=[{"name": "Dam A", "start": "spillway"}], initial_water=ponds)
    job = build_job(values, tmp_path / "out")
    parsed = config.RunConfig.model_validate(job)
    assert parsed.dam_levels[0].name == "Dam A" and parsed.dam_levels[0].start == "spillway"
    assert parsed.initial_levels[0].level == 498.5 and len(parsed.initial_levels[0].coordinates) == 4
    assert (tmp_path / "out" / "inputs" / "initial_water.geojson").is_file()
    plain = config.RunConfig.model_validate(build_job(full_values(tmp_path), tmp_path / "plain"))
    assert plain.dam_levels == [] and plain.initial_levels == []


def test_a_pond_without_a_level_or_a_dam_without_one_stops_the_run_in_words(tmp_path: Path) -> None:
    pond = Feature("Polygon", RING, {"level": None})
    assert initial_problems([pond]) == ["Every initial water polygon needs a level: choose the field that holds it."]
    found = problems(full_values(tmp_path, initial_water=[pond], dam_rows=[DamRow("X", START_LEVEL)], output="o"))
    assert "Dam X starts at a level: type the level." in found
    assert any("initial water" in text for text in found)
