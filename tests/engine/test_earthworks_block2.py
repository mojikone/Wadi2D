"""A mixed channel with dykes on real Block 2 ground, read-only, through the whole pipeline on the CPU."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import rasterio

from wadi2d.config.schema import RunConfig
from wadi2d.engine.terrain_preview import preview_terrain
from wadi2d.run import run_job

pytestmark = pytest.mark.data

A, B = (435800.0, 2727300.0), (437200.0, 2727000.0)
EXTENT = (435600.0, 2726700.0, 437400.0, 2727500.0)
LOW_END = [(437395.0, 2726700.0), (437395.0, 2727500.0)]
DX = 10.0
BOTTOM = 30.0


def ground_along(dem: Path, stations: np.ndarray) -> np.ndarray:
    length = float(np.hypot(B[0] - A[0], B[1] - A[1]))
    x = A[0] + (B[0] - A[0]) * stations / length
    y = A[1] + (B[1] - A[1]) * stations / length
    with rasterio.open(dem) as src:
        return np.array([value[0] for value in src.sample(zip(x, y, strict=True))], dtype=np.float64)


@pytest.fixture(scope="module")
def mixed_job(block2_dir: Path, tmp_path_factory) -> RunConfig:
    """A design line through the fan: its bed and tops are smooth, the ground is not, so the banks keep changing."""
    folder = tmp_path_factory.mktemp("block2")
    dem = block2_dir / "Hydrology" / "Terrain" / "GGC_2_MERGE_HDSM_5.tif"
    length = float(np.hypot(B[0] - A[0], B[1] - A[1]))
    stations = np.arange(0.0, length + 1.0, 100.0)
    bed = np.polyval(np.polyfit(stations, ground_along(dem, stations), 1), stations) - 2.0
    table = folder / "sections.csv"
    with table.open("w", newline="", encoding="utf-8") as stream:
        rows = csv.writer(stream)
        rows.writerow(("station", "bed_z", "width", "left_top_z", "right_top_z", "left_slope", "right_slope"))
        for station, level in zip(stations[::2], bed[::2], strict=True):
            rows.writerow(
                (station, round(level, 3), BOTTOM, round(level + 3.0, 3), round(level + 2.5, 3), 2.0, 2.0)
            )
    channel = {
        "kind": "channel_dyke", "name": "Mixed", "coordinates": [A, B], "section": {"table": str(table)},
        "openings": [{"start": 500.0, "end": 580.0, "side": "left"}], "lining_n": 0.02,
        "start_end": "taper", "end_end": "taper", "taper_length": 100.0,
    }  # fmt: skip
    return RunConfig.model_validate(
        {
            "grid": {"dx": DX, "extent": EXTENT},
            "terrain": {"dem": str(dem), "manning": 0.04, "objects": [channel]},
            "hydrology": {"curve_number": 85.0},
            "storm": {"kind": "uniform", "depth_mm": 60.0, "duration_min": 30.0},
            "boundaries": [{"kind": "normal", "coordinates": LOW_END, "slope": 0.012}],
            "outputs": {
                "map_every_s": 0.0,
                "live_every_s": 0.0,
                "progress_every_s": 1.0,
                "terrain_map": True,
            },
            "run": {"duration_s": 1800.0, "backend": "cpu"},
        }
    )


@pytest.fixture(scope="module")
def previewed(mixed_job: RunConfig, tmp_path_factory) -> tuple[dict, Path]:
    out = tmp_path_factory.mktemp("preview")
    return preview_terrain(mixed_job, out), out


def test_each_bank_changes_between_cut_and_dyke_along_one_line(previewed):
    report, out = previewed
    item = json.loads((out / "preview.json").read_text(encoding="utf-8"))[0]
    for bank in ("left_state", "right_state"):
        assert {"cut", "dyke"} <= set(item[bank])
        assert sum(a != b for a, b in zip(item[bank], item[bank][1:], strict=False)) >= 2
    assert "open" in item["left_state"]
    assert "open" not in item["right_state"]
    assert any(left != right for left, right in zip(item["left_state"], item["right_state"], strict=True))
    assert report["volumes"][0]["cut_m3"] > 0.0
    assert report["volumes"][0]["fill_m3"] > 0.0


def test_the_new_ground_follows_the_design_where_it_was_cut_or_built(previewed):
    report, _out = previewed
    with (
        rasterio.open(report["files"]["change"]) as change,
        rasterio.open(report["files"]["modified"]) as new,
    ):
        delta = change.read(1, masked=True).compressed()
        assert new.read(1, masked=True).min() > 0.0
    assert delta.min() < -1.0
    assert delta.max() > 1.0


def test_a_real_run_with_the_channel_closes_its_balance(mixed_job, tmp_path):
    run = run_job(mixed_job, tmp_path / "run")
    assert run.exit_code == 0, run.message
    assert abs(run.balance.relative) < 1e-5
    events = [
        json.loads(s) for s in (tmp_path / "run" / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert next(e for e in events if e["ev"] == "terrain")["volumes"][0]["object"] == "Mixed"
    with h5py.File(tmp_path / "run" / "results.h5", "r") as f:
        assert float(f["maxima"]["depth"][()].max()) > 0.2
    with rasterio.open(tmp_path / "run" / "terrain" / "terrain_modified.tif") as src:
        assert src.width * src.res[0] == pytest.approx(EXTENT[2] - EXTENT[0], abs=4.0 * DX * 32.0)
