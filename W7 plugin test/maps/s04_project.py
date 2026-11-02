"""The final results as one QGIS project, grouped and styled. Own process, python-qgis-ltr.bat. Writes Wadi2D_results.qgz."""
import os
import sys
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsHillshadeRenderer,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsRasterLayer,
    QgsRasterShader,
    QgsRendererCategory,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont

ROOT = Path(r"D:\Mojtaba\Renardet\Wadi2D")
W2 = ROOT / "W2 full extent run"
T2 = W2 / "terrain"
RUN2 = W2 / "runs" / "full_30m_200yr"
HY = ROOT / "W7 plugin test" / "maps"
QML = Path(sys.argv[1])
CRS = QgsCoordinateReferenceSystem("EPSG:32640")
HYBRID = "type=xyz&url=https://mt1.google.com/vt/lyrs%3Dy%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0&crs=EPSG3857"
SWITCH_SCALE = 60000.0  # the 5 m raster shows when zoomed in past this; the 20 m one, lifted by maximum, above it

app = QgsApplication([], False)
app.initQgis()
project = QgsProject.instance()
project.setCrs(CRS)
project.setTitle("Wadi2D results")
project.setFilePathStorage = None
root = project.layerTreeRoot()


def raster(path, name, qml=None, opacity=None):
    layer = QgsRasterLayer(str(path), name)
    assert layer.isValid(), path
    if qml:
        layer.loadNamedStyle(str(QML / qml))
    if opacity is not None:
        layer.renderer().setOpacity(opacity)
    project.addMapLayer(layer, False)
    return layer


def vector(path, name):
    layer = QgsVectorLayer(str(path), name, "ogr")
    assert layer.isValid(), path
    layer.setCrs(CRS)
    project.addMapLayer(layer, False)
    return layer


def by_scale(fine, coarse):
    fine.setScaleBasedVisibility(True)
    fine.setMaximumScale(1.0)
    fine.setMinimumScale(SWITCH_SCALE)
    coarse.setScaleBasedVisibility(True)
    coarse.setMaximumScale(SWITCH_SCALE)
    coarse.setMinimumScale(100000000.0)


def ramp(layer, stops, opacity=0.85):
    shader = QgsRasterShader()
    fn = QgsColorRampShader(stops[0][0], stops[-1][0])
    fn.setColorRampType(QgsColorRampShader.Interpolated)
    fn.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, QColor(c), lab) for v, c, lab in stops])
    shader.setRasterShaderFunction(fn)
    r = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    r.setOpacity(opacity)
    layer.setRenderer(r)


def labels(layer, field, size, colour, placement=None, bold=False):
    fmt = QgsTextFormat()
    font = QFont("Arial")
    font.setBold(bold)
    fmt.setFont(font)
    fmt.setSize(size)
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
    s.displayAll = True
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
    layer.setLabelsEnabled(True)


def outline(layer, colour, width):
    layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": colour, "outline_width": str(width)})))


def stroke(layer, colour, width):
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": colour, "width": str(width)})))


def add(group, layers, on=False):
    for layer in layers:
        node = group.addLayer(layer)
        node.setItemVisibilityChecked(on)
        node.setExpanded(False)


# 1. Full extent
full = root.addGroup("1 Full project extent: Block 2 200-yr storm, 30 m grid")
res = full.addGroup("Results at the 5 m pixel")
haz5 = raster(T2 / "pixel_hazard_sloped_5m.tif", "Hazard H1-H6, 5 m (zoomed in)", "Block_2_Hazard_200y.qml", 0.85)
haz20 = raster(T2 / "pixel_hazard_20m.tif", "Hazard H1-H6, 20 m by maximum (zoomed out)", "Block_2_Hazard_200y.qml", 0.85)
dep5 = raster(T2 / "pixel_depth_sloped_5m.tif", "Maximum depth, 5 m (zoomed in)", "Block2_Depth_200Year.qml", 0.85)
dep20 = raster(T2 / "pixel_depth_20m.tif", "Maximum depth, 20 m by maximum (zoomed out)", "Block2_Depth_200Year.qml", 0.85)
by_scale(haz5, haz20)
by_scale(dep5, dep20)
add(res, [haz5, haz20], on=True)
add(res, [dep5, dep20])
eng = full.addGroup("Engine maps, 30 m cells")
speed = raster(RUN2 / "maps" / "max_speed.tif", "Maximum speed, m/s")
ramp(speed, [(0, "#ffffff", "0"), (2, "#fee08b", "2"), (4, "#fc8d59", "4"), (8, "#d73027", "8"), (12, "#67001f", "12+")])
arrival = raster(RUN2 / "maps" / "arrival.tif", "Arrival time, s")
ramp(arrival, [(0, "#ffffcc", "0"), (21600, "#a1dab4", "6 h"), (43200, "#41b6c4", "12 h"), (64800, "#2c7fb8", "18 h"), (86400, "#253494", "24 h")])
add(eng, [speed, arrival])
set1 = full.addGroup("Setup")
bnd = vector(W2 / "boundaries.geojson", "Open boundaries along the coast")
stroke(bnd, "#e0001b", 1.2)
dom = vector(W2 / "domain.geojson", "Model domain, actual project boundary")
outline(dom, "#0033cc", 0.8)
add(set1, [bnd, dom], on=True)
ter = full.addGroup("Terrain")
dem = raster(T2 / "NSA5_COP30_blend.tif", "NSA 5 m with Copernicus 30 m, hillshade")
shade = QgsHillshadeRenderer(dem.dataProvider(), 1, 315, 45)
shade.setZFactor(1.5)
shade.setMultiDirectional(True)
dem.setRenderer(shade)
add(ter, [dem])

