"""W104 session 4 through the real dock: the Hybrid 2D model, as near his definition as the dock's fields reach.

His Hybrid 2D: the catchments above the five dams and HAT-J4 lumped, each subbasin's water entering the grid at its
own outlet and routed in 2D, the dams as 2D pools. On a generated basin the dock's Hybrid 2D card changes nothing of the
routing: the lumped water follows the generated reaches and the dams' lumped reservoirs and enters at the outfalls,
as in Hybrid Lumped (said in the README; checked here on the job the card writes, not run). The nearest the dock's own
fields reach: the basin generated with no crest lines in Structures (so it holds no reservoirs) and Reach routing
"Muskingum" with no K and X typed (so every generated reach is left out and its water runs on the 2D grid from the
junction above it); the crest lines and spillways picked again for the run, so the dams are 2D pools. The project of
session 3; the Hybrid 2D card; its own output folder; saved as the scenario Hybrid 2D.
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

    w.read_project(h)
    dock = yield from h.open_dock(all_sections=False)
    yield lambda: dock.model.ready
    h.log(f"restored: page {dock.types.page}, type {dock.types.kind}, folder {dock.panel.folder.filePath()}")
    hyd, box, s = dock.hydrology, dock.hydrology.basin, dock.structures
    w.card(dock, "hybrid_2d")
    iface.mapCanvas().setExtent(dock.terrain.domain.currentLayer().extent())

    h.log("=== 1 the card alone, on Hybrid Lumped's basin: what the job does")
    if w.problems_now(dock):  # the second try: the first try's basin was set aside; its card-alone job is in logs/
        h.log(f"the card alone is not checked again: {w.problems_now(dock)}")
    else:
        plain = w.job_of(dock)
        h.log(f"Hybrid 2D card on the outfall basin: grid {plain['grid']} | lumped_entry {plain['hydrology'].get('lumped_entry')} | reach_routing {plain['hydrology'].get('reach_routing')} | basin {plain['hydrology'].get('basin_json')}")
        (w.LOGS / f"{session}_card_alone_job.json").write_text(json.dumps(plain, indent=1), encoding="utf-8")

    h.log("=== 2 the basin again, with no crest lines, into this model's folder")
    dock.panel.folder.setFilePath(str(w.RUNS / w.MODELS["hybrid_2d"]))
    # Basin points: an outfall 150 m above each dam on every stream of 5 km2 or more that crosses its crest line, so
    # each branch's water enters the grid inside the pool (the first try put the outfalls 200 m below the dams, as
    # Hybrid Lumped: with no crest line in the generation nothing collects a dam's branches, and the branches that
    # join below the outfall drained to none and were left to rain on the grid), and HAT-J4's outfall of Hybrid Lumped
    from qgis.core import QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer

    for old in w.layers_by_title("Basin points, outfalls and junctions"):
        QgsProject.instance().removeMapLayer(old.id())
    hybrid = QgsVectorLayer(str(w.INPUTS / "basin_points_hybrid.gpkg"), "hybrid", "ogr")
    clicks = [(f["name"], "outfall", f.geometry().asPoint()) for f in hybrid.getFeatures() if f["name"] == "HAT-J4"]
    clicks += [(name, "outfall", QgsPointXY(*xy)) for name, xy in _above_dams(h, w.RUNS / w.MODELS["lumped"] / "wadi2d_basin")]
    box.new_points_button.click()
    points = box.pour.currentLayer()
    for _name, kind, point in clicks:
        w.pick(box.point_kind, kind)
        box.place_button.setChecked(True)
        dock.basin_points._clicked(QgsPointXY(point))
    names = points.fields().indexOf("name")
    points.dataProvider().changeAttributeValues({f.id(): {names: clicks[n][0]} for n, f in enumerate(points.getFeatures())})
    saved = w.INPUTS / "basin_points_hybrid2d_outfalls.gpkg"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    QgsVectorFileWriter.writeAsVectorFormatV3(points, str(saved), QgsProject.instance().transformContext(), options)
    kept = QgsVectorLayer(str(saved), "Basin points, outfalls above the dams", "ogr")
    QgsProject.instance().addMapLayer(kept)
    box.pour.setLayer(kept)
    QgsProject.instance().removeMapLayer(points.id())
    h.check("outfalls above the dams and at HAT-J4", kept.featureCount() == len(clicks) and len(clicks) > 6, [(c[0], c[1]) for c in clicks])
    crest, spill = s.layers["crest_line"].currentLayer(), s.layers["spillway"].currentLayer()
    s.layers["crest_line"].setLayer(None)
    s.layers["spillway"].setLayer(None)
    steps.begin("Generate basin without the dams")
    box.generate_button.click()
    yield lambda: dock._basin_query is None and box.generate_button.isEnabled()
    steps.end("Generate basin without the dams", box.summary.text(), subbasins=_count(box.model, "subbasin"), reservoirs=_count(box.model, "reservoir"))
    h.check("no reservoir in this basin", _count(box.model, "reservoir") == 0, box.summary.text()[:300])
    dam_areas = {"Bidah 03": 20.03, "Faydh 01": 74.42, "R5A": 117.12, "R2A": 175.94, "Z4C": 211.56, "HAT-J4": 260.36}
    lumped = {d: 0.0 for d in dam_areas}
    for e in box.model["elements"]:
        hit = next((d for d in dam_areas if e["name"] == d or e["name"].startswith(f"{d} above")), None)
        if hit and e.get("downstream") is None:
            lumped[hit] += (e["parameters"].get("drainage_area_km2") or {}).get("value") or 0.0
    h.log(f"lumped area above each dam (outfalls) against the dam's: {[(d, round(a, 2), dam_areas[d]) for d, a in lumped.items()]}")
    short = [d for d, a in lumped.items() if a < 0.9 * dam_areas[d]]
    if short:
        h.check("the outfalls carry at least 90 % of each dam's area: no run", False, short)
        return
    s.layers["crest_line"].setLayer(crest)
    s.fields["crest_line"]["crest_z"].setField("z")
    s.layers["spillway"].setLayer(spill)
    s.fields["spillway"]["crest_z"].setField("z")
    s.fields["spillway"]["coefficient"].setField("c")
    s.fields["spillway"]["length"].setField("length")
    h.check("the dams back in Structures for the 2D pools", s.layers["crest_line"].currentLayer() is crest and s.layers["spillway"].currentLayer() is spill)

    h.log("=== 3 Reach routing Muskingum with no K and X: every reach left out")
    w.pick(hyd.routing, "muskingum")
    h.log(f"Muskingum table: {len(hyd.muskingum.rows)} reaches, values {hyd.muskingum.values()}")
    w.big_shot(h, dock, f"{session}_hydrology", open_only="hydrology")
    w.set_reduction(h, dock, "curve", w.NUMBERS["grid_area_km2"])
    w.set_simulation(h, dock)
    dock.panel.limiter.setChecked(True)
    job = w.job_of(dock)
    (w.LOGS / f"{session}_job.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    h.log(f"Hybrid 2D job: grid {job['grid']} | routing {job['hydrology'].get('reach_routing')} muskingum {job['hydrology'].get('muskingum')} | storm {json.dumps(job.get('storm'))[:400]}")
    statuses = dock.status_links.refresh()
    h.log("status: " + "; ".join(f"{k}: {v.state} {v.words[:120]}" for k, v in statuses.items()))
    w.save_project(h)

    folder = yield from w.run_and_time(h, dock, steps, "Run Hybrid 2D", 3.5)
    done = h.events(folder, "done") if folder else []
    finished = bool(done) and done[-1].get("code") == 0
    h.log(f"Hybrid 2D outcome: finished {finished}; the dock says: {dock.panel.message.text()[:1500]}")
    w.big_shot(h, dock, f"{session}_run", open_only="run")
    w.big_shot(h, dock, f"{session}_junctions", open_only="hydrology")
    if finished:
        dock.panel.results_button.click()
        yield lambda: True
        w.big_shot(h, dock, f"{session}_results")
        dock.types.show_model()
        w.save_scenario(h, dock, "Hybrid 2D")
    w.save_project(h)


ABOVE_M = 150.0
DAMS = ("Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C")


LEAST_KM2 = 5.0
"""Streams of Suggest's thalwegs layer draining at least this much get a junction where they cross a dam."""


