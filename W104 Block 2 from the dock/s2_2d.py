"""W104 session 2 through the real dock: the 2D model.

The project of session 1 opened in a fresh QGIS, the dock restoring the model. The 2D card; its own output folder;
the Mesh section: the aligned centre mesh, Suggest breaklines on the domain, its layer chosen, Build mesh; the 2D part
of the area reduction at 100 km2 on the ARF FM curve; Run (the CN grid is session 1's, its holes filled with 88 in
QGIS). Saved as the scenario 2D; the project saved.
"""

import json
from pathlib import Path


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w104_help", Path(h.SCENARIO).parent / "w104_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    w.limits(h, 4.0)
    session = Path(h.P).name
    steps = w.Steps(h, session)
    from qgis.utils import iface

    steps.begin("open the project")
    w.read_project(h)
    steps.end("open the project")
    dock = yield from h.open_dock(all_sections=False)
    yield lambda: dock.model.ready
    h.log(f"restored: page {dock.types.page}, type {dock.types.kind}, folder {dock.panel.folder.filePath()}; {dock.model_bar.message.text()[:300]}")
    w.card(dock, "2d")
    dock.panel.folder.setFilePath(str(w.RUNS / w.MODELS["2d"]))
    domain = dock.terrain.domain.currentLayer()
    h.check("the aligned domain restored", domain is not None and domain.name().startswith("Domain aligned"), domain.name() if domain else None)
    iface.mapCanvas().setExtent(domain.extent())

    mesh = dock.mesh
    mesh.setCollapsed(False)
    if mesh.current_kind() != "aligned" or mesh.corridor_layer.currentLayer() is None:
        h.log("=== the Mesh section: the aligned centre mesh, Suggest breaklines, Build mesh")
        mesh.kind.setCurrentIndex(mesh.kind.findData("aligned"))
        mesh.kind.activated.emit(mesh.kind.currentIndex())  # a user's choice in the combo
        h.check("aligned kind made from centres", mesh.current_kind() == "aligned" and mesh.corridor_generator.currentData() == "centres", (mesh.current_kind(), mesh.corridor_generator.currentData()))
        steps.begin("Suggest breaklines")
        mesh.suggest_button.click()
        yield lambda: getattr(mesh, "suggester", None) is not None and mesh.suggester.query is None
        steps.end("Suggest breaklines", dock.panel.message.text())
        suggested = w.find_layer("Suggested breaklines")
        h.check("the Suggested breaklines layer loaded", suggested is not None, dock.panel.message.text()[:300])
        if suggested is not None and suggested.isEditable():
            suggested.commitChanges()  # nothing deleted: the suggestion as it stands, saved
        mesh.corridor_layer.setLayer(suggested)
        w.big_shot(h, dock, f"{session}_mesh_suggested", open_only="mesh")
        w.render_map(h, f"{session}_suggested", [w.find_layer("Thalwegs"), suggested, domain], domain)
    else:
        h.log(f"the mesh as session 2a left it: {mesh.corridor_layer.currentLayer().name()}")
    w.set_reduction(h, dock, None, w.NUMBERS["grid_area_km2"])
    h.check("the 2D part reads the curve at 100 km2", "0.91" in dock.reduction.grid.factor.text(), dock.reduction.grid.factor.text())
    w.big_shot(h, dock, f"{session}_reduction_2d", open_only="reduction")

    hyd = dock.hydrology
    hyd.setCollapsed(False)
    if hyd.cn.box.isEnabled():  # the dock fix of W104: a value beside the CN grid, for the cells it gives none
        hyd.cn.box.setValue(w.NUMBERS["curve_number_fill"])
    h.log(f"curve number: raster {hyd.cn.raster.currentLayer().name() if hyd.cn.raster.currentLayer() else None}, value box enabled {hyd.cn.box.isEnabled()}, value {hyd.cn.box.value()}")
    w.big_shot(h, dock, f"{session}_hydrology_2d", open_only="hydrology")
    dock.panel.limiter.setChecked(True)
    w.set_simulation(h, dock)

    if not mesh.summary.text().startswith("Built"):
        steps.begin("Build mesh")
        mesh.preview_button.click()
        yield lambda: mesh.preview_button.isEnabled() and not mesh.summary.text().startswith("Building the mesh")
        steps.end("Build mesh", mesh.summary.text())
        w.big_shot(h, dock, f"{session}_mesh_built", open_only="mesh")
        aligned = w.find_layer("Aligned cells") or w.find_layer("Aligned")
        w.render_map(h, f"{session}_mesh", [w.find_layer("Cell grid"), aligned, domain], domain)

    job = w.job_of(dock)
    h.log(f"2D job: storm {json.dumps(job.get('storm'))[:500]} | strips {job.get('strips')} | hydrology {job['hydrology']} | terrain cn {job['terrain'].get('cn_raster')} | run {job['run']}")
    statuses = dock.status_links.refresh()
    h.log("status: " + "; ".join(f"{k}: {v.state} {v.words[:120]}" for k, v in statuses.items()))
    w.save_project(h)

    folder = yield from w.run_and_time(h, dock, steps, f"Run 2D ({session})", 3.0)
    done = h.events(folder, "done") if folder else []
    finished = bool(done) and done[-1].get("code") == 0
    h.log(f"2D outcome: finished {finished}; the dock says: {dock.panel.message.text()[:1500]}")
    w.big_shot(h, dock, f"{session}_run_2d", open_only="run")
    if finished:
        dock.panel.results_button.click()
        yield lambda: True
        w.big_shot(h, dock, f"{session}_results_2d")
        dock.types.show_model()
        w.save_scenario(h, dock, "2D")
    w.save_project(h)
