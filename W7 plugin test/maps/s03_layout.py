"""Three A3 sheets from a QGIS print layout: the hybrid setup, maximum depth, AIDR hazard. Own process, python-qgis-ltr.bat."""
import json
import os
import sys
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLayerTree,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsMapLayerLegendUtils,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsRendererCategory,
    QgsCategorizedSymbolRenderer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont

HERE = Path(__file__).resolve().parent
L = HERE / "layers"
T = HERE / "terrain"
QML = Path(sys.argv[1])
SAT = "type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=17&zmin=0&crs=EPSG3857"
setup = json.loads((HERE / "setup.json").read_text())
facts = json.loads((HERE / "facts.json").read_text())

app = QgsApplication([], False)
app.initQgis()
project = QgsProject.instance()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:32640"))


def vector(name, title):
    layer = QgsVectorLayer(str(L / f"{name}.geojson"), title, "ogr")
    layer.setCrs(QgsCoordinateReferenceSystem("EPSG:32640"))
    project.addMapLayer(layer, False)
    return layer


def labels(layer, field, size, colour, placement=None, bold=False, every=True):
    fmt = QgsTextFormat()
    font = QFont("Arial")
    font.setBold(bold)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setSizeUnit(QgsUnitTypes.RenderPoints)
    fmt.setColor(QColor(colour))
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setColor(QColor("white"))
    fmt.setBuffer(buf)
    s = QgsPalLayerSettings()
    s.fieldName = field
    s.setFormat(fmt)
    if placement is not None:
        s.placement = placement
    s.displayAll = every
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
    layer.setLabelsEnabled(True)


subs = vector("subbasins", "Subbasins")
lumped = QgsFillSymbol.createSimple({"color": "255,170,60,70", "outline_color": "#b35a00", "outline_width": "0.5"})
twod = QgsFillSymbol.createSimple({"color": "40,190,90,110", "outline_color": "#0a7a30", "outline_width": "0.8"})
subs.setRenderer(QgsCategorizedSymbolRenderer("mode", [QgsRendererCategory("lumped", lumped, "Subbasin, lumped HMS (rain masked in 2D)"), QgsRendererCategory("2d", twod, "Subbasin, 2D rain-on-grid")]))
labels(subs, "label", 8.5, "#5a2d00", Qgis.LabelPlacement.OverPoint, bold=True)
domain = vector("domain", "2D model domain (closed walls except open boundaries)")
domain.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#0033cc", "outline_width": "1.1"})))
bound = vector("boundaries", "Open boundary")
bound.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#e0001b", "width": "1.6"})))
labels(bound, "label", 8.5, "#a00014", Qgis.LabelPlacement.Line, bold=True)
inflow = vector("inflows", "Lumped hydrograph enters 2D here")
inflow.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({"name": "circle", "color": "#d400d4", "outline_color": "white", "size": "3.2"})))
labels(inflow, "label", 7.5, "#7a007a", Qgis.LabelPlacement.OrderedPositionsAroundPoint)
sections = vector("sections", "Dam section")
sections.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#000000", "width": "1.0"})))
labels(sections, "label", 8, "#000000", Qgis.LabelPlacement.Line, bold=True)
reach_path = L / "reaches.geojson"
reaches = None
if reach_path.exists():
    reaches = vector("reaches", "Reach, routed by the 2D model here")
    reaches.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#00b7e0", "width": "0.5"})))
sat = QgsRasterLayer(SAT, "Satellite", "wms")
sat.renderer().setOpacity(0.55)
project.addMapLayer(sat, False)
depth = QgsRasterLayer(str(T / "depth_10m.tif"), "Maximum depth, m")
depth.loadNamedStyle(str(QML / "Block2_Depth_200Year.qml"))
depth.renderer().setOpacity(0.9)
project.addMapLayer(depth, False)
hazard = QgsRasterLayer(str(T / "hazard_10m.tif"), "AIDR hazard class")
hazard.loadNamedStyle(str(QML / "Block_2_Hazard_200y.qml"))
hazard.renderer().setOpacity(0.95)
project.addMapLayer(hazard, False)

layout = QgsPrintLayout(project)
layout.initializeDefaults()
pages = layout.pageCollection()
pages.page(0).setPageSize("A3", QgsLayoutItemPage.Landscape)
for _ in range(2):
    p = QgsLayoutItemPage(layout)
    p.setPageSize("A3", QgsLayoutItemPage.Landscape)
    pages.addPage(p)
W, H = 420.0, 297.0
GAP = 10.0
ext = domain.extent()
ext.scale(1.04)


def label(page, text, x, y, w, h, size, bold=False, colour="#000000"):
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    font = QFont("Arial")
    font.setPointSizeF(size)
    font.setBold(bold)
    item.setFont(font)
    item.setFontColor(QColor(colour))
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters), page=page)
    item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(item)
    return item


kept = []


