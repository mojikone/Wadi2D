"""W50 through the real dock on Bidah at 20 m: the smooth polygons and depth picture as a tick, off by default.

1. The tick: there, unticked, greyed out with the pixel maps off.
2. A run with it off: the rasters of record and the setup layers load, no Flood maps group, the record depth shown;
   Make map has the engine draw the polygons and the picture first, with progress, then writes the sheets; the run's
   own files stay as they were.
3. A run with it on: the drawing comes with the run, Flood maps loads, Make map writes the sheets with no engine call.

    powershell -File tests\\dock\\run_check.ps1 "<full path>\\W50 products speed and time slider maps\\dock_smooth_option.py" <throwaway folder> -Copy "<full path>\\W50 products speed and time slider maps"
"""

import json
import sqlite3
from pathlib import Path

MAIN_VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
"""The worktree has no environment of its own; the engine still runs this checkout (run_check's engine.py)."""


def layers_of(run):
    path = run / "pixels" / "map_layers.gpkg"
    if not path.is_file():
        return set()
    with sqlite3.connect(path) as db:
        return {row[0] for row in db.execute("SELECT table_name FROM gpkg_contents")}


def child_names(h, name):
    top = h.group_of(name)
    return [child.name() for child in top.children()] if top is not None else []


def visible(h, name):
    top = h.group_of(name)
    return [n.name() for n in top.findLayers() if n.isVisible()] if top is not None else []


def stamps(run):
    return {p.name: p.stat().st_mtime_ns for p in (run / "pixels").glob("pixel_*.tif")}


def scenario(h):
    h.VENV = MAIN_VENV
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from wadi2d_qgis.result_layers import GROUP_CELLS, GROUP_MAPS, GROUP_RECORD, GROUP_SETUP

    panel = dock.panel

    h.log("=== 1 the tick")
    h.check("the tick is in the Run section", hasattr(panel, "smooth"))
    h.check("it is unticked by default", not panel.smooth.isChecked(), panel.smooth.text())
    h.check("its label is plain", panel.smooth.text() == "Smooth map polygons and depth picture (slower)", panel.smooth.text())
    h.check("its tip says Make map makes them", "Make map" in panel.smooth.toolTip(), panel.smooth.toolTip())
    panel.pixels.setChecked(False)
    h.check("greyed out without the pixel maps", not panel.smooth.isEnabled())
    panel.pixels.setChecked(True)
    h.check("back with them", panel.smooth.isEnabled())

    h.log("=== 2 a run with the tick off")
    h.set_rain_job(dock, ground, "plain", dx=20.0, sim_hours=1.0)
    plain = h.RUNS / "plain"
    yield from h.run(dock)
    h.check("the run finished", (plain / "pixels" / "pixels.json").is_file(), panel.message.text())
    job = json.loads((plain / "job.json").read_text(encoding="utf-8"))
    h.check("the job leaves the default alone", "smooth" not in job.get("outputs", {}), job.get("outputs"))
    h.check("no depth picture", not (plain / "pixels" / "depth_drawing.tif").exists())
    found = layers_of(plain)
    h.check("the setup layers are written, the polygons not", "domain" in found and "hazard_classes" not in found, sorted(found))
    groups = child_names(h, plain.name)
    h.check("setup, record and cells load, no Flood maps", groups == [GROUP_SETUP, GROUP_RECORD, GROUP_CELLS], groups)
    shown = visible(h, plain.name)
    h.check("the depth of record is the one shown", any("depth" in s.lower() for s in shown) and "max_depth" not in shown, shown)
    h.check("Make map is offered", panel.map_button.isEnabled())
    h.shot("plain_loaded")
    before = stamps(plain)
    panel.map_title.setText("Bidah, tick off")
    panel.map_button.click()
    h.check("Make map starts the drawing", dock.drawing is not None, panel.message.text())
    h.check("it says why", "smooth polygons" in panel.message.text(), panel.message.text())
    h.check("Run waits meanwhile", not panel.run_button.isEnabled())
    seen = []

    def drawn():
        if dock.drawing is not None:
            seen.append((panel.bar.value(), panel.status.text()))
        return dock.drawing is None

    yield drawn
    h.log(f"progress seen: {sorted(set(seen))[:3]} .. {sorted(set(seen))[-3:]}")
    h.check("progress was shown", len({v for v, _s in seen}) > 1, sorted({v for v, _s in seen}))
    h.check("it speaks of the drawing, not the run's clock", all(t.startswith("Pixel maps") for _v, t in seen), sorted({t for _v, t in seen}))
    h.check("the sheets were written", (plain / "pixels" / "plain_maps.pdf").is_file() and "Map written" in panel.message.text(), panel.message.text())
    h.check("the picture and the polygons are there now", (plain / "pixels" / "depth_drawing.tif").is_file() and "hazard_classes" in layers_of(plain))
    h.check("the rasters of record were not touched", stamps(plain) == before)
    h.check("the run's own engine log is untouched", (plain / "drawings.out").exists() and (plain / "engine.out").exists())
    groups = child_names(h, plain.name)
    h.check("Flood maps join the run's group", groups == [GROUP_SETUP, GROUP_MAPS, GROUP_RECORD, GROUP_CELLS], groups)
    shown = visible(h, plain.name)
    h.check("the picture takes over from the depth of record", "Maximum depth, m" in shown and "AIDR hazard class" not in shown, shown)
    h.check("Run is free again", panel.run_button.isEnabled())
    h.shot("plain_drawn")
    panel.map_button.click()
    h.check("a second Make map draws nothing again", dock.drawing is None and "Map written" in panel.message.text(), panel.message.text())

    h.log("=== 3 a run with the tick on")
    panel.smooth.setChecked(True)
    panel.folder.setFilePath(str(h.RUNS / "ticked"))
    ticked = h.RUNS / "ticked"
    yield from h.run(dock)
    job = json.loads((ticked / "job.json").read_text(encoding="utf-8"))
    h.check("the job asks for them", job["outputs"].get("smooth") == {"enabled": True}, job["outputs"].get("smooth"))
    h.check("the picture comes with the run", (ticked / "pixels" / "depth_drawing.tif").is_file() and "hazard_classes" in layers_of(ticked))
    groups = child_names(h, ticked.name)
    h.check("Flood maps load with the run", groups == [GROUP_SETUP, GROUP_MAPS, GROUP_RECORD, GROUP_CELLS], groups)
    panel.map_title.setText("Bidah, tick on")
    panel.map_button.click()
    h.check("Make map needs no engine", dock.drawing is None and "Map written" in panel.message.text(), panel.message.text())
    h.shot("ticked")
