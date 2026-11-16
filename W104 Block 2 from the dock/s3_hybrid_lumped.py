"""W104 session 3 through the real dock: the Hybrid Lumped model.

The project of session 2 opened; the Hybrid Lumped card; its own output folder. Hydrology: a new Basin points layer, an
outfall clicked 200 m below each of the five dams (W79's entry points) and one at the HAT-S7 / HAT-S8 confluence (the
junction of the Lumped model's generated basin draining about Basin 3's 261 km2 there, beside his HMS icon of HAT-J4),
the points named and the layer saved; Generate basin, which keeps only what drains to an outfall; the lumped part of
the area reduction as the curve (each lumped subbasin at the area of the element where it enters the grid), the 2D part
at 100 km2; Run. Saved as the scenario Hybrid Lumped; the project saved.
"""

import json
import math
from pathlib import Path

DAMS = ("Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C")
HAT_J4_KM2 = 260.97


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w104_help", Path(h.SCENARIO).parent / "w104_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    w.limits(h, 3.0)
    session = Path(h.P).name
    steps = w.Steps(h, session)
    from qgis.core import QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer
    from qgis.utils import iface

    w.read_project(h)
    dock = yield from h.open_dock(all_sections=False)
    yield lambda: dock.model.ready
    h.log(f"restored: page {dock.types.page}, type {dock.types.kind}, folder {dock.panel.folder.filePath()}")
    lumped_basin = w.RUNS / w.MODELS["lumped"] / "wadi2d_basin"
    junctions_a = next(
        (l for l in w.layers_by_title("Junctions, generated") if str(lumped_basin) in l.source()), None
    )  # the Lumped model's generated basin, on the map
    for old in w.layers_by_title("Basin points, outfalls"):  # the first try of this session (its R2A click was off the stream)
        QgsProject.instance().removeMapLayer(old.id())
    w.card(dock, "hybrid_lumped")
    dock.panel.folder.setFilePath(str(w.RUNS / w.MODELS["hybrid_lumped"]))
    hyd, box = dock.hydrology, dock.hydrology.basin
    hyd.setCollapsed(False)
    iface.mapCanvas().setExtent(dock.terrain.domain.currentLayer().extent())

    h.log("=== 1 the Basin points: an outfall below each dam and at HAT-J4")
    hat = _hat_j4(h, junctions_a, w.NUMBERS["clicks"]["HAT-J4"])
    below = _below_dams(h, lumped_basin)
    box.new_points_button.click()
    points = box.pour.currentLayer()
    clicks = [(f"{dam} outfall", below.get(dam) or w.NUMBERS["clicks"][f"{dam} outfall"]) for dam in DAMS] + [("HAT-J4", hat)]
    h.log(f"clicks: {clicks}")
    for _name, (x, y) in clicks:
        w.pick(box.point_kind, "outfall")
        box.place_button.setChecked(True)  # Click on the map
        dock.basin_points._clicked(QgsPointXY(x, y))  # the map tool's click at that place
    h.check("six outfalls on the Basin points layer", points.featureCount() == 6, points.featureCount())
    names = points.fields().indexOf("name")
    renames = {f.id(): clicks[n][0] for n, f in enumerate(points.getFeatures())}
    points.dataProvider().changeAttributeValues({fid: {names: name} for fid, name in renames.items()})
    saved = w.INPUTS / "basin_points_hybrid.gpkg"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    QgsVectorFileWriter.writeAsVectorFormatV3(points, str(saved), QgsProject.instance().transformContext(), options)
    kept = QgsVectorLayer(str(saved), "Basin points, outfalls", "ogr")
    QgsProject.instance().addMapLayer(kept)
    box.pour.setLayer(kept)
    QgsProject.instance().removeMapLayer(points.id())
    h.check("the layer saved and chosen", box.pour.currentLayer() is kept and kept.featureCount() == 6, kept.source())

    h.log("=== 2 Generate basin: what drains to an outfall")
    steps.begin("Generate basin to the outfalls")
    box.generate_button.click()
    yield lambda: dock._basin_query is None and box.generate_button.isEnabled()
    steps.end("Generate basin to the outfalls", box.summary.text(), subbasins=_count(box.model, "subbasin"), reservoirs=_count(box.model, "reservoir"))
    areas = _areas(box.model, [name for name, _xy in clicks])
    h.log(f"outfall and reservoir drainage areas: {areas}")
    outfalls = [name for name, _xy in clicks if name in areas]
    h.check("five reservoirs and six outfalls", _count(box.model, "reservoir") == 5 and len(outfalls) == 6, (areas, _count(box.model, "reservoir")))
    off = [n for n in outfalls if n != "HAT-J4" and (areas.get(n) or 0.0) < 0.98 * (areas.get(n[: -len(" outfall")]) or 1e9)]
    if off or len(outfalls) < 6 or _count(box.model, "reservoir") != 5:
        h.check("every outfall on its dam's stream: no run", False, off)
        return
    w.big_shot(h, dock, f"{session}_hydrology_outfalls", open_only="hydrology")
    model_layers = w.layers_by_title("Subbasins, generated")
    w.render_map(h, f"{session}_basin", [kept, w.layers_by_title("Reaches, generated")[-1], model_layers[-1], dock.terrain.domain.currentLayer()], dock.terrain.domain.currentLayer())
    h.log("junction rows: " + " | ".join(" / ".join(str(r.get(k)) for k in ("junction", "route", "next_junction")) for r in box.rows[:200] if r["junction"] in areas or "outfall" in r["junction"].lower()))

    h.log("=== 3 area reduction and run")
    w.set_reduction(h, dock, "curve", w.NUMBERS["grid_area_km2"])
    w.big_shot(h, dock, f"{session}_reduction", open_only="reduction")
    w.set_simulation(h, dock)
    dock.panel.limiter.setChecked(True)
    job = w.job_of(dock)
    h.log(f"Hybrid Lumped job: storm {json.dumps(job.get('storm'))[:700]} | grid {job['grid']} | run {job['run']} | basin {job['hydrology'].get('basin_json')} | subbasins {len(job['hydrology'].get('subbasins', []))} lumped {sum(1 for s in job['hydrology'].get('subbasins', []) if s['mode'] == 'lumped')}")
    h.check("the catchments left out of the mesh", job["grid"].get("exclude_lumped") is True, job["grid"])
    statuses = dock.status_links.refresh()
    h.log("status: " + "; ".join(f"{k}: {v.state} {v.words[:120]}" for k, v in statuses.items()))
    w.save_project(h)
    folder = yield from w.run_and_time(h, dock, steps, "Run Hybrid Lumped", 3.0)
    done = h.events(folder, "done") if folder else []
    finished = bool(done) and done[-1].get("code") == 0
    h.log(f"Hybrid Lumped outcome: finished {finished}; the dock says: {dock.panel.message.text()[:1500]}")
    w.big_shot(h, dock, f"{session}_run", open_only="run")
    w.big_shot(h, dock, f"{session}_junctions", open_only="hydrology")
    if finished:
        dock.panel.results_button.click()
        yield lambda: True
        w.big_shot(h, dock, f"{session}_results")
        dock.types.show_model()
        w.save_scenario(h, dock, "Hybrid Lumped")
    w.save_project(h)


