"""The generated basin of Block 2 against the HMS model's own numbers, known without it.

Reads Block 2 only. Run from the repository root with the worktree first on PYTHONPATH:
    python "W24 basin model/scripts/make_jobs.py"
    python "W24 basin model/scripts/validate_block2.py"
Writes `W24 basin model/results/`: `validation.json`, the two generated models, and the outlets used. Nothing here tunes anything.

Two models. *As a user would*: a stream threshold and the five axes. *Aligned*: pour points at the outlets of the 18 HMS polygons
and no threshold, so each HMS subbasin and reach has a generated twin to compare. An outlet is the pixel of largest drainage area
inside a polygon, the dam lines left out.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from rasterio import features

from wadi2d.basin import load_network
from wadi2d.basin.build import assemble
from wadi2d.basin.contract import value_of
from wadi2d.basin.delineate import Surface, flow_surface, read_surface
from wadi2d.basin.layers import write_layers
from wadi2d.basin.pour import gather
from wadi2d.config.schema import BasinSettings
from wadi2d.hms import load_basin, load_met, load_nals, load_pdata, load_results
from wadi2d.hms.basin import Reach as HmsReach
from wadi2d.hms.basin import Subbasin as HmsSubbasin
from wadi2d.hms.sqlite import reach_lines, reach_statistics, subbasin_polygons, subbasin_statistics
from wadi2d.hydrology import LumpedEngine, analyse_point, point_storm
from wadi2d.hydrology.from_hms import basin_from_hms, grid_from_hms, load_project_tables, storm_from_hms
from wadi2d.run import load_job

HERE = Path(__file__).resolve().parents[1]
HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
SQLITE = HMS / "Basin_1.sqlite"
ANALYSIS = "DA 100yr B1"
MET = "FM_100yr.met"
RESULTS = "DAA_DA_100yr_B1.results"
DAMS = ("Faydh 01", "Bidah 03", "R5A", "R2A", "Z4C")
THRESHOLDS = (5.0, 10.0, 20.0, 40.0)
CHOSEN_THRESHOLD = 10.0
KIRPICH_COEFFICIENT, KIRPICH_LENGTH, KIRPICH_SLOPE = 0.0195, 0.77, -0.385
"""Tc in minutes, L in m, S in m/m."""
REACH_MATCH_M = 30.0
"""A generated reach counts for an HMS reach when most of it lies this close to the HMS line."""
REACH_SHARE = 0.5


class Hms:
    """The HMS model, its storm and its results."""

    def __init__(self) -> None:
        self.file = load_basin(HMS / "Basin_1.basin")
        self.basin = basin_from_hms(self.file)
        tables = load_project_tables(load_pdata(HMS / "HEC_HMS_Block_02.pdata"), HMS / "HEC_HMS_Block_02.dss")
        self.storm = storm_from_hms(load_met(HMS / MET).storm, tables)
        self.grid = grid_from_hms(load_nals(HMS / "HEC_HMS_Block_02.nals").analysis(ANALYSIS))
        self.results = load_results(HMS / "results" / RESULTS)
        self.polygons = {p.name: shapely.make_valid(p.shape()) for p in subbasin_polygons(SQLITE)}
        self.subbasins = {e.name: e for e in self.file.elements if isinstance(e, HmsSubbasin)}
        self.reaches = {e.name: e for e in self.file.elements if isinstance(e, HmsReach)}
        self.statistics = subbasin_statistics(SQLITE)
        self.reach_statistics = reach_statistics(SQLITE)
        lines = reach_lines(SQLITE, self.reaches)
        self.reach_lines = {row.name: row.shape() for row in lines}

    def peak(self, name: str) -> float:
        return float(self.results.element(name).outflow_max)

    def peak_time(self, name: str) -> float:
        reference = self.results.element(name)
        return (reference.outflow_max_time - self.results.start).total_seconds() / 3600.0


def kirpich(length_m: float, slope: float) -> float:
    return KIRPICH_COEFFICIENT * length_m**KIRPICH_LENGTH * slope**KIRPICH_SLOPE


def lag_share(hms: Hms) -> dict[str, float]:
    """HMS's lag over Kirpich on HMS's own longest length and 10-85 slope, one number per subbasin."""
    shares = {
        name: element.transform.lag
        / kirpich(hms.statistics[name].longest_length, hms.statistics[name].slope_10_85)
        for name, element in hms.subbasins.items()
    }
    return {
        "min": min(shares.values()),
        "max": max(shares.values()),
        "mean": float(np.mean(list(shares.values()))),
    }


def by_name(model: dict) -> dict[str, dict]:
    return {element["name"]: element for element in model["elements"]}


def dam_areas(model: dict, hms: Hms) -> dict[str, dict[str, float]]:
    """Drainage area at the dams, by the network, against HMS's."""
    basin = load_network(model, skip_incomplete=True)
    return {
        dam: {
            "hms": hms.basin.drainage_area(dam),
            "generated": round(basin.drainage_area(dam), 3),
            "raster": value_of(by_name(model)[dam], "drainage_area_km2"),
        }
        for dam in DAMS
    }


