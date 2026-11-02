# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""On QGIS's own Python, offscreen: the profile editor with real mouse and key events, and the section around it.

Started by ``test_editor_qgis.py``. Arguments: a DEM, a throwaway folder. Prints ``EDITOR PASSED`` as its last line.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "plugin"))
DEM, FOLDER = Path(sys.argv[1]), Path(sys.argv[2])

from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer  # noqa: E402
from qgis.PyQt.QtCore import QEvent, QPoint, QPointF, Qt, QTimer  # noqa: E402
from qgis.PyQt.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from qgis.PyQt.QtTest import QTest  # noqa: E402
from qgis.PyQt.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QgsApplication([], True)
app.initQgis()

from wadi2d_qgis.profile_editor import ProfileEditor  # noqa: E402
from wadi2d_qgis.profile_table import BED, LEFT, RIGHT, ProfileStore, profile_folder, read_rows  # noqa: E402
from wadi2d_qgis.sections.structures import StructuresSection  # noqa: E402

X0, Y0 = 400000.0, 2700000.0
schema = None


def fail(condition, text) -> None:
    if not condition:
        raise AssertionError(text)


def geojson(name: str, features: list) -> Path:
    crs = {"type": "name", "properties": {"name": "EPSG:32640"}}
    path = FOLDER / f"{name}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "crs": crs, "features": features}), encoding="utf-8")
    return path


def line(coordinates, **properties) -> dict:
    return {"type": "Feature", "properties": properties, "geometry": {"type": "LineString", "coordinates": coordinates}}


def add_vector(path: Path, name: str):
    layer = QgsVectorLayer(str(path), name, "ogr")
    fail(layer.isValid(), f"layer {name}")
    QgsProject.instance().addMapLayer(layer)
    return layer


dem = QgsRasterLayer(str(DEM), "dem")
fail(dem.isValid(), "the DEM")
QgsProject.instance().addMapLayer(dem)
crs = dem.crs()
A, B, C = [X0 + 20.0, Y0 - 100.0], [X0 + 320.0, Y0 - 100.0], [X0 + 320.0, Y0 - 300.0]
dykes = add_vector(geojson("dykes", [
    line([A, B, C], name="First", bed=99.0, top=104.0),
    line([C, [X0 + 100.0, Y0 - 300.0]], name="Second", bed=98.0, top=103.0),
]), "dykes")  # fmt: skip
crests = add_vector(geojson("crests", [line([A, B], z=101.0)]), "crests")

section = StructuresSection()
section.layers["channel_dyke"].setLayer(dykes)
rows = section.shaped["channel_dyke"]
rows.fields["crest_z"].setField("bed")
rows.fields["top_z"].setField("top")
rows.fields["name"].setField("name")
section.layers["crest_line"].setLayer(crests)
section.fields["crest_line"]["crest_z"].setField("z")
fail(section.profile_rows["channel_dyke"].button.text() == "Edit profile...", "the button")
fail("wall" not in section.profile_rows, "a wall has no level to edit")

asked = []
section.edit_requested.connect(asked.append)
section.profile_rows["channel_dyke"].button.click()
section.profile_rows["crest_line"].button.click()
fail(asked == ["channel_dyke", "crest_line"], asked)

before = section.values(crs)["structures"]
fail("fid" not in before["channel_dyke"][0].properties, "the id leaves the section")
fail(before["channel_dyke"][0].properties.get("table") is None, "no table yet")
fail(before["crest_line"][0].properties == {"crest_z": 101.0}, before["crest_line"][0].properties)
fail(len(before["crest_line"][0].coordinates[0]) == 2, "no Z yet")

lines = section.lines("channel_dyke", crs)
fail([item.label for item in lines] == ["First", "Second"], [item.label for item in lines])
editor = ProfileEditor("channel_dyke", dykes, lambda: section.lines("channel_dyke", crs), dem, section.profiles)
editor.resize(1180, 900)
editor.show()
QApplication.processEvents()
canvas = editor.canvas
model = editor.model

