"""D3 through the real dock: a table of lines, near cell, rows, far cell, with the actual sizes beside them, on Bidah ground."""

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import w32dock  # noqa: E402

import json
import os
import subprocess
from pathlib import Path

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsRectangle
from qgis.PyQt.QtTest import QTest

MAIN_VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
"""A worktree has no .venv of its own; the engine still comes from the worktree, by the path in engine.py."""
NEAR, ROWS, FAR, ACTUAL_NEAR, ACTUAL_FAR = 1, 2, 3, 4, 5
STREAMS_OFF_KM2 = 100000.0


def box(table, row, column):
    return table.cellWidget(row, column)


def actual(table, row):
    return table.item(row, ACTUAL_NEAR).text(), table.item(row, ACTUAL_FAR).text()


def job_of(folder):
    return json.loads((folder / "job.json").read_text(encoding="utf-8"))


def grid_layer(h, run):
    group = h.group_of(run)
    setup = group.findGroup("Model setup") if group else None
    if setup is None:
        return None
    found = [node.layer() for node in setup.findLayers() if node.layer().name().startswith("Cell grid")]
    return found[0] if found else None


def tile_box(feature) -> QgsGeometry:
    return QgsGeometry.fromRect(feature.geometry().boundingBox())


def _added_a_line(layer, coordinates) -> bool:
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in coordinates]))
    layer.startEditing()
    layer.addFeature(feature)
    return layer.commitChanges()


