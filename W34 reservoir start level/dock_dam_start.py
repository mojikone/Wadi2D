"""W34 through the real dock: the dam start table and initial water, on Bidah's own dam, grid pool only.

Bidah 03's dam as the validation job draws it (three crest-line pieces at 105 m, one spillway at 100 m), named in a layer
field, so the table lists it. Four short runs: empty (the default), full to the spillway, a level, and a pond drawn as a
polygon. W32 (item 6b) held 3.740 Mm3 in this grid pool with crest lines at 100 m, through a polygon bounded by the dam
line and reaching 3 km up the valley (3.658 with the W8 embankment); the first run of this check compared against 3.658,
misread from W32's table, and failed at +4.8 %.
"""

import json

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant

NAME = "Bidah dam"
GRID_POOL_W32_M3 = 3.740e6
LEVEL = 98.0


def job_of(folder):
    return json.loads((folder / "job.json").read_text(encoding="utf-8"))


def start_storage(h, folder):
    done = h.events(folder, "done")
    return done[-1]["balance"]["storage_start_m3"] if done else None


def pool_notes(h, folder):
    return [e["message"] for e in h.events(folder, "warn") if e.get("message", "").startswith(f"dam {NAME}")]


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()
    dam = json.loads((h.VALIDATION / "jobs" / "dam_Bidah03_100yr_20.json").read_text(encoding="utf-8"))
    crests = [o for o in dam["terrain"]["objects"] if o["kind"] == "crest_line"]
    spill = next(o for o in dam["terrain"]["objects"] if o["kind"] == "spillway")
    crest_layer = h.add_vector(
        h.geojson("crests", [h.line(o["coordinates"], name=NAME, crest_z=o["z_constant"]) for o in crests]), "dam crest", ground.crs
    )
    spill_layer = h.add_vector(
        h.geojson("spill", [h.line(spill["coordinates"], crest_z=100.0, coefficient=2.1, length=72.0)]), "dam spillway", ground.crs
    )
    s = dock.structures
    s.setCollapsed(False)
    table = s.start_water.table

    h.log("=== 1 the table lists the dam once, empty")
    h.check("no crest layer, no rows", table.rowCount() == 0, table.rowCount())
    s.layers["crest_line"].setLayer(crest_layer)
    s.fields["crest_line"]["crest_z"].setField("crest_z")
    s.layers["spillway"].setLayer(spill_layer)
    for key in ("crest_z", "coefficient", "length"):
        s.fields["spillway"][key].setField(key)
    h.check("three pieces, one dam", table.rowCount() == 1, table.rowCount())
    h.check("named by the layer", table.item(0, 0).text() == NAME, table.item(0, 0).text())
    start, level = table.cellWidget(0, 1), table.cellWidget(0, 2)
    h.check("starts empty", start.currentData() == "empty", start.currentData())
    h.check("no level for an empty dam", not level.isEnabled())
    h.widget_shot("table_empty", s.start_water)

    def run(folder):
        h.set_rain_job(dock, ground, folder, dx=20.0, rain=1.0, hours=0.05, sim_hours=0.05, pixels=False)
        yield from h.run(dock)
        out = h.RUNS / folder
        done = h.events(out, "done")
        h.check(f"{folder} finished", done and done[-1].get("code") == 0, dock.panel.message.text())
        return out

    h.log("=== 2 empty: no dam_levels in the job, no water at the start")
    out = yield from run("empty")
    h.check("empty writes nothing", "dam_levels" not in job_of(out), job_of(out).get("dam_levels"))
    h.check("no water at the start", start_storage(h, out) == 0.0, start_storage(h, out))

    h.log("=== 3 full to the spillway: the pool behind the dam, as W32 measured it")
    start, level = table.cellWidget(0, 1), table.cellWidget(0, 2)  # each run rebuilds the row's widgets
    start.setCurrentIndex(start.findData("spillway"))
    out = yield from run("spillway")
    h.check("the job names the start", job_of(out).get("dam_levels") == [{"name": NAME, "start": "spillway"}], job_of(out).get("dam_levels"))
    full = start_storage(h, out)
    notes = pool_notes(h, out)
    h.log(f"start storage {full:,.0f} m3; notes {notes}")
    h.check("the run says what it filled", notes and "starts at 100 m" in notes[0], notes)
    h.check("within 3 % of W32's grid pool with crest lines", abs(full / GRID_POOL_W32_M3 - 1.0) < 0.03, f"{full / GRID_POOL_W32_M3:.4f}")
    h.check("no less than W32's polygon, which stopped 3 km up", full >= GRID_POOL_W32_M3, f"{full:,.0f}")

    h.log("=== 4 a level: less water, and the level in the job")
    start, level = table.cellWidget(0, 1), table.cellWidget(0, 2)
    start.setCurrentIndex(start.findData("level"))
    h.check("a level box once asked", level.isEnabled())
    level.setValue(LEVEL)
    out = yield from run("level")
    h.check("the job holds the level", job_of(out).get("dam_levels") == [{"name": NAME, "start": LEVEL}], job_of(out).get("dam_levels"))
    lower = start_storage(h, out)
    h.check("a lower level holds less", 0.0 < lower < full, (lower, full))
    h.widget_shot("table_level", s.start_water)

    h.log("=== 5 initial water, a pond drawn as a polygon")
    start = table.cellWidget(0, 1)
    start.setCurrentIndex(start.findData("empty"))
    box = ground.domain.extent()
    cx, cy = box.center().x(), box.center().y()
    pond = QgsVectorLayer(f"Polygon?crs={ground.crs.authid()}", "pond", "memory")
    pond.dataProvider().addAttributes([QgsField("wl", QVariant.Double)])
    pond.updateFields()
    feature = QgsFeature(pond.fields())
    ring = [QgsPointXY(cx - 200, cy - 200), QgsPointXY(cx + 200, cy - 200), QgsPointXY(cx + 200, cy + 200), QgsPointXY(cx - 200, cy + 200)]
    feature.setGeometry(QgsGeometry.fromPolygonXY([ring]))
    zmin = ground.dem.dataProvider().sample(box.center(), 1)[0]
    feature["wl"] = float(zmin) + 1.0
    pond.dataProvider().addFeatures([feature])
    from qgis.core import QgsProject

    QgsProject.instance().addMapLayer(pond)
    s.start_water.ponds.setLayer(pond)
    from wadi2d_qgis.job_builder import problems

    found = problems(dock._collect())
    h.check("a pond without its level field is stopped", any("initial water" in p for p in found), found)
    s.start_water.pond_level.setField("wl")
    out = yield from run("pond")
    levels = job_of(out).get("initial_levels") or []
    h.check("the pond reaches the job", len(levels) == 1 and abs(levels[0]["level"] - feature["wl"]) < 1e-9, levels)
    h.check("the pond holds water at the start", start_storage(h, out) > 0.0, start_storage(h, out))