def _hat_j4(h, layer, icon):
    """The junction of the Lumped model's basin at the HAT-S7 / HAT-S8 confluence: within 3 km of his HMS icon, the
    drainage area nearest Basin 3's 260.97 km2. A user clicks it on the map."""
    best = None
    for f in layer.getFeatures() if layer is not None else []:
        p = f.geometry().asPoint()
        far = math.hypot(p.x() - icon[0], p.y() - icon[1])
        area = f["drainage_area_km2"]
        if far <= 3000.0 and area:
            score = abs(area - HAT_J4_KM2)
            if best is None or score < best[0]:
                best = (score, (p.x(), p.y()), area, far, f["name"])
    h.log(f"HAT-J4 click: {best}")
    return best[1] if best else tuple(icon)


BELOW_M = 200.0
"""An outfall this far down the generated reach below each dam: a click on the reach the Lumped model's basin drew.
W79's own entry points lie off the D8 stream at R2A (the first try snapped to a 0.08 km2 rill there)."""


def _below_dams(h, folder: Path) -> dict:
    from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer

    model = json.loads((folder / "basin.json").read_text(encoding="utf-8"))
    els = {e["name"]: e for e in model["elements"]}
    reaches = QgsVectorLayer(f"{folder / 'basin.gpkg'}|layername=reaches", "reaches", "ogr")
    shapes = {f["name"]: f.geometry() for f in reaches.getFeatures()}
    out = {}
    for dam in DAMS:
        reach = els.get(dam, {}).get("downstream")
        if reach not in shapes or els[reach]["kind"] != "reach":
            h.log(f"{dam}: no generated reach below it ({reach}); W79's point is clicked")
            continue
        line = shapes[reach]
        start = QgsGeometry.fromPointXY(QgsPointXY(*els[dam]["outlet"]))
        at = line.lineLocatePoint(start)
        p = line.interpolate(min(at + BELOW_M, line.length())).asPoint()
        out[dam] = (p.x(), p.y())
        h.log(f"{dam}: {BELOW_M:g} m down reach {reach} ({line.length():.0f} m) at {out[dam]}")
    return out


def _count(model, kind):
    return sum(1 for e in (model or {}).get("elements", []) if e.get("kind") == kind)


def _areas(model, names):
    out = {}
    for e in (model or {}).get("elements", []):
        names_here = [e["name"], *e.get("aliases", [])] if isinstance(e.get("aliases"), list) else [e["name"]]
        if any(n in names for n in names_here) or e.get("kind") == "reservoir":
            out[e["name"]] = (e.get("parameters", {}).get("drainage_area_km2") or {}).get("value")
    return out
