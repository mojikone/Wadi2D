"""Cut and fill against the analytic prism; the terrain rasters; what the CLI hands the plugin."""

from __future__ import annotations

import csv
import json
import math

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, job, write_dem
from tests.terrain.helpers import GROUND, flat_bed, grid_of, obj
from wadi2d.config.schema import Terrain
from wadi2d.engine.cli import main
from wadi2d.terrain import Ground, apply_objects
from wadi2d.terrain.report import preview_data, survey


def volumes(tmp_path, objects, cfg=None, maps=False):
    grid = grid_of()
    bed = flat_bed()
    cfg = cfg or Terrain()
    edits = apply_objects(grid, objects, 1.0, cfg, Ground(bed, grid.x0, grid.y0))
    return survey(cfg, grid, bed, edits, tmp_path, None, write_maps=maps)


def diagonal(length: float, angle: float = 45.0):
    ux, uy = math.cos(math.radians(angle)), -math.sin(math.radians(angle))
    half = 0.5 * length
    return [(160.0 - half * ux, 160.0 - half * uy), (160.0 + half * ux, 160.0 + half * uy)]


@pytest.mark.parametrize(
    "line", [[(160.0, 300.0), (160.0, 20.0)], diagonal(280.0)], ids=["straight", "diagonal"]
)
def test_a_cut_against_the_analytic_prism(tmp_path, line):
    # 3 m deep, 10 m bottom, 2:1 and 3:1 banks: area = (10 + (2 + 3) * 3 / 2) * 3
    channel = obj(
        "channel", line, z_constant=97.0, section={"width": 10.0, "left_slope": 2.0, "right_slope": 3.0}
    )
    row = volumes(tmp_path, [channel]).volumes[0]
    assert row["cut_m3"] == pytest.approx((10.0 + 2.5 * 3.0) * 3.0 * 280.0, rel=0.01)
    assert row["fill_m3"] == 0.0


@pytest.mark.parametrize(
    "line", [[(160.0, 300.0), (160.0, 20.0)], diagonal(280.0)], ids=["straight", "diagonal"]
)
def test_a_fill_against_the_analytic_prism_with_its_cones(tmp_path, line):
    # 2 m high, 4 m crest, 2:1 and 3:1 banks: prism, plus half a cone of each bank's slope at each end
    bank = obj(
        "embankment", line, z_constant=102.0, section={"width": 4.0, "left_slope": 2.0, "right_slope": 3.0}
    )
    prism = (4.0 + 2.5 * 2.0) * 2.0 * 280.0
    # the nose takes the outer slope of its side: half a cone and a half-crest wedge at each end
    cones = 2.0 * (math.pi * (4.0**2 + 6.0**2) / 2.0 * 2.0 / 3.0 / 2.0 + 0.5 * (4.0 + 6.0) * 2.0 * 2.0 / 2.0)
    row = volumes(tmp_path, [bank]).volumes[0]
    assert row["fill_m3"] == pytest.approx(prism + cones, rel=0.02)
    assert row["fill_m3"] > prism
    assert row["cut_m3"] == 0.0


def test_a_mixed_section_against_its_hand_area(tmp_path):
    # flat ground 100, bed 97, bottom 10. Left bank cut to the ground: slope 2 from 5 to 11.
    # Right bank top 102: inner slope 2 from 5 to 15, crest 3 to 18, outer slope 2 to 22.
    section = {
        "width": 10.0, "left_slope": 2.0, "right_slope": 2.0, "left_top_z": 99.0, "right_top_z": 102.0,
        "right_crest_width": 3.0, "right_outer_slope": 2.0, "left_crest_width": 1.0, "left_outer_slope": 2.0,
    }  # fmt: skip
    dyke = obj("channel_dyke", [(160.0, 310.0), (160.0, 10.0)], z_constant=97.0, section=section)
    row = volumes(tmp_path, [dyke]).volumes[0]
    cut = (10.0 * 3.0 + 3.0 * 6.0 / 2.0 + 3.0 * 6.0 / 2.0) * 300.0
    fill = (2.0 * 4.0 / 2.0 + 2.0 * 3.0 + 2.0 * 4.0 / 2.0) * 300.0
    assert row["cut_m3"] == pytest.approx(cut, rel=0.01)
    assert row["fill_m3"] == pytest.approx(fill, rel=0.02)


def test_volumes_by_station_add_up_and_follow_the_section(tmp_path):
    rows = [{"station": 0.0, "bed_z": 98.0, "width": 10.0}, {"station": 280.0, "bed_z": 96.0, "width": 10.0}]
    channel = obj(
        "channel",
        [(160.0, 300.0), (160.0, 20.0)],
        name="C1",
        section={"rows": rows, "left_slope": 0.0, "right_slope": 0.0},
    )
    report = volumes(tmp_path, [channel], Terrain(volume_step=70.0))
    with open(tmp_path / "volumes_by_station.csv", newline="", encoding="utf-8") as stream:
        table = list(csv.DictReader(stream))
    cut = [float(line["cut_m3"]) for line in table]
    assert len(cut) == 4
    assert table[0]["object"] == "C1"
    assert sum(cut) == pytest.approx(report.volumes[0]["cut_m3"], rel=1e-3)
    assert cut == sorted(cut)
    assert cut[0] == pytest.approx(10.0 * 70.0 * (2.0 + 0.25), rel=0.03)


