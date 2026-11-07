"""The elements of ``basin.json``: what was measured for each subbasin, reach, junction and reservoir, and from what.

Names are short and stay: a pour point names its junction, the rest count S, R and J from the largest drainage area down, and a
rerun beside an earlier ``basin.json`` keeps every name whose outlet has not moved.

Interface: :class:`Namer`, :func:`build_elements`, :class:`Built`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely

from wadi2d.basin.contract import (
    JUNCTION,
    REACH,
    RESERVOIR,
    SOURCE_DERIVED,
    SOURCE_JOB,
    SOURCE_MISSING,
    SOURCE_RASTER,
    SOURCE_TERRAIN,
    SUBBASIN,
    Element,
    Model,
    parameter,
)
from wadi2d.basin.delineate import Surface
from wadi2d.basin.kernels import NONE, longest_paths, path_to
from wadi2d.basin.network import Network
from wadi2d.basin.parameters import land_slope, read_on_surface, zonal_mean
from wadi2d.basin.pour import KIND_DAM, PourPoint
from wadi2d.basin.reservoirs import crest_of, pool_table, spillways_of
from wadi2d.basin.sections import HIGH_GROUND, fit_section
from wadi2d.config.schema import BasinSettings, RunConfig

PREFIXES = {SUBBASIN: "S", REACH: "R", JUNCTION: "J"}
LAYERS = {SUBBASIN: "subbasins", REACH: "reaches", JUNCTION: "junctions", RESERVOIR: "junctions"}
AREA_DIGITS, LENGTH_DIGITS, SLOPE_DIGITS, TABLE_DIGITS = 4, 2, 6, 3
TEN_85_FROM_TOP = (0.15, 0.9)
"""The 10-85 points as shares of the longest path from its top, as HMS's statistics take them."""


class Namer:
    """Short names, stable across reruns."""

    def __init__(self, previous: Model | None, pixel: float, reserved: Iterable[str]) -> None:
        self.pixel = pixel
        self.taken = set(reserved)
        self.earlier: dict[tuple[str, int, int], str] = {}
        for element in (previous or {}).get("elements", []):
            self.earlier[self._key(element["kind"], *element["outlet"])] = element["name"]
            self.taken.add(element["name"])
        self.counters = dict.fromkeys(PREFIXES, 0)

    def _key(self, kind: str, x: float, y: float) -> tuple[str, int, int]:
        family = JUNCTION if kind == RESERVOIR else kind
        return family, round(x / self.pixel), round(y / self.pixel)

    def name(self, kind: str, x: float, y: float) -> str:
        """The element's earlier name, or the next free one."""
        kept = self.earlier.get(self._key(kind, x, y))
        if kept is not None:
            return kept
        while True:
            self.counters[kind] += 1
            name = f"{PREFIXES[kind]}{self.counters[kind]}"
            if name not in self.taken:
                self.taken.add(name)
                return name


@dataclass
class Built:
    """The elements and what the layers need beside them."""

    elements: list[Element] = field(default_factory=list)
    links: dict[str, int] = field(default_factory=dict)
    """Subbasin name to the link whose label it is."""
    lines: dict[str, shapely.LineString] = field(default_factory=dict)
    """Reach name to its line."""


def _element(kind: str, name: str, downstream: str | None, x: float, y: float, parameters: dict) -> Element:
    return {
        "kind": kind,
        "name": name,
        "downstream": downstream,
        "outlet": [round(float(x), LENGTH_DIGITS), round(float(y), LENGTH_DIGITS)],
        "geometry": {"layer": LAYERS[kind], "name": name},
        "parameters": parameters,
        "missing": [],
    }


def _number(value: float, digits: int) -> float | None:
    return round(float(value), digits) if np.isfinite(value) else None


def _curve_numbers(
    cfg: RunConfig, surface: Surface, net: Network, labels: int, settings: BasinSettings, notes: list[str]
) -> tuple[np.ndarray, str]:
    """Mean CN per label: from the raster, else the job's single value, else missing."""
    if cfg.terrain.cn_raster is not None:
        mean, share = zonal_mean(read_on_surface(cfg.terrain.cn_raster, surface), net.label, labels)
        poor = np.flatnonzero((share < settings.min_raster_share) & (share > 0.0))
        if poor.size:
            notes.append(
                f"{poor.size} subbasins have the CN raster over less of them than {settings.min_raster_share:g}"
            )
        return np.where(share >= settings.min_raster_share, mean, np.nan), SOURCE_RASTER
    if cfg.hydrology.curve_number is not None:
        return np.full(labels, cfg.hydrology.curve_number), SOURCE_JOB
    return np.full(labels, np.nan), SOURCE_MISSING


