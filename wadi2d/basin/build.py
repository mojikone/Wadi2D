"""From a job to a basin model: the whole of ``wadi2d basin``.

Interface: :class:`Assembly`, :func:`assemble`, :func:`build_basin`, :data:`BASIN_FILE`, :data:`GEOMETRY_FILE`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from wadi2d.basin.barriers import ground_edits
from wadi2d.basin.contract import (
    FORMAT,
    FORMAT_VERSION,
    JUNCTION,
    REACH,
    RESERVOIR,
    SUBBASIN,
    Model,
    check_model,
    refresh,
    write_model,
)
from wadi2d.basin.delineate import Surface, flow_surface, read_surface
from wadi2d.basin.elements import Built, Namer, build_elements
from wadi2d.basin.kernels import NONE
from wadi2d.basin.layers import write_layers
from wadi2d.basin.network import Network, build_network
from wadi2d.basin.points import POINT_OUTFALL, PointEdit, keep_outfalls
from wadi2d.basin.pour import gather
from wadi2d.basin.routes import junction_routes
from wadi2d.config.schema import BasinSettings, RunConfig

BASIN_FILE = "basin.json"
GEOMETRY_FILE = "basin.gpkg"


@dataclass
class Assembly:
    """A model and what it was measured on."""

    model: Model
    surface: Surface
    network: Network
    built: Built


def _inputs(cfg: RunConfig, pour_layer: str | Path | None) -> dict[str, str | list | None]:
    return {
        "dem": cfg.terrain.dem,
        "domain": cfg.grid.domain,
        "extent": list(cfg.grid.extent) if cfg.grid.extent is not None else None,
        "cn_raster": cfg.terrain.cn_raster,
        "manning_raster": cfg.terrain.manning_raster,
        "pour_points": None if pour_layer is None else str(pour_layer),
    }


def _analysis(surface: Surface, label: np.ndarray) -> dict[str, float | int]:
    ny, nx = surface.shape
    ground = int(surface.valid.sum())
    outside = ground - int(np.count_nonzero(label != NONE))
    return {
        "pixel_m": surface.pixel,
        "x0": surface.x0,
        "y0": surface.y0,
        "ny": ny,
        "nx": nx,
        "ground_km2": round(ground * surface.km2_per_pixel, 4),
        "unassigned_km2": round(outside * surface.km2_per_pixel, 4),
    }


def assemble(
    cfg: RunConfig,
    settings: BasinSettings,
    pour_layer: str | Path | None = None,
    previous: Model | None = None,
    surface: Surface | None = None,
) -> Assembly:
    """Measure the model; ``surface`` reuses a delineation of the same ground."""
    notes: list[str] = []
    if surface is None:
        z, pixel, x0, y0, crs = read_surface(cfg, settings)
        surface = flow_surface(z, pixel, x0, y0, crs, ground_edits(cfg, z, pixel, x0, y0, settings, notes))
    edits: list[PointEdit] = []
    surface, pour = gather(cfg, surface, settings, pour_layer, notes, edits)
    network = build_network(surface, pour, settings, edits)
    reserved = [point.name for point in pour.values()] + [src["name"] for p in pour.values() for src in p.sources]
    namer = Namer(previous, surface.pixel, reserved)
    built = build_elements(cfg, surface, network, settings, namer, notes)
    _outfalls(built, network, [point.name for point in pour.values() if point.role == POINT_OUTFALL], notes)
    model: Model = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "name": cfg.project.name,
        "crs": surface.crs,
        "geometry_file": GEOMETRY_FILE,
        "inputs": _inputs(cfg, pour_layer),
        "settings": settings.model_dump(),
        "analysis": _analysis(surface, network.label),
        "elements": built.elements,
        "notes": notes,
    }
    refresh(check_model(model))
    model["routes"] = [asdict(route) for route in junction_routes(model).values()]
    return Assembly(model, surface, network, built)


def _outfalls(built: Built, network: Network, outfalls: list[str], notes: list[str]) -> None:
    """Keep what drains to the layer's outfalls, in place; the pixels of what leaves no longer count as assigned."""
    if not outfalls:
        return
    built.elements = keep_outfalls(built.elements, outfalls, notes)
    names = {e["name"] for e in built.elements}
    links = [link for name, link in built.links.items() if name in names]
    built.links = {name: link for name, link in built.links.items() if name in names}
    built.lines = {name: line for name, line in built.lines.items() if name in names}
    network.label = np.where(np.isin(network.label, links), network.label, NONE)


def _counts(model: Model) -> dict[str, int]:
    kinds = [element["kind"] for element in model["elements"]]
    return {
        "subbasins": kinds.count(SUBBASIN),
        "reaches": kinds.count(REACH),
        "junctions": kinds.count(JUNCTION),
        "reservoirs": kinds.count(RESERVOIR),
        "incomplete": sum(bool(element["missing"]) for element in model["elements"]),
    }


def build_basin(
    cfg: RunConfig, settings: BasinSettings, pour_layer: str | Path | None, out: str | Path
) -> dict:
    """Write ``basin.json`` and ``basin.gpkg`` into ``out``; names carry over from a ``basin.json`` already there."""
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / BASIN_FILE
    previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    result = assemble(cfg, settings, pour_layer, previous)
    write_layers(folder / GEOMETRY_FILE, result.surface, result.network.label, result.built)
    write_model(result.model, target)
    return {"basin": str(target), "geometry": str(folder / GEOMETRY_FILE), **_counts(result.model)}
