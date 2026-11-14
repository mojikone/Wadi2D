"""The Basin points layer (W73): kinds that break the network, edits that change it, sources and outfalls, on the two arms
joining one valley of the conftest, where every area is known by hand."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tests.basin.conftest import ARM_OFFSET, FORK_ROW, NX, NY, PIXEL, Valley, col_x, row_y
from wadi2d.basin import load_network
from wadi2d.basin.build import assemble, build_basin
from wadi2d.basin.contract import value_of
from wadi2d.config.schema import BasinSettings
from wadi2d.hydrology import LumpedEngine, TimeGrid
from wadi2d.run import load_job

SETTINGS = BasinSettings(stream_threshold_km2=0.5, snap_m=30.0, min_reach_m=0.0, min_subbasin_km2=0.0)
KM2 = PIXEL**2 / 1e6
LOW, ARM_ROW = 220, 100
"""A junction on the main valley; the row of the junctions on the arms."""


def arm_col(row: int, side: int) -> int:
    """The column of an arm's bed at a row north of the fork; side -1 west, +1 east."""
    return NX // 2 + side * round(ARM_OFFSET * (FORK_ROW - row) / FORK_ROW)


def layer(folder: Path, points: list[dict]) -> Path:
    """A GeoJSON point layer in the DEM's CRS; ``col`` and ``row`` give the place, the rest are its fields."""
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [col_x(p.pop("col")), row_y(p.pop("row"))]},
            "properties": p,
        }
        for p in points
    ]
    path = folder / "basin_points.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


def model(valley: Valley, points: list[dict] | None = None, settings: BasinSettings = SETTINGS) -> dict:
    path = None if points is None else layer(valley.folder, points)
    return assemble(load_job(valley.job), settings, path).model


def elements(m: dict, kind: str | None = None) -> dict[str, dict]:
    return {e["name"]: e for e in m["elements"] if kind is None or e["kind"] == kind}


def area_above(m: dict, name: str) -> float:
    """The subbasin area draining to an element, by walking the file."""
    by = elements(m)
    total = 0.0
    for element in m["elements"]:
        if element["kind"] != "subbasin":
            continue
        at = element["downstream"]
        while at is not None and at != name:
            at = by[at]["downstream"]
        if at == name:
            total += value_of(element, "area_km2")
    return total


def arms() -> list[dict]:
    return [
        {"name": "JW", "kind": "junction", "col": arm_col(ARM_ROW, -1), "row": ARM_ROW},
        {"name": "JE", "kind": "junction", "col": arm_col(ARM_ROW, 1), "row": ARM_ROW},
    ]