def peaks(model: dict, hms: Hms) -> dict[str, dict[str, float]]:
    """The 100-yr peak at each dam on its own storm area, the same storm and step as HMS."""
    engine = LumpedEngine(load_network(model, skip_incomplete=True))
    out: dict[str, dict[str, float]] = {}
    for dam in DAMS:
        result = analyse_point(engine, point_storm(hms.storm), hms.grid, dam)
        out[dam] = {
            "hms": round(hms.peak(dam), 1),
            "hms_time_h": round(hms.peak_time(dam), 2),
            "generated": round(result.peak, 1),
            "time_h": round(result.peak_minutes / 60.0, 2),
            "ratio": round(result.peak / hms.peak(dam), 3),
        }
    return out


def polygon_pixels(surface: Surface, polygon: shapely.Geometry) -> np.ndarray:
    grid = features.geometry_mask([polygon], surface.shape, surface.transform, invert=True)
    return np.flatnonzero(grid.ravel() & surface.valid)


def hms_outlets(hms: Hms, surface: Surface, settings: BasinSettings, path: Path) -> None:
    """The outlet of every HMS polygon, as a point layer."""
    lines = [surface.line_pixels(o.crest.coordinates) for o in dam_points(hms, surface, settings)]
    on_dam = np.zeros(surface.down.size, dtype=bool)
    on_dam[np.concatenate(lines)] = True
    features_out = []
    for name, polygon in hms.polygons.items():
        pixels = polygon_pixels(surface, polygon)
        pixels = pixels[~on_dam[pixels]]
        best = pixels[np.argmax(surface.count[pixels])]
        x, y = surface.xy(best)
        features_out.append(
            {
                "type": "Feature",
                "properties": {"name": f"at {name}"},
                "geometry": {"type": "Point", "coordinates": [float(x), float(y)]},
            }
        )
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features_out}), encoding="utf-8")


def dam_points(hms: Hms, surface: Surface, settings: BasinSettings) -> list:
    cfg = load_job(HERE / "jobs" / "block2.json")
    _collected, points = gather(cfg, surface, settings, None, [])
    return list(points.values())


def overlaps(hms: Hms, assembly) -> dict[str, tuple[str, float, float]]:
    """Each HMS subbasin's generated twin by largest shared area: name, shared share of HMS, intersection over union."""
    surface, label = assembly.surface, assembly.network.label
    by_link = {link: name for name, link in assembly.built.links.items()}
    twins: dict[str, tuple[str, float, float]] = {}
    for name, polygon in hms.polygons.items():
        pixels = polygon_pixels(surface, polygon)
        held = label[pixels]
        held = held[held >= 0]
        best = np.bincount(held).argmax()
        shared = np.count_nonzero(held == best)
        union = pixels.size + np.count_nonzero(label == best) - shared
        twins[name] = (by_link[int(best)], round(shared / pixels.size, 3), round(shared / union, 3))
    return twins


def reach_twins(hms: Hms, assembly) -> dict[str, list[str]]:
    """The generated reaches lying along each HMS reach."""
    found: dict[str, list[str]] = {}
    for name, line in hms.reach_lines.items():
        strip = line.buffer(REACH_MATCH_M)
        found[name] = [
            key
            for key, drawn in assembly.built.lines.items()
            if drawn.intersection(strip).length >= REACH_SHARE * drawn.length
        ]
    return found


