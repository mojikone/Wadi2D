"""Shaped terrain on a mesh: a negative crest coefficient reads the energy head, and nothing leaks across cell sizes."""

from __future__ import annotations

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.config.schema import RunConfig, Tables
from wadi2d.grid.quad import QuadGrid, lattice_view
from wadi2d.run import prepare_grid, run_job
from wadi2d.solver.layout import TILE
from wadi2d.tables import ArrayBed
from wadi2d.tables.builder import CrestFaces
from wadi2d.tables.quad import build_quad_tables

pytest.importorskip("whitebox")

BACKENDS = ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)]
PIXEL, DX, COARSE = 2.0, 4.0, 8.0
NX, NY = 256, 128
"""Cells of DX: 1 km by 500 m, room for coarse tiles on both sides of the barrier."""
GROUND, CREST = 100.0, 102.0
MESH = {
    "enabled": True, "coarse_dx": COARSE, "min_dx": 1.0, "analysis_pixel": 2.0, "stream_area_fine_km2": 100.0,
    "stream_area_mid_km2": 100.0,
}  # fmt: skip


def _dem(tmp_path):
    return write_dem(tmp_path / "flat.tif", np.full((NY * 2, NX * 2), GROUND), PIXEL)


def _diagonal() -> list[tuple[float, float]]:
    return [(X0 + 330.0, Y0 - 4.0), (X0 + 450.0, Y0 - NY * DX + 4.0)]


def _embankment(line=None, width=3.0) -> dict:
    return {
        "kind": "embankment",
        "coordinates": line or _diagonal(),
        "z": [CREST, CREST],
        "section": {"width": width, "left_slope": 2.0, "right_slope": 2.0},
    }


def _weir_job(dem, stage: float, mesh: bool, objects: list[dict], backend="cpu", duration=600.0) -> RunConfig:
    """Water held at ``stage`` west of a barrier, a free edge far to the east."""
    parts = {
        "terrain": {"objects": objects, "manning": 0.03},
        "boundaries": [
            {"kind": "stage", "coordinates": [(X0 + 16.0, Y0), (X0 + 16.0, Y0 - NY * DX)], "stage": stage},
            {"kind": "free", "coordinates": [(X0 + NX * DX - 16.0, Y0), (X0 + NX * DX - 16.0, Y0 - NY * DX)]},
        ],
        "run": {"duration_s": duration, "source_every_s": 30.0, "backend": backend},
        "outputs": {
            "lines": [
                {"name": "past", "coordinates": [(X0 + 800.0, Y0 - 4.0), (X0 + 800.0, Y0 - NY * DX + 4.0)]}
            ],
            "series_every_s": 10.0,
        },
    }
    if mesh:
        parts["mesh"] = MESH
        parts["numerics"] = {"local_time_stepping": True}
    return job(dem, NX, NY, DX, **parts)


def test_a_shaped_crest_keeps_its_negative_coefficient_on_a_mesh(tmp_path):
    dem = _dem(tmp_path)
    uniform = prepare_grid(_weir_job(dem, 101.0, False, [_embankment()]), tmp_path / "c")[0]
    quad = prepare_grid(_weir_job(dem, 101.0, True, [_embankment()]), tmp_path / "c")[0]
    assert quad.grid.level.max() > 0
    assert quad.cwx.min() < 0.0
    assert quad.cwx.min() == pytest.approx(float(uniform.cwx.min()))
    assert quad.cwy.min() == pytest.approx(float(uniform.cwy.min()))
    count = int(np.count_nonzero(quad.cwx < 0.0)) + int(np.count_nonzero(quad.cwy < 0.0))
    assert count == int(np.count_nonzero(uniform.cwx < 0.0)) + int(np.count_nonzero(uniform.cwy < 0.0))


