"""The conserving variant on Block 2's eight reaches with HMS's own inflows. Reads the project; writes nothing.

The HMS path's replication is ``test_block2_replication.py``, untouched; here the same reaches are built with the
job's other choice and must close their volume. Peaks and timings against the HMS path are recorded by
``W29 conserving routing/block2_reaches.py``, not asserted.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.hydrology.test_block2_replication import ANALYSIS, REACHES, STEP_MINUTES
from tests.hydrology.test_conserving_routing import DIP, DRAINED, IDENTITY, TAIL_HOURS, triangle, volume
from wadi2d.config.schema import REACH_CONSERVING, REACH_HMS
from wadi2d.hms import daa_fpart, load_basin, open_dss
from wadi2d.hydrology.from_hms import basin_from_hms

pytestmark = pytest.mark.data

SHORT_FLOOD_PEAK = 80.0
"""The 20-minute triangle on which the HMS path reads 1.91 x the inflow volume on R1 (W25)."""
HMS_GAIN_ON_R1 = 1.5


@pytest.fixture(scope="module")
def reaches(hms_project_dir: Path) -> dict[str, tuple]:
    """Every reach's HMS inflow and its routing under both schemes."""
    hms_basin = load_basin(hms_project_dir / "Basin_1.basin")
    faithful = basin_from_hms(hms_basin, reach_routing=REACH_HMS)
    conserving = basin_from_hms(hms_basin, reach_routing=REACH_CONSERVING)
    out = {}
    with open_dss(hms_project_dir / "DA_100yr_B1.dss") as dss:
        for name in REACHES:
            inflow = dss.read_timeseries(name, "FLOW-COMBINE", daa_fpart(ANALYSIS, name)).values
            tail = np.zeros(int(TAIL_HOURS * 60.0 / STEP_MINUTES))
            out[name] = (np.r_[0.0, inflow, tail], faithful.elements[name].routing, conserving.elements[name].routing)
    return out


@pytest.mark.parametrize("name", REACHES)
def test_every_reach_closes_its_volume_with_the_hms_inflow(reaches: dict, name: str) -> None:
    inflow, _faithful, conserving = reaches[name]
    outflow, storage = conserving.route_conserving(inflow, STEP_MINUTES)
    entered = volume(inflow, STEP_MINUTES)
    assert abs(entered - volume(outflow, STEP_MINUTES) - storage) < IDENTITY * entered
    assert abs(volume(outflow, STEP_MINUTES) / entered - 1.0) < DRAINED
    assert outflow.min() >= -DIP * inflow.max()


def test_r1_on_the_short_flood_where_the_hms_path_reads_nearly_twice_the_volume(reaches: dict) -> None:
    _inflow, faithful, conserving = reaches["R1"]
    short = triangle(SHORT_FLOOD_PEAK, STEP_MINUTES)
    entered = volume(short, STEP_MINUTES)
    assert volume(faithful.route(short, STEP_MINUTES), STEP_MINUTES) / entered > HMS_GAIN_ON_R1
    assert abs(volume(conserving.route(short, STEP_MINUTES), STEP_MINUTES) / entered - 1.0) < DRAINED


def test_the_schemes_differ_in_volume_and_not_in_the_cells(reaches: dict) -> None:
    for name, (_inflow, faithful, conserving) in reaches.items():
        assert faithful.grid(STEP_MINUTES * 60.0) == conserving.grid(STEP_MINUTES * 60.0), name
        assert faithful.scheme == REACH_HMS and conserving.scheme == REACH_CONSERVING
