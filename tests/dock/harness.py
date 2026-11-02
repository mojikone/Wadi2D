"""Drives the real dock from inside a separate QGIS with a throwaway profile. Started by run_check.ps1.

A check is a scenario file with ``def scenario(h)``, a generator: it sets widgets and clicks buttons as a user would, and
yields a function that says when to go on, so QGIS keeps running in between. ``h`` is this module. Nothing here touches
another QGIS window or the default profile.
"""

import csv
import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path

from qgis.core import (
    QgsMapRendererSequentialJob,
    QgsMapSettings,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QSize, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication
from qgis.utils import iface

P = Path(os.environ["WADI2D_PLUG"])
REPO = Path(os.environ["WADI2D_REPO"])
SCENARIO = Path(os.environ["WADI2D_SCENARIO"])
BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
VALIDATION = REPO / "W1 research and design note" / "validation" / "block2_full"
DATA = P / "data"
RUNS = P / "runs"
LOG = P / "log.txt"
VENV = REPO / ".venv" / "Scripts" / "python.exe"
STEP_LIMIT = 1000.0
TOTAL_LIMIT = 2400.0
T0 = time.monotonic()
results = []
current = [None]


def log(text):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.monotonic() - T0:7.1f} {text}\n")


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:200]))
    log(f"{'PASS' if ok else 'FAIL'} {name} {str(detail)[:260]}")


def shot(name):
    QApplication.processEvents()
    iface.mainWindow().grab().save(str(P / f"{len(results):03d}_{name}.png"))


def render(name, layers, centre, scale, size=(1000, 700), dpi=96):
    """What a user sees at this scale, drawn to the end, off the screen: a minimized window's canvas shows nothing."""
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setDestinationCrs(layers[0].crs())
    settings.setOutputSize(QSize(*size))
    settings.setOutputDpi(dpi)
    settings.setBackgroundColor(QColor("white"))
    half = (size[0] / 2.0 / dpi * 0.0254 * scale, size[1] / 2.0 / dpi * 0.0254 * scale)
    point = QgsPointXY(centre)
    settings.setExtent(QgsRectangle(point.x() - half[0], point.y() - half[1], point.x() + half[0], point.y() + half[1]))
    job = QgsMapRendererSequentialJob(settings)
    job.start()
    job.waitForFinished()
    path = P / f"render_{name}.png"
    job.renderedImage().save(str(path))
    return path


def geojson(name, features, epsg=32640):
    crs = {"type": "name", "properties": {"name": f"EPSG:{epsg}"}}
    path = DATA / f"{name}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "crs": crs, "features": features}), encoding="utf-8")
    return path


def line(coords, **props):
    return {"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}}


def add_vector(path, name, crs):
    layer = QgsVectorLayer(str(path), name, "ogr")
    layer.setCrs(crs)
    QgsProject.instance().addMapLayer(layer)
    return layer


def add_raster(path, name):
    layer = QgsRasterLayer(str(path), name)
    QgsProject.instance().addMapLayer(layer)
    return layer


def events(folder, kind):
    path = Path(folder) / "progress.jsonl"
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if f'"{kind}"' in s[:30]]


def peaks(folder):
    out = {}
    for f in sorted((Path(folder) / "series").glob("line_*.csv")):
        with f.open() as h:
            rows = list(csv.reader(h))[1:]
        if rows:
            out[f.stem[5:]] = round(max(abs(float(r[1])) for r in rows), 1)
    return out


def idle(dock, limit=900):
    start = time.monotonic()

    def done():
        if time.monotonic() - start > limit:
            raise TimeoutError(f"no finish in {limit} s: {dock.panel.message.text()}")
        return dock.run is None and dock.panel.run_button.isEnabled()

    return done