def test_a_layer_without_kinds_reads_as_before(valley: Valley) -> None:
    plain = model(valley, [{"name": "Site", "col": NX // 2, "row": LOW}])
    assert "Site" in elements(plain, "junction")
    assert "role" not in elements(plain)["Site"]["pour_point"]


def test_a_junction_point_splits_the_reach_and_the_subbasin(valley: Valley) -> None:
    plain = model(valley)
    split = model(valley, [{"name": "Site", "kind": "junction", "col": NX // 2, "row": LOW}])
    assert len(elements(split, "subbasin")) == len(elements(plain, "subbasin")) + 1
    assert len(elements(split, "reach")) == len(elements(plain, "reach")) + 1
    site = elements(split)["Site"]
    assert area_above(split, "Site") == pytest.approx(value_of(site, "drainage_area_km2"), abs=1e-3)
    assert site["pour_point"]["role"] == "junction"


def test_remove_junction_joins_the_reaches_through_a_confluence(valley: Valley) -> None:
    site = {"name": "Site", "kind": "junction", "col": NX // 2, "row": LOW}
    plain = model(valley, [*arms(), dict(site)])
    fork = next(n for n, e in elements(plain, "junction").items() if e["downstream"] and n not in ("JW", "JE", "Site")
                and elements(plain)[e["downstream"]]["kind"] == "reach")
    gone = model(valley, [*arms(), dict(site), {"name": "X", "kind": "remove_junction", "col": NX // 2, "row": FORK_ROW}])
    assert fork not in elements(gone)
    reaches = {e["downstream"]: e for e in elements(plain, "reach").values()}
    into_fork = [e for e in elements(plain, "reach").values() if e["downstream"] == fork]
    below_fork = next(e for e in elements(plain, "reach").values() if elements(plain)[fork]["downstream"] == e["name"])
    assert len(into_fork) == 2 and reaches
    joined = [e for e in elements(gone, "reach").values() if e["downstream"] == "Site"]
    assert len(joined) == 2  # the main arm and the tributary both run on to Site
    length = sorted(value_of(e, "length_m") for e in joined)
    expected = sorted(value_of(e, "length_m") + value_of(below_fork, "length_m") for e in into_fork)
    assert length == pytest.approx(expected, abs=2 * PIXEL * np.sqrt(2))
    # nothing is lost: what drains to Site is its drainage area, with or without the fork
    assert area_above(gone, "Site") == pytest.approx(value_of(elements(gone)["Site"], "drainage_area_km2"), abs=1e-3)
    assert area_above(gone, "Site") == pytest.approx(area_above(plain, "Site"), abs=1e-3)


@pytest.mark.parametrize(
    ("where", "words"),
    [((NX // 2, LOW), "delete that point instead"), ((NX // 2, NY - 1), "an outlet stays"), ((10, 10), "no junction")],
)
def test_remove_junction_refuses_in_words(valley: Valley, where: tuple[int, int], words: str) -> None:
    points = [{"name": "Site", "kind": "junction", "col": NX // 2, "row": LOW}]
    points.append({"name": "X", "kind": "remove_junction", "col": where[0], "row": where[1]})
    with pytest.raises(ValueError, match=words):
        model(valley, points)


def test_join_subbasins_makes_one_of_the_two_arms(valley: Valley) -> None:
    plain = model(valley)
    fork = next(n for n, e in elements(plain, "junction").items() if e["downstream"] is not None)
    arms_plain = [e for e in elements(plain, "subbasin").values() if e["downstream"] == fork]
    joined = model(valley, [{"name": "Join", "kind": "join_subbasins", "col": NX // 2, "row": FORK_ROW}])
    arms_joined = [e for e in elements(joined, "subbasin").values() if e["downstream"] == fork]
    assert len(arms_plain) == 2 and len(arms_joined) == 1
    total = sum(value_of(e, "area_km2") for e in arms_plain)
    assert value_of(arms_joined[0], "area_km2") == pytest.approx(total, abs=1e-3)
    assert value_of(arms_joined[0], "tc_minutes") is not None  # recomputed on the merged path


def test_join_subbasins_with_one_local_subbasin_refuses(valley: Valley) -> None:
    points = [{"name": "Site", "kind": "junction", "col": NX // 2, "row": LOW}]
    points.append({"name": "J", "kind": "join_subbasins", "col": NX // 2, "row": LOW})
    with pytest.raises(ValueError, match="nothing to join"):
        model(valley, points)


def test_two_outfalls_make_two_networks_in_one_generation(valley: Valley) -> None:
    both = model(
        valley,
        [
            {"name": "OW", "kind": "outfall", "col": arm_col(ARM_ROW, -1), "row": ARM_ROW},
            {"name": "OE", "kind": "outfall", "col": arm_col(ARM_ROW, 1), "row": ARM_ROW},
        ],
    )
    by = elements(both)
    assert by["OW"]["downstream"] is None and by["OE"]["downstream"] is None
    for name in ("OW", "OE"):
        assert area_above(both, name) == pytest.approx(value_of(by[name], "drainage_area_km2"), abs=1e-3)
    total = sum(value_of(e, "area_km2") for e in elements(both, "subbasin").values())
    assert total == pytest.approx(value_of(by["OW"], "drainage_area_km2") + value_of(by["OE"], "drainage_area_km2"))
    assert any("drain to no outfall" in note for note in both["notes"])
    assert both["analysis"]["unassigned_km2"] == pytest.approx(NY * NX * KM2 - total, abs=1e-3)


def test_an_outfall_above_another_stays_in_its_network(valley: Valley) -> None:
    m = model(
        valley,
        [
            {"name": "Up", "kind": "outfall", "col": arm_col(ARM_ROW, -1), "row": ARM_ROW},
            {"name": "Down", "kind": "outfall", "col": NX // 2, "row": LOW},
        ],
    )
    assert elements(m)["Up"]["downstream"] is not None
    assert elements(m)["Down"]["downstream"] is None


def test_a_source_enters_the_network_at_its_junction(valley: Valley) -> None:
    (valley.folder / "inflow.csv").write_text("minutes,flow\n0,0\n60,50\n180,0\n", encoding="utf-8")
    m = model(valley, [{"name": "Wadi X", "kind": "source", "file": "inflow.csv", "col": NX // 2, "row": LOW}])
    source = elements(m, "source")["Wadi X"]
    junction = elements(m)[source["downstream"]]
    assert junction["kind"] == "junction" and junction["name"] != "Wadi X"
    assert value_of(source, "hydrograph") == {"minutes": [0.0, 60.0, 180.0], "flow_m3s": [0.0, 50.0, 0.0]}
    basin = load_network(m, skip_incomplete=True)
    grid = TimeGrid(10.0, 30)
    run = LumpedEngine(basin).run(None, grid, only=["Wadi X", junction["name"]])
    expected = np.interp(np.arange(31) * 10.0, [0.0, 60.0, 180.0], [0.0, 50.0, 0.0], right=0.0)
    assert np.allclose(run.outflow["Wadi X"], expected)
    assert np.allclose(run.inflow[junction["name"]], expected)


def test_a_source_area_counts_in_the_drainage_area_below(valley: Valley) -> None:
    """W75: as HMS counts a source's representative area; none, and the ground's area stands, said in the notes."""
    (valley.folder / "inflow.csv").write_text("minutes,flow\n0,0\n60,50\n180,0\n", encoding="utf-8")
    at = {"col": arm_col(ARM_ROW, -1), "row": ARM_ROW}
    low = {"name": "Low", "kind": "junction", "col": NX // 2, "row": LOW}
    bare = model(valley, [{"name": "Wadi X", "kind": "source", "file": "inflow.csv", **at}, dict(low)])
    given = model(valley, [{"name": "Wadi X", "kind": "source", "file": "inflow.csv", "area_km2": 12.5, **at}, dict(low)])
    assert any("no area_km2" in note for note in bare["notes"])
    assert any("12.5 km2 is in the drainage area" in note for note in given["notes"])
    entry = elements(given, "source")["Wadi X"]["downstream"]
    for name in (entry, "Low"):
        before, after = (value_of(elements(m)[name], "drainage_area_km2") for m in (bare, given))
        assert after == pytest.approx(before + 12.5, abs=1e-4)
    assert value_of(elements(given)["JE"] if "JE" in elements(given) else elements(given)["Low"], "drainage_area_km2")
    engine_bare, engine_given = (load_network(m, skip_incomplete=True) for m in (bare, given))
    assert engine_given.drainage_area(entry) == pytest.approx(engine_bare.drainage_area(entry) + 12.5)
    assert engine_given.drainage_area("Wadi X") == pytest.approx(12.5)


def test_a_source_without_a_file_refuses(valley: Valley) -> None:
    with pytest.raises(ValueError, match="needs a file"):
        model(valley, [{"name": "S", "kind": "source", "col": NX // 2, "row": LOW}])


def test_a_diversion_point_carries_its_block(valley: Valley) -> None:
    m = model(
        valley,
        [
            {"name": "Div", "kind": "diversion", "method": "Inflow-Diversion Table", "divert_to": "Site",
             "table": "[[0, 0], [500, 100]]", "limits": '{"max_m3s": 50}', "col": NX // 2, "row": 180},
            {"name": "Site", "kind": "design_point", "alias": "S-1", "col": NX // 2, "row": LOW},
        ],
    )  # fmt: skip
    div = elements(m)["Div"]
    assert div["kind"] == "junction"
    assert div["diversion"] == {  # read for the element at generation since W75
        "method": "Inflow-Diversion Table", "divert_to": "Site", "table": "[[0, 0], [500, 100]]", "parameters": None,
        "limits": {"max_flow_m3s": 50.0}, "point": "Div", "tables": {"table": {"x": [0.0, 500.0], "y": [0.0, 100.0]}},
    }  # fmt: skip
    assert elements(m)["Site"]["pour_point"]["aliases"] == ["S-1"]


def test_a_dam_point_without_its_crest_line_stays_a_junction(valley: Valley) -> None:
    m = model(valley, [{"name": "Dam A", "kind": "dam", "crest_line": "Nope", "col": NX // 2, "row": LOW}])
    assert elements(m)["Dam A"]["kind"] == "junction"
    assert any("W58 decision 4" in note for note in m["notes"])


def test_an_unknown_kind_is_refused_by_name(valley: Valley) -> None:
    with pytest.raises(ValueError, match="kind 'weir'"):
        model(valley, [{"name": "P", "kind": "weir", "col": NX // 2, "row": LOW}])


def test_the_files_take_the_sources(valley: Valley) -> None:
    (valley.folder / "inflow.csv").write_text("minutes,flow\n0,0\n60,50\n180,0\n", encoding="utf-8")
    path = layer(valley.folder, [{"name": "Wadi X", "kind": "source", "file": "inflow.csv", "col": NX // 2, "row": LOW}])
    build_basin(load_job(valley.job), SETTINGS, path, valley.folder / "basin")
    again = json.loads((valley.folder / "basin" / "basin.json").read_text(encoding="utf-8"))
    assert "Wadi X" in elements(again, "source")
