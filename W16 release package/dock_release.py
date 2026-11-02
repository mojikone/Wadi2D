"""Runs inside a separate QGIS with a throwaway profile: the plugin as a release installs it, on the engine a release installs.

WADI2D_MODE: gpu, the plugin the installer copied, through QGIS's own loader; the Block 2 hybrid against the peaks on record,
then rain, a map and a mesh. zip, the plugin through QGIS's own Install from ZIP, finding the engine by the shared record.
cpu, the CPU engine on a small area.
"""
import csv
import json
import os
import sys
import time
import traceback
from pathlib import Path

import qgis.utils
from qgis.core import QgsProject, QgsRasterLayer, QgsSettings, QgsVectorLayer
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication
from qgis.utils import iface

P = Path(os.environ["WADI2D_PLUG"])
REPO = Path(os.environ["WADI2D_REPO"])
MODE = os.environ["WADI2D_MODE"]
BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
V = REPO / "W1 research and design note" / "validation" / "block2_full"
DATA = P / "data"
RUNS = P / "runs"
LOG = P / "log.txt"
PLUGIN = "wadi2d_qgis"
HYBRID_ON_RECORD = {"Bidah_03": 654.9, "Faydh_01": 898.1, "R2A": 1426.4, "R5A": 1003.4, "Z4C": 2021.0}  # W15, log_dock_options.txt
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
    iface.mainWindow().grab().save(str(P / f"{MODE}_{name}.png"))


def geojson(name, features):
    crs = {"type": "name", "properties": {"name": "EPSG:32640"}}
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


def idle(dock, limit):
    start = time.monotonic()

    def done():
        if time.monotonic() - start > limit:
            raise TimeoutError(f"no finish in {limit} s: {dock.panel.message.text()}")
        return dock.run is None and dock.panel.run_button.isEnabled()

    return done


def rain_job(dock, folder, dx, hours, sim_hours, mixed, bidah):
    h = dock.hydrology
    h.folder.setFilePath("")
    dock.terrain.dx.setValue(dx)
    dock.terrain.domain.setLayer(bidah)
    h.rain.setValue(60.0)
    h.hours.setValue(hours)
    dock.boundaries.layer.setLayer(mixed)
    dock.points.layer.setLayer(None)
    dock.panel.duration.setValue(sim_hours)
    dock.panel.folder.setFilePath(str(RUNS / folder))
    dock.panel.run_button.click()


def get_plugin():
    if MODE == "zip":
        import pyplugin_installer

        pyplugin_installer.instance().installFromZipFile(os.environ["WADI2D_ZIP"])
        check("QGIS installed the zip", PLUGIN in qgis.utils.active_plugins, qgis.utils.active_plugins)
    else:
        qgis.utils.updateAvailablePlugins()
        check("QGIS sees the plugin", PLUGIN in qgis.utils.available_plugins, qgis.utils.plugin_paths)
        check("QGIS loads it", qgis.utils.loadPlugin(PLUGIN) and qgis.utils.startPlugin(PLUGIN))
    plugin = qgis.utils.plugins[PLUGIN]
    source = Path(sys.modules[PLUGIN].__file__)
    check("the plugin is the installed copy, not the repository", str(REPO) not in str(source), source)
    check("metadata reads", qgis.utils.pluginMetadata(PLUGIN, "version") == os.environ["WADI2D_VERSION"], qgis.utils.pluginMetadata(PLUGIN, "version"))
    return plugin


