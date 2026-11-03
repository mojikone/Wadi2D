"""The face discharges saved with each map: what a run writes, what a line reads from them, and what happens without them."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import h5py
import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
from wadi2d.config.schema import RunConfig
from wadi2d.forcing import line_faces
from wadi2d.grid.tiles import TileGrid
from wadi2d.io.results import FACE_FIELDS
from wadi2d.products.face_flow import (
    FLOW_ESTIMATE,
    FLOW_FACES,
    FaceCrossing,
    face_crossing,
    face_flow,
    frames_have_faces,
)
from wadi2d.products.frames import frame_names
from wadi2d.products.result_lines import catalogue, read_line
from wadi2d.run import EXIT_STOPPED, job_hash, run_job
from wadi2d.solver.layout import TILE
from wadi2d.solver.state import state_index

SIZE = 40
DX = 5.0
WIDE = SIZE * DX
MIDDLE_X = X0 + WIDE / 2.0
ACROSS = [(MIDDLE_X, Y0 - 2.5), (MIDDLE_X, Y0 - WIDE + 2.5)]
OBLIQUE = [(MIDDLE_X - 40.0, Y0 - 2.5), (MIDDLE_X + 40.0, Y0 - WIDE + 2.5)]
BENT = [(MIDDLE_X - 30.0, Y0 - 2.5), (MIDDLE_X + 20.0, Y0 - WIDE / 2.0), (MIDDLE_X - 30.0, Y0 - WIDE + 2.5)]
EVERY_S = 60.0
"""Maps and series on the same steps, so the two readings fall on the same instants."""
STOP_AFTER_S = 0.4
LONG_S = 3600.0
"""Long enough for the stop to land inside the run on a loaded machine."""


def plane_job(tmp_path: Path, duration_s: float = 600.0, **outputs) -> RunConfig:
    """Rain on a plane falling east, out through the east edge, with three upfront lines across it."""
    dem = write_dem(tmp_path / "dem.tif", tilted_box(SIZE, SIZE, DX, 0.02), DX)
    east = X0 + WIDE - DX / 2.0
    lines = [{"name": name, "coordinates": c} for name, c in (("across", ACROSS), ("oblique", OBLIQUE), ("bent", BENT))]
    return job(
        dem, SIZE, SIZE, DX,
        run={"duration_s": duration_s},
        storm={"kind": "uniform", "depth_mm": 300.0, "duration_min": 10.0},
        boundaries=[{"kind": "normal", "slope": 0.02, "coordinates": [(east, Y0), (east, Y0 - WIDE)]}],
        outputs={
            "map_every_s": EVERY_S, "series_every_s": EVERY_S, "pixels": {"enabled": False}, "lines": lines, **outputs,
        },
    )  # fmt: skip


@pytest.fixture
def finished(tmp_path: Path) -> Path:
    assert run_job(plane_job(tmp_path), tmp_path / "run").exit_code == 0
    return tmp_path / "run"


def map_times(run: Path) -> np.ndarray:
    """When each map was taken, to the step; a frame's name holds whole seconds only."""
    with h5py.File(run / "results.h5", "r") as f:
        return np.array([float(f["maps"][name].attrs["t_s"]) for name in frame_names(run / "results.h5")])


def record_at_frames(run: Path, name: str, t_s=None) -> np.ndarray:
    """The upfront line's series at the instants of the maps; the two fall on the same steps here."""
    line = next(item for item in catalogue(run)["lines"] if item["name"] == name)
    return np.interp(map_times(run) if t_s is None else t_s, line["t_s"], line["discharge_m3s"])


# the writer


def test_a_run_saves_both_face_discharges_with_every_map(finished: Path) -> None:
    with h5py.File(finished / "results.h5", "r") as f:
        names = frame_names(finished / "results.h5")
        assert len(names) >= 10
        for name in names:
            group = f["maps"][name]
            for field in FACE_FIELDS:
                assert group[field].dtype == np.float32
                assert group[field].shape == f["mask"].shape
        assert frames_have_faces(f, names)
        late = f["maps"][names[-1]]
        assert float(late["qx"][:].max()) > 0.0  # eastward through west faces
        assert float(np.abs(late["qy"][:]).max()) < float(late["qx"][:].max())  # a plane falling east


