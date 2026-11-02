"""The mesher: its rules on made-up ground, then whole jobs on a mesh through the engine."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import CRS, X0, Y0, job, write_dem
from tests.engine.test_run import full_job, valley
from wadi2d.config.schema import Mesh, RefineZone, RunConfig
from wadi2d.engine.cli import main
from wadi2d.mesh import streams
from wadi2d.mesh.build import levels_above, must_be_fine
from wadi2d.mesh.refine import Lattice, break_levels, line_levels, squares, stream_levels, zone_levels
from wadi2d.mesh.streams import Terrain, incision
from wadi2d.run import run_job
from wadi2d.solver.layout import TILE

PIXEL = 5.0
PER_SQUARE = 64
"""A tile of 32 cells of 10 m over 5 m pixels."""
SQUARES = 4
BIG = 50.0e6
"""Drainage area of the test streams, m2: over every threshold."""


def _plane(slope: float) -> np.ndarray:
    n = SQUARES * PER_SQUARE
    x = (np.arange(n) + 0.5) * PIXEL
    return np.tile(500.0 - slope * x, (n, 1))


def _along_row(z: np.ndarray, row: int) -> Terrain:
    """A stream down one row, with a huge drainage area, as D8 draws one on any ground."""
    area = np.zeros(z.shape)
    area[row, :] = BIG
    return Terrain(z, area, PIXEL)


def _levels(t: Terrain, cfg: Mesh | None = None, top: int = 2) -> np.ndarray:
    inside = np.ones(t.z.shape, bool)
    return stream_levels(t, inside, cfg or Mesh(), PER_SQUARE, top)


def test_a_wadi_cut_into_the_ground_stays_fine():
    z = _plane(0.01)
    z[150:170, :] -= 3.0
    level = _levels(_along_row(z, 160))
    assert level[160 // PER_SQUARE].max() == 0
    assert level[0].min() == 2


@pytest.mark.parametrize("slope", [0.0, 0.002, 0.05, 0.3])
def test_a_stream_across_open_ground_forces_nothing(slope):
    """D8 draws a stream on any plain or plane. No channel means no refinement, however steep."""
    level = _levels(_along_row(_plane(slope), 160))
    assert level.min() == 2


def test_incision_is_zero_on_a_plane_whatever_its_slope():
    z = _plane(0.3)
    inner = incision(z, PIXEL, 200.0)[60:-60, 60:-60]
    assert np.abs(inner).max() < 1e-6


def test_incision_is_zero_up_to_the_edge_of_a_sloping_raster():
    z = _plane(0.3)
    assert np.abs(incision(z, PIXEL, 200.0)).max() < 1e-6


def test_a_window_on_a_hole_in_the_dem_scores_nothing():
    z = _plane(0.05)
    z[100:110, 100:110] = np.nan
    assert np.abs(incision(z, PIXEL, 200.0)).max() < 1e-6


def test_a_small_wadi_is_one_step_finer_than_coarse():
    z = _plane(0.01)
    z[150:170, :] -= 3.0
    t = _along_row(z, 160)
    t.area[160, :] = 3.0e6
    level = _levels(t, Mesh(stream_area_fine_km2=10.0, stream_area_mid_km2=1.0))
    assert level[160 // PER_SQUARE].max() == 1


def test_a_uniform_slope_is_not_a_slope_break_but_a_bank_is():
    cfg = Mesh(break_depth=0.5, break_share=0.05)
    inside = np.ones((SQUARES * PER_SQUARE, SQUARES * PER_SQUARE), bool)
    assert (
        break_levels(Terrain(_plane(0.3), np.zeros(inside.shape), PIXEL), inside, cfg, PER_SQUARE, 2).min()
        == 2
    )
    z = _plane(0.02)
    z[:, 100:] += 0.3 * (np.arange(z.shape[1] - 100) * PIXEL)
    assert break_levels(Terrain(z, np.zeros(inside.shape), PIXEL), inside, cfg, PER_SQUARE, 2).min() == 1


def test_squares_counts_pixels():
    flags = np.zeros((8, 8), bool)
    flags[0, :3] = True
    assert squares(flags, 4).tolist() == [[3, 0], [0, 0]]


def test_a_line_refines_the_squares_it_touches():
    lat = Lattice(0.0, 320.0 * SQUARES, 10.0, SQUARES, SQUARES)
    level = line_levels([[(10.0, 480.0), (1270.0, 480.0)]], lat, 10.0, 2)
    assert level[2].max() == 0
    assert level[0].min() == 2


def test_a_zone_refines_to_its_cell_size():
    lat = Lattice(0.0, 320.0 * SQUARES, 10.0, SQUARES, SQUARES)
    ring = [(10.0, 10.0), (300.0, 10.0), (300.0, 300.0), (10.0, 300.0)]
    level = zone_levels(Mesh(zones=[RefineZone(coordinates=ring, dx=20.0)]), lat, 2)
    assert level[3, 0] == 1
    assert level[0, 3] == 2


def test_coarse_cell_must_be_a_power_of_two_of_the_fine_one():
    good = RunConfig.model_validate({"grid": {"dx": 10.0}, "mesh": {"coarse_dx": 40.0}})
    bad = RunConfig.model_validate({"grid": {"dx": 10.0}, "mesh": {"coarse_dx": 30.0}})
    assert levels_above(good) == 2
    with pytest.raises(ValueError, match="power of two"):
        levels_above(bad)


def test_lines_that_sit_on_faces_are_named_for_refinement():
    cfg = RunConfig.model_validate(
        {
            "terrain": {
                "objects": [
                    {"kind": "wall", "coordinates": [(0.0, 0.0), (1.0, 1.0)]},
                    {"kind": "burn_line", "coordinates": [(5.0, 5.0), (6.0, 6.0)], "depth": 1.0},
                ]
            },
            "boundaries": [{"kind": "free", "coordinates": [(2.0, 2.0), (3.0, 3.0)]}],
            "outputs": {"lines": [{"name": "a", "coordinates": [(4.0, 4.0), (5.0, 5.0)]}]},
        }
    )
    assert len(must_be_fine(cfg)) == 3


@pytest.fixture
def big_valley(tmp_path):
    return write_dem(tmp_path / "valley.tif", valley(512, 384, 1.0), 1.0)


def _on_mesh(cfg: RunConfig, **mesh) -> RunConfig:
    data = cfg.model_dump(mode="json")
    data["grid"]["dx"] = 4.0
    data["mesh"] = {
        "enabled": True, "coarse_dx": 8.0, "min_dx": 1.0, "analysis_pixel": 2.0, "stream_area_fine_km2": 0.02,
        "stream_area_mid_km2": 0.01, "incision_width": 60.0, "incision_depth": 0.2, **mesh,
    }  # fmt: skip
    data["outputs"]["live_every_s"] = 0.0
    return RunConfig.model_validate(data)


def _uniform(cfg: RunConfig) -> RunConfig:
    data = cfg.model_dump(mode="json")
    data["grid"]["dx"] = 4.0
    data["outputs"]["live_every_s"] = 0.0
    return RunConfig.model_validate(data)


@pytest.mark.parametrize("backend", ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)])
def test_a_job_on_a_mesh_keeps_the_water_and_follows_the_uniform_run(big_valley, tmp_path, backend):
    pytest.importorskip("whitebox")
    base = full_job(big_valley, backend, 900.0)
    plain = run_job(_uniform(base), tmp_path / "plain")
    data = _on_mesh(base).model_dump(mode="json")
    data["numerics"]["local_time_stepping"] = True
    mesh = run_job(RunConfig.model_validate(data), tmp_path / "mesh")
    assert mesh.exit_code == 0, mesh.message
    assert mesh.cells < plain.cells
    assert abs(mesh.balance.relative) < 1e-5
    assert mesh.peaks["Cross"][0] == pytest.approx(plain.peaks["Cross"][0], rel=0.1)
    assert (tmp_path / "mesh" / "maps" / "max_depth.tif").is_file()


def test_an_inflow_on_a_mesh_enters_whole(big_valley, tmp_path):
    """A hydrograph put into cells of two sizes: what entered is what the table holds."""
    pytest.importorskip("whitebox")
    flows = {"times_s": [0.0, 600.0], "flows": [1.0, 1.0]}
    cfg = job(
        big_valley, 128, 96, 4.0,
        terrain={"manning": 0.04},
        hydrology={"inflows": [{"name": "in", "x": X0 + 100.0, "y": Y0 - 192.0, **flows}], "inject_radius": 12.0},
        run={"duration_s": 600.0, "backend": "cpu"},
        mesh={
            "enabled": True, "coarse_dx": 8.0, "min_dx": 1.0, "analysis_pixel": 2.0, "stream_area_fine_km2": 100.0,
            "stream_area_mid_km2": 100.0,
        },
    )  # fmt: skip
    summary = run_job(cfg, tmp_path / "run")
    assert summary.exit_code == 0, summary.message
    assert summary.balance.inflow == pytest.approx(600.0, rel=1e-6)
    assert abs(summary.balance.relative) < 1e-5


def test_a_design_line_through_coarse_tiles_is_refused(big_valley, tmp_path):
    """Its faces are not on the lattice the engine reads: a wrong discharge with no warning, unless it stops here."""
    pytest.importorskip("whitebox")
    cfg = _on_mesh(
        full_job(big_valley, "cpu", 60.0),
        refine_lines=False,
        stream_area_fine_km2=9.0,
        stream_area_mid_km2=9.0,
    )
    summary = run_job(cfg, tmp_path / "run")
    assert summary.exit_code == 2
    assert "coarse tiles" in summary.message


def test_a_mesh_below_the_smallest_cell_is_refused(big_valley, tmp_path):
    pytest.importorskip("whitebox")
    summary = run_job(_on_mesh(full_job(big_valley, "cpu", 60.0), min_dx=5.0), tmp_path / "run")
    assert summary.exit_code == 2
    assert "min_dx" in summary.message


def test_the_preview_writes_the_cell_sizes_and_the_counts(big_valley, tmp_path, capsys):
    pytest.importorskip("whitebox")
    path = tmp_path / "job.json"
    path.write_text(_on_mesh(full_job(big_valley, "cpu", 60.0)).model_dump_json(), encoding="utf-8")
    assert main(["mesh", str(path), "--out", str(tmp_path / "preview")]) == 0
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event["ev"] == "mesh"
    with rasterio.open(event["raster"]) as src:
        sizes = src.read(1, masked=True).compressed()
    assert set(np.unique(sizes)) <= {4.0, 8.0}
    assert TILE == 32
    assert (
        json.loads((tmp_path / "preview" / "mesh.json").read_text(encoding="utf-8"))["cells"]
        == event["cells"]
    )


def test_the_default_job_has_no_mesh():
    assert RunConfig().mesh.enabled is False


class _SilentWhitebox:
    """Exits 0 and writes nothing, ``silent`` times; what two meshers at once can do to each other."""

    silent = 0

    def set_verbose_mode(self, _on: bool) -> None:
        pass

    def breach_depressions_least_cost(self, _in: str, _out: str, dist: int, fill: bool) -> int:
        return 0

    def d8_flow_accumulation(self, _in: str, out: str, out_type: str) -> int:
        if type(self).silent > 0:
            type(self).silent -= 1
            return 0
        shutil.copy(Path(out).with_name("z.tif"), out)
        return 0


def _analysis(monkeypatch, silent: int) -> np.ndarray:
    _SilentWhitebox.silent = silent
    monkeypatch.setitem(sys.modules, "whitebox", SimpleNamespace(WhiteboxTools=_SilentWhitebox))
    monkeypatch.setattr(streams, "ANALYSIS_WAIT_S", 0.0)
    return streams.drainage_area(np.ones((8, 8)), 2.0, X0, Y0, CRS)


def test_a_stream_analysis_that_wrote_nothing_is_tried_again(monkeypatch):
    assert _analysis(monkeypatch, 1).shape == (8, 8)


def test_a_stream_analysis_that_never_writes_says_so_in_plain_words(monkeypatch):
    with pytest.raises(RuntimeError, match="wrote no result"):
        _analysis(monkeypatch, streams.ANALYSIS_TRIES)
