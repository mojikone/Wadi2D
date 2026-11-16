"""W101 item 1 through the real dock: the rain sources, the Area reduction in two parts and the Data tables.

The sections in their places; Data tables holding patterns and curves with their charts; the six rain sources, the
Steady rain's mm/h still giving its old depth; the parts shown by model type; the job of each choice, taken by the
engine's own schema; a real run on Bidah with a depth, a pattern of Data tables and the 2D part's own reduction; the
model saved and brought back to the same job; a model of format 2 opened, its steady rain and design storm moved in
words.
"""

import json
from pathlib import Path

PATTERN = {"time": [0.0, 25.0, 100.0], "depth": [0.0, 60.0, 100.0], "time_units": "percent", "form": "cumulative"}
CURVE = {"areas_km2": [1.0, 10.0, 100.0, 1000.0], "factors": [1.0, 0.97, 0.913, 0.7], "reduces_below_table": True}


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w101_help", Path(h.SCENARIO).parent / "w101_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from wadi2d_qgis import model_doc
    from wadi2d_qgis.reduction_rows import factor_at
    from wadi2d_qgis.section_status import MISSING, OPTIONAL, READY

    storm, arf, tables = dock.storm, dock.reduction, dock.tables
    out = h.RUNS / "built"

    h.log("=== 1 the two new sections in their places")
    keys = [s.key for s in dock.sections]
    h.check("Data tables before Storm, Area reduction after it", keys[2:6] == ["hydrology", "tables", "storm", "reduction"], keys)
    h.check("their titles", tables.title() == "3b. Data tables" and arf.title() == "4b. Area reduction", (tables.title(), arf.title()))
    statuses = dock.status_links.refresh()
    h.check("each has a card and a step", all(k in dock.cards and k in dock.strip.steps for k in ("tables", "reduction")), list(dock.strip.steps))
    h.check("an empty store is optional, in words", statuses["tables"].state == OPTIONAL and "None" in statuses["tables"].words, statuses["tables"])

    h.log("=== 2 Data tables: a pattern and a curve, each with its chart")
    name = tables.add_table("patterns", "Front loaded", PATTERN)
    curve = tables.add_table("arf_curves", "Block 2", CURVE)
    h.check("the store holds both", name in tables.store["patterns"] and curve in tables.store["arf_curves"])
    h.check("the curve shown, drawn on log area", tables.kind() == "arf_curves" and tables.chart.log_x and len(tables.chart.xs) == 4, (tables.chart.xs, tables.chart.log_x))
    h.check("status Ready, counted", dock.status_links.refresh()["tables"] == (READY, "1 pattern \N{MIDDLE DOT} 1 curve"), dock.status_links.refresh()["tables"])
    second = tables.add_table("arf_curves", "Block 2")
    h.check("a second of the same name takes the next free one", second == "Block 2 2", second)
    tables.pairs.set_rows([(100.0, 0.9), (10.0, 0.95)])
    state = dock.status_links.refresh()["tables"]
    h.check("a table the engine would refuse makes the section Missing, in words", state.state == MISSING and "must rise" in state.words, state)
    h.check("and says so under the table", "must rise" in tables.problem.text(), tables.problem.text())
    tables.name_edit.setText("Scratch")
    tables.rename_button.click()
    h.check("renamed in place", "Scratch" in tables.store["arf_curves"] and second not in tables.store["arf_curves"])
    tables.remove_button.click()
    h.check("removed", list(tables.store["arf_curves"]) == [curve], list(tables.store["arf_curves"]))
    tables.which.setCurrentIndex(tables.which.findData("patterns"))
    h.check("the pattern drawn as the share fallen", tables.chart.ys[-1] == 1.0 and tables.chart.xs == [0.0, 25.0, 100.0], (tables.chart.xs, tables.chart.ys))
    w.big_shot(h, dock, "tables_pattern", open_only="tables")
    tables.which.setCurrentIndex(tables.which.findData("arf_curves"))
    w.big_shot(h, dock, "tables_curve", open_only="tables")

    h.log("=== 3 the rain sources")
    sources = [storm.kind.itemData(i) for i in range(storm.kind.count())]
    h.check("six sources, the Steady rain retired", sources == ["fixed", "depth", "depth_grid", "gridded", "gauges", "hyetograph"], sources)
    h.check("a fixed depth first", storm.kind.currentData() == "fixed")
    h.set_rain_job(dock, ground, "rain_a", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=False)
    job = w.built(dock, out)
    h.check("an older check's mm/h gives the job Steady rain wrote", job["storm"] == {"kind": "uniform", "depth_mm": 20.0, "duration_min": 30.0}, job["storm"])
    h.check("the Storm card says so", dock.status_links.refresh()["storm"].words.startswith("Fixed depth 20 mm over 0.5 h"), dock.status_links.refresh()["storm"])
    h.check("the patterns of Data tables are offered", storm.depth_pattern.findData(f"table:{name}") >= 0)
    w.pick(storm.kind, "depth")
    storm.depth_mm.setValue(157.0)
    w.pick(storm.depth_pattern, "scs:II")
    h.check("an SCS curve sets 24 h", storm.depth_hours.value() == 24.0)
    job = w.built(dock, out)
    h.check("depth and SCS II: the engine takes it", job["storm"]["pattern"] == {"kind": "scs", "scs_type": "II"} and w.validated(job).storm.duration_min == 1440.0, job["storm"])
    storm.depth_hours.setValue(6.0)
    h.check("an SCS curve over 6 h is refused in words", any("24-hour" in p for p in w.problems_of(dock, out)), w.problems_of(dock, out))
    w.pick(storm.depth_pattern, f"table:{name}")
    job = w.built(dock, out)
    h.check("a pattern of Data tables: named, and carried", job["storm"]["pattern"] == {"kind": "table", "table": name} and list(job["data_tables"]["patterns"]) == [name], job.get("data_tables"))
    h.check("the engine fills it in", w.validated(job).storm.pattern.values.depth == PATTERN["depth"])
    w.big_shot(h, dock, "storm_depth_pattern", open_only="storm")
    raster = w.constant_raster(h.DATA / "depth_50mm.tif", ground.dem, 50.0)
    depth_layer = h.add_raster(raster, "w101 depth grid")
    w.pick(storm.kind, "depth_grid")
    storm.depth_raster.setLayer(depth_layer)
    storm.grid_hours.setValue(1.0)
    w.pick(storm.grid_pattern, "uniform")
    job = w.built(dock, out)
    h.check("a depth grid: its file, no pattern for uniform", job["storm"]["kind"] == "depth_grid" and Path(job["storm"]["depth_grid"]) == raster.resolve() and "pattern" not in job["storm"], job["storm"])
    w.validated(job)

    h.log("=== 4 the parts by model type")
    arf.setCollapsed(False)
    for kind, lumped, grid in (("2d", False, True), ("lumped", True, False), ("hybrid_lumped", True, True), (None, True, True)):
        dock.types.choose(kind)
        h.check(f"{kind}: lumped part {'shown' if lumped else 'hidden'}, 2D part {'shown' if grid else 'hidden'}", arf.lumped.isVisibleTo(arf) == lumped and arf.grid.isVisibleTo(arf) == grid, (arf.lumped.isVisibleTo(arf), arf.grid.isVisibleTo(arf)))
    w.pick(storm.kind, "hyetograph")
    h.check("observed rain: the parts off, said", not arf.lumped.isEnabled() and "rain itself" in arf.source_note.text(), arf.source_note.text())
    h.check("its status Optional", dock.status_links.refresh()["reduction"].state == OPTIONAL)

    h.log("=== 5 the job of each reduction")
    w.pick(storm.kind, "fixed")
    storm.fixed_depth.setValue(20.0)
    storm.hours.setValue(0.5)
    for box in (arf.lumped, arf.grid):
        w.pick(box.form, "area")
        w.pick(box.curve, curve)
        box.area.setValue(100.0)
    h.check("the factor at the area shown, as the engine reads it", f"{factor_at(CURVE, 100.0):.4f}" in arf.grid.factor.text() and arf.grid.chart.mark == (100.0, 0.913), (arf.grid.factor.text(), arf.grid.chart.mark))
    job = w.built(dock, out)
    h.check("one area for both parts: the single-storm form of before", job["storm"].get("storm_area_km2") == 100.0 and job["storm"]["arf"]["factors"] == CURVE["factors"] and "area_reduction" not in job["storm"] and "data_tables" not in job, job["storm"])
    w.pick(arf.lumped.form, "curve")
    h.check("the lumped curve says what it reads", "enters the grid" in arf.lumped.note.text() and not arf.lumped.note.isHidden())
    job = w.built(dock, out)
    h.check("parts that differ: storm.area_reduction, the curve by name", job["storm"]["area_reduction"] == {"lumped": {"form": "curve", "curve": curve}, "grid": {"form": "area", "curve": curve, "area_km2": 100.0}} and list(job["data_tables"]["arf_curves"]) == [curve], job["storm"])
    w.validated(job)
    w.pick(arf.grid.form, "study")
    h.check("the study: refused for a single Run without its area, in words", any("single Run" in p for p in w.problems_of(dock, out)))
    arf.grid.single.setValue(74.3)
    job = w.built(dock, out)
    h.check("a single Run reads the study's curve at its area", job["storm"]["area_reduction"]["grid"] == {"form": "area", "curve": curve, "area_km2": 74.3}, job["storm"]["area_reduction"])
    h.check("the study's job reads the curve itself", w.built(dock, out, study={"n_areas": 3})["storm"]["area_reduction"]["grid"] == {"form": "curve", "curve": curve})
    h.check("the 2D part's study areas shown", not arf.study_label.isHidden())
    w.big_shot(h, dock, "reduction_split", open_only="reduction")
    w.pick(arf.lumped.form, "coefficient")
    arf.lumped.coefficient.setValue(0.0)
    h.check("a coefficient of 0: Missing, in words", dock.status_links.refresh()["reduction"].state == MISSING, dock.status_links.refresh()["reduction"])

    h.log("=== 6 a real run: a depth with a pattern of Data tables, the 2D part's own reduction")
    dock.types.choose("2d")
    w.pick(storm.kind, "depth")
    storm.depth_mm.setValue(40.0)
    storm.depth_hours.setValue(0.5)
    w.pick(storm.depth_pattern, f"table:{name}")
    w.pick(arf.grid.form, "area")
    w.pick(arf.grid.curve, curve)
    arf.grid.area.setValue(20.0)
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    dock.panel.folder.setFilePath(str(h.RUNS / "rain_run"))
    yield from h.run(dock)
    run = dock.results_dir
    done = h.events(run, "done")
    h.check("finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text())
    job = json.loads((run / "job.json").read_text(encoding="utf-8"))
    h.check("the run's job: a depth, its pattern by name, the 2D part alone", job["storm"]["kind"] == "depth" and job["storm"]["area_reduction"] == {"grid": {"form": "area", "curve": curve, "area_km2": 20.0}} and job["run"]["model_type"] == "2d", job["storm"])
    records = [e for e in h.events(run, "output") if e.get("kind") == "area_reduction"]
    grid_record = next((e for e in records if e.get("part") == "grid"), None)
    expected = factor_at(CURVE, 20.0)
    h.check("the engine read the 2D factor the dock showed", grid_record is not None and abs(grid_record["factor"] - expected) < 1e-9, (records, expected))
    h.check("the model beside the job holds the store", "Front loaded" in json.loads((run / "model.wadi2d.json").read_text(encoding="utf-8"))["sections"]["tables"]["extra"]["store"]["patterns"])

    h.log("=== 7 saved and brought back")
    before = w.built(dock, out)
    doc = dock.model.collect()
    dock.model.reset()
    h.check("a reset empties the store", tables.store == {"patterns": {}, "arf_curves": {}})
    dock.model.apply(doc)
    after = w.built(dock, out)
    h.check("the same job after the round trip", before == after, [k for k in before if before.get(k) != after.get(k)])
    h.check("the choices by name came back", storm.depth_pattern.currentData() == f"table:{name}" and arf.grid.curve.currentData() == curve)

    h.log("=== 8 a model of format 2")
    old = {
        "format": model_doc.FORMAT, "version": 2, "model_type": None, "show_all": False, "page": "model",
        "sections": {
            "storm": {"widgets": {"kind": {"data": "single", "text": "Single hyetograph"}, "single": {"data": "uniform", "text": "Constant rain"}, "rain": 40.0, "hours": 0.5}},
        },
    }  # fmt: skip
    dock.model.reset()
    h.set_rain_job(dock, ground, "rain_old", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=False)
    steady_job = w.built(dock, out)
    words = dock.model.apply(model_doc.loads(model_doc.dumps(old)))
    h.check("its steady rain opens as a fixed depth", storm.kind.currentData() == "fixed" and storm.fixed_depth.value() == 20.0, (storm.kind.currentData(), storm.fixed_depth.value()))
    h.check("said in words", any("fixed depth of 20 mm" in text for text in words), words)
    h.check("and writes the job it wrote", w.built(dock, out)["storm"] == steady_job["storm"], (w.built(dock, out)["storm"], steady_job["storm"]))
    design = {
        "format": model_doc.FORMAT, "version": 2, "sections": {"storm": {"widgets": {
            "kind": {"data": "hypothetical", "text": ""}, "design_depth": 120.0, "design_hours": 6.0,
            "pattern": [[0.0, 0.0], [50.0, 70.0], [100.0, 100.0]], "arf_mode": {"data": "area", "text": ""},
            "storm_area": 74.3, "arf": [[10.0, 0.99], [100.0, 0.913]],
        }}},
    }  # fmt: skip
    dock.model.reset()
    words = dock.model.apply(model_doc.loads(model_doc.dumps(design)))
    h.check("a design storm opens as a depth with its pattern in Data tables", storm.kind.currentData() == "depth" and storm.depth_pattern.currentData() == "table:Design pattern" and "Design pattern" in tables.store["patterns"], (storm.kind.currentData(), storm.depth_pattern.currentData()))
    h.check("its area reduction as both parts at its area", arf.grid.form.currentData() == "area" and arf.lumped.area.value() == 74.3 and arf.grid.curve.currentData() == "Area reduction")
    h.check("said in words", any("Depth and pattern" in text for text in words) and any("Area reduction" in text for text in words), words)
    dock.model.reset()
    dock.types.choose(None)