def sheet(page, title, sub, layers, legend_layers, notes):
    mx, my, mw, mh = 10.0, 26.0, 280.0, 261.0
    label(page, title, 10, 8, 400, 10, 19, True)
    label(page, sub, 10, 18, 400, 7, 10.5)
    m = QgsLayoutItemMap(layout)
    m.attemptMove(QgsLayoutPoint(mx, my, QgsUnitTypes.LayoutMillimeters), page=page)
    m.attemptResize(QgsLayoutSize(mw, mh, QgsUnitTypes.LayoutMillimeters))
    m.setCrs(QgsCoordinateReferenceSystem("EPSG:32640"))
    m.zoomToExtent(ext)
    m.setLayers(layers)
    m.setKeepLayerSet(True)
    m.setFrameEnabled(True)
    layout.addLayoutItem(m)
    root = QgsLayerTree()
    kept.append(root)  # the legend does not own it
    for lay in legend_layers:
        root.addLayer(lay)
    leg = QgsLayoutItemLegend(layout)
    leg.setLinkedMap(m)
    leg.setAutoUpdateModel(False)
    leg.model().setRootGroup(root)
    for node in root.findLayers():
        if isinstance(node.layer(), QgsRasterLayer):  # leave out the band name
            count = len(leg.model().layerLegendNodes(node, True))
            QgsMapLayerLegendUtils.setLegendNodeOrder(node, list(range(1, count)))
            leg.model().refreshLayerLegend(node)
    leg.setTitle("Legend")
    leg.attemptMove(QgsLayoutPoint(296, 26, QgsUnitTypes.LayoutMillimeters), page=page)
    layout.addLayoutItem(leg)
    bar = QgsLayoutItemScaleBar(layout)
    bar.setStyle("Single Box")
    bar.setLinkedMap(m)
    bar.setUnits(QgsUnitTypes.DistanceKilometers)
    bar.setNumberOfSegments(4)
    bar.setNumberOfSegmentsLeft(0)
    bar.setUnitsPerSegment(2.5)
    bar.setUnitLabel("km")
    bar.attemptMove(QgsLayoutPoint(296, 258, QgsUnitTypes.LayoutMillimeters), page=page)
    layout.addLayoutItem(bar)
    arrow = QgsLayoutItemPicture(layout)
    arrow.setPicturePath(QgsApplication.svgPaths()[0] + "/arrows/NorthArrow_02.svg")
    arrow.attemptMove(QgsLayoutPoint(394, 224, QgsUnitTypes.LayoutMillimeters), page=page)
    arrow.attemptResize(QgsLayoutSize(18, 24, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(arrow)
    label(page, notes, 296, 150, 116, 100, 9.5)
    label(page, "EPSG:32640. Imagery: Google.", 296, 278, 116, 6, 8, colour="#555555")


overlay_all = [x for x in (sections, inflow, bound, domain) if x]
setup_layers = [sections, inflow, bound, domain] + ([reaches] if reaches else []) + [subs, sat]
legend_setup = [subs, domain, bound, inflow] + ([reaches] if reaches else []) + [sections]
notes_setup = (
    f"How the model is built\n\n"
    f"Hills: {setup['lumped_n']} subbasins, {setup['lumped_km2']:,.0f} km2, run in lumped HMS (SCS CN, lag). Their rain is masked out of the 2D model.\n\n"
    f"Each hydrograph enters the 2D model at its magenta point, {setup['inflow_points']} points.\n\n"
    f"2D: {', '.join(setup['two_d'])} and the plain, rain-on-grid on {setup['dx']:g} m cells with 5 m terrain tables, CN grid, Manning n {setup['manning']:g}.\n\n"
    f"Water leaves through {setup['boundaries']} open boundaries, normal depth at S 0.008. Every other edge of the domain is a closed wall. HMS reaches are not routed: the 2D model carries the hydrographs down the wadis.\n\n"
    f"Storm: Block 2 200-yr, {setup['storm_mm']:g} mm, 24 h, storm area {setup['storm_area']:g} km2. Simulated {setup['duration_h']:g} h.\n\n"
    f"{facts['water']}"
)
sheet(0, "Wadi2D hybrid model, Block 2: setup", "Lumped HMS hills feeding the 2D model downstream", setup_layers, legend_setup, notes_setup)
sheet(1, "Wadi2D hybrid model, Block 2: maximum depth", "Block 2 200-yr storm. Depth at the 5 m pixel, sloped water surface", [sections, inflow, bound, domain, depth, sat], [depth, domain, bound, inflow, sections], facts["depth"])
sheet(2, "Wadi2D hybrid model, Block 2: AIDR hazard H1 to H6", "Block 2 200-yr storm. Pixel depth x interpolated velocity, 15-minute maps", [sections, inflow, bound, domain, hazard, sat], [hazard, domain, bound, inflow, sections], facts["hazard"])

exporter = QgsLayoutExporter(layout)
pdf = QgsLayoutExporter.PdfExportSettings()
pdf.dpi = 200
pdf.rasterizeWholeImage = False
img = QgsLayoutExporter.ImageExportSettings()
img.dpi = 200
print("png", exporter.exportToImage(str(HERE / "sheet.png"), img), flush=True)
print("pdf", exporter.exportToPdf(str(HERE / "Wadi2D_hybrid_Block2_maps.pdf"), pdf), flush=True)
sys.stdout.flush()
os._exit(0)