def scenario():
    project = QgsProject.instance()
    DATA.mkdir(exist_ok=True)
    RUNS.mkdir(exist_ok=True)
    check("no engine setting in this profile", QgsSettings().value("wadi2d/engine", "", type=str) == "")
    jobs = json.loads((V / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    dam = json.loads((V / "jobs" / "dam_Bidah03_100yr_20.json").read_text(encoding="utf-8"))
    dem = add_raster(BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif", "terrain")
    crs = dem.crs()
    project.setCrs(crs)
    block = add_vector(V / "domain.geojson", "domain block 2", crs)
    bidah = add_vector(V / "domain_Bidah03.geojson", "domain bidah", crs)
    dams = add_vector(geojson("dams", [line(k["coordinates"], name=k["name"]) for k in jobs["outputs"]["lines"]]), "dam lines", crs)
    outlet = add_vector(geojson("outs", [line(k["coordinates"]) for k in jobs["boundaries"]]), "outlets", crs)
    mixed = add_vector(geojson("mixed", [line(k["coordinates"], kind="normal", value=0.01) for k in dam["boundaries"]]), "mixed outlets", crs)
    iface.mapCanvas().setExtent(bidah.extent())
    iface.mapCanvas().refresh()

    plugin = get_plugin()
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    current[0] = dock
    yield lambda: dock.schema is not None or "not found" in dock.engine_label.text()
    check("engine found with nothing set by hand", "ready" in dock.engine_label.text().lower(), dock.engine_label.text())
    dock.terrain.dem.setLayer(dem)

    if MODE == "gpu":
        log("=== hybrid against the record")
        dock.terrain.dx.setValue(40.0)
        dock.terrain.domain.setLayer(block)
        h = dock.hydrology
        h.folder.setFilePath(str(Path(os.environ["WADI2D_HMS"])))
        yield lambda: h.files["basin"].count() > 0
        h.files["met"].setCurrentText("FM_200yr.met")
        check("hms read by the installed engine", h.table.rowCount() == 18, h.table.rowCount())
        for row in range(h.table.rowCount()):
            h.table.cellWidget(row, 1).setCurrentText("2d" if h.table.item(row, 0).text() == "S13" else "lumped")
        dock.boundaries.layer.setLayer(outlet)
        dock.boundaries.kind.setCurrentText("normal")
        dock.boundaries.value.setValue(0.008)
        dock.points.layer.setLayer(dams)
        dock.points.name.setField("name")
        dock.panel.duration.setValue(30.0)
        dock.panel.folder.setFilePath(str(RUNS / "hybrid"))
        dock.panel.run_button.click()
        yield lambda: dock.run is not None
        yield idle(dock, 900)
        folder = RUNS / "hybrid"
        finish = events(folder, "done")
        check("hybrid finished", finish and finish[-1].get("code") == 0, dock.panel.message.text())
        check("on the GPU", "cuda" in events(folder, "start")[-1].get("backend", "").lower() or "gpu" in events(folder, "start")[-1].get("backend", "").lower(), events(folder, "start")[-1].get("backend"))
        got = peaks(folder)
        log(f"peaks {got}")
        worst = max(abs(got.get(k, 0.0) - v) for k, v in HYBRID_ON_RECORD.items())
        check("the five peaks match the record", worst <= 0.1, f"worst {worst:.2f} m3/s")
        check("no CuPy noise in engine.err", "CUDA_PATH" not in (folder / "engine.err").read_text(encoding="utf-8", errors="replace"))
        shot("hybrid")

        log("=== rain, pixel maps, Make map")
        rain_job(dock, "rain", 20.0, 2.0, 4.0, mixed, bidah)
        yield lambda: dock.run is not None
        yield idle(dock, 600)
        folder = RUNS / "rain"
        finish = events(folder, "done")
        check("rain finished", finish and finish[-1].get("code") == 0, dock.panel.message.text())
        check("pixel depth written", any((folder / "pixels").glob("*depth*.tif")), [p.name for p in (folder / "pixels").glob("*")][:8])
        names = [ly.name() for ly in project.mapLayers().values()]
        check("flood maps loaded", any("depth" in n.lower() for n in names), names[:8])
        yield lambda: dock.panel.map_button.isEnabled()
        dock.panel.map_button.click()
        yield lambda: "Map written" in dock.panel.message.text() or "not" in dock.panel.message.text().lower()
        pdf = list((folder / "pixels").glob("*_maps.pdf"))
        check("pdf written", pdf and pdf[0].stat().st_size > 100000, dock.panel.message.text())

        log("=== mesh, on WhiteboxTools from the installer")
        m = dock.mesh
        m.setCollapsed(False)
        dock.terrain.dx.setValue(10.0)
        m.enabled.setChecked(True)
        m.coarse.setValue(40.0)
        m.summary.clear()
        m.preview_button.click()
        yield lambda: m.preview_button.isEnabled() and m.summary.text() not in ("", "Reading the ground and the streams...")
        check("mesh preview", "cells," in m.summary.text(), m.summary.text())
        rain_job(dock, "mesh", 10.0, 1.0, 1.0, mixed, bidah)
        yield lambda: dock.run is not None
        yield idle(dock, 600)
        finish = events(RUNS / "mesh", "done")
        check("mesh run finished", finish and finish[-1].get("code") == 0, dock.panel.message.text())
        m.enabled.setChecked(False)
    else:
        log(f"=== small rain, {MODE}")
        rain_job(dock, "small", 40.0, 0.5, 0.5, mixed, bidah)
        yield lambda: dock.run is not None
        yield idle(dock, 900)
        folder = RUNS / "small"
        finish = events(folder, "done")
        check("run finished", finish and finish[-1].get("code") == 0, dock.panel.message.text())
        backend = events(folder, "start")[-1].get("backend", "")
        if MODE == "cpu":
            check("on the CPU", "cpu" in backend.lower() or "numba" in backend.lower(), backend)
        check("mass", abs(finish[-1]["balance"].get("relative_error", 1)) < 1e-5, finish[-1]["balance"].get("relative_error"))
        log(f"loop {finish[-1].get('loop_s')} s on {backend}")
        check("pixel maps written", any((folder / "pixels").glob("*.tif")))
    shot("finished")


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
STEP_LIMIT = 1000.0


def tick():
    global gen
    try:
        if gen is None:
            gen = scenario()
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
            text = dock_now.panel.message.text() + " | " + dock_now.mesh.summary.text()
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
    if time.monotonic() - T0 > 2400.0:
        log("TIMEOUT")
        finish("timeout")
        return
    QTimer.singleShot(250, tick)


LOG.write_text("", encoding="utf-8")
QTimer.singleShot(5000, tick)
log("script loaded")
