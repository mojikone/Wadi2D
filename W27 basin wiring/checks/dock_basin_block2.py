"""Block 2 through the real dock: the basin generated from the DEM with the five axes, run lumped by default under the
HMS 100-yr storm, with the NRCS lag and with the HMS-style lag; then the same storm on the HMS project itself. The
five dam peaks are read from the lumped network's series of each run and written to a JSON beside the log.

The HMS route here is what the dock has always done: every HMS subbasin lumped, its hydrograph entering the grid at
its outlet; the network series of that run are the HMS replication, unaffected by the grid.
"""

import csv
import json

from qgis.PyQt.QtCore import QPointF

DX = 40.0
GEN_HOURS = 30.0
"""Every HMS dam peak falls before hour 16; the generated run stops at 30 h, the HMS route takes the control file's 48."""
THRESHOLD_KM2 = 10.0
DAMS = ("Faydh 01", "Bidah 03", "R5A", "R2A", "Z4C")


def done_event(h, folder):
    found = h.events(folder, "done")
    return found[-1] if found else {}


def network_peak(folder, name, column="inflow_m3s"):
    path = folder / "series" / f"network_{name.replace(' ', '_')}.csv"
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    t, q = head.index("t_s"), head.index(column)
    best = max(body, key=lambda r: float(r[q]))
    return {"peak_m3s": round(float(best[q]), 1), "at_h": round(float(best[t]) / 3600.0, 2)}


def fill_storm(dock, storm):
    """The HMS 100-yr storm on the dock's design page: depth, duration, pattern, area, the ARF table."""
    from wadi2d_qgis.storm_rows import KIND_DESIGN  # the harness puts the plugin on the path when the dock opens

    s = dock.storm
    s.kind.setCurrentIndex(s.kind.findData(KIND_DESIGN))
    s.design_depth.setValue(storm["depth_mm"])
    s.design_hours.setValue(storm["duration_min"] / 60.0)
    s.pattern.set_rows(list(zip(storm["time_percent"], storm["depth_percent"])))
    s.storm_area.setValue(storm["storm_area_km2"])
    s.arf.set_rows(list(zip(storm["arf"]["areas_km2"], storm["arf"]["factors"])))