def _above_dams(h, folder: Path) -> list:
    """A point this far up every stream that crosses a dam's main crest line (Suggest's thalwegs, on the map), on the
    upper side by the DEM: the user's click. A dam on two wadi branches (R5A, R2A) gets one on each, so no branch's
    water enters below the dam."""
    from qgis.core import QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

    thalwegs = QgsVectorLayer(f"{folder.parents[1] / '2D_breaklines' / 'suggested_breaklines.gpkg'}|layername=thalwegs", "t", "ogr")
    crests = QgsVectorLayer(str(Path(h.SCENARIO).parent / "inputs" / "crest_lines.gpkg"), "c", "ogr")
    dem = next(layer for layer in QgsProject.instance().mapLayers().values() if layer.name().startswith("GGC_2_MERGE_HDSM"))
    out, held = [], []
    for crest in crests.getFeatures():
        if crest["name"] not in DAMS:
            continue
        line = crest.geometry()
        number = 0
        for t in thalwegs.getFeatures(line.boundingBox()):
            if (t["area_km2"] or 0.0) < LEAST_KM2 or not t.geometry().intersects(line):
                continue
            stream = t.geometry()
            for part in stream.intersection(line).asGeometryCollection() or [stream.intersection(line)]:
                cross = part.asPoint() if part.type() == 0 else part.centroid().asPoint()
                at = stream.lineLocatePoint(QgsGeometry.fromPointXY(cross))
                ends = [stream.interpolate(min(max(at + s, 0.0), stream.length())).asPoint() for s in (-ABOVE_M, ABOVE_M)]
                z = [dem.dataProvider().sample(QgsPointXY(p), 1)[0] for p in ends]
                up = ends[0] if z[0] >= z[1] else ends[1]
                if any(up.distance(p) < 100.0 for p in held):
                    continue
                held.append(up)
                number += 1
                out.append((f"{crest['name']} above {number}", (up.x(), up.y())))
        h.log(f"{crest['name']}: {number} junctions {ABOVE_M:g} m above the dam")
    return out


def _count(model, kind):
    return sum(1 for e in (model or {}).get("elements", []) if e.get("kind") == kind)
