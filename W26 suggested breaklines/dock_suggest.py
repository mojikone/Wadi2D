"""D4 through the real dock: Suggest breaklines on Bidah, the layer editable, one line deleted, the rest run as crest lines."""

import json
import sqlite3

from qgis.core import QgsGeometry, QgsPointXY, QgsProject, QgsWkbTypes

COLUMNS = ["name", "kind", "side", "height_m", "length_m", "area_km2", "slope", "score", "why", "near_dx", "rows", "far_dx"]


def layers_named(prefix):
    return [ly for ly in QgsProject.instance().mapLayers().values() if ly.name().startswith(prefix)]


def rows(layer):
    return [{name: f[name] for name in COLUMNS} for f in layer.getFeatures()]


def scenario(h):
    from pathlib import Path

    h.VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")  # a worktree has no venv; the engine code is still this checkout's
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from wadi2d_qgis import suggest_lines  # on the path once the dock is open

    m = dock.mesh
    h.check("button in the Mesh section", m.suggest_button.text() == "Suggest breaklines", m.suggest_button.text())
    h.check("mesh need not be ticked", not m.enabled.isChecked() and m.suggest_button.isEnabled())

    h.log("=== 1 without a DEM")
    dock.terrain.dem.setLayer(None)
    m.suggest_button.click()
    h.check("refused without a DEM", "DEM" in dock.panel.message.text(), dock.panel.message.text())

    h.log("=== 2 Bidah at 10 m")
    h.set_rain_job(dock, ground, "banks", dx=10.0, sim_hours=0.5)
    m.setCollapsed(False)
    h.widget_shot("mesh_section", m)
    m.suggest_button.click()
    h.check("says it is working", dock.panel.message.text() == suggest_lines.WORKING, dock.panel.message.text())
    yield lambda: dock.panel.message.text() != suggest_lines.WORKING
    text = dock.panel.message.text()
    h.check("suggested", text.startswith("Suggested"), text)
    folder = h.RUNS / "banks_breaklines"
    gpkg = folder / "suggested_breaklines.gpkg"
    h.check("file beside the run folder", gpkg.is_file(), gpkg)
    lines = layers_named("Suggested breaklines")
    refs = layers_named("Thalwegs")
    h.check("one suggestion layer, one thalweg layer", len(lines) == 1 and len(refs) == 1, (len(lines), len(refs)))
    layer, thalwegs = lines[0], refs[0]
    h.check("layer is valid and in editing", layer.isValid() and layer.isEditable(), layer.name())
    h.check("thalwegs are read-only", thalwegs.readOnly())
    h.check("fields", [f.name() for f in layer.fields()][1:] == COLUMNS, [f.name() for f in layer.fields()])
    h.check("vertices carry Z", QgsWkbTypes.hasZ(layer.wkbType()), QgsWkbTypes.displayString(layer.wkbType()))
    h.check("in the DEM's CRS", layer.crs() == ground.crs, layer.crs().authid())
    table = rows(layer)
    counts = {}
    for r in table:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    h.log(f"kinds {counts}; first rows {[(r['kind'], r['side'], round(r['height_m'], 2), round(r['length_m'])) for r in table[:6]]}")
    h.check("banks and crests found", counts.get("stream bank", 0) >= 2 and sum(counts.values()) > counts.get("stream bank", 0), counts)
    scores = [r["score"] for r in table]
    h.check("biggest first", scores == sorted(scores, reverse=True), scores[:5])
    h.check("name counts them", layer.name() == f"Suggested breaklines: {counts.get('stream bank', 0)} banks, {sum(counts.values()) - counts.get('stream bank', 0)} crests", layer.name())
    h.check("every line has a reason", all(r["why"] for r in table))
    h.check("kinds are the four", set(counts) <= {"stream bank", "road", "dam", "other crest"}, set(counts))

    ref = QgsGeometry.unaryUnion([f.geometry() for f in thalwegs.getFeatures()])
    nearest = []
    for f in layer.getFeatures():
        if f["kind"] == "stream bank":
            for v in f.geometry().vertices():
                nearest.append(ref.distance(QgsGeometry.fromPointXY(QgsPointXY(v.x(), v.y()))))
    h.check("no bank vertex within a cell of a thalweg", nearest and min(nearest) >= 10.0 - 0.01, (round(min(nearest), 1) if nearest else None, len(nearest)))
    h.log(f"bank vertex distance to thalweg: min {min(nearest):.1f}, median {sorted(nearest)[len(nearest) // 2]:.1f}")

    with sqlite3.connect(gpkg) as db:
        n_file = db.execute("SELECT count(*) FROM breaklines").fetchone()[0]
    h.check("the layer is the file", layer.featureCount() == n_file, (layer.featureCount(), n_file))

    centre = layer.extent().center()
    h.render("lines_all", [layer, thalwegs, ground.dem], centre, 40000)
    first = next(layer.getFeatures())
    h.render("lines_near", [layer, thalwegs, ground.dem], first.geometry().centroid().asPoint(), 6000)
    h.render("lines_close", [layer, thalwegs, ground.dem], first.geometry().centroid().asPoint(), 2000)

    h.log("=== 2b the same layer fills the Mesh table")
    m.enabled.setChecked(True)
    m.lines.layer.setLayer(layer)
    yield lambda: m.lines.table.rowCount() == layer.featureCount()
    h.check("mesh table has a row per line", m.lines.table.rowCount() == layer.featureCount(), (m.lines.table.rowCount(), layer.featureCount()))
    first_row = m.lines.rows[0]
    h.check("mesh table reads near, rows and far from the layer", (first_row.near, first_row.rows, first_row.far) == (10.0, 4, 40.0) and first_row.near_pinned, (first_row.near, first_row.rows, first_row.far))
    h.widget_shot("mesh_table", m)
    m.lines.layer.setLayer(None)
    m.enabled.setChecked(False)

    h.log("=== 3 delete one line and save")
    fid = first.id()
    layer.deleteFeature(fid)
    h.check("deleted in the buffer", layer.featureCount() == n_file - 1)
    h.check("saved", layer.commitChanges(), layer.commitErrors())
    with sqlite3.connect(gpkg) as db:
        n_after = db.execute("SELECT count(*) FROM breaklines").fetchone()[0]
    h.check("the file lost it too", n_after == n_file - 1, (n_after, n_file))

    h.log("=== 4 the rest run as crest lines, no field needed")
    s = dock.structures
    s.setCollapsed(False)
    s.layers["crest_line"].setLayer(layer)
    dock.panel.folder.setFilePath(str(h.RUNS / "with_lines"))
    yield from h.run(dock)
    folder = h.RUNS / "with_lines"
    done = h.events(folder, "done")
    h.check("run finished", done and done[-1]["code"] == 0, dock.panel.message.text())
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    objects = job["terrain"]["objects"]
    h.check("every line became a crest line", len(objects) == n_after and all(o["kind"] == "crest_line" for o in objects), (len(objects), n_after))
    h.check("each with its vertex elevations", all(len(o.get("z", [])) == len(o["coordinates"]) >= 2 for o in objects))
    start = h.events(folder, "start")[-1]
    h.log(f"run with lines: cells {start['cells']}, peaks {h.peaks(folder)}")
    s.layers["crest_line"].setLayer(None)

    h.log("=== 5 a second click replaces the layers")
    dock.panel.folder.setFilePath(str(h.RUNS / "banks"))
    m.suggest_button.click()
    yield lambda: dock.panel.message.text() != suggest_lines.WORKING
    h.check("still one of each", len(layers_named("Suggested breaklines")) == 1 and len(layers_named("Thalwegs")) == 1)
    again = layers_named("Suggested breaklines")[0]
    h.check("the second suggestion is a numbered folder, the edited file untouched", (h.RUNS / "banks_breaklines_2" / "suggested_breaklines.gpkg").is_file() and "banks_breaklines_2" in again.source(), again.source())
    h.check("and is whole again", again.featureCount() == n_file, (again.featureCount(), n_file))
    h.shot("end")
