"""Satellite hybrid backgrounds for the film, drawn by QGIS in its own process. One coarse picture of the whole view, one fine
window round each zoom target, both in UTM 40N, so the film can sample them directly. Run with python-qgis-ltr.bat."""
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
from qgis.PyQt.QtCore import QEventLoop, QSize
from qgis.PyQt.QtGui import QColor

HERE = Path(__file__).resolve().parent
OUT = HERE / "terrain" / "background"
OUT.mkdir(exist_ok=True)
URL = "type=xyz&url=https://mt1.google.com/vt/lyrs%3Dy%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0&crs=EPSG3857"
BASE = {"name": "base", "x0": 385000.0, "x1": 625000.0, "y0": 2540000.0, "y1": 2790000.0, "mpp": 35.0}
FINE_W, FINE_H, FINE_MPP = 22000.0, 13000.0, 5.0

app = QgsApplication([], False)
app.initQgis()
layer = QgsRasterLayer(URL, "hybrid", "wms")
print("layer valid", layer.isValid(), layer.error().summary()[:200], flush=True)
QgsProject.instance().addMapLayer(layer, False)


def draw(job: dict) -> None:
    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:32640"))
    settings.setExtent(QgsRectangle(job["x0"], job["y0"], job["x1"], job["y1"]))
    w = round((job["x1"] - job["x0"]) / job["mpp"])
    h = round((job["y1"] - job["y0"]) / job["mpp"])
    settings.setOutputSize(QSize(w, h))
    settings.setOutputDpi(96)
    settings.setBackgroundColor(QColor("black"))
    settings.setFlag(QgsMapSettings.RenderPartialOutput, False)
    render = QgsMapRendererParallelJob(settings)
    loop = QEventLoop()
    render.finished.connect(loop.quit)
    render.start()
    loop.exec_()
    print(job["name"], w, h, "errors", [m.message[:120] for m in render.errors()][:3], flush=True)
    render.renderedImage().save(str(OUT / f"{job['name']}.png"), "PNG")
    v = settings.visibleExtent()
    (OUT / f"{job['name']}.json").write_text(json.dumps({"x0": v.xMinimum(), "y0": v.yMinimum(), "x1": v.xMaximum(), "y1": v.yMaximum(), "w": w, "h": h}))


if len(sys.argv) > 1 and sys.argv[1] == "test":
    x, y = 500600.0, 2645790.0
    draw({"name": "test", "x0": x - 2000.0, "x1": x + 2000.0, "y0": y - 1200.0, "y1": y + 1200.0, "mpp": 5.0})
elif len(sys.argv) > 1 and sys.argv[1] == "base":
    draw(BASE)
else:
    draw(BASE)
    for n, spot in enumerate(json.loads((HERE / "video_hotspots.json").read_text())):
        x, y = spot["x"], spot["y"]
        draw({"name": f"fine{n}", "x0": x - FINE_W / 2, "x1": x + FINE_W / 2, "y0": y - FINE_H / 2, "y1": y + FINE_H / 2, "mpp": FINE_MPP})
sys.stdout.flush()
os._exit(0)
