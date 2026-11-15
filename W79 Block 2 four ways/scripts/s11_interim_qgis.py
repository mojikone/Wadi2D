"""Block2_four_ways_interim_cells.qgz: what the reruns hold so far, before their pixel rasters, in the plugin's group pattern.

Run with ``"C:\\Program Files\\QGIS 3.44.8\\bin\\python-qgis-ltr.bat" s11_interim_qgis.py``: its own QgsApplication
without a GUI, CPU only, writing only W79's interim project. A common group (terrain hillshade from the 5 m DEM, the
domain, the outflow lines, the dams, the HMS subbasins, the aligned cells, run 2's dam table and dam_peaks.csv), then for
each 2D rerun that has finished its solver a ``Wadi2D – <run>`` group: Model setup (cell grid, aligned cells, edge
checks), "Cell maps, interim" (max depth, max speed, hazard on the cells), the dam result lines' series as tables, and
the pixel rasters and the time slider where they already exist. Rerun it as products land.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parent
sys.path.insert(0, str(REPO / "plugin"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis.core import (  # noqa: E402
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsHillshadeRenderer,
    QgsLayerTreeGroup,
    QgsLineSymbol,
    QgsProject,
    QgsRasterLayer,
    QgsReferencedRectangle,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)

app = QgsApplication([], False)
app.initQgis()

from w79 import DAMS, DEM5, INPUTS, JOBS, RUN_NAMES, RUN_TITLES, RUNS, safe_csv_uri  # noqa: E402
from wadi2d_qgis import layer_groups as lg  # noqa: E402
from wadi2d_qgis import result_layers as rl  # noqa: E402
from wadi2d_qgis import style  # noqa: E402
from wadi2d_qgis import time_layer as tl  # noqa: E402

CRS = QgsCoordinateReferenceSystem("EPSG:32640")
OUT = Path(os.environ.get("W79_QGZ", HERE / "Block2_four_ways_interim_cells.qgz"))
INTERIM = "interim, cell maps"
project = QgsProject.instance()
project.setCrs(CRS)
project.setTitle(f"Block 2 four ways (W79), {INTERIM}")
root = project.layerTreeRoot()
notes: list[str] = []


def vec(uri: str, title: str, subset: str = ""):
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True
    layer = QgsVectorLayer(uri, title, "ogr", options)
    assert layer.isValid(), uri
    if subset:
        layer.setSubsetString(subset)
    return layer


def table(path: Path, title: str, subset: str = ""):
    layer = QgsVectorLayer(safe_csv_uri(path), title, "delimitedtext")
    assert layer.isValid(), path
    if subset:
        layer.setSubsetString(subset)
    return layer


def line_style(layer, colour: str, width: float, dash: bool = False) -> None:
    props = {"color": colour, "width": str(width)}
    if dash:
        props["line_style"] = "dash"
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple(props)))


def add_all(group, layers, shown=True) -> None:
    for layer in layers:
        lg.add_layer(group, layer, shown=shown).setExpanded(False)


def outflow_lines() -> Path:
    """The rerun jobs' boundaries (the sea, the side and north outlets) as a file QGIS reads."""
    job = json.loads((JOBS / f"{RUN_NAMES[1]}.json").read_text(encoding="utf-8"))
    features = [{"type": "Feature", "properties": {"kind": b["kind"], "slope": b.get("slope"), "number": i + 1},
                 "geometry": {"type": "LineString", "coordinates": b["coordinates"]}}
                for i, b in enumerate(job["boundaries"])]
    path = RUNS / "inputs" / "outflow_lines.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "crs": {"type": "name", "properties": {
        "name": "urn:ogc:def:crs:EPSG::32640"}}, "features": features}), encoding="utf-8")
    return path