def test_an_old_crest_keeps_its_positive_coefficient_on_a_mesh(tmp_path):
    line = {"kind": "crest_line", "coordinates": _diagonal(), "z_constant": CREST}
    quad = prepare_grid(_weir_job(_dem(tmp_path), 101.0, True, [line]), tmp_path / "c")[0]
    assert quad.cwx.max() == pytest.approx(CRITICAL_WEIR_COEFF)
    assert quad.cwx.min() >= 0.0


def _interface_grid() -> QuadGrid:
    mask = np.zeros((64, 192), bool)
    mask[2:-2, 2:-2] = True
    level = np.array([[0, 0, 1, 1, 0, 0], [0, 0, 1, 1, 0, 0]], np.int32)
    return QuadGrid.from_levels(mask, 0.0, 0.0, 4.0, level)


def _crest_at(q: QuadGrid, j: int, i: int) -> CrestFaces:
    crest = CrestFaces.empty(q.shape)
    crest.xwall = np.zeros(q.shape, bool)
    crest.ywall = np.zeros(q.shape, bool)
    crest.xz[j, i] = 3.0
    crest.xc[j, i] = -CRITICAL_WEIR_COEFF
    return crest


def test_a_negative_coefficient_survives_on_a_west_interface_face():
    q = _interface_grid()
    row = q.interfaces[q.interfaces[:, 1] == 0][0]
    j0, i0 = q.tiles[row[0], 0] * TILE, q.tiles[row[0], 1] * TILE
    tab = build_quad_tables(
        q, ArrayBed(np.zeros((72, 200)), 4.0, 4, 4), Tables(), 0.03, _crest_at(q, j0 + 5, i0)
    )
    assert tab.cwx.ravel()[int(row[5]) + 5 * int(row[6])] == pytest.approx(-CRITICAL_WEIR_COEFF)


def test_a_crest_on_an_east_interface_is_refused():
    """That face lies in the coarse tile's raster: the mesher keeps lines off it, and the tables refuse it if not."""
    q = _interface_grid()
    row = q.interfaces[q.interfaces[:, 1] == 2][0]
    j0, i0 = q.tiles[row[0], 0] * TILE, (q.tiles[row[0], 1] + 1) * TILE
    with pytest.raises(ValueError, match="coarse tiles"):
        build_quad_tables(
            q, ArrayBed(np.zeros((72, 200)), 4.0, 4, 4), Tables(), 0.03, _crest_at(q, j0 + 5, i0)
        )


@pytest.mark.parametrize("backend", BACKENDS)
def test_an_embankment_holds_water_below_its_crest_across_cell_sizes(tmp_path, backend):
    cfg = _weir_job(_dem(tmp_path), CREST - 0.3, True, [_embankment()], backend)
    out = tmp_path / "held"
    summary = run_job(cfg, out)
    assert summary.exit_code == 0, summary.message
    assert summary.peaks["past"][0] == 0.0


@pytest.mark.parametrize("backend", BACKENDS)
def test_an_overtopped_embankment_passes_the_flow_of_the_uniform_grid(tmp_path, backend):
    dem = _dem(tmp_path)
    stage = CREST + 0.4
    plain = run_job(_weir_job(dem, stage, False, [_embankment()], backend, 900.0), tmp_path / "plain")
    mesh = run_job(_weir_job(dem, stage, True, [_embankment()], backend, 900.0), tmp_path / "mesh")
    assert mesh.exit_code == 0, mesh.message
    assert abs(mesh.balance.relative) < 1e-5
    assert mesh.peaks["past"][0] == pytest.approx(plain.peaks["past"][0], rel=0.08)


