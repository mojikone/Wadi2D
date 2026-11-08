"""Load the stream corridors of Block 2 at 30 m into QGIS in the colours of the maps and save a project beside them.

Run inside QGIS (the Python console, or ``qgis-ltr.bat --code <this file>``). Layers: the DEM as a hillshade, the
1 km2 thalwegs (red dashed), the corridor outlines, the corridor cells (blue), the gap triangles (orange) and the
squares that stay (grey outlines, shown under 1:30,000). Nothing of an open project is removed.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsHillshadeRenderer,
    QgsLineSymbol,
    QgsProject,
    QgsRasterLayer,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)
from qgis.utils import iface

WORK = Path(r"D:\Mojtaba\Renardet\Wadi2D\W45 aligned mesh engine\stream_corridors")
DEM = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif")
MESH = WORK / "stream_mesh.gpkg"
SQUARES = WORK / "stream_squares.gpkg"
GROUP = "Stream corridors, Block 2 at 30 m"


def fill(colour: str, outline: str, width: str) -> QgsFillSymbol:
    return QgsFillSymbol.createSimple({"color": colour, "outline_color": outline, "outline_width": width})


def main() -> None:
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    old = root.findGroup(GROUP)
    if old is not None:
        root.removeChildNode(old)
    group = root.insertGroup(0, GROUP)
    layers = []
    squares = QgsVectorLayer(f"{SQUARES}|layername=squares_kept", "Squares that stay (30 m)", "ogr")
    squares.setRenderer(QgsSingleSymbolRenderer(fill("0,0,0,0", "#707070", "0.15")))
    squares.setScaleBasedVisibility(True)
    squares.setMinimumScale(30000.0)
    squares.setMaximumScale(1.0)
    layers.append(squares)
    triangles = QgsVectorLayer(f"{MESH}|layername=gap_triangles", "Gap triangles", "ogr")
    triangles.setRenderer(QgsSingleSymbolRenderer(fill("240,160,48,64", "#c86400", "0.2")))
    layers.append(triangles)
    cells = QgsVectorLayer(f"{MESH}|layername=corridor_cells", "Corridor cells (two of 30 m across)", "ogr")
    cells.setRenderer(QgsSingleSymbolRenderer(fill("42,127,212,64", "#1b4f8a", "0.25")))
    layers.append(cells)
    outlines = QgsVectorLayer(f"{MESH}|layername=corridors", "Corridors", "ogr")
    outlines.setRenderer(QgsSingleSymbolRenderer(fill("42,127,212,90", "#1b4f8a", "0.3")))
    outlines.setScaleBasedVisibility(True)
    outlines.setMinimumScale(1e9)
    outlines.setMaximumScale(30000.0)  # the filled corridors stand in for the cells when zoomed out
    layers.append(outlines)
    thalwegs = QgsVectorLayer(f"{MESH}|layername=thalwegs", "Thalwegs, 1 km2 streams", "ogr")
    thalwegs.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#d40000", "width": "0.5", "line_style": "dash"})))
    layers.append(thalwegs)
    for layer in reversed(layers):  # thalwegs on top, squares at the bottom
        if not layer.isValid():
            print("invalid layer", layer.name())
            continue
    for layer in layers:
        if layer.isValid():
            project.addMapLayer(layer, False)
    for layer in (thalwegs, outlines, cells, triangles, squares):
        if layer.isValid():
            group.addLayer(layer)
    if DEM.is_file() and not any(ly.source() == str(DEM) for ly in project.mapLayers().values()):
        dem = QgsRasterLayer(str(DEM), "Terrain, hillshade (GGC 5 m)")
        if dem.isValid():
            shade = QgsHillshadeRenderer(dem.dataProvider(), 1, 315.0, 45.0)
            dem.setRenderer(shade)
            dem.setOpacity(0.85)
            project.addMapLayer(dem, False)
            group.addLayer(dem)
    if outlines.isValid() and iface is not None:
        iface.mapCanvas().setDestinationCrs(QgsCoordinateReferenceSystem(outlines.crs()))
        iface.mapCanvas().setExtent(outlines.extent())
        iface.mapCanvas().refresh()
    out = WORK / "stream_corridors.qgz"
    if not project.fileName():
        project.setCrs(QgsCoordinateReferenceSystem(outlines.crs()))
        project.write(str(out))
        print("project saved to", out)
    else:
        print("layers added to the open project", project.fileName(), "(not saved)")


main()
