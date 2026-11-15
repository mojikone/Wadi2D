"""Block2_four_ways.qgz: the four runs in one QGIS project, built headless in its own QGIS 3.44.8 process.

Run with ``"C:\\Program Files\\QGIS 3.44.8\\bin\\python-qgis-ltr.bat" s06_qgis_project.py``. It never touches an open QGIS
or any of his projects: it starts its own QgsApplication without a GUI and writes only W79's project file.

The run groups use the plugin's own modules (``plugin/wadi2d_qgis``: layer_groups, result_layers, time_layer, style), so
each is laid out and styled as the dock lays out a run: ``Wadi2D – <run>`` > Inputs (Terrain, Boundaries, Structures,
Hydrology, Mesh) and ``Results – <run>`` > Time slider, Model setup (domain, sea boundary, inflows, result lines, cell
grid), Pixel rasters of record (hazard, depth, speed, depth x speed), Cell maps. Run 2 has no grid: its group holds the
lumped network's peaks and series as tables and the subbasins with their peaks. A common group at the bottom holds the
terrain, the domain, the dams and the HMS model.
"""

from __future__ import annotations

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
    QgsMarkerSymbol,
    QgsProject,
    QgsRasterLayer,
    QgsReferencedRectangle,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)

app = QgsApplication([], False)
app.initQgis()

from w79 import DAMS, DEM5, INPUTS, RUN_NAMES, RUN_TITLES, RUNS, safe_csv_uri  # noqa: E402
from wadi2d_qgis import layer_groups as lg  # noqa: E402
from wadi2d_qgis import result_layers as rl  # noqa: E402
from wadi2d_qgis import style  # noqa: E402
from wadi2d_qgis import time_layer as tl  # noqa: E402

import os  # noqa: E402

CRS = QgsCoordinateReferenceSystem("EPSG:32640")
OUT = Path(os.environ.get("W79_QGZ", HERE / "Block2_four_ways.qgz"))
TEST_RUN = os.environ.get("W79_TEST_RUN")
"""A dry pass of this script on one finished run folder, written to W79_QGZ: debugging only."""


def run_folder(number: int) -> Path:
    return RUNS / (TEST_RUN or RUN_NAMES[number])
project = QgsProject.instance()
project.setCrs(CRS)
project.setTitle("Block 2 four ways (W79)")
root = project.layerTreeRoot()


def csv_table(path: Path, title: str, subset: str = ""):
    layer = QgsVectorLayer(safe_csv_uri(path), title, "delimitedtext")
    assert layer.isValid(), path
    if subset:
        layer.setSubsetString(subset)
    return layer


def vec(path: Path, title: str, layer_name: str | None = None, subset: str = ""):
    uri = str(path) if layer_name is None else f"{path}|layername={layer_name}"
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True
    layer = QgsVectorLayer(uri, title, "ogr", options)
    assert layer.isValid(), uri
    if subset:
        layer.setSubsetString(subset)
    return layer


def line_style(layer, colour: str, width: float, dash: bool = False) -> None:
    props = {"color": colour, "width": str(width)}
    if dash:
        props["line_style"] = "dash"
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple(props)))


def labelled(layer, field: str, size: float, colour: str, placement) -> None:
    style._labels(layer, field, size, colour, placement, bold=True)  # the plugin's label settings


