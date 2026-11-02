"""Runs inside a separate QGIS with a throwaway profile: the real dock's Mesh section, end to end, on real runs.

Launched by run_plug.ps1. Nothing here touches another QGIS window or the default profile. The dock is created the way the
plugin creates it; every step is a widget set or a button clicked, as a user would.
"""

import csv
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication
from qgis.utils import iface

P = Path(os.environ["WADI2D_PLUG"])
REPO = Path(os.environ["WADI2D_REPO"])
VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
W1 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\ras_rain_on_grid")
DATA = P / "data"
RUNS = P / "runs"
LOG = P / "log.txt"
T0 = time.monotonic()
results = []
shots = [0]
current = [None]


def log(text):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.monotonic() - T0:7.1f} {text}\n")


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:200]))
    log(f"{'PASS' if ok else 'FAIL'} {name} {str(detail)[:260]}")


def shot(name):
    QApplication.processEvents()
    shots[0] += 1
    iface.mainWindow().grab().save(str(P / f"{shots[0]:02d}_{name}.png"))


def geojson(name, features):
    crs = {"type": "name", "properties": {"name": "EPSG:32640"}}
    path = DATA / f"{name}.geojson"
    path.write_text(
        json.dumps({"type": "FeatureCollection", "crs": crs, "features": features}), encoding="utf-8"
    )
    return path


