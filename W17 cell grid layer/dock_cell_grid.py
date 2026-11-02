"""D2 through the real dock: the real cell grid in Model setup after every kind of run."""

import json

from qgis.core import QgsProject


def grid_layer(h, run):
    group = h.group_of(run)
    setup = group.findGroup("Model setup") if group else None
    if setup is None:
        return None
    found = [node.layer() for node in setup.findLayers() if node.layer().name().startswith("Cell grid")]
    return found[0] if found else None


def cells_in(layer):
    return sum(f["cells"] for f in layer.getFeatures())


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()

    h.log("=== 1 a uniform run")
    h.set_rain_job(dock, ground, "uniform")
    yield from h.run(dock)
    folder = h.RUNS / "uniform"
    start = h.events(folder, "start")[-1]
    h.check("finished", h.events(folder, "done")[-1]["code"] == 0, dock.panel.message.text())
    layer = grid_layer(h, "uniform")
    h.check("cell grid under Model setup", layer is not None)
    h.check("name says the size and the scale", layer.name() == "Cell grid, 20 m, drawn from 1:20,000 in", layer.name())
    h.check("the cells are the solver's", cells_in(layer) == start["cells"], (cells_in(layer), start["cells"]))
    h.check("one feature per tile", layer.featureCount() == start["tiles"], (layer.featureCount(), start["tiles"]))
    h.check("ticked on", QgsProject.instance().layerTreeRoot().findLayer(layer).isVisible())
    h.check("draws only near enough", layer.hasScaleBasedVisibility() and layer.minimumScale() == 20000, layer.minimumScale())
    h.check("the layer is in the DEM's CRS", layer.crs() == ground.crs, layer.crs().authid())
    box, extent = layer.extent(), ground.domain.extent()
    h.check("covers the domain", box.width() >= extent.width() - 40 and box.height() >= extent.height() - 40, box.toString(0))
    h.check("on no map sheet", all("Cell grid" not in ly.name() for ly in _setup_list(folder)))

    middle = layer.getFeature(1).geometry().boundingBox().center()
    depth = [ly for ly in QgsProject.instance().mapLayers().values() if ly.name() == "Maximum depth, m"][0]
    h.render("near", [layer, depth, ground.dem], middle, 4000)
    h.render("far", [layer, depth, ground.dem], middle, 100000)

    h.log("=== 2 pixel maps off: no products, the grid all the same")
    h.set_rain_job(dock, ground, "no_pixels", sim_hours=0.3, pixels=False)
    yield from h.run(dock)
    h.check("no pixel maps", not (h.RUNS / "no_pixels" / "pixels").exists())
    h.check("grid without products", grid_layer(h, "no_pixels") is not None)

    h.log("=== 3 stopped in mid run")
    h.set_rain_job(dock, ground, "stopped", sim_hours=48.0, pixels=False)
    dock.panel.run_button.click()
    yield lambda: dock.run is not None
    yield lambda: dock.panel.bar.value() >= 1
    dock.panel.stop_button.click()
    yield h.idle(dock, 120)
    h.check("stopped", "topped" in dock.panel.message.text(), dock.panel.message.text())
    h.check("grid of a stopped run", grid_layer(h, "stopped") is not None)

    h.log("=== 4 a mesh: tiles at their own sizes")
    m = dock.mesh
    m.setCollapsed(False)
    h.set_rain_job(dock, ground, "mesh", dx=10.0, sim_hours=0.3, pixels=False)
    m.enabled.setChecked(True)
    m.coarse.setValue(40.0)
    yield from h.run(dock)
    folder = h.RUNS / "mesh"
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    h.check("the job is a mesh", job["mesh"]["enabled"], job.get("mesh"))
    layer = grid_layer(h, "mesh")
    start = h.events(folder, "start")[-1]
    h.check("mesh name gives the range", layer.name() == "Cell grid, 10 to 40 m, drawn from 1:10,000 in", layer.name())
    h.check("mesh cells are the solver's", cells_in(layer) == start["cells"], (cells_in(layer), start["cells"]))
    sizes = sorted({f["cell_m"] for f in layer.getFeatures()})
    h.check("three sizes", sizes == [10.0, 20.0, 40.0], sizes)
    h.render("mesh", [layer, ground.dem], layer.extent().center(), 9000)
    m.enabled.setChecked(False)

    h.log("=== 5 Make map still works beside it")
    h.set_rain_job(dock, ground, "sheets", sim_hours=1.0)
    yield from h.run(dock)
    dock.panel.map_button.click()
    yield lambda: "Map written" in dock.panel.message.text()
    pdf = list((h.RUNS / "sheets" / "pixels").glob("*_maps.pdf"))
    h.check("pdf written", pdf and pdf[0].stat().st_size > 100000, dock.panel.message.text())


def _setup_list(folder):
    from wadi2d_qgis.result_layers import open_layers

    return open_layers(folder).setup()
