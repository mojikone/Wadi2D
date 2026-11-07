"""Lines read back from saved frames: the geometry, the way the flow runs, and the record of the same run to hold them to."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from rasterio.crs import CRS

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
from wadi2d.config.schema import Pixels, RunConfig
from wadi2d.engine.cli import main
from wadi2d.grid.quad import QuadGrid
from wadi2d.products.cell_grid import write_cell_grid
from wadi2d.products.face_flow import FLOW_FACES
from wadi2d.products.result_lines import (
    FLOW_FLOOR,
    GROUND_CELLS,
    GROUND_DEM,
    MOST_SAMPLES,
    SAMPLES_PER_CELL,
    Picker,
    Samples,
    catalogue,
    cell_sizes,
    crossing,
    line_flow,
    read_line,
    sample_line,
    surface_way,
)
from wadi2d.run import run_job
from wadi2d.solver.layout import TILE

SIZE = 40
DX = 5.0
WIDE = SIZE * DX
MIDDLE_X = X0 + WIDE / 2.0
ACROSS = [(MIDDLE_X, Y0 - 2.5), (MIDDLE_X, Y0 - WIDE + 2.5)]


def plane(east: float, north: float) -> tuple[np.ndarray, np.ndarray]:
    """(3, 3, 1) levels of a plane rising east and north, all wet; row 0 lies north."""
    rows, columns = np.mgrid[-1:2, -1:2]
    level = east * columns - north * rows
    return level[:, :, None].astype(np.float64), np.ones((3, 3, 1), bool)


def along(east: float, north: float) -> Samples:
    return Samples(np.zeros(1), np.zeros(1), np.zeros(1), np.array([east]), np.array([north]), 1.0)


def test_samples_sit_in_the_middle_of_equal_stretches() -> None:
    samples = sample_line([(0.0, 0.0), (100.0, 0.0)], 10.0)
    assert samples.count == 10
    assert samples.station.tolist() == [5.0 + 10.0 * n for n in range(10)]
    assert samples.spacing == 10.0
    assert (samples.east == 1.0).all() and (samples.north == 0.0).all()


def test_a_bent_line_keeps_its_length_and_turns_at_the_vertex() -> None:
    samples = sample_line([(0.0, 0.0), (30.0, 0.0), (30.0, 40.0)], 1.0)
    assert samples.count * samples.spacing == pytest.approx(70.0)
    assert samples.east[0] == 1.0 and samples.north[0] == 0.0
    assert samples.east[-1] == 0.0 and samples.north[-1] == 1.0
    assert samples.x[-1] == pytest.approx(30.0) and samples.y[-1] == pytest.approx(39.5)


def test_a_long_line_takes_wider_samples_and_a_repeated_vertex_does_no_harm() -> None:
    samples = sample_line([(0.0, 0.0), (0.0, 0.0), (1e6, 0.0)], 1.0)
    assert samples.count == MOST_SAMPLES
    assert samples.spacing == pytest.approx(1e6 / MOST_SAMPLES)


@pytest.mark.parametrize("coordinates", [[(0.0, 0.0)], [(1.0, 1.0), (1.0, 1.0)]])
def test_a_line_needs_a_length(coordinates: list) -> None:
    with pytest.raises(ValueError, match="A result line needs"):
        sample_line(coordinates, 1.0)


def test_the_flow_runs_down_the_water_surface() -> None:
    east, north = surface_way(*plane(0.0, -2.0))  # falls north
    assert east[0] == pytest.approx(0.0) and north[0] == pytest.approx(1.0)
    east, north = surface_way(*plane(3.0, 0.0))  # rises east
    assert east[0] == pytest.approx(-1.0) and north[0] == pytest.approx(0.0)
    east, north = surface_way(*plane(1.0, 1.0))
    assert east[0] == pytest.approx(-(0.5**0.5)) and north[0] == pytest.approx(-(0.5**0.5))


def test_a_dry_neighbour_does_not_turn_the_flow() -> None:
    level, wet = plane(1.0, 0.0)
    level[0, :, 0] = 1000.0  # a bank to the north, above the water
    wet[0, :, 0] = False
    east, north = surface_way(level, wet)
    assert east[0] == pytest.approx(-1.0) and north[0] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("east", "north", "share"),
    [(0.0, 1.0, 1.0), (1.0, 0.0, 0.0), (0.5**0.5, 0.5**0.5, 0.5**0.5), (0.0, -1.0, 1.0)],
)
def test_the_share_that_crosses_is_the_sine_of_the_angle(east: float, north: float, share: float) -> None:
    level, wet = plane(1.0, 0.0)  # flowing west
    assert crossing(along(east, north), level, wet)[0] == pytest.approx(share)


def test_still_water_counts_as_crossing_square() -> None:
    level, wet = plane(0.0, 0.0)
    assert crossing(along(1.0, 0.0), level, wet)[0] == 1.0


def test_flow_is_mean_depth_times_speed_over_the_wet_length() -> None:
    samples = Samples(np.zeros(3), np.zeros(3), np.zeros(3), np.ones(3), np.zeros(3), 2.0)
    q = line_flow(samples, np.array([1.0, 2.0, 9.0]), np.array([3.0, 1.0, 9.0]), np.array([1.0, 0.5, 1.0]), np.array([True, True, False]))
    assert q == pytest.approx((1.0 * 3.0 + 2.0 * 1.0 * 0.5) * 2.0)


def test_the_picker_reads_each_cell_in_the_order_given_and_only_the_blocks_it_needs() -> None:
    field = np.arange(400.0 * 400.0).reshape(400, 400).astype(np.float32)
    rows, columns = np.array([399, 0, 200, 0]), np.array([5, 0, 390, 1])
    asked = []

    def window(row: int, column: int, height: int, width: int) -> np.ndarray:
        asked.append((height, width))
        return field[row : row + height, column : column + width]

    assert Picker(rows, columns).read(window).tolist() == field[rows, columns].tolist()
    assert len(asked) == 3
    assert max(h * w for h, w in asked) <= 2


def test_cell_sizes_on_a_mesh_follow_the_tiles(tmp_path: Path) -> None:
    mask = np.ones((TILE * 4, TILE * 4), bool)
    levels = np.zeros((4, 4), np.int32)
    levels[:2, :2] = 1
    grid = QuadGrid.from_levels(mask, 0.0, 0.0, DX, levels)
    write_cell_grid(grid, CRS.from_epsg(32640).to_wkt(), tmp_path)

    class Mesh:
        enabled = True

    class Config:
        mesh = Mesh

    sizes = cell_sizes(tmp_path, Config, mask.shape)
    assert grid.level.max() >= 1
    for t in range(1, grid.ntiles):
        row, column = (int(v) for v in grid.tiles[t])
        size = 1 << int(grid.level[t])
        assert (sizes[row : row + size, column : column + size] == size).all()


@pytest.fixture
def finished(tmp_path: Path) -> Path:
    """Rain on a plane falling east, out through the east edge, with a line across it and a point on it."""
    dem = write_dem(tmp_path / "dem.tif", tilted_box(SIZE, SIZE, DX, 0.02), DX)
    east = X0 + WIDE - DX / 2.0
    cfg = job(
        dem, SIZE, SIZE, DX,
        run={"duration_s": 600.0},
        storm={"kind": "uniform", "depth_mm": 300.0, "duration_min": 10.0},
        boundaries=[{"kind": "normal", "slope": 0.02, "coordinates": [(east, Y0), (east, Y0 - WIDE)]}],
        outputs={
            "map_every_s": 60.0, "pixels": {"enabled": False},
            "lines": [{"name": "mid line", "coordinates": ACROSS}],
            "points": [{"name": "mid", "x": MIDDLE_X + 2.5, "y": Y0 - WIDE / 2.0 - 2.5}],
        },
    )  # fmt: skip
    assert run_job(cfg, tmp_path / "run").exit_code == 0
    return tmp_path / "run"


def test_the_catalogue_holds_the_frames_and_the_series_of_record(finished: Path) -> None:
    found = catalogue(finished)
    assert len(found["frames_s"]) >= 10
    assert 60.0 <= found["interval_s"] <= 65.0
    assert [line["name"] for line in found["lines"]] == ["mid line"]
    line = found["lines"][0]
    assert line["coordinates"] == [list(p) for p in ACROSS]
    assert len(line["t_s"]) == len(line["discharge_m3s"]) > 10
    assert max(np.abs(line["discharge_m3s"])) > 1.0
    point = found["points"][0]
    assert point["name"] == "mid" and len(point["level_m"]) == len(point["t_s"])
    assert found["lumped"] == []  # no lumped network in this run


def test_flow_from_frames_is_the_upfront_line_at_the_frames(finished: Path) -> None:
    """The run saved the face discharges, so the line reads the record, sign included, at the frame times."""
    record = catalogue(finished)["lines"][0]
    found = read_line(finished, ACROSS, "same line")
    assert found["name"] == "same line"
    assert found["flow_source"] == FLOW_FACES
    at_frames = np.interp(found["t_s"], record["t_s"], record["discharge_m3s"])
    flow = np.array(found["flow_m3s"])
    running = np.abs(at_frames) > 0.25 * np.abs(at_frames).max()
    assert running.sum() >= 3
    assert flow[running] == pytest.approx(at_frames[running], rel=0.01)
    assert flow.min() < 0.0  # eastward through a line drawn southward is to its left


def test_a_line_along_the_flow_passes_little(finished: Path) -> None:
    y = Y0 - WIDE / 2.0
    along_it = read_line(finished, [(X0 + 40.0, y), (X0 + WIDE - 40.0, y)])
    across_it = read_line(finished, ACROSS)
    assert max(np.abs(along_it["flow_m3s"])) < 0.1 * max(np.abs(across_it["flow_m3s"]))


def test_the_level_on_the_line_is_the_level_recorded_at_the_point(finished: Path) -> None:
    point = catalogue(finished)["points"][0]
    y = point["y"]
    found = read_line(finished, [(point["x"] - 12.5, y), (point["x"] + 12.5, y)])
    middle = len(found["station_m"]) // 2
    frame = int(np.argmin(np.abs(np.array(found["t_s"]) - 300.0)))
    level = found["level_m"][frame][middle]
    recorded = float(np.interp(found["t_s"][frame], point["t_s"], point["level_m"]))
    assert level == pytest.approx(recorded, abs=0.02)


def test_the_ground_is_the_dem_and_water_stands_only_above_it(finished: Path) -> None:
    y = Y0 - WIDE / 2.0
    found = read_line(finished, [(X0 + 2.5, y), (X0 + WIDE - 2.5, y)])
    assert found["ground_source"] == GROUND_DEM
    station = np.array(found["station_m"])
    ground = np.array(found["ground_m"])
    expected = 100.0 - 0.02 * (np.floor((station + 2.5) / DX) + 0.5) * DX
    assert np.abs(ground - expected).max() < 0.03
    level = found["level_m"][len(found["t_s"]) // 2]
    wet = [k for k, v in enumerate(level) if v is not None]
    assert wet
    assert all(level[k] > ground[k] for k in wet)
    assert 0.0 < max(found["deepest_m"]) < 3.0


def test_samples_are_a_quarter_of_a_cell(finished: Path) -> None:
    found = read_line(finished, ACROSS)
    assert found["station_m"][1] - found["station_m"][0] == pytest.approx(DX / SAMPLES_PER_CELL, abs=0.01)
    assert found["length_m"] == pytest.approx(WIDE - DX)


def test_with_the_dem_gone_the_ground_is_each_cells_lowest_point(finished: Path) -> None:
    (finished.parent / "dem.tif").unlink()
    found = read_line(finished, ACROSS)
    assert found["ground_source"] == GROUND_CELLS
    assert max(np.abs(found["flow_m3s"])) > 0.0
    assert all(g is None or 90.0 < g < 100.0 for g in found["ground_m"])


def test_a_sheet_under_the_depth_floor_of_the_maps_still_counts_as_flow() -> None:
    assert Pixels().depth_floor > FLOW_FLOOR


def test_a_line_off_the_model_is_told_so(finished: Path) -> None:
    with pytest.raises(ValueError, match="does not cross the model"):
        read_line(finished, [(X0 - 500.0, Y0), (X0 - 400.0, Y0)])


def test_part_of_a_line_off_the_model_reads_as_dry(finished: Path) -> None:
    found = read_line(finished, [(MIDDLE_X, Y0 + 50.0), (MIDDLE_X, Y0 - 50.0)])
    level = found["level_m"][len(found["t_s"]) // 2]
    assert level[0] is None
    assert any(v is not None for v in level)
    assert found["ground_m"][0] is None


def test_the_command_writes_what_the_plugin_reads(finished: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    listing = tmp_path / "listing.json"
    assert main(["lines", str(finished), "--out", str(listing)]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == str(listing)
    assert json.loads(listing.read_text("utf-8"))["lines"][0]["name"] == "mid line"
    request = tmp_path / "line.json"
    request.write_text(json.dumps({"name": "Line 1", "coordinates": ACROSS}), "utf-8")
    answer = tmp_path / "answer.json"
    assert main(["lines", str(finished), "--line", str(request), "--out", str(answer)]) == 0
    read = json.loads(answer.read_text("utf-8"))
    assert read["name"] == "Line 1" and len(read["level_m"]) == len(read["t_s"])
    assert read["flow_source"] == FLOW_FACES


def test_the_command_says_when_a_run_saved_too_few_maps(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    dem = write_dem(tmp_path / "dem.tif", tilted_box(40, 40, 5.0, 0.01), 5.0)
    assert run_job(job(dem, 40, 40, 5.0, run={"duration_s": 30.0}), tmp_path / "run").exit_code == 0
    request = tmp_path / "line.json"
    request.write_text(json.dumps({"coordinates": ACROSS}), "utf-8")
    assert main(["lines", str(tmp_path / "run"), "--line", str(request), "--out", str(tmp_path / "a.json")]) == 3
    assert "a line needs two" in capsys.readouterr().err
    assert main(["lines", str(tmp_path / "run"), "--out", str(tmp_path / "b.json")]) == 0
    assert json.loads((tmp_path / "b.json").read_text("utf-8"))["frames_s"] == []


def test_a_burned_channel_shows_in_the_ground(tmp_path: Path) -> None:
    dem = write_dem(tmp_path / "dem.tif", tilted_box(SIZE, SIZE, DX, 0.02), DX)
    y = Y0 - WIDE / 2.0
    burn = {"kind": "burn_line", "coordinates": [(X0, y), (X0 + WIDE, y)], "width": 20.0, "depth": 3.0}
    cfg = job(
        dem, SIZE, SIZE, DX,
        run={"duration_s": 180.0},
        terrain={"objects": [burn]},
        storm={"kind": "uniform", "depth_mm": 300.0, "duration_min": 3.0},
        outputs={"map_every_s": 60.0, "pixels": {"enabled": False}},
    )  # fmt: skip
    assert run_job(cfg, tmp_path / "run").exit_code == 0
    ground = read_line(tmp_path / "run", ACROSS)["ground_m"]
    assert max(ground) - min(ground) == pytest.approx(3.0, abs=0.1)


def test_on_a_mesh_a_line_reads_the_coarse_cells_and_stands_near_its_record(tmp_path: Path) -> None:
    pytest.importorskip("whitebox")
    from tests.engine.test_mesh import _on_mesh, full_job, valley

    dem = write_dem(tmp_path / "valley.tif", valley(512, 384, 1.0), 1.0)
    data = _on_mesh(full_job(dem, "cpu", 900.0)).model_dump(mode="json")
    data["outputs"].update(map_every_s=60.0, series_every_s=30.0, pixels={"enabled": False})
    summary = run_job(RunConfig.model_validate(data), tmp_path / "mesh")
    assert summary.exit_code == 0, summary.message
    run = tmp_path / "mesh"
    record = catalogue(run)["lines"][0]
    found = read_line(run, record["coordinates"], record["name"])
    assert found["flow_source"] == FLOW_FACES
    at_frames = np.interp(found["t_s"], record["t_s"], record["discharge_m3s"])
    flow = np.array(found["flow_m3s"])
    running = np.abs(at_frames) > 0.25 * np.abs(at_frames).max()
    assert flow[running] == pytest.approx(at_frames[running], rel=0.01)  # an upfront line on a mesh sits on finest cells
    assert found["ground_source"] == GROUND_DEM
    assert max(found["deepest_m"]) > 0.0
