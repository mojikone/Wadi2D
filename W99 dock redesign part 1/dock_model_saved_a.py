"""W99 step 1, first half: a dock filled in every section, and the QGIS project saved with it.

``dock_model_saved_b.py`` is the second half, in a QGIS started afresh: it opens the project and builds the job again.
Both keep what they share in ``model_shared`` beside their own folders.
"""

import importlib.util
import json
import shutil
from pathlib import Path

from qgis.core import QgsProject


def helper(h):
    spec = importlib.util.spec_from_file_location("model_fill", Path(h.SCENARIO).parent / "model_fill.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scenario(h):
    mf = helper(h)
    shared = mf.shared(h)
    for old in shared.glob("*"):
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    ground = h.Bidah()
    extra = mf.extra_layers(h, ground)
    dock = yield from h.open_dock()
    model = dock.model

    h.log("=== 1 every section has a state, and a new dock is not a changed project")
    h.check("the model is kept once the engine answers", model.ready)
    keys = [section.key for section in dock.sections]
    h.check("every section has its name in the model", all(keys) and len(set(keys)) == len(keys), keys)
    first = model.collect()
    h.check("the document names its format", (first["format"], first["version"]) == ("wadi2d-model", 2), first["version"])
    counts = {key: len(state["widgets"]) for key, state in first["sections"].items()}
    h.log(f"inputs found by section: {counts}")
    h.check("every section's inputs are found", all(counts[k] > 0 for k in keys if k != "gauges"), counts)
    h.check("Gauges, whose one field became the run's start, still saves its table", "gauges" in first["sections"]["gauges"]["rows"])
    h.check("the Storm widgets Hydrology borrows are saved once", "rain" not in first["sections"]["hydrology"]["widgets"])
    model.keep()
    _text, found = QgsProject.instance().readEntry("Wadi2D", "model", "")
    h.check("an untouched dock writes nothing into the project", not found)

    h.log("=== 2 fill the dock")
    folder = shared / "runs" / "full"
    mf.fill(
        dock, ground.dem, ground.domain, ground.outlets, ground.lines, extra["crests"], extra["refinement"],
        extra["ponds"], extra["record"], folder,
    )  # fmt: skip
    from wadi2d_qgis.job_builder import problems

    values = dock._collect()
    h.check("the filled dock has a job to build", problems(values) == [], problems(values))
    out = shared / "job"
    job = mf.built(dock, out)
    h.check("the job carries the mesh lines", len(job.get("mesh", {}).get("lines", [])) == 2, job.get("mesh", {}).keys())
    h.check("the job carries the dam's start level", job.get("dam_levels") == [{"name": "Bidah 03", "start": 97.25}], job.get("dam_levels"))
    h.check("the job carries the pinned boundary", job["boundaries"][0].get("stage") == 2.5 and job["boundaries"][1].get("slope") == 0.008, job["boundaries"])
    h.check("the job carries the observed gauge", "observed" in job["outputs"], list(job["outputs"]))
    (shared / "job_a.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    (shared / "inputs_a.json").write_text(json.dumps(mf.input_files(out)), encoding="utf-8")

    h.log("=== 3 save the project at once: the model goes with it")
    state = model.collect()
    (shared / "state_a.json").write_text(json.dumps(state["sections"], indent=1), encoding="utf-8")
    project = QgsProject.instance()
    path = shared / "model.qgz"
    h.check("the project is written", project.write(str(path)), project.error())
    text, found = project.readEntry("Wadi2D", "model", "")
    h.check("the project holds the model", found and json.loads(text)["sections"] == state["sections"])
    h.widget_shot("model_bar", dock.model_bar)
    yield lambda: True