def test_each_object_is_tallied_on_what_it_found(tmp_path):
    dam = obj(
        "embankment", [(40.0, 160.0), (280.0, 160.0)], z_constant=105.0, name="Dam", section={"width": 6.0}
    )
    drain = obj(
        "channel", [(160.0, 300.0), (160.0, 20.0)], z_constant=98.0, name="Drain", section={"width": 4.0}
    )
    first, second = volumes(tmp_path, [dam, drain]).volumes
    alone = volumes(tmp_path, [drain]).volumes[0]
    assert first["object"] == "Dam"
    assert second["cut_m3"] > alone["cut_m3"]  # it also cuts through the dam


def test_a_burn_line_is_tallied_too(tmp_path):
    burn = obj("burn_line", [(160.0, 300.0), (160.0, 20.0)], width=4.0, depth=1.0)
    assert volumes(tmp_path, [burn]).volumes[0]["cut_m3"] == pytest.approx(4.0 * 280.0, rel=0.05)


def test_the_rasters_hold_the_new_ground_and_the_change(tmp_path):
    channel = obj("channel", [(160.0, 300.0), (160.0, 20.0)], z_constant=97.0, section={"width": 10.0})
    report = volumes(tmp_path, [channel], maps=True)
    grid = grid_of()
    with rasterio.open(report.files["modified"]) as new, rasterio.open(report.files["change"]) as change:
        row, col = round(grid.y0 - 160.5), round(160.5 - grid.x0)
        window = ((row, row + 1), (col, col + 1))
        assert new.read(1, window=window)[0, 0] == pytest.approx(97.0)
        assert change.read(1, window=window)[0, 0] == pytest.approx(-3.0)
        assert new.res == (1.0, 1.0)


def test_the_preview_says_what_each_bank_is(tmp_path):
    section = {"width": 10.0, "left_top_z": 99.0, "right_top_z": 102.0}
    dyke = obj(
        "channel_dyke",
        [(160.0, 300.0), (160.0, 20.0)],
        z_constant=97.0,
        section=section,
        openings=[{"start": 100.0, "end": 140.0, "side": "right"}],
    )
    grid = grid_of()
    bed = flat_bed()
    cfg = Terrain(preview_sections=3)
    ground = Ground(bed, grid.x0, grid.y0)
    edits = apply_objects(grid, [dyke], 1.0, cfg, ground)
    data = preview_data([dyke], ground, grid.dx, cfg, edits.shapes)[0]
    assert set(data["left_state"]) == {"cut"}
    assert set(data["right_state"]) == {"dyke", "open"}
    assert data["ground"][0] == GROUND
    assert data["new"][0] == 97.0
    assert len(data["sections"]) == 3
    section_row = data["sections"][1]
    assert min(section_row["new"]) == 97.0
    assert max(section_row["new"]) == 102.0
    assert section_row["station"] == pytest.approx(140.0)


def test_the_terrain_command_needs_no_run_and_says_what_it_found(tmp_path, capsys):
    dem = write_dem(tmp_path / "d.tif", np.full((64, 64), 100.0), 2.0)
    line = [(X0 + 20.0, Y0 - 60.0), (X0 + 100.0, Y0 - 60.0)]
    objects = [
        {
            "kind": "channel",
            "name": "C",
            "coordinates": line,
            "z": [101.0, 102.0],
            "section": {"width": 12.0},
        },
    ]
    cfg = job(dem, 16, 16, 8.0, terrain={"objects": objects})
    path = tmp_path / "job.json"
    path.write_text(cfg.model_dump_json(), encoding="utf-8")
    assert main(["terrain", str(path), "--out", str(tmp_path / "t")]) == 0
    said = json.loads(capsys.readouterr().out)
    assert any("adverse" in note for note in said["notes"])
    assert any("above the ground" in note for note in said["notes"])
    assert said["volumes"][0]["object"] == "C"
    assert (tmp_path / "t" / "preview.json").is_file()
    assert (tmp_path / "t" / "terrain_modified.tif").is_file()


def test_the_terrain_command_refuses_in_words_a_table_out_of_order(tmp_path, capsys):
    dem = write_dem(tmp_path / "d.tif", np.full((64, 64), 100.0), 2.0)
    table = tmp_path / "s.csv"
    table.write_text("station,bed_z\n50,99\n10,98\n", encoding="utf-8")
    objects = [
        {
            "kind": "channel",
            "coordinates": [(X0 + 20.0, Y0 - 60.0), (X0 + 100.0, Y0 - 60.0)],
            "section": {"table": str(table)},
        }
    ]
    path = tmp_path / "job.json"
    path.write_text(job(dem, 16, 16, 8.0, terrain={"objects": objects}).model_dump_json(), encoding="utf-8")
    assert main(["terrain", str(path), "--out", str(tmp_path / "t")]) == 2
    assert "stations must increase" in capsys.readouterr().err