def dam_layers(kinds: tuple[str, ...]) -> list:
    """The dam inputs of dams.geojson, one layer per kind, styled."""
    gj = INPUTS / "dams.geojson"
    out = []
    if "crest_line" in kinds:
        lay = vec(gj, "Dam crest lines (2D pools), crest on the GGC terrain", subset="\"kind\" = 'crest_line'")
        line_style(lay, "#8b0000", 1.2)
        labelled(lay, "dam", 8.0, "#8b0000", Qgis.LabelPlacement.Line)
        out.append(lay)
    if "spillway" in kinds:
        lay = vec(gj, "Spillways (2D), Q = C L H^1.5", subset="\"kind\" = 'spillway'")
        line_style(lay, "#ff8c00", 2.4)
        out.append(lay)
    if "pool" in kinds:
        lay = vec(gj, "Pool at dam crest + 0.3 m (DEM)", subset="\"kind\" LIKE 'pool_%'")
        lay.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
            {"color": "90,160,230,60", "outline_color": "#1f4e8c", "outline_width": "0.3"})))
        out.append(lay)
    if "ring" in kinds:
        lay = vec(gj, "Pool inflow lines (read the inflow on the grid)", subset="\"kind\" = 'inflow_ring'")
        line_style(lay, "#7b2fbf", 0.8, dash=True)
        out.append(lay)
    if "entry" in kinds:
        lay = vec(gj, "Run 3: reservoir outflow enters the grid here", subset="\"kind\" = 'outflow_entry_run3'")
        lay.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
            {"name": "triangle", "color": "#d400d4", "outline_color": "white", "size": "3.4"})))
        labelled(lay, "dam", 7.5, "#7a007a", Qgis.LabelPlacement.OrderedPositionsAroundPoint)
        out.append(lay)
    if "dam_line" in kinds:
        lay = vec(gj, "Dam result lines (W1)", subset="\"kind\" = 'dam_line'")
        line_style(lay, "#000000", 1.0)
        labelled(lay, "dam", 8.0, "#000000", Qgis.LabelPlacement.Line)
        out.append(lay)
    return out


def hms_layers() -> list:
    net = RUNS / RUN_NAMES[2] / "network.gpkg"
    subs = vec(net, "HMS Basin 3 subbasins", "subbasins")
    subs.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"color": "0,0,0,0", "outline_color": "#1f4e8c", "outline_width": "0.35"})))
    labelled(subs, "name", 7.0, "#1f3a66", Qgis.LabelPlacement.OverPoint)
    junctions = vec(net, "HMS Basin 3 junctions and reservoirs", "junctions")
    style.style_basin_junctions(junctions)
    reaches = vec(net, "HMS Basin 3 reaches", "reaches")
    style.style_basin_reaches(reaches)
    return [junctions, reaches, subs]


def add_all(group, layers, shown=True) -> None:
    for layer in layers:
        node = lg.add_layer(group, layer, shown=shown)
        node.setExpanded(False)


def common_group() -> None:
    top = root.insertGroup(0, "Block 2 \N{EN DASH} common inputs (terrain, domain, dams, HMS model)")
    hill = QgsRasterLayer(str(DEM5), "Terrain, GGC HDSM 5 m, hillshade")
    hill.setRenderer(QgsHillshadeRenderer(hill.dataProvider(), 1, 315.0, 45.0))
    dem = QgsRasterLayer(str(DEM5), "Terrain, GGC HDSM 5 m, elevation")
    dem.setOpacity(0.5)
    dom = vec(INPUTS / "domain.geojson", "2D domain to the sea (Basin 3 polygons + coast strip)")
    style.style_domain(dom)
    dams = dam_layers(("dam_line", "crest_line", "spillway", "entry", "ring", "pool"))
    peaks = csv_table(HERE / "dam_peaks.csv", "Dam peaks, all four runs, with the ARF of each (dam_peaks.csv)")
    outflow = rl._vector(run_folder(1), rl.BOUNDARY_LAYER, "Outflow lines: the sea, the side and north outlets (normal depth)")
    if outflow is None:
        raise SystemExit("run 1 has no boundary layer")
    style.style_boundaries(outflow)
    cells = [lay for lay in rl.open_strip_mesh(run_folder(1))]
    for lay in cells:
        lay.setName(f"Aligned cells, 20 m centre mesh (run 1): {lay.name()}")
    add_all(top, [peaks, *dams, outflow, *hms_layers(), dom])
    add_all(top, cells, shown=False)
    project.addMapLayer(dem, False)
    project.addMapLayer(hill, False)
    top.addLayer(dem).setItemVisibilityChecked(False)
    top.addLayer(hill)


