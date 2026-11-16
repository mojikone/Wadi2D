"""A flow line's hydrograph as an interval and a list of flows, HEC-RAS's table entry (W96)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.engine.conftest import tilted_box, write_dem
from tests.engine.test_inflow_lines import SLOPE, WEST, flow_line, plane_job
from wadi2d.config.schema import FlowHydrograph
from wadi2d.run import job_hash, run_job


@pytest.fixture
def plane(tmp_path):
    """The plane of test_inflow_lines: 400 x 96 m falling 1 % east."""
    return write_dem(tmp_path / "plane.tif", tilted_box(200, 48, 2.0, SLOPE), 2.0)


def test_a_step_and_a_list_write_out_their_times_and_refuse_a_mix() -> None:
    f = FlowHydrograph(step_s=300.0, flows=[0.0, 2.0, 2.0, 0.0])
    assert f.table() == ([0.0, 300.0, 600.0, 900.0], [0.0, 2.0, 2.0, 0.0])
    assert FlowHydrograph(times_s=[0.0, 60.0], flows=[1.0, 1.0]).table() == ([0.0, 60.0], [1.0, 1.0])
    assert FlowHydrograph(file="q.csv").table() is None
    for bad in (
        {"step_s": 300.0, "times_s": [0.0, 300.0], "flows": [1.0, 1.0]},
        {"step_s": 300.0, "flows": [1.0]},
        {"step_s": 300.0},
        {"step_s": 0.0, "flows": [1.0, 1.0]},
        {"step_s": 300.0, "flows": [1.0, 1.0], "file": "q.csv"},
    ):
        with pytest.raises(ValidationError):
            FlowHydrograph(**bad)


def test_a_line_without_a_step_keeps_its_hash_and_a_step_table_hashes_as_its_times(plane) -> None:
    times = plane_job(plane, flow_line(WEST, times_s=[0.0, 300.0, 600.0], flows=[0.0, 2.0, 0.0]), 900.0)
    step = plane_job(plane, flow_line(WEST, step_s=300.0, flows=[0.0, 2.0, 0.0]), 900.0)
    dumped = times.model_dump(mode="json")["boundaries"][0]["flow"]
    assert dumped["step_s"] is None  # in the job as written, and popped from the hash below
    assert job_hash(times) != job_hash(step)  # two ways of writing a table are two jobs to a checkpoint


def test_the_step_table_enters_as_the_same_table_of_times_does(plane, tmp_path) -> None:
    flows = [0.0, 2.0, 2.0, 0.0]
    a = run_job(plane_job(plane, flow_line(WEST, step_s=300.0, flows=flows), 1200.0), tmp_path / "a")
    b = run_job(plane_job(plane, flow_line(WEST, times_s=[0.0, 300.0, 600.0, 900.0], flows=flows), 1200.0), tmp_path / "b")
    assert a.exit_code == b.exit_code == 0, a.message
    assert a.balance.inflow == pytest.approx(2.0 * (150.0 + 300.0 + 150.0), rel=1e-6)
    assert a.balance.inflow == b.balance.inflow and a.balance.storage == b.balance.storage