def line(coords, **props):
    return {"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}}


def polygon(ring, **props):
    return {"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def add_vector(path, name, crs):
    layer = QgsVectorLayer(str(path), name, "ogr")
    layer.setCrs(crs)
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
            out[f.stem[5:]] = round(max(abs(float(r[1])) for r in rows), 2)
    return out


def finished(dock):
    return dock.run is None and dock.panel.run_button.isEnabled()


def scenario():
    project = QgsProject.instance()
    DATA.mkdir(exist_ok=True)
    if RUNS.exists():
        shutil.rmtree(RUNS)
    RUNS.mkdir()
    job = json.loads((W1 / "jobs" / "10m_n050_em.json").read_text(encoding="utf-8"))
    dem = QgsRasterLayer(str(W1 / "terrain" / "bidah_0p5m.tif"), "terrain")
    project.addMapLayer(dem)
    crs = dem.crs()
    project.setCrs(crs)
    domain = add_vector(W1 / "domain_wadi_10m.geojson", "domain", crs)
    outs = add_vector(geojson("outs", [line(b["coordinates"]) for b in job["boundaries"]]), "outlets", crs)
    lines = add_vector(
        geojson("lines", [line(k["coordinates"], name=k["name"]) for k in job["outputs"]["lines"]]),
        "lines",
        crs,
    )
    e = domain.extent()
    x, y = e.center().x(), e.center().y()
    ring = [
        [x - 800, y - 800],
        [x + 800, y - 800],
        [x + 800, y + 800],
        [x - 800, y + 800],
        [x - 800, y - 800],
    ]
    zones = add_vector(geojson("zones", [polygon(ring, size=10.0)]), "zones", crs)
    iface.mapCanvas().setExtent(e)
    iface.mapCanvas().refresh()

    sys.path.insert(0, str(REPO / "plugin"))
    import wadi2d_qgis
    from wadi2d_qgis import settings

    check("plugin from this branch", str(REPO) in wadi2d_qgis.__file__, wadi2d_qgis.__file__)
    settings.set_engine_text(f'"{VENV}" "{P / "engine.py"}"')
    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    current[0] = dock
    yield lambda: dock.schema is not None
    check("engine found", "ready" in dock.engine_label.text().lower(), dock.engine_label.text())
    m = dock.mesh
    check("mesh section is second", dock.sections[1] is m, m.title())
    check("mesh off by default", not m.enabled.isChecked())
    check("local steps off by default", not m.local_steps.isChecked())
    check("coarse cell from the schema", m.coarse.value() == 40.0, m.coarse.value())
    check("wadi areas from the schema", (m.fine_area.value(), m.mid_area.value()) == (10.0, 1.0))
    check("preview waits for the tick", not m.preview_button.isEnabled())

    t, h = dock.terrain, dock.hydrology
    t.dem.setLayer(dem)
    t.dx.setValue(10.0)
    t.domain.setLayer(domain)
    t.manning.box.setValue(0.05)
    h.rain.setValue(30.0)
    h.hours.setValue(2.0)
    dock.boundaries.layer.setLayer(outs)
    dock.boundaries.kind.setCurrentText("normal")
    dock.boundaries.value.setValue(0.01)
    dock.points.layer.setLayer(lines)
    dock.points.name.setField("name")
    dock.panel.duration.setValue(4.0)

    log("=== 1 the default stays the uniform grid")
    dock.panel.folder.setFilePath(str(RUNS / "uniform"))
    shot("uniform_ready")
    dock.panel.run_button.click()
    yield lambda: dock.run is not None
    yield lambda: finished(dock)
    folder = RUNS / "uniform"
    done = events(folder, "done")
    check("uniform finished", done and done[-1].get("code") == 0, dock.panel.message.text())
    written = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    check("uniform job has no mesh", "mesh" not in written and "numerics" not in written, sorted(written))
    start = events(folder, "start")[-1]
    check("uniform cell count", start["cells"] == 220006, start["cells"])
    base = peaks(folder)
    log(f"uniform peaks {base}; loop {done[-1].get('loop_s')} s")

    log("=== 2 a coarse cell off the ladder")
    m.setCollapsed(False)
    m.enabled.setChecked(True)
    check("ticking the mesh turns on local steps", m.local_steps.isChecked())
    check("preview ready after the tick", m.preview_button.isEnabled())
    m.coarse.setValue(30.0)
    dock.panel.folder.setFilePath(str(RUNS / "refused"))
    dock.panel.run_button.click()
    check("bad coarse cell refused", "coarsest cell" in dock.panel.message.text(), dock.panel.message.text())
    check("refused run did not start", dock.run is None and not (RUNS / "refused").exists())
    m.coarse.setValue(40.0)

    log("=== 3 preview")
    m.summary.clear()
    m.preview_button.click()
    yield (
        lambda: (
            "cells," in m.summary.text()
            or "exit" in m.summary.text().lower()
            or (
                m.preview_button.isEnabled()
                and m.summary.text() != "Reading the ground and the streams..."
                and m.summary.text()
            )
        )
    )
    text = m.summary.text()
    check("preview summary", "cells," in text and "fewer" in text, text)
    found = [ly for ly in project.mapLayers().values() if ly.name().startswith("Wadi2D mesh")]
    check("preview layer on the map", len(found) == 1 and found[0].isValid(), [ly.name() for ly in found])
    first_cells = int(text.split(" cells")[0].replace(",", ""))
    check("preview three sizes", found and "10 m" in text and "20 m" in text and "40 m" in text, text)
    check("preview at least 3 x fewer", first_cells * 3 <= 220006, first_cells)
    provider = found[0].dataProvider()
    stats = provider.bandStatistics(1)
    check(
        "preview raster holds cell sizes",
        (stats.minimumValue, stats.maximumValue) == (10.0, 40.0),
        (stats.minimumValue, stats.maximumValue),
    )
    iface.mapCanvas().refresh()
    shot("preview")

    log("=== 4 a zone refines, and the old preview goes")
    m.zones.setLayer(zones)
    m.zone_dx.setField("")
    m.summary.clear()
    m.preview_button.click()
    check(
        "zone without a field refused",
        "choose the field" in dock.panel.message.text(),
        dock.panel.message.text(),
    )
    m.zone_dx.setField("size")
    m.preview_button.click()
    yield lambda: "cells," in m.summary.text() or "exit" in m.summary.text().lower()
    cells = int(m.summary.text().split(" cells")[0].replace(",", ""))
    check("zone adds cells", cells > first_cells, (first_cells, cells))
    found = [ly for ly in project.mapLayers().values() if ly.name().startswith("Wadi2D mesh")]
    check("one preview layer only", len(found) == 1, len(found))
    shot("preview_zone")
    m.zones.setLayer(None)

    log("=== 5 a run on the mesh")
    dock.panel.folder.setFilePath(str(RUNS / "mesh"))
    dock.panel.estimate_button.click()
    yield lambda: dock.panel.estimate_label.text() not in ("", "Estimating...")
    check(
        "estimate says it is for the uniform grid",
        "uniform grid" in dock.panel.estimate_label.text(),
        dock.panel.estimate_label.text(),
    )
    dock.panel.run_button.click()
    yield lambda: dock.run is not None
    yield lambda: dock.panel.bar.value() >= 20 or finished(dock)
    shot("mesh_running")
    yield lambda: finished(dock)
    folder = RUNS / "mesh"
    done = events(folder, "done")
    check("mesh finished", done and done[-1].get("code") == 0, dock.panel.message.text())
    written = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    check(
        "mesh in the job",
        written["mesh"]["enabled"] and written["mesh"]["coarse_dx"] == 40.0,
        written.get("mesh"),
    )
    check(
        "local steps in the job",
        written["numerics"] == {"local_time_stepping": True},
        written.get("numerics"),
    )
    start = events(folder, "start")[-1]
    check("mesh cell count", start["cells"] == first_cells, start["cells"])
    relative = done[-1]["balance"]["relative_error"] if done else 1.0
    check("mesh mass", abs(relative) < 1e-6, relative)
    got = peaks(folder)
    log(
        f"mesh peaks {got}; uniform {base}; loop {done[-1].get('loop_s')} s; warnings {[w.get('message', '')[:100] for w in events(folder, 'warn')]}"
    )
    for name, value in base.items():
        check(
            f"mesh peak {name} within 10 %",
            abs(got.get(name, 0.0) / max(value, 1e-9) - 1.0) < 0.10,
            (got.get(name), value),
        )
    names = [ly.name() for ly in project.mapLayers().values()]
    check(
        "mesh maps loaded",
        any("depth" in n.lower() for n in names),
        [n for n in names if "depth" in n.lower()][:4],
    )
    check("results button", dock.panel.open_button.isVisible())
    with (folder / "maps").joinpath("max_depth.tif").open("rb") as f:
        check("max depth written", len(f.read(16)) == 16)
    shot("mesh_finished")

    log("=== 6 stop in mid run on the mesh")
    dock.panel.duration.setValue(30.0)
    dock.panel.folder.setFilePath(str(RUNS / "stopped"))
    dock.panel.run_button.click()
    yield lambda: dock.run is not None
    yield lambda: dock.panel.bar.value() >= 2 or finished(dock)
    dock.panel.stop_button.click()
    yield lambda: finished(dock)
    done = events(RUNS / "stopped", "done")
    check("stopped on request", done and done[-1].get("status") == "stopped", dock.panel.message.text())
    check("maps of a stopped mesh run", (RUNS / "stopped" / "maps" / "max_depth.tif").is_file())

    log("=== 7 unticking returns to the uniform grid")
    m.enabled.setChecked(False)
    m.local_steps.setChecked(False)
    dock.panel.duration.setValue(0.25)
    dock.panel.folder.setFilePath(str(RUNS / "back"))
    dock.panel.run_button.click()
    yield lambda: dock.run is not None
    yield lambda: finished(dock)
    written = json.loads((RUNS / "back" / "job.json").read_text(encoding="utf-8"))
    check("back to uniform", "mesh" not in written and events(RUNS / "back", "start")[-1]["cells"] == 220006)
    shot("end")


gen = None
waiting = [None]
step_started = [time.monotonic()]
said = [""]
STEP_LIMIT = 900.0


def finish(failed=""):
    fails = [r for r in results if not r[1]]
    log(f"SUMMARY {len(results) - len(fails)} passed, {len(fails)} failed {failed}")
    for r in fails:
        log(f"  FAILED {r[0]}: {r[2]}")
    log("DONE")
    QgsProject.instance().setDirty(False)
    QTimer.singleShot(400, iface.actionExit().trigger)


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