def dam_layers() -> list:
    gj = str(INPUTS / "dams.geojson")
    crest = vec(gj, "Dam crest lines (2D pools in runs 1 and 4)", "\"kind\" = 'crest_line'")
    line_style(crest, "#8b0000", 1.2)
    style._labels(crest, "dam", 8.0, "#8b0000", Qgis.LabelPlacement.Line, bold=True)
    spill = vec(gj, "Spillways (2D), Q = C L H^1.5", "\"kind\" = 'spillway'")
    line_style(spill, "#ff8c00", 2.4)
    lines = vec(gj, "Dam result lines (W1)", "\"kind\" = 'dam_line'")
    line_style(lines, "#000000", 1.0)
    ring = vec(gj, "Pool inflow lines", "\"kind\" = 'inflow_ring'")
    line_style(ring, "#7b2fbf", 0.8, dash=True)
    entry = vec(gj, "Run 3: reservoir outflow enters the grid here", "\"kind\" = 'outflow_entry_run3'")
    return [lines, crest, spill, ring, entry]


def common() -> None:
    top = root.insertGroup(0, f"Block 2 \N{EN DASH} common inputs ({INTERIM})")
    hill = QgsRasterLayer(str(DEM5), "Terrain, GGC HDSM 5 m, hillshade")
    hill.setRenderer(QgsHillshadeRenderer(hill.dataProvider(), 1, 315.0, 45.0))
    dom = vec(str(INPUTS / "domain.geojson"), "2D domain to the sea (Basin 3 polygons + coast strip)")
    style.style_domain(dom)
    out = vec(str(outflow_lines()), "Outflow lines: the sea, the side and north outlets (normal depth)")
    style.style_boundaries(out)
    net = RUNS / RUN_NAMES[2] / "network.gpkg"
    subs = vec(f"{net}|layername=subbasins", "HMS Basin 3 subbasins")
    subs.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"color": "0,0,0,0", "outline_color": "#1f4e8c", "outline_width": "0.35"})))
    style._labels(subs, "name", 7.0, "#1f3a66", Qgis.LabelPlacement.OverPoint, bold=True)
    peaks = table(HERE / "dam_peaks.csv", "Dam peaks so far, with the ARF of each (dam_peaks.csv)")
    run2 = table(RUNS / RUN_NAMES[2] / "network_peaks.csv",
                 "Run 2, full HMS way: every element at its own area (dams: Reservoir rows)", "\"kind\" = 'Reservoir'")
    add_all(top, [peaks, run2, *dam_layers(), out, subs, dom])
    cells = rl.open_strip_mesh(RUNS / RUN_NAMES[1])
    for layer in cells:
        layer.setName(f"Aligned cells, 20 m centre mesh (run 1): {layer.name()}")
    add_all(top, cells, shown=False)
    project.addMapLayer(hill, False)
    top.addLayer(hill)


