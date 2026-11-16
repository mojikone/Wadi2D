"""The four kinds of run as a saved setting, checked against the job; old jobs infer theirs (W96)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
from wadi2d.config.model_type import inferred_type, model_type
from wadi2d.config.schema import RunConfig
from wadi2d.run import job_hash

LUMPED_SUB = {"subbasins": [{"name": "S1", "mode": "lumped", "outlet": (X0 + 10.0, Y0 - 10.0)}]}


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    return write_dem(tmp_path / "dem.tif", tilted_box(40, 40, 2.0, 0.01), 2.0)


def test_old_jobs_infer_their_type_from_what_they_hold(dem) -> None:
    assert model_type(job(dem, 10, 10, 8.0)) == "2d"
    assert model_type(job(dem, 10, 10, 8.0, hydrology=LUMPED_SUB)) == "hybrid_2d"
    assert model_type(job(dem, 10, 10, 8.0, hydrology=LUMPED_SUB, grid={"exclude_lumped": True})) == "hybrid_lumped"
    lumped = RunConfig.model_validate({"run": {"lumped_only": True}, "hydrology": {"hms_basin": "b.basin"}})
    assert model_type(lumped) == "lumped"
    hms_for_cn_only = job(dem, 10, 10, 8.0, hydrology={"hms_basin": "b.basin", "subbasins": [{"name": "S1", "mode": "2d"}]})
    assert model_type(hms_for_cn_only) == "2d"


def test_a_type_sets_what_it_implies_where_the_job_is_silent(dem) -> None:
    hybrid = job(dem, 10, 10, 8.0, hydrology=LUMPED_SUB, run={"model_type": "hybrid_lumped"})
    assert hybrid.grid.exclude_lumped and model_type(hybrid) == inferred_type(hybrid) == "hybrid_lumped"
    lumped = RunConfig.model_validate({"run": {"model_type": "lumped"}, "hydrology": {"hms_basin": "b.basin"}})
    assert lumped.run.lumped_only


@pytest.mark.parametrize(
    ("kind", "parts", "words"),
    [
        ("2d", {"hydrology": LUMPED_SUB}, "has no lumped part"),
        ("2d", {"grid": {"exclude_lumped": True}}, "leaves no catchment out"),
        ("hybrid_2d", {}, "needs a lumped part"),
        ("hybrid_2d", {"hydrology": LUMPED_SUB, "grid": {"exclude_lumped": True}}, "choose Hybrid Lumped"),
        ("hybrid_lumped", {"hydrology": LUMPED_SUB, "grid": {"exclude_lumped": False}}, "exclude_lumped must be on"),
        ("lumped", {"run": {"lumped_only": False}}, "run.lumped_only must be on"),
    ],
)
def test_a_type_that_does_not_fit_the_job_is_refused_in_words(dem, kind, parts, words) -> None:
    run = {"model_type": kind, **parts.pop("run", {})}
    with pytest.raises(ValidationError, match=words):
        job(dem, 10, 10, 8.0, run=run, **parts)


def test_a_grid_type_needs_a_domain_and_a_lumped_one_a_network() -> None:
    with pytest.raises(ValidationError, match=r"needs terrain\.dem"):
        RunConfig.model_validate({"run": {"model_type": "2d"}, "grid": {"extent": (0.0, 0.0, 1.0, 1.0)}})
    with pytest.raises(ValidationError, match="needs a domain"):
        RunConfig.model_validate({"run": {"model_type": "2d"}, "terrain": {"dem": "d.tif"}})
    with pytest.raises(ValidationError, match="needs a lumped network"):
        RunConfig.model_validate({"run": {"model_type": "lumped"}})


def test_the_type_changes_no_hash(dem) -> None:
    plain = job(dem, 10, 10, 8.0, hydrology=LUMPED_SUB)
    typed = job(dem, 10, 10, 8.0, hydrology=LUMPED_SUB, run={"model_type": "hybrid_2d"})
    assert job_hash(plain) == job_hash(typed)