@pytest.mark.gpu
def test_the_gpu_saves_the_same_face_discharges_and_the_line_reads_its_record(tmp_path: Path) -> None:
    data = plane_job(tmp_path).model_dump(mode="json")
    data["run"]["backend"] = "gpu"
    cfg = RunConfig.model_validate(data)
    assert run_job(cfg, tmp_path / "gpu").exit_code == 0
    found = read_line(tmp_path / "gpu", ACROSS)
    assert found["flow_source"] == FLOW_FACES
    at_frames = record_at_frames(tmp_path / "gpu", "across")
    running = np.abs(at_frames) > 0.25 * np.abs(at_frames).max()
    assert np.array(found["flow_m3s"])[running] == pytest.approx(at_frames[running], rel=0.01)


def test_the_setting_does_not_change_the_water_or_the_job_hash(tmp_path: Path) -> None:
    on = plane_job(tmp_path)
    off = plane_job(tmp_path, face_discharge=False)
    assert on.outputs.face_discharge and not off.outputs.face_discharge
    assert job_hash(on) == job_hash(off)


# the reader


@pytest.mark.parametrize("name, coordinates", [("across", ACROSS), ("oblique", OBLIQUE), ("bent", BENT)])
def test_a_line_reads_the_upfront_line_at_the_frames_sign_included(finished: Path, name: str, coordinates) -> None:
    found = read_line(finished, coordinates, name)
    assert found["flow_source"] == FLOW_FACES
    at_frames = record_at_frames(finished, name)
    flow = np.array(found["flow_m3s"])
    running = np.abs(at_frames) > 0.25 * np.abs(at_frames).max()
    assert running.sum() >= 3
    assert flow[running] == pytest.approx(at_frames[running], abs=2e-3, rel=1e-6)
    assert np.sign(flow[running]).tolist() == np.sign(at_frames[running]).tolist()


