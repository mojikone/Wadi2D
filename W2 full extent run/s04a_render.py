"""Headless QGIS, its own process: terrain/depth_90m.tif through his QML, on white. Run with python-qgis-ltr.bat."""
import json
import os
import sys
from pathlib import Path

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

HERE = Path(__file__).resolve().parent
QML = sys.argv[1]
app = QgsApplication([], False)
app.initQgis()
depth = QgsRasterLayer(str(HERE / "terrain" / "depth_90m.tif"), "depth")
print("valid", depth.isValid(), depth.loadNamedStyle(QML))
QgsProject.instance().addMapLayer(depth, False)
settings = QgsMapSettings()
settings.setLayers([depth])
settings.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:32640"))
e = depth.extent()
settings.setExtent(e)
height = 2432
settings.setOutputSize(QSize(int(height * e.width() / e.height()), height))
settings.setOutputDpi(200)
settings.setBackgroundColor(QColor("white"))
job = QgsMapRendererParallelJob(settings)
job.start()
job.waitForFinished()
print("errors", [m.message for m in job.errors()])
job.renderedImage().save(str(HERE / "terrain" / "map_white_full.png"), "PNG")
v = settings.visibleExtent()
(HERE / "terrain" / "map_full_extent.json").write_text(json.dumps([v.xMinimum(), v.yMinimum(), v.xMaximum(), v.yMaximum()]))
sys.stdout.flush()
os._exit(0)
