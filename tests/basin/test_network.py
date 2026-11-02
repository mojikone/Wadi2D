"""Delineation against a catchment known without it."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tests.basin.conftest import ARM_OFFSET, FORK_ROW, NX, NY, PIXEL, Valley, col_x, row_y, write_job
from wadi2d.basin.delineate import flow_surface, read_surface
from wadi2d.basin.kernels import NONE, accumulate, trace_links, upstream_first
from wadi2d.basin.network import build_network
from wadi2d.basin.pour import PourPoint, collect_at_dams, crossing, crossings, gather, snapped
from wadi2d.config.schema import BasinSettings, DesignLine, DesignPoint, Outputs, TerrainObject
from wadi2d.mesh.streams import drainage_area
from wadi2d.run import load_job

KM2_PER_PIXEL = PIXEL**2 / 1e6
SETTINGS = BasinSettings(stream_threshold_km2=0.5, snap_m=30.0, min_reach_m=0.0, min_subbasin_km2=0.0)


def surface_of(job: Path, settings: BasinSettings = SETTINGS):
    return flow_surface(*read_surface(load_job(job), settings))


def outlet(surface) -> int:
    return int(np.argmax(surface.count))


def test_kernels_on_a_hand_made_line() -> None:
    # 0 -> 1 -> 2 <- 3
    down = np.array([1, 2, NONE, 2], dtype=np.int64)
    order = upstream_first(down)
    assert list(order).index(2) == 3
    count = accumulate(down, order, np.ones(4, dtype=bool))
    assert count.tolist() == [1, 2, 4, 1]


def test_a_cycle_is_seen() -> None:
    assert upstream_first(np.array([1, 0, NONE], dtype=np.int64)).size < 3


def test_every_pixel_reaches_the_one_outlet(valley: Valley) -> None:
    surface = surface_of(valley.job)
    assert surface.count.max() == NY * NX
    assert surface.down[outlet(surface)] == NONE


def test_own_area_equals_whitebox_area(valley: Valley) -> None:
    surface = surface_of(valley.job)
    theirs = drainage_area(surface.z, surface.pixel, surface.x0, surface.y0, "EPSG:32640")
    assert np.array_equal(surface.count.reshape(surface.shape) * PIXEL**2, theirs)


def test_the_valley_gives_three_links_and_three_headwaters_split_by_the_ridge(valley: Valley) -> None:
    surface = surface_of(valley.job)
    net = build_network(surface, {}, SETTINGS)
    heads = [link for link in range(net.tops.size) if net.start_node[link] == NONE]
    assert len(heads) == 2
    pixels = np.bincount(net.label[net.label != NONE], minlength=net.tops.size)
    assert pixels.sum() == NY * NX
    for link in heads:
        assert pixels[link] == pytest.approx(FORK_ROW * NX / 2, rel=0.05)
    assert net.nodes.size == 2  # the confluence and the outlet


def test_a_node_pixel_closes_the_largest_stream() -> None:
    # 0 -> 2, 1 -> 2 -> 3; pixel 1 drains more
    down = np.array([2, 2, 3, NONE], dtype=np.int64)
    count = np.array([5, 9, 15, 16], dtype=np.int64)
    stream = np.ones(4, dtype=bool)
    node = np.array([False, False, True, True])
    link, _tops, bottoms, above_top = trace_links(down, upstream_first(down), stream, node, count)
    assert link[1] == link[2]
    assert link[0] != link[1]
    assert bottoms[link[0]] == 0
    assert above_top[link[3]] == 2


def test_the_subbasins_above_a_pour_point_hold_exactly_its_drainage_area(valley: Valley) -> None:
    surface = surface_of(valley.job)
    pixel = surface.flat(col_x(NX // 2), row_y(220))
    net = build_network(surface, {pixel: PourPoint("Site", "layer", pixel, 0.0, 0.0)}, SETTINGS)
    assert pixel in net.nodes
    pixels = np.bincount(net.label[net.label != NONE], minlength=net.tops.size)
    held = 0
    pending = [pixel]
    while pending:
        node = pending.pop()
        for link in np.flatnonzero(net.end_node == node):
            held += pixels[link]
            if net.start_node[link] != NONE:
                pending.append(int(net.start_node[link]))
    assert held == surface.count[pixel]


def test_with_no_threshold_a_pour_point_alone_makes_the_network(valley: Valley) -> None:
    settings = SETTINGS.model_copy(update={"stream_threshold_km2": None})
    surface = surface_of(valley.job, settings)
    pixel = surface.flat(col_x(NX // 2), row_y(220))
    net = build_network(surface, {pixel: PourPoint("Site", "layer", pixel, 0.0, 0.0)}, settings)
    assert net.nodes.size == 2
    assert net.tops.size == 2


def test_no_stream_and_no_point_says_so(valley: Valley) -> None:
    settings = SETTINGS.model_copy(update={"stream_threshold_km2": 1e5})
    with pytest.raises(ValueError, match="no stream"):
        build_network(surface_of(valley.job, settings), {}, settings)


def test_a_small_catchment_joins_a_neighbour_at_its_junction(valley: Valley) -> None:
    settings = SETTINGS.model_copy(update={"min_subbasin_km2": 0.2})
    surface = surface_of(valley.job, settings)
    pixel = surface.flat(col_x(NX // 2 - ARM_OFFSET), row_y(FORK_ROW - 3))
    point = {pixel: PourPoint("Near fork", "layer", pixel, 0.0, 0.0)}
    plain = build_network(surface, point, SETTINGS)
    joined = build_network(surface, point, settings)
    assert joined.joined
    assert joined.subbasins.size < plain.subbasins.size
    assert np.array_equal(joined.label == NONE, plain.label == NONE)


def test_a_line_lands_on_the_wadi_it_crosses(valley: Valley) -> None:
    surface = surface_of(valley.job)
    y = row_y(250)
    pixel = crossing(surface, [(col_x(40), y), (col_x(160), y)])
    assert surface.xy(pixel)[0] == pytest.approx(col_x(NX // 2), abs=2 * PIXEL)


def test_a_point_snaps_to_the_nearest_stream(valley: Valley) -> None:
    surface = surface_of(valley.job)
    pixel = snapped(surface, col_x(NX // 2 + 2), row_y(250), SETTINGS)
    assert abs(surface.xy(pixel)[0] - col_x(NX // 2)) <= PIXEL
    assert surface.count[pixel] * KM2_PER_PIXEL >= SETTINGS.stream_threshold_km2


def test_gather_settles_shared_pixels_and_reports_what_it_drops(valley: Valley) -> None:
    surface = surface_of(valley.job)
    y = row_y(250)
    ring = [(col_x(10), row_y(10)), (col_x(30), row_y(10)), (col_x(30), row_y(30)), (col_x(10), row_y(10))]
    cfg = load_job(valley.job).model_copy(
        update={
            "outputs": Outputs(
                lines=[
                    DesignLine(name="Axis", coordinates=[(col_x(60), y), (col_x(140), y)]),
                    DesignLine(name="Same axis", coordinates=[(col_x(70), y), (col_x(130), y)]),
                    DesignLine(name="Ring", coordinates=ring),
                ],
                points=[DesignPoint(name="Off", x=0.0, y=0.0)],
            )
        }
    )
    notes: list[str] = []
    _surface, points = gather(cfg, surface, SETTINGS, None, notes)
    assert [p.name for p in points.values()] == ["Axis"]
    assert next(iter(points.values())).aliases == ["Same axis"]
    assert any("Ring" in note for note in notes)
    assert any("Off" in note for note in notes)


def test_a_design_line_across_two_arms_gets_one_node_on_each(valley: Valley) -> None:
    surface = surface_of(valley.job)
    y = row_y(FORK_ROW // 2)
    line = [(col_x(20), y), (col_x(180), y)]
    pixels = crossings(surface, line, 0.5 / KM2_PER_PIXEL)
    assert len(pixels) == 2
    cfg = load_job(valley.job).model_copy(
        update={"outputs": Outputs(lines=[DesignLine(name="Across", coordinates=line)])}
    )
    _surface, points = gather(cfg, surface, SETTINGS, None, [])
    assert sorted(p.name for p in points.values()) == ["Across", "Across 2"]
    assert {p.line for p in points.values()} == {"Across"}


def test_a_dam_stops_every_stream_across_its_line(valley: Valley) -> None:
    surface = surface_of(valley.job)
    y = row_y(FORK_ROW // 2)
    line = [(col_x(20), y), (col_x(180), y)]
    crest = TerrainObject(kind="crest_line", name="Long", coordinates=line, z_constant=200.0)
    pixel = crossing(surface, line)
    natural = surface.count[pixel]
    dam = PourPoint("Long", "dam", pixel, 0.0, 0.0, crest=crest)
    collected = collect_at_dams(surface, [dam])
    assert collected.count[pixel] > 1.9 * natural
    assert collected.count.max() == surface.count.max()
    assert surface.count[pixel] == natural


def test_a_dam_on_a_small_wadi_is_a_node_and_a_saddle_is_not(valley: Valley) -> None:
    surface = surface_of(valley.job)
    y = row_y(20)
    small = TerrainObject(
        kind="crest_line", name="Small", coordinates=[(col_x(20), y), (col_x(80), y)], z_constant=200.0
    )
    saddle = TerrainObject(
        kind="crest_line", name="Saddle", coordinates=[(col_x(0), y), (col_x(4), y)], z_constant=200.0
    )
    terrain = load_job(valley.job).terrain.model_copy(update={"objects": [small, saddle]})
    cfg = load_job(valley.job).model_copy(update={"terrain": terrain})
    settings = SETTINGS.model_copy(update={"stream_threshold_km2": 5.0, "dam_min_km2": 0.01})
    notes: list[str] = []
    _surface, points = gather(cfg, surface, settings, None, notes)
    assert [p.name for p in points.values()] == ["Small"]
    assert any("Saddle" in note for note in notes)


def test_a_node_above_a_confluence_on_the_smaller_stream_still_drains_to_it(
    tmp_path: Path, valley: Valley
) -> None:
    surface = surface_of(valley.job)
    net = build_network(surface, {}, SETTINGS)
    fork = int(net.end_node[np.flatnonzero(net.start_node == NONE)[0]])
    smaller = min(
        (p for p in np.flatnonzero(surface.down == fork) if surface.count[p] > 100),
        key=lambda p: surface.count[p],
    )
    point = {int(smaller): PourPoint("Beside", "layer", int(smaller), 0.0, 0.0)}
    joined = build_network(surface, point, SETTINGS)
    assert int(smaller) in joined.nodes
    assert not np.any(joined.start_node == smaller)


def test_the_domain_cuts_the_catchment(tmp_path: Path, valley: Valley) -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                (col_x(0), row_y(FORK_ROW)),
                (col_x(NX - 1), row_y(FORK_ROW)),
                (col_x(NX - 1), row_y(NY - 1)),
                (col_x(0), row_y(NY - 1)),
                (col_x(0), row_y(FORK_ROW)),
            ]
        ],
    }
    domain = tmp_path / "domain.geojson"
    domain.write_text(
        json.dumps({"type": "Feature", "properties": {}, "geometry": polygon}), encoding="utf-8"
    )
    job = write_job(tmp_path, valley.dem, grid={"domain": str(domain)})
    surface = surface_of(job)
    assert surface.valid.sum() < 0.51 * NY * NX
    assert surface.count.max() == surface.valid.sum()