def test_the_crossing_is_the_staircase_of_an_upfront_line(finished: Path) -> None:
    with h5py.File(finished / "results.h5", "r") as f:
        mask = f["mask"][:]
        x0, y0, dx = (float(f.attrs[key]) for key in ("x0", "y0", "dx"))
    grid = TileGrid(x0, y0, dx, mask)
    tiles = np.ones((mask.shape[0] // TILE + 1, mask.shape[1] // TILE + 1), np.int64)
    for coordinates in (ACROSS, OBLIQUE, BENT):
        crossing = face_crossing(mask, x0, y0, dx, coordinates, tiles)
        upfront = line_faces(grid, coordinates)
        assert state_index(grid, crossing.x_rows, crossing.x_columns).tolist() == upfront.xfaces.tolist()
        assert state_index(grid, crossing.y_rows, crossing.y_columns).tolist() == upfront.yfaces.tolist()
        assert crossing.x_weight.tolist() == upfront.xsign.tolist()
        assert crossing.y_weight.tolist() == upfront.ysign.tolist()
        assert crossing.count > 0


def test_the_sum_is_signed_to_the_right_of_the_line() -> None:
    crossing = FaceCrossing(
        np.array([0, 1]), np.array([3, 3]), np.array([-1.0, -1.0]), np.array([5]), np.array([2]), np.array([1.0])
    )
    assert face_flow(np.array([2.0, 3.0], np.float32), np.array([0.5], np.float32), crossing) == pytest.approx(-4.5)
    assert face_flow(np.zeros(2, np.float32), np.zeros(1, np.float32), crossing) == 0.0


def test_on_a_quadtree_only_the_edges_on_a_coarse_face_count_each_a_share_of_it() -> None:
    """Four tiles, the eastern two of cells twice the size: a line across them reads each coarse face once."""
    mask = np.ones((TILE * 2, TILE * 2), bool)
    tiles = np.ones((3, 3), np.int64)
    tiles[:, 1] = 2
    x0, y0, dx = 0.0, TILE * 2 * DX, DX
    fine = face_crossing(mask, x0, y0, dx, [(10.0 * DX, y0 - DX), (10.0 * DX, y0 - TILE * DX)], tiles)
    coarse_face = face_crossing(mask, x0, y0, dx, [(42.0 * DX, y0 - DX), (42.0 * DX, y0 - TILE * DX)], tiles)
    inside = face_crossing(mask, x0, y0, dx, [(43.0 * DX, y0 - DX), (43.0 * DX, y0 - TILE * DX)], tiles)
    assert fine.count == TILE - 1 and (np.abs(fine.x_weight) == 1.0).all()
    assert coarse_face.count == TILE - 1 and (np.abs(coarse_face.x_weight) == 0.5).all()
    assert inside.count == 0
    painted = np.zeros(mask.shape, np.float32)
    painted[:, 42:44] = 6.0  # one coarse column of cells, each face carrying 6 m3/s painted on both finest cells
    assert abs(face_flow(painted[coarse_face.x_rows, coarse_face.x_columns], np.zeros(0), coarse_face)) == pytest.approx(
        6.0 * (TILE - 1) / 2.0
    )


# without the faces


def test_a_run_that_kept_no_faces_falls_back_to_the_estimate_and_says_so(tmp_path: Path) -> None:
    assert run_job(plane_job(tmp_path, face_discharge=False), tmp_path / "run").exit_code == 0
    with h5py.File(tmp_path / "run" / "results.h5", "r") as f:
        names = frame_names(tmp_path / "run" / "results.h5")
        assert not frames_have_faces(f, names)
        assert all(field not in f["maps"][names[-1]] for field in FACE_FIELDS)
    found = read_line(tmp_path / "run", ACROSS)
    assert found["flow_source"] == FLOW_ESTIMATE
    at_frames = np.abs(record_at_frames(tmp_path / "run", "across"))
    flow = np.array(found["flow_m3s"])
    running = at_frames > 0.25 * at_frames.max()
    assert flow.min() >= 0.0  # the estimate has no sign
    assert np.abs(flow[running] / at_frames[running] - 1.0).max() < 0.08  # the limit the W21 plot states


def test_one_map_without_faces_sends_the_whole_line_to_the_estimate(finished: Path) -> None:
    """A run resumed from a checkpoint made before the setting existed holds maps of both kinds."""
    names = frame_names(finished / "results.h5")
    with h5py.File(finished / "results.h5", "r+") as f:
        del f["maps"][names[len(names) // 2]]["qx"]
        assert not frames_have_faces(f, names)
    assert read_line(finished, ACROSS)["flow_source"] == FLOW_ESTIMATE


def test_no_maps_means_no_faces() -> None:
    assert not frames_have_faces(None, [])


# resume


def test_a_stopped_run_resumed_keeps_the_faces_on_every_map_and_the_line_its_record(tmp_path: Path) -> None:
    cfg = plane_job(tmp_path, LONG_S)
    out = tmp_path / "broken"

    def stop_soon() -> None:
        while not (out / "results.h5").exists():
            time.sleep(0.02)
        time.sleep(STOP_AFTER_S)
        (out / "stop").touch()

    thread = threading.Thread(target=stop_soon, daemon=True)
    thread.start()
    stopped = run_job(cfg, out)
    thread.join()
    assert stopped.exit_code == EXIT_STOPPED
    before = frame_names(out / "results.h5")
    done = run_job(cfg, out, resume=True)
    assert done.exit_code == 0, done.message
    names = frame_names(out / "results.h5")
    assert len(names) > len(before) >= 1
    with h5py.File(out / "results.h5", "r") as f:
        assert frames_have_faces(f, names)
    found = read_line(out, ACROSS)
    assert found["flow_source"] == FLOW_FACES
    at_frames = record_at_frames(out, "across")
    running = np.abs(at_frames) > 0.25 * np.abs(at_frames).max()
    assert np.array(found["flow_m3s"])[running] == pytest.approx(at_frames[running], abs=2e-3, rel=1e-6)
