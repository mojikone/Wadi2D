"""W106 session 1 through the real dock: Block 2 from the ground up with the gaps of W104 fixed, and the Lumped model.

His raw layers only: the DEM, his CN grid with its holes, the Manning grid, and what he drew (a rough outline, the
outflow lines, the dams' crest lines and spillways, the dam lines). As a user, all in the dock, nothing in QGIS's own
tools: the Lumped card first (its Terrain shows Domain from an outline, gap 5); the domain completed upstream from the
rough outline, the streams it sends out by closed edges named and opened with the dock's button (gap 9); the CN grid
with 88 beside it for its holes (gap 1); the reach n at its 0.1 (gap 7); the basin generated at 7.5 km2, every
subbasin with a CN (gap 2); the completed domain aligned to the generated subbasins in place (gap 4); the basin again
on it; the storm typed in; the lumped area reduction as the curve; the Lumped model run; saved.
"""

import json
from pathlib import Path

THRESHOLD_KM2 = 7.5
"""W104's search for about Basin 3's 104 subbasins ended at 7.5 km2 (108); taken as found."""


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w106_help", Path(h.SCENARIO).parent / "w106_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    w.limits(h, 3.0)
    steps = w.Steps(h, "s1")
    w.RUNS.mkdir(exist_ok=True)
    from qgis.utils import iface

    lay = w.load_inputs(h)
    iface.mapCanvas().setDestinationCrs(lay["crs"])
    iface.mapCanvas().setExtent(lay["rough_outline"].extent())
    steps.begin("open the dock")
    dock = yield from h.open_dock(all_sections=False)
    steps.end("open the dock", dock.engine_label.text())
    w.big_shot(h, dock, "01_start_page")

    h.log("=== 1 the Lumped card first: Terrain, its domain box (gap 5), the dams and the dam lines")
    w.card(dock, "lumped")
    dock.panel.folder.setFilePath(str(w.RUNS / w.MODELS["lumped"]))
    w.set_terrain(h, dock, lay)
    w.set_boundaries(h, dock, lay)  # hidden under Lumped; the 2D models of the project share the layer
    w.set_structures(h, dock, lay)
    t = dock.terrain
    h.check("gap 5: the Lumped card shows Domain from an outline", t.outline_box.isVisibleTo(t))
    t.outline.setLayer(lay["rough_outline"])
    t.outline_keep.setLayer(lay["outflow_lines"])
    steps.begin("Complete upstream")
    t.complete_button.click()
    yield lambda: dock.domain_links.query is None and t.complete_button.isEnabled()
    said = t.outline_words.text()
    steps.end("Complete upstream", said, folder=str(dock.domain_links.folder))
    completed = t.domain.currentLayer()
    h.check("the completed domain chosen as Terrain's domain", completed is not None and completed.name().startswith("Domain completed upstream"), completed.name() if completed else None)
    leaving = list(dock.domain_links.leaving)
    h.log(f"gap 9: streams leaving by closed edges: {json.dumps([{k: v for k, v in r.items() if k != 'coordinates'} for r in leaving])}")
    h.check("gap 9: the dock names the streams leaving the completed domain, the Fizh branch among them", any(r["area_km2"] > 200.0 for r in leaving) and t.outflow_button.isVisibleTo(t), said[-600:])
    w.big_shot(h, dock, "02_terrain_completed", open_only="terrain")
    before = lay["outflow_lines"].featureCount()
    t.outflow_button.click()  # Add N outflow lines there
    yield lambda: True
    added = lay["outflow_lines"].featureCount() - before
    h.check("gap 9: Add outflow lines there adds them to the Boundaries layer", added == len(leaving) and not t.outflow_button.isVisibleTo(t), (before, added, t.outline_words.text()[:300]))
    w.set_boundaries(h, dock, lay)  # their slope typed as for his own side outlets
    w.render_map(h, "02_domain_completed", [lay["outflow_lines"], lay["rough_outline"], completed], completed)

    h.log("=== 2 Hydrology: his CN grid with 88 beside it, the reach n, the basin from the DEM")
    hyd = dock.hydrology
    w.set_cn(h, dock, lay, w.NUMBERS["curve_number_fill"])
    box = hyd.basin
    box.setChecked(True)
    box.threshold.setValue(THRESHOLD_KM2)
    steps.begin("Generate basin")
    box.generate_button.click()
    yield lambda: dock._basin_query is None and box.generate_button.isEnabled()
    steps.end("Generate basin", box.summary.text(), subbasins=_count(box.model, "subbasin"))
    lacking = [e["name"] for e in (box.model or {}).get("elements", []) if e.get("kind") == "subbasin" and e.get("missing")]
    h.check("gap 2: every generated subbasin has its CN (88 where the grid has none, by area)", box.model and not lacking, (lacking, box.summary.text()[:400]))
    h.check("gap 7: the reach n box at 0.1, said where it comes from", abs(hyd.reach_n.value() - 0.1) < 1e-9 and hyd.reach_box.isVisibleTo(hyd) and "HEC-HMS" in hyd.reach_n_note.text(), hyd.reach_n.text())
    reaches = [e for e in box.model.get("elements", []) if e.get("kind") == "reach"]
    h.check("gap 7: the generated reaches hold n 0.1, the job's", reaches and all(e["parameters"]["manning_n"] == {"value": 0.1, "source": "job"} for e in reaches), reaches[0]["parameters"].get("manning_n") if reaches else None)

    h.log("=== 3 Align to catchments, on Terrain's (completed) domain in place (gap 4); the basin again")
    t.outline_catchments.setLayer(w.find_layer("Subbasins, generated"))
    completed_km2 = _area(t.domain.currentLayer())  # Align replaces the completed layers
    steps.begin("Align to catchments")
    t.align_button.click()
    h.check("gap 4: Align says it aligns Terrain's completed domain", "Terrain's domain" in t.outline_words.text() and "completed upstream" in t.outline_words.text(), t.outline_words.text())
    yield lambda: dock.domain_links.query is None and t.align_button.isEnabled()
    report = _report(dock)
    steps.end("Align to catchments", t.outline_words.text(), folder=str(dock.domain_links.folder))
    aligned = t.domain.currentLayer()
    h.check("gap 4: the completed domain aligned, not the rough outline", aligned is not None and aligned.name().startswith("Domain aligned") and abs(report.get("outline_km2", 0.0) - completed_km2) < 0.05, (aligned.name() if aligned else None, report.get("outline_km2"), completed_km2))
    h.log(f"align report: {json.dumps({k: v for k, v in report.items() if k != 'leaving'})[:1200]}; leaving after it: {[(r['area_km2'], round(r['x']), round(r['y'])) for r in report.get('leaving', [])]}")
    w.render_map(h, "03_domain_aligned", [lay["outflow_lines"], w.find_layer("Subbasins, generated"), aligned], aligned)
    steps.begin("Generate basin on the aligned domain")
    box.generate_button.click()
    yield lambda: dock._basin_query is None and box.generate_button.isEnabled()
    steps.end("Generate basin on the aligned domain", box.summary.text(), subbasins=_count(box.model, "subbasin"), reservoirs=_count(box.model, "reservoir"))
    h.check("five reservoirs from the crest lines", _count(box.model, "reservoir") == 5, _count(box.model, "reservoir"))
    _dam_areas(h, box.model)
    w.big_shot(h, dock, "04_hydrology_basin", open_only="hydrology")
    w.render_map(h, "04_basin", [w.find_layer("Reaches, generated"), w.find_layer("Subbasins, generated"), t.domain.currentLayer()], t.domain.currentLayer())

    h.log("=== 4 the storm, the area reduction, the simulation, Run")
    w.type_storm(h, dock)
    w.set_reduction(h, dock, "curve", None)
    w.set_simulation(h, dock)
    job = w.job_of(dock)
    h.log(f"Lumped job hydrology: {json.dumps({k: v for k, v in job['hydrology'].items() if k != 'subbasins'})[:800]} | run {job['run']}")
    h.check("the job: Lumped, CN 88 beside the grid, reach n 0.1", job["run"].get("model_type") == "lumped" and job["hydrology"].get("curve_number") == 88.0 and job["hydrology"].get("reach_manning_n") == 0.1 and job["terrain"].get("cn_raster"), job["hydrology"].get("curve_number"))
    folder = yield from w.run_and_time(h, dock, steps, "Run Lumped", 0.5)
    done = h.events(folder, "done") if folder else []
    h.check("Lumped finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text()[:400])
    w.big_shot(h, dock, "06_run_lumped", open_only="run")
    w.save_scenario(h, dock, "Lumped")
    w.save_project(h)


def _report(dock) -> dict:
    path = Path(dock.domain_links.folder or "") / "domain_report.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _area(layer) -> float:
    return sum(f.geometry().area() for f in layer.getFeatures()) / 1e6 if layer is not None else 0.0


def _count(model, kind: str) -> int:
    return sum(1 for e in (model or {}).get("elements", []) if e.get("kind") == kind)


def _dam_areas(h, model: dict) -> None:
    w79 = {"Bidah 03": 20.97, "Faydh 01": 74.30, "R5A": 117.10, "R2A": 175.87, "Z4C": 211.09}
    for e in model.get("elements", []):
        if e.get("kind") == "reservoir":
            area = (e.get("parameters", {}).get("drainage_area_km2") or {}).get("value")
            base = next((v for k, v in w79.items() if e["name"].startswith(k)), None)
            h.log(f"reservoir {e['name']}: {area} km2 against Basin 3's {base}")
