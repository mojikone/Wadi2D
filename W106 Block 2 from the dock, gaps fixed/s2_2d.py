"""W106 session 2 through the real dock: the 2D model.

The project of session 1 opened in a fresh QGIS, the dock restoring the model. The 2D card, its own folder. First the
CN grid's holes with no value beside it: Run says so with the count of cells, before the engine (gap 1); then 88 beside
the grid. The Mesh section: the aligned centre mesh, Suggest breaklines, Build mesh; the 2D part of the area reduction
at 100 km2 on ARF FM; Run. The run writes each dam's 2D pool as an element of record (gap 8). Saved as the scenario 2D.
"""

import json
from pathlib import Path


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w106_help", Path(h.SCENARIO).parent / "w106_help.py")
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
    domain = dock.terrain.domain.currentLayer()
    h.check("the aligned domain restored", domain is not None and domain.name().startswith("Domain aligned"), domain.name() if domain else None)
    iface.mapCanvas().setExtent(domain.extent())
    hyd = dock.hydrology
    hyd.setCollapsed(False)
    h.check("the CN value 88 restored beside the grid", hyd.cn.raster.currentLayer() is not None and hyd.cn.box.value() == w.NUMBERS["curve_number_fill"], (hyd.cn.box.value(), hyd.cn.box.text()))

    mesh = dock.mesh
    mesh.setCollapsed(False)
    h.log("=== the Mesh section: the aligned centre mesh, Suggest breaklines, Build mesh")
    mesh.kind.setCurrentIndex(mesh.kind.findData("aligned"))
    mesh.kind.activated.emit(mesh.kind.currentIndex())
    h.check("aligned kind made from centres", mesh.current_kind() == "aligned" and mesh.corridor_generator.currentData() == "centres", (mesh.current_kind(), mesh.corridor_generator.currentData()))
    dock.panel.folder.setFilePath(str(w.RUNS / w.MODELS["2d"]))
    steps.begin("Suggest breaklines")
    mesh.suggest_button.click()
    yield lambda: getattr(mesh, "suggester", None) is not None and mesh.suggester.query is None
    steps.end("Suggest breaklines", dock.panel.message.text())
    suggested = w.find_layer("Suggested breaklines")
    h.check("the Suggested breaklines layer loaded", suggested is not None, dock.panel.message.text()[:300])
    if suggested is not None and suggested.isEditable():
        suggested.commitChanges()
    mesh.corridor_layer.setLayer(suggested)
    w.set_reduction(h, dock, None, w.NUMBERS["grid_area_km2"])
    h.check("the 2D part reads the curve at 100 km2", "0.91" in dock.reduction.grid.factor.text(), dock.reduction.grid.factor.text())
    dock.panel.limiter.setChecked(True)
    w.set_simulation(h, dock)
    steps.begin("Build mesh")
    mesh.preview_button.click()
    yield lambda: mesh.preview_button.isEnabled() and not mesh.summary.text().startswith("Building the mesh")
    steps.end("Build mesh", mesh.summary.text())
    w.big_shot(h, dock, f"{session}_mesh_built", open_only="mesh")

    h.log("=== gap 1: the CN grid's holes with no value beside it, said before the run")
    dock.panel.folder.setFilePath(str(w.RUNS / "2D_cn_check"))
    hyd.cn.box.setValue(hyd.cn.box.minimum())
    steps.begin("Run with no CN for the grid's holes")
    dock.panel.run_button.click()
    yield lambda: True
    said = dock.panel.message.text()
    steps.end("Run with no CN for the grid's holes", said)
    h.check("gap 1: Run stops before the engine and gives the count of cells without a CN", dock.run is None and "The CN grid gives no value on" in said and "cells of 20 m" in said, said[:400])
    w.big_shot(h, dock, f"{session}_cn_refused", open_only="hydrology")
    hyd.cn.box.setValue(w.NUMBERS["curve_number_fill"])
    dock.panel.folder.setFilePath(str(w.RUNS / w.MODELS["2d"]))

    job = w.job_of(dock)
    h.log(f"2D job: strips {job.get('strips')} | hydrology {job['hydrology']} | terrain cn {job['terrain'].get('cn_raster')} | run {job['run']}")
    h.check("the 2D job: CN 88 beside the grid, no lumped part", job["hydrology"].get("curve_number") == 88.0 and not job["hydrology"].get("basin_json"), job["hydrology"])
    w.save_project(h)

    folder = yield from w.run_and_time(h, dock, steps, f"Run 2D ({session})", 3.0)
    done = h.events(folder, "done") if folder else []
    finished = bool(done) and done[-1].get("code") == 0
    h.log(f"2D outcome: finished {finished}; the dock says: {dock.panel.message.text()[:1500]}")
    pools = json.loads((folder / "pools.json").read_text(encoding="utf-8")) if folder and (folder / "pools.json").is_file() else {}
    h.log(f"gap 8: pools {json.dumps(pools.get('dams', []))[:1500]}")
    h.check("gap 8: the run writes the five dams' 2D pools", sum(1 for d in pools.get("dams", []) if d.get("peak_inflow_m3s")) == 5, [d.get("dam") for d in pools.get("dams", [])])
    w.big_shot(h, dock, f"{session}_run_2d", open_only="run")
    if finished:
        dock.panel.results_button.click()
        yield lambda: True
        w.big_shot(h, dock, f"{session}_results_2d")
        dock.types.show_model()
        w.save_scenario(h, dock, "2D")
    w.save_project(h)
