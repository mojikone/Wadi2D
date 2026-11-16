"""W104 session 1 through the real dock: Block 2 from the ground up, and the Lumped model run.

His raw layers only (DEM, CN and Manning rasters, and what he drew: a rough outline, the outflow lines, the dams'
crest lines and spillways, the dam lines). In the dock, as a user: the start page; Terrain, Boundaries, Structures and
Results points; the domain completed upstream from the rough outline; the basin generated from the DEM with a stream
threshold searched for about the HMS model's 104 subbasins; the domain aligned to the generated subbasins and the
basin generated again on it; the storm typed into Data tables and Storm; the area reduction; the Lumped model run,
saved as a scenario; the project saved for session 2.
"""

import json
from pathlib import Path

TARGET_SUBBASINS = 104
FIRST_THRESHOLD_KM2 = 7.5
"""The first attempt of this session searched from 10 km2 (78 subbasins) to 7.5 km2 (108): logs/s1_first_steps.json."""
TRIES = 4
CN_FILL = 88.0
"""W79's CN where his grid has none (W1's value): put into the grid's holes with QGIS's own Fill NoData cells, because
the dock has no value beside a CN grid and a generated subbasin the grid covers less than 90 % gets no CN at all."""


def filled_cn(h, w, lay):
    """His CN grid clipped round the rough outline and its holes filled with 88, by QGIS's Processing tools, as a
    designer prepares a raster before the model; the dock is not involved."""
    import processing
    from qgis.core import QgsProject, QgsRasterLayer

    out = w.RUNS / "inputs"
    out.mkdir(parents=True, exist_ok=True)
    e = lay["rough_outline"].extent()
    margin = 6000.0
    window = f"{e.xMinimum() - margin},{e.xMaximum() + margin},{e.yMinimum() - margin},{e.yMaximum() + margin} [EPSG:32640]"
    clipped = processing.run("gdal:cliprasterbyextent", {"INPUT": lay["cn"].source(), "PROJWIN": window, "OUTPUT": str(out / "cn_clipped.tif")})
    filled = processing.run("native:fillnodata", {"INPUT": clipped["OUTPUT"], "BAND": 1, "FILL_VALUE": CN_FILL, "OUTPUT": str(out / "cn_filled_88.tif")})
    layer = QgsRasterLayer(filled["OUTPUT"], "CN_Include_Hill_Area, holes filled with 88")
    QgsProject.instance().addMapLayer(layer)
    h.check("the CN grid's holes filled in QGIS", layer.isValid(), filled["OUTPUT"])
    return layer


