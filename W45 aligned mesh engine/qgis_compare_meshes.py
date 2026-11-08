"""Load the three Block 2 meshes of compare_meshes.py into QGIS as three groups in the map colours, over one lattice
of 30 m squares and the GGC hillshade, and save the project. Run inside QGIS (the Python console or the engine link).
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
KINDS = [
    ("streams", "1. Streams as two 30 m cells, no banks"),
    ("floor", "2. Under 5 % is floodplain: 30 m cells across the floor"),
    ("dock", "3. The Mesh section's rule today: 2 m banks, cells a quarter of the width"),
]
BASE = "Block 2 at 30 m: the squares and the ground"


def fill(colour: str, outline: str, width: str) -> QgsFillSymbol:
    return QgsFillSymbol.createSimple({"color": colour, "outline_color": outline, "outline_width": width})


def add(project, group, layer, renderer, visible=True, min_scale=None, max_scale=None):
    if not layer.isValid():
        print("invalid layer", layer.name())
        return None
    layer.setRenderer(renderer)
    if min_scale is not None or max_scale is not None:
        layer.setScaleBasedVisibility(True)
        layer.setMinimumScale(min_scale if min_scale is not None else 1e12)
        layer.setMaximumScale(max_scale if max_scale is not None else 1.0)
    project.addMapLayer(layer, False)
    node = group.addLayer(layer)
    node.setItemVisibilityChecked(visible)
    return layer


def main() -> None:
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    for _kind, title in KINDS + [("", BASE)]:
        old = root.findGroup(title)
        if old is not None:
            root.removeChildNode(old)
    extent_layer = None
    for n, (kind, title) in enumerate(KINDS):
        mesh = WORK / f"mesh_{kind}.gpkg"
        if not mesh.is_file():
            print("missing", mesh)
            continue
        group = root.insertGroup(n, title)
        group.setItemVisibilityChecked(n == 0)
        add(project, group, QgsVectorLayer(f"{mesh}|layername=thalwegs", "Thalwegs, 1 km2 streams", "ogr"),
            QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#d40000", "width": "0.45", "line_style": "dash"})))
        banks = QgsVectorLayer(f"{mesh}|layername=banks", "Banks used", "ogr")
        if banks.isValid():
            add(project, group, banks, QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#008000", "width": "0.4"})))
        outlines = add(project, group, QgsVectorLayer(f"{mesh}|layername=corridors", "Corridors (zoomed out)", "ogr"),
                       QgsSingleSymbolRenderer(fill("42,127,212,110", "#1b4f8a", "0.3")), min_scale=1e9, max_scale=30000.0)
        add(project, group, QgsVectorLayer(f"{mesh}|layername=corridor_cells", "Corridor cells", "ogr"),
            QgsSingleSymbolRenderer(fill("42,127,212,64", "#1b4f8a", "0.25")))
        add(project, group, QgsVectorLayer(f"{mesh}|layername=gap_triangles", "Gap triangles", "ogr"),
            QgsSingleSymbolRenderer(fill("240,160,48,64", "#c86400", "0.2")))
        if extent_layer is None:
            extent_layer = outlines
    base = root.insertGroup(len(KINDS), BASE)
    lattice = WORK / "lattice_squares.gpkg"
    if lattice.is_file():
        add(project, base, QgsVectorLayer(f"{lattice}|layername=squares", "Squares of 30 m (under 1:30,000)", "ogr"),
            QgsSingleSymbolRenderer(fill("0,0,0,0", "#707070", "0.15")), min_scale=30000.0, max_scale=1.0)
    if DEM.is_file():
        dem = QgsRasterLayer(str(DEM), "Terrain, hillshade (GGC 5 m)")
        if dem.isValid():
            dem.setRenderer(QgsHillshadeRenderer(dem.dataProvider(), 1, 315.0, 45.0))
            dem.setOpacity(0.85)
            project.addMapLayer(dem, False)
            base.addLayer(dem)
    if extent_layer is not None and iface is not None:
        iface.mapCanvas().setDestinationCrs(QgsCoordinateReferenceSystem(extent_layer.crs()))
        iface.mapCanvas().setExtent(extent_layer.extent())
        iface.mapCanvas().refresh()
    out = WORK / "compare_meshes.qgz"
    project.setCrs(QgsCoordinateReferenceSystem(extent_layer.crs()) if extent_layer is not None else project.crs())
    project.write(str(out))
    print("project saved to", out)


main()
