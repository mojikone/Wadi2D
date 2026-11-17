"""W106 session 3 through the real dock: the Hybrid Lumped model on a generated basin (gap 3).

The project of session 2 opened; the Hybrid Lumped card, its own folder. Hydrology: a new Basin points layer and one
point, a junction at the HAT-S7 / HAT-S8 confluence named HAT-J4, the click saying which stream of the Lumped model's
basin it lies on (gap 6); the layer saved; Generate basin on the whole domain, each point said with its stream and
drainage area and drawn (gap 6); Last points: the five dams and HAT-J4 added; the lumped part of the area reduction as
the curve, the 2D part at 100 km2; Run. The card sets the generated basin's rule: the lumped model ends at the last
points, the catchments above them left out of the mesh, their routed outflow entering at the dams and HAT-J4.
"""

import json
import math
from pathlib import Path

HAT_J4_KM2 = 260.97


def helper(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w106_help", Path(h.SCENARIO).parent / "w106_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    return w


def scenario(h):
    w = helper(h)
    w.limits(h, 3.0)
    session = Path(h.P).name
    steps = w.Steps(h, session)
    w.read_project(h)
    dock = yield from h.open_dock(all_sections=False)
    yield lambda: dock.model.ready
    yield from hybrid(h, w, dock, steps, session, "hybrid_lumped", "last_points", "Hybrid Lumped")


def hybrid(h, w, dock, steps, session: str, kind: str, rule: str, title: str):
    from qgis.core import QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer
    from qgis.utils import iface

    h.log(f"restored: page {dock.types.page}, type {dock.types.kind}, folder {dock.panel.folder.filePath()}")
    lumped_basin = w.RUNS / w.MODELS["lumped"] / "wadi2d_basin"
    w.card(dock, kind)
    dock.panel.folder.setFilePath(str(w.RUNS / w.MODELS[kind]))
    hyd, box = dock.hydrology, dock.hydrology.basin
    hyd.setCollapsed(False)
    iface.mapCanvas().setExtent(dock.terrain.domain.currentLayer().extent())

    h.log("=== 1 a junction point at the HAT-S7 / HAT-S8 confluence, named HAT-J4")
    saved = w.INPUTS / "basin_points_hat_j4.gpkg"
    if not saved.is_file():
        hat = _hat_j4(h, lumped_basin, w.NUMBERS["clicks"]["HAT-J4"])
        box.new_points_button.click()
        points = box.pour.currentLayer()
        w.pick(box.point_kind, "junction")
        box.place_button.setChecked(True)
        dock.basin_points._clicked(QgsPointXY(*hat))  # the map tool's click there
        said = box.summary.text()
        h.check("gap 6: the click names the stream of the last generated basin and its drainage area", "of the last generated basin" in said and "km2" in said, said[-400:])
        names = points.fields().indexOf("name")
        points.dataProvider().changeAttributeValues({f.id(): {names: "HAT-J4"} for f in points.getFeatures()})
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        QgsVectorFileWriter.writeAsVectorFormatV3(points, str(saved), QgsProject.instance().transformContext(), options)
        QgsProject.instance().removeMapLayer(points.id())
    kept = w.find_layer("Basin points, HAT-J4")
    if kept is None:
        kept = QgsVectorLayer(str(saved), "Basin points, HAT-J4", "ogr")
        QgsProject.instance().addMapLayer(kept)
    box.pour.setLayer(kept)
    h.check("the HAT-J4 point layer saved and chosen", box.pour.currentLayer() is kept and kept.featureCount() == 1, kept.source())

    h.log("=== 2 Generate basin on the whole domain; where each point snapped")
    box.setChecked(True)
    steps.begin("Generate basin")
    box.generate_button.click()
    yield lambda: dock._basin_query is None and box.generate_button.isEnabled()
    summary = box.summary.text()
    steps.end("Generate basin", summary, subbasins=_count(box.model, "subbasin"), reservoirs=_count(box.model, "reservoir"))
    hat_area = next(((e["parameters"].get("drainage_area_km2") or {}).get("value") for e in box.model["elements"] if e["name"] == "HAT-J4"), None)
    h.check("gap 6: Generate basin says where HAT-J4 snapped and what drains there", "Basin points:" in summary and "HAT-J4 moved" in summary and w.find_layer("Basin points: where each snapped") is not None, (hat_area, summary[-500:]))
    h.check("HAT-J4 on the confluence of about Basin 3's 261 km2", hat_area is not None and abs(hat_area - HAT_J4_KM2) < 0.05 * HAT_J4_KM2, hat_area)
    h.check("five reservoirs", _count(box.model, "reservoir") == 5, _count(box.model, "reservoir"))

    h.log("=== 3 Last points: the five dams and HAT-J4")
    table = hyd.last_points
    if not any(r[0] == "HAT-J4" for r in table.rows()):
        _add_junction(h, table, "HAT-J4")
    rows = table.rows()
    h.log(f"last points: {rows}")
    h.check("the last points: five dams ticked and HAT-J4", sum(1 for r in rows if r[2]) == 6 and any(r[0] == "HAT-J4" for r in rows), rows)
    words = hyd.standing(kind).words
    h.check("Hydrology says how many subbasins the last points leave lumped", "lie above the last points and run lumped" in words, words[-300:])
    w.set_reduction(h, dock, "curve", w.NUMBERS["grid_area_km2"])
    w.set_simulation(h, dock)
    dock.panel.limiter.setChecked(True)
    job = w.job_of(dock)
    hy = job["hydrology"]
    h.log(f"{title} job: grid {job['grid']} | run {job['run']} | rule {hy.get('generated_entry')} | last points {hy.get('last_points')} | reach n {hy.get('reach_manning_n')} | cn {hy.get('curve_number')}")
    h.check(f"gap 3: the {title} card sets the generated basin's rule {rule!r}", hy.get("generated_entry") == rule and job["run"].get("model_type") == kind, hy.get("generated_entry"))
    w.big_shot(h, dock, f"{session}_hydrology", open_only="hydrology")
    w.save_project(h)

    folder = yield from w.run_and_time(h, dock, steps, f"Run {title}", 3.0)
    done = h.events(folder, "done") if folder else []
    finished = bool(done) and done[-1].get("code") == 0
    h.log(f"{title} outcome: finished {finished}; the dock says: {dock.panel.message.text()[:1500]}")
    if folder is not None:
        for line in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines():
            ev = json.loads(line)
            if ev.get("ev") in ("left_out", "warn") or (ev.get("ev") == "output" and ev.get("kind") in ("lumped_entry_areas", "pools")):
                h.log(f"run event: {json.dumps(ev)[:700]}")
    h.check(f"{title} finished", finished, dock.panel.message.text()[:300])
    w.big_shot(h, dock, f"{session}_run", open_only="run")
    if finished:
        dock.panel.results_button.click()
        yield lambda: True
        w.big_shot(h, dock, f"{session}_results")
        dock.types.show_model()
        w.save_scenario(h, dock, title)
    w.save_project(h)


def _add_junction(h, table, name: str) -> None:
    """The Last points table's Add a junction, the junction chosen by name."""
    combo = table.junction
    combo.setCurrentIndex(combo.findText(name))
    h.log(f"last points table: Add a junction at {combo.currentText()!r}")
    table.add_button.click()


def _hat_j4(h, folder: Path, icon):
    """The junction of the Lumped model's basin at the HAT-S7 / HAT-S8 confluence: within 3 km of his HMS icon, the
    drainage area nearest Basin 3's 260.97 km2 (W104's choice). A user clicks it on the map."""
    model = json.loads((folder / "basin.json").read_text(encoding="utf-8"))
    best = None
    for e in model["elements"]:
        if e["kind"] not in ("junction",):
            continue
        x, y = e["outlet"]
        far = math.hypot(x - icon[0], y - icon[1])
        area = (e["parameters"].get("drainage_area_km2") or {}).get("value")
        if far <= 3000.0 and area:
            score = abs(area - HAT_J4_KM2)
            if best is None or score < best[0]:
                best = (score, (x, y), area, far, e["name"])
    h.log(f"HAT-J4 click: {best}")
    return best[1] if best else tuple(icon)


def _count(model, kind):
    return sum(1 for e in (model or {}).get("elements", []) if e.get("kind") == kind)