fail(editor.table.rowCount() == 3, "two stations and the blank row")
fail(model.tied, "one top field: the tops start together")
fail(editor.tied.isChecked() and editor.tied.isVisible(), "the box shows it")
fail(len(editor.canvas.ground) > 50, len(editor.canvas.ground))
slope = editor.canvas.ground[-1][1] - editor.canvas.ground[0][1]
fail(slope < -5.0, f"the ground falls along the line: {slope}")
fail(not editor.drop_button.isEnabled(), "nothing to drop yet")
fail("fields of the layer" in editor.route.text(), editor.route.text())


def pixel(key: str, index: int) -> QPoint:
    return canvas.to_pixel(*model.points[key][index]).toPoint()


def double_click(point: QPoint) -> None:
    QTest.mouseDClick(canvas, Qt.LeftButton, Qt.NoModifier, point)


def move(point: QPoint, modifiers) -> None:
    """A real move event: QTest.mouseMove only moves the cursor, and offscreen that sends nothing."""
    event = QMouseEvent(
        QEvent.MouseMove, QPointF(point), QPointF(canvas.mapToGlobal(point)), Qt.NoButton, Qt.LeftButton, modifiers
    )
    QApplication.sendEvent(canvas, event)


def drag(start: QPoint, end: QPoint, modifiers=Qt.NoModifier) -> None:
    QTest.mousePress(canvas, Qt.LeftButton, modifiers, start)
    move(QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2), modifiers)
    move(end, modifiers)
    QTest.mouseRelease(canvas, Qt.LeftButton, modifiers, end)
    QApplication.processEvents()


# A point added by a double-click, on the nearest series, in the table at once.
middle = canvas.to_pixel(250.0, model.level(LEFT, 250.0)).toPoint()
double_click(middle + QPoint(0, 2))
fail(len(model.points[LEFT]) == 3, model.points[LEFT])
fail(len(model.points[RIGHT]) == 3, "tied: both tops get it")
fail(editor.table.rowCount() == 4, editor.table.rowCount())
fail(model.can_undo, "the add can be undone")

# A drag, through the real event loop, ending in one undo step.
steps_before = len(model._undo)
start = pixel(LEFT, 1)
target = QPoint(start.x() + 40, start.y() + 30)
drag(start, target)
fail(len(model._undo) == steps_before + 1, "one drag, one undo")
held = model.points[LEFT][1]
at = canvas.to_data(target)
fail(abs(held[0] - at[0]) < 1.0 and abs(held[1] - at[1]) < 0.1, (held, at))
fail(model.points[RIGHT][1] == held, "tied: both tops moved")
fail(abs(held[0] * 10 - round(held[0] * 10)) < 1e-6, "a drag lands on 0.1 m")
fail(editor.table.item(1, 2).text() == format(held[1], ".10g"), editor.table.item(1, 2).text())

# Shift holds the station.
start = pixel(LEFT, 1)
was = model.points[LEFT][1][0]
drag(start, QPoint(start.x() + 60, start.y() - 25), Qt.ShiftModifier)
fail(model.points[LEFT][1][0] == was, "Shift holds the station")

# Undo and redo from the keyboard and the buttons.
level = model.points[LEFT][1][1]
QTest.keyClick(editor, Qt.Key_Z, Qt.ControlModifier)
QApplication.processEvents()
fail(model.points[LEFT][1][1] != level, "Ctrl+Z")
QTest.keyClick(editor, Qt.Key_Y, Qt.ControlModifier)
QApplication.processEvents()
fail(model.points[LEFT][1][1] == level, "Ctrl+Y")
editor.undo_button.click()
editor.redo_button.click()
fail(model.points[LEFT][1][1] == level, "the buttons")

# The ends of the line keep their stations.
start = pixel(BED, 0)
drag(start, QPoint(start.x() + 80, start.y() + 10))
fail(model.points[BED][0][0] == 0.0, "station 0 stays")

