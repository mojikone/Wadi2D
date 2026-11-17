# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The holes of a CN grid where rain falls on the grid, counted before a run (W106, gap 1 of W104).

The engine refuses a run whose CN grid leaves rained cells without a CN and no CN is given for them
(``hydrology.curve_number``), but only once the grid and its tables are built: minutes on Block 2. The dock counts the
same holes first, on cells of the run's size over the domain, so the words come before the run with the count.

What is counted: every cell of the run's size whose centre lies in the domain and on no value of the CN grid (outside it
or on its no-data), less the cells under the generated subbasins the model runs lumped, whose rain is not on the grid.
Under an HMS project the lumped polygons are the project's own, which the dock does not read: there the count is said
as a note and the run goes on, the engine having the last word.

Interface: :func:`lumped_above`, :func:`holes_words`, :func:`count_holes` (GDAL, inside QGIS only).
"""

from __future__ import annotations

from pathlib import Path

RESERVOIR, SUBBASIN = "reservoir", "subbasin"
SUBBASINS_LAYER = "subbasins"
"""The layer of ``basin.gpkg`` that holds the subbasin polygons (``wadi2d/basin/layers.py``)."""


def lumped_above(model: dict, last_points: list[str] | None) -> set[str]:
    """The subbasins of a generated basin (``basin.json`` as data) at or above a last point: every dam when
    ``last_points`` is None (the engine's default, W105). A subbasin lacking a parameter is not lumped, so not here."""
    elements = {e["name"]: e for e in model.get("elements", [])}
    points = (
        [n for n, e in elements.items() if e.get("kind") == RESERVOIR] if last_points is None else list(last_points)
    )
    upstream: dict[str, list[str]] = {}
    for name, element in elements.items():
        below = element.get("downstream")
        if below is not None:
            upstream.setdefault(below, []).append(name)
    above: set[str] = set()
    todo = [p for p in points if p in elements]
    while todo:
        name = todo.pop()
        if name in above:
            continue
        above.add(name)
        todo.extend(upstream.get(name, []))
    return {
        n for n in above if elements[n].get("kind") == SUBBASIN and not elements[n].get("missing")
    }


HYBRIDS = ("hybrid_lumped", "hybrid_2d")
LAST_POINT_RULES = ("last_points", "outlets")
"""``hydrology.generated_entry`` of the two hybrids on a generated basin (W106): only what lies above a last point
is lumped."""


def lumped_of_job(job: dict) -> tuple[str | None, set[str], bool]:
    """The ``basin.gpkg`` and the subbasins whose rain a run of ``job`` keeps off the grid, and whether the count is
    sure (False under an HMS project, whose polygons the dock does not read)."""
    h = job.get("hydrology") or {}
    if h.get("hms_basin"):
        return None, set(), False
    path = h.get("basin_json")
    if not path or not Path(path).is_file():
        return None, set(), True
    import json

    model = json.loads(Path(path).read_text(encoding="utf-8"))
    asked = {s["name"]: s.get("mode", "lumped") for s in h.get("subbasins") or []}
    if (job.get("run") or {}).get("model_type") in HYBRIDS and h.get("generated_entry") in LAST_POINT_RULES:
        names = lumped_above(model, h.get("last_points"))
    else:
        names = {e["name"] for e in model.get("elements", []) if e.get("kind") == SUBBASIN and not e.get("missing")}
    names = {name for name in names if asked.get(name, "lumped") == "lumped"}
    return str(Path(path).with_name("basin.gpkg")), names, True


def check_job(job: dict) -> tuple[str, bool] | None:
    """The words before a run of ``job`` whose CN grid has holes where rain falls and no CN is given for them, and
    whether they stop the run; None when there is nothing to say. GDAL, so inside QGIS."""
    terrain, h, run = job.get("terrain") or {}, job.get("hydrology") or {}, job.get("run") or {}
    cn_raster, domain = terrain.get("cn_raster"), (job.get("grid") or {}).get("domain")
    if not cn_raster or h.get("curve_number") or run.get("lumped_only") or not domain:
        return None
    gpkg, lumped, sure = lumped_of_job(job)
    dx = float(job["grid"]["dx"])
    holes = count_holes(cn_raster, domain, dx, gpkg, lumped)
    if not holes:
        return None
    return holes_words(holes, dx, sure), sure


def holes_words(holes: int, dx: float, refuse: bool) -> str:
    """The dock's words on ``holes`` cells of ``dx`` m without a CN where rain falls on the grid."""
    area = holes * dx * dx / 1.0e6
    said = (
        f"The CN grid gives no value on {holes:,} cells of {dx:g} m where rain falls on the grid ({area:,.2f} km2): "
        "they would run off with no losses, and the engine refuses that. Give a CN where the grid has none "
        "(Hydrology, Curve number), or extend the grid."
    )
    return said if refuse else said.replace("the engine refuses that", "the engine refuses that if they are rained on")


def count_holes(
    cn_raster: str, domain_file: str, dx: float, basin_gpkg: str | None = None, lumped: set[str] | None = None
) -> int:
    """Cells of ``dx`` m with their centre in the domain (a vector file) and no CN, less those under the subbasins
    ``lumped`` of ``basin_gpkg`` (its ``subbasins`` layer). GDAL as QGIS ships it; the grid is read at the cells' size,
    nearest value."""
    import numpy as np
    from osgeo import gdal, ogr

    gdal.UseExceptions()
    source = ogr.Open(str(domain_file))
    layer = source.GetLayer(0)
    x0, x1, y0, y1 = layer.GetExtent()
    width, height = max(int(np.ceil((x1 - x0) / dx)), 1), max(int(np.ceil((y1 - y0) / dx)), 1)
    bounds = (x0, y1 - height * dx, x0 + width * dx, y1)
    raster = gdal.Open(str(cn_raster))  # held: a band outlives no dataset in GDAL's Python
    nodata = raster.GetRasterBand(1).GetNoDataValue()
    raster = None
    srs = layer.GetSpatialRef()
    warped = gdal.Warp(
        "", str(cn_raster), format="MEM", outputBounds=bounds, width=width, height=height, resampleAlg="near",
        srcNodata=nodata, dstNodata=-1.0e30, outputType=gdal.GDT_Float64,
        dstSRS=srs.ExportToWkt() if srs is not None else None,
    )  # fmt: skip
    values = warped.GetRasterBand(1).ReadAsArray()
    has = np.isfinite(values) & (values > -1.0e29)
    if nodata is not None and np.isfinite(nodata):
        has &= values != nodata
    inside = _burn(warped, source.GetLayer(0), width, height)
    if lumped and basin_gpkg and Path(basin_gpkg).is_file():
        basin = ogr.Open(str(basin_gpkg))
        polygons = basin.GetLayerByName(SUBBASINS_LAYER)
        if polygons is not None:
            quoted = ", ".join("'" + name.replace("'", "''") + "'" for name in sorted(lumped))
            polygons.SetAttributeFilter(f"name IN ({quoted})")
            inside &= ~_burn(warped, polygons, width, height)
    return int(np.count_nonzero(inside & ~has))


def _burn(like, layer, width: int, height: int):
    """Cells whose centre lies in the polygons of ``layer``, on the grid of ``like``."""
    import numpy as np
    from osgeo import gdal

    target = gdal.GetDriverByName("MEM").Create("", width, height, 1, gdal.GDT_Byte)
    target.SetGeoTransform(like.GetGeoTransform())
    target.SetProjection(like.GetProjection())
    gdal.RasterizeLayer(target, [1], layer, burn_values=[1])
    return np.asarray(target.GetRasterBand(1).ReadAsArray(), bool)