def scenario(h):
    w = h_helper(h)
    w.limits(h, 3.0)
    steps = w.Steps(h, "s1")
    w.RUNS.mkdir(exist_ok=True)
    from qgis.utils import iface

    lay = w.load_inputs(h)
    steps.begin("CN grid holes filled in QGIS")
    lay["cn_filled"] = filled_cn(h, w, lay)
    steps.end("CN grid holes filled in QGIS", lay["cn_filled"].source())
    iface.mapCanvas().setDestinationCrs(lay["crs"])
    iface.mapCanvas().setExtent(lay["rough_outline"].extent())
    steps.begin("open the dock")
    dock = yield from h.open_dock(all_sections=False)
    steps.end("open the dock", dock.engine_label.text())
    h.check("the start page first", dock.types.page == "start")
    w.big_shot(h, dock, "01_start_page")

    h.log("=== 1 a 2D card first: Terrain, Boundaries, Structures and the domain from the rough outline")
    w.card(dock, "2d")
    dock.panel.folder.setFilePath(str(w.RUNS / w.MODELS["lumped"]))
    w.set_terrain(h, dock, lay)
    w.set_boundaries(h, dock, lay)
    w.set_structures(h, dock, lay)
    t = dock.terrain
    t.outline.setLayer(lay["rough_outline"])
    h.check("the outline box shows for a 2D model", t.outline_box.isVisibleTo(t))
    steps.begin("Complete upstream")
    t.complete_button.click()
    yield lambda: dock.domain_links.query is None and t.complete_button.isEnabled()
    steps.end("Complete upstream", t.outline_words.text(), folder=str(dock.domain_links.folder))
    completed = t.domain.currentLayer()
    h.check("the completed domain chosen as Terrain's domain", completed is not None and completed.name().startswith("Domain completed upstream"), completed.name() if completed else None)
    report = _report(dock)
    h.log(f"completion report: {json.dumps(report)[:1500]}")
    w.big_shot(h, dock, "02_terrain_completed", open_only="terrain")
    w.render_map(h, "02_domain_completed", [lay["outflow_lines"], lay["rough_outline"], completed], completed)

    h.log("=== 2 the Lumped card: the basin from the DEM, a stream threshold for about 104 subbasins")
    w.card(dock, "lumped")
    hyd = dock.hydrology
    hyd.setCollapsed(False)
    h.check("Lumped hides Terrain's outline box", not t.outline_box.isVisibleTo(t))
    hyd.cn.raster.setLayer(lay["cn"])  # his CN grid as it is: the box beside it closes (the dock's rule)
    h.check("the dock offers no CN beside a CN grid", not hyd.cn.box.isEnabled())
    hyd.cn.raster.setLayer(lay["cn_filled"])  # the generated subbasins and the rain-on-grid cells take their CN from it
    h.log(f"curve number: raster {hyd.cn.raster.currentLayer().name()}, the value box enabled: {hyd.cn.box.isEnabled()}")
    box = hyd.basin
    box.setChecked(True)
    threshold, tried = FIRST_THRESHOLD_KM2, []
    for attempt in range(TRIES):
        box.threshold.setValue(threshold)
        label = f"Generate basin, {threshold:g} km2"
        steps.begin(label)
        box.generate_button.click()
        yield lambda: dock._basin_query is None and box.generate_button.isEnabled()
        count = _count(box.model, "subbasin") if box.model else 0
        steps.end(label, box.summary.text(), subbasins=count, threshold_km2=threshold)
        tried.append((threshold, count))
        if not count or abs(count - TARGET_SUBBASINS) <= 0.1 * TARGET_SUBBASINS:
            break
        threshold = max(round(threshold * count / TARGET_SUBBASINS * 2.0) / 2.0, 0.5)
    h.log(f"thresholds tried: {tried}")
    h.check("a basin of about 104 subbasins", tried and abs(tried[-1][1] - TARGET_SUBBASINS) <= 0.15 * TARGET_SUBBASINS, tried)
    w.big_shot(h, dock, "03_hydrology_first_basin", open_only="hydrology")

    h.log("=== 3 back to 2D: the domain aligned to the generated subbasins; the basin again on it")
    w.card(dock, "2d")
    subbasins = w.find_layer("Subbasins, generated")
    t.outline_catchments.setLayer(subbasins)
    # Align works on the Rough outline picker, not on Terrain's domain: the first attempt aligned the rough outline
    # itself (1,416.5 km2) and lost the completion. The completed domain, loaded again from its file, is the outline.
    from qgis.core import QgsProject, QgsVectorLayer

    copy = QgsVectorLayer(f"{Path(dock.domain_links.folder) / 'domain.gpkg'}|layername=domain", "Completed domain, the outline to align", "ogr")
    QgsProject.instance().addMapLayer(copy)
    t.outline.setLayer(copy)
    basin_job = json.loads((Path(dock.panel.folder.filePath()) / "wadi2d_basin" / "job.json").read_text(encoding="utf-8"))
    h.check("Generate basin reads the runs' own DEM store (the W104 fix)", Path(basin_job["grid"]["cache_dir"]) == (w.RUNS / "wadi2d_cache").resolve() and not (Path(dock.panel.folder.filePath()) / "wadi2d_cache").exists(), basin_job["grid"]["cache_dir"])
    steps.begin("Align to catchments")
    t.align_button.click()
    yield lambda: dock.domain_links.query is None and t.align_button.isEnabled()
    steps.end("Align to catchments", t.outline_words.text(), folder=str(dock.domain_links.folder))
    aligned = t.domain.currentLayer()
    h.check("the aligned domain chosen", aligned is not None and aligned.name().startswith("Domain aligned"), aligned.name() if aligned else None)
    h.log(f"alignment report: {json.dumps(_report(dock))[:1500]}")
    w.render_map(h, "03_domain_aligned", [lay["outflow_lines"], subbasins, aligned], aligned)
    w.card(dock, "lumped")
    label = f"Generate basin on the aligned domain, {box.threshold.value():g} km2"
    steps.begin(label)
    box.generate_button.click()
    yield lambda: dock._basin_query is None and box.generate_button.isEnabled()
    steps.end(label, box.summary.text(), subbasins=_count(box.model, "subbasin"), reservoirs=_count(box.model, "reservoir"))
    h.check("five reservoirs from the crest lines", _count(box.model, "reservoir") == 5, _count(box.model, "reservoir"))
    _dam_areas(h, box.model)
    w.big_shot(h, dock, "04_hydrology_basin", open_only="hydrology")
    w.render_map(h, "04_basin", [w.find_layer("Reaches, generated"), w.find_layer("Subbasins, generated"), dock.terrain.domain.currentLayer()], dock.terrain.domain.currentLayer())

    h.log("=== 4 the storm, the area reduction, the simulation")
    w.type_storm(h, dock)
    w.big_shot(h, dock, "05_tables", open_only="tables")
    w.big_shot(h, dock, "05_storm", open_only="storm")
    w.set_reduction(h, dock, "curve", None)
    w.big_shot(h, dock, "05_reduction_lumped", open_only="reduction")
    w.set_simulation(h, dock)
    job = w.job_of(dock)
    h.log(f"Lumped job: storm {json.dumps(job.get('storm'))[:600]} | hydrology {json.dumps({k: v for k, v in job['hydrology'].items() if k != 'subbasins'})[:600]} | run {job['run']}")
    h.check("the job is a Lumped model on the generated basin", job["run"].get("model_type") == "lumped" and job["run"].get("lumped_only") and job["hydrology"].get("basin_json"), job["run"])
    statuses = dock.status_links.refresh()
    h.log("status: " + "; ".join(f"{k}: {v.state} {v.words[:120]}" for k, v in statuses.items()))

    h.log("=== 5 Run the Lumped model")
    folder = yield from w.run_and_time(h, dock, steps, "Run Lumped", 0.5)
    done = h.events(folder, "done") if folder else []
    h.check("Lumped finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text()[:400])
    w.big_shot(h, dock, "06_run_lumped", open_only="run")
    if dock.panel.results_button.isEnabled():
        dock.panel.results_button.click()
        yield lambda: True
        w.big_shot(h, dock, "07_results_lumped")
        dock.types.show_model()
    w.save_scenario(h, dock, "Lumped")
    w.save_project(h)


def h_helper(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w104_help", Path(h.SCENARIO).parent / "w104_help.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(dock) -> dict:
    folder = Path(dock.domain_links.folder or "")
    path = folder / "domain_report.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _count(model: dict | None, kind: str) -> int:
    return sum(1 for e in (model or {}).get("elements", []) if e.get("kind") == kind)


def _dam_areas(h, model: dict) -> None:
    """Each reservoir's drainage area against W79's (Basin 3)."""
    w79 = {"Bidah 03": 20.97, "Faydh 01": 74.30, "R5A": 117.10, "R2A": 175.87, "Z4C": 211.09}
    for e in model.get("elements", []):
        if e.get("kind") == "reservoir":
            area = (e.get("parameters", {}).get("drainage_area_km2") or {}).get("value")
            base = next((v for k, v in w79.items() if e["name"].startswith(k)), None)
            h.log(f"reservoir {e['name']}: {area} km2 against Basin 3's {base}")