# 2. Hybrid
hyb = root.addGroup("2 Hybrid Block 2: lumped HMS hills into 2D, 20 m grid")
res2 = hyb.addGroup("Results at the 5 m pixel")
h5 = raster(HY / "terrain" / "pixel_hazard_sloped_5m.tif", "Hazard H1-H6, 5 m (zoomed in)", "Block_2_Hazard_200y.qml", 0.85)
h10 = raster(HY / "terrain" / "hazard_10m.tif", "Hazard H1-H6, 10 m by maximum (zoomed out)", "Block_2_Hazard_200y.qml", 0.85)
d5 = raster(HY / "terrain" / "pixel_depth_sloped_5m.tif", "Maximum depth, 5 m (zoomed in)", "Block2_Depth_200Year.qml", 0.85)
d10 = raster(HY / "terrain" / "depth_10m.tif", "Maximum depth, 10 m by maximum (zoomed out)", "Block2_Depth_200Year.qml", 0.85)
by_scale(h5, h10)
by_scale(d5, d10)
add(res2, [h5, h10, d5, d10])
set2 = hyb.addGroup("Setup")
sec = vector(HY / "layers" / "sections.geojson", "Dam sections")
stroke(sec, "#000000", 0.9)
labels(sec, "label", 9, "#000000", Qgis.LabelPlacement.Line, True)
inf = vector(HY / "layers" / "inflows.geojson", "Lumped hydrographs enter 2D here")
inf.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({"name": "circle", "color": "#d400d4", "outline_color": "white", "size": "3"})))
labels(inf, "label", 8, "#7a007a", Qgis.LabelPlacement.OrderedPositionsAroundPoint)
b2 = vector(HY / "layers" / "boundaries.geojson", "Open boundaries")
stroke(b2, "#e0001b", 1.4)
labels(b2, "label", 9, "#a00014", Qgis.LabelPlacement.Line, True)
d2 = vector(HY / "layers" / "domain.geojson", "2D model domain")
outline(d2, "#0033cc", 1.0)
rch = vector(HY / "layers" / "reaches.geojson", "Reaches, routed by the 2D model here")
stroke(rch, "#00b7e0", 0.5)
labels(rch, "label", 7.5, "#006f8a", Qgis.LabelPlacement.Line)
sub = vector(HY / "layers" / "subbasins.geojson", "Subbasins, lumped or 2D")
lumped = QgsFillSymbol.createSimple({"color": "255,170,60,70", "outline_color": "#b35a00", "outline_width": "0.5"})
twod = QgsFillSymbol.createSimple({"color": "40,190,90,110", "outline_color": "#0a7a30", "outline_width": "0.8"})
sub.setRenderer(QgsCategorizedSymbolRenderer("mode", [QgsRendererCategory("lumped", lumped, "Lumped HMS"), QgsRendererCategory("2d", twod, "2D rain-on-grid")]))
labels(sub, "label", 9, "#5a2d00", Qgis.LabelPlacement.OverPoint, True)
add(set2, [sec, inf, b2, d2, rch, sub])

# 3. Background
back = root.addGroup("3 Background")
sat = raster(HYBRID, "Google satellite hybrid") if False else QgsRasterLayer(HYBRID, "Google satellite hybrid", "wms")
project.addMapLayer(sat, False)
add(back, [sat], on=True)
for group in (hyb, eng, ter):
    group.setExpanded(False)
hyb.setItemVisibilityChecked(False)
res2.setItemVisibilityChecked(False)
set2.setItemVisibilityChecked(False)
eng.setItemVisibilityChecked(False)
ter.setItemVisibilityChecked(False)
view = project.viewSettings()
extent = dom.extent()
extent.scale(1.05)
from qgis.core import QgsReferencedRectangle  # noqa: E402

view.setDefaultViewExtent(QgsReferencedRectangle(extent, CRS))
out = ROOT / "Wadi2D_results.qgz"
print("saved", project.write(str(out)), out.stat().st_size, flush=True)
print("layers", len(project.mapLayers()), flush=True)
os._exit(0)