def grid_run(number: int) -> bool:
    folder = RUNS / RUN_NAMES[number]
    if not (folder / "maps" / "max_depth.tif").is_file():
        notes.append(f"run {number}: no cell maps yet")
        return False
    model = lg.model_of_run(folder)
    group = lg.model_group(model)
    pixels = rl.has_products(folder)
    group.setName(f"{lg.model_title(model)}  ({RUN_TITLES[number]}; {'pixel rasters' if pixels else INTERIM})")
    if pixels:
        rl.load_products(folder)
    rl.load_cell_grid(folder)
    for layer in rl.load_strip_mesh(folder):  # 0.5 M outlines and 1.3 M faces: off until zoomed in
        root.findLayer(layer.id()).setItemVisibilityChecked(False)
    results = lg.run_results(folder)
    setup = lg.subgroup(results, lg.SETUP)
    edges = folder / "edge_checks.gpkg"
    if edges.is_file():
        add_all(setup, [vec(f"{edges}|layername=edge_streams", "Edge check: streams across the domain edge"),
                        vec(f"{edges}|layername=edge_pools", "Edge check: water against the domain edge")], shown=False)
    slider(folder, number)
    cells = lg.subgroup(results, f"{lg.CELLS} (interim: the pixel rasters are not made yet)" if not pixels else lg.CELLS)
    strip = folder / "maps" / "strip_maxima.gpkg"
    if strip.is_file():  # above the square cells' rasters, which are blank where the aligned cells are
        aligned = []
        for field, title, ranges in (
            ("max_depth_m", "Aligned cells: maximum depth, m", DEPTH_RANGES),
            ("max_speed_ms", "Aligned cells: maximum speed, m/s", SPEED_RANGES),
            ("max_dv", "Aligned cells: hazard, depth x speed, m2/s", HAZARD_RANGES),
        ):
            layer = vec(f"{strip}|layername=strip_maxima", title)
            graduated(layer, field, ranges)
            aligned.append((layer, field == "max_depth_m" and not pixels))
        for layer, shown in aligned:
            add_all(cells, [layer], shown=shown)
    else:
        notes.append(f"run {number}: no aligned-cell maxima yet")
    for name, title, styler in (("max_depth.tif", "Maximum depth, cells, m", style.style_depth),
                                ("max_speed.tif", "Maximum speed, cells, m/s", None),
                                ("hazard.tif", "Hazard, cells", style.style_hazard)):
        layer = QgsRasterLayer(str(folder / "maps" / name), title)
        if layer.isValid():
            if styler is not None:
                styler(layer)
            add_all(cells, [layer], shown=name == "max_depth.tif" and not pixels)
    series = lg.subgroup(results, "Dam result lines: series of record (every 60 s)")
    tables = []
    for dam in DAMS:
        for suffix, what in (("", "dam line (outflow)"), ("_inflow", "line round the pool (inflow)")):
            path = folder / "series" / f"line_{dam.replace(' ', '_')}{suffix}.csv"
            if path.is_file():
                tables.append(table(path, f"{dam}: {what}"))
    add_all(series, tables)
    if (folder / "w79_check.json").is_file():
        add_all(results, [table(HERE / "dam_peaks.csv", "Dam peaks of this run", f"\"run\" = {number}")])
    return True


def lumped_run() -> None:
    """Run 2 the plugin's way without the plugin: its network labelled with peak, time to peak and ARF, the peaks table,
    the reservoirs' series; the dock's chart is drawn to run2_charts/ and the dam workbook is run2_dam_workbook.xlsx."""
    folder = RUNS / RUN_NAMES[2]
    model = lg.model_of_run(folder)
    group = lg.model_group(model)
    group.setName(f"{lg.model_title(model)}  ({RUN_TITLES[2]}; each element at its own ARF area)")
    results = lg.run_results(folder)
    net = folder / "network.gpkg"
    subs = vec(f"{net}|layername=subbasins", "Subbasins: peak outflow, time to peak, ARF")
    style.style_subbasins(subs)
    style._labels(subs, "label", 6.5, "#1f3a66", Qgis.LabelPlacement.OverPoint)
    junctions = vec(f"{net}|layername=junctions", "Junctions and reservoirs: peak outflow, time to peak, ARF")
    style.style_basin_junctions(junctions)
    style._labels(junctions, "label", 7.0, "#000000", Qgis.LabelPlacement.OrderedPositionsAroundPoint, bold=True)
    reaches = vec(f"{net}|layername=reaches", "Reaches, Muskingum-Cunge: peak outflow")
    style.style_basin_reaches(reaches)
    add_all(lg.subgroup(results, lg.SETUP), [junctions, reaches, subs])
    series = lg.subgroup(results, "Series of record, every 5 min (charts: run2_charts/, workbook: run2_dam_workbook.xlsx)")
    tables = [table(folder / "network_peaks.csv", "Every element: ARF area and factor, peaks, times, volumes")]
    for dam in DAMS:
        tables.append(table(folder / "series" / f"network_{dam.replace(' ', '_')}_Reservoir.csv",
                            f"{dam} Reservoir: inflow, outflow, pool, storage, rain"))
    add_all(series, tables)
    add_all(results, [table(HERE / "dam_peaks.csv", "Dam peaks of this run", "\"run\" = 2")])