def scenario(h):
    w32dock.setup(h)
    if not h.VENV.exists():
        h.VENV = MAIN_VENV
    stored = json.loads((Path(h.SCENARIO).parent / "wadi_line.geojson").read_text(encoding="utf-8"))
    wadi = stored["features"][0]["geometry"]["coordinates"]
    ground = h.Bidah()
    dock = yield from h.open_dock()
    m = dock.mesh
    t = m.lines
    table = t.table

    h.log("=== 0 what is under test")
    from wadi2d_qgis.protocol import clean_env

    code = f"import sys; sys.path.insert(0, r'{h.REPO}'); import wadi2d; print(wadi2d.__file__)"
    where = subprocess.run([str(h.VENV), "-c", code], capture_output=True, text=True, env=clean_env(dict(os.environ))).stdout.strip()
    h.check("the engine code is this checkout's", str(h.REPO) in where, where)
    h.check("the engine answering knows mesh lines", dock.schema.has("mesh.lines.near_dx"))
    h.check("the mesh is off by default", not m.enabled.isChecked())
    h.check("the table is off with the mesh", not table.isEnabled() and not t.layer.isEnabled())
    h.check("it says the ladder", "only doubles" in t.note.text(), t.note.text())

    h.log("=== 1 a layer with no fields fills the table")
    second = [[438700.0, 2727500.0], [438300.0, 2727100.0]]
    layer = h.add_vector(h.geojson("two", [h.line(wadi, name="Wadi"), h.line(second)]), "two lines", ground.crs)
    fields = h.add_vector(
        h.geojson("fields", [h.line(wadi, near_dx=20.0, rows=6, far_dx=40.0)]), "lines with fields", ground.crs
    )
    h.set_rain_job(dock, ground, "band", dx=10.0, sim_hours=0.3, pixels=False)
    m.setCollapsed(False)
    m.enabled.setChecked(True)
    m.coarse.setValue(40.0)
    m.fine_area.setValue(STREAMS_OFF_KM2)  # so that what the band refines is the line's own doing
    m.mid_area.setValue(STREAMS_OFF_KM2)
    h.check("the table is on with the mesh", table.isEnabled() and t.layer.isEnabled())
    h.check("no layer, no rows", table.rowCount() == 0, table.rowCount())
    t.layer.setLayer(layer)
    h.check("one row per line", table.rowCount() == 2, table.rowCount())
    h.check("names from the layer, numbers else", [table.item(r, 0).text() for r in range(2)] == ["Wadi", "Line 2"])
    h.check("the name is not editable", not table.item(0, 0).flags() & 2)
    h.check("near starts at the finest", box(table, 0, NEAR).value() == 10.0, box(table, 0, NEAR).value())
    h.check("far starts at the coarsest", box(table, 0, FAR).value() == 40.0, box(table, 0, FAR).value())
    h.check("rows start at the engine's default", box(table, 0, ROWS).value() == dock.schema.default("mesh.lines.rows"))
    h.check("rows take the engine's bounds", box(table, 0, ROWS).minimum() == 1 and box(table, 0, ROWS).maximum() == 1000)
    h.check("on the ladder nothing moves", actual(table, 0) == ("10", "40"), actual(table, 0))
    h.check("no rounding said", not t.rounded.isVisible() and not t.rounded.text(), t.rounded.text())

    h.log("=== 2 sizes off the ladder show what they become, before any run")
    box(table, 0, NEAR).setValue(15.0)
    box(table, 0, FAR).setValue(30.0)
    box(table, 0, ROWS).setValue(8.0)
    h.check("requested stays as typed", (box(table, 0, NEAR).value(), box(table, 0, FAR).value()) == (15.0, 30.0))
    h.check("actual near goes down", actual(table, 0)[0] == "10", actual(table, 0))
    h.check("actual far goes down", actual(table, 0)[1] == "20", actual(table, 0))
    h.check("a moved size stands out", table.item(0, ACTUAL_NEAR).font().bold())
    h.check("a size that did not move does not", not table.item(1, ACTUAL_NEAR).font().bold())
    h.check("the dock says it in words", t.rounded.text() == "Wadi: near 15 m becomes 10 m, far 30 m becomes 20 m.", t.rounded.text())
    h.check("the tooltip gives both", "15" in table.item(0, ACTUAL_NEAR).toolTip() and "10" in table.item(0, ACTUAL_NEAR).toolTip())
    box(table, 1, NEAR).setValue(5.0)
    h.check("below the finest holds at the finest", actual(table, 1)[0] == "10", actual(table, 1))
    box(table, 1, NEAR).setValue(10.0)
    typed = box(table, 1, NEAR)
    typed.lineEdit().selectAll()
    QTest.keyClicks(typed.lineEdit(), "25")
    h.check("typing keeps its keys, and Actual answers at once", typed.lineEdit().text() == "25" and actual(table, 1)[0] == "20", (typed.lineEdit().text(), actual(table, 1)))
    typed.setValue(10.0)
    m.resize(470, m.sizeHint().height())
    h.widget_shot("mesh_section", m)

    h.log("=== 3 the ladder follows the finest and the coarsest cell")
    dock.terrain.dx.setValue(5.0)
    h.check("line 1, a set near, stands on a finer ladder", actual(table, 0)[0] == "10" and box(table, 0, NEAR).value() == 15.0, actual(table, 0))
    dock.terrain.dx.setValue(12.0)
    h.check("the ladder is the snapped cell: 12 m on 5 m pixels is 10", actual(table, 0)[0] == "10", actual(table, 0))
    dock.terrain.dx.setValue(10.0)
    m.coarse.setValue(80.0)
    h.check("a far nobody set follows the coarsest", box(table, 1, FAR).value() == 80.0, box(table, 1, FAR).value())
    h.check("a far set by hand stays", box(table, 0, FAR).value() == 30.0, box(table, 0, FAR).value())
    m.coarse.setValue(40.0)

    h.log("=== 4 near above far is refused before a run")
    box(table, 1, FAR).setValue(5.0)
    dock.panel.run_button.click()
    h.check("refused in plain words", "near cell must not be larger" in dock.panel.message.text(), dock.panel.message.text())
    h.check("nothing started", dock.run is None)
    box(table, 1, FAR).setValue(40.0)

    h.log("=== 5 the preview: the engine's own numbers equal the table's")
    m.preview_button.click()
    yield lambda: "cells" in m.summary.text() or "failed" in m.summary.text().lower()
    h.log(f"preview says: {m.summary.text()}")
    h.check("the preview names the line", "Wadi: 10 m for 8 rows each side, no coarser than 20 m within 240 m" in m.summary.text(), m.summary.text())
    summary = json.loads((Path(dock._mesh_folder) / "mesh.json").read_text(encoding="utf-8"))
    table_says = [(table.item(r, 0).text(), *actual(table, r)) for r in range(2)]
    engine_says = [(s["name"], f"{s['near']:g}", f"{s['far']:g}") for s in summary["lines"]]
    h.check("table and engine agree, line by line", table_says == engine_says, (table_says, engine_says))
    h.check("a raster of tile sizes", dock._mesh_layer is not None)

    h.log("=== 6 a run on the band")
    yield from h.run(dock, 2400)
    folder = h.RUNS / "band"
    w32dock.record(h, folder, 'band')
    done = h.events(folder, "done")
    h.check("finished", done and done[-1]["code"] == 0, dock.panel.message.text())
    written = job_of(folder)["mesh"]["lines"]
    h.check("the job holds what was asked", (written[0]["near_dx"], written[0]["rows"], written[0]["far_dx"]) == (15.0, 8, 30.0), written[0])
    h.check("two lines in the job", len(written) == 2, len(written))
    h.check("the lines are on file", (folder / "inputs" / "mesh_lines.geojson").is_file())
    resolved = json.loads((folder / "config.resolved.json").read_text(encoding="utf-8"))["mesh"]["lines"]
    h.check("the engine took them", resolved[0]["near_dx"] == 15.0 and resolved[0]["name"] == "Wadi", resolved[0]["name"])
    warned = [e["message"] for e in h.events(folder, "warn")]
    h.check("the run says what it rounded", any("Wadi" in w and "15 m" in w and "10 m" in w for w in warned), warned)
    said = h.LOG.read_text(encoding="utf-8")
    h.check("the dock said it on starting", "Wadi: near 15 m becomes 10 m" in said)
    h.check("mass closes", abs(done[-1]["balance"]["relative_error"]) < 1e-5, done[-1]["balance"]["relative_error"])

    grid = grid_layer(h, "band")
    start = h.events(folder, "start")[-1]
    h.check("cell grid in Model setup", grid is not None)
    h.check("its cells are the solver's", sum(f["cells"] for f in grid.getFeatures()) == start["cells"])
    line = QgsGeometry.fromPolylineXY([QgsPointXY(p[0], p[1]) for p in wadi])
    touched = [f for f in grid.getFeatures() if tile_box(f).intersects(line)]
    h.check("every tile on the line is at near size", touched and all(f["cell_m"] == 10.0 for f in touched), len(touched))
    band = line.buffer(80.0, 8)
    within = [f for f in grid.getFeatures() if tile_box(f).intersects(band)]
    h.check("every tile within the 8 rows is at near size", all(f["cell_m"] == 10.0 for f in within), len(within))
    sizes = sorted({f["cell_m"] for f in grid.getFeatures()})
    h.check("three sizes on the map", sizes == [10.0, 20.0, 40.0], sizes)
    fine_tiles = sum(1 for f in grid.getFeatures() if f["cell_m"] == 10.0)
    coarse_tiles = sum(1 for f in grid.getFeatures() if f["cell_m"] == 40.0)
    h.log(f"tiles: {fine_tiles} of 10 m, {coarse_tiles} of 40 m, of {grid.featureCount()}")
    far_off = [f for f in grid.getFeatures() if not tile_box(f).intersects(line.buffer(2000.0, 8))]
    h.check("away from the line nothing asks for fine cells", far_off and all(f["cell_m"] > 10.0 for f in far_off), len(far_off))
    shown = h.add_vector(h.geojson("wadi_only", [h.line(wadi)]), "wadi", ground.crs)
    middle = QgsGeometry.fromPolylineXY([QgsPointXY(*p[:2]) for p in wadi]).interpolate(line.length() / 2.0).asPoint()
    h.render("band_near", [grid, shown, ground.dem], middle, 4000)
    h.render("band", [grid, shown, ground.dem], middle, 9000)
    extent = grid.extent()
    h.log(f"grid extent {QgsRectangle(extent).toString(0)}")
    h.render("band_whole", [grid, shown, ground.dem], extent.center(), 9900, size=(1400, 1000))

    h.log("=== 7 a mesh with no lines through the same dock: fewer cells, and no lines in the job")
    t.layer.setLayer(None)
    h.check("no layer, no rows again", table.rowCount() == 0, table.rowCount())
    h.set_rain_job(dock, ground, "no_lines", dx=10.0, sim_hours=0.3, pixels=False)
    yield from h.run(dock, 2400)
    plain = h.RUNS / "no_lines"
    w32dock.record(h, plain, 'no_lines')
    h.check("no lines key", "lines" not in job_of(plain)["mesh"], list(job_of(plain)["mesh"]))
    h.check("no lines file", not (plain / "inputs" / "mesh_lines.geojson").exists())
    other = h.events(plain, "start")[-1]
    h.check("the band added cells", start["cells"] > other["cells"], (start["cells"], other["cells"]))

    h.log("=== 8 fields fill a row by themselves")
    t.layer.setLayer(fields)
    h.check("near from its field", box(table, 0, NEAR).value() == 20.0, box(table, 0, NEAR).value())
    h.check("rows from its field", box(table, 0, ROWS).value() == 6.0, box(table, 0, ROWS).value())
    h.check("far from its field", box(table, 0, FAR).value() == 40.0, box(table, 0, FAR).value())
    h.check("on the ladder", actual(table, 0) == ("20", "40") and not t.rounded.text(), actual(table, 0))
    box(table, 0, ROWS).setValue(9.0)
    h.check("a set row stays through an edit of the layer", _added_a_line(fields, second) and table.rowCount() == 2 and box(table, 0, ROWS).value() == 9.0, table.rowCount())
    h.check("the new line starts afresh", box(table, 1, ROWS).value() == dock.schema.default("mesh.lines.rows"), box(table, 1, ROWS).value())

    h.log("=== 8b a layer that leaves the project takes its rows with it")
    QgsProject.instance().removeMapLayer(fields.id())
    left = t.layer.currentLayer()
    h.check("the rows follow the picker, with no error", table.rowCount() == (left.featureCount() if left else 0), (left.name() if left else None, table.rowCount()))
    t.layer.setLayer(layer)
    h.check("another layer fills it again", table.rowCount() == 2, table.rowCount())

    h.log("=== 9 a line off the domain is refused, not ignored")
    away = h.add_vector(h.geojson("away", [h.line([[400000.0, 2600000.0], [400500.0, 2600000.0]], name="Far away")]), "away", ground.crs)
    t.layer.setLayer(away)
    h.set_rain_job(dock, ground, "away", dx=10.0, sim_hours=0.1, pixels=False)
    yield from h.run(dock, 2400)
    h.check("refused by name", "Far away" in dock.panel.message.text() and "domain" in dock.panel.message.text(), dock.panel.message.text())

    h.log("=== 10 the mesh off: the uniform job, lines ignored")
    t.layer.setLayer(layer)
    m.enabled.setChecked(False)
    h.check("the table is off again", not table.isEnabled())
    dock.mesh.local_steps.setChecked(False)
    h.set_rain_job(dock, ground, "uniform", dx=20.0, sim_hours=0.1, pixels=False)
    yield from h.run(dock, 2400)
    uniform = h.RUNS / "uniform"
    w32dock.record(h, uniform, 'uniform')
    h.check("finished", h.events(uniform, "done")[-1]["code"] == 0, dock.panel.message.text())
    h.check("no mesh in the job", "mesh" not in job_of(uniform), list(job_of(uniform)))
    h.check("one cell size", {f["cell_m"] for f in grid_layer(h, "uniform").getFeatures()} == {20.0})
    QgsProject.instance().setDirty(False)
