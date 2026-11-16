"""The roughness and curve-number tables a job's ``terrain.roughness`` and ``hydrology.cn_override`` describe (W96).

Interface: :func:`roughness_grid`, :func:`roughness_identity`, :func:`override_cells`, :func:`with_curve_overrides`,
:func:`land_paths`, :func:`with_land_paths`.

A raster is read at the cell centres, nearest pixel, as every raster of a run is (:func:`raster_at_cells`); a land-use
raster's codes are looked up in the job's table, and a code found and not listed stops the run by name, never a
default. A lumped subbasin takes the mean CN of its polygon's pixels, HMS's composite curve number.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio.crs import CRS
from rasterio.mask import mask as clip_to
from rasterio.warp import transform_geom

from wadi2d.config.land import (
    CN_LAND_USE,
    CN_RANGE,
    CN_SUBBASIN,
    ROUGH_GRID,
    ROUGH_LAND_USE,
    ROUGH_SPLIT,
    ROUGH_UNIFORM,
    CurveOverride,
)
from wadi2d.config.schema import RunConfig
from wadi2d.grid.tiles import TileGrid
from wadi2d.hydrology.losses import ScsCurveNumber
from wadi2d.hydrology.model import Basin
from wadi2d.terrain.sampling import raster_at_cells

LAND_PATHS = (("terrain", "roughness", "raster"), ("terrain", "roughness", "land_use"), ("hydrology", "cn_override", "land_use"))
"""Every raster path these parts hold: (part, sub-part, name)."""


def by_class(codes: np.ndarray, table: dict[int, float], what: str, path: str) -> np.ndarray:
    """``codes`` looked up in ``table``; NaN stays NaN. A finite code the table lacks raises, naming every one."""
    out = np.full(codes.shape, np.nan)
    finite = np.isfinite(codes)
    if not finite.any():
        return out
    found = np.rint(codes[finite]).astype(np.int64)
    missing = sorted(set(np.unique(found).tolist()) - set(table))
    if missing:
        raise ValueError(
            f"{what}: the land-use raster {Path(path).name} holds the classes {missing}, which its table does not "
            "list: add a row for each"
        )
    keys = np.array(sorted(table), np.int64)
    values = np.array([table[k] for k in keys.tolist()], np.float64)
    out[finite] = values[np.searchsorted(keys, found)]
    return out


def roughness_grid(
    cfg: RunConfig,
    grid: TileGrid,
    crs: str = "",
    cells: tuple[np.ndarray, np.ndarray] | None = None,
    aligned: bool = False,
) -> float | np.ndarray:
    """Manning n of ``terrain.roughness``: one value, or a grid at ``cells`` (the mask by default) with the holes at
    ``roughness.n``, else ``terrain.manning``. ``aligned`` asks for the strips' cells, which only 'split' tells apart."""
    r = cfg.terrain.roughness
    if r.form == ROUGH_UNIFORM:
        return float(r.n)
    if r.form == ROUGH_SPLIT:
        return float(r.n_aligned if aligned else r.n)
    hole = cfg.terrain.manning if r.n is None else r.n
    if r.form == ROUGH_GRID:
        n = raster_at_cells(r.raster, grid, crs, cells)
    elif r.form == ROUGH_LAND_USE:
        n = by_class(raster_at_cells(r.land_use, grid, crs, cells), {c.code: c.n for c in r.classes}, "terrain.roughness", r.land_use)
    else:  # pragma: no cover - the schema allows no other form
        raise ValueError(f"terrain.roughness: unknown form {r.form!r}")
    return np.where(np.isfinite(n), n, hole)


def roughness_identity(cfg: RunConfig, identity) -> dict:
    """What the tables' cache must know of ``terrain.roughness``: its numbers, and its raster by ``identity``."""
    data = cfg.terrain.roughness.model_dump(mode="json")
    for name in ("raster", "land_use"):
        if data[name] is not None:
            data[name] = identity(data[name])
    return data


def land_paths(cfg: RunConfig) -> dict[str, str]:
    """Every raster path of these parts, by its dotted name in the job."""
    out = {}
    for part, sub, name in LAND_PATHS:
        holder = getattr(getattr(cfg, part), sub)
        value = None if holder is None else getattr(holder, name)
        if value is not None:
            out[f"{part}.{sub}.{name}"] = value
    return out


def with_land_paths(cfg: RunConfig, base: Path) -> RunConfig:
    """The same job with these parts' relative raster paths made absolute from ``base``."""
    for part, sub, name in LAND_PATHS:
        holder = getattr(getattr(cfg, part), sub)
        value = None if holder is None else getattr(holder, name)
        if value is None or Path(value).is_absolute():
            continue
        moved = holder.model_copy(update={name: str((base / value).resolve())})
        cfg = cfg.model_copy(update={part: getattr(cfg, part).model_copy(update={sub: moved})})
    return cfg


def reads_cells(cfg: RunConfig) -> bool:
    """True when the CN comes from a raster read at the cells: the CN grid, or a land-use override."""
    o = cfg.hydrology.cn_override
    return cfg.terrain.cn_raster is not None or (o is not None and o.by == CN_LAND_USE)


