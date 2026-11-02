"""Headless QGIS, its own process: one raster through a QML, on white, at one screen pixel per cell. Args: tif qml png [opacity]."""
import json
import os
import sys

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsProject,
    QgsRasterLayer,
)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor

tif, qml, png = sys.argv[1:4]
app = QgsApplication([], False)
app.initQgis()
layer = QgsRasterLayer(tif, "layer")
print("valid", layer.isValid(), layer.loadNamedStyle(qml))
if len(sys.argv) > 4:
    layer.renderer().setOpacity(float(sys.argv[4]))
QgsProject.instance().addMapLayer(layer, False)
settings = QgsMapSettings()
settings.setLayers([layer])
settings.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:32640"))
e = layer.extent()
settings.setExtent(e)
settings.setOutputSize(QSize(layer.width(), layer.height()))
settings.setOutputDpi(96)
settings.setBackgroundColor(QColor("white"))
job = QgsMapRendererParallelJob(settings)
job.start()
job.waitForFinished()
print("errors", [m.message for m in job.errors()])
print("saved", job.renderedImage().save(png, "PNG"))
v = settings.visibleExtent()
with open(png + ".json", "w") as f:
    json.dump([v.xMinimum(), v.yMinimum(), v.xMaximum(), v.yMaximum()], f)
sys.stdout.flush()
os._exit(0)
