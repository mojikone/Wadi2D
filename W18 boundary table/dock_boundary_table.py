"""D8 through the real dock: one line layer, a table of kinds and values, no fields needed; the field route stays."""

import json

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer


def cells(table, row):
    return table.cellWidget(row, 1), table.cellWidget(row, 2)


def job_of(folder):
    return json.loads((folder / "job.json").read_text(encoding="utf-8"))["boundaries"]


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()
    b = dock.boundaries
    table = b.table

    coords = [o["coordinates"] for o in ground.outlets_data]
    h.check("the Bidah job has two outlets", len(coords) == 2, len(coords))
    middle = len(coords[1]) // 2 or 1
    first, second = coords[1][: middle + 1], coords[1][middle:]
    if len(first) < 2 or len(second) < 2:  # a straight two-point line: split it at its midpoint
        (x0, y0), (x1, y1) = coords[1][0][:2], coords[1][-1][:2]
        mid = [(x0 + x1) / 2.0, (y0 + y1) / 2.0]
        first, second = [[x0, y0], mid], [mid, [x1, y1]]
    three = h.add_vector(h.geojson("three", [h.line(coords[0]), h.line(first), h.line(second)]), "three outlets", ground.crs)

    h.log("=== 1 a layer with no fields fills the table")
    h.check("the layer has no kind or value", [f.name() for f in three.fields()] in ([], ["fid"], ["id"]), [f.name() for f in three.fields()])
    h.check("no layer, no rows", table.rowCount() == 0, table.rowCount())
    b.layer.setLayer(three)
    h.check("one row per line", table.rowCount() == 3, table.rowCount())
    h.check("rows are numbered", [table.item(r, 0).text() for r in range(3)] == ["Line 1", "Line 2", "Line 3"])
    h.check("the name is not editable", not table.item(0, 0).flags() & 2)

    h.log("=== 2 Kind and Value set every line")
    b.kind.setCurrentText("normal")
    b.value.setValue(0.008)
    h.check("all rows follow the kind", [cells(table, r)[0].currentText() for r in range(3)] == ["normal"] * 3)
    h.check("all rows follow the value", [cells(table, r)[1].value() for r in range(3)] == [0.008] * 3)

    h.log("=== 3 each line its own")
    kind, value = cells(table, 0)
    kind.setCurrentText("stage")
    h.check("value filled by kind", value.value() == 0.0, value.value())
    h.check("stage takes any level", value.maximum() > 1000.0 and value.minimum() < -1000.0, (value.minimum(), value.maximum()))
    value.setValue(2.5)
    kind3, value3 = cells(table, 2)
    kind3.setCurrentText("free")
    h.check("free has no value", not value3.isEnabled())
    _, value2 = cells(table, 1)
    h.check("normal keeps the schema's bounds", value2.minimum() == 1e-05 and value2.maximum() == 0.5, (value2.minimum(), value2.maximum()))
    b.value.setValue(0.02)
    h.check("an untouched row still follows", value2.value() == 0.02, value2.value())
    h.check("an edited row stays", cells(table, 0)[1].value() == 2.5, cells(table, 0)[1].value())
    table.setCurrentCell(1, 0)  # flashes the line
    b.setCollapsed(False)
    b.resize(470, b.sizeHint().height())
    h.widget_shot("boundaries", b)

    h.log("=== 4 it reaches the engine")
    t = dock.terrain
    t.dem.setLayer(ground.dem)
    t.dx.setValue(20.0)
    t.domain.setLayer(ground.domain)
    dock.hydrology.rain.setValue(60.0)
    dock.hydrology.hours.setValue(1.0)
    dock.panel.duration.setValue(1.0)
    dock.panel.pixels.setChecked(False)
    dock.panel.folder.setFilePath(str(h.RUNS / "own"))
    yield from h.run(dock)
    folder = h.RUNS / "own"
    done = h.events(folder, "done")
    h.check("finished", done and done[-1]["code"] == 0, dock.panel.message.text())
    written = job_of(folder)
    h.check("three lines in the job", len(written) == 3, len(written))
    h.check("line 1 is a stage", written[0]["kind"] == "stage" and written[0]["stage"] == 2.5, written[0])
    h.check("line 2 is normal", written[1]["kind"] == "normal" and written[1]["slope"] == 0.02, written[1])
    h.check("line 3 is free", written[2]["kind"] == "free", written[2])
    resolved = json.loads((folder / "config.resolved.json").read_text(encoding="utf-8"))["boundaries"]
    h.check("the engine took them", [(r["kind"], r["stage"], r["slope"]) for r in resolved][:2] == [("stage", 2.5, 0.005), ("normal", 0.0, 0.02)], resolved[0])
    h.check("mass closes", abs(done[-1]["balance"]["relative_error"]) < 1e-5, done[-1]["balance"]["relative_error"])

    h.log("=== 5 the field route stays")
    b.layer.setLayer(ground.mixed)
    h.check("rows of the new layer", table.rowCount() == 2, table.rowCount())
    h.check("fields fill the table", [(cells(table, r)[0].currentText(), cells(table, r)[1].value()) for r in range(2)] == [("normal", 0.01)] * 2)
    b.kind.setCurrentText("free")
    h.check("fields outrank Kind", cells(table, 0)[0].currentText() == "normal")
    b.kind.setCurrentText("normal")
    cells(table, 1)[1].setValue(0.03)
    dock.panel.folder.setFilePath(str(h.RUNS / "fields"))
    yield from h.run(dock)
    written = job_of(h.RUNS / "fields")
    h.check("the field reaches the job", written[0]["slope"] == 0.01, written[0])
    h.check("an edit outranks the field", written[1]["slope"] == 0.03, written[1])

    h.log("=== 6 the table keeps up with the layer")
    memory = QgsVectorLayer("LineString?crs=EPSG:32640", "drawn", "memory")
    QgsProject.instance().addMapLayer(memory)
    x, y = coords[0][0][:2]

    def add(offset):
        feature = QgsFeature(memory.fields())
        feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x + offset, y), QgsPointXY(x + offset, y + 100.0)]))
        memory.dataProvider().addFeature(feature)
        memory.dataProvider().dataChanged.emit()
        memory.triggerRepaint()
        memory.dataChanged.emit()

    add(0.0)
    b.layer.setLayer(memory)
    h.check("a drawn layer has a row", table.rowCount() == 1, table.rowCount())
    cells(table, 0)[1].setValue(0.04)
    add(50.0)
    h.check("a new line appears", table.rowCount() == 2, table.rowCount())
    h.check("the edit survives", cells(table, 0)[1].value() == 0.04, cells(table, 0)[1].value())
    b.layer.setLayer(None)
    h.check("no layer, no rows again", table.rowCount() == 0)
    b.layer.setLayer(three)
    h.check("back to the layer, rows afresh", table.rowCount() == 3)
    memory.dataChanged.emit()  # the old layer is no longer watched
    h.check("the old layer is let go", table.rowCount() == 3)
