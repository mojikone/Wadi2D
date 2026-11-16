"""W101 item 5 through the real dock: the domain from a rough outline in Terrain. A rough outline of Bidah 30 m inside
its domain is completed upstream with the boundary lines kept, then aligned to the domain itself as one catchment;
each result is loaded as the domain with what changed and the report's areas in words; a run on the completed domain.
"""

import json
from pathlib import Path


def scenario(h):
    import importlib.util

    from qgis.core import QgsGeometry

    spec = importlib.util.spec_from_file_location("w101_help", Path(h.SCENARIO).parent / "w101_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from wadi2d_qgis.domain_links import SLOT_DOMAIN
    from wadi2d_qgis.layer_groups import SLOT, find_model, model_name

    t = dock.terrain
    out = h.RUNS / "built"
    h.set_rain_job(dock, ground, "domain_run", dx=30.0, rain=10.0, hours=0.25, sim_hours=0.25, pixels=False)
    t.setCollapsed(False)
    whole = QgsGeometry.unaryUnion([f.geometry() for f in ground.domain.getFeatures()])
    rough_geometry = whole.buffer(-30.0, 8)  # inside keep_m (50 m) of the outlets, so they stay kept edges
    rough = h.add_vector(
        h.geojson("w101_rough", [{"type": "Feature", "properties": {"name": "rough"}, "geometry": json.loads(rough_geometry.asJson())}]),
        "w101 rough outline", ground.crs,
    )  # fmt: skip
    h.log(f"Bidah's domain {whole.area() / 1e6:.3f} km2, the rough outline {rough_geometry.area() / 1e6:.3f} km2")

    def domain_layers():
        top = find_model(model_name(dock.panel.folder.filePath()))
        return [n.layer() for n in top.findLayers() if n.customProperty(SLOT) == SLOT_DOMAIN] if top is not None else []

    def press(button):
        button.click()
        yield lambda: dock.domain_links.query is None and t.complete_button.isEnabled()
        h.log(f"{button.text()}: {t.outline_words.text()}")

    h.log("=== 1 the box in Terrain, by model type")
    h.check("Domain from an outline under Terrain's domain", t.outline_box.isVisibleTo(t) and t.complete_button.text() == "Complete upstream" and t.align_button.text() == "Align to catchments")
    dock.types.choose("lumped")
    h.check("not for a Lumped model", not t.outline_box.isVisibleTo(t))
    dock.types.choose(None)
    h.check("back with no type", t.outline_box.isVisibleTo(t))

    h.log("=== 2 refused in words")
    yield from press(t.complete_button)
    h.check("no outline: said", "Choose the rough outline" in t.outline_words.text(), t.outline_words.text())
    t.outline.setLayer(rough)
    yield from press(t.align_button)
    h.check("no catchments to align to: said", "catchments to align to" in t.outline_words.text(), t.outline_words.text())

    h.log("=== 3 Complete upstream, the boundary lines kept")
    yield from press(t.complete_button)
    report = json.loads(next(Path(dock.domain_links.folder).glob("domain_report.json")).read_text(encoding="utf-8"))
    h.check("the report's areas in words", t.outline_words.text().startswith(f"Domain {report['domain_km2']:,.2f} km2, the outline of") and "completed upstream" in t.outline_words.text(), t.outline_words.text()[:200])
    h.check("the catchments draining in added", report["added_km2"] > 0.0 and report["domain_km2"] > report["outline_km2"], (report["outline_km2"], report["domain_km2"], report["added_km2"]))
    h.check("the boundary lines kept as edges", report["kept_lines"] == len(ground.outlets_data), (report["kept_lines"], len(ground.outlets_data)))
    h.check("the folder beside the run folder", Path(dock.domain_links.folder).name == "domain_run_domain", dock.domain_links.folder)
    layers = domain_layers()
    names = [layer.name() for layer in layers]
    h.check("domain and what changed under Inputs > Terrain", len(layers) == 2 and any(n.startswith("Domain completed upstream") for n in names), names)
    h.check("chosen as Terrain's domain", t.domain.currentLayer() is not None and t.domain.currentLayer().name().startswith("Domain completed upstream"), t.domain.currentLayer().name() if t.domain.currentLayer() else None)
    completed = t.domain.currentLayer()
    job = w.built(dock, out)
    written = h.add_vector(Path(job["grid"]["domain"]), "w101 job domain", ground.crs)
    area = sum(f.geometry().area() for f in written.getFeatures()) / 1e6
    h.check("the job's domain is the completed one", abs(area - report["domain_km2"]) < 1e-3, (area, report["domain_km2"]))
    w.big_shot(h, dock, "terrain_outline", open_only="terrain")

    h.log("=== 4 a run on the completed domain")
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    yield from h.run(dock)
    done = h.events(dock.results_dir, "done")
    h.check("finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text())
    ran = h.add_vector(Path(json.loads((dock.results_dir / "job.json").read_text(encoding="utf-8"))["grid"]["domain"]), "w101 run domain", ground.crs)
    area = sum(f.geometry().area() for f in ran.getFeatures()) / 1e6
    h.check("on that domain", abs(area - report["domain_km2"]) < 1e-3, (area, report["domain_km2"]))

    h.log("=== 5 Align to catchments")
    t.outline_catchments.setLayer(ground.domain)
    dock.panel.folder.setFilePath(str(h.RUNS / "domain_run"))
    yield from press(t.align_button)
    report = json.loads(next(Path(dock.domain_links.folder).glob("domain_report.json")).read_text(encoding="utf-8"))
    h.check("aligned to the one catchment, in words", "aligned to 1 catchment" in t.outline_words.text(), t.outline_words.text()[:200])
    h.check("the 30 m band added back as a gap", report["gap_added_km2"] > 0.0 and abs(report["domain_km2"] - whole.area() / 1e6) < 0.01 * whole.area() / 1e6, (report["domain_km2"], whole.area() / 1e6, report["gap_added_km2"]))
    names = [layer.name() for layer in domain_layers()]
    h.check("the completed layers replaced", len(names) == 2 and all(n.startswith("Domain aligned") for n in names), names)
    h.check("a new folder, the first kept", Path(dock.domain_links.folder).name == "domain_run_domain_2" and (h.RUNS / "domain_run_domain" / "domain.geojson").is_file(), dock.domain_links.folder)
    h.check("Terrain's domain the aligned one", t.domain.currentLayer().name().startswith("Domain aligned") and t.domain.currentLayer() is not completed)

    h.log("=== 6 saved with the model")
    doc = dock.model.collect()
    dock.model.reset()
    h.check("reset empties the outline", t.outline.currentLayer() is None)
    dock.model.apply(doc)
    h.check("the outline and the catchments come back", t.outline.currentLayer() is rough and t.outline_catchments.currentLayer() is ground.domain)
