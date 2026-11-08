"""W45 through the real dock: Suggest breaklines on Bidah, corridors from the suggestion in the Mesh section, a run on
them against the same run on squares, the corridor layers under Model setup, the pixel maps carrying the corridors."""

import json
import sqlite3

from qgis.core import QgsProject


def layers_named(prefix):
    return [ly for ly in QgsProject.instance().mapLayers().values() if ly.name().startswith(prefix)]


def scenario(h):
    from pathlib import Path

    h.VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from wadi2d_qgis import suggest_lines

    m = dock.mesh
    h.check("corridor controls in the Mesh section", m.corridors.text().startswith("Corridors"), m.corridors.text())
    h.check("corridor controls off until ticked", not m.corridors.isChecked() and not m.corridor_layer.isEnabled())
    h.check("defaults from the schema", m.corridor_cell_min.value() == 20.0 and m.corridor_cell_max.value() == 50.0 and m.corridor_fraction.value() == 0.25 and m.corridor_outside.value() == 1, (m.corridor_cell_min.value(), m.corridor_cell_max.value(), m.corridor_fraction.value(), m.corridor_outside.value()))

    h.log("=== 1 corridors without the suggestion layer are refused")
    h.set_rain_job(dock, ground, "corridors", dx=20.0, hours=1.0, sim_hours=2.0)
    dock.points.layer.setLayer(ground.lines)
    m.setCollapsed(False)
    m.corridors.setChecked(True)
    h.check("controls on when ticked", m.corridor_layer.isEnabled() and m.corridor_cell_min.isEnabled())
    m.corridor_layer.setLayer(None)
    dock.panel.run_button.click()
    yield lambda: dock.run is not None or "Suggested breaklines" in dock.panel.message.text()
    h.check("refused without the layer", dock.run is None and "Suggested breaklines" in dock.panel.message.text(), dock.panel.message.text())

    h.log("=== 2 suggest the banks")
    h.check(
        "Suggest settings from the schema",
        m.bank_rise.value() == 2.0 and m.bank_reach.value() == 300.0 and m.bank_depth.value() == 0.2 and m.crest_height.value() == 0.5 and m.crest_disc.value() == 40.0,
        (m.bank_rise.value(), m.bank_reach.value(), m.bank_depth.value(), m.crest_height.value(), m.crest_disc.value()),
    )
    h.check("no depth map chosen", m.bank_depth_layer.currentLayer() is None and "bank_depth_map" not in m.breakline_values())
    h.check("the bank offset is one cell and reaches the values", m.bank_offset.value() == 1.0 and m.breakline_values()["bank_offset_cells"] == 1.0, m.breakline_values())
    m.bank_rise.setValue(3.0)
    m.suggest_button.click()
    yield lambda: dock.panel.message.text() != suggest_lines.WORKING
    lines = layers_named("Suggested breaklines")
    h.check("one suggestion layer", len(lines) == 1, len(lines))
    h.check("the words name the bank rule", "Banks: ground 3 m over the bed of the wadi" in dock.panel.message.text(), dock.panel.message.text()[:260])
    layer = lines[0]
    sfolder = Path(layer.source().split("|")[0]).parent
    sjob = json.loads((sfolder / "job.json").read_text(encoding="utf-8"))
    h.check("the suggestion's job carries the settings", sjob.get("breaklines", {}).get("bank_rise_m") == 3.0 and sjob["breaklines"].get("crest_height_m") == 0.5 and "bank_depth_map" not in sjob["breaklines"], sjob.get("breaklines"))
    m.bank_rise.setValue(2.0)
    m.corridor_layer.setLayer(layer)
    h.check("the layer's file is the banks file", m.corridor_values()["banks"].endswith("suggested_breaklines.gpkg"), m.corridor_values())
    h.check("the width rule reaches the job values", m.corridor_values()["cell_min_m"] == 20.0 and m.corridor_values()["cell_max_m"] == 50.0 and m.corridor_values()["width_fraction"] == 0.25 and m.corridor_values()["rows_outside"] == 1, m.corridor_values())
    h.widget_shot("mesh_corridors", m)

    h.log("=== 3 run with corridors")
    dock.panel.folder.setFilePath(str(h.RUNS / "corridors"))
    yield from h.run(dock)
    folder = h.RUNS / "corridors"
    done = h.events(folder, "done")
    h.check("run finished", done and done[-1]["code"] == 0, dock.panel.message.text())
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    strips_job = job.get("strips", {})
    h.check("job carries the banks file", strips_job.get("enabled") and strips_job.get("banks", "").endswith("suggested_breaklines.gpkg"), strips_job)
    built = h.events(folder, "strips")
    h.check("corridors built from the banks", built and built[-1]["corridors"] >= 1 and built[-1]["cells"] > 0, built[-1] if built else None)
    rules = built[-1].get("rules", []) if built else []

    def expected_cells(width):  # the schema's rule: a quarter of the width held between 20 and 50 m, the nearest whole number of cells
        return max(1, round(width / min(max(0.25 * width, 20.0), 50.0)))

    h.check(
        "the width rule reported per corridor",
        rules and all(r["cells_across"] == expected_cells(r["width_m"]) and abs(r["across_m"] - r["width_m"] / r["cells_across"]) < 0.2 for r in rules),
        rules[:4],
    )
    h.check("job carries the width rule", strips_job.get("cell_min_m") == 20.0 and strips_job.get("cell_max_m") == 50.0 and strips_job.get("width_fraction") == 0.25 and strips_job.get("rows_outside") == 1, strips_job)
    h.log(f"strips event: {built[-1] if built else None}")
    h.check("books close", done and abs(done[-1]["balance"]["relative_error"]) < 1e-6, done[-1]["balance"]["relative_error"] if done else None)
    h.check("GPU took the run", done and h.events(folder, "start")[-1].get("backend", "") == "gpu", h.events(folder, "start")[-1].get("backend") if done else None)
    gpkg = folder / "maps" / "strip_mesh.gpkg"
    h.check("strip mesh written", gpkg.is_file(), gpkg)
    with sqlite3.connect(gpkg) as db:
        kinds = dict(db.execute("SELECT kind, COUNT(*) FROM strip_faces GROUP BY kind").fetchall())
        cells = db.execute("SELECT COUNT(*), MAX(max_depth_m) FROM strip_cells").fetchone()
    h.check("faces on the banks, at the join and inside", kinds.get("breakline", 0) > 0 and kinds.get("interface", 0) > 0 and kinds.get("inner", 0) > 0, kinds)
    h.check("cells with water", cells[0] > 0 and cells[1] > 0.0, cells)
    cell_layers = layers_named("Corridor cells")
    face_layers = layers_named("Corridor faces")
    h.check("corridor layers loaded", len(cell_layers) == 1 and len(face_layers) == 1, (len(cell_layers), len(face_layers)))
    setup = h.group_of(folder.name).findGroup("Model setup")
    names = [node.name() for node in setup.findLayers()] if setup is not None else []
    h.check("under Model setup beside the cell grid", any(n.startswith("Corridor cells") for n in names) and any(n.startswith("Cell grid") for n in names), names)
    stats = json.loads((folder / "pixels" / "pixels.json").read_text(encoding="utf-8"))
    h.check("pixel maps carry the corridors", stats.get("strip_pixels", 0) > 0 and stats.get("strip_depth_max_m", 0.0) > 0.0, {k: stats.get(k) for k in ("kept_cells", "strip_pixels", "strip_depth_max_m")})
    h.check("Make map available", dock.panel.map_button.isEnabled())
    depth = layers_named("Maximum depth")
    if depth and cell_layers:
        centre = cell_layers[0].extent().center()
        h.render("corridors_close", [face_layers[0], cell_layers[0], depth[0], ground.dem], centre, 3000)
    peaks = h.peaks(folder)
    h.log(f"peaks with corridors {peaks}")

    h.log("=== 4 the same run on squares alone")
    m.corridors.setChecked(False)
    dock.panel.folder.setFilePath(str(h.RUNS / "squares"))
    yield from h.run(dock)
    plain = h.RUNS / "squares"
    done2 = h.events(plain, "done")
    h.check("squares run finished", done2 and done2[-1]["code"] == 0, dock.panel.message.text())
    h.check("no corridors without the tick", not h.events(plain, "strips") and "strips" not in json.loads((plain / "job.json").read_text(encoding="utf-8")))
    h.check("no corridor layers for it", len(layers_named("Corridor cells")) == 1)
    peaks2 = h.peaks(plain)
    h.log(f"peaks on squares {peaks2}")
    for name, peak in peaks.items():
        if peaks2.get(name, 0.0) > 1.0:
            ratio = peak / peaks2[name]
            h.check(f"line {name} within 10 % of the squares", 0.9 <= ratio <= 1.1, round(ratio, 3))

    h.log("=== 5 corridors with the mesh refinement are refused")
    m.corridors.setChecked(True)
    m.enabled.setChecked(True)
    dock.panel.folder.setFilePath(str(h.RUNS / "both"))
    dock.panel.run_button.click()
    yield lambda: dock.run is not None or "uniform grid" in dock.panel.message.text()
    h.check("refused together", dock.run is None and "uniform grid" in dock.panel.message.text(), dock.panel.message.text())
    m.enabled.setChecked(False)
    m.corridors.setChecked(False)
    h.shot("end")
