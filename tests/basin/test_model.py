"""The basin model: parameters against hand numbers, the contract, the loader, the routes, the command."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from tests.basin.conftest import (
    BED_SLOPE,
    NX,
    NY,
    PIXEL,
    SIDE_SLOPE,
    Valley,
    col_x,
    row_y,
    straight_valley,
    valley_dem,
    write_job,
    write_raster,
)
from wadi2d.basin import junction_routes, load_network, read_model, refresh
from wadi2d.basin.build import assemble
from wadi2d.basin.contract import SOURCE_JOB, SOURCE_RASTER, SOURCE_USER, check_model, value_of
from wadi2d.basin.elements import Namer
from wadi2d.basin.kernels import NONE
from wadi2d.basin.parameters import hms_kirpich_lag_minutes, index_celerity, nrcs_lag_minutes
from wadi2d.basin.routes import ROUTE_NONE, ROUTE_REACH
from wadi2d.config.schema import REACH_CONSERVING, REACH_HMS, BasinSettings, DesignPoint, RunConfig
from wadi2d.engine.cli import main
from wadi2d.hydrology import LumpedEngine, TimeGrid
from wadi2d.hydrology.model import Junction, Reach, Reservoir, Subbasin
from wadi2d.hydrology.reservoir import ReservoirOutflowStructures
from wadi2d.run import EXIT_INVALID, load_job
from wadi2d.storm import HypotheticalStorm, PercentPattern

SETTINGS = BasinSettings(
    stream_threshold_km2=0.5, snap_m=30.0, section_half_width_m=300.0, section_search_m=20.0
)
STORM = HypotheticalStorm(
    depth_mm=100.0,
    pattern=PercentPattern(np.array([0.0, 100.0]), np.array([0.0, 100.0])),
    duration_hours=6.0,
)
GRID = TimeGrid(5.0, 288)


def complete_job(folder: Path, dem: Path, **parts) -> Path:
    cn = write_raster(folder / "cn.tif", np.full((NY, NX), 85.0))
    terrain = {"cn_raster": str(cn), "manning": 0.05, **parts.pop("terrain", {})}
    return write_job(folder, dem, terrain=terrain, **parts)


def by_kind(model: dict, kind: str) -> list[dict]:
    return [e for e in model["elements"] if e["kind"] == kind]


def model_of(job: Path, settings: BasinSettings = SETTINGS, **kwargs) -> dict:
    return assemble(load_job(job), settings, **kwargs).model


def test_the_nrcs_lag_by_hand() -> None:
    # 1000 m = 3280.84 ft, S = 2.5 in, Y = 5 %: 3280.84^0.8 * 3.5^0.7 / (1900 * 2.236) h
    assert nrcs_lag_minutes(1000.0, 80.0, 0.05) == pytest.approx(0.3676 * 60.0, rel=2e-3)


def test_the_index_celerity_by_hand() -> None:
    # 10 m wide, vertical sides, 1 m deep: A 10, P 12, V = (10/12)^(2/3) * 0.1 / 0.05
    assert index_celerity(0.05, 0.01, 10.0, 0.0, 1.0) == pytest.approx(5.0 / 3.0 * 1.7711, rel=1e-3)


def test_every_parameter_is_measured_with_its_source(valley: Valley) -> None:
    model = model_of(complete_job(valley.folder, valley.dem))
    subbasin = by_kind(model, "subbasin")[0]
    assert subbasin["missing"] == []
    assert subbasin["parameters"]["curve_number"] == {"value": 85.0, "source": SOURCE_RASTER}
    assert subbasin["parameters"]["lag_minutes"]["value"] > 0.0
    reach = by_kind(model, "reach")[0]
    assert reach["missing"] == []
    assert reach["parameters"]["manning_n"] == {"value": 0.05, "source": SOURCE_JOB}


def test_a_reach_reads_the_slope_of_the_valley_and_its_v_section(valley: Valley) -> None:
    model = model_of(complete_job(valley.folder, valley.dem))
    reach = by_kind(model, "reach")[0]
    assert value_of(reach, "slope") == pytest.approx(BED_SLOPE, rel=0.05)
    assert value_of(reach, "side_slope") == pytest.approx(1.0 / SIDE_SLOPE, rel=0.1)
    assert value_of(reach, "bottom_width_m") == pytest.approx(PIXEL, rel=0.5)
    assert value_of(reach, "length_m") == pytest.approx(150 * PIXEL, rel=0.05)


def test_a_flat_bed_reads_as_a_bottom_width(tmp_path: Path) -> None:
    width = 60.0
    dem = write_raster(tmp_path / "dem.tif", straight_valley(width))
    points = [
        DesignPoint(name="Top", x=col_x(NX // 2), y=row_y(100)),
        DesignPoint(name="Foot", x=col_x(NX // 2), y=row_y(250)),
    ]
    job = complete_job(tmp_path, dem, outputs={"points": [p.model_dump() for p in points]})
    settings = SETTINGS.model_copy(update={"stream_threshold_km2": None, "snap_m": 0.0})
    reach = by_kind(model_of(job, settings), "reach")[0]
    assert value_of(reach, "length_m") == pytest.approx(150 * PIXEL, rel=0.02)
    assert value_of(reach, "bottom_width_m") == pytest.approx(width, rel=0.25)
    assert value_of(reach, "side_slope") == pytest.approx(1.0 / SIDE_SLOPE, rel=0.15)


def test_the_longest_path_of_a_straight_valley(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", straight_valley())
    subbasin = by_kind(model_of(complete_job(tmp_path, dem)), "subbasin")[0]
    # the far corner runs along its row to the thalweg, the steeper way, then down the valley
    across, along = NX // 2 * PIXEL, (NY - 1) * PIXEL
    assert value_of(subbasin, "flow_length_m") == pytest.approx(across + along, rel=0.02)
    drop = across * SIDE_SLOPE + along * BED_SLOPE
    assert value_of(subbasin, "flow_path_slope") == pytest.approx(drop / (across + along), rel=0.02)
    # the top 10 % of the length is on the bank, the rest of the 10-85 stretch on the thalweg
    length = across + along
    bank_share = (across - 0.15 * length) / (0.75 * length)
    expected = bank_share * SIDE_SLOPE + (1.0 - bank_share) * BED_SLOPE
    assert value_of(subbasin, "slope_10_85") == pytest.approx(expected, rel=0.03)


def test_missing_names_exactly_what_is_absent(valley: Valley) -> None:
    model = model_of(valley.job)
    subbasin = by_kind(model, "subbasin")[0]
    assert subbasin["missing"] == ["curve_number", "lag_minutes"]
    assert subbasin["parameters"]["curve_number"] == {"value": None, "source": "missing"}
    assert by_kind(model, "reach")[0]["missing"] == ["manning_n", "index_celerity"]
    assert by_kind(model, "junction")[0]["missing"] == []


def test_the_schema_default_manning_is_not_a_value_of_the_job(valley: Valley) -> None:
    assert "manning" not in load_job(valley.job).terrain.model_fields_set


def test_a_single_cn_of_the_job_counts_and_says_so(tmp_path: Path, valley: Valley) -> None:
    job = write_job(tmp_path, valley.dem, hydrology={"curve_number": 70.0})
    subbasin = by_kind(model_of(job), "subbasin")[0]
    assert subbasin["parameters"]["curve_number"] == {"value": 70.0, "source": SOURCE_JOB}
    assert subbasin["missing"] == []


def test_a_raster_in_another_crs_is_warped_onto_the_analysis_pixels(tmp_path: Path, valley: Valley) -> None:
    west, north, size = 56.9, 22.65, 0.0005
    path = tmp_path / "cn_geographic.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=400, width=400, count=1, dtype="float32", nodata=-1.0,
        crs="EPSG:4326", transform=Affine(size, 0.0, west, 0.0, -size, north),
    ) as dst:  # fmt: skip
        dst.write(np.full((400, 400), 77.0, dtype=np.float32), 1)
    job = write_job(tmp_path, valley.dem, terrain={"cn_raster": str(path)})
    subbasin = by_kind(model_of(job, SETTINGS), "subbasin")[0]
    assert value_of(subbasin, "curve_number") == pytest.approx(77.0)


def test_a_raster_that_covers_too_little_leaves_cn_missing_and_says_so(
    tmp_path: Path, valley: Valley
) -> None:
    partial = np.full((NY, NX), 85.0)
    partial[:, : NX // 2 + 40] = -9999.0
    cn = write_raster(tmp_path / "cn.tif", partial)
    model = model_of(write_job(tmp_path, valley.dem, terrain={"cn_raster": str(cn)}))
    assert "curve_number" in by_kind(model, "subbasin")[0]["missing"]
    assert any("CN raster" in note for note in model["notes"])


def test_manning_comes_from_a_raster_before_the_job(tmp_path: Path, valley: Valley) -> None:
    n = write_raster(tmp_path / "n.tif", np.full((NY, NX), 0.07))
    job = complete_job(tmp_path, valley.dem, terrain={"manning_raster": str(n)})
    reach = by_kind(model_of(job), "reach")[0]
    assert reach["parameters"]["manning_n"]["source"] == SOURCE_RASTER
    assert value_of(reach, "manning_n") == pytest.approx(0.07)


def test_filling_a_value_by_hand_refreshes_what_follows_and_keeps_numbers(valley: Valley) -> None:
    model = model_of(valley.job)
    subbasin = by_kind(model, "subbasin")[0]
    subbasin["parameters"]["curve_number"]["value"] = 80.0
    refresh(model)
    assert subbasin["parameters"]["curve_number"]["source"] == SOURCE_USER
    lag = value_of(subbasin, "lag_minutes")
    assert lag > 0.0
    assert subbasin["missing"] == []
    subbasin["parameters"]["curve_number"]["value"] = 60.0
    refresh(model)
    assert value_of(subbasin, "lag_minutes") == lag


def test_the_loader_refuses_an_incomplete_model_and_names_it(valley: Valley) -> None:
    model = model_of(valley.job)
    with pytest.raises(ValueError, match="curve_number"):
        load_network(model)


def test_skip_incomplete_keeps_what_can_run_and_cuts_at_a_reach_that_cannot(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    model = model_of(complete_job(tmp_path, dem))
    reach = by_kind(model, "reach")[0]
    reach["parameters"]["manning_n"] = {"value": None, "source": "missing"}
    reach["parameters"]["index_celerity"] = {"value": None, "source": "missing"}
    above = next(e["name"] for e in model["elements"] if e["downstream"] == reach["name"])
    basin = load_network(model, skip_incomplete=True)
    assert reach["name"] not in basin.elements
    assert basin.elements[above].downstream is None


def test_the_lumped_engine_runs_unchanged_and_closes_the_volume(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    model = model_of(complete_job(tmp_path, dem))
    basin = load_network(model)
    assert {type(e) for e in basin.elements.values()} == {Subbasin, Reach, Junction}
    outlet = next(e for e in model["elements"] if e["downstream"] is None)
    assert basin.drainage_area(outlet["name"]) == pytest.approx(NY * NX * PIXEL**2 / 1e6, rel=1e-3)
    run = LumpedEngine(basin).run(STORM, GRID)
    volume = float(np.trapezoid(run.outflow[outlet["name"]])) * GRID.dt_seconds
    excess_mm = sum(run.water[name].excess.sum() * basin.elements[name].area_km2 for name in basin.subbasins)
    assert volume == pytest.approx(excess_mm * 1000.0, rel=0.01)


def test_the_loader_gives_every_reach_the_scheme_the_job_asks(tmp_path: Path) -> None:
    model = model_of(complete_job(tmp_path, write_raster(tmp_path / "dem.tif", valley_dem())))
    reaches = [e["name"] for e in by_kind(model, "reach")]
    assert reaches
    for scheme in (REACH_HMS, REACH_CONSERVING):
        basin = load_network(model, reach_routing=scheme)
        assert {basin.elements[name].routing.scheme for name in reaches} == {scheme}
    assert {load_network(model).elements[name].routing.scheme for name in reaches} == {REACH_HMS}


def test_the_file_loads_as_the_dict_does(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    job = complete_job(tmp_path, dem)
    assert main(["basin", str(job), "--out", str(tmp_path / "b"), "--threshold-km2", "0.5"]) == 0
    model = read_model(tmp_path / "b" / "basin.json")
    assert set(load_network(tmp_path / "b" / "basin.json").elements) == {e["name"] for e in model["elements"]}


def test_check_model_refuses_what_is_not_a_model(valley: Valley) -> None:
    model = model_of(valley.job)
    with pytest.raises(ValueError, match="format"):
        check_model({**model, "format": "x"})
    with pytest.raises(ValueError, match="version"):
        check_model({**model, "format_version": "9"})
    doubled = {**model, "elements": [*model["elements"], model["elements"][0]]}
    with pytest.raises(ValueError, match="twice"):
        check_model(doubled)
    lost = json.loads(json.dumps(model))
    lost["elements"][0]["downstream"] = "nowhere"
    with pytest.raises(ValueError, match="nowhere"):
        check_model(lost)


def test_routes_say_reach_none_and_the_next_junction(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    model = model_of(complete_job(tmp_path, dem))
    routes = junction_routes(model)
    fork = next(r for r in routes.values() if r.reach is not None)
    assert fork.route == ROUTE_REACH
    assert fork.next_junction in routes
    outlet = next(r for r in routes.values() if r.next_junction is None)
    assert outlet.route == ROUTE_NONE and outlet.reach is None


def test_an_incomplete_reach_routes_none_and_says_what_it_lacks(valley: Valley) -> None:
    routes = junction_routes(model_of(valley.job))
    fork = next(r for r in routes.values() if r.reach is not None)
    assert fork.route == ROUTE_NONE
    assert fork.reach_missing == ("manning_n", "index_celerity")
    assert fork.next_junction is not None


def test_a_short_link_joins_its_junctions_with_no_reach(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    settings = SETTINGS.model_copy(update={"min_reach_m": 5000.0})
    model = model_of(complete_job(tmp_path, dem), settings)
    assert by_kind(model, "reach") == []
    routes = junction_routes(model)
    assert any(r.route == ROUTE_NONE and r.next_junction is not None for r in routes.values())
    assert isinstance(load_network(model), type(load_network(model)))


def test_a_node_entering_the_next_from_the_side_keeps_its_downstream(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    job = complete_job(tmp_path, dem)
    plain = assemble(load_job(job), SETTINGS)
    surface = plain.surface
    fork = next(int(n) for n in plain.network.nodes if surface.down[n] != NONE)
    side = min(
        (int(p) for p in np.flatnonzero(surface.down == fork) if surface.count[p] > 100),
        key=surface.count.item,
    )
    x, y = surface.xy(side)
    point = DesignPoint(name="Beside", x=float(x), y=float(y))
    job = complete_job(tmp_path, dem, outputs={"points": [point.model_dump()]})
    settings = SETTINGS.model_copy(update={"snap_m": 0.0})
    model = model_of(job, settings, surface=surface)
    beside = next(e for e in model["elements"] if e["name"] == "Beside")
    assert (
        value_of(next(e for e in model["elements"] if e["name"] == beside["downstream"]), "drainage_area_km2")
        > 0.0
    )
    assert len([e for e in model["elements"] if e["downstream"] is None]) == 1


def dam_job(folder: Path, dem: Path, spillway: bool = True) -> Path:
    y = row_y(250)
    objects = [
        {
            "kind": "crest_line",
            "name": "Dam A",
            "coordinates": [(col_x(40), y), (col_x(160), y)],
            "z_constant": 126.0,
        }
    ]
    if spillway:
        objects.append(
            {
                "kind": "spillway",
                "coordinates": [(col_x(95), y), (col_x(105), y)],
                "z_constant": 120.0,
                "length": 50.0,
                "coefficient": 2.0,
            }
        )
    return complete_job(folder, dem, terrain={"objects": objects})


def test_a_dam_becomes_a_reservoir_with_the_pool_on_the_ground(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    model = model_of(dam_job(tmp_path, dem))
    dam = by_kind(model, "reservoir")[0]
    assert dam["name"] == "Dam A"
    assert dam["missing"] == []
    levels = np.array(value_of(dam, "elevation_m"))
    volumes = np.array(value_of(dam, "volume_m3"))
    areas = np.array(value_of(dam, "area_m2"))
    bed = levels[0]
    assert bed == pytest.approx(110.0, abs=0.2)  # (300 - 250) rows x 10 m x 2 %, above the 100 m floor
    height = 8.0
    index = int(np.argmin(np.abs(levels - (bed + height))))
    # the pool of a V valley on a slope: a triangle h / sv long, 2 h / ss wide at the dam, a pyramid of it
    h = levels[index] - bed
    assert areas[index] == pytest.approx(h**2 / (SIDE_SLOPE * BED_SLOPE), rel=0.05)
    assert volumes[index] == pytest.approx(h**3 / (3.0 * SIDE_SLOPE * BED_SLOPE), rel=0.05)
    assert value_of(dam, "initial_elevation_m") == 120.0
    assert value_of(dam, "spillways") == [
        {"crest_elevation_m": 120.0, "crest_length_m": 50.0, "coefficient": 2.0, "outlet": 0}
    ]


def test_the_reservoir_loads_and_routes_with_the_spillway_rating(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    model = model_of(dam_job(tmp_path, dem))
    basin = load_network(model)
    dam = basin.elements["Dam A"]
    assert isinstance(dam, Reservoir)
    assert isinstance(dam.routing, ReservoirOutflowStructures)
    pulse = HypotheticalStorm(depth_mm=100.0, pattern=STORM.pattern, duration_hours=1.0)
    run = LumpedEngine(basin).run(pulse, GRID)
    assert 0.0 < run.outflow["Dam A"].max() < 0.9 * run.inflow["Dam A"].max()


def test_a_dam_without_a_spillway_says_so_and_passes_as_a_junction(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    model = model_of(dam_job(tmp_path, dem, spillway=False))
    dam = by_kind(model, "reservoir")[0]
    assert dam["missing"] == ["spillways", "initial_elevation_m"]
    assert isinstance(load_network(model, skip_incomplete=True).elements["Dam A"], Junction)


def test_a_crest_under_the_ground_is_reported(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    y = row_y(250)
    crest = {
        "kind": "crest_line",
        "name": "Low",
        "coordinates": [(col_x(90), y), (col_x(110), y)],
        "z_constant": 50.0,
    }
    model = model_of(complete_job(tmp_path, dem, terrain={"objects": [crest]}))
    assert any("Low" in note for note in model["notes"])


def test_the_command_writes_both_files_and_the_three_layers(tmp_path: Path, capsys) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    out = tmp_path / "basin"
    assert main(["basin", str(complete_job(tmp_path, dem)), "--out", str(out), "--threshold-km2", "0.5"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["subbasins"] == 3
    model = json.loads((out / "basin.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(out / "basin.gpkg")
    tables = {row[0] for row in db.execute("select table_name from gpkg_contents")}
    assert tables == {"subbasins", "reaches", "junctions"}
    for layer, kinds in (("subbasins", ("subbasin",)), ("reaches", ("reach",)), ("junctions", ("junction",))):
        names = {row[0] for row in db.execute(f"select name from {layer}")}
        assert names == {e["name"] for e in model["elements"] if e["kind"] in kinds}
    db.close()


def test_the_command_reports_a_bad_job_with_the_invalid_code(tmp_path: Path, capsys) -> None:
    job = tmp_path / "job.json"
    job.write_text('{"terrain": {"dem": "none.tif"}, "grid": {"extent": [0, 0, 1, 1]}}', encoding="utf-8")
    assert main(["basin", str(job), "--out", str(tmp_path / "b")]) != 0


def test_threshold_zero_means_pour_points_only(tmp_path: Path, capsys) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    argv = ["basin", str(complete_job(tmp_path, dem)), "--out", str(tmp_path / "b"), "--threshold-km2", "0"]
    assert main(argv) == EXIT_INVALID
    assert "no stream" in capsys.readouterr().err


def test_names_stay_when_a_pour_point_is_added(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    job = complete_job(tmp_path, dem)
    out = tmp_path / "basin"
    assert main(["basin", str(job), "--out", str(out), "--threshold-km2", "0.5"]) == 0
    first = json.loads((out / "basin.json").read_text(encoding="utf-8"))
    points = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Site"},
                "geometry": {"type": "Point", "coordinates": [col_x(NX // 2), row_y(220)]},
            }
        ],
    }
    layer = tmp_path / "points.geojson"
    layer.write_text(json.dumps(points), encoding="utf-8")
    argv = ["basin", str(job), "--out", str(out), "--threshold-km2", "0.5", "--pour-points", str(layer)]
    assert main(argv) == 0
    second = json.loads((out / "basin.json").read_text(encoding="utf-8"))
    junctions = {e["name"]: e["outlet"] for e in second["elements"]}
    assert "Site" in junctions
    for element in first["elements"]:
        if element["kind"] == "junction":
            assert junctions[element["name"]] == element["outlet"]
    assert (out / "basin.previous.json").exists()


def test_a_namer_skips_a_name_in_use() -> None:
    namer = Namer(None, 10.0, ["S1", "J2"])
    assert namer.name("subbasin", 0.0, 0.0) == "S2"
    assert namer.name("junction", 0.0, 0.0) == "J1"
    assert namer.name("junction", 50.0, 0.0) == "J3"


def test_the_job_carries_the_basin_settings_and_a_checkpoint_ignores_them() -> None:
    from wadi2d.run import job_hash

    assert "BasinSettings" in json.dumps(RunConfig.model_json_schema())
    assert RunConfig().model_dump()["basin"]["lag_method"] == "nrcs"
    plain = RunConfig(terrain={"dem": __file__})
    moved = plain.model_copy(update={"basin": BasinSettings(lag_method="hms_kirpich")})
    assert job_hash(plain) == job_hash(moved)


def test_the_hms_lag_rule_reads_an_hms_lag_of_block_2() -> None:
    """S1 of the Block 2 model: longest path 26,164 m, 10-85 slope 0.01707, lag 112.0 min (`W24 basin model`)."""
    from wadi2d.basin.parameters import hms_kirpich_lag_minutes

    assert hms_kirpich_lag_minutes(26164.0, 0.01707) == pytest.approx(112.0, rel=0.01)


def test_the_lag_method_of_the_settings_decides_the_derived_lag(valley: Valley) -> None:
    nrcs = model_of(complete_job(valley.folder, valley.dem))
    settings = SETTINGS.model_copy(update={"lag_method": "hms_kirpich"})
    kirpich = model_of(complete_job(valley.folder, valley.dem), settings)
    first = by_kind(nrcs, "subbasin")[0]
    twin = by_kind(kirpich, "subbasin")[0]
    assert kirpich["settings"]["lag_method"] == "hms_kirpich"
    expected = hms_kirpich_lag_minutes(value_of(twin, "flow_length_m"), value_of(twin, "slope_10_85"))
    assert value_of(twin, "lag_minutes") == pytest.approx(expected, abs=0.01)
    assert value_of(first, "lag_minutes") != value_of(twin, "lag_minutes")
    assert [r["junction"] for r in nrcs["routes"]] == [e["name"] for e in nrcs["elements"] if e["kind"] in ("junction", "reservoir")]


def test_a_file_without_a_lag_method_is_the_nrcs_one(valley: Valley) -> None:
    model = model_of(complete_job(valley.folder, valley.dem))
    old = json.loads(json.dumps(model))
    del old["settings"]["lag_method"]
    for element in by_kind(old, "subbasin"):
        element["parameters"]["lag_minutes"] = {"value": None, "source": "derived"}
    refresh(old)
    assert value_of(by_kind(old, "subbasin")[0], "lag_minutes") == value_of(by_kind(model, "subbasin")[0], "lag_minutes")
