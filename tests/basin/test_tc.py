"""Kirpich's time of concentration at every element (W64): the formula by hand, and on a straight valley whose longest
paths are known from its geometry."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.basin.conftest import BED_SLOPE, NX, PIXEL, SIDE_SLOPE, col_x, row_y, straight_valley, write_raster
from tests.basin.test_model import SETTINGS, by_kind, complete_job, model_of
from wadi2d.basin import read_model
from wadi2d.basin.build import build_basin
from wadi2d.basin.contract import SOURCE_DERIVED, value_of
from wadi2d.basin.parameters import kirpich_tc_minutes
from wadi2d.config.schema import DesignPoint
from wadi2d.run import load_job

TOP_ROW, FOOT_ROW = 100, 250


def _hand_tc(length_m: float, slope: float) -> float:
    """His HMS expression written out: (0.75 L)^0.77 / (52 S^0.385), minutes."""
    return (0.75 * length_m) ** 0.77 / (52.0 * slope**0.385)


def _hand_path(rows: int) -> tuple[float, float]:
    """The far corner of the valley's top row to a point ``rows`` down the thalweg: across its row, then down.
    The 10-85 slope as `test_the_longest_path_of_a_straight_valley` takes it: bank, then bed."""
    across, along = NX // 2 * PIXEL, rows * PIXEL
    length = across + along
    bank_share = max(across - 0.15 * length, 0.0) / (0.75 * length)
    return length, bank_share * SIDE_SLOPE + (1.0 - bank_share) * BED_SLOPE


def test_the_kirpich_tc_by_hand() -> None:
    # L 10 km: 7,500 m on the 10-85 path; 7500^0.77 = 963.6, 0.01^0.385 = 0.16982, 963.6 / (52 x 0.16982) = 109.1 min
    assert kirpich_tc_minutes(10_000.0, 0.01) == pytest.approx(109.1, abs=0.1)
    assert kirpich_tc_minutes(10_000.0, 0.01) == pytest.approx(_hand_tc(10_000.0, 0.01), rel=1e-12)


@pytest.fixture
def two_points(tmp_path: Path) -> Path:
    dem = write_raster(tmp_path / "dem.tif", straight_valley())
    points = [
        DesignPoint(name="Top", x=col_x(NX // 2), y=row_y(TOP_ROW)),
        DesignPoint(name="Foot", x=col_x(NX // 2), y=row_y(FOOT_ROW)),
    ]
    return complete_job(tmp_path, dem, outputs={"points": [p.model_dump() for p in points]})


def _model(job: Path) -> dict:
    settings = SETTINGS.model_copy(update={"stream_threshold_km2": None, "snap_m": 0.0})
    return model_of(job, settings)


def test_every_element_carries_tc_on_the_longest_path_above_it(two_points: Path) -> None:
    model = _model(two_points)
    named = {e["name"]: e for e in model["elements"]}
    for rows, name in ((TOP_ROW, "Top"), (FOOT_ROW, "Foot")):
        length, slope = _hand_path(rows)
        node = named[name]
        assert value_of(node, "tc_flow_length_m") == pytest.approx(length, rel=0.02)
        assert value_of(node, "tc_slope_10_85") == pytest.approx(slope, rel=0.03)
        assert value_of(node, "tc_minutes") == pytest.approx(_hand_tc(length, slope), rel=0.03)
        assert node["parameters"]["tc_minutes"]["source"] == SOURCE_DERIVED
    # the reach between them carries its outlet's figure, and the foot's path is the longer one
    reach = by_kind(model, "reach")[0]
    assert reach["downstream"] == "Foot"
    assert value_of(reach, "tc_minutes") == value_of(named["Foot"], "tc_minutes")
    assert value_of(named["Foot"], "tc_minutes") > value_of(named["Top"], "tc_minutes")


def test_a_subbasin_tc_is_its_own_path_and_its_kirpich_lag_is_0_6_of_it(two_points: Path) -> None:
    model = _model(two_points)
    named = {e["name"]: e for e in model["elements"]}
    head = next(e for e in by_kind(model, "subbasin") if e["downstream"] == "Top")
    tc = value_of(head, "tc_minutes")
    assert tc == pytest.approx(_hand_tc(value_of(head, "flow_length_m"), value_of(head, "slope_10_85")), abs=0.01)
    assert value_of(head, "lag_minutes") == pytest.approx(0.6 * tc, abs=0.02)
    # the head subbasin's own path is the whole path above Top
    assert tc == pytest.approx(value_of(named["Top"], "tc_minutes"), rel=0.01)
    # the local subbasin between the points has a shorter path than the junction it drains to
    local = next(e for e in by_kind(model, "subbasin") if e["downstream"] == "Foot")
    assert value_of(local, "tc_minutes") < value_of(named["Foot"], "tc_minutes")


def test_an_older_basin_file_gains_the_subbasin_tc_on_reading(two_points: Path, tmp_path: Path) -> None:
    settings = SETTINGS.model_copy(update={"stream_threshold_km2": None, "snap_m": 0.0})
    build_basin(load_job(two_points), settings, None, tmp_path / "basin")
    path = tmp_path / "basin" / "basin.json"
    import json

    model = json.loads(path.read_text(encoding="utf-8"))
    for element in model["elements"]:
        element["parameters"].pop("tc_minutes", None)
    path.write_text(json.dumps(model), encoding="utf-8")
    read = read_model(path)
    assert all(value_of(e, "tc_minutes") > 0.0 for e in read["elements"])


def test_the_layers_carry_tc(two_points: Path, tmp_path: Path) -> None:
    settings = SETTINGS.model_copy(update={"stream_threshold_km2": None, "snap_m": 0.0})
    build_basin(load_job(two_points), settings, None, tmp_path / "basin")
    with sqlite3.connect(tmp_path / "basin" / "basin.gpkg") as db:
        for layer in ("subbasins", "reaches", "junctions"):
            values = [row[0] for row in db.execute(f"SELECT tc_minutes FROM {layer}")]
            assert values and all(v is not None and v > 0.0 for v in values), (layer, values)
