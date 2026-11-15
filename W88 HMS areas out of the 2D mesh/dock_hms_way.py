"""W88 through the real dock, CPU engine: the HMS way (lumped-only run), the lumped water on the network with the
carried catchments left out of the mesh, the network in a run's group, the depth display cutoff and Make map.

1. Block 2's HMS project (Basin_1, FM_100yr), "The HMS way only" and "each element at its own area": the run is the
   lumped network alone; it opens with its network layers labelled with peaks, the time-slider buttons off, Result
   lines listing every element, a right-click name under a junction matching its entry, the chart's peak the record's.
2. Opening that folder again in a fresh project brings its network back.
3. Bidah at 20 m: S13 rain-on-grid, every other subbasin lumped "down the HMS reaches", the exclude tick on: the job
   carries both, the carried catchments are left out, the network layer marks them, the depth layers are cut at the
   0.05 m default, a new cutoff restyles them, Make map writes the sheets with the cutoff in their notes.

    powershell -File tests\\dock\\run_check.ps1 "<full path>\\W88 HMS areas out of the 2D mesh\\dock_hms_way.py" <throwaway folder> -Copy "<full path>\\W88 HMS areas out of the 2D mesh"
"""

import csv
import json
from pathlib import Path

MAIN_VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
"""The worktree has no environment of its own; the engine still runs this checkout (run_check's engine.py)."""


def settled(lines):
    return lambda: lines.query is None and not lines.waiting


def group_names(h, run):
    top = h.group_of(f"Results \N{EN DASH} {run.name}")
    return [child.name() for child in top.children()] if top is not None else []


def network_layers(run_name):
    from qgis.core import QgsProject
    from wadi2d_qgis.network_layers import TITLES

    found = {}
    for layer in QgsProject.instance().mapLayers().values():
        for key, title in TITLES.items():
            if layer.name() == title and run_name in layer.source():
                found[key] = layer
    return found