# Apart, a top moves alone.
editor.tied.setChecked(False)
fail(not model.tied, "the box drives the model")
right = model.points[RIGHT][1][1]
start = pixel(LEFT, 1)
drag(start, QPoint(start.x(), start.y() + 15))
fail(model.points[RIGHT][1][1] == right, "apart")
fail(canvas.active == LEFT and editor.radios[LEFT].isChecked(), "the series in hand shows")

# The wheel zooms along the line, and Whole line comes back.
span = canvas.x_range[1] - canvas.x_range[0]
canvas.x_range = (canvas.x_range[0], canvas.x_range[0] + span / 2.0)
editor.fit_button.click()
fail(canvas.x_range[1] - canvas.x_range[0] == span, "Whole line")

# A typed level outside the frame brings the frame with it; a zoomed view stays where it was put.
level = model.points[BED][0][1]
editor.table.item(0, 1).setText(str(canvas.y_range[1] + 20.0))
fail(canvas.y_range[0] <= model.points[BED][0][1] <= canvas.y_range[1], canvas.y_range)
editor.undo()
editor.fit_button.click()
canvas.whole = False
held_view = canvas.y_range
editor.table.item(0, 1).setText(str(canvas.y_range[1] + 20.0))
fail(canvas.y_range == held_view, "a zoomed view stays")
editor.undo()
fail(model.points[BED][0][1] == level, level)
editor.fit_button.click()



def wheel(point: QPoint, clicks: int, modifiers=Qt.NoModifier) -> None:
    local, turn = QPointF(point), QPoint(0, 120 * clicks)
    event = QWheelEvent(
        local, QPointF(canvas.mapToGlobal(point)), QPoint(0, 0), turn, Qt.NoButton, modifiers, Qt.NoScrollPhase, False
    )
    QApplication.sendEvent(canvas, event)


def choose_from_menu(press, number: int) -> None:
    """Press, and take an entry of the menu that opens: a menu holds the event loop until it is answered."""

    def answer() -> None:
        menu = QApplication.activePopupWidget()
        fail(menu is not None, "the menu opens")
        action = menu.actions()[number]
        menu.close()
        action.trigger()

    QTimer.singleShot(50, answer)
    press()


# The wheel zooms along the line around the mouse, Ctrl and the wheel zoom the levels, the middle button pans.
editor.fit_button.click()
whole_x, whole_y = canvas.x_range, canvas.y_range
middle = canvas.rect().center()
under = canvas.to_data(QPointF(middle))
wheel(middle, 1)
fail(canvas.x_range[1] - canvas.x_range[0] < whole_x[1] - whole_x[0], "the wheel zooms in")
fail(canvas.y_range == whole_y, "and leaves the levels")
fail(abs(canvas.to_data(QPointF(middle))[0] - under[0]) < 0.01, "around the mouse")
fail(not canvas.whole, "and the view is no longer the whole line")
wheel(middle, 1, Qt.ControlModifier)
fail(canvas.y_range[1] - canvas.y_range[0] < whole_y[1] - whole_y[0], "Ctrl zooms the levels")
held_x = canvas.x_range
QTest.mousePress(canvas, Qt.MiddleButton, Qt.NoModifier, middle)
pan = QMouseEvent(QEvent.MouseMove, QPointF(middle + QPoint(40, 0)), QPointF(canvas.mapToGlobal(middle)), Qt.NoButton, Qt.MiddleButton, Qt.NoModifier)
QApplication.sendEvent(canvas, pan)
QTest.mouseRelease(canvas, Qt.MiddleButton, Qt.NoModifier, middle + QPoint(40, 0))
fail(canvas.x_range[0] < held_x[0], "the middle button pans")
editor.fit_button.click()
fail(canvas.x_range == whole_x and canvas.y_range == whole_y and canvas.whole, "Whole line again")

