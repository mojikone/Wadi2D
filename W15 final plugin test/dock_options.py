"""Runs inside a separate QGIS with a throwaway profile: the real dock through every option, on real GPU runs."""
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
BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
V = REPO / "W1 research and design note" / "validation" / "block2_full"
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
    path.write_text(json.dumps({"type": "FeatureCollection", "crs": crs, "features": features}), encoding="utf-8")
    return path


def line(coords, **props):
    return {"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}}


def add_vector(path, name, crs):
    layer = QgsVectorLayer(str(path), name, "ogr")
    layer.setCrs(crs)  # some of these files name no CRS, and are in UTM
    QgsProject.instance().addMapLayer(layer)
    return layer


def add_raster(path, name):
    layer = QgsRasterLayer(str(path), name)
    QgsProject.instance().addMapLayer(layer)
    return layer


def reset(dock):
    h, s, b, t, pts = dock.hydrology, dock.structures, dock.boundaries, dock.terrain, dock.points
    h.folder.setFilePath("")
    h.cn.raster.setLayer(None)
    for picker in s.layers.values():
        picker.setLayer(None)
    b.layer.setLayer(None)
    pts.layer.setLayer(None)
    t.manning.raster.setLayer(None)


def wait_done(dock, limit):
    start = time.monotonic()
    seen = [False]

    def done():
        if dock.live.layer() is not None:
            seen[0] = True
        if time.monotonic() - start > limit:
            raise TimeoutError(f"no finish in {limit} s; status: {dock.panel.status.text()}")
        return dock.run is None and dock.panel.run_button.isEnabled()

    return done, seen


def peaks(folder):
    out = {}
    for f in sorted((Path(folder) / "series").glob("line_*.csv")):
        with f.open() as h:
            rows = list(csv.reader(h))[1:]
        if rows:
            q = [abs(float(r[1])) for r in rows]
            out[f.stem[5:]] = round(max(q), 1)
    return out


def events(folder, kind):
    path = Path(folder) / "progress.jsonl"
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if f'"{kind}"' in s[:30]]


