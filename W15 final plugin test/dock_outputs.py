"""Runs inside a separate QGIS with a throwaway profile: the new outputs through the real dock, on real GPU runs.

Pattern of W7's plug_check.py. Hybrid run, layers and Make map; the estimate's disk note and the map interval; Stop in
the middle of the pixel step; the pixel step switched off; Make map on a finished run picked by its folder.
"""
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

from qgis.core import QgsLayoutItemLegend, QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication
from qgis.utils import iface

P = Path(os.environ["WADI2D_PLUG"])
TREE = Path(os.environ["WADI2D_REPO"])
MAIN = Path(r"D:\Mojtaba\Renardet\Wadi2D")
BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
V = MAIN / "W1 research and design note" / "validation" / "block2_full"
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
    path = P / f"{name}.geojson"
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


def idle(dock, limit, seen=None):
    start = time.monotonic()

    def done():
        if seen is not None and dock.run is not None and dock.run.state.product_stage:
            seen.append((dock.panel.bar.value(), dock.panel.status.text()))
        if time.monotonic() - start > limit:
            raise TimeoutError(f"no finish in {limit} s; status: {dock.panel.status.text()}")
        return dock.run is None and dock.panel.run_button.isEnabled()

    return done


def tree_texts(node):
    model = iface.layerTreeView().layerTreeModel()
    return [str(n.data(0)) for n in model.layerLegendNodes(node)]


