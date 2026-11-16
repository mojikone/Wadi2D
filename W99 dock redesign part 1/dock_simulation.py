"""W99 step 4 through the real dock: the Simulation section, before Run.

One start where three were, the simulated time, the 2D step (automatic or fixed, with the engine's own bounds and its
own refusal), the lumped step only where there is a lumped part, the map and series intervals, one engine choice. At
the defaults the job holds nothing new; a real run holds a fixed step, and a real run is refused by the engine in its
own words when the fixed step is longer than the flow allows.
"""

import importlib.util
import json
from pathlib import Path

START = "2021-10-04 00:00"


def helper(h, name="model_fill"):
    spec = importlib.util.spec_from_file_location(name, Path(h.SCENARIO).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def big_shot(h, dock, name, size=(440, 900), top=None):
    """The dock's frame at the width of a real dock, the card ``top`` brought to the top of the sections."""
    from qgis.PyQt.QtWidgets import QApplication

    frame = dock.widget()
    held = frame.size()
    frame.resize(*size)
    QApplication.processEvents()
    if top is not None:  # no events between this and the picture: the window would take its docked size back
        dock.scroll.verticalScrollBar().setValue(max(dock.cards[top].y() - 8, 0))
    frame.grab().save(str(h.P / f"widget_{name}.png"))
    frame.resize(held)
    QApplication.processEvents()


def labels(widget, text):
    """The form labels with this text that a user would see in the widget."""
    from qgis.PyQt.QtWidgets import QLabel

    return [label for label in widget.findChildren(QLabel) if label.text() == text and label.isVisibleTo(widget)]


def scenario(h):
    mf = helper(h)
    ground = h.Bidah()
    box = ground.domain.extent()
    cx, cy = box.center().x(), box.center().y()
    ring = [[cx - 150.0, cy - 150.0], [cx + 150.0, cy - 150.0], [cx + 150.0, cy + 150.0], [cx - 150.0, cy + 150.0], [cx - 150.0, cy - 150.0]]
    patch = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}
    small = h.add_vector(h.geojson("w99_small", [patch]), "w99 small domain", ground.crs)
    record = h.DATA / "w99_flow.csv"
    record.write_text("time,flow_m3s\n2021-10-04 00:00,0\n2021-10-04 00:30,12.5\n", encoding="utf-8")
    dock = yield from h.open_dock()
    from wadi2d_qgis.job_builder import problems
    from wadi2d_qgis.section_status import MISSING, READY

    sim, panel, storm = dock.simulation, dock.panel, dock.storm
    links = dock.status_links

    def built():
        return mf.built(dock, h.RUNS / "job")

    h.log("=== 1 a section of its own, before Run")
    keys = [s.key for s in dock.sections]
    h.check("Simulation sits before Run", keys.index("simulation") == keys.index("run") - 1 and sim.title() == "7c. Simulation", keys)
    h.check("the sections before it keep their places and names", keys[:8] == ["terrain", "mesh", "hydrology", "storm", "structures", "boundaries", "points", "gauges"] and panel.title() == "8. Run")
    h.check("it has its card and its step", dock.cards["simulation"].section is sim and "simulation" in links.refresh() and "simulation" in dock.strip.steps)
    sim.setCollapsed(False)
    panel.setCollapsed(False)
    storm.setCollapsed(False)
    dock.gauges.setCollapsed(False)
    h.check("one Run starts at field in the whole dock, in Simulation", len(labels(dock.widget(), "Run starts at")) == 1 and len(labels(sim, "Run starts at")) == 1, len(labels(dock.widget(), "Run starts at")))
    h.check("the gridded rain, the rain gauges and the observed gauges read that one field", storm.start is sim.start and storm.gauge_start is sim.start and dock.gauges.start is sim.start)
    h.check("Run no longer shows the simulated time, the maps or the engine", not labels(panel, "Simulated time, h") and not labels(panel, "Save maps") and not labels(panel, "Engine"))
    h.check("Simulation shows them", len(labels(sim, "Simulated time, h")) == 1 and len(labels(sim, "Save maps")) == 1 and len(labels(sim, "Engine")) == 1)
    h.check("older checks still reach them from Run", panel.duration is sim.duration and panel.maps is sim.maps and panel.backend is sim.backend)

    h.log("=== 2 at the defaults the job holds nothing new")
    h.set_rain_job(dock, ground, "sim", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=False)
    sim.backend.setCurrentIndex(sim.backend.findData("cpu"))
    job = built()
    h.check("no numerics, no lumped step, no series interval, no start", "numerics" not in job and "time_step_min" not in job["hydrology"] and "series_every_s" not in job["outputs"] and "rain_start" not in job["storm"], (job.get("numerics"), job["hydrology"], job["outputs"]))
    h.check("the simulated time, the maps and the engine as before", job["run"] == {"duration_s": 2700.0, "backend": "cpu"} and job["outputs"]["map_every_s"] == 900.0, job["run"])
    h.check("the defaults shown are the engine's", (sim.cfl.value(), sim.dt_max.value(), sim.dt_min.value(), sim.lumped_step.value(), sim.series.value()) == tuple(dock.schema.default(p) for p in ("numerics.cfl", "numerics.dt_max", "numerics.dt_min", "hydrology.time_step_min", "outputs.series_every_s")), (sim.cfl.value(), sim.dt_max.value(), sim.dt_min.value()))
    status = links.refresh()["simulation"]
    h.check("its status says what will run", status == (READY, "0.75 h \N{MIDDLE DOT} automatic step, Courant 0.45 \N{MIDDLE DOT} maps every 15 min \N{MIDDLE DOT} lumped step 5 min"), status)

    h.log("=== 3 the one start reaches whoever reads it")
    sim.start.setText(START)
    dock.points.layer.setLayer(ground.lines)
    dock.points.name.setField("name")
    dock.gauges.add_row("flow")
    dock.gauges.set_row(0, name="gauge", file=str(record), at="Bidah 03")
    job = built()
    h.check("a design rain: the observed record is read from the run's start", job["outputs"]["observed"][0].get("start") == START and "rain_start" not in job["storm"], job["outputs"]["observed"])
    grids = h.DATA / "w99_grids"
    grids.mkdir(exist_ok=True)
    storm.kind.setCurrentIndex(storm.kind.findData("gridded"))
    storm.is_folder.setCurrentIndex(1)
    storm.rain_file.setFilePath(str(grids))
    storm.period.setValue(10.0)
    job = built()
    h.check("a gridded rain starts there", job["storm"].get("rain_start") == START, job["storm"])
    h.check("and carries it for the observed record, as before", "start" not in job["outputs"]["observed"][0], job["outputs"]["observed"])
    storm.kind.setCurrentIndex(storm.kind.findData("gauges"))
    storm.gauge_table.add_row("rain")
    storm.gauge_table.set_row(0, name="west", file=str(record), x=cx, y=cy)
    job = built()
    h.check("rain gauges start there, and the observed record with them", job["storm"].get("rain_start") == START and job["outputs"]["observed"][0].get("start") == START, job["storm"].get("rain_start"))
    sim.start.setText("the fourth")
    found = problems(dock._collect())
    h.check("a start that is no date stops the run in words", any("not a date and time" in text for text in found), found)
    h.check("and the section is Missing", links.refresh()["simulation"].state == MISSING and "2021-10-04 00:00" in links.refresh()["simulation"].words)
    sim.start.setText("")
    storm.kind.setCurrentIndex(storm.kind.findData("single"))
    dock.gauges.gauges.rows.clear()
    dock.gauges.gauges._show()
    dock.points.layer.setLayer(None)

    h.log("=== 4 the 2D step: automatic, then fixed")
    h.check("automatic by default, with its three numbers in sight", sim.step_mode.currentData() == "auto" and sim.auto_box.isVisible() and not sim.fixed_box.isVisible())
    sim.cfl.setValue(0.3)
    h.check("a Courant number moved off the default reaches the job, alone", built().get("numerics") == {"cfl": 0.3}, built().get("numerics"))
    sim.dt_max.setValue(2.0)
    sim.dt_min.setValue(0.01)
    h.check("so do the largest and the smallest step", built()["numerics"] == {"cfl": 0.3, "dt_max": 2.0, "dt_min": 0.01}, built()["numerics"])
    sim.dt_min.setValue(1.0)
    sim.dt_max.setValue(0.5)
    h.check("a smallest step over the largest stops the run in words", any("smallest 2D step" in text for text in problems(dock._collect())), problems(dock._collect()))
    h.check("and the section says so", links.refresh()["simulation"] == (MISSING, "The smallest 2D step must not exceed the largest."))
    for box, path in ((sim.cfl, "numerics.cfl"), (sim.dt_max, "numerics.dt_max"), (sim.dt_min, "numerics.dt_min")):
        box.setValue(dock.schema.default(path))
    h.check("back at the defaults the job has no numerics again", "numerics" not in built())
    sim.step_mode.setCurrentIndex(sim.step_mode.findData("fixed"))
    h.check("Fixed shows its one number and hides the three", sim.fixed_box.isVisible() and not sim.auto_box.isVisible() and "advanced" in sim.step_mode.currentText().lower())
    low, high = dock.schema.bounds("numerics.dt_max")[0], dock.schema.bounds("numerics.dt_min")[1]
    h.check("its bounds are the engine's own", (sim.fixed_step.minimum(), sim.fixed_step.maximum()) == (low, high) == (0.001, 1.0), (sim.fixed_step.minimum(), sim.fixed_step.maximum()))
    h.check("and are said in words, with what the engine does when the step is too long", f"between {low:g} and {high:g} s" in sim.fixed_note.text() and "stops the run and names the cell" in sim.fixed_note.text() and sim.fixed_note.isVisible(), sim.fixed_note.text())
    sim.fixed_step.setValue(5.0)
    h.check("a step over the engine's bound cannot be typed", sim.fixed_step.value() == high, sim.fixed_step.value())
    sim.fixed_step.setValue(0.25)
    h.check("a fixed step is both of the engine's bounds in the job", built()["numerics"] == {"dt_max": 0.25, "dt_min": 0.25}, built()["numerics"])
    h.check("the status says fixed", "fixed step 0.25 s" in links.refresh()["simulation"].words, links.refresh()["simulation"].words)
    for section in dock.sections:
        section.setCollapsed(section is not sim)
    yield lambda: True
    big_shot(h, dock, "simulation_fixed", top="simulation")

    h.log("=== 5 a real run at the fixed step")
    for section in dock.sections:
        section.setCollapsed(section is not sim and section is not panel)
    sim.duration.setValue(0.1)
    yield from h.run(dock)
    run = h.RUNS / "sim"
    done = h.events(run, "done")
    h.log(f"done: {done[-1] if done else None}")
    h.check("the run at the fixed step finished", bool(done) and done[-1].get("code") == 0, panel.message.text()[:200])
    written = json.loads((run / "job.json").read_text(encoding="utf-8"))
    h.check("its job holds the fixed step", written["numerics"] == {"dt_max": 0.25, "dt_min": 0.25}, written.get("numerics"))
    steps = done[-1].get("steps") if done else None
    h.check("it took one step every 0.25 s: 1,440 in 0.1 h", steps is not None and abs(steps - 1440) <= 1, steps)

    h.log("=== 6 a fixed step longer than the flow allows: the engine's own refusal")
    dock.terrain.domain.setLayer(small)
    dock.terrain.dx.setValue(5.0)
    dock.boundaries.layer.setLayer(None)
    sim.fixed_step.setValue(1.0)
    panel.folder.setFilePath(str(h.RUNS / "refused"))
    yield from h.run(dock)
    said = panel.message.text()
    h.log(f"Run says: {said}")
    refused = h.events(h.RUNS / "refused", "done")
    h.check("the engine stopped the run", bool(refused) and refused[-1].get("code") != 0, refused[-1] if refused else None)
    h.check("and Run shows its words: the time step, below the floor", "time step" in said and ("below" in said or "minimum" in said), said[:300])
    dock.terrain.domain.setLayer(ground.domain)
    dock.terrain.dx.setValue(30.0)
    dock.boundaries.layer.setLayer(ground.mixed)
    sim.step_mode.setCurrentIndex(sim.step_mode.findData("auto"))
    h.check("automatic again: no numerics", "numerics" not in built())

    h.log("=== 7 the lumped step, the series and the engine")
    sim.lumped_step.setValue(2.0)
    sim.series.setValue(30.0)
    job = built()
    h.check("a lumped step and a series interval moved off the defaults reach the job", job["hydrology"].get("time_step_min") == 2.0 and job["outputs"].get("series_every_s") == 30.0, (job["hydrology"], job["outputs"]))
    sim.maps.setCurrentIndex(1)
    h.check("the map interval as before", built()["outputs"]["map_every_s"] == 300.0)
    h.check("the lumped step shows with no type", len(labels(sim, "Lumped step, min")) == 1 and sim.lumped_step.isVisible())
    dock.header.back_button.click()
    dock.start_page.cards["2d"].click()
    yield lambda: True
    h.check("2D: no lumped step to set, and none in the job", not sim.lumped_step.isVisible() and not labels(sim, "Lumped step, min") and "time_step_min" not in built()["hydrology"], built()["hydrology"])
    h.check("2D: its status leaves the lumped step out", "lumped step" not in links.refresh()["simulation"].words, links.refresh()["simulation"].words)
    dock.header.back_button.click()
    dock.start_page.cards["hybrid_2d"].click()
    yield lambda: True
    h.check("a hybrid: the lumped step shows", sim.lumped_step.isVisible() and len(labels(sim, "Lumped step, min")) == 1)
    dock.header.back_button.click()
    dock.start_page.cards["lumped"].click()
    yield lambda: True
    sim.cfl.setValue(0.3)
    h.check("Lumped: no 2D step and no maps to set", not sim.step_mode.isVisible() and not sim.auto_box.isVisible() and not sim.maps.isVisible() and sim.lumped_step.isVisible())
    h.check("Lumped: its status is the lumped model's", links.refresh()["simulation"] == (READY, "0.1 h \N{MIDDLE DOT} lumped step 2 min"), links.refresh()["simulation"])
    sim.cfl.setValue(dock.schema.default("numerics.cfl"))
    for section in dock.sections:
        section.setCollapsed(section is not sim)
    yield lambda: True
    big_shot(h, dock, "simulation_lumped", top="simulation")
    dock.header.back_button.click()
    dock.start_page.all_button.click()
    yield lambda: True
    h.check("one engine choice, and it is the one the pixel slider takes", sim.chosen_backend() == "cpu" and panel.chosen_backend() == "cpu")

    h.log("=== 8 saved with the model, under Simulation")
    sim.start.setText(START)
    sim.step_mode.setCurrentIndex(sim.step_mode.findData("fixed"))
    sim.fixed_step.setValue(0.5)
    doc = dock.model.collect()
    job = built()
    saved = doc["sections"]["simulation"]["widgets"]
    h.check("the document is of the new format", doc["version"] == 2)
    h.check("Simulation holds the start, the time, the steps, the intervals and the engine", saved["start"] == START and saved["duration"] == 0.1 and saved["step_mode"]["data"] == "fixed" and saved["fixed_step"] == 0.5 and saved["lumped_step"] == 2.0 and saved["series"] == 30.0 and saved["backend"]["data"] == "cpu", saved)
    h.check("no other section saves them", not {"duration", "maps", "backend"} & set(doc["sections"]["run"]["widgets"]) and "start" not in doc["sections"]["storm"]["widgets"] and "start" not in doc["sections"]["gauges"]["widgets"], list(doc["sections"]["run"]["widgets"]))
    dock.model.reset()
    h.check("a new model: the defaults again", sim.start.text() == "" and sim.step_mode.currentData() == "auto" and sim.series.value() == 60.0)
    dock.model.apply(doc)
    again = built()
    h.check("the model comes back, and its job with it", dock.model.collect()["sections"] == doc["sections"] and again == job, mf.differences(job, again)[:5])

    h.log("=== 9 while a run is going the maps and the engine are held, as they were in Run")
    sim.step_mode.setCurrentIndex(sim.step_mode.findData("auto"))
    sim.start.setText("")
    sim.duration.setValue(0.5)
    panel.folder.setFilePath(str(h.RUNS / "held"))
    panel.run_button.click()
    yield lambda: dock.run is not None
    h.check("held while it runs", not sim.maps.isEnabled() and not sim.backend.isEnabled())
    yield h.idle(dock)
    h.check("free again when it ends", sim.maps.isEnabled() and sim.backend.isEnabled())
    yield lambda: True
