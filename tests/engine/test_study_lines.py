"""Lines read after a depth-area study take their own drainage area (W53, his order of 2026-11-13): the two runs
either side, blended with the study's own weights, the end run outside them, and one named run with no raster."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from tests.engine.conftest import CRS, X0, Y0, job, tilted_box, write_dem
from wadi2d.arf import arf_study, interpolate_peak, run_name
from wadi2d.engine.cli import main
from wadi2d.products.result_lines import read_line
from wadi2d.products.study_lines import FROM_ACCUMULATION, FROM_DESIGN_LINE, read_study_line, study_catalogue

AREAS = [10.0, 900.0]
DESIGN = [(X0 + 100.0, Y0), (X0 + 100.0, Y0 - 64.0)]
ACROSS = [[X0 + 60.0, Y0 - 1.0], [X0 + 60.0, Y0 - 63.0]]
"""In the accumulation raster's eighth column: 1e4 + 7 x (2e7 - 1e4) / 15 cells of 64 m2, about 598 km2."""
WEST = [[X0 + 2.0, Y0 - 1.0], [X0 + 2.0, Y0 - 63.0]]
EAST = [[X0 + 122.0, Y0 - 1.0], [X0 + 122.0, Y0 - 63.0]]


def make_study(root, accumulation: bool, composite: bool = True):
    dem = write_dem(root / "t.tif", tilted_box(64, 32, 2.0, 0.02), 2.0)
    with rasterio.open(
        root / "accum.tif", "w", driver="GTiff", height=8, width=16, count=1, dtype="float32", nodata=-1.0, crs=CRS,
        transform=Affine(8.0, 0.0, X0, 0.0, -8.0, Y0),
    ) as dst:  # fmt: skip
        dst.write(np.tile(np.linspace(1e4, 2e7, 16, dtype=np.float32), (8, 1)), 1)
    arf = {"areas_km2": AREAS, "composite": composite, **({"accumulation": str(root / "accum.tif")} if accumulation else {})}
    cfg = job(
        dem, 32, 16, 4.0,
        storm={
            "kind": "uniform", "depth_mm": 60.0, "duration_min": 10.0,
            "arf": {"areas_km2": [1.0, 1000.0], "factors": [1.0, 0.5], "table_type": "test table"},
        },
        boundaries=[{"kind": "free", "coordinates": [(X0 + 126.0, Y0), (X0 + 126.0, Y0 - 64.0)]}],
        run={"duration_s": 1500.0, "source_every_s": 30.0}, arf=arf,
        outputs={"lines": [{"name": "Outlet", "coordinates": DESIGN, "drainage_area_km2": 100.0}], "series_every_s": 10.0,
                 "map_every_s": 10.0},
    )  # fmt: skip
    study = arf_study(cfg, root / "study")
    assert study.exit_code == 0, study.message
    return root / "study", study


@pytest.fixture(scope="module")
def studied(tmp_path_factory):
    return make_study(tmp_path_factory.mktemp("with_raster"), True)


def runs(folder):
    return [folder / "runs" / run_name(a) for a in AREAS]


def test_a_line_between_the_runs_is_the_hand_weighted_blend_of_both(studied) -> None:
    folder, _study = studied
    found = read_study_line(folder, ACROSS, "across")
    area = (1e4 + 7.0 * (2e7 - 1e4) / 15.0) * 64.0 / 1e6
    said = found["study"]
    assert said["area_source"] == FROM_ACCUMULATION
    assert said["drainage_area_km2"] == pytest.approx(area, rel=1e-6)
    w = math.log(area / 10.0) / math.log(90.0)
    assert (said["low_km2"], said["high_km2"]) == (10.0, 900.0)
    assert said["weight_high"] == pytest.approx(w, abs=1e-6) and said["weight_low"] == pytest.approx(1.0 - w, abs=1e-6)
    low, high = (read_line(run, ACROSS, "across") for run in runs(folder))
    assert found["flow_m3s"] == pytest.approx([(1 - w) * a + w * b for a, b in zip(low["flow_m3s"], high["flow_m3s"], strict=True)], abs=1e-3)
    peak = {k: max(map(abs, r["flow_m3s"])) for k, r in (("low", low), ("high", high), ("found", found))}
    assert peak["high"] < peak["found"] < peak["low"] and peak["high"] > 0.0
    frame = int(np.argmax(found["deepest_m"]))
    ground = np.array(low["ground_m"], float)
    depth = [np.nan_to_num(np.array(r["level_m"][frame], dtype=float) - ground) for r in (low, high)]
    want = (1 - w) * np.maximum(depth[0], 0.0) + w * np.maximum(depth[1], 0.0)
    got = np.nan_to_num(np.array(found["level_m"][frame], dtype=float) - ground)
    np.testing.assert_allclose(got, want, atol=2e-3)
    assert len(found["speed_m_s"]) == len(found["t_s"]) and "weight" in said["words"]
    assert said["design_peak_m3s"] == pytest.approx(
        interpolate_peak(np.array(AREAS), np.array([max(map(abs, low["flow_m3s"])), max(map(abs, high["flow_m3s"]))]), area), abs=1e-3
    )


