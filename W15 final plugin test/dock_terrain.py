"""Runs inside a separate QGIS with a throwaway profile: the terrain tools through the real dock, on Block 2 ground."""
import csv
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

from qgis.core import QgsPointXY, QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication
from qgis.utils import iface

ROOT = Path(os.environ["WADI2D_REPO"])
P = Path(os.environ["WADI2D_PLUG"])
VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
DEM = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif"
DATA = P / "data"
RUNS = P / "runs"
LOG = P / "log.txt"
T0 = time.monotonic()
results = []
shots = [0]
current = [None]
A, B = (435800.0, 2727300.0), (438600.0, 2726700.0)


def log(text):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.monotonic() - T0:7.1f} {text}\n")


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:200]))
    log(f"{'PASS' if ok else 'FAIL'} {name} {str(detail)[:260]}")


def shot(name, widget=None):
    QApplication.processEvents()
    shots[0] += 1
    (widget or iface.mainWindow()).grab().save(str(P / f"{shots[0]:02d}_{name}.png"))


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


def events(folder, kind):
    path = Path(folder) / "progress.jsonl"
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if f'"{kind}"' in s[:30]]


def clear_structures(dock):
    for picker in dock.structures.layers.values():
        picker.setLayer(None)


def wait_run(dock, limit):
    start = time.monotonic()

    def done():
        if time.monotonic() - start > limit:
            raise TimeoutError(f"no finish in {limit} s; status: {dock.panel.status.text()}")
        return dock.run is None and dock.panel.run_button.isEnabled()

    return done


def preview_done(dock):
    return lambda: dock.structures.preview_button.isEnabled()


