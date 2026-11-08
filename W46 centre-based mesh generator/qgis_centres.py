"""Load the centre generator's Block 2 mesh (block2_centres.py) into QGIS as group 6 of the W45 comparison project,
coloured by what each cell is, and save the project. Run inside QGIS (the Python console or the engine link)."""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsProject,
    QgsRendererCategory,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)
from qgis.utils import iface

WORK = Path(r"D:\Mojtaba\Renardet\Wadi2D\W46 centre-based mesh generator\block2")
MESH = WORK / "mesh_centres.gpkg"
PROJECT = Path(r"D:\Mojtaba\Renardet\Wadi2D\W45 aligned mesh engine\stream_corridors\compare_meshes.qgz")
GROUP = "6. Cells from centres (W46): 4-sided on the lines, polygons of 5 to 8 faces around, squares beyond"
FACE_COLOURS = {5: "255,210,127,120", 6: "255,167,38,120", 7: "230,81,0,120", 8: "183,28,28,120"}


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


def band_renderer() -> QgsCategorizedSymbolRenderer:
    categories = [QgsRendererCategory(4, fill("0,0,0,0", "#707070", "0.2"), "4 faces, a square")]
    for n, colour in FACE_COLOURS.items():
        categories.append(QgsRendererCategory(n, fill(colour, "#555555", "0.25"), f"{n} faces"))
    for n in range(9, 13):
        categories.append(QgsRendererCategory(n, fill("123,31,162,140", "#4a148c", "0.3"), f"{n} faces, over the limit"))
    return QgsCategorizedSymbolRenderer("faces", categories)


def main() -> None:
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    old = root.findGroup(GROUP)
    if old is not None:
        root.removeChildNode(old)
    for child in root.children():
        if hasattr(child, "setItemVisibilityChecked") and child.name()[:2] in ("1.", "2.", "3.", "4.", "5.") and child.name() != GROUP:
            child.setItemVisibilityChecked(False)
    group = root.insertGroup(0, GROUP)
    add(project, group, QgsVectorLayer(f"{MESH}|layername=thalwegs", "Thalwegs, 1 km2 streams", "ogr"),
        QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#d40000", "width": "0.45", "line_style": "dash"})))
    add(project, group, QgsVectorLayer(f"{MESH}|layername=bed_edges", "Bed edges, the floor rule (scarp 1 m in 10 m, rise 2 m, 5 % cap)", "ogr"),
        QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#008000", "width": "0.7"})))
    add(project, group, QgsVectorLayer(f"{MESH}|layername=line_faces", "Faces on the lines", "ogr"),
        QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#08306b", "width": "0.6"})))
    cells = add(project, group, QgsVectorLayer(f"{MESH}|layername=line_cells", "Cells on the lines, 4-sided", "ogr"),
                QgsSingleSymbolRenderer(fill("42,127,212,90", "#1b4f8a", "0.25")))
    add(project, group, QgsVectorLayer(f"{MESH}|layername=band_cells", "Cells around them, by faces", "ogr"), band_renderer())
    if cells is not None and iface is not None:
        iface.mapCanvas().setDestinationCrs(QgsCoordinateReferenceSystem(cells.crs()))
        iface.mapCanvas().refresh()
    project.write(str(PROJECT))
    print("project saved to", PROJECT)


main()
