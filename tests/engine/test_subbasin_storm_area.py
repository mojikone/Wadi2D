"""A lumped subbasin at a storm area of its own (W79, his rule of 2026-11-15: a subbasin above a dam reads the ARF at
the dam's drainage area, as HMS's depth-area analysis at the dam does; the 2D cells and the rest at the storm's area).
The rain and the hydrograph of that subbasin scale by the table's factor at its own area, nothing else moves, and a
job without it keeps its hash."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from tests.engine.conftest import job
from tests.engine.test_handback import CHAIN, DX, MIDDLE, NX, NY, SINK, SUB, X0, plane, write_basin
from tests.engine.test_network_series import _polygons
from tests.hydrology.test_network import GRID, small_basin
from wadi2d.arf import check_storm
from wadi2d.config.schema import Subbasin
from wadi2d.forcing import build_storm
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.run import InvalidJob, _lumped_basin, _lumped_rain, job_hash, run_job
from wadi2d.storm import ArfTable, UniformStorm
from wadi2d.storm.own_area import OwnAreas

TABLE = {"areas_km2": [10.0, 1000.0], "factors": [1.0, 0.5], "table_type": "test table"}
STORM_AREA, OWN_AREA = 10.0, 505.0
AT_STORM, AT_OWN = 1.0, 0.75
"""The table's factors at the two areas."""
DESIGN = {"kind": "hypothetical", "depth_mm": 50.0, "duration_min": 60.0, "time_percent": [0, 50, 100],
          "depth_percent": [0, 80, 100], "arf": TABLE, "storm_area_km2": STORM_AREA}  # fmt: skip


def _job(tmp_path, own: float | None, storm: dict = DESIGN, **extra):
    wide = SUB.replace("Subbasin: Side", "Subbasin: Wide").format(down="J")
    basin = write_basin(tmp_path, SUB.format(down="J"), wide, CHAIN, SINK)
    side = {"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE), "storm_area_km2": own, **extra}
    return job(
        plane(tmp_path), NX, NY, DX, storm=storm,
        hydrology={
            "hms_basin": str(basin), "time_step_min": 5.0, "inject_radius": 6.0, "polygons": str(_polygons(tmp_path)),
            "subbasins": [side, {"name": "Wide", "mode": "2d"}],
        },
        run={"duration_s": 7200.0, "backend": "cpu"},
    )  # fmt: skip


def test_the_area_is_for_a_lumped_subbasin_beside_a_table(tmp_path) -> None:
    assert Subbasin(name="S", storm_area_km2=74.3).storm_area_km2 == 74.3
    with pytest.raises(ValidationError, match="2D subbasin"):
        Subbasin(name="S", mode="2d", storm_area_km2=74.3)
    with pytest.raises(ValidationError):
        Subbasin(name="S", storm_area_km2=0.0)
    with pytest.raises(ValidationError, match=r"needs storm.arf"):
        _job(
            tmp_path, OWN_AREA, storm={k: v for k, v in DESIGN.items() if k not in ("arf", "storm_area_km2")}
        )
    given = {**{k: v for k, v in DESIGN.items() if k not in ("arf", "storm_area_km2")}, "arf_factor": 0.8}
    with pytest.raises(ValidationError, match=r"no storm.arf_factor"):
        _job(tmp_path, OWN_AREA, storm=given)


def test_only_the_named_subbasin_reads_its_own_area() -> None:
    storm = UniformStorm(10.0, 60.0, storm_area_km2=STORM_AREA, arf=ArfTable([10.0, 1000.0], [1.0, 0.5]))
    base = LumpedEngine(small_basin()).run(storm, GRID)
    own = LumpedEngine(small_basin()).run(OwnAreas(storm, {"A": OWN_AREA}), GRID)
    assert own.water["A"].precipitation == pytest.approx(AT_OWN * base.water["A"].precipitation, rel=1e-12)
    assert np.array_equal(own.water["B"].precipitation, base.water["B"].precipitation)
    assert np.array_equal(own.outflow["C"], base.outflow["C"])
    assert own.outflow["A"] == pytest.approx(AT_OWN * base.outflow["A"], rel=1e-9), "no losses: linear"
    later = OwnAreas(storm, {"A": OWN_AREA}).at_area(1000.0)
    assert later.over("A").total_depth == pytest.approx(10.0 * AT_OWN) and later.over("B").total_depth == 5.0


def test_the_network_takes_it_and_an_unknown_name_is_refused(tmp_path) -> None:
    cfg = _job(tmp_path, OWN_AREA)
    basin, hms, _cut = _lumped_basin(cfg, "")
    rain = _lumped_rain(cfg, build_storm(cfg), basin, hms, "")
    assert rain.over("Side").total_depth == pytest.approx(50.0 * AT_OWN, rel=1e-12)
    assert rain.over("Wide").total_depth == pytest.approx(50.0 * AT_STORM, rel=1e-12)
    data = cfg.model_dump(mode="json")
    data["hydrology"]["subbasins"].append({"name": "Nowhere", "mode": "lumped", "storm_area_km2": 3.0})
    with pytest.raises(InvalidJob, match="Nowhere"):
        _lumped_rain(type(cfg).model_validate(data), build_storm(cfg), basin, hms, "")


def test_the_run_moves_that_hydrograph_alone_and_says_so(tmp_path) -> None:
    plain = run_job(_job(tmp_path, None), tmp_path / "plain")
    own = run_job(_job(tmp_path, OWN_AREA), tmp_path / "own")
    assert plain.exit_code == own.exit_code == 0
    assert own.balance.rain == pytest.approx(plain.balance.rain, rel=1e-12), "the 2D cells keep the storm's area"
    assert own.balance.inflow == pytest.approx(AT_OWN * plain.balance.inflow, rel=1e-6), "CN 100: linear"
    events = (tmp_path / "own" / "progress.jsonl").read_text(encoding="utf-8")
    assert '"kind": "subbasin_storm_areas"' in events and "Side 505" in events
    assert "subbasin_storm_areas" not in (tmp_path / "plain" / "progress.jsonl").read_text(encoding="utf-8")


def test_a_study_refuses_it_and_an_old_job_keeps_its_hash(tmp_path) -> None:
    with pytest.raises(InvalidJob, match="choose the study or their areas"):
        check_storm(_job(tmp_path, OWN_AREA))
    old = _job(tmp_path, None)
    assert (
        "storm_area_km2"
        not in old.model_dump(mode="json", exclude_defaults=True)["hydrology"]["subbasins"][0]
    )
    assert job_hash(old) != job_hash(_job(tmp_path, OWN_AREA))
    data = old.model_dump(mode="json")
    data["hydrology"]["subbasins"][0].pop("storm_area_km2")
    assert job_hash(type(old).model_validate(data)) == job_hash(old)
