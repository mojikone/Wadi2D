"""Suggested breaklines on made-up ground: a wadi with a road across its plain, through the whole command.

The rules under test are his of 2026-11-01: a bank line either side of a defined wadi, never on the thalweg, one
bank where one exists, none where the stream is not incised; crests found by the top-hat, split at gaps.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import shapely
from rasterio.crs import CRS

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.breaklines import DEFAULTS, suggest
from wadi2d.breaklines.crests import top_hat
from wadi2d.breaklines.settings import BANK, DAM, LAYER, LEFT, RIGHT, ROAD, THALWEG_LAYER
from wadi2d.breaklines.thalweg import downstream, trace
from wadi2d.breaklines.window import Window, flow_fields
from wadi2d.engine.cli import main

pytest.importorskip("whitebox")

PIXEL = 2.0
NX, NY = 1000, 500
"""2 km by 1 km, the wadi along the middle falling east, its thalweg off any pixel boundary."""
DX = 10.0
MESH = {"stream_area_mid_km2": 0.05, "incision_width": 150.0}
AXIS = 503.0
AXIS_Y = Y0 - AXIS
ROAD_X = X0 + 1200.0


def _ground(valley: bool = True, channel: bool = True, road_gap: float = 40.0, one_bank: bool = False) -> np.ndarray:
    x = (np.arange(NX) + 0.5) * PIXEL
    y = (np.arange(NY) + 0.5) * PIXEL
    xx, yy = np.meshgrid(x, y)
    off = yy - AXIS
    plain = 200.0 - 0.01 * xx
    z = plain + 0.05 * np.abs(off) if valley else plain
    if channel:
        z = np.where(np.abs(off) < 30.0, plain - 3.0 + 0.01 * np.abs(off), z)
    if one_bank:  # the south wall stands; the north side is open ground at bed level, falling gently to the thalweg
        z = np.where(off < 30.0, plain - 3.0 + 0.001 * np.abs(off), plain + 0.05 * off)
    road = (np.abs(xx - 1200.0) < 10.0) & (np.abs(off) > road_gap)
    return np.where(road, z + 1.0, z)


def _suggest(tmp_path: Path, z: np.ndarray, settings=DEFAULTS, **mesh):
    dem = write_dem(tmp_path / "ground.tif", z, PIXEL)
    cfg = job(dem, NX * PIXEL / DX, NY * PIXEL / DX, DX, mesh={**MESH, **mesh})
    return suggest(cfg, tmp_path / "out", settings)


def _lines(path: str, layer: str = LAYER):
    db = sqlite3.connect(path)
    columns = [row[1] for row in db.execute(f"PRAGMA table_info({layer})")][2:]
    out = []
    for blob, *values in db.execute(f'SELECT geom, {", ".join(columns)} FROM "{layer}"'):
        out.append((shapely.from_wkb(blob[40:]), dict(zip(columns, values, strict=True))))
    db.close()
    return out


def _coords(geometry) -> np.ndarray:
    return np.asarray(geometry.geoms[0].coords)


@pytest.fixture(scope="module")
def wadi(tmp_path_factory):
    folder = tmp_path_factory.mktemp("wadi")
    summary = _suggest(folder, _ground(), replace(DEFAULTS, road_length_m=300.0))
    return summary, _lines(summary["path"]), _lines(summary["path"], THALWEG_LAYER)


def test_the_thalweg_runs_down_the_wadi(wadi):
    summary, _lines_found, thalwegs = wadi
    assert 1 <= summary["thalwegs"] == len(thalwegs) <= 2
    assert sum(row["length_m"] for _g, row in thalwegs) > 1500.0
    assert max(row["area_km2"] for _g, row in thalwegs) == pytest.approx(2.0, abs=0.1)  # the whole raster
    for geometry, row in thalwegs:
        assert row["incised_m"] > 2.0
        assert np.abs(_coords(geometry)[:, 1] - AXIS_Y).max() < 2 * DX / 2


def test_a_bank_line_stands_either_side_and_never_on_the_thalweg(wadi):
    _summary, lines, _thalwegs = wadi
    banks = [(g, r) for g, r in lines if r["kind"] == BANK]
    assert sorted(r["side"] for _g, r in banks) == [LEFT, RIGHT]
    for geometry, row in banks:
        y = _coords(geometry)[:, 1]
        assert np.abs(y - AXIS_Y).min() >= DX
        assert np.abs(y - AXIS_Y).max() <= 60.0
        assert (y > AXIS_Y).all() if row["side"] == LEFT else (y < AXIS_Y).all()
        assert row["length_m"] > 1500.0
        assert row["height_m"] == pytest.approx(float(row["why"].split(", ")[1].split(" m")[0]), abs=0.05)
        assert row["score"] == pytest.approx(row["height_m"] * row["length_m"])


def test_every_vertex_carries_the_ground_there(wadi):
    _summary, lines, _thalwegs = wadi
    for geometry, row in lines:
        assert geometry.has_z
        for x, y, z in geometry.geoms[0].coords:
            ground = 200.0 - 0.01 * (x - X0) + 0.05 * abs(y - AXIS_Y)
            if row["kind"] == BANK:
                assert -3.5 <= z - ground <= 0.5
            else:
                assert z == pytest.approx(ground + 1.0, abs=1.5)


def test_the_road_is_found_in_two_pieces_split_at_its_gap(wadi):
    summary, lines, _thalwegs = wadi
    crests = [(g, r) for g, r in lines if r["kind"] != BANK]
    assert len(crests) == 2 and summary["crests"] == 2
    for geometry, row in crests:
        xy = _coords(geometry)[:, :2]
        assert np.abs(xy[:, 0] - ROAD_X).max() < 2 * DX
        assert row["kind"] == ROAD, row
        assert row["height_m"] == pytest.approx(1.0, abs=0.15)
        assert 380.0 <= row["length_m"] <= 470.0
        assert row["area_km2"] == 0.0
    sides = sorted(_coords(g)[:, 1].mean() > AXIS_Y for g, _r in crests)
    assert sides == [False, True]


def test_the_lines_come_scored_and_the_biggest_first(wadi):
    _summary, lines, _thalwegs = wadi
    scores = [r["score"] for _g, r in lines]
    assert scores == sorted(scores, reverse=True)
    assert lines[0][1]["kind"] == BANK


def test_a_crest_across_the_wadi_reads_as_a_dam(tmp_path):
    summary = _suggest(tmp_path, _ground(road_gap=0.0))
    crests = [r for _g, r in _lines(summary["path"]) if r["kind"] != BANK]
    assert [r["kind"] for r in crests] == [DAM]
    assert crests[0]["area_km2"] == pytest.approx(2.0, abs=0.1)
    assert crests[0]["length_m"] > 900.0
    assert "crosses a wadi" in crests[0]["why"]


def test_a_plain_has_no_banks_and_no_crest_along_its_edge(tmp_path):
    summary = _suggest(tmp_path, _ground(valley=False, channel=False, road_gap=0.0), replace(DEFAULTS, road_length_m=300.0))
    lines = _lines(summary["path"])
    assert summary["banks"] == 0 and summary["crests"] == 1
    assert all(r["kind"] == ROAD for _g, r in lines)
    assert np.abs(_coords(lines[0][0])[:, 0] - ROAD_X).max() < 2 * DX


def test_one_bank_only_where_one_bank_exists(tmp_path):
    summary = _suggest(tmp_path, _ground(one_bank=True))
    banks = [r for _g, r in _lines(summary["path"]) if r["kind"] == BANK]
    assert {r["side"] for r in banks} == {RIGHT}, banks  # the wall is south: the right bank, looking east


def test_the_top_hat_sees_no_crest_on_a_plane_up_to_its_edge():
    x = (np.arange(200) + 0.5) * 5.0
    z = np.tile(100.0 + 0.1 * x, (120, 1)) + 0.1 * (np.arange(120) * 5.0)[:, None]
    assert np.abs(top_hat(z, 5.0, 40.0)).max() < 1e-6


def test_the_d8_pointer_codes_are_whiteboxes():
    def plane(east: float, south: float) -> Window:
        x = (np.arange(40) + 0.5) * 5.0
        z = np.tile(100.0 - east * x, (30, 1)) - south * (np.arange(30) * 5.0)[:, None]
        return Window(z, np.ones(z.shape, bool), X0, Y0, 5.0, 10.0, CRS.from_epsg(32640).to_wkt())

    _area, east = flow_fields(plane(0.05, 0.0))
    assert (east[2:-2, 2:-2] == 2).all()
    _area, south = flow_fields(plane(0.0, 0.05))
    assert (south[2:-2, 2:-2] == 8).all()
    tj, ti = downstream(south)
    assert (tj[5, 5], ti[5, 5]) == (6, 5)
    lines = trace(np.ones(south.shape, bool), south)
    assert all(len(ln) == 30 for ln in lines) and len(lines) == 40


def test_a_dem_without_a_crs_is_named_as_the_cause():
    z = np.tile(100.0 - 0.05 * (np.arange(40) + 0.5) * 5.0, (30, 1))
    with pytest.raises(RuntimeError, match="no CRS"):
        flow_fields(Window(z, np.ones(z.shape, bool), X0, Y0, 5.0, 10.0, ""))


def test_the_command_writes_the_file_and_says_what_it_holds(tmp_path, capsys):
    dem = write_dem(tmp_path / "ground.tif", _ground(), PIXEL)
    path = tmp_path / "job.json"
    path.write_text(job(dem, 200, 100, DX, mesh=MESH).model_dump_json(), encoding="utf-8")
    assert main(["breaklines", str(path), "--out", str(tmp_path / "out")]) == 0
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event["ev"] == "breaklines"
    assert Path(event["path"]).is_file() and event["layer"] == LAYER
    assert event["banks"] == 2 and event["crests"] == 2 and event["pixel_m"] == 5.0

