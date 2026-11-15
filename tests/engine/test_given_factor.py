"""A given area-reduction factor (W83, his word of 2026-11-15: 0.7 means a 30 % reduction): every depth times f,
on the 2D cells and the lumped network alike, with no table and no storm area; refused beside a table or a study."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from tests.engine.conftest import CRS, job
from tests.engine.test_handback import CHAIN, DX, MIDDLE, NX, NY, SINK, SUB, X0, plane, write_basin
from tests.engine.test_network_series import _polygons
from tests.engine.test_rain_run import DX as BOX_DX
from tests.engine.test_rain_run import QUICK, SIDE, TABLE, box, events, gridded, stack
from tests.hydrology.test_network import GRID, small_basin
from wadi2d.arf import check_storm
from wadi2d.config.schema import Storm
from wadi2d.engine.rain_preview import AREA_2D, rain_preview
from wadi2d.forcing import build_storm
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.run import InvalidJob, _lumped_basin, _lumped_rain, arf_tags, job_hash, run_job
from wadi2d.storm import UniformStorm
from wadi2d.storm.arf import GivenFactor
from wadi2d.storm.gridded import GriddedStorm
from wadi2d.storm.rain_frames import RainFrames

F = 0.7
UNIFORM = {"kind": "uniform", "depth_mm": 30.0, "duration_min": 30.0}
DESIGN = {"kind": "hypothetical", "depth_mm": 80.0, "duration_min": 60.0, "time_percent": [0, 50, 100],
          "depth_percent": [0, 80, 100]}  # fmt: skip


def test_the_factor_is_validated_and_refused_beside_a_table_or_an_area() -> None:
    assert Storm.model_validate({**UNIFORM, "arf_factor": 1.0}).arf_factor == 1.0
    for bad in (0.0, -0.1, 1.2):
        with pytest.raises(ValidationError):
            Storm.model_validate({**UNIFORM, "arf_factor": bad})
    for extra in ({"arf": TABLE}, {"storm_area_km2": 50.0}, {"arf": TABLE, "storm_area_km2": 50.0}):
        with pytest.raises(ValidationError, match="not both"):
            Storm.model_validate({**DESIGN, "arf_factor": F, **extra})
    table = {"kind": "hyetograph", "hyetograph_min": [30.0], "hyetograph_mm": [10.0], "arf_factor": F}
    with pytest.raises(ValidationError, match="takes no area reduction"):
        Storm.model_validate(table)
    with pytest.raises(ValidationError, match="takes no area reduction"):
        Storm.model_validate({"kind": "none", "arf_factor": F})
    with pytest.raises(ValueError):
        GivenFactor(0.0)


def test_every_storm_that_takes_a_reduction_takes_the_factor_at_any_area(tmp_path) -> None:
    uniform = build_storm(job("x.tif", 8, 8, 4.0, storm={**UNIFORM, "arf_factor": F}))
    assert uniform.total_depth == 30.0 * F
    assert uniform.at_area(5.0).total_depth == uniform.at_area(5000.0).total_depth == 30.0 * F
    design = build_storm(job("x.tif", 8, 8, 4.0, storm={**DESIGN, "arf_factor": F}))
    assert design.area_factor == F and design.total_depth == 80.0 * F
    assert design.at_area(900.0).area_factor == F
    folder = stack(tmp_path, 40.0, 10.0)
    grid = build_storm(job("x.tif", 8, 8, 4.0, storm=gridded(folder, arf_factor=F)))
    whole = build_storm(job("x.tif", 8, 8, 4.0, storm=gridded(folder)))
    assert grid.area_factor == F and grid.at_area(3.0).area_factor == F
    assert grid.total_depth == pytest.approx(F * whole.total_depth, rel=1e-15)  # the frames are float32: not 17.5


@pytest.mark.parametrize("storm", [UNIFORM, "gridded"])
def test_the_run_rains_f_times_the_whole_storm_and_says_so(tmp_path, storm) -> None:
    dem = box(tmp_path)
    storm = gridded(stack(tmp_path, 40.0, 10.0)) if storm == "gridded" else storm
    plain = run_job(job(dem, SIDE, SIDE, BOX_DX, storm=storm, run=QUICK), tmp_path / "plain")
    given = job(dem, SIDE, SIDE, BOX_DX, storm={**storm, "arf_factor": F}, run=QUICK)
    run = run_job(given, tmp_path / "given")
    assert run.exit_code == plain.exit_code == 0
    assert run.balance.rain == pytest.approx(F * plain.balance.rain, rel=1e-6)
    said = [e for e in events(tmp_path / "given") if e.get("kind") == "area_reduction"]
    assert [(e["factor"], e["storm_area_km2"], e["arf_table_type"]) for e in said] == [(F, None, "given")]
    words = [e["message"] for e in events(tmp_path / "given") if e.get("ev") == "warn"]
    assert "rain: every depth is multiplied by 0.7000, the given area-reduction factor, over the whole event" in words
    assert not any("area-reduction table" in w for w in words)
    resolved = (tmp_path / "given" / "config.resolved.json").read_text(encoding="utf-8")
    assert '"arf_factor": 0.7' in resolved
    assert arf_tags(given) == {"arf_table_type": "given", "arf_factor": "0.7"}
    assert not [e for e in events(tmp_path / "plain") if e.get("kind") == "area_reduction"]


def test_the_lumped_network_takes_f_times_the_rain() -> None:
    from shapely.geometry import box as rectangle

    steps = 12
    starts = 5.0 * np.arange(steps)
    frames = RainFrames(np.full((steps, 1, 3), 10.0 / steps), starts, starts + 5.0, 0.0, 3000.0, 1000.0, 3000.0, CRS)
    polygons = {name: rectangle(100.0, 100.0, 2500.0, 2500.0) for name in ("A", "B", "C")}
    given = GivenFactor(F)
    whole = LumpedEngine(small_basin()).run(GriddedStorm(frames).bind(polygons, CRS), GRID)
    grid = LumpedEngine(small_basin()).run(GriddedStorm(frames, arf=given).bind(polygons, CRS), GRID)
    design = LumpedEngine(small_basin()).run(UniformStorm(10.0, 60.0, arf=given), GRID)
    assert grid.outflow["OUT"] == pytest.approx(design.outflow["OUT"], rel=1e-9)
    assert grid.outflow["OUT"] == pytest.approx(F * whole.outflow["OUT"], rel=1e-9), "no losses: linear"


def test_preview_and_network_read_the_factor_on_a_lumped_subbasin_and_the_2d_area(tmp_path) -> None:
    wide = SUB.replace("Subbasin: Side", "Subbasin: Wide").format(down="J")
    basin = write_basin(tmp_path, SUB.format(down="J"), wide, CHAIN, SINK)
    cfg = job(
        plane(tmp_path), NX, NY, DX, storm={**DESIGN, "depth_mm": 50.0, "arf_factor": F},
        hydrology={
            "hms_basin": str(basin), "time_step_min": 5.0, "inject_radius": 6.0, "polygons": str(_polygons(tmp_path)),
            "subbasins": [{"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE)}, {"name": "Wide", "mode": "2d"}],
        },
        run={"duration_s": 7200.0, "backend": "cpu"},
    )  # fmt: skip
    found = rain_preview(cfg)
    assert found["arf_factor"] == F and found["area_factor"] == F and found["storm_area_km2"] is None
    side, two_d = found["areas"]
    assert two_d["name"] == AREA_2D
    assert side["depth_mm"] == pytest.approx(50.0 * F, rel=1e-6) == pytest.approx(two_d["depth_mm"], rel=1e-6)
    basin_model, hms, _cut = _lumped_basin(cfg, "")
    network = _lumped_rain(cfg, build_storm(cfg), basin_model, hms, "").over("Side")
    assert network.total_depth == pytest.approx(50.0 * F, rel=1e-9)


def test_a_study_refuses_the_factor_in_words() -> None:
    cfg = job("x.tif", 8, 8, 4.0, storm={**DESIGN, "arf_factor": F})
    with pytest.raises(InvalidJob, match="choose the study or the given factor"):
        check_storm(cfg)


def test_an_old_job_keeps_its_hash_and_a_factor_changes_it(tmp_path) -> None:
    dem = box(tmp_path)
    old = job(dem, SIDE, SIDE, BOX_DX, storm=UNIFORM, run=QUICK)
    data = old.model_dump(mode="json")
    assert data["storm"]["arf_factor"] is None
    assert job_hash(old) == job_hash(job(dem, SIDE, SIDE, BOX_DX, storm={**UNIFORM, "arf_factor": None}, run=QUICK))
    assert job_hash(job(dem, SIDE, SIDE, BOX_DX, storm={**UNIFORM, "arf_factor": F}, run=QUICK)) != job_hash(old)