def _ranged(values: np.ndarray, o: CurveOverride) -> np.ndarray:
    """Every value in a range becomes the range's CN; NaN and values in no range stay."""
    out = np.array(values, np.float64, copy=True)
    for r in o.ranges:
        out[(values >= r.low) & (values <= r.high)] = r.curve_number
    return out


def _known_names(cfg: RunConfig, polygons: dict) -> set[str]:
    return {s.name for s in cfg.hydrology.subbasins} | set(polygons)


def override_cells(
    cfg: RunConfig,
    cn: np.ndarray,
    grid: TileGrid,
    polygons: dict[str, shapely.Geometry],
    crs: str = "",
    cells: tuple[np.ndarray, np.ndarray] | None = None,
) -> np.ndarray:
    """The CN grid of the rain-on-grid cells with ``hydrology.cn_override`` on it; ``cells`` as for the CN raster."""
    o = cfg.hydrology.cn_override
    if o is None:
        return cn
    if o.by == CN_RANGE:
        return _ranged(cn, o)
    if o.by == CN_LAND_USE:
        codes = raster_at_cells(o.land_use, grid, crs, cells)
        mapped = by_class(codes, {c.code: c.curve_number for c in o.classes}, "hydrology.cn_override", o.land_use)
        return np.where(np.isfinite(codes), mapped, cn)
    from wadi2d.forcing import _labels

    unknown = [s.name for s in o.subbasins if s.name not in _known_names(cfg, polygons)]
    if unknown:
        raise ValueError(f"hydrology.cn_override names {unknown}, which are no subbasin of the job and have no polygon")
    rows = [s for s in o.subbasins if s.name in polygons]
    labels = _labels(grid, [polygons[s.name] for s in rows])
    out = np.array(cn, np.float64, copy=True)
    for k, row in enumerate(rows):
        out[labels == k + 1] = row.curve_number
    return out


def polygon_mean(path: str, polygon: shapely.Geometry, crs: str, table: dict[int, float], what: str) -> float | None:
    """The mean of ``table`` over the land-use pixels whose centres lie in ``polygon``; None when none does."""
    with rasterio.open(path) as src:
        geom = polygon
        if src.crs is not None and crs and CRS.from_user_input(crs) != src.crs:
            geom = shapely.geometry.shape(transform_geom(CRS.from_user_input(crs), src.crs, shapely.geometry.mapping(polygon)))
        try:
            band, _transform = clip_to(src, [shapely.geometry.mapping(geom)], crop=True, filled=False)
        except ValueError:  # the polygon lies off the raster
            return None
    values = np.ma.filled(band[0].astype(np.float64), np.nan)
    mapped = by_class(values, table, what, path)
    mapped = mapped[np.isfinite(mapped)]
    return float(mapped.mean()) if mapped.size else None


def _with_cn(basin: Basin, name: str, value: float) -> None:
    element = basin.elements[name]
    if not isinstance(element.loss, ScsCurveNumber):
        raise ValueError(
            f"hydrology.cn_override: subbasin {name} loses its rain by {type(element.loss).__name__}, not by SCS curve "
            "number, so it has no CN to set"
        )
    basin.elements[name] = replace(element, loss=replace(element.loss, curve_number=float(value)))


def with_curve_overrides(basin: Basin, cfg: RunConfig, crs: str = "") -> dict[str, float]:
    """Set the CN of the lumped subbasins ``hydrology.cn_override`` reaches, in place; the CN taken, by name. A job
    part without the field (a stand-in some callers build) means no override."""
    o = getattr(cfg.hydrology, "cn_override", None)
    if o is None:
        return {}
    taken: dict[str, float] = {}
    subs = basin.subbasins
    if o.by == CN_SUBBASIN:
        rows = {s.name: s.curve_number for s in o.subbasins}
        stray = sorted(set(rows) - set(subs) - {s.name for s in cfg.hydrology.subbasins})
        if stray:
            from wadi2d.forcing import load_polygons

            stray = sorted(set(stray) - set(load_polygons(cfg.hydrology, crs)))
        if stray:
            raise ValueError(f"hydrology.cn_override names {stray}, which are no subbasin of the job and have no polygon")
        for name, value in rows.items():
            if name in subs:
                _with_cn(basin, name, value)
                taken[name] = value
        return taken
    if o.by == CN_RANGE:
        for name, element in subs.items():
            if isinstance(element.loss, ScsCurveNumber):
                value = float(_ranged(np.array([element.loss.curve_number]), o)[0])
                if value != element.loss.curve_number:
                    _with_cn(basin, name, value)
                    taken[name] = value
        return taken
    from wadi2d.forcing import load_polygons

    polygons = load_polygons(cfg.hydrology, crs)
    lacking = sorted(set(subs) - set(polygons))
    if lacking:
        raise ValueError(
            f"hydrology.cn_override by land use reads each lumped subbasin's polygon, and {lacking} have none: give "
            "hydrology.hms_sqlite or hydrology.polygons"
        )
    table = {c.code: c.curve_number for c in o.classes}
    for name in subs:
        value = polygon_mean(o.land_use, polygons[name], crs, table, "hydrology.cn_override")
        if value is not None:
            _with_cn(basin, name, value)
            taken[name] = value
    return taken
