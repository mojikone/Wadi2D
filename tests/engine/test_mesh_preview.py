"""Build mesh before any run (W101 item 4): ``wadi2d mesh`` draws and counts the cells a run of the job steps, on
squares, the quadtree and the aligned centre mesh alike, and says the mesher's refusals in words."""

from __future__ import annotations

import json

import fiona
import numpy as np
import pytest

from tests.engine.test_left_out import DX, aligned, valley_job
from wadi2d.config.schema import RunConfig
from wadi2d.engine.cli import main
from wadi2d.run import prepare_grid


def preview(tmp_path, cfg: RunConfig, name: str, capsys) -> tuple[int, dict, dict]:
    path = tmp_path / f"{name}.json"
    path.write_text(cfg.model_dump_json(), encoding="utf-8")
    code = main(["mesh", str(path), "--out", str(tmp_path / name)])
    captured = capsys.readouterr()
    if code != 0:
        return code, json.loads(captured.err.strip().splitlines()[-1]), {}
    event = json.loads(captured.out.strip().splitlines()[-1])
    return code, event, json.loads((tmp_path / name / "mesh.json").read_text(encoding="utf-8"))


def test_squares_are_counted_and_drawn(tmp_path, capsys) -> None:
    code, event, summary = preview(tmp_path, valley_job(tmp_path, False), "squares", capsys)
    assert code == 0 and event["kind"] == summary["kind"] == "squares"
    assert summary["cells"] == summary["squares"] == event["cells"] > 0
    assert summary["smallest_m"] == DX
    with fiona.open(event["grid"]) as src:
        assert sum(f["properties"]["cells"] for f in src) == summary["cells"], (
            "the drawn tiles hold the counted cells"
        )


def test_the_aligned_cells_are_the_runs_own(tmp_path, capsys) -> None:
    cfg = valley_job(tmp_path, False, strips=aligned(tmp_path))
    code, event, summary = preview(tmp_path, cfg, "aligned", capsys)
    assert code == 0 and summary["kind"] == "aligned", event
    tables, _crs = prepare_grid(cfg, tmp_path / "cache_run")
    run_strip = tables.strip.mesh
    assert summary["aligned"] == run_strip.real, "as many aligned cells as the run steps"
    assert summary["squares"] == int(tables.grid.mask.sum()), "and the squares the run keeps beside them"
    assert summary["cells"] == summary["aligned"] + summary["squares"]
    with fiona.open(event["strip_cells"]) as src:
        areas = np.array([f["properties"]["area_m2"] for f in src])
    assert areas.size == summary["aligned"]
    assert areas.sum() == pytest.approx(summary["replaced"] * DX * DX, rel=1e-9), (
        "they tile the squares they replace"
    )
    assert summary["smallest_m2"] == pytest.approx(areas.min())


def test_the_quadtree_keeps_its_raster_and_draws_its_tiles(tmp_path, capsys) -> None:
    mesh = {"enabled": True, "min_dx": DX, "coarse_dx": 2.0 * DX, "analysis_pixel": DX}
    code, event, summary = preview(tmp_path, valley_job(tmp_path, False, mesh=mesh), "quad", capsys)
    assert code == 0 and summary["kind"] == "quadtree"
    assert event["raster"].endswith("mesh_cell_size.tif") and summary["tiles_by_size"]
    assert summary["smallest_m"] in (DX, 2.0 * DX)
    with fiona.open(event["grid"]) as src:
        assert sum(f["properties"]["cells"] for f in src) == summary["cells"]


def test_a_refusal_is_said_in_words(tmp_path, capsys) -> None:
    mesh = {"enabled": True, "min_dx": DX, "coarse_dx": 2.0 * DX, "analysis_pixel": DX}
    cfg = valley_job(tmp_path, False, mesh=mesh, strips=aligned(tmp_path))
    code, error, _ = preview(tmp_path, cfg, "both", capsys)
    assert code != 0 and "uniform grid" in error["message"]
