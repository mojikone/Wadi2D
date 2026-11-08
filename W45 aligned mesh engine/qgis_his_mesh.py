"""Load his mesh rule of Block 2 (his_mesh.py) into QGIS as one group in the map colours, over the hillshade, and
save the project. Run inside QGIS (the Python console or the engine link)."""

from __future__ import annotations

import os
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
SUFFIX = os.environ.get("WADI2D_MESH_SUFFIX", "")
MESH = WORK / f"mesh_his{SUFFIX}.gpkg"
GROUP = ("5. His rule with fixed 30 m cells repeated to the 5 % edge, 60 m mountains" if SUFFIX else "4. His rule: 30 m, corridors across the 5 % floor, 60 m mountains over 20 %")


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
    old = root.findGroup(GROUP)
    if old is not None:
        root.removeChildNode(old)
    for n in range(root.children().__len__()):  # the other mesh groups off, so this one shows alone
        child = root.children()[n]
        if hasattr(child, "setItemVisibilityChecked") and child.name()[:2] in ("1.", "2.", "3.", "4.", "5.") and child.name() != GROUP:
            child.setItemVisibilityChecked(False)
    group = root.insertGroup(0, GROUP)
    add(project, group, QgsVectorLayer(f"{MESH}|layername=thalwegs", "Thalwegs, 1 km2 streams", "ogr"),
        QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#d40000", "width": "0.45", "line_style": "dash"})))
    add(project, group, QgsVectorLayer(f"{MESH}|layername=floor_edges", "Floor edges, under 5 %", "ogr"),
        QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#008000", "width": "0.4"})))
    outlines = add(project, group, QgsVectorLayer(f"{MESH}|layername=corridors", "Corridors (zoomed out)", "ogr"),
                   QgsSingleSymbolRenderer(fill("42,127,212,110", "#1b4f8a", "0.3")), min_scale=1e9, max_scale=30000.0)
    add(project, group, QgsVectorLayer(f"{MESH}|layername=corridor_cells", "Corridor cells, 30 m across the floor", "ogr"),
        QgsSingleSymbolRenderer(fill("42,127,212,64", "#1b4f8a", "0.25")))
    add(project, group, QgsVectorLayer(f"{MESH}|layername=gap_triangles", "Gap triangles", "ogr"),
        QgsSingleSymbolRenderer(fill("240,160,48,64", "#c86400", "0.2")))
    add(project, group, QgsVectorLayer(f"{MESH}|layername=cells_60", "Mountain cells, 60 m", "ogr"),
        QgsSingleSymbolRenderer(fill("80,80,80,40", "#303030", "0.3")), min_scale=200000.0, max_scale=1.0)
    add(project, group, QgsVectorLayer(f"{MESH}|layername=cells_30", "Squares, 30 m (under 1:30,000)", "ogr"),
        QgsSingleSymbolRenderer(fill("0,0,0,0", "#707070", "0.15")), min_scale=30000.0, max_scale=1.0)
    if DEM.is_file() and not any(ly.source() == str(DEM) for ly in project.mapLayers().values()):
        dem = QgsRasterLayer(str(DEM), "Terrain, hillshade (GGC 5 m)")
        if dem.isValid():
            dem.setRenderer(QgsHillshadeRenderer(dem.dataProvider(), 1, 315.0, 45.0))
            dem.setOpacity(0.85)
            project.addMapLayer(dem, False)
            group.addLayer(dem)
    if outlines is not None and iface is not None:
        iface.mapCanvas().setDestinationCrs(QgsCoordinateReferenceSystem(outlines.crs()))
        iface.mapCanvas().setExtent(outlines.extent())
        iface.mapCanvas().refresh()
    out = WORK / "compare_meshes.qgz"
    project.write(str(out))
    print("project saved to", out)


main()