# The right button: a menu on a point, another on the plot.
count = len(model.points[LEFT])
start = pixel(LEFT, 1)
choose_from_menu(lambda: QTest.mouseClick(canvas, Qt.RightButton, Qt.NoModifier, start), 0)
fail(len(model.points[LEFT]) == count - 1, "Delete this point")
editor.undo()
empty = canvas.to_pixel(0.5 * (model.points[BED][0][0] + model.points[BED][1][0]), model.points[BED][0][1] - 3.0).toPoint()
choose_from_menu(lambda: QTest.mouseClick(canvas, Qt.RightButton, Qt.NoModifier, empty), 0)
fail(canvas.selected is not None, "Add a point here")
editor.undo()

# Delete from the keyboard: the selected point.
count = len(model.points[LEFT])
start = pixel(LEFT, 1)
QTest.mouseClick(canvas, Qt.LeftButton, Qt.NoModifier, start)
QTest.keyClick(canvas, Qt.Key_Delete)
fail(len(model.points[LEFT]) == count - 1, "Delete")
editor.undo()
fail(len(model.points[LEFT]) == count, "and back")

# The table takes typing: a level, a new row, a bad number, a station out of its place.
item = editor.table.item(0, 1)
item.setText("98.5")
fail(model.points[BED][0] == [0.0, 98.5], model.points[BED][0])
blank = editor.table.rowCount() - 1
editor.table.item(blank, 0).setText("400")
fail(model.at(BED, 400.0) is not None, "a new row")
item = editor.table.item(0, 1)
item.setText("abc")
fail("not a number" in editor.words.text(), editor.words.text())
fail(editor.table.item(0, 1).text() == "98.5", "the cell comes back")
editor.table.item(editor.table.rowCount() - 1, 1).setText("7")
fail("station first" in editor.words.text(), editor.words.text())
editor.table.setCurrentCell(1, 0)
stations = model.stations()
editor.delete_row.click()
fail(len(model.stations()) == len(stations) - 1, "Delete row")

# A paste from a spreadsheet.
QApplication.clipboard().setText("100\t98.8\t\t\n150\t98.7\t104\t104\n")
editor.table.setCurrentCell(0, 0)
editor.table.setFocus()
QTest.keyClick(editor.table, Qt.Key_V, Qt.ControlModifier)
fail(model.at(BED, 150.0) is not None and model.level(BED, 150.0) == 98.7, "a paste")

# What cannot be built is refused before the engine sees it.
good = model.points[RIGHT][0][1]
model.begin()
model.drag(RIGHT, 0, 0.0, 10.0)
model.end()
editor.refresh()
fail(editor.save() is False, "a top under the bed is not saved")
fail("below the bed at station 0" in editor.words.text(), editor.words.text())
editor.undo()
fail(model.points[RIGHT][0][1] == good, "undo")

# Unsaved edits are not lost by changing line, and Save there goes to the line in the plot, not the one chosen.
first_points = json.dumps(model.points)
editor.ask = lambda *_: QMessageBox.Cancel
editor.line_box.setCurrentIndex(1)
fail(editor.line_box.currentIndex() == 0 and editor.line.label == "First", "Cancel stays")
fail(editor.model is model, "the same points")
editor.ask = lambda *_: QMessageBox.Save
editor.line_box.setCurrentIndex(1)
fail(editor.line.label == "Second", "Save goes on")
folder = profile_folder(dykes)
first_file = folder / "channel_dyke_line_0.csv"
second_file = folder / "channel_dyke_line_1.csv"
fail(first_file.is_file() and not second_file.is_file(), "saved for the line it belongs to")
editor.ask = lambda *_: QMessageBox.Discard
fail(not editor.model.dirty, "the second line starts clean")

# The file holds the columns the engine reads, and comes back in the editor.
with first_file.open(encoding="utf-8") as stream:
    saved = list(csv.DictReader(stream))
