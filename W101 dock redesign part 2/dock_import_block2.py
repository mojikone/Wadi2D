"""W101, his item of 2026-11-16: the four Block 2 jobs of W79, which the dock did not write, imported into the dock.

Each job is imported (Import a job: every field the dock has a control for, its inline lines and polygons into a
GeoPackage beside the model), given its model type, saved as a scenario in W102, and then proved: the job the dock
writes from it, as Run writes it (the HMS import included), is compared field by field with the original, both read
through the engine's own schema so that defaults written out or left out compare alike. What differs is what the dock
cannot hold yet, by section. Read-only on his folders; the scenarios, the GeoPackages, the rebuilt jobs and the report
go to W102.
"""

import json
from pathlib import Path

W79 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways")
W102 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W102 Block 2 models in the dock")
JOBS = (
    ("2D", "rerun2_run1_full_2d_aligned", "2d"),
    ("Lumped", "rerun2_run2_hms_lumped", "lumped"),
    ("Hybrid Lumped", "rerun2_run3_hybrid_aligned", "hybrid_lumped"),
    ("Hybrid 2D", "rerun2_run4_hybrid_2d_routing_aligned", "hybrid_2d"),
)


def resolved(job: dict) -> dict:
    """A job as the engine reads it: every default written out, the domain as its polygon."""
    from wadi2d.config.schema import RunConfig

    from wadi2d_qgis.job_import import in_phase_order

    out = in_phase_order(RunConfig.model_validate(job).model_dump(mode="json"))
    domain = (out.get("grid") or {}).get("domain")
    if domain and Path(domain).is_file():
        out["grid"]["domain"] = [f["geometry"]["coordinates"] for f in json.loads(Path(domain).read_text(encoding="utf-8"))["features"]]
    return out


def scenario(h):
    dock = yield from h.open_dock()
    from qgis.core import QgsProject
    from wadi2d_qgis.job_import import not_held

    W102.mkdir(exist_ok=True)
    report = {}
    for name, stem, kind in JOBS:
        h.log(f"=== {name}: {stem}")
        source = W79 / "jobs" / f"{stem}.json"
        original = json.loads(source.read_text(encoding="utf-8"))
        dock.panel.folder.setFilePath(str(W102))
        words = dock.model.import_job(str(source))
        h.check(f"{name}: imported", bool(dock.terrain.dem_layer()) and dock.panel.folder.filePath() == str(W102), dock.model_bar.message.text()[:300])
        dock.types.choose(kind)
        objects = original["terrain"]["objects"]
        h.check(f"{name}: simulated time 48 h", dock.simulation.duration.value() == original["run"]["duration_s"] / 3600.0, dock.simulation.duration.value())
        grid_part = dock.reduction.grid
        h.check(f"{name}: the storm's ARF read at 100 km2, its factor shown", dock.reduction.lumped.form.currentData() == "area" and dock.reduction.lumped.area.value() == 100.0 and (kind == "lumped" or "0.9130" in grid_part.factor.text()), (dock.reduction.lumped.form.currentData(), grid_part.factor.text()))
        rows = dock.boundaries.rows
        h.check(f"{name}: its {len(original['boundaries'])} outflow lines, normal depth at their slopes", [(r.kind, r.value) for r in rows] == [(b["kind"], b["slope"]) for b in original["boundaries"]], [(r.kind, r.value) for r in rows])
        for object_kind in ("crest_line", "spillway"):
            count = sum(1 for o in objects if o["kind"] == object_kind)
            layer = dock.structures.layers[object_kind].currentLayer()
            h.check(f"{name}: its {count} {object_kind}s", (layer.featureCount() if layer is not None else 0) == count, layer.featureCount() if layer is not None else None)
        design = dock.points.layer.currentLayer()
        h.check(f"{name}: its result lines", (design.featureCount() if design else 0) == len(original["outputs"].get("lines") or []), design.featureCount() if design else None)
        strips = original.get("strips") or {}
        if strips.get("enabled"):
            h.check(f"{name}: the aligned centre mesh, not the corridors", dock.mesh.corridors.isChecked() and dock.mesh.corridor_generator.currentData() == strips.get("generator"), dock.mesh.corridor_generator.currentData())
        dock.model.compare_job(original)  # again, with the type the scenario is
        yield lambda: dock.model.comparison is not None
        dock_words, dock_found = dock.model.comparison
        held = {section.key: section.standing(kind) for section in dock.sections}
        path = dock.model.save_scenario(name)
        h.check(f"{name}: saved as a scenario", path is not None and path.is_file(), str(path))
        out = W102 / "rebuilt" / stem
        made = {}

        def built(job_path, made=made):
            made["job"] = json.loads(Path(job_path).read_text(encoding="utf-8"))

        def failed(text, made=made):
            made["error"] = text

        values = dock._collect()
        values["output"] = str(out)
        dock._prepare(values, out, built, failed, lambda text, _tone="info": None)
        yield lambda: made
        h.check(f"{name}: the dock writes its job, as Run does", "job" in made, made.get("error", ""))
        if "job" not in made:
            continue
        engine_found = not_held(resolved(original), resolved(made["job"]))
        layers = {
            layer.name(): layer.source() for layer in QgsProject.instance().mapLayers().values()
            if "imported_inputs" in layer.source()
        }  # fmt: skip
        report[name] = {
            "job": str(source),
            "scenario": str(path),
            "rebuilt_job": str(out / "job.json"),
            "model_type": kind,
            "import_words": words,
            "dock_comparison": dock_words,
            "not_held_by_the_engines_reading": engine_found,
            "inline_layers": layers,
            "sections": {key: [status.state, status.words] for key, status in held.items()},
        }
        h.log(f"{name}: not held by the engine's reading: {json.dumps(engine_found)}")
        h.check(f"{name}: the dock's own comparison and the engine's agree on the sections", set(dock_found or {}) <= set(engine_found) | {"Other"} or not dock_found, (dock_found, engine_found))
    (W102 / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    h.check("the report written", (W102 / "report.json").is_file())