def subbasin_table(hms: Hms, assembly, twins: dict) -> list[dict[str, Any]]:
    elements = by_name(assembly.model)
    rows = []
    for name, element in hms.subbasins.items():
        twin, share, iou = twins[name]
        made = elements[twin]
        stat = hms.statistics[name]
        rows.append(
            {
                "name": name,
                "twin": twin,
                "shared": share,
                "iou": iou,
                "area_hms": element.area,
                "area": value_of(made, "area_km2"),
                "cn_hms": element.loss.curve_number,
                "cn": value_of(made, "curve_number"),
                "lag_hms": element.transform.lag,
                "lag": value_of(made, "lag_minutes"),
                "length_hms": round(stat.longest_length),
                "length": round(value_of(made, "flow_length_m")),
                "path_slope_hms": round(stat.longest_slope, 4),
                "path_slope": value_of(made, "flow_path_slope"),
                "slope_10_85_hms": round(stat.slope_10_85, 5),
                "slope_10_85": value_of(made, "slope_10_85"),
                "land_slope_hms": round(stat.basin_slope, 3),
                "land_slope": round(value_of(made, "slope"), 3),
            }
        )
    return rows


def reach_table(hms: Hms, assembly, twins: dict[str, list[str]]) -> list[dict[str, Any]]:
    elements = by_name(assembly.model)
    rows = []
    for name, element in hms.reaches.items():
        made = [elements[key] for key in twins[name]]
        route = element.route
        length = sum(value_of(e, "length_m") for e in made)
        drop = sum(value_of(e, "length_m") * value_of(e, "slope") for e in made)
        rows.append(
            {
                "name": name,
                "twins": twins[name],
                "length_hms": route.length,
                "length": round(length, 1),
                "slope_hms": route.energy_slope,
                "slope": round(drop / length, 5) if length else None,
                "width_hms": route.bottom_width,
                "width": [value_of(e, "bottom_width_m") for e in made],
                "side_hms": route.side_slope,
                "side": [value_of(e, "side_slope") for e in made],
            }
        )
    return rows


def with_kirpich(model: dict, share: float) -> dict:
    """Diagnosis, not a product setting: every lag from the generated terrain by the rule HMS's lags turn out to follow."""
    out = copy.deepcopy(model)
    for element in out["elements"]:
        if element["kind"] == "subbasin":
            slope = value_of(element, "slope_10_85")
            if not slope:
                continue  # a sliver of a few pixels at a node keeps its generated lag
            lag = share * kirpich(value_of(element, "flow_length_m"), slope)
            element["parameters"]["lag_minutes"]["value"] = lag
    return out


def with_hms(
    model: dict, hms: Hms, twins: dict, reaches: dict[str, list[str]], lag=False, cn=False, reach=False
) -> dict:
    """A copy of the model with one family of parameters taken from HMS, on the mapped elements."""
    out = copy.deepcopy(model)
    elements = by_name(out)
    for name, (twin, _share, _iou) in twins.items():
        source = hms.subbasins[name]
        if lag:
            elements[twin]["parameters"]["lag_minutes"]["value"] = source.transform.lag
        if cn:
            elements[twin]["parameters"]["curve_number"]["value"] = source.loss.curve_number
    if reach:
        for name, keys in reaches.items():
            route = hms.reaches[name].route
            total = sum(value_of(elements[key], "length_m") for key in keys)
            for key in keys:
                parameters = elements[key]["parameters"]
                share = parameters["length_m"]["value"] / total
                parameters["length_m"]["value"] = route.length * share
                parameters["slope"]["value"] = route.energy_slope
                parameters["manning_n"]["value"] = route.mannings_n
                parameters["bottom_width_m"]["value"] = route.bottom_width
                parameters["side_slope"]["value"] = route.side_slope
                parameters["index_celerity"]["value"] = route.index_celerity
    return out


