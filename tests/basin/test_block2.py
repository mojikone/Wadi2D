"""The command's model on real ground, one small catchment of Block 2, read-only. The whole catchment is `W24 basin model`."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from wadi2d.basin import load_network
from wadi2d.basin.build import assemble
from wadi2d.basin.contract import value_of
from wadi2d.config.schema import BasinSettings
from wadi2d.run import load_job

pytestmark = pytest.mark.data

JOB = Path(__file__).parents[2] / "W24 basin model" / "jobs" / "dam_Bidah03.json"
HMS_AREA_KM2 = 20.971
AXIS_SHARE = 0.96
"""About 4 % of the HMS polygon of S13 lies past the axis (`validation/block2_full.md`), so it never crosses it."""
FSL = 100.0
SPILLWAY_LENGTH = 72.0


@pytest.fixture(scope="module")
def dam(block2_dir: Path) -> dict:
    model = assemble(load_job(JOB), BasinSettings()).model
    return next(e for e in model["elements"] if e["kind"] == "reservoir") | {"model": model}


def test_the_dam_reads_the_area_above_its_axis(dam: dict) -> None:
    assert value_of(dam, "drainage_area_km2") == pytest.approx(AXIS_SHARE * HMS_AREA_KM2, rel=0.01)


def test_the_pool_reads_the_dam_teams_curve(dam: dict, block2_dir: Path) -> None:
    file = block2_dir / "Hydrology" / "SHP" / "Block 2 Dams" / "EAV" / "Bidah 03 EAV.csv"
    with open(file, encoding="utf-8-sig", newline="") as source:
        rows = np.array(list(csv.reader(source))[1:], dtype=np.float64)
    volume = np.interp(FSL, rows[:, 1], rows[:, 2])
    made = np.interp(FSL, value_of(dam, "elevation_m"), value_of(dam, "volume_m3"))
    assert made == pytest.approx(volume, rel=0.01)


def test_the_network_loads_with_the_job_spillway(dam: dict) -> None:
    assert value_of(dam, "spillways")[0]["crest_length_m"] == SPILLWAY_LENGTH
    assert dam["name"] in load_network(dam["model"]).elements