DEPTH_RANGES = ((0.05, 0.5, "#a5d2fa"), (0.5, 2.0, "#468ce1"), (2.0, 5.0, "#144baf"), (5.0, 1e9, "#081e64"))
"""The cell maps' depth stops (``style.DEPTH_STOPS``) as classes; under 0.05 m is not drawn, as the raster fades it out."""
SPEED_RANGES = ((0.0, 1.0, "#2c7bb6"), (1.0, 2.0, "#abd9e9"), (2.0, 3.5, "#ffffbf"), (3.5, 5.0, "#fdae61"),
                (5.0, 1e12, "#d7191c"))
HAZARD_RANGES = ((0.0, 0.3, "#ffffbe"), (0.3, 0.6, "#ffdc6e"), (0.6, 1.0, "#faaa3c"), (1.0, 4.0, "#e15a28"),
                 (4.0, 1e12, "#96141e"))
"""``style.HAZARD_CLASSES``: depth x speed, the bands of the cell maps' hazard raster."""


def graduated(layer, field: str, ranges) -> None:
    from qgis.core import QgsGraduatedSymbolRenderer, QgsRendererRange

    items = []
    for low, high, colour in ranges:
        symbol = QgsFillSymbol.createSimple({"color": colour, "outline_style": "no"})
        label = f"{low:g} to {high:g}" if high < 1e8 else f"over {low:g}"
        items.append(QgsRendererRange(low, high, symbol, label))
    layer.setRenderer(QgsGraduatedSymbolRenderer(field, items))


def slider(folder: Path, number: int) -> None:
    """The light time slider (hourly, flooded cells, aligned cells included) shown unchecked on top; the full one,
    every 15 min on every square cell, unchecked in a subgroup of its own: turning it on loads 2.9 M cells."""
    from qgis.core import QgsMeshLayer

    top = lg.run_results(folder)
    group = lg.subgroup(top, tl.TIME, 0)
    light = folder / "frames_light.nc"
    if light.is_file():
        layer = QgsMeshLayer(str(light), "Flood over time, light: hourly, flooded cells, aligned cells included", "mdal")
        if layer.isValid():
            layer.setCrs(CRS)
            style.style_frames(layer)
            lg.add_layer(group, layer, shown=False, index=0)
    full = tl.open_frames(folder)
    if full is not None:
        full.setName("Flood over time, full: every 15 min, every square cell (heavy, no aligned cells)")
        heavy = lg.subgroup(group, "Full file (heavy: 2.9 M cells; turn on with care)")
        lg.add_layer(heavy, full, shown=False)
        heavy.setItemVisibilityChecked(False)
        heavy.setExpanded(False)
    else:
        notes.append(f"run {number}: no time-slider file yet")


def main() -> None:
    common()
    lumped_run()
    lg.find_model(lg.model_of_run(RUNS / RUN_NAMES[2])).setItemVisibilityChecked(False)
    made = [n for n in (4, 3, 1) if grid_run(n)]  # each model group goes on top: run 1 ends first
    for number in made:
        if number != min(made):
            node = lg.find_model(lg.model_of_run(RUNS / RUN_NAMES[number]))
            if node is not None:
                node.setItemVisibilityChecked(False)
    for child in root.children():
        if isinstance(child, QgsLayerTreeGroup):
            child.setExpanded(False)
    dom = vec(str(INPUTS / "domain.geojson"), "extent")
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(dom.extent(), CRS))
    project.writeEntryBool("Paths", "/Absolute", False)
    if not project.write(str(OUT)):
        raise SystemExit(f"could not write {OUT}")
    bad = [layer.name() for layer in project.mapLayers().values() if not layer.isValid()]
    print("wrote", OUT, "layers", len(project.mapLayers()), "invalid", bad, "runs", made, "notes", notes)


main()
app.exitQgis()
