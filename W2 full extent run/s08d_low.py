"""The coarse satellite picture in patches: QGIS draws a limited number of tiles per image. Run with python-qgis-ltr.bat."""
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
    QgsRectangle,
)
from qgis.PyQt.QtCore import QEventLoop, QPoint, QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter

HERE = Path(__file__).resolve().parent
OUT = HERE / "terrain" / "background"
URL = "type=xyz&url=https://mt1.google.com/vt/lyrs%3Dy%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0&crs=EPSG3857"
X0, X1, Y0, Y1, MPP = 385000.0, 625000.0, 2540000.0, 2790000.0, 280.0
PATCH = 1000  # pixels

app = QgsApplication([], False)
app.initQgis()
layer = QgsRasterLayer(URL, "hybrid", "wms")
QgsProject.instance().addMapLayer(layer, False)
crs = QgsCoordinateReferenceSystem("EPSG:32640")
w, h = round((X1 - X0) / MPP), round((Y1 - Y0) / MPP)
sheet = QImage(w, h, QImage.Format_RGB32)
sheet.fill(QColor("black"))
paint = QPainter(sheet)
for row in range(0, h, PATCH):
    for col in range(0, w, PATCH):
        pw, ph = min(PATCH, w - col), min(PATCH, h - row)
        s = QgsMapSettings()
        s.setLayers([layer])
        s.setDestinationCrs(crs)
        x = X0 + col * MPP
        y = Y1 - row * MPP
        s.setExtent(QgsRectangle(x, y - ph * MPP, x + pw * MPP, y))
        s.setOutputSize(QSize(pw, ph))
        s.setOutputDpi(96)
        s.setBackgroundColor(QColor("black"))
        job = QgsMapRendererParallelJob(s)
        loop = QEventLoop()
        job.finished.connect(loop.quit)
        job.start()
        loop.exec_()
        paint.drawImage(QPoint(col, row), job.renderedImage())
    print("row", row, flush=True)
paint.end()
sheet.save(str(OUT / "low.png"), "PNG")
(OUT / "low.json").write_text(json.dumps({"x0": X0, "y0": Y0, "x1": X1, "y1": Y1, "w": w, "h": h}))
sys.stdout.flush()
os._exit(0)