def scenario():
    project = QgsProject.instance()
    DATA.mkdir(parents=True, exist_ok=True)
    if RUNS.exists():
        shutil.rmtree(RUNS)
    RUNS.mkdir()
    dem = QgsRasterLayer(DEM, "terrain")
    project.addMapLayer(dem)
    crs = dem.crs()
    project.setCrs(crs)
    x0, y0, x1, y1 = 435500.0, 2726000.0, 438900.0, 2728000.0
    ring = [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]
    domain_path = DATA / "domain.geojson"
    domain_path.write_text(
        json.dumps({
            "type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:32640"}},
            "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": ring}}],
        }),
        encoding="utf-8",
    )  # fmt: skip
    domain = add_vector(domain_path, "domain", crs)
    table = DATA / "sections.csv"
    source = ROOT / "W15 final plugin test" / "sections.csv"
    shutil.copy2(source, table)
    bad_table = DATA / "bad.csv"
    bad_table.write_text("station,bed_z,left_top_z,right_top_z\n500,120,124,124\n100,121,125,125\n", encoding="utf-8")
    mixed = add_vector(geojson("mixed", [line([list(A), list(B)], name="Mixed channel", openings="900-1000 left")]), "mixed", crs)
    bank_line = [[436200.0, 2727800.0], [436900.0, 2727650.0], [437500.0, 2727700.0]]
    bank = add_vector(geojson("bank", [line(bank_line, name="North dyke", crest=125.0, gap="400-460", w=7.0)]), "bank", crs)
    drain_line = [[436000.0, 2726300.0], [437000.0, 2726200.0], [438000.0, 2726250.0]]
    drain = add_vector(geojson("drain", [line(drain_line, name="South drain", start=122.4, fall=0.0009)]), "drain", crs)
    spill = add_vector(geojson("spill", [line([[436500.0, 2727735.0], [436620.0, 2727710.0]], z=121.0, c=2.1, l=60.0)]), "spill", crs)
    burn = add_vector(geojson("burn", [line([[436000.0, 2727500.0], [436500.0, 2727500.0]], z=118.0)]), "burn", crs)
    wall = add_vector(geojson("wall", [line([[435700.0, 2726500.0], [435900.0, 2726500.0]])]), "wall", crs)
    outlet = add_vector(geojson("outlet", [line([[438895.0, y0], [438895.0, y1]])]), "outlet", crs)
    bad = add_vector(geojson("badopen", [line([list(A), list(B)], name="Bad", gap="nine to ten")]), "bad opening", crs)
    iface.mapCanvas().setExtent(domain.extent())
    iface.mapCanvas().refresh()

    sys.path.insert(0, str(ROOT / "plugin"))
    import wadi2d_qgis
    from wadi2d_qgis import settings

    check("plugin is this branch", str(ROOT) in wadi2d_qgis.__file__, wadi2d_qgis.__file__)
    settings.set_engine_text(f'"{VENV}" "{ROOT / "W8 terrain tools" / "engine_worktree.py"}"')
    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    current[0] = dock
    yield lambda: dock.schema is not None
    check("engine found", "ready" in dock.engine_label.text().lower(), dock.engine_label.text())
    s = dock.structures
    s.setCollapsed(False)
    dyke_rows, bank_rows, drain_rows = s.shaped["channel_dyke"], s.shaped["embankment"], s.shaped["channel"]
    check("rows hidden until a layer is chosen", not dyke_rows.isVisibleTo(s))
    check("defaults from the engine", bank_rows.numbers["width"].box.value() == 5.0, bank_rows.numbers["width"].box.value())
    check("tooltips from the engine", bool(dyke_rows.numbers["left_outer_slope"].box.toolTip()), dyke_rows.numbers["left_outer_slope"].box.toolTip())
    check("ends from the engine", [dyke_rows.end_end.itemText(i) for i in range(dyke_rows.end_end.count())] == ["open", "closed", "taper"])
    check("no lining by default", drain_rows.numbers["lining_n"].box.text() == "none", drain_rows.numbers["lining_n"].box.text())

    log("=== 1 what a run needs is not asked of a preview")
    dock.terrain.dem.setLayer(dem)
    dock.terrain.dx.setValue(10.0)
    dock.terrain.domain.setLayer(domain)
    dock.hydrology.rain.setValue(0.0)
    s.preview_button.click()
    yield preview_done(dock)
    check("preview needs an object", "to preview" in s.preview_label.text(), s.preview_label.text())

    log("=== 2 three objects, three ways of giving a section")
    s.layers["channel_dyke"].setLayer(mixed)
    yield lambda: True
    check("rows shown when a layer is chosen", dyke_rows.isVisibleTo(s))
    s.preview_button.click()
    yield preview_done(dock)
    check("a dyke with no levels is refused in words", "needs a bed" in s.preview_label.text(), s.preview_label.text())
    dyke_rows.table.setFilePath(str(table))
    dyke_rows.fields["name"].setField("name")
    dyke_rows.fields["openings"].setField("openings")
    dyke_rows.numbers["lining_n"].box.setValue(0.02)
    dyke_rows.start_end.setCurrentText("taper")
    dyke_rows.end_end.setCurrentText("taper")
    dyke_rows.taper.setValue(100.0)
    s.layers["embankment"].setLayer(bank)
    bank_rows.fields["crest_z"].setField("crest")
    bank_rows.fields["openings"].setField("gap")
    bank_rows.fields["name"].setField("name")
    bank_rows.numbers["width"].field.setField("w")
    bank_rows.numbers["left_slope"].box.setValue(2.5)
    s.layers["channel"].setLayer(drain)
    drain_rows.fields["bed_start_z"].setField("start")
    drain_rows.fields["bed_slope"].setField("fall")
    drain_rows.fields["name"].setField("name")
    drain_rows.numbers["width"].box.setValue(36.0)
    drain_rows.numbers["left_slope"].box.setValue(1.5)
    drain_rows.numbers["right_slope"].box.setValue(1.5)
    shot("fields_set")
    s.resize(max(s.width(), 460), s.sizeHint().height())
    shot("structures_section", s)
    started = time.monotonic()
    s.preview_button.click()
    check("preview says it is working", "Working" in s.preview_label.text(), s.preview_label.text())
    yield preview_done(dock)
    text = s.preview_label.text()
    log(f"preview took {time.monotonic() - started:.1f} s; said: {text[:900]}")
    check("preview gives the volumes", "Earthworks" in text and "Mixed channel: cut" in text and "North dyke: fill" in text and "South drain: cut" in text, text)
    check("preview gives the checks", "above the ground" in text, text)
    names = [layer.name() for layer in project.mapLayers().values()]
    check("preview loads both rasters", "terrain change" in names and "terrain modified" in names, names)
    root = project.layerTreeRoot()
    check("preview has its group", root.findGroup("Wadi2D terrain preview") is not None)
    change = next(layer for layer in project.mapLayers().values() if layer.name() == "terrain change")
    value, known = change.dataProvider().sample(QgsPointXY(0.5 * (A[0] + B[0]), 0.5 * (A[1] + B[1])), 1)
    check("the change layer holds the cut or fill on the line", known and value != 0.0, value)
    report = dock.preview.report
    rows = list(csv.DictReader(open(report["files"]["volumes"], newline="", encoding="utf-8")))
    by_name = {r["object"]: r for r in rows}
    check("the volumes table has every object", set(by_name) == {"Mixed channel", "North dyke", "South drain"}, sorted(by_name))
    check("the plain channel cut ground", float(by_name["South drain"]["cut_m3"]) > 0.0, by_name["South drain"])
    check("the mixed channel cut and filled", float(by_name["Mixed channel"]["cut_m3"]) > 0.0 and float(by_name["Mixed channel"]["fill_m3"]) > 0.0, by_name["Mixed channel"])
    check("the profile button appears", s.profile_button.isVisible())
    extent = iface.mapCanvas().extent()
    check("the map went to the preview", extent.width() < 20000.0 and extent.contains(QgsPointXY(*A)), extent.toString(0))
    # the canvas shows its old image scaled up until the new one is drawn
    project.layerTreeRoot().findLayer(domain.id()).setItemVisibilityChecked(False)
    iface.mapCanvas().refresh()
    iface.mapCanvas().waitWhileRendering()
    shot("preview_on_map")
    from wadi2d_qgis.profile_view import ProfileDialog

    dialog = ProfileDialog(dock.preview.data, dock)
    dialog.resize(900, 700)
    dialog.show()
    dialog.slider.setValue(5)
    QApplication.processEvents()
    check("the dialog lists the objects", dialog.objects.count() == 3, dialog.objects.count())
    check("the slider steps through the sections", "Station" in dialog.station.text(), dialog.station.text())
    states = next(item for item in dock.preview.data if item["name"] == "Mixed channel")
    flips = sum(a != b for a, b in zip(states["left_state"], states["left_state"][1:]))
    both = {*states["left_state"]} >= {"cut", "dyke", "open"}
    check("the left bank is cut, dyke and open along one line", both and flips >= 2, f"{flips} changes")
    shot("profile_dialog", dialog)
    dialog.objects.setCurrentIndex(1)
    dialog.slider.setValue(4)
    QApplication.processEvents()
    shot("profile_second", dialog)
    dialog.objects.setCurrentIndex(2)
    dialog.slider.setValue(5)
    QApplication.processEvents()
    shot("profile_third", dialog)
    dialog.close()

    log("=== 3 a second preview replaces the first")
    bank_rows.numbers["left_slope"].box.setValue(3.0)
    s.preview_button.click()
    yield preview_done(dock)
    groups = [child.name() for child in root.children() if child.name() == "Wadi2D terrain preview"]
    check("one preview group", len(groups) == 1, groups)

    log("=== 4 mistakes")
    dyke_rows.table.setFilePath(str(bad_table))
    s.preview_button.click()
    yield preview_done(dock)
    check("stations out of order are refused in words", "stations must increase" in s.preview_label.text(), s.preview_label.text())
    check("no profile after a refusal", not s.profile_button.isVisible())
    dyke_rows.table.setFilePath(str(DATA / "not_there.csv"))
    s.preview_button.click()
    yield preview_done(dock)
    check("a missing table is said", "not there" in s.preview_label.text(), s.preview_label.text())
    dyke_rows.table.setFilePath(str(table))
    s.layers["channel_dyke"].setLayer(bad)
    dyke_rows.table.setFilePath(str(table))
    dyke_rows.fields["openings"].setField("gap")
    s.preview_button.click()
    yield preview_done(dock)
    check("a bad opening is said", "is not a range" in s.preview_label.text(), s.preview_label.text())
    s.layers["channel_dyke"].setLayer(mixed)
    dyke_rows.table.setFilePath(str(table))
    dyke_rows.fields["openings"].setField("openings")
    dyke_rows.fields["name"].setField("name")

    log("=== 5 a real run, the modified terrain asked for")
    dock.hydrology.rain.setValue(40.0)
    dock.hydrology.hours.setValue(1.0)
    dock.hydrology.cn.box.setValue(85.0)
    dock.boundaries.layer.setLayer(outlet)
    dock.boundaries.kind.setCurrentText("normal")
    dock.boundaries.value.setValue(0.012)
    dock.panel.duration.setValue(2.0)
    dock.panel.folder.setFilePath(str(RUNS / "full"))
    s.terrain_map.setChecked(True)
    dock.panel.estimate_button.click()
    yield lambda: dock.panel.estimate_label.text() not in ("", "Estimating...")
    check("estimate works with the objects", "cells" in dock.panel.estimate_label.text(), dock.panel.estimate_label.text())
    dock.panel.run_button.click()
    yield lambda: dock.run is not None or "must" in dock.panel.message.text()
    shot("run_started")
    yield wait_run(dock, 900)
    folder = RUNS / "full"
    done = events(folder, "done")
    check("run finished", done and done[-1].get("code") == 0, dock.panel.message.text())
    said = dock.panel.message.text()
    log(f"final message: {said[:1200]}")
    check("the final message has the volumes", "Earthworks" in said and "Mixed channel: cut" in said, said)
    check("the final message has the checks", "above the ground" in said, said)
    balance = done[-1].get("balance", {}) if done else {}
    check("mass balance closes", abs(balance.get("relative_error", 1.0)) < 1e-5, balance.get("relative_error"))
    start = events(folder, "start")
    check("which device", bool(start), start[-1].get("backend") if start else "")
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    objects = {o.get("name", o["kind"]): o for o in job["terrain"]["objects"]}
    log(f"objects in the job: {sorted(objects)}")
    mix = objects["Mixed channel"]
    check("the table is copied into the run", Path(mix["section"]["table"]).parent == (folder / "inputs").resolve() and Path(mix["section"]["table"]).is_file(), mix["section"]["table"])
    check("lining, opening and ends in the job", mix["lining_n"] == 0.02 and mix["openings"][0]["side"] == "left" and mix["start_end"] == "taper", {k: mix.get(k) for k in ("lining_n", "openings", "start_end", "taper_length")})
    north = objects["North dyke"]
    check("a field wins over the number", north["section"]["width"] == 7.0, north["section"])
    check("the number stands where no field is chosen", north["section"]["left_slope"] == 3.0, north["section"])
    check("a text field gives the opening", north["openings"] == [{"start": 400.0, "end": 460.0, "side": "both"}], north["openings"])
    drain_obj = objects["South drain"]
    check("the design rule reaches the job", drain_obj["section"]["bed_start_z"] == 122.4 and drain_obj["section"]["bed_slope"] == 0.0009, drain_obj["section"])
    resolved = json.loads((folder / "config.resolved.json").read_text(encoding="utf-8"))
    rows_held = [o for o in resolved["terrain"]["objects"] if o["kind"] == "channel_dyke"][0]["section"]["rows"]
    check("the saved job holds the table's numbers", len(rows_held) >= 5, len(rows_held))
    for name in ("volumes.csv", "volumes_by_station.csv", "terrain_modified.tif", "terrain_change.tif"):
        check(f"run wrote {name}", (folder / "terrain" / name).is_file())
    with_map = QgsRasterLayer(str(folder / "terrain" / "terrain_modified.tif"), "check")
    check("the modified terrain opens and covers the domain", with_map.isValid() and with_map.extent().width() >= 3400.0, with_map.extent().toString(0))
    shot("run_finished")

    log("=== 6 no map unless asked")
    s.terrain_map.setChecked(False)
    dock.panel.folder.setFilePath(str(RUNS / "nomap"))
    dock.panel.run_button.click()
    yield lambda: dock.run is not None or "must" in dock.panel.message.text()
    yield wait_run(dock, 600)
    folder = RUNS / "nomap"
    check("the cached grid is used", any(e.get("kind") == "grid_cache_hit" for e in events(folder, "output")), "")
    check("volumes without the map", (folder / "terrain" / "volumes.csv").is_file())
    check("no map unasked", not (folder / "terrain" / "terrain_modified.tif").exists())

    log("=== 7 a spillway on the embankment, with the old kinds beside it")
    s.layers["spillway"].setLayer(spill)
    s.fields["spillway"]["crest_z"].setField("z")
    s.fields["spillway"]["coefficient"].setField("c")
    s.fields["spillway"]["length"].setField("l")
    s.layers["wall"].setLayer(wall)
    s.layers["burn_line"].setLayer(burn)
    s.fields["burn_line"]["crest_z"].setField("z")
    dock.panel.folder.setFilePath(str(RUNS / "mixed_kinds"))
    dock.panel.run_button.click()
    yield lambda: dock.run is not None or "must" in dock.panel.message.text()
    yield wait_run(dock, 600)
    folder = RUNS / "mixed_kinds"
    done = events(folder, "done")
    check("old and new kinds run together", done and done[-1].get("code") == 0, dock.panel.message.text())
    kinds = sorted(o["kind"] for o in json.loads((folder / "job.json").read_text(encoding="utf-8"))["terrain"]["objects"])
    check("all six kinds in the job", kinds == ["burn_line", "channel", "channel_dyke", "embankment", "spillway", "wall"], kinds)

    log("=== 8 old kinds alone, as before")
    clear_structures(dock)
    s.layers["wall"].setLayer(wall)
    s.layers["burn_line"].setLayer(burn)
    s.fields["burn_line"]["crest_z"].setField("z")
    dock.panel.folder.setFilePath(str(RUNS / "old_kinds"))
    dock.panel.run_button.click()
    yield lambda: dock.run is not None or "must" in dock.panel.message.text()
    yield wait_run(dock, 600)
    folder = RUNS / "old_kinds"
    done = events(folder, "done")
    check("old kinds still run", done and done[-1].get("code") == 0, dock.panel.message.text())
    check("a burn line alone reports its cut", "burn_line 1: cut" in dock.panel.message.text(), dock.panel.message.text())
    shot("end")


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


P.mkdir(parents=True, exist_ok=True)
LOG.write_text("", encoding="utf-8")
QTimer.singleShot(5000, tick)
log("script loaded")
