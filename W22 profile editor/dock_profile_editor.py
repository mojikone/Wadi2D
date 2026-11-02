"""D7 through the real dock: the profile editor on Block 2 ground, and the ground the engine then used."""

import csv
import itertools
import json
import os
import subprocess
from pathlib import Path

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QEvent, QPoint, QPointF, Qt
from qgis.PyQt.QtGui import QMouseEvent
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QApplication, QMessageBox

MAIN_PYTHON = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
"""A worktree has no .venv of its own; the engine still comes from the worktree, through engine.py."""

BED, CREST, LEFT, RIGHT = "bed_z", "crest_z", "left_top_z", "right_top_z"
X0, Y0, X1, Y1 = 435500.0, 2726000.0, 438900.0, 2728000.0
WADI = [[435800.0, 2727300.0], [437200.0, 2727000.0], [438600.0, 2726700.0]]
DRAIN = [[436000.0, 2726300.0], [437000.0, 2726200.0], [438000.0, 2726250.0]]
BANK = [[436200.0, 2727800.0], [436900.0, 2727650.0], [437500.0, 2727700.0]]
CREST_LINE = [[435700.0, 2726600.0], [436300.0, 2726500.0]]
SPILL = [[436500.0, 2727735.0], [436620.0, 2727710.0]]
BURN = [[436000.0, 2727500.0], [436500.0, 2727500.0]]


def clear(dock):
    for picker in dock.structures.layers.values():
        picker.setLayer(None)


def drag(canvas, start, end, modifiers=Qt.NoModifier):
    """Press, move and release as real Qt events on the canvas, as a user's hand gives them."""
    QTest.mousePress(canvas, Qt.LeftButton, modifiers, start)
    for point in (QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2), end):
        event = QMouseEvent(QEvent.MouseMove, QPointF(point), QPointF(canvas.mapToGlobal(point)), Qt.NoButton, Qt.LeftButton, modifiers)
        QApplication.sendEvent(canvas, event)
    QTest.mouseRelease(canvas, Qt.LeftButton, modifiers, end)
    QApplication.processEvents()


def station_point(coordinates, s):
    """The point at station ``s`` of a polyline."""
    total = 0.0
    for (x0, y0), (x1, y1) in itertools.pairwise(coordinates):
        run = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if s <= total + run:
            share = (s - total) / run
            return x0 + share * (x1 - x0), y0 + share * (y1 - y0)
        total += run
    return tuple(coordinates[-1])


