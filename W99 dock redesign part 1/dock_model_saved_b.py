"""W99 step 1, second half: a QGIS started afresh opens the project of ``dock_model_saved_a.py``.

The job the dock builds must be the one the first QGIS built, to the last character and in every input file. Then the
other ways a model comes back: a project read while the dock is open, a scenario, the sections one at a time through
other kinds of input (an HMS project, rain gauges, a hyetograph), a finished run opened into an empty project, and a
run from before the model was saved, which has only its job.
"""

import importlib.util
import json
import shutil
from pathlib import Path

from qgis.core import QgsProject


def helper(h, name="model_fill"):
    spec = importlib.util.spec_from_file_location(name, Path(h.SCENARIO).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same_job(h, mf, name, dock, shared, job_a, inputs_a):
    out = shared / "job"
    job = mf.built(dock, out)
    h.check(f"{name}: the job is the first QGIS's", job == job_a, mf.differences(job_a, job)[:6])
    files = mf.input_files(out)
    odd = [key for key in sorted(set(files) | set(inputs_a)) if files.get(key) != inputs_a.get(key)]
    h.check(f"{name}: every input file is the same", not odd, odd)


def scenario(h):
    mf = helper(h)
    shared = mf.shared(h)
    job_a = json.loads((shared / "job_a.json").read_text(encoding="utf-8"))
    inputs_a = json.loads((shared / "inputs_a.json").read_text(encoding="utf-8"))
    state_a = json.loads((shared / "state_a.json").read_text(encoding="utf-8"))
    project = QgsProject.instance()

    h.log("=== 1 a fresh QGIS opens the project, then the dock")
    h.check("the project opens", project.read(str(shared / "model.qgz")), project.error())
    dock = yield from h.open_dock()
    model = dock.model
    now = mf.plain_paths(model.collect()["sections"])
    h.check("the dock holds the saved model", now == mf.plain_paths(state_a), mf.differences(mf.plain_paths(state_a), now)[:6])
    same_job(h, mf, "project then dock", dock, shared, job_a, inputs_a)
    h.check("nothing is said when all came back", dock.model_bar.message.text() == "", dock.model_bar.message.text())
    h.check("the restored model does not mark the project changed", not project.isDirty())
    dock.terrain.setCollapsed(False)
    h.widget_shot("restored_terrain", dock.terrain)

    h.log("=== 2 a new project empties the dock; reading the project with the dock open fills it")
    project.clear()
    h.check("a new project: the cell size is the default again", dock.terrain.dx.value() == 20.0, dock.terrain.dx.value())
    h.check("a new project: the mesh is off again", not dock.mesh.enabled.isChecked())
    h.check("a new project: no gauge rows", len(dock.gauges.rows) == 0, len(dock.gauges.rows))
    h.check("the project opens again", project.read(str(shared / "model.qgz")), project.error())
    same_job(h, mf, "dock then project", dock, shared, job_a, inputs_a)

    h.log("=== 3 a scenario: a named copy in the output folder")
    bar = dock.model_bar
    bar.scenario_name.setText("full: as saved")
    bar.save_button.click()
    saved = shared / "runs" / "full" / "scenarios" / "full_ as saved.wadi2d.json"
    h.check("the scenario file is in the model's folder", saved.is_file(), bar.message.text())
    h.check("the scenario is listed", bar.scenarios.findText("full_ as saved") >= 0, [bar.scenarios.itemText(n) for n in range(bar.scenarios.count())])
    dock.terrain.dx.setValue(50.0)
    dock.boundaries.table.cellWidget(0, 2).setValue(9.0)
    dock.storm.pattern.set_rows([(0.0, 0.0), (100.0, 100.0)])
    dock.gauges.set_row(0, at="elsewhere")
    changed = mf.built(dock, shared / "job")
    h.check("the changes reach the job", changed != job_a)
    bar.scenarios.setCurrentIndex(bar.scenarios.findText("full_ as saved"))
    bar.open_button.click()
    same_job(h, mf, "scenario", dock, shared, job_a, inputs_a)
    yield lambda: True
    model.keep()
    kept = mf.plain_paths(json.loads(project.readEntry("Wadi2D", "model", "")[0])["sections"])
    h.check("an opened scenario is the project's model now", kept == mf.plain_paths(state_a), mf.differences(mf.plain_paths(state_a), kept)[:6])

    h.log("=== 4 other inputs, each saved and brought back in this session")
    layers = mf.find_layers(project)
    variants = helper(h, "model_variants")
    yield from variants.round_trips(h, mf, dock, layers, shared)

    h.log("=== 5 a finished run opened into an empty project")
    project.clear()
    ground = h.Bidah()
    h.set_rain_job(dock, ground, "own", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=False)
    dock.points.layer.setLayer(ground.lines)
    dock.points.name.setField("name")
    dock.boundaries.kind.setCurrentText("normal")
    dock.boundaries.value.setValue(0.012)
    dock.hydrology.cn.box.setValue(85.0)
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    yield from h.run(dock)
    run = h.RUNS / "own"
    done = h.events(run, "done")
    h.check("the run finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text()[:200])
    h.check("the run folder holds its model", (run / "model.wadi2d.json").is_file())
    run_job = json.loads((run / "job.json").read_text(encoding="utf-8"))
    project.clear()
    h.check("the empty project has no layers", len(project.mapLayers()) == 0, len(project.mapLayers()))
    h.check("the dock is back at its defaults", dock.hydrology.cn.box.value() != 85.0, dock.hydrology.cn.box.value())
    bar.run_folder.setFilePath(str(run))
    bar.open_run_button.click()
    h.log(f"model bar says: {bar.message.text()}")
    h.check("the layers of the run were added to the project", len(project.mapLayers()) >= 4, [layer.name() for layer in project.mapLayers().values()])
    rebuilt = h.RUNS / "rebuilt"
    again = mf.built(dock, rebuilt)
    diff = mf.differences(mf.normal(run_job, run), mf.normal(again, rebuilt))
    h.check("the job of the refilled dock is the run's", not diff, diff[:6])
    h.check("the run's results are the dock's", dock.results_dir == run, dock.results_dir)
    h.check("Result lines is offered for the opened run", dock.panel.lines_button.isEnabled())

    h.log("=== 6 a run from before the model was saved: only its job")
    old = h.RUNS / "old_run"
    shutil.copytree(run, old)
    (old / "model.wadi2d.json").unlink()
    here, there = json.dumps(str(run))[1:-1], json.dumps(str(old))[1:-1]
    moved = (old / "job.json").read_text(encoding="utf-8").replace(here, there)
    (old / "job.json").write_text(moved, encoding="utf-8")  # as if the run had been made in this folder
    project.clear()
    bar.run_folder.setFilePath(str(old))
    bar.open_run_button.click()
    words = bar.message.text()
    h.log(f"model bar says: {words}")
    h.check("it says the run has no saved model", "no saved model" in words, words[:200])
    rebuilt_old = h.RUNS / "rebuilt_old"
    from_job = mf.built(dock, rebuilt_old)
    old_job = json.loads((old / "job.json").read_text(encoding="utf-8"))
    diff = mf.differences(mf.normal(old_job, old), mf.normal(from_job, rebuilt_old), within=0.00051)
    h.log(f"differences from the old job, coordinates to the millimetre: {diff}")
    h.check("the DEM, the cell size and the domain came back", from_job["grid"]["dx"] == 30.0 and from_job["terrain"]["dem"] == old_job["terrain"]["dem"] and "domain" in from_job["grid"], from_job["grid"])
    named = "run.model_type (only in second)"  # step 2: the job had no type, the dock gives it the one it runs as
    h.check("the old run's type is read from its job: 2D", dock.types.kind == "2d" and named in diff, (dock.types.kind, diff[:3]))
    diff = [d for d in diff if d != named]
    h.check("the whole job came back, coordinates to the millimetre", not diff, diff[:6])
    h.check("nothing is reported as lost", "Could not be restored" not in words, words[-300:])
    h.check("the dock's inputs the job reader names all exist", "no longer has" not in words)
    bar.setCollapsed(False)
    h.widget_shot("model_bar_old_run", bar)
    yield lambda: True