def _channel_job(dem, mesh: bool) -> RunConfig:
    """A channel between dykes along the box, fed at its head, with a dry plain on both sides."""
    y = Y0 - NY * DX / 2.0
    obj = {
        "kind": "channel_dyke",
        "coordinates": [(X0 + 40.0, y), (X0 + NX * DX - 40.0, y)],
        "z": [GROUND - 1.0, GROUND - 1.5],
        "section": {
            "width": 12.0, "left_slope": 2.0, "right_slope": 2.0, "left_crest_width": 3.0, "right_crest_width": 3.0,
            "left_top_z": CREST, "right_top_z": CREST,
        },
    }  # fmt: skip
    parts = {
        "terrain": {"objects": [obj], "manning": 0.03},
        "hydrology": {
            "inflows": [
                {"name": "in", "x": X0 + 80.0, "y": y, "times_s": [0.0, 1200.0], "flows": [6.0, 6.0]}
            ],
            "inject_radius": 6.0,
        },
        "boundaries": [
            {"kind": "free", "coordinates": [(X0 + NX * DX - 8.0, y + 6.0), (X0 + NX * DX - 8.0, y - 6.0)]}
        ],
        "run": {"duration_s": 500.0, "source_every_s": 30.0, "backend": "cpu"},
    }
    if mesh:
        parts["mesh"] = MESH
        parts["numerics"] = {"local_time_stepping": True}
    return job(dem, NX, NY, DX, **parts)


def test_a_channel_between_dykes_keeps_its_water_across_cell_sizes(tmp_path):
    y0 = Y0
    out = tmp_path / "run"
    summary = run_job(_channel_job(_dem(tmp_path), True), out)
    assert summary.exit_code == 0, summary.message
    assert abs(summary.balance.relative) < 1e-5
    tables, _crs = prepare_grid(_channel_job(_dem(tmp_path), True), tmp_path / "c")
    assert tables.grid.level.max() > 0
    import h5py

    with h5py.File(out / "results.h5", "r") as f:
        depth = f["maxima/mean_depth"][()]
    rows = (y0 - np.asarray(tables.grid.y0)) / DX
    middle = NY // 2 - round(float(rows))
    assert depth[middle, NX // 2] > 0.1
    assert depth[middle + 12 :, :].max() == 0.0
    assert depth[: middle - 12, :].max() == 0.0


def test_a_crest_that_reaches_a_coarse_tile_is_refused_in_plain_words(tmp_path):
    cfg = _weir_job(_dem(tmp_path), 101.0, True, [_embankment()])
    data = cfg.model_dump(mode="json")
    data["mesh"]["refine_lines"] = False
    summary = run_job(RunConfig.model_validate(data), tmp_path / "run")
    assert summary.exit_code == 2
    assert "coarse tiles" in summary.message


def test_a_wall_that_reaches_a_coarse_tile_is_refused_in_plain_words(tmp_path):
    wall = {"kind": "wall", "coordinates": _diagonal()}
    cfg = _weir_job(_dem(tmp_path), 101.0, True, [wall])
    data = cfg.model_dump(mode="json")
    data["mesh"]["refine_lines"] = False
    summary = run_job(RunConfig.model_validate(data), tmp_path / "run")
    assert summary.exit_code == 2


def test_the_survey_walks_every_square_of_a_coarse_tile(tmp_path):
    grid = prepare_grid(_weir_job(_dem(tmp_path), 101.0, True, [_embankment()]), tmp_path / "c")[0].grid
    view = lattice_view(grid)
    assert grid.level.max() > 0
    assert view.ntiles - 1 == sum(4 ** int(s) for s in grid.level[1:])
    assert len({tuple(row) for row in view.tiles[1:].tolist()}) == view.ntiles - 1


def test_the_volumes_on_a_mesh_are_those_of_the_uniform_grid(tmp_path):
    dem = _dem(tmp_path)
    a = run_job(_weir_job(dem, 100.0, False, [_embankment()], duration=30.0), tmp_path / "a")
    b = run_job(_weir_job(dem, 100.0, True, [_embankment()], duration=30.0), tmp_path / "b")
    assert a.exit_code == 0 and b.exit_code == 0, b.message
    import json

    def fill(folder):
        events = [json.loads(s) for s in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
        return next(e for e in events if e["ev"] == "terrain")["volumes"][0]["fill_m3"]

    assert fill(tmp_path / "b") == pytest.approx(fill(tmp_path / "a"), rel=1e-6)