def solver_ground(h, job, points):
    """What the solver's grid holds at these points, read through the engine on the run's own job and cache."""
    numbers = [str(value) for point in points for value in point]
    script = str(h.REPO / "W22 profile editor" / "read_ground.py")
    cache = Path(job).parent.parent / "wadi2d_cache"
    from wadi2d_qgis.protocol import clean_env

    done = subprocess.run(  # QGIS's own Python must not leak in: the dock's engine runs on this environment too
        [str(h.VENV), script, str(h.REPO), str(job), str(cache), *numbers],
        capture_output=True, text=True, timeout=300, cwd=str(h.P), env=clean_env(dict(os.environ)),
    )  # fmt: skip
    h.log(f"read_ground: {done.stdout.strip()[:300]} {done.stderr.strip()[-200:] if done.returncode else ''}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def sample(path, point):
    from qgis.core import QgsRasterLayer

    layer = QgsRasterLayer(str(path), "probe")
    value, known = layer.dataProvider().sample(QgsPointXY(*point), 1)
    return value if known else None


def volumes(folder):
    with (Path(folder) / "terrain" / "volumes.csv").open(newline="", encoding="utf-8") as stream:
        return {row["object"]: row for row in csv.DictReader(stream)}


def objects(folder):
    job = json.loads((Path(folder) / "job.json").read_text(encoding="utf-8"))
    return job["terrain"]["objects"]


def scenario(h):
    if not h.VENV.exists():
        h.VENV = MAIN_PYTHON
    project = QgsProject.instance()
    ground = h.Bidah()
    crs = ground.crs
    domain_path = h.geojson("box", [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[X0, Y0], [X1, Y0], [X1, Y1], [X0, Y1], [X0, Y0]]]}}])
    box = h.add_vector(domain_path, "small domain", crs)
    outlet = h.add_vector(h.geojson("outlet", [h.line([[438895.0, Y0], [438895.0, Y1]], kind="normal", value=0.012)]), "outlet", crs)
    wadi = h.add_vector(h.geojson("wadi", [h.line(WADI, name="Wadi cut", start=122.0, fall=0.0009, top=125.0)]), "wadi", crs)
    drain = h.add_vector(h.geojson("drain", [h.line(DRAIN, name="South drain", start=122.4, fall=0.0009)]), "drain", crs)
    bank = h.add_vector(h.geojson("bank", [h.line(BANK, name="North dyke", crest=125.0)]), "bank", crs)
    crest = h.add_vector(h.geojson("crest", [h.line(CREST_LINE, z=122.0)]), "crest", crs)
    spill = h.add_vector(h.geojson("spill", [h.line(SPILL, z=124.0, c=2.1, l=30.0)]), "spill", crs)
    burn = h.add_vector(h.geojson("burn", [h.line(BURN, z=121.0)]), "burn", crs)

    dock = yield from h.open_dock()
    s = dock.structures
    s.setCollapsed(False)
    t = dock.terrain
    t.dem.setLayer(ground.dem)
    t.dx.setValue(10.0)
    t.domain.setLayer(box)
    dock.hydrology.rain.setValue(40.0)
    dock.hydrology.hours.setValue(1.0)
    dock.hydrology.cn.box.setValue(85.0)
    dock.boundaries.layer.setLayer(outlet)
    dock.points.layer.setLayer(None)
    dock.panel.duration.setValue(1.0)
    dock.panel.pixels.setChecked(False)
    s.terrain_map.setChecked(True)

    dyke_rows = s.shaped["channel_dyke"]
    drain_rows = s.shaped["channel"]
    bank_rows = s.shaped["embankment"]

    h.log("=== 1 where the editor sits in the dock")
    h.check("no button until a layer is chosen", not dyke_rows.profile_row.isVisibleTo(s))
    h.check("walls have no profile", "wall" not in s.profile_rows)
    s.layers["channel_dyke"].setLayer(wadi)
    dyke_rows.fields["bed_start_z"].setField("start")
    dyke_rows.fields["bed_slope"].setField("fall")
    dyke_rows.fields["top_z"].setField("top")
    dyke_rows.fields["name"].setField("name")
    dyke_rows.numbers["width"].box.setValue(20.0)
    QApplication.processEvents()
    h.check("the button shows with the layer", dyke_rows.profile_row.isVisibleTo(s) and dyke_rows.profile_row.button.text() == "Edit profile...")
    h.check("no saved profile yet", dyke_rows.profile_row.saved.text() == "", dyke_rows.profile_row.saved.text())
    s.resize(max(s.width(), 470), s.sizeHint().height())
    h.widget_shot("structures_section", s)

    h.log("=== 2 a run on the fields alone: what an edit has to differ from")
    dock.panel.folder.setFilePath(str(h.RUNS / "fields"))
    yield from h.run(dock)
    plain = h.RUNS / "fields"
    done = h.events(plain, "done")
    h.check("the fields run finishes", done and done[-1]["code"] == 0, dock.panel.message.text())
    plain_object = next(o for o in objects(plain) if o["kind"] == "channel_dyke")
    h.check("the fields reach the job", plain_object["section"]["bed_start_z"] == 122.0 and "table" not in plain_object["section"], plain_object["section"])

    h.log("=== 3 the same ground as Preview terrain")
    s.preview_button.click()
    yield lambda: s.preview_button.isEnabled()
    item = dock.preview.data[0]
    h.check("Preview terrain still works", item["kind"] == "channel_dyke" and "Earthworks" in s.preview_label.text(), s.preview_label.text()[:200])

    h.log("=== 4 the editor opens from the dock on the line's own numbers")
    dyke_rows.profile_row.button.click()
    QApplication.processEvents()
    editor = dock.editor
    h.check("the button opens the editor", editor is not None and editor.isVisible())
    h.check("beside the map, not over it: not modal", not editor.isModal())
    model = editor.model
    canvas = editor.canvas
    length = 2 * (1400.0**2 + 300.0**2) ** 0.5
    h.check("one line in the box, by its name", editor.line_box.count() == 1 and editor.line_box.currentText() == "Wadi cut", editor.line_box.currentText())
    h.check("three series", model.keys == (BED, LEFT, RIGHT), model.keys)
    h.check("the bed starts from its fields", model.points[BED][0] == [0.0, 122.0] and abs(model.points[BED][1][1] - (122.0 - 0.0009 * length)) < 1e-6, model.points[BED])
    h.check("the tops start from their field", model.points[LEFT][0] == [0.0, 125.0] and model.points[RIGHT] == model.points[LEFT], model.points[LEFT])
    h.check("one top field: both tops together", editor.tied.isChecked() and model.tied)
    h.check("the route says fields", "fields of the layer" in editor.route.text(), editor.route.text())
    h.check("vertices are marked", len(canvas.vertices) == 3, canvas.vertices)
    from wadi2d_qgis.profile_table import interp

    gaps = sorted(abs(interp(canvas.ground, station) - level) for station, level in zip(item["station"], item["ground"], strict=True))
    median = gaps[len(gaps) // 2]
    h.check("the ground is the DEM along the line: within 0.15 m of the engine's, at the median", median < 0.15, f"median {median:.3f}, worst {gaps[-1]:.3f}, {len(canvas.ground)} samples")
    h.widget_shot("01_opened", editor)

    h.log("=== 5 drag, type, undo, by real events")
    target = 1500.0
    at = canvas.to_pixel(target, model.level(BED, target)).toPoint()
    QTest.mouseDClick(canvas, Qt.LeftButton, Qt.NoModifier, at)
    QApplication.processEvents()
    h.check("a double-click adds a point on the bed", len(model.points[BED]) == 3 and abs(model.points[BED][1][0] - target) < 3.0, model.points[BED])
    h.check("the table has its row", editor.table.rowCount() == len(model.stations()) + 1, editor.table.rowCount())
    point = canvas.to_pixel(*model.points[BED][1]).toPoint()
    top_before = json.dumps(model.points[LEFT])
    drag(canvas, point, QPoint(point.x(), point.y() + 70), Qt.ShiftModifier)
    dragged = list(model.points[BED][1])
    h.check("Shift and a drag lower the bed and hold the station", dragged[1] < model.level(BED, 0.0) - 1.5 and abs(dragged[0] - target) < 3.0, dragged)
    h.check("the tops stayed", json.dumps(model.points[LEFT]) == top_before)
    h.widget_shot("02_dragged", editor)
    editor.undo_button.click()
    h.check("undo puts it back", model.points[BED][1] != dragged)
    QTest.keyClick(editor, Qt.Key_Y, Qt.ControlModifier)
    QApplication.processEvents()
    h.check("Ctrl+Y brings it again", model.points[BED][1] == dragged, model.points[BED][1])
    row = model.stations().index(dragged[0])
    edited_station = dragged[0]
    edited_level = 118.5
    editor.table.item(row, 1).setText(str(edited_level))
    h.check("a typed level lands on the point", model.points[BED][1] == [edited_station, edited_level], model.points[BED][1])
    point = canvas.to_pixel(model.points[LEFT][1][0], model.points[LEFT][1][1]).toPoint()
    h.check("the tops are the same at every point", model.tops_alike())
    drag(canvas, point + QPoint(0, 0), QPoint(point.x(), point.y() - 8), Qt.ShiftModifier)
    h.check("both tops move together", model.tops_alike() and model.points[LEFT][1][1] != 125.0, model.points[LEFT])
    editor.undo()

    h.log("=== 6 what cannot be built is met here, in words")
    before = json.dumps(model.points)
    model.begin()
    model.drag(LEFT, 0, 0.0, 100.0)
    model.end()
    editor.refresh()
    h.check("Save refuses a top under the bed", editor.save() is False and "below the bed at station 0" in editor.words.text(), editor.words.text())
    editor.preview()
    h.check("Preview refuses it too, before the engine", not editor.waiting and "below the bed" in editor.words.text(), editor.words.text())
    editor.undo()
    h.check("undo clears it", json.dumps(model.points) == before)

    h.log("=== 7 Preview terrain in the editor: the engine's result on unsaved points")
    profiles = s.profiles
    h.check("nothing is saved yet", profiles.count(wadi, "channel_dyke") == 0)
    editor.preview_button.click()
    h.check("it says it is working", "Working" in editor.words.text() or not editor.waiting, editor.words.text())
    yield lambda: not editor.waiting
    h.log(f"editor says: {editor.words.text()[:500]}")
    h.check("the engine's words reach the editor", "Earthworks" in editor.words.text() and "Wadi cut: cut" in editor.words.text(), editor.words.text()[:200])
    h.check("the pane holds the engine's profile", editor.pane.item is not None and editor.pane.item["name"] == "Wadi cut")
    view = editor.pane.item
    bed_gaps = [abs(model.level(BED, station) - level) for station, level in zip(view["station"], view["bed"], strict=True)]
    h.check("the engine's bed is the bed in the plot, to 2 cm", max(bed_gaps) < 0.02, f"worst {max(bed_gaps):.4f}")
    near = min(range(len(view["station"])), key=lambda n: abs(view["station"][n] - edited_station))
    was = min(range(len(item["station"])), key=lambda n: abs(item["station"][n] - edited_station))
    h.check("the new ground went down where the bed did", view["new"][near] < item["new"][was] - 1.0, (view["new"][near], item["new"][was]))
    h.check("the draft left no file behind", profiles.count(wadi, "channel_dyke") == 0)
    h.check("the draft is gone from the store", profiles.draft is None)
    h.check("the same canvas as Preview terrain", type(editor.pane.canvas).__name__ == "ProfileCanvas")
    change = next(layer for layer in project.mapLayers().values() if layer.name() == "terrain change")
    h.check("the map holds this preview", change.isValid(), change.source()[-60:])
    h.widget_shot("03_previewed", editor)
    canvas.selected = (BED, 1)
    canvas.selected_point.emit(edited_station)
    QApplication.processEvents()
    section = view["sections"][editor.pane.slider.value()]
    h.check("taking a point turns the section to it", abs(section["station"] - edited_station) <= length / 8.0, section["station"])
    h.widget_shot("04_section_at_the_point", editor)
    h.render("preview_change", [change, ground.dem], QgsPointXY(*station_point(WADI, edited_station)), 25000.0)
    model.begin()
    model.drag(BED, 1, edited_station, edited_level - 0.01)
    model.end()
    editor.refresh()
    h.check("an edit marks the preview out of date", "since this preview" in editor.pane.banner.text(), editor.pane.banner.text())
    editor.undo()
    h.check("undoing the edit makes it good again", "result for these points" in editor.pane.banner.text(), editor.pane.banner.text())

    h.log("=== 8 Save, and a run: the ground the engine used")
    h.check("Save writes the file", editor.save() is True, editor.words.text())
    saved = profiles.table(wadi, "channel_dyke", "0")
    h.check("beside the layer, by line", saved is not None and Path(saved).parent == h.DATA / "wadi_profiles" and Path(saved).name == "channel_dyke_line_0.csv", saved)
    h.check("the dock counts it", "1 saved" in dyke_rows.profile_row.saved.text(), dyke_rows.profile_row.saved.text())
    h.check("the route says saved", "saved profile" in editor.route.text() and editor.drop_button.isEnabled(), editor.route.text())
    h.widget_shot("structures_with_a_saved_profile", s)
    h.widget_shot("profile_row", dyke_rows.profile_row)
    h.check("the button keeps its width beside the count", dyke_rows.profile_row.button.width() >= dyke_rows.profile_row.button.sizeHint().width(), dyke_rows.profile_row.button.width())
    h.check("the count fits", dyke_rows.profile_row.saved.width() >= dyke_rows.profile_row.saved.sizeHint().width(), dyke_rows.profile_row.saved.width())
    with Path(saved).open(encoding="utf-8") as stream:
        head = stream.readline().strip()
    h.check("in the engine's own columns", head == "station,bed_z,left_top_z,right_top_z", head)
    dock.panel.folder.setFilePath(str(h.RUNS / "edited"))
    yield from h.run(dock)
    edited = h.RUNS / "edited"
    done = h.events(edited, "done")
    h.check("the edited run finishes", done and done[-1]["code"] == 0, dock.panel.message.text())
    h.check("mass closes", abs(done[-1]["balance"]["relative_error"]) < 1e-5, done[-1]["balance"]["relative_error"])
    entry = next(o for o in objects(edited) if o["kind"] == "channel_dyke")
    copied = Path(entry["section"]["table"])
    h.check("the job names the table in inputs", copied.parent == (edited / "inputs").resolve() and copied.is_file(), copied)
    h.check("the copy holds the saved numbers", copied.read_text(encoding="utf-8") == Path(saved).read_text(encoding="utf-8"))
    resolved = json.loads((edited / "config.resolved.json").read_text(encoding="utf-8"))
    rows = next(o for o in resolved["terrain"]["objects"] if o["kind"] == "channel_dyke")["section"]["rows"]
    h.check("the engine's resolved job holds the edited level", any(r["station"] == edited_station and r["bed_z"] == edited_level for r in rows), [(r["station"], r["bed_z"]) for r in rows])
    point = station_point(WADI, edited_station)
    new_map, old_map = sample(edited / "terrain" / "terrain_modified.tif", point), sample(plain / "terrain" / "terrain_modified.tif", point)
    h.log(f"terrain at station {edited_station}: fields {old_map}, edited {new_map}, bed asked {edited_level}")
    h.check("the modified terrain stands at the edited bed", abs(new_map - edited_level) < 0.15, new_map)
    h.check("and the run on the fields does not", abs(old_map - edited_level) > 1.0, old_map)
    grids = {name: solver_ground(h, folder / "job.json", [point]) for name, folder in (("fields", plain), ("edited", edited))}
    h.log(f"solver zmin: {grids}")
    h.check("the engine under test is this worktree", str(h.REPO) in grids["edited"]["engine"], grids["edited"]["engine"])
    h.check("the solver's cell went down to the edited bed", abs(grids["edited"]["zmin"][0] - edited_level) < 0.3, grids["edited"]["zmin"])
    h.check("and by more than a metre from the fields' run", grids["fields"]["zmin"][0] - grids["edited"]["zmin"][0] > 1.0, (grids["fields"]["zmin"][0], grids["edited"]["zmin"][0]))
    cut_old, cut_new = float(volumes(plain)["Wadi cut"]["cut_m3"]), float(volumes(edited)["Wadi cut"]["cut_m3"])
    h.check("more ground was cut", cut_new > cut_old + 100.0, (cut_old, cut_new))
    h.render("modified_terrain", [h.add_raster(edited / "terrain" / "terrain_change.tif", "edited change"), ground.dem], QgsPointXY(*point), 25000.0)

    h.log("=== 9 the saved profile comes back; the field and table routes stay")
    editor.close()
    QApplication.processEvents()
    h.check("closing leaves the dock free", dock.editor is None)
    s.layers["channel_dyke"].setLayer(None)
    s.layers["channel_dyke"].setLayer(wadi)
    dyke_rows.fields["bed_start_z"].setField("start")
    dyke_rows.fields["bed_slope"].setField("fall")
    dyke_rows.fields["top_z"].setField("top")
    dyke_rows.fields["name"].setField("name")
    h.check("a layer chosen again finds its profile", "1 saved" in dyke_rows.profile_row.saved.text(), dyke_rows.profile_row.saved.text())
    dyke_rows.profile_row.button.click()
    editor = dock.editor
    h.check("the editor reopens on the saved points", editor.model.points[BED][1] == [edited_station, edited_level], editor.model.points[BED])
    editor.close()

    s.layers["channel"].setLayer(drain)
    drain_rows.fields["bed_start_z"].setField("start")
    drain_rows.fields["bed_slope"].setField("fall")
    drain_rows.fields["name"].setField("name")
    drain_rows.numbers["width"].box.setValue(30.0)
    table = h.DATA / "drain_section.csv"
    table.write_text("station,bed_z,width\n0,122.4,30\n1000,121.5,30\n2002,120.6,30\n", encoding="utf-8")
    dock.panel.folder.setFilePath(str(h.RUNS / "routes"))
    values = dock._collect()
    routes = values["structures"]
    h.check("the field route alone: no table on the drain", routes["channel"][0].properties.get("table") is None, routes["channel"][0].properties.get("table"))
    drain_rows.table.setFilePath(str(table))
    routes = dock._collect()["structures"]
    h.check("the Section table route works", routes["channel"][0].properties.get("table") == str(table), routes["channel"][0].properties.get("table"))
    h.check("the saved profile stands beside it", routes["channel_dyke"][0].properties.get("table") == saved, routes["channel_dyke"][0].properties.get("table"))
    yield from h.run(dock)
    routes_folder = h.RUNS / "routes"
    done = h.events(routes_folder, "done")
    h.check("a run on a saved profile and a section table", done and done[-1]["code"] == 0, dock.panel.message.text())
    entry = next(o for o in objects(routes_folder) if o["kind"] == "channel")
    h.check("the section table reaches the job as ever", Path(entry["section"]["table"]).name == "channel_1_drain_section.csv", entry["section"]["table"])

    h.log("=== 10 a table in the dock opens in the editor; Save keeps a copy for that line; the table stays")
    drain_rows.profile_row.button.click()
    editor = dock.editor
    h.check("the editor starts from the section table", editor.model.points[BED] == [[0.0, 122.4], [1000.0, 121.5], [2002.0, 120.6]], editor.model.points[BED])
    h.check("it says the table is in use", "drain_section.csv" in editor.route.text(), editor.route.text())
    h.check("the other column stays with its stations", editor.model.rows()[0]["width"] == 30.0, editor.model.rows()[0])
    text_before = table.read_text(encoding="utf-8")
    editor.table.item(1, 1).setText("121.0")
    h.check("Save", editor.save(), editor.words.text())
    h.check("the user's table is not touched", table.read_text(encoding="utf-8") == text_before)
    written = Path(profiles.table(drain, "channel", "0")).read_text(encoding="utf-8").splitlines()
    h.check("the saved copy keeps width", written[0] == "station,bed_z,width" and written[2] == "1000,121,30", written[:3])
    h.widget_shot("05_channel_from_a_table", editor)
    routes = dock._collect()["structures"]
    h.check("the edit outranks the table", routes["channel"][0].properties.get("table") == profiles.table(drain, "channel", "0"), routes["channel"][0].properties.get("table"))

    h.log("=== 11 Drop goes back, and the job is the one before any edit")
    editor.drop_button.click()
    h.check("the table is in use again", editor.model.points[BED][1] == [1000.0, 121.5] and "drain_section.csv" in editor.route.text(), editor.route.text())
    h.check("the file stays under another name", any(p.name.endswith(".dropped") for p in (h.DATA / "drain_profiles").iterdir()), list((h.DATA / "drain_profiles").iterdir()))
    editor.close()
    drain_rows.table.setFilePath("")
    s.layers["channel"].setLayer(None)
    dyke_rows.profile_row.button.click()
    editor = dock.editor
    editor.drop_button.click()
    h.check("back to the fields", editor.model.points[BED][0] == [0.0, 122.0] and len(editor.model.points[BED]) == 2, editor.model.points[BED])
    h.check("the count follows", dyke_rows.profile_row.saved.text() == "", dyke_rows.profile_row.saved.text())
    editor.close()
    dock.panel.folder.setFilePath(str(h.RUNS / "dropped"))
    yield from h.run(dock)
    back = next(o for o in objects(h.RUNS / "dropped") if o["kind"] == "channel_dyke")
    h.check("the job after Drop is the job of the fields, to the last key", back == plain_object, {k: (back.get(k), plain_object.get(k)) for k in set(back) | set(plain_object) if back.get(k) != plain_object.get(k)})
    h.check("the cached grid of the fields is used again", any(e.get("kind") == "grid_cache_hit" for e in h.events(h.RUNS / "dropped", "output")))

    h.log("=== 12 tops apart, on a channel with dykes given a top for each bank")
    wadi2 = h.add_vector(h.geojson("wadi2", [h.line(WADI, start=122.0, fall=0.0009, left=124.0, right=125.5)]), "wadi2", crs)
    s.layers["channel_dyke"].setLayer(wadi2)
    dyke_rows.fields["bed_start_z"].setField("start")
    dyke_rows.fields["bed_slope"].setField("fall")
    dyke_rows.fields["left_top_z"].setField("left")
    dyke_rows.fields["right_top_z"].setField("right")
    dyke_rows.fields["top_z"].setField("")
    dyke_rows.fields["name"].setField("")
    dyke_rows.profile_row.button.click()
    editor = dock.editor
    h.check("apart: the box is off", not editor.tied.isChecked() and not editor.model.tied)
    h.check("no name: the line goes by its number", editor.line_box.currentText() == "Line 1", editor.line_box.currentText())
    editor.close()

    h.log("=== 13 an embankment's crest")
    clear(dock)
    s.layers["embankment"].setLayer(bank)
    bank_rows.fields["crest_z"].setField("crest")
    bank_rows.fields["name"].setField("name")
    s.profile_rows["embankment"].button.click()
    editor = dock.editor
    model = editor.model
    h.check("one series, the crest", model.keys == (CREST,) and model.points[CREST][0] == [0.0, 125.0], model.points)
    at = model.length / 2.0
    point = editor.canvas.to_pixel(at, model.level(CREST, at)).toPoint()
    QTest.mouseDClick(editor.canvas, Qt.LeftButton, Qt.NoModifier, point)
    QApplication.processEvents()
    h.check("a point on the crest", len(model.points[CREST]) == 3, model.points[CREST])
    editor.table.item(1, 1).setText("126.5")
    middle = model.points[CREST][1][0]
    h.widget_shot("06_embankment", editor)
    h.check("Save", editor.save(), editor.words.text())
    editor.preview_button.click()
    yield lambda: not editor.waiting
    h.check("the preview draws its tops", editor.pane.item is not None and "left_top" in editor.pane.item, editor.words.text()[:200])
    tops = editor.pane.item
    n = min(range(len(tops["station"])), key=lambda i: abs(tops["station"][i] - middle))
    h.check("the engine's crest is the edited one", abs(tops["left_top"][n] - 126.5) < 0.05, tops["left_top"][n])
    h.widget_shot("07_embankment_previewed", editor)
    editor.close()

    h.log("=== 14 elevations: crest line, spillway, burn line")
    s.layers["crest_line"].setLayer(crest)
    s.fields["crest_line"]["crest_z"].setField("z")
    s.layers["spillway"].setLayer(spill)
    s.fields["spillway"]["crest_z"].setField("z")
    s.fields["spillway"]["coefficient"].setField("c")
    s.fields["spillway"]["length"].setField("l")
    s.layers["burn_line"].setLayer(burn)
    s.fields["burn_line"]["crest_z"].setField("z")
    h.check("each has its button", all(s.profile_rows[kind].isVisibleTo(s) for kind in ("crest_line", "spillway", "burn_line")))
    s.profile_rows["crest_line"].button.click()
    editor = dock.editor
    h.check("a crest line starts from its field", editor.model.points[CREST] == [[0.0, 122.0], [editor.model.points[CREST][1][0], 122.0]], editor.model.points)
    crest_length = editor.model.length
    editor.table.item(editor.table.rowCount() - 1, 0).setText("200")
    editor.table.item(1, 1).setText("123.2")
    h.widget_shot("08_crest_line", editor)
    editor.preview_button.click()
    yield lambda: not editor.waiting
    h.log(f"crest preview says: {editor.words.text()[:300]}")
    h.check("Save", editor.save(), editor.words.text())
    editor.close()
    s.profile_rows["spillway"].button.click()
    editor = dock.editor
    editor.table.item(0, 1).setText("123.8")
    h.check("Save", editor.save(), editor.words.text())
    editor.close()
    s.profile_rows["burn_line"].button.click()
    editor = dock.editor
    h.check("the burn line says invert", editor.model.labels[CREST] == "invert" and editor.radios[CREST].text() == "invert")
    editor.table.item(1, 1).setText("119.0")
    editor.preview_button.click()
    yield lambda: not editor.waiting
    h.check("a burn line previews its volume", "burn_line" in editor.words.text() and "cut" in editor.words.text(), editor.words.text()[:200])
    h.check("Save", editor.save(), editor.words.text())
    editor.close()
    dock.panel.folder.setFilePath(str(h.RUNS / "elevations"))
    yield from h.run(dock)
    folder = h.RUNS / "elevations"
    done = h.events(folder, "done")
    h.check("a run with all four edited", done and done[-1]["code"] == 0, dock.panel.message.text())
    written = {o["kind"]: o for o in objects(folder)}
    entry = written["crest_line"]
    h.check("the crest line's job has Z per vertex and an added vertex", entry["z"] == [122.0, 123.2, 122.0] and len(entry["coordinates"]) == 3 and "z_constant" not in entry, entry)
    h.check("the added vertex lies on the line", abs(((entry["coordinates"][1][0] - CREST_LINE[0][0]) ** 2 + (entry["coordinates"][1][1] - CREST_LINE[0][1]) ** 2) ** 0.5 - 200.0) < 1e-6, entry["coordinates"])
    h.check("its length is the same", abs(sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in itertools.pairwise(entry["coordinates"])) - crest_length) < 1e-6)
    h.check("the spillway keeps its C and length", written["spillway"]["z"][0] == 123.8 and written["spillway"]["coefficient"] == 2.1 and written["spillway"]["length"] == 30.0, written["spillway"])
    h.check("the burn line's job has its invert", written["burn_line"]["z"][-1] == 119.0, written["burn_line"])
    burned = []  # a burn only lowers: look where the edited invert stands under the ground
    for at in range(0, 500, 25):
        where = station_point(BURN, float(at))
        invert = 121.0 - 2.0 * at / 500.0
        if sample(ground.dem.source(), where) > invert + 0.5:
            burned.append((sample(folder / "terrain" / "terrain_modified.tif", where), invert))
    h.check("the ground took the burn at the edited invert", burned and all(abs(new - invert) < 0.3 for new, invert in burned), burned[:6])
    geo = json.loads((folder / "inputs" / "crest_line.geojson").read_text(encoding="utf-8"))
    h.check("the run folder holds what made it", geo["features"][0]["geometry"]["coordinates"][1][2] == 123.2, geo["features"][0]["geometry"]["coordinates"])

    h.log("=== 15 a line with no level, a drawn layer, a multi-part line")
    clear(dock)
    memory = QgsVectorLayer("LineString?crs=EPSG:32640", "drawn", "memory")
    project.addMapLayer(memory)
    feature = QgsFeature(memory.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in DRAIN]))
    memory.dataProvider().addFeature(feature)
    memory.updateExtents()
    s.layers["channel"].setLayer(memory)
    dock.panel.folder.setFilePath(str(h.RUNS / "drawn"))
    h.check("with no level a run is refused as before", any("needs a bed" in text for text in __import__("wadi2d_qgis.job_builder", fromlist=["problems"]).problems(dock._collect())))
    s.profile_rows["channel"].button.click()
    editor = dock.editor
    h.check("it starts on the ground, and says so", "start on the ground" in editor.words.text() and len(editor.model.points[BED]) == 3, editor.words.text())
    h.widget_shot("09_on_the_ground", editor)
    editor.table.item(1, 1).setText("116.0")
    h.check("Save for a layer with no file", editor.save(), editor.words.text())
    drawn_id = str(next(iter(memory.getFeatures())).id())
    h.check("into the temporary folder, not the project", "wadi2d_profiles" in str(profiles.table(memory, "channel", drawn_id)), drawn_id)
    editor.close()
    yield from h.run(dock)
    done = h.events(h.RUNS / "drawn", "done")
    h.check("a line given its bed by the editor alone runs", done and done[-1]["code"] == 0, dock.panel.message.text())
    multi = {"type": "Feature", "properties": {"name": "Two reaches"}, "geometry": {"type": "MultiLineString", "coordinates": [DRAIN, BURN]}}
    multi_layer = h.add_vector(h.geojson("multi", [multi]), "multi", crs)
    s.layers["channel"].setLayer(multi_layer)
    s.shaped["channel"].fields["name"].setField("name")
    s.profile_rows["channel"].button.click()
    editor = dock.editor
    h.check("each part is a line in the box", [editor.line_box.itemText(n) for n in range(editor.line_box.count())] == ["Two reaches", "Two reaches, part 2"], [editor.line_box.itemText(n) for n in range(editor.line_box.count())])
    editor.table.item(0, 1).setText("121.0")
    h.check("Save part 1", editor.save(), editor.words.text())
    editor.line_box.setCurrentIndex(1)
    editor.table.item(0, 1).setText("120.0")
    h.check("Save part 2", editor.save(), editor.words.text())
    names = sorted(p.name for p in (h.DATA / "multi_profiles").iterdir())
    h.check("one file each", len(names) == 2 and any("part2" in name for name in names), names)
    editor.close()
    parts = dock._collect()["structures"]["channel"]
    h.check("each part gets its own", parts[0].properties["table"] != parts[1].properties["table"], [p.properties.get("table") for p in parts])

    h.log("=== 16 unsaved edits and an open editor")
    s.profile_rows["channel"].button.click()
    editor = dock.editor
    editor.table.item(0, 1).setText("119.5")
    editor.ask = lambda *_: QMessageBox.Cancel
    h.check("Cancel keeps the editor open", editor.close() is False and editor.isVisible())
    s.profile_rows["channel"].button.click()
    h.check("a second click does not lose the edits", dock.editor is editor and editor.model.dirty)
    editor.ask = lambda *_: QMessageBox.Discard
    h.check("Discard closes it", editor.close() is True)
    QApplication.processEvents()
    s.profile_rows["channel"].button.click()
    editor = dock.editor
    editor.table.item(0, 1).setText("119.4")
    editor.ask = lambda *_: QMessageBox.Discard
    s.layers["channel"].setLayer(None)
    QApplication.processEvents()
    h.check("the layer going closes its editor", dock.editor is None)
    clear(dock)
    t.dem.setLayer(None)
    dock.structures.layers["channel"].setLayer(multi_layer)
    s.profile_rows["channel"].button.click()
    h.check("no DEM: said, and no editor", dock.editor is None and "DEM" in s.preview_label.text(), s.preview_label.text())
