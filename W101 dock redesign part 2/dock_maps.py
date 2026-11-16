"""W101, his item 7, through the real dock: the map controls.

The pixel of the maps of record (empty is the engine's rule), the depth x speed raster (off by default), no choice of
surface (the continuous one is the engine's default and the dock writes none), a window of a finished run mapped at
the terrain's finest resolution, and a Lumped model's Terrain asking for no cell size, Manning or pit fill.
"""

import json
from pathlib import Path


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w101_help", Path(h.SCENARIO).parent / "w101_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from qgis.core import QgsProject, QgsRasterLayer
    from qgis.PyQt.QtWidgets import QLabel

    panel, terrain = dock.panel, dock.terrain
    out = h.RUNS / "built"
    pixel = ground.dem.rasterUnitsPerPixelX()

    h.log("=== 1 the controls and the job at their defaults")
    h.set_rain_job(dock, ground, "maps", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=True)
    panel.setCollapsed(False)
    h.check("Map pixel, Automatic first", panel.map_pixel.value() == 0.0 and panel.map_pixel.text() == "Automatic", panel.map_pixel.text())
    h.check("the depth x speed raster off", not panel.dv_raster.isChecked() and panel.dv_raster.text() == "Depth x speed raster")
    shown = [label.text() for label in panel.findChildren(QLabel) if label.isVisibleTo(panel)]
    h.check("no choice of surface is offered", not any("urface" in text for text in shown), shown)
    job = w.built(dock, out)
    h.check("at the defaults the job holds no pixel settings", "pixels" not in job["outputs"], job["outputs"])
    h.check("the window button named for the terrain's own resolution", panel.window_button.text() == "Map a window at the terrain's finest resolution")
    h.check("its tooltip gives this DEM's pixel", f"{pixel:g} m on this DEM" in panel.window_button.toolTip(), panel.window_button.toolTip())
    h.check("no window before a run", not panel.window_button.isEnabled())

    h.log("=== 2 Lumped asks Terrain for no cell size, Manning or pit fill")
    for kind, hidden in (("lumped", True), ("2d", False), (None, False)):
        dock.types.choose(kind)
        h.check(f"{kind}: cell size, Manning, pit fill {'hidden' if hidden else 'shown'}", all(widget.isVisibleTo(terrain) != hidden for widget in (terrain.dx, terrain.manning, terrain.fill_pits)) and (terrain.form.labelForField(terrain.dx).isVisibleTo(terrain) != hidden))
    dock.types.choose("lumped")
    w.big_shot(h, dock, "terrain_lumped", open_only="terrain")
    dock.types.choose(None)

    h.log("=== 3 a run with a pixel of 10 m and the depth x speed raster")
    panel.map_pixel.setValue(10.0)
    panel.dv_raster.setChecked(True)
    job = w.built(dock, out)
    h.check("the job holds both, the engine takes them", job["outputs"]["pixels"] == {"pixel_m": 10.0, "dv_raster": True} and w.validated(job).outputs.pixels.surface == "continuous", job["outputs"])
    panel.backend.setCurrentIndex(panel.backend.findData("cpu"))
    w.big_shot(h, dock, "run_maps", open_only="run")
    yield from h.run(dock)
    run = dock.results_dir
    done = h.events(run, "done")
    h.check("finished", bool(done) and done[-1].get("code") == 0, panel.message.text())
    depth = QgsRasterLayer(str(run / "pixels" / "pixel_depth.tif"), "d")
    h.check("the maps of record at 10 m", depth.isValid() and abs(depth.rasterUnitsPerPixelX() - 10.0) < 1e-6, depth.rasterUnitsPerPixelX())
    h.check("the depth x speed raster written", (run / "pixels" / "pixel_dv.tif").is_file())
    h.check("the window button enabled after the run", panel.window_button.isEnabled())

    h.log("=== 4 a window at the terrain's finest resolution")
    box = ground.domain.extent().center()
    window = (box.x() - 400.0, box.y() - 400.0, box.x() + 400.0, box.y() + 400.0)
    dock.window_links.map_box(run, window)
    yield lambda: panel.window_button.isEnabled()
    layers = dock.window_links.layers
    names = [layer.name() for layer in layers]
    h.check("depth, speed and hazard loaded", names == ["Depth, m", "Speed, m/s", "Hazard class"], (names, panel.message.text()))
    h.check("at the DEM's own pixel", bool(layers) and abs(layers[0].rasterUnitsPerPixelX() - pixel) < 1e-6, [layer.rasterUnitsPerPixelX() for layer in layers])
    h.check("over the window drawn", bool(layers) and layers[0].extent().width() <= 800.0 + 2 * pixel, layers[0].extent().toString() if layers else "")
    root = QgsProject.instance().layerTreeRoot()
    node = root.findLayer(layers[0].id()) if layers else None
    h.check("in the run's group", node is not None and "Window at the DEM pixel" in node.parent().name(), node.parent().name() if node else None)
    h.check("the run's own maps untouched", abs(QgsRasterLayer(str(run / "pixels" / "pixel_depth.tif"), "d").rasterUnitsPerPixelX() - 10.0) < 1e-6)
    h.check("the model beside the job holds the settings", json.loads((run / "model.wadi2d.json").read_text(encoding="utf-8"))["sections"]["run"]["widgets"]["map_pixel"] == 10.0)
