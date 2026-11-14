"""W75: a generated basin's diversion point runs as W72's diversion element, on the two arms of the conftest's valley."""

from __future__ import annotations

import json

import numpy as np
import pytest

from tests.basin.conftest import Valley
from tests.basin.test_points import ARM_ROW, SETTINGS, arm_col, elements, layer, model
from wadi2d.basin import load_network
from wadi2d.basin.build import build_basin
from wadi2d.hydrology import LumpedEngine, TimeGrid
from wadi2d.hydrology.model import Diversion
from wadi2d.run import load_job

GRID = TimeGrid(10.0, 40)
SOURCE = "minutes,flow\n0,0\n60,50\n240,0\n"


def points(valley: Valley, **diversion) -> list[dict]:
    """A source and a diversion on the west arm's junction, a junction on the east arm to take the diverted flow."""
    (valley.folder / "inflow.csv").write_text(SOURCE, encoding="utf-8")
    west, east = arm_col(ARM_ROW, -1), arm_col(ARM_ROW, 1)
    return [
        {"name": "In", "kind": "source", "file": "inflow.csv", "col": west, "row": ARM_ROW},
        {"name": "Div", "kind": "diversion", "divert_to": "JE", "col": west, "row": ARM_ROW, **diversion},
        {"name": "JE", "kind": "junction", "col": east, "row": ARM_ROW},
    ]


def run(m: dict):
    basin = load_network(m, skip_incomplete=True)
    below = basin.elements["Div"].downstream  # None here: the valley's reaches lack a Manning n, so they cut the network
    out = LumpedEngine(basin).run(None, GRID, only=[n for n in ("In", "Div", "JE", below) if n is not None])
    return basin, out, below


def test_an_inflow_function_point_diverts_and_closes_its_books(valley: Valley) -> None:
    m = model(valley, points(valley, method="inflow function", table="[[0, 0], [100, 40]]", limits='{"max_m3s": 15}'))
    block = elements(m)["Div"]["diversion"]
    assert block["method"] == "Inflow-Diversion Table" and block["tables"]["table"] == {"x": [0.0, 100.0], "y": [0.0, 40.0]}
    assert block["limits"] == {"max_flow_m3s": 15.0}
    basin, out, below = run(m)
    assert isinstance(basin.elements["Div"], Diversion) and basin.elements["Div"].branch == "JE"
    inflow = out.inflow["Div"]
    expected = np.minimum(0.4 * inflow, 15.0)
    assert np.allclose(out.branched["Div"], expected, atol=1e-12)
    assert out.branched["Div"].max() == pytest.approx(15.0)
    assert np.allclose(out.outflow["Div"] + out.branched["Div"], inflow, atol=1e-12)  # mass, per ordinate
    assert np.allclose(out.inflow["JE"], out.branched["Div"], atol=1e-12)  # all of the diverted flow arrives
    if below is not None:
        assert np.allclose(out.inflow[below], out.outflow["Div"], atol=1e-12)  # and all of what stays goes on
    assert inflow.sum() * GRID.dt_seconds == pytest.approx((out.outflow["Div"] + out.inflow["JE"]).sum() * GRID.dt_seconds)


def test_a_constant_point_with_a_volume_cap(valley: Valley) -> None:
    m = model(valley, points(valley, method="Constant Flow", parameters='{"rate_m3s": 10}', limits='{"max_volume_m3": 60000}'))
    _basin, out, _below = run(m)
    diverted = out.branched["Div"]
    assert diverted.max() == pytest.approx(10.0)
    assert diverted.sum() * GRID.dt_seconds == pytest.approx(60000.0)
    assert np.allclose(out.outflow["Div"] + diverted, out.inflow["Div"], atol=1e-12)


def test_a_lateral_weir_point_from_files_beside_the_layer_through_basin_json(valley: Valley) -> None:
    (valley.folder / "rating.csv").write_text("stage_m,flow_m3s\n100,0\n101,20\n102,80\n104,300\n", encoding="utf-8")
    pts = points(valley, method="Lateral Weir", table="rating.csv",
                 parameters='{"crest_m": 100.8, "length_m": 10, "coefficient": 1.6}')  # fmt: skip
    path = layer(valley.folder, pts)
    build_basin(load_job(valley.job), SETTINGS, path, valley.folder / "basin")
    saved = json.loads((valley.folder / "basin" / "basin.json").read_text(encoding="utf-8"))
    block = elements(saved)["Div"]["diversion"]
    assert block["tables"]["table"]["x"] == [100.0, 101.0, 102.0, 104.0]  # read into the file: it stands alone
    (valley.folder / "rating.csv").unlink()
    _basin, out, _below = run(saved)
    diverted = out.branched["Div"]
    assert 0.0 < diverted.max() < out.inflow["Div"].max()
    assert np.allclose(out.outflow["Div"] + diverted, out.inflow["Div"], atol=1e-9)
    assert np.allclose(out.inflow["JE"], diverted, atol=1e-12)
    stage = np.interp(out.outflow["Div"], [0, 20, 80, 300], [100, 101, 102, 104])  # the weir law at the passed flow
    head = np.maximum(stage - 100.8, 0.0)
    assert np.allclose(diverted, 1.6 * 10 * head**1.5, atol=1e-6)


def test_not_connected_leaves_the_network(valley: Valley) -> None:
    m = model(valley, points(valley, method="Constant Flow", parameters='{"rate_m3s": 5}', divert_to=""))
    basin, out, _below = run(m)
    assert basin.elements["Div"].branch is None
    assert out.branched["Div"].max() == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("fields", "words"),
    [
        ({"method": "weir"}, "method 'weir' is not one of"),
        ({"method": "Lateral Weir", "table": "[[100, 0], [101, 20]]", "parameters": '{"crest_m": 100.5}'}, "needs"),
        ({"method": "Constant Flow", "parameters": '{"rate_m3s": 5, "pattern": "x"}'}, "takes no \\['pattern'\\]"),
        ({"method": "Inflow-Diversion Table"}, "the table field is empty"),
        ({"method": "Constant Flow", "parameters": '{"rate_m3s": 5}', "divert_to": "Nowhere"}, "divert_to 'Nowhere'"),
        ({"method": "Constant Flow", "parameters": '{"rate_m3s": 5}', "divert_to": "In"}, "drains back into Div, a loop"),
        ({"method": "Constant Flow", "parameters": '{"rate_m3s": 5}', "limits": '{"max_cfs": 5}'}, "limits \\['max_cfs'\\]"),
    ],
)
def test_refusals_in_words(valley: Valley, fields: dict, words: str) -> None:
    with pytest.raises(ValueError, match=words):
        model(valley, points(valley, **fields))
