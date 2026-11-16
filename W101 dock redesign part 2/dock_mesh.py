"""W101 item 4 through the real dock: one Mesh section, the kind first; Build mesh on squares, the quadtree and the
aligned centre mesh, drawn under Inputs > Mesh with its words; an engine refusal in its words; the new settings in the
job; a run whose cells are the ones Build mesh drew; a model of the older dock on its own kind; one dark picture.
"""

import json
from pathlib import Path


def scenario(h):
    import importlib.util

    from qgis.core import QgsApplication, QgsProject

    spec = importlib.util.spec_from_file_location("w101_help", Path(h.SCENARIO).parent / "w101_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from wadi2d_qgis import suggest_lines
    from wadi2d_qgis.layer_groups import SLOT, SLOT_MESH, find_model, model_name

    m = dock.mesh
    out = h.RUNS / "built"
    h.set_rain_job(dock, ground, "mesh_run", dx=30.0, rain=10.0, hours=0.25, sim_hours=0.25, pixels=False)
    m.setCollapsed(False)

    def mesh_layers():
        top = find_model(model_name(dock.panel.folder.filePath()))
        nodes = [n for n in top.findLayers() if n.customProperty(SLOT) == SLOT_MESH] if top is not None else []
        return [n.layer() for n in nodes]

    def build(label):
        m.preview_button.click()
        yield lambda: m.preview_button.isEnabled()
        h.log(f"{label}: {m.summary.text()}")
        return json.loads((Path(dock._mesh_folder) / "mesh.json").read_text(encoding="utf-8")) if dock._mesh_folder else {}

    def shown(widget):
        return widget.isVisibleTo(m)

    h.log("=== 1 the kind first")
    from qgis.PyQt.QtWidgets import QLabel

    row = m.form.getWidgetPosition(m.kind)[0]
    above = [m.form.itemAt(r, m.form.SpanningRole) or m.form.itemAt(r, m.form.FieldRole) for r in range(row)]
    h.check("Mesh kind is the section's first input, under the card's words", all(isinstance(i.widget(), QLabel) for i in above), (row, [type(i.widget()).__name__ for i in above]))
    h.check("three kinds, squares to start", [m.kind.itemData(i) for i in range(m.kind.count())] == ["squares", "quadtree", "aligned"] and m.kind.currentData() == "squares")
    h.check("squares: no quadtree or aligned sizes", not shown(m.quad_box) and not shown(m.aligned_box))
    h.check("Advanced closed, local time stepping not offered on squares", not m.advanced.is_open() and not shown(m.local_steps))
    m.set_kind("quadtree")
    h.check("quadtree: its sizes, the mesh tick on", shown(m.quad_box) and m.enabled.isChecked() and not m.corridors.isChecked())
    m.advanced.set_open(True)
    h.check("local time stepping under Advanced, on with the quadtree", shown(m.local_steps) and m.local_steps.isChecked())
    m.set_kind("aligned")
    h.check("aligned: the centre mesh, the corridors tick on", m.corridors.isChecked() and not m.enabled.isChecked() and m.corridor_generator.currentData() == "centres")
    h.check("its box and the gorge rows; no rings sizes", shown(m.aligned_box) and shown(m.gorge_rows) and not shown(m.corridor_cell_min))
    h.check("the cells across are Terrain's 30 m", "30 m (Terrain's cell size)" in m.across_note.text(), m.across_note.text())
    h.check("local time stepping off and gone with the quadtree", not shown(m.local_steps) and not m.local_steps.isChecked(), m.local_steps.isChecked())
    w.pick(m.corridor_generator, "rings")
    h.check("rings: the corridor sizes, no gorge rows", shown(m.corridor_cell_min) and not shown(m.gorge_rows))
    m.set_kind("squares")
    m.local_steps.setChecked(False)
    m.enabled.setChecked(True)
    h.check("an older model's tick reads as the quadtree", m.kind.currentData() == "quadtree")
    m.enabled.setChecked(False)
    m.local_steps.setChecked(False)

    h.log("=== 2 Build mesh on squares")
    h.check("the button on any kind", m.preview_button.isEnabled() and m.preview_button.text() == "Build mesh")
    summary = yield from build("squares")
    h.check("the engine's count in words", summary.get("kind") == "squares" and f"{summary['cells']:,} square cells of 30 m" in m.summary.text(), m.summary.text())
    grids = [layer for layer in mesh_layers() if layer.name().startswith("Cell grid")]
    h.check("the cell grid under Inputs > Mesh", len(grids) == 1, [layer.name() for layer in mesh_layers()])
    h.check("its tiles hold the cells counted", sum(f["cells"] for f in grids[0].getFeatures()) == summary["cells"])

    h.log("=== 3 Build mesh on the quadtree")
    m.set_kind("quadtree")
    m.coarse.setValue(120.0)
    summary = yield from build("quadtree")
    h.check("its words: fewer cells, the smallest", summary.get("kind") == "quadtree" and "fewer than the uniform grid" in m.summary.text() and "Smallest cell 30 m" in m.summary.text(), m.summary.text())
    names = [layer.name() for layer in mesh_layers()]
    h.check("cell sizes and cell grid, the last build replaced", len(names) == 2 and any(n.startswith("Cell grid") for n in names) and any("cell size" in n for n in names), names)

    h.log("=== 4 an engine refusal, in its words")
    far = [[ground.domain.extent().xMaximum() + 50000.0, ground.domain.extent().yMaximum()], [ground.domain.extent().xMaximum() + 51000.0, ground.domain.extent().yMaximum()]]
    off = h.add_vector(h.geojson("w101_far_line", [h.line(far, name="Far away")]), "w101 far line", ground.crs)
    m.lines.layer.setLayer(off)
    yield from build("refused")
    h.check("the engine's refusal said in the section", "touches no cell of the domain" in m.summary.text() and "Far away" in m.summary.text(), m.summary.text())
    m.lines.layer.setLayer(None)

    h.log("=== 5 Suggest, then Build mesh on the aligned centre mesh")
    m.set_kind("aligned")
    m.suggest_button.click()
    yield lambda: dock.panel.message.text() != suggest_lines.WORKING
    found = [layer for layer in QgsProject.instance().mapLayers().values() if layer.name().startswith("Suggested breaklines")]
    h.check("a suggestion layer", len(found) >= 1, dock.panel.message.text()[:200])
    m.corridor_layer.setLayer(found[-1])
    h.check("the card Ready in words", dock.status_links.refresh()["mesh"].state == "ready", dock.status_links.refresh()["mesh"])
    summary = yield from build("aligned")
    h.check("its words: aligned cells, squares, the smallest", summary.get("kind") == "aligned" and "aligned along the streams" in m.summary.text() and "Smallest cell" in m.summary.text(), m.summary.text())
    names = [layer.name() for layer in mesh_layers()]
    h.check("the aligned cells over the cell grid", names[:2] == ["Wadi2D mesh, aligned cells", names[1]] and names[1].startswith("Cell grid"), names)
    cells = next(layer for layer in mesh_layers() if layer.name() == "Wadi2D mesh, aligned cells")
    h.check("one polygon a cell", cells.featureCount() == summary["aligned"], (cells.featureCount(), summary["aligned"]))
    w.big_shot(h, dock, "mesh_aligned", open_only="mesh")

    h.log("=== 6 the new settings in the job")
    m.stream_area.setValue(2.5)
    m.bank_scarp.setValue(1.5)
    m.gorge_rows.setValue(4)
    job = w.built(dock, out)
    h.check("Suggest's streams without the quadtree", job.get("mesh") == {"stream_area_mid_km2": 2.5}, job.get("mesh"))
    h.check("the floor's scarp", job["breaklines"].get("bank_scarp_m") == 1.5, job["breaklines"])
    h.check("the gorge rows of the centre mesh", job["strips"].get("gorge_rows") == 4 and job["strips"]["generator"] == "centres", job["strips"])
    cfg = w.validated(job)
    h.check("the engine's schema takes them", cfg.strips.gorge_rows == 4 and cfg.mesh.stream_area_mid_km2 == 2.5 and not cfg.mesh.enabled)
    before = w.built(dock, out)
    doc = dock.model.collect()
    dock.model.reset()
    dock.model.apply(doc)
    h.check("saved and brought back: the same job", w.built(dock, out) == before)
    h.check("and the same kind", m.kind.currentData() == "aligned")
    m.stream_area.setValue(1.0)
    m.bank_scarp.setValue(1.0)
    m.gorge_rows.setValue(0)
    job = w.built(dock, out)
    h.check("at the engine's values none of them is written", "mesh" not in job and "bank_scarp_m" not in job["breaklines"] and "gorge_rows" not in job["strips"], (job.get("mesh"), job["breaklines"]))

    h.log("=== 7 a run steps the cells Build mesh drew")
    summary = yield from build("aligned again")
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    yield from h.run(dock)
    run = dock.results_dir
    done = h.events(run, "done")
    h.check("finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text())
    strips = h.events(run, "strips")[-1]
    start = h.events(run, "start")[-1]
    h.log(f"run: start {start.get('cells')} squares, strips {strips}")
    h.check("as many aligned cells", strips["cells"] + strips["triangles"] == summary["aligned"], (strips, summary["aligned"]))
    h.check("as many squares", start["cells"] == summary["squares"], (start["cells"], summary["squares"]))
    h.check("the same squares replaced", strips["replaced"] == summary["replaced"], (strips["replaced"], summary["replaced"]))

    h.log("=== 8 one dark picture")
    try:
        QgsApplication.instance().setUITheme("Night Mapping")
        w.big_shot(h, dock, "mesh_aligned_dark", open_only="mesh")
        h.log("dark picture taken")
    finally:
        QgsApplication.instance().setUITheme("default")