fail(list(saved[0]) == ["station", "bed_z", "left_top_z", "right_top_z"], list(saved[0]))
fail(saved[0]["bed_z"] == "98.5", saved[0])
editor.line_box.setCurrentIndex(0)
fail(json.dumps(editor.model.points) == first_points, f"the saved points come back: {editor.model.points} {first_points}")
fail(editor.drop_button.isEnabled() and "saved profile" in editor.route.text(), editor.route.text())
fail(section.profiles.count(dykes, "channel_dyke") == 1, "counted")
section.refresh_profiles()
fail("1 saved" in section.profile_rows["channel_dyke"].saved.text(), section.profile_rows["channel_dyke"].saved.text())

# A saved profile reaches what the section gives the job, for that line alone, and outranks a chosen table.
table = FOLDER / "shared.csv"
table.write_text("station,bed_z\n0,50\n", encoding="utf-8")
rows.table.setFilePath(str(table))
structures = section.values(crs)["structures"]
fail(structures["channel_dyke"][0].properties["table"] == str(first_file), "the edit outranks the table")
fail(structures["channel_dyke"][1].properties["table"] == str(table), "the other line keeps the table")

# Drop goes back; the file stays under another name.
editor.drop_button.click()
fail(not first_file.is_file(), "out of use")
fail(first_file.with_name(first_file.name + ".dropped").is_file(), "not destroyed")
fail(editor.model.points[BED][0] == [0.0, 50.0], "back to the table")
rows.table.setFilePath("")
editor.close()
fail(not editor.isVisible(), "closed")
fail(section.values(crs)["structures"]["channel_dyke"][0].properties.get("table") is None, "as it was")

# An elevation kind: its profile lands on the vertices, and the field gives way.
editor = ProfileEditor("crest_line", crests, lambda: section.lines("crest_line", crs), dem, section.profiles)
editor.show()
fail(editor.model.keys == ("crest_z",), editor.model.keys)
fail(not editor.tied.isVisible(), "no tops here")
editor.model.begin()
editor.model.add("crest_z", 120.0, 103.0)
editor.model.end()
fail(editor.save(), editor.words.text())
fail(read_rows(profile_folder(crests) / "crest_line_line_0.csv")[1] == {"station": 120.0, "crest_z": 103.0}, "the file")
feature = section.values(crs)["structures"]["crest_line"][0]
fail(feature.vertex_z() == [101.0, 103.0, 101.0], feature.vertex_z())
fail("crest_z" not in feature.properties, "the field gives way")

# The folder box: another folder for this layer, kept on the layer, and a folder that cannot be written is said.
other = FOLDER / "my profiles"
editor.folder.setFilePath(str(other))
fail(crests.customProperty("wadi2d/profile_folder") == str(other), "kept on the layer")
fail(profile_folder(crests) == other, "the store follows it")
fail(section.values(crs)["structures"]["crest_line"][0].vertex_z() is None, "the old folder's file is no longer found")
fail("fields of the layer" in editor.route.text(), editor.route.text())
fail(editor.save(), editor.words.text())
fail((other / "crest_line_line_0.csv").is_file(), "saved in the new folder")
blocked = FOLDER / "a file"
blocked.write_text("x", encoding="utf-8")
editor.folder.setFilePath(str(blocked))
fail(editor.save() is False, "a folder that is a file")
fail("could not be written" in editor.words.text(), editor.words.text())
editor.folder.setFilePath("")
fail(crests.customProperty("wadi2d/profile_folder") is None, "cleared")
fail(profile_folder(crests) == FOLDER / "crests_profiles", "back beside the layer")
editor.ask = lambda *_: QMessageBox.Discard
editor.close()

# A hole under the line and a broken table are said, not raised.
store = ProfileStore()
broken = FOLDER / "broken.csv"
broken.write_text("station,bed_z\n0,x\n", encoding="utf-8")
lines = section.lines("channel_dyke", crs)
lines[0] = type(lines[0])(**{**lines[0].__dict__, "table": str(broken)})
editor = ProfileEditor("channel_dyke", dykes, lambda: lines, dem, store)
fail("Showing the line without it" in editor.words.text(), editor.words.text())
editor.close()

print("EDITOR PASSED")
