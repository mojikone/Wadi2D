"""Runs inside a separate QGIS with a throwaway profile: a mesh run through the real dock, its pixel maps and Make map.

Launched by run_plug.ps1 with this file's name. The ground is the Bidah terrain thinned to 2 m in the throwaway folder, so
the pixel step stays small on a GPU that is shared. Every step is a widget set or a button clicked, as a user would.
"""

import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

from osgeo import gdal
from qgis.core import QgsLayoutItemLegend, QgsProject, QgsRasterLayer, QgsVectorLayer
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
PIXEL = 2.0
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


def add_vector(path, name, crs):
    layer = QgsVectorLayer(str(path), name, "ogr")
    layer.setCrs(crs)
    QgsProject.instance().addMapLayer(layer)
    return layer


def events(folder, kind):
    path = Path(folder) / "progress.jsonl"
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if f'"{kind}"' in s[:30]]


def idle(dock, limit):
    start = time.monotonic()

    def done():
        if time.monotonic() - start > limit:
            raise TimeoutError(f"no finish in {limit} s; status: {dock.panel.status.text()}")
        return dock.run is None and dock.panel.run_button.isEnabled()

    return done


def thin_ground(extent) -> Path:
    """The terrain at 2 m over the domain and a margin."""
    path = DATA / "bidah_2m.tif"
    window = [extent.xMinimum() - 100, extent.yMaximum() + 100, extent.xMaximum() + 100, extent.yMinimum() - 100]
    done = gdal.Translate(
        str(path), str(W1 / "terrain" / "bidah_0p5m.tif"), projWin=window, xRes=PIXEL, yRes=PIXEL,
        resampleAlg="average", creationOptions=["COMPRESS=DEFLATE", "TILED=YES"],
    )  # fmt: skip
    done.FlushCache()
    del done
    return path