def grid_run(number: int) -> None:
    folder = run_folder(number)
    model = lg.model_of_run(folder)
    group = lg.model_group(model)
    group.setName(f"{lg.model_title(model)}  ({RUN_TITLES[number]})")
    found = rl.load_products(folder)
    if found is None and not TEST_RUN:
        raise SystemExit(f"{folder} has no pixel rasters")
    rl.load_cell_grid(folder)
    if not rl.load_strip_mesh(folder) and not TEST_RUN:  # the aligned cells and their faces, beside the cell grid
        raise SystemExit(f"{folder} has no aligned cells (maps/strip_mesh.gpkg)")
    frames = tl.open_frames(folder)
    if frames is None:
        raise SystemExit(f"{folder} has no time-slider frames")
    tl._add(frames, folder)  # the dock's own placement, into the Time slider group
    results = lg.run_results(folder)
    cells = lg.subgroup(results, lg.CELLS)
    for name, title, styler in (("max_depth.tif", "Maximum depth, cells, m", style.style_depth),
                                ("max_speed.tif", "Maximum speed, cells, m/s", None),
                                ("hazard.tif", "Hazard, cells", style.style_hazard)):
        lay = QgsRasterLayer(str(folder / "maps" / name), title)
        if lay.isValid():
            if styler is not None:
                styler(lay)
            add_all(cells, [lay], shown=False)
    cells.setExpanded(False)
    add_all(results, [csv_table(HERE / "dam_peaks.csv", "Dam peaks of this run", f"\"run\" = {number}")])
    structures = lg.input_group(model, lg.STRUCTURES)
    if number in (1, 4):
        add_all(structures, dam_layers(("crest_line", "spillway", "ring")))
    else:
        add_all(structures, dam_layers(("ring",)))
    hyd = lg.input_group(model, lg.HYDROLOGY)
    if number == 3:
        add_all(hyd, dam_layers(("entry",)))
    if number in (3, 4):
        subs = hms_layers()[2]
        add_all(hyd, [subs], shown=False)


def lumped_run() -> None:
    folder = RUNS / RUN_NAMES[2]
    model = lg.model_of_run(folder)
    group = lg.model_group(model)
    group.setName(f"{lg.model_title(model)}  ({RUN_TITLES[2]})")
    results = lg.run_results(folder)
    series = lg.subgroup(results, "Network series of record (lumped engine, every element)")
    tables = [csv_table(folder / "network_peaks.csv", "Every element: peak, time to peak, volume")]
    for dam in DAMS:
        tables.append(csv_table(folder / "series" / f"network_{dam.replace(' ', '_')}_Reservoir.csv",
                                f"{dam} Reservoir: inflow, outflow, pool, storage, every 5 min"))
    add_all(series, tables)
    net = folder / "network.gpkg"
    subs = vec(net, "Subbasins, peak outflow", "subbasins")
    style.style_subbasins(subs)
    junctions = vec(net, "Junctions and reservoirs", "junctions")
    style.style_basin_junctions(junctions)
    reaches = vec(net, "Reaches, Muskingum-Cunge", "reaches")
    style.style_basin_reaches(reaches)
    add_all(lg.subgroup(results, lg.SETUP), [junctions, reaches, subs])
    add_all(results, [csv_table(HERE / "dam_peaks.csv", "Dam peaks of this run", "\"run\" = 2")])
    add_all(lg.input_group(model, lg.HYDROLOGY), hms_layers(), shown=False)


def main() -> None:
    common_group()
    for number in ((1, 2) if TEST_RUN else (4, 3, 2, 1)):  # each model group goes on top: run 1 ends first
        if number == 2:
            lumped_run()
        else:
            grid_run(number)
        if number != 1:
            node = lg.find_model(lg.model_of_run(run_folder(number) if number != 2 else RUNS / RUN_NAMES[2]))
            if node is not None:
                node.setItemVisibilityChecked(False)
    for child in root.children():
        if isinstance(child, QgsLayerTreeGroup):
            child.setExpanded(child.name().startswith(lg.MODEL_PREFIX + RUN_NAMES[1]))
    dom = vec(INPUTS / "domain.geojson", "extent")
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(dom.extent(), CRS))
    project.writeEntryBool("Paths", "/Absolute", False)
    if not project.write(str(OUT)):
        raise SystemExit(f"could not write {OUT}")
    print("wrote", OUT, "layers", len(project.mapLayers()))


main()
app.exitQgis()