def scenario(h):
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    axes = json.loads((h.REPO / "W24 basin model" / "jobs" / "block2.json").read_text(encoding="utf-8"))["terrain"]["objects"]
    dem = h.add_raster(h.BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif", "terrain")
    crs = dem.crs()
    from qgis.core import QgsProject

    QgsProject.instance().setCrs(crs)
    block = h.add_vector(h.VALIDATION / "domain.geojson", "domain block 2", crs)
    crests = h.add_vector(
        h.geojson("axes", [h.line(o["coordinates"], z=o["z_constant"], name=o["name"]) for o in axes]), "dam axes", crs
    )
    outs = h.add_vector(
        h.geojson("outs", [h.line(k["coordinates"], kind="normal", value=0.01) for k in jobs["boundaries"]]), "outlets", crs
    )
    lines = h.add_vector(
        h.geojson("dams", [h.line(k["coordinates"], name=k["name"]) for k in jobs["outputs"]["lines"] if k["name"] in DAMS]),
        "dam lines", crs,
    )  # fmt: skip
    cn = h.add_raster(h.BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn")
    dock = yield from h.open_dock()
    t, hy, box, s = dock.terrain, dock.hydrology, dock.hydrology.basin, dock.structures

    t.dem.setLayer(dem)
    t.dx.setValue(DX)
    t.domain.setLayer(block)
    t.manning.box.setValue(0.1)  # HMS's own reach n, used unchanged as W24 did; also the 2D n, which carries little here
    hy.folder.setFilePath("")
    hy.cn.raster.setLayer(cn)
    s.layers["crest_line"].setLayer(crests)
    s.fields["crest_line"]["crest_z"].setField("z")
    dock.boundaries.layer.setLayer(outs)
    dock.points.layer.setLayer(lines)
    dock.points.name.setField("name")
    dock.panel.duration.setValue(GEN_HOURS)
    dock.panel.pixels.setChecked(False)
    storm = jobs["storm"]
    fill_storm(dock, storm)
    peaks = {}

    for lag in ("nrcs", "hms_kirpich"):
        h.log(f"=== generated basin, lag {lag}")
        folder = h.RUNS / f"block2_gen_{lag}"
        dock.panel.folder.setFilePath(str(folder))
        box.setChecked(True)
        box.threshold.setValue(THRESHOLD_KM2)
        box.lag.setCurrentIndex(box.lag.findData(lag))
        box.generate_button.click()
        yield lambda: box.generate_button.isEnabled()
        h.log(f"summary: {box.summary.text()}")
        model = box.model
        h.check(f"{lag}: a basin was generated", model is not None, box.summary.text()[:200])
        kinds = [e["kind"] for e in model["elements"]]
        h.check(f"{lag}: 41 subbasins and 18 reaches at 10 km2 as W24 had", kinds.count("subbasin") == 41 and kinds.count("reach") == 18, (kinds.count("subbasin"), kinds.count("reach")))
        h.check(f"{lag}: the five axes are reservoirs", {e["name"] for e in model["elements"] if e["kind"] == "reservoir"} == set(DAMS))
        h.check(f"{lag}: basin.json says which lag made it", model["settings"]["lag_method"] == lag, model["settings"].get("lag_method"))
        if lag == "nrcs":
            group = h.group_of("Wadi2D basin")
            layers = [n.layer() for n in group.findLayers()] if group else []
            extent = block.extent()
            h.render("basin_block2", [*layers, dem], QPointF(extent.center().x(), extent.center().y()), 250000, size=(1200, 1400))
            h.widget_shot("hydrology_block2", hy)
        yield from h.run(dock, limit=1500)
        done = done_event(h, folder)
        h.check(f"{lag}: the run finished", done.get("code") == 0, dock.panel.message.text()[:300])
        warned = [e["message"] for e in h.events(folder, "warn")]
        h.check(f"{lag}: the five dams are warned as junctions, lacking a spillway", sum("spillways" in w for w in warned) == 5, warned[:3])
        b = done.get("balance", {})
        h.check(f"{lag}: no rain on the grid but the unassigned ground", b.get("rain_m3", 1e12) < 0.15 * b.get("inflow_m3", 1), (b.get("rain_m3"), b.get("inflow_m3")))
        h.check(f"{lag}: mass closes", abs(b.get("relative_error", 1)) < 1e-6, b.get("relative_error"))
        peaks[f"generated_{lag}"] = {dam: network_peak(folder, dam) for dam in DAMS}
        h.log(f"peaks {lag}: {peaks[f'generated_{lag}']}")
        h.check(f"{lag}: a peak at every dam", all(peaks[f"generated_{lag}"].values()), peaks[f"generated_{lag}"])

    h.log("=== the HMS project, lumped, the same storm")
    folder = h.RUNS / "block2_hms"
    dock.panel.folder.setFilePath(str(folder))
    hy.folder.setFilePath(str(h.BLOCK / "HEC_HMS_Block_02"))
    hy.files["basin"].setCurrentText("Basin_1.basin")
    hy.files["met"].setCurrentText("FM_100yr.met")
    hy.files["control"].setCurrentText("Control_1.control")
    h.check("the basin box is off under the HMS project", not box.isChecked() and not box.isEnabled())
    h.check("18 HMS subbasins, all lumped", hy.table.rowCount() == 18 and all(hy.table.cellWidget(r, 1).currentText() == "lumped" for r in range(18)))
    yield from h.run(dock, limit=2000)
    done = done_event(h, folder)
    h.check("the HMS run finished", done.get("code") == 0, dock.panel.message.text()[:300])
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    h.check("the HMS run has the same storm", job["storm"]["depth_mm"] == storm["depth_mm"] and abs(job["storm"]["storm_area_km2"] - storm["storm_area_km2"]) < 0.1, (job["storm"]["depth_mm"], job["storm"].get("storm_area_km2")))
    peaks["hms"] = {dam: network_peak(folder, dam) for dam in DAMS}
    peaks["hms_2d_lines"] = h.peaks(folder)
    h.log(f"peaks hms: {peaks['hms']}")
    h.check("a network peak at every HMS dam", all(peaks["hms"].values()), peaks["hms"])
    ratios = {}
    for key in ("generated_nrcs", "generated_hms_kirpich"):
        ratios[key] = {dam: round(peaks[key][dam]["peak_m3s"] / peaks["hms"][dam]["peak_m3s"], 3) for dam in DAMS if peaks[key][dam] and peaks["hms"][dam]}
    h.log(f"ratios to HMS: {ratios}")
    h.check("the HMS-style lag reads closer to HMS than NRCS at every dam", all(abs(ratios["generated_hms_kirpich"][d] - 1.0) < abs(ratios["generated_nrcs"][d] - 1.0) for d in DAMS), ratios)
    (h.P / "block2_peaks.json").write_text(json.dumps({"peaks": peaks, "ratios": ratios, "storm_area_km2": storm["storm_area_km2"], "dx": DX}, indent=1), encoding="utf-8")