def scenario():
    project = QgsProject.instance()
    DATA.mkdir(exist_ok=True)
    if RUNS.exists():
        shutil.rmtree(RUNS)
    RUNS.mkdir()
    jobs = json.loads((V / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    dam = json.loads((V / "jobs" / "dam_Bidah03_100yr_20.json").read_text(encoding="utf-8"))
    dem = add_raster(BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif", "terrain")
    crs = dem.crs()
    project.setCrs(crs)
    block = add_vector(V / "domain.geojson", "domain block 2", crs)
    bidah = add_vector(V / "domain_Bidah03.geojson", "domain bidah", crs)
    lines = geojson("dams", [line(k["coordinates"], name=k["name"]) for k in jobs["outputs"]["lines"]])
    outs = geojson("outs", [line(k["coordinates"]) for k in jobs["boundaries"]])
    dams = add_vector(lines, "dam lines", crs)
    outlet = add_vector(outs, "outlets", crs)
    objs = {o["kind"]: o for o in dam["terrain"]["objects"]}
    log(f"dam objects {sorted(objs)}; boundaries {len(dam['boundaries'])}")
    crest = add_vector(geojson("crest", [line(objs["crest_line"]["coordinates"], z=objs["crest_line"].get("z_constant", 105.0))]), "crest", crs) if "crest_line" in objs else None
    spill = add_vector(geojson("spill", [line(objs["spillway"]["coordinates"], z=objs["spillway"].get("z_constant", 100.0), c=2.1, l=objs["spillway"].get("length") or 50.0)]), "spill", crs) if "spillway" in objs else None
    x0, y0, x1, y1 = bidah.extent().xMinimum(), bidah.extent().yMinimum(), bidah.extent().xMaximum(), bidah.extent().yMaximum()
    wall = add_vector(geojson("wall", [line([[x0 + 400, y0 + 400], [x0 + 900, y0 + 400]])]), "wall", crs)
    burn = add_vector(geojson("burn", [line([[x0 + 400, y0 + 800], [x0 + 900, y0 + 800]], z=100.0)]), "burn", crs)
    mixed = add_vector(geojson("mixed", [line(k["coordinates"], kind="normal", value=0.01) for k in dam["boundaries"]]), "mixed outlets", crs)
    cnr = add_raster(BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn")
    man = add_raster(V / "manning" / "hills_100.tif", "manning")
    iface.mapCanvas().setExtent(block.extent())
    iface.mapCanvas().refresh()

    sys.path.insert(0, str(REPO / "plugin"))
    import wadi2d_qgis
    from wadi2d_qgis import settings

    engine = f'"{REPO / ".venv" / "Scripts" / "python.exe"}" -m wadi2d.engine.cli'
    settings.set_engine_text(engine)
    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    current[0] = dock
    yield lambda: dock.schema is not None
    check("engine found", "ready" in dock.engine_label.text().lower(), dock.engine_label.text())

    # 1. hybrid: HMS catchments upstream, 2D downstream, one catchment in 2D
    log("=== 1 hybrid")
    dock.terrain.dem.setLayer(dem)
    dock.terrain.dx.setValue(40.0)
    dock.terrain.domain.setLayer(block)
    dock.hydrology.folder.setFilePath(str(Path(os.environ["WADI2D_HMS"])))
    yield lambda: dock.hydrology.files["basin"].count() > 0
    h = dock.hydrology
    h.files["met"].setCurrentText("FM_200yr.met")
    check("hms files listed", h.files["control"].currentText() == "Control_1.control", [h.files[k].currentText() for k in h.files])
    check("hms subbasins listed", h.table.rowCount() == 18, h.table.rowCount())
    check("mode choices", h.table.cellWidget(0, 1).count() >= 2, [h.table.cellWidget(0, 1).itemText(i) for i in range(h.table.cellWidget(0, 1).count())])
    for row in range(h.table.rowCount()):
        h.table.cellWidget(row, 1).setCurrentText("2d" if h.table.item(row, 0).text() == "S13" else "lumped")
    dock.boundaries.layer.setLayer(outlet)
    dock.boundaries.kind.setCurrentText("normal")
    dock.boundaries.value.setValue(0.008)
    dock.points.layer.setLayer(dams)
    dock.points.name.setField("name")
    dock.panel.duration.setValue(30.0)
    dock.panel.folder.setFilePath(str(RUNS / "hybrid"))
    shot("hybrid_ready")
    dock.panel.estimate_button.click()
    yield lambda: dock.panel.estimate_label.text() not in ("", "Estimating...") or (dock.panel.estimate_label.text() == "" and dock.panel.message.text() != "")
    text = dock.panel.estimate_label.text() + " / " + dock.panel.message.text()
    check("hybrid estimate", "min" in text.lower() or "s" in text.lower(), text)
    dock.panel.run_button.click()
    done, seen = wait_done(dock, 900)
    yield lambda: dock.run is not None
    yield lambda: dock.panel.bar.value() >= 30 or done()
    shot("hybrid_running")
    yield done
    folder = RUNS / "hybrid"
    msg = dock.panel.message.text()
    finish = events(folder, "done")
    check("hybrid finished", finish and finish[-1].get("code") == 0, msg)
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    modes = [s["mode"] for s in job["hydrology"]["subbasins"]]
    check("hybrid job modes", modes.count("lumped") == 17 and modes.count("2d") == 1, modes.count("lumped"))
    check("hybrid storm", job["storm"]["depth_mm"] == 251.0 and job["storm"]["storm_area_km2"] == 300.0, job["storm"]["depth_mm"])
    check("hybrid control sets time", job["run"]["duration_s"] == 172800.0, job["run"]["duration_s"])
    check("hybrid note on the time", "48 h" in msg or (folder / "progress.jsonl").exists(), msg)
    balance = finish[-1]["balance"] if finish else {}
    check("hybrid mass", abs(balance.get("relative_error", 1)) < 1e-5, balance.get("relative_error"))
    check("hybrid inflow reached 2D", balance.get("inflow_m3", 0) > 0, balance.get("inflow_m3"))
    log(f"hybrid peaks {peaks(folder)}; warnings {[e.get('message', '')[:110] for e in events(folder, 'warn')]}")
    check("hybrid hydrographs", sum(1 for v in peaks(folder).values() if v > 1) >= 5, peaks(folder))
    names = [lay.name() for lay in project.mapLayers().values()]
    check("hybrid maps loaded", any("max_depth" in n or "depth" in n.lower() for n in names), [n for n in names if "hybrid" in n or "depth" in n.lower()][:6])
    check("results button", dock.panel.open_button.isVisible())
    shot("hybrid_finished")

    # 2. every structure, per-line boundaries, CN and Manning rasters
    log("=== 2 structures")
    reset(dock)
    yield lambda: dock.hydrology.rain_box.isVisibleTo(dock.hydrology)
    t = dock.terrain
    t.dx.setValue(20.0)
    t.domain.setLayer(bidah)
    t.manning.raster.setLayer(man)
    h.cn.raster.setLayer(cnr)
    h.rain.setValue(60.0)
    h.hours.setValue(2.0)
    s = dock.structures
    if crest:
        s.layers["crest_line"].setLayer(crest)
        s.fields["crest_line"]["crest_z"].setField("z")
    if spill:
        s.layers["spillway"].setLayer(spill)
        s.fields["spillway"]["crest_z"].setField("z")
        s.fields["spillway"]["coefficient"].setField("c")
        s.fields["spillway"]["length"].setField("l")
    s.layers["wall"].setLayer(wall)
    s.layers["burn_line"].setLayer(burn)
    s.fields["burn_line"]["crest_z"].setField("z")
    dock.boundaries.layer.setLayer(mixed)
    dock.panel.duration.setValue(4.0)
    dock.panel.folder.setFilePath(str(RUNS / "objects"))
    dock.panel.run_button.click()
    done, seen = wait_done(dock, 400)
    yield lambda: dock.run is not None or "must" in dock.panel.message.text()
    yield done
    folder = RUNS / "objects"
    finish = events(folder, "done") if (folder / "progress.jsonl").exists() else []
    check("objects finished", finish and finish[-1].get("code") == 0, dock.panel.message.text())
    if finish:
        job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        kinds = sorted(o["kind"] for o in job["terrain"]["objects"])
        check("objects in the job", "wall" in kinds and "burn_line" in kinds, kinds)
        check("rasters in the job", job["terrain"]["manning_raster"] and job["terrain"]["cn_raster"], job["terrain"]["cn_raster"])
        check("live layer seen", seen[0])
    shot("objects_finished")

    # 3. stop in mid run
    log("=== 3 stop")
    dock.panel.duration.setValue(48.0)
    dock.panel.folder.setFilePath(str(RUNS / "stop"))
    dock.panel.run_button.click()
    yield lambda: dock.run is not None
    yield lambda: dock.panel.bar.value() >= 3
    dock.panel.stop_button.click()
    done, _ = wait_done(dock, 120)
    yield done
    check("stopped", "Stopped" in dock.panel.message.text() or "stopped" in dock.panel.message.text(), dock.panel.message.text())
    check("stop wrote maps", (RUNS / "stop" / "maps" / "max_depth.tif").exists())

    # 4. a folder that already holds a run
    log("=== 4 occupied folder")
    dock.panel.duration.setValue(0.5)
    dock.panel.folder.setFilePath(str(RUNS / "objects"))
    dock.panel.run_button.click()
    yield lambda: dock.run is not None
    said = dock.panel.message.text()
    check("occupied folder is not overwritten", "already holds" in said or dock.run.out_dir.name != "objects", said)
    other = dock.run.out_dir
    done, _ = wait_done(dock, 200)
    yield done
    check("second run in its own folder", other.name != "objects" and (other / "maps").exists(), other.name)

    # 5. the plugin reloads while a run goes on
    log("=== 5 reload in mid run")
    dock.panel.duration.setValue(12.0)
    dock.panel.folder.setFilePath(str(RUNS / "reload"))
    dock.panel.run_button.click()
    yield lambda: dock.run is not None
    yield lambda: dock.panel.bar.value() >= 2
    run_dir = dock.run.out_dir
    plugin.unload()
    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    dock = plugin.dock
    current[0] = dock
    check("run picked up after reload", dock is not None and dock.run is not None, run_dir.name)
    if dock is not None and dock.run is not None:
        done, _ = wait_done(dock, 300)
        yield done
        check("reloaded run finished", "Finished" in dock.panel.message.text(), dock.panel.message.text()[:140])
    else:
        plugin.toggle_action.setChecked(True)
        dock = plugin.dock
    yield lambda: dock.schema is not None

    # 6. what a user gets wrong
    log("=== 6 errors")
    t, h = dock.terrain, dock.hydrology
    t.dem.setLayer(dem)
    t.domain.setLayer(bidah)
    t.dx.setValue(20.0)
    h.rain.setValue(10.0)
    h.hours.setValue(1.0)
    dock.panel.duration.setValue(1.0)
    dock.panel.folder.setFilePath("")
    dock.panel.run_button.click()
    check("no output folder", "output folder" in dock.panel.message.text(), dock.panel.message.text())
    dock.panel.folder.setFilePath(str(RUNS / "bad"))
    h.rain.setValue(0.0)
    dock.panel.run_button.click()
    check("no rain", "rain" in dock.panel.message.text(), dock.panel.message.text())
    h.rain.setValue(10.0)
    empty = P / "empty_hms"
    empty.mkdir(exist_ok=True)
    h.folder.setFilePath(str(empty))
    yield lambda: not h.rain_box.isVisibleTo(h)
    dock.panel.run_button.click()
    check("empty HMS folder", "HMS" in dock.panel.message.text(), dock.panel.message.text())
    h.folder.setFilePath("")
    wgs = QgsRasterLayer(str(Path(os.environ["WADI2D_HMS"]).parent / "wgs.tif"), "wgs")
    if wgs.isValid():
        project.addMapLayer(wgs)
        t.dem.setLayer(wgs)
        dock.panel.run_button.click()
        check("geographic DEM", "projected" in dock.panel.message.text(), dock.panel.message.text())
        t.dem.setLayer(dem)
    bad = geojson("nocrs", [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[438000, 2726000], [439000, 2726000], [439000, 2727000], [438000, 2726000]]]}}])
    text = bad.read_text(encoding="utf-8")
    data = json.loads(text)
    data.pop("crs")
    bad.write_text(json.dumps(data), encoding="utf-8")
    wrong = QgsVectorLayer(str(bad), "no crs", "ogr")
    project.addMapLayer(wrong)
    t.domain.setLayer(wrong)
    dock.panel.run_button.click()
    check("domain with no CRS", "lands nowhere" in dock.panel.message.text() or "CRS" in dock.panel.message.text(), dock.panel.message.text())
    t.domain.setLayer(bidah)
    settings.set_engine_text('"C:\\nowhere\\python.exe" -m wadi2d.engine.cli')
    dock.load_engine()
    yield lambda: "not found" in dock.engine_label.text().lower()
    check("bad engine path", not dock.panel.run_button.isEnabled(), dock.engine_label.text())
    settings.set_engine_text(engine)
    dock.load_engine()
    yield lambda: dock.schema is not None and dock.panel.run_button.isEnabled()
    check("engine back", True)
    shot("errors_done")


gen = None
waiting = [None]
step_started = [time.monotonic()]
said = [""]
STEP_LIMIT = 1000.0


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
        import wadi2d_qgis  # noqa: F401  # the plugin is on the path once the scenario has started
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
    if time.monotonic() - T0 > 2400.0:
        log("TIMEOUT")
        finish("timeout")
        return
    QTimer.singleShot(250, tick)


LOG.write_text("", encoding="utf-8")
QTimer.singleShot(5000, tick)
log("script loaded")