def user_model(cfg, surface: Surface, threshold: float, hms: Hms) -> dict[str, Any]:
    settings = BasinSettings(stream_threshold_km2=threshold)
    assembly = assemble(cfg, settings, surface=surface)
    model = assembly.model
    kinds = [e["kind"] for e in model["elements"]]
    summary = {
        "subbasins": kinds.count("subbasin"),
        "reaches": kinds.count("reach"),
        "nodes": kinds.count("junction") + kinds.count("reservoir"),
        "areas": dam_areas(model, hms),
        "peaks": peaks(model, hms),
        "unassigned_km2": model["analysis"]["unassigned_km2"],
    }
    return {"summary": summary, "assembly": assembly}


def write_model_files(assembly, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "basin.json").write_text(json.dumps(assembly.model, indent=1), encoding="utf-8")
    write_layers(folder / "basin.gpkg", assembly.surface, assembly.network.label, assembly.built)


def design_lines(surface: Surface, hms: Hms) -> dict[str, Any]:
    """The axes as plain design lines: one node per stream, the line's area their sum."""
    cfg = load_job(HERE / "jobs" / "block2_lines.json")
    model = assemble(cfg, BasinSettings(stream_threshold_km2=CHOSEN_THRESHOLD), surface=surface).model
    out: dict[str, Any] = {}
    for dam in DAMS:
        nodes = [e for e in model["elements"] if e.get("pour_point", {}).get("line") == dam]
        out[dam] = {
            "nodes": len(nodes),
            "sum_km2": round(sum(value_of(e, "drainage_area_km2") for e in nodes), 3),
            "line_km2": nodes[0]["pour_point"]["line_km2"],
            "hms": hms.basin.drainage_area(dam),
        }
    return out


def attribution(hms: Hms, model: dict, twins: dict, reaches: dict) -> dict[str, Any]:
    """The aligned model's peaks, then with each family of parameters taken from HMS."""
    cases = {
        "generated": {},
        "HMS lag": {"lag": True},
        "HMS CN": {"cn": True},
        "HMS reaches": {"reach": True},
        "HMS lag and reaches": {"lag": True, "reach": True},
        "HMS lag, CN, reaches": {"lag": True, "cn": True, "reach": True},
    }
    out = {case: peaks(with_hms(model, hms, twins, reaches, **flags), hms) for case, flags in cases.items()}
    out["Kirpich rule on generated terrain, diagnosis"] = peaks(
        with_kirpich(model, lag_share(hms)["mean"]), hms
    )
    return out


def main() -> None:
    results = HERE / "results"
    results.mkdir(exist_ok=True)
    hms = Hms()
    cfg = load_job(HERE / "jobs" / "block2.json")
    surface = flow_surface(*read_surface(cfg, BasinSettings()))
    out: dict[str, Any] = {
        "hms_subbasin_area_km2": sum(e.area for e in hms.subbasins.values()),
        "hms_lag_over_kirpich": lag_share(hms),
    }
    runs = {threshold: user_model(cfg, surface, threshold, hms) for threshold in THRESHOLDS}
    out["as_a_user_would"] = {str(threshold): run["summary"] for threshold, run in runs.items()}
    write_model_files(runs[CHOSEN_THRESHOLD]["assembly"], results / "block2_threshold_10km2")
    out["design_lines"] = design_lines(surface, hms)

    aligned = BasinSettings(stream_threshold_km2=None, snap_m=0.0)
    layer = results / "hms_outlets.geojson"
    hms_outlets(hms, gather(cfg, surface, aligned, None, [])[0], aligned, layer)
    assembly = assemble(cfg, aligned, layer, surface=surface)
    twins = overlaps(hms, assembly)
    reaches = reach_twins(hms, assembly)
    out["aligned"] = {
        "areas": dam_areas(assembly.model, hms),
        "subbasins": subbasin_table(hms, assembly, twins),
        "reaches": reach_table(hms, assembly, twins=reaches),
        "attribution": attribution(hms, assembly.model, twins, reaches),
        "elements": len(assembly.model["elements"]),
        "notes": assembly.model["notes"],
    }
    write_model_files(assembly, results / "block2_aligned_to_hms")
    (results / "validation.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1)[:2000], file=sys.stderr)


if __name__ == "__main__":
    main()
