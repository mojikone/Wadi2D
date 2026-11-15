"""Time a time-slider file in QGIS, headless: load it as a mesh layer, style it as the plugin does, render one frame of
the whole domain and then a 3 km window with QgsMapRendererParallelJob, and a second frame (a frame change).

Usage (QGIS's Python): s15_slider_render_test.py <file.nc> [<file.nc> ...]. Prints one JSON line per file and writes
a PNG of the domain frame beside this folder's runs/ as <file>.render.png.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "plugin"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsDateTimeRange,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsMeshLayer,
    QgsRectangle,
)
from qgis.PyQt.QtCore import QSize  # noqa: E402

app = QgsApplication([], False)
app.initQgis()

from wadi2d_qgis import style  # noqa: E402

CRS = QgsCoordinateReferenceSystem("EPSG:32640")
WINDOW = QgsRectangle(436000.0, 2716000.0, 439000.0, 2719000.0)
"""3 km round the R2A dam and the wadi below it."""


def render(layer, extent, when) -> tuple[float, object]:
    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setDestinationCrs(CRS)
    settings.setOutputSize(QSize(1600, 1000))
    settings.setExtent(extent)
    settings.setIsTemporal(True)
    settings.setTemporalRange(when)
    job = QgsMapRendererParallelJob(settings)
    t0 = time.perf_counter()
    job.start()
    job.waitForFinished()
    return time.perf_counter() - t0, job.renderedImage()


def main() -> None:
    for name in sys.argv[1:]:
        path = Path(name)
        t0 = time.perf_counter()
        layer = QgsMeshLayer(str(path), path.name, "mdal")
        assert layer.isValid(), path
        load = time.perf_counter() - t0
        style.style_frames(layer)
        layer.updateTriangularMesh()
        span = layer.temporalProperties().timeExtent()
        start = span.begin()
        frame = QgsDateTimeRange(start.addSecs(12 * 3600), start.addSecs(12 * 3600 + 60))
        other = QgsDateTimeRange(start.addSecs(14 * 3600), start.addSecs(14 * 3600 + 60))
        whole, image = render(layer, layer.extent(), frame)
        image.save(str(path.with_suffix(".render.png")))
        window, _ = render(layer, WINDOW, frame)
        change, _ = render(layer, layer.extent(), other)
        faces = layer.meshFaceCount() if hasattr(layer, "meshFaceCount") else None
        print(json.dumps({"file": str(path), "mb": round(path.stat().st_size / 1e6, 1), "faces": faces,
                          "load_s": round(load, 2), "domain_frame_s": round(whole, 2), "window_frame_s": round(window, 2),
                          "frame_change_s": round(change, 2)}), flush=True)
    os._exit(0)


main()
