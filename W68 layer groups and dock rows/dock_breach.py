"""W68 through the real dock: the dam breach row in Structures (W63), refused on the mesh, then a breach that runs.

Bidah 03's dam as W34 drew it (three crest-line pieces at 105 m named "Bidah dam", the spillway at 100 m), the pool full
to the spillway at the start, 20 m cells on the CPU. A breach on the dam, opened at 0.05 h by the run's clock to a bottom
at 90 m, 40 m wide, 1:1 sides, in 10 minutes; one hour of run.
"""

import json

NAME = "Bidah dam"


def job_of(folder):
    return json.loads((folder / "job.json").read_text(encoding="utf-8"))


def scenario(h):
    from qgis.PyQt.QtCore import QCoreApplication

    from pathlib import Path

    h.VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")  # a worktree has no venv of its own
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
    s.layers["crest_line"].setLayer(crest_layer)
    s.fields["crest_line"]["crest_z"].setField("crest_z")
    s.layers["spillway"].setLayer(spill_layer)
    for key in ("crest_z", "coefficient", "length"):
        s.fields["spillway"][key].setField(key)
    start = s.start_water.table.cellWidget(0, 1)
    start.setCurrentIndex(start.findData("spillway"))

    h.log("=== 1 the row: added on the named dam, each field a widget")
    table = s.breaches
    h.check("no breach until one is added", table.table.isHidden() and table.rows == [])
    table.add_button.click()
    QCoreApplication.processEvents()
    h.check("one row, on the named dam", len(table.rows) == 1 and table.rows[0].dam == NAME, table.rows)
    cell = table.table.cellWidget
    from wadi2d_qgis.sections.breach_table import COLUMNS

    keys = [key for key, _words in COLUMNS]
    col = {key: n for n, key in enumerate(keys)}
    h.check("the dam's names are the table's", [cell(0, 0).itemText(i) for i in range(cell(0, 0).count())] == [NAME])
    h.check("held and pipe off for a level-started overtopping", not cell(0, col["held_min"]).isEnabled() and not cell(0, col["piping_z"]).isEnabled())

    h.set_rain_job(dock, ground, "breach", dx=20.0, rain=1.0, hours=0.05, sim_hours=1.0, pixels=False)
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    from wadi2d_qgis.job_builder import problems

    found = problems(dock._collect())
    h.check("an empty row is stopped in words", any("Breach of Bidah dam: type the final bottom" in p for p in found), found)
    cell(0, col["bottom_z"]).setValue(90.0)
    cell(0, col["width_m"]).setValue(40.0)
    cell(0, col["slope"]).setValue(1.0)
    cell(0, col["formation_min"]).setValue(10.0)
    trigger = cell(0, col["trigger"])
    trigger.setCurrentIndex(trigger.findData("time"))
    cell(0, col["value"]).setValue(0.05)
    h.widget_shot("breach_row", table)

    h.log("=== 2 refused on the mesh, in the engine's words, before any run")
    dock.mesh.enabled.setChecked(True)
    found = problems(dock._collect())
    h.check("the mesh refuses the breach", any("uniform grid in this version: untick the mesh" in p for p in found), found)
    dock.mesh.enabled.setChecked(False)
    found = problems(dock._collect())
    h.check("ticking the mesh ticked local steps, which stays refused", any("local time stepping" in p for p in found), found)
    dock.mesh.local_steps.setChecked(False)
    found = problems(dock._collect())
    h.check("off the mesh and local steps, nothing stops it", not [p for p in found if "breach" in p.lower()], found)

    h.log("=== 3 the breach runs")
    yield from h.run(dock, 1500)
    out = h.RUNS / "breach"
    done = h.events(out, "done")
    h.check("the run finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text()[:300])
    job = job_of(out).get("breaches") or []
    h.check(
        "the job carries the row in the engine's units",
        len(job) == 1 and job[0]["dam"] == NAME and job[0]["trigger_time_s"] == 180.0 and job[0]["formation_time_s"] == 600.0,
        job,
    )
    said = [e.get("stage") or e.get("what") or e.get("message", "") for e in h.events(out, "breach")]
    h.log(f"breach events: {h.events(out, 'breach')[:4]}")
    h.check("the breach started and formed", len(said) >= 2, said)
    series = sorted(p.name for p in (out / "series").glob("breach_*.csv"))
    h.check("its series is written", bool(series), series)