def _slope_10_85(surface: Surface, start: int, end: int) -> float:
    """Fall between 10 % and 85 % of the longest path, over that length."""
    pixels, along = path_to(surface.down, start, end, surface.nx, surface.pixel)
    length = float(along[-1])
    if length <= 0.0:
        return float("nan")
    high, low = np.interp(np.array(TEN_85_FROM_TOP) * length, along, surface.breached.ravel()[pixels])
    return float(high - low) / ((TEN_85_FROM_TOP[1] - TEN_85_FROM_TOP[0]) * length)


def _subbasin_parameters(
    cfg: RunConfig, surface: Surface, net: Network, settings: BasinSettings, notes: list[str]
) -> dict[int, dict[str, Any]]:
    """The measured parameters of every subbasin, by link."""
    labels = net.tops.size
    label, down = net.label, surface.down
    pixels = np.bincount(label[label != NONE], minlength=labels)
    longest, start = longest_paths(down, surface.order, label, labels, surface.nx, surface.pixel)
    slopes, _share = zonal_mean(land_slope(surface.z, surface.pixel), label, labels)
    curve, curve_source = _curve_numbers(cfg, surface, net, labels, settings, notes)
    breached = surface.breached.ravel()
    measured: dict[int, dict[str, Any]] = {}
    for link in net.subbasins.tolist():
        drop = breached[start[link]] - breached[net.end_node[link]]
        measured[link] = {
            "area_km2": parameter(_number(pixels[link] * surface.km2_per_pixel, AREA_DIGITS), SOURCE_TERRAIN),
            "flow_length_m": parameter(_number(longest[link], LENGTH_DIGITS), SOURCE_TERRAIN),
            "slope": parameter(_number(slopes[link], SLOPE_DIGITS), SOURCE_TERRAIN),
            "flow_path_slope": parameter(
                _number(drop / max(longest[link], surface.pixel), SLOPE_DIGITS), SOURCE_TERRAIN
            ),
            "slope_10_85": parameter(
                _number(_slope_10_85(surface, int(start[link]), int(net.end_node[link])), SLOPE_DIGITS),
                SOURCE_TERRAIN,
            ),
            "curve_number": parameter(_number(curve[link], 2), curve_source),
            "lag_minutes": parameter(None, SOURCE_DERIVED),
        }
    return measured


def _manning(
    cfg: RunConfig, raster: np.ndarray | None, pixels: np.ndarray, settings: BasinSettings
) -> dict[str, Any]:
    """Manning n along a reach: the raster, else a value the job sets. The schema's default is nobody's decision."""
    if raster is not None:
        along = raster[pixels]
        if np.count_nonzero(np.isfinite(along)) >= settings.min_raster_share * along.size:
            return parameter(round(float(np.nanmean(along)), 4), SOURCE_RASTER)
    if "manning" in cfg.terrain.model_fields_set:
        return parameter(cfg.terrain.manning, SOURCE_JOB)
    return parameter(None, SOURCE_MISSING)


def _reach_parameters(
    cfg: RunConfig,
    surface: Surface,
    pixels: np.ndarray,
    along: np.ndarray,
    raster: np.ndarray | None,
    ground: np.ndarray,
    settings: BasinSettings,
) -> tuple[dict[str, Any], bool]:
    """A reach measured along its D8 line, and whether its sections show open ground."""
    x, y = surface.xy(pixels)
    length = float(along[-1])
    breached = surface.breached.ravel()
    slope = max((breached[pixels[0]] - breached[pixels[-1]]) / length, settings.min_slope)
    fit = fit_section(ground, surface, x, y, along, settings)
    return {
        "length_m": parameter(round(length, LENGTH_DIGITS), SOURCE_TERRAIN),
        "slope": parameter(round(float(slope), SLOPE_DIGITS), SOURCE_TERRAIN),
        "manning_n": _manning(cfg, raster, pixels, settings),
        "bottom_width_m": parameter(round(fit.bottom_width_m, LENGTH_DIGITS), SOURCE_TERRAIN),
        "side_slope": parameter(round(fit.side_slope, 3), SOURCE_TERRAIN),
        "index_celerity": parameter(None, SOURCE_DERIVED),
        "section": parameter(
            {
                "depth_m": list(fit.depths_m),
                "width_m": list(fit.widths_m),
                "stations": fit.stations,
                "open_ground": fit.open_ground,
            },
            SOURCE_TERRAIN,
        ),
    }, fit.open_ground