def test_a_line_laid_on_a_design_line_gives_the_studys_own_design_point_answer(studied) -> None:
    folder, study = studied
    found = read_study_line(folder, [list(p) for p in DESIGN], "on the design line")
    said, row = found["study"], study.table[0]
    assert said["area_source"] == FROM_DESIGN_LINE and said["drainage_area_km2"] == 100.0
    assert (said["low_km2"], said["high_km2"]) == (row["storm_area_low_km2"], row["storm_area_high_km2"])
    assert said["design_peak_m3s"] == pytest.approx(row["design_peak_m3s"], rel=0.02), "frames every 10 s, as the series"


def test_below_or_above_the_runs_the_end_run_holds_and_says_so(studied) -> None:
    folder, _study = studied
    west = read_study_line(folder, WEST, "west")
    assert west["study"]["clamped"] == "below" and west["study"]["low_km2"] == west["study"]["high_km2"] == 10.0
    assert west["flow_m3s"] == read_line(runs(folder)[0], WEST, "west")["flow_m3s"]
    assert "below the smallest storm area" in west["study"]["words"]
    east = read_study_line(folder, EAST, "east")
    assert east["study"]["clamped"] == "above" and east["study"]["low_km2"] == 900.0
    assert east["flow_m3s"] == read_line(runs(folder)[1], EAST, "east")["flow_m3s"]
    assert "above the largest storm area" in east["study"]["words"]


def test_the_command_reads_a_study_in_one_request_and_lists_its_lines_without_one_runs_record(studied, tmp_path) -> None:
    folder, _study = studied
    request = tmp_path / "line.json"
    request.write_text(json.dumps({"name": "across", "coordinates": ACROSS}), encoding="utf-8")
    assert main(["lines", str(folder), "--line", str(request), "--out", str(tmp_path / "a.json")]) == 0
    answer = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
    assert answer["study"]["low_km2"] == 10.0 and answer["study"]["high_km2"] == 900.0
    assert main(["lines", str(folder), "--out", str(tmp_path / "list.json")]) == 0
    listing = json.loads((tmp_path / "list.json").read_text(encoding="utf-8"))
    assert listing["study"] == {"areas_km2": AREAS, "accumulation": True}
    assert [set(line) for line in listing["lines"]] == [{"name", "coordinates"}]
    assert listing == study_catalogue(folder) | {}


def test_a_raster_kept_for_lines_alone_writes_no_composite_map(studied) -> None:
    folder, study = studied
    assert study.composite, "with the raster and the default, the composite maps are written as before"
    assert (folder / "composite" / "max_depth.tif").is_file()
    (folder.parent / "lines_only").mkdir(exist_ok=True)
    alone_folder, alone = make_study(folder.parent / "lines_only", True, composite=False)
    assert not alone.composite and not (alone_folder / "composite").exists()
    assert read_study_line(alone_folder, ACROSS, "across")["study"]["area_source"] == FROM_ACCUMULATION


def test_how_a_study_picks_its_areas_and_whether_it_maps_leave_the_job_hash_alone(tmp_path) -> None:
    from wadi2d.run import job_hash

    cfg = job(write_dem(tmp_path / "t.tif", tilted_box(16, 16, 2.0, 0.02), 2.0), 8, 8, 4.0)
    changed = cfg.model_copy(update={"arf": cfg.arf.model_copy(update={"by_arf_step": True, "arf_step_max": 0.02, "composite": False})})
    assert job_hash(changed) == job_hash(cfg)


def test_with_no_raster_a_line_reads_the_smallest_run_and_says_which(tmp_path) -> None:
    folder, _study = make_study(tmp_path, False)
    found = read_study_line(folder, ACROSS, "across")
    said = found["study"]
    assert said["drainage_area_km2"] is None and said["low_km2"] == said["high_km2"] == 10.0
    assert "no flow accumulation raster" in said["words"] and "10 km2 alone" in said["words"]
    assert found["flow_m3s"] == read_line(runs(folder)[0], ACROSS, "across")["flow_m3s"]
    on_design = read_study_line(folder, [list(p) for p in DESIGN], "design")
    assert on_design["study"]["area_source"] == FROM_DESIGN_LINE, "a design line keeps its own area with no raster"