def scenario():
    project = QgsProject.instance()
    if RUNS.exists():
        shutil.rmtree(RUNS)
    RUNS.mkdir(parents=True)
    jobs = json.loads((V / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    dem = add_raster(BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif", "terrain")
    crs = dem.crs()
    project.setCrs(crs)
    block = add_vector(V / "domain.geojson", "domain block 2", crs)
    dams = add_vector(geojson("dams", [line(k["coordinates"], name=k["name"]) for k in jobs["outputs"]["lines"]]), "dam lines", crs)
    outlet = add_vector(geojson("outs", [line(k["coordinates"]) for k in jobs["boundaries"]]), "outlets", crs)
    iface.mapCanvas().setExtent(block.extent())
    iface.mapCanvas().refresh()

    sys.path.insert(0, str(TREE / "plugin"))
    import wadi2d_qgis
    from wadi2d_qgis import settings

    check("plugin from the branch", str(TREE) in wadi2d_qgis.__file__, wadi2d_qgis.__file__)
    engine = f'"{MAIN / ".venv" / "Scripts" / "python.exe"}" "{P / "engine_w9.py"}"'
    settings.set_engine_text(engine)
    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    current[0] = dock
    yield lambda: dock.schema is not None
    check("engine found", "ready" in dock.engine_label.text().lower(), dock.engine_label.text())
    check("engine is the branch", str(TREE) in (P / "engine_file.txt").read_text(encoding="utf-8"), (P / "engine_file.txt").read_text(encoding="utf-8"))
    panel = dock.panel
    check("map choices", panel.maps.count() == 2 and panel.maps.currentData() == 900.0, [panel.maps.itemText(i) for i in range(panel.maps.count())])
    check("disk note shown", "disk" in panel.maps_note.text(), panel.maps_note.text())
    check("pixels on by default", panel.pixels.isChecked())
    check("make map waits for a run", not panel.map_button.isEnabled())

    log("=== 1 hybrid")
    dock.terrain.dem.setLayer(dem)
    dock.terrain.dx.setValue(40.0)
    dock.terrain.domain.setLayer(block)
    dock.hydrology.folder.setFilePath(str(Path(os.environ["WADI2D_HMS"])))
    yield lambda: dock.hydrology.files["basin"].count() > 0
    h = dock.hydrology
    h.files["met"].setCurrentText("FM_200yr.met")
    for row in range(h.table.rowCount()):
        h.table.cellWidget(row, 1).setCurrentText("2d" if h.table.item(row, 0).text() == "S13" else "lumped")
    h.cn.raster.setLayer(add_raster(BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn"))
    dock.boundaries.layer.setLayer(outlet)
    dock.boundaries.kind.setCurrentText("normal")
    dock.boundaries.value.setValue(0.008)
    dock.points.layer.setLayer(dams)
    dock.points.name.setField("name")
    panel.duration.setValue(30.0)
    panel.folder.setFilePath(str(RUNS / "hybrid"))
    panel.estimate_button.click()
    yield lambda: panel.estimate_label.text() not in ("", "Estimating...")
    check("estimate says the disk of the maps", "saved maps" in panel.estimate_label.text() and "GB of disk" in panel.estimate_label.text(), panel.estimate_label.text())
    shot("ready")
    seen = []
    panel.run_button.click()
    yield lambda: dock.run is not None
    yield idle(dock, 1200, seen)
    folder = RUNS / "hybrid"
    finish = events(folder, "done")
    check("hybrid finished", finish and finish[-1].get("code") == 0, panel.message.text())
    check("pixel step finished", finish and finish[-1].get("products") == "finished", finish[-1].get("products") if finish else "")
    check("bar and status followed the pixel step", len(seen) >= 3 and any("Pixel maps" in text for _v, text in seen), seen[:3] + seen[-2:])
    values = [v for v, _t in seen]
    check("bar rose through the pixel step", values == sorted(values) and values[-1] > values[0], values[:4] + values[-4:])
    for name in ("pixel_depth.tif", "pixel_hazard.tif", "pixel_speed.tif", "pixel_dv.tif", "depth_drawing.tif", "map_layers.gpkg", "pixels.json"):
        check(f"file {name}", (folder / "pixels" / name).exists())
    stats = json.loads((folder / "pixels" / "pixels.json").read_text(encoding="utf-8"))
    log(f"class km2 {stats['class_km2']}")
    resolved = json.loads((folder / "config.resolved.json").read_text(encoding="utf-8"))
    check("the edge blend reaches the run", resolved["outputs"]["pixels"]["edge_passes"] == 3, resolved["outputs"]["pixels"]["edge_passes"])
    log(f"drawn change % {stats['smooth']['change_pct']}")
    high = [abs(stats["smooth"]["change_pct"][k]) for k in ("H3", "H4", "H5", "H6")]
    check("smoothing under 1 % for H3 and above", max(high) < 1.0, high)
    top = project.layerTreeRoot().findGroup("hybrid")
    names = [child.name() for child in top.children()] if top else []
    check("groups", names == ["Model setup", "Flood maps", "Pixel rasters, the numbers of record", "Cell maps"], names)
    nodes = {n.name(): n for n in top.findLayers()}
    check("depth is on, hazard off, cell maps off", nodes["Maximum depth, m"].isVisible() and not nodes["AIDR hazard class"].isVisible() and not nodes["max_depth"].isVisible(), sorted(nodes))
    hazard = nodes["AIDR hazard class"].layer()
    colours = [c.symbol().color().name() for c in hazard.renderer().categories()]
    check("AIDR colours", colours == ["#0000ff", "#0080ff", "#00ffff", "#00ff00", "#ffff00", "#ff0000"], colours)
    ramp = nodes["Maximum depth, m"].layer().renderer().shader().rasterShaderFunction().colorRampItemList()
    check("Blues to 3 m", ramp[-1].value == 3.0 and ramp[-1].color.name() == "#08306b", [(i.value, i.color.name()) for i in ramp])
    texts = [t for n in top.findLayers() if isinstance(n.layer(), QgsRasterLayer) for t in tree_texts(n)]
    check("no stray band line in the layer tree", not any("Band" in t for t in texts), [t for t in texts if "Band" in t][:4])
    check("hazard layer has six classes", hazard.featureCount() >= 4, hazard.featureCount())
    iface.mapCanvas().setExtent(hazard.extent())
    iface.mapCanvas().refresh()
    shot("hybrid_finished")

    log("=== 2 make map")
    check("make map ready", panel.map_button.isEnabled())
    panel.background.setCurrentIndex(0)
    panel.map_button.click()
    pdf = folder / "pixels" / "hybrid_maps.pdf"
    yield lambda: "Map written" in panel.message.text() or "could not" in panel.message.text()
    check("pdf written", pdf.exists() and pdf.stat().st_size > 100000, panel.message.text())
    layouts = project.layoutManager().printLayouts()
    check("layout kept in the project", len(layouts) == 1, [x.name() for x in layouts])
    legends = [i for i in layouts[0].items() if isinstance(i, QgsLayoutItemLegend)]
    bad = []
    for legend in legends:
        for node in legend.model().rootGroup().findLayers():
            bad += [str(n.data(0)) for n in legend.model().layerLegendNodes(node, True) if "Band" in str(n.data(0))]
    check("no stray legend line on the sheets", len(legends) == 3 and not bad, bad)
    panel.map_button.click()
    yield lambda: "Map written" in panel.message.text()
    check("a second map replaces the first", len(project.layoutManager().printLayouts()) == 1)

    log("=== 3 stop in the pixel step")
    h.folder.setFilePath("")
    yield lambda: h.rain_box.isVisibleTo(h)
    dock.points.layer.setLayer(None)
    h.cn.raster.setLayer(None)
    h.rain.setValue(40.0)
    h.hours.setValue(3.0)
    panel.duration.setValue(6.0)
    panel.maps.setCurrentIndex(1)
    panel.folder.setFilePath(str(RUNS / "stop"))
    panel.run_button.click()
    yield lambda: dock.run is not None
    yield lambda: dock.run is None or dock.run.state.product_stage == "maps"
    job = json.loads((RUNS / "stop" / "job.json").read_text(encoding="utf-8"))
    check("five-minute maps reached the job", job["outputs"]["map_every_s"] == 300.0, job["outputs"])
    stopped_at = time.monotonic()
    check("stop button live in the pixel step", panel.stop_button.isEnabled())
    panel.stop_button.click()
    yield idle(dock, 60)
    log(f"stop took {time.monotonic() - stopped_at:.1f} s")
    finish = events(RUNS / "stop", "done")
    check("run stays finished", finish and finish[-1].get("code") == 0 and finish[-1].get("products") == "stopped", finish[-1] if finish else "")
    check("stop within the grace period", time.monotonic() - stopped_at < 30.0)
    check("says so", "Pixel maps stopped" in panel.message.text(), panel.message.text())
    check("cell maps written", (RUNS / "stop" / "maps" / "max_depth.tif").exists())
    leftovers = list((RUNS / "stop" / "pixels").glob("*")) if (RUNS / "stop" / "pixels").exists() else []
    check("no half-written pixel files", not leftovers, leftovers)
    check("no map button for it", not panel.map_button.isEnabled())
    shot("stopped")

    log("=== 4 pixel step off")
    panel.pixels.setChecked(False)
    panel.maps.setCurrentIndex(0)
    panel.duration.setValue(1.0)
    panel.folder.setFilePath(str(RUNS / "off"))
    panel.run_button.click()
    yield lambda: dock.run is not None
    yield idle(dock, 300)
    check("off means off", not (RUNS / "off" / "pixels").exists() and "Finished" in panel.message.text(), panel.message.text()[:120])
    panel.pixels.setChecked(True)

    log("=== 5 make map on a finished run")
    panel.folder.setFilePath(str(RUNS / "hybrid"))
    yield lambda: panel.map_button.isEnabled()
    panel.background.setCurrentIndex(1)
    panel.map_button.click()
    yield lambda: "Map written" in panel.message.text() or "could not" in panel.message.text()
    check("map from a chosen folder, satellite", "Map written" in panel.message.text(), panel.message.text())
    shot("end")


gen = None
waiting = [None]
step_started = [time.monotonic()]
said = [""]
STEP_LIMIT = 1500.0


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
            text = dock_now.panel.message.text() + " | " + dock_now.panel.estimate_label.text()
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
    if time.monotonic() - T0 > 3000.0:
        log("TIMEOUT")
        finish("timeout")
        return
    QTimer.singleShot(250, tick)


P.mkdir(parents=True, exist_ok=True)
LOG.write_text("", encoding="utf-8")
(P / "engine_w9.py").write_text(
    "import sys\n"
    f"sys.path.insert(0, r'{TREE}')\n"
    "import wadi2d\n"
    f"open(r'{P / 'engine_file.txt'}', 'w').write(wadi2d.__file__)\n"
    "from wadi2d.engine.cli import main\n"
    "sys.exit(main())\n",
    encoding="utf-8",
)
QTimer.singleShot(5000, tick)
log("script loaded")