def _reservoir_parameters(
    cfg: RunConfig, surface: Surface, pour: PourPoint, settings: BasinSettings, notes: list[str]
) -> dict[str, Any]:
    """The pool behind a dam and its rating. No spillway object leaves ``spillways`` missing."""
    crest = pour.crest
    level = crest_of(crest)
    line = surface.line_pixels(crest.coordinates)
    bed = float(surface.z.ravel()[line].min())
    if level <= bed:
        notes.append(
            f"dam {pour.name}: crest {level:g} m is at or under the ground {bed:.2f} m: another datum?"
        )
    table = pool_table(surface, line, max(level, bed) + settings.reservoir_top_m, settings.reservoir_step_m)
    ratings = spillways_of(crest, cfg, settings)
    low = min((rating["crest_elevation_m"] for rating in ratings), default=None)
    if low is not None and not table.elevation_m[0] <= low <= table.elevation_m[-1]:
        notes.append(f"dam {pour.name}: spillway {low:g} m is off its table: another datum?")
    return {
        "crest_elevation_m": parameter(level, SOURCE_JOB),
        "elevation_m": parameter([round(float(v), TABLE_DIGITS) for v in table.elevation_m], SOURCE_TERRAIN),
        "area_m2": parameter([round(float(v), 1) for v in table.area_m2], SOURCE_TERRAIN),
        "volume_m3": parameter([round(float(v), 1) for v in table.volume_m3], SOURCE_TERRAIN),
        "spillways": parameter(ratings or None, SOURCE_JOB),
        "initial_elevation_m": parameter(round(float(table.elevation_m[0]), TABLE_DIGITS), SOURCE_DERIVED),
    }


def _node_names(surface: Surface, net: Network, namer: Namer) -> dict[int, str]:
    names: dict[int, str] = {}
    for node in net.nodes.tolist():
        point = net.pour.get(node)
        names[node] = point.name if point else namer.name(JUNCTION, *surface.xy(node))
    return names


def build_elements(
    cfg: RunConfig, surface: Surface, net: Network, settings: BasinSettings, namer: Namer, notes: list[str]
) -> Built:
    """Every element of the model, subbasins first; lags and celerities follow in ``refresh``."""
    built = Built()
    names = _node_names(surface, net, namer)
    below: dict[int, str | None] = {node: None for node in names}
    measured = _subbasin_parameters(cfg, surface, net, settings, notes)
    for link in net.subbasins.tolist():
        x, y = surface.xy(net.bottoms[link])
        name = namer.name(SUBBASIN, x, y)
        built.links[name] = link
        built.elements.append(_element(SUBBASIN, name, names[int(net.end_node[link])], x, y, measured[link]))
    raster = (
        None if cfg.terrain.manning_raster is None else read_on_surface(cfg.terrain.manning_raster, surface)
    )
    ground = np.where(np.isfinite(surface.z), surface.z, HIGH_GROUND)
    open_reaches: list[str] = []
    for link in np.flatnonzero(net.start_node != NONE)[
        np.argsort(net.bottoms[net.start_node != NONE])
    ].tolist():
        start, end = int(net.start_node[link]), int(net.end_node[link])
        pixels, along = path_to(surface.down, start, end, surface.nx, surface.pixel)
        if along[-1] < settings.min_reach_m:
            below[start] = names[end]
            continue
        x, y = surface.xy(net.bottoms[link])
        name = namer.name(REACH, x, y)
        parameters, is_open = _reach_parameters(cfg, surface, pixels, along, raster, ground, settings)
        built.elements.append(_element(REACH, name, names[end], x, y, parameters))
        built.lines[name] = shapely.LineString(np.column_stack(surface.xy(pixels)))
        below[start] = name
        if is_open:
            open_reaches.append(name)
    if open_reaches:
        notes.append(f"open ground, no channel in the sections: {sorted(open_reaches)}")
    for node in net.nodes.tolist():
        x, y = surface.xy(node)
        if below[node] is None and surface.down[node] != NONE:
            below[node] = names[
                int(surface.down[node])
            ]  # a node entering the next one from the side has no link
        area = parameter(_number(surface.count[node] * surface.km2_per_pixel, AREA_DIGITS), SOURCE_TERRAIN)
        point = net.pour.get(node)
        parameters = {"drainage_area_km2": area}
        kind = JUNCTION
        if point is not None and point.kind == KIND_DAM:
            kind = RESERVOIR
            parameters |= _reservoir_parameters(cfg, surface, point, settings, notes)
        element = _element(kind, names[node], below[node], x, y, parameters)
        if point is not None:
            element["pour_point"] = {
                "kind": point.kind,
                "x": point.x,
                "y": point.y,
                "line": point.line,
                "line_km2": None if point.line_km2 is None else round(point.line_km2, AREA_DIGITS),
                "aliases": point.aliases,
            }
        built.elements.append(element)
    return built