class Bidah:
    """Block 2's ground around Bidah: small, real, and fast. All of it read-only."""

    def __init__(self):
        project = QgsProject.instance()
        jobs = json.loads((VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
        dam = json.loads((VALIDATION / "jobs" / "dam_Bidah03_100yr_20.json").read_text(encoding="utf-8"))
        self.dem = add_raster(BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif", "terrain")
        self.crs = self.dem.crs()
        project.setCrs(self.crs)
        self.domain = add_vector(VALIDATION / "domain_Bidah03.geojson", "domain bidah", self.crs)
        self.outlets_data = dam["boundaries"]
        self.outlets = add_vector(geojson("outs", [line(k["coordinates"]) for k in dam["boundaries"]]), "outlets", self.crs)
        self.mixed = add_vector(
            geojson("mixed", [line(k["coordinates"], kind="normal", value=0.01) for k in dam["boundaries"]]), "mixed outlets", self.crs
        )
        self.lines = add_vector(geojson("dams", [line(k["coordinates"], name=k["name"]) for k in jobs["outputs"]["lines"]]), "dam lines", self.crs)
        iface.mapCanvas().setExtent(self.domain.extent())
        iface.mapCanvas().refresh()


def open_dock():
    """The plugin of this checkout; yields until the engine has answered. Use: ``dock = yield from h.open_dock()``."""
    sys.path.insert(0, str(REPO / "plugin"))
    import wadi2d_qgis
    from wadi2d_qgis import settings

    check("plugin from this checkout", str(REPO) in wadi2d_qgis.__file__, wadi2d_qgis.__file__)
    settings.set_engine_text(f'"{VENV}" "{P / "engine.py"}"')
    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    current[0] = dock
    yield lambda: dock.schema is not None
    check("engine found", "ready" in dock.engine_label.text().lower(), dock.engine_label.text())
    return dock


def set_rain_job(dock, ground, folder, dx=20.0, rain=60.0, hours=1.0, sim_hours=1.5, pixels=True):
    """Rain on the Bidah domain, ready to run."""
    t, h = dock.terrain, dock.hydrology
    h.folder.setFilePath("")
    t.dem.setLayer(ground.dem)
    t.dx.setValue(dx)
    t.domain.setLayer(ground.domain)
    h.rain.setValue(rain)
    h.hours.setValue(hours)
    dock.boundaries.layer.setLayer(ground.mixed)
    dock.points.layer.setLayer(None)
    dock.panel.duration.setValue(sim_hours)
    dock.panel.pixels.setChecked(pixels)
    dock.panel.folder.setFilePath(str(RUNS / folder))


def run(dock, limit=900):
    """Click Run and wait for the end. Use: ``yield from h.run(dock)``."""
    dock.panel.run_button.click()
    yield lambda: dock.run is not None
    yield idle(dock, limit)


def group_of(name):
    return QgsProject.instance().layerTreeRoot().findGroup(name)


def finish(failed=""):
    fails = [r for r in results if not r[1]]
    log(f"SUMMARY {len(results) - len(fails)} passed, {len(fails)} failed {failed}")
    for r in fails:
        log(f"  FAILED {r[0]}: {r[2]}")
    log("DONE")
    QgsProject.instance().setDirty(False)
    QTimer.singleShot(400, iface.actionExit().trigger)


gen = None
waiting = [None]
step_started = [time.monotonic()]
said = [""]


def load_scenario():
    spec = importlib.util.spec_from_file_location("dock_scenario", SCENARIO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scenario(sys.modules[__name__])


def tick():
    global gen
    try:
        if gen is None:
            gen = load_scenario()
            waiting[0] = next(gen)
        while waiting[0]():
            waiting[0] = next(gen)
            step_started[0] = time.monotonic()
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and w.isModal():
                log(f"MODAL {type(w).__name__} {w.windowTitle()}: {getattr(w, 'text', lambda: '')()}")
                w.close()
        dock_now = current[0]
        if dock_now is not None:
            text = dock_now.panel.message.text()
            if text != said[0]:
                said[0] = text
                log(f"dock says: {text[:300]}")
        if time.monotonic() - step_started[0] > STEP_LIMIT:
            log(f"STEP TIMEOUT; waiting on {waiting[0]}")
            shot("step_timeout")
            finish("step timeout")
            return
    except StopIteration:
        finish()
        return
    except Exception:
        log(traceback.format_exc())
        shot("crash")
        finish("exception")
        return
    if time.monotonic() - T0 > TOTAL_LIMIT:
        log("TIMEOUT")
        finish("timeout")
        return
    QTimer.singleShot(250, tick)


sys.modules.setdefault("dock_harness", sys.modules[__name__])
DATA.mkdir(exist_ok=True)
RUNS.mkdir(exist_ok=True)
LOG.write_text("", encoding="utf-8")
QTimer.singleShot(4000, tick)
log("script loaded")
