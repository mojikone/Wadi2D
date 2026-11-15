"""Prints the layer tree of a QGIS project and whether each layer is valid: the check of Block2_four_ways.qgz.

Run with QGIS's own Python: ``python-qgis-ltr.bat s07_tree.py <project.qgz>``."""

import sys

from qgis.core import QgsApplication, QgsLayerTreeGroup, QgsProject

app = QgsApplication([], False)
app.initQgis()
project = QgsProject.instance()
assert project.read(sys.argv[1]), sys.argv[1]
bad = []


def walk(node, depth=0):
    for child in node.children():
        if isinstance(child, QgsLayerTreeGroup):
            print("  " * depth + f"[{'x' if child.isVisible() else ' '}] {child.name()}")
            walk(child, depth + 1)
        else:
            layer = child.layer()
            ok = layer is not None and layer.isValid()
            if not ok:
                bad.append(child.name())
            print("  " * depth + f" - {child.name()}" + ("" if ok else "   <INVALID>"))


walk(project.layerTreeRoot())
print("layers", len(project.mapLayers()), "invalid", len(bad), bad)
app.exitQgis()