def scenario(h):
    h.VENV = MAIN_VENV
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from qgis.core import QgsPointXY
    from wadi2d_qgis import settings, style
    from wadi2d_qgis.element_view import matching
    from wadi2d_qgis.layer_groups import NETWORK

    panel, y, storm = dock.panel, dock.hydrology, dock.storm
    panel.backend.setCurrentIndex(panel.backend.findData("cpu"))
    hills = h.BLOCK / "HEC_HMS_Block_02"

    h.log("=== 1 the HMS way only")
    h.check("the dock has the three HMS-way controls", all(hasattr(y, n) for n in ("lumped_entry", "lumped_only", "arf_by_element")))
    dock.terrain.dem.setLayer(ground.dem)
    dock.terrain.domain.setLayer(ground.domain)
    dock.terrain.dx.setValue(20.0)
    y.folder.setFilePath(str(hills))
    yield lambda: y.files["basin"].count() > 0
    y.files["basin"].setCurrentText("Basin_1.basin")
    y.files["met"].setCurrentText("FM_100yr.met")
    storm.kind.setCurrentIndex(storm.kind.findData("hms"))
    choices = [y.lumped_entry.itemData(i) for i in range(y.lumped_entry.count())]
    h.check("the lumped entry choices are the engine's", choices == ["outlet", "network"], choices)
    h.check("the arf tick waits for the HMS way", not y.arf_by_element.isEnabled())
    y.lumped_only.setChecked(True)
    h.check("then it is offered, and the network choices step aside", y.arf_by_element.isEnabled() and not y.lumped_entry.isEnabled() and not y.exclude.isEnabled())
    y.arf_by_element.setChecked(True)
    dock.boundaries.layer.setLayer(ground.mixed)
    dock.points.layer.setLayer(None)
    panel.duration.setValue(48.0)
    lumped = h.RUNS / "hms_way"
    panel.folder.setFilePath(str(lumped))
    yield from h.run(dock, 600)
    done = h.events(lumped, "done")
    h.check("the lumped-only run finished", done and done[-1].get("code") == 0 and done[-1].get("lumped_only"), panel.message.text())
    job = json.loads((lumped / "job.json").read_text(encoding="utf-8"))
    h.check("the job asks for the HMS way and each element's area", job["run"].get("lumped_only") is True and job["hydrology"].get("arf_by_element") is True, (job["run"], job["hydrology"].get("arf_by_element")))
    h.check("it wrote no grid", not (lumped / "maps").exists() and (lumped / "lumped_run.json").is_file())
    h.check("its group holds the network", NETWORK in group_names(h, lumped), group_names(h, lumped))
    found = network_layers(lumped.name)
    h.check("subbasins and junctions are loaded", {"subbasins", "points"} <= set(found), sorted(found))
    subs = found.get("subbasins")
    labels = [f["label"] for f in subs.getFeatures()] if subs is not None else []
    h.check("18 catchments, each labelled with area and peak", len(labels) == 18 and all("km2" in t and "m3/s" in t for t in labels), labels[:2])
    h.check("Time slider buttons are off, Result lines on", not panel.frames_button.isEnabled() and not panel.pixel_frames_button.isEnabled() and panel.lines_button.isEnabled())
    with (lumped / "network_peaks.csv").open(encoding="utf-8") as f:
        peaks = {row["element"]: row for row in csv.DictReader(f)}
    h.check("each element read at its own area", abs(float(peaks["Bidah 03"]["storm_area_km2"]) - float(peaks["Bidah 03"]["drainage_km2"])) < 1e-6, peaks["Bidah 03"]["storm_area_km2"])
    h.log("peaks: " + ", ".join(f"{k} {float(v['outflow_peak_m3s']):.1f}" for k, v in peaks.items() if k in ("Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C")))
    panel.lines_button.click()
    lines = dock.line_panel
    yield settled(lines)
    labels = [lines.choice.itemText(i) for i in range(lines.choice.count())]
    h.check("Result lines lists the elements", "Lumped element: Bidah 03" in labels and len(labels) >= 40, len(labels))
    points = found.get("points")
    bidah = next((f for f in points.getFeatures() if f["name"] == "Bidah 03"), None) if points is not None else None
    if bidah is not None:
        from qgis.utils import iface

        where = bidah.geometry().asPoint()
        iface.mapCanvas().setDestinationCrs(points.crs())
        iface.mapCanvas().setCenter(QgsPointXY(where))
        iface.mapCanvas().zoomScale(20000)
        iface.mapCanvas().refresh()
        names = lines.names_under(QgsPointXY(where))
        hit = matching(lines.items, names)
        h.check("a right-click on the dam's junction finds its chart", hit and lines.items[hit[0]].name == "Bidah 03", names[:4])
        if hit:
            lines.show_entry(hit[0])
            yield settled(lines)
            view = lines.plot.view
            peak = max(view.charts[0].curves[0].values) if view is not None else -1.0
            record = float(peaks["Bidah 03"]["outflow_peak_m3s"])
            h.check("its chart holds the run's peak", abs(peak - record) <= 1e-3 * record + 1e-3, (peak, record))
            h.widget_shot("bidah03_chart", lines.plot)
    h.shot("hms_way")

    h.log("=== 2 the folder opened again")
    top = h.group_of(f"Results \N{EN DASH} {lumped.name}")
    if top is not None:
        top.parent().removeChildNode(top)
    panel.folder.setFilePath("")
    panel.folder.setFilePath(str(lumped))
    yield lambda: True
    h.check("choosing the folder brings the network back", NETWORK in group_names(h, lumped), group_names(h, lumped))

    h.log("=== 3 S13 on the grid, the rest down the reaches, the carried catchments left out")
    y.lumped_only.setChecked(False)
    h.check("the network choices come back", y.lumped_entry.isEnabled() and y.exclude.isEnabled())
    y.lumped_entry.setCurrentIndex(y.lumped_entry.findData("network"))
    y.exclude.setChecked(True)
    rows = {y.table.item(r, 0).text(): r for r in range(y.table.rowCount())}
    y.table.cellWidget(rows["S13"], 1).setCurrentText("2d")
    panel.duration.setValue(1.5)
    panel.pixels.setChecked(True)
    hybrid = h.RUNS / "hybrid"
    panel.folder.setFilePath(str(hybrid))
    yield from h.run(dock, 1500)
    done = h.events(hybrid, "done")
    h.check("the hybrid finished", done and done[-1].get("code") == 0, panel.message.text())
    job = json.loads((hybrid / "job.json").read_text(encoding="utf-8"))
    h.check("the job asks for both", job["hydrology"].get("lumped_entry") == "network" and job["grid"].get("exclude_lumped") is True)
    resolved = json.loads((hybrid / "config.resolved.json").read_text(encoding="utf-8"))
    leaving = [i["element"] for i in resolved["hydrology"]["inflows"] if not i.get("enters", True)]
    # Bidah 03 takes S13's water on the grid, so it is not lumped all the way: no inflow there
    h.check("the other dams' water leaves at the network's outlets", sorted(leaving) == ["Faydh 01", "R2A", "R5A", "Z4C"], leaving)
    said = h.events(hybrid, "left_out")
    h.check("the run names what it left out", said and "S13" not in said[-1]["subbasins"] and len(said[-1]["subbasins"]) == 17, said[-1] if said else None)
    found = network_layers(hybrid.name)
    subs = found.get("subbasins")
    out = {f["name"]: f["left_out"] for f in subs.getFeatures()} if subs is not None else {}
    h.check("the network layer marks them left out", len(out) == 17 and all(v == 1 for v in out.values()), out)
    from qgis.core import QgsProject as Project

    depth = [layer for layer in Project.instance().mapLayers().values() if layer.customProperty(style.DEPTH_STYLE)]
    h.check("depth layers are styled by the cutoff", depth, [layer.name() for layer in depth])
    cut = [layer.renderer().shader().rasterShaderFunction() for layer in depth if hasattr(layer.renderer(), "shader")]
    h.check("cut at the 0.05 m default", cut and all(s.clip() and abs(s.minimumValue() - 0.05) < 1e-9 for s in cut), [s.minimumValue() for s in cut])
    panel.cutoff.setValue(0.1)
    h.check("the cutoff is saved", abs(settings.depth_cutoff() - 0.1) < 1e-9, settings.depth_cutoff())
    cut = [layer.renderer().shader().rasterShaderFunction() for layer in depth if hasattr(layer.renderer(), "shader")]
    h.check("a new cutoff restyles them", cut and all(abs(s.minimumValue() - 0.1) < 1e-9 for s in cut), [s.minimumValue() for s in cut])
    h.shot("hybrid")
    panel.map_button.click()

    def drawn():
        return (dock.drawing is None and "Map written" in panel.message.text()) or "not made" in panel.message.text()

    yield drawn
    pdf = hybrid / "pixels" / f"{hybrid.name}_maps.pdf"
    h.check("Make map wrote the sheets", pdf.is_file() and "Map written" in panel.message.text(), panel.message.text())
    book = getattr(dock, "_book", None)
    texts = []
    if book is not None:
        from qgis.core import QgsLayoutItemLabel

        texts += [item.text() for item in book.layout.items() if isinstance(item, QgsLayoutItemLabel)]
    h.log(f"{len(texts)} sheet labels read")
    h.check("the depth sheet says the cutoff", any("Depth under 0.1 m is not drawn" in t for t in texts), len(texts))
    panel.cutoff.setValue(style.DEPTH_CUTOFF_M)