def scenario():
    project = QgsProject.instance()
    DATA.mkdir(exist_ok=True)
    if RUNS.exists():
        shutil.rmtree(RUNS)
    RUNS.mkdir()
    job = json.loads((W1 / "jobs" / "10m_n050_em.json").read_text(encoding="utf-8"))
    domain = QgsVectorLayer(str(W1 / "domain_wadi_10m.geojson"), "domain", "ogr")
    dem = QgsRasterLayer(str(thin_ground(domain.extent())), "terrain")
    check("thinned ground", dem.isValid() and abs(dem.rasterUnitsPerPixelX() - PIXEL) < 1e-6, dem.rasterUnitsPerPixelX())
    project.addMapLayer(dem)
    crs = dem.crs()
    project.setCrs(crs)
    domain.setCrs(crs)
    project.addMapLayer(domain)
    outs = add_vector(geojson("outs", [line(b["coordinates"]) for b in job["boundaries"]]), "outlets", crs)
    lines = add_vector(
        geojson("lines", [line(k["coordinates"], name=k["name"]) for k in job["outputs"]["lines"]]), "lines", crs
    )
    iface.mapCanvas().setExtent(domain.extent())
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
    m, panel = dock.mesh, dock.panel
    t, h = dock.terrain, dock.hydrology

    log("=== 1 what the mesh section says")
    m.setCollapsed(False)
    note = m.speed_note.text()
    check("local stepping: no time on a uniform grid", "saves no time on a uniform grid" in note, note)
    check("local stepping: helps on a large mesh", "helps on a large mesh" in note, note)
    check("mesh: time above 1 M cells, memory below", "above about 1 M cells" in note and "only memory" in note, note)
    check("the tooltips say the same", "no time" in m.local_steps.toolTip() and "1 M cells" in m.enabled.toolTip())
    shot("mesh_section")

    log("=== 2 a mesh run with its pixel maps")
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
    panel.duration.setValue(4.0)
    m.enabled.setChecked(True)
    m.coarse.setValue(40.0)
    check("pixels on by default", panel.pixels.isChecked())
    check("make map waits for a run", not panel.map_button.isEnabled())
    panel.folder.setFilePath(str(RUNS / "mesh"))
    panel.estimate_button.click()
    yield lambda: panel.estimate_label.text() not in ("", "Estimating...")
    estimate = panel.estimate_label.text()
    check("the estimate says its time is rough", "rough" in estimate, estimate)
    check("the estimate counts the mesh", int(estimate.split(" cells")[0].replace(",", "")) < 200000, estimate)
    panel.run_button.click()
    yield lambda: dock.run is not None
    yield idle(dock, 1200)
    folder = RUNS / "mesh"
    done = events(folder, "done")
    check("mesh finished", done and done[-1].get("code") == 0, panel.message.text())
    check("pixel step finished", done and done[-1].get("products") == "finished", done[-1].get("products") if done else "")
    start = events(folder, "start")[-1]
    check("cells of the estimate", f"{start['cells']:,} cells" in estimate, (start["cells"], estimate))
    for name in ("pixel_depth.tif", "pixel_hazard.tif", "pixel_speed.tif", "pixel_dv.tif", "depth_drawing.tif", "map_layers.gpkg", "pixels.json"):
        check(f"file {name}", (folder / "pixels" / name).exists())
    stats = json.loads((folder / "pixels" / "pixels.json").read_text(encoding="utf-8"))
    log(f"class km2 {stats['class_km2']}; cell sizes {stats.get('cell_sizes_m')}")
    check("three cell sizes in the step", stats.get("cell_sizes_m") == [10.0, 20.0, 40.0], stats.get("cell_sizes_m"))
    check("flood classes", sum(stats["class_km2"].values()) > 0.05, stats["class_km2"])
    top = project.layerTreeRoot().findGroup("mesh")
    names = [child.name() for child in top.children()] if top else []
    check("groups", names == ["Model setup", "Flood maps", "Pixel rasters, the numbers of record", "Cell maps"], names)
    nodes = {n.name(): n for n in top.findLayers()} if top else {}
    check("depth map on", "Maximum depth, m" in nodes and nodes["Maximum depth, m"].isVisible(), sorted(nodes))
    hazard = nodes["AIDR hazard class"].layer() if "AIDR hazard class" in nodes else None
    check("hazard polygons", hazard is not None and hazard.featureCount() >= 3, hazard.featureCount() if hazard else None)
    if hazard is not None:
        iface.mapCanvas().setExtent(hazard.extent())
        iface.mapCanvas().refresh()
    shot("mesh_pixels")

    log("=== 3 make map on the mesh run")
    check("make map ready", panel.map_button.isEnabled())
    panel.background.setCurrentIndex(0)
    panel.map_button.click()
    pdf = folder / "pixels" / "mesh_maps.pdf"
    yield lambda: "Map written" in panel.message.text() or "could not" in panel.message.text()
    check("pdf written", pdf.exists() and pdf.stat().st_size > 100000, panel.message.text())
    layouts = project.layoutManager().printLayouts()
    check("layout kept in the project", len(layouts) == 1, [x.name() for x in layouts])
    legends = [i for i in layouts[0].items() if isinstance(i, QgsLayoutItemLegend)] if layouts else []
    check("three legends", len(legends) == 3, len(legends))
    shot("mesh_map")

    log("=== 4 stop inside the pixel step of a mesh run")
    dock.points.layer.setLayer(None)
    panel.duration.setValue(4.0)
    panel.maps.setCurrentIndex(1)
    panel.folder.setFilePath(str(RUNS / "stop"))
    panel.run_button.click()
    yield lambda: dock.run is not None
    yield lambda: dock.run is None or dock.run.state.product_stage == "maps"
    stopped_at = time.monotonic()
    check("stop button live in the pixel step", panel.stop_button.isEnabled())
    panel.stop_button.click()
    yield idle(dock, 120)
    log(f"stop took {time.monotonic() - stopped_at:.1f} s")
    done = events(RUNS / "stop", "done")
    check(
        "run stays finished",
        done and done[-1].get("code") == 0 and done[-1].get("products") == "stopped",
        done[-1] if done else "",
    )
    check("cell maps written", (RUNS / "stop" / "maps" / "max_depth.tif").exists())
    leftovers = list((RUNS / "stop" / "pixels").glob("*")) if (RUNS / "stop" / "pixels").exists() else []
    check("no half-written pixel files", not leftovers, leftovers)
    panel.maps.setCurrentIndex(0)

    log("=== 5 the same ground uniform, to set the two sets of pixels side by side")
    dock.points.layer.setLayer(lines)
    dock.points.name.setField("name")
    m.enabled.setChecked(False)
    m.local_steps.setChecked(False)
    panel.folder.setFilePath(str(RUNS / "uniform"))
    panel.run_button.click()
    yield lambda: dock.run is not None
    yield idle(dock, 1200)
    other = RUNS / "uniform"
    done = events(other, "done")
    check("uniform finished", done and done[-1].get("code") == 0, panel.message.text())
    plain = json.loads((other / "pixels" / "pixels.json").read_text(encoding="utf-8"))
    wet, wet_plain = sum(stats["class_km2"].values()), sum(plain["class_km2"].values())
    log(f"uniform class km2 {plain['class_km2']}")
    check("wet area within 10 % of the uniform run", abs(wet / wet_plain - 1.0) < 0.10, (wet, wet_plain))

    log("=== 6 make map again on the finished mesh run, from its folder")
    panel.folder.setFilePath(str(folder))
    yield lambda: panel.map_button.isEnabled()
    panel.map_button.click()
    yield lambda: "Map written" in panel.message.text() or "could not" in panel.message.text()
    check("map from a chosen folder", "Map written" in panel.message.text(), panel.message.text())
    shot("end")


gen = None
waiting = [None]
step_started = [time.monotonic()]
said = [""]
STEP_LIMIT = 1300.0


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
        if dock_now is not None and dock_now.panel.message.text() != said[0]:
            said[0] = dock_now.panel.message.text()
            log(f"dock says: {said[0][:300]}")
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
    if time.monotonic() - T0 > 2700.0:
        log("TIMEOUT")
        finish("timeout")
        return
    QTimer.singleShot(250, tick)


LOG.write_text("", encoding="utf-8")
QTimer.singleShot(5000, tick)
log("script loaded")
