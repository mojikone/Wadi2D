"""W99 step 4: models saved by steps 1 and 2, of format 1, opened by the dock of step 4.

Run it into the throwaway folder where the plugin of the merged steps 1 and 2 (commit ``bd4b4dd``) ran
``dock_model_saved_a.py`` and ``W77``'s ``dock_gauges.py``: it opens the QGIS project that plugin saved, and the run
folders it wrote. The job the dock builds from each must be the one the old plugin wrote, and what the way up to format
2 moved is said in words.
"""

import importlib.util
import json
from pathlib import Path

from qgis.core import QgsProject


def helper(h, name="model_fill"):
    spec = importlib.util.spec_from_file_location(name, Path(h.SCENARIO).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scenario(h):
    mf = helper(h)
    shared = mf.shared(h)
    job_a = json.loads((shared / "job_a.json").read_text(encoding="utf-8"))
    inputs_a = json.loads((shared / "inputs_a.json").read_text(encoding="utf-8"))
    project = QgsProject.instance()

    h.log("=== 1 the project saved by the plugin of steps 1 and 2")
    h.check("the project opens", project.read(str(shared / "model.qgz")), project.error())
    old = json.loads(project.readEntry("Wadi2D", "model", "")[0])
    h.check("it holds a model of format 1, with the starts and Run's fields where they were", old["version"] == 1 and "duration" in old["sections"]["run"]["widgets"] and "start" in old["sections"]["gauges"]["widgets"] and "simulation" not in old["sections"], old["version"])
    dock = yield from h.open_dock()
    sim = dock.simulation
    out = shared / "job"
    job = mf.built(dock, out)
    h.check("the job the dock builds is the old plugin's, to the character", job == job_a, mf.differences(job_a, job)[:6])
    files = mf.input_files(out)
    odd = [key for key in sorted(set(files) | set(inputs_a)) if files.get(key) != inputs_a.get(key)]
    h.check("and every input file", not odd, odd)
    h.check("Run's three fields are Simulation's now", (sim.duration.value(), sim.maps.currentIndex(), sim.backend.currentData()) == (2.25, 1, "cpu"), (sim.duration.value(), sim.maps.currentIndex(), sim.backend.currentData()))
    h.check("the observed gauges' start is the run's one start", sim.start.text() == "2021-10-04 00:00" == old["sections"]["gauges"]["widgets"]["start"], sim.start.text())
    said = dock.model_bar.message.text()
    h.log(f"model bar says: {said}")
    h.check("what moved is said in words", "one start now" in said and "2021-10-04 00:00" in said and "observed gauges" in said, said)
    h.check("nothing is called lost", "Could not be restored" not in said, said)
    dock.terrain.dx.setValue(31.0)  # any change: the project's copy is written again
    dock.model.keep()
    kept = json.loads(project.readEntry("Wadi2D", "model", "")[0])
    h.check("the project's copy is of format 2 once it is kept", kept["version"] == 2 and kept["sections"]["simulation"]["widgets"]["start"] == "2021-10-04 00:00" and "start" not in kept["sections"]["gauges"]["widgets"], kept["version"])

    h.log("=== 2 the runs that plugin wrote, each with its model of format 1")
    runs = sorted(path.parent for path in (Path(h.P).parent / "dock_gauges" / "runs").glob("*/model.wadi2d.json"))
    h.check("the old plugin's rain gauge runs are there", len(runs) >= 2, [run.name for run in runs])
    bar = dock.model_bar
    for run in runs:
        saved = json.loads((run / "model.wadi2d.json").read_text(encoding="utf-8"))
        wrote = json.loads((run / "job.json").read_text(encoding="utf-8"))
        project.clear()
        bar.run_folder.setFilePath(str(run))
        bar.open_run_button.click()
        yield lambda: True
        rebuilt = run.parent / "w99_rebuilt"
        again = mf.built(dock, rebuilt)
        diff = mf.differences(mf.normal(wrote, run), mf.normal(again, rebuilt))
        h.check(f"{run.name}: a model of format {saved['version']} gives the job that run wrote", saved["version"] == 1 and not diff, diff[:6])
        starts = (saved["sections"]["storm"]["widgets"].get("gauge_start"), saved["sections"]["gauges"]["widgets"].get("start"))
        h.check(f"{run.name}: the rain gauges' start is the run's", sim.start.text() == starts[0] and wrote["storm"].get("rain_start") == starts[0], (sim.start.text(), starts))
        h.log(f"{run.name}: starts {starts}; model bar says: {bar.message.text()[:400]}")
        h.check(f"{run.name}: said in words", "one start now" in bar.message.text() and "the rain" in bar.message.text(), bar.message.text()[:300])
    yield lambda: True
